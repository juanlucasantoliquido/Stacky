# Plan 159 — Catálogo unificado de modelos/efforts (dinámico, sin redeploy)

**Estado: PROPUESTO v1 — 2026-07-17**

## 1. Título, objetivo y KPI

**Objetivo:** eliminar las listas de modelos/efforts de Claude Code CLI hardcodeadas y
desincronizadas en el frontend, reemplazándolas por UN catálogo backend único,
versionado en disco y consultable por endpoint, editable **sin rebuild ni redeploy
del frontend** (a lo sumo un archivo de config que se recarga solo, sin ni siquiera
reiniciar el backend dentro del TTL de caché).

**KPI-1 (paridad):** los 3 componentes migrados (`IncidentResolverModal.tsx`,
`EpicFromBriefModal.tsx`, `ModelDecisionChip.tsx`) muestran EXACTAMENTE la misma
lista de modelos y efforts porque leen la misma fuente. Verificable con
`npx vitest run src/__tests__/modelSelectorsConsistency.test.ts` → exit 0.

**KPI-2 (vivo sin redeploy):** editar `backend/config/model_catalog.json` en disco
y, sin reiniciar el proceso backend, una nueva consulta al endpoint después de que
expire el TTL de caché (300s) o cuyo `mtime` cambió, refleja el contenido nuevo.
Verificable con `test_cache_invalidated_on_mtime_change` en
`tests/test_plan159_model_catalog_loader.py`.

**KPI-3 (cero listas viejas):** 0 ocurrencias de `CLAUDE_MODELS`, `CLAUDE_EFFORTS`,
`ALT_MODELS` o el literal `"claude-opus-4-7"` fuera del archivo de fallback de
emergencia único. Verificable con el mismo test de KPI-1.

## 2. Por qué ahora — el gap que cierra

Investigación verificada en este repo, hoy (2026-07-17), archivo:línea:

- `Stacky Agents/frontend/src/components/IncidentResolverModal.tsx:26-33` — const
  `CLAUDE_MODELS` = `["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5"]`
  (**sin `claude-sonnet-5`**, que es el modelo PRIMARIO real del CLI —
  `config.py:235` `CLAUDE_CODE_CLI_MODEL = os.getenv(..., "claude-sonnet-5")`).
  `const CLAUDE_EFFORTS` (línea 33) es un array plano `["low","medium","high","xhigh","max"]`
  sin validar combinación modelo+effort. El `useState` inicial del modelo
  (línea 56) es `"claude-sonnet-4-6"` — tampoco coincide con el default real del
  backend (`claude-sonnet-5`).
- `Stacky Agents/frontend/src/components/EpicFromBriefModal.tsx:28-49` — otra
  lista distinta: `claude-sonnet-5` primero, `claude-opus-4-8`, `claude-haiku-4-5`,
  `claude-sonnet-4-6` como fallback; además una matriz `supportedModels` por
  effort (líneas 39-49) y una función `isEffortValidForModel` (líneas 51-55) que
  NINGÚN otro componente reutiliza.
- `Stacky Agents/frontend/src/components/ModelDecisionChip.tsx:15-24` — const
  `ALT_MODELS = ["claude-opus-4-7", "claude-sonnet-5", "claude-haiku-4-5"]` usa
  **`opus-4-7`**, una versión que no coincide con NINGUNA de las otras dos listas
  (que usan `opus-4-8`). Es un bug real y concreto de desincronización, no
  hipotético.
- `Stacky Agents/backend/services/claude_code_cli_runner.py:2072-2116`
  (`_resolve_claude_code_cli_bin`) solo hace `shutil.which()` del binario. La
  construcción del comando (`~2058-2067`) acepta cualquier string en `--model` y
  valida `--effort` contra una tupla fija `("low","medium","high","xhigh","max")`
  literal en Python — no existe introspección real del CLI (no hay parseo de
  `--help`, ni subcomando `models`, ni manifest). Confirmado: no existe tal
  mecanismo hoy.
- Precedente real de introspección dinámica que SÍ existe:
  `Stacky Agents/backend/copilot_bridge.py:65` `list_copilot_models()` — hace
  `GET https://models.github.ai/catalog/models` con el token OAuth de `gh` y
  devuelve el catálogo real de GitHub Copilot. Se usa hoy en
  `api/pm.py:661`, `api/pr_review.py:286` y `services/llm_router.py:78`, pero
  para el eje `config.LLM_BACKEND` (chat interno de PM / revisor de PRs / routing),
  **no** para el modelo que se pasa como `--model` al binario `claude` spawneado
  por `claude_code_cli_runner.py`. Son dos conceptos distintos en este repo y hay
  que no confundirlos (ver §6 Fuera de scope).
