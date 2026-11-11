"""Apply only domain migrations; no app mounting or payment migrations."""

import argparse
from hashlib import sha256
from pathlib import Path
import sys

from .database import DomainDatabase, DomainError


def apply_migrations(database: DomainDatabase) -> int:
    applied = 0
    with database.transaction() as connection:
        connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('domain-migrations:' || current_schema(), 0))")
        connection.execute("CREATE TABLE IF NOT EXISTS domain_schema_migrations (name TEXT PRIMARY KEY, checksum TEXT NOT NULL)")
        for path in sorted(Path(__file__).with_name("migrations").glob("*.sql")):
            script = path.read_text(encoding="utf-8")
            checksum = sha256(script.encode("utf-8")).hexdigest()
            existing = connection.execute("SELECT checksum FROM domain_schema_migrations WHERE name = %s", (path.name,)).fetchone()
            if existing:
                if existing["checksum"] != checksum:
                    raise DomainError("migration_conflict")
                continue
            connection.execute(script, prepare=False)
            connection.execute("INSERT INTO domain_schema_migrations (name, checksum) VALUES (%s, %s)", (path.name, checksum))
            applied += 1
    return applied


def main(argv=None):
    parser = argparse.ArgumentParser(description="Apply domain migrations before payment migrations.")
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args(argv)
    try:
        count = apply_migrations(DomainDatabase.from_environment(env_file=args.env_file))
        print(f"Applied {count} domain migration(s).")
        return 0
    except DomainError as error:
        print(f"Domain migration failed [{error.code}]: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
