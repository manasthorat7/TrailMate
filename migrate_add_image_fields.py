"""
migrate_add_image_fields.py
---------------------------
One-time, backward-compatible migration that adds the two Cloudinary image
columns to the `trek` table when they do not yet exist.

Usage (from the project root):
    python migrate_add_image_fields.py

This script is safe to re-run: it checks for column existence before
attempting ALTER TABLE, so it will exit cleanly if the columns are
already present.

Why not db.create_all()?
    db.create_all() creates missing *tables* but does NOT alter existing
    tables to add missing columns. This script uses raw SQL ALTER TABLE
    so it can be applied to any existing database (SQLite or PostgreSQL)
    without discarding data.
"""

import os
import sys

# Make sure the project root is on sys.path
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from database import db


def column_exists(conn, table, column):
    """Return True if *column* exists in *table* (dialect-agnostic)."""
    dialect = conn.dialect.name
    if dialect == 'sqlite':
        result = conn.execute(
            db.text(f"PRAGMA table_info({table})")
        )
        return any(row[1] == column for row in result)
    else:
        # PostgreSQL / MySQL compatible
        result = conn.execute(
            db.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :tbl AND column_name = :col"
            ),
            {'tbl': table, 'col': column}
        )
        return result.fetchone() is not None


def run_migration(app):
    with app.app_context():
        with db.engine.connect() as conn:
            changes = []

            if not column_exists(conn, 'trek', 'image_url'):
                conn.execute(
                    db.text("ALTER TABLE trek ADD COLUMN image_url VARCHAR(500)")
                )
                changes.append('image_url')
                print("  + Added column: trek.image_url")
            else:
                print("  ✓ Column already exists: trek.image_url")

            if not column_exists(conn, 'trek', 'image_public_id'):
                conn.execute(
                    db.text("ALTER TABLE trek ADD COLUMN image_public_id VARCHAR(200)")
                )
                changes.append('image_public_id')
                print("  + Added column: trek.image_public_id")
            else:
                print("  ✓ Column already exists: trek.image_public_id")

            if changes:
                conn.commit()
                print(f"\nMigration complete. Added {len(changes)} column(s): {', '.join(changes)}")
            else:
                print("\nNo changes needed — database is already up to date.")


if __name__ == '__main__':
    print("TrailMate — Cloudinary image fields migration")
    print("=" * 50)
    app = create_app()
    run_migration(app)
