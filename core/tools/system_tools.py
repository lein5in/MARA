from datetime import datetime, timedelta
from zoneinfo import ZoneInfoNotFoundError

from core import system
from core.events import ModeChanged
from core.tools.registry import Registry, ToolError, LOCAL


def _sys(fn, *args):
    try:
        return fn(*args)
    except system.SystemActionError as e:
        raise ToolError(str(e))


def _level(level) -> int:
    try:
        return int(level)
    except (TypeError, ValueError):
        raise ToolError("level must be a number between 0 and 100")


def resolve_pause_target(minutes=None, until=None, now: datetime | None = None) -> datetime:
    now = now or datetime.now().astimezone()
    if minutes is not None and until:
        raise ToolError("give either minutes or until, not both")
    if minutes is not None:
        try:
            minutes = float(minutes)
        except (TypeError, ValueError):
            raise ToolError("minutes must be a number")
        if minutes <= 0:
            raise ToolError("minutes must be positive")
        return now + timedelta(minutes=minutes)
    if until:
        try:
            target = datetime.fromisoformat(str(until))
        except ValueError:
            raise ToolError("until must be an ISO 8601 datetime, e.g. 2026-10-29T21:00")
        if target.tzinfo is None:
            target = target.replace(tzinfo=now.tzinfo)
        if target <= now:
            raise ToolError(f"until is in the past (now is {now.isoformat(timespec='minutes')})")
        return target
    raise ToolError("give minutes or until")


def register(reg: Registry):
    @reg.tool("set_volume", "Set the system output volume (0-100).",
              {"level": {"type": "integer", "minimum": 0, "maximum": 100}}, ["level"], LOCAL)
    def set_volume(ctx, level):
        return f"Volume set to {_sys(system.set_volume, _level(level))}%."

    @reg.tool("get_volume", "Read the current system volume and mute state.")
    def get_volume(ctx):
        level, muted = _sys(system.get_volume)
        return f"Volume is {level}%" + (" (muted)." if muted else ".")

    @reg.tool("set_mute", "Mute or unmute the system sound.",
              {"muted": {"type": "boolean"}}, ["muted"], LOCAL)
    def set_mute(ctx, muted):
        _sys(system.set_mute, bool(muted))
        return "Sound muted." if muted else "Sound unmuted."

    @reg.tool("set_brightness", "Set the screen brightness (0-100).",
              {"level": {"type": "integer", "minimum": 0, "maximum": 100}}, ["level"], LOCAL)
    def set_brightness(ctx, level):
        return f"Brightness set to {_sys(system.set_brightness, _level(level))}%."

    @reg.tool("get_brightness", "Read the current screen brightness.")
    def get_brightness(ctx):
        return f"Brightness is {_sys(system.get_brightness)}%."

    @reg.tool("wifi_connect", "Connect to a known WiFi network. Without ssid, connects to the first known profile.",
              {"ssid": {"type": "string"}}, [], LOCAL)
    def wifi_connect(ctx, ssid=None):
        return _sys(system.wifi_connect, ssid)

    @reg.tool("wifi_disconnect", "Disconnect from the current WiFi network.", risk=LOCAL)
    def wifi_disconnect(ctx):
        return _sys(system.wifi_disconnect)

    @reg.tool("wifi_status", "Check whether WiFi is connected and to which network.")
    def wifi_status(ctx):
        return _sys(system.wifi_status)

    @reg.tool("get_time",
              "Get the real current date and time, locally or in another place. Always use this instead of guessing. "
              "For another city or country pass its IANA timezone (e.g. Asia/Tokyo, America/New_York).",
              {"timezone": {"type": "string", "description": "IANA timezone name. Omit for local time."}})
    def get_time(ctx, timezone=None):
        try:
            current = system.now(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ToolError(f"unknown timezone '{timezone}', use an IANA name like Europe/Paris")
        where = timezone or "local"
        return f"{current.strftime('%A %d %B %Y, %H:%M')} ({where}, UTC{current.strftime('%z')[:3]}:{current.strftime('%z')[3:]})"

    @reg.tool("take_screenshot", "Save a screenshot of the screen to the user's Screenshots folder. Does not let you see it.",
              {"filename": {"type": "string"}}, [], LOCAL)
    def take_screenshot(ctx, filename=None):
        return f"Screenshot saved to {_sys(system.take_screenshot, filename)}."

    @reg.tool("set_silent", "Turn silent mode on or off. In silent mode MARA writes but does not speak.",
              {"on": {"type": "boolean"}}, ["on"], LOCAL)
    def set_silent(ctx, on):
        system.set_silent(bool(on))
        ctx.emit(ModeChanged(system.is_silent(), system.is_vision()))
        return f"Silent mode {'on' if on else 'off'}."

    @reg.tool("pause_mara",
              "Put MARA to sleep for a while when the user asks to be left alone. Give either minutes, or until as an "
              "ISO 8601 local datetime you compute from the current time (call get_time first if unsure). "
              "Never use this as a delay between actions. The user wakes MARA by saying her name.",
              {"minutes": {"type": "number"}, "until": {"type": "string", "description": "ISO 8601 datetime"}},
              [], LOCAL)
    def pause_mara(ctx, minutes=None, until=None):
        target = resolve_pause_target(minutes, until)
        system.set_pause(target, ctx.memory)
        return f"Paused until {target.strftime('%A %H:%M')}. Tell the user when you will be back."
