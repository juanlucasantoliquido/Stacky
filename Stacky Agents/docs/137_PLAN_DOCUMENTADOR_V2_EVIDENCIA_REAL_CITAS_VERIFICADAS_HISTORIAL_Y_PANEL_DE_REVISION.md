# Plan 137 — Documentador v2: evidencia real de código, citas [V] verificadas, historial persistente y panel de revisión

**Versión:** v1
**Estado:** PROPUESTO (2026-07-14)
**Origen:** revisión dirigida del subsistema Documentador (planes 109/113/114) pedida por el operador: mejoras de funcionalidad, eficiencia y UX/UI.
**Flag master:** `STACKY_DOCS_DOCUMENTER_V2_ENABLED` (default **OFF**, activable desde la UI en el panel de flags del Arnés; `requires` el master del 113).
**Convive con:** planes 134/135/136 (100% frontend, tocan `App.tsx`/`TicketBoard.tsx`/modales — CERO solapamiento de archivos con este plan, que toca `doc_documenter.py`, `api/docs.py` y los componentes `docs/` del Documentador). No re-propone nada de la serie Obsidian 109-115 (grafo 109/111, RAG 112, 1-click 113, staleness 114, TF-IDF 115): la EXTIENDE.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Rutas, símbolos y comandos son LITERALES.
> Prohibido desviarse de los nombres exactos, prohibido "mejorar" el alcance.
> Todo lo ambiguo ya fue decidido acá.

---

## 1. Objetivo + KPI/impacto esperado

El Documentador 1-click (plan 113) funciona pero tiene un defecto estructural: **le pide al agente citas `archivo:línea` sin darle el código** — el bloque de contexto de módulo es UNA frase sin evidencia (`doc_documenter.py:235-243`), así que las marcas `[V]` no pueden estar fundadas y el anti-alucinación queda en el papel. Además nadie verifica las citas producidas, el estado del run vive solo en memoria (un restart lo pierde con la rama huérfana), la UI esconde las razones de skip y no muestra QUÉ se escribió, y se invoca al LLM para modos sin ningún target. Este plan cierra los 6 gaps con lógica determinista (sin LLM nuevo), detrás de una sola flag OFF.

**KPIs (todos binarios):**

- **KPI-1 (evidencia real):** con la flag ON, el contexto de un modo RECONSTRUIR/COMPLETAR contiene el árbol de archivos del módulo y símbolos con número de línea reales. Verificación: test `test_module_context_v2_incluye_arbol_y_simbolos` (F1).
- **KPI-2 (citas verificadas):** toda propuesta aplicada lleva `citations: {total, ok, bad}` calculado contra el filesystem real; una cita a archivo inexistente o línea fuera de rango cae en `bad`. Verificación: tests de `verify_citations` (F2).
- **KPI-3 (cero invocaciones LLM vacías):** con la flag ON, un modo sin targets (NORMALIZAR sin notas, ACTUALIZAR sin stale, ENRIQUECER sin huérfanas) NO llama a `invoke_documenter`. Verificación: test `test_short_circuit_no_invoca_modos_sin_targets` (F3).
- **KPI-4 (run sobrevive al restart):** con la flag ON, el reporte terminal de un run queda en disco y `GET /api/docs/documenter/status?run=<id>` lo devuelve aunque el proceso se haya reiniciado. Verificación: tests de persistencia (F4).
- **KPI-5 (revisión sin salir de la UI):** el panel muestra por archivo escrito un preview del contenido y por archivo saltado la razón en castellano; el operador decide keep/discard viendo QUÉ se escribió. Verificación: tests puros de `documenterModel` (F6) + `tsc --noEmit` en 0.
- **KPI-6 (flag OFF = byte-idéntico):** con `STACKY_DOCS_DOCUMENTER_V2_ENABLED=false` el pipeline se comporta EXACTAMENTE como hoy (mismo contexto, mismos modos, sin persistencia, respuesta de status sin campos nuevos con valor). Verificación: tests "flag OFF" de F1/F3/F4/F5.

---

## 2. Por qué ahora / gaps que cierra (evidencia archivo:línea)

1. **Contexto sin evidencia (funcionalidad — el gap más grave).** `services/doc_documenter.py:235-243` (`_module_context_block`): el `content` es literalmente `f"Documentá el módulo '{module}'. Citá archivo:línea del código real."`. El agente NO recibe árbol ni símbolos ni una sola línea de código → cualquier `[V] archivo:línea` que produzca es inventado. El prompt (`doc_documenter.py:28-29`) exige "citan archivo:línea real del contexto provisto", pero el contexto provisto no tiene ninguno.
2. **Gate de marcas trivial (calidad).** `doc_documenter.py:188`: `marks_ok = any(tok in body for tok in _MARKS)` — alcanza con UNA marca cualquiera en todo el cuerpo. Nadie verifica que las citas `[V]` apunten a archivos/líneas existentes; `sources=` del bloque DOC (`doc_documenter.py:164-168`) se parsea y se descarta sin validar.
3. **Estado volátil, sin historial (robustez).** `doc_documenter.py:518` (`_run_registry: dict[str, dict] = {}`): registro en memoria del proceso. Restart del backend ⇒ `GET /documenter/status` devuelve 404 (`api/docs.py:297-299`) y el operador queda con una rama `stacky/doc-*` creada y CERO reporte de qué contiene. No existe endpoint de historial de corridas.
4. **Invocaciones LLM sin valor (eficiencia).** `doc_documenter.py:662-668`: el loop invoca al agente para CADA modo del plan sin chequear targets. ENRIQUECER corre SIEMPRE (todo estado de salud lo incluye, `doc_documenter.py:123-145`) aunque el subgrafo tenga 0 huérfanas; cada invocación puede costar hasta 1800 s (`_INVOKE_TIMEOUT_S`, `doc_documenter.py:169`).
5. **UI opaca para decidir (UX).** `frontend/src/components/docs/DocumenterResultPanel.tsx:26-34`: muestra `writtenCount`/`skippedCount` y `diff_stat` crudo; las razones de skip (`missing_confidence_marks`, `canonical_readonly`, `unsafe_path`, `max_files_cap` — `doc_documenter.py:483-493`) NUNCA se muestran, y no hay forma de ver el contenido escrito sin ir a git por consola. El human-in-the-loop decide a ciegas.
6. **Sin lista de archivos con contenido (UX/API).** `api/docs.py:300-308`: el status expone `written` (paths) pero no el contenido propuesto; en modo degradado (carpeta-sombra, `doc_documenter.py:654-658`) ni siquiera hay rama que diffear.

