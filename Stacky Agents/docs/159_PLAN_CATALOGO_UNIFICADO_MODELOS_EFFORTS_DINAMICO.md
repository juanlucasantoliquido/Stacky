# Plan 159 — Catálogo unificado de modelos/efforts (dinámico, sin redeploy)

**Estado: CRITICADO v2 — 2026-07-17 — veredicto del juez sobre v1: RECHAZADO
(C1 bloqueante: la ruta del catálogo no existe en el deploy congelado). Esta v2
aplica los fixes C1..C11 y queda lista para `implementar-plan-stacky`.**

## 0. Versionado y changelog v1 → v2

Crítica adversarial (`criticar-y-mejorar-plan`) sobre la v1 PROPUESTA. Hallazgos
aplicados en esta v2:

- **C1 (BLOQUEANTE, resuelto):** la v1 resolvía la ruta del JSON con
  `Path(__file__).parent.parent/config/` — en el deploy real (PyInstaller
  `--onedir`, `deployment/build_release.ps1:523-541`) eso apunta DENTRO del
  bundle `_internal/`, donde el JSON jamás se empaqueta (solo hay
  `--collect-data services`, no `config/`). Resultado v1: en producción SIEMPRE
  fallback de emergencia (1 modelo, 1 effort) y KPI-2 falso justo donde
  importa. v2: resolución vía `runtime_paths.backend_root()` (frozen = dir del
  exe, `runtime_paths.py:30-33`) + copia del JSON como archivo EXTERNO editable
  junto al exe en `build_release.ps1` (mismo patrón que `backend\.env`,
  líneas 574-591) + test dedicado (F0 caso 6).
- **C2 (IMPORTANTE, resuelto):** el snippet del endpoint v1 usaba `time.time()`
  pero `api/agents.py` NO importa `time` (verificado: 0 hits) → NameError 500
  si se copiaba literal. v2: el endpoint devuelve `loaded_at`/`TTL_SEC` que
  ahora expone el loader; no necesita `time`.
- **C3 (IMPORTANTE, resuelto):** la v1 llamaba `list_copilot_models()`
  (red viva, `timeout_sec=15`, `copilot_bridge.py:65`) en CADA GET → hasta 15s
  de bloqueo por apertura de modal con red caída. v2: `get_copilot_models_cached()`
  con caché propio TTL 300s y `timeout_sec=5`, más caché de promesa en el hook
  frontend.
- **C4 (IMPORTANTE, resuelto):** F4 v1 dejaba elegir entre `.skip` "o se acepta
  que falle parcialmente… si el runner de la fase lo permite" — ambigüedad que
  un modelo menor no puede resolver. v2: mandato único — el test se escribe
  completo en F4 y cada fase valida con filtro `-t`; prohibido `.skip`.
- **C5 (IMPORTANTE, resuelto):** la clave `emergency_fallback` dentro del JSON
  v1 era dato muerto (el loader nunca la leía) y constituía un TERCER fallback
  destinado a divergir — la clase exacta de bug que este plan mata. v2: se
  elimina del JSON; quedan exactamente 2 fallbacks embebidos, uno por lado de
  la red (backend `_EMERGENCY_FALLBACK`, frontend `EMERGENCY_MODEL_CATALOG`).
- **C6 (IMPORTANTE, resuelto — [ADICIÓN ARQUITECTO] guardia anti-drift):** nada
  impedía que el JSON y `config.py` volvieran a divergir (el renacer del bug
  original). v2: tests 7-8 de F0 comparan `default_model` del JSON contra el
  literal default de `CLAUDE_CODE_CLI_MODEL` en `config.py:235` (por regex
  sobre el texto, determinista, sin depender del env) y validan consistencia
  interna `effort_support` ⊆ `models`/`efforts`.
- **C7 (MENOR, resuelto):** `resolveModelCatalog` v1 descartaba los runtimes
  vivos (copilot) al caer a emergencia. v2: merge por runtime — solo
  `claude_code_cli` se reemplaza por el de emergencia.
- **C8 (MENOR, resuelto):** literal `300` duplicado (loader y endpoint) y
  `cached_at` inventado con `time.time()`. v2: `TTL_SEC` exportado del loader y
  `cached_at = catalog["loaded_at"]` real.
- **C9 (MENOR, resuelto):** los tests de flag OFF no precisaban el target del
  monkeypatch. v2: SIEMPRE sobre la INSTANCIA (`from config import config`,
  como hace `api/agents.py:9`) — nunca sobre el módulo (gotcha conocida
  config-módulo-vs-instancia).
- **C10 (MENOR, resuelto):** los greps del DoD llevaban rutas con espacios sin
  comillas (se parten en pathspecs). v2: rutas entre comillas.
- **C11 (MENOR, resuelto):** dos footguns documentados por escrito: (a) PROHIBIDO
  crear `backend/config/__init__.py` — un paquete regular `config/` shadowearía
  el módulo `config.py` y rompería todo el backend (sin `__init__.py`, el
  módulo gana al namespace package: sin riesgo); (b) los cachés módulo-level
  nuevos exigen fixture autouse de reset en cada archivo de test backend
  (test-order pollution conocida del repo).

Sin colisiones con los vecinos: el plan 157 (DB Compare config UX) y el 158
(telemetría de costos `claude_code_cli`) no tocan catálogo de modelos ni los 3
componentes frontend de este plan (verificado por grep en ambos docs: 0 hits).

## 1. Título, objetivo y KPI

**Objetivo:** eliminar las listas de modelos/efforts de Claude Code CLI
hardcodeadas y desincronizadas en el frontend, reemplazándolas por UN catálogo
backend único, versionado en disco y consultable por endpoint, editable **sin
rebuild ni redeploy del frontend y sin reiniciar el backend** (recarga sola por
TTL/mtime) — **tanto en desarrollo como en el deploy congelado (PyInstaller)**.

**KPI-1 (paridad):** los 3 componentes migrados (`IncidentResolverModal.tsx`,
`EpicFromBriefModal.tsx`, `ModelDecisionChip.tsx`) muestran EXACTAMENTE la misma
lista de modelos y efforts porque leen la misma fuente. Verificable con
`npx vitest run src/__tests__/modelSelectorsConsistency.test.ts` → exit 0.

**KPI-2 (vivo sin redeploy, dev Y frozen):** editar
`<backend_root>/config/model_catalog.json` en disco (en dev:
`backend/config/`; en el deploy: `backend/config/` junto al exe) y, sin
reiniciar el proceso backend, una nueva consulta al endpoint después de que
expire el TTL (300s) o cuyo `mtime` cambió refleja el contenido nuevo.
Verificable con `test_cache_invalidated_on_mtime_change` +
`test_path_resolves_via_runtime_paths_backend_root` en
`tests/test_plan159_model_catalog_loader.py`.

**KPI-3 (cero listas viejas):** 0 ocurrencias de `CLAUDE_MODELS`,
`CLAUDE_EFFORTS`, `ALT_MODELS` o el literal `"claude-opus-4-7"` en los 3
componentes migrados. Verificable con el mismo test de KPI-1.

