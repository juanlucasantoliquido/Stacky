# 147 — Resolución robusta de rutas de proyecto + estado UI de watchers

- **Estado:** PROPUESTO v1
- **Fecha:** 2026-07-15
- **Autor:** StackyArchitectaUltraEficientCode (perfil: normal, heredado de Opus 4.8)
- **Serie:** 144–149 (derivada de `docs/reportes/2026-07-15_AUDITORIA_LOGS_deploy_vs_dev.md`)
- **Cierra:** **V2 [ALTO]** (`outputs_dir`/`repo_root` mal resuelto → output_watcher ciego, 4.761×) + **D8 [BAJO][V]** (`repo_root()` no resoluble → watchers inactivos, silencioso).
- **Cross-ref:** 144 (D4 estados / D2-D3 stalls), 145 (helper de dedup + aislar pytest), 146 (V1 import, V5 mkdir ledger, V4 re-deploy fallback), 148/149 (degradación / intake).

---

## 1. Título, objetivo e impacto

**Objetivo (1 párrafo).** Hoy la resolución de la raíz del repo donde el agente escribe `Agentes/outputs` (`runtime_paths.repo_root()`) puede emitir una ruta **plausible pero mal formada** — a la que le falta el segmento del proyecto (p. ej. `C:\desarrollo\GIT\RS\Agentes\outputs` en vez de `...\RSPACIFICO\Agentes\outputs`). El `output_watcher` termina poleando un directorio inexistente para siempre y los runs "no hacen nada" (V2, 4.761 warnings/día). Y cuando la resolución sí falla de forma explícita (sentinel), el sistema queda **sin watchers en silencio**: sólo un WARNING en log, nada en la UI (D8). Este plan **endurece `repo_root()` para que NUNCA devuelva una ruta sin segmento de proyecto** (o resuelve al `workspace_root` del proyecto activo / `STACKY_REPO_ROOT`, o devuelve un sentinel inexistente explícito) y **superficia en la UI el estado "sin proyecto activo → watchers inactivos"** reusando el banner de salud y el endpoint `/api/diag/*` ya existentes.

**KPI / impacto esperado.**
- **0** rutas `outputs_dir` mal formadas emitidas: toda ruta devuelta o contiene el segmento de proyecto (workspace_root / `STACKY_REPO_ROOT`) o es el sentinel inexistente `__stacky_repo_root_unresolved__`.
- **De 4.761 WARNING/día → ≤1 evento informativo** por período no-resuelto en dev sin proyecto (throttle + downgrade a INFO cuando la ausencia de `outputs_dir` es *esperada* por no haber proyecto activo).
- **Estado de watchers visible en 1 vistazo**: `/api/diag/health` devuelve `watchers_active`/`watchers_inactive_reason` y el HealthBanner muestra un aviso accionable "Activá un proyecto" cuando los watchers no escanean. El operador deja de preguntarse "por qué no pasa nada".
- **Runtime-agnóstico**: idéntico para Codex / Claude Code / Copilot (la resolución de rutas y los watchers no dependen del runner).

---

## 2. Por qué ahora / gap que cierra

- **Reproducción en este mismo working tree.** `repo_root()` no-congelado devuelve `Path(__file__).resolve().parents[4]` (`runtime_paths.py:136` `[V]`). En este checkout el módulo vive en `…\STACKY\Stacky\Stacky Agents\backend\runtime_paths.py`, así que `parents[4] = …\GIT\RS` y `outputs_dir()` = `…\GIT\RS\Agentes\outputs` — **la misma ruta mal formada del reporte** (V2). El fallback `parents[4]` asume el layout **embebido** `<repo>/Tools/Stacky/Stacky Agents/backend/` (así lo documenta el docstring en `runtime_paths.py:112-113` `[V]`), pero en un checkout standalone o mal anidado **sobrepasa** (overshoot) y produce una ruta sin el segmento de proyecto. `[V]`
- **Causa raíz refinada (respecto del `[INF]` del reporte).** El reporte infirió "cuando no hay proyecto activo o `STACKY_REPO_ROOT` correcto". La causa real en código es **más amplia**: en modo **no-congelado** `repo_root()` **ignora por completo** el `workspace_root` del proyecto activo (sólo lo consulta en modo congelado, `runtime_paths.py:119-123` `[V]`) y cae directo a `parents[4]`, un supuesto de profundidad de directorios frágil. Endurecer sólo el caso "sin proyecto" no alcanza: hay que **preferir el `workspace_root` del proyecto activo también en dev** y **validar** el fallback `parents[4]` antes de usarlo.
- **D8 es "esperado pero silencioso".** El sentinel (`runtime_paths.py:18`, `_UNRESOLVED_REPO_ROOT` `[V]`) y su WARNING throttled (`_warned_unresolved_repo_root`, `runtime_paths.py:23` `[V]`) ya evitan el flood, pero el operador **no tiene señal en la UI**. `/api/diag/health` ya expone `repo_root`/`outputs_dir`/`active_project`/`warnings` (`api/diag.py:285-367` `[V]`) — falta un campo explícito `watchers_active` y un check dedicado en el banner.
- **Bajo riesgo, alto ROI.** El fix es local (`runtime_paths.py` + preflight + diag + un check de banner). No toca el pipeline de ejecución ni el contrato de artifacts.

