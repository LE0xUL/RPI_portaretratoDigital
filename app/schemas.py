from pydantic import BaseModel


class PhotoOut(BaseModel):
    id: int
    display_url: str
    thumb_url: str


class SettingsOut(BaseModel):
    slideshow_interval_seconds: int
    slideshow_order: str
    transition_effect: str
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