**KPI-4 (anti-drift, nuevo en v2):** el `default_model` del JSON coincide con
el default literal de `CLAUDE_CODE_CLI_MODEL` en `config.py`, y todo modelo
referido por `effort_support` existe en `models`. Verificable con los casos 7-8
de `tests/test_plan159_model_catalog_loader.py`.

## 2. Por qué ahora — el gap que cierra

Investigación verificada en este repo (2026-07-17), archivo:línea:

- `Stacky Agents/frontend/src/components/IncidentResolverModal.tsx:26-33` —
  `CLAUDE_MODELS` = `["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5"]`
  (**sin `claude-sonnet-5`**, el modelo PRIMARIO real del CLI —
  `config.py:235` `CLAUDE_CODE_CLI_MODEL = os.getenv(..., "claude-sonnet-5")`).
  `CLAUDE_EFFORTS` (línea 33) es un array plano sin validar combinación
  modelo+effort. El `useState` inicial del modelo (línea 56) es
  `"claude-sonnet-4-6"` — tampoco coincide con el default real del backend.
  Los `.map()` están en las líneas 289 y 297.
- `Stacky Agents/frontend/src/components/EpicFromBriefModal.tsx:28-55` — otra
  lista distinta (`claude-sonnet-5` primero) + matriz por effort
  (`CLAUDE_EFFORTS`, líneas 39-49) + `isEffortValidForModel` (líneas 51-55)
  que ningún otro componente reutiliza. Los `.map()` están en 512 y 525.
- `Stacky Agents/frontend/src/components/ModelDecisionChip.tsx:15-24` —
  `ALT_MODELS = ["claude-opus-4-7", ...]` usa **`opus-4-7`**, versión que no
  coincide con NINGUNA de las otras dos listas (`opus-4-8`). Bug real de
  desincronización, no hipotético. `MODEL_LABEL` en 17-24; usos en 36-37.
- `Stacky Agents/backend/services/claude_code_cli_runner.py:2072-2116`
  (`_resolve_claude_code_cli_bin`) solo hace `shutil.which()`; la construcción
  del comando (~2058-2067) acepta cualquier string en `--model` y valida
  `--effort` contra la tupla fija `("low","medium","high","xhigh","max")`. No
  existe introspección real del CLI (ni `--help` parseado, ni subcomando
  `models`, ni manifest).
- Introspección dinámica que SÍ existe: `backend/copilot_bridge.py:65`
  `list_copilot_models(timeout_sec=15)` — `GET https://models.github.ai/catalog/models`
  con token `gh`. Se usa en `api/pm.py:661`, `api/pr_review.py:286`,
  `services/llm_router.py:78`, pero para el eje `config.LLM_BACKEND`, **no**
  para el `--model` del binario `claude` (ver §6). **Sin caché propia**: cada
  llamada es red viva (motivo del fix C3).
- **Evidencia del deploy congelado (nueva en v2, motivo de C1):**
  `deployment/build_release.ps1:523-541` congela el backend con PyInstaller
  `--onedir` y solo empaqueta datos de `services` (`--collect-data services`);
  las líneas 569-591 muestran el patrón de la casa para archivos EXTERNOS
  editables junto al exe (`backend\.env`, que `config.py` carga desde
  `backend_root()\.env`). `runtime_paths.py:26-33`: `backend_root()` = dir del
  exe en frozen, dir `backend/` en dev. Cualquier ruta basada en `__file__`
  dentro de `services/` muere en frozen.
- Bonus documentado (fuera de scope, §6): `backend/api/pm.py:650-656` tiene una
  CUARTA lista hardcodeada (`claude-opus-4-7`, eje LLM_BACKEND de PM). Mismo
  síntoma, otro eje.
- 3 runtimes confirmados en `frontend/src/types.ts:10`:
  `type AgentRuntime = "github_copilot" | "codex_cli" | "claude_code_cli"`.
  Codex: `config.py:205` `CODEX_CLI_MODEL` (default `""` = decide el CLI),
  `config.py:222` `CODEX_CLI_MODEL_DENYLIST`; `codex_cli_runner.py:576`
  confirma que **Codex no tiene flag `--effort`** (se traduce a presupuesto de
  turnos). `github_copilot` no tiene runner CLI propio; su único mecanismo real
  de modelos es `list_copilot_models()`.

**Conclusión de diseño:** no existe introspección real para Claude Code CLI ni
Codex CLI. La alternativa honesta es un **archivo de catálogo versionado en el
repo, leído en runtime por el backend** vía `runtime_paths.backend_root()`, con
caché de 300s invalidada por `mtime`, y copiado por `build_release.ps1` como
archivo externo editable junto al exe. Para `github_copilot` el catálogo delega
en `list_copilot_models()` con caché propio. Trade-off explícito: el archivo lo
mantiene el equipo de desarrollo/release — un solo archivo contra los 3-4
hardcodeos de hoy. El operador mono-usuario no toca nada.

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad de contrato:** el catálogo expone `claude_code_cli`,
  `codex_cli` y `github_copilot` con la misma forma de respuesta. Si un runtime
  no tiene selección de modelo hoy en la UI (codex, copilot), el catálogo igual
  reporta datos honestos con `note` explícita — no se inventa UI nueva (§6).
- **Válido en dev Y en el deploy congelado (v2):** toda ruta de disco pasa por
  `runtime_paths`; prohibido `Path(__file__)` para datos editables.
- **Cero trabajo extra para el operador:** flag `STACKY_MODEL_CATALOG_ENABLED`
  default **ON**. Mantener el JSON es tarea del equipo de desarrollo. Ninguna
  de las 4 excepciones duras aplica.
- **Human-in-the-loop:** el operador sigue eligiendo modelo/effort a mano; solo
  cambia DE DÓNDE vienen las opciones.
- **Mono-operador sin auth:** el endpoint nuevo no lleva control de acceso
  adicional (coherente con el resto de `/api/agents/*`).
- **Nunca selector vacío:** si el catálogo no está disponible (flag OFF,
  archivo roto, red caída para copilot), se degrada a fallback embebido único
  por lado (backend y frontend), jamás lista vacía ni 500.
- **Reusar patrones existentes:** shape de respuesta como `GET /api/agents/models`
  (`endpoints.ts:1082-1090`: `cached_at`, `ttl_sec`, `fallback_used`), mismo
  blueprint (`bp` de `api/agents.py`, registrado en `api/__init__.py:66`),
  categoría de flags `runtimes_cli` (`services/harness_flags.py:118`), patrón
  de test de flag de `tests/test_plan131_incident_flag.py`, y patrón "archivo
  externo junto al exe" de `build_release.ps1:569-591`.

## 4. Fases