Los planes recientes 134/135/136 son UX de runs/errores/protección en la shell general y NO tocan el Documentador; el 128 (tablero de planes) y el 129 (paleta) tampoco. No hay duplicación.

---

## 3. Principios y guardarraíles (no negociables, van en el código)

1. **Paridad 3 runtimes.** Todo lo nuevo es determinista (Python puro / TS puro) y corre ANTES o DESPUÉS de la invocación LLM. La invocación sigue siendo `agent_runner.run_agent(..., runtime=runtime)` (`doc_documenter.py:342-354`), que ya es runtime-agnóstica (Codex CLI / Claude Code CLI / GitHub Copilot Pro). Fallback existente intacto: output vacío o timeout ⇒ `parse_proposals("")` ⇒ `[]` y el run sigue (`doc_documenter.py:330-359`).
2. **Cero trabajo extra del operador.** Flag master **OFF**. Se activa desde la UI (los `FlagSpec` con `env_only=False` aparecen solos en el panel genérico de flags del Arnés — patrón plan 33/86). Sin pasos manuales nuevos, sin config nueva obligatoria, backward-compatible al 100% (KPI-6).
3. **Human-in-the-loop.** Nada de autonomía nueva: el Documentador sigue proponiendo a una rama revertible y el operador sigue decidiendo keep/discard. Este plan solo le da MÁS información para decidir. Prohibido auto-merge, auto-keep, auto-retry con LLM.
4. **Mono-operador sin auth.** Ningún concepto de usuario/rol en endpoints nuevos.
5. **No degradar.** Ninguna fase toca `agent_runner`, el runner de CLI, ni el gate git del 113 (`prepare_doc_branch`/`keep`/`discard`). `docs/sistema/` sigue read-only (`_is_canonical`, `doc_documenter.py:463-465`). Las funciones nuevas NUNCA lanzan hacia el pipeline: capturan y loguean (patrón `doc_documenter.py:91-93`).
6. **Reuso.** Se reusa `doc_indexer.list_doc_sources` para rutas, el registry/lock de runs del 113, `runtime_paths.data_dir()` para persistencia, el panel de flags existente y `documenterModel.ts` para lógica pura de UI.
7. **Gotchas de la casa codificados:**
   - Los `FlagSpec` nuevos van **SIN kwarg `default=`** (el default runtime vive en `config.py` con `os.getenv(..., "false")`) — un `default=` explícito fuera de `_CURATED_DEFAULTS_ON` rompe `test_default_known_only_for_curated` (patrón exacto de `STACKY_DOCS_DOCUMENTER_MAX_FILES`, `services/harness_flags.py:1590-1604`, que no tiene `default=`).
   - Toda flag nueva DEBE quedar categorizada (si no, rompe `test_every_registry_flag_is_categorized`): se agregan a la tupla donde ya vive `STACKY_DOCS_DOCUMENTER_MAX_FILES` (`services/harness_flags.py:143`).
   - `requires` es profundidad 1 contra un master existente: ambas flags nuevas llevan `requires="STACKY_DOCS_DOCUMENTER_ENABLED"` (NUNCA una contra la otra — encadenar rompe R4) y se agrega la arista al mapa congelado `tests/test_harness_flags_requires.py:158`.
   - Tests backend nuevos se registran en `HARNESS_TEST_FILES` de `backend/scripts/run_harness_tests.sh` **y** `backend/scripts/run_harness_tests.ps1` (si no, falla el meta-test del plan 49).
   - Frontend: `@testing-library/react` y `jsdom` NO están en `package.json` — los tests de UI son de LÓGICA PURA en `src/docs/*.test.ts` (vitest sin DOM) + gate `tsc --noEmit`.
   - Tests backend se corren POR ARCHIVO con el venv real `backend/.venv` (py3.13).

**Comandos de verificación estándar (se repiten por fase):**

```powershell
# Backend (desde N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend):
& .\.venv\Scripts\python.exe -m pytest tests\<archivo>.py -q
# Frontend (desde N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend):
npx vitest run src/docs/documenterModel.test.ts
npx tsc --noEmit
```

---

## 4. Fases

### F0 — Flags del arnés + esqueleto del módulo de evidencia

**Objetivo:** dejar registradas las 2 flags (OFF, visibles/activables en la UI) y creado el módulo `doc_evidence.py` vacío de lógica LLM, con sus tests de registro en verde. Valor: gate seguro para todo lo demás.

**Archivos a crear:**
- `Stacky Agents/backend/services/doc_evidence.py`
- `Stacky Agents/backend/tests/test_doc_evidence.py`