- Bonus hallado durante la verificación (no pedido explícitamente, se deja
  documentado): `Stacky Agents/backend/api/pm.py:650-656` tiene una CUARTA lista
  hardcodeada (`claude-opus-4-7` también, para el backend `anthropic` de
  `services/pm/pm_llm_client.py`) — mismo síntoma, otro eje (LLM_BACKEND de PM,
  no Claude Code CLI). Queda fuera de este plan (§6) pero es evidencia adicional
  de que el patrón "cada componente hardcodea su propia lista" es sistémico.
- 3 runtimes confirmados en `frontend/src/types.ts:10`:
  `type AgentRuntime = "github_copilot" | "codex_cli" | "claude_code_cli"`.
  Codex: `config.py:205` `CODEX_CLI_MODEL` (env-only, default `""` = decide el
  CLI) y `config.py:222` `CODEX_CLI_MODEL_DENYLIST`; `codex_cli_runner.py:576`
  confirma **Codex no tiene flag `--effort`** — el nivel se traduce internamente
  a presupuesto de turnos. github_copilot no tiene runner CLI propio
  (`services/` solo tiene `codex_cli_runner.py` y `claude_code_cli_runner.py`);
  su único mecanismo de modelos reales es `list_copilot_models()`.

**Conclusión de diseño:** no existe introspección real para Claude Code CLI ni
para Codex CLI hoy. La alternativa más honesta es un **archivo de catálogo
versionado en el repo pero leído en runtime por el backend**, con caché de 300s
invalidada por `mtime` — así una edición del archivo se refleja sin reiniciar el
backend y SIN NUNCA requerir rebuild/redeploy del frontend. Para
`github_copilot` el catálogo delega en la introspección real ya existente
(`list_copilot_models()`). Trade-off explícito: el archivo lo mantiene al día el
**equipo de desarrollo/release** cuando Anthropic/OpenAI publican un modelo
nuevo — pero es **un solo archivo**, contra los 3-4 lugares hardcodeados de hoy;
menos carga que el estado actual, no más. El operador mono-usuario no toca nada.

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad de contrato:** el catálogo expone `claude_code_cli`,
  `codex_cli` y `github_copilot` con la misma forma de respuesta. Si un runtime
  no tiene selección de modelo hoy en la UI (codex, copilot), el catálogo igual
  reporta datos honestos (o una nota explícita de por qué no aplica) — no se
  inventa una UI nueva para ellos en este plan (ver §6).
- **Cero trabajo extra para el operador:** flag `STACKY_MODEL_CATALOG_ENABLED`
  default **ON**. Mantener el JSON al día es tarea del equipo de desarrollo, no
  del operador mono-usuario. Ninguna excepción de las 4 duras aplica aquí.
- **Human-in-the-loop:** el operador sigue eligiendo modelo/effort a mano en los
  3 componentes; el plan solo cambia DE DÓNDE vienen las opciones, no automatiza
  la elección.
- **Mono-operador sin auth:** el endpoint nuevo no necesita ni lleva control de
  acceso adicional (coherente con el resto de `/api/agents/*`).
- **Nunca selector vacío:** si el catálogo no está disponible (flag OFF, archivo
  roto, red caída para copilot), se degrada a un fallback embebido único y
  visible, jamás una lista vacía o un 500.
- **Reusar patrones existentes:** mismo shape de respuesta que
  `GET /api/agents/models` (`endpoints.ts:1082-1090`: `cached_at`, `ttl_sec`,
  `fallback_used`), mismo blueprint (`bp` de `api/agents.py`, ya registrado en
  `api/__init__.py:66`), misma categoría de flags `runtimes_cli`
  (`services/harness_flags.py:118-128`), mismo patrón de test de flag que
  `tests/test_plan131_incident_flag.py`.

## 4. Fases

