"""Aplica migraciones Alembic solo cuando hay cambios pendientes."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


def run_alembic_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = ["alembic", "-c", str(ALEMBIC_INI), *args]
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def parse_revision(output: str) -> list[str]:
    revisions = []
    for line in output.splitlines():
        token = line.strip()
        if not token:
            continue
        parts = token.split()
        for part in parts:
            if part.replace("_", "").isalnum() and len(part) >= 7:
                revisions.append(part.strip(","))
                break
    return revisions


def main() -> int:
    load_dotenv()
    current_proc = run_alembic_command(["current"])
    if current_proc.returncode != 0:
        sys.stderr.write(current_proc.stderr)
        return current_proc.returncode
    heads_proc = run_alembic_command(["heads"])
    if heads_proc.returncode != 0:
        sys.stderr.write(heads_proc.stderr)
        return heads_proc.returncode

    current_revs = parse_revision(current_proc.stdout)
    head_revs = parse_revision(heads_proc.stdout)

    current_set = set(current_revs)
    head_set = set(head_revs)

    if current_set == head_set:
        print("Alembic: base actual ya está en la última revisión, no se aplica upgrade.")
        return 0

    upgrade_proc = run_alembic_command(["upgrade", "head"])
    sys.stdout.write(upgrade_proc.stdout)
    sys.stderr.write(upgrade_proc.stderr)
    return upgrade_proc.returncode


if __name__ == "__main__":
    sys.exit(main())