---

## 3. Principios y guardarraíles (rieles duros de Stacky)

1. **Paridad 3 runtimes.** V2 y D8 son **runtime-agnósticos**: la resolución de `repo_root`/`outputs_dir`, el `output_watcher` (Modo A/B) y el banner de salud son idénticos corriendo bajo Codex CLI, Claude Code CLI o GitHub Copilot Pro. No hay rama por runtime ni fallback específico: **aplica idéntico a los 3**. (Los conceptos runtime-específicos como "trust de workspace" pertenecen a 144, no a este plan.)
2. **Cero trabajo extra al operador.** Todo es invisible/automático. La única superficie nueva es un **aviso informativo** en el banner que **amplifica** al operador ("Activá un proyecto para que los watchers escaneen") — no agrega pasos ni configuración. `STACKY_REPO_ROOT` sigue siendo un override **opcional** (no obligatorio). **Ninguna** de las 4 excepciones duras se dispara.
3. **Human-in-the-loop.** El plan **no** activa proyectos ni cambia configuración por su cuenta: sólo **informa** el estado. La activación de proyecto la hace el operador.
4. **Mono-operador sin auth.** Sin RBAC. El endpoint de diagnóstico y el banner son de lectura para el único operador.
5. **No degradar / backward-compatible / reusar.** Se reusa: el sentinel y el throttle ya existentes en `runtime_paths.py`, el endpoint `/api/diag/health` y `/api/diag/local`, el `HealthBanner` y su patrón `DiagCheck`, el kill-switch env-only estilo `STACKY_OPERATIONAL_HEALTH_ENABLED`. **No se inventa** ningún subsistema.

### Política de flags de este plan

- **F1 (endurecer `repo_root`) NO lleva flag.** Es un **fix de bug verificado**: hoy emite una ruta mal formada (`…\GIT\RS\Agentes\outputs`) que rompe el watcher. Corregirlo no agrega comportamiento opt-in. **Backward-compat garantizada** para los tres caminos que hoy funcionan: (a) `STACKY_REPO_ROOT` seteado → idéntico; (b) proyecto activo con `workspace_root` → idéntico (y ahora también aplica en dev, que antes lo ignoraba = mejora); (c) layout embebido `<repo>/Tools/Stacky/…` → idéntico. **Sólo cambia** el caso hoy roto (overshoot) que pasa de "ruta mal formada" a "sentinel inexistente explícito" — estrictamente mejor. Justificación de "sin flag": corrige código roto, no introduce feature.
- **F3 (check de watchers en el banner) lleva kill-switch env-only, default ON:** `STACKY_WATCHERS_HEALTH_CHECK` (default `"true"`). **NO** es una flag del arnés (`FLAG_REGISTRY`), por lo que **el patrón triple NO aplica** — sigue el precedente exacto de `STACKY_OPERATIONAL_HEALTH_ENABLED` (`api/diag.py:579` `[V]`: `os.getenv(..., "true")`, sin entrada en `FLAG_REGISTRY`). No hay nada que el operador configure (es un kill-switch interno de observabilidad), así que no requiere UI. Regla citada: "Kill-switch interno default ON puede ser env-only".

---

## 4. Fases

> **Entorno de tests (verificado).** Venv real: `backend/.venv/Scripts/python.exe` (py3.13). Correr **por archivo** (la suite completa contamina cross-file). Comando canónico (cwd = `Stacky Agents/backend`):
> `.venv/Scripts/python.exe -m pytest tests/<archivo>.py -q`
> Frontend: `vitest` instalado; **no** hay `@testing-library/react` ni `jsdom` en `package.json` (gap estructural conocido) → el gate real de UI es `npx tsc --noEmit` + smoke manual. `npx vitest run <archivo>` sólo para lógica pura.

---

### F0 — Contrato de resolución robusta (TESTS PRIMERO, RED)

**Objetivo.** Fijar por test el nuevo contrato de `repo_root()`: nunca devuelve una ruta sin segmento de proyecto; el `workspace_root` del proyecto activo gana también en dev; un checkout **no embebido** sin proyecto ni `STACKY_REPO_ROOT` devuelve el sentinel. **Valor:** blinda la causa raíz de V2 con un test que hoy falla.

**Archivo a editar:** `backend/tests/test_runtime_paths.py`

**Cambios exactos:**
1. **Reemplazar** `test_not_frozen_uses_source_layout` (hoy tautológico: compara `repo_root()` contra `parents[4]` calculado igual, `test_runtime_paths.py:40-44` `[V]`) por tests que validen el layout embebido de verdad, usando un helper monkeypatcheable `_module_path` (introducido en F1).
2. **Agregar** el fixture helper para fabricar layouts en `tmp_path` sin tocar el filesystem real (sólo se construyen `Path`, no se crean dirs — la resolución es estructural, no consulta existencia).

**Tests a agregar/ajustar (nombres exactos):**

