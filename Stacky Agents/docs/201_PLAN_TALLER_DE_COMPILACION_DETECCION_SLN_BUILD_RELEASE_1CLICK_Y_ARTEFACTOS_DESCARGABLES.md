# Plan 201 — Taller de Compilación: detección de `.sln`, build en Release 1-click y artefactos descargables

> Estado: PROPUESTO v1 (2026-07-18). Pipeline: proponer → **[este paso]** → criticar (`criticar-y-mejorar-plan`) → implementar (`implementar-plan-stacky`) → supervisar.
> Autor: StackyArchitectaUltraEficientCode (perfil normal, heredado de Opus 4.8).
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro (paridad obligatoria; el núcleo NO usa LLM).

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Agregar al dashboard de despliegue un panel nuevo **"Compilar"** (Taller de Compilación) que, con puros clicks y **cero tipeo**, (a) **detecta determinísticamente** todas las soluciones `.sln` del workspace del proyecto activo y las lista con sus proyectos (`.csproj`/`.vbproj`) clasificados por tipo, (b) **guarda esas ubicaciones** de forma idempotente para que el operador solo tenga que **tildar** qué soluciones trackear, (c) **compila en Release** cada solución seleccionada dejando una **carpeta artefacto descargable** por-sln, o un **artefacto unificado** de todas las que el operador seleccione, y (d) ofrece un botón **"Usar como app de despliegue"** que registra esa carpeta en el Centro de Despliegues (Plan 120) cerrando el lazo **compilar → desplegar → rollback**. La compilación depende de un toolchain .NET (MSBuild/.NET SDK) que **no está garantizado** en una instalación default: por eso el build **se auto-gatea con detección de capacidad** y, si el toolchain falta, **degrada a un "doctor"** con instrucciones — nunca crashea, nunca auto-instala nada.

**Gap que cierra.** El Centro de Despliegues (Plan 120: `Stacky Agents/backend/api/devops_deployments.py`, `Stacky Agents/frontend/src/components/devops/DeploymentsSection.tsx`, modelo puro `Stacky Agents/frontend/src/components/devops/deploymentsModel.ts:14-19`) SOLO despliega artefactos **ya compilados** (`DeployApp.artifact = { kind:'folder'|'zip'; path }`) a destinos locales/remotos, con ledger, rollback y DORA. **Ninguna** pieza compila desde fuente. Hoy el operador tiene que abrir Visual Studio a mano, compilar Release, ubicar `bin/Release`, comprimir y recién ahí crear una `DeployApp` **tipeando** id y ruta absoluta. Este plan construye la **etapa previa que hoy no existe** y la conecta al Plan 120.

**KPI / impacto medible.**
- **Tipeo:** de escribir manualmente `id` + ruta absoluta del artefacto (2 campos, propenso a error) a **0 caracteres tipeados**.
- **Clicks:** de "abrir VS + build + explorar + zip + crear app" (proceso multi-herramienta de minutos) a **4 clicks** dentro de Stacky: `Escanear` → tildar solución(es) → `Compilar` → `Descargar` (o `Usar como app de despliegue`).
- **Cobertura de detección:** el operador ve **el 100%** de los `.sln` del workspace sin conocer su ubicación de antemano (antes: 0% asistido, todo manual).
- **Paridad de runtimes:** 3/3 idénticos en el núcleo (scan + build son deterministas, sin LLM).

---

## 2. Por qué ahora / gap que cierra (anclado en evidencia)

1. **El Plan 120 ya provee el consumidor exacto** de lo que este plan produce. `deploymentsModel.ts:14-19` define `DeployApp { id; name?; artifact:{ kind:'folder'|'zip'; path }; targets }`. Una carpeta artefacto con `kind:'folder'` + `path` absoluto es literalmente lo que `deploy_executor` copia a los destinos. Falta **quién produce esa carpeta**.
2. **Ya existe el patrón determinista a reusar** para el scanner: `Stacky Agents/backend/services/pipeline_stack_detector.py:19-55` (Plan 97). Es **puro** respecto del resultado (único I/O = lectura de disco), usa `os.walk` con profundidad limitada (`pipeline_stack_detector.py:32-34`), ignora carpetas pesadas (`:36-37`), topa en 500 entradas (`:40`), **nunca lanza** (`OSError → None`, `:54`) y ya mapea `.sln`/`.csproj` → `'dotnet'` (`:15`). El scanner nuevo replica **este mismo patrón**.
3. **Ya existe la resolución de raíz correcta:** `Stacky Agents/backend/runtime_paths.py:66-103` `_active_workspace_root()` lee `projects/<active>/config.json → workspace_root`. Es la raíz donde escanear. No se reinventa.
4. **Ya existe el registro declarativo de secciones DevOps** (`Stacky Agents/frontend/src/pages/DevOpsPage.tsx:97-179`): agregar una sección = **una entrada** en `DEVOPS_SECTIONS` + un componente, sin refactor.
5. **Ya existe el patrón de logs vivos** (`Stacky Agents/backend/log_streamer.py:21-120`), la persistencia de apps idempotente (`Stacky Agents/backend/services/deploy_store.py:70-83`) y la validación de app (`Stacky Agents/backend/services/deploy_planner.py:30-50`) que el bridge reutiliza tal cual.

**Conclusión:** el trabajo es **aditivo y de bajo riesgo**: dos servicios deterministas nuevos (scanner, builder) + detección de toolchain + un blueprint + una sección UI + un bridge de un botón. Nada modifica el Plan 120 ni `build_release.ps1`.

---

## 3. Principios y guardarraíles (NO negociables — codificados en cada fase)

- **G1 · Cero trabajo extra al operador.** Todo por clicks. Sin tipeo. Sin nueva carga de configuración obligatoria. Backward-compatible.
- **G2 · Human-in-the-loop innegociable.** Nada se auto-escanea, auto-compila ni auto-despliega. Cada acción es un click explícito del operador. `Compilar`, `Descargar` y `Usar como app de despliegue` **exigen `confirm:true`** en el body (patrón `devops_deployments.py:6-7`).
- **G3 · Determinista-primero, LLM opcional.** El núcleo (scan + clasificación + build) **no toca ningún LLM** → idéntico en los 3 runtimes. El enriquecimiento con LLM (nombres amigables) es **best-effort, opt-in por request (`enrich:true`), y degrada en silencio** a la heurística determinista si el runtime no está disponible (F11).
- **G4 · Paridad de 3 runtimes.** Cada ítem funciona igual en Codex/Claude/Copilot o degrada con fallback explícito. El único punto que roza un LLM es F11, aislado y con fallback.
- **G5 · Mono-operador sin auth.** Cero RBAC, cero multiusuario. `current_user` es informativo.
- **G6 · No degradar performance/seguridad/estabilidad/DX.** Scanner y detección son **read-only** y acotados (topes de profundidad/entradas). El build produce **carpetas nuevas** (no destructivo). Servir zips para descarga **valida path-traversal** (F7). Se **reusa** todo lo existente; no se reinventa.
- **G7 · EXCEPCIÓN DURA #3 (prerequisito no garantizado).** La **ejecución** del build depende de MSBuild/.NET SDK, ausente en instalación default. Esto NO se respeta apagando la feature, sino **degradando de forma controlada**: la flag queda **default ON** (detección/catálogo/UI son read-only y seguras), y el botón `Compilar` **se auto-gatea con detección de capacidad** (`vswhere`/`dotnet`); si el toolchain falta, muestra **doctor + no-op**, con fallback explícito. Citada en F3, F5, F6.
- **G8 · Config vía UI.** La flag `STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED` es visible/toggleable desde **Configuración → Arnés → categoría DevOps** (queda cableada en `harness_flags.py`, no solo env var).

---

## 4. Flag del arnés (una sola, default ON) — cableado EXACTO en 5 lugares

**Flag nueva:** `STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED` · tipo `bool` · **default ON** · categoría `devops` · sin `requires`.

> **GOTCHA DURO (memoria "Receta flag DEVOPS default-ON = 5 lugares").** Una `FlagSpec` con `default=True` DEBE estar curada, o el meta-test `test_default_known_only_for_curated` (`Stacky Agents/backend/tests/test_harness_flags.py:758-772`) se pone rojo. El default EFECTIVO en runtime lo da `config.py` (leído vía la **instancia** `config.config`, NO el módulo). Toda flag nueva DEBE estar categorizada o `test_every_registry_flag_is_categorized` se rompe.

Los 5 lugares (todos obligatorios; F0 los hace de una para de-riesgar):

