"""services/silence_audit.py — Plan 255 F3.

Censo determinista del SILENCIO del backend: `except` que no dejan rastro.
PURO: solo lee archivos, sin red, sin DB, sin importar el código auditado.
Espejo de `services/provider_coupling_audit.py` (mismo patrón: escáner de
producción + baseline JSON commiteado + meta-test que solo compara).

Detección por AST, NUNCA por regex
----------------------------------
Un regex sobre `except Exception` es destructivo y da falsos positivos (ya pasó
en este repo con un centinela textual de flags). Acá se camina el árbol
(`ast.ExceptHandler`) y el escape hatch se lee a nivel TOKEN
(`tokenize.COMMENT`), que también es análisis léxico y no textual: el módulo
`ast` descarta los comentarios, así que no hay forma de verlos con `ast` solo.

Los DOS buckets (anti-gaming)
-----------------------------
Si el ratchet contara solo `body == [Pass()]`, instrumentar un sitio con
`note_swallowed` lo sacaría de la cuenta **sin arreglar nada** — y el plan 255
F1 explícitamente no loguea. Por eso:

  * `mudos_totales`      — `Pass` **o** solo `note_swallowed(...)`. CONGELADO.
                           Instrumentar mueve un sitio de bucket, no lo saca.
  * `mudos_sin_contador` — solo `Pass`. Puede bajar libremente: bajarlo es
                           exactamente el progreso que F1 representa.
  * `silence_ok`         — excluidos por marca explícita `# silence-ok: <motivo>`.

Uso:
    python -m services.silence_audit                  # imprime el censo
    python -m services.silence_audit --write-baseline # regenera el baseline
"""
from __future__ import annotations

import ast
import io
import json
import sys
import tokenize
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]

_EXCLUDED_PARTS = ("tests", ".venv", "venv", "__pycache__", "node_modules")

# El escáner NUNCA se escanea a sí mismo: la prosa de un artefacto chocando con
# su propio gate es un gotcha recurrente de este repo.
_SELF = "services/silence_audit.py"

# Solo cuentan los handlers que atrapan CUALQUIER cosa. Un `except OSError: pass`
# es una decisión acotada; `except Exception: pass` es un agujero.
_CATCH_ALL = frozenset({"Exception", "BaseException"})

_MARCA = "# silence-ok:"

_BASELINE_PATH = _BACKEND / "tests" / "silence_ratchet_baseline.json"

# Paquetes de primer nivel usados por la regla de rename.
_RAIZ = "<raíz>"


# ── Núcleo: clasificación de UN archivo ───────────────────────────────────────


def _silence_ok_lines(src: str) -> set[int]:
    """Líneas con una marca `# silence-ok: <motivo>` NO vacía.

    A nivel token, no textual. Una marca sin motivo después de los dos puntos
    NO exime: el punto del mecanismo es obligar a escribir el porqué.
    """
    lineas: set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type != tokenize.COMMENT:
                continue
            texto = tok.string.strip()
            if not texto.startswith(_MARCA):
                continue
            motivo = texto[len(_MARCA):].strip()
            if motivo:
                lineas.add(tok.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return lineas
    return lineas


def _es_catch_all(handler: ast.ExceptHandler) -> bool:
    tipo = handler.type
    if tipo is None:
        return True  # `except:` desnudo atrapa todo
    nombres: list[str] = []
    if isinstance(tipo, ast.Name):
        nombres = [tipo.id]
    elif isinstance(tipo, ast.Tuple):
        nombres = [e.id for e in tipo.elts if isinstance(e, ast.Name)]
    return bool(set(nombres) & _CATCH_ALL)


def _solo_note_swallowed(handler: ast.ExceptHandler) -> bool:
    """El body es exactamente una llamada a `note_swallowed(...)`."""
    if len(handler.body) != 1:
        return False
    nodo = handler.body[0]
    if not isinstance(nodo, ast.Expr) or not isinstance(nodo.value, ast.Call):
        return False
    fn = nodo.value.func
    if isinstance(fn, ast.Name):
        return fn.id == "note_swallowed"
    if isinstance(fn, ast.Attribute):
        return fn.attr == "note_swallowed"
    return False


def _solo_pass(handler: ast.ExceptHandler) -> bool:
    return len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass)


