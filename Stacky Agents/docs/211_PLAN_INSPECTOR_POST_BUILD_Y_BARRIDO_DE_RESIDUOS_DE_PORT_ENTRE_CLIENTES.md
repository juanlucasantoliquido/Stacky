# Plan 211 — Inspector post-build + barrido de residuos de port entre clientes

> Estado: **PROPUESTO v1** (2026-07-21). Pipeline: proponer → **[este paso ✓]** → criticar (`criticar-y-mejorar-plan`) → implementar (`implementar-plan-stacky`) → supervisar.
> Autor: StackyArchitectaUltraEficientCode (perfil normal, heredado de Opus 4.8).
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro (paridad obligatoria; el núcleo NO usa LLM).

---

## Planes relacionados (leer antes de implementar)

- **DEPENDE de Plan 210** — "Gate de build determinista del Developer: fin del falso 'Build OK'" (`Stacky Agents/docs/210_PLAN_GATE_DE_BUILD_DETERMINISTA_DEL_DEVELOPER_FIN_DEL_FALSO_BUILD_OK.md`). Este plan **consume el `BuildVerdict`** (contrato §5 del 210) y se engancha en la **seam de contribuidores de evidencia** que el 210 expone: `dev_build_verify.register_evidence_contributor(fn)` (F5 del 210). Los findings **bloqueantes** que produce este plan **fluyen al `gate_ok`** del 210 (bajan el estado + tiñen el deliverable de rojo) por el mecanismo de re-persistencia del veredicto que ya define el 210 F5. **No implementar 211 sin 210.**
- **DEPENDE (transitivo) de Plan 201** — "Taller de Compilación" (`Stacky Agents/docs/201_PLAN_TALLER_DE_COMPILACION_DETECCION_SLN_BUILD_RELEASE_1CLICK_Y_ARTEFACTOS_DESCARGABLES.md`). La Capa B inspecciona los **project files construidos** que el 210 resolvió (vía el `build.summary.json` + `verdict.solutions` del 201). Reusa el scanner `solution_scanner` (F1 del 201) para mapear `.sln → .csproj` cuando hace falta.
- **Coordina con Plan 208** — igual que el 210: cuando el 208 cablee la transición de estado en runners, el gate del 210 (que este plan alimenta con findings) debe correr en ese path. Sin acción extra en este plan.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** El Plan 210 verifica que el Developer **compiló** (veredicto de máquina). Este plan agrega dos inspecciones **deterministas** que van más allá del exit code de compilación y cierran un agujero real del trabajo multicliente de Stacky: **(Capa B) Inspector post-build** — parsea los archivos de proyecto construidos (`.csproj`/`.sln`) buscando efectos colaterales de build peligrosos (`PostBuildEvent`, `<Target AfterTargets="Build">`, tareas `<Copy>`, `OutputPath`/`OutDir` con rutas **absolutas** o tokens de **otro cliente**) — porque "compila" no garantiza "no copia binarios a la carpeta de otro cliente"; **(Capa C) Barrido de residuos de port** — grep determinista de los archivos que el Developer **tocó** contra un catálogo de tokens de **otros clientes** del registro de perfiles de Stacky (servidores de BD, rutas, `product_name`/`client_label`) — para atrapar residuos tras portar la estructura de un cliente a otro (ej.: quedó un servidor o una ruta de **Ripley** en un cambio de **Pacífico**). Ambas emiten **findings** tipados (warning/bloqueante) que se anexan al deliverable, aparecen en la UI, y — si son bloqueantes — **bajan el `gate_ok` del 210** (el ticket no avanza a "Build OK"). Núcleo 100% determinista, sin LLM, idéntico en los 3 runtimes.

**Gap que cierra.** Hoy nada en Stacky mira los efectos colaterales del build ni detecta residuos de un cliente en otro; con el trabajo multicliente (Ripley/Pacífico/CREA/…) un port trae residuos silenciosos que "compilan" igual y llegan a QA/ADO como "OK".

**KPI / impacto medible (binarios).**
- **KPI-1 — Detección de PostBuildEvents peligrosos:** 100% de los `.csproj` construidos con un `PostBuildEvent`/`<Copy>`/`AfterTargets` con ruta absoluta o token ajeno producen ≥1 finding. Medible: fixtures de F1 + contador `post_build_inspect.blocking`.
- **KPI-2 — Detección de residuos de port:** dado un archivo cambiado con un token de otro cliente (servidor/ruta), se produce ≥1 finding bloqueante. Medible: fixtures de F2 + contador `port_residue.blocking`.
- **KPI-3 — Cero falsos verdes compuestos:** un build que "compila" pero tiene un residuo bloqueante NO obtiene `gate_ok` (el 210 lo baja). Medible: test de integración F4.
- **KPI-4 — Bajo ruido (DX):** los tokens del catálogo pasan un filtro de distinctividad (len≥4, no-stopword) y se **excluye el proyecto activo** → los findings apuntan a residuos reales, no a auto-referencias. Medible: test de F2 con el propio proyecto (0 findings).
- **KPI-5 — Paridad 3 runtimes:** parsing + catálogo + scan + severidad son Python determinista → idéntico en Codex/Claude/Copilot. Cero LLM.
- **KPI-6 — Cero regresión:** ambas flags OFF → el deliverable/estado queda idéntico al del 210 solo. Ningún test existente se rompe.

