# Plan 80 — Integración real (wiring) de `codebase-memory-mcp` para búsqueda de código eficiente en tokens

> **Estado:** v2 -> v3 (2026-06-30) — APROBADO-CON-CAMBIOS por StackyArchitectaUltraEficientCode (2ª pasada).
> **Changelog v3:**
> - C-RES-1 RESUELTO (BLOQUEANTE): `_build_internal_servers(...)` era una referencia a función inexistente. F2 pseudocódigo refactorizado: el helper se llama `_build_internal_server_block` y se define inline en la misma F2 con firma y cuerpo exactos, tomando los mismos parámetros que la `maybe_write_mcp_config` original. Ver sección F2 §Extracción de bloque interno.
> - C-RES-2 RESUELTO (IMPORTANTE): F3 y "Notas para el modelo menor" añaden nota explícita: el servidor externo arranca sin índice; el operador debe correr `codebase-memory-mcp index_repository --path <ruta-repo>` (o `config set auto_index true`) ANTES de activar el flag. Sin índice previo, las tools devuelven vacío. Añadido a "Fuera de scope" la responsabilidad de indexación.
> - C-RES-3 RESUELTO (IMPORTANTE): §1 KPI ítem 3 reescrito — elimina "telemetría automática antes/después" (promesa no cumplida por el cuerpo). El KPI ahora dice "estimación PoC manual" de forma honesta. F5 título ajustado: "Medición estimada (PoC manual)" en lugar de "REAL". El productor no existe en el runtime; `aggregate_savings()` es función pura sin instrumentación automática — declarado sin ambigüedad.
> - C-RES-4 RESUELTO (MENOR): F7 añade un caso 4 en `test_plan80_ratchet_byteidentical.py` que verifica que los 9 archivos `test_plan80_*.py` también estén en `run_harness_tests.ps1` (en sync con el .sh). Sin este test el ".ps1" queda como promesa cosmética.
> - [ADICIÓN ARQUITECTO v3] F2 añade una nota de seguridad del `binary_path`: antes de escribir el server externo, el writer debe verificar que `binary_path` no contenga separadores de path relativos (`..`) para evitar path traversal si el operador escribe la ruta por UI. La función pura `build_external_server_entry` en F1 rechaza paths con `..` (devuelve `None` + log warn) — añadido al pseudocódigo de F1 y a su test caso 3b.
> - C-RES-5 RESUELTO (MENOR, cierre del árbitro): la fila "Medición de ahorro de tokens" de la tabla §0 todavía decía "telemetría automática antes/después" — inconsistente con C-RES-3 (F5 = PoC manual, sin telemetría auto). Alineada la fila §0 con F5: "función pura de estimación + endpoint; PoC manual reproducible; `samples=0`/`delta_pct: null` hasta que el operador corra la PoC". Sin este ajuste el plan se contradecía a sí mismo (objetivo↔implementación).
>
> **Changelog v2 (preservado):**
> - C1 RESUELTO (ampliado): eliminado el caveat ambiguo de `type="str"`. `BINARY_PATH` es `type="str" env_only=False`. F0 AÑADE tres fixes a `harness_flags.py`:
>   1. `_type_zero("str")→""` (`:1846-1853`).
>   2. **`_cast` bug BLOQUEANTE (`:2004`):** `_cast` no tiene branch para `"str"` → `raise ValueError("Tipo desconocido")` al guardar el flag desde la UI (PUT). Fix mínimo: añadir antes del raise final: `if spec.type == "str": return "" if raw is None else str(raw)`. Esto también arregla el bug latente de `STACKY_MIGRATOR_EPIC_POLICY` (Plan 74), misma línea, cero scope extra.
>   3. Rama `"str"` en `HarnessFlagsPanel.tsx` (texto libre, idéntica a `"csv"`, sin split).
>   El tipo `"str"` ya existe en producción (`STACKY_MIGRATOR_EPIC_POLICY`, harness_flags.py:1788) pero `_cast` + `_type_zero` tenían bugs latentes que F0 sella.
> - C2 RESUELTO: F2 añade test caso 8 (catch monolítico en runner: si `write_text` lanza, devuelve `None` y el runner no propaga; garantiza que el catch existente es suficiente porque las funciones puras de F1 nunca lanzan). Se documenta por qué el externo no puede tumbar al interno con las funciones puras.
> - C3 RESUELTO: F3 fija 3b como **la única opción implementada** en este plan. Opción 3a se convierte en plan 80b independiente explícito, documentado en apéndice. Eliminada la frase "trivial y segura" (ambigua).
> - C4 RESUELTO: `aggregate_savings()` retorna `{"samples": 0, "delta_pct": null, "note": "..."}`. La card F6 muestra "sin datos aún". Test F5 caso 5 afirma `delta_pct is None`.
> - C5 RESUELTO: F6 añade `test_plan80_status_shape.py` con no-regresión de las 5 claves del 76 + las 2 de `wiring`.
> - C6 RESUELTO: F2 test caso 2 especifica comparación estructural `json.loads(actual) == json.loads(esperado)` (no strings).
> - C7 RESUELTO: F7 documenta que el caso 3 es redundante si `test_plan76_routes_registered.py` sigue verde; se mantiene como centinela de co-existencia.
> - C8 RESUELTO: F4 test caso 1 usa `"copilot_pro"` citando `codebase_memory_mcp.py:31`.
> - [ADICIÓN ARQUITECTO] F2 añade test caso 9: medir el **tiempo de escritura del writer** con ambos servers activos vs solo el interno, afirmando que el overhead es < 5 ms (las funciones puras no tocan disco ni red; el único costo es serialización JSON de 1 entrada extra). Esto blinda que el wiring no introduce latencia perceptible en el hot path del runner.
> - [ADICIÓN ARQUITECTO] F0 añade `pair="STACKY_CODEBASE_MEMORY_MCP_ENABLED"` en el `FlagSpec` de `*_PROJECTS` (ya se menciona en el plan pero el pseudocódigo del FlagSpec no lo incluía explícitamente). Sin `pair`, la UI no renderiza el `*_PROJECTS` junto al master toggle.

> **Pre-requisito DURO:** Plan 76 IMPLEMENTADO (commit `233adbd5`) — flag `STACKY_CODEBASE_MEMORY_MCP_ENABLED`, blueprint `api/codebase_memory_mcp.py`, helpers `services/codebase_memory_mcp_status.py`, guías en `docs/_evals/codebase-memory-mcp/`. **Este plan CONSTRUYE sobre ese sustrato; no lo reescribe.**
> **Roadmap:** continuación directa del Plan 76 (eval) → este es el **plan de implementación concreta** que el 76 dejó pendiente para "si F4 elige (B)". El 76 eligió (B) ADOPTAR-OPCIONAL-NO-CORE. Hoy el flag del 76 es **decorativo**: encenderlo no inyecta nada en el runtime (solo cambia un `enabled: true` en un endpoint de estado). Este plan lo vuelve **funcional**.

---

## 0. Reconciliación EXPLÍCITA con el Plan 76 (qué heredo / agrego / cambio)

| Aspecto | Plan 76 (ya implementado) | Plan 80 (este) |
|---|---|---|
| Flag `STACKY_CODEBASE_MEMORY_MCP_ENABLED` | **HEREDO tal cual** (`config.py`, `FLAG_REGISTRY` `env_only=False` cat `"avanzado"`, `.env.example`, `harness_defaults.env`) | No lo redefino; **agrego** su par `*_PROJECTS` y `*_BINARY_PATH` |
| Blueprint `GET /api/codebase-memory-mcp/status` | **HEREDO** (`api/codebase_memory_mcp.py`, `url_prefix="/codebase-memory-mcp"` correcto, sin `/api/api`) | **Extiendo** la respuesta con `wiring` (estado real de inyección) sin romper el shape actual |
| Helpers puros `codebase_memory_mcp_status.py` | **HEREDO** (`mcp_installation_status`, `build_installation_guide`) | **Agrego** helpers puros nuevos en módulo separado para el wiring (`codebase_memory_mcp_wiring.py`) |
| Clave MCP namespaced `"codebase-memory-mcp"` ≠ `"stacky"` | **HEREDO el contrato** (C4/C10 del 76) | Lo **aplico en el writer real** de `mcpServers` |
| Guías de instalación read-only | **HEREDO** (`docs/_evals/codebase-memory-mcp/install-*.md`) | **Agrego** sección de re-indexación/watcher (D6 del 76 quedó en doc, lo hago accionable) |
| Decisión D1-D9 | **NO la toco** (es la eval del 76) | La **cito**; corrijo SOLO con evidencia nueva del repo real (ver §2) |
| Wiring real en runtimes | **NO existe** (76 es read-only por diseño: era una eval) | **ES EL CORE DE ESTE PLAN** |
| Medición de ahorro de tokens | 76 lo dejó como PoC manual pendiente (`poc-metrics.md`) | **Agrego función pura de estimación + endpoint** para una PoC manual reproducible (NO telemetría automática; `aggregate_savings` reporta `samples=0`/`delta_pct: null` hasta que el operador corra la PoC — ver F5, C-RES-3 v3) |

