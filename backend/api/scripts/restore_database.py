from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def postgres_url(value: str) -> str:
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a FVENTAS PostgreSQL custom-format backup.")
    parser.add_argument("backup_file")
    parser.add_argument("--database-url", default=os.environ.get("FVENTAS_DATABASE_URL", ""))
    parser.add_argument("--yes", action="store_true", help="Confirm destructive restore.")
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("Este restore reemplaza datos. Reejecuta con --yes para confirmar.")
    if not args.database_url:
        raise SystemExit("FVENTAS_DATABASE_URL es obligatorio.")
    if not args.database_url.startswith("postgresql"):
        raise SystemExit("Restore productivo solo soporta PostgreSQL.")

    backup_path = Path(args.backup_file)
    if not backup_path.exists():
        raise SystemExit(f"Backup no encontrado: {backup_path}")

    command = [
        "pg_restore",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--dbname",
        postgres_url(args.database_url),
        str(backup_path),
    ]
    subprocess.run(command, check=True)
    print(f"Backup restaurado: {backup_path}")


if __name__ == "__main__":
    main()
