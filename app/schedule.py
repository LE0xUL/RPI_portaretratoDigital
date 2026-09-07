from datetime import datetime, time


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def compute_screen_on(
    schedule_enabled: bool,
    schedule_on_time: str | None,
    schedule_off_time: str | None,
    now: datetime,
) -> bool:
    """True si la pantalla debería estar encendida ahora mismo.

    Maneja ventanas de apagado que cruzan la medianoche (ej. off=22:00, on=07:00).
    """
    if not schedule_enabled or not schedule_on_time or not schedule_off_time:
        return True

    on_t = _parse_hhmm(schedule_on_time)
    off_t = _parse_hhmm(schedule_off_time)
    now_t = now.time()

    if on_t == off_t:
        return True

    if off_t < on_t:
        # Ventana de apagado dentro del mismo día, ej. off=13:00 -> on=15:00
        is_off = off_t <= now_t < on_t
    else:
        # Ventana de apagado cruza medianoche, ej. off=22:00 -> on=07:00
        is_off = now_t >= off_t or now_t < on_t

    return not is_off