def classify_source(src: str) -> dict:
    """Clasifica UN texto fuente. PURA — es la unidad testeable del escáner.

    {'mudos_totales': int, 'mudos_sin_contador': int, 'silence_ok': int}
    """
    vacio = {"mudos_totales": 0, "mudos_sin_contador": 0, "silence_ok": 0}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return dict(vacio)

    exentas = _silence_ok_lines(src)
    totales = sin_contador = exentos = 0

    for nodo in ast.walk(tree):
        if not isinstance(nodo, ast.ExceptHandler):
            continue
        if not _es_catch_all(nodo):
            continue
        es_pass = _solo_pass(nodo)
        es_contado = _solo_note_swallowed(nodo)
        if not (es_pass or es_contado):
            continue

        # Exento si hay una marca entre el `except` y su primera sentencia.
        primera = nodo.body[0].lineno
        if any(ln in exentas for ln in range(nodo.lineno, primera + 1)):
            exentos += 1
            continue

        totales += 1
        if es_pass:
            sin_contador += 1

    return {"mudos_totales": totales, "mudos_sin_contador": sin_contador,
            "silence_ok": exentos}


# ── Censo del árbol ───────────────────────────────────────────────────────────


def _python_files() -> list[Path]:
    return sorted(
        p for p in _BACKEND.rglob("*.py")
        if not any(part in _EXCLUDED_PARTS for part in p.relative_to(_BACKEND).parts)
        and p.relative_to(_BACKEND).as_posix() != _SELF
    )


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def scan_silent_handlers() -> dict:
    """Censo del silencio. Salida determinista, rutas posix relativas a backend/.

    {'mudos_totales': {archivo: int},      # Pass  O  solo note_swallowed  <- CONGELADO
     'mudos_sin_contador': {archivo: int}, # solo Pass                     <- puede bajar
     'silence_ok': {archivo: int}}         # excluidos por marca explícita
    """
    totales: dict[str, int] = {}
    sin_contador: dict[str, int] = {}
    exentos: dict[str, int] = {}

    for path in _python_files():
        rel = path.relative_to(_BACKEND).as_posix()
        texto = _read(path)
        if not texto:
            continue
        r = classify_source(texto)
        if r["mudos_totales"]:
            totales[rel] = r["mudos_totales"]
        if r["mudos_sin_contador"]:
            sin_contador[rel] = r["mudos_sin_contador"]
        if r["silence_ok"]:
            exentos[rel] = r["silence_ok"]

    return {
        "mudos_totales": dict(sorted(totales.items())),
        "mudos_sin_contador": dict(sorted(sin_contador.items())),
        "silence_ok": dict(sorted(exentos.items())),
        "mudos_totales_total": sum(totales.values()),
        "mudos_sin_contador_total": sum(sin_contador.values()),
        "silence_ok_total": sum(exentos.values()),
    }


# ── Comparación contra el baseline ────────────────────────────────────────────


def paquete_de(rel: str) -> str:
    """Paquete de primer nivel (`services`, `api`, `harness`, …) o la raíz."""
    partes = rel.split("/")
    return partes[0] if len(partes) > 1 else _RAIZ


def load_baseline(path: Path | None = None) -> dict:
    ruta = path or _BASELINE_PATH
    return json.loads(ruta.read_text(encoding="utf-8"))


