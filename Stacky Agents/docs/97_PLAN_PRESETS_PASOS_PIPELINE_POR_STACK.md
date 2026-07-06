# Plan 97 — Presets de pasos de pipeline por stack técnico (compilar/test/lint) con detección opcional

**Estado:** PROPUESTO
**Versión:** v1
**Fecha:** 2026-07-05
**Serie DevOps:** complementa la serie base 87-91 (builder gráfico) y la serie E2E
93-96 (preflight/variables/producción/doctor) — NO es el plan 5 de esa serie
(numeración compartida distinta), pero reusa su infraestructura de flags/health/
contrato de extensión. Puede implementarse en paralelo a 93-96: no depende de
ninguno de ellos, y ninguno de ellos depende de este.
**Requisito textual del operador (validado con evidencia, ver §2):** "los
pipelines ya te tienen que dar preset con scripts para el proyecto: compilar,
test, etc." — el operador no-experto debe poder arrancar el builder con pasos
reales de compilar/testear/lintear/empaquetar según el stack de SU proyecto, en
vez de un único ejemplo genérico con `echo`.
**Dependencias:** plan 87 IMPLEMENTADO (`84a9ecb5` — panel host, `starterSpec`,
`specBuilder.ts`, `PipelineBuilderSection.tsx`, contrato de extensión §3.12).
Ninguna otra dependencia de la serie E2E 93-96 (todas sin implementar aún).
Verificado en working tree 2026-07-05:

| Pieza existente reusada | Evidencia (archivo:línea) |
|---|---|
| `starterSpec()` (único ejemplo hoy, genérico, 1 stage/1 job/1 step con echo) | `frontend/src/devops/specBuilder.ts:80-101` |
| Punto de integración UI del estado vacío (CTA "Empezar con ejemplo") | `frontend/src/components/devops/PipelineBuilderSection.tsx:251-272` |
| Tipos espejo del contrato (`StepDraft`/`JobDraft`/`StageDraft`/`PipelineSpecDraft`) | `frontend/src/devops/specBuilder.ts:9-41` |
| `PipelineSpec`/`Step`/`Job`/`Stage` + `dict_to_spec` + `_validate_spec` (backend, fuente de verdad) | `backend/services/pipeline_spec.py:27,32,42,49,56,65,112` |
| Renderers puros spec→YAML (ADO y GitLab) | `backend/services/pipeline_renderers.py:23` (`to_ado_yaml`), `:126` (`to_gitlab_yaml`) |
| Blueprint del panel + health con booleans aditivos | `backend/api/devops.py` (rutas `/api/devops/health`, `/api/devops/parse-yaml`) |
| Contrato de extensión §3.12 (`DEVOPS_SECTIONS` declarativo, gate por health) | `frontend/src/pages/DevOpsPage.tsx` |
| `FlagGateBanner` (aviso en llano + activar por UI) | `frontend/src/components/devops/FlagGateBanner.tsx` |
| Endpoint de importación de YAML existente (PURO, reusable como ejemplo de patrón) | `backend/api/devops.py` (`POST /api/devops/parse-yaml`) |
| Patrón flag 5 patas + gotchas (`_CURATED_DEFAULTS_ON`, `env_only`, requires) | `backend/config.py` (línea de `STACKY_DEVOPS_PANEL_ENABLED`), `backend/services/harness_flags.py` (`_CATEGORY_KEYS["devops"]`, `FlagSpec`), `backend/services/harness_flags_help.py`, `backend/harness_defaults.env`, ratchet `backend/scripts/run_harness_tests.ps1` |
| Mapa congelado de `requires` (R4, profundidad 1) | `backend/tests/test_harness_flags_requires.py` (`_REQUIRES_MAP_FROZEN`) |
| Detector de literales placeholder (referencia de qué NO hay que confundir con esto) | plan 93 F1 (`services/pipeline_preflight.py`, `PLACEHOLDER_LITERALS`) — **complementario**: el 93 detecta placeholders ya puestos; este plan 97 evita que se pongan en primer lugar ofreciendo el script real desde el día 1 |

**GAP VERIFICADO (no existe hoy, búsqueda dirigida en el repo):** no hay ningún
detector de stack técnico por archivos de manifiesto (`requirements.txt`,
`package.json`, `*.csproj`, `pyproject.toml`, `Pipfile`) en `backend/services/`
ni `backend/api/`. Los únicos usos de `package.json` en el backend son
`services/app_version.py` (lee la VERSIÓN de Stacky mismo, no del proyecto del
operador) y `services/config_transfer.py` (idéntico propósito). El único
`.csproj` que aparece es un glob hardcodeado para RIPLEY en
`services/client_profile_default_templates.py:66` (`"Batch/*/*.csproj"`), no una
detección genérica. `services/ado_pipeline_inference.py` infiere STAGES vía LLM a
partir de contexto de **tickets** (texto de ADO), no analiza el código del
proyecto — es complementario, no se superpone. **Conclusión: el gap es real; se
construye desde cero, sin duplicar nada existente.**

---

## 1. Objetivo + KPI

Ofrecer, en el mismo punto donde hoy solo existe "Empezar con ejemplo"
(`starterSpec` genérico), una **galería de presets de pipeline por stack
técnico** (Python+pytest, Node+npm, .NET+dotnet, y un preset "Genérico" de
respaldo) que arma un `PipelineSpecDraft` completo y **editable** con pasos
reales de instalar-dependencias / lint / test / compilar-empaquetar — nunca un
`echo` de relleno. Adicionalmente, un botón **opt-in** "Detectar stack de mi
proyecto" que lee (solo-lectura) los archivos de manifiesto del repo del
proyecto activo y **pre-selecciona** el preset más probable, dejando SIEMPRE la
decisión final y la edición en manos del operador (HITL).

**KPI (aspiracional, no criterio de done — los binarios están en cada fase):**
- El operador llega de "lienzo vacío" a un pipeline con pasos REALES (no `echo`)
  de compilar+test en ≤ 2 clicks (elegir preset + opcionalmente confirmar
  detección), igual que hoy con "Empezar con ejemplo" (mismo costo de UX, más
  valor).