> **Venv backend:** `Stacky Agents/backend/.venv/Scripts/python.exe`. Correr
> pytest SIEMPRE por archivo desde `Stacky Agents/backend`:
> `.venv\Scripts\python.exe -m pytest tests/<archivo> -q`.
> **Frontend:** `npx vitest run <archivo>` desde `Stacky Agents/frontend`
> (vitest ^4.1.9 en devDependencies; no hay script `test` — usar `npx`
> directo). Build: `npx tsc --noEmit` desde `Stacky Agents/frontend`.
> **Regla anti-pollution (C11b):** cada archivo de test backend nuevo lleva una
> fixture `autouse` que resetea los cachés módulo-level de
> `services/model_catalog.py` antes de cada caso:
> ```python
> import pytest
> from services import model_catalog
>
> @pytest.fixture(autouse=True)
> def _reset_catalog_caches():
>     model_catalog._cache.update(data=None, loaded_at=0.0, mtime=None)
>     model_catalog._copilot_cache.update(models=None, loaded_at=0.0, error=None)
>     yield
> ```

### F0 — Backend: catálogo versionado + loader frozen-aware + caché copilot + release

**Objetivo en 1 frase:** crear la única fuente de verdad en disco (válida en
dev y en el deploy congelado) y las funciones que la leen con caché
inteligente, sin tocar todavía ningún endpoint HTTP.

**Archivos:**
- NUEVO `Stacky Agents/backend/config/model_catalog.json`
- NUEVO `Stacky Agents/backend/services/model_catalog.py`
- NUEVO `Stacky Agents/backend/tests/test_plan159_model_catalog_loader.py`
- EDITAR `Stacky Agents/deployment/build_release.ps1` (fix C1, ver abajo)

> **PROHIBIDO (C11a):** crear `backend/config/__init__.py`. Un paquete regular
> `config/` shadowearía el módulo `backend/config.py` y rompería TODO el
> backend. Sin `__init__.py` no hay riesgo: el módulo `config.py` tiene
> precedencia sobre el namespace package.

**Contenido exacto de `model_catalog.json`** (valores migrados 1:1 desde los
componentes citados en §2; la matriz `effort_support` es la que ya existía en
`EpicFromBriefModal.tsx:44-48`; SIN clave `emergency_fallback` — fix C5):

```json
{
  "version": 1,
  "updated_at": "2026-07-17",
  "runtimes": {
    "claude_code_cli": {
      "source": "static_config_file",
      "default_model": "claude-sonnet-5",
      "default_effort": "medium",
      "models": [
        {"id": "claude-sonnet-5", "label": "Sonnet 5 (recomendado)", "recommended": true},
        {"id": "claude-opus-4-8", "label": "Opus 4.8 (mayor calidad, más lento, mayor costo)", "recommended": false},
        {"id": "claude-haiku-4-5", "label": "Haiku 4.5 (más rápido, menor costo)", "recommended": false},
        {"id": "claude-sonnet-4-6", "label": "Sonnet 4.6 (fallback del CLI)", "recommended": false}
      ],
      "efforts": [
        {"id": "low", "label": "low — mínimo (respuestas rápidas)"},
        {"id": "medium", "label": "medium — estándar"},
        {"id": "high", "label": "high — alto (recomendado para épicas)"},
        {"id": "xhigh", "label": "xhigh — muy alto"},
        {"id": "max", "label": "max — máximo"}
      ],
      "effort_support": {
        "claude-haiku-4-5": ["low", "medium", "high"],
        "claude-sonnet-5": ["low", "medium", "high", "max"],
        "claude-sonnet-4-6": ["low", "medium", "high", "max"],
        "claude-opus-4-8": ["low", "medium", "high", "xhigh", "max"]
      }
    },
    "codex_cli": {
      "source": "static_config_file",
      "default_model": "",
      "default_effort": null,
      "models": [
        {"id": "", "label": "Automático (decide Codex CLI)", "recommended": true}
      ],
      "efforts": [],
      "effort_support": {},
      "note": "Codex CLI no soporta --effort como flag; el nivel se traduce internamente a presupuesto de turnos (ver codex_cli_runner.py:576-591)."
    },
    "github_copilot": {
      "source": "live_introspection",
      "default_model": null,
      "default_effort": null,
      "models": [],
      "efforts": [],
      "effort_support": {},
      "note": "Poblado en runtime desde copilot_bridge.list_copilot_models() con caché TTL; ver campo 'error' de la respuesta del endpoint si la introspección falla."
    }
  }
}
```

**`services/model_catalog.py` — contrato exacto (v2):**

```python
"""Plan 159 v2 — catálogo único de modelos/efforts por runtime, leído de disco
con caché invalidada por mtime (sin restart, sin redeploy de frontend).
Resolución de ruta vía runtime_paths.backend_root(): válida en dev (backend/)
y en el deploy congelado PyInstaller (dir del exe). PROHIBIDO usar __file__
para esta ruta (C1)."""
from pathlib import Path
import json
import logging
import os
import time

import runtime_paths

logger = logging.getLogger(__name__)

TTL_SEC = 300  # único literal del TTL; el endpoint lo reexpone tal cual (C8)


def _catalog_path() -> Path:
    # C1: backend_root() = dir del exe en frozen / backend/ en dev.
    # Mismo patrón que config.py con backend_root()/.env
    # (build_release.ps1:574-591 copia el archivo junto al exe).
    return runtime_paths.backend_root() / "config" / "model_catalog.json"


_EMERGENCY_FALLBACK: dict = {
    "runtimes": {
        "claude_code_cli": {
            "source": "emergency_fallback", "default_model": "claude-sonnet-5",
            "default_effort": "medium",
            "models": [{"id": "claude-sonnet-5", "label": "Sonnet 5"}],
            "efforts": [{"id": "medium", "label": "medium"}],
            "effort_support": {},
        },
        "codex_cli": {"source": "emergency_fallback", "default_model": "", "default_effort": None,
                       "models": [{"id": "", "label": "Automático"}], "efforts": [], "effort_support": {}},
        "github_copilot": {"source": "emergency_fallback", "default_model": None, "default_effort": None,
                            "models": [], "efforts": [], "effort_support": {}},
    }
}

_cache: dict = {"data": None, "loaded_at": 0.0, "mtime": None}
_copilot_cache: dict = {"models": None, "loaded_at": 0.0, "error": None}


def load_model_catalog(force_refresh: bool = False) -> dict:
    """Devuelve {"fallback_used": bool, "error": str|None, "loaded_at": float,
    "runtimes": {...}}.

    Relee el archivo si: force_refresh=True, TTL expiró, o el mtime cambió
    desde la última lectura. Nunca lanza — cualquier fallo cae al fallback
    de emergencia embebido.
    """
    now = time.time()
    path = _catalog_path()
    try:
        current_mtime = os.path.getmtime(path)
    except OSError:
        current_mtime = None

    stale = (
        force_refresh
        or _cache["data"] is None
        or (now - _cache["loaded_at"]) > TTL_SEC
        or current_mtime != _cache["mtime"]
    )
    if not stale:
        return _cache["data"]

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if "runtimes" not in raw:
            raise ValueError("model_catalog.json sin clave 'runtimes'")
        result = {"fallback_used": False, "error": None, "loaded_at": now,
                  "runtimes": raw["runtimes"]}
    except Exception as e:  # noqa: BLE001
        logger.warning("model_catalog: fallback de emergencia (%s)", e)
        result = {"fallback_used": True, "error": str(e), "loaded_at": now,
                  "runtimes": _EMERGENCY_FALLBACK["runtimes"]}

    _cache.update(data=result, loaded_at=now, mtime=current_mtime)
    return result


def get_copilot_models_cached(force_refresh: bool = False) -> dict:
    """C3: introspección viva de github_copilot con caché propio (TTL_SEC) y
    timeout corto (5s, no los 15 default de copilot_bridge). Devuelve
    {"models": [...], "error": str|None}. Nunca lanza. Un fallo también se
    cachea TTL_SEC (no martillar una red caída); ?refresh=true lo fuerza."""
    now = time.time()
    if (not force_refresh and _copilot_cache["models"] is not None
            and (now - _copilot_cache["loaded_at"]) <= TTL_SEC):
        return {"models": _copilot_cache["models"], "error": _copilot_cache["error"]}
    try:
        import copilot_bridge
        raw = copilot_bridge.list_copilot_models(timeout_sec=5)
        models = [
            {"id": m.get("id"), "label": m.get("name") or m.get("id"), "recommended": False}
            for m in raw if m.get("id")
        ]
        _copilot_cache.update(models=models, loaded_at=now, error=None)
    except Exception as e:  # noqa: BLE001
        logger.warning("model_catalog: introspección copilot falló (%s)", e)
        _copilot_cache.update(models=[], loaded_at=now, error=str(e))
    return {"models": _copilot_cache["models"], "error": _copilot_cache["error"]}
```

