from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.image_utils import promote_to_original, save_variants
from app.models import Album, Photo, UsbVolume
from app.routers.admin_router import _render_photo_grid
from app.schemas import UsbHeartbeatIn, UsbHeartbeatOut, UsbNewFileOut, UsbPendingCopyOut

router = APIRouter(prefix="/admin/usb", dependencies=[Depends(require_admin)])


@router.post("/heartbeat", response_model=UsbHeartbeatOut)
def heartbeat(payload: UsbHeartbeatIn, db: Session = Depends(get_db)):
    """El daemon del host (kiosk-setup/usb-import.py) reporta, cada ~15s, qué
    unidades USB están conectadas ahora mismo y qué archivos de imagen tienen.
    No sube bytes acá -- solo metadata liviana. La respuesta le dice qué
    archivos todavía no están registrados (para subirlos a /photos) y qué
    fotos tienen una copia a biblioteca pendiente (para releerlas del disco y
    postearlas a /photos/{id}/copy-complete)."""
    seen_uuids = {v.fs_uuid for v in payload.volumes}

    for volume in db.scalars(select(UsbVolume).where(UsbVolume.connected.is_(True))).all():
        if volume.fs_uuid not in seen_uuids:
            volume.connected = False
            for album in volume.albums:
                album.connected = False

    new_files: list[UsbNewFileOut] = []

    for v in payload.volumes:
        volume = db.scalars(select(UsbVolume).where(UsbVolume.fs_uuid == v.fs_uuid)).first()
        if volume is None:
            volume = UsbVolume(fs_uuid=v.fs_uuid, label=v.label, connected=True)
            db.add(volume)
            db.flush()
        else:
            volume.connected = True
            volume.label = v.label

        for folder in v.folders:
            album = db.scalars(
                select(Album).where(
                    Album.usb_volume_id == volume.id, Album.source_relpath == folder.relpath
                )
            ).first()
            if album is None:
                folder_name = folder.relpath.rsplit("/", 1)[-1] or folder.relpath
                display_label = v.label or v.fs_uuid[:8]
                album = Album(
                    name=f"{display_label} – {folder_name}",
                    is_active=True,
                    usb_volume_id=volume.id,
                    source_relpath=folder.relpath,
                    connected=True,
                )
                db.add(album)
                db.flush()
            else:
                album.connected = True

            existing_by_relpath = {
                p.source_relpath: p
                for p in db.scalars(select(Photo).where(Photo.album_id == album.id)).all()
            }
            for f in folder.files:
                existing = existing_by_relpath.get(f.relpath)
                if (
                    existing is None
                    or existing.source_size != f.size
                    or existing.source_mtime != f.mtime
                ):
                    new_files.append(
                        UsbNewFileOut(fs_uuid=v.fs_uuid, album_id=album.id, relpath=f.relpath)
                    )

    pending_rows = db.scalars(
        select(Photo)
        .join(Album, Photo.album_id == Album.id)
        .where(
            Photo.copy_requested_at.is_not(None),
            Photo.has_original.is_(False),
            Album.connected.is_(True),
        )
    ).all()
    pending_copies = [
        UsbPendingCopyOut(
            fs_uuid=p.album.usb_volume.fs_uuid,
            photo_id=p.id,
            album_id=p.album_id,
            source_relpath=p.source_relpath,
        )
        for p in pending_rows
        if p.source_relpath is not None and p.album.usb_volume is not None
    ]

    db.commit()
    return UsbHeartbeatOut(new_files=new_files, pending_copies=pending_copies)


@router.post("/photos")
def register_photo(
    album_id: int = Form(...),
    source_relpath: str = Form(...),
    source_size: int = Form(...),
    source_mtime: float = Form(...),
    file: UploadFile = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
):
    """El daemon sube UN archivo nuevo (o cambiado) reportado por /heartbeat.
    Solo se generan variantes display+thumb -- nunca se guarda 'original'
    hasta que el usuario pida explícitamente copiarla a la biblioteca."""
    album = db.get(Album, album_id)
    if album is None or album.usb_volume_id is None:
        raise HTTPException(status_code=409, detail="album_gone")

    existing = db.scalars(
        select(Photo).where(Photo.album_id == album_id, Photo.source_relpath == source_relpath)
    ).first()

    if existing is not None and existing.has_original:
        # ya se copió a la biblioteca antes; no la pisamos con una vista previa vieja
        return {"ok": True, "photo_id": existing.id}

    if existing is not None:
        filename, width, height = save_variants(file.file, ("display", "thumb"), filename=existing.filename)
        existing.width = width
        existing.height = height
        existing.source_size = source_size
        existing.source_mtime = source_mtime
        db.commit()
        return {"ok": True, "photo_id": existing.id}

    filename, width, height = save_variants(file.file, ("display", "thumb"))
    photo = Photo(
        filename=filename,
        original_filename=source_relpath.rsplit("/", 1)[-1],
        width=width,
        height=height,
        file_size_bytes=source_size,
        album_id=album.id,
        source="usb",
        has_original=False,
        source_relpath=source_relpath,
        source_size=source_size,
        source_mtime=source_mtime,
    )
    db.add(photo)
    db.commit()
    return {"ok": True, "photo_id": photo.id}


@router.post("/photos/{photo_id}/copy", response_class=HTMLResponse)
def request_copy_photo(
    request: Request,
    photo_id: int,
    from_album_id: int | None = None,
    target_album_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    """Disparado desde el dashboard (humano). Si la foto ya tiene copia local
    (se pidió antes y el daemon ya la trajo), mover es inmediato -- si no,
    queda pendiente hasta que el daemon la vea en el próximo heartbeat."""
    photo = db.get(Photo, photo_id)
    if photo is not None:
        if photo.has_original:
            if target_album_id is not None:
                photo.album_id = target_album_id
        else:
            photo.copy_requested_at = datetime.now(timezone.utc)
            photo.pending_target_album_id = target_album_id
        db.commit()
    return _render_photo_grid(request, db, from_album_id)


@router.post("/albums/{album_id}/copy", response_class=HTMLResponse)
def request_copy_album(
    request: Request,
    album_id: int,
    target_album_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    album = db.get(Album, album_id)
    if album is not None:
        now = datetime.now(timezone.utc)
        for photo in list(album.photos):
            if photo.has_original:
                if target_album_id is not None:
                    photo.album_id = target_album_id
            else:
                photo.copy_requested_at = now
                photo.pending_target_album_id = target_album_id
        db.commit()
    return _render_photo_grid(request, db, album_id)


@router.post("/photos/{photo_id}/copy-complete")
def copy_complete(photo_id: int, file: UploadFile, db: Session = Depends(get_db)):
    """El daemon releyó el archivo real desde la USB (todavía conectada) y
    manda los bytes originales -- acá se genera por fin el 'original'."""
    photo = db.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="photo_gone")

    width, height, file_size_bytes = promote_to_original(file.file, photo.filename)
    photo.width = width
    photo.height = height
    photo.file_size_bytes = file_size_bytes
    photo.has_original = True
    photo.copy_requested_at = None
    if photo.pending_target_album_id is not None:
        target = db.get(Album, photo.pending_target_album_id)
        if target is not None:
            photo.album_id = target.id
        photo.pending_target_album_id = None
    db.commit()
    return {"ok": True}