```python
# --- helpers de fabricación de layout (paths, sin crear dirs) ---
def _embedded_module_path(root: Path) -> Path:
    # <root>/Tools/Stacky/Stacky Agents/backend/runtime_paths.py  → parents[4]==root
    return root / "Tools" / "Stacky" / "Stacky Agents" / "backend" / "runtime_paths.py"

def _standalone_module_path(root: Path) -> Path:
    # <root>/STACKY/Stacky/Stacky Agents/backend/runtime_paths.py → parents[4]==root, NO embebido
    return root / "STACKY" / "Stacky" / "Stacky Agents" / "backend" / "runtime_paths.py"


def test_source_layout_repo_root_matches_embedded(monkeypatch, tmp_path):
    """El helper devuelve <repo> SOLO si el layout embebido Tools/Stacky/... calza."""
    monkeypatch.setattr(runtime_paths, "_module_path",
                        lambda: _embedded_module_path(tmp_path).resolve())
    assert runtime_paths._source_layout_repo_root() == tmp_path.resolve()


def test_source_layout_repo_root_none_when_standalone(monkeypatch, tmp_path):
    """Checkout no embebido (overshoot) → None (NO ruta mal formada)."""
    monkeypatch.setattr(runtime_paths, "_module_path",
                        lambda: _standalone_module_path(tmp_path).resolve())
    assert runtime_paths._source_layout_repo_root() is None


def test_not_frozen_embedded_layout_uses_repo_root(monkeypatch, tmp_path):
    """No congelado + layout embebido + sin proyecto → devuelve <repo> embebido."""
    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: False)
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: None)
    monkeypatch.setattr(runtime_paths, "_module_path",
                        lambda: _embedded_module_path(tmp_path).resolve())
    assert runtime_paths.repo_root() == tmp_path.resolve()


def test_not_frozen_standalone_returns_sentinel(monkeypatch, tmp_path):
    """No congelado + checkout no embebido + sin proyecto → sentinel, NO parents[4] (V2)."""
    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: False)
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: None)
    monkeypatch.setattr(runtime_paths, "_module_path",
                        lambda: _standalone_module_path(tmp_path).resolve())
    result = runtime_paths.repo_root()
    assert result == runtime_paths._UNRESOLVED_REPO_ROOT
    assert not result.exists()


def test_active_project_wins_even_not_frozen(monkeypatch, tmp_path):
    """CLAVE: en dev el workspace_root del proyecto activo gana sobre parents[4]."""
    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: False)
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: tmp_path)
    # aunque el layout embebido resolviera, el proyecto activo tiene prioridad
    monkeypatch.setattr(runtime_paths, "_module_path",
                        lambda: _embedded_module_path(tmp_path / "other").resolve())
    assert runtime_paths.repo_root() == tmp_path


def test_warning_throttled_non_frozen_standalone(monkeypatch, caplog):
    """El WARNING 'no resoluble' se emite UNA vez también en dev standalone."""
    import logging
    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: False)
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: None)
    monkeypatch.setattr(runtime_paths, "_module_path",
                        lambda: _standalone_module_path(Path("Z:/nope")).resolve())
    with caplog.at_level(logging.WARNING, logger="stacky.runtime_paths"):
        for _ in range(5):
            runtime_paths.repo_root()
    warnings = [r for r in caplog.records if "no resoluble" in r.getMessage()]
    assert len(warnings) == 1
```

**Tests EXISTENTES que se conservan sin cambios** (siguen válidos): `test_env_override_wins_even_when_frozen`, `test_frozen_with_active_project_uses_workspace_root`, `test_frozen_without_active_project_returns_nonexistent_sentinel`, `test_frozen_re_resolves_when_project_activates_later`, `test_warning_throttled_to_single_emit`. El fixture `_clean_env` (`test_runtime_paths.py:23-29` `[V]`) ya rearma `_warned_unresolved_repo_root` — mantener.

**Comando:** `cd backend && .venv/Scripts/python.exe -m pytest tests/test_runtime_paths.py -q`
**Criterio de aceptación (binario):** los tests nuevos **FALLAN en RED** con `AttributeError: module 'runtime_paths' has no attribute '_module_path'/'_source_layout_repo_root'` (helpers aún inexistentes). Falla esperada = fase lista para F1.
**Flag:** ninguna. **Runtime:** N/A (test). **Trabajo del operador:** ninguno.

---

### F1 — Endurecer `repo_root()` en `runtime_paths.py` (GREEN)

**Objetivo.** Implementar la resolución que **jamás emite una ruta sin segmento de proyecto**. **Valor:** cierra V2 en la raíz — el `output_watcher` deja de polear `…\GIT\RS\Agentes\outputs`.

**Archivo a editar:** `backend/runtime_paths.py`

**Cambios exactos:**

1. **Agregar** un accessor monkeypatcheable y la constante de layout embebido, arriba de `repo_root()`:

