# Plan 97 — Presets de pasos de pipeline por stack técnico (compilar/test/lint) con detección opcional

**Estado:** CRITICADO (v2 → v3 — APROBADO-CON-CAMBIOS)
**Versión:** v3
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

## Changelog v1 → v2 (crítica adversarial)

Crítica del juez el 2026-07-05. Veredicto: **APROBADO-CON-CAMBIOS** (v1 tenía 1
defecto BLOQUEANTE en la letra, resuelto acá). Hallazgos y fixes aplicados:

- **C1 (BLOQUEANTE, resuelto):** F2 leía las keys `local_path`/`path`, que **no
  existen** en `project_manager.get_project_config`. La key real es
  **`workspace_root`** (`project_manager.py:12,152,155`). Con la letra de v1 el
  detector nacía **muerto en producción** (`root` siempre `None` → `detected`
  siempre `null`) y — peor — los tests del endpoint mockean
  `get_project_config`, así que quedaba **verde-falso**. v2 usa `workspace_root`
  y agrega un test de cableado que fija la key real (F2, C1).
- **C2 (IMPORTANTE, resuelto):** F3 usaba una variable `project` que el
  componente NO tiene. `PipelineBuilderSection` deriva el proyecto activo de
  `useWorkbench((s) => s.activeProject)?.name` como `activeProject`
  (`PipelineBuilderSection.tsx:50-51`). Además faltaba guard para proyecto
  activo vacío (`''` → 400 innecesario). v2 usa `activeProject`, desactiva el
  botón y hace early-return si está vacío (F3, C2).
- **C3 (IMPORTANTE — pedido explícito del operador, resuelto con
  [ADICIÓN ARQUITECTO]):** v1 entregaba SOLO 4 presets de pipeline completo
  (2-4 steps c/u). El operador pidió *"muchos elementos scripts de acciones de
  pipeline prehechas"*. Un preset entero no cubre el caso "quiero AGREGAR una
  acción concreta (docker build, publicar artefacto, cobertura, lint…) a un job
  que ya tengo". v2 agrega **F1-bis: biblioteca de ≥20 acciones de pipeline
  prehechas (step snippets)** insertables con 1 click en el job seleccionado,
  reusando el helper inmutable de steps de `specBuilder.ts`.
- **C4 (MENOR, resuelto):** `detect_stack` calculaba la profundidad con
  `dirpath[len(project_root):]`, que se desfasa si `project_root` trae separador
  final. v2 normaliza con `os.path.normpath` al entrar (F2, C4).
- **C5 (MENOR, resuelto):** el KPI decía "nunca un `echo` de relleno / 0%" y el
  preset `generic` sí trae `echo`. v2 reformula el KPI para que sea consistente
  con la excepción documentada de `generic` (§1, C5).
- **C6 (MENOR, resuelto):** contadores de tests actualizados por el test de
  cableado nuevo de C1 (F2: 10 + 6 = 16; F1-bis: 8 vitest) en F2/F4/§9.

---

## Changelog v2 → v3 (2ª crítica adversarial — foco: MÁS acciones prehechas)

