import os
import tempfile

_tmp_dir = tempfile.mkdtemp(prefix="photoframe-test-")
os.environ.setdefault("DATA_DIR", _tmp_dir)
os.environ.setdefault("INVITE_CODE", "test-code")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_client(client):
    resp = client.post("/login", data={"code": os.environ["INVITE_CODE"]}, follow_redirects=False)
    assert resp.status_code == 303
    assert "pf_session" in resp.cookies
    return client
