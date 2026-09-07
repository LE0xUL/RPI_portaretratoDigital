import io
import re

from PIL import Image


def _fake_jpeg(color) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=color).save(buf, "JPEG")
    return buf.getvalue()


def test_display_page_is_public(client):
    resp = client.get("/display")
    assert resp.status_code == 200
    assert "stage" in resp.text


def test_admin_requires_login(client):
    resp = client.get("/admin/photos", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_login_wrong_code_rejected(client):
    resp = client.post("/login", data={"code": "wrong"}, follow_redirects=False)
    assert resp.status_code == 401
    assert "pf_session" not in resp.cookies


def test_upload_list_and_delete_photo(admin_client):
    resp = admin_client.post(
        "/admin/photos",
        files=[("files", ("a.jpg", _fake_jpeg("red"), "image/jpeg"))],
    )
    assert resp.status_code == 200
    assert "photo-card" in resp.text

    state = admin_client.get("/api/display/state").json()
    assert len(state["photos"]) == 1
    photo_id = state["photos"][0]["id"]

    resp = admin_client.delete(f"/admin/photos/{photo_id}")
    assert resp.status_code == 200

    state = admin_client.get("/api/display/state").json()
    assert len(state["photos"]) == 0


def test_albums_filter_display_state(admin_client):
    admin_client.post(
        "/admin/photos",
        files=[
            ("files", ("a.jpg", _fake_jpeg("blue"), "image/jpeg")),
            ("files", ("b.jpg", _fake_jpeg("green"), "image/jpeg")),
        ],
    )
    photo_ids = [p["id"] for p in admin_client.get("/api/display/state").json()["photos"]]
    assert len(photo_ids) >= 2

    resp = admin_client.post("/admin/albums", data={"name": "Familia"})
    assert resp.status_code == 200
    match = re.search(r'hx-patch="/admin/albums/(\d+)"', resp.text)
    assert match, resp.text
    album_id = int(match.group(1))

    # Asociar solo una foto y activar el álbum -> el display debe filtrar por esa foto
    admin_client.post(f"/admin/albums/{album_id}/photos/{photo_ids[0]}")
    admin_client.patch(f"/admin/albums/{album_id}", data={"is_active": "on"})

    state = admin_client.get("/api/display/state").json()
    assert [p["id"] for p in state["photos"]] == [photo_ids[0]]

    # Desactivar el álbum (checkbox no enviado, como haría un navegador real) ->
    # fallback a la librería completa
    admin_client.patch(f"/admin/albums/{album_id}", data={})
    state = admin_client.get("/api/display/state").json()
    assert set(p["id"] for p in state["photos"]) == set(photo_ids)


def test_settings_roundtrip(admin_client):
    resp = admin_client.post(
        "/admin/settings",
        data={
            "slideshow_interval_seconds": 30,
            "slideshow_order": "random",
            "transition_effect": "slide",
            "image_fit": "contain",
            "display_orientation": "portrait",
            "show_clock": "on",
            "show_date": "on",
            "show_weather": "on",
            "weather_latitude": -34.6,
            "weather_longitude": -58.4,
            "weather_units": "metric",
            "schedule_enabled": "on",
            "schedule_off_time": "22:00",
            "schedule_on_time": "07:00",
        },
    )
    assert resp.status_code == 200

    state = admin_client.get("/api/display/state").json()
    assert state["settings"]["slideshow_interval_seconds"] == 30
    assert state["settings"]["slideshow_order"] == "random"
    assert state["settings"]["transition_effect"] == "slide"
    assert state["settings"]["image_fit"] == "contain"
    assert state["settings"]["display_orientation"] == "portrait"
    assert state["settings"]["show_weather"] is True


def test_settings_with_empty_optional_number_fields(admin_client):
    # Un navegador real manda "" (no omite el campo) cuando un <input type="number">
    # queda vacío; esto no debe romper el parseo de weather_latitude/longitude.
    resp = admin_client.post(
        "/admin/settings",
        data={
            "slideshow_interval_seconds": 15,
            "slideshow_order": "sequential",
            "transition_effect": "fade",
            "image_fit": "cover",
            "display_orientation": "landscape",
            "weather_latitude": "",
            "weather_longitude": "",
            "weather_units": "metric",
        },
    )
    assert resp.status_code == 200

    state = admin_client.get("/api/display/state").json()
    assert state["settings"]["show_weather"] is False


def test_weather_endpoint_returns_204_without_coordinates(admin_client):
    admin_client.post(
        "/admin/settings",
        data={
            "slideshow_interval_seconds": 15,
            "slideshow_order": "sequential",
            "transition_effect": "fade",
            "image_fit": "cover",
            "display_orientation": "landscape",
            "show_weather": "on",
            "weather_units": "metric",
        },
    )
    resp = admin_client.get("/api/display/weather")
    assert resp.status_code == 204
