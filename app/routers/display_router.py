import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Album, Photo, Settings
from app.power import consume_pending_action, request_action
from app.schedule import compute_screen_on
from app.schemas import PowerActionIn
from app.weather import get_weather

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _get_settings(db: Session) -> Settings:
    settings_row = db.get(Settings, 1)
    if settings_row is None:
        settings_row = Settings(id=1)
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
    return settings_row


def _active_photos(db: Session) -> list[Photo]:
    """Fotos "activas": las de álbumes activados. Si ninguno está activo, se
    muestra toda la biblioteca (fallback histórico, evita una pantalla negra).

    Una foto de un álbum USB desconectado se excluye -- salvo que ya tenga
    copia local (has_original=True): el punto de "copiar a la biblioteca" es
    justamente que sobreviva a que se desenchufe la unidad, así que una foto
    ya copiada no debería desaparecer solo porque sigue archivada bajo un
    álbum que resulta estar temporalmente desconectado.
    """
    any_active = db.scalars(select(Album.id).where(Album.is_active.is_(True))).first()
    if any_active is None:
        return list(db.scalars(select(Photo).order_by(Photo.created_at.asc())).all())

    return list(
        db.scalars(
            select(Photo)
            .join(Album, Photo.album_id == Album.id)
            .where(
                Album.is_active.is_(True),
                or_(Album.connected.is_(True), Photo.has_original.is_(True)),
            )
            .order_by(Photo.created_at.asc())
        ).all()
    )


@router.get("/display", response_class=HTMLResponse)
def display_page(request: Request):
    return templates.TemplateResponse(request, "display.html", {})


@router.get("/api/display/state")
def display_state(db: Session = Depends(get_db)):
    settings_row = _get_settings(db)
    photos = _active_photos(db)

    photos_version = hashlib.md5(",".join(str(p.id) for p in photos).encode()).hexdigest()
    settings_version = settings_row.updated_at.isoformat()

    return {
        "settings": {
            "slideshow_interval_seconds": settings_row.slideshow_interval_seconds,
            "slideshow_order": settings_row.slideshow_order,
            "transition_effect": settings_row.transition_effect,
            "image_fit": settings_row.image_fit,
            "display_orientation": settings_row.display_orientation,
            "show_clock": settings_row.show_clock,
            "show_date": settings_row.show_date,
            "show_weather": settings_row.show_weather,
            "weather_units": settings_row.weather_units,
        },
        "photos": [
            {
                "id": p.id,
                "display_url": f"/media/photos/display/{p.filename}.jpg",
                "thumb_url": f"/media/photos/thumb/{p.filename}.jpg",
            }
            for p in photos
        ],
        "photos_version": photos_version,
        "settings_version": settings_version,
        "screen_on": compute_screen_on(
            settings_row.schedule_enabled,
            settings_row.schedule_on_time,
            settings_row.schedule_off_time,
            datetime.now(),
        ),
    }


@router.get("/api/display/weather")
def display_weather(db: Session = Depends(get_db)):
    settings_row = _get_settings(db)
    if not settings_row.show_weather or settings_row.weather_latitude is None or settings_row.weather_longitude is None:
        return Response(status_code=204)

    weather = get_weather(
        settings_row.weather_latitude, settings_row.weather_longitude, settings_row.weather_units
    )
    if weather is None:
        return Response(status_code=204)
    return JSONResponse(weather)


@router.get("/api/display/screen-status")
def display_screen_status(db: Session = Depends(get_db)):
    settings_row = _get_settings(db)
    return {
        "screen_on": compute_screen_on(
            settings_row.schedule_enabled,
            settings_row.schedule_on_time,
            settings_row.schedule_off_time,
            datetime.now(),
        )
    }


@router.post("/api/display/power-action")
def post_power_action(payload: PowerActionIn):
    request_action(payload.action, payload.hide_seconds)
    return {"ok": True}


@router.get("/api/display/power-status")
def get_power_status():
    pending = consume_pending_action()
    if pending is None:
        return {"action": None, "hide_seconds": None}
    return pending
