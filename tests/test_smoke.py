import io
import re

from PIL import Image


def _fake_jpeg(color) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=color).save(buf, "JPEG")
    return buf.getvalue()


def _create_album(client, name: str) -> int:
    resp = client.post("/admin/albums", data={"name": name})
    # order_by(created_at.desc()) -> el álbum recién creado aparece primero
    matches = re.findall(r'hx-patch="/admin/albums/(\d+)"', resp.text)
    assert matches, resp.text
    return int(matches[0])


def _activate_album(client, album_id: int) -> None:
    resp = client.patch(f"/admin/albums/{album_id}", data={"is_active": "on"})
    assert resp.status_code == 200


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


def test_upload_without_album_rejected(admin_client):
    resp = admin_client.post(
        "/admin/photos",
        files=[("files", ("a.jpg", _fake_jpeg("red"), "image/jpeg"))],
    )
    assert resp.status_code == 422


def test_upload_list_and_delete_photo(admin_client):
    album_id = _create_album(admin_client, "Cumple")
    resp = admin_client.post(
        "/admin/photos",
        data={"album_id": album_id},
        files=[("files", ("a.jpg", _fake_jpeg("red"), "image/jpeg"))],
    )
    assert resp.status_code == 200
    assert "photo-card" in resp.text

    _activate_album(admin_client, album_id)
    state = admin_client.get("/api/display/state").json()
    photo_ids_before = {p["id"] for p in state["photos"]}

    resp = admin_client.get(f"/admin/albums/{album_id}")
    album_photo_ids = [int(m) for m in re.findall(r'/admin/photos/(\d+)\?', resp.text)]
    assert len(album_photo_ids) == 1
    photo_id = album_photo_ids[0]
    assert photo_id in photo_ids_before

    resp = admin_client.delete(f"/admin/photos/{photo_id}?from_album_id={album_id}")
    assert resp.status_code == 200

    state = admin_client.get("/api/display/state").json()
    assert photo_id not in {p["id"] for p in state["photos"]}


def test_albums_filter_display_state(admin_client):
    album_a = _create_album(admin_client, "Familia A")
    album_b = _create_album(admin_client, "Familia B")

    admin_client.post(
        "/admin/photos",
        data={"album_id": album_a},
        files=[("files", ("a.jpg", _fake_jpeg("blue"), "image/jpeg"))],
    )
    admin_client.post(
        "/admin/photos",
        data={"album_id": album_b},
        files=[("files", ("b.jpg", _fake_jpeg("green"), "image/jpeg"))],
    )

    _activate_album(admin_client, album_a)

    state = admin_client.get("/api/display/state").json()
    photo_a_ids = {
        int(m)
        for m in re.findall(r'/admin/photos/(\d+)\?', admin_client.get(f"/admin/albums/{album_a}").text)
    }
    assert photo_a_ids
    assert {p["id"] for p in state["photos"]} & photo_a_ids == photo_a_ids

    photo_b_ids = {
        int(m)
        for m in re.findall(r'/admin/photos/(\d+)\?', admin_client.get(f"/admin/albums/{album_b}").text)
    }
    assert not ({p["id"] for p in state["photos"]} & photo_b_ids)


def test_move_photo_between_albums(admin_client):
    source = _create_album(admin_client, "Origen")
    target = _create_album(admin_client, "Destino")

    admin_client.post(
        "/admin/photos",
        data={"album_id": source},
        files=[("files", ("a.jpg", _fake_jpeg("red"), "image/jpeg"))],
    )
    resp = admin_client.get(f"/admin/albums/{source}")
    photo_id = int(re.findall(r'/admin/photos/(\d+)\?', resp.text)[0])

    resp = admin_client.patch(
        f"/admin/photos/{photo_id}/album?from_album_id={source}", data={"album_id": target}
    )
    assert resp.status_code == 200

    assert f"/admin/photos/{photo_id}?" not in admin_client.get(f"/admin/albums/{source}").text
    assert f"/admin/photos/{photo_id}?" in admin_client.get(f"/admin/albums/{target}").text


def test_delete_nonempty_local_album_blocked(admin_client):
    album_id = _create_album(admin_client, "Con fotos")
    admin_client.post(
        "/admin/photos",
        data={"album_id": album_id},
        files=[("files", ("a.jpg", _fake_jpeg("red"), "image/jpeg"))],
    )
    resp = admin_client.delete(f"/admin/albums/{album_id}")
    assert resp.status_code == 200
    assert "tiene fotos" in resp.text
    # sigue existiendo
    assert admin_client.get(f"/admin/albums/{album_id}").status_code == 200


def test_settings_roundtrip(admin_client):
    resp = admin_client.post(
        "/admin/settings",
        data={
            "slideshow_interval_seconds": 30,
            "slideshow_order": "random",
            "transition_effects": ["slide", "zoom-in"],
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
    assert state["settings"]["transition_effects"] == ["slide", "zoom-in"]
    assert state["settings"]["image_fit"] == "contain"
    assert state["settings"]["display_orientation"] == "portrait"
    assert state["settings"]["show_weather"] is True


def test_settings_transition_effects_defaults_to_fade_if_none_selected(admin_client):
    resp = admin_client.post(
        "/admin/settings",
        data={
            "slideshow_interval_seconds": 15,
            "slideshow_order": "sequential",
            "image_fit": "cover",
            "display_orientation": "landscape",
            "weather_units": "metric",
        },
    )
    assert resp.status_code == 200
    state = admin_client.get("/api/display/state").json()
    assert state["settings"]["transition_effects"] == ["fade"]


def test_settings_transition_effects_ignores_unknown_values(admin_client):
    resp = admin_client.post(
        "/admin/settings",
        data={
            "slideshow_interval_seconds": 15,
            "slideshow_order": "sequential",
            "transition_effects": ["fade", "not-a-real-effect"],
            "image_fit": "cover",
            "display_orientation": "landscape",
            "weather_units": "metric",
        },
    )
    assert resp.status_code == 200
    state = admin_client.get("/api/display/state").json()
    assert state["settings"]["transition_effects"] == ["fade"]


def test_settings_with_empty_optional_number_fields(admin_client):
    # Un navegador real manda "" (no omite el campo) cuando un <input type="number">
    # queda vacío; esto no debe romper el parseo de weather_latitude/longitude.
    resp = admin_client.post(
        "/admin/settings",
        data={
            "slideshow_interval_seconds": 15,
            "slideshow_order": "sequential",
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
            "image_fit": "cover",
            "display_orientation": "landscape",
            "show_weather": "on",
            "weather_units": "metric",
        },
    )
    resp = admin_client.get("/api/display/weather")
    assert resp.status_code == 204


def test_display_page_includes_power_menu(client):
    resp = client.get("/display")
    assert "tap-zone" in resp.text
    assert "power-menu" in resp.text


def test_power_action_is_consumed_once(client):
    # nada pendiente todavía
    assert client.get("/api/display/power-status").json()["action"] is None

    resp = client.post("/api/display/power-action", json={"action": "hide", "hide_seconds": 30})
    assert resp.status_code == 200

    # el primer poll del host la ve y la consume...
    status = client.get("/api/display/power-status").json()
    assert status == {"action": "hide", "hide_seconds": 30}

    # ...un segundo poll ya no debe repetirla
    status_again = client.get("/api/display/power-status").json()
    assert status_again["action"] is None


def test_power_action_rejects_unknown_action(client):
    resp = client.post("/api/display/power-action", json={"action": "reformat-disk"})
    assert resp.status_code == 422
