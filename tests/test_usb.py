from tests.test_smoke import _fake_jpeg


def _heartbeat_payload(fs_uuid="TEST-UUID", label="MI_USB", relpath="DCIM/img1.jpg", size=100, mtime=111.0):
    return {
        "volumes": [
            {
                "fs_uuid": fs_uuid,
                "label": label,
                "folders": [{"relpath": "DCIM", "files": [{"relpath": relpath, "size": size, "mtime": mtime}]}],
            }
        ]
    }


def test_heartbeat_creates_active_album_and_reports_new_file(admin_client):
    resp = admin_client.post("/admin/usb/heartbeat", json=_heartbeat_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["new_files"]) == 1
    assert body["new_files"][0]["relpath"] == "DCIM/img1.jpg"
    album_id = body["new_files"][0]["album_id"]

    albums_page = admin_client.get("/admin/albums").text
    assert "USB conectada" in albums_page

    # una vez registrada la foto, un heartbeat con el mismo archivo no debe
    # volver a reportarla como nueva (dedup por álbum + source_relpath)
    admin_client.post(
        "/admin/usb/photos",
        data={"album_id": album_id, "source_relpath": "DCIM/img1.jpg", "source_size": 100, "source_mtime": 111.0},
        files={"file": ("img1.jpg", _fake_jpeg("blue"), "image/jpeg")},
    )
    resp2 = admin_client.post("/admin/usb/heartbeat", json=_heartbeat_payload())
    assert resp2.json()["new_files"] == []
    assert resp2.json()["pending_copies"] == []


def test_register_usb_photo_has_no_original_until_copied(admin_client):
    resp = admin_client.post("/admin/usb/heartbeat", json=_heartbeat_payload(fs_uuid="UUID-2"))
    album_id = resp.json()["new_files"][0]["album_id"]

    resp = admin_client.post(
        "/admin/usb/photos",
        data={"album_id": album_id, "source_relpath": "DCIM/img1.jpg", "source_size": 100, "source_mtime": 111.0},
        files={"file": ("img1.jpg", _fake_jpeg("blue"), "image/jpeg")},
    )
    assert resp.status_code == 200
    photo_id = resp.json()["photo_id"]

    album_detail = admin_client.get(f"/admin/albums/{album_id}").text
    assert "Sin copia local" in album_detail
    # no tiene botón de "mover" (has_original=False) -- solo "copiar a la biblioteca"
    assert f"/admin/photos/{photo_id}/album" not in album_detail
    assert f"/admin/usb/photos/{photo_id}/copy" in album_detail


def test_copy_photo_then_copy_complete_promotes_to_local(admin_client):
    resp = admin_client.post("/admin/usb/heartbeat", json=_heartbeat_payload(fs_uuid="UUID-3"))
    album_id = resp.json()["new_files"][0]["album_id"]
    resp = admin_client.post(
        "/admin/usb/photos",
        data={"album_id": album_id, "source_relpath": "DCIM/img1.jpg", "source_size": 100, "source_mtime": 111.0},
        files={"file": ("img1.jpg", _fake_jpeg("green"), "image/jpeg")},
    )
    photo_id = resp.json()["photo_id"]

    resp = admin_client.post(f"/admin/usb/photos/{photo_id}/copy?from_album_id={album_id}", data={})
    assert resp.status_code == 200

    hb = admin_client.post("/admin/usb/heartbeat", json=_heartbeat_payload(fs_uuid="UUID-3")).json()
    assert hb["pending_copies"] == [
        {"fs_uuid": "UUID-3", "photo_id": photo_id, "album_id": album_id, "source_relpath": "DCIM/img1.jpg"}
    ]

    resp = admin_client.post(
        f"/admin/usb/photos/{photo_id}/copy-complete",
        files={"file": ("img1.jpg", _fake_jpeg("green"), "image/jpeg")},
    )
    assert resp.status_code == 200

    album_detail = admin_client.get(f"/admin/albums/{album_id}").text
    assert "Sin copia local" not in album_detail

    # ya no debería aparecer como pendiente
    hb2 = admin_client.post("/admin/usb/heartbeat", json=_heartbeat_payload(fs_uuid="UUID-3")).json()
    assert hb2["pending_copies"] == []


def test_disconnect_hides_uncopied_photo_but_keeps_copied_one(admin_client):
    resp = admin_client.post("/admin/usb/heartbeat", json=_heartbeat_payload(fs_uuid="UUID-4"))
    album_id = resp.json()["new_files"][0]["album_id"]

    admin_client.post(
        "/admin/usb/photos",
        data={"album_id": album_id, "source_relpath": "DCIM/img1.jpg", "source_size": 100, "source_mtime": 111.0},
        files={"file": ("img1.jpg", _fake_jpeg("red"), "image/jpeg")},
    )
    resp = admin_client.post(
        "/admin/usb/photos",
        data={"album_id": album_id, "source_relpath": "DCIM/img2.jpg", "source_size": 100, "source_mtime": 111.0},
        files={"file": ("img2.jpg", _fake_jpeg("red"), "image/jpeg")},
    )
    copied_photo_id = resp.json()["photo_id"]

    admin_client.post(f"/admin/usb/photos/{copied_photo_id}/copy?from_album_id={album_id}", data={})
    admin_client.post(
        f"/admin/usb/photos/{copied_photo_id}/copy-complete",
        files={"file": ("img2.jpg", _fake_jpeg("red"), "image/jpeg")},
    )

    state_before = admin_client.get("/api/display/state").json()
    ids_before = {p["id"] for p in state_before["photos"]}
    assert copied_photo_id in ids_before

    # desconectar: heartbeat sin volúmenes
    admin_client.post("/admin/usb/heartbeat", json={"volumes": []})

    albums_page = admin_client.get("/admin/albums").text
    assert "USB desconectada" in albums_page

    state_after = admin_client.get("/api/display/state").json()
    ids_after = {p["id"] for p in state_after["photos"]}
    assert copied_photo_id in ids_after  # ya tiene copia local, no depende de la USB