- 4 presets cubiertos desde el día 1 (Python, Node, .NET, Genérico), cada uno
  generando YAML válido para ADO y GitLab (paridad dura, criterio binario F2/F3).
- 0% de falsos "detecté tu stack": si hay ambigüedad o cero señales, el detector
  degrada a "no pude detectar, elegí manualmente" — nunca inventa.
- 0 líneas de config nuevas para el operador: el detector es un botón, no un
  paso obligatorio; los presets están siempre disponibles sin flag para verlos,
  y la detección automática es opt-in con flag propia default OFF (ver F0).

## 2. Por qué ahora / gap que cierra (evidencia)

`starterSpec()` (`specBuilder.ts:80-101`) es el ÚNICO punto de partida no-vacío
del builder hoy: 1 stage `build` / 1 job `build-job` / 1 step `compilar` con
script literal `echo "reemplazar por el comando real"`. Es deliberadamente un
placeholder (así lo detecta el plan 93 F1 como "step sin trabajo real"). El
operador no-experto — el usuario objetivo declarado de la serie DevOps — no
sabe qué comando poner ahí: no conoce la sintaxis de compilar con `dotnet`, ni
cómo correr pytest con el venv del repo, ni el comando de `npm run build`. Hoy
tiene que escribirlo a mano sin ninguna guía. Esto es exactamente el gap que
señaló el operador ("los pipelines ya te tienen que dar preset con scripts para
el proyecto: compilar, test, etc.") y está **verificado por ausencia de código**:
no existe ningún catálogo de presets ni detector de stack en el repo (ver tabla
de arriba). El costo de cerrarlo es bajo (funciones puras + 1 componente UI +
1 endpoint fino de solo-lectura) y el valor es alto porque es el PRIMER contacto
del operador con el builder (afecta a el 100% de los pipelines nuevos).

## 3. Principios y guardarraíles (NO negociables)

1. **3 runtimes con paridad (Codex CLI / Claude Code CLI / GitHub Copilot Pro):**
   este plan es 100% UI + Flask (no toca el camino de ejecución de agentes).
   Impacto: NINGUNO en los tres runtimes — se declara explícitamente por fase.
   Ningún ítem depende de qué runtime esté corriendo Stacky.
2. **Cero trabajo extra para el operador:** los presets están siempre visibles
   sin ninguna flag (son datos estáticos, mismo costo que ya existe con
   `starterSpec`); la DETECCIÓN automática por archivos es la única parte
   opt-in, con flag propia default OFF (F0). Sin nueva carga de configuración,
   backward-compatible con `starterSpec` (que sigue existiendo intacto).
3. **Human-in-the-loop innegociable:** el detector solo **sugiere** un preset
   preseleccionado; el operador SIEMPRE debe hacer click en "Usar este preset"
   para aplicarlo, y puede editar cualquier step después. Ningún preset se
   commitea ni dispara solo — sigue el flujo HITL existente de commit/trigger
   del plan 87 (intacto). Prohibida la autonomía proactiva (nunca se aplica un
   preset sin acción explícita del operador).
4. **Mono-operador, sin auth real:** ningún concepto de roles/permisos.
5. **Paridad dura ADO+GitLab:** cada preset es un `PipelineSpecDraft` agnóstico
   de tracker (igual que hoy); el YAML de ambos providers sale de los MISMOS
   renderers ya existentes (`to_ado_yaml`/`to_gitlab_yaml`), cero renderer nuevo.
6. **No degradar lo existente:** `starterSpec`, `emptySpec`, `validateSpecLocal`,
   `PipelineSpec`/`_validate_spec`, y el flujo de importar YAML NO cambian de
   contrato. Todo lo de este plan es ADITIVO (funciones y componentes nuevos).
7. **Reusar, no reinventar:** el detector de stack es solo-lectura sobre el
   filesystem del proyecto activo (mismo patrón de acceso a disco que usa
   `project_manager.get_project_config`/`runtime_paths`), NO un LLM, NO un
   servicio nuevo de análisis de código. Los presets son datos estáticos en
   TypeScript puro (mismo patrón que `starterSpec`), sin backend nuevo para
   servirlos.
8. **Ratchet de tests:** todo archivo de test backend nuevo se registra en
   `backend/scripts/run_harness_tests.sh` **y** `run_harness_tests.ps1`.
9. **Ayuda llana (plan 86):** la flag nueva necesita su entrada `PlainHelp`.
10. **Nunca 500 / nunca bloquear:** el endpoint de detección degrada siempre a
    una respuesta 200 con `detected: null` cuando no hay señal clara o hay error
    de lectura de disco (permiso denegado, proyecto sin ruta local, etc.) —
    nunca lanza al operador un error duro por esto.

## 4. Fases

> Comando de tests backend (por archivo, con el venv del repo — la suite
> completa está contaminada, plan 49):
> `"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/<archivo>" -q`
> ejecutado desde `Stacky Agents/backend` (los tests asumen cwd=backend).
> Gate frontend: `npx tsc --noEmit` en `Stacky Agents/frontend` (0 errores) +
> `npx vitest run <archivo>` SIEMPRE por archivo (vitest ya instalado desde el
> plan 87 F3.0 — nunca `npx vitest run` a secas, colectaría specs huérfanos).

### F0 — Presets estáticos puros (frontend, sin flag, sin backend)

**Objetivo:** catálogo de 4 presets de pipeline como datos TypeScript puros,
inmediatamente disponibles en el builder sin ninguna flag (mismo nivel de
"siempre visible" que `starterSpec` hoy).

**Archivo NUEVO:** `Stacky Agents/frontend/src/devops/pipelinePresets.ts`

```ts
/**
 * pipelinePresets.ts — Plan 97 F0
 * Catálogo ESTÁTICO de presets de pipeline por stack técnico.
 * Cada preset produce un PipelineSpecDraft completo y editable (specBuilder.ts).
 * NUNCA usa scripts de relleno tipo echo — todo comando es el REAL del stack.
 */
import type { PipelineSpecDraft } from "./specBuilder";

export type PresetId = "python" | "node" | "dotnet" | "generic";

export interface PipelinePreset {
  id: PresetId;
  label: string;          // texto del botón/tarjeta en la galería
  description: string;    // 1 frase en llano de qué hace
  build: () => PipelineSpecDraft;  // función pura, siempre devuelve spec NUEVO
}

function preset_python(): PipelineSpecDraft {
  return {
    name: "pipeline-python",
    stages: [{
      name: "build-and-test",
      jobs: [{
        name: "python-job",
        steps: [
          { name: "instalar-dependencias", script: "pip install -r requirements.txt", env: {} },
          { name: "lint", script: "python -m flake8 .", env: {} },
          { name: "test", script: "python -m pytest -q", env: {} },
        ],
        runner_tags: [], variables: {}, artifacts: [], services: [],
      }],
    }],
    variables: {},
    trigger_branches: [],
  };
}

function preset_node(): PipelineSpecDraft {
  return {
    name: "pipeline-node",
    stages: [{
      name: "build-and-test",
      jobs: [{
        name: "node-job",
        steps: [
          { name: "instalar-dependencias", script: "npm ci", env: {} },
          { name: "lint", script: "npm run lint --if-present", env: {} },
          { name: "test", script: "npm test --if-present", env: {} },
          { name: "compilar", script: "npm run build --if-present", env: {} },
        ],
        runner_tags: [], variables: {}, artifacts: [], services: [],
      }],
    }],
    variables: {},
    trigger_branches: [],
  };
}

function preset_dotnet(): PipelineSpecDraft {
  return {
    name: "pipeline-dotnet",
    stages: [{
      name: "build-and-test",
      jobs: [{
        name: "dotnet-job",
        steps: [
          { name: "restaurar", script: "dotnet restore", env: {} },
          { name: "compilar", script: "dotnet build --configuration Release --no-restore", env: {} },
          { name: "test", script: "dotnet test --no-build --configuration Release", env: {} },
        ],
        runner_tags: [], variables: {}, artifacts: [], services: [],
      }],
    }],
    variables: {},
    trigger_branches: [],
  };
}

function preset_generic(): PipelineSpecDraft {
  return {
    name: "pipeline-generico",
    stages: [{
      name: "build-and-test",
      jobs: [{
        name: "generic-job",
        steps: [
          { name: "compilar", script: "echo \"Reemplazá este paso por tu comando de build\"", env: {} },
          { name: "test", script: "echo \"Reemplazá este paso por tu comando de test\"", env: {} },
        ],
        runner_tags: [], variables: {}, artifacts: [], services: [],
      }],
    }],
    variables: {},
    trigger_branches: [],
  };
}

export const PIPELINE_PRESETS: readonly PipelinePreset[] = [
  { id: "python", label: "Python (pip + pytest)", description: "Instala dependencias con pip, corre flake8 y pytest.", build: preset_python },
  { id: "node", label: "Node (npm)", description: "Instala con npm ci, corre lint/test/build si existen los scripts.", build: preset_node },
  { id: "dotnet", label: ".NET (dotnet)", description: "Restaura, compila en Release y corre los tests con dotnet test.", build: preset_dotnet },
  { id: "generic", label: "Genérico (sin stack detectado)", description: "Plantilla neutra: reemplazá los comandos por los tuyos.", build: preset_generic },
];

export function getPresetById(id: PresetId): PipelinePreset {
  const p = PIPELINE_PRESETS.find((x) => x.id === id);
  if (!p) throw new Error(`Preset desconocido: ${id}`);
  return p;
}
```

**Nota de diseño (por qué el preset "generic" SÍ tiene `echo`):** es
deliberadamente el ÚNICO caso donde no hay comando real posible (no hay stack
identificable) — se distingue de `starterSpec` en que ofrece 2 steps
(compilar+test) en vez de 1, y su mensaje es explícito ("Reemplazá este paso"),
igual de detectable por el `PLACEHOLDER_LITERALS` del plan 93 si ese plan se
implementa después (no hay acoplamiento: son literales independientes, el plan
93 no necesita conocer este archivo).

**Tests PRIMERO** — archivo nuevo
`Stacky Agents/frontend/src/devops/pipelinePresets.test.ts` (vitest, TS puro,
sin imports de React):
- `all_presets_have_unique_ids`: los 4 `id` de `PIPELINE_PRESETS` son únicos y
  coinciden exactamente con `["python", "node", "dotnet", "generic"]`.
- `every_preset_builds_valid_spec`: para cada preset, `build()` produce un
  `PipelineSpecDraft` con `name` no vacío, ≥1 stage, ≥1 job, ≥1 step con
  `script` no vacío (pre-requisito de `validateSpecLocal` en 0 errores —
  test siguiente).
- `every_preset_passes_local_validation`: `validateSpecLocal(preset.build())`
  devuelve `[]` para los 4 presets (importar `validateSpecLocal` de
  `specBuilder.ts`, ya existente).
- `python_preset_has_no_echo_placeholder`: el script de NINGÚN step de
  `preset_python()` es igual a `starterSpec().stages[0].jobs[0].steps[0].script`
  (es decir, no reusa el literal placeholder de 87).
- `node_and_dotnet_presets_have_no_echo_placeholder`: ídem para node y dotnet.
- `generic_preset_is_the_only_one_with_echo`: de los 4 presets, únicamente
  `"generic"` tiene algún step cuyo script empieza con `"echo "`.
- `build_is_pure_and_immutable`: llamar `build()` dos veces devuelve objetos
  `!==` (referencias distintas) pero deep-equal (misma estructura) — mismo
  patrón que `addStage_appends_and_is_immutable` del plan 87 F3.
- `getPresetById_unknown_throws`: `getPresetById("foo" as any)` lanza.
- `getPresetById_known_returns_preset`: `getPresetById("python").id === "python"`.

Comando: `npx vitest run src/devops/pipelinePresets.test.ts` en
`Stacky Agents/frontend`.

**Criterio de aceptación BINARIO:** los 9 tests nuevos pasan +
`npx tsc --noEmit` 0 errores. Verificable con los comandos exactos de arriba.
**Flag:** ninguna (datos estáticos puros, mismo nivel que `starterSpec`;
siempre visibles, cero configuración).
**Impacto por runtime:** Codex CLI / Claude Code CLI / GitHub Copilot Pro:
NINGUNO (no hay ejecución de agentes involucrada). Fallback: no aplica.
**Trabajo del operador:** ninguno (los presets están disponibles siempre, sin
paso de configuración).

### F1 — Galería de presets en el builder (reemplaza/amplía el CTA de estado vacío)

**Objetivo:** que el operador vea y elija un preset con 1 click desde el mismo
lugar donde hoy solo tiene "Empezar con ejemplo".

**Archivo a editar:**
`Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx`

En el bloque del estado vacío (líneas 251-272, "C11 - CTA estado vacío"),
AGREGAR (sin quitar los botones existentes "Empezar con ejemplo" y "+ stage")
una galería de tarjetas de preset ANTES de esos dos botones:

```tsx
// Plan 97 F1 — galería de presets por stack (antes de "Empezar con ejemplo")
import { PIPELINE_PRESETS, type PipelinePreset } from '../../devops/pipelinePresets';

// ... dentro del componente, junto a los demás handlers:
const handleUsePreset = (preset: PipelinePreset) => {
  setSpec(preset.build());
};

// ... en el JSX, DENTRO de `{isEmpty ? (...) : (...)}`, ANTES del <p> "Agregá tu
// primer stage...":
<div className={styles.presetGallery} style={{ marginBottom: '16px' }}>
  <p className={styles.textMuted} style={{ marginBottom: '8px' }}>
    Elegí un preset para tu proyecto:
  </p>
  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
    {PIPELINE_PRESETS.map((preset) => (
      <button
        key={preset.id}
        onClick={() => handleUsePreset(preset)}
        className={styles.btnPrimary}
        style={{ padding: '10px 16px', textAlign: 'left' }}
        title={preset.description}
      >
        {preset.label}
      </button>
    ))}
  </div>
</div>
```

**Casos borde:**
- Si el operador ya tenía trabajo en edición (spec no vacío) y usa un preset
  desde OTRO punto de entrada que no sea el estado vacío (ver F3, detección
  automática), debe pedirse confirmación — mismo patrón YA existente en
  `handleImportYaml` (línea ~175: `if (!specsEqual(spec, emptySpec()) &&
  !window.confirm(...))`). En el estado vacío (`isEmpty === true`) no hace
  falta confirmar porque no hay nada que perder.
- Agregar `presetGallery` a `Stacky Agents/frontend/src/components/devops/devops.module.css`
  si el archivo de estilos del módulo lo requiere (clase mínima, solo
  `display:flex; flex-wrap:wrap; gap:8px;` si no se usa inline — a criterio del
  implementador seguir el patrón de estilos YA usado en el resto del archivo,
  que es mayormente inline `style={{}}`; no introducir un sistema de estilos
  nuevo).

**Tests** — no aplica test unitario de React (el proyecto no tiene
`@testing-library/react` instalada, gap preexistente fuera de scope, plan 87
C2). Verificación:
- `npx tsc --noEmit` en `Stacky Agents/frontend` — 0 errores.
- Verificación manual/grep: `grep -n "PIPELINE_PRESETS" frontend/src/components/devops/PipelineBuilderSection.tsx`
  debe encontrar el import y el `.map(...)`.

**Criterio de aceptación BINARIO:** `npx tsc --noEmit` 0 errores; el grep de
arriba encuentra 2+ ocurrencias (import + uso); los botones "Empezar con
ejemplo" y "+ stage" siguen presentes sin cambios (grep negativo: el diff del
archivo NO borra esas líneas, solo agrega antes).
**Flag:** ninguna (misma condición que F0 — siempre visible).
**Impacto por runtime:** NINGUNO en los 3 runtimes (declarado).
**Trabajo del operador:** ninguno (botones nuevos, ningún paso obligatorio —
seguir usando "Empezar con ejemplo" sigue funcionando igual que hoy).

