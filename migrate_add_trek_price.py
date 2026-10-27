"""
migrate_add_trek_price.py
--------------------------
One-time, backward-compatible migration adding the `price` column to `trek`.
Uses raw SQL ALTER TABLE (SQLite/Postgres compatible) and checks column existence.
Does NOT use db.create_all() as migration.

Existing treks keep NULL price (legacy state) until an administrator sets a
valid price. No placeholder price is invented and no customer is charged.

Usage:
    python migrate_add_trek_price.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from database import db


def column_exists(conn, table, column):
    dialect = conn.dialect.name
    if dialect == 'sqlite':
        rows = conn.execute(db.text(f"PRAGMA table_info({table})")).fetchall()
        return any(row[1] == column for row in rows)
    # PostgreSQL / other
    from sqlalchemy import inspect
    insp = inspect(conn)
    cols = [c['name'] for c in insp.get_columns(table)]
    return column in cols


def run_migration(app):
    uri = str(app.config.get('SQLALCHEMY_DATABASE_URI') or '')
    if os.environ.get('REQUIRE_POSTGRES', '').strip().lower() in ('1', 'true', 'yes'):
        if not uri.lower().startswith('postgresql'):
            raise RuntimeError(
                'Refusing to run: REQUIRE_POSTGRES is set but the configured database is not PostgreSQL.'
            )

    with app.app_context():
        conn = db.engine.connect()
        trans = conn.begin()
        try:
            if not column_exists(conn, 'trek', 'price'):
                dialect = conn.dialect.name
                if dialect == 'sqlite':
                    conn.execute(db.text("ALTER TABLE trek ADD COLUMN price NUMERIC(10, 2)"))
                else:
                    conn.execute(db.text("ALTER TABLE trek ADD COLUMN IF NOT EXISTS price NUMERIC(10, 2)"))
                print("Added column: trek.price")
            else:
                print("Column trek.price already exists; no change.")
            trans.commit()
        except Exception:
            trans.rollback()
            raise
        finally:
            conn.close()

    # Verification output (no credentials).
    with app.app_context():
        from sqlalchemy import inspect, text
        insp = inspect(db.engine)
        columns = {c['name']: c for c in insp.get_columns('trek')}
        if 'price' not in columns:
            raise RuntimeError('Verification failed: trek.price is missing after migration.')
        total = db.session.execute(text('SELECT COUNT(*) FROM trek')).scalar() or 0
        null_prices = db.session.execute(
            text('SELECT COUNT(*) FROM trek WHERE price IS NULL')
        ).scalar() or 0
        print(f"Verified: trek.price exists; {total} trek(s) preserved, {null_prices} with NULL price (legacy).")


if __name__ == '__main__':
    app = create_app()
    run_migration(app)
    print("Migration complete.")