**Archivos a editar:**
- `Stacky Agents/backend/config.py` (inmediatamente después de la línea del bloque `STACKY_DOCS_DOCUMENTER_MAX_FILES`, hoy `config.py:525-527`)
- `Stacky Agents/backend/services/harness_flags.py` (tupla de categoría en `:143` y `FLAG_REGISTRY` después del `FlagSpec` de `STACKY_DOCS_DOCUMENTER_MAX_FILES`, hoy `:1590-1604`)
- `Stacky Agents/backend/services/harness_flags_help.py` (junto a los `PlainHelp` del 113, hoy `:298-306`)
- `Stacky Agents/backend/tests/test_harness_flags_requires.py` (mapa congelado, hoy `:158`)
- `Stacky Agents/backend/scripts/run_harness_tests.sh` y `run_harness_tests.ps1` (agregar `tests/test_doc_evidence.py`, `tests/test_documenter_v2_pipeline.py`, `tests/test_plan137_endpoints.py` a `HARNESS_TEST_FILES`)

**Flags exactas (nombres literales):**

| Key | type | default runtime (config.py) | requires | env_only |
|---|---|---|---|---|
| `STACKY_DOCS_DOCUMENTER_V2_ENABLED` | bool | `os.getenv("STACKY_DOCS_DOCUMENTER_V2_ENABLED", "false").lower() == "true"` | `STACKY_DOCS_DOCUMENTER_ENABLED` | False |
| `STACKY_DOCS_DOCUMENTER_EVIDENCE_MAX_CHARS` | int | `int(os.getenv("STACKY_DOCS_DOCUMENTER_EVIDENCE_MAX_CHARS", "12000") or "12000")` | `STACKY_DOCS_DOCUMENTER_ENABLED` | False, `min_value=1000`, `max_value=100000` |

`FlagSpec` de la bool: `label="Documentador v2: evidencia, citas e historial (Plan 137)"`, `group="global"`, `description` que diga que activa evidencia real de código en el contexto, verificación determinista de citas [V], short-circuit de modos sin targets, historial persistente de corridas y preview por archivo en el panel; default OFF. **SIN kwarg `default=`** (guardarraíl §3.7). La int: `label="Documentador v2: tope de caracteres de evidencia"`.

En `config.py` los dos atributos van en la clase de config con el MISMO patrón de las líneas 522-527 existentes.

En `harness_flags_help.py` agregar dos `PlainHelp` calcando el formato de `STACKY_DOCS_DOCUMENTER_ENABLED` (`:298`).

En `test_harness_flags_requires.py:158` (dict congelado de aristas) agregar exactamente:
```python
    "STACKY_DOCS_DOCUMENTER_V2_ENABLED": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 137
    "STACKY_DOCS_DOCUMENTER_EVIDENCE_MAX_CHARS": "STACKY_DOCS_DOCUMENTER_ENABLED",  # Plan 137
```

`services/doc_evidence.py` arranca con docstring de módulo (`"""Plan 137 — Evidencia determinista para el Documentador..."""`) y las firmas de F1/F2 (pueden implementarse ya en F1; en F0 alcanza con que el módulo exista e importe sin error).

**Tests PRIMERO** (en `tests/test_doc_evidence.py`, sección F0):
1. `test_flags_v2_registradas_y_off_por_default`: importa `config.config`; asserts `config.STACKY_DOCS_DOCUMENTER_V2_ENABLED is False` y `config.STACKY_DOCS_DOCUMENTER_EVIDENCE_MAX_CHARS == 12000`.
2. `test_flags_v2_en_flag_registry`: desde `services.harness_flags` obtener el registro (mismo acceso que usa `tests/test_harness_flags.py`) y assert que ambas keys existen, que la bool no tiene default curado en True y que ambas tienen `requires == "STACKY_DOCS_DOCUMENTER_ENABLED"`.
3. `test_modulo_doc_evidence_importa`: `import services.doc_evidence` no lanza.

**Comandos:**
```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_doc_evidence.py -q
& .\.venv\Scripts\python.exe -m pytest tests\test_harness_flags.py -q
& .\.venv\Scripts\python.exe -m pytest tests\test_harness_flags_requires.py -q
```

**Criterio de aceptación (binario):** los 3 comandos en verde (0 failed). Flag protectora: las dos nuevas, OFF. **Impacto por runtime:** ninguno (solo registro). **Trabajo del operador:** ninguno (opt-in default off).

---

### F1 — Evidencia real de módulo en el contexto (funcionalidad núcleo)

**Objetivo:** que RECONSTRUIR/COMPLETAR reciban árbol + símbolos con líneas reales del módulo, para que las `[V]` sean verificables de verdad.

**Archivos a editar:** `services/doc_evidence.py`, `services/doc_documenter.py` (`_module_context_block`, hoy `:235-243`), `tests/test_doc_evidence.py`.

**Símbolos exactos en `doc_evidence.py`:**