> **Venv backend:** `Stacky Agents/backend/.venv/Scripts/python.exe`. Correr
> pytest SIEMPRE por archivo desde `Stacky Agents/backend`:
> `.venv\Scripts\python.exe -m pytest tests/<archivo> -q`
> (POSIX: `.venv/Scripts/python.exe -m pytest tests/<archivo> -q`).
> **Frontend:** `npx vitest run <archivo>` desde `Stacky Agents/frontend`
> (vitest ^4.1.9 está en `devDependencies`, no hay script `test` en
> `package.json` — es esperado, correr con `npx` directo). Build:
> `npx tsc --noEmit` desde `Stacky Agents/frontend`.

### F0 — Backend: catálogo versionado + loader con caché/mtime + fallback de emergencia

**Objetivo en 1 frase:** crear la única fuente de verdad en disco y la función
que la lee con caché inteligente, sin tocar todavía ningún endpoint HTTP.

**Archivos:**
- NUEVO `Stacky Agents/backend/config/model_catalog.json`
- NUEVO `Stacky Agents/backend/services/model_catalog.py`
- NUEVO `Stacky Agents/backend/tests/test_plan159_model_catalog_loader.py`

**Contenido exacto de `model_catalog.json`** (valores migrados 1:1 desde los
componentes actuales citados en §2, sin inventar datos nuevos; la matriz
`effort_support` es la que ya existía en `EpicFromBriefModal.tsx:44-48`):

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
      "note": "Poblado en runtime desde copilot_bridge.list_copilot_models(); ver campo 'error' de la respuesta del endpoint si la introspección falla."
    }
  },
  "emergency_fallback": {
    "claude_code_cli": {
      "models": [{"id": "claude-sonnet-5", "label": "Sonnet 5"}],
      "efforts": [{"id": "medium", "label": "medium"}]
    }
  }
}
```

**`services/model_catalog.py` — contrato exacto:**

```python
"""Plan 159 — catálogo único de modelos/efforts por runtime, leído de disco
con caché invalidada por mtime (sin restart, sin redeploy de frontend)."""
from pathlib import Path
import json, os, time, logging

logger = logging.getLogger(__name__)

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "config" / "model_catalog.json"
_TTL_SEC = 300

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


def load_model_catalog(force_refresh: bool = False) -> dict:
    """Devuelve {"fallback_used": bool, "error": str|None, "runtimes": {...}}.

    Relee el archivo si: force_refresh=True, TTL expiró, o el mtime cambió
    desde la última lectura. Nunca lanza — cualquier fallo cae al fallback
    de emergencia embebido.
    """
    now = time.time()
    try:
        current_mtime = os.path.getmtime(_CATALOG_PATH)
    except OSError:
        current_mtime = None

    stale = (
        force_refresh
        or _cache["data"] is None
        or (now - _cache["loaded_at"]) > _TTL_SEC
        or current_mtime != _cache["mtime"]
    )
    if not stale:
        return _cache["data"]

    try:
        raw = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        if "runtimes" not in raw:
            raise ValueError("model_catalog.json sin clave 'runtimes'")
        result = {"fallback_used": False, "error": None, "runtimes": raw["runtimes"]}
    except Exception as e:  # noqa: BLE001
        logger.warning("model_catalog: fallback de emergencia (%s)", e)
        result = {"fallback_used": True, "error": str(e), "runtimes": _EMERGENCY_FALLBACK["runtimes"]}

    _cache.update(data=result, loaded_at=now, mtime=current_mtime)
    return result
```

**Tests primero — `tests/test_plan159_model_catalog_loader.py`** (5 casos):
1. `test_loads_real_file_claude_code_cli_has_sonnet5` — carga el archivo real
   del repo, confirma `"claude-sonnet-5"` en los `id` de
   `runtimes["claude_code_cli"]["models"]` (guarda de regresión del bug
   original: sonnet-5 faltante).
2. `test_missing_file_falls_back_to_emergency` — con `monkeypatch` apunta
   `model_catalog._CATALOG_PATH` a un `Path` inexistente, confirma
   `fallback_used is True` y `models` no vacío.
3. `test_malformed_json_falls_back` — escribe JSON roto en un `tmp_path`,
   apunta `_CATALOG_PATH` ahí, confirma `fallback_used is True` sin excepción
   propagada.
4. `test_cache_reused_within_ttl` — con `monkeypatch` sobre `time.time`,
   confirma que una segunda llamada dentro del TTL NO vuelve a leer el disco
   (mock de `Path.read_text` con `call_count == 1`).
5. `test_cache_invalidated_on_mtime_change` — escribe un archivo en
   `tmp_path`, carga, modifica el archivo y su `mtime` (`os.utime`), vuelve a
   llamar `load_model_catalog()` y confirma que el contenido nuevo aparece SIN
   pasar `force_refresh=True` ni reiniciar nada (prueba central de "sin
   redeploy/sin restart", KPI-2).

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan159_model_catalog_loader.py -q`
**Criterio de aceptación BINARIO:** exit 0, `5 passed`.

