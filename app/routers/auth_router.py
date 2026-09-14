from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import clear_session_cookie, create_session_cookie
from app.config import ASSET_VERSION, settings

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["asset_version"] = ASSET_VERSION


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login_submit(request: Request, code: str = Form(...)):
    if code != settings.INVITE_CODE:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Código incorrecto"},
            status_code=401,
        )
    response = RedirectResponse(url="/admin/photos", status_code=303)
    create_session_cookie(response)
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(response)
    return response