Segunda pasada del juez el 2026-07-05 (el operador REITERÓ el pedido de "muchas
acciones de pipeline prehechas"). Veredicto: **APROBADO-CON-CAMBIOS**. Cambios:

- **C1 (IMPORTANTE, resuelto):** el inserter de acciones de F1-bis solo aparecía
  con un job YA seleccionado, así que en el builder VACÍO (0 stages) el operador
  no-experto no llegaba a la biblioteca en su primer contacto. v3 agrega, en el
  estado vacío, un botón "Insertá acciones sueltas (job vacío)" que scaffolda
  stage+job y lo selecciona, reusando `addStage`/`addJob`/`setSelected` (F1-ter).
- **C2 (IMPORTANTE, resuelto):** no había garantía AUTOMATIZADA de paridad YAML
  para los snippets (riel duro #5). v3 fija el invariante testeable "todo script
  de snippet es de UNA sola línea, no vacío, sin `$(`"
  (`every_snippet_script_is_single_line`) — el camino que ambos renderers ya
  manejan idéntico (F1-bis/F1-ter).
- **C3 (IMPORTANTE — pedido reiterado, [ADICIÓN ARQUITECTO]):** el catálogo pasa
  de ≥20 a **≥40 acciones** (categorías nuevas `seguridad` y `versionar`; stacks
  Go/Rust/Java-Maven/Gradle/PHP) y se agregan **Recetas**: bundles ordenados de
  acciones que se insertan de una en el job (CI Python/Node/.NET/Go, Docker
  build+push, Calidad Python), reusando `appendStep` en un fold (F1-ter).
- **C4 (MENOR, resuelto):** con 40+ acciones el `<select>` se vuelve inmanejable;
  v3 agrega un filtro por texto sobre la biblioteca (F1-ter).
- **C5 (MENOR, resuelto):** el inserter podía quedar visible con un `selected`
  fuera de rango tras borrar stage/job; v3 lo condiciona a que el índice exista
  realmente (F1-ter).

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
- El operador llega de "lienzo vacío" a un pipeline con pasos REALES de
  compilar+test en ≤ 2 clicks (elegir preset + opcionalmente confirmar
  detección), igual que hoy con "Empezar con ejemplo" (mismo costo de UX, más
  valor). Ningún preset de stack usa `echo` de relleno; el único con `echo` es
  el preset `generic` (plantilla neutra explícita, sin stack identificable) —
  ver nota de diseño en F0 (C5).
- 4 presets de pipeline completo desde el día 1 (Python, Node, .NET, Genérico),
  cada uno generando YAML válido para ADO y GitLab (paridad dura, criterio
  binario F2/F3).
- **[ADICIÓN ARQUITECTO]** ≥ 40 acciones de pipeline prehechas (step snippets)
  disponibles desde el día 1 (instalar deps, lint, test, cobertura, compilar,
  empaquetar, publicar artefacto/imagen, calidad, seguridad, versionar) para
  Python/Node/.NET/Go/Rust/Java/PHP, insertables con 1 click en el job
  seleccionado y editables después. Además **≥ 6 recetas** (bundles ordenados:
  CI Python/Node/.NET/Go, Docker build+push, Calidad Python) que insertan varios
  pasos de una sola vez — el "muchos elementos scripts de acciones prehechas" que
  pidió el operador, ahora accesible incluso desde el builder vacío (F1-bis +
  F1-ter). Provider-neutrales: el mismo snippet/receta vale para ADO y GitLab
  (sin interpolación `$(VAR)`/`$VAR`, scripts de una sola línea).
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

### F1-bis — [ADICIÓN ARQUITECTO] Biblioteca de acciones de pipeline prehechas (step snippets)

**Por qué (pedido explícito del operador, C3):** los 4 presets de F0 arman un
pipeline COMPLETO desde cero, pero no cubren el caso "ya tengo un job y quiero
AGREGARLE una acción concreta" (docker build, publicar artefacto, correr
cobertura, un lint puntual). El operador pidió textualmente "muchos elementos
scripts de acciones de pipeline prehechas". Esta fase entrega una **biblioteca de
acciones individuales** (base ≥26 acá; ampliada a **≥40 + recetas** en F1-ter),
cada una un `StepDraft` real y editable, insertable con 1 click en el job
seleccionado. Es datos estáticos TypeScript puros (mismo
patrón y mismo "siempre visible sin flag" que los presets de F0), reusa el
contrato `StepDraft` y el patrón inmutable de `addStep` ya existente
(`specBuilder.ts:329`), y no toca ningún renderer ni el backend.

**Regla de paridad dura (ADO+GitLab):** el CUERPO del script se pasa VERBATIM a
ambos renderers, y la sintaxis de interpolación de variables difiere entre
providers (ADO `$(VAR)` vs GitLab `$VAR`). Por eso **ningún snippet usa
interpolación de variables del runner**: donde haría falta un valor (ej. tag de
imagen), el snippet trae un literal editable (`myapp:latest`) que el operador
cambia. Así el mismo snippet es válido en ADO y en GitLab sin bifurcar.

**Archivo NUEVO:** `Stacky Agents/frontend/src/devops/pipelineStepSnippets.ts`

```ts
/**
 * pipelineStepSnippets.ts — Plan 97 F1-bis
 * Biblioteca ESTÁTICA de acciones de pipeline prehechas (step snippets).
 * Cada snippet produce un StepDraft real y editable (specBuilder.ts).
 * Provider-neutral: sin interpolación $(VAR)/$VAR (paridad ADO+GitLab).
 */
import type { StepDraft } from "./specBuilder";

export type SnippetCategory =
  | "dependencias" | "lint" | "test" | "build" | "publicar" | "calidad"
  | "seguridad" | "versionar";  // F1-ter — categorías nuevas

export const SNIPPET_CATEGORIES: readonly SnippetCategory[] = [
  "dependencias", "lint", "test", "build", "publicar", "calidad",
  "seguridad", "versionar",
];

export interface StepSnippet {
  id: string;               // único, kebab-case
  category: SnippetCategory;
  label: string;            // texto corto en la UI (español)
  description: string;      // 1 frase en llano
  build: () => StepDraft;   // función pura, siempre devuelve StepDraft NUEVO
}

function step(name: string, script: string): StepDraft {
  return { name, script, env: {} };
}

export const PIPELINE_STEP_SNIPPETS: readonly StepSnippet[] = [
  // ── dependencias ──
  { id: "dep-pip-install", category: "dependencias", label: "pip install (requirements.txt)", description: "Instala dependencias Python con pip.", build: () => step("instalar-dependencias", "pip install -r requirements.txt") },
  { id: "dep-poetry-install", category: "dependencias", label: "poetry install", description: "Instala dependencias con Poetry.", build: () => step("instalar-dependencias", "poetry install --no-interaction") },
  { id: "dep-npm-ci", category: "dependencias", label: "npm ci", description: "Instala dependencias Node de forma reproducible.", build: () => step("instalar-dependencias", "npm ci") },
  { id: "dep-yarn-install", category: "dependencias", label: "yarn install (frozen)", description: "Instala dependencias con Yarn sin tocar el lockfile.", build: () => step("instalar-dependencias", "yarn install --frozen-lockfile") },
  { id: "dep-dotnet-restore", category: "dependencias", label: "dotnet restore", description: "Restaura paquetes NuGet.", build: () => step("restaurar", "dotnet restore") },
  // ── lint ──
  { id: "lint-flake8", category: "lint", label: "flake8", description: "Chequeo de estilo Python con flake8.", build: () => step("lint", "python -m flake8 .") },
  { id: "lint-black-check", category: "lint", label: "black --check", description: "Verifica formato Python con black (sin modificar).", build: () => step("lint-formato", "python -m black --check .") },
  { id: "lint-ruff", category: "lint", label: "ruff check", description: "Linter Python rápido con ruff.", build: () => step("lint", "python -m ruff check .") },
  { id: "lint-eslint", category: "lint", label: "npm run lint", description: "Corre el script de lint de Node si existe.", build: () => step("lint", "npm run lint --if-present") },
  { id: "lint-prettier-check", category: "lint", label: "prettier --check", description: "Verifica formato con Prettier (sin modificar).", build: () => step("lint-formato", "npx prettier --check .") },
  { id: "lint-dotnet-format", category: "lint", label: "dotnet format --verify", description: "Verifica formato .NET sin aplicar cambios.", build: () => step("lint-formato", "dotnet format --verify-no-changes") },
  // ── test ──
  { id: "test-pytest", category: "test", label: "pytest", description: "Corre la suite de tests Python.", build: () => step("test", "python -m pytest -q") },
  { id: "test-pytest-cov", category: "test", label: "pytest + cobertura", description: "Corre pytest generando reporte de cobertura XML.", build: () => step("test-cobertura", "python -m pytest --cov --cov-report=xml") },
  { id: "test-npm-test", category: "test", label: "npm test", description: "Corre el script de tests de Node si existe.", build: () => step("test", "npm test --if-present") },
  { id: "test-jest", category: "test", label: "jest --ci", description: "Corre Jest en modo CI.", build: () => step("test", "npx jest --ci") },
  { id: "test-dotnet", category: "test", label: "dotnet test", description: "Corre los tests .NET en Release.", build: () => step("test", "dotnet test --no-build --configuration Release") },
  // ── build ──
  { id: "build-npm", category: "build", label: "npm run build", description: "Compila el proyecto Node si existe el script.", build: () => step("compilar", "npm run build --if-present") },
  { id: "build-dotnet-release", category: "build", label: "dotnet build (Release)", description: "Compila la solución .NET en Release.", build: () => step("compilar", "dotnet build --configuration Release --no-restore") },
  { id: "build-python", category: "build", label: "python -m build", description: "Empaqueta el proyecto Python (sdist+wheel).", build: () => step("compilar", "python -m build") },
  { id: "build-docker", category: "build", label: "docker build", description: "Construye la imagen Docker (editá el tag).", build: () => step("docker-build", "docker build -t myapp:latest .") },
  // ── publicar / artefactos ──
  { id: "pub-docker-push", category: "publicar", label: "docker push", description: "Publica la imagen Docker (editá el tag).", build: () => step("docker-push", "docker push myapp:latest") },
  { id: "pub-dotnet-publish", category: "publicar", label: "dotnet publish", description: "Publica el binario .NET a ./publish.", build: () => step("publicar", "dotnet publish -c Release -o ./publish") },
  { id: "pub-npm-pack", category: "publicar", label: "npm pack", description: "Genera el tarball del paquete npm.", build: () => step("empaquetar", "npm pack") },
  { id: "pub-tar-dist", category: "publicar", label: "tar dist/", description: "Empaqueta la carpeta dist en un .tgz (tar disponible en Windows y Linux modernos).", build: () => step("empaquetar", "tar -czf dist.tgz dist") },
  // ── calidad ──
  { id: "qual-sonar", category: "calidad", label: "sonar-scanner", description: "Análisis de calidad con SonarQube (lee sonar-project.properties).", build: () => step("calidad", "sonar-scanner") },
  { id: "qual-coverage-report", category: "calidad", label: "coverage report", description: "Muestra el reporte de cobertura Python en consola.", build: () => step("cobertura", "python -m coverage report") },
];

export function getSnippetsByCategory(cat: SnippetCategory): readonly StepSnippet[] {
  return PIPELINE_STEP_SNIPPETS.filter((s) => s.category === cat);
}
```

**Archivo a editar (helper inmutable, reuso):**
`Stacky Agents/frontend/src/devops/specBuilder.ts` — agregar UNA función pura
espejo de `addStep` (misma firma inmutable + guards NOOP idénticos), que
inserta un `StepDraft` YA armado en vez de uno vacío:

```ts
// Plan 97 F1-bis — inserta un step prefabricado (snippet) en un job, inmutable.
// Mismo patrón/guards que addStep (specBuilder.ts:329); solo cambia que el step
// llega ya construido en vez de crear el placeholder "step-1".
export function appendStep(
  spec: PipelineSpecDraft, stageIndex: number, jobIndex: number, step: StepDraft
): PipelineSpecDraft {
  if (stageIndex < 0 || stageIndex >= spec.stages.length) return spec;
  const stages = spec.stages.map((s, si) => {
    if (si !== stageIndex) return s;
    if (jobIndex < 0 || jobIndex >= s.jobs.length) return s;
    const jobs = s.jobs.map((j, ji) =>
      ji !== jobIndex ? j : { ...j, steps: [...j.steps, { ...step }] });
    return { ...s, jobs };
  });
  return { ...spec, stages };
}
```

**Archivo a editar (UI):**
`Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx` —
reusar el estado `selected` YA existente (`{ si?, ji?, sti? }`, línea 61) y
`setSpec` (línea 54). Cuando hay un JOB seleccionado (`selected?.si != null &&
selected?.ji != null`), mostrar un selector categorizado de acciones + botón
"Insertar acción". Agregar al import de `../../devops/specBuilder` el símbolo
`appendStep`, e importar la biblioteca:

```tsx
// Plan 97 F1-bis — biblioteca de acciones prehechas
import { PIPELINE_STEP_SNIPPETS, SNIPPET_CATEGORIES, getSnippetsByCategory } from '../../devops/pipelineStepSnippets';
// ... y agregar `appendStep` a la lista de imports existente de specBuilder ...

const [snippetId, setSnippetId] = useState<string>('');

const handleInsertSnippet = () => {
  if (selected?.si == null || selected?.ji == null || !snippetId) return;
  const snip = PIPELINE_STEP_SNIPPETS.find((s) => s.id === snippetId);
  if (!snip) return;
  setSpec((prev) => appendStep(prev, selected.si!, selected.ji!, snip.build()));
};

// JSX — solo cuando hay un job seleccionado (junto a los controles del job):
{selected?.si != null && selected?.ji != null && (
  <div style={{ marginTop: '8px', display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
    <label className={styles.textMuted}>Insertar acción prehecha:</label>
    <select value={snippetId} onChange={(e) => setSnippetId(e.target.value)}>
      <option value="">— elegí una acción —</option>
      {SNIPPET_CATEGORIES.map((cat) => (
        <optgroup key={cat} label={cat}>
          {getSnippetsByCategory(cat).map((s) => (
            <option key={s.id} value={s.id} title={s.description}>{s.label}</option>
          ))}
        </optgroup>
      ))}
    </select>
    <button onClick={handleInsertSnippet} disabled={!snippetId} className={styles.btnPrimary} style={{ padding: '6px 12px' }}>
      Insertar acción
    </button>
  </div>
)}
```

(NOTA: la ubicación exacta del bloque JSX — junto al árbol de bloques
`BlockTree`/panel `BlockProperties` — la elige el implementador para que quede
al lado de la vista del job seleccionado; lo único fijo es que se renderiza SOLO
cuando `selected?.si != null && selected?.ji != null` y que muta vía
`setSpec(appendStep(...))`, sin prop nueva.)

**Tests PRIMERO** — archivo nuevo
`Stacky Agents/frontend/src/devops/pipelineStepSnippets.test.ts` (vitest, TS puro):
- `all_snippets_have_unique_ids`: los `id` de `PIPELINE_STEP_SNIPPETS` son únicos.
- `at_least_20_snippets`: `PIPELINE_STEP_SNIPPETS.length >= 20` (piso base; la
  ampliación a ≥40 se verifica en F1-ter con `at_least_40_snippets`).
- `every_snippet_builds_valid_step`: para cada snippet, `build()` da un
  `StepDraft` con `name` no vacío, `script` no vacío y `env` objeto.
- `no_snippet_uses_echo_or_ado_macro`: ningún `script` empieza con `"echo "` ni
  contiene `"$("` (evita el placeholder de relleno y la macro de variable de
  ADO — paridad).
- `every_snippet_script_is_single_line` (C2): ningún `script` contiene `"\n"`
  ni `"\r"` — invariante de paridad: un script de UNA línea renderiza igual en
  ADO y en GitLab (mismo camino que los presets ya validados).
- `every_snippet_category_is_declared`: la `category` de cada snippet ∈
  `SNIPPET_CATEGORIES`.
- `getSnippetsByCategory_covers_all`: la suma de `getSnippetsByCategory(c)` sobre
  las 8 categorías reconstruye exactamente `PIPELINE_STEP_SNIPPETS` (sin
  huérfanos).
- `build_is_pure_and_immutable`: `build()` dos veces da objetos `!==` pero
  deep-equal (mismo patrón que los presets de F0).
- `appendStep_inserts_snippet_and_keeps_spec_valid`: partiendo de un spec con 1
  stage / 1 job vacío, `appendStep(spec, 0, 0, snip.build())` deja el step en el
  job, no muta el `spec` original (inmutable) y `validateSpecLocal` del
  resultado no reporta "el job no tiene steps".

Comando: `npx vitest run src/devops/pipelineStepSnippets.test.ts` en
`Stacky Agents/frontend`.

**Criterio de aceptación BINARIO:** los 9 tests nuevos pasan +
`npx tsc --noEmit` 0 errores; `PIPELINE_STEP_SNIPPETS.length >= 20` (piso base;
F1-ter lo sube a ≥40); ningún snippet usa `echo`/`$(` y todos son de una sola
línea; los botones y presets de F0/F1 siguen intactos (grep negativo: el diff de
`specBuilder.ts` solo AGREGA `appendStep`, no toca `addStep`).
**Flag:** ninguna (datos estáticos puros, mismo nivel que los presets de F0;
siempre visibles, cero configuración).
**Impacto por runtime:** Codex CLI / Claude Code CLI / GitHub Copilot Pro:
NINGUNO (UI pura, sin ejecución de agentes). Fallback: no aplica.
**Trabajo del operador:** ninguno (la biblioteca está siempre disponible; usar un
snippet es un click opcional, y el step insertado es 100% editable — HITL).

### F1-ter — [ADICIÓN ARQUITECTO] Catálogo ampliado (≥40) + Recetas + filtro + acceso desde el builder vacío

**Por qué (pedido REITERADO del operador, C3):** el operador volvió a pedir
"muchas acciones de pipeline prehechas". F1-ter (a) amplía el catálogo de F1-bis
a **≥40 acciones** con 2 categorías nuevas (`seguridad`, `versionar`) y más
stacks (Go/Rust/Java-Maven/Gradle/PHP), (b) agrega **Recetas** (bundles ordenados
de acciones que se insertan de una), (c) un **filtro por texto** para navegar 40+
acciones, y (d) un acceso a la biblioteca **desde el builder vacío** (C1). Todo es
datos estáticos + helpers puros + UI mínima, reusando `appendStep` — sin flag,
sin backend, sin tocar renderers.

**(a) Ampliación del catálogo — AGREGAR estas entradas a
`PIPELINE_STEP_SNIPPETS`** (`pipelineStepSnippets.ts`), respetando el invariante
de una sola línea y sin `$(`:

```ts
  // ── dependencias (más stacks) ──
  { id: "dep-composer-install", category: "dependencias", label: "composer install", description: "Instala dependencias PHP con Composer.", build: () => step("instalar-dependencias", "composer install --no-interaction --prefer-dist") },
  { id: "dep-go-download", category: "dependencias", label: "go mod download", description: "Descarga módulos Go.", build: () => step("instalar-dependencias", "go mod download") },
  { id: "dep-cargo-fetch", category: "dependencias", label: "cargo fetch", description: "Descarga dependencias Rust.", build: () => step("instalar-dependencias", "cargo fetch") },
  // ── lint (más stacks) ──
  { id: "lint-go-vet", category: "lint", label: "go vet", description: "Análisis estático de Go.", build: () => step("lint", "go vet ./...") },
  { id: "lint-cargo-clippy", category: "lint", label: "cargo clippy", description: "Linter de Rust con Clippy (falla en warnings).", build: () => step("lint", "cargo clippy -- -D warnings") },
  // ── build (más stacks) ──
  { id: "build-go", category: "build", label: "go build", description: "Compila todos los paquetes Go.", build: () => step("compilar", "go build ./...") },
  { id: "build-cargo-release", category: "build", label: "cargo build (release)", description: "Compila Rust en modo release.", build: () => step("compilar", "cargo build --release") },
  { id: "build-maven", category: "build", label: "mvn package", description: "Empaqueta un proyecto Maven (sin tests).", build: () => step("compilar", "mvn -B -DskipTests package") },
  { id: "build-gradle", category: "build", label: "gradle build", description: "Compila y arma con Gradle.", build: () => step("compilar", "./gradlew build") },
  // ── test (más stacks) ──
  { id: "test-go", category: "test", label: "go test", description: "Corre los tests de Go.", build: () => step("test", "go test ./...") },
  { id: "test-cargo", category: "test", label: "cargo test", description: "Corre los tests de Rust.", build: () => step("test", "cargo test") },
  { id: "test-maven", category: "test", label: "mvn verify", description: "Corre la fase verify de Maven (tests + checks).", build: () => step("test", "mvn -B verify") },
  { id: "test-phpunit", category: "test", label: "phpunit", description: "Corre los tests PHP con PHPUnit.", build: () => step("test", "vendor/bin/phpunit") },
  // ── publicar (más) ──
  { id: "pub-twine-check", category: "publicar", label: "twine check", description: "Valida los artefactos Python antes de publicar.", build: () => step("validar-artefacto", "python -m twine check dist/*") },
  // ── seguridad ──
  { id: "sec-npm-audit", category: "seguridad", label: "npm audit", description: "Reporta vulnerabilidades de dependencias Node.", build: () => step("auditar-seguridad", "npm audit --audit-level=high") },
  { id: "sec-pip-audit", category: "seguridad", label: "pip-audit", description: "Reporta vulnerabilidades de dependencias Python (requiere pip-audit).", build: () => step("auditar-seguridad", "python -m pip_audit") },
  { id: "sec-dotnet-vuln", category: "seguridad", label: "dotnet list --vulnerable", description: "Lista paquetes NuGet con vulnerabilidades conocidas.", build: () => step("auditar-seguridad", "dotnet list package --vulnerable") },
  { id: "sec-trivy-fs", category: "seguridad", label: "trivy fs", description: "Escanea el filesystem por vulnerabilidades con Trivy (requiere trivy en el runner).", build: () => step("auditar-seguridad", "trivy fs .") },
  // ── versionar ──
  { id: "ver-git-describe", category: "versionar", label: "git describe", description: "Imprime la versión derivada del último tag Git.", build: () => step("version", "git describe --tags --always") },
  { id: "ver-git-short-sha", category: "versionar", label: "git short SHA", description: "Imprime el SHA corto del commit actual.", build: () => step("version", "git rev-parse --short HEAD") },
```

Con estas 20 entradas el total pasa de 26 a **46** (≥40). Todas son de una línea
y sin `$(` (cumplen `every_snippet_script_is_single_line` y
`no_snippet_uses_echo_or_ado_macro`).

**(b) Recetas — Archivo NUEVO:**
`Stacky Agents/frontend/src/devops/pipelineRecipes.ts`

```ts
/**
 * pipelineRecipes.ts — Plan 97 F1-ter
 * Recetas = bundles ORDENADOS de acciones prehechas que se insertan de una en un
 * job. NO duplican scripts: referencian snippets de pipelineStepSnippets.ts por
 * id y reusan el helper inmutable appendStep.
 */
import type { StepDraft } from "./specBuilder";
import { PIPELINE_STEP_SNIPPETS } from "./pipelineStepSnippets";

export interface StepRecipe {
  id: string;
  label: string;
  description: string;
  stepIds: readonly string[];  // ids EXISTENTES de PIPELINE_STEP_SNIPPETS, en orden
}

export const PIPELINE_RECIPES: readonly StepRecipe[] = [
  { id: "ci-python", label: "CI Python completo", description: "pip install, flake8 y pytest con cobertura.", stepIds: ["dep-pip-install", "lint-flake8", "test-pytest-cov"] },
  { id: "ci-node", label: "CI Node completo", description: "npm ci, lint, test y build.", stepIds: ["dep-npm-ci", "lint-eslint", "test-npm-test", "build-npm"] },
  { id: "ci-dotnet", label: "CI .NET completo", description: "restore, build Release y test.", stepIds: ["dep-dotnet-restore", "build-dotnet-release", "test-dotnet"] },
  { id: "ci-go", label: "CI Go completo", description: "vet, build y test de Go.", stepIds: ["lint-go-vet", "build-go", "test-go"] },
  { id: "docker-build-push", label: "Docker build + push", description: "Construye y publica la imagen (editá el tag).", stepIds: ["build-docker", "pub-docker-push"] },
  { id: "quality-python", label: "Calidad Python", description: "ruff, black --check, pytest con cobertura y reporte.", stepIds: ["lint-ruff", "lint-black-check", "test-pytest-cov", "qual-coverage-report"] },
];

export function buildRecipeSteps(recipe: StepRecipe): StepDraft[] {
  return recipe.stepIds.map((id) => {
    const snip = PIPELINE_STEP_SNIPPETS.find((s) => s.id === id);
    if (!snip) throw new Error(`Receta '${recipe.id}' referencia snippet inexistente: ${id}`);
    return snip.build();
  });
}
```

**(c)+(d) UI — editar `PipelineBuilderSection.tsx`:**

1. **Acceso desde el builder vacío (C1):** en el bloque del estado vacío de F1
   (junto a la galería de presets), agregar un botón que scaffolda un job y lo
   selecciona, dejando visible el inserter de acciones (reusa `addStage`/`addJob`
   YA importados, y `setSelected`):

```tsx
// Plan 97 F1-ter (C1) — acceso a las acciones sueltas sin partir de un preset
const handleStartEmptyJob = () => {
  const scaffolded = addJob(addStage(emptySpec()), 0); // stage-1 + job-1
  setSpec(scaffolded);
  setSelected({ si: 0, ji: 0 });
};
// ...botón en el estado vacío, junto a "Empezar con ejemplo":
<button onClick={handleStartEmptyJob} className={styles.btnSecondary} style={{ padding: '8px 16px' }}>
  Insertá acciones sueltas (job vacío)
</button>
```

2. **Filtro (c) + Recetas (b):** ampliar el inserter de F1-bis. Cambiar el guard
   de render de F1-bis para exigir que el índice EXISTA de verdad (C5), agregar
   el filtro y el selector de recetas:

```tsx
import { PIPELINE_RECIPES, buildRecipeSteps } from '../../devops/pipelineRecipes';

const [snippetFilter, setSnippetFilter] = useState('');
const [recipeId, setRecipeId] = useState('');

// C5 — el job seleccionado debe existir realmente en el spec actual
const jobSelected =
  selected?.si != null && selected?.ji != null &&
  selected.si < spec.stages.length &&
  selected.ji < (spec.stages[selected.si]?.jobs.length ?? 0);

const filteredSnippets = PIPELINE_STEP_SNIPPETS.filter((s) => {
  const q = snippetFilter.trim().toLowerCase();
  return q === '' || `${s.label} ${s.description} ${s.category}`.toLowerCase().includes(q);
});

const handleInsertRecipe = () => {
  if (!jobSelected || !recipeId) return;
  const rec = PIPELINE_RECIPES.find((r) => r.id === recipeId);
  if (!rec) return;
  setSpec((prev) => buildRecipeSteps(rec).reduce(
    (acc, st) => appendStep(acc, selected!.si!, selected!.ji!, st), prev));
};

// JSX (reemplaza el `{selected?.si != null && selected?.ji != null && (` de F1-bis
// por `{jobSelected && (`), y DENTRO agrega, antes del <select> de acciones:
<input
  type="text"
  value={snippetFilter}
  onChange={(e) => setSnippetFilter(e.target.value)}
  placeholder="Filtrar acciones…"
  style={{ padding: '4px 8px' }}
/>
// ...el <select> de acciones ahora mapea `filteredSnippets` agrupados por
// categoría (usar getSnippetsByCategory pero filtrando por `filteredSnippets`,
// o simplemente mapear `filteredSnippets` directo si el filtro está activo).
// ...y un segundo control para recetas:
<label className={styles.textMuted}>Insertar receta (varios pasos):</label>
<select value={recipeId} onChange={(e) => setRecipeId(e.target.value)}>
  <option value="">— elegí una receta —</option>
  {PIPELINE_RECIPES.map((r) => (
    <option key={r.id} value={r.id} title={r.description}>{r.label}</option>
  ))}
</select>
<button onClick={handleInsertRecipe} disabled={!recipeId} className={styles.btnPrimary} style={{ padding: '6px 12px' }}>
  Insertar receta
</button>
```

(NOTA: `addStage`/`addJob`/`emptySpec` ya están importados en el componente
—verificado en el bloque de imports de `specBuilder`—; `setSelected` es el setter
del estado `selected` de la línea 61. El `btnSecondary` es opcional: si no existe
esa clase en `devops.module.css`, usar `btnPrimary` o un estilo inline, sin
introducir un sistema de estilos nuevo.)

**Tests PRIMERO** — extender `pipelineStepSnippets.test.ts` (F1-bis) con:
- `at_least_40_snippets`: `PIPELINE_STEP_SNIPPETS.length >= 40`.
- `snippet_categories_include_seguridad_and_versionar`: ambas ∈ `SNIPPET_CATEGORIES`
  y cada una tiene ≥1 snippet.

**Archivo NUEVO** `Stacky Agents/frontend/src/devops/pipelineRecipes.test.ts`
(vitest, TS puro):
- `all_recipes_have_unique_ids`: los `id` de `PIPELINE_RECIPES` son únicos.
- `every_recipe_references_existing_snippets` (clave anti-drift): cada `stepId`
  de cada receta existe en `PIPELINE_STEP_SNIPPETS` (si alguien borra/renombra un
  snippet referenciado, este test se pone rojo).
- `every_recipe_has_at_least_two_steps`: `recipe.stepIds.length >= 2` (una receta
  es un bundle, no un solo paso).
- `buildRecipeSteps_returns_valid_steps`: para cada receta, `buildRecipeSteps`
  devuelve `StepDraft[]` con `name`/`script` no vacíos y del mismo largo que
  `stepIds`.
- `buildRecipeSteps_unknown_snippet_throws`: una receta ad-hoc con un `stepId`
  inexistente hace lanzar a `buildRecipeSteps` (defensivo).
- `inserting_recipe_into_empty_job_keeps_spec_valid`: partiendo de un spec 1
  stage / 1 job vacío, hacer `reduce(appendStep)` con los steps de una receta deja
  el job con N steps, no muta el spec original, y `validateSpecLocal` da `[]`.

Comando:
`npx vitest run src/devops/pipelineStepSnippets.test.ts src/devops/pipelineRecipes.test.ts`
en `Stacky Agents/frontend`.

**Criterio de aceptación BINARIO:** `PIPELINE_STEP_SNIPPETS.length >= 40`;
`PIPELINE_RECIPES.length >= 6`; los 2 tests nuevos de snippets + 6 de recetas
pasan; `npx tsc --noEmit` 0 errores; desde el builder vacío, el botón "Insertá
acciones sueltas" deja seleccionado un job y visible el inserter (verificación
manual/grep de `handleStartEmptyJob`); el inserter NO se muestra si `selected`
apunta fuera de rango (C5, cubierto por `jobSelected`).
**Flag:** ninguna (datos estáticos + UI, igual que F1-bis).
**Impacto por runtime:** NINGUNO en los 3 runtimes (UI pura). Fallback: no aplica.
**Trabajo del operador:** ninguno (todo opcional y editable — HITL).

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
    project_root = os.path.normpath(project_root)  # C4: normaliza separador final (evita off-by-one de profundidad)
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
    # C1 (BLOQUEANTE resuelto): la key REAL de la ruta del repo en el dict de
    # get_project_config es `workspace_root` (project_manager.py:12,152,155).
    # v1 usaba `local_path`/`path`, que NO existen -> el detector nacía muerto.
    root = (cfg or {}).get("workspace_root")
    detected = detect_stack(root) if root else None
    return jsonify({"detected": detected})
```

(NOTA para el implementador — key RESUELTA por la crítica (C1): la ruta del repo
del proyecto vive en la key `workspace_root` del dict que devuelve
`get_project_config` — verificado en `project_manager.py:12` (docstring del
schema), `:152` y `:155` (se persiste como `workspace_root`). NO usar
`local_path` ni `path`: no existen en ese dict y dejarían el detector siempre en
`None`. Si el proyecto no tiene `workspace_root` configurado, `root` queda `None`
y `detect_stack(None)` ya está cubierto por el guard `if not project_root` →
devuelve `None`, nunca lanza.)

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
  `workspace_root` configurado (mock de `get_project_config` → `None` o dict
  SIN la key `workspace_root`) → 200 con `{"detected": null}` (nunca error).
- `test_detects_and_returns_stack`: flag ON, `get_project_config` mockeado a
  `{"workspace_root": str(tmp_path)}` con un `package.json` dentro de `tmp_path`
  → 200 con `{"detected": "node"}`.
- `test_endpoint_uses_workspace_root_key` (C1, anti-verde-falso): mock de
  `get_project_config` → dict con `workspace_root` apuntando a un `tmp_path` que
  tiene `requirements.txt`, PERO además con las keys legacy
  `{"local_path": "/no/existe", "path": "/no/existe"}`; el endpoint DEBE
  devolver `{"detected": "python"}` (lee `workspace_root`, ignora las legacy).
  Este test se pone en rojo si alguien vuelve a leer `local_path`/`path`.
- `test_route_registered`: centinela — `"/api/devops/detect-stack"` está en
  `[r.rule for r in app.url_map.iter_rules()]`.

Comando:
`"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan97_stack_detect_endpoint.py" -q`

**Ratchet:** registrar `test_plan97_stack_detector.py` y
`test_plan97_stack_detect_endpoint.py` en `backend/scripts/run_harness_tests.sh`
**y** `backend/scripts/run_harness_tests.ps1`.

**Criterio de aceptación BINARIO:** 10 + 6 = 16 tests nuevos verdes (10 del
detector puro + 6 del endpoint, incluido `test_endpoint_uses_workspace_root_key`
de C1); ningún test existente (`test_plan87_devops_endpoints.py`) se rompe.
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
  // C2: el proyecto activo se deriva de useWorkbench (YA existe en el componente,
  // PipelineBuilderSection.tsx:50-51) como `activeProject`; NO hay prop `project`.
  if (!activeProject) {
    setDetectError('Seleccioná un proyecto activo primero.');
    return;
  }
  setDetecting(true);
  setDetectError(null);
  try {
    const { detected } = await DevOps.detectStack(activeProject);
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
    <button onClick={() => void handleDetectStack()} disabled={detecting || !activeProject} className={styles.btnPrimary} style={{ padding: '8px 16px' }}>
      {detecting ? 'Detectando…' : 'Detectar stack de mi proyecto'}
    </button>
    {detectError && <p className={styles.textWarn} style={{ marginTop: '8px' }}>{detectError}</p>}
  </div>
)}
```

(NOTA — RESUELTO por la crítica (C2): `PipelineBuilderSection` recibe SOLO la
prop `ctx: DevOpsSectionContext` (`PipelineBuilderSection.tsx:45-49`) y NO recibe
`project`. El proyecto activo YA está disponible en el componente como
`activeProject`, derivado de `useWorkbench((s) => s.activeProject)?.name`
(`PipelineBuilderSection.tsx:50-51`). Usar `activeProject` — no inventar prop
nueva. `ctx.health` expone las flags booleanas del panel (mismo patrón que
`ctx.health.generator_enabled`/`trigger_enabled`, líneas 86 y 305 del
componente).)

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
npx vitest run src/devops/pipelinePresets.test.ts src/devops/pipelineStepSnippets.test.ts src/devops/pipelineRecipes.test.ts
npx tsc --noEmit
```

**Checklist binario:**
- [ ] Los 4 presets (`python`/`node`/`dotnet`/`generic`) generan spec válido
      (`validateSpecLocal` → `[]`) y ninguno usa el literal placeholder de
      `starterSpec`, salvo `generic` que lo declara explícitamente distinto.
- [ ] La biblioteca de acciones prehechas tiene ≥40 snippets (F1-bis+F1-ter) y
      ≥6 recetas; insertar un snippet o una receta con `appendStep` deja el spec
      válido; ningún snippet usa `echo`/`$(` y todos son de una sola línea
      (paridad ADO+GitLab); toda receta referencia solo snippets existentes;
      `addStep` queda intacto (grep negativo).
- [ ] Desde el builder VACÍO, "Insertá acciones sueltas (job vacío)" scaffolda
      stage+job, lo selecciona y muestra el inserter de acciones; el inserter no
      aparece si `selected` apunta fuera de rango (C5).
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
| Proyecto sin ruta local configurada (`workspace_root` ausente) | `detect_stack(None)` devuelve `None` sin lanzar; endpoint responde 200 con `detected: null` |
| Árbol de archivos gigante (repo grande) cuelga el detector | Tope de 500 entradas escaneadas + profundidad máxima 2 + exclusión de carpetas pesadas conocidas (`node_modules`, `.git`, `venv`, etc.) |
| Presets quedan desactualizados si cambia una convención (ej. `npm ci` deja de ser el estándar) | Son datos estáticos editables por el operador tras aplicarlos; no hay acoplamiento a versiones de herramientas — si cambia la convención, se edita `pipelinePresets.ts` en un plan futuro sin tocar el contrato |
| Un snippet (F1-bis) usa un comando que no aplica al proyecto (ej. `sonar-scanner` sin SonarQube) | El snippet es un punto de partida editable/borrable (HITL); nada se ejecuta al insertarlo. Los snippets son provider-neutrales y no interpolan variables del runner, así que no rompen la paridad ADO+GitLab |
| Confusión entre "preset" (este plan) y "template de publicación" (plan 88) | Nombres y archivos distintos (`pipelinePresets.ts` vs `publication_spec.py`); ámbitos distintos (pipeline de CI vs. publicación de proceso batch/agenda) — sin colisión de conceptos ni de flags |
| El detector encuentra un `.csproj`/`package.json` de una herramienta interna (ej. carpeta de tooling) y detecta mal | Aceptable en v1: es solo una SUGERENCIA preseleccionada, nunca se aplica sin click explícito del operador; documentado como fuera de scope refinar la heurística más allá de manifiestos en la raíz/nivel 1-2 |

## 6. Fuera de scope (v1)

- Presets de pipeline COMPLETO para más stacks (Go, Rust, Java/Maven, PHP) —
  quedan 4 presets (Python/Node/.NET/Genérico); esos stacks SÍ están cubiertos a
  nivel de acciones sueltas y recetas (F1-ter), pero un preset entero por stack se
  agrega en un plan futuro sobre `PIPELINE_PRESETS` sin romper el contrato.
- Acciones que NO son un script sino una directiva del pipeline: cache nativo
  (ADO `Cache@2` / GitLab `cache:`) y deploy con target concreto — se excluyen a
  propósito porque no son un `StepDraft` de script y romperían la neutralidad de
  provider; se tratarían en un plan futuro con soporte de campos nativos.
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
- **Acción prehecha / step snippet (F1-bis, [ADICIÓN ARQUITECTO])**: un
  `StepDraft` individual real y editable (un solo paso: instalar deps, lint,
  test, compilar, empaquetar, publicar, calidad, seguridad, versionar) insertable
  con 1 click en un job existente. A diferencia del preset, no arma un pipeline
  entero: AGREGA una acción concreta al job seleccionado.
- **Receta / bundle (F1-ter, [ADICIÓN ARQUITECTO])**: conjunto ORDENADO de
  acciones prehechas (referenciadas por id) que se insertan de una sola vez en un
  job (ej. "CI Node completo" = install→lint→test→build). No duplica scripts:
  reusa los snippets y `appendStep`.
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
3. F1-bis — [ADICIÓN ARQUITECTO] biblioteca de acciones prehechas
   (`pipelineStepSnippets.ts`) + helper `appendStep` + inserter UI + tests
   vitest (siempre visible, sin flag; independiente de F2/F3, puede ir junto a
   F1 o inmediatamente después).
4. F1-ter — [ADICIÓN ARQUITECTO] catálogo ampliado (≥40) + recetas
   (`pipelineRecipes.ts`) + filtro + acceso desde builder vacío + tests vitest
   (mismo commit que F1-bis o inmediatamente después; sube el piso a ≥40).
5. F0-bis — flag `STACKY_DEVOPS_STACK_DETECT_ENABLED` (5 patas) + tests.
6. F2 — detector de stack (`pipeline_stack_detector.py`) + endpoint + tests
   (implementar EN EL MISMO commit que F0-bis o inmediatamente después, nunca
   antes — la flag debe existir para que el guard del endpoint compile).
7. F3 — botón de detección en el frontend, gateado por health.
8. F4 — cierre y checklist binario.

## 9. Definición de Hecho (DoD)

- F0: 9 tests vitest verdes (`pipelinePresets.test.ts`) + `tsc` 0 errores.
- F1-bis: 9 tests vitest verdes (`pipelineStepSnippets.test.ts`) + `tsc` 0
  errores; ningún snippet usa `echo`/`$(` y todos son de una sola línea.
- F1-ter: `PIPELINE_STEP_SNIPPETS.length >= 40` + `PIPELINE_RECIPES.length >= 6`;
  2 tests vitest nuevos de snippets + 6 de recetas (`pipelineRecipes.test.ts`)
  verdes; toda receta referencia solo snippets existentes.
- F0-bis: 5 tests backend verdes + 3 meta-tests no-regresión verdes.
- F2: 10 + 6 = 16 tests backend verdes (`test_plan97_stack_detector.py` +
  `test_plan97_stack_detect_endpoint.py`, incluido el test de cableado de C1 que
  fija la key `workspace_root`).
- F1/F3: `tsc --noEmit` 0 errores + greps de integración verificados (sin
  suite de componente React, gap preexistente fuera de scope).
- Flag `STACKY_DEVOPS_STACK_DETECT_ENABLED` default OFF; con OFF, byte-idéntico
  al comportamiento previo a este plan (endpoint 404, botón ausente).
- Los 4 presets pasan `validateSpecLocal` en 0 errores y ninguno duplica el
  literal placeholder de `starterSpec` (salvo `generic`, declarado distinto).
- La biblioteca de acciones prehechas ofrece ≥40 snippets (F1-bis+F1-ter) + ≥6
  recetas; insertar cualquier snippet o receta vía `appendStep` deja el spec
  válido (`validateSpecLocal` limpio); las acciones sueltas son accesibles desde
  el builder vacío (botón "Insertá acciones sueltas").
- Paridad ADO+GitLab preservada: presets Y snippets usan el mismo
  `PipelineSpecDraft`/`StepDraft` y los mismos renderers ya existentes, sin
  bifurcación por tracker (snippets provider-neutrales, sin `$(VAR)`/`$VAR`).
- Cero cambios de contrato en `starterSpec`, `emptySpec`, `validateSpecLocal`,
  `addStep`, `PipelineSpec`/`_validate_spec`, `to_ado_yaml`/`to_gitlab_yaml`,
  `DevOpsPage.tsx` (shell intacto). `appendStep` es ADITIVO (no toca `addStep`).
- Tests registrados en `run_harness_tests.sh` y `run_harness_tests.ps1`.
- `_REQUIRES_MAP_FROZEN` actualizado con la arista nueva y su meta-test verde.