**Edición de `deployment/build_release.ps1` (fix C1):** inmediatamente DESPUÉS
de la línea que copia `.env.example` (línea 572,
`Copy-Item -LiteralPath (Join-Path $backendDir ".env.example") ...`), insertar:

```powershell
# Plan 159: catalogo de modelos como archivo EXTERNO editable junto al exe
# (mismo patron que backend\.env). services/model_catalog.py lo resuelve via
# runtime_paths.backend_root()\config\model_catalog.json en dev y en frozen.
New-Item -ItemType Directory -Path (Join-Path $releaseBackendDir "config") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $backendDir "config\model_catalog.json") -Destination (Join-Path $releaseBackendDir "config\model_catalog.json") -Force
```

**Tests primero — `tests/test_plan159_model_catalog_loader.py`** (9 casos, con
la fixture autouse de reset del preámbulo de §4):
1. `test_loads_real_file_claude_code_cli_has_sonnet5` — carga el archivo real
   del repo, confirma `"claude-sonnet-5"` entre los `id` de
   `runtimes["claude_code_cli"]["models"]` (guarda de regresión del bug
   original).
2. `test_missing_file_falls_back_to_emergency` — `monkeypatch.setattr(model_catalog, "_catalog_path", lambda: tmp_path / "no_existe.json")`,
   confirma `fallback_used is True` y `models` no vacío.
3. `test_malformed_json_falls_back` — escribe JSON roto en `tmp_path`, apunta
   `_catalog_path` ahí, confirma `fallback_used is True` sin excepción.
4. `test_cache_reused_within_ttl` — `monkeypatch` sobre `time.time`, segunda
   llamada dentro del TTL NO relee disco (mock de `Path.read_text`,
   `call_count == 1`).
5. `test_cache_invalidated_on_mtime_change` — escribe archivo en `tmp_path`,
   carga, modifica contenido y `mtime` (`os.utime`), rellama
   `load_model_catalog()` y confirma el contenido nuevo SIN `force_refresh` ni
   restart (KPI-2).
6. `test_path_resolves_via_runtime_paths_backend_root` (C1) —
   `monkeypatch.setattr(runtime_paths, "backend_root", lambda: tmp_path)` tras
   crear `tmp_path/config/model_catalog.json` con un modelo marcador
   `"modelo-frozen-test"`; confirma que ese modelo aparece en el resultado
   (prueba el contrato frozen: en el deploy, backend_root = dir del exe).
7. **[ADICIÓN ARQUITECTO — guardia anti-drift]**
   `test_catalog_default_model_matches_config_literal` — lee el TEXTO de
   `backend/config.py` (`(Path(__file__).resolve().parent.parent / "config.py").read_text(encoding="utf-8")`),
   extrae con regex `os\.getenv\(\s*"CLAUDE_CODE_CLI_MODEL",\s*"([^"]+)"\)` el
   default literal, y asserta que es igual a
   `runtimes["claude_code_cli"]["default_model"]` del JSON real. Determinista
   (no depende del env del runner). Si Anthropic cambia el default en
   `config.py` y nadie actualiza el JSON (o viceversa), este test se pone rojo:
   el bug que motivó este plan no puede renacer en silencio.
8. **[ADICIÓN ARQUITECTO — guardia anti-drift]**
   `test_effort_support_consistent_with_models` — sobre el JSON real de
   `claude_code_cli`: cada clave de `effort_support` existe en
   `{m["id"] for m in models}` y cada effort listado en sus valores existe en
   `{e["id"] for e in efforts}`.
9. `test_copilot_models_cached_single_network_call` (C3) — `monkeypatch` de
   `copilot_bridge.list_copilot_models` con contador; dos llamadas seguidas a
   `get_copilot_models_cached()` → contador `== 1`; una tercera con
   `force_refresh=True` → contador `== 2`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan159_model_catalog_loader.py -q`
**Criterio de aceptación BINARIO:** exit 0, `9 passed`. Además:
`Select-String -Path "Stacky Agents\deployment\build_release.ps1" -Pattern "model_catalog.json"`
devuelve >= 1 línea (la copia al release existe).

**Flag:** ninguna todavía (se agrega en F2). **Trabajo del operador: ninguno.**

---

### F1 — Backend: endpoint `GET /api/agents/model-catalog`

**Objetivo en 1 frase:** exponer el catálogo de F0 por HTTP, con introspección
copilot CACHEADA (C3), sin romper nunca (siempre 200) y sin `import time` (C2:
`api/agents.py` no importa `time`; el snippet no lo necesita).

**Archivo a editar:** `Stacky Agents/backend/api/agents.py` — agregar, cerca de
la ruta existente `@bp.get("/models")` (línea 1120), una nueva ruta. `config`
en ese módulo ya es la INSTANCIA (`from config import config`, línea 9):

```python
@bp.get("/model-catalog")
def model_catalog_route():
    """Plan 159 v2 — catálogo unificado modelos/efforts por runtime CLI
    (claude_code_cli, codex_cli, github_copilot). Fuente:
    services/model_catalog.py (+ introspección cacheada de github_copilot).
    Siempre 200; nunca deja el selector del frontend vacío."""
    if not getattr(config, "STACKY_MODEL_CATALOG_ENABLED", True):
        return jsonify({"ok": False, "reason": "catalog_disabled", "runtimes": {}})

    from services.model_catalog import (
        TTL_SEC,
        get_copilot_models_cached,
        load_model_catalog,
    )

    refresh = request.args.get("refresh", "").lower() in {"1", "true", "yes"}
    catalog = load_model_catalog(force_refresh=refresh)
    copilot = get_copilot_models_cached(force_refresh=refresh)

    runtimes = {**catalog["runtimes"], "github_copilot": {
        **catalog["runtimes"].get("github_copilot", {}),
        "models": copilot["models"],
        "error": copilot["error"],
    }}

    return jsonify({
        "ok": True,
        "cached_at": catalog["loaded_at"],  # C2/C8: real, sin time.time()
        "ttl_sec": TTL_SEC,
        "fallback_used": catalog["fallback_used"],
        "runtimes": runtimes,
    })