**Flag:** ninguna todavía (se agrega en F2). **Trabajo del operador: ninguno.**

---

### F1 — Backend: endpoint `GET /api/agents/model-catalog`

**Objetivo en 1 frase:** exponer el catálogo de F0 por HTTP, incorporando
introspección real de `github_copilot` vía `copilot_bridge.list_copilot_models()`,
sin romper nunca (siempre 200).

**Archivo a editar:** `Stacky Agents/backend/api/agents.py` — agregar, cerca de
la ruta existente `@bp.get("/models")` (línea ~1120), una nueva ruta:

```python
@bp.get("/model-catalog")
def model_catalog_route():
    """Plan 159 — catálogo unificado modelos/efforts por runtime CLI
    (claude_code_cli, codex_cli, github_copilot). Fuente: services/model_catalog.py
    + introspección viva de github_copilot. Siempre 200; nunca deja el
    selector del frontend vacío."""
    if not getattr(config, "STACKY_MODEL_CATALOG_ENABLED", True):
        return jsonify({"ok": False, "reason": "catalog_disabled", "runtimes": {}})

    from services.model_catalog import load_model_catalog
    refresh = request.args.get("refresh", "").lower() in {"1", "true", "yes"}
    catalog = load_model_catalog(force_refresh=refresh)
    runtimes = catalog["runtimes"]

    copilot_error = None
    try:
        import copilot_bridge
        raw = copilot_bridge.list_copilot_models()
        runtimes = {**runtimes, "github_copilot": {
            **runtimes.get("github_copilot", {}),
            "models": [
                {"id": m.get("id"), "label": m.get("name") or m.get("id"), "recommended": False}
                for m in raw if m.get("id")
            ],
        }}
    except Exception as e:  # noqa: BLE001
        copilot_error = str(e)
        runtimes = {**runtimes, "github_copilot": {
            **runtimes.get("github_copilot", {}), "models": [], "error": copilot_error,
        }}

    return jsonify({
        "ok": True,
        "cached_at": time.time(),
        "ttl_sec": 300,
        "fallback_used": catalog["fallback_used"],
        "runtimes": runtimes,
    })
```

**Archivo nuevo:** `Stacky Agents/backend/tests/test_plan159_model_catalog_endpoint.py`
(5 casos, patrón de fixture `client` igual al resto de `api/agents.py`):
1. `test_endpoint_returns_200_and_claude_models` — GET, status 200,
   `"claude-sonnet-5"` presente en `runtimes.claude_code_cli.models[*].id`.
2. `test_endpoint_includes_codex_note` — `runtimes.codex_cli.efforts == []` y
   `"note"` presente y no vacío.
3. `test_endpoint_copilot_models_from_live_introspection` — `monkeypatch` de
   `copilot_bridge.list_copilot_models` devolviendo una lista fake de 2
   modelos; confirma que ambos aparecen en `runtimes.github_copilot.models`.
4. `test_endpoint_copilot_failure_degrades_not_500` — `monkeypatch` de
   `list_copilot_models` para que lance `RuntimeError`; confirma status 200
   (no 500), `runtimes.github_copilot.error` no None, `models == []`.
