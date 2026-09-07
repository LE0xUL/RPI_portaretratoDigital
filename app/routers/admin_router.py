from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.image_utils import delete_photo_files, save_upload
from app.models import Album, Photo, Settings

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])
templates = Jinja2Templates(directory="templates")


def _get_settings(db: Session) -> Settings:
    settings_row = db.get(Settings, 1)
    if settings_row is None:
        settings_row = Settings(id=1)
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
    return settings_row


# ---------- Fotos ----------

@router.get("/photos", response_class=HTMLResponse)
def photos_page(request: Request, db: Session = Depends(get_db)):
    photos = db.scalars(select(Photo).order_by(Photo.created_at.desc())).all()
    return templates.TemplateResponse(request, "admin/photos.html", {"photos": photos})


@router.post("/photos", response_class=HTMLResponse)
def upload_photos(request: Request, files: list[UploadFile], db: Session = Depends(get_db)):
    for upload in files:
        filename, width, height, size_bytes = save_upload(upload.file)
        db.add(
            Photo(
                filename=filename,
                original_filename=upload.filename or filename,
                width=width,
                height=height,
                file_size_bytes=size_bytes,
            )
        )
    db.commit()
    photos = db.scalars(select(Photo).order_by(Photo.created_at.desc())).all()
    return templates.TemplateResponse(request, "admin/_photo_grid.html", {"photos": photos})


@router.delete("/photos/{photo_id}", response_class=HTMLResponse)
def delete_photo(request: Request, photo_id: int, db: Session = Depends(get_db)):
    photo = db.get(Photo, photo_id)
    if photo is not None:
        delete_photo_files(photo.filename)
        db.delete(photo)
        db.commit()
    photos = db.scalars(select(Photo).order_by(Photo.created_at.desc())).all()
    return templates.TemplateResponse(request, "admin/_photo_grid.html", {"photos": photos})


# ---------- Álbumes ----------

@router.get("/albums", response_class=HTMLResponse)
def albums_page(request: Request, db: Session = Depends(get_db)):
    albums = db.scalars(select(Album).order_by(Album.created_at.desc())).all()
    return templates.TemplateResponse(request, "admin/albums.html", {"albums": albums})


@router.post("/albums", response_class=HTMLResponse)
def create_album(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    db.add(Album(name=name.strip()))
    db.commit()
    albums = db.scalars(select(Album).order_by(Album.created_at.desc())).all()
    return templates.TemplateResponse(request, "admin/_album_list.html", {"albums": albums})


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
    return templates.TemplateResponse(request, "admin/_album_list.html", {"albums": albums})


@router.delete("/albums/{album_id}", response_class=HTMLResponse)
def delete_album(request: Request, album_id: int, db: Session = Depends(get_db)):
    album = db.get(Album, album_id)
    if album is not None:
        db.delete(album)
        db.commit()
    albums = db.scalars(select(Album).order_by(Album.created_at.desc())).all()
    return templates.TemplateResponse(request, "admin/_album_list.html", {"albums": albums})


@router.get("/albums/{album_id}", response_class=HTMLResponse)
def album_detail(request: Request, album_id: int, db: Session = Depends(get_db)):
    album = db.get(Album, album_id)
    photos = db.scalars(select(Photo).order_by(Photo.created_at.desc())).all()
    member_ids = {p.id for p in album.photos} if album else set()
    return templates.TemplateResponse(
        request,
        "admin/album_detail.html",
        {"album": album, "photos": photos, "member_ids": member_ids},
    )


@router.post("/albums/{album_id}/photos/{photo_id}", response_class=HTMLResponse)
def add_photo_to_album(
    request: Request, album_id: int, photo_id: int, db: Session = Depends(get_db)
):
    album = db.get(Album, album_id)
    photo = db.get(Photo, photo_id)
    if album is not None and photo is not None and photo not in album.photos:
        album.photos.append(photo)
        db.commit()
    return _album_detail_response(request, db, album_id)


@router.delete("/albums/{album_id}/photos/{photo_id}", response_class=HTMLResponse)
def remove_photo_from_album(
    request: Request, album_id: int, photo_id: int, db: Session = Depends(get_db)
):
    album = db.get(Album, album_id)
    photo = db.get(Photo, photo_id)
    if album is not None and photo is not None and photo in album.photos:
        album.photos.remove(photo)
        db.commit()
    return _album_detail_response(request, db, album_id)


def _album_detail_response(request: Request, db: Session, album_id: int):
    album = db.get(Album, album_id)
    photos = db.scalars(select(Photo).order_by(Photo.created_at.desc())).all()
    member_ids = {p.id for p in album.photos} if album else set()
    return templates.TemplateResponse(
        request,
        "admin/_album_photo_grid.html",
        {"album": album, "photos": photos, "member_ids": member_ids},
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
    transition_effect: str = Form("fade"),
    image_fit: str = Form("cover"),
    display_orientation: str = Form("landscape"),
    show_clock: bool = Form(False),
    show_date: bool = Form(False),
    show_weather: bool = Form(False),
    weather_latitude: float | None = Form(None),
    weather_longitude: float | None = Form(None),
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
    settings_row.transition_effect = transition_effect
    settings_row.image_fit = image_fit
    settings_row.display_orientation = display_orientation
    settings_row.show_clock = show_clock
    settings_row.show_date = show_date
    settings_row.show_weather = show_weather
    settings_row.weather_latitude = weather_latitude
    settings_row.weather_longitude = weather_longitude
    settings_row.weather_location_name = weather_location_name
    settings_row.weather_units = weather_units
    settings_row.schedule_enabled = schedule_enabled
    settings_row.schedule_off_time = schedule_off_time or None
    settings_row.schedule_on_time = schedule_on_time or None
    db.commit()
    db.refresh(settings_row)
    return templates.TemplateResponse(request, "admin/settings.html", {"settings": settings_row, "saved": True})