**Qué NO cambio del 76:** la decisión (B), la scorecard, el blueprint de status, los helpers de status, la clave namespaced, el centinela `test_plan76_routes_registered.py`, el ratchet con token específico. **No duplico** ninguno de esos archivos; los reuso.

---

## 1. Objetivo y KPI

**Objetivo:** que cuando el operador active `STACKY_CODEBASE_MEMORY_MCP_ENABLED` (default OFF), el agente **realmente** consuma el servidor `codebase-memory-mcp` para buscar código (símbolos, callers, snippets) en vez de grep-ear/leer archivos enteros — reduciendo tokens por query estructural — **con paridad honesta entre runtimes** y **medición real del ahorro** (no promesa).

**Problema real que resuelve (declarado por el operador):** "cualquier llamada gasta muchos tokens" — hoy el agente descubre código leyendo archivos enteros. El MCP indexa el codebase en un grafo local y devuelve solo los chunks relevantes (`get_code_snippet`, `search_graph`, `trace_call_path`).

**KPI / DoD medible:**
1. Con flag ON para un proyecto, el `mcp-config.json` del run de Claude CLI contiene **2 servers** (`"stacky"` + `"codebase-memory-mcp"`) y el agente puede invocar las tools del MCP externo. (Verificado por test del writer + test del builder de args.)
2. Con flag OFF (default), Stacky es **byte-idéntico** a hoy: 1 solo server (o ninguno), cero inyección del externo. (Ratchet F6 del 76 sigue verde + nuevo ratchet de este plan.)
3. **Métrica de ahorro estimada (PoC manual):** `codebase_memory_mcp_wiring.py` expone `estimate_query_savings(chars_baseline, chars_mcp_response)` (función pura, sin productor automático en el runtime) y `aggregate_savings()` que retorna `{samples:0, delta_pct:null}` hasta que el operador corra la PoC manual del 76. El KPI se cumple cuando el panel muestra ese shape honesto. **No hay instrumentación automática de runs** (C-RES-3): el runtime no llama `estimate_query_savings` con datos reales. El endpoint `/api/codebase-memory-mcp/savings` expone el estado honesto siempre.
4. **Paridad honesta:** Claude CLI = inyección automática; Codex = guía manual (Opción 3b, F3 — ver §Nota-3b); Copilot Pro = guía manual (degradación controlada documentada — el bridge HTTP no spawnea CLI con flags MCP). **No se promete inyección automática donde el runtime no la soporta.**

> **Nota-3b:** La opción de wiring automático de Codex (Opción 3a) NO se implementa en este plan. Es el plan 80b independiente. Ver F3.

---

## 2. Evidencia del repo real (anti-alucinación) y corrección de supuestos del 76

Verificado contra https://github.com/DeusData/codebase-memory-mcp (WebFetch 2026-06-30) y contra el código de Stacky (archivo:línea):

- **El MCP es un binario estático en C/C++ (88.4% C), zero-dependencies, stdio, 100% local, sin telemetría.** ("your code, queries, environment, and usage never leave your machine"). → **Refuerza D9** (egress local) que el 76 dejó DUDOSO por falta de PoC: el README declara local-only; la PoC sandbox del operador sigue siendo el gate final, pero el riesgo baja.
- **Windows nativo:** binarios prebuilt + Scoop/Winget/Chocolatey. → **Refuerza D8** (el 76 ya lo tenía APROBADO).
- **14 tools concretas** (no las que sumió el boceto): indexado (`index_repository`, `index_status`, `list_projects`, `delete_project`); query (`search_graph`, `trace_path`/`trace_call_path`, `detect_changes`, `query_graph`, `get_graph_schema`, `get_code_snippet`, `get_architecture`, `search_code`, `manage_adr`, `ingest_traces`). → Las que dan ahorro de tokens directo son `get_code_snippet` (lee por nombre cualificado, no archivo entero), `search_graph` y `search_code`.
- **Re-indexación:** manual (`index_repository`) o auto en session-start si `config set auto_index true`; watcher de background (git polling) re-indexa cambios. → **Hace accionable D6** del 76.
- **Launch:** `codebase-memory-mcp` (stdio) como subproceso — **idéntico al modelo de `stacky_mcp_server.py`** (subproceso stdio declarado en `mcpServers`).

**Wiring de Stacky verificado (archivo:línea):**
- `services/stacky_mcp.py:22` `maybe_write_mcp_config(...)` escribe `run_dir/mcp-config.json` con literal `{"mcpServers":{"stacky":{...}}}` (`:63-71`) — **un solo server hardcodeado, sin merge**.
- `services/claude_code_cli_runner.py:595` único caller; `:1828-1829` `cmd.extend(["--mcp-config", str(mcp_config_file)])` — **solo Claude CLI consume `--mcp-config`**.
- `services/claude_code_cli_runner.py:605-607` catch monolítico: si el writer lanza, `mcp_config_file=None` → degrada **TODO** el MCP (incluido "stacky"). **Análisis de riesgo:** las funciones puras de F1 (`build_external_server_entry`, `merge_external_server`) nunca lanzan porque no tocan disco ni red. El único punto de fallo real del writer es `write_text` (disco). Por lo tanto el catch monolítico existente ya es suficiente en la práctica — el 2º server no puede tumbar al interno salvo error de escritura en disco, que ya degrada todo el MCP (comportamiento existente). F2 lo verifica con un test explícito.
- `services/codex_cli_runner.py:336` comentario "sin rama MCP"; `:1316` solo recibe `mcp_enabled: bool` para texto de reglas → **Codex NO inyecta MCP hoy**.
- `copilot_bridge.py` sin referencias MCP → **Copilot NO inyecta MCP** (bridge HTTP de modelos).
- `services/cli_feature_flags.py:119-127` `mcp_enabled(project_name)` = `project_enabled(enabled=CLAUDE_CODE_CLI_MCP_ENABLED, projects_csv=CLAUDE_CODE_CLI_MCP_PROJECTS, ...)`. Patrón `master AND allowlist CSV`.
- `services/harness_flags.py:19-27` `FlagSpec(key,type,label,description,group,pair,env_only,default)`; `pair` asocia el `*_PROJECTS` para que la UI los renderice juntos.
- `services/harness_flags.py:1788` `type="str"` YA SE USA en producción (`STACKY_MIGRATOR_EPIC_POLICY`). Sin embargo, `_type_zero(flag_type)` (`:1846-1853`) **no tiene caso `"str"`** y cae a `return 0` (int) — bug latente: no explotó en producción porque `MIGRATOR_EPIC_POLICY` tiene `default="auto"` (no None), así `_type_zero` nunca se invocó para ella. F0 lo sella. El frontend `HarnessFlagsPanel.tsx` tampoco tiene rama para `"str"` — F0 la añade (idéntica a `"csv"`, input de texto libre sin split).

---

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes, paridad HONESTA con fallback explícito por runtime** (no promesa ciega):
  - **Claude Code CLI:** inyección automática del 2º server en `mcp-config.json` (extendiendo el writer existente). **Primario.**
  - **Codex CLI:** **Opción 3b — guía manual** (default duro en este plan). El wiring automático es el plan 80b independiente. Con flag ON, el runner emite un log informativo; la guía del 76 ya existe. Con flag OFF, byte-idéntico.
  - **GitHub Copilot Pro:** el bridge HTTP no spawnea CLI con MCP → **fallback = guía manual VS Code** (ya existe del 76). Degradación controlada documentada. **No se promete inyección automática.**
- **Cero trabajo extra al operador:** todo opt-in, default OFF. El binario lo instala el operador aparte (Stacky NO lo empaqueta — fuera de scope del 76, se mantiene). Con flag OFF, **nada cambia**.
- **No tumbar el MCP interno:** el 2º server es **aditivo**; F1 garantiza que las funciones puras nunca lanzan; el único fallo posible es `write_text` (disco), que ya degrada todo el MCP (comportamiento histórico). F2 caso 8 lo verifica.
- **Human-in-the-loop:** el agente consume el MCP como herramienta; el operador sigue revisando outputs. No hay autonomía nueva.
- **Mono-operador sin auth:** sin RBAC.
- **No degradar / backward-compatible:** flag OFF = byte-idéntico (ratchet). El writer refactorizado con flag OFF produce **exactamente** el mismo `mcp-config.json` que hoy.
- **TDD + funciones puras + ratchet + no falsos verdes:** todo el wiring se expresa como **funciones puras** (`build_external_server_entry`, `merge_external_server`, `estimate_query_savings`) testeables sin red ni binario, más centinelas.
- **Reuso obligatorio:** flag del 76, patrón `project_enabled`, `FlagSpec.pair`, telemetría existente, clave namespaced del 76.
- **Seguridad:** el server externo se inyecta SOLO si flag ON. El gate de egress (D9 del 76) sigue siendo responsabilidad de la PoC sandbox del operador; este plan **no** abre red desde el backend de Stacky (las funciones son puras).

---

## 4. Fases

### F0 — Par de flags por proyecto + fix `_type_zero("str")` + rama frontend para `"str"`