```python
_SYMBOL_PATTERNS: dict[str, str] = {
    ".py":  r"^(?:async\s+def|def|class)\s+\w+",
    ".ts":  r"^export\s+(?:async\s+)?(?:function|class|const|interface|type)\s+\w+",
    ".tsx": r"^export\s+(?:async\s+)?(?:function|class|const|interface|type)\s+\w+",
    ".js":  r"^(?:export\s+)?(?:async\s+)?(?:function|class|const)\s+\w+",
    ".cs":  r"^\s*(?:public|internal|protected|private)\s+.*(?:class|interface|void|Task|string|int|bool)\s+\w+",
    ".ps1": r"^function\s+[\w-]+",
}

def extract_symbols(rel_path: str, content: str) -> list[str]:
    """Devuelve ["<rel_path>:<lineno> <línea recortada a 120 chars>"] por cada match
    del patrón de la extensión. Extensión sin patrón → []. Nunca lanza."""

def build_module_evidence(workspace_root: str, module: str, *,
                          max_files: int = 30, max_chars: int = 12000) -> str:
    """Evidencia determinista de un módulo:
    - base = Path(workspace_root) / module  si module != "<repo>", si no workspace_root.
    - Si base no existe o no es dir → "" (el caller degrada al texto del 113).
    - Archivos: sorted(base.rglob("*")) filtrando extensiones de _SYMBOL_PATTERNS + ".md",
      EXCLUYENDO cualquier path que contenga "/node_modules/", "/.git/", "/__pycache__/",
      "/.venv/", "/dist/", "/build/" (comparar sobre str(path).replace("\\\\", "/")).
      Tope max_files (orden alfabético ⇒ determinista).
    - Salida (texto plano):
        "ARBOL:\\n" + una línea por archivo (path relativo a workspace_root, POSIX)
        + "\\nSIMBOLOS:\\n" + extract_symbols(...) de cada archivo (paths relativos a
        workspace_root para que archivo:línea sea citable tal cual).
    - Truncado duro a max_chars con sufijo "\\n[...evidencia truncada]".
    - Lecturas con encoding="utf-8", errors="ignore". Nunca lanza (try/except → "")."""
```

**Edición en `doc_documenter.py`** — `_module_context_block` queda:

```python
def _module_context_block(project_name: str, module: str) -> dict:
    from config import config as _cfg
    content = f"Documentá el módulo '{module}'. Citá archivo:línea del código real."
    if bool(getattr(_cfg, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", False)):
        try:
            from services import doc_evidence, doc_indexer
            ws = doc_indexer.list_doc_sources(project_name).get("workspace_root")
            if ws:
                ev = doc_evidence.build_module_evidence(
                    str(ws), module,
                    max_chars=int(getattr(_cfg, "STACKY_DOCS_DOCUMENTER_EVIDENCE_MAX_CHARS", 12000)))
                if ev:
                    content = content + "\n\nEVIDENCIA DEL CODIGO (única fuente válida para [V]):\n" + ev
        except Exception as exc:
            logger.warning("doc_documenter: evidencia v2 no disponible: %s", exc)
    return {"id": f"module-{module}", "kind": "module-tree", "title": f"Módulo: {module}",
            "content": content, "source": {"type": "module", "module": module}}
```

**Tests PRIMERO** (sección F1 de `tests/test_doc_evidence.py`; usar `tmp_path` de pytest para armar un mini-repo con `mod/a.py` conteniendo `def foo():` en línea 3 y `mod/b.ts` con `export function bar()` en línea 1):
1. `test_extract_symbols_python_y_ts`: devuelve `"mod/a.py:3 def foo():"`-style y la línea del export.
2. `test_extract_symbols_extension_desconocida_vacia`: `.xyz` → `[]`.
3. `test_build_module_evidence_arbol_y_simbolos`: contiene `"ARBOL:"`, `"SIMBOLOS:"`, `"mod/a.py"` y `"mod/a.py:3"`.
4. `test_build_module_evidence_excluye_node_modules`: archivo bajo `mod/node_modules/x.js` no aparece.
5. `test_build_module_evidence_trunca`: con `max_chars=50`, `len(out) <= 50 + len("\n[...evidencia truncada]")` y termina con el sufijo.
6. `test_build_module_evidence_dir_inexistente_vacio`: módulo inexistente → `""`.
7. `test_module_context_v2_incluye_arbol_y_simbolos`: monkeypatch `config.config.STACKY_DOCS_DOCUMENTER_V2_ENABLED = True` y `services.doc_indexer.list_doc_sources` → `{"workspace_root": str(tmp_path)}`; `_module_context_block("p", "mod")["content"]` contiene `"EVIDENCIA DEL CODIGO"` y `"mod/a.py:3"`.
8. `test_module_context_flag_off_identico_113`: con la flag en False, el `content` es EXACTAMENTE `"Documentá el módulo 'mod'. Citá archivo:línea del código real."`.

**Comando:** `& .\.venv\Scripts\python.exe -m pytest tests\test_doc_evidence.py -q`

**Criterio binario:** comando en verde. **Flag:** `STACKY_DOCS_DOCUMENTER_V2_ENABLED` (OFF). **Runtimes:** el bloque de contexto viaja igual a los 3 runtimes vía `context_blocks` de `run_agent`; fallback = texto del 113 si la evidencia falla o la flag está OFF. **Trabajo del operador:** ninguno.

---

### F2 — Verificador determinista de citas [V]

**Objetivo:** medir (sin bloquear) cuántas citas `archivo:línea` de cada propuesta existen de verdad, y exponerlo en el reporte.

**Archivos a editar:** `services/doc_evidence.py`, `services/doc_documenter.py` (`apply_proposals`, hoy `:468-503`, y el dataclass `ApplyResult` `:444-449`), `tests/test_doc_evidence.py`.

**Símbolos exactos en `doc_evidence.py`:**

```python
_CITATION_RE = re.compile(r"(?P<path>[\w][\w./\\-]*\.[A-Za-z0-9]{1,5}):(?P<line>\d{1,6})")

def extract_citations(text: str) -> list[tuple[str, int]]:
    """Todos los pares (path_normalizado_posix, línea) que matchean _CITATION_RE en text.
    Deduplicados preservando orden. Nunca lanza."""

def verify_citations(text: str, workspace_root: str) -> dict:
    """{"total": N, "ok": M, "bad": ["path:line", ...]} donde una cita es ok si
    Path(workspace_root)/path existe como archivo Y (línea == 0 o línea <=
    cantidad de líneas del archivo, contadas con read_text(utf-8, errors='ignore')).
    workspace_root vacío/inexistente → {"total": N, "ok": 0, "bad": [todas]}.
    Nunca lanza."""
```