### F2 — Backend: detector de stack por archivos de manifiesto (función pura + endpoint solo-lectura)

**Objetivo:** dado el proyecto activo, leer (solo-lectura) sus archivos de
manifiesto en disco y devolver el `PresetId` más probable, o `null` si no hay
señal clara — SIN LLM, determinista, testeable.

**Archivo NUEVO:** `Stacky Agents/backend/services/pipeline_stack_detector.py`

```python
"""pipeline_stack_detector.py — Plan 97 F2.
Detector determinista de stack técnico por archivos de manifiesto.
PURO respecto del resultado (misma entrada -> misma salida); el único I/O es
lectura de disco (os.path.exists), sin parseo de contenido, sin red, sin LLM.
"""
from __future__ import annotations
import os

# Orden de precedencia: si hay señales de más de un stack (monorepo), gana el
# primero de esta lista (Python > Node > .NET) — decisión arbitraria pero
# DETERMINISTA y documentada; el operador siempre puede elegir manualmente.
_MANIFEST_SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("python", ("requirements.txt", "pyproject.toml", "Pipfile")),
    ("node", ("package.json",)),
    ("dotnet", (".csproj", ".sln")),  # sufijos: se busca CUALQUIER archivo que TERMINE así
)


def detect_stack(project_root: str) -> str | None:
    """Devuelve 'python' | 'node' | 'dotnet' | None (sin señal clara o ruta inválida).
    NUNCA lanza: cualquier error de filesystem (permiso denegado, ruta
    inexistente) se traduce a None. Busca en el nivel raíz Y en subcarpetas de
    profundidad máxima 2 (para monorepos simples tipo backend/ + frontend/),
    con un tope de 500 entradas escaneadas para no colgar en árboles gigantes."""
    if not project_root or not os.path.isdir(project_root):
        return None
    try:
        scanned = 0
        found: set[str] = set()
        for dirpath, dirnames, filenames in os.walk(project_root):
            depth = dirpath[len(project_root):].count(os.sep)
            if depth >= 2:
                dirnames[:] = []  # no bajar más
            # ignorar carpetas pesadas conocidas (mismo criterio que .gitignore típico)
            dirnames[:] = [d for d in dirnames if d not in
                           ("node_modules", ".git", "venv", ".venv", "bin", "obj", "__pycache__")]
            for fname in filenames:
                scanned += 1
                if scanned > 500:
                    break
                for stack_id, patterns in _MANIFEST_SIGNALS:
                    for pat in patterns:
                        if pat.startswith(".") and fname.endswith(pat):
                            found.add(stack_id)
                        elif fname == pat:
                            found.add(stack_id)
            if scanned > 500:
                break
        for stack_id, _ in _MANIFEST_SIGNALS:
            if stack_id in found:
                return stack_id
        return None
    except OSError:
        return None
```