```

**Archivo nuevo:** `Stacky Agents/backend/tests/test_plan159_model_catalog_endpoint.py`
(5 casos; fixture `client` con el mismo patrón de los tests existentes de
`api/agents.py`, p. ej. el de `tests/test_plan131_incident_flag.py`; MÁS la
fixture autouse de reset de cachés del preámbulo de §4 — sin ella, el caché
copilot contamina entre casos):
1. `test_endpoint_returns_200_and_claude_models` — GET, status 200,
   `"claude-sonnet-5"` en `runtimes.claude_code_cli.models[*].id`.
2. `test_endpoint_includes_codex_note` — `runtimes.codex_cli.efforts == []` y
   `"note"` presente y no vacía.
3. `test_endpoint_copilot_models_from_live_introspection` — `monkeypatch` de
   `copilot_bridge.list_copilot_models` devolviendo 2 modelos fake; ambos
   aparecen en `runtimes.github_copilot.models`.
4. `test_endpoint_copilot_failure_degrades_not_500` — `monkeypatch` de
   `list_copilot_models` lanzando `RuntimeError`; status 200 (no 500),
   `runtimes.github_copilot.error` no None, `models == []`.
5. `test_endpoint_disabled_flag_returns_ok_false` — C9: monkeypatch SOBRE LA
   INSTANCIA, nunca el módulo:
   ```python
   from config import config as config_instance
   monkeypatch.setattr(config_instance, "STACKY_MODEL_CATALOG_ENABLED", False, raising=False)
   ```
   Confirma `ok is False`, `reason == "catalog_disabled"`, status 200.

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan159_model_catalog_endpoint.py -q`
**Criterio de aceptación BINARIO:** exit 0, `5 passed`.

**Flag:** consumida vía `getattr(config, ..., True)` (robusto si F1 corre antes
de F2). **Trabajo del operador: ninguno.**

---

### F2 — Backend: flag `STACKY_MODEL_CATALOG_ENABLED` (default ON, categorizada)

**Objetivo en 1 frase:** dar de alta la flag que protege el endpoint, siguiendo
el patrón exacto de `STACKY_ADAPTIVE_EFFORT_ENABLED` (`config.py:794`) y el
test de `test_plan131_incident_flag.py`.

**Archivos:**
- EDITAR `Stacky Agents/backend/config.py` — agregar, junto a las demás flags
  bool de runtimes CLI (mismo patrón que las líneas 794-795 y 950-951):
  ```python
  # Plan 159 — kill-switch del catálogo unificado de modelos/efforts. OFF:
  # el endpoint devuelve {"ok": False, "reason": "catalog_disabled"} y el
  # frontend cae a su fallback embebido único (nunca selector vacío).
  STACKY_MODEL_CATALOG_ENABLED: bool = os.getenv(
      "STACKY_MODEL_CATALOG_ENABLED", "true"
  ).lower() in ("1", "true", "yes")
  ```
- EDITAR `Stacky Agents/backend/services/harness_flags.py`:
  - Agregar `FlagSpec` en `FLAG_REGISTRY` (cerca de
    `STACKY_ADAPTIVE_EFFORT_ENABLED`):
    ```python
    FlagSpec(
        key="STACKY_MODEL_CATALOG_ENABLED",
        type="bool",
        label="Catálogo unificado de modelos/efforts",
        description=(
            "Plan 159 — fuente única backend de modelos/efforts disponibles por "
            "runtime (Claude Code CLI, Codex CLI, GitHub Copilot), consumida por "
            "los 3 selectores del frontend. OFF = cada selector usa su fallback "
            "estático embebido (comportamiento pre-159)."
        ),
        group="global",
        default=True,  # Grupo B — sin costo de tokens, solo UI; promovida ON de alta.
    ),
    ```
  - Agregar `"STACKY_MODEL_CATALOG_ENABLED"` a la tupla
    `_CATEGORY_KEYS["runtimes_cli"]` (línea 118, junto a las flags
    `CLAUDE_CODE_CLI_*`/`CODEX_CLI_*`).
- EDITAR `Stacky Agents/backend/services/harness_flags_help.py` — entrada en
  `PLAIN_HELP`:
  ```python
  "STACKY_MODEL_CATALOG_ENABLED": PlainHelp(
      what="Controla si el selector de modelo/effort del Resolutor de Incidencias y "
           "de la Épica desde Brief usa la lista actualizada del servidor o una lista fija.",
      on_effect="Si la activás: los selectores siempre muestran los modelos/efforts vigentes, sin necesitar una actualización de la app.",
      off_effect="Si la apagás: los selectores muestran una lista mínima fija embebida, que puede quedar desactualizada.",
      example="Como una carta de restaurante que se actualiza sola en vez de tener que reimprimirla cada vez que cambia un plato.",
  ),
  ```
- NUEVO `Stacky Agents/backend/tests/test_plan159_model_catalog_flag.py`
  (patrón de `tests/test_plan131_incident_flag.py`, 4 casos; incluir también la
  fixture autouse de reset de cachés):
  1. `test_flag_default_on` — sin env var seteada,
     `config.config.STACKY_MODEL_CATALOG_ENABLED is True` (acá `config` es el
     MÓDULO importado con `import config`, y `config.config` la instancia —
     gotcha conocida).
  2. `test_flagspec_registered` — `spec.type == "bool"`, `spec.env_only is False`,
     `spec.default is True`, y
     `"STACKY_MODEL_CATALOG_ENABLED" in _CATEGORY_KEYS["runtimes_cli"]`.
  3. `test_plain_help_entry` — existe en `PLAIN_HELP`, los 4 campos no vacíos.
  4. `test_endpoint_returns_ok_false_when_flag_off` — repite el caso 5 de F1
     desde este archivo (C9: monkeypatch sobre la INSTANCIA `config.config`,
     `raising=False`), para que quede agrupado con el resto de tests de la
     flag. Redundante a propósito: cada archivo se corre aislado.

**Comandos:**
- `.venv\Scripts\python.exe -m pytest tests/test_plan159_model_catalog_flag.py -q` → exit 0, `4 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q` → exit 0
  (`test_every_registry_flag_is_categorized` verde con la flag nueva).