| # | Archivo | Qué agregar | Ancla de referencia |
|---|---------|-------------|---------------------|
| 1 | `Stacky Agents/backend/services/harness_flags.py` | Una `FlagSpec(key="STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED", type="bool", label="Taller de Compilación", description="Detecta soluciones .sln del workspace, compila en Release y produce artefactos descargables (build requiere toolchain .NET).", group="global", default=True)` dentro de `FLAG_REGISTRY`. | `FlagSpec` = `harness_flags.py:21-42` |
| 2 | `Stacky Agents/backend/services/harness_flags.py` | Agregar `"STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED",` a la tupla `_CATEGORY_KEYS["devops"]`. | `harness_flags.py:199-216` |
| 3 | `Stacky Agents/backend/tests/test_harness_flags.py` | Agregar `"STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED",` al conjunto `_CURATED_DEFAULTS_ON` (hay exactamente uno). | `test_harness_flags.py:467` |
| 4 | `Stacky Agents/backend/config.py` | Nuevo atributo de `Config`: `STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED: bool = os.getenv("STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED", "true").lower() == "true"` — **espejá exactamente** la forma de `STACKY_DEVOPS_SERVERS_ENABLED`. | `config.py:1196-1197` (patrón default "true") |
| 5 | `Stacky Agents/backend/api/devops.py` | En el dict del endpoint `/devops/health`, agregar `"build_workshop_enabled": bool(getattr(cfg, "STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED", False)),`. | `devops.py:45,58,65` (patrón `*_enabled`) |

