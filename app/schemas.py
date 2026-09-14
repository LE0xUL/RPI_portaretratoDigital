from typing import Literal

from pydantic import BaseModel


class PhotoOut(BaseModel):
    id: int
    display_url: str
    thumb_url: str


class SettingsOut(BaseModel):
    slideshow_interval_seconds: int
    slideshow_order: str
    transition_effects: list[str]
    image_fit: str
    display_orientation: str
    show_clock: bool
    show_date: bool
    show_weather: bool
    weather_units: str


class DisplayStateOut(BaseModel):
    settings: SettingsOut
    photos: list[PhotoOut]
    photos_version: str
    settings_version: str
    screen_on: bool


class WeatherOut(BaseModel):
    temperature: float | None
    weather_code: int | None
    units: str


class ScreenStatusOut(BaseModel):
    screen_on: bool


class PowerActionIn(BaseModel):
    action: Literal["shutdown", "reboot", "hide"]
    hide_seconds: int | None = None


class PowerStatusOut(BaseModel):
    action: Literal["shutdown", "reboot", "hide"] | None
    hide_seconds: int | None = None


class UsbHeartbeatFile(BaseModel):
    relpath: str
    size: int
    mtime: float


class UsbHeartbeatFolder(BaseModel):
    relpath: str
    files: list[UsbHeartbeatFile]


class UsbHeartbeatVolume(BaseModel):
    fs_uuid: str
    label: str | None = None
    folders: list[UsbHeartbeatFolder]


class UsbHeartbeatIn(BaseModel):
    volumes: list[UsbHeartbeatVolume]


class UsbNewFileOut(BaseModel):
    fs_uuid: str
    album_id: int
    relpath: str


class UsbPendingCopyOut(BaseModel):
    fs_uuid: str
    photo_id: int
    album_id: int
    source_relpath: str


class UsbHeartbeatOut(BaseModel):
    new_files: list[UsbNewFileOut]
    pending_copies: list[UsbPendingCopyOut]