**Edición en `doc_documenter.py`:**
- `ApplyResult` gana el campo `files: list[dict] = field(default_factory=list)` (se completa en F5; acá se agrega ya el campo).
- `apply_proposals` gana kwarg `workspace_root: str | None = None` (default None ⇒ comportamiento actual intacto). Tras escribir cada archivo OK, si `workspace_root` no es None:
```python
            from services import doc_evidence
            citations = doc_evidence.verify_citations(
                prop.content + " " + ",".join(prop.sources), workspace_root)
```
  y guarda `{"path": norm, "action": prop.action, "citations": citations}` en `result.files` (el preview de contenido se suma en F5).
- En `run_documenter` (`:670`) el call pasa a `apply_proposals(all_props, write_root, branch, degraded=degraded, workspace_root=(workspace_root if _v2_enabled() else None))`, donde `_v2_enabled()` es un helper nuevo módulo-level:
```python
def _v2_enabled() -> bool:
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", False))
```

**Regla dura:** las citas malas NO producen skip ni bloqueo en este plan (solo reporte). Bloquear queda explícitamente fuera de scope (§6).

**Tests PRIMERO** (sección F2 de `tests/test_doc_evidence.py`):
1. `test_extract_citations_basico`: `"ver a.py:10 y src/b.ts:3"` → `[("a.py", 10), ("src/b.ts", 3)]`.
2. `test_extract_citations_dedup_y_backslash`: `"x\\y.py:5 x/y.py:5"` → una sola entrada `("x/y.py", 5)`.
3. `test_verify_citations_ok_y_bad`: con `tmp_path/a.py` de 12 líneas: `"a.py:10"` ok, `"a.py:99"` bad, `"nope.py:1"` bad; total 3, ok 1.
4. `test_verify_citations_sin_root`: `verify_citations("a.py:1", "")["ok"] == 0`.
5. `test_apply_proposals_anota_citations`: propuesta con `[V] a.py:1` y `workspace_root=tmp_path` (con `a.py` presente) ⇒ `result.files[0]["citations"]["ok"] == 1`.
6. `test_apply_proposals_sin_workspace_root_sin_files_citations`: con `workspace_root=None`, `result.files == []` (comportamiento 113 intacto).

**Comando:** `& .\.venv\Scripts\python.exe -m pytest tests\test_doc_evidence.py -q`

**Criterio binario:** verde. **Flag:** V2 (OFF ⇒ `workspace_root=None` ⇒ sin cambio). **Runtimes:** post-proceso determinista idéntico para los 3; sin fallback necesario. **Trabajo del operador:** ninguno.

---

### F3 — Short-circuit de modos sin targets (eficiencia)

**Objetivo:** no invocar al LLM cuando un modo no tiene nada que hacer; reportar los modos salteados.

**Archivos a crear:** `Stacky Agents/backend/tests/test_documenter_v2_pipeline.py`.
**Archivos a editar:** `services/doc_documenter.py` (nueva función módulo-level + loop de `run_documenter` `:662-668` + `_new_run_record` `:577-582` + dict `report` `:690-703`).

**Símbolo exacto:**

```python
def should_invoke_mode(mode: DocumenterMode, plan: DocumenterPlan,
                       orphan_count: int) -> tuple[bool, str]:
    """(True, "") si el modo tiene trabajo; (False, razón) si no.
    Reglas EXACTAS (sin flag acá; el gate por flag lo hace el caller):
    - NORMALIZAR  → (False, "sin_notas_para_normalizar") si plan.notes_to_normalize == []
    - ACTUALIZAR  → (False, "sin_notas_stale") si plan.notes_to_update == []
    - ENRIQUECER  → (False, "sin_huerfanas") si orphan_count == 0
    - RECONSTRUIR y COMPLETAR → SIEMPRE (True, "") (usan ["<repo>"] como fallback hoy).
    Pura, sin I/O, nunca lanza."""
```

`orphan_count` se calcula UNA vez en `run_documenter` antes del loop, solo si `_v2_enabled()`:
```python
    orphan_count = -1  # -1 = no evaluado (flag OFF) ⇒ should_invoke_mode no se consulta
    if _v2_enabled():
        try:
            from services import doc_graph
            orphan_count = len(doc_graph.build_graph(project_name=project_name).get("orphans", []) or [])
        except Exception:
            orphan_count = 1  # degradación conservadora: ante error, invocar igual
```
Loop nuevo (reemplaza `:663-668`):
```python
    modes_skipped: list[dict] = []
    for mode in plan.modes:
        if _v2_enabled():
            ok, why = should_invoke_mode(mode, plan, orphan_count)
            if not ok:
                modes_skipped.append({"mode": str(mode.value), "reason": why})
                continue
        if run_id:
            _update_run(run_id, current_mode=str(mode.value))
        ctx = build_context_for_mode(mode, plan, project_name)
        props = invoke_documenter(mode, ctx, project_name, runtime)
        all_props += props
```
`_new_run_record` suma `"modes_skipped": []`; el dict `report` suma `"modes_skipped": modes_skipped`.