> **NO hand-editar** `Stacky Agents/backend/harness_defaults.env` (memoria: lo genera `Stacky Agents/deployment/export_harness_defaults.py`, prohibido a mano). El default ON efectivo ya lo da `config.py` (lugar #4); el `.env` horneado no es necesario para que la flag arranque ON en dev.
> **NO** hay arista `requires=`, así que **NO** se toca `_REQUIRES_MAP_FROZEN` ni bounds-map (es `bool`, no `int`).

---

## 5. Arquitectura objetivo (mapa de artefactos nuevos)

```
BACKEND (Stacky Agents/backend/)
  services/solution_scanner.py       (F1) PURO — os.walk determinista → catálogo de .sln + proyectos clasificados
  services/solution_store.py         (F2) persistencia idempotente del catálogo + selección (tracked) por workspace
  services/build_toolchain.py        (F3) detección de capacidad (vswhere→MSBuild / dotnet) + remediation "doctor"
  services/solution_builder.py       (F5) build Release por-sln + unificado, log vivo en memoria, timeout+cancelación
  services/solution_enricher.py      (F11, OPCIONAL) enriquecimiento LLM best-effort con fallback determinista
  api/devops_build_workshop.py       (F4/F6/F7/F8) blueprint /devops/build (scan, catalog, track, doctor, compile, status, cancel, download, register-deploy-app)

FRONTEND (Stacky Agents/frontend/src/)
  components/devops/buildWorkshopModel.ts        (F9) helpers PUROS testeables (sin render)
  components/devops/buildWorkshopModel.test.ts   (F9) vitest del modelo puro
  components/devops/BuildWorkshopSection.tsx     (F10) UI de la sección
  pages/DevOpsPage.tsx                            (F0) +1 entrada en DEVOPS_SECTIONS
  api/endpoints.ts                                (F10) +objeto DevOpsBuildWorkshop (espejo de DevOpsDeployments)
  components/devops/__tests__/BuildWorkshopSection.test.ts (F10) presencia de la sección + gate

DATOS (data_dir() = Stacky Agents/backend/data/ en dev)
  data/build_solutions.json          catálogo persistido + selección (F2)
  data/build_artifacts/<slug>/<ts>/  staging del build por-sln (F5)
  data/build_artifacts/unified/<ts>/ staging del build unificado (F6)
  data/build_runs.jsonl              ledger append-only de builds (F6) — permite descargar tras reinicio
```

**Contrato de datos del catálogo** (persistido en `data/build_solutions.json`, schema congelado por F2):

```json
{
  "<workspace_root_absoluto>": {
    "scanned_at": "2026-07-18T12:00:00Z",
    "solutions": [
      {
        "slug": "mi-solucion",
        "sln_path": "N:\\ws\\src\\MiSolucion.sln",
        "sln_name": "MiSolucion",
        "friendly_name": "Mi Solucion",
        "tracked": false,
        "projects": [
          { "name": "Web.App", "csproj_path": "N:\\ws\\src\\Web.App\\Web.App.csproj", "type": "web", "target_framework": "net8.0" }
        ]
      }
    ]
  }
}
```
- Clave de primer nivel = `workspace_root` absoluto → múltiples proyectos coexisten; re-scan **reemplaza** solo esa clave.
- `tracked` (selección del operador) se **preserva** al re-escanear para los `slug` que sigan existiendo (merge por `slug`).

---

## 6. Fases

> Convención de tests: **backend** = pytest **por archivo** con el intérprete del backend; **frontend** = vitest **por archivo** (hay contaminación cross-file conocida — memoria `gotcha-vitest-test-order-pollution-frontend`).
> **Comando backend** (desde `Stacky Agents/backend`): `& ".venv\Scripts\python.exe" -m pytest tests\<archivo> -q` — si `.venv` no existe, usar `venv\Scripts\python.exe` (mismo py3.13). Ambos existen; `.venv` es el primario.
> **Comando frontend** (desde `Stacky Agents/frontend`): `npx vitest run src\components\devops\<archivo>.test.ts`.
> **Registrar** CADA `test_*.py` nuevo en `Stacky Agents/backend/scripts/run_harness_tests.sh` array `HARNESS_TEST_FILES` (`run_harness_tests.sh:20`) o el meta-ratchet se pone rojo (memoria `stacky-ratchet-obliga-registrar-tests`).

---

### F0 — Flag + esqueleto de sección (gate primero)

**Objetivo:** dejar la flag cableada en los 5 lugares (§4) y la sección "Compilar" visible (default ON) mostrando un placeholder, sin lógica. Valor: de-riesga toda la ceremonia de flags/health/sección antes de escribir lógica.

**Archivos a editar:**
- Los 5 de §4 (harness_flags.py ×2, test_harness_flags.py, config.py, api/devops.py).
- `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` — agregar al final del array `DEVOPS_SECTIONS` (después de la entrada `despliegues`, `DevOpsPage.tsx:170-178`):

```tsx
// Plan 201 — Taller de Compilación (detección .sln + build Release + artefactos descargables)
{
  id: 'taller-compilacion',
  label: 'Compilar',
  icon: '🔨',
  healthKey: 'build_workshop_enabled',
  gateFlagKey: 'STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED',
  gateMessage: 'La sección Compilar necesita la flag STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED (Configuración → Arnés, categoría DevOps).',
  render: (ctx) => <BuildWorkshopSection ctx={ctx} />,
},
```
- Importar el componente arriba (junto a `DeploymentsSection`, `DevOpsPage.tsx:92-93`): `import { BuildWorkshopSection } from '../components/devops/BuildWorkshopSection';`
- Crear placeholder `Stacky Agents/frontend/src/components/devops/BuildWorkshopSection.tsx` (mínimo, sin `style={{}}` inline — usar clases de `./devops.module.css`; memoria `gotcha-ratchet-nuevo-archivo-cero-inline-style`):

```tsx
import React from 'react';
import type { DevOpsSectionContext } from '../../pages/DevOpsPage';
export const BuildWorkshopSection: React.FC<{ ctx: DevOpsSectionContext }> = () => {
  return <div>Taller de Compilación (Plan 201) — próximamente</div>;
};
```

**Nombres exactos:** flag `STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED`; health key `build_workshop_enabled`; section id `taller-compilacion`; componente `BuildWorkshopSection`.

**Casos borde:** el id `taller-compilacion` NO debe aparecer fuera del array `DEVOPS_SECTIONS` (test C20 `DevOpsPage.test.ts` F4.e).

**Tests (TDD):**
- Backend: extender/crear `Stacky Agents/backend/tests/test_plan201_flag.py`:
  - `test_flag_registered_and_curated`: `STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED` está en `FLAG_REGISTRY`, en `_CATEGORY_KEYS["devops"]` y en `_CURATED_DEFAULTS_ON`.
  - `test_health_exposes_build_workshop_enabled`: el endpoint `/api/devops/health` incluye la clave `build_workshop_enabled` (usar el test client existente; mirar `test_plan120_api.py` como molde).
  - Registrar `tests/test_plan201_flag.py` en `HARNESS_TEST_FILES`.
  - Correr: `& ".venv\Scripts\python.exe" -m pytest tests\test_plan201_flag.py tests\test_harness_flags.py -q`
- Frontend: `Stacky Agents/frontend/src/pages/__tests__/BuildWorkshopSection.test.ts` (molde: `RemoteConsoleSection.test.ts:7-11`): `DEVOPS_SECTIONS` contiene `{ id:'taller-compilacion', gateFlagKey:'STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED' }`.
  - Correr: `npx vitest run src\pages\__tests__\BuildWorkshopSection.test.ts`

**Criterio de aceptación BINARIO:**
- `& ".venv\Scripts\python.exe" -m pytest tests\test_plan201_flag.py tests\test_harness_flags.py -q` → verde.
- `grep -rn "STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED" "Stacky Agents/backend/config.py"` → 1+ match.
- `npx vitest run src\pages\__tests__\BuildWorkshopSection.test.ts` → verde.

**Flag:** `STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED` (default ON). **Impacto runtime:** idéntico en los 3 (read-only, sin LLM). **Trabajo del operador:** ninguno (la sección aparece sola).

---

### F1 — Scanner determinista de soluciones (`solution_scanner.py`)

**Objetivo:** función pura que recorre el `workspace_root` y devuelve el catálogo de `.sln` con sus proyectos clasificados. Valor: es el corazón "detectar automáticamente y determinísticamente".

**Archivo a crear:** `Stacky Agents/backend/services/solution_scanner.py`.

**API pública (nombres exactos):**
```python
def scan_solutions(workspace_root: str | None) -> list[dict]
def slugify_solution(name: str) -> str
```
- `scan_solutions(None)` o ruta inválida → `[]` (NUNCA lanza; espejo de `pipeline_stack_detector.detect_stack`, `pipeline_stack_detector.py:25-26,54-55`).
- Salida = lista de dicts `{"slug","sln_path","sln_name","friendly_name","projects":[...]}` ordenada por `sln_path` (determinismo). Cada proyecto: `{"name","csproj_path","type","target_framework"}`.

**Constantes de módulo (deterministas, acotadas):**
```python
_IGNORE_DIRS = ("node_modules", ".git", "venv", ".venv", "bin", "obj",
                "__pycache__", "packages", ".vs", "TestResults", "dist", "node")
_MAX_DEPTH = 8          # más profundo que pipeline_stack_detector (repos de cliente anidan más)
_MAX_ENTRIES = 5000     # tope duro anti-cuelgue
_CSPROJ_HEAD_BYTES = 65536
_WEB_SDK = "microsoft.net.sdk.web"
_WORKER_SDK = "microsoft.net.sdk.worker"
_WEB_GUID = "349c5851-65df-11da-9384-00065b846f21"  # ProjectTypeGuid web clásico
```

**Pseudocódigo `scan_solutions`:**
```python
def scan_solutions(workspace_root):
    if not workspace_root or not os.path.isdir(workspace_root):
        return []
    root = os.path.normpath(workspace_root)
    sln_paths = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath[len(root):].count(os.sep)
        if depth >= _MAX_DEPTH:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
        for fname in filenames:
            scanned += 1
            if scanned > _MAX_ENTRIES:
                break
            if fname.lower().endswith(".sln"):
                sln_paths.append(os.path.join(dirpath, fname))
        if scanned > _MAX_ENTRIES:
            break
    out = []
    seen_slugs = set()
    for sln in sorted(sln_paths):
        name = os.path.splitext(os.path.basename(sln))[0]
        slug = _dedupe(slugify_solution(name), seen_slugs)  # asegura unicidad estable
        projects = _parse_sln_projects(sln)   # ver abajo
        out.append({
            "slug": slug, "sln_path": sln, "sln_name": name,
            "friendly_name": _title_case(name), "projects": projects,
        })
    return out
```
- `_parse_sln_projects(sln)`: lee el `.sln` (texto), aplica el regex de proyectos, resuelve rutas relativas contra el dir del `.sln`, filtra `.csproj`/`.vbproj`, e infiere tipo. Errores por archivo → se saltan (nunca propaga).

```python
_SLN_PROJECT_RE = re.compile(
    r'Project\("\{[0-9A-Fa-f-]+\}"\)\s*=\s*"([^"]+)",\s*"([^"]+)",\s*"\{[0-9A-Fa-f-]+\}"'
)
def _parse_sln_projects(sln_path):
    try:
        text = _read_text_safe(sln_path)   # utf-8 con errors="replace"
    except OSError:
        return []
    sln_dir = os.path.dirname(sln_path)
    projects = []
    for m in _SLN_PROJECT_RE.finditer(text):
        proj_name, rel = m.group(1), m.group(2).replace("\\", os.sep)
        if not (rel.lower().endswith(".csproj") or rel.lower().endswith(".vbproj")):
            continue
        csproj = os.path.normpath(os.path.join(sln_dir, rel))
        ptype, tfm = _infer_project(csproj)
        projects.append({"name": proj_name, "csproj_path": csproj,
                         "type": ptype, "target_framework": tfm})
    return projects
```

```python
def _infer_project(csproj_path):
    # tipo determinista por señales. Nunca lanza.
    try:
        text = _read_head_bytes(csproj_path, _CSPROJ_HEAD_BYTES).lower()
    except OSError:
        return ("unknown", "")
    tfm = _first_group(r'<targetframework[^>]*>([^<]+)</targetframework', text)
    proj_dir = os.path.dirname(csproj_path)
    web = (_WEB_SDK in text) or (_WEB_GUID in text) \
          or os.path.exists(os.path.join(proj_dir, "web.config"))
    if web:
        return ("web", tfm)
    if _WORKER_SDK in text:
        return ("service", tfm)
    if "<outputtype>exe</outputtype>" in text or "<outputtype>winexe</outputtype>" in text:
        return ("console", tfm)
    return ("library", tfm)
```

**`slugify_solution` (garantiza que el bridge del Plan 120 acepte el id):**
```python
def slugify_solution(name):
    # DEBE matchear deploy_planner._APP_ID_RE: [a-z0-9] inicial, luego [a-z0-9_-], 1..64.
    s = re.sub(r'[^a-z0-9]+', '-', (name or '').strip().lower()).strip('-')
    if not s or not s[0].isalnum():
        s = 'sln-' + s
    s = s[:64].rstrip('-')
    return s or 'sln'
```

**Casos borde (cubrir en tests):** workspace `None`/inexistente → `[]`; workspace sin `.sln` → `[]`; `.sln` corrupto/sin proyectos parseables → solución con `projects:[]` (no crash); `.csproj` referenciado inexistente → `type:"unknown"`, `target_framework:""`; nombres de `.sln` con espacios/acentos → slug ASCII válido; dos `.sln` con el mismo nombre en carpetas distintas → slugs únicos (`_dedupe` agrega sufijo `-2`, `-3`, ... determinista por orden).

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan201_solution_scanner.py`:**
- `test_scan_none_and_missing_returns_empty`
- `test_scan_no_sln_returns_empty` (tmp_path con archivos random)
- `test_scan_finds_sln_and_parses_projects` (escribir un `.sln` fixture con 2 líneas `Project(...)` + `.csproj` reales con `<OutputType>Exe</OutputType>` y `Microsoft.NET.Sdk.Web`)
- `test_infer_types` (web por SDK, web por `web.config`, console por Exe, library por default, service por Worker SDK)
- `test_slugify_matches_app_id_regex` (importar `_APP_ID_RE` de `services.deploy_planner` y assert `.match(slug)` para nombres con espacios/acentos/símbolos)
- `test_duplicate_names_get_unique_slugs`
- `test_ignores_bin_obj_and_depth_cap` (crear `.sln` bajo `bin/` y a profundidad > `_MAX_DEPTH`; NO deben aparecer)
- `test_corrupt_sln_no_crash`
- Registrar en `HARNESS_TEST_FILES`. Correr: `& ".venv\Scripts\python.exe" -m pytest tests\test_plan201_solution_scanner.py -q`

**Criterio BINARIO:** el comando anterior → verde; `scan_solutions` no importa nada de LLM/red (`grep -n "import" "Stacky Agents/backend/services/solution_scanner.py"` NO contiene `requests`, `runtime`, `llm`, `copilot`).

**Flag:** protegido aguas arriba por `STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED` (el servicio no chequea flag; lo hace el endpoint F4). **Runtime:** idéntico 3/3 (sin LLM). **Trabajo del operador:** ninguno.

---

### F2 — Persistencia del catálogo + selección (`solution_store.py`)

**Objetivo:** guardar el catálogo (las ubicaciones) de forma idempotente y persistir qué soluciones el operador tildó. Valor: "guardar las ubicaciones de cada SLN" + "solo tildar".

**Archivo a crear:** `Stacky Agents/backend/services/solution_store.py`.

**API pública (nombres exactos):**
```python
def store_path() -> Path                      # data_dir()/"build_solutions.json"
def rescan_and_save(workspace_root: str) -> dict   # corre scanner, hace merge de 'tracked', guarda, devuelve el bloque del workspace
def load_catalog(workspace_root: str) -> dict      # {"scanned_at","solutions":[...]} o {"scanned_at":None,"solutions":[]}
def set_tracked(workspace_root: str, slug: str, tracked: bool) -> dict   # togglea y guarda; devuelve el bloque
def tracked_solutions(workspace_root: str) -> list[dict]                 # subconjunto tracked=True
```
- Usa `from runtime_paths import data_dir` (patrón `deploy_store.py:28-29`).
- Escritura atómica idempotente idéntica a `deploy_store._save_apps` (`deploy_store.py:53-56`): `path.parent.mkdir(parents=True, exist_ok=True)` + `json.dumps(..., indent=2, ensure_ascii=False)`.
- Un `threading.Lock` de módulo (patrón `deploy_store.py:24`).
- **Merge de `tracked`:** al re-escanear, para cada `slug` nuevo, si existía con `tracked=True`, preservarlo; slugs desaparecidos se eliminan.
- JSON corrupto/no-dict → degradar a `{}` con `logger.warning` (patrón `deploy_store.py:48-50`).

**Pseudocódigo merge:**
```python
def rescan_and_save(workspace_root):
    fresh = scan_solutions(workspace_root)           # F1
    with _LOCK:
        doc = _load_doc()                            # dict o {}
        prev = doc.get(workspace_root, {}).get("solutions", [])
        prev_tracked = {s["slug"] for s in prev if s.get("tracked")}
        for s in fresh:
            s["tracked"] = s["slug"] in prev_tracked
        doc[workspace_root] = {"scanned_at": _utcnow_iso(), "solutions": fresh}
        _save_doc(doc)
        return doc[workspace_root]
```

**Casos borde:** `workspace_root` vacío → `load_catalog` devuelve `{"scanned_at":None,"solutions":[]}`; `set_tracked` de un slug inexistente → no-op (no crash, devuelve bloque sin cambios); archivo inexistente → `{}`.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan201_solution_store.py`:** (monkeypatch `store_path` a `tmp_path/"build_solutions.json"`, molde `test_plan120_store.py:37`)
- `test_load_missing_returns_empty`
- `test_rescan_persists_and_reload_matches` (monkeypatch `solution_scanner.scan_solutions` a un fake)
- `test_tracked_survives_rescan`
- `test_set_tracked_toggles_and_persists`
- `test_set_tracked_unknown_slug_is_noop`
- `test_corrupt_json_degrades_to_empty`
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `load_catalog` tras `rescan_and_save` devuelve las mismas soluciones (round-trip byte-estable salvo `scanned_at`).

**Flag/Runtime/Operador:** igual que F1.

---

### F3 — Detección de toolchain / doctor (`build_toolchain.py`)

**Objetivo:** decidir determinísticamente si se puede compilar (MSBuild vía `vswhere`, o `dotnet`) y, si no, entregar un "doctor" con remediación. Valor: hace posible la **EXCEPCIÓN DURA #3** (degradación controlada, no-op seguro).

**Archivo a crear:** `Stacky Agents/backend/services/build_toolchain.py`.

**API pública (nombres exactos):**
```python
def detect_toolchain() -> dict
```
Salida:
```python
{
  "available": bool,
  "builder": "msbuild" | "dotnet" | None,
  "msbuild_path": str | None,
  "dotnet_path": str | None,
  "version": str | None,
  "remediation": { "message": str, "command": str, "url": str } | None,
}
```

**Seams testeables (para monkeypatch, evita depender del SO real):**
```python
def _which(exe: str) -> str | None            # shutil.which
def _run(args: list[str], timeout: int = 20) -> tuple[int, str, str]   # subprocess LIST args, nunca shell=True
def _vswhere_path() -> str | None             # %ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe si existe
```

**Pseudocódigo:**
```python
def detect_toolchain():
    # 1) MSBuild vía vswhere (primario Windows)
    vsw = _vswhere_path()
    if vsw:
        code, out, _ = _run([vsw, "-latest", "-products", "*",
                             "-requires", "Microsoft.Component.MSBuild",
                             "-find", r"MSBuild\**\Bin\MSBuild.exe"])
        first = out.splitlines()[0].strip() if out.strip() else ""
        if code == 0 and first and os.path.exists(first):
            return {"available": True, "builder": "msbuild",
                    "msbuild_path": first, "dotnet_path": None,
                    "version": None, "remediation": None}
    # 2) dotnet en PATH
    dn = _which("dotnet")
    if dn:
        code, out, _ = _run([dn, "--version"])
        if code == 0:
            return {"available": True, "builder": "dotnet",
                    "msbuild_path": None, "dotnet_path": dn,
                    "version": out.strip(), "remediation": None}
    # 3) nada → doctor
    return {"available": False, "builder": None, "msbuild_path": None,
            "dotnet_path": None, "version": None,
            "remediation": {
              "message": "No se encontró MSBuild ni .NET SDK. Instalá el .NET SDK o Visual Studio Build Tools para compilar.",
              "command": "winget install --id Microsoft.DotNet.SDK.8 -e",
              "url": "https://dotnet.microsoft.com/download"}}
```

**Casos borde:** `vswhere` presente pero sin MSBuild instalado → cae a dotnet; `dotnet` en PATH pero roto (`--version` != 0) → doctor; ningún ejecutable → doctor (NUNCA crash). `detect_toolchain` **nunca lanza** (envolver todo en try/except → doctor).

**IMPORTANTE (G2/G7):** este servicio **NO ejecuta el instalador**. Solo **reporta** `remediation.command`. La instalación queda 100% en manos del operador (F10: botón que copia el comando con confirmación; opcionalmente "Ejecutar" detrás de un confirm HITL explícito, fuera del alcance mínimo de este plan).

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan201_build_toolchain.py`:** (monkeypatch `_which`, `_run`, `_vswhere_path`)
- `test_msbuild_detected_via_vswhere`
- `test_dotnet_fallback_when_no_msbuild`
- `test_doctor_when_nothing_available` (assert `available is False` y `remediation` con `command`/`url`)
- `test_never_raises_on_subprocess_error` (`_run` lanza → devuelve doctor)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -n "shell=True" "Stacky Agents/backend/services/build_toolchain.py"` → **0 matches** (siempre lista de args).

**Flag:** F4 gatea aguas arriba. **Runtime:** idéntico 3/3. **EXCEPCIÓN DURA #3 citada aquí.** **Operador:** ninguno (la detección corre sola al abrir la sección).

---

### F4 — API de scan/catálogo/track/doctor (`devops_build_workshop.py`)

**Objetivo:** exponer el scanner, el store y el doctor por HTTP. Valor: la UI puede escanear y tildar por clicks.

**Archivo a crear:** `Stacky Agents/backend/api/devops_build_workshop.py`.

**Blueprint (patrón `devops_deployments.py:22`):**
```python
bp = Blueprint("devops_build_workshop", __name__, url_prefix="/devops/build")
```
Guard por flag con `abort(404)` (patrón `devops_deployments.py:37-39`), usando la **instancia** `_config.config`:
```python
import config as _config
def _guard():
    if not bool(getattr(_config.config, "STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED", False)):
        abort(404)
```

**Endpoints de esta fase (rutas finales `/api/devops/build/...`):**
| Método | Ruta | Body/params | Respuesta |
|--------|------|-------------|-----------|
| `POST` | `/scan` | `{ "enrich": false }` (opcional; F11) | `{ "workspace_root", "catalog": {scanned_at, solutions[]}, "toolchain": {...} }` |
| `GET`  | `/catalog` | — | igual que `/scan` pero **sin** re-escanear (lee lo persistido) + `toolchain` fresco |
| `POST` | `/track` | `{ "slug": str, "tracked": bool }` | `{ "catalog": {...} }` |
| `GET`  | `/doctor` | — | `{ "toolchain": {...} }` (llama `build_toolchain.detect_toolchain()`) |

**Resolución de workspace:** `from runtime_paths import _active_workspace_root`; `ws = _active_workspace_root()`; si `ws is None` → responder `200` con `{"workspace_root": None, "catalog": {"scanned_at": None, "solutions": []}, "toolchain": detect_toolchain()}` y un campo `"warning": "No hay proyecto activo con workspace_root."` (NUNCA 500). El scan usa `str(ws)`.

**Registro del blueprint (patrón `api/__init__.py:45-53` + `:107-115`):**
- Import: `from .devops_build_workshop import bp as devops_build_workshop_bp  # Plan 201 — Taller de Compilación`
- Registro: `api_bp.register_blueprint(devops_build_workshop_bp)  # Plan 201 — url_prefix="/devops/build" → /api/devops/build/...`

**Casos borde:** flag OFF → todos los endpoints `404`; sin proyecto activo → `200` con catálogo vacío + warning; `POST /track` con slug inexistente → `200` no-op.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan201_api.py`:** (Flask test client + monkeypatch `_active_workspace_root`, `solution_store.store_path`, `build_toolchain.detect_toolchain`; molde `test_plan120_api.py:40`)
- `test_scan_off_returns_404` (flag OFF)
- `test_scan_no_active_workspace_returns_empty_200`
- `test_scan_persists_and_catalog_reads_back`
- `test_track_toggles`
- `test_doctor_returns_toolchain`
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.
- **GOTCHA (memoria `gotcha-config-reload-harness-flags-contamina`):** para forzar flag OFF/ON en test usar `monkeypatch.setattr(_config.config, "STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED", False)` sobre la **instancia**, NO `importlib.reload(config)`.

**Criterio BINARIO:** comando verde; `grep -rn "devops_build_workshop_bp" "Stacky Agents/backend/api/__init__.py"` → 2 matches (import + register).

**Flag:** `STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED`. **Runtime:** idéntico 3/3. **Operador:** ninguno (scan y doctor son 1 click en F10).

---

### F5 — Builder de soluciones (`solution_builder.py`)

**Objetivo:** compilar una `.sln` en Release, recolectar la salida a un staging por-sln, con log vivo, timeout y cancelación. Valor: "compilar en Release y dejar una carpeta".

**Archivo a crear:** `Stacky Agents/backend/services/solution_builder.py`.

**API pública (nombres exactos):**
```python
def start_build(slugs: list[str], unified: bool, workspace_root: str) -> str   # devuelve build_id (uuid4 hex); lanza el thread
def get_status(build_id: str) -> dict | None
def cancel(build_id: str) -> bool
def artifact_zip_path(build_id: str) -> Path | None    # resuelto desde el registro/ledger (F7 lo usa)
```

**Registro en memoria + ledger durable:**
```python
_LOCK = threading.Lock()
_BUILDS: dict[str, dict] = {}   # build_id -> {status, mode, slugs, artifact_dir, zip_path, log:[...], started_at, finished_at, error, _proc, _cancel}
```
- `status` ∈ `{"running","success","failed","cancelled","toolchain_missing"}`.
- Log vivo = lista de dicts `{"ts","level","message"}` (misma forma que `log_streamer.LogEvent.to_dict`, `log_streamer.py:31-43`), **empujada con lock**.
  - **DECISIÓN (evita FK huérfana):** NO se usa `log_streamer.close()` (`log_streamer.py:109-120`) porque persiste `ExecutionLog(execution_id=...)` contra la tabla `executions`; un build no es un `AgentExecution`, así que crearía FK inválida. Se usa un buffer propio, mismo **shape** que `log_streamer` (patrón reusado sin el acople a BD). El log completo se vuelca además a `<artifact_dir>/build.log`.
- Ledger append-only `data/build_runs.jsonl` (patrón `deploy_store.append_ledger`, `deploy_store.py:120-125`): una línea al terminar con `{build_id, mode, slugs, status, zip_path, finished_at}` → permite `artifact_zip_path` tras reinicio del backend.

**Constantes:**
```python
_BUILD_TIMEOUT_SEC = 1800   # 30 min; la cancelación manual es la garantía primaria anti-cuelgue (G6)
```
(Se deja como constante y NO como flag `int` para no arrastrar la ceremonia de `_FROZEN_BOUNDS`/bounds-map; promover a flag UI es un follow-up.)

**Comando de build (subprocess LIST args — NUNCA shell string; así espacios/acentos y backslashes finales son seguros, memoria rutas Windows):**
- Toolchain `dotnet`:
  ```
  [dotnet_path, "build", sln_path, "-c", "Release", "-o", staging_dir, "--nologo"]
  ```
- Toolchain `msbuild`:
  ```
  [msbuild_path, sln_path, "/t:Build", "/p:Configuration=Release", "/p:OutDir=" + staging_dir + os.sep, "/nologo"]
  ```
  (El `os.sep` final va DENTRO del argv element; como se pasa por lista, no hay comilla que el backslash escape — el bug clásico de `OutDir="...\"` solo ocurre construyendo un string de shell, que acá está PROHIBIDO.)

**Pseudocódigo por-sln:**
```python
def _run_one(build_id, slug, workspace_root, base_dir):
    tc = detect_toolchain()
    if not tc["available"]:
        _set(build_id, status="toolchain_missing")
        _push(build_id, "error", tc["remediation"]["message"])
        return None
    sln = _sln_path_for_slug(slug, workspace_root)   # desde solution_store.load_catalog
    if not sln or not os.path.exists(sln):
        _push(build_id, "error", f"Solución no encontrada: {slug}"); return None
    staging = base_dir / slug
    staging.mkdir(parents=True, exist_ok=True)
    args = _build_args(tc, sln, str(staging))
    _push(build_id, "info", "Compilando " + slug + " en Release…")
    proc = subprocess.Popen(args, stdout=PIPE, stderr=STDOUT, text=True,
                            encoding="utf-8", errors="replace", cwd=os.path.dirname(sln))
    _set(build_id, _proc=proc)
    try:
        for line in proc.stdout:          # streaming línea a línea
            if _is_cancelled(build_id):
                _terminate_tree(proc); _set(build_id, status="cancelled"); return None
            _push(build_id, "info", line.rstrip())
        proc.wait(timeout=_BUILD_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        _terminate_tree(proc); _push(build_id,"error","timeout"); return "failed"
    if proc.returncode != 0:
        return "failed"
    (staging_parent := staging).write ...   # (no-op) — el artefacto queda en staging
    return "success"
```
- `_terminate_tree(proc)`: `proc.terminate()` y best-effort `subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"], ...)` en Windows (matar hijos MSBuild). Nunca lanza.
- `start_build` corre `_run_all` en un `threading.Thread(daemon=True)` y devuelve `build_id` de inmediato (no bloquea el request).
- Al terminar TODOS los slugs: si todos `success` → `status="success"`, generar zip (F7 la lógica de zip vive acá): `zip_path = shutil.make_archive(str(base_dir), "zip", root_dir=str(base_dir))` → `<base_dir>.zip`; volcar `build.log`; escribir línea de ledger. Si alguno `failed` → `status="failed"` (los que compilaron quedan en staging).

**Staging dirs:** por-sln = `data/build_artifacts/<slug>/<ts>/`; el `base_dir` del build por-sln es `data/build_artifacts/<slug>/<ts>/` (un solo slug) — para F5. (Unificado en F6.)

**Casos borde:** toolchain ausente → `status="toolchain_missing"`, sin crash; build falla (returncode≠0) → `status="failed"`, staging parcial conservado; timeout → terminate + failed; cancel a mitad → terminate + `cancelled`; ruta del `.sln` con espacios/acentos → funciona (lista de args); slug sin `.sln` en disco → línea de error, sigue.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan201_solution_builder.py`:** (monkeypatch `detect_toolchain`, `subprocess.Popen` por un fake que emite líneas y un returncode; monkeypatch `data_dir` a `tmp_path`)
- `test_toolchain_missing_sets_status_and_no_crash`
- `test_successful_build_produces_staging_and_zip` (fake Popen returncode 0 + crea archivos en `-o`/OutDir)
- `test_failed_build_sets_failed`
- `test_cancel_terminates`
- `test_build_args_use_list_and_release` (assert `-c Release`/`/p:Configuration=Release` en args; assert NO se usa `shell=True`)
- `test_path_with_spaces_in_args` (sln bajo carpeta con espacio → arg intacto)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -n "shell=True" "Stacky Agents/backend/services/solution_builder.py"` → **0 matches**; `grep -n "log_streamer" "Stacky Agents/backend/services/solution_builder.py"` → **0 matches** (buffer propio, no acople BD).

**Flag/Runtime:** F6 gatea; idéntico 3/3 (el build es MSBuild/dotnet, no LLM). **EXCEPCIÓN DURA #3** citada (rama `toolchain_missing`). **Operador:** opt-in (default ON; build requiere toolchain, degrada a doctor).

---

### F6 — API de build / status / cancel + build unificado

**Objetivo:** disparar builds (por-sln y unificado) y seguirlos por polling. Valor: "compilar por clicks" + "despliegue unificado de lo que yo seleccione".

**Archivo a editar:** `Stacky Agents/backend/api/devops_build_workshop.py` (agregar endpoints).

**Endpoints (rutas finales `/api/devops/build/...`):**
| Método | Ruta | Body | Respuesta | HITL |
|--------|------|------|-----------|------|
| `POST` | `/compile` | `{ "slugs":[...], "unified":bool, "confirm":true }` | `200 { "build_id" }` **o** `200 { "status":"toolchain_missing", "toolchain":{...} }` | `confirm:true` obligatorio → si falta, `400` |
| `GET`  | `/status/<build_id>` | — | `{ status, mode, slugs, log:[...], artifact_ready:bool, error }` | — |
| `POST` | `/cancel/<build_id>` | `{ "confirm":true }` | `{ "cancelled":bool }` | `confirm:true` |

**Reglas:**
- `/compile`: `_guard()` primero (flag). Validar `slugs` no vacío y que sean slugs `tracked` del catálogo actual (defensa: no compilar algo no listado). Llamar `detect_toolchain()`; si `available` es `False` → responder `200 {"status":"toolchain_missing","toolchain":{...}}` (NO error, así el `api.post` normal del front lo puede renderizar; memoria `gotcha-frontend-api-wrapper-lanza-en-non-2xx`). Si `confirm` != `true` → `400 {"error":"confirm requerido"}`. Si ok → `build_id = solution_builder.start_build(slugs, unified, str(ws))` y devolver `{"build_id"}`.
- `unified:true` → el builder usa base_dir `data/build_artifacts/unified/<ts>/` y crea un subdir por slug: `unified/<ts>/<slug>/`; el zip final es `unified/<ts>.zip` con todos adentro.
- `unified:false` con 1 slug → base_dir `data/build_artifacts/<slug>/<ts>/`.
- `unified:false` con N slugs → N builds independientes; para simplificar el contrato de la UI, **cuando N>1 y unified=false**, el endpoint responde `400 {"error":"Para varias soluciones usá 'unificado' o compilá de a una"}` (decisión determinista y clara para el modelo menor; evita multiplexar N build_ids en un status).

**Casos borde:** `slugs` vacío → `400`; slug no-tracked → `400`; flag OFF → `404`; toolchain ausente → `200` doctor; `status` de build_id inexistente → `404`.

**Tests (TDD) — extender `test_plan201_api.py`:**
- `test_compile_requires_confirm`
- `test_compile_toolchain_missing_returns_doctor_200`
- `test_compile_starts_build_returns_build_id` (monkeypatch `solution_builder.start_build` → `"fakeid"` y `detect_toolchain` available)
- `test_compile_multi_without_unified_rejected`
- `test_status_unknown_returns_404`
- `test_cancel_requires_confirm`
- Correr por archivo.

**Criterio BINARIO:** comando verde.

**Flag:** `STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED`. **Runtime:** idéntico 3/3. **EXCEPCIÓN DURA #3** (rama doctor en `/compile`). **Operador:** click `Compilar` + confirmación (HITL).

---

### F7 — Descarga del artefacto (zip) con guard anti path-traversal

**Objetivo:** endpoint `GET` que entrega el zip del build. Valor: "dejar una carpeta descargada del despliegue".

**Archivo a editar:** `Stacky Agents/backend/api/devops_build_workshop.py`.

**Endpoint:**
| Método | Ruta | Respuesta |
|--------|------|-----------|
| `GET` | `/artifact/<build_id>/download` | `send_file(zip_path, as_attachment=True, download_name="<slug-o-unified>-<ts>.zip")` o `404` |

**Guard de seguridad (obligatorio, G6):**
```python
zip_path = solution_builder.artifact_zip_path(build_id)   # resuelto desde registro/ledger, NUNCA desde input del usuario
if not zip_path:
    abort(404)
root = (data_dir() / "build_artifacts").resolve()
target = Path(zip_path).resolve()
if os.path.commonpath([str(root), str(target)]) != str(root):
    abort(400)          # fuera del árbol permitido → rechazo
if not target.exists():
    abort(404)
return send_file(str(target), as_attachment=True, download_name=target.name)
```
- `build_id` NUNCA se interpola en una ruta de filesystem; solo se usa como **clave** para buscar el zip en el registro en memoria o en `data/build_runs.jsonl`. El `commonpath` es defensa en profundidad.

**Casos borde:** build sin terminar / sin zip → `404`; build_id inexistente → `404`; zip movido/borrado → `404`; intento de `build_id` con `../` → clave no encontrada → `404` (y aunque se resolviera, `commonpath` lo bloquea).

**Tests (TDD) — extender `test_plan201_api.py`:**
- `test_download_ready_returns_file` (sembrar un zip real en `tmp_path/build_artifacts/...` + registrar en el registro)
- `test_download_unknown_build_404`
- `test_download_path_outside_root_rejected` (monkeypatch `artifact_zip_path` → una ruta fuera de `build_artifacts` → `400`)
- Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -n "commonpath" "Stacky Agents/backend/api/devops_build_workshop.py"` → 1+ match.

**Flag/Runtime/Operador:** flag ON; idéntico 3/3; operador clickea `Descargar`.

---

### F8 — Bridge al Centro de Despliegues (Plan 120)

**Objetivo:** botón "Usar como app de despliegue" que registra la carpeta artefacto como `DeployApp` vía el store del Plan 120, cerrando compilar → desplegar → rollback. Valor: el lazo completo con clicks.

**Archivo a editar:** `Stacky Agents/backend/api/devops_build_workshop.py`.

**Endpoint:**
| Método | Ruta | Body | Respuesta | HITL |
|--------|------|------|-----------|------|
| `POST` | `/register-deploy-app` | `{ "build_id":str, "slug":str, "confirm":true }` | `{ "app": {...} }` o `400 {"error"}` | `confirm:true` |

**Lógica (reusa validación y store del Plan 120 tal cual):**
```python
from services import deploy_store
def register_deploy_app():
    _guard()
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm requerido"}), 400
    build_id, slug = body.get("build_id"), body.get("slug")
    st = solution_builder.get_status(build_id)
    if not st or st["status"] != "success":
        return jsonify({"error": "El build no está terminado con éxito"}), 400
    artifact_dir = solution_builder.artifact_dir_for(build_id, slug)   # carpeta (no el zip)
    if not artifact_dir or not os.path.isdir(artifact_dir):
        return jsonify({"error": "Artefacto no encontrado"}), 400
    friendly = _friendly_for(slug)   # de solution_store.load_catalog
    payload = {
        "id": slug,                                   # slugify_solution ya garantiza _APP_ID_RE
        "name": friendly,
        "artifact": {"kind": "folder", "path": os.path.abspath(artifact_dir)},
        "targets": {},                                # el operador configura destinos en la sección Despliegues
    }
    try:
        app = deploy_store.upsert_app(payload)        # valida vía deploy_planner.validate_app
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"app": app})
```
- `deploy_store.upsert_app` (`deploy_store.py:70-83`) valida con `deploy_planner.validate_app` (`deploy_planner.py:30-50`): `id` debe matchear `_APP_ID_RE` (garantizado por `slugify_solution`), `artifact.kind` ∈ `{folder,zip}` (usamos `folder`), `artifact.path` absoluto (usamos `os.path.abspath`). **NO** escribir `deploy_apps.json` a mano — usar `upsert_app` (idempotente por `id`).

**Casos borde:** build no `success` → `400`; artefacto inexistente → `400`; `id` colisiona con una app existente → `upsert_app` **actualiza** (idempotente, por diseño del Plan 120); `confirm` faltante → `400`.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan201_bridge.py`:** (monkeypatch `deploy_store._apps_path` a `tmp_path`, `solution_builder.get_status`/`artifact_dir_for`)
- `test_register_requires_confirm`
- `test_register_rejects_unfinished_build`
- `test_register_creates_deploy_app_with_folder_artifact` (assert la app aparece en `deploy_store.list_apps()` con `artifact.kind=="folder"`)
- `test_register_is_idempotent_on_same_slug`
- `test_slug_id_passes_deploy_planner_validation` (assert `deploy_planner.validate_app(payload) == []`)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; tras `register-deploy-app`, `deploy_store.get_app(slug)` no es `None` y su `artifact.kind == "folder"`.

