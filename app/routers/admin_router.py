from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import ASSET_VERSION
from app.database import get_db
from app.image_utils import delete_photo_files, save_upload
from app.models import Album, Photo, Settings
from app.routers.display_router import _active_photos

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])
templates = Jinja2Templates(directory="templates")
templates.env.globals["asset_version"] = ASSET_VERSION

TRANSITION_EFFECTS = {"none", "fade", "slide", "slide-up", "zoom-in", "zoom-out", "blur"}


def _get_settings(db: Session) -> Settings:
    settings_row = db.get(Settings, 1)
    if settings_row is None:
        settings_row = Settings(id=1)
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
    return settings_row


def _pending_copy_count(db: Session) -> int:
    return len(db.scalars(select(Photo.id).where(Photo.copy_requested_at.is_not(None))).all())


def _local_albums(db: Session) -> list[Album]:
    """Álbumes válidos como destino de upload/mover -- nunca los de USB, que
    el daemon del host gestiona en exclusiva vía app/routers/usb_router.py."""
    return list(
        db.scalars(select(Album).where(Album.usb_volume_id.is_(None)).order_by(Album.name)).all()
    )


def _render_photo_grid(request: Request, db: Session, from_album_id: int | None):
    """Re-renderiza el grid correcto según de dónde vino la acción: el grid de
    un álbum puntual (desde su página de detalle) o el de fotos activas
    (desde la sección "Fotos")."""
    if from_album_id is not None:
        album = db.get(Album, from_album_id)
        if album is None:
            return templates.TemplateResponse(
                request, "admin/_photo_grid.html", {"photos": _active_photos(db), "move_targets": _local_albums(db)}
            )
        return templates.TemplateResponse(
            request,
            "admin/_album_photo_grid.html",
            {"album": album, "photos": album.photos, "move_targets": _local_albums(db)},
        )
    return templates.TemplateResponse(
        request, "admin/_photo_grid.html", {"photos": _active_photos(db), "move_targets": _local_albums(db)}
    )


# ---------- Fotos ----------

@router.get("/photos", response_class=HTMLResponse)
def photos_page(request: Request, db: Session = Depends(get_db)):
    photos = _active_photos(db)
    return templates.TemplateResponse(
        request, "admin/photos.html", {"photos": photos, "move_targets": _local_albums(db)}
    )


@router.post("/photos", response_class=HTMLResponse)
def upload_photos(
    request: Request,
    files: list[UploadFile],
    album_id: int = Form(...),
    db: Session = Depends(get_db),
):
    album = db.get(Album, album_id)
    if album is None or album.usb_volume_id is not None:
        return HTMLResponse("Álbum inválido para subir fotos.", status_code=400)
    for upload in files:
        filename, width, height, size_bytes = save_upload(upload.file)
        db.add(
            Photo(
                filename=filename,
                original_filename=upload.filename or filename,
                width=width,
                height=height,
                file_size_bytes=size_bytes,
                album_id=album.id,
            )
        )
    db.commit()
    return _render_photo_grid(request, db, from_album_id=album.id)


@router.patch("/photos/{photo_id}/album", response_class=HTMLResponse)
def move_photo(
    request: Request,
    photo_id: int,
    album_id: int = Form(...),
    from_album_id: int | None = None,
    db: Session = Depends(get_db),
):
    photo = db.get(Photo, photo_id)
    target = db.get(Album, album_id)
    if (
        photo is not None
        and target is not None
        and target.usb_volume_id is None
        and photo.has_original
    ):
        photo.album_id = target.id
        db.commit()
    return _render_photo_grid(request, db, from_album_id)


@router.delete("/photos/{photo_id}", response_class=HTMLResponse)
def delete_photo(
    request: Request,
    photo_id: int,
    from_album_id: int | None = None,
    db: Session = Depends(get_db),
):
    photo = db.get(Photo, photo_id)
    if photo is not None:
        delete_photo_files(photo.filename)
        db.delete(photo)
        db.commit()
    return _render_photo_grid(request, db, from_album_id)


# ---------- Álbumes ----------

@router.get("/albums", response_class=HTMLResponse)
def albums_page(request: Request, db: Session = Depends(get_db)):
    albums = db.scalars(select(Album).order_by(Album.created_at.desc())).all()
    return templates.TemplateResponse(
        request, "admin/albums.html", {"albums": albums, "pending_copy_count": _pending_copy_count(db)}
    )


