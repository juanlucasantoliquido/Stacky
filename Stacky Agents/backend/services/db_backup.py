from __future__ import annotations

import re
import shutil
from datetime import date, datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from config import config
from runtime_paths import data_dir

BACKUP_KEEP = 4
_BACKUP_RE = re.compile(r"^stacky_agents-(\d{8})\.db$")


def backups_dir() -> Path:
    return data_dir() / "backups"


def sqlite_db_path(database_url: str | None = None) -> Path | None:
    raw_url = database_url or config.DATABASE_URL
    try:
        url = make_url(raw_url)
    except Exception:
        return None

    if url.get_backend_name() != "sqlite":
        return None
    database = url.database or ""
    if not database or database == ":memory:" or database.startswith("file:"):
        return None

    path = Path(database)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve(strict=False)


def ensure_weekly_backup(today: date | None = None) -> dict:
    today = today or date.today()
    source = sqlite_db_path()
    backup_dir = backups_dir()

    if source is None:
        return {"ok": True, "skipped": True, "reason": "non_sqlite_database", "backup_path": None}
    if not source.exists():
        return {"ok": False, "skipped": True, "reason": "database_missing", "backup_path": None}

    backup_dir.mkdir(parents=True, exist_ok=True)
    existing_this_week = [
        path
        for path in backup_dir.glob("stacky_agents-*.db")
        if _same_iso_week(_date_from_backup(path), today)
    ]
    if existing_this_week:
        prune_old_backups(backup_dir)
        newest = sorted(existing_this_week, reverse=True)[0]
        return {"ok": True, "skipped": True, "reason": "already_backed_up_this_week", "backup_path": str(newest)}

    target = backup_dir / f"stacky_agents-{today:%Y%m%d}.db"
    shutil.copy2(source, target)
    prune_old_backups(backup_dir)
    return {"ok": True, "skipped": False, "reason": None, "backup_path": str(target)}


def list_backups() -> list[dict]:
    backup_dir = backups_dir()
    if not backup_dir.exists():
        return []
    items = []
    for path in sorted(backup_dir.glob("stacky_agents-*.db"), reverse=True):
        try:
            stat = path.stat()
        except OSError:
            continue
        items.append({
            "path": str(path),
            "filename": path.name,
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return items


def prune_old_backups(backup_dir: Path | None = None, keep: int = BACKUP_KEEP) -> int:
    base = backup_dir or backups_dir()
    if not base.exists():
        return 0
    backups = sorted(
        [path for path in base.glob("stacky_agents-*.db") if _date_from_backup(path) is not None],
        reverse=True,
    )
    deleted = 0
    for path in backups[keep:]:
        try:
            path.unlink()
            deleted += 1
        except OSError:
            continue
    return deleted


def _date_from_backup(path: Path) -> date | None:
    match = _BACKUP_RE.match(path.name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def _same_iso_week(left: date | None, right: date) -> bool:
    if left is None:
        return False
    return left.isocalendar()[:2] == right.isocalendar()[:2]
