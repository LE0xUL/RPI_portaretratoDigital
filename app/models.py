import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return uuid.uuid4().hex


class UsbVolume(Base):
    """Una unidad USB reconocida por el UUID de su filesystem (no por su label,
    que no es estable entre reconexiones ni único entre dispositivos)."""

    __tablename__ = "usb_volumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fs_uuid: Mapped[str] = mapped_column(String, unique=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    connected: Mapped[bool] = mapped_column(Boolean, default=True)

    albums: Mapped[list["Album"]] = relationship(back_populates="usb_volume")


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String, unique=True, default=_uuid)
    original_filename: Mapped[str] = mapped_column(String)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    album_id: Mapped[int] = mapped_column(ForeignKey("albums.id"), nullable=False)
    album: Mapped["Album"] = relationship(back_populates="photos", foreign_keys=[album_id])

    # Proveniencia: fotos "usb" pueden no tener el original guardado todavía
    # (has_original=False), solo variantes display/thumb generadas al vuelo.
    source: Mapped[str] = mapped_column(String, default="local")  # "local" | "usb"
    has_original: Mapped[bool] = mapped_column(Boolean, default=True)
    source_relpath: Mapped[str | None] = mapped_column(String, nullable=True)
    source_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_mtime: Mapped[float | None] = mapped_column(Float, nullable=True)

    # "Copiar a la biblioteca" es un pedido que solo el daemon del host puede
    # cumplir (necesita leer el archivo real desde la USB). Ver app/routers/usb_router.py.
    copy_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pending_target_album_id: Mapped[int | None] = mapped_column(
        ForeignKey("albums.id", ondelete="SET NULL"), nullable=True
    )


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Sin unique=True: álbumes USB se identifican por (usb_volume_id, source_relpath),
    # no por nombre, y carpetas como "DCIM" se repiten entre dispositivos.
    name: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    photos: Mapped[list["Photo"]] = relationship(
        back_populates="album", foreign_keys="Photo.album_id"
    )

    usb_volume_id: Mapped[int | None] = mapped_column(ForeignKey("usb_volumes.id"), nullable=True)
    usb_volume: Mapped["UsbVolume | None"] = relationship(back_populates="albums")
    source_relpath: Mapped[str | None] = mapped_column(String, nullable=True)
    # Denormalizado desde usb_volume.connected para no hacer join en _active_photos().
    # Se actualiza siempre junto con UsbVolume.connected, nunca por separado.
    connected: Mapped[bool] = mapped_column(Boolean, default=True)


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    slideshow_interval_seconds: Mapped[int] = mapped_column(Integer, default=15)
    slideshow_order: Mapped[str] = mapped_column(String, default="sequential")  # sequential|random
    transition_effect: Mapped[str] = mapped_column(String, default="fade")  # fade|slide|none
    image_fit: Mapped[str] = mapped_column(String, default="cover")  # cover|contain
    display_orientation: Mapped[str] = mapped_column(String, default="landscape")  # landscape|portrait

    show_clock: Mapped[bool] = mapped_column(Boolean, default=True)
    show_date: Mapped[bool] = mapped_column(Boolean, default=True)
    show_weather: Mapped[bool] = mapped_column(Boolean, default=False)
    weather_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    weather_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    weather_location_name: Mapped[str | None] = mapped_column(String, nullable=True)
    weather_units: Mapped[str] = mapped_column(String, default="metric")  # metric|imperial

    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_off_time: Mapped[str | None] = mapped_column(String, nullable=True)  # "HH:MM"
    schedule_on_time: Mapped[str | None] = mapped_column(String, nullable=True)  # "HH:MM"

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
