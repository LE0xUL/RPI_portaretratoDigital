from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

COOKIE_NAME = "pf_session"
MAX_AGE_SECONDS = 60 * 60 * 24 * 365  # 1 año: no repreguntar el código seguido

_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="pf-session")


def create_session_cookie(response: Response) -> None:
    token = _serializer.dumps({"auth": True})
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,  # LAN, sin HTTPS en el MVP
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


def is_authenticated(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    try:
        _serializer.loads(token, max_age=MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return False
    return True


class AdminAuthRequired(Exception):
    """Señala que la request no trae una sesión válida; el handler en main.py decide cómo redirigir."""


async def require_admin(request: Request):
    if not is_authenticated(request):
        raise AdminAuthRequired()