@router.post("/albums", response_class=HTMLResponse)
def create_album(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    db.add(Album(name=name.strip()))
    db.commit()
    albums = db.scalars(select(Album).order_by(Album.created_at.desc())).all()
    return templates.TemplateResponse(
        request,
        "admin/_album_list.html",
        {"albums": albums, "error": None, "pending_copy_count": _pending_copy_count(db)},
    )


@router.patch("/albums/{album_id}", response_class=HTMLResponse)
def update_album(
    request: Request,
    album_id: int,
    name: str | None = Form(None),
    is_active: bool = Form(False),
    db: Session = Depends(get_db),
):
    album = db.get(Album, album_id)
    if album is not None:
        if name:
            album.name = name.strip()
        album.is_active = is_active
        db.commit()
    albums = db.scalars(select(Album).order_by(Album.created_at.desc())).all()
    return templates.TemplateResponse(
        request,
        "admin/_album_list.html",
        {"albums": albums, "error": None, "pending_copy_count": _pending_copy_count(db)},
    )


@router.delete("/albums/{album_id}", response_class=HTMLResponse)
def delete_album(request: Request, album_id: int, db: Session = Depends(get_db)):
    album = db.get(Album, album_id)
    error = None
    if album is not None:
        if album.usb_volume_id is not None and album.connected:
            error = 'Desconectá la unidad USB antes de borrar el álbum "{}".'.format(album.name)
        elif album.usb_volume_id is None and len(album.photos) > 0:
            error = 'El álbum "{}" tiene fotos. Moveilas o borralas antes de borrar el álbum.'.format(
                album.name
            )
        else:
            for photo in list(album.photos):
                delete_photo_files(photo.filename)
                db.delete(photo)
            db.delete(album)
            db.commit()
    albums = db.scalars(select(Album).order_by(Album.created_at.desc())).all()
    return templates.TemplateResponse(
        request,
        "admin/_album_list.html",
        {"albums": albums, "error": error, "pending_copy_count": _pending_copy_count(db)},
    )


@router.get("/albums/{album_id}", response_class=HTMLResponse)
def album_detail(request: Request, album_id: int, db: Session = Depends(get_db)):
    album = db.get(Album, album_id)
    return templates.TemplateResponse(
        request,
        "admin/album_detail.html",
        {
            "album": album,
            "photos": album.photos if album else [],
            "move_targets": _local_albums(db),
        },
    )


# ---------- Settings ----------

@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    settings_row = _get_settings(db)
    return templates.TemplateResponse(request, "admin/settings.html", {"settings": settings_row, "saved": False})


@router.post("/settings", response_class=HTMLResponse)
def update_settings(
    request: Request,
    slideshow_interval_seconds: int = Form(15),
    slideshow_order: str = Form("sequential"),
    transition_effects: list[str] = Form([]),
    image_fit: str = Form("cover"),
    display_orientation: str = Form("landscape"),
    show_clock: bool = Form(False),
    show_date: bool = Form(False),
    show_weather: bool = Form(False),
    weather_latitude: str | None = Form(None),
    weather_longitude: str | None = Form(None),
    weather_location_name: str | None = Form(None),
    weather_units: str = Form("metric"),
    schedule_enabled: bool = Form(False),
    schedule_off_time: str | None = Form(None),
    schedule_on_time: str | None = Form(None),
    db: Session = Depends(get_db),
):
    settings_row = _get_settings(db)
    settings_row.slideshow_interval_seconds = slideshow_interval_seconds
    settings_row.slideshow_order = slideshow_order
    valid_effects = [e for e in transition_effects if e in TRANSITION_EFFECTS]
    settings_row.transition_effect = ",".join(valid_effects) if valid_effects else "fade"
    settings_row.image_fit = image_fit
    settings_row.display_orientation = display_orientation
    settings_row.show_clock = show_clock
    settings_row.show_date = show_date
    settings_row.show_weather = show_weather
    settings_row.weather_latitude = float(weather_latitude) if weather_latitude else None
    settings_row.weather_longitude = float(weather_longitude) if weather_longitude else None
    settings_row.weather_location_name = weather_location_name
    settings_row.weather_units = weather_units
    settings_row.schedule_enabled = schedule_enabled
    settings_row.schedule_off_time = schedule_off_time or None
    settings_row.schedule_on_time = schedule_on_time or None
    db.commit()
    db.refresh(settings_row)
    return templates.TemplateResponse(request, "admin/settings.html", {"settings": settings_row, "saved": True})
