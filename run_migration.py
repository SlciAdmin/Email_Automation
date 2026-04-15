"""
run_migration.py
────────────────
Run this ONCE to add the missing columns to your existing database.
Usage:  python run_migration.py

Safe to run multiple times – it skips columns that already exist.
"""

import os
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text, inspect

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:SLCI123@localhost:5432/email_automation"
)

engine = create_engine(DATABASE_URL)

NEW_COLUMNS = [
    # (column_name, sql_type, default_expression)
    ("body_html",        "TEXT",          "''"),
    ("cc",               "VARCHAR(500)",  "''"),
    ("reply_to",         "VARCHAR(200)",  "''"),
    ("attachments_info", "TEXT",          "'[]'"),
]

def column_exists(inspector, table, col):
    return any(c["name"] == col for c in inspector.get_columns(table))

with engine.connect() as conn:
    inspector = inspect(engine)

    for col_name, col_type, default in NEW_COLUMNS:
        if column_exists(inspector, "emails", col_name):
            print(f"  ✓ Column already exists: emails.{col_name}")
        else:
            sql = (
                f"ALTER TABLE emails "
                f"ADD COLUMN {col_name} {col_type} NOT NULL DEFAULT {default};"
            )
            conn.execute(text(sql))
            conn.commit()
            print(f"  ➕ Added column: emails.{col_name} ({col_type})")

print("\n✅ Migration complete.  You can now restart app.py.")