from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = APP_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.secrets_store import read_secret_from_file  # noqa: E402


AUTH_FIELDS = {
    "ado_auth.json": [("pat", "pat_format")],
    "jira_auth.json": [("token", "token_format"), ("password", "password_format")],
    "mantis_auth.json": [("token", "token_format"), ("password", "password_format")],
}

DATA_CONFIG_FILES = [
    "active_project.json",
    "flow_config.json",
    "preferences.json",
    "ui_sections.json",
    "runtime_config.json",
]


def copy_tree_clean(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if dst.exists():
        shutil.rmtree(dst)
    ignore = shutil.ignore_patterns(
        "vscode_instance.json",
        "*.log",
        "__pycache__",
        ".pytest_cache",
    )
    shutil.copytree(src, dst, ignore=ignore)


def export_auth_file(path: Path) -> bool:
    fields = AUTH_FIELDS.get(path.name)
    if not fields or not path.is_file():
        return False

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False

    changed = False
    for field, format_field in fields:
        if not payload.get(field):
            continue
        try:
            resolved = read_secret_from_file(
                path,
                field,
                format_field=format_field,
                allow_preencoded=(field == "pat"),
                detect_preencoded=(field == "pat"),
            )
        except Exception:
            continue
        if not resolved.value:
            continue
        payload[field] = resolved.value
        payload[format_field] = "preencoded" if resolved.is_preencoded else "raw"
        changed = True

    if changed:
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return changed


def export_project_secrets(projects_dir: Path) -> int:
    count = 0
    for auth_file in projects_dir.glob("*/auth/*.json"):
        if export_auth_file(auth_file):
            count += 1
    return count


def copy_data_config(src_data: Path, dst_data: Path) -> int:
    dst_data.mkdir(parents=True, exist_ok=True)
    count = 0
    for name in DATA_CONFIG_FILES:
        src = src_data / name
        if src.is_file():
            shutil.copy2(src, dst_data / name)
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-projects", required=True)
    parser.add_argument("--source-data", required=True)
    parser.add_argument("--release-root", required=True)
    args = parser.parse_args()

    source_projects = Path(args.source_projects).resolve()
    source_data = Path(args.source_data).resolve()
    release_root = Path(args.release_root).resolve()

    release_projects = release_root / "projects"
    release_data = release_root / "data"

    copy_tree_clean(source_projects, release_projects)
    auth_count = export_project_secrets(release_projects)
    data_count = copy_data_config(source_data, release_data)

    summary = {
        "projects_source": str(source_projects),
        "data_source": str(source_data),
        "projects_exported": len([p for p in release_projects.iterdir() if p.is_dir()]) if release_projects.exists() else 0,
        "auth_files_exported": auth_count,
        "data_config_files_exported": data_count,
        "credential_format": "portable_raw_reencrypt_on_first_use",
    }
    (release_root / "EXPORT_CONFIG_INFO.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