**Flag:** `STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED`. **Runtime:** idéntico 3/3. **Operador:** click "Usar como app de despliegue" + confirmación.

---

### F9 — Modelo puro del frontend (`buildWorkshopModel.ts`)

**Objetivo:** helpers puros testeables (sin render), patrón de la casa (`deploymentsModel.ts`). Valor: lógica de UI verificable barata.

**Archivos a crear:** `Stacky Agents/frontend/src/components/devops/buildWorkshopModel.ts` + `.test.ts`.

**Tipos y funciones puras (nombres exactos):**
```ts
export interface SolutionProject { name: string; csproj_path: string; type: 'web'|'console'|'service'|'library'|'unknown'; target_framework: string }
export interface SolutionEntry { slug: string; sln_path: string; sln_name: string; friendly_name: string; tracked: boolean; projects: SolutionProject[] }
export interface Toolchain { available: boolean; builder: 'msbuild'|'dotnet'|null; version: string|null; remediation: { message: string; command: string; url: string } | null }
export interface BuildStatus { status: 'running'|'success'|'failed'|'cancelled'|'toolchain_missing'; mode: 'single'|'unified'; slugs: string[]; log: { ts: string; level: string; message: string }[]; artifact_ready: boolean; error: string|null }

export function trackedSlugs(solutions: SolutionEntry[]): string[]
export function canCompile(toolchain: Toolchain, selectedCount: number): boolean   // available && selectedCount>=1
export function compileMode(unified: boolean, selectedCount: number): 'single'|'unified'|'invalid'  // >1 && !unified => 'invalid'
export function buildStatusLabel(status: BuildStatus['status']): string            // español, sin colisionar con STATUS_LABEL de deployments
export function formatBuildDuration(startIso: string, endIso: string|null, now?: Date): string
export function projectTypeLabel(t: SolutionProject['type']): string               // 'web'→'Web', etc.
export function summarizeCatalog(solutions: SolutionEntry[]): { total: number; tracked: number; byType: Record<string, number> }
```