**Registro en el arnés (ratchet, obligatorio):**
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` — agregar al
  arreglo `HARNESS_TEST_FILES` (sección nueva "— Plan 159 —"):
  ```
  tests/test_plan159_model_catalog_loader.py
  tests/test_plan159_model_catalog_endpoint.py
  tests/test_plan159_model_catalog_flag.py
  ```
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.ps1` — misma alta,
  mismo orden.

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q`
**Criterio de aceptación BINARIO:** exit 0.

**Flag:** `STACKY_MODEL_CATALOG_ENABLED`, default **ON**, visible/toggleable en
el panel de flags de la UI (categoría "Runtimes CLI") sin acción del operador.
**Trabajo del operador: ninguno.**

---

### F3 — Frontend: cliente API + fallback de emergencia único + hook con caché

**Objetivo en 1 frase:** dar al frontend UNA función para pedir el catálogo,
UNA constante de emergencia (reemplaza las 3 dispersas) y un hook con caché de
promesa module-level (no repetir el fetch en cada montaje de modal), con la
lógica de resolución testeable sin DOM (gap conocido: no hay
`@testing-library/react` ni `jsdom` en `package.json` — no se puede usar
`renderHook`).

**Archivos:**
- EDITAR `Stacky Agents/frontend/src/api/endpoints.ts` — agregar, cerca de
  `Agents.models` (línea ~1082):
  ```typescript
  export interface ModelCatalogEntry { id: string; label: string; recommended?: boolean }
  export interface RuntimeModelCatalog {
    source: string;
    default_model: string | null;
    default_effort: string | null;
    models: ModelCatalogEntry[];
    efforts: { id: string; label: string }[];
    effort_support: Record<string, string[]>;
    note?: string;
    error?: string | null;
  }
  export interface ModelCatalogResponse {
    ok: boolean;
    reason?: string;
    cached_at?: number;
    ttl_sec?: number;
    fallback_used?: boolean;
    runtimes: Partial<Record<"claude_code_cli" | "codex_cli" | "github_copilot", RuntimeModelCatalog>>;
  }
  export const ModelCatalogApi = {
    get: (refresh = false) =>
      api.get<ModelCatalogResponse>(`/api/agents/model-catalog${refresh ? "?refresh=true" : ""}`),
  };
  ```
- NUEVO `Stacky Agents/frontend/src/services/modelCatalogFallback.ts`:
  ```typescript
  import type { ModelCatalogResponse, RuntimeModelCatalog } from "../api/endpoints";

  /** Plan 159 — ÚNICO fallback embebido del lado frontend. Reemplaza las 3
   * listas locales de IncidentResolverModal / EpicFromBriefModal /
   * ModelDecisionChip. Su gemelo backend es _EMERGENCY_FALLBACK en
   * services/model_catalog.py (uno por lado de la red, C5). */
  export const EMERGENCY_MODEL_CATALOG: Record<string, RuntimeModelCatalog> = {
    claude_code_cli: {
      source: "emergency_fallback",
      default_model: "claude-sonnet-5",
      default_effort: "medium",
      models: [
        { id: "claude-sonnet-5", label: "Sonnet 5 (recomendado)", recommended: true },
        { id: "claude-opus-4-8", label: "Opus 4.8", recommended: false },
        { id: "claude-haiku-4-5", label: "Haiku 4.5", recommended: false },
      ],
      efforts: [{ id: "medium", label: "medium" }],
      effort_support: {},
    },
  };

  /** Función pura, testeable sin DOM: decide qué catálogo mostrar.
   * C7: merge POR RUNTIME — si claude viene vacío se reemplaza SOLO
   * claude_code_cli por el de emergencia, preservando datos vivos de los
   * demás runtimes (p. ej. introspección copilot). */
  export function resolveModelCatalog(
    apiResult: ModelCatalogResponse | null | undefined
  ): Record<string, RuntimeModelCatalog> {
    if (!apiResult || !apiResult.ok) return EMERGENCY_MODEL_CATALOG;
    const rt = (apiResult.runtimes || {}) as Record<string, RuntimeModelCatalog>;
    const hasClaudeModels = (rt.claude_code_cli?.models?.length ?? 0) > 0;
    if (!hasClaudeModels) {
      return { ...rt, claude_code_cli: EMERGENCY_MODEL_CATALOG.claude_code_cli };
    }
    return rt;
  }
  ```
- NUEVO `Stacky Agents/frontend/src/hooks/useModelCatalog.ts` — hook delgado
  (`useState` + `useEffect`), mismo estilo manual que
  `src/hooks/useReviewInboxCount.ts`, sin librería nueva. Con caché de promesa
  module-level (C3/C11 frontend): una variable de módulo
  `let catalogPromise: Promise<ModelCatalogResponse> | null = null;` — el
  primer montaje hace `catalogPromise = ModelCatalogApi.get()`, los siguientes
  reusan la misma promesa (un solo fetch por sesión de página; el TTL vivo lo
  maneja el backend). Expone
  `{ catalog: Record<string, RuntimeModelCatalog>, loading: boolean }`,
  aplicando `resolveModelCatalog` al resultado (y también en el `catch`:
  `resolveModelCatalog(null)`).

**Tests primero (función pura, sin DOM):**
NUEVO `Stacky Agents/frontend/src/services/__tests__/modelCatalogFallback.test.ts`
(5 casos):
1. `EMERGENCY_MODEL_CATALOG.claude_code_cli.models` contiene un `id === "claude-sonnet-5"`.
2. `resolveModelCatalog({ok:false, runtimes:{}})` devuelve `EMERGENCY_MODEL_CATALOG`.
3. `resolveModelCatalog(null)` y `resolveModelCatalog(undefined)` devuelven
   `EMERGENCY_MODEL_CATALOG`.
4. C7: con `{ok:true, runtimes:{claude_code_cli:{...models:[]}, github_copilot:{...models:[{id:"gpt-x",label:"X"}]}}}`
   → `claude_code_cli` es el de emergencia PERO `github_copilot.models`
   preserva `"gpt-x"`.
5. Con `{ok:true, runtimes:{claude_code_cli:{...models:[{id:"x",label:"X"}]}}}`
   → devuelve los datos reales, NO el fallback.

**Comando:** `npx vitest run src/services/__tests__/modelCatalogFallback.test.ts`
(desde `Stacky Agents/frontend`)
**Criterio de aceptación BINARIO:** exit 0, `5 passed`.

**Flag:** ninguna nueva en frontend (consume la de F2 vía el `ok` de la
respuesta). **Trabajo del operador: ninguno.**

---

### F4 — Frontend: migrar `IncidentResolverModal.tsx`

**Objetivo en 1 frase:** que el selector de modelo/effort del Resolutor de
Incidencias lea del catálogo único, incluyendo `claude-sonnet-5`, y corrija su
default inconsistente.

**Archivo a editar:** `Stacky Agents/frontend/src/components/IncidentResolverModal.tsx`
- Eliminar `const CLAUDE_MODELS` (líneas 26-31) y `const CLAUDE_EFFORTS`
  (línea 33).
- Importar `useModelCatalog` de `../hooks/useModelCatalog` y
  `EMERGENCY_MODEL_CATALOG` de `../services/modelCatalogFallback`.
- Reemplazar el `.map()` sobre `CLAUDE_MODELS` (línea 289) por `.map()` sobre
  `catalog.claude_code_cli?.models ?? []`.
- Reemplazar el `.map()` sobre `CLAUDE_EFFORTS` (línea 297) por `.map()` sobre
  `catalog.claude_code_cli?.efforts ?? []`.
- Cambiar el `useState` inicial de `selectedModel` (línea 56, hoy
  `useState("claude-sonnet-4-6")`) para que arranque desde
  `EMERGENCY_MODEL_CATALOG.claude_code_cli.default_model` (import directo,
  síncrono) y se sincronice con `catalog.claude_code_cli?.default_model` vía
  `useEffect` cuando el fetch resuelve (primer render nunca sin valor).

**Test de consistencia (cubre F4, F5 y F6 — grep-gate sin DOM). Mandato único
(C4): el archivo se escribe COMPLETO en esta fase, SIN `.skip`, y cada fase se
valida con el filtro `-t` de vitest (F4 y F5 filtran su componente; F6 corre
sin filtro y exige 6/6). PROHIBIDO usar `.skip` o "aceptar fallos parciales".**
NUEVO `Stacky Agents/frontend/src/__tests__/modelSelectorsConsistency.test.ts`:
```typescript
import { readFileSync } from "fs";
import { join } from "path";
import { describe, it, expect } from "vitest";