**Objetivo (1 frase):** dar al server externo su propio control por proyecto (como `CLAUDE_CODE_CLI_MCP_*`), sin acoplarlo al flag del MCP interno, y cerrar el bug latente de `_type_zero` y `HarnessFlagsPanel` para el tipo `"str"`.

**Valor:** el operador puede activar el MCP externo en un proyecto y configurar la ruta del binario desde la UI (igual que cualquier otra flag editable), sin trabajo extra.

**Archivos exactos:**

**A. `backend/config.py`** — AÑADIR junto a las demás flags de la categoría (patrón EXACTO de `config.py:817`, usando `os.getenv("...","")`, NUNCA `: str = ""`):
```python
# Plan 80 — Allowlist por proyecto para el MCP externo codebase-memory-mcp.
# Master = STACKY_CODEBASE_MEMORY_MCP_ENABLED (Plan 76, ya existe). Vacío = todos los proyectos.
STACKY_CODEBASE_MEMORY_MCP_PROJECTS: str = os.getenv(
    "STACKY_CODEBASE_MEMORY_MCP_PROJECTS", ""
)
# Plan 80 — Ruta absoluta del binario codebase-memory-mcp en la máquina del operador.
# Vacío (default) => NO se inyecta el 2º server aunque el master esté ON (degradación segura).
STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH: str = os.getenv(
    "STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH", ""
)
```

**B. `backend/services/cli_feature_flags.py`** — AÑADIR wrapper tipado (mismo patrón que `mcp_enabled`, `:119-127`):
```python
def codebase_memory_mcp_enabled(project_name: str | None) -> bool:
    """Plan 80 — server MCP externo codebase-memory-mcp, por proyecto."""
    from config import config
    return project_enabled(
        enabled=config.STACKY_CODEBASE_MEMORY_MCP_ENABLED,
        projects_csv=config.STACKY_CODEBASE_MEMORY_MCP_PROJECTS,
        project_name=project_name,
    )
```

**C. `backend/services/harness_flags.py`** — DOS cambios:

C.1 — AÑADIR los dos `FlagSpec` en la sección de flags `"avanzado"`, con `pair` explícito en `*_PROJECTS`:
```python
FlagSpec(
    key="STACKY_CODEBASE_MEMORY_MCP_PROJECTS",
    type="csv",
    label="Codebase Memory MCP — proyectos (CSV) — Plan 80",
    description=(
        "Plan 80 — Lista CSV de proyectos donde inyectar el MCP externo codebase-memory-mcp. "
        "Vacío = todos (si el master STACKY_CODEBASE_MEMORY_MCP_ENABLED está ON). "
        "Requiere también STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH seteado."
    ),
    group="global",
    pair="STACKY_CODEBASE_MEMORY_MCP_ENABLED",   # <-- renderiza junto al master toggle
    env_only=False,
    default="",
),
FlagSpec(
    key="STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH",
    type="str",
    label="Codebase Memory MCP — ruta del binario — Plan 80",
    description=(
        "Plan 80 — Ruta absoluta al ejecutable codebase-memory-mcp instalado por el operador. "
        "Vacío = no se inyecta el 2º server (seguro). Stacky NO empaqueta el binario. "
        "Ejemplo: C:\\\\tools\\\\codebase-memory-mcp.exe"
    ),
    group="global",
    env_only=False,
    default="",
),
```
> Agregar ambas keys a `_CATEGORY_KEYS["avanzado"]`.

C.2 — FIX BUG LATENTE en `_type_zero` (`:1846-1853`). BUSCAR la función y añadir el caso `"str"` antes del fallback final:
```python
def _type_zero(flag_type: str) -> object:
    if flag_type == "bool":
        return False
    if flag_type in ("csv", "json", "str"):   # <-- añadir "str" aquí
        return ""
    if flag_type == "float":
        return 0.0
    return 0  # int
```

C.3 — FIX BUG BLOQUEANTE en `_cast` (`:2004`). `_cast` no tiene branch para `"str"` y lanza `ValueError("Tipo desconocido")` al guardar un flag `type="str"` desde el `HarnessFlagsPanel` (PUT de flags). BUSCAR la función `_cast` y añadir **antes del `raise ValueError` final** (`:2004`):
```python
    if spec.type == "str":
        return "" if raw is None else str(raw)
    raise ValueError(f"Tipo desconocido en FLAG_REGISTRY para {spec.key!r}: {spec.type!r}")
```
> Este fix de 1 línea también cierra el bug latente de `STACKY_MIGRATOR_EPIC_POLICY` (Plan 74, `type="str"`, `env_only=False`). Impacto: ninguno en las flags existentes (todos los tipos anteriores siguen sus propias ramas; `"str"` es nueva). **Es el pre-requisito más importante de F0**: sin él, editar `BINARY_PATH` por UI tira `ValueError` y la flag es inutilizable desde el frontend.

**D. `frontend/src/components/HarnessFlagsPanel.tsx`** — AÑADIR rama para `"str"` después del bloque `if (flag.type === "csv")` (`:115-126`):
```tsx
if (flag.type === "str") {
  return (
    <input
      type="text"
      className={styles.textInput}
      value={localText}
      disabled={saving}
      onChange={(e) => setLocalText(e.target.value)}
      onBlur={() => onUpdate(flag.key, localText)}
    />
  );
}
```
> La clase `styles.textInput` ya existe (misma que `"csv"`). La diferencia semántica es que no se hace split por comas — es un string libre (ruta de archivo).

**E. `backend/.env.example` y `backend/harness_defaults.env`** — AÑADIR:
```
STACKY_CODEBASE_MEMORY_MCP_PROJECTS=
STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH=
```

**Tests PRIMERO (TDD):** `backend/tests/test_plan80_flags.py`:
1. `config.STACKY_CODEBASE_MEMORY_MCP_PROJECTS == ""` por default.
2. `config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH == ""` por default.
3. `codebase_memory_mcp_enabled("X")` → `False` con master OFF.
4. `codebase_memory_mcp_enabled("X")` → `True` con master ON + allowlist vacía (parchear `config`).
5. `codebase_memory_mcp_enabled("X")` → `True` solo si "X" ∈ allowlist; `False` para "Y" no listado.
6. `FLAG_REGISTRY` contiene `STACKY_CODEBASE_MEMORY_MCP_PROJECTS` con `env_only=False`, `type="csv"`, `pair="STACKY_CODEBASE_MEMORY_MCP_ENABLED"`, key en `_CATEGORY_KEYS["avanzado"]`.
7. `FLAG_REGISTRY` contiene `STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH` con `env_only=False`, `type="str"`, key en `_CATEGORY_KEYS["avanzado"]`.
8. **Fix `_type_zero`:** `_type_zero("str") == ""` (string vacío, NO entero 0).
9. **Fix `_type_zero` regresión:** `_type_zero("bool") == False`, `_type_zero("csv") == ""`, `_type_zero("float") == 0.0`, `_type_zero("int") == 0` — no hay regresión en los tipos existentes.
10. **Fix `_cast` para `"str"` (BUG BLOQUEANTE):** `_cast(spec_str, "C:\\tools\\cbm.exe") == "C:\\tools\\cbm.exe"` (no lanza). `spec_str` es un `FlagSpec` con `type="str"`.
11. **Fix `_cast` para `"str"` con None:** `_cast(spec_str, None) == ""` (devuelve string vacío).
12. **Fix `_cast` regresión:** `_cast(spec_str_migrator, "free_degrade") == "free_degrade"` donde `spec_str_migrator` es el spec de `STACKY_MIGRATOR_EPIC_POLICY` — confirma que el bug latente del Plan 74 también queda resuelto.

**Comando:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan80_flags.py -q`

**Criterio binario:** los 12 casos pasan.

**Flag:** `STACKY_CODEBASE_MEMORY_MCP_ENABLED` (master, del 76) + `STACKY_CODEBASE_MEMORY_MCP_PROJECTS` + `STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH`. Defaults OFF/vacío.

**Impacto por runtime:** ninguno (solo flags y UI). **Trabajo del operador:** ninguno (defaults seguros).

---

### F1 — Función pura: construir el dict `mcpServers` con 1 o 2 servers (sin tocar disco)

**Objetivo (1 frase):** extraer la construcción del dict `mcpServers` de `maybe_write_mcp_config` a una función pura que devuelva 1 server (`"stacky"`) o 2 (`+ "codebase-memory-mcp"`) según flags, manteniendo byte-identidad con flag OFF.

**Valor:** testeable sin disco ni red; garantiza que con flag OFF el shape es idéntico a hoy; aísla el riesgo del 2º server.

**Archivos exactos:**
- `backend/services/codebase_memory_mcp_wiring.py` (NUEVO, helpers PUROS):
```python
"""Plan 80 — Helpers puros para inyectar el server MCP externo codebase-memory-mcp.
PUROS: no tocan disco, no abren red, no spawnean binarios. Solo arman dicts/strings.
Contrato de clave (Plan 76, C4/C10): el server externo usa la clave 'codebase-memory-mcp',
NUNCA 'stacky' (esa es del MCP interno).
"""
from __future__ import annotations