**Casos borde:** `solutions` vacío → `summarizeCatalog` `{total:0,tracked:0,byType:{}}`; `compileMode(false, 2)` → `'invalid'`; `canCompile({available:false,...}, 5)` → `false`; `formatBuildDuration` con `endIso=null` → "en curso".

**Tests (TDD) — `buildWorkshopModel.test.ts`** (vitest, molde de los tests de `deploymentsModel`): un `it` por función cubriendo el caso normal + los borde de arriba. Correr: `npx vitest run src\components\devops\buildWorkshopModel.test.ts`.

**Criterio BINARIO:** comando verde.

**Flag/Runtime/Operador:** N/A (puro); idéntico 3/3.

---

### F10 — UI de la sección (`BuildWorkshopSection.tsx`) + endpoints.ts

**Objetivo:** la pantalla real: escanear, tildar, compilar, ver log vivo, descargar, doctor, y bridge. Valor: la experiencia "solo clicks".

**Archivos a editar/crear:**
- `Stacky Agents/frontend/src/api/endpoints.ts` — **espejar** el bloque `DevOpsDeployments` con un objeto nuevo:
```ts
export const DevOpsBuildWorkshop = {
  scan: (enrich = false) => api.post('/devops/build/scan', { enrich }),
  catalog: () => api.get('/devops/build/catalog'),
  track: (slug: string, tracked: boolean) => api.post('/devops/build/track', { slug, tracked }),
  doctor: () => api.get('/devops/build/doctor'),
  compile: (slugs: string[], unified: boolean) => api.post('/devops/build/compile', { slugs, unified, confirm: true }),
  status: (buildId: string) => api.get(`/devops/build/status/${buildId}`),
  cancel: (buildId: string) => api.post(`/devops/build/cancel/${buildId}`, { confirm: true }),
  registerDeployApp: (buildId: string, slug: string) => api.post('/devops/build/register-deploy-app', { build_id: buildId, slug, confirm: true }),
  artifactDownloadUrl: (buildId: string) => `/api/devops/build/artifact/${buildId}/download`,
};
```
  - **GOTCHA (memoria `gotcha-frontend-api-wrapper-lanza-en-non-2xx`):** `api.post`/`api.get` **lanzan** en non-2xx. `/compile` con toolchain ausente responde **200** (doctor), así que `api.post` sirve. Para descargar, usar un `<a href={DevOpsBuildWorkshop.artifactDownloadUrl(buildId)} download>` (GET directo del navegador), no `api.get`.
