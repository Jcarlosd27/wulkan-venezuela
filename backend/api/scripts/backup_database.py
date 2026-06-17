from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def postgres_url(value: str) -> str:
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a PostgreSQL custom-format backup for FVENTAS.")
    parser.add_argument("--database-url", default=os.environ.get("FVENTAS_DATABASE_URL", ""))
    parser.add_argument("--output-dir", default=os.environ.get("FVENTAS_BACKUP_DIR", "backups"))
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("FVENTAS_DATABASE_URL es obligatorio.")
    if not args.database_url.startswith("postgresql"):
        raise SystemExit("Backup productivo solo soporta PostgreSQL.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_file = output_dir / f"fventas-{timestamp}.dump"
    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--file",
        str(output_file),
        postgres_url(args.database_url),
    ]
    subprocess.run(command, check=True)
    print(f"Backup creado: {output_file}")


if __name__ == "__main__":
    main()