const FILES = [
  "src/components/IncidentResolverModal.tsx",
  "src/components/EpicFromBriefModal.tsx",
  "src/components/ModelDecisionChip.tsx",
];

describe("Plan 159 — sin listas de modelos hardcodeadas fuera del catálogo", () => {
  for (const rel of FILES) {
    const src = readFileSync(join(process.cwd(), rel), "utf-8");
    it(`${rel} no declara CLAUDE_MODELS/CLAUDE_EFFORTS/ALT_MODELS local`, () => {
      expect(src).not.toMatch(/const\s+CLAUDE_MODELS\s*[:=]/);
      expect(src).not.toMatch(/const\s+CLAUDE_EFFORTS\s*[:=]/);
      expect(src).not.toMatch(/const\s+ALT_MODELS\s*[:=]/);
    });
    it(`${rel} no contiene el literal stale claude-opus-4-7`, () => {
      expect(src).not.toContain("claude-opus-4-7");
    });
  }
});
```

**Comando F4:** `npx vitest run src/__tests__/modelSelectorsConsistency.test.ts -t IncidentResolverModal`
más `npx tsc --noEmit` (0 errores).
**Criterio de aceptación BINARIO F4:** los 2 casos filtrados de
`IncidentResolverModal.tsx` pasan; `tsc --noEmit` exit 0.

**Flag:** ninguna nueva. **Trabajo del operador: ninguno.**

---

### F5 — Frontend: migrar `EpicFromBriefModal.tsx`

**Objetivo en 1 frase:** eliminar la segunda lista divergente y su validador
local, usando `effort_support` del catálogo para la misma validación.

**Archivo a editar:** `Stacky Agents/frontend/src/components/EpicFromBriefModal.tsx`
- Eliminar `const CLAUDE_MODELS` (líneas 28-37), `const CLAUDE_EFFORTS`
  (líneas 39-49) y `function isEffortValidForModel` (líneas 51-55).
- Importar `useModelCatalog`.
- Reemplazar cada llamada `isEffortValidForModel(effort, modelId)` por una
  función local equivalente que consulte
  `catalog.claude_code_cli?.effort_support?.[modelId]?.includes(effort) ?? true`
  (el `?? true` evita bloquear la selección cuando el catálogo degradó a
  emergencia, cuya matriz está vacía).
- Los `<select>` que iteraban `CLAUDE_MODELS`/`CLAUDE_EFFORTS` (líneas 512 y
  525) pasan a iterar `catalog.claude_code_cli?.models ?? []` /
  `catalog.claude_code_cli?.efforts ?? []`.

**Comando:** `npx vitest run src/__tests__/modelSelectorsConsistency.test.ts -t EpicFromBriefModal`
más `npx tsc --noEmit`.
**Criterio de aceptación BINARIO:** los 2 casos filtrados de
`EpicFromBriefModal.tsx` pasan; `tsc --noEmit` exit 0.

**Flag:** ninguna nueva. **Trabajo del operador: ninguno.**

---

### F6 — Frontend: migrar `ModelDecisionChip.tsx`

**Objetivo en 1 frase:** cerrar la serie corrigiendo el bug concreto
`claude-opus-4-7` → catálogo real (`claude-opus-4-8`), y resolver labels desde
la misma fuente.

**Archivo a editar:** `Stacky Agents/frontend/src/components/ModelDecisionChip.tsx`
- Eliminar `const ALT_MODELS` (línea 15) y `const MODEL_LABEL` (líneas 17-24).
- Importar `useModelCatalog`.
- `modelLabel` (línea 36) pasa a buscar en
  `catalog.claude_code_cli?.models.find(m => m.id === decision.model)?.label ?? decision.model`.
- `alternatives` (línea 37) pasa a
  `(catalog.claude_code_cli?.models ?? []).map(m => m.id).filter(id => id !== decision.model)`.

**Comando:** `npx vitest run src/__tests__/modelSelectorsConsistency.test.ts`
(sin filtro — los 3 archivos deben pasar los 2 casos cada uno, 6/6)
más `npx tsc --noEmit`.
**Criterio de aceptación BINARIO:** `6 passed`, `tsc --noEmit` exit 0.

**Flag:** ninguna nueva. **Trabajo del operador: ninguno.**

---

### F7 — Cierre: verificación consolidada

**Objetivo en 1 frase:** correr TODOS los comandos de aceptación de F0-F6 en
una pasada y confirmar que nada quedó en rojo antes de dar el plan por
completo.

**Sin archivos nuevos.** Comandos en orden (backend: desde
`Stacky Agents/backend`; frontend: desde `Stacky Agents/frontend`):

```
.venv\Scripts\python.exe -m pytest tests/test_plan159_model_catalog_loader.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan159_model_catalog_endpoint.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan159_model_catalog_flag.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
npx vitest run src/services/__tests__/modelCatalogFallback.test.ts
npx vitest run src/__tests__/modelSelectorsConsistency.test.ts
npx tsc --noEmit
```

**Criterio de aceptación BINARIO global:** los 8 comandos exit 0.

**Smoke manual (documentar como pendiente, no bloqueante):** abrir el Resolutor
de Incidencias, confirmar que el selector de modelo muestra
"Sonnet 5 (recomendado)" como primera opción; editar
`backend/config/model_catalog.json` agregando un modelo de prueba, esperar 5
minutos (TTL) o pasar `?refresh=true`, confirmar que aparece sin reiniciar
backend ni frontend. En el próximo deploy real: verificar que
`release/backend/config/model_catalog.json` existe junto al exe y que editarlo
también se refleja (prueba definitiva de C1).

**Trabajo del operador: ninguno** para que el plan funcione; el smoke manual es
verificación opcional de quien despliega.

## 5. Riesgos y mitigaciones

- **El JSON queda desactualizado si nadie lo edita** — igual que las listas de
  hoy, pero ahora es 1 archivo en vez de 3-4, Y (v2) la guardia anti-drift de
  F0 casos 7-8 pone tests en rojo si el JSON diverge de `config.py` o de sí
  mismo. Carga del equipo de desarrollo/release, no del operador.
- **Deploy congelado (C1)** — mitigado por diseño en v2: ruta vía
  `runtime_paths.backend_root()` + copia explícita en `build_release.ps1` como
  archivo externo (patrón `backend\.env` ya existente). Si aun así el archivo
  faltara en un release, el fallback de emergencia mantiene el selector
  funcional (degradado y visible vía `fallback_used: true`).
- **Caché de 300s retrasa la propagación de una edición** — trade-off
  explícito: nunca requiere restart ni redeploy, a lo sumo 5 minutos de
  latencia (o `?refresh=true`).
- **`list_copilot_models()` puede fallar o colgar** — v2: caché TTL propio +
  `timeout_sec=5` + try/except; degrada a `models: []` + `error` visible sin
  afectar `claude_code_cli`/`codex_cli`. Un fallo también se cachea TTL_SEC
  (no martillar red caída); `?refresh=true` fuerza reintento.
- **Flag OFF podría dejar selectores vacíos** — mitigado:
  `EMERGENCY_MODEL_CATALOG` (F3) está compilada en el bundle, no depende de
  red.
- **La matriz `effort_support` heredada de `EpicFromBriefModal.tsx:44-48`
  nunca fue verificada contra el CLI real** — se migra tal cual, sin inventar
  datos; el caso 8 de F0 al menos garantiza su consistencia interna. Verificar
  contra matriz oficial de Anthropic queda para un plan futuro.
- **Test-order pollution por cachés módulo-level** — mitigada por la fixture
  autouse de reset (§4, C11b) en los 3 archivos de test backend.
- **Colisión de numeración con sesiones paralelas** — releer `ls docs/` en
  frío antes de escribir y antes de commitear (práctica vigente).

## 6. Fuera de scope

- `GET /api/ai/models` (`api/pm.py:616`) y `GET /api/agents/models`
  (`api/agents.py:1120`) — eje `config.LLM_BACKEND` (chat interno de PM /
  revisor de PRs / routing), **no** el eje `--model`/`--effort` del Claude Code
  CLI spawneado. No se tocan; `pm.py:650-656` comparte el síntoma
  (`claude-opus-4-7` stale) y queda documentado para un plan de seguimiento.
- Selector de modelo/effort en la UI para `codex_cli` o `github_copilot` donde
  hoy NO existe (`IncidentResolverModal.tsx` solo muestra el selector cuando
  `agentRuntime === "claude_code_cli"`, línea 284). El catálogo backend expone
  los 3 runtimes por paridad de contrato; este plan migra únicamente los 3
  componentes que hoy controlan `claude_code_cli`.
- Cambiar la lógica de decisión automática de modelo/effort
  (`STACKY_ADAPTIVE_EFFORT_ENABLED`, `services/adaptive_selector.py`) — no se
  toca el routing, solo el catálogo de OPCIONES para elegir a mano.
- Introspección real del binario `claude` (no existe hoy). Si Anthropic la
  publica, un plan futuro reemplaza `source: "static_config_file"` por
  `"live_introspection"` sin cambiar el contrato del endpoint.
- Editor visual del JSON en el panel de flags — el archivo se edita directo en
  repo/deploy; ya es editable sin redeploy, que es el requisito real.
- Validación dura de `--model` contra el catálogo en
  `claude_code_cli_runner.py` — rechazar un modelo desconocido podría romper
  runs válidos con modelos recién publicados; a lo sumo un warning en un plan
  futuro.

## 7. Glosario, orden de implementación y Definición de Hecho

**Glosario:**
- **AgentRuntime:** motor que ejecuta un agente Stacky: `"github_copilot"`,
  `"codex_cli"` o `"claude_code_cli"` (`frontend/src/types.ts:10`).
- **Catálogo unificado:** el objeto `{"runtimes": {...}}` servido por
  `GET /api/agents/model-catalog`, única fuente de modelos/efforts para los 3
  componentes frontend.
- **Fallback de emergencia:** exactamente DOS embebidos, uno por lado de la
  red — backend `_EMERGENCY_FALLBACK` (`services/model_catalog.py`) y frontend
  `EMERGENCY_MODEL_CATALOG` (`modelCatalogFallback.ts`). El JSON NO lleva
  fallback propio (C5).
- **`effort_support`:** mapa `{modelo: [efforts válidos]}` que reemplaza
  `isEffortValidForModel` de `EpicFromBriefModal.tsx`.
- **TTL de caché:** `TTL_SEC = 300` (único literal, en
  `services/model_catalog.py`); tiempo máximo para que una edición del JSON se
  refleje sin reiniciar el backend.
- **`backend_root()`:** `runtime_paths.py:30-33` — dir de `backend/` en dev,
  dir del exe en el deploy congelado. Única vía válida para resolver la ruta
  del catálogo (C1).
- **`STACKY_MODEL_CATALOG_ENABLED`:** flag kill-switch del endpoint, default
  ON, categoría `runtimes_cli`, visible en el panel de flags.

**Orden de implementación:** estrictamente secuencial F0 → F1 → F2 → F3 → F4 →
F5 → F6 → F7. Cada fase depende de la anterior (F1 necesita el loader de F0;
F3 el endpoint de F1/F2; F4-F6 el hook de F3; F7 es verificación consolidada).

**Definición de Hecho (DoD) global:**
1. Los 8 comandos de F7 exit 0.
2. `grep -rn "CLAUDE_MODELS\|CLAUDE_EFFORTS\|ALT_MODELS" "Stacky Agents/frontend/src/components/IncidentResolverModal.tsx" "Stacky Agents/frontend/src/components/EpicFromBriefModal.tsx" "Stacky Agents/frontend/src/components/ModelDecisionChip.tsx"` → 0 resultados (rutas SIEMPRE entre comillas, C10).
3. `grep -rn "claude-opus-4-7" "Stacky Agents/frontend/src"` → 0 resultados.
4. Los 3 archivos de test backend nuevos están en `HARNESS_TEST_FILES` de
   `run_harness_tests.sh` Y `run_harness_tests.ps1`.
5. La flag `STACKY_MODEL_CATALOG_ENABLED` aparece en el panel de flags de la
   UI (categoría "Runtimes CLI") sin acción del operador.
6. `Select-String -Path "Stacky Agents\deployment\build_release.ps1" -Pattern "model_catalog.json"` → >= 1 línea (C1: el release copia el JSON junto al exe).
7. NO existe `Stacky Agents/backend/config/__init__.py` (C11a).
8. Commit del doc con mensaje `docs(plan-159): <slug>` y, en la implementación,
   un commit separado por fase con TDD real corrido con el venv del repo (no
   falsos verdes).
