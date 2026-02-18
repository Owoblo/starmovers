"""Initialize the SQLite database from schema.sql."""

import sqlite3
from pathlib import Path


def init_db(db_path: Path | None = None):
    """Create all tables from schema.sql."""
    if db_path is None:
        from outreach_engine.config import cfg
        db_path = cfg.db_path

    db_path.parent.mkdir(parents=True, exist_ok=True)

    schema_path = Path(__file__).parent / "schema.sql"
    schema_sql = schema_path.read_text()

    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()
    print(f"Database initialized at {db_path}")


if __name__ == "__main__":
    init_db()