5. `test_endpoint_disabled_flag_returns_ok_false` — con
   `config.STACKY_MODEL_CATALOG_ENABLED = False` (monkeypatch de atributo),
   confirma `ok is False`, `reason == "catalog_disabled"`, status 200.

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan159_model_catalog_endpoint.py -q`
**Criterio de aceptación BINARIO:** exit 0, `5 passed`.

**Flag:** consumida (`STACKY_MODEL_CATALOG_ENABLED`), se declara en F2. Si F1
corre antes de F2, usar `getattr(config, "STACKY_MODEL_CATALOG_ENABLED", True)`
como en el snippet (ya así de robusto). **Trabajo del operador: ninguno.**

---

### F2 — Backend: flag `STACKY_MODEL_CATALOG_ENABLED` (default ON, categorizada)

**Objetivo en 1 frase:** dar de alta la flag que protege el endpoint, siguiendo
el patrón exacto de `STACKY_ADAPTIVE_EFFORT_ENABLED` y el test de
`test_plan131_incident_flag.py`.

**Archivos:**
- EDITAR `Stacky Agents/backend/config.py` — agregar, junto a las demás flags
  bool de runtimes CLI:
  ```python
  # Plan 159 — kill-switch del catálogo unificado de modelos/efforts. OFF:
  # el endpoint devuelve {"ok": False, "reason": "catalog_disabled"} y el
  # frontend cae a su fallback embebido único (nunca selector vacío).
  STACKY_MODEL_CATALOG_ENABLED: bool = os.getenv(
      "STACKY_MODEL_CATALOG_ENABLED", "true"
  ).lower() in ("1", "true", "yes")
  ```
- EDITAR `Stacky Agents/backend/services/harness_flags.py`:
  - Agregar `FlagSpec` en `FLAG_REGISTRY` (cerca de `STACKY_ADAPTIVE_EFFORT_ENABLED`,
    ~línea 1075):
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
    `_CATEGORY_KEYS["runtimes_cli"]` (línea ~118-128, junto a las demás flags
    de `CLAUDE_CODE_CLI_*`/`CODEX_CLI_*`).
- EDITAR `Stacky Agents/backend/services/harness_flags_help.py` — agregar
  entrada en `PLAIN_HELP`:
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
  (mismo patrón que `tests/test_plan131_incident_flag.py`, 4 casos):
  1. `test_flag_default_on` — sin env var seteada, `config.config.STACKY_MODEL_CATALOG_ENABLED is True`.
  2. `test_flagspec_registered` — `spec.type == "bool"`, `spec.env_only is False`,
     `spec.default is True`, y `"STACKY_MODEL_CATALOG_ENABLED" in _CATEGORY_KEYS["runtimes_cli"]`.
  3. `test_plain_help_entry` — existe en `PLAIN_HELP`, los 4 campos no vacíos.
  4. `test_endpoint_returns_ok_false_when_flag_off` — repite el caso 5 de F1
     desde este archivo, para que quede agrupado con el resto de tests de la
     flag (redundante a propósito, cada archivo se corre aislado).

**Comandos:**
- `.venv\Scripts\python.exe -m pytest tests/test_plan159_model_catalog_flag.py -q` → exit 0, `4 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q` → exit 0
  (`test_every_registry_flag_is_categorized` sigue verde con la flag nueva).

**Registro en el arnés (ratchet, obligatorio):**
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` — agregar al
  arreglo `HARNESS_TEST_FILES` (sección nueva "— Plan 159 —"):
  ```
  tests/test_plan159_model_catalog_loader.py
  tests/test_plan159_model_catalog_endpoint.py
  tests/test_plan159_model_catalog_flag.py
  ```
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.ps1` — mismo alta,
  mismo orden.

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q`
**Criterio de aceptación BINARIO:** exit 0 (el meta-test exige que todo archivo
`test_*.py` nuevo esté registrado; si no lo está, falla listando el faltante).

**Flag:** `STACKY_MODEL_CATALOG_ENABLED`, default **ON**. **Trabajo del
operador: ninguno** (kill-switch interno, no requiere acción — sigue siendo
configurable desde el panel de flags existente si algún desarrollador
necesitara apagarlo).

---

### F3 — Frontend: cliente API + fallback de emergencia único + hook

**Objetivo en 1 frase:** dar al frontend UNA función para pedir el catálogo y
UNA constante de emergencia (reemplaza las 3 dispersas), con lógica de
resolución testeable sin DOM (gap conocido: no hay `@testing-library/react` ni
`jsdom` en `package.json` — no se puede usar `renderHook`).