---

## 2. Por qué ahora / gap que cierra (anclado en evidencia verificada)

Anclas releídas contra el repo el 2026-07-21:

1. **El 210 verifica el exit code, pero no los efectos colaterales del build.** El `BuildVerdict` del 210 (`services/dev_build_verify.py`, contrato §5 del Plan 210) tiene `ok`/`entry_kind`/`returncode`/`summary_path` — dice "compiló", no "el `.csproj` no copia binarios a `C:\OtroCliente\bin`". Un `PostBuildEvent` con `xcopy` a una ruta ajena **compila con returncode 0** y hoy nadie lo mira.
2. **Stacky es multicliente y ya tiene el registro de perfiles necesario para el catálogo de "otros clientes".** `project_manager.get_all_projects()` (`backend/project_manager.py:39`) devuelve la lista de configs (`projects/<dir>/config.json`), y cada config trae su `client_profile` inline — el loader canónico es `services/client_profile.load_client_profile(project_name)` (`backend/services/client_profile.py:266`), y el perfil tiene `terminology.product_name`/`terminology.client_label` (`Developer.agent.md:54`), `database.server` (`azure_devops.json:23-24`) y `code_layout.online_path`/`batch_path` (`azure_devops.json:3-8`). El proyecto activo se obtiene con `runtime_paths._active_workspace_root()` (`runtime_paths.py:66-103`) / `project_manager.get_active_project()` (`project_manager.py:65`). **La materia prima para detectar "esto es un token de OTRO cliente" ya existe; falta el barrido.**
3. **El Developer porta estructura entre clientes de RS (mismo producto, distinto cliente).** Los agentes `rs-techdev-docs`/`ripley-techdev-docs` trabajan el mismo producto RS sobre distintos clientes (Ripley Oracle, Pacífico SQL Server). Portar una pantalla/lote de un cliente a otro deja residuos (servidor, rutas `trunk/OnLine`, nombres) que "compilan" pero apuntan al cliente equivocado. No hay red de seguridad determinista.
4. **El 210 ya expone la seam exacta para colgar estas inspecciones sin re-tocar el publish.** F5 del Plan 210 define `dev_build_verify.register_evidence_contributor(fn)` y la re-persistencia del veredicto con los `blocking_findings` fusionados, de modo que un finding bloqueante de un contribuidor **baja el `gate_ok`** que el gate de estado (F4 del 210, en `api/tickets.py:530` `_apply_task_state`) lee después. **Este plan solo registra dos contribuidores; no modifica `publish_from_execution` ni `_apply_task_state`.**
5. **Hay patrón determinista de parsing de `.csproj`/`.sln` a reusar.** El scanner del 201 (`services/solution_scanner.py`, F1 del 201) ya lee `.sln`, resuelve `.csproj` y lee heads acotados (`_read_head_bytes`) sin red ni LLM, nunca lanza. La Capa B replica ese patrón para inspeccionar los project files.
6. **Hay patrón de enmascarado de secretos reusable** (Plan 188/195: `secret_masking`) por si un residuo aparece en una línea con credenciales — el evidence se enmascara antes de anexarlo al deliverable. Degrada a truncado si no está disponible.

**Conclusión:** aditivo, determinista, de bajo riesgo. Dos servicios puros nuevos + dos contribuidores registrados en la seam del 210. Nada nuevo en el publish ni en el gate.

---

## 3. Principios y guardarraíles (NO negociables)

- **G1 · Determinista, cero LLM.** Parsing, catálogo, scan y severidad son Python puro. Mismo resultado en los 3 runtimes.
- **G2 · Human-in-the-loop.** Solo **inspecciona y reporta**; no edita código del cliente, no borra, no revierte ports. Los bloqueantes **degradan el estado** (vía el gate del 210), no ejecutan ninguna acción. El operador decide.
- **G3 · Bajo ruido / no degradar DX.** Filtro de distinctividad de tokens (len≥4, stoplist) + exclusión del proyecto activo + caps de findings. Severidad conservadora: bloqueante solo para lo inequívoco (ruta absoluta/token ajeno en build event; servidor/ruta ajena en código). El resto = warning (se ve, no bloquea).
- **G4 · Paridad 3 runtimes.** El núcleo no depende del runtime; se ejecuta server-side al publicar/gatear.
- **G5 · Mono-operador sin auth.** Cero RBAC.
- **G6 · No degradar performance/seguridad/estabilidad.** Lecturas acotadas (`_MAX_FILE_BYTES`, cap de archivos y findings). `git` con args de lista (nunca `shell=True`), degradación a `[]` si no hay repo. Evidence enmascarado (secretos). Nunca lanza hacia el publish (todo `try/except`, patrón del 210 F5).
- **G7 · EXCEPCIÓN DURA #3 heredada del 210.** La Capa B solo corre si hubo build (`verdict.solutions`); si el toolchain faltó (`toolchain_missing`) o el 201 no está (`build_workshop_unavailable`), la Capa B no tiene project files construidos → devuelve vacío (no inventa). La Capa C (residuos) corre igual (escanea fuente, no depende del build).
- **G8 · Config vía UI.** Ambas flags visibles/toggleables en Configuración → Arnés → DevOps.