- `Stacky Agents/frontend/src/components/devops/BuildWorkshopSection.tsx` — reemplazar el placeholder de F0.

**Comportamiento UI (todo clicks):**
1. Al montar: `useQuery(['build-catalog'], DevOpsBuildWorkshop.catalog)`; muestra `toolchain` (chip verde "MSBuild/.NET listo" o **panel doctor** rojo con `remediation.message`, botón **Copiar comando** y link `Descargar .NET SDK`).
   - **Copiar comando:** usar el **copyService del Plan 194** (memoria `plan-194-status` / ratchet `writeText`), NO `navigator.clipboard.writeText` directo.
2. Botón **Escanear** → `DevOpsBuildWorkshop.scan()` → invalida `['build-catalog']`. Muestra `summarizeCatalog` (total / tildadas / por tipo).
3. Lista de soluciones: cada fila con **checkbox** (`tracked`) → `DevOpsBuildWorkshop.track(slug, next)`; muestra `friendly_name`, `sln_path`, chips de proyectos (`projectTypeLabel`).
4. Barra de acción: toggle **Unificado**; botón **Compilar** habilitado por `canCompile(toolchain, trackedCount)` y `compileMode(...)!=='invalid'`.
   - **Compilar** abre confirmación HITL (reusar el diálogo canónico del Plan 164 `useConfirm`/`Dialog` si está disponible; si no, `window.confirm` es aceptable pero preferir la primitiva de marca). Al confirmar → `DevOpsBuildWorkshop.compile(trackedSlugs, unified)`.
   - Si la respuesta trae `status:'toolchain_missing'` → mostrar el doctor (no error).