**Archivo a editar:** `Stacky Agents/backend/api/devops.py` — agregar ruta
nueva (mismo patrón guard-per-request que `parse_yaml_route`):

```python
from services.pipeline_stack_detector import detect_stack

@bp.get("/detect-stack")
def detect_stack_route():
    """Detecta el stack técnico del proyecto activo por archivos de manifiesto.
    SOLO-LECTURA. Flag propia STACKY_DEVOPS_STACK_DETECT_ENABLED."""
    if not getattr(_config.config, "STACKY_DEVOPS_STACK_DETECT_ENABLED", False):
        abort(404)
    project = request.args.get("project")
    if not project:
        return jsonify({"error": "project es obligatorio"}), 400
    # Reusar la resolución de ruta YA existente del proyecto (mismo helper que
    # usa el resto de api/devops.py y api/projects.py para ir de nombre -> ruta
    # en disco; NO inventar una ruta nueva de resolución).
    from project_manager import get_project_config
    cfg = get_project_config(project)
    root = (cfg or {}).get("local_path") or (cfg or {}).get("path")
    detected = detect_stack(root) if root else None
    return jsonify({"detected": detected})
```

(NOTA para el implementador: `get_project_config` y la key exacta de la ruta
local del proyecto — `local_path` vs `path` vs otra — deben confirmarse leyendo
`Stacky Agents/backend/project_manager.py` antes de escribir esta ruta; usar
`grep -n "def get_project_config" -A 20 project_manager.py` y tomar la key
REAL que ese diccionario devuelve. Si el proyecto no tiene ruta local
configurada, `root` queda `None` y `detect_stack(None)` ya está cubierto por
el guard `if not project_root` → devuelve `None`, nunca lanza.)