```python
# Nombres de los directorios intermedios del layout EMBEBIDO:
#   <repo>/Tools/Stacky/Stacky Agents/backend/runtime_paths.py
# Sólo si estos calzan exactamente, parents[4] es un <repo> bien formado.
_EMBEDDED_SUFFIX = ("Tools", "Stacky", "Stacky Agents", "backend", "runtime_paths.py")


def _module_path() -> Path:
    """Path resuelto de este módulo. Indirección para poder testear la
    resolución de layout sin depender de la ubicación real del archivo."""
    return Path(__file__).resolve()


def _source_layout_repo_root() -> Path | None:
    """<repo> SÓLO si el layout embebido Tools/Stacky/Stacky Agents/backend calza.

    Devuelve `parents[4]` únicamente cuando reconstruir ese path con el sufijo
    embebido reproduce EXACTAMENTE la ubicación del módulo. En un checkout
    standalone o mal anidado (p. ej. `<x>/STACKY/Stacky/Stacky Agents/backend`)
    el sufijo no calza y devolvemos None en vez de una ruta que sobrepasa el
    <repo> real (causa raíz de V2). Resolución puramente ESTRUCTURAL: no
    consulta el filesystem (no depende de que exista `Agentes/`).
    """
    here = _module_path()
    try:
        candidate = here.parents[4]
    except IndexError:
        return None
    if candidate.joinpath(*_EMBEDDED_SUFFIX) == here:
        return candidate
    return None
```

2. **Reescribir** `repo_root()` (reemplaza el cuerpo actual `runtime_paths.py:99-136`):

```python
def repo_root() -> Path:
    """Root del repo donde el agente escribe `Agentes/outputs`.

    Prioridad (JAMÁS emite una ruta sin segmento de proyecto):
      1. `STACKY_REPO_ROOT` — override explícito (tests / deploys).
      2. `workspace_root` del proyecto activo (`_active_workspace_root()`).
         Aplica en congelado Y en dev: si hay proyecto activo, esa es la raíz
         donde el agente escribe, sin importar frozen/no-frozen.
      3. No congelado + layout EMBEBIDO válido (`_source_layout_repo_root()`):
         `<repo>` desde `<repo>/Tools/Stacky/Stacky Agents/backend/`.
      4. Cualquier otro caso (congelado sin proyecto; dev standalone/no
         embebido): sentinel inexistente `_UNRESOLVED_REPO_ROOT` + WARNING
         throttled. NUNCA se cae a `parents[4]` a ciegas (evita la ruta
         plausible-pero-mal-formada `…\GIT\RS\Agentes\outputs` — causa V2).
    """
    global _warned_unresolved_repo_root
    env = os.getenv("STACKY_REPO_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()

    ws = _active_workspace_root()
    if ws is not None:
        _warned_unresolved_repo_root = False  # rearmar el warning
        return ws

    if not is_frozen():
        src = _source_layout_repo_root()
        if src is not None:
            _warned_unresolved_repo_root = False
            return src

    # No resoluble: ni override, ni proyecto activo, ni layout embebido válido.
    if not _warned_unresolved_repo_root:
        logger.warning(
            "repo_root() no resoluble: sin proyecto activo y sin STACKY_REPO_ROOT "
            "(frozen=%s). Devuelvo sentinel inexistente (%s); los watchers no "
            "escanearán hasta activar un proyecto con workspace_root o setear "
            "STACKY_REPO_ROOT.",
            is_frozen(), _UNRESOLVED_REPO_ROOT,
        )
        _warned_unresolved_repo_root = True
    return _UNRESOLVED_REPO_ROOT
```

**Casos borde cubiertos:**
- `parents[4]` con menos de 5 niveles (checkout raro) → `IndexError` → `None` → sentinel (no crash).
- Comparación `candidate.joinpath(*_EMBEDDED_SUFFIX) == here`: ambos derivan de `here` ya resuelto y el sufijo no tiene `..`, así que la igualdad es estructural y case-insensitive en Windows (`WindowsPath.__eq__`). No toca disco.
- Proyecto activo que se activa **después** del arranque: como el `output_watcher` resuelve `outputs_dir` **lazy por scan** (`services/output_watcher.py:153-163` `[V]`), el próximo scan re-resuelve al nuevo `workspace_root` sin reiniciar. El throttle se rearma (`_warned_unresolved_repo_root = False`) para volver a avisar si se pierde el proyecto.

**Notas de no-regresión:**
- `config.py` importa de `runtime_paths` sólo `backend_root, data_dir, runtime_config, stacky_agents_dir` (`config.py:6-11` `[V]`) — **no** `repo_root`; el cambio no afecta el import-time de config.
- `data_dir()` es independiente de `repo_root()` (`runtime_paths.py:48-54` `[V]`) → el SQLite ledger de V5 (146) **no** se ve afectado por este cambio (su ruta sale de `data_dir`, no de `repo_root`).
- Consumidores de `repo_root()` que arman `Agentes/outputs` (`services/agent_html_output.py:76-91`, `services/output_watcher.py:50`, `services/artifact_context.py:37`, `api/qa_browser.py:466`, `[V]`) reciben ahora, o el `workspace_root` correcto, o un sentinel cuyo `relative_to`/`exists()` degradan a no-op (comportamiento ya tolerado por esos call-sites cuando el dir no existe).

**Comando:** `cd backend && .venv/Scripts/python.exe -m pytest tests/test_runtime_paths.py -q`
**Criterio de aceptación (binario):** **todos** los tests de F0 + los conservados pasan (**GREEN**). En particular `test_not_frozen_standalone_returns_sentinel` y `test_active_project_wins_even_not_frozen` en verde.
**Flag:** ninguna (fix de bug, justificado en §3). **Runtime:** idéntico a los 3. **Trabajo del operador:** ninguno.

---

### F2 — Downgrade + distinción del preflight en `app.py`