def compare_to_baseline(scan: dict, baseline: dict) -> dict:
    """Compara `actual <= baseline` POR ARCHIVO. Nunca escribe nada.

    - Un archivo nuevo sin entrada tiene límite implícito **0**: no puede nacer
      con deuda muda.
    - Bajar NO exige regenerar: la comparación es `<=`, no `==`.
    - RENAME: si un archivo desapareció del árbol y el total del paquete de
      primer nivel no subió, no es deuda nueva — es el mismo `pass` con otro
      nombre de archivo. Convertir un rename inocente en deuda ajena es
      exactamente el gotcha que este plan evita.

    {'violations': [str], 'renames_posibles': [str]}
    """
    actual = scan["mudos_totales"]
    base = baseline["mudos_totales"]

    def _por_paquete(d: dict) -> dict:
        out: dict[str, int] = {}
        for rel, n in d.items():
            out[paquete_de(rel)] = out.get(paquete_de(rel), 0) + n
        return out

    pkg_actual = _por_paquete(actual)
    pkg_base = _por_paquete(base)
    desaparecidos = {rel for rel in base if rel not in actual}
    paquetes_con_bajas = {paquete_de(rel) for rel in desaparecidos}

    violations: list[str] = []
    renames: list[str] = []

    for rel in sorted(actual):
        n = actual[rel]
        limite = base.get(rel, 0)
        if n <= limite:
            continue
        pkg = paquete_de(rel)
        if pkg in paquetes_con_bajas and pkg_actual.get(pkg, 0) <= pkg_base.get(pkg, 0):
            renames.append(
                f"{rel}: {limite} -> {n}, pero el paquete '{pkg}' no creció y hay "
                f"archivos que desaparecieron: posible rename detectado; regenerá "
                f"el baseline con `python -m services.silence_audit --write-baseline`"
            )
            continue
        violations.append(
            f"{rel}: el silencio subió de {limite} a {n}. Un `except` nuevo que no "
            f"deja rastro necesita `note_swallowed(...)` o la marca "
            f"`# silence-ok: <motivo>`. Si el cambio es legítimo, regenerá el "
            f"baseline con `python -m services.silence_audit --write-baseline`."
        )

    return {"violations": violations, "renames_posibles": renames}


def write_baseline(path: Path | None = None) -> dict:
    """Genera y ESCRIBE el baseline. Solo se invoca a mano, nunca desde un test.

    Un baseline autogenerado por el test que valida contra el baseline pasa
    siempre por construcción — o sea, no valida nada.
    """
    ruta = path or _BASELINE_PATH
    scan = scan_silent_handlers()
    payload = {
        "_comando": "python -m services.silence_audit --write-baseline",
        "_regla": ("mudos_totales cuenta los handlers catch-all cuyo cuerpo es "
                   "solo `pass` O solo `note_swallowed(...)`. Instrumentar NO "
                   "baja este número (anti-gaming, plan 255 C2)."),
        "mudos_totales": scan["mudos_totales"],
        "mudos_totales_total": scan["mudos_totales_total"],
    }
    ruta.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return payload


def render_report_text(scan: dict) -> str:
    lineas = [
        "Censo de silencio del backend (Plan 255 F3)",
        "",
        f"mudos_totales      = {scan['mudos_totales_total']}  (CONGELADO por el ratchet)",
        f"mudos_sin_contador = {scan['mudos_sin_contador_total']}  (puede bajar)",
        f"silence_ok         = {scan['silence_ok_total']}  (marca explícita con motivo)",
        "",
        "Top por archivo:",
    ]
    top = sorted(scan["mudos_totales"].items(), key=lambda kv: (-kv[1], kv[0]))[:15]
    lineas.extend(f"  {n:4d}  {rel}" for rel, n in top)
    return "\n".join(lineas) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if "--write-baseline" in args:
        payload = write_baseline()
        print(f"baseline escrito: {_BASELINE_PATH}")
        print(f"mudos_totales_total = {payload['mudos_totales_total']}")
        return 0
    print(render_report_text(scan_silent_handlers()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