**Registro:** ninguno nuevo — la ruta se agrega al blueprint `devops` YA
registrado en `api/__init__.py` (sin tocar ese archivo).

**Tests PRIMERO** — archivo nuevo
`Stacky Agents/backend/tests/test_plan97_stack_detector.py`:
- `test_detect_python_by_requirements_txt`: carpeta temporal
  (`tmp_path` fixture de pytest) con solo `requirements.txt` → `"python"`.
- `test_detect_python_by_pyproject_toml`: solo `pyproject.toml` → `"python"`.
- `test_detect_node_by_package_json`: solo `package.json` → `"node"`.
- `test_detect_dotnet_by_csproj`: archivo `App/Foo.csproj` (subcarpeta) →
  `"dotnet"`.
- `test_detect_none_when_empty_dir`: carpeta vacía → `None`.
- `test_detect_none_when_path_missing`: ruta que no existe → `None` (nunca
  lanza).
- `test_detect_none_when_path_is_none`: `detect_stack(None)` → `None`.
- `test_detect_precedence_python_over_node`: carpeta con `requirements.txt` Y
  `package.json` → `"python"` (precedencia documentada).
- `test_detect_ignores_node_modules_depth`: `package.json` únicamente DENTRO de
  `node_modules/algo/package.json` (no en la raíz ni nivel 1) → `None` (la
  carpeta se excluye del walk).
- `test_detect_depth_cap_finds_nested_manifest`: `backend/requirements.txt`
  (profundidad 1) → `"python"` (monorepo simple soportado).

Comando: `"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan97_stack_detector.py" -q`
desde `Stacky Agents/backend`.

**Tests del endpoint** — archivo nuevo
`Stacky Agents/backend/tests/test_plan97_stack_detect_endpoint.py` (copiar
fixtures `app_flag_on`/`app_flag_off` del patrón de
`tests/test_plan87_devops_endpoints.py`, cambiando la key a
`STACKY_DEVOPS_STACK_DETECT_ENABLED`):
- `test_flag_off_404`: GET `/api/devops/detect-stack?project=x` con flag OFF →
  404.
- `test_missing_project_400`: flag ON, sin query param `project` → 400.
- `test_unknown_project_returns_null_detected`: flag ON, proyecto sin
  `local_path`/`path` configurado (mock de `get_project_config` → `None` o
  dict sin esas keys) → 200 con `{"detected": null}` (nunca error).
- `test_detects_and_returns_stack`: flag ON, `get_project_config` mockeado a
  una carpeta `tmp_path` con `package.json` → 200 con
  `{"detected": "node"}`.
- `test_route_registered`: centinela — `"/api/devops/detect-stack"` está en
  `[r.rule for r in app.url_map.iter_rules()]`.

Comando:
`"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan97_stack_detect_endpoint.py" -q`

**Ratchet:** registrar `test_plan97_stack_detector.py` y
`test_plan97_stack_detect_endpoint.py` en `backend/scripts/run_harness_tests.sh`
**y** `backend/scripts/run_harness_tests.ps1`.

**Criterio de aceptación BINARIO:** 10 + 5 = 15 tests nuevos verdes; ningún
test existente (`test_plan87_devops_endpoints.py`) se rompe.
**Flag:** `STACKY_DEVOPS_STACK_DETECT_ENABLED` — ver F0-bis abajo (alta de la
flag antes de que esta fase pueda mergearse activa; si se implementa F2 antes
que la flag, el endpoint debe quedar detrás de un `getattr(..., False)` que
por default sea `False` de todos modos mientras no exista `config.py`, así que
en la práctica esta fase y la subsección "Flag" de F0-bis se implementan
JUNTAS en el mismo commit — igual que la nota del plan 93 sobre F0+F3).
**Impacto por runtime:** NINGUNO en los 3 runtimes (UI + Flask puro).
**Trabajo del operador:** opt-in (activar la flag por UI para ver el botón de
detección; sin la flag, la galería de presets de F1 sigue funcionando igual,
manual).