**Archivos:**
- EDITAR `Stacky Agents/frontend/src/api/endpoints.ts` — agregar, cerca de
  `Agents.models` (línea ~1082), un nuevo export:
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

  /** Plan 159 — ÚNICO fallback embebido. Reemplaza las 3 listas locales de
   * IncidentResolverModal / EpicFromBriefModal / ModelDecisionChip. */
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

  /** Función pura, testeable sin DOM: decide qué catálogo mostrar. */
  export function resolveModelCatalog(
    apiResult: ModelCatalogResponse | null | undefined
  ): Record<string, RuntimeModelCatalog> {
    if (!apiResult || !apiResult.ok) return EMERGENCY_MODEL_CATALOG;
    const rt = apiResult.runtimes || {};
    const hasClaudeModels = (rt.claude_code_cli?.models?.length ?? 0) > 0;
    if (!hasClaudeModels) return EMERGENCY_MODEL_CATALOG;
    return rt as Record<string, RuntimeModelCatalog>;
  }
  ```
- NUEVO `Stacky Agents/frontend/src/hooks/useModelCatalog.ts` — hook delgado
  (`useState` + `useEffect` + `ModelCatalogApi.get()` + `resolveModelCatalog`),
  mismo estilo manual que los hooks existentes en ese directorio (p. ej.
  `useReviewInboxCount.ts`), sin librería nueva. Expone
  `{ catalog: Record<string, RuntimeModelCatalog>, loading: boolean }`.

**Tests primero (función pura, sin DOM):**
NUEVO `Stacky Agents/frontend/src/services/__tests__/modelCatalogFallback.test.ts`
(4 casos):
1. `EMERGENCY_MODEL_CATALOG.claude_code_cli.models` contiene un `id === "claude-sonnet-5"`.
2. `resolveModelCatalog({ok:false, runtimes:{}})` devuelve `EMERGENCY_MODEL_CATALOG`.
3. `resolveModelCatalog({ok:true, runtimes:{claude_code_cli:{...,models:[]}}})`
   (edge: ok pero sin modelos) también cae a `EMERGENCY_MODEL_CATALOG` — nunca
   selector vacío.
4. `resolveModelCatalog({ok:true, runtimes:{claude_code_cli:{...,models:[{id:"x",label:"X"}]}}})`
   devuelve los datos reales, NO el fallback.

**Comando:** `npx vitest run src/services/__tests__/modelCatalogFallback.test.ts`
(desde `Stacky Agents/frontend`)
**Criterio de aceptación BINARIO:** exit 0, `4 passed`.

**Flag:** ninguna nueva en frontend (consume la de F2 vía el `ok` de la
respuesta). **Trabajo del operador: ninguno.**

---

### F4 — Frontend: migrar `IncidentResolverModal.tsx`

**Objetivo en 1 frase:** que el selector de modelo/effort del Resolutor de
Incidencias lea del catálogo único, incluyendo `claude-sonnet-5`, y corrija su
default inconsistente.

**Archivo a editar:** `Stacky Agents/frontend/src/components/IncidentResolverModal.tsx`
- Eliminar `const CLAUDE_MODELS` (líneas 26-30) y `const CLAUDE_EFFORTS`
  (línea 32-33) tal como están hoy.
- Importar `useModelCatalog` de `../hooks/useModelCatalog`.
- Reemplazar el `.map()` sobre `CLAUDE_MODELS` (línea 289) por
  `.map()` sobre `catalog.claude_code_cli?.models ?? []`.
- Reemplazar el `.map()` sobre `CLAUDE_EFFORTS` (línea 297) por
  `.map()` sobre `catalog.claude_code_cli?.efforts ?? []`.
- Cambiar el `useState` inicial de `selectedModel` (línea 56, hoy
  `useState("claude-sonnet-4-6")`) para que arranque desde
  `EMERGENCY_MODEL_CATALOG.claude_code_cli.default_model` (import directo, sin
  esperar la respuesta async) y se sincronice con
  `catalog.claude_code_cli?.default_model` vía un `useEffect` cuando el fetch
  resuelve (para no dejar el primer render sin valor).

**Test de consistencia (cubre F4, F5 y F6 juntas — grep-gate sin DOM):**
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
(Este test se escribe completo en F4 pero solo pasará al 100% al cerrar F6 —
en F4 se corre con `.skip` en los otros 2 archivos, o se acepta que falle
parcialmente hasta F6 si el runner de la fase lo permite; el criterio BINARIO
de F4 abajo solo exige que `IncidentResolverModal.tsx` cumpla.)

**Comando F4:** `npx vitest run src/__tests__/modelSelectorsConsistency.test.ts -t IncidentResolverModal`
más `npx tsc --noEmit` (0 errores).
**Criterio de aceptación BINARIO F4:** el caso de test para
`IncidentResolverModal.tsx` pasa; `tsc --noEmit` exit 0.

**Flag:** ninguna nueva. **Trabajo del operador: ninguno.**

---

### F5 — Frontend: migrar `EpicFromBriefModal.tsx`

**Objetivo en 1 frase:** eliminar la segunda lista divergente y su validador
local, usando `effort_support` del catálogo para la misma validación.

**Archivo a editar:** `Stacky Agents/frontend/src/components/EpicFromBriefModal.tsx`
- Eliminar `const CLAUDE_MODELS` (líneas 28-33), `const CLAUDE_EFFORTS`
  (líneas 39-49) y `function isEffortValidForModel` (líneas 51-55).
- Importar `useModelCatalog`.
- Reemplazar `isEffortValidForModel(effort, modelId)` por una función local
  equivalente que consulte `catalog.claude_code_cli?.effort_support?.[modelId]?.includes(effort)`.
- Los `<select>` que iteraban `CLAUDE_MODELS`/`CLAUDE_EFFORTS` pasan a iterar
  `catalog.claude_code_cli?.models` / `.efforts`.

**Comando:** `npx vitest run src/__tests__/modelSelectorsConsistency.test.ts -t EpicFromBriefModal`
más `npx tsc --noEmit`.
**Criterio de aceptación BINARIO:** el caso de test para
`EpicFromBriefModal.tsx` pasa; `tsc --noEmit` exit 0.

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
(sin filtro — ahora los 3 archivos deben pasar los 2 casos cada uno, 6/6)
más `npx tsc --noEmit`.
**Criterio de aceptación BINARIO:** `6 passed`, `tsc --noEmit` exit 0.

**Flag:** ninguna nueva. **Trabajo del operador: ninguno.**

---

### F7 — Cierre: verificación consolidada

**Objetivo en 1 frase:** correr TODOS los comandos de aceptación de F0-F6 en
una pasada y confirmar que nada quedó en rojo antes de dar el plan por
completo.

**Sin archivos nuevos.** Comandos a correr en orden, todos desde sus
directorios respectivos (backend: `Stacky Agents/backend`; frontend:
`Stacky Agents/frontend`):

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

**Criterio de aceptación BINARIO global:** los 8 comandos anteriores exit 0.

**Smoke manual (documentar como pendiente del operador, no bloqueante):**
abrir el Resolutor de Incidencias, confirmar que el selector de modelo
muestra "Sonnet 5 (recomendado)" como primera opción; editar
`backend/config/model_catalog.json` agregando un modelo de prueba, esperar
5 minutos (TTL) o pasar `?refresh=true`, confirmar que aparece sin reiniciar
el backend ni el frontend.

**Trabajo del operador: ninguno** para que el plan funcione; el smoke manual
es una verificación opcional de quien lo despliega, no un paso obligatorio
para el operador final.

## 5. Riesgos y mitigaciones

- **El JSON queda desactualizado si nadie lo edita** — igual que las listas de
  hoy, pero ahora es 1 archivo en vez de 3-4. Mitigación: es carga del equipo
  de desarrollo/release, no del operador; documentado explícitamente en §2.
- **Caché de 300s retrasa la propagación de una edición** — trade-off
  explícito: nunca requiere restart de backend ni redeploy de frontend, solo
  hasta 5 minutos de latencia (o `?refresh=true` para forzar). Aceptable dado
  que un modelo nuevo no aparece con frecuencia de segundos.
- **`copilot_bridge.list_copilot_models()` puede fallar** (sin token `gh`, red
  caída) — ya mitigado por diseño: try/except en el endpoint (F1), degrada a
  `models: []` + `error` visible, sin afectar `claude_code_cli` ni `codex_cli`
  que siguen sirviendo desde el JSON estático.
- **Flag OFF podría dejar selectores vacíos si el fallback frontend no está
  bien enlazado** — mitigado: `EMERGENCY_MODEL_CATALOG` (F3) es una constante
  independiente del backend, compilada en el bundle, no depende de red.
- **La matriz `effort_support` migrada desde `EpicFromBriefModal.tsx:44-48`
  nunca fue verificada contra el comportamiento real del CLI** (es una
  suposición documentada en el código original, "Plan 43 F3 — efforts
  oficiales"). Mitigación: se migra tal cual estaba, sin inventar datos
  nuevos; se dejó comentado en el JSON como heredado. Un plan futuro debería
  verificarla contra Anthropic si publican la matriz oficial.
- **Riesgo de colisión de numeración con sesiones paralelas** — mitigado por
  el PASO 0/PASO 2 de este mismo plan (reverificación en frío antes de
  escribir y antes de commitear).

## 6. Fuera de scope

- `GET /api/ai/models` (`api/pm.py:616`) y `GET /api/agents/models`
  (`api/agents.py:1120`) — eje `config.LLM_BACKEND` (chat interno de PM /
  revisor de PRs / routing), **no** el eje `--model`/`--effort` del Claude
  Code CLI spawneado. No se tocan, aunque `pm.py:650-656` comparte el mismo
  síntoma (lista `claude-opus-4-7` stale) — se deja documentado como hallazgo
  para un plan de seguimiento, no se mezcla con este.
- Agregar selector de modelo/effort en la UI para `codex_cli` o
  `github_copilot` donde hoy NO existe (`IncidentResolverModal.tsx` solo
  muestra el selector cuando `agentRuntime === "claude_code_cli"`, línea 284).
  El catálogo backend expone los 3 runtimes por paridad de contrato, pero
  este plan migra únicamente los 3 componentes que el operador nombró, que
  hoy controlan exclusivamente `claude_code_cli`.
- Cambiar la lógica de decisión automática de modelo/effort
  (`STACKY_ADAPTIVE_EFFORT_ENABLED`, `services/adaptive_selector.py`) — no se
  toca el routing, solo el catálogo de OPCIONES disponibles para elegir a
  mano.
- Construir introspección real del binario `claude` (no existe hoy, no hay
  evidencia de que el CLI la exponga). Si Anthropic la publica en el futuro,
  es un plan de seguimiento que reemplazaría `source: "static_config_file"`
  por `"live_introspection"` en `claude_code_cli`, sin cambiar el contrato del
  endpoint.
- Editor visual en el panel de flags para el JSON del catálogo — el archivo se
  edita directamente en el repo/deploy, no se construye una UI de edición en
  este plan (sería trabajo nuevo no pedido, y el archivo ya es editable sin
  redeploy, que es el requisito real).

## 7. Glosario, orden de implementación y Definición de Hecho

**Glosario:**
- **AgentRuntime:** el motor que ejecuta un agente Stacky: `"github_copilot"`,
  `"codex_cli"` o `"claude_code_cli"` (`frontend/src/types.ts:10`).
- **Catálogo unificado:** el objeto `{"runtimes": {...}}` servido por
  `GET /api/agents/model-catalog`, única fuente de modelos/efforts para los 3
  componentes frontend.
- **Fallback de emergencia:** `EMERGENCY_MODEL_CATALOG` en
  `modelCatalogFallback.ts` — lo que se muestra si el catálogo del backend no
  está disponible por cualquier motivo.
- **`effort_support`:** mapa `{modelo: [efforts válidos]}` que reemplaza la
  función `isEffortValidForModel` local de `EpicFromBriefModal.tsx`.
- **TTL de caché:** 300s; tiempo máximo que puede tardar una edición del JSON
  en reflejarse sin reiniciar el backend.
- **`STACKY_MODEL_CATALOG_ENABLED`:** flag kill-switch del endpoint nuevo,
  default ON, categoría `runtimes_cli`.

**Orden de implementación:** estrictamente secuencial F0 → F1 → F2 → F3 → F4 →
F5 → F6 → F7. Cada fase depende de que la anterior esté verde (F1 necesita el
loader de F0; F3 necesita el endpoint de F1/F2; F4-F6 necesitan el hook de F3;
F7 es solo verificación consolidada).

**Definición de Hecho (DoD) global:**
1. Los 8 comandos de F7 (§4, sección F7) exit 0.
2. `grep -rn "CLAUDE_MODELS\|CLAUDE_EFFORTS\|ALT_MODELS" Stacky Agents/frontend/src/components/IncidentResolverModal.tsx Stacky Agents/frontend/src/components/EpicFromBriefModal.tsx Stacky Agents/frontend/src/components/ModelDecisionChip.tsx` → 0 resultados.
3. `grep -rn "claude-opus-4-7" Stacky Agents/frontend/src` → 0 resultados.
4. Los 3 archivos nuevos de test backend están en `HARNESS_TEST_FILES` de
   `run_harness_tests.sh` Y `run_harness_tests.ps1`.
5. La flag `STACKY_MODEL_CATALOG_ENABLED` aparece en el panel de flags de la
   UI (categoría "Runtimes CLI") sin acción adicional del operador.
6. Commit creado en la rama de trabajo con el mensaje
   `docs(plan-159): <slug>` (este documento) y, en una implementación
   posterior, un commit separado por fase con TDD real corrido con el venv
   del repo (no falsos verdes).