EXTERNAL_MCP_KEY = "codebase-memory-mcp"  # contrato Plan 76 — NO cambiar a "stacky"

def build_external_server_entry(binary_path: str) -> dict | None:
    """Devuelve la entrada de mcpServers para el server externo, o None si no procede.
    None si binary_path está vacío (degradación segura: no se inyecta nada).
    None si binary_path contiene '..' (path traversal — seguridad; C-RES-1 adición v3).
    PURA: no verifica que el archivo exista (eso lo decide el operador); solo arma el dict."""
    if not binary_path or not binary_path.strip():
        return None
    # Seguridad (C-RES-1 [ADICIÓN v3]): rechazar paths con traversal.
    # El operador escribe binary_path desde la UI; si contiene ".." podría apuntar fuera de la ruta esperada.
    import pathlib
    try:
        parts = pathlib.PurePath(binary_path.strip()).parts
    except Exception:
        return None
    if ".." in parts:
        return None
    return {"command": binary_path.strip(), "args": []}

def merge_external_server(
    base_servers: dict, *, external_enabled: bool, binary_path: str
) -> dict:
    """Devuelve un NUEVO dict de servers, añadiendo 'codebase-memory-mcp' si corresponde.
    - external_enabled False -> devuelve base_servers SIN cambios (byte-idéntico).
    - external_enabled True pero binary_path vacío -> base_servers SIN cambios (degradación segura).
    - external_enabled True + binary_path -> base_servers + {'codebase-memory-mcp': {...}}.
    NUNCA pisa la clave 'stacky'. NUNCA muta base_servers (copia)."""
    if not external_enabled:
        return dict(base_servers)
    entry = build_external_server_entry(binary_path)
    if entry is None:
        return dict(base_servers)
    merged = dict(base_servers)
    merged[EXTERNAL_MCP_KEY] = entry
    return merged
```

**Tests PRIMERO (TDD):** `backend/tests/test_plan80_wiring_pure.py`:
1. `build_external_server_entry("")` → `None`.
2. `build_external_server_entry("   ")` → `None`.
3. `build_external_server_entry("C:\\tools\\cbm.exe")` → `{"command": "C:\\tools\\cbm.exe", "args": []}`.
3b. **[ADICIÓN v3 — path traversal]** `build_external_server_entry("C:\\tools\\..\\cbm.exe")` → `None` (rechazado; el path contiene `".."`). `build_external_server_entry("..\\cbm.exe")` → `None`. Esto verifica el guard de seguridad para paths relativos escritos por el operador en la UI.
4. `merge_external_server({"stacky": {...}}, external_enabled=False, binary_path="C:\\x.exe")` → idéntico al input (NO agrega clave externa).
5. `merge_external_server({"stacky": {...}}, external_enabled=True, binary_path="")` → idéntico al input (degradación: sin ruta no inyecta).
6. `merge_external_server({"stacky": {...}}, external_enabled=True, binary_path="C:\\x.exe")` → tiene `"stacky"` Y `"codebase-memory-mcp"`; `"stacky"` intacto.
7. **No-mutación:** pasar un dict `base`, llamar `merge_external_server(base, external_enabled=True, binary_path="C:\\x.exe")`, afirmar que `base` NO cambió (sigue con 1 sola clave).
8. **Pureza (sin red):** `monkeypatch.setattr("socket.socket", _raise)`; afirmar que las 3 funciones retornan normal.
9. La constante `EXTERNAL_MCP_KEY == "codebase-memory-mcp"` (contrato 76) y `!= "stacky"`.

**Comando:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan80_wiring_pure.py -q`

**Criterio binario:** los 9 casos pasan; función pura demostrada (caso 8) y no-mutante (caso 7).

**Flag:** n/a (funciones puras; el gate se aplica en F2). **Impacto por runtime:** ninguno todavía. **Trabajo del operador:** ninguno.

---

### F2 — Cablear el merge en el writer real de Claude CLI (`maybe_write_mcp_config`)

**Objetivo (1 frase):** que `maybe_write_mcp_config` escriba el `mcp-config.json` con el 2º server cuando el flag externo está ON y hay binario, sin tumbar el server `"stacky"` y siendo byte-idéntico con flag externo OFF.

**Valor:** Claude CLI (runtime primario) consume realmente el MCP externo. Es el corazón del plan.

**Archivos exactos:**
- `backend/services/stacky_mcp.py` — REFACTOR de `maybe_write_mcp_config` (`:22-76`). Cambios precisos:
  1. Extraer la construcción del bloque interno a una función local privada `_build_internal_server_block` (ver §Extracción de bloque interno abajo) que devuelve `dict` con la entrada `"stacky"` completa.
  2. Construir `base_servers = {"stacky": _build_internal_server_block(...)}` si el interno está ON, o `base_servers = {}` si está OFF.
  3. Aplicar `merge_external_server(base_servers, external_enabled=cli_feature_flags.codebase_memory_mcp_enabled(project_name), binary_path=config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH)`.
  4. Si el dict resultante de servers está **vacío** → devolver `None` (igual que hoy cuando todo está OFF; no se escribe config ni se pasa `--mcp-config`).
  5. Escribir `{"mcpServers": <servers_merged>}`.

  **§Extracción de bloque interno (C-RES-1 fix):** AÑADIR en `stacky_mcp.py` la función privada (antes de `maybe_write_mcp_config`) con la firma y el cuerpo EXACTOS derivados del código existente de `:42-70`:
  ```python
  def _build_internal_server_block(
      *,
      execution_id: int,
      port: int,
      project_name: str | None,
      ticket_id: int | None,
      ado_id: int | None,
      agent_type: str | None,
  ) -> dict:
      """Construye el dict de la entrada 'stacky' para mcpServers.
      Igual que el bloque inline anterior (stacky_mcp.py:42-70), extraído para
      permitir construir base_servers condicionalmente (Plan 80 F2)."""
      import os, sys
      from pathlib import Path
      backend_dir = Path(__file__).resolve().parents[1]
      server_path = backend_dir / "services" / "stacky_mcp_server.py"
      env: dict[str, str] = {
          "STACKY_MCP_EXECUTION_ID": str(execution_id),
          "STACKY_MCP_PORT": str(port),
          "DATABASE_URL": os.getenv("DATABASE_URL", ""),
          "PYTHONPATH": str(backend_dir),
      }
      if project_name:
          env["STACKY_MCP_PROJECT"] = project_name
      if ticket_id is not None:
          env["STACKY_MCP_TICKET_ID"] = str(ticket_id)
      if ado_id is not None:
          env["STACKY_MCP_ADO_ID"] = str(ado_id)
      if agent_type:
          env["STACKY_MCP_AGENT_TYPE"] = agent_type
      env = {k: v for k, v in env.items() if v != ""}
      return {
          "command": sys.executable,
          "args": [str(server_path)],
          "env": env,
      }
  ```
  > Esta extracción es refactoring 1:1 — **no cambia el comportamiento** cuando solo está el interno ON (byte-idéntico a hoy).

  Pseudocódigo del nuevo `maybe_write_mcp_config` (reemplaza `:22-76` completo):
  ```python
  def maybe_write_mcp_config(run_dir, *, project_name, ticket_id, ado_id, execution_id, port, agent_type=None):
      from services import cli_feature_flags
      from config import config
      from services.codebase_memory_mcp_wiring import merge_external_server

      internal_on = cli_feature_flags.mcp_enabled(project_name)
      external_on = cli_feature_flags.codebase_memory_mcp_enabled(project_name)
      base_servers = (
          {"stacky": _build_internal_server_block(
              execution_id=execution_id, port=port, project_name=project_name,
              ticket_id=ticket_id, ado_id=ado_id, agent_type=agent_type,
          )}
          if internal_on else {}
      )
      servers = merge_external_server(
          base_servers,
          external_enabled=external_on,
          binary_path=config.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH,
      )
      if not servers:
          return None  # nada que inyectar (byte-idéntico a hoy cuando todo OFF)
      config_path = run_dir / "mcp-config.json"
      config_path.write_text(
          json.dumps({"mcpServers": servers}, ensure_ascii=False, indent=2),
          encoding="utf-8",
      )
      return config_path
  ```
  **Backward-compat:** si `external_on` es False (default), `servers == {"stacky": {...}}` cuando interno ON, o `{}` → `None` cuando interno OFF → **byte-idéntico al comportamiento actual**.

  **Aditividad y no-fallo:** el server externo NUNCA pisa `"stacky"` (garantizado por F1 caso 6). Las funciones puras de F1 nunca lanzan (no tocan disco ni red). El único punto de fallo del writer es `write_text` (igual que hoy). El catch monolítico de `claude_code_cli_runner.py:605-607` es suficiente: si `write_text` lanza, degrada todo el MCP (comportamiento existente sin cambio). **El externo NO puede tumbar al interno en ausencia de fallo de disco.**