**Objetivo.** Cuando `outputs_dir` no existe **sólo porque no hay proyecto activo** (estado esperado), no gritar `WARNING` repetible: bajar a `INFO`; reservar el `WARNING` accionable para el caso realmente roto (proyecto activo pero `outputs_dir` ausente). **Valor:** elimina el grueso de los 4.761 WARNING/día en dev sin proyecto.

**Archivo a editar:** `backend/app.py` (función `_log_completion_preflight`, `app.py:142-179` `[V]`)

**Cambio exacto** (reemplaza el bloque `if not od_exists:` en `app.py:163-168`):

```python
        active = get_active_project()
        logger.info(
            "preflight cierre open-chat: repo_root=%s outputs_dir=%s (existe=%s) active_project=%s",
            rr, od, od_exists, active or "(ninguno)",
        )
        if not od_exists:
            if active is None:
                # Estado ESPERADO: sin proyecto activo no hay workspace_root, así
                # que outputs_dir aún no resuelve. No es un error → INFO, no WARNING.
                logger.info(
                    "preflight: sin proyecto activo → outputs_dir aún no resoluble "
                    "(%s). Los watchers escanearán al activar un proyecto. "
                    "(Estado visible en /api/diag/health y en el banner de salud.)",
                    od,
                )
            else:
                # Proyecto activo PERO el dir no existe → misconfig real, accionable.
                logger.warning(
                    "preflight: proyecto activo '%s' pero outputs_dir NO existe (%s) "
                    "— el output_watcher no encontrará artifacts. Revisá "
                    "workspace_root del proyecto / STACKY_REPO_ROOT.",
                    active, od,
                )
```

> Nota: `get_active_project` ya se importa dentro de la función (`app.py:153` `[V]`); mover su cálculo arriba del `logger.info` no cambia dependencias.

**Cross-ref 145.** Los duplicados que quedan provienen de que **pytest escribe al mismo log diario** (V7); su aislamiento lo resuelve 145. Cuando 145 publique su **helper de dedup**, este preflight puede migrar a él; **147 no bloquea en 145** (orden global: 147 se implementa antes que 145) y se auto-contiene con el downgrade a INFO. `[INF]`

**Archivo de test (nuevo):** `backend/tests/test_completion_preflight.py`

```python
import logging
from pathlib import Path
import app  # noqa: E402  (import de módulo backend; ver sys.path en conftest)

def test_preflight_no_active_project_logs_info_not_warning(monkeypatch, caplog, tmp_path):
    missing = tmp_path / "no_existe" / "Agentes" / "outputs"
    monkeypatch.setattr("runtime_paths.repo_root", lambda: tmp_path / "no_existe")
    monkeypatch.setattr("services.agent_html_output.outputs_dir", lambda: missing)
    monkeypatch.setattr("services.ado_client.ado_pat_present", lambda: True)
    monkeypatch.setattr("project_manager.get_active_project", lambda: None)
    logger = logging.getLogger("stacky_agents.app")
    with caplog.at_level(logging.INFO, logger="stacky_agents.app"):
        app._log_completion_preflight(logger)
    msgs = [r for r in caplog.records if "outputs_dir" in r.getMessage()]
    assert msgs, "esperaba al menos un mensaje de preflight"
    assert not any(r.levelno == logging.WARNING and "NO existe" in r.getMessage()
                   for r in caplog.records)

def test_preflight_active_project_missing_dir_warns(monkeypatch, caplog, tmp_path):
    missing = tmp_path / "ws" / "Agentes" / "outputs"
    monkeypatch.setattr("runtime_paths.repo_root", lambda: tmp_path / "ws")
    monkeypatch.setattr("services.agent_html_output.outputs_dir", lambda: missing)
    monkeypatch.setattr("services.ado_client.ado_pat_present", lambda: True)
    monkeypatch.setattr("project_manager.get_active_project", lambda: "RSPACIFICO")
    logger = logging.getLogger("stacky_agents.app")
    with caplog.at_level(logging.WARNING, logger="stacky_agents.app"):
        app._log_completion_preflight(logger)
    assert any(r.levelno == logging.WARNING and "NO existe" in r.getMessage()
               for r in caplog.records)
```

> Los `monkeypatch.setattr("<módulo>.<símbolo>", ...)` apuntan al **módulo fuente** porque `_log_completion_preflight` hace imports **locales** (`from services.agent_html_output import outputs_dir`, etc., `app.py:150-153` `[V]`), que se resuelven en el momento de la llamada.

**Comando:** `cd backend && .venv/Scripts/python.exe -m pytest tests/test_completion_preflight.py -q`
**Criterio de aceptación (binario):** ambos tests **GREEN**: sin proyecto → sin WARNING "NO existe"; con proyecto activo + dir ausente → WARNING presente.
**Flag:** ninguna (ajuste de nivel de log de un fix). **Runtime:** idéntico a los 3. **Trabajo del operador:** ninguno.

---

### F3 — Estado explícito de watchers: `/api/diag/health` + check en `/api/diag/local` + banner (D8)

**Objetivo.** Superficiar "sin proyecto activo → watchers inactivos" como **estado de primera clase** en el endpoint de diagnóstico y en el banner de salud. **Valor:** cierra D8 — el operador entiende *por qué* "no pasa nada".