---

## 4. Flags del arnés (dos, default ON) — cableado EXACTO

| Flag | Capa | Categoría | Default |
|------|------|-----------|---------|
| `STACKY_DEV_POST_BUILD_INSPECT_ENABLED` | B (inspector) | `devops` | **ON** |
| `STACKY_DEV_PORT_RESIDUE_SCAN_ENABLED` | C (residuos) | `devops` | **ON** |

Para **cada** flag, los 5 lugares (idéntico patrón al Plan 210 §4; anclas verificadas 2026-07-21):
1. `services/harness_flags.py` — `FlagSpec(key=..., type="bool", label=..., description=..., group="global", default=True)` en `FLAG_REGISTRY` (`harness_flags.py:379`; `FlagSpec` `:21`).
2. `services/harness_flags.py` — agregar la key a la tupla `_CATEGORY_KEYS["devops"]` (`harness_flags.py:117`, tupla `:202`).
3. `tests/test_harness_flags.py` — agregar la key a `_CURATED_DEFAULTS_ON` (`:467`).
4. `config.py` — atributo `Config`: `<KEY>: bool = os.getenv("<KEY>", "true").lower() in ("1","true","yes")` (patrón `config.py:1192-1194`).
5. `api/devops.py` — en `_health_payload()`: `"post_build_inspect_enabled": bool(getattr(cfg,"STACKY_DEV_POST_BUILD_INSPECT_ENABLED",False)),` y `"port_residue_scan_enabled": ...`.

Labels/descriptions:
- `STACKY_DEV_POST_BUILD_INSPECT_ENABLED` — label "Inspector post-build", desc "Detecta PostBuildEvents, tareas Copy y OutputPath con rutas absolutas o de otros clientes en los .csproj construidos por el Developer."
- `STACKY_DEV_PORT_RESIDUE_SCAN_ENABLED` — label "Barrido de residuos de port", desc "Detecta en los archivos que tocó el Developer tokens (servidores, rutas, nombres) de OTROS clientes del registro de perfiles."

> NO hand-editar `harness_defaults.env`. NO hay `requires=` (ambas `bool`). Health key colateral en `/bootstrap` es intencional (paridad).

---

## 5. Arquitectura objetivo

```
BACKEND (Stacky Agents/backend/)
  services/post_build_inspector.py      (F1) PURO — parsea .csproj/.sln → InspectFinding[]
  services/port_residue_scanner.py       (F2/F3) catálogo de tokens ajenos + _changed_files(git) + scan → ResidueFinding[]
  services/dev_build_contributors.py     (F3) los 2 contribuidores que se registran en la seam del 210 + register(fn)
  app.py                                  (F3) +1 bloque: dev_build_contributors.register(dev_build_verify.register_evidence_contributor)

FRONTEND (Stacky Agents/frontend/src/)
  components/portFindingsModel.ts         (F5) helpers PUROS (agrupar/contar/severidad/label)
  components/portFindingsModel.test.ts    (F5) vitest
  components/OutputPanel.tsx              (F5) pane "Inspección post-build / Residuos" desde execution.metadata.build_findings
```

**Contratos de finding (CONGELADOS por F1/F2):**
```python
@dataclass(frozen=True)
class InspectFinding:
    kind: str        # 'post_build_event' | 'after_targets' | 'copy_task' | 'abs_output_path' | 'foreign_token_in_project'
    severity: str    # 'blocking' | 'warning'
    file: str        # ruta del .csproj/.sln
    detail: str      # explicación legible
    evidence: str    # snippet matcheado, truncado a 200 chars

@dataclass(frozen=True)
class ResidueFinding:
    token: str
    kind: str        # 'server' | 'path' | 'workspace' | 'product' | 'client_label'
    severity: str    # 'blocking' | 'warning'
    file: str
    line: int
    evidence: str    # línea matcheada, enmascarada+truncada
    source_project: str   # de qué otro cliente es el token
```
Ambos se serializan a `dict` (via `asdict`) para fluir por la seam del 210 como `{kind,severity,file,detail}` (mapeo: `InspectFinding.detail`→`detail`; `ResidueFinding` compone `detail = f"token '{token}' de {source_project} ({kind})"`).

---

## 6. Fases

> Convención de tests idéntica al Plan 210 §6 (backend por archivo con el venv; frontend vitest por archivo; registrar cada `test_*.py` en `HARNESS_TEST_FILES`, `run_harness_tests.sh:20`).

---

### F0 — Flags + esqueleto de módulos (gate primero)

**Objetivo:** dejar las 2 flags cableadas (5 lugares c/u §4) y `post_build_inspector.py` / `port_residue_scanner.py` / `dev_build_contributors.py` creados con firmas y dataclasses, sin lógica (stubs que devuelven `[]`). Valor: de-riesga la ceremonia.