**Tests PRIMERO** (`tests/test_documenter_v2_pipeline.py`):
1. `test_should_invoke_mode_tabla_completa`: los 5 modos con targets vacíos y no vacíos según la tabla (10 asserts).
2. `test_short_circuit_no_invoca_modos_sin_targets`: monkeypatch flag ON, `plan_documenter_run` → plan con modes `[NORMALIZAR, ENRIQUECER]` y listas vacías, `doc_graph.build_graph` → `{"orphans": []}`, `invoke_documenter` → función espía que appendea a una lista; correr `run_documenter("p", "mock")` con `_resolve_target_paths` monkeypatcheado a `(str(tmp_path), str(tmp_path), str(tmp_path))` (repo NO git ⇒ modo degradado, no importa acá); assert espía NO llamada y `report["modes_skipped"] == [{"mode": "NORMALIZAR", ...}, {"mode": "ENRIQUECER", ...}]`.
3. `test_flag_off_invoca_todos_los_modos`: mismo escenario con flag OFF ⇒ espía llamada 2 veces y `modes_skipped == []`.

**Comando:** `& .\.venv\Scripts\python.exe -m pytest tests\test_documenter_v2_pipeline.py -q`

**Criterio binario:** verde. **Flag:** V2 (OFF ⇒ loop idéntico al 113). **Runtimes:** ahorra invocaciones en los 3 por igual; degradación conservadora ante error = invocar (nunca pierde trabajo). **Trabajo del operador:** ninguno.

---

### F4 — Historial persistente de corridas (robustez)

**Objetivo:** el reporte terminal de cada run sobrevive al restart y hay historial consultable.

**Archivos a editar:** `services/doc_documenter.py`, `api/docs.py`, `tests/test_documenter_v2_pipeline.py`; crear `tests/test_plan137_endpoints.py`.

**Símbolos exactos en `doc_documenter.py`:**

```python
def _runs_dir() -> Path:
    """runtime_paths.data_dir() / "documenter_runs" (mkdir parents+exist_ok). Nunca lanza:
    ante error devuelve Path(tempfile.gettempdir()) / "stacky-documenter-runs"."""

def _persist_run_report(run_id: str, report: dict) -> None:
    """Si _v2_enabled(): escribe json.dumps(report, ensure_ascii=False, default=str)
    en _runs_dir()/<run_id>.json (encoding utf-8). Best-effort: except → logger.warning."""

def list_runs(limit: int = 20) -> list[dict]:
    """Si no _v2_enabled(): []. Lee los .json de _runs_dir() ordenados por mtime desc,
    tope limit; devuelve [{"run_id": stem, "state", "modes", "branch", "written_count":
    len(written), "skipped_count": len(skipped), "degraded", "mtime_iso"}]. Nunca lanza."""
```

- En `run_documenter`, después de `_update_run(run_id, **report)` (`:704-705`): `_persist_run_report(run_id or "sync", report)`.
- `get_run` (`:614-617`): si el registry no tiene el id **y** `_v2_enabled()`, intenta leer `_runs_dir()/<run_id>.json` y devolver el dict (except → None). El endpoint decide (`api/docs.py:342-370`) NO cambia: un run leído de disco tras restart tiene `state="completed"` y el operador puede decidir keep/discard igual porque `keep_doc_branch`/`discard_doc_branch` solo necesitan `target_root` y `branch`, que están en el reporte persistido.
- **Endpoint nuevo** en `api/docs.py` (debajo de `documenter_status`):
```python
@bp.get("/documenter/runs")
def documenter_runs():
    """Plan 137 — Historial de corridas persistidas. 404 si el master 113 está OFF;
    lista vacía si la V2 está OFF."""
    if not _documenter_enabled():
        return jsonify({"ok": False, "error": "documenter_disabled"}), 404
    from services import doc_documenter
    return jsonify({"ok": True, "runs": doc_documenter.list_runs()})
```

**Tests PRIMERO:**
- En `tests/test_documenter_v2_pipeline.py`:
  4. `test_persist_y_get_run_desde_disco`: monkeypatch flag ON y `runtime_paths.data_dir` → `tmp_path`; `_persist_run_report("abc123", {"state": "completed", "written": [], "skipped": [], "modes": [], "branch": None, "degraded": True})`; limpiar `_run_registry`; `get_run("abc123")["state"] == "completed"`.
  5. `test_list_runs_ordena_y_limita`: escribir 3 reportes con mtimes distintos (usar `os.utime`); `list_runs(2)` devuelve 2, el más nuevo primero.
  6. `test_persistencia_flag_off_inerte`: flag OFF ⇒ `_persist_run_report` no crea archivo y `list_runs() == []`.
- En `tests/test_plan137_endpoints.py` (calcar el patrón de `tests/test_plan113_endpoints.py:18` para fixture de app + flag):
  1. `test_runs_404_si_master_off`.
  2. `test_runs_lista_vacia_v2_off` (master ON, V2 OFF ⇒ `{"ok": True, "runs": []}`).
  3. `test_runs_devuelve_historial` (ambas ON + data_dir monkeypatcheado con un reporte).

**Comandos:**
```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_documenter_v2_pipeline.py -q
& .\.venv\Scripts\python.exe -m pytest tests\test_plan137_endpoints.py -q
```

**Criterio binario:** ambos en verde. **Flag:** V2 (OFF ⇒ sin archivos nuevos en disco, endpoint devuelve `[]`). **Runtimes:** independiente del runtime. **Trabajo del operador:** ninguno.

---

### F5 — Preview por archivo en el reporte (API)

**Objetivo:** que el reporte incluya, por archivo escrito, un preview del contenido (funciona también en modo degradado carpeta-sombra, donde no hay rama que diffear).

**Archivos a editar:** `services/doc_documenter.py` (`apply_proposals`), `api/docs.py` (`documenter_status`), `tests/test_documenter_v2_pipeline.py`, `tests/test_plan137_endpoints.py`.