- `backend/services/claude_code_cli_runner.py` — el caller (`:595`) y el builder de args (`:1828-1829`) **NO cambian** (siguen recibiendo un `Path | None` y extendiendo `--mcp-config`).

**Tests PRIMERO (TDD):** `backend/tests/test_plan80_writer.py` (usa `tmp_path` para `run_dir`; parchea `config` y `cli_feature_flags`):
1. **Todo OFF (default):** interno OFF + externo OFF → `maybe_write_mcp_config(...)` devuelve `None`, no escribe archivo. (Byte-idéntico a hoy.)
2. **Solo interno ON (comportamiento histórico):** interno ON + externo OFF → escribe config con `mcpServers` que tiene SOLO `"stacky"`. Afirmar `json.loads(resultado) == json.loads(esperado)` donde `esperado` es el dict con solo `"stacky"` (comparación estructural, NO string).
3. **Interno ON + externo ON + binary_path seteado:** `mcpServers` tiene `"stacky"` Y `"codebase-memory-mcp"`; este último con `command == binary_path`.
4. **Interno OFF + externo ON + binary_path seteado:** `mcpServers` tiene SOLO `"codebase-memory-mcp"` (sin `"stacky"`); el archivo se escribe (no None).
5. **Externo ON pero binary_path vacío:** se comporta como externo OFF (degradación segura): si interno ON → solo `"stacky"`; si interno OFF → `None`.
6. **Externo ON pero proyecto NO en allowlist:** `codebase_memory_mcp_enabled` devuelve False → no se inyecta el externo.
7. **El server `"stacky"` conserva su `env` y `command`** (no lo rompe el merge): parchear interno ON + externo ON, leer el JSON escrito, afirmar que `mcpServers["stacky"]["command"]` y `["env"]` siguen presentes.
8. **Catch monolítico suficiente:** parchear `config_path.write_text` para que lance `OSError`; afirmar que `maybe_write_mcp_config` **lanza** (el runner ya lo captura en `:605-607`). Esto verifica que el writer no traga el error y que el runner tiene responsabilidad del catch — no cambia el comportamiento, solo documenta el contrato.
9. **[ADICIÓN ARQUITECTO] Overhead de serialización:** medir el tiempo de ejecución de `maybe_write_mcp_config` con 2 servers vs 1 server usando `time.perf_counter()`; afirmar que la diferencia es < 5 ms (las funciones puras no tienen overhead perceptible). Sin red, sin disco mock — solo la serialización JSON.

**Comando:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan80_writer.py -q`

**Criterio binario:** los 9 casos pasan; con externo OFF el JSON es el histórico (casos 1 y 2); con externo ON aparece la 2ª clave sin romper la 1ª (casos 3, 7); el overhead es < 5 ms (caso 9).

**Flag:** `STACKY_CODEBASE_MEMORY_MCP_ENABLED` + `_PROJECTS` + `_BINARY_PATH`. Default OFF/vacío.

**Impacto por runtime:**
- **Claude Code CLI:** con flag ON + binario, inyecta el 2º server automáticamente. Con OFF, idéntico a hoy.
- **Codex:** sin cambios aún (F3). **Copilot:** sin cambios (no aplica).

**Trabajo del operador:** ninguno con flag OFF; si activa, debe haber instalado el binario y seteado `STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH` (la guía del 76 + F4 lo explican).

---

### F3 — Codex CLI: Opción 3b (guía manual) implementada; plan 80b documenta Opción 3a

**Objetivo (1 frase):** cerrar la paridad honesta de Codex: emitir log informativo cuando el flag externo está ON (sin auto-inyección) y documentar por qué Opción 3a es un plan independiente (80b).

**Valor:** el operador sabe exactamente qué runtime auto-inyecta y cuál no; el modelo menor no tiene ambigüedad.

**Decisión fija (no ambigua):** F3 implementa **SOLO 3b (guía manual)**. La Opción 3a (wiring automático de Codex) NO se implementa en este plan por las siguientes razones verificadas:
1. `codex_cli_runner.py:336` no tiene rama MCP hoy — agregarlo es nuevo wiring en un runner que nunca lo tuvo, con riesgo de regresión no nulo.
2. No se ha verificado con evidencia directa que Codex CLI acepte `[mcp_servers]` en `config.toml` pasado por-run (no hay documentación oficial en el contexto disponible). Sin esa evidencia, no se puede diseñar el wiring.
3. El riesgo de un run de Codex roto por un config TOML inválido es mayor que el beneficio de la auto-inyección en el corto plazo.

La Opción 3a queda documentada en `docs/_evals/codebase-memory-mcp/integration-3-runtimes.md` como plan 80b (fase independiente que el operador puede pedir si verifica soporte TOML de Codex).

> **Nota CRÍTICA — Indexación previa (C-RES-2):** el server externo `{"command": binary_path, "args": []}` arranca **sin índice**. Las tools `search_graph`, `get_code_snippet`, `trace_call_path` devuelven vacío si no se corrió `index_repository` primero. El operador debe ejecutar **una sola vez** (y luego cuando el codebase cambie significativamente):
> ```
> codebase-memory-mcp index_repository --path "N:\GIT\RS\STACKY\Stacky"
> ```
> O configurar indexación automática: `codebase-memory-mcp config set auto_index true` (re-indexa cambios en background via git polling). **Sin este paso, activar el flag produce un MCP funcional pero con tools que devuelven vacío — el agente degrada silenciosamente.** Esta nota debe figurar en el apéndice `integration-3-runtimes.md` y en `poc-metrics.md`.

**Archivos exactos:**
- `backend/services/codex_cli_runner.py` — AÑADIR, en la zona de construcción del prompt de reglas donde ya se lee `mcp_enabled`, **1 línea de log informativo** (no bloqueante, no cambia el run):
  ```python
  # Plan 80 — MCP externo: Codex no auto-inyecta. Ver plan 80b y guía install-codex.md.
  if cli_feature_flags.codebase_memory_mcp_enabled(project_name):
      log("info", "Codex: MCP externo activado (flag ON) pero requiere config manual. Ver install-codex.md (Plan 76/80).")
  ```
  > Buscar la zona cerca de `:1316` donde se lee `mcp_enabled`. Añadir el bloque DESPUÉS de ese check, en el mismo scope. NO bloquea el run.

- `docs/_evals/codebase-memory-mcp/integration-3-runtimes.md` (CREAR o AÑADIR si ya existe) — APÉNDICE Plan 80:
  ```
  ## Plan 80: Estado de auto-inyección por runtime

  | Runtime         | Auto-inyección | Ruta soportada | Razón |
  |---|---|---|---|
  | Claude Code CLI | SÍ (F2)        | `--mcp-config` automático | `claude_code_cli_runner.py:595` ya escribe el config |
  | Codex CLI       | NO (3b)        | Guía manual `install-codex.md` | Sin rama MCP en `codex_cli_runner.py`; soporte TOML sin verificar |
  | Copilot Pro     | NO (F4)        | Guía manual `install-copilot-pro.md` | Bridge HTTP; no spawnea CLI |

  ### Plan 80b (futuro): Opción 3a para Codex
  Prerequisito: verificar que Codex CLI acepta `[mcp_servers.X] command="..." args=[]` en un `config.toml` pasado por-run (o flag `--config`).
  Si se verifica: crear `build_codex_mcp_toml_block(binary_path) -> str | None` en `codebase_memory_mcp_wiring.py` y cablear en `codex_cli_runner.py` análogo a F2 de este plan, con su propio catch que no rompa el run.
  ```

**Tests PRIMERO (TDD):** `backend/tests/test_plan80_codex.py`:
1. Con flag externo OFF, `codebase_memory_mcp_enabled(project_name)` es False → el bloque de log NO se ejecuta (parchear `log` y afirmar 0 llamadas con mensaje "MCP externo").
2. Con flag externo ON, el log informativo se emite (parchear `log` y afirmar llamada con mensaje que contiene "MCP externo" y "manual").
3. **Byte-identidad:** con flag OFF, el `codex_cli_runner` produce el mismo output de reglas que hoy (sin texto extra de MCP externo). Afirmar que el string de reglas construido no contiene "codebase-memory-mcp".
4. `build_installation_guide("codex")` (del 76) retorna guía no vacía (la ruta soportada sigue existiendo).

**Comando:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan80_codex.py -q`

**Criterio binario:** los 4 casos pasan; opción elegida (3b) registrada en doc; con flag OFF Codex es byte-idéntico a hoy.

**Flag:** mismo trío. **Impacto por runtime:** Codex = manual documentado; Claude y Copilot sin cambios. **Trabajo del operador:** ninguno con OFF; si ON y Codex, sigue la guía manual del 76.

---

### F4 — Copilot Pro: confirmar "no aplica auto-inyección" + guía manual robusta (degradación controlada)

**Objetivo (1 frase):** documentar de forma testeable que Copilot Pro NO recibe inyección automática (el bridge HTTP no spawnea CLI con MCP) y que su ruta soportada es la guía manual VS Code del 76.

**Valor:** paridad HONESTA: el operador sabe que en Copilot el MCP se configura una vez en VS Code y no por-run.