**Archivos a editar/crear:**
- `backend/api/diag.py` (editar `health()`)
- `backend/services/local_diagnostics.py` (agregar `_check_watchers_active` + registro)
- `backend/frontend/src/components/HealthBanner.tsx` (agregar entrada en `FIX_HINT`)

**F3.a — Campo estructurado en `/api/diag/health`.** En `api/diag.py` `health()` (`:285-367` `[V]`), computar el estado y agregarlo al payload:

```python
    # Estado explícito de watchers (D8): activos SOLO si hay proyecto activo y
    # el outputs_dir resuelto existe (o sea, repo_root no es el sentinel).
    from runtime_paths import _UNRESOLVED_REPO_ROOT
    repo_root_unresolved = (repo_root_path is not None
                            and Path(repo_root_path) == _UNRESOLVED_REPO_ROOT)
    if active_project is None:
        watchers_active = False
        watchers_inactive_reason = "sin_proyecto_activo"
    elif repo_root_unresolved:
        watchers_active = False
        watchers_inactive_reason = "repo_root_no_resoluble"
    elif not outputs_exists:
        watchers_active = False
        watchers_inactive_reason = "outputs_dir_inexistente"
    else:
        watchers_active = True
        watchers_inactive_reason = None
```

y sumar al `jsonify({...})` de retorno (`:353-367`) las claves:
```python
        "watchers_active": watchers_active,
        "watchers_inactive_reason": watchers_inactive_reason,
```
(No se remueve nada del payload existente → backward-compatible.)

**F3.b — Check dedicado en el banner** (`services/local_diagnostics.py`). Registrar en `run_local_diagnostics()` (lista de `checks`, `:28-37` `[V]`) un nuevo `_check_watchers_active()` **al final** de la lista:

```python
def _check_watchers_active() -> dict:
    """D8 — Estado explícito 'sin proyecto activo → watchers inactivos'.

    Kill-switch env-only default ON: STACKY_WATCHERS_HEALTH_CHECK=false lo apaga.
    """
    if os.getenv("STACKY_WATCHERS_HEALTH_CHECK", "true").strip().lower() == "false":
        return _result("watchers", "Watchers de artifacts", "ok",
                       "Check deshabilitado (STACKY_WATCHERS_HEALTH_CHECK=false).")
    from runtime_paths import repo_root, _UNRESOLVED_REPO_ROOT
    from services.agent_html_output import outputs_dir

    active = get_active_project()
    try:
        rr = repo_root()
        od = outputs_dir()
        od_exists = od.exists()
    except Exception as exc:  # noqa: BLE001
        return _result("watchers", "Watchers de artifacts", "warning",
                       f"No se pudo resolver outputs_dir: {exc}")

    unresolved = rr == _UNRESOLVED_REPO_ROOT
    detail = {"active_project": active, "repo_root": str(rr),
              "outputs_dir": str(od), "outputs_dir_exists": od_exists}

    if active is None:
        return _result("watchers", "Watchers de artifacts", "warning",
            "Sin proyecto activo → los watchers no escanean artifacts; los runs "
            "no se cerrarán automáticamente. Activá un proyecto.", detail)
    if unresolved or not od_exists:
        return _result("watchers", "Watchers de artifacts", "warning",
            f"outputs_dir no resuelve para '{active}' ({od}). Los watchers no "
            "escanean. Revisá workspace_root del proyecto / STACKY_REPO_ROOT.", detail)
    return _result("watchers", "Watchers de artifacts", "ok",
                   f"Watchers escaneando {od}.", detail)
```

y en `run_local_diagnostics()`:
```python
    checks = [
        _check_backend(),
        _check_tracker(),
        _check_cli_runtimes(),
        _check_gh_auth(),
        _check_vscode_installation(),
        _check_vscode_bridge(),
        _check_database_storage(),
        _check_orphan_runs(),
        _check_watchers_active(),   # ← D8
    ]
```

> Reusa el helper `_result` (`:436-449` `[V]`) y el patrón `id/label/status/message/detail`. El `HealthBanner` ya renderiza cualquier check `warning`/`error` (`HealthBanner.tsx:70-78` `[V]`), así que el aviso aparece **sin** tocar la lógica de render.

**F3.c — Fix-hint del banner** (`HealthBanner.tsx`). Agregar la entrada en `FIX_HINT` (`:50-56` `[V]`):
```ts
  watchers: { label: "Activar proyecto", tab: "settings" },
```
(el handler `goTab` mapea `tab: "settings"` → `/settings`, `HealthBanner.tsx:106-109` `[V]`, donde vive la activación de proyecto).

**Archivos de test (nuevos):**