**Ediciones exactas:**
- Constante módulo-level en `doc_documenter.py`: `_PREVIEW_MAX_CHARS = 4000`.
- En `apply_proposals`, el dict que F2 agrega a `result.files` gana la clave `"content_preview": prop.content[:_PREVIEW_MAX_CHARS]` (solo cuando `workspace_root is not None`, es decir solo con V2 ON — misma condición de F2).
- El dict `report` de `run_documenter` gana `"files": result.files`.
- `_new_run_record` gana `"files": []` y `"modes_skipped": []` (este último ya agregado en F3; verificar, no duplicar).
- `documenter_status` (`api/docs.py:300-308`) agrega al jsonify: `"files": rec.get("files", [])`, `"modes_skipped": rec.get("modes_skipped", [])`. Con V2 OFF ambos son `[]` ⇒ backward-compatible (KPI-6: campos presentes pero vacíos; el frontend actual los ignora).

**Tests PRIMERO:**
- `tests/test_documenter_v2_pipeline.py` caso 7 `test_apply_proposals_incluye_preview`: propuesta con contenido de 5000 chars y `workspace_root=str(tmp_path)` ⇒ `len(result.files[0]["content_preview"]) == 4000`.
- `tests/test_plan137_endpoints.py` caso 4 `test_status_expone_files_y_modes_skipped`: sembrar `_run_registry` con un record que tenga `files` y `modes_skipped` no vacíos; el GET los devuelve.

**Comandos:** los mismos dos de F4. **Criterio binario:** verde. **Flag:** V2. **Runtimes:** idéntico en los 3 (el preview sale del contenido parseado, no del runtime). **Trabajo del operador:** ninguno.

---

### F6 — Panel de revisión en la UI (UX/UI)

**Objetivo:** que el operador decida keep/discard viendo archivos escritos con preview, razones de skip en castellano, chip de citas y modos salteados — sin salir de la UI.

**Archivos a editar:**
- `Stacky Agents/frontend/src/api/endpoints.ts` — extender el tipo `DocumenterStatusResponse` con `files?: DocumenterFileEntry[]` y `modes_skipped?: { mode: string; reason: string }[]`; agregar `export interface DocumenterFileEntry { path: string; action: string; content_preview?: string; citations?: { total: number; ok: number; bad: string[] } }`; agregar `Docs.documenterRuns = () => fetch GET /api/docs/documenter/runs` calcando el estilo de `Docs.documenterStatus`.
- `Stacky Agents/frontend/src/docs/documenterModel.ts` — funciones puras nuevas (sin React/DOM):

```ts
export function formatSkipReason(reason: string): string {
  // mapa LITERAL; clave desconocida → la clave tal cual
  const map: Record<string, string> = {
    unsafe_path: "Ruta insegura (fuera del repo)",
    canonical_readonly: "docs/sistema/ es de solo lectura",
    missing_confidence_marks: "Sin marcas [V]/[INF]/[NV]",
    max_files_cap: "Superó el tope de archivos del run",
  };
  if (reason.startsWith("write_error:")) return "Error de escritura";
  return map[reason] ?? reason;
}

export interface DocumenterFileView {
  path: string;
  action: string;
  preview: string;          // content_preview ?? ""
  citationsLabel: string;   // "" si no hay citations; si no `${ok}/${total} citas verificadas`
  citationsBad: string[];   // citations?.bad ?? []
}

export function buildFilesView(status: DocumenterStatusResponse | null | undefined): DocumenterFileView[];
export function buildSkippedView(status: DocumenterStatusResponse | null | undefined): { path: string; label: string }[];
// skipped viene como [path, reason][] del backend (tuplas serializadas como arrays JSON)
```

- `Stacky Agents/frontend/src/components/docs/DocumenterResultPanel.tsx` — debajo del `diff_stat` actual (`:30-34`), render aditivo y condicional (si `buildFilesView(status).length === 0` y `buildSkippedView(status).length === 0`, el panel queda EXACTAMENTE como hoy):
  - Lista de archivos: `<details>` por archivo con `<summary>{f.path} · {f.action}{f.citationsLabel ? " · " + f.citationsLabel : ""}</summary>` y `<pre style={{ maxHeight: 240, overflow: "auto" }}>{f.preview}</pre>`; si `f.citationsBad.length > 0`, una línea `Citas no verificables: {f.citationsBad.join(", ")}` con `color: "#a00"`.
  - Lista de saltados: `<ul>` con `{s.path} — {s.label}`.
  - Modos salteados: línea `Modos sin trabajo: {modes_skipped.map(m => m.mode).join(", ")}` solo si el array viene no vacío.
- `Stacky Agents/frontend/src/docs/documenterModel.test.ts` — EXTENDER (ya existe) con la sección Plan 137.

**Tests PRIMERO** (vitest puro, sin jsdom — gotcha §3.7):
1. `formatSkipReason` mapea las 4 claves conocidas, el prefijo `write_error:` y una desconocida.
2. `buildFilesView` con status `{ files: [{path, action, content_preview, citations:{total:3, ok:2, bad:["x.py:9"]}}] }` ⇒ `citationsLabel === "2/3 citas verificadas"` y `citationsBad` correcto; con `files` ausente ⇒ `[]`.
3. `buildSkippedView` con `skipped: [["a.md", "missing_confidence_marks"]]` ⇒ label en castellano; con `skipped` ausente ⇒ `[]`.
4. `summarizeDocumenterStatus` NO cambia de contrato: los tests existentes siguen en verde sin editar.

**Comandos:**
```powershell
# desde N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend
npx vitest run src/docs/documenterModel.test.ts
npx tsc --noEmit
```