**Archivos exactos:**
- `docs/_evals/codebase-memory-mcp/integration-3-runtimes.md` — ya escrito en F3 (tabla + apéndice). No duplicar.
- No se toca `copilot_bridge.py` (no aplica). No se promete auto-inyección.

**Tests PRIMERO (TDD):** `backend/tests/test_plan80_copilot.py`:
1. `build_installation_guide("copilot_pro")` (del 76; string exacto `"copilot_pro"` igual que en `codebase_memory_mcp.py:31`) retorna guía no vacía que menciona la clave `"codebase-memory-mcp"` (el contrato del 76) — confirma que la guía es coherente con la clave namespaced.
2. **Centinela anti-promesa:** leer `copilot_bridge.py` como texto y afirmar que `"codebase_memory_mcp_wiring"` NO está en el contenido Y `"mcp-config"` NO está en el contenido — garantiza que nadie agregó auto-inyección frágil a Copilot por error.

**Comando:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan80_copilot.py -q`

**Criterio binario:** ambos casos pasan; apéndice escrito (en F3).

**Flag:** n/a (Copilot es manual siempre). **Impacto por runtime:** Copilot sin cambios de runtime. **Trabajo del operador:** si quiere MCP en Copilot, configura VS Code una vez (guía 76). Con OFF, nada.

---

### F5 — Medición ESTIMADA del ahorro de tokens (PoC manual, no telemetría automática)

**Objetivo (1 frase):** estimar y registrar, de forma reproducible, cuántos tokens ahorra usar el MCP externo vs leer archivos enteros, exponiéndolo en un endpoint para que el KPI sea medible y no prometido a ciegas.

**Valor:** el operador ve el shape correcto del endpoint (con `samples=0` honestamente declarado); si corre la PoC, ve `delta_pct` real con evidencia.

**Enfoque (honesto y barato):** NO se instrumenta el binario externo (es una caja negra). Se mide el **proxy controlado** que ya pidió el 76 en `poc-metrics.md`, ahora automatizado como **función pura + endpoint**:
- Para una query estructural (ej. "definición de símbolo X"), el baseline (sin MCP) implica leer el/los archivo(s) candidato(s) enteros → `tokens_baseline ≈ chars_archivos / 4` (heurística de tokens estándar, declarada).
- Con MCP, la respuesta es el snippet/grafo → `tokens_mcp ≈ chars_respuesta_mcp / 4`.
- `delta = tokens_baseline - tokens_mcp`, `delta_pct = delta / tokens_baseline`.

**Honestidad sobre el store:** no existe un sink genérico reutilizable en el runtime (ni `output_watcher` ni `harness_health` exponen escritura de métricas). Por lo tanto `aggregate_savings()` devuelve `{"samples": 0, "delta_pct": null, "note": "Poblar con PoC de queries.md (Plan 76)."}` hasta que el operador corra la PoC. La card F6 muestra "sin datos aún" en vez de `0%`. Esto es honesto y no confunde al operador.

**Archivos exactos:**
- `backend/services/codebase_memory_mcp_wiring.py` — AÑADIR función pura:
```python
def estimate_query_savings(chars_baseline: int, chars_mcp_response: int) -> dict:
    """Plan 80 — Estima ahorro de tokens de una query estructural (heurística ~4 chars/token).
    PURA. Devuelve {tokens_baseline, tokens_mcp, delta, delta_pct}.
    delta_pct = 0.0 si chars_baseline == 0 (evita div/0).
    delta y delta_pct pueden ser negativos (si el MCP devuelve más chars que el baseline)."""
    tb = max(0, chars_baseline) // 4
    tm = max(0, chars_mcp_response) // 4
    delta = tb - tm
    pct = (delta / tb) if tb > 0 else 0.0
    return {"tokens_baseline": tb, "tokens_mcp": tm, "delta": delta, "delta_pct": round(pct, 4)}

def aggregate_savings() -> dict:
    """Plan 80 — Retorna métricas agregadas de ahorro estimado.
    Hasta que el operador pobla la PoC (queries.md del 76), retorna samples=0 y delta_pct=null.
    PURA. No abre red ni disco."""
    return {
        "samples": 0,
        "delta_pct": None,
        "note": "Poblar con PoC de queries.md (Plan 76 docs/_evals/codebase-memory-mcp/).",
    }
```

- `backend/api/codebase_memory_mcp.py` — EXTENDER el blueprint del 76 con una ruta nueva (mismo `bp`, NO nuevo blueprint, NO `/api/api`):
```python
@bp.get("/savings")
def savings_route():
    """GET /api/codebase-memory-mcp/savings — métricas agregadas de ahorro estimado.
    Siempre 200. Retorna samples=0 hasta que el operador corra la PoC."""
    from services.codebase_memory_mcp_wiring import aggregate_savings
    return jsonify(aggregate_savings())
```

- `docs/_evals/codebase-memory-mcp/poc-metrics.md` — completar con el protocolo automatizado: comando exacto para correr las queries congeladas de `queries.md` (del 76) sobre el repo de Stacky y volcar `estimate_query_savings` por query. El commit SHA y los números van acá (reproducible).

**Tests PRIMERO (TDD):** `backend/tests/test_plan80_savings.py`:
1. `estimate_query_savings(0, 0)` → `{"tokens_baseline":0,"tokens_mcp":0,"delta":0,"delta_pct":0.0}` (sin div/0).
2. `estimate_query_savings(4000, 400)` → `tokens_baseline=1000, tokens_mcp=100, delta=900, delta_pct=0.9`.
3. `estimate_query_savings(400, 4000)` (MCP peor) → `delta` negativo, `delta_pct` negativo (no se oculta el caso malo).
4. Negativos clamped: `estimate_query_savings(-10, -10)` → `0,0,0,0.0`.
5. `aggregate_savings()` retorna `{"samples": 0, "delta_pct": None, "note": ...}` — `delta_pct` es `None` (no `0.0`), `samples == 0`.
6. `GET /api/codebase-memory-mcp/savings` → 200 con `samples == 0` y `delta_pct is None` (con flag OFF también 200; reporta estado honesto).
7. Pureza (sin red): monkeypatch `socket.socket`; `estimate_query_savings` y `aggregate_savings` retornan normal.

**Comando:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan80_savings.py -q`

**Criterio binario:** los 7 casos pasan; el endpoint `/api/codebase-memory-mcp/savings` registrado bajo `/api` (sin doble prefijo) y siempre 200.

**Flag:** la medición no requiere el flag ON (es estimación pura); el endpoint existe siempre (read-only). **Impacto por runtime:** ninguno (telemetría). **Trabajo del operador:** ninguno; opcional correr la PoC para poblar números.

---

### F6 — UI: extender la card del 76 con estado de wiring + ahorro (read-only, sin toggle nuevo) + no-regresión del shape del 76

**Objetivo (1 frase):** que el operador vea en la UI si el wiring está activo, la ruta del binario configurada, y el estado de ahorro — sin agregar toggles (los da el panel de flags) — y que el shape del `/status` del 76 no se rompa.

**Valor:** visibilidad operativa; el operador entiende el estado real sin leer logs.

**Archivos exactos:**
- `backend/api/codebase_memory_mcp.py` — EXTENDER `status_route()` para incluir `wiring` en el JSON (NO cambiar las claves existentes, solo agregar):
```python
# En status_route(), antes del return:
from services.codebase_memory_mcp_wiring import merge_external_server  # ya importado si F2 también lo usa
from config import config as cfg
binary_path_set = bool(cfg.STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH.strip())
injects_external = st.get("enabled", False) and binary_path_set
wiring = {"binary_path_set": binary_path_set, "injects_external": injects_external}
return jsonify({**st, "guides": guides, "wiring": wiring})
```
> No se expone la ruta completa del binario (solo `binary_path_set: bool`). `injects_external` es la conjunción del flag master + path configurado.

- `frontend/src/components/CodebaseMemoryMcpCard.tsx` — si el 76 la creó, EXTENDER; si quedó como opcional no creada, CREAR (read-only). Muestra: `enabled` (del status), `binary_path_set` (sí/no), `injects_external` (sí/no), `savings.samples` y `savings.delta_pct` (de `/savings` — mostrar "sin datos aún" si `delta_pct is null`), y un link a la guía. **Sin toggle** (el toggle del flag lo renderiza `HarnessFlagsPanel`).

**Tests PRIMERO (TDD):**
- `backend/tests/test_plan80_status_shape.py` (NUEVO — no-regresión del shape del 76):
  1. `GET /api/codebase-memory-mcp/status` → 200 y el JSON contiene las claves del 76: `"enabled"`, `"installed_hint"`, `"flag"`, `"external_repo"`, `"guides"` — todas presentes.
  2. El JSON contiene la clave nueva `"wiring"` con sub-claves `"binary_path_set"` (bool) e `"injects_external"` (bool).
  3. Con `STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH=""` (default), `wiring["binary_path_set"] == False` y `wiring["injects_external"] == False`.
  4. Con `STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH="C:\\x.exe"` y flag master ON, `wiring["binary_path_set"] == True` y `wiring["injects_external"] == True`.