1. `backend/tests/test_watchers_health_check.py` — unit de `_check_watchers_active`:
```python
import services.local_diagnostics as ld

def test_no_active_project_warns(monkeypatch, tmp_path):
    monkeypatch.delenv("STACKY_WATCHERS_HEALTH_CHECK", raising=False)
    monkeypatch.setattr(ld, "get_active_project", lambda: None)
    monkeypatch.setattr("runtime_paths.repo_root", lambda: tmp_path)
    monkeypatch.setattr("services.agent_html_output.outputs_dir",
                        lambda: tmp_path / "Agentes" / "outputs")
    r = ld._check_watchers_active()
    assert r["id"] == "watchers" and r["status"] == "warning"

def test_active_project_with_dir_ok(monkeypatch, tmp_path):
    monkeypatch.delenv("STACKY_WATCHERS_HEALTH_CHECK", raising=False)
    od = tmp_path / "Agentes" / "outputs"; od.mkdir(parents=True)
    monkeypatch.setattr(ld, "get_active_project", lambda: "RSPACIFICO")
    monkeypatch.setattr("runtime_paths.repo_root", lambda: tmp_path)
    monkeypatch.setattr("services.agent_html_output.outputs_dir", lambda: od)
    r = ld._check_watchers_active()
    assert r["status"] == "ok"

def test_kill_switch_disables(monkeypatch):
    monkeypatch.setenv("STACKY_WATCHERS_HEALTH_CHECK", "false")
    monkeypatch.setattr(ld, "get_active_project", lambda: None)
    r = ld._check_watchers_active()
    assert r["status"] == "ok"
```
**Comando:** `cd backend && .venv/Scripts/python.exe -m pytest tests/test_watchers_health_check.py -q`

2. `backend/tests/test_diag_health_watchers.py` — contrato del endpoint:
```python
import app as app_module

def _client(monkeypatch):
    flask_app = app_module.create_app()
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()

def test_health_reports_watchers_active_fields(monkeypatch):
    monkeypatch.setattr("project_manager.get_active_project", lambda: None)
    client = _client(monkeypatch)
    resp = client.get("/api/diag/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "watchers_active" in data
    assert data["watchers_active"] is False
    assert data["watchers_inactive_reason"] == "sin_proyecto_activo"
```
> Si `create_app()` resulta caro/con side-effects en el harness, alternativa: importar `api.diag` y llamar `health()` dentro de un `app.test_request_context()`. Elegir la que corra limpio por-archivo (verificar durante implementación con el comando de abajo; **no** asumir).

**Comando:** `cd backend && .venv/Scripts/python.exe -m pytest tests/test_diag_health_watchers.py -q`

**Frontend:** `cd frontend && npx tsc --noEmit` (debe dar **0 errores**). No hay test RTL (gap estructural jsdom/@testing-library ausente); el render del banner se valida en el smoke de F4.

**Criterio de aceptación (binario):**
- Los 2 archivos de test backend **GREEN**.
- `npx tsc --noEmit` → 0 errores.
- `GET /api/diag/health` incluye `watchers_active` y `watchers_inactive_reason`.
- `GET /api/diag/local` incluye un check `id="watchers"`.

**Flag:** `STACKY_WATCHERS_HEALTH_CHECK` (env-only, default ON). **Runtime:** idéntico a los 3 (diagnóstico agnóstico). **Trabajo del operador:** ninguno (opt-in default ON; el banner sólo informa).

---

### F4 — Verificación integral + smoke manual

**Objetivo.** Confirmar los criterios binarios end-to-end y el comportamiento observable. **Valor:** cero falsos verdes.

