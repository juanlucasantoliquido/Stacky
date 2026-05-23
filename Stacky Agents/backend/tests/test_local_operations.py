from __future__ import annotations

import logging
import os
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def test_daily_file_logging_writes_and_exports_zip(tmp_path):
    from services.local_file_logging import _DailyStackyFileHandler, build_logs_zip

    log_dir = tmp_path / "logs"
    handler = _DailyStackyFileHandler(log_dir)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger = logging.getLogger("stacky.test.local_file")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    logger.warning("phase4 file log")
    handler.close()
    logger.removeHandler(handler)

    today_log = log_dir / f"stacky-{date.today():%Y-%m-%d}.log"
    assert today_log.exists()
    assert "phase4 file log" in today_log.read_text(encoding="utf-8")

    payload = build_logs_zip(days=3, base_dir=log_dir)
    zip_path = tmp_path / "logs.zip"
    zip_path.write_bytes(payload)
    with zipfile.ZipFile(zip_path) as zf:
        assert today_log.name in zf.namelist()


def test_db_backup_keeps_latest_four(tmp_path, monkeypatch):
    from services import db_backup

    db = tmp_path / "stacky_agents.db"
    db.write_bytes(b"sqlite-db")

    monkeypatch.setattr(db_backup, "sqlite_db_path", lambda database_url=None: db)
    monkeypatch.setattr(db_backup, "backups_dir", lambda: tmp_path / "backups")

    first = db_backup.ensure_weekly_backup(today=date(2026, 5, 22))
    assert first["ok"] is True
    assert first["skipped"] is False
    assert Path(first["backup_path"]).exists()

    second = db_backup.ensure_weekly_backup(today=date(2026, 5, 23))
    assert second["skipped"] is True
    assert second["reason"] == "already_backed_up_this_week"

    for offset in range(1, 7):
        db_backup.ensure_weekly_backup(today=date(2026, 5, 22) + timedelta(days=offset * 7))

    backups = sorted((tmp_path / "backups").glob("stacky_agents-*.db"))
    assert len(backups) == 4