### F0-bis — Flag `STACKY_DEVOPS_STACK_DETECT_ENABLED` (5 patas)

**Nota de orden:** esta fase se numera F0-bis porque LÓGICAMENTE es
prerrequisito de F2/F3 (igual que el patrón de la serie 93/94/95/96 donde F0 es
siempre la flag), pero se documenta después de F0/F1/F2 en este texto para que
el detector (F2) ya esté completamente especificado cuando se lee la flag que
lo protege. **Implementar ANTES o EN EL MISMO commit que F2** (no después).

**Objetivo:** dar de alta `STACKY_DEVOPS_STACK_DETECT_ENABLED` en las 5 patas
sin romper ningún meta-test — mismo patrón EXACTO que las flags de la serie
87-91/93.

**Archivos a editar:**
1. `Stacky Agents/backend/config.py` — junto a `STACKY_DEVOPS_PANEL_ENABLED`,
   copiando el patrón EXACTO de parseo de la flag vecina:
   ```python
   # Plan 97 — Deteccion opt-in de stack tecnico para presets de pipeline. Default OFF.
   STACKY_DEVOPS_STACK_DETECT_ENABLED: bool = os.getenv(
       "STACKY_DEVOPS_STACK_DETECT_ENABLED", "false"
   ).lower() in ("1", "true", "yes")
   ```
2. `Stacky Agents/backend/services/harness_flags.py`:
   - `_CATEGORY_KEYS["devops"]`: agregar
     `"STACKY_DEVOPS_STACK_DETECT_ENABLED",  # Plan 97 — deteccion de stack para presets`.
   - `FlagSpec` COMPLETO (con `label` y `group`, campos REQUERIDOS del
     dataclass):
     ```python
     FlagSpec(
         key="STACKY_DEVOPS_STACK_DETECT_ENABLED",
         type="bool",
         label="Detección de stack para presets (Plan 97)",
         description=(
             "Plan 97 — Agrega el boton 'Detectar stack de mi proyecto' en el "
             "builder de pipelines: lee (solo lectura) los archivos de manifiesto "
             "del proyecto (requirements.txt, package.json, *.csproj) y "
             "preselecciona el preset de pasos mas probable. Default OFF: sin "
             "esta flag, la galeria de presets sigue disponible pero manual."
         ),
         group="global",
         env_only=False,
         requires="STACKY_DEVOPS_PANEL_ENABLED",
     ),
     ```
     SIN `default=` (gotcha `_CURATED_DEFAULTS_ON`). SIN `reserved=` (tiene
     consumidor real en F2/F3).
3. `Stacky Agents/backend/services/harness_flags_help.py` — entrada
   `PlainHelp`: ON = "un botón te sugiere el tipo de proyecto (Python/Node/.NET)
   para armar el pipeline con los comandos correctos"; OFF = "elegís el preset
   vos mismo de una lista, sin detección automática".
4. `Stacky Agents/backend/harness_defaults.env` — agregar la línea
   `STACKY_DEVOPS_STACK_DETECT_ENABLED=false` (orden alfabético; el generador
   canónico es `deployment/export_harness_defaults.py` — solo AGREGAR la línea,
   no regenerar el archivo completo ni tocar líneas ajenas, mismo cuidado que
   señaló la crítica del plan 93 C8).
5. `Stacky Agents/backend/tests/test_harness_flags_requires.py` — agregar la
   arista al `_REQUIRES_MAP_FROZEN`:
   ```python
   "STACKY_DEVOPS_STACK_DETECT_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 97
   ```
   (R4 profundidad 1 OK: `STACKY_DEVOPS_PANEL_ENABLED` no tiene `requires`
   propio — verificado en `harness_flags.py`.)

**Tests PRIMERO** — archivo nuevo
`Stacky Agents/backend/tests/test_plan97_stack_detect_flag.py` (espejo de
`tests/test_plan93_preflight_flag.py` / `test_plan91_servers_flag.py`,
cambiando la key):
- `test_f0_flag_in_registry`: `env_only is False`,
  `requires == "STACKY_DEVOPS_PANEL_ENABLED"`, `group == "global"`, `label` no
  vacío, `default is None`.
- `test_f0_flag_in_category_devops`.
- `test_f0_config_default_off` (patrón `monkeypatch.delenv` +
  `importlib.reload(config)`).
- `test_f0_flag_has_plain_help`.
- `test_f0_harness_defaults_contains_flag` (literal
  `STACKY_DEVOPS_STACK_DETECT_ENABLED=false`).
- No-regresión: `tests/test_harness_flags.py` + `tests/test_flag_wiring.py` +
  `tests/test_harness_flags_requires.py`.

Comando:
`"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan97_stack_detect_flag.py" "Stacky Agents/backend/tests/test_harness_flags.py" "Stacky Agents/backend/tests/test_flag_wiring.py" "Stacky Agents/backend/tests/test_harness_flags_requires.py" -q`
desde `Stacky Agents/backend`.

**Ratchet:** registrar el archivo en ambos scripts.
**Criterio de aceptación BINARIO:** 5 tests nuevos + 3 meta-tests verdes; flag
default OFF verificado por `test_f0_config_default_off`.
**Flag:** `STACKY_DEVOPS_STACK_DETECT_ENABLED` (default OFF).
**Impacto por runtime:** NINGUNO. **Trabajo del operador:** ninguno (opt-in).

### F3 — Frontend: botón "Detectar stack de mi proyecto" (gated por flag)

**Objetivo:** conectar el endpoint de F2 a la UI de la galería de F1, gateado
por la flag de F0-bis, con fallback explícito si está OFF o si la detección no
encuentra nada.

**Archivo a editar:**
`Stacky Agents/frontend/src/api/endpoints.ts` — extender el namespace `DevOps`
ya existente (mismo objeto que expone `health`/`parseYaml`):

```ts
export const DevOps = {
  // ...health, parseYaml existentes sin cambios...
  detectStack: (project: string) =>
    api.get<{ detected: string | null }>(`/api/devops/detect-stack?project=${encodeURIComponent(project)}`),
};
```