**Archivos a editar/crear:** los de §4 (harness_flags ×2, test_harness_flags, config, devops.py) + los 3 módulos backend (stubs con los dataclasses de §5 y firmas públicas devolviendo `[]`).

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan211_flags.py`:**
- `test_both_flags_registered_and_curated` (ambas keys en `FLAG_REGISTRY`, `_CATEGORY_KEYS["devops"]`, `_CURATED_DEFAULTS_ON`).
- `test_health_exposes_both_flags` (`/api/devops/health` incluye `post_build_inspect_enabled` y `port_residue_scan_enabled`).
- `test_modules_import_clean` (importar los 3 módulos no lanza; `inspect_projects([], workspace_root="x") == []`).
- Registrar en `HARNESS_TEST_FILES`. Correr: `& ".venv\Scripts\python.exe" -m pytest tests\test_plan211_flags.py tests\test_harness_flags.py -q`

**Criterio BINARIO:** comando verde; `grep -rn "STACKY_DEV_POST_BUILD_INSPECT_ENABLED\|STACKY_DEV_PORT_RESIDUE_SCAN_ENABLED" "Stacky Agents/backend/config.py"` → 2 matches.

**Flag:** ambas (default ON). **Runtime:** idéntico 3/3. **Operador:** ninguno.

---

### F1 — Inspector post-build (`post_build_inspector.py`, Capa B)

**Objetivo:** función pura que parsea los project files construidos y emite findings por efectos colaterales peligrosos. Valor: "compila" ya no oculta un `PostBuildEvent` que copia a otro cliente.

**Archivo a editar:** `Stacky Agents/backend/services/post_build_inspector.py`.

**API pública:**
```python
def inspect_projects(project_files: list[str], *, workspace_root: str,
                     foreign_tokens: dict | None = None) -> list[InspectFinding]
```
- `project_files`: rutas de `.csproj`/`.sln` construidos (el contribuidor F3 los deriva de `verdict.solutions` + resolución `.sln→.csproj`).
- `foreign_tokens`: catálogo opcional de la Capa C (para elevar a bloqueante un build event que menciona a otro cliente). Si None, se usa `{}`.

**Constantes:**
```python
_MAX_FILE_BYTES = 262144
_ABS_WIN_RE = re.compile(r'([A-Za-z]:[\\/]|\\\\[^\\/])')     # C:\... o UNC \\server
_POST_BUILD_RE = re.compile(r'(?is)<PostBuildEvent>(.*?)</PostBuildEvent>')
_TARGET_AFTER_RE = re.compile(r'(?is)<Target\b[^>]*\b(?:AfterTargets|BeforeTargets)\s*=\s*"[^"]*Build[^"]*"[^>]*>(.*?)</Target>')
_COPY_RE = re.compile(r'(?is)<Copy\b[^>]*?(DestinationFolder|DestinationFiles)\s*=\s*"([^"]*)"')
_OUTPUT_RE = re.compile(r'(?is)<(OutputPath|OutDir)>([^<]*)</(?:OutputPath|OutDir)>')
```

**Reglas de severidad (deterministas):**
- `<PostBuildEvent>` presente: si su contenido matchea `_ABS_WIN_RE` o `_contains_foreign(content, foreign_tokens)` → `blocking` (`kind="post_build_event"`); si no (relativo, benigno) → `warning`.
- `<Target AfterTargets/BeforeTargets="...Build...">`: si el cuerpo tiene abs path o token ajeno → `blocking` (`kind="after_targets"`); si contiene `<Exec>`/`<Copy>` pero relativo → `warning`; sin tareas relevantes → sin finding.
- `<Copy DestinationFolder|DestinationFiles="X">`: `X` abs o token ajeno → `blocking` (`kind="copy_task"`); relativo → `warning`.
- `<OutputPath>`/`<OutDir>` con valor abs o token ajeno → `warning` por default; **`blocking`** solo si el valor contiene un token ajeno (`kind="abs_output_path"`). (Un OutputPath absoluto propio es común; ajeno es residuo.)
- Errores por archivo (no existe, no lee) → se saltan (nunca propaga).

**Helpers:**
```python
def _read_head(path):
    try:
        with open(path, "rb") as fh: return fh.read(_MAX_FILE_BYTES).decode("utf-8", errors="replace")
    except OSError: return ""
def _is_abs(s): return bool(_ABS_WIN_RE.search(s or ""))
def _contains_foreign(text, foreign_tokens):
    low = (text or "").lower()
    return next((tok for tok in (foreign_tokens or {}) if tok in low), None)
