"""Run the minimal QA UAT commitment smoke with local AgendaWeb credentials.

This is intentionally small: one Playwright spec, one customer, one flow.
It loads secrets from Tools/Stacky/.secrets/agenda_web.env, forces a clean
login by default, and writes a short JSON summary next to the screenshots.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STACKY_ROOT = ROOT.parents[1]
DEFAULT_SECRETS = STACKY_ROOT / ".secrets" / "agenda_web.env"
DEFAULT_CLIENTE = "7780380119179197"
SPEC = ROOT / "playwright" / "smoke" / "compromiso_minimo.spec.ts"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run compromiso minimo QA UAT smoke.")
    parser.add_argument("--cliente", default=DEFAULT_CLIENTE, help="CLCOD/OCRAIZ del cliente.")
    parser.add_argument("--monto", default="50000", help="Monto de proyeccion a cargar.")
    parser.add_argument("--secrets", default=str(DEFAULT_SECRETS), help="Path a agenda_web.env.")
    visibility = parser.add_mutually_exclusive_group()
    visibility.add_argument("--headed", dest="headed", action="store_true", default=True,
                            help="Abrir browser visible (default).")
    visibility.add_argument("--headless", dest="headed", action="store_false",
                            help="Correr con browser oculto.")
    parser.add_argument("--reuse-auth", action="store_true", help="No borrar .auth antes de correr.")
    args = parser.parse_args(argv)

    env = os.environ.copy()
    load_env_file(Path(args.secrets), env)

    missing = [k for k in ("AGENDA_WEB_BASE_URL", "AGENDA_WEB_USER", "AGENDA_WEB_PASS") if not env.get(k)]
    if missing:
        print(
            "BLOCKED missing required env vars: " + ", ".join(missing) +
            f". Source {args.secrets} or set them in the shell.",
            file=sys.stderr,
        )
        return 2

    run_id = datetime.now(timezone.utc).strftime("compromiso-%Y%m%dT%H%M%SZ")
    evidence_dir = ROOT / "evidence" / "manual" / f"{run_id}-{args.cliente}"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    if not args.reuse_auth:
        reset_auth_cache(ROOT / ".auth")

    env.update({
        "QA_UAT_COMPROMISO_CLCOD": str(args.cliente),
        "QA_UAT_COMPROMISO_MONTO": str(args.monto),
        "QA_UAT_COMPROMISO_EVIDENCE_DIR": str(evidence_dir),
        "QA_UAT_TEST_TIMEOUT_MS": env.get("QA_UAT_TEST_TIMEOUT_MS", "120000"),
        "QA_UAT_EXPECT_TIMEOUT_MS": env.get("QA_UAT_EXPECT_TIMEOUT_MS", "10000"),
        "QA_UAT_ACTION_TIMEOUT_MS": env.get("QA_UAT_ACTION_TIMEOUT_MS", "15000"),
        "QA_UAT_NAV_TIMEOUT_MS": env.get("QA_UAT_NAV_TIMEOUT_MS", "30000"),
        "QA_UAT_RETRIES": "0",
        "QA_UAT_WORKERS": "1",
        "QA_UAT_TRACE": env.get("QA_UAT_TRACE", "retain-on-failure"),
        "QA_UAT_SCREENSHOT": env.get("QA_UAT_SCREENSHOT", "only-on-failure"),
        "QA_UAT_VIDEO": env.get("QA_UAT_VIDEO", "retain-on-failure"),
        "QA_UAT_HEADED": "true" if args.headed else "false",
        "STACKY_QA_UAT_HEADLESS": "0" if args.headed else "1",
        "STACKY_QA_UAT_SLOW_MO": env.get("STACKY_QA_UAT_SLOW_MO", "500" if args.headed else "0"),
    })

    playwright = ROOT / "node_modules" / ".bin" / "playwright.cmd"
    if not playwright.exists():
        playwright = ROOT / "node_modules" / ".bin" / "playwright"

    cmd = [
        str(playwright),
        "test",
        "./" + SPEC.relative_to(ROOT).as_posix(),
        "--workers=1",
        "--reporter=list",
    ]

    print(f"RUN {run_id}")
    print(f"CLIENTE {args.cliente}")
    print(f"URL {env['AGENDA_WEB_BASE_URL']}")
    print(f"EVIDENCE {evidence_dir}")

    started = datetime.now(timezone.utc)
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )

    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    summary = {
        "run_id": run_id,
        "cliente": str(args.cliente),
        "base_url": env["AGENDA_WEB_BASE_URL"],
        "headed": bool(args.headed),
        "reuse_auth": bool(args.reuse_auth),
        "spec": str(SPEC),
        "evidence_dir": str(evidence_dir),
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    (evidence_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return proc.returncode


def load_env_file(path: Path, env: dict[str, str]) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        env[key.strip()] = value


def reset_auth_cache(auth_dir: Path) -> None:
    auth_dir.mkdir(parents=True, exist_ok=True)
    for name in ("agenda.json", "agenda.fingerprint.json"):
        target = (auth_dir / name).resolve()
        if target.parent != auth_dir.resolve():
            raise RuntimeError(f"Refusing to remove auth path outside auth dir: {target}")
        try:
            target.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