**Archivo a editar:**
`Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx` —
DENTRO del bloque de galería agregado en F1, si
`ctx.health.stack_detect_enabled === true` (agregar esa key aditiva al health
del backend en `api/devops.py` `devops_health_route`, patrón idéntico a las
demás keys booleanas del dict), mostrar un botón adicional ANTES de la galería:

```tsx
// Plan 97 F3 — detección opt-in (solo si la flag está ON vía health)
const [detecting, setDetecting] = useState(false);
const [detectError, setDetectError] = useState<string | null>(null);

const handleDetectStack = async () => {
  setDetecting(true);
  setDetectError(null);
  try {
    const { detected } = await DevOps.detectStack(project);
    if (detected) {
      const preset = PIPELINE_PRESETS.find((p) => p.id === detected);
      if (preset) {
        if (!isEmpty && !window.confirm('Vas a reemplazar el pipeline en edición con el preset detectado. ¿Continuar?')) {
          return;
        }
        setSpec(preset.build());
        return;
      }
    }
    setDetectError('No pude detectar el stack de tu proyecto. Elegí un preset de la lista.');
  } catch (e) {
    setDetectError(`No se pudo detectar el stack: ${e instanceof Error ? e.message : String(e)}`);
  } finally {
    setDetecting(false);
  }
};

// JSX, antes de la galería de F1, solo si ctx.health.stack_detect_enabled:
{ctx.health.stack_detect_enabled && (
  <div style={{ marginBottom: '12px' }}>
    <button onClick={() => void handleDetectStack()} disabled={detecting} className={styles.btnPrimary} style={{ padding: '8px 16px' }}>
      {detecting ? 'Detectando…' : 'Detectar stack de mi proyecto'}
    </button>
    {detectError && <p className={styles.textWarn} style={{ marginTop: '8px' }}>{detectError}</p>}
  </div>
)}
```

(NOTA: `ctx`/`project` deben tomarse de las props REALES que
`PipelineBuilderSection` ya recibe — confirmar leyendo la firma del componente
en el archivo antes de escribir esto; si el componente hoy no recibe `project`
como prop, usar la misma fuente que usa `handleSaveDraft`/`handleLoadDraft`
para saber el proyecto activo, sin inventar una prop nueva si ya hay una vía
existente.)

**Fallback explícito si la flag está OFF:** el botón simplemente no se
renderiza (`ctx.health.stack_detect_enabled` es `undefined`/`false`) — la
galería manual de F1 sigue 100% funcional. Esto es EL fallback: no hace falta
ningún otro camino alterno.

**Tests:** no hay test de componente React (mismo gap preexistente que F1).
Verificación:
- `npx tsc --noEmit` — 0 errores.
- grep: `grep -n "detectStack" frontend/src/api/endpoints.ts frontend/src/components/devops/PipelineBuilderSection.tsx` encuentra ambas ocurrencias.

**Criterio de aceptación BINARIO:** `npx tsc --noEmit` 0 errores; los 2 greps
de arriba encuentran matches; con la flag OFF (health sin la key o en `false`)
el botón de detección no aparece — verificable manualmente arrancando el
backend con `STACKY_DEVOPS_STACK_DETECT_ENABLED=false` (default) y confirmando
en la respuesta de `GET /api/devops/health` que la key es `false`/ausente.
**Flag:** `STACKY_DEVOPS_STACK_DETECT_ENABLED` (gate inline por health, mismo
patrón que el resto del panel).
**Impacto por runtime:** NINGUNO en los 3 runtimes.
**Trabajo del operador:** opt-in (activar la flag por UI desde
`HarnessFlagsPanel`, categoría "DevOps", para ver el botón; sin activarla, la
galería manual de presets sigue disponible sin ningún paso adicional).

### F4 — Cierre: no-regresión + checklist binario

