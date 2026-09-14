from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.auth import AdminAuthRequired
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.migrations import migrate_legacy_schema
from app.models import Settings
from app.routers import admin_router, auth_router, display_router, usb_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate_legacy_schema()
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        if db.get(Settings, 1) is None:
            db.add(Settings(id=1))
            db.commit()

    yield


app = FastAPI(title="Portarretrato Digital", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media/photos", StaticFiles(directory=str(settings.photos_dir)), name="media_photos")

app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(usb_router.router)
app.include_router(display_router.router)


@app.exception_handler(AdminAuthRequired)
async def admin_auth_required_handler(request: Request, exc: AdminAuthRequired):
    if request.headers.get("HX-Request") == "true":
        from fastapi.responses import Response

        return Response(status_code=401, headers={"HX-Redirect": "/login"})
    return RedirectResponse(url="/login", status_code=303)


@app.get("/")
def root():
    return RedirectResponse(url="/display")