def _trunc(s, n=200): return (s or "").strip()[:n]
```

**Casos borde:** `project_files` vacío → `[]`; `.csproj` sin eventos → `[]`; `PostBuildEvent` relativo (`copy $(TargetPath) ..\shared`) → `warning`; abs (`xcopy "C:\Ripley\bin"`) → `blocking`; `foreign_tokens` con "ripley" y el evento lo menciona → `blocking` con `kind` acorde.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan211_inspector.py`:** (fixtures `.csproj` en `tmp_path`)
- `test_empty_returns_empty`
- `test_post_build_absolute_is_blocking`
- `test_post_build_relative_is_warning`
- `test_copy_task_absolute_is_blocking`
- `test_after_targets_with_foreign_token_blocking` (pasar `foreign_tokens={"ripley": {...}}`)
- `test_output_path_foreign_token_blocking_vs_own_absolute_warning`
- `test_unreadable_file_skipped_no_crash`
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -nE "import requests|copilot|llm" "Stacky Agents/backend/services/post_build_inspector.py"` → 0 matches.

**Flag:** el servicio no chequea flag (lo hace el contribuidor F3). **Runtime:** idéntico 3/3. **Operador:** ninguno.

---

### F2 — Barrido de residuos de port (`port_residue_scanner.py`, Capa C)

**Objetivo:** construir el catálogo de tokens de **otros clientes** y escanear los archivos que el Developer tocó. Valor: atrapar el residuo Ripley→Pacífico.

**Archivo a editar:** `Stacky Agents/backend/services/port_residue_scanner.py`.

**API pública:**
```python
def build_foreign_token_catalog(active_project: str | None) -> dict
# {token_lower: {"source_project": str, "kind": "server"|"path"|"workspace"|"product"|"client_label"}}
def scan_files_for_foreign_tokens(files: list[str], catalog: dict, *, workspace_root: str) -> list[ResidueFinding]
```

**Constantes:**
```python
_MIN_TOKEN_LEN = 4
_STOPWORDS = {"online","batch","test","tests","src","app","main","code","data","trunk",
              "azure","devops","http","https","true","false","null","none","core","base",
              "prod","dev","qa","release","debug","windows","system","server","local"}
_SOURCE_EXTS = (".cs",".vb",".csproj",".sln",".config",".sql",".aspx",".cshtml",".razor",".resx")
_MAX_FILE_BYTES = 524288
_MAX_FINDINGS = 200
_SEVERITY = {"server":"blocking","path":"blocking","workspace":"blocking",
             "product":"warning","client_label":"warning"}
```

**`build_foreign_token_catalog` (deterministic):**
```python
def build_foreign_token_catalog(active_project):
    from project_manager import get_all_projects, get_active_project
    from runtime_paths import _active_workspace_root
    active_ws = os.path.normpath(str(_active_workspace_root() or ""))
    active_name = (active_project or get_active_project() or "").strip().lower()
    catalog = {}
    for cfg in get_all_projects():                     # cada cfg = projects/<dir>/config.json
        name = str(cfg.get("name") or cfg.get("project_name") or "").strip()
        ws = os.path.normpath(str(cfg.get("workspace_root") or ""))
        if (name and name.lower() == active_name) or (ws and ws == active_ws):
            continue                                   # excluir el proyecto ACTIVO (auto-referencias)
        prof = cfg.get("client_profile") or {}
        term = prof.get("terminology") or {}
        db = prof.get("database") or {}
        cl = prof.get("code_layout") or {}
        _add(catalog, db.get("server"), name, "server")
        _add(catalog, term.get("product_name"), name, "product")
        _add(catalog, term.get("client_label"), name, "client_label")
        _add(catalog, os.path.basename(ws) if ws else "", name, "workspace")
        for p in (cl.get("online_path"), cl.get("batch_path"), cl.get("lib_path")):
            _add_path_tokens(catalog, p, name, "path")
    return catalog

def _add(catalog, value, source, kind):
    tok = (value or "").strip().lower()
    if len(tok) >= _MIN_TOKEN_LEN and tok not in _STOPWORDS and re.search(r'[a-z0-9]', tok):
        catalog.setdefault(tok, {"source_project": source, "kind": kind})

def _add_path_tokens(catalog, path, source, kind):
    # separa 'trunk/OnLine' -> ['trunk','onlin e'...]; solo agrega segmentos distintivos
    for seg in re.split(r'[\\/]+', (path or "")):
        _add(catalog, seg, source, kind)
```
- Nota: los segmentos comunes (`trunk`, `online`) caen por el stoplist → no se agregan. Sobreviven los distintivos (nombres de cliente, servidores).

**`scan_files_for_foreign_tokens`:**
```python
def scan_files_for_foreign_tokens(files, catalog, *, workspace_root):
    if not catalog: return []
    out = []
    for rel in files:
        if not rel.lower().endswith(_SOURCE_EXTS): continue
        path = rel if os.path.isabs(rel) else os.path.join(workspace_root, rel)
        text = _read_text(path)                       # <= _MAX_FILE_BYTES, errors='replace', OSError→""
        if not text: continue
        low = text.lower()
        for tok, meta in catalog.items():
            if tok in low:
                ln, evidence = _first_line_with(text, tok)
                out.append(ResidueFinding(
                    token=tok, kind=meta["kind"], severity=_SEVERITY.get(meta["kind"],"warning"),
                    file=path, line=ln, evidence=_mask(_trunc(evidence)),
                    source_project=meta["source_project"]))
                if len(out) >= _MAX_FINDINGS: return out
    return out