**Comandos (todos deben pasar):**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_plan97_stack_detector.py tests/test_plan97_stack_detect_endpoint.py tests/test_plan97_stack_detect_flag.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan87_devops_endpoints.py tests/test_harness_flags.py tests/test_flag_wiring.py tests/test_harness_flags_requires.py -q
cd "../frontend"
npx vitest run src/devops/pipelinePresets.test.ts
npx tsc --noEmit
```

**Checklist binario:**
- [ ] Los 4 presets (`python`/`node`/`dotnet`/`generic`) generan spec válido
      (`validateSpecLocal` → `[]`) y ninguno usa el literal placeholder de
      `starterSpec`, salvo `generic` que lo declara explícitamente distinto.
- [ ] La galería de presets aparece en el estado vacío del builder JUNTO a
      (no en reemplazo de) "Empezar con ejemplo" y "+ stage" — ambos botones
      preexistentes intactos.
- [ ] Flag `STACKY_DEVOPS_STACK_DETECT_ENABLED` OFF por default: el endpoint
      `/api/devops/detect-stack` da 404, el botón de detección no aparece,
      byte-idéntico al comportamiento previo a este plan.
- [ ] Con la flag ON, detectar un proyecto con `requirements.txt` preselecciona
      el preset `python`; un proyecto sin manifiestos reconocibles devuelve
      `detected: null` y la UI muestra el mensaje de "no pude detectar" sin
      romper nada.
- [ ] El detector NUNCA lanza excepción hacia el endpoint (ruta inexistente,
      permiso denegado, symlink roto) — siempre 200 con `detected` en `null` o
      el string esperado.
- [ ] Arista `STACK_DETECT_ENABLED → PANEL_ENABLED` en `_REQUIRES_MAP_FROZEN`
      y `test_harness_flags_requires.py` verde.
- [ ] Paridad ADO+GitLab: los 4 presets generan YAML válido con
      `to_ado_yaml`/`to_gitlab_yaml` sin cambios en esos renderers (verificar
      manualmente pegando el output de `preset.build()` de cada preset en
      `dict_to_spec` + `to_ado_yaml`/`to_gitlab_yaml` desde una consola Python
      del venv — no hace falta test automatizado nuevo porque los renderers ya
      tienen su propia suite intacta y estos specs no usan ningún campo fuera
      del contrato congelado `test_f1_spec_shape_frozen` del plan 87).
- [ ] Tests registrados en ambos scripts de ratchet
      (`run_harness_tests.sh`/`.ps1`).
- [ ] Cero cambios en `DevOpsPage.tsx` (el shell no se toca — todo el trabajo
      vive dentro de `PipelineBuilderSection.tsx` y archivos nuevos).

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Monorepo con más de un stack (ej. backend Python + frontend Node) | Precedencia documentada y determinista (Python > Node > .NET); el operador siempre puede ignorar la sugerencia y elegir manualmente (HITL) |
| Proyecto sin ruta local configurada (`local_path` ausente) | `detect_stack(None)` devuelve `None` sin lanzar; endpoint responde 200 con `detected: null` |
| Árbol de archivos gigante (repo grande) cuelga el detector | Tope de 500 entradas escaneadas + profundidad máxima 2 + exclusión de carpetas pesadas conocidas (`node_modules`, `.git`, `venv`, etc.) |
| Presets quedan desactualizados si cambia una convención (ej. `npm ci` deja de ser el estándar) | Son datos estáticos editables por el operador tras aplicarlos; no hay acoplamiento a versiones de herramientas — si cambia la convención, se edita `pipelinePresets.ts` en un plan futuro sin tocar el contrato |
| Confusión entre "preset" (este plan) y "template de publicación" (plan 88) | Nombres y archivos distintos (`pipelinePresets.ts` vs `publication_spec.py`); ámbitos distintos (pipeline de CI vs. publicación de proceso batch/agenda) — sin colisión de conceptos ni de flags |
| El detector encuentra un `.csproj`/`package.json` de una herramienta interna (ej. carpeta de tooling) y detecta mal | Aceptable en v1: es solo una SUGERENCIA preseleccionada, nunca se aplica sin click explícito del operador; documentado como fuera de scope refinar la heurística más allá de manifiestos en la raíz/nivel 1-2 |

## 6. Fuera de scope (v1)

- Presets para más stacks (Go, Rust, Java/Maven, PHP, etc.) — se agregan en un
  plan futuro incremental sobre `PIPELINE_PRESETS` sin romper el contrato.
- Detección por contenido de archivos (parsear `package.json` para saber si es
  React vs Vue, o `requirements.txt` para saber si es Django vs Flask) — v1
  detecta únicamente por PRESENCIA de manifiesto, no por contenido.
- Integración con el generador declarativo del plan 73 (`pipeline_generator.py`)
  más allá de que ambos comparten el mismo `PipelineSpec` — este plan no toca
  ese endpoint.
- Integración con el preflight del plan 93 (que detecta placeholders YA
  puestos) — son complementarios mencionados en el objetivo, pero este plan no
  depende de que 93 esté implementado ni lo modifica.
- Presets específicos de publicación (batch/agenda) del plan 88 — ese plan
  cubre "publicar un proceso ya compilado"; este plan cubre "compilar/testear
  el código fuente". Ámbitos distintos, sin fusión en v1.
- Guardar el preset elegido como "default del proyecto" para futuros pipelines
  — v1 es un punto de partida editable, no una preferencia persistida.

## 7. Glosario

- **Preset de pipeline**: `PipelineSpecDraft` completo y editable con pasos
  reales (no placeholders) para un stack técnico específico.
- **Stack técnico**: el lenguaje/ecosistema de un proyecto (Python, Node,
  .NET) inferido por la presencia de sus archivos de manifiesto estándar.
- **Manifiesto**: archivo que declara dependencias/config de un proyecto
  (`requirements.txt`, `package.json`, `*.csproj`, etc.).
- **`starterSpec`**: el ejemplo único y genérico que ya existía desde el plan
  87 (1 stage/1 job/1 step con `echo`); sigue existiendo intacto, este plan lo
  complementa, no lo reemplaza.
- **Detección opt-in**: capacidad protegida por flag propia, apagada por
  default, que el operador activa explícitamente por UI.
- **HITL (Human-In-The-Loop)**: ninguna acción mutante (aplicar un preset,
  commitear, disparar) ocurre sin un click explícito del operador.

## 8. Orden de implementación

1. F0 — catálogo de presets estáticos (`pipelinePresets.ts`) + tests vitest.
2. F1 — galería de presets en el builder (siempre visible, sin flag).
3. F0-bis — flag `STACKY_DEVOPS_STACK_DETECT_ENABLED` (5 patas) + tests.
4. F2 — detector de stack (`pipeline_stack_detector.py`) + endpoint + tests
   (implementar EN EL MISMO commit que F0-bis o inmediatamente después, nunca
   antes — la flag debe existir para que el guard del endpoint compile).
5. F3 — botón de detección en el frontend, gateado por health.
6. F4 — cierre y checklist binario.

## 9. Definición de Hecho (DoD)

- F0: 9 tests vitest verdes (`pipelinePresets.test.ts`) + `tsc` 0 errores.
- F0-bis: 5 tests backend verdes + 3 meta-tests no-regresión verdes.
- F2: 10 + 5 = 15 tests backend verdes (`test_plan97_stack_detector.py` +
  `test_plan97_stack_detect_endpoint.py`).
- F1/F3: `tsc --noEmit` 0 errores + greps de integración verificados (sin
  suite de componente React, gap preexistente fuera de scope).
- Flag `STACKY_DEVOPS_STACK_DETECT_ENABLED` default OFF; con OFF, byte-idéntico
  al comportamiento previo a este plan (endpoint 404, botón ausente).
- Los 4 presets pasan `validateSpecLocal` en 0 errores y ninguno duplica el
  literal placeholder de `starterSpec` (salvo `generic`, declarado distinto).
- Paridad ADO+GitLab preservada: los presets usan el mismo `PipelineSpecDraft`
  y los mismos renderers ya existentes, sin bifurcación por tracker.
- Cero cambios de contrato en `starterSpec`, `emptySpec`, `validateSpecLocal`,
  `PipelineSpec`/`_validate_spec`, `to_ado_yaml`/`to_gitlab_yaml`,
  `DevOpsPage.tsx` (shell intacto).
- Tests registrados en `run_harness_tests.sh` y `run_harness_tests.ps1`.
- `_REQUIRES_MAP_FROZEN` actualizado con la arista nueva y su meta-test verde.
