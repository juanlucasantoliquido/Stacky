"""services/ledger_writer.py — Plan 258 F1/F2/F4. Portero de los ledgers JSONL.

Es una capa de VALIDACION + PROCEDENCIA + RUTA. **No es un mecanismo de
escritura nuevo**: el lock, la reescritura atomica (`tmp + replace`), la
retencion `MAX_ROWS` y la ALLOWLIST anti-secretos de cada `*_ledger.py` ya son
correctos y se preservan intactos (plan 258 C3/C10).

Que resuelve, medido:
  - `data/ci_runs.jsonl`     -> 8 de 8 lineas son fixture de test (`myproject`).
  - `data/env_applies.jsonl` -> 10 de 10 las escribio pytest (root bajo tmpdir).
  - `data/config_transfer_events.jsonl` -> LIMPIO. Hay un patron correcto en el
    repo; el problema no es el formato JSONL, es que un test pueda alcanzar el
    archivo del operador.

Tres invariantes que NO se negocian:
  1. En test-mode la ruta se aisla: un test jamas escribe en `backend/data/`.
  2. `infer_env_for_legacy_line` NUNCA devuelve 'prod'. Una linea historica sin
     marca es 'unknown'. Afirmar procedencia sin evidencia seria inventar el
     dato, que es exactamente el problema que este plan resuelve.
  3. El default de lectura es ('prod','unknown'), NO 'prod': filtrar a prod puro
     esconderia las 444 lineas reales de config_transfer_events (plan 258 C7).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import runtime_paths

logger = logging.getLogger("stacky.ledger_writer")

SCHEMA_VERSION = 1

ENV_PROD = "prod"
ENV_TEST = "test"
ENV_UNKNOWN = "unknown"
ENVS_VALIDOS = (ENV_PROD, ENV_TEST, ENV_UNKNOWN)

# Inventario REAL verificado (plan 258 E4). NO incluye publish_ledger (es
# DB-backed, no un JSONL) ni telemetry_harvest (su writer es del plan 255 y el
# archivo todavia no existe: entra al guard de F7 por glob, no a la migracion).
LEDGER_NAMES: tuple[str, ...] = (
    "ci_runs", "env_applies", "db_query_audit",
    "config_transfer_events", "build_runs",
)

# Validacion por (ledger, event_type). El default 'run' es el evento clasico.
# DESVIACION DOCUMENTADA respecto del texto del plan: para `build_runs` el plan
# proponia ("ts",) y ese campo NO EXISTE en el writer real
# (services/solution_builder.py:226 escribe build_id/mode/slugs/status/base_dir/
# zip_path/finished_at). Con ("ts",) el portero habria rechazado el 100% de los
# builds, en silencio. La clave load-bearing verificada es `build_id`.
REQUIRED_KEYS: dict[tuple[str, str], tuple[str, ...]] = {
    ("ci_runs", "run"):                ("project", "tracker_type", "pipeline_id", "triggered_at"),
    ("env_applies", "run"):            ("root", "fingerprint"),
    ("db_query_audit", "run"):         ("ts", "project", "result"),
    ("config_transfer_events", "run"): ("ts", "action", "project", "result"),
    ("build_runs", "run"):             ("build_id",),
}


# ---------------------------------------------------------------------------
# Configuracion y modo test
# ---------------------------------------------------------------------------

def _test_mode() -> bool:
    """Idioma de la casa, replicado por modulo (local_file_logging.py:61,
    error_fingerprints.py:59, lifecycle_log.py:46, output_watcher.py:986).
    NO existe `config.STACKY_TEST_MODE` — plan 258 C5."""
    return os.getenv("STACKY_TEST_MODE", "").lower() in {"1", "true", "yes"}


def _flag(key: str, default: bool = True) -> bool:
    """Lee la INSTANCIA `config.config`, nunca el modulo (que devolveria el
    default y mataria la rama OFF)."""
    try:
        import config as _config
        return bool(getattr(_config.config, key, default))
    except Exception:  # noqa: BLE001 — el portero jamas rompe por configuracion
        return default


def _cfg_str(key: str, default: str = "") -> str:
    try:
        import config as _config
        valor = getattr(_config.config, key, default)
        return "" if valor is None else str(valor)
    except Exception:  # noqa: BLE001
        return default


def test_ledgers_dir() -> Path:
    """Directorio aislado de ledgers bajo test. Calca la receta del plan 145
    para logs (`local_file_logging.py:64-65`)."""
    return Path(tempfile.gettempdir()) / "stacky-test-ledgers"


def _dirs_del_operador() -> tuple[Path, ...]:
    salida: list[Path] = []
    for fn in (runtime_paths.backend_root, runtime_paths.app_root):
        try:
            salida.append((Path(fn()) / "data").resolve())
        except Exception:  # noqa: BLE001
            continue
    return tuple(salida)


def ledger_path(name: str, *, base: Path | str | None = None) -> Path:
    """Ruta del ledger `name`.

    En test-mode devuelve una ruta AISLADA bajo `stacky-test-ledgers/`, NUNCA
    `backend/data/`.

    DESVIACION DOCUMENTADA (y deliberada) respecto del texto del plan: el
    aislamiento NO es incondicional. Si el llamador YA desvio su `data_dir()` a
    un tmp propio, ese desvio MANDA. Un aislamiento incondicional habria puesto
    en rojo a `tests/test_plan191_ci_ledger_hook.py` y
    `tests/test_plan198_env_ledger.py`, que hacen
    `monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)` y despues
    huellean el archivo DENTRO de `tmp_path`. El invariante que importa se
    conserva entero: **un test nunca escribe en el `data/` del operador**.

    `base` existe porque tres writers (`db_query.py`, `config_transfer.py`,
    `solution_builder.py`) hacen `from runtime_paths import data_dir`, y sus
    tests parchean ESE alias del modulo, no `runtime_paths.data_dir`. Ignorarlo
    habria roto `tests/test_db_query_audit.py`. El portero decide el
    AISLAMIENTO; cada writer conserva su propia resolucion de directorio.
    """
    base = Path(base) if base is not None else Path(runtime_paths.data_dir())
    if _test_mode():
        try:
            resuelto = base.resolve()
        except OSError:  # pragma: no cover
            resuelto = base
        if resuelto in _dirs_del_operador():
            base = test_ledgers_dir()
    return base / f"{name}.jsonl"


# ---------------------------------------------------------------------------
# F1 — sellado y validacion
# ---------------------------------------------------------------------------

def _falta(event: dict, clave: str) -> bool:
    """Ausente O vacio. `_clean_entry` proyecta TODAS las ENTRY_FIELDS con
    `.get()`, asi que una clave obligatoria puede existir valiendo None: mirar
    solo `in` daria un falso verde."""
    if clave not in event:
        return True
    valor = event[clave]
    if valor is None:
        return True
    return isinstance(valor, str) and not valor.strip()


def stamp_event(name: str, event: dict, *, event_type: str = "run",
                allow_incomplete: bool = False) -> dict | None:
    """Valida y sella UN evento. NO escribe: devuelve el dict a persistir.

    - Inyecta `env` = 'test' si `_test_mode()` else 'prod'.
    - Inyecta `schema_version` SOLO si falta. `config_transfer_events` ya usa
      esa clave para la version del perfil del cliente: el sello no la pisa.
    - Valida `REQUIRED_KEYS[(name, event_type)]`: si falta alguna, devuelve
      None y loguea a `error` (salvo `allow_incomplete=True`).

    Devuelve None si el evento NO debe escribirse.
    """
    if not isinstance(event, dict):
        logger.error("ledger %s: evento no es un dict (%s)", name, type(event).__name__)
        return None

    sellado = dict(event)
    if sellado.get("env") not in ENVS_VALIDOS:
        sellado["env"] = ENV_TEST if _test_mode() else ENV_PROD
    if sellado.get("schema_version") is None:
        sellado["schema_version"] = SCHEMA_VERSION

    if allow_incomplete or not _flag("STACKY_LEDGER_STRICT_SCHEMA_ENABLED", True):
        return sellado

    requeridas = REQUIRED_KEYS.get((name, event_type))
    if requeridas is None:
        return sellado

    faltantes = [k for k in requeridas if _falta(sellado, k)]
    if faltantes:
        logger.error(
            "ledger %s: evento RECHAZADO (event_type=%s), faltan claves obligatorias %s. "
            "No se escribio nada.", name, event_type, faltantes,
        )
        return None
    return sellado


# ---------------------------------------------------------------------------
# F2 — procedencia de lo historico, sin borrar nada
# ---------------------------------------------------------------------------

# Reglas NOMBRADAS: (ledger_o_None, campo, predicado, motivo).
# NO se hace substring sobre cualquier valor string del evento: 'pytest',
# 'test_reaper' o 'DB exploded' pueden aparecer en texto libre legitimo (una
# query auditada, una ruta de proyecto, un titulo de ticket) — plan 258 C9.
_TEST_RULES: tuple[tuple[str | None, str, str, str], ...] = (
    (None,      "root",    "startswith_tmpdir",           "root bajo el tmpdir de pytest"),
    (None,      "root",    "contains:pytest-of-",         "root con directorio de pytest"),
    ("ci_runs", "web_url", "startswith:http://gitlab/p/", "web_url de fixture"),
    ("ci_runs", "sha",     "equals:newsha",               "sha de fixture"),
    ("ci_runs", "project", "in:_FIXTURE_PROJECTS",        "project de fixture"),
)

_FIXTURE_PROJECTS_DEFAULT = ("myproject",)


def _fixture_projects() -> tuple[str, ...]:
    """Ampliable por el operador desde la UI (perilla CSV). Un proyecto real que
    se llame `myproject` se saca de la lista y deja de marcarse."""
    crudo = _cfg_str("STACKY_LEDGER_TEST_MARKERS", ",".join(_FIXTURE_PROJECTS_DEFAULT))
    return tuple(p.strip() for p in crudo.split(",") if p.strip())


def _matchea(predicado: str, valor: object) -> bool:
    if not isinstance(valor, str) or not valor:
        return False
    if predicado == "startswith_tmpdir":
        try:
            tmp = Path(tempfile.gettempdir()).resolve()
            return Path(valor).resolve().is_relative_to(tmp)
        except (OSError, ValueError):
            return False
    if predicado.startswith("startswith:"):
        return valor.startswith(predicado.split(":", 1)[1])
    if predicado.startswith("contains:"):
        return predicado.split(":", 1)[1] in valor
    if predicado.startswith("equals:"):
        return valor == predicado.split(":", 1)[1]
    if predicado == "in:_FIXTURE_PROJECTS":
        return valor in _fixture_projects()
    return False


def infer_env_for_legacy_line(name: str, event: dict) -> str:
    """Plan 258 F2 — procedencia de una linea SIN campo `env`.

    Devuelve 'test' solo si una regla de `_TEST_RULES` matchea en el CAMPO que
    la regla nombra; 'unknown' en caso contrario.

    NUNCA devuelve 'prod' por inferencia: una linea historica sin marca es
    'unknown', no 'prod'. Afirmar procedencia sin evidencia seria inventar
    datos, que es exactamente el problema que este plan resuelve.
    """
    if not isinstance(event, dict):
        return ENV_UNKNOWN
    if not _flag("STACKY_LEDGER_LEGACY_INFERENCE_ENABLED", True):
        return ENV_UNKNOWN
    for ledger, campo, predicado, _motivo in _TEST_RULES:
        if ledger is not None and ledger != name:
            continue
        if _matchea(predicado, event.get(campo)):
            return ENV_TEST
    return ENV_UNKNOWN


def event_env(name: str, event: dict) -> str:
    """Procedencia efectiva. El campo explicito SIEMPRE gana; solo si no esta
    (o no es valido) se cae en la inferencia."""
    if isinstance(event, dict):
        declarado = event.get("env")
        if declarado in ENVS_VALIDOS:
            return str(declarado)
    return infer_env_for_legacy_line(name, event if isinstance(event, dict) else {})


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

def _leer_crudo(path: Path) -> list[dict]:
    """Tolera (saltea) lineas corruptas e IGNORA claves desconocidas: un lector
    viejo frente a un campo nuevo sigue funcionando, y al reves tambien."""
    if not path.is_file():
        return []
    filas: list[dict] = []
    try:
        crudo = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for linea in crudo.splitlines():
        if not linea.strip():
            continue
        try:
            obj = json.loads(linea)
        except ValueError:
            continue
        if isinstance(obj, dict):
            filas.append(obj)
    return filas


def read_events(name: str, *, env: tuple[str, ...] | None = (ENV_PROD, ENV_UNKNOWN),
                path: Path | None = None) -> list[dict]:
    """Lee el ledger filtrando por procedencia.

    DEFAULT ('prod','unknown'): NO oculta datos reales del operador — las 444
    lineas de `config_transfer_events` y las 9 de `db_query_audit` son
    historicas sin marca y DEBEN seguir visibles (plan 258 C7). Filtrar a 'prod'
    puro es una decision EXPLICITA del llamador.

    `env=None` devuelve todo, incluido 'test'. Las lineas SIN campo `env` se
    clasifican con `infer_env_for_legacy_line` (F2). Ignora claves desconocidas.
    """
    filas = _leer_crudo(path if path is not None else ledger_path(name))
    salida: list[dict] = []
    for fila in filas:
        procedencia = event_env(name, fila)
        if env is not None and procedencia not in env:
            continue
        if fila.get("env") not in ENVS_VALIDOS:
            fila = {**fila, "env": procedencia}
        salida.append(fila)
    return salida


def env_breakdown(name: str, *, path: Path | None = None) -> dict[str, int]:
    """{'total': n, 'prod': n, 'test': n, 'unknown': n} de un ledger."""
    filas = _leer_crudo(path if path is not None else ledger_path(name))
    conteo = {"total": len(filas), ENV_PROD: 0, ENV_TEST: 0, ENV_UNKNOWN: 0}
    for fila in filas:
        conteo[event_env(name, fila)] += 1
    return conteo


# ---------------------------------------------------------------------------
# F4 — limpieza asistida (la UNICA pieza destructiva del plan)
# ---------------------------------------------------------------------------

PURGE_ACTION = "ledger_purge_test_lines"

# Solo los ledgers que tienen `_LOCK` + `_write_rows` propios. Los otros tres
# (`db_query.py`, `config_transfer.py`, `solution_builder.py`) escriben con un
# `open(..., "a")` sin lock: purgarlos seria inseguro, asi que se declara NO
# SOPORTADO en v1 en vez de hacerlo mal (plan 258, caso borde de F4).
_PURGEABLES: dict[str, str] = {
    "ci_runs": "services.ci_run_ledger",
    "env_applies": "services.env_apply_ledger",
}

_REINTENTOS_REPLACE = 5
_ESPERA_BASE_S = 0.12


def backups_dir() -> Path:
    return Path(runtime_paths.data_dir()) / "ledger_backups"


def purgeable(name: str) -> bool:
    return name in _PURGEABLES


def deletable_count(name: str) -> int:
    """Cuantas lineas se borrarian. Solo `test` probado: `unknown` NUNCA."""
    if not purgeable(name):
        return 0
    filas = _leer_crudo(ledger_path(name))
    return sum(1 for f in filas if event_env(name, f) == ENV_TEST)


def _hacer_backup(name: str, origen: Path) -> Path:
    """Copia previa OBLIGATORIA. Si falla, la purga se aborta."""
    destino_dir = backups_dir()
    destino_dir.mkdir(parents=True, exist_ok=True)
    marca = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    destino = destino_dir / f"{name}-{marca}.jsonl"
    destino.write_bytes(origen.read_bytes() if origen.is_file() else b"")
    return destino


def purge_test_lines(name: str, *, confirm_token: str, dry_run: bool = True) -> dict:
    """Plan 258 F4 — elimina las lineas con env='test' (o inferido 'test').

    `dry_run=True` (DEFAULT) solo cuenta y devuelve un preview: un llamador que
    olvide el argumento NO borra nada.

    Con `dry_run=False` exige `confirm_token` (`services/confirm_token.py`, del
    plan 253 — prohibido reimplementar otro) y hace backup previo a
    `data/ledger_backups/<name>-<ts>.jsonl`. Si el backup falla, se ABORTA.

    Reescribe usando el `_write_rows` del propio ledger (tmp + replace bajo su
    `_LOCK`), NUNCA un replace propio: ese camino ya esta resuelto y probado
    (plan 258 C3). En Windows `tmp.replace(path)` falla si otro handle tiene el
    archivo abierto: se reintenta con backoff y, si no se puede, se devuelve
    `ledger_locked` con el archivo INTACTO.

    NUNCA toca lineas 'prod' ni 'unknown'.
    """
    if not purgeable(name):
        return {"ok": False, "error": "ledger_no_soportado", "ledger": name,
                "deleted": 0, "dry_run": True,
                "detail": "este archivo se escribe sin lock propio; purgarlo seria inseguro"}

    import importlib

    modulo = importlib.import_module(_PURGEABLES[name])
    destino = ledger_path(name)

    with modulo._LOCK:  # noqa: SLF001 — el lock del ledger ES el contrato
        filas = _leer_crudo(destino)
        conservar = [f for f in filas if event_env(name, f) != ENV_TEST]
        borrables = len(filas) - len(conservar)

        preview = {
            "ok": True, "ledger": name, "total": len(filas),
            "deletable": borrables, "kept": len(conservar),
            "deleted": 0, "dry_run": True, "backup": None,
        }
        if dry_run:
            return preview
        if borrables == 0:
            return {**preview, "dry_run": False}

        from services.confirm_token import ConfirmTokenError, consume_token

        payload = consume_token(PURGE_ACTION, confirm_token)
        if str(payload.get("ledger") or "") != name:
            raise ConfirmTokenError("la confirmacion era para otro archivo de registro")
        if int(payload.get("deletable", -1)) != borrables:
            raise ConfirmTokenError(
                f"el conteo cambio desde que lo viste ({payload.get('deletable')} -> {borrables})")

        try:
            copia = _hacer_backup(name, destino)
        except OSError as exc:
            logger.error("ledger %s: backup FALLIDO, purga abortada: %s", name, exc)
            return {**preview, "ok": False, "dry_run": False, "error": "backup_fallido",
                    "detail": str(exc)}

        ultimo: Exception | None = None
        for intento in range(_REINTENTOS_REPLACE):
            try:
                modulo._write_rows(conservar)  # noqa: SLF001
                break
            except OSError as exc:            # Windows: archivo abierto por otro handle
                ultimo = exc
                time.sleep(_ESPERA_BASE_S * (2 ** intento))
        else:
            logger.error("ledger %s: no se pudo reescribir (%s). Archivo INTACTO.", name, ultimo)
            return {**preview, "ok": False, "dry_run": False, "error": "ledger_locked",
                    "detail": str(ultimo), "backup": str(copia)}

        logger.info("ledger %s: purgadas %d lineas de test (backup en %s)",
                    name, borrables, copia)
        return {"ok": True, "ledger": name, "total": len(filas),
                "deletable": borrables, "kept": len(conservar),
                "deleted": borrables, "dry_run": False, "backup": str(copia)}


__all__ = [
    "ENV_PROD", "ENV_TEST", "ENV_UNKNOWN", "ENVS_VALIDOS",
    "LEDGER_NAMES", "REQUIRED_KEYS", "SCHEMA_VERSION", "PURGE_ACTION",
    "backups_dir", "deletable_count", "env_breakdown", "event_env",
    "infer_env_for_legacy_line", "ledger_path", "purge_test_lines",
    "purgeable", "read_events", "stamp_event", "test_ledgers_dir",
]