```
- `_mask(s)`: `try: from services.secret_masking import mask_secrets; return mask_secrets(s) except Exception: return s` (reuso Plan 188/195; degrada a sin-enmascarar+truncado). El implementador confirma el nombre real del helper de masking grepeando `def mask` en `services/secret_masking*.py`; si difiere, ajustar el import (fallback: truncado).
- `_first_line_with(text, tok)`: itera líneas, devuelve `(nro_linea_1based, linea)` de la primera que contiene `tok` (case-insensitive).

**`_changed_files` (resolver determinista de archivos tocados — se define acá, lo usa el contribuidor F3):**
```python
def changed_files(workspace_root: str | None) -> list[str]:
    # git-only, determinista, degrada a [] si no hay repo. NUNCA lanza. Args de lista (no shell).
    if not workspace_root or not os.path.isdir(workspace_root): return []
    porcelain = _git(workspace_root, ["status","--porcelain","--untracked-files=all"])
    files = _parse_porcelain(porcelain)               # paths modificados/agregados/untracked
    if not files:
        last = _git(workspace_root, ["show","--name-only","--pretty=format:","HEAD"])
        files = [l.strip() for l in last.splitlines() if l.strip()]
    return [f for f in files if f.lower().endswith(_SOURCE_EXTS)]

