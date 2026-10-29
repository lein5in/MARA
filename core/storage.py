import os
import shutil
import tempfile
from pathlib import Path

from core.log import get_logger
log = get_logger(__name__)


def atomic_write_bytes(path: Path, data: bytes):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _copy_atomic(src: Path, dst: Path):
    atomic_write_bytes(dst, src.read_bytes())
    log.info(f"[Data] Migrated {src.name} -> {dst}")


def migrate_legacy_data(data_dir: Path, key: tuple[Path, Path], encrypted: list[tuple[Path, Path]], plain: list[tuple[Path, Path]]):
    """Copy (never move) legacy files into data_dir. Each pair is (legacy, new).
    Encrypted files are only copied together with the key, enc files first and key last."""
    data_dir.mkdir(parents=True, exist_ok=True)

    key_old, key_new = key
    if key_old.exists() and not key_new.exists():
        pending = [(o, n) for o, n in encrypted if o.exists() and not n.exists()]
        try:
            for old, new in pending:
                _copy_atomic(old, new)
            _copy_atomic(key_old, key_new)
        except OSError as e:
            log.error(f"[Data] Key/memory migration failed: {e}")
            for _, new in pending:
                if new.exists() and not key_new.exists():
                    try:
                        new.unlink()
                    except OSError:
                        pass

    for old, new in plain:
        if old.exists() and not new.exists():
            try:
                _copy_atomic(old, new)
            except OSError as e:
                log.error(f"[Data] Migration of {old.name} failed: {e}")


def copy_if_missing(src: Path, dst: Path) -> bool:
    if dst.exists() or not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return True
