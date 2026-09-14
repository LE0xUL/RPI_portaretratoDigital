"""Migración única de la DB pre-existente (Photo<->Album muchos-a-muchos) al
esquema nuevo (Photo.album_id obligatorio + tablas de USB).

No hay Alembic en este repo (ver CLAUDE.md) — para una instalación nueva
`Base.metadata.create_all()` ya crea el esquema correcto directamente. Esto
solo corre cuando detecta una DB existente con el esquema viejo (ausencia de
la columna `photos.album_id`), y debe ejecutarse antes de `create_all()`.

Usa sqlite3 crudo, no el engine de SQLAlchemy: reconstruir la tabla `albums`
requiere `PRAGMA foreign_keys=OFF` mientras se la reemplaza, y dejar ese
pragma pegado en una conexión que el pool de la app puede reusar después
sería un bug silencioso (se perdería el chequeo de integridad referencial
para el resto de la vida del proceso). Con una conexión propia, descartada
al terminar, ese riesgo no existe.
"""

import shutil
import sqlite3
from datetime import datetime, timezone

from app.config import settings


def migrate_legacy_schema() -> None:
    db_path = settings.db_path
    if not db_path.exists():
        return  # instalación nueva

    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "photos" not in tables:
            return  # DB vacía, nada que migrar

        columns = {row[1] for row in conn.execute("PRAGMA table_info(photos)").fetchall()}
        if "album_id" in columns:
            return  # ya migrada
    finally:
        conn.close()

    _backup(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            with conn:  # una sola transacción: todo o nada
                _do_migrate(conn)
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(f"Migración dejó referencias inválidas: {violations}")
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
    finally:
        conn.close()


def _backup(db_path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.bak-{timestamp}")
    shutil.copy2(db_path, backup_path)


def _do_migrate(conn: sqlite3.Connection) -> None:
    # 1. Reconstruir 'albums': quita el UNIQUE en name (colisiona con carpetas
    #    USB repetidas como "DCIM" entre dispositivos distintos) y agrega las
    #    columnas nuevas de USB. SQLite no soporta DROP CONSTRAINT, así que
    #    esto requiere crear la tabla de nuevo y copiar los datos.
    conn.execute(
        """
        CREATE TABLE albums_new (
            id INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL,
            usb_volume_id INTEGER REFERENCES usb_volumes(id),
            source_relpath VARCHAR,
            connected BOOLEAN NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        "INSERT INTO albums_new (id, name, is_active, created_at, connected) "
        "SELECT id, name, is_active, created_at, 1 FROM albums"
    )
    conn.execute("DROP TABLE albums")
    conn.execute("ALTER TABLE albums_new RENAME TO albums")

    # 2. Columnas nuevas de 'photos'. Quedan nullable a nivel SQLite en bases
    #    migradas (SQLite no puede agregar NOT NULL retroactivo sin rebuild);
    #    la aplicación nunca escribe NULL en album_id, documentado en CLAUDE.md.
    for ddl in (
        "ALTER TABLE photos ADD COLUMN album_id INTEGER REFERENCES albums(id)",
        "ALTER TABLE photos ADD COLUMN source VARCHAR DEFAULT 'local'",
        "ALTER TABLE photos ADD COLUMN has_original BOOLEAN DEFAULT 1",
        "ALTER TABLE photos ADD COLUMN source_relpath VARCHAR",
        "ALTER TABLE photos ADD COLUMN source_size INTEGER",
        "ALTER TABLE photos ADD COLUMN source_mtime FLOAT",
        "ALTER TABLE photos ADD COLUMN copy_requested_at DATETIME",
        "ALTER TABLE photos ADD COLUMN pending_target_album_id INTEGER REFERENCES albums(id)",
    ):
        conn.execute(ddl)

    # 3. Backfill album_id: por foto, el álbum más antiguo entre sus
    #    membresías previas en album_photos (determinístico). Huérfanas
    #    (cero álbumes) van a un álbum "Sin clasificar" creado on-demand.
    rows = conn.execute(
        """
        SELECT ap.photo_id, ap.album_id
        FROM album_photos ap
        JOIN albums a ON a.id = ap.album_id
        ORDER BY ap.photo_id, a.created_at ASC, a.id ASC
        """
    ).fetchall()
    chosen: dict[int, int] = {}
    for photo_id, album_id in rows:
        chosen.setdefault(photo_id, album_id)

    photo_ids = [row[0] for row in conn.execute("SELECT id FROM photos").fetchall()]
    orphan_ids = [pid for pid in photo_ids if pid not in chosen]
    if orphan_ids:
        existing = conn.execute(
            "SELECT id FROM albums WHERE name = ?", ("Sin clasificar",)
        ).fetchone()
        if existing:
            fallback_id = existing[0]
        else:
            cursor = conn.execute(
                "INSERT INTO albums (name, is_active, created_at, connected) "
                "VALUES (?, 0, datetime('now'), 1)",
                ("Sin clasificar",),
            )
            assert cursor.lastrowid is not None
            fallback_id = cursor.lastrowid
        for pid in orphan_ids:
            chosen[pid] = fallback_id

    conn.executemany(
        "UPDATE photos SET album_id = ? WHERE id = ?",
        [(album_id, photo_id) for photo_id, album_id in chosen.items()],
    )

    conn.execute("DROP TABLE IF EXISTS album_photos")