def _git(ws, args):
    try:
        p = subprocess.run(["git","-C",ws,*args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        return p.stdout if p.returncode == 0 else ""
    except Exception:
        return ""
```

> **Nota sobre la identidad del proyecto:** la exclusión del proyecto activo es robusta por el **match de `workspace_root` normalizado** (`ws == active_ws`), independiente de que el `config.json` tenga o no una clave `name`/`project_name`. Si esa clave falta, `source_project` queda `""` (solo cosmético en el label del finding); la exclusión NO se ve afectada. Si se quiere el nombre siempre, el implementador puede enumerar los directorios de `projects/` (el nombre del proyecto = nombre de carpeta) — sub-decisión opcional, no requerida.

**Casos borde:** catálogo vacío (proyecto único) → `[]`; el proyecto ACTIVO no aporta tokens (excluido por ws-match) → 0 auto-findings; token en stoplist (`online`) → no está en catálogo; archivo no-fuente → se salta; sin git → `changed_files → []` (Capa C no aplica, no crashea); línea con credencial → evidence enmascarado.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan211_residue.py`:** (monkeypatch `project_manager.get_all_projects` con 2-3 configs fake; `tmp_path` con archivos fuente)
- `test_catalog_excludes_active_project` (config activo + 1 ajeno → tokens solo del ajeno)
- `test_catalog_applies_stoplist_and_minlen` ("online"/"src" NO entran; "pacifico"/servidor sí)
- `test_scan_flags_foreign_server_blocking` (archivo con el servidor de otro cliente → finding blocking `kind="server"`)
- `test_scan_flags_foreign_path_blocking`
- `test_scan_client_label_is_warning`
- `test_scan_own_tokens_zero_findings` (archivo con tokens del proyecto activo → 0 findings)
- `test_changed_files_degrades_without_git` (`workspace_root` sin `.git` → `[]`)
- `test_evidence_is_masked_or_truncated`
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -n "shell=True" "Stacky Agents/backend/services/port_residue_scanner.py"` → 0 matches.

**Flag:** el contribuidor F3 gatea. **Runtime:** idéntico 3/3. **Operador:** ninguno.

---

### F3 — Contribuidores + registro en la seam del 210 (`dev_build_contributors.py`)

**Objetivo:** empaquetar Capa B y Capa C como los dos contribuidores que el 210 invoca al anotar el deliverable, cada uno gateado por su flag. Valor: los findings fluyen al deliverable y al `gate_ok` sin tocar el publish.

**Archivo a crear:** `Stacky Agents/backend/services/dev_build_contributors.py`.

**API:**
```python
def register(register_fn) -> None:
    # register_fn == dev_build_verify.register_evidence_contributor
    register_fn(_inspect_contributor)
    register_fn(_residue_contributor)

def _inspect_contributor(ado_id: int, verdict) -> dict:
    import config as _config
    if not getattr(_config.config, "STACKY_DEV_POST_BUILD_INSPECT_ENABLED", False):
        return _empty()
    ws = _workspace_root_for_ado(ado_id)              # helper compartido (mismo del 210 F5)
    if not verdict.solutions: return _empty()          # G7: sin build no hay project files
    project_files = _project_files_for_solutions(verdict.solutions, ws)  # .sln + .csproj resueltos (reusa solution_scanner)
    foreign = port_residue_scanner.build_foreign_token_catalog(None)
    findings = post_build_inspector.inspect_projects(project_files, workspace_root=str(ws or ""), foreign_tokens=foreign)
    return _to_contribution("Inspección post-build", findings_to_dicts(findings))

def _residue_contributor(ado_id: int, verdict) -> dict:
    import config as _config
    if not getattr(_config.config, "STACKY_DEV_PORT_RESIDUE_SCAN_ENABLED", False):
        return _empty()
    ws = _workspace_root_for_ado(ado_id)
    catalog = port_residue_scanner.build_foreign_token_catalog(None)
    files = port_residue_scanner.changed_files(str(ws or ""))
    findings = port_residue_scanner.scan_files_for_foreign_tokens(files, catalog, workspace_root=str(ws or ""))
    return _to_contribution("Residuos de port entre clientes", residue_to_dicts(findings))
```
- `_to_contribution(title, dicts)`: separa `blocking = [d for d in dicts if d["severity"]=="blocking"]`, `warnings = [...]`, arma `section_html` (una `<table>` con file/severity/detail; verde/amarillo/rojo según haya blocking) y devuelve `{"title": title, "section_html": html, "blocking": blocking, "warnings": warnings}`.
- `_empty()`: `{"title":"","section_html":"","blocking":[],"warnings":[]}`.
- `_workspace_root_for_ado(ado_id)`: **importar el helper público del 210** — `from services.dev_build_verify import workspace_root_for_ado` (declarado público en el Plan 210 F3, resuelve `Ticket.stacky_project_name` → `workspace_root`). Una sola implementación; NO replicar.
- `_project_files_for_solutions(solutions, ws)`: para cada `.sln`, agregar la `.sln` + sus `.csproj` (via `solution_scanner._parse_sln_projects` o `scan_solutions_ex`); degrada a solo las `.sln` si el scanner no está.

**Registro en `app.py`** (junto al bloque de post-hooks, `app.py:853-855`):
```python
# Plan 211 — inspector post-build + residuos de port como contribuidores de evidencia del build (Plan 210).
from services import dev_build_verify, dev_build_contributors
dev_build_contributors.register(dev_build_verify.register_evidence_contributor)
```

**Casos borde:** flag B OFF → `_inspect_contributor` vacío; flag C OFF → `_residue_contributor` vacío; sin build (`verdict.solutions == []`) → inspector vacío, residuos igual corre; sin git → residuos vacío. Un blocking de cualquiera baja `gate_ok` (mecanismo del 210 F5: `annotate_build_evidence` fusiona `blocking` y re-persiste el veredicto → gate de estado del 210 lo lee).

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan211_contributors.py`:** (monkeypatch `post_build_inspector.inspect_projects`, `port_residue_scanner.*`, `_workspace_root_for_ado`, `_config.config`)
- `test_inspect_contributor_off_returns_empty`
- `test_residue_contributor_off_returns_empty`
- `test_inspect_skips_when_no_solutions`
- `test_contribution_shape` (devuelve keys `title/section_html/blocking/warnings`)
- `test_blocking_finding_present_in_contribution`
- `test_register_calls_register_fn_twice` (un fake `register_fn` recibe 2 callables)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -rn "dev_build_contributors.register" "Stacky Agents/backend/app.py"` → 1 match.

**Flag:** ambas. **Runtime:** idéntico 3/3. **Operador:** ninguno.

---

### F4 — Integración con el gate del 210 (findings bloquean el "Build OK")

**Objetivo:** verificar de punta a punta que un finding bloqueante de este plan baja el `gate_ok` del 210 y, por ende, el estado no avanza y el deliverable sale en rojo. Valor: el falso verde compuesto ("compila pero tiene residuo") queda cerrado.

**Archivos:** ninguno nuevo (el mecanismo lo provee el 210 F5). Esta fase es **de integración/test**: confirma el cableado.

> **Sub-paso de metadata para la UI (F5):** al fusionar findings, `annotate_build_evidence` del 210 debe además escribir un resumen en `execution.metadata["build_findings"]` = `{"blocking": N, "warnings": M, "items": [ {kind,severity,file,detail} ... cap 50 ]}` para que el pane de F5 lo lea. Si el 210 aún no escribe esa metadata, agregar la escritura en el punto donde el 210 re-persiste el veredicto (es 1 línea; backward-compatible). Documentar como dependencia hacia el 210.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan211_integration.py`:** (usa las funciones reales del 210 `annotate_build_evidence` + `read_verdict`, con contribuidores reales monkeypatcheados para devolver un blocking)
- `test_blocking_residue_flips_gate_ok_false` (verdict inicial `gate_ok True`; registrar un contribuidor que devuelve un `blocking` → tras `annotate_build_evidence`, `read_verdict(...).gate_ok is False` y `blocking_findings` no vacío)
- `test_warning_only_keeps_gate_ok_true` (contribuidor con solo `warnings` → `gate_ok` sigue True, pero el warning aparece en el HTML)
- `test_deliverable_html_lists_findings` (el HTML anotado contiene la tabla de findings)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; un blocking de 211 produce `gate_ok False` en el veredicto re-persistido (el gate de estado del 210 F4 lo lee → downgrade).

**Flag:** ambas. **Runtime:** idéntico 3/3. **Operador:** ninguno.

---

### F5 — Pane de findings en la UI (default ON)

**Objetivo:** mostrar los findings al operador junto al veredicto de build. Valor: el operador ve el residuo/efecto colateral de un vistazo.

**Archivos a crear/editar:**
- `Stacky Agents/frontend/src/components/portFindingsModel.ts` — PUROS: `groupBySeverity(items)`, `severityColor(sev): 'red'|'amber'|'gray'`, `findingLabel(kind): string`, `countBlocking(items): number`. Sin `style={{}}` inline.
- `Stacky Agents/frontend/src/components/portFindingsModel.test.ts` — vitest por función.
- `Stacky Agents/frontend/src/components/OutputPanel.tsx` — leer `execution.metadata.build_findings` (poblado en F4) y renderizar un pane con la lista (rojo si hay blocking). Solo `agentType === "developer"` y si hay items.

**Casos borde:** sin `build_findings` → pane no aparece; solo warnings → pane ámbar; con blocking → pane rojo.

**Tests (TDD) — `portFindingsModel.test.ts`:** un `it` por función (grupos, color, label, conteo). Correr: `npx vitest run src\components\portFindingsModel.test.ts`.

**Criterio BINARIO:** comando verde; `tsc` del frontend sin errores nuevos (memoria `gotcha-rtl-jsdom-structural-gap`: validar con `tsc` + modelo puro, no RTL).

**Flag:** el pane depende de la metadata (poblada con flags ON). **Runtime:** N/A (UI). **Operador:** ninguno; ve el pane solo.

---

## 5-bis. Orden de implementación

F0 → F1 → F2 → F3 → F4 → F5. F1 y F2 son independientes entre sí; F3 depende de ambas + de la seam del 210 (F5 del 210); F4 valida la integración; F5 depende de la metadata que F4 asegura. **Prerequisito externo duro:** Plan 210 implementado (la seam `register_evidence_contributor` + la re-persistencia del veredicto). Si el 210 no está, F3/F4 no tienen dónde engancharse → **no implementar 211 antes que 210.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|-----------|
| R1 | Falsos positivos de residuos (token común de otro cliente que también es legítimo acá). | Filtro de distinctividad (len≥4 + stoplist) + exclusión del proyecto activo + severidad conservadora (bloqueante solo server/path/workspace). Warnings no bloquean. Follow-up: allowlist de supresión por proyecto. |
| R2 | El proyecto no es git → Capa C no ve archivos tocados. | `changed_files` degrada a `[]` (Capa C no aplica, no crashea). La Capa B (inspector) no depende de git. |
| R3 | Muchos archivos/tokens → scan lento. | Caps: `_MAX_FILE_BYTES`, `_MAX_FINDINGS`, filtro a `_SOURCE_EXTS`, corte temprano. Corre post-run (no en hot path). |
| R4 | Un residuo aparece en una línea con secretos → se filtra al deliverable. | `_mask` (reuso `secret_masking`) antes de anexar; degrada a truncado. |
| R5 | La Capa B eleva a bloqueante un `OutputPath` absoluto legítimo del propio proyecto. | Regla: `OutputPath` absoluto propio = warning; bloqueante SOLO si contiene token ajeno. Documentado en F1. |
| R6 | Doble registro de contribuidores (app recargada en tests). | `register` es idempotente por identidad de función; los tests que importan `app` no deben duplicar (usar el fake `register_fn`). |
| R7 | Divergencia en la resolución de workspace entre 210 y 211. | El 210 F3 expone `workspace_root_for_ado` **público**; 211 lo importa (F3). Una sola implementación, cero replicación. |

---

## 7. Fuera de scope (explícito)

- **NO** repara ni revierte residuos ni edita `.csproj` (G2: solo reporta).
- **NO** implementa el gate de estado ni el publish (eso es Plan 210; este plan solo aporta findings a la seam).
- **NO** compila nada (usa el build que ya hizo el 210/201).
- **NO** escanea proyectos que no son fuente RS (filtra por `_SOURCE_EXTS`).
- **NO** agrega RBAC/multiusuario (G5).
- **NO** hand-edita `harness_defaults.env`.

---

## 8. Glosario + DoD

**Glosario:**
- **Residuo de port** — token de OTRO cliente (servidor, ruta, nombre) que quedó en el código tras portar estructura entre clientes RS.
- **Catálogo de tokens ajenos** — tokens distintivos de todos los perfiles EXCEPTO el activo (`build_foreign_token_catalog`).
- **Efecto colateral de build** — `PostBuildEvent`/`AfterTargets`/`Copy`/`OutputPath` que hace algo más que compilar (copiar binarios, escribir fuera del árbol).
- **Contribuidor de evidencia** — función registrada en la seam del 210 que suma findings/HTML al veredicto de build.
- **Finding bloqueante** — baja el `gate_ok` del 210 → el ticket no avanza a "Build OK".

**Definition of Done (binario):**
1. Los 6 archivos de test (`test_plan211_flags`, `_inspector`, `_residue`, `_contributors`, `_integration`, + `portFindingsModel.test.ts`) → **verdes**, por archivo con el venv, todos los `test_plan211_*.py` en `HARNESS_TEST_FILES`.
2. `grep -rn "dev_build_contributors.register" "Stacky Agents/backend/app.py"` → 1 match.
3. `grep -n "shell=True" "Stacky Agents/backend/services/port_residue_scanner.py"` → 0 matches.
4. Con ambas flags OFF: el deliverable/estado queda idéntico al del 210 solo (KPI-6); ningún test existente se rompe.
5. Test de integración F4: un blocking de 211 produce `gate_ok False` en el veredicto re-persistido.
6. **Smoke E2E (manual, pendiente):** correr un developer sobre un proyecto con un `.csproj` que tenga un `PostBuildEvent` a ruta absoluta y un archivo con un servidor de otro cliente → el deliverable lista ambos findings, el `gate_ok` es False y el ticket no avanza. (Depende de 210 + 201 mergeados.)

**Trabajo del operador:** ninguno (opt-in default ON; ambas flags toggleables desde Configuración → Arnés → DevOps; degrada a vacío si no hay build/git).
