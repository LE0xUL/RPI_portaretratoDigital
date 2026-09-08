import threading

ALLOWED_ACTIONS = {"shutdown", "reboot", "hide"}

_lock = threading.Lock()
_pending: dict | None = None


def request_action(action: str, hide_seconds: int | None = None) -> None:
    global _pending
    with _lock:
        _pending = {"action": action, "hide_seconds": hide_seconds}


def consume_pending_action() -> dict | None:
    """Devuelve la acción pendiente (si hay) y la limpia, para que el poller del
    host la ejecute una sola vez."""
    global _pending
    with _lock:
        pending, _pending = _pending, None
        return pending
