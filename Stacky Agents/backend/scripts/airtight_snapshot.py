"""scripts/airtight_snapshot.py — Plan 258 F7. Guard de estanqueidad del arnes.

EL INVARIANTE, uno solo: *una corrida del arnes no debe modificar ningun
artefacto de runtime del operador.* Un enunciado verificable que cubre los
archivos presentes Y los futuros — a diferencia de perseguir la contaminacion
marcador por marcador (`myproject` en ci_runs, el tmpdir de pytest en
env_applies), que es artesanal y no escala: `build_runs.jsonl` aparecio sin que
nadie lo notara.

Como se usa (el runner del arnes ya itera POR ARCHIVO, que es el gotcha de la
casa; por eso esto es un WRAPPER del runner y no un test dentro de la suite):

    cd "N:\\GIT\\RS\\STACKY\\Stacky\\Stacky Agents\\backend"
    .venv\\Scripts\\python.exe scripts/airtight_snapshot.py --save
    bash scripts/run_harness_tests.sh
    .venv\\Scripts\\python.exe scripts/airtight_snapshot.py --verify

`--verify` sale con codigo 1 y NOMBRA cada artefacto contaminado con su delta
de bytes. Eso habria atrapado `env_applies.jsonl` el primer dia.

Sin dependencias externas y READ-ONLY sobre el arbol vigilado: solo huellea y
compara. Lo unico que escribe es su propia huella, y la deja FUERA del arbol
(en el temporal del sistema) para no ser su propio falso positivo.

`snapshot` y `diff_snapshots` son homonimos de los de `services/dbcompare_diff.py`
(otro dominio, otra firma, otro modulo): no hay colision, este archivo no se
importa desde ningun runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

# Rutas vigiladas: TODO artefacto de runtime del operador.
WATCHED_GLOBS: tuple[str, ...] = (
    "data/*.jsonl",
    "data/**/*.jsonl",       # incluye data/db_compare/sql_exec_ledger.jsonl
    "data/logs/*.log",
    "data/*.db",
    "data/*.db-wal",         # la base corre en WAL (plan 253): el -wal es parte del dato
    "data/*.db-shm",
)

# La huella NO vive bajo el arbol vigilado: seria su propio falso positivo.
SNAPSHOT_FILE = Path(tempfile.gettempdir()) / "stacky-airtight-snapshot.json"

_CHUNK = 1 << 20


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            bloque = fh.read(_CHUNK)
            if not bloque:
                break
            h.update(bloque)
    return h.hexdigest()


def snapshot(root: Path) -> dict[str, tuple[int, str]]:
    """{ruta_relativa: (size_bytes, sha256)} de todo lo que matchea WATCHED_GLOBS.

    Archivo ausente = NO aparece en el dict (su aparicion TAMBIEN es un cambio).
    Un archivo ilegible se saltea: el guard nunca tumba la corrida que vigila.
    """
    root = Path(root)
    huellas: dict[str, tuple[int, str]] = {}
    for patron in WATCHED_GLOBS:
        for p in root.glob(patron):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if rel in huellas:
                continue
            try:
                huellas[rel] = (p.stat().st_size, _sha256(p))
            except OSError:
                continue
    return huellas


def diff_snapshots(before: dict, after: dict) -> list[str]:
    """Lista legible de artefactos creados / modificados / borrados.

    Vacia = la corrida fue estanca.
    """
    cambios: list[str] = []
    for rel in sorted(set(before) | set(after)):
        antes = before.get(rel)
        despues = after.get(rel)
        if antes == despues:
            continue
        if antes is None:
            cambios.append(f"CREADO      {rel} (+{despues[0]} bytes)")
        elif despues is None:
            cambios.append(f"BORRADO     {rel} (-{antes[0]} bytes)")
        else:
            delta = despues[0] - antes[0]
            signo = f"+{delta}" if delta >= 0 else str(delta)
            cambios.append(f"MODIFICADO  {rel} ({signo} bytes, {antes[0]} -> {despues[0]})")
    return cambios


def _log_del_dia() -> str:
    """El log del dia en curso: si el operador tiene el backend CORRIENDO
    mientras testea, el server lo escribe legitimamente y seria falso positivo.

    Los `.jsonl` NO se excluyen NUNCA: un ledger no debe crecer por una corrida
    de tests bajo ninguna circunstancia.
    """
    return f"data/logs/stacky-{date.today().isoformat()}.log"


def _coincide(rel: str, patrones: tuple[str, ...]) -> bool:
    from fnmatch import fnmatch
    return any(fnmatch(rel, pat) for pat in patrones)


def _filtrar(cambios: list[str], ignorados: tuple[str, ...]) -> list[str]:
    if not ignorados:
        return cambios
    quedan = []
    for linea in cambios:
        partes = linea.split()
        rel = partes[1] if len(partes) > 1 else ""
        if not _coincide(rel, ignorados):
            quedan.append(linea)
    return quedan


def _default_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _guard_habilitado() -> bool:
    """Perilla del operador (default ON). Es un verificador read-only, asi que
    no cae en ninguna de las 4 excepciones duras. Se lee por entorno porque el
    guard corre como script suelto, FUERA del proceso de Flask."""
    crudo = os.getenv("STACKY_HARNESS_AIRTIGHT_GUARD_ENABLED", "true").strip().lower()
    return crudo in ("1", "true", "yes")


def _guardar(root: Path, destino: Path) -> int:
    huellas = snapshot(root)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({
        "root": str(root),
        "files": {k: list(v) for k, v in huellas.items()},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[airtight] huella guardada: {len(huellas)} artefactos -> {destino}")
    return 0


def _verificar(root: Path, origen: Path, ignorados: tuple[str, ...]) -> int:
    if not origen.is_file():
        print(f"[airtight] NO hay huella previa en {origen}. Corre --save antes del arnes.",
              file=sys.stderr)
        return 2
    crudo = json.loads(origen.read_text(encoding="utf-8"))
    antes = {k: tuple(v) for k, v in (crudo.get("files") or {}).items()}
    despues = snapshot(root)

    cambios = _filtrar(diff_snapshots(antes, despues), ignorados)
    if not cambios:
        print(f"[airtight] OK: la corrida fue ESTANCA ({len(despues)} artefactos vigilados).")
        return 0

    print(f"[airtight] FALLA: la corrida modifico {len(cambios)} artefacto(s) del operador:",
          file=sys.stderr)
    for linea in cambios:
        print(f"  {linea}", file=sys.stderr)
    print("\n  Un test NO debe escribir en data/. Redirigi la ruta (services/ledger_writer.py:"
          "ledger_path aisla bajo el temporal del sistema en test-mode) o mockea el writer.",
          file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Guard de estanqueidad del arnes (plan 258 F7).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--save", action="store_true", help="huella ANTES de correr el arnes")
    g.add_argument("--verify", action="store_true", help="compara DESPUES; sale 1 si hubo cambios")
    ap.add_argument("--root", default=None, help="raiz a vigilar (default: backend/)")
    ap.add_argument("--snapshot-file", default=None, help=f"archivo de huella (default: {SNAPSHOT_FILE})")
    ap.add_argument("--ignore-globs", default="",
                    help="patrones a ignorar en --verify, separados por coma")
    args = ap.parse_args(argv)

    if not _guard_habilitado():
        print("[airtight] guard deshabilitado por configuracion; no se verifica nada.")
        return 0

    root = Path(args.root).resolve() if args.root else _default_root()
    destino = Path(args.snapshot_file) if args.snapshot_file else SNAPSHOT_FILE

    if args.save:
        return _guardar(root, destino)

    ignorados = tuple(p.strip() for p in args.ignore_globs.split(",") if p.strip())
    ignorados = ignorados + (_log_del_dia(),)
    return _verificar(root, destino, ignorados)


if __name__ == "__main__":
    raise SystemExit(main())
