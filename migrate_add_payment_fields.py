"""
migrate_add_payment_fields.py
-----------------------------
One-time, backward-compatible migration adding Razorpay/payment columns to Booking.
Uses raw SQL ALTER TABLE (SQLite/Postgres compatible) and checks column existence.
Does NOT use db.create_all() as migration.

Existing rows are tagged payment_status='Legacy' when the payment_status column
is first added. They must not be treated as newly abandoned Unpaid bookings by
the pending-payment expiry job. New bookings still default to 'Unpaid' when
created outside the application flow.

On SQLite the whole migration runs in one IMMEDIATE transaction, so a failure
rolls back every schema and data change. Re-running after success is a no-op and
does not re-tag new Unpaid bookings.

Usage:
    python migrate_add_payment_fields.py
"""

import os
import sys
from contextlib import contextmanager, nullcontext

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from database import db


def column_exists(conn, table, column):
    dialect = conn.dialect.name
    if dialect == 'sqlite':
        result = conn.execute(db.text(f"PRAGMA table_info({table})"))
        return any(row[1] == column for row in result)
    else:
        result = conn.execute(
            db.text("SELECT column_name FROM information_schema.columns WHERE table_name = :tbl AND column_name = :col"),
            {'tbl': table, 'col': column}
        )
        return result.fetchone() is not None


def index_exists(conn, table, index_name):
    dialect = conn.dialect.name
    if dialect == 'sqlite':
        result = conn.execute(db.text(f"PRAGMA index_list({table})"))
        return any(row[1] == index_name for row in result)
    else:
        result = conn.execute(
            db.text("SELECT indexname FROM pg_indexes WHERE tablename = :tbl AND indexname = :idx"),
            {'tbl': table, 'idx': index_name}
        )
        return result.fetchone() is not None


@contextmanager
def _atomic_sqlite_transaction(conn):
    """
    Run the SQLite migration as one write transaction.

    The pysqlite driver does not reliably include DDL in an implicit
    transaction, so a failure part-way through the ALTER statements could
    leave a partially migrated schema. BEGIN IMMEDIATE makes all DDL and DML
    in this block commit or roll back together.
    """
    conn.exec_driver_sql('BEGIN IMMEDIATE')
    try:
        yield
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()


def run_migration(app):
    with app.app_context():
        with db.engine.connect() as conn:
            is_sqlite = conn.dialect.name == 'sqlite'
            transaction = _atomic_sqlite_transaction(conn) if is_sqlite else nullcontext()

            with transaction:
                changes = []
                payment_status_existed = column_exists(conn, 'booking', 'payment_status')

                if not payment_status_existed:
                    conn.execute(db.text("ALTER TABLE booking ADD COLUMN payment_status VARCHAR(50) DEFAULT 'Unpaid' NOT NULL"))
                    # Preserve pre-Razorpay bookings. Tagging them 'Legacy' prevents
                    # the expiry job from cancelling historical/Completed records.
                    conn.execute(db.text("UPDATE booking SET payment_status = 'Legacy' WHERE payment_status = 'Unpaid'"))
                    changes.append('payment_status')
                    print("  + Added column: booking.payment_status (existing rows tagged 'Legacy')")
                else:
                    print("  ✓ Column already exists: booking.payment_status")
                    print("    (Existing rows were NOT re-tagged; review legacy rows manually if needed.)")

                if not column_exists(conn, 'booking', 'amount'):
                    conn.execute(db.text("ALTER TABLE booking ADD COLUMN amount FLOAT"))
                    changes.append('amount')
                    print("  + Added column: booking.amount")
                else:
                    print("  ✓ Column already exists: booking.amount")

                if not column_exists(conn, 'booking', 'currency'):
                    conn.execute(db.text("ALTER TABLE booking ADD COLUMN currency VARCHAR(10) DEFAULT 'INR' NOT NULL"))
                    changes.append('currency')
                    print("  + Added column: booking.currency")
                else:
                    print("  ✓ Column already exists: booking.currency")

                if not column_exists(conn, 'booking', 'razorpay_order_id'):
                    conn.execute(db.text("ALTER TABLE booking ADD COLUMN razorpay_order_id VARCHAR(100)"))
                    changes.append('razorpay_order_id')
                    print("  + Added column: booking.razorpay_order_id")
                else:
                    print("  ✓ Column already exists: booking.razorpay_order_id")

                if not column_exists(conn, 'booking', 'razorpay_payment_id'):
                    conn.execute(db.text("ALTER TABLE booking ADD COLUMN razorpay_payment_id VARCHAR(100)"))
                    changes.append('razorpay_payment_id')
                    print("  + Added column: booking.razorpay_payment_id")
                else:
                    print("  ✓ Column already exists: booking.razorpay_payment_id")

                if not column_exists(conn, 'booking', 'razorpay_signature'):
                    conn.execute(db.text("ALTER TABLE booking ADD COLUMN razorpay_signature VARCHAR(200)"))
                    changes.append('razorpay_signature')
                    print("  + Added column: booking.razorpay_signature")

                # Add unique index on razorpay_order_id if possible
                if not index_exists(conn, 'booking', 'ix_booking_razorpay_order_id'):
                    try:
                        conn.execute(db.text("CREATE UNIQUE INDEX ix_booking_razorpay_order_id ON booking(razorpay_order_id)"))
                        print("  + Added unique index: ix_booking_razorpay_order_id")
                    except Exception as e:
                        if is_sqlite:
                            raise RuntimeError(
                                "SQLite migration could not create the unique Razorpay order index; "
                                "all changes were rolled back."
                            ) from e
                        print(f"  ! Could not create unique index (may exist or dialect limitation): {e}")

                if is_sqlite and payment_status_existed:
                    unpaid_count = conn.execute(db.text(
                        "SELECT COUNT(*) FROM booking WHERE payment_status = 'Unpaid'"
                    )).scalar()
                    if unpaid_count:
                        print(f"  ! {unpaid_count} existing row(s) still have payment_status='Unpaid'; "
                              "review historical rows before starting the app.")

                # PostgreSQL keeps its existing commit behavior. SQLite commits
                # in _atomic_sqlite_transaction so an index-only rerun persists.
                if not is_sqlite and changes:
                    conn.commit()

            if changes:
                print(f"\nMigration complete. Added {len(changes)} column(s): {', '.join(changes)}")
            else:
                print("\nMigration complete. No schema changes needed.")


if __name__ == '__main__':
    app = create_app()
    print("Starting payment fields migration...")
    run_migration(app)
    print("Done.")
