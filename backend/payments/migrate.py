"""Apply payment migrations only after domain migrations."""
from hashlib import sha256
from pathlib import Path
import os
import sys
import psycopg


def apply(database_url):
    if not database_url:
        raise ValueError("DATABASE_URL is required")
    count = 0
    with psycopg.connect(database_url, connect_timeout=10) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('payment-migrations:' || current_schema(), 0))")
        domain = conn.execute("SELECT to_regclass('domain_schema_migrations')").fetchone()[0]
        if not domain or not conn.execute("SELECT 1 FROM domain_schema_migrations WHERE name = '001_domain.sql'").fetchone():
            raise ValueError("Apply domain migrations first")
        conn.execute("CREATE TABLE IF NOT EXISTS payment_schema_migrations (name TEXT PRIMARY KEY, checksum TEXT NOT NULL)")
        for path in sorted(Path(__file__).with_name("migrations").glob("*.sql")):
            script = path.read_text(encoding="utf-8-sig")
            digest = sha256(script.encode()).hexdigest()
            previous = conn.execute("SELECT checksum FROM payment_schema_migrations WHERE name = %s", (path.name,)).fetchone()
            if previous:
                if previous[0] != digest:
                    raise ValueError("An applied payment migration has changed: " + path.name)
                continue
            conn.execute(script, prepare=False)
            conn.execute("INSERT INTO payment_schema_migrations (name, checksum) VALUES (%s, %s)", (path.name, digest))
            count += 1
    return count


def main():
    try:
        count = apply(os.getenv("DATABASE_URL", ""))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except psycopg.Error:
        print("Payment migration failed; check database access and schema.", file=sys.stderr)
        return 1
    print(f"Applied {count} payment migration(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