5. Con `build_id`: `useQuery(['build-status', buildId], () => DevOpsBuildWorkshop.status(buildId), { refetchInterval: 1500, enabled: !!buildId })`. Render del **log vivo** (lista de `log[]`), `buildStatusLabel(status)`, botón **Cancelar** (HITL) mientras `running`.
6. Al `status==='success'` con `artifact_ready`: botón **Descargar** (`<a download>`) + botón **Usar como app de despliegue** (HITL confirm → `registerDeployApp`; al éxito, toast "Registrado en Despliegues" e invalidar `['devops-deployments-overview']` para que la sección Despliegues lo muestre).

**Ratchets a respetar (memoria):**
- **Cero `style={{}}` inline** en el `.tsx` nuevo → usar clases de `./devops.module.css` (agregar las que falten allí). Memoria `gotcha-ratchet-nuevo-archivo-cero-inline-style`.
- Si `uiDebtRatchet`/`formDebtBaseline.json` marca el archivo nuevo, agregar su entrada de baseline siguiendo el patrón existente (`formDebtBaseline.json:53` tiene `"components/devops/DeploymentsSection.tsx": 6`). NO empeorar deuda ajena.
- Copiar al portapapeles SIEMPRE vía copyService (Plan 194).

**Tests (TDD):**
- Ya cubierto lo puro en F9. Para la sección, `Stacky Agents/frontend/src/components/devops/__tests__/BuildWorkshopSection.test.ts`: importa el módulo y valida que **exporta** `BuildWorkshopSection` (RTL/jsdom NO están instalados — memoria `gotcha-rtl-jsdom-structural-gap`; el gate real es `tsc` + smoke manual). Correr: `npx vitest run src\components\devops\__tests__\BuildWorkshopSection.test.ts`.
- Gate de tipos: `npx tsc --noEmit` (desde `Stacky Agents/frontend`).

**Criterio BINARIO:** `npx tsc --noEmit` sin errores nuevos; los tests vitest de F9/F10 verdes; smoke manual: la sección "Compilar" aparece, `Escanear` lista `.sln`, y con toolchain ausente muestra el doctor sin romper.

**Flag:** `STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED`. **Runtime:** idéntico 3/3 (UI no llama LLM). **Operador:** clicks (Escanear / tildar / Compilar / Descargar / Usar como app).

---

### F11 — (OPCIONAL) Enriquecimiento LLM con fallback determinista (`solution_enricher.py`)

**Objetivo:** mejorar `friendly_name`/clasificación con un LLM **si está disponible**, degradando en silencio a la heurística determinista. Valor: "azúcar" opcional; el operador pidió "determinísticamente mejor" → el default ES determinista.

**Archivo a crear:** `Stacky Agents/backend/services/solution_enricher.py`.

**API pública:**
```python
def enrich_catalog(solutions: list[dict]) -> list[dict]   # devuelve solutions con friendly_name mejorado; NUNCA lanza; si LLM no disponible → devuelve la entrada TAL CUAL
```
- Se invoca SOLO cuando `POST /scan` recibe `{"enrich": true}` (default `false`). Nunca corre en background (respeta la regla "flags que queman tokens ociosos": esto es on-demand, no un loop).
- Reusa el helper local existente (`invoke_local_llm` / el bridge de runtime) detrás de un `try/except` total. Cualquier error/ausencia → return input sin cambios.
- **Paridad 3 runtimes:** como el core (F1) ya produce `friendly_name` determinista, los 3 runtimes muestran lo mismo por default; el enriquecimiento es idéntico best-effort en los 3 y su ausencia no cambia el resultado funcional.

