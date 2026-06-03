"""Idempotent CLDV database bootstrap: create the `cldv` database (if missing)
and apply the schema. Safe to re-run."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

_HERE = os.path.dirname(os.path.abspath(__file__))

HOST     = os.environ.get("POSTGRES_HOST", "localhost")
PORT     = int(os.environ.get("POSTGRES_PORT", 5440))
USER     = os.environ.get("POSTGRES_USER", "")
PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
DBNAME   = os.environ.get("POSTGRES_DB", "cldv")
BOOTSTRAP_DB = os.environ.get("POSTGRES_BOOTSTRAP_DB", "postgres")


def create_db_if_not_exists():
    conn = psycopg2.connect(host=HOST, port=PORT, user=USER,
                            password=PASSWORD, dbname=BOOTSTRAP_DB)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DBNAME,))
            if cur.fetchone() is None:
                # This server has no template1; use the always-present template0.
                cur.execute(f'CREATE DATABASE "{DBNAME}" TEMPLATE template0')
                print(f"  Created database: {DBNAME}")
            else:
                print(f"  Database {DBNAME} already exists — skipping create")
    finally:
        conn.close()


def apply_schema():
    schema_path = os.path.join(_HERE, "cldv_schema.sql")
    conn = psycopg2.connect(host=HOST, port=PORT, user=USER,
                            password=PASSWORD, dbname=DBNAME)
    try:
        conn.autocommit = True  # schema SQL has explicit BEGIN/COMMIT
        with conn.cursor() as cur, open(schema_path) as f:
            cur.execute(f.read())
    finally:
        conn.close()
    print("  Schema applied.")


if __name__ == "__main__":
    print("Setting up CLDV database...")
    create_db_if_not_exists()
    apply_schema()
    print("Done.")