- Frontend: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx tsc --noEmit` → 0 errores.

**Comando:** backend `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan80_status_shape.py -q`; frontend `npx tsc --noEmit`.

**Criterio binario:** `/status` mantiene las 5 claves del 76 + agrega `wiring`; `tsc` 0 errores; los 4 casos de status shape pasan.

**Flag:** n/a (UI read-only). **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F7 — Ratchet byte-idéntico + registro de tests (cierre y blindaje)

**Objetivo (1 frase):** garantizar que con flag externo OFF el sistema es byte-idéntico (incluido el `mcp-config.json`) y registrar todos los tests nuevos en el ratchet (Plan 49).

**Valor:** evita falsos verdes y regresiones; cumple el riel de blindaje del arnés.

**Archivos exactos:**
- `backend/tests/test_plan80_ratchet_byteidentical.py` (NUEVO):
  1. **Byte-identidad del writer (`maybe_write_mcp_config`):** con `STACKY_CODEBASE_MEMORY_MCP_ENABLED` OFF (default) e interno ON (parchear `cli_feature_flags.mcp_enabled → True`), llamar `maybe_write_mcp_config(tmp_path, ...)`, leer el archivo escrito y afirmar: `json.loads(content) == {"mcpServers": {"stacky": {...}}}` Y `"codebase-memory-mcp" not in content`. (Token específico sobre el ARCHIVO del writer, NO sobre `build_agent_env` — `build_agent_env` arma el env del proceso, no el mcp-config.json; no mezclar. Lección C10 del 76.)
  2. **Todo OFF:** interno OFF + externo OFF → `maybe_write_mcp_config` devuelve `None` (igual que hoy).
  3. **Anti-promesa Copilot:** re-afirmar (o referenciar) el centinela de F4.
  4. **[C-RES-4] Ratchet .ps1 en sync:** leer `scripts/run_harness_tests.ps1` como texto y afirmar que los 9 archivos `test_plan80_*.py` también están mencionados en él. Sin este caso, la advertencia "sh + ps1" del plan 80 es cosmética: el `.ps1` puede quedar desync y el operador en Windows no tiene cobertura.

> **Nota para el modelo menor:** F7 case 1 importa `maybe_write_mcp_config` de `services.stacky_mcp` — NO `build_agent_env` de `services.agent_env`. El wiring MCP va por el FILE `mcp-config.json` + flag `--mcp-config` (`claude_code_cli_runner.py:1828`), no por variables de entorno del proceso. Testear `build_agent_env` no cubriría este wiring.

- Registrar en `HARNESS_TEST_FILES` (sh + ps1, lección `stacky-ratchet-obliga-registrar-tests`): `test_plan80_flags.py`, `test_plan80_wiring_pure.py`, `test_plan80_writer.py`, `test_plan80_codex.py`, `test_plan80_copilot.py`, `test_plan80_savings.py`, `test_plan80_status_shape.py`, `test_plan80_ratchet_byteidentical.py`, `test_plan80_routes_registered.py` (9 archivos total).

- **Centinela de rutas** `backend/tests/test_plan80_routes_registered.py` (réplica del patrón de `test_plan76_routes_registered.py`):
  1. `"/api/codebase-memory-mcp/savings" in rules` (la ruta nueva de F5).
  2. `"/api/api/codebase-memory-mcp/savings" not in rules` (sin doble prefijo).
  3. `"/api/codebase-memory-mcp/status" in rules` (la del 76 sigue viva — redundante con el 76 pero documenta co-existencia; si `test_plan76_routes_registered.py` sigue verde, este caso 3 puede omitirse en futuras revisiones).

**Tests PRIMERO (TDD):** los archivos de arriba.

**Comando:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan80_ratchet_byteidentical.py tests/test_plan80_routes_registered.py tests/conformance/test_harness_ratchet.py -q`

**Criterio binario:** byte-identidad con flag OFF demostrada (token `"codebase-memory-mcp"` ausente, no genérico `mcpServers`); centinela de rutas verde; ratchet verde con los 9 tests `test_plan80_*` registrados.

**Flag:** n/a. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

1. **R1 — El 2º server frágil tumba el MCP interno "stacky".** Mitigación: F1 garantiza aditividad (caso 6/7) y pureza (caso 8 — no lanza); F2 analiza que el catch monolítico `:605-607` es suficiente porque las funciones puras no pueden fallar (solo `write_text` puede fallar, que ya degradaba todo el MCP); F2 caso 8 verifica el contrato del catch. **El externo NO puede tumbar al interno salvo fallo de disco**, que ya degradaba todo el MCP.
2. **R2 — Falso-fallo de byte-identidad por el substring `mcpServers`.** Mitigación (lección C10 del 76): el ratchet F7 aserta el token específico `"codebase-memory-mcp"`, NUNCA el genérico `mcpServers` (que ya existe del interno).
3. **R3 — Doble-prefijo `/api/api`.** Mitigación (lección 72/76): F5 extiende el `bp` existente del 76 (`url_prefix="/codebase-memory-mcp"`, ya registrado en `api_bp`), NO crea blueprint nuevo ni toca `app.py`; centinela F7 lo verifica.
4. **R4 — Prometer paridad de inyección automática que no existe.** Mitigación: F3/F4 son explícitos — solo Claude auto-inyecta; Codex siempre 3b (manual) en este plan; Copilot siempre manual. Centinela anti-promesa F4.
5. **R5 — Codex: introducir wiring frágil.** Mitigación: F3 implementa 3b (solo log informativo, 0 riesgo de regresión). La opción 3a es plan 80b independiente.
6. **R6 — Métrica de ahorro falseada/optimista.** Mitigación: `aggregate_savings()` retorna `delta_pct: null` (no 0.0), card muestra "sin datos aún"; F5 caso 3 reporta `delta` negativo si el MCP es peor; la heurística (4 chars/token) es declarada.
7. **R7 — Egress/exfiltración del codebase por el binario externo.** Mitigación: el README declara 100% local; la PoC sandbox deny-egress (D9 del 76) sigue siendo el gate del operador. Este plan NO abre red desde el backend. El flag default OFF.
8. **R8 — `type="str"` bug en `_type_zero` y frontend.** RESUELTO en F0: `_type_zero("str")→""`, rama `"str"` en `HarnessFlagsPanel.tsx`. Test F0 caso 8/9 lo verifica.
9. **R9 — Cambiar el contrato del gate de `maybe_write_mcp_config` rompe runs existentes.** Mitigación: F2 casos 1/2 prueban byte-identidad con externo OFF; el nuevo guard solo devuelve `None` cuando AMBOS están OFF (= comportamiento histórico).
10. **R10 — El binario no está instalado pero el flag está ON.** Mitigación: sin `BINARY_PATH` el 2º server NO se inyecta (F1 caso 5); el agente sigue operando con grep/lectura (degradación natural); la card F6 muestra `binary_path_set: false`.

---

## 6. Fuera de scope

- **NO** empaquetar el binario del MCP en el deploy de Stacky (igual que el 76).
- **NO** indexar repos automáticamente desde el backend (la indexación inicial es responsabilidad del operador; ver Nota CRÍTICA en F3).
- **NO** instrumentar/parchear el binario externo (caja negra; la métrica es proxy declarado).
- **NO** auth/RBAC (mono-operador).
- **NO** auto-inyección en Copilot (bridge HTTP, no aplica).
- **NO** auto-inyección en Codex en este plan (es plan 80b; requiere verificación previa de soporte TOML).
- **NO** abrir red desde el backend de Stacky (las funciones de wiring son puras).
- **NO** re-decidir la scorecard D1-D9 del 76 (se cita y se refuerza con evidencia).
- **NO** store persistente de métricas de ahorro (evita migración de DB; `aggregate_savings` es PoC-driven).

---

## 7. Glosario

- **codebase-memory-mcp:** servidor MCP externo (binario C estático, stdio, 100% local) que indexa un codebase en un knowledge graph y responde queries estructurales (`get_code_snippet`, `search_graph`, `trace_call_path`, etc.). https://github.com/DeusData/codebase-memory-mcp
- **MCP / `mcpServers`:** Model Context Protocol; el `mcp-config.json` declara servers stdio como subprocesos. Stacky ya inyecta uno interno (`"stacky"`, `stacky_mcp.py:64`).
- **Clave namespaced:** contrato del Plan 76 — el server externo usa la clave `"codebase-memory-mcp"`, distinta de la interna `"stacky"`, para coexistir sin colisión.
- **Writer:** `maybe_write_mcp_config` (`stacky_mcp.py:22`) que escribe el `mcp-config.json` por-run; solo lo consume el runtime Claude CLI (`claude_code_cli_runner.py:1828`).
- **`FLAG_REGISTRY` / `FlagSpec`:** registro declarativo (`harness_flags.py`) que hace visible una flag en la UI sin tocar el frontend; `pair` asocia el `*_PROJECTS` al master toggle.
- **Patrón `project_enabled`:** `master_flag AND allowlist_csv` (`cli_feature_flags.py:25`); allowlist vacía = todos.
- **Ratchet:** mecanismo del Plan 49 que obliga a registrar todo test nuevo en `HARNESS_TEST_FILES`.
- **Paridad honesta:** cada runtime declara explícitamente si auto-inyecta o degrada a guía manual; no se promete soporte no verificado.
- **delta_pct (ahorro):** `(tokens_baseline - tokens_mcp) / tokens_baseline`, heurística ~4 chars/token, reproducible con `queries.md` del 76. `null` hasta que se corra la PoC.
- **Opciones 3a/3b (Codex):** 3b = guía manual (este plan); 3a = auto-inyección (plan 80b, requiere verificar soporte TOML de Codex).
- **`_type_zero`:** función interna de `harness_flags.py` que devuelve el valor "off/vacío" para cada tipo de flag. El bug `"str"→0` está corregido en F0.