**Pasos:**
1. **Backend por archivo** (todos GREEN, pegar output real):
   - `cd backend && .venv/Scripts/python.exe -m pytest tests/test_runtime_paths.py -q`
   - `cd backend && .venv/Scripts/python.exe -m pytest tests/test_completion_preflight.py -q`
   - `cd backend && .venv/Scripts/python.exe -m pytest tests/test_watchers_health_check.py -q`
   - `cd backend && .venv/Scripts/python.exe -m pytest tests/test_diag_health_watchers.py -q`
   - Regresión de vecinos: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_diag_endpoint.py -q` (no debe romperse por las claves nuevas).
2. **Frontend:** `cd frontend && npx tsc --noEmit` → 0 errores.
3. **Smoke manual (documentar resultado):**
   - Arrancar backend **sin** proyecto activo.
   - `GET /api/diag/health` → `watchers_active:false`, `watchers_inactive_reason:"sin_proyecto_activo"`.
   - `GET /api/diag/local` → check `watchers` en `warning`.
   - El `HealthBanner` muestra "Watchers de artifacts — Sin proyecto activo…" con botón "Activar proyecto".
   - Verificar en el log: `INFO` de preflight (no `WARNING` "NO existe").
   - Activar un proyecto con `workspace_root` válido → repetir: `watchers_active:true`, check en `ok`, banner limpio; el próximo scan del `output_watcher` toma el nuevo `outputs_dir` (log "output watcher started/scan").

**Criterio de aceptación (binario):** los 5 comandos de test en verde con output pegado + `tsc` en 0 + los 6 puntos del smoke observados. **Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | Un consumidor de `repo_root()` dependía del `parents[4]` overshoot en dev standalone y ahora recibe el sentinel. | Baja | Medio | Todos los call-sites de `repo_root()` no-test arman `Agentes/outputs` para el **workspace del proyecto** (`[V]` §4.F1). Con proyecto activo resuelve igual; sin proyecto, el sentinel degrada a no-op (dir inexistente ya tolerado). Tests usan `STACKY_REPO_ROOT`. |
| R2 | El test viejo `test_not_frozen_uses_source_layout` (tautológico) queda obsoleto. | Alta | Bajo | Se **reemplaza** explícitamente en F0 por tests que validan el layout embebido de verdad. |
| R3 | `create_app()` en `test_diag_health_watchers.py` con side-effects que ensucian por-archivo. | Media | Bajo | F3 ofrece alternativa `test_request_context` + llamada directa a `health()`; elegir la que corra limpio (verificar, no asumir). |
| R4 | El operador confunde "watchers inactivos (esperado)" con "sistema roto". | Baja | Bajo | El mensaje del banner es **accionable y no alarmista** ("Activá un proyecto"), status `warning` (no `error`), con botón directo. |
| R5 | Choque con la sesión paralela activa sobre `runtime_paths.py` / `app.py`. | Media | Medio | Cambios acotados a funciones nombradas; el implementador re-lee en frío y hace `git status` antes de tocar (memoria: sesión concurrente en árbol compartido). |
| R6 | 145 aún no existe cuando se implementa 147 (orden global). | Alta | Bajo | 147 es **auto-contenido**: throttle propio + downgrade a INFO. La migración al helper de dedup de 145 es una nota futura, **no** una dependencia dura. |

---

## 6. Fuera de scope (lo cierran otros planes de la serie)

- **D4 vocabulario de estados** (`needs_review` rechazado por `ticket_status.VALID_STATUSES` = `{idle,running,completed,error,cancelled}`, `services/ticket_status.py:35,110-111` `[V]`; choca con `agent_completion.TERMINAL_STATUSES`, `:44` `[V]`) → **144**.
- **D2/D3 stalls y reaper de 120 min** → **144**.
- **404 `pipeline/status`, strip ANSI, aislar pytest (V7), helper de dedup** → **145**.
- **V1 import `Execution`→`AgentExecution`** (`services/ado_edit_learning.py:259` `[V]`), **V5 mkdir del SQLite ledger** (`services/ado_edit_ledger.py`, usa `data_dir`, `[V]`), **V4 re-deploy con `CLAUDE_CODE_CLI_MODEL_FALLBACK`** (`config.py:216-217` `[V]`) → **146**.
- **Degradación de integraciones (PAT/Jira/LLM local 502, api-version)** → **148**.
- **`pending-task.json` inválido + excepciones tipadas en endpoints** → **149**.
- **No** se cambia el `output_watcher` (ya resuelve lazy per-scan), ni se auto-activa proyecto, ni se crea UI nueva de proyectos.

---

## 7. Glosario + Orden de implementación + DoD

### Glosario (términos Stacky)
- **`repo_root()`**: raíz del workspace del **proyecto activo** donde el agente escribe `Agentes/outputs`. No es el repo de Stacky.
- **`workspace_root`**: campo de `projects/<activo>/config.json` con la ruta del checkout del cliente (p. ej. RSPACIFICO). Lo lee `_active_workspace_root()`.
- **Sentinel `_UNRESOLVED_REPO_ROOT`**: path inexistente a propósito (`<backend>/__stacky_repo_root_unresolved__`) que se devuelve en vez de una ruta mal formada; hace no-op a los watchers.
- **Layout embebido**: `<repo>/Tools/Stacky/Stacky Agents/backend/` — Stacky como submódulo del repo del cliente. `parents[4]` sólo es válido si este layout calza.
- **`output_watcher` (Modo A/B)**: polea `Agentes/outputs` para cerrar runs y crear Tasks; resuelve `outputs_dir` lazy por scan.
- **`DiagCheck`**: item `{id,label,status,message,detail}` que el `HealthBanner` renderiza (warning/error).
- **Kill-switch env-only**: variable de entorno interna (default ON) que no es flag del arnés ni requiere UI (no hay valor que el operador configure).

### Orden de implementación
1. **F0** — tests del contrato de `repo_root()` (RED).
2. **F1** — endurecer `repo_root()` + `_source_layout_repo_root`/`_module_path` (GREEN).
3. **F2** — downgrade/distinción del preflight en `app.py` + tests.
4. **F3** — `watchers_active` en `/api/diag/health`, `_check_watchers_active` en `/api/diag/local`, `FIX_HINT` del banner + tests + `tsc`.
5. **F4** — verificación por-archivo + `tsc` + smoke manual.

### Definición de Hecho (DoD) global
- [ ] `repo_root()` **nunca** devuelve una ruta sin segmento de proyecto: o `STACKY_REPO_ROOT`, o `workspace_root` del proyecto activo (frozen **y** dev), o layout embebido válido, o el sentinel inexistente.
- [ ] `test_runtime_paths.py` verde, incluyendo `test_not_frozen_standalone_returns_sentinel` y `test_active_project_wins_even_not_frozen`.
- [ ] Preflight: sin proyecto activo → **INFO** (no WARNING); proyecto activo + dir ausente → **WARNING** accionable. `test_completion_preflight.py` verde.
- [ ] `/api/diag/health` expone `watchers_active` + `watchers_inactive_reason`; `/api/diag/local` incluye check `watchers`; banner con fix-hint "Activar proyecto". Tests backend verdes + `tsc --noEmit` 0.
- [ ] Smoke manual observado (6 puntos de F4) con output pegado.
- [ ] Paridad 3 runtimes: sin ramas por runtime; comportamiento idéntico.
- [ ] Cero trabajo extra al operador; backward-compatible; ningún subsistema reinventado.
- [ ] Memoria actualizada con el hecho durable (resolución hardened + contrato de `_source_layout_repo_root`).
