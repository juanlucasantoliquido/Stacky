#!/usr/bin/env python3
"""
batch_test_gen.py — Stacky Tool: Generador de Tests Unitarios para Batch

ACCIONES:
  list      Lista todos los procesos batch detectados con sus sub-procesos
  scan      Analiza un proceso batch en detalle
  generate  Genera archivos .cs de tests NUnit para uno o todos los procesos
  diff      Muestra cambios en trunk/Batch respecto al ultimo scan guardado
  watch     Monitorea trunk/Batch y regenera tests automaticamente ante cambios
  enrich    Enriquece assertions de tests via Copilot (requiere VS Code + Stacky extension)

SALIDA: JSON a stdout  |  tabla formateada con --pretty
ERRORES: JSON con "ok": false + exit code 1

CONFIGURACIÓN:
  config.json en la misma carpeta que este script

EJEMPLOS:
  python batch_test_gen.py list
  python batch_test_gen.py list --pretty
  python batch_test_gen.py scan RSProcIN
  python batch_test_gen.py scan RSProcOUT --pretty
  python batch_test_gen.py scan --all --pretty
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

# ─── PATHS ───────────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent
_CONFIG_FILE = _SCRIPT_DIR / "config.json"

# ─── CONFIG ──────────────────────────────────────────────────────────────────


def _load_config() -> dict:
    if _CONFIG_FILE.is_file():
        try:
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            _error(f"Error al leer config.json: {exc}")
    _error("config.json no encontrado. Crea uno basándote en config.example.json")
    return {}  # unreachable


def _resolve_paths(cfg: dict) -> tuple[Path, Path, Path]:
    """Resuelve batch_root, negocio_root y output_root desde config."""
    base = _SCRIPT_DIR

    def resolve(key: str) -> Path:
        raw = cfg.get(key, "")
        if not raw:
            _error(f"config.json: falta la clave '{key}'")
        p = Path(raw)
        return p if p.is_absolute() else (base / p).resolve()

    return resolve("batch_root"), resolve("negocio_root"), resolve("output_root")


# ─── OUTPUT HELPERS ───────────────────────────────────────────────────────────


def _out(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _error(msg: str, code: int = 1) -> None:
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False, indent=2))
    sys.exit(code)


def _section(title: str) -> None:
    width = 60
    print(f"\n{'-' * width}")
    print(f"  {title}")
    print(f"{'-' * width}")


def _kv(key: str, value: Any, indent: int = 2) -> None:
    pad = " " * indent
    print(f"{pad}{key:<22} {value}")


# ─── SERIALIZACIÓN ────────────────────────────────────────────────────────────


def _serialize_subproc(sp) -> dict:
    return {
        "name": sp.name,
        "constant_value": sp.constant_value,
        "type": sp.subproc_type.value,
        "enabled_in_xml": sp.enabled_in_xml,
        "biz_namespace": sp.biz_namespace,
        "biz_class": sp.biz_class,
        "dalc_class": sp.dalc_class,
        "biz_methods": [
            {"name": m.name, "return_type": m.return_type, "params": m.params}
            for m in sp.biz_methods
        ],
    }


def _serialize_process(bp) -> dict:
    return {
        "name": bp.name,
        "main_class": bp.main_class,
        "main_cs": str(bp.main_cs_path),
        "xml_config": str(bp.xml_config_path) if bp.xml_config_path else None,
        "sub_process_count": len(bp.sub_processes),
        "sub_processes": [_serialize_subproc(sp) for sp in bp.sub_processes],
        "xml_parameters": bp.xml_parameters,
        "warnings": bp.warnings,
    }


# ─── PRETTY PRINT ─────────────────────────────────────────────────────────────


def _pretty_list(processes: list) -> None:
    total_sp = sum(len(bp.sub_processes) for bp in processes)
    _section(f"PROCESOS BATCH DETECTADOS  ({len(processes)} procesos / {total_sp} sub-procesos)")

    for bp in processes:
        warn_tag = f"  [{len(bp.warnings)} warn]" if bp.warnings else ""
        print(f"\n  > {bp.name:<22} clase:{bp.main_class:<20}{warn_tag}")
        for sp in bp.sub_processes:
            xml_tag = ""
            if sp.enabled_in_xml is True:
                xml_tag = " [XML:ON]"
            elif sp.enabled_in_xml is False:
                xml_tag = " [XML:OFF]"
            methods_str = ", ".join(m.name for m in sp.biz_methods[:3])
            if len(sp.biz_methods) > 3:
                methods_str += f" +{len(sp.biz_methods)-3}"
            biz_full = f"{sp.biz_namespace}.{sp.biz_class}" if sp.biz_namespace else sp.biz_class
            print(
                f"      [{sp.constant_value}] {sp.name:<22} -> {biz_full:<30}"
                f"  metodos:[{methods_str}]{xml_tag}"
            )

    print()


def _pretty_scan(bp) -> None:
    _section(f"ANÁLISIS: {bp.name}")
    _kv("Clase principal:", bp.main_class)
    _kv("Archivo .cs:", bp.main_cs_path.name)
    _kv("XML config:", bp.xml_config_path.name if bp.xml_config_path else "—")
    _kv("Sub-procesos:", len(bp.sub_processes))

    if bp.xml_parameters:
        print("\n  Parámetros XML:")
        for k, v in bp.xml_parameters.items():
            _kv(k + ":", v, indent=4)

    for sp in bp.sub_processes:
        _section(f"  SUB-PROCESO: {sp.name}  (valor={sp.constant_value}, tipo={sp.subproc_type.value})")
        _kv("Habilitado en XML:", sp.enabled_in_xml if sp.enabled_in_xml is not None else "no figura")
        _kv("Clase de negocio:", f"{sp.biz_namespace}.{sp.biz_class}" if sp.biz_namespace else sp.biz_class or "-")
        _kv("Clase DALC:", sp.dalc_class or "-")
        if sp.biz_methods:
            print(f"  {'Metodos detectados:':22}")
            for m in sp.biz_methods:
                params = ", ".join(m.params) if m.params else ""
                print(f"    * {m.return_type:<12} {m.name}({params})")
        else:
            _kv("Metodos:", "no detectados")

    if bp.warnings:
        print("\n  ADVERTENCIAS:")
        for w in bp.warnings:
            print(f"    - {w}")
    print()


# ─── ACCIONES ────────────────────────────────────────────────────────────────


def cmd_list(args: argparse.Namespace, cfg: dict) -> None:
    from core.scanner import scan_batch_folder

    batch_root, negocio_root, _ = _resolve_paths(cfg)
    excluded = set(cfg.get("excluded_processes", []))

    processes = scan_batch_folder(batch_root, negocio_root, excluded or None)

    if not processes:
        _error("No se encontraron procesos batch en " + str(batch_root))

    if args.pretty:
        _pretty_list(processes)
    else:
        _out({"ok": True, "processes": [_serialize_process(bp) for bp in processes]})


def cmd_scan(args: argparse.Namespace, cfg: dict) -> None:
    from core.scanner import scan_batch_folder, scan_single_process

    batch_root, negocio_root, _ = _resolve_paths(cfg)
    excluded = set(cfg.get("excluded_processes", []))

    if args.all:
        processes = scan_batch_folder(batch_root, negocio_root, excluded or None)
    else:
        if not args.process:
            _error("Debes especificar un nombre de proceso o usar --all")
        bp = scan_single_process(args.process, batch_root, negocio_root)
        processes = [bp] if bp else []

    if not processes:
        _error("Proceso no encontrado o sin sub-procesos detectados.")

    if args.pretty:
        for bp in processes:
            _pretty_scan(bp)
    else:
        data = [_serialize_process(bp) for bp in processes]
        _out({"ok": True, "processes": data})


def cmd_generate(args: argparse.Namespace, cfg: dict) -> None:
    from core.scanner import scan_batch_folder, scan_single_process
    from core.template_engine import generate_tests_for_process

    batch_root, negocio_root, output_root = _resolve_paths(cfg)
    excluded = set(cfg.get("excluded_processes", []))

    # Resolver output_root (puede venir del flag --output)
    if hasattr(args, "output") and args.output:
        output_root = Path(args.output)

    output_root.mkdir(parents=True, exist_ok=True)

    # Determinar procesos a generar
    if getattr(args, "all", False):
        processes = scan_batch_folder(batch_root, negocio_root, excluded or None)
    else:
        if not args.process:
            _error("Debes especificar un nombre de proceso o usar --all")
        bp = scan_single_process(args.process, batch_root, negocio_root)
        processes = [bp] if bp else []

    if not processes:
        _error("No se encontraron procesos para generar.")

    force = getattr(args, "force", False)
    summary: list[dict] = []

    for bp in processes:
        result = generate_tests_for_process(bp, output_root, force=force)
        summary.append({
            "process": bp.name,
            "output_dir": str(output_root / bp.name),
            "created": result["created"],
            "updated": result["updated"],
            "skipped": result["skipped"],
        })

    if getattr(args, "pretty", False):
        _section(f"TESTS GENERADOS  ({len(processes)} proceso(s))")
        for s in summary:
            print(f"\n  > {s['process']}")
            print(f"    Carpeta: {s['output_dir']}")
            if s["created"]:
                print(f"    Creados ({len(s['created'])}):")
                for f in s["created"]:
                    print(f"      + {f}")
            if s["updated"]:
                print(f"    Actualizados ({len(s['updated'])}):")
                for f in s["updated"]:
                    print(f"      ~ {f}")
            if s["skipped"]:
                print(f"    Omitidos ({len(s['skipped'])}):")
                for f in s["skipped"]:
                    print(f"      = {f}")
        total_created = sum(len(s["created"]) for s in summary)
        total_updated = sum(len(s["updated"]) for s in summary)
        print(f"\n  Total: {total_created} archivos creados, {total_updated} actualizados.\n")
    else:
        _out({"ok": True, "summary": summary})


def cmd_diff(args: argparse.Namespace, cfg: dict) -> None:
    from core.scanner import scan_batch_folder
    from core.state_tracker import compute_diff, load_state, save_state

    batch_root, negocio_root, output_root = _resolve_paths(cfg)
    excluded = set(cfg.get("excluded_processes", []))

    current = scan_batch_folder(batch_root, negocio_root, excluded or None)
    old_state = load_state(_SCRIPT_DIR)
    diff = compute_diff(old_state, current)

    if args.save or getattr(args, "auto_generate", False):
        save_state(_SCRIPT_DIR, current, batch_root)

    if getattr(args, "auto_generate", False) and diff.has_changes:
        from core.template_engine import generate_tests_for_process
        output_root.mkdir(parents=True, exist_ok=True)
        targets = (
            diff.new_processes
            + list(diff.new_subprocs.keys())
            + diff.changed_source
        )
        generated: list[str] = []
        for name in set(targets):
            bp = next((p for p in current if p.name == name), None)
            if bp:
                result = generate_tests_for_process(bp, output_root, force=False)
                if result["created"] or result["updated"]:
                    generated.append(name)
        if getattr(args, "pretty", False) and generated:
            print(f"\n  Tests regenerados para: {', '.join(generated)}")

    if getattr(args, "pretty", False):
        if not diff.has_changes:
            if old_state is None:
                print("\n  Sin estado previo. Ejecuta 'diff --save' para guardar el estado actual.")
            else:
                print("\n  Sin cambios detectados desde el ultimo scan.\n")
        else:
            _section(f"CAMBIOS DETECTADOS en trunk/Batch")
            for line in diff.summary_lines():
                print(line)
            print()
    else:
        _out({
            "ok": True,
            "has_changes": diff.has_changes,
            "new_processes": diff.new_processes,
            "removed_processes": diff.removed_processes,
            "new_subprocs": diff.new_subprocs,
            "removed_subprocs": diff.removed_subprocs,
            "changed_methods": diff.changed_methods,
            "changed_source": diff.changed_source,
        })


def cmd_watch(args: argparse.Namespace, cfg: dict) -> None:
    """Monitorea trunk/Batch en un loop, detecta cambios y regenera tests."""
    import time
    from core.scanner import scan_batch_folder
    from core.state_tracker import compute_diff, load_state, save_state
    from core.template_engine import generate_tests_for_process

    batch_root, negocio_root, output_root = _resolve_paths(cfg)
    excluded = set(cfg.get("excluded_processes", []))
    interval = getattr(args, "interval", 30)
    auto_gen = getattr(args, "auto_generate", True)

    output_root.mkdir(parents=True, exist_ok=True)

    print(f"\n  [watch] Monitoreando {batch_root}")
    print(f"  [watch] Intervalo: {interval}s | Auto-generate: {auto_gen}")
    print("  [watch] Ctrl+C para detener.\n")

    # Snapshot inicial
    current = scan_batch_folder(batch_root, negocio_root, excluded or None)
    save_state(_SCRIPT_DIR, current, batch_root)
    print(f"  [watch] Estado inicial: {len(current)} procesos.")

    try:
        while True:
            time.sleep(interval)
            new_scan = scan_batch_folder(batch_root, negocio_root, excluded or None)
            old_state = load_state(_SCRIPT_DIR)
            diff = compute_diff(old_state, new_scan)

            if diff.has_changes:
                print(f"\n  [watch] Cambios detectados:")
                for line in diff.summary_lines():
                    print(f"  {line}")

                if auto_gen:
                    targets = set(
                        diff.new_processes
                        + list(diff.new_subprocs.keys())
                        + diff.changed_source
                    )
                    for name in targets:
                        bp = next((p for p in new_scan if p.name == name), None)
                        if bp:
                            result = generate_tests_for_process(bp, output_root, force=False)
                            total = len(result["created"]) + len(result["updated"])
                            print(f"  [watch] {name}: {total} archivos generados/actualizados.")

                save_state(_SCRIPT_DIR, new_scan, batch_root)
            else:
                from datetime import datetime
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"  [watch] {ts} — Sin cambios.", end="\r")

    except KeyboardInterrupt:
        print("\n  [watch] Detenido.\n")


def cmd_enrich(args: argparse.Namespace, cfg: dict) -> None:
    from core.lm_enricher import bridge_available, enrich_test_file
    from core.scanner import scan_batch_folder, scan_single_process

    batch_root, negocio_root, output_root = _resolve_paths(cfg)
    excluded = set(cfg.get("excluded_processes", []))
    model = getattr(args, "model", "claude-sonnet-4.5")
    dry_run = getattr(args, "dry_run", False)
    target_subproc = getattr(args, "subproc", None)

    # Verificar bridge
    if not bridge_available():
        _error(
            "VS Code Bridge no disponible en 127.0.0.1:5052.\n"
            "  1. Abre VS Code\n"
            "  2. Asegurate de tener la extension Stacky Agents instalada\n"
            "  3. Verifica que el bridge HTTP este activo"
        )

    # Determinar procesos
    if getattr(args, "all", False):
        processes = scan_batch_folder(batch_root, negocio_root, excluded or None)
    else:
        if not args.process:
            _error("Especifica un proceso o usa --all")
        bp = scan_single_process(args.process, batch_root, negocio_root)
        processes = [bp] if bp else []

    if not processes:
        _error("No se encontraron procesos.")

    results: list[dict] = []

    for bp in processes:
        for sp in bp.sub_processes:
            if target_subproc and sp.name != target_subproc:
                continue
            test_file = output_root / bp.name / f"Test_{bp.name}_{sp.name}.cs"
            result = enrich_test_file(
                test_file=test_file,
                biz_namespace=sp.biz_namespace,
                biz_class=sp.biz_class,
                dalc_class=sp.dalc_class,
                negocio_root=negocio_root,
                process_name=bp.name,
                subproc_name=sp.name,
                model=model,
                dry_run=dry_run,
            )
            result["process"] = bp.name
            result["subproc"] = sp.name
            result["file"] = test_file.name
            results.append(result)

    if getattr(args, "pretty", False):
        ok_count = sum(1 for r in results if r["ok"] and r["status"] == "enriched")
        dry_count = sum(1 for r in results if r["status"] == "dry_run")
        skip_count = sum(1 for r in results if r["status"] == "skipped")
        err_count = sum(1 for r in results if not r["ok"] and r["status"] not in ("skipped", "dry_run"))
        _section(f"ENRIQUECIMIENTO LLM  ({len(results)} sub-procesos)")
        for r in results:
            if r["ok"] and r["status"] == "enriched":
                icon = "+"
            elif r["status"] == "dry_run":
                icon = "~"
            elif r["status"] == "skipped":
                icon = "="
            else:
                icon = "!"
            print(f"  [{icon}] {r['process']}.{r['subproc']:<22}  {r['message']}")
        extra = f" | Dry-run: {dry_count}" if dry_count else ""
        print(f"\n  Enriquecidos: {ok_count} | Omitidos: {skip_count} | Errores: {err_count}{extra}\n")
    else:
        _out({"ok": True, "results": results})


# ─── MAIN ─────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="batch_test_gen",
        description="Stacky Tool — Generador de Tests Unitarios para procesos Batch",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nivel de logging interno (default: WARNING)",
    )

    sub = parser.add_subparsers(dest="action", required=True)

    # list
    p_list = sub.add_parser("list", help="Lista todos los procesos batch detectados")
    p_list.add_argument("--pretty", action="store_true", help="Salida formateada en tabla")

    # scan
    p_scan = sub.add_parser("scan", help="Analiza un proceso batch en detalle")
    p_scan.add_argument("process", nargs="?", help="Nombre del proceso (ej: RSProcIN)")
    p_scan.add_argument("--all", action="store_true", help="Analiza todos los procesos")
    p_scan.add_argument("--pretty", action="store_true", help="Salida formateada")

    # generate
    p_gen = sub.add_parser("generate", help="Genera archivos .cs de tests NUnit")
    p_gen.add_argument("process", nargs="?", help="Nombre del proceso (ej: RSProcIN)")
    p_gen.add_argument("--all", action="store_true", help="Genera tests para todos los procesos")
    p_gen.add_argument("--pretty", action="store_true", help="Salida formateada")
    p_gen.add_argument("--force", action="store_true", help="Sobreescribe archivos existentes")
    p_gen.add_argument("--output", help="Carpeta de salida (override de output_root en config.json)")

    # diff
    p_diff = sub.add_parser("diff", help="Muestra cambios en trunk/Batch vs ultimo scan guardado")
    p_diff.add_argument("--pretty", action="store_true", help="Salida formateada")
    p_diff.add_argument("--save", action="store_true", help="Guarda el estado actual tras el diff")
    p_diff.add_argument("--auto-generate", action="store_true",
                        help="Genera tests automaticamente para los cambios detectados")

    # watch
    p_watch = sub.add_parser("watch", help="Monitorea trunk/Batch y regenera tests ante cambios")
    p_watch.add_argument("--interval", type=int, default=30,
                         help="Segundos entre escaneos (default: 30)")
    p_watch.add_argument("--auto-generate", action="store_true",
                         help="Genera tests automaticamente ante cambios (default: True)", default=True)
    p_watch.add_argument("--no-auto-generate", dest="auto_generate", action="store_false")

    # enrich
    p_enrich = sub.add_parser("enrich", help="Enriquece tests con assertions reales via Copilot")
    p_enrich.add_argument("process", nargs="?", help="Nombre del proceso (ej: RSProcIN)")
    p_enrich.add_argument("--all", action="store_true", help="Enriquece todos los procesos")
    p_enrich.add_argument("--subproc", help="Solo un sub-proceso especifico (ej: RESCAMPTEL)")
    p_enrich.add_argument("--model", default="claude-sonnet-4.5",
                          help="Modelo LLM a usar (default: claude-sonnet-4.5)")
    p_enrich.add_argument("--dry-run", action="store_true",
                          help="Simula sin escribir archivos")
    p_enrich.add_argument("--pretty", action="store_true", help="Salida formateada")

    return parser


def main() -> None:
    # Forzar UTF-8 en stdout para evitar errores cp1252 en Windows
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s: %(message)s",
    )

    cfg = _load_config()

    if args.action == "list":
        cmd_list(args, cfg)
    elif args.action == "scan":
        cmd_scan(args, cfg)
    elif args.action == "generate":
        cmd_generate(args, cfg)
    elif args.action == "diff":
        cmd_diff(args, cfg)
    elif args.action == "watch":
        cmd_watch(args, cfg)
    elif args.action == "enrich":
        cmd_enrich(args, cfg)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