---

## 8. Orden de implementación

1. **F0** — Par de flags + fix `_type_zero("str")` + rama frontend `"str"`. Tests `test_plan80_flags.py` (9 casos).
2. **F1** — Funciones puras de merge. Tests `test_plan80_wiring_pure.py` (9 casos).
3. **F2** — Refactor de `maybe_write_mcp_config` para 1/2 servers. Tests `test_plan80_writer.py` (9 casos, incl. overhead < 5 ms).
4. **F3** — Codex: 3b (log + doc). Tests `test_plan80_codex.py` (4 casos).
5. **F4** — Copilot: centinela anti-promesa. Tests `test_plan80_copilot.py` (2 casos).
6. **F5** — `estimate_query_savings` + `aggregate_savings` + endpoint `/savings`. Tests `test_plan80_savings.py` (7 casos).
7. **F6** — `/status` + `wiring` + card UI + no-regresión shape 76. Tests `test_plan80_status_shape.py` (4 casos) + `tsc` 0 errores.
8. **F7** — Ratchet byte-idéntico + centinela de rutas + registrar 9 tests en `HARNESS_TEST_FILES`.

Cada fase deja el sistema verde y backward-compatible (flag OFF = byte-idéntico).

---

## 9. Definición de Hecho (DoD global)

- [ ] **(a)** F0: flags en `config.py` + `FLAG_REGISTRY` (con `pair` en `*_PROJECTS`) + `.env.example` + `harness_defaults.env` + fix `_type_zero("str")→""` + fix `_cast` branch `"str"` (`:2004`, pre-requisito DURO) + rama `"str"` en `HarnessFlagsPanel.tsx`; `test_plan80_flags.py` verde (12 casos, incl. PUT de flag `"str"` no lanza).
- [ ] **(b)** F1: `codebase_memory_mcp_wiring.py` con funciones puras; `test_plan80_wiring_pure.py` verde (incl. no-mutación y pureza-sin-red).
- [ ] **(c)** F2: `maybe_write_mcp_config` inyecta 1 o 2 servers; byte-idéntico con externo OFF (comparación estructural); nunca pisa `"stacky"`; catch monolítico verificado; overhead < 5 ms; `test_plan80_writer.py` verde (9 casos).
- [ ] **(d)** F3: 3b implementada (log informativo en Codex); opción 3a documentada en apéndice como plan 80b; `test_plan80_codex.py` verde (4 casos); byte-idéntico con flag OFF.
- [ ] **(e)** F4: centinela anti-promesa Copilot; `test_plan80_copilot.py` verde (2 casos).
- [ ] **(f)** F5: `estimate_query_savings` + `aggregate_savings` (delta_pct null, samples 0) + `GET /api/codebase-memory-mcp/savings` (200, sin doble prefijo, delta_pct null honesto); `test_plan80_savings.py` verde (7 casos).
- [ ] **(g)** F6: `/status` mantiene las 5 claves del 76 + agrega `wiring`; card read-only (con "sin datos aún" si delta_pct null); `test_plan80_status_shape.py` verde (4 casos); `tsc` 0 errores.
- [ ] **(h)** F7: byte-identidad con flag OFF (token específico `codebase-memory-mcp`, no genérico); centinela `test_plan80_routes_registered.py` verde; 9 tests `test_plan80_*` registrados en `HARNESS_TEST_FILES` (sh **y** ps1 — caso 4 del ratchet verifica ambos); ratchet verde (4 casos).
- [ ] **(i)** Paridad declarada por runtime: Claude=auto (F2), Codex=manual-3b (F3), Copilot=manual (F4); sin promesas no verificadas.
- [ ] **(j)** Con flag OFF (default), los 3 runtimes operan exactamente como antes del plan (byte-idéntico).
- [ ] **(k)** Reconciliación con Plan 76 cumplida: reusan flag/blueprint/helpers/guías/clave namespaced del 76; no se duplica ni se reabre su decisión.

---

## 10. Notas para el modelo menor que implemente esto

- **Venv:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest <test> -q` (py3.13).
- **Blueprint:** NO crear blueprint nuevo. EXTENDER el `bp` del 76 en `api/codebase_memory_mcp.py`. Las rutas nuevas `/savings` quedan bajo `/api/codebase-memory-mcp/` automáticamente. NUNCA `app.py`, NUNCA `url_prefix="/api/..."`.
- **Clave MCP:** SIEMPRE `"codebase-memory-mcp"` (constante `EXTERNAL_MCP_KEY`). NUNCA `"stacky"` (es la interna).
- **Byte-identidad:** el assert mira el token `"codebase-memory-mcp"`, NUNCA `mcpServers` (ya existe del interno → falso-fallo, lección C10 del 76).
- **Flag config.py:** patrón `os.getenv("...","false").lower() in ("1","true","yes")` para bool; `os.getenv("...","")` para str/csv. NUNCA `: bool = False` ni `: str = ""`.
- **`_type_zero`:** en `harness_flags.py`, añadir `"str"` a la rama `("csv", "json")` para que devuelva `""`. Sin esta corrección, `declared_default` para un FlagSpec `type="str"` con `default=None` devuelve `0` (int), rompiendo la UI.
- **`_cast` (PRE-REQUISITO DURO, harness_flags.py:2004):** añadir `if spec.type == "str": return "" if raw is None else str(raw)` **antes del `raise ValueError` final** (`:2004`). Sin esto, cualquier intento de guardar un flag `type="str"` desde el frontend lanza `ValueError("Tipo desconocido")` y el PUT falla. Este es el fix más crítico de F0.
- **`HarnessFlagsPanel.tsx`:** añadir rama `if (flag.type === "str")` con `<input type="text">` idéntica a la de `"csv"` (misma clase `styles.textInput`). La diferencia es solo semántica (no hace split por comas).
- **Funciones puras:** `build_external_server_entry`, `merge_external_server`, `estimate_query_savings`, `aggregate_savings` — sin red, sin disco, sin binario; testear con strings/dicts y monkeypatch de `socket.socket`.
- **Indexación previa OBLIGATORIA antes de usar el MCP externo (C-RES-2):** el server externo arranca sin índice. Antes de activar el flag en producción, correr: `codebase-memory-mcp index_repository --path "<ruta-del-repo>"`. Sin esto, `search_graph` y `get_code_snippet` devuelven vacío. Documentar esto en el apéndice `integration-3-runtimes.md`.
- **`build_external_server_entry` rechaza paths con `..` (C-RES-1 adición v3):** el guard de path traversal devuelve `None` si el path contiene `".."`. Test F1 caso 3b verifica esto.
- **`_build_internal_server_block` (extracción F2):** función privada en `stacky_mcp.py`; debe aceptar exactamente los mismos parámetros que `maybe_write_mcp_config` y construir el dict `"stacky"` idéntico al bloque original (`:42-70`). No cambiar el shape ni las env vars.
- **Ratchet .ps1 en sync (C-RES-4):** F7 caso 4 verifica que `run_harness_tests.ps1` lista los 9 archivos. El Windows CI usa el `.ps1`, no el `.sh`.
- **No tumbar "stacky":** el merge es aditivo; el server interno se inyecta aunque el externo falle (binary_path vacío → externo no se inyecta, interno sí). Las funciones puras de F1 nunca lanzan.
- **Codex:** implementar SOLO 3b (log informativo). NO cablear auto-inyección. El plan 80b es el que haría 3a si el operador lo pide.
- **Copilot:** NO agregar auto-inyección. Es manual por diseño (bridge HTTP). Verificar centinela F4 caso 2.
- **`aggregate_savings()`:** retorna `delta_pct: None` (no `0.0`). La card muestra "sin datos aún". El test F5 caso 5 verifica `delta_pct is None`.
- **`pair` en FlagSpec:** `STACKY_CODEBASE_MEMORY_MCP_PROJECTS` debe tener `pair="STACKY_CODEBASE_MEMORY_MCP_ENABLED"` para que la UI lo renderice junto al master toggle. Sin `pair`, el `*_PROJECTS` queda suelto en la UI.
- **Cada commit deja el sistema verde y backward-compatible.**
- **Si una fase revela un GAP no listado**, detener y actualizar este doc antes de seguir.
- **No empaquetar el binario del MCP** (igual que el 76).
