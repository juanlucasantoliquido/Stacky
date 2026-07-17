"""CLI del verificador de integridad (Plan 130). Exit: 0 ok, 1 hallazgos, 2 error interno."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ importable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verifica sintaxis e imports del backend sin ejecutar codigo.")
    parser.add_argument("--root", default=None, help="Raiz a escanear (default: backend/)")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        from services.code_integrity import run_checks
        report = run_checks(Path(args.root) if args.root else None)
    except Exception as exc:  # error interno del verificador, NUNCA del codigo analizado
        print(f"[code-integrity] error interno: {type(exc).__name__}", file=sys.stderr)
        return 2
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        for f in report["syntax_errors"]:
            print(f"{f['file']}:{f['line']} — {f['message']}")
        for f in report["broken_imports"]:
            print(f"{f['file']}:{f['line']} — import roto: {f['import']}")
        total = len(report["syntax_errors"]) + len(report["broken_imports"])
        print(f"[code-integrity] {report['files_scanned']} archivos, {total} hallazgos, {report['elapsed_ms']} ms")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
