import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import app.migrations as migrations


def _make_legacy_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE albums (
            id INTEGER PRIMARY KEY,
            name VARCHAR UNIQUE,
            is_active BOOLEAN,
            created_at DATETIME
        );
        CREATE TABLE photos (
            id INTEGER PRIMARY KEY,
            filename VARCHAR UNIQUE,
            original_filename VARCHAR,
            width INTEGER,
            height INTEGER,
            file_size_bytes INTEGER,
            created_at DATETIME
        );
        CREATE TABLE album_photos (
            album_id INTEGER REFERENCES albums(id),
            photo_id INTEGER REFERENCES photos(id),
            PRIMARY KEY (album_id, photo_id)
        );
        """
    )
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT INTO albums (id, name, is_active, created_at) VALUES (1, 'Viejo', 1, ?)", (now,))
    conn.execute(
        "INSERT INTO albums (id, name, is_active, created_at) VALUES (2, 'Nuevo', 0, ?)",
        ("2099-01-01T00:00:00+00:00",),
    )
    for pid, fname, orig in ((1, "f1", "a.jpg"), (2, "f2", "b.jpg"), (3, "f3", "orphan.jpg")):
        conn.execute(
            "INSERT INTO photos (id, filename, original_filename, width, height, file_size_bytes, created_at) "
            "VALUES (?, ?, ?, 10, 10, 100, ?)",
            (pid, fname, orig, now),
        )
    # foto 1 pertenece a ambos álbumes -> debe quedar en el más antiguo (álbum 1, "Viejo")
    conn.execute("INSERT INTO album_photos (album_id, photo_id) VALUES (1, 1)")
    conn.execute("INSERT INTO album_photos (album_id, photo_id) VALUES (2, 1)")
    # foto 2 pertenece solo al álbum 2
    conn.execute("INSERT INTO album_photos (album_id, photo_id) VALUES (2, 2)")
    # foto 3 no pertenece a ningún álbum -> huérfana, debe ir a "Sin clasificar"
    conn.commit()
    conn.close()


def test_migrate_legacy_schema_backfills_albums(tmp_path, monkeypatch):
    # db_path es una property calculada desde DATA_DIR (sin setter propio),
    # así que para redirigirla en el test hay que pisar DATA_DIR.
    monkeypatch.setattr(migrations.settings, "DATA_DIR", tmp_path)
    db_path = migrations.settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _make_legacy_db(db_path)

    migrations.migrate_legacy_schema()

    conn = sqlite3.connect(str(db_path))
    columns = {row[1] for row in conn.execute("PRAGMA table_info(photos)").fetchall()}
    assert "album_id" in columns

    rows = dict(conn.execute("SELECT id, album_id FROM photos").fetchall())
    assert rows[1] == 1
    assert rows[2] == 2

    fallback = conn.execute("SELECT id FROM albums WHERE name = 'Sin clasificar'").fetchone()
    assert fallback is not None
    assert rows[3] == fallback[0]

    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "album_photos" not in tables

    # sin unique=True en name: no debe fallar duplicar un nombre de álbum
    conn.execute("INSERT INTO albums (name, is_active, created_at, connected) VALUES ('Viejo', 0, datetime('now'), 1)")
    conn.commit()
    conn.close()

    # correr de nuevo es un no-op (la columna album_id ya existe)
    migrations.migrate_legacy_schema()

    backups = list(db_path.parent.glob("photoframe.db.bak-*"))
    assert len(backups) == 1


def test_migrate_legacy_schema_noop_for_fresh_install(tmp_path, monkeypatch):
    monkeypatch.setattr(migrations.settings, "DATA_DIR", tmp_path)
    db_path = migrations.settings.db_path

    migrations.migrate_legacy_schema()  # no existe el archivo: no debe fallar ni crear nada

    assert not db_path.exists()