**Casos borde:** LLM devuelve basura/timeout → se ignora, queda el determinista; `solutions` vacío → `[]`.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan201_enricher.py`:**
- `test_enrich_without_llm_returns_input_unchanged` (monkeypatch el helper LLM a que lance → salida == entrada)
- `test_enrich_applies_friendly_name_when_llm_ok` (monkeypatch el helper → nombre mejorado)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; con LLM forzado a fallar, `enrich_catalog(x) == x`.

**Flag:** bajo `STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED`; el enrich es un **parámetro de request** (`enrich`), no una flag nueva. **Runtime:** degrada idéntico en los 3. **Operador:** opcional (un toggle "mejorar nombres con IA" en el botón Escanear, default apagado).

---

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación (fase) |
|--------|-------------------|
| Toolchain .NET ausente (EXCEPCIÓN #3) | Detección de capacidad + doctor + no-op; flag sigue ON pero `Compilar` degrada (F3/F5/F6). NUNCA crash. |
| Builds largos que cuelgan | `_BUILD_TIMEOUT_SEC=1800` + **Cancelar** manual (HITL) + `taskkill /T /F` best-effort del árbol de procesos (F5/F6). |
| Rutas Windows con espacios/acentos ("Stacky Agents" tiene espacio) | subprocess **siempre con lista de args**, jamás string de shell; `OutDir`/`-o` como argv element (el bug `OutDir="...\"` solo ocurre con shell string) (F5). Test con path con espacio. |
| `.sln`/`.csproj` enorme o árbol gigante | Topes duros `_MAX_DEPTH=8`, `_MAX_ENTRIES=5000`, lectura de `.csproj` acotada a 64KB (F1). |
| Colisión de nombres de artefacto | Subdir por `<slug>/<timestamp>`; slugs deduplicados de forma estable (F1/F5). |
| Path-traversal al servir zips | `artifact_zip_path` resuelto por clave (nunca por input) + `os.path.commonpath` contra `data/build_artifacts` (F7). |
| FK huérfana si se reusa `log_streamer.close()` | Buffer de logs propio (mismo shape, sin persist a `ExecutionLog`) + volcado a `build.log` (F5). |
| Backend reiniciado a mitad de build | Registro en memoria se pierde → `status` desconocido; el ledger `build_runs.jsonl` permite **descargar** artefactos ya terminados tras reinicio (F5/F6). Documentado. |
| Operador compila algo no listado | `/compile` valida que los `slugs` sean `tracked` del catálogo actual (F6). |
| Ratchets de UI (inline-style / deuda / writeText) | Cero `style={{}}`; baseline si aplica; copyService del 194 (F10). |
| Meta-tests de flags rojos | Cableado en los 5 lugares de §4 + registro en `HARNESS_TEST_FILES` (F0). |

---

## 8. Fuera de scope (explícito)

- **CI remoto / pipelines de CI** (eso es la serie DevOps 186–195). Este plan compila **localmente** con el toolchain de la máquina del operador.
- **Firmar binarios del cliente** (code signing).
- **Deploy remoto / rollback** — ya es el **Plan 120**; este plan solo **produce** el artefacto y ofrece el bridge para registrarlo.
- **Tocar `Stacky Agents/deployment/build_release.ps1`** (compila Stacky mismo; no es un builder de `.sln` arbitrarios).
- **Auto-instalar el toolchain** sin intervención (el doctor solo reporta el comando; instalar es decisión del operador).
- **Promover el timeout a flag `int` de UI** (queda como constante; follow-up).

---

## 9. Glosario (para modelo menor)

- **`.sln` (solution):** archivo de texto de Visual Studio que agrupa uno o más proyectos. Contiene líneas `Project("{GUID}") = "Nombre", "ruta\Proj.csproj", "{GUID}"`.
- **`.csproj` / `.vbproj`:** archivo de proyecto .NET (C# / VB). Declara SDK, `OutputType`, `TargetFramework`.
- **MSBuild:** motor de compilación de Microsoft (parte de Visual Studio / Build Tools). Ejecutable `MSBuild.exe`.
- **`vswhere`:** utilitario que localiza instalaciones de Visual Studio / Build Tools y, con `-find`, la ruta de `MSBuild.exe`.
- **`dotnet`:** CLI del .NET SDK; `dotnet build -c Release -o <dir>` compila y recolecta salida.
- **publish / Release:** "Release" = configuración optimizada (no Debug). El artefacto Release es lo que se despliega.
- **`workspace_root`:** raíz del repositorio del **proyecto activo** de Stacky (`projects/<active>/config.json`), donde se escanean los `.sln`.
- **`DeployApp` / `artifact`:** unidad desplegable del Plan 120: `{ id, name?, artifact:{ kind:'folder'|'zip', path }, targets }`. La carpeta artefacto de este plan encaja como `kind:'folder'`.
- **ledger:** archivo append-only (`.jsonl`) con el historial (de deploys en Plan 120; de builds en este plan).
- **flag del arnés:** interruptor de feature en `harness_flags.py` + `config.py`, toggleable desde Configuración → Arnés.
- **runtime vs `LLM_BACKEND`:** el **runtime** es quién ejecuta al agente (Codex/Claude/Copilot CLI); el `LLM_BACKEND` es el proveedor del modelo. El núcleo de este plan **no depende** de ninguno (es determinista).

---

## 10. Orden de implementación (numerado)

1. **F0** — Flag en 5 lugares + entrada `DEVOPS_SECTIONS` + health + placeholder. (Verde de meta-tests de flags.)
2. **F1** — `solution_scanner.py` (puro) + tests.
3. **F2** — `solution_store.py` (persistencia idempotente + tracked) + tests.
4. **F3** — `build_toolchain.py` (detección/doctor) + tests.
5. **F4** — `devops_build_workshop.py` (scan/catalog/track/doctor) + registro blueprint + tests.
6. **F5** — `solution_builder.py` (build por-sln, log, timeout, cancel) + tests.
7. **F6** — API compile/status/cancel + unificado + tests.
8. **F7** — download con guard path-traversal + tests.
9. **F8** — bridge `register-deploy-app` → `deploy_store.upsert_app` + tests.
10. **F9** — `buildWorkshopModel.ts` + `.test.ts`.
11. **F10** — `BuildWorkshopSection.tsx` + `endpoints.ts` + `tsc` + smoke.
12. **F11** — (opcional) `solution_enricher.py` + tests.

Cada fase se mergea/valida sola (autocontenida). F1–F3 son independientes entre sí y pueden ir en cualquier orden tras F0; F4 depende de F1–F3; F6/F7/F8 dependen de F5; F10 depende de F4–F9.

---

## 11. Definición de Hecho (DoD) — binaria

- [ ] `STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED` registrada en los 5 lugares de §4; `& ".venv\Scripts\python.exe" -m pytest tests\test_harness_flags.py -q` verde.
- [ ] `/api/devops/health` incluye `build_workshop_enabled`.
- [ ] La sección "Compilar" aparece en DevOps (default ON) y respeta el gate declarativo.
- [ ] `scan_solutions(None)` → `[]`; con un workspace fixture con `.sln`, lista soluciones + proyectos clasificados; no importa LLM/red.
- [ ] El catálogo persiste en `data/build_solutions.json`, re-scan es idempotente y `tracked` sobrevive.
- [ ] `detect_toolchain()` devuelve `available:true` con MSBuild/dotnet, o `available:false` + `remediation`; nunca lanza; sin `shell=True`.
- [ ] Endpoints `/devops/build/{scan,catalog,track,doctor,compile,status,cancel,artifact,register-deploy-app}` responden; flag OFF → 404; sin workspace → 200 vacío.
- [ ] `POST /compile` exige `confirm:true`, degrada a doctor 200 si falta toolchain, y arranca build en thread devolviendo `build_id`.
- [ ] El build produce `data/build_artifacts/<slug>/<ts>/` (o `unified/<ts>/`), un `build.log`, un `.zip`, y una línea en `data/build_runs.jsonl`.
- [ ] `GET /artifact/<build_id>/download` entrega el zip con guard `commonpath`; rutas fuera del árbol → 400/404.
- [ ] `POST /register-deploy-app` crea una `DeployApp` (`kind:'folder'`) vía `deploy_store.upsert_app` y aparece en la sección Despliegues.
- [ ] Todos los `test_plan201_*.py` registrados en `HARNESS_TEST_FILES` y verdes **por archivo** con el venv del backend.
- [ ] `buildWorkshopModel.test.ts` verde y `npx tsc --noEmit` sin errores nuevos.
- [ ] Smoke manual: en una máquina **sin** toolchain, la sección muestra el doctor y `Compilar` NO crashea (no-op controlado).
- [ ] Paridad 3 runtimes: el núcleo (scan+build) no llama a ningún LLM (F11 opcional y con fallback). Trabajo del operador: solo clicks.
```