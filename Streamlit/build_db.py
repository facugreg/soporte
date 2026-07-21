"""Genera cuentacorriente.db (SQLite) a partir de sql/01_crear_base_datos_sqlite.sql."""

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
SQL_SCRIPT = BASE_DIR / "sql" / "01_crear_base_datos_sqlite.sql"
DB_PATH = BASE_DIR / "cuentacorriente.db"


def build():
    script = SQL_SCRIPT.read_text(encoding="utf-8")
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(script)
        conn.commit()
    finally:
        conn.close()

    print(f"Base de datos creada en: {DB_PATH}")


if __name__ == "__main__":
    build()