**Criterio binario:** vitest en verde y `tsc --noEmit` con 0 errores. **Flag:** sin flag frontend — el render es data-driven: con V2 OFF el backend manda `files: []`/`modes_skipped: []` y el panel es idéntico al actual (KPI-6). **Runtimes:** N/A (frontend). **Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| La evidencia infla el prompt y degrada la invocación | Tope duro `STACKY_DOCS_DOCUMENTER_EVIDENCE_MAX_CHARS` (12000 default, ajustable en UI) + truncado determinista (F1). |
| `verify_citations` marca `bad` citas válidas por rutas relativas al módulo | Las citas se emiten en la evidencia como relativas a `workspace_root` (F1 lo garantiza); es report-only, nunca bloquea (F2, §6). |
| Short-circuit saltea trabajo real | Reglas EXACTAS solo para targets estructuralmente vacíos; ante error de grafo se invoca igual (degradación conservadora, F3). |
| Persistencia escribe basura en data dir compartida | Subcarpeta propia `documenter_runs/`, JSON por run, best-effort, solo con flag ON (F4). |
| Regresión del flujo 113 con flag OFF | KPI-6 + tests "flag OFF" explícitos en F1/F3/F4 + `workspace_root=None` default en `apply_proposals` (F2). |
| WIP ajeno sin commitear en el working tree (hoy: `test_documenter_autonomy.py`, `graphViewport.ts`, `DocGraphView.tsx` traen trabajo reciente) | Pre-flight por fase: `git status -- "<ruta>"` antes de editar CADA archivo; si tiene WIP ajeno, NO usar `git add -A` jamás — staging quirúrgico por pathspec (regla de la casa, precedente 135/136). |

## 6. Fuera de scope (explícito)

- Bloquear/skipear propuestas por citas malas (solo se reportan; endurecer el gate sería un plan futuro con evidencia de falsos positivos).
- Reintentos automáticos con LLM ante propuestas malas (violaría human-in-the-loop y costo).
- Diff git por archivo vía endpoint (el preview del contenido cubre la necesidad y funciona en modo degradado).
- Selector de módulos/scope en la UI (el 1-click sigue siendo 1-click).
- Cambios en `Documentador.agent.md`, `agents/documenter.py`, `agent_runner`, runner CLI o el gate git del 113.
- Tests RTL/jsdom de componentes React (gap estructural conocido; gate = lógica pura + tsc).

## 7. Glosario

- **Documentador 1-click (plan 113):** pipeline que detecta salud documental, invoca al agente `Documentador` por modos y escribe propuestas a una rama git revertible; el operador decide keep/discard.
- **Modo:** etapa del plan del Documentador (`RECONSTRUIR/NORMALIZAR/COMPLETAR/ACTUALIZAR/ENRIQUECER`), enum `DocumenterMode` en `doc_documenter.py:54-59`.
- **Marcas [V]/[INF]/[NV]:** etiquetas de confianza anti-alucinación: verificado con `archivo:línea` / inferido / no verificable.
- **Modo degradado (carpeta-sombra):** cuando el target no es repo git, las propuestas se escriben a `.stacky-docs-proposed/` sin rama (`doc_documenter.py:654-658`).
- **Huérfanas:** notas sin links en el grafo documental (`/api/docs/graph`, plan 109).
- **FlagSpec / FLAG_REGISTRY:** registro declarativo de flags del arnés en `services/harness_flags.py`; las de `env_only=False` se activan desde la UI.
- **Ratchet de tests:** meta-test (plan 49) que exige que todo archivo de test backend nuevo esté listado en `HARNESS_TEST_FILES` de `run_harness_tests.sh` y `.ps1`.
- **Runtime:** motor de ejecución del agente: `codex_cli`, `claude_code_cli` o `github_copilot` — el Documentador les pasa el mismo contexto a los tres.

## 8. Orden de implementación

1. F0 — flags + esqueleto + registro en ratchet (todo lo demás depende del gate).
2. F1 — evidencia real de módulo.
3. F2 — verificador de citas (usa el mini-repo de tests de F1).
4. F3 — short-circuit de modos.
5. F4 — persistencia + endpoint historial.
6. F5 — preview por archivo en reporte y status.
7. F6 — UI (consume los campos de F4/F5).

## 9. Definición de Hecho (DoD)

- [ ] Las 2 flags registradas (FlagSpec sin `default=`, categorizadas, `requires` al master 113, aristas en el mapa congelado, PlainHelp) y visibles/activables en la UI de flags del Arnés; default OFF.
- [ ] Los 4 archivos de test (3 backend nuevos + `documenterModel.test.ts` extendido) en verde, corridos POR ARCHIVO con `backend\.venv\Scripts\python.exe -m pytest` y `npx vitest run` respectivamente, con output real leído (cero falsos verdes).
- [ ] `tests/test_doc_evidence.py`, `tests/test_documenter_v2_pipeline.py` y `tests/test_plan137_endpoints.py` listados en `HARNESS_TEST_FILES` de `run_harness_tests.sh` **y** `run_harness_tests.ps1`.
- [ ] `npx tsc --noEmit` en 0 errores.
- [ ] Suites preexistentes del subsistema en verde: `tests/test_plan113_endpoints.py`, `tests/test_documenter_autonomy.py`, `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py` (por archivo).
- [ ] Con la flag OFF, `POST /documenter/run` + `GET /documenter/status` devuelven exactamente los campos de hoy más `files: []` y `modes_skipped: []` (verificado por test de F5).
- [ ] Ningún cambio en `agent_runner`, runners de CLI, `Documentador.agent.md` ni gate git del 113 (`git diff` lo confirma).
- [ ] Staging quirúrgico: solo los archivos de este plan en el commit (prohibido `git add -A`; hay WIP ajeno vivo en el working tree).
