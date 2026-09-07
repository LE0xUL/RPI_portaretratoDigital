import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return uuid.uuid4().hex


album_photos = Table(
    "album_photos",
    Base.metadata,
    Column("album_id", ForeignKey("albums.id", ondelete="CASCADE"), primary_key=True),
    Column("photo_id", ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True),
)


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String, unique=True, default=_uuid)
    original_filename: Mapped[str] = mapped_column(String)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    albums: Mapped[list["Album"]] = relationship(
        secondary=album_photos, back_populates="photos"
    )


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    photos: Mapped[list["Photo"]] = relationship(
        secondary=album_photos, back_populates="albums"
    )


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
