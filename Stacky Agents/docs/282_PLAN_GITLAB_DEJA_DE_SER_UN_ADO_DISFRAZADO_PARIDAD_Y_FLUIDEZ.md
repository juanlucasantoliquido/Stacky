# Plan 282 — GitLab deja de ser un ADO disfrazado: paridad que se ve y cierre que no miente

**Estado:** PROPUESTO v1
**Fecha:** 2026-08-01
**Rama:** `docs/plan-279` (rama de trabajo vigente; **no** se abre rama nueva — el worktree es único y
hay sesiones paralelas escribiendo el 280 y el 281 en este mismo árbol)
**Depende de:** 276 (TLS + sync + grafo), 277 (jerarquía), 278 (publicador de épica), 270/271 (cierre y
estado), **280 (dependencia DURA de F1, ver abajo)**

### Frontera con los planes hermanos (escritos en paralelo, LEER ANTES DE IMPLEMENTAR)

Los tres planes atacan el mismo incidente de campo —la corrida de RIPLEY/GitLab del 2026-08-01, execs
211/212— desde tres capas distintas. **Las fronteras se verificaron leyendo los dos documentos, no
asumiendo.**

| Plan | Su capa | Qué NO hace |
|---|---|---|
| **280** — El desenlace mira el trabajo entregado | **Decidir** el estado terminal: `has_delivered_work`, `classify_outcome_reason`, 4 motores → 1 | No toca a qué tracker se publica |
| **281** — El ruteo por tracker deja de mentir | **Enrutar** el cliente: erradicar los 8 sitios ADO-only, gate por AST, la firma `no usa Azure DevOps` | No toca `ado_publisher.py` (verificado: `grep ado_publisher\|post_comment` en el 281 → **0 hits**) |
| **282** — este | **Entregar y mostrar**: que el resultado llegue al issue de GitLab y que la pantalla hable el idioma del tracker | No decide estados ni erradica sitios ADO-only |

**Cesión explícita al plan 280.** La versión inicial de este plan tenía una fase F1 que agregaba un guard
de idempotencia a `_mark_terminal` (`claude_code_cli_runner.py:3105`, `codex_cli_runner.py:1975`) para que
el runner no pisara el `completed` del `output_watcher`. **Se retiró.** El plan 280 resuelve el mismo
síntoma más arriba y con más evidencia (44 ejecuciones y 93.447 caracteres de trabajo bajo estado `error`,
contra las 2 corridas que medía este plan): al hacer que la regla 8 mire el trabajo entregado, la
ejecución nunca llega a `_mark_terminal("error")`. Dos planes tocando los mismos dos runners para el mismo
síntoma es trabajo duplicado y conflicto de merge garantizado. **F1 de este plan (publicación) declara al
280 como dependencia dura:** sin el 280, la ejecución queda en `error` y el gate
`agent_completion_internal.py:233-234` (`final_status != "completed"` → `skipped`) impide publicar. Este
plan **no** vuelve a implementar esa lógica ni la parchea por su cuenta.

**Pase entrante del plan 281 §7 — aceptado en parte, y lo rechazado se dice.** El 281 deriva a este plan:
- *"Deep links de GitLab, `base_url` con namespace pegado, y demás features a medio portar"* →
  **ACEPTADO como diagnóstico, DIFERIDO como trabajo** (§6.8): la normalización silenciosa y la
  validación del backend ya contienen el caso; falta solo el hint en la UI.
- *"Construir el equivalente GitLab de los 7 sitios que F7 degrada a valor neutro"* (criterios de
  aceptación, self-review, similar tickets, auto-assign, business preflight, enriquecimiento de contexto,
  estado equivalente de tarea) → **RECHAZADO por priorización, ver §6.14.** Son 7 features nuevas, no
  arreglos de paridad. Aceptarlas volvería este plan inimplementable y contradice el encargo explícito de
  acotar el alcance a lo que se cierra bien.
- *"El breaker `ado_sync` con key de proyecto GitLab"* y *"la cadencia de polling"* → **RECHAZADO**, §6.15.

---

## 1. Objetivo

Stacky nació ADO-first. GitLab se agregó después y quedó a mitad de camino: **el trabajo se produce, pero
no llega al tracker y la pantalla habla un idioma que no es el del operador.** Este plan cierra la brecha
de FLUIDEZ en dos frentes medidos en vivo sobre RIPLEY/GitLab (53 issues abiertos / 1009 totales):

1. **El trabajo no llega al tracker.** El análisis técnico se generó, se validó y **no se publicó**:
   el publicador de comentarios (`services/ado_publisher.py`) es ADO-only y muere en
   `services/project_context.py:340-342`, aunque `services/gitlab_provider.py:440` ya implementa
   `post_comment`. Evidencia dura: tabla `agent_html_publish`, filas 56 y 57, `status='failed'`, con el
   `comment.html` válido en disco (12.163 y 22.448 bytes). Contraste en la misma tabla: filas 50-55,
   proyecto RSPACIFICO (ADO), `status='ok'`.
2. **La UI habla ADO.** La pestaña dice "Tickets ADO" mientras el título de la propia página dice
   "Tickets GitLab"; cada tarjeta rotula `ADO-1234`; el filtro "Solo abiertos" es **ciego** en GitLab; y
   "Copiar link ADO" pega una URL a `dev.azure.com/UbimiaPacifico/Strategist_Pacifico` — **la organización
   de otro cliente**.

Y por debajo de los dos, tres silencios que rompen la confianza sin decir nada: cuatro servicios GitLab
que **pierden el CA bundle** y mueren contra el certificado interno del operador; un `update_item_assignee`
que **borra al asignado** cuando el username no resuelve; y tres tabs ADO-only ofrecidos en el menú de un
proyecto GitLab que terminan en un cartel de "solo disponible para Azure DevOps".

Al terminar este plan, un operador GitLab ve su vocabulario, sus links funcionan, sus filtros filtran, y
cuando el agente termina el trabajo **el resultado aparece en su issue**.

### KPI / impacto esperado (todos binarios y medibles)

| # | KPI | Hoy (medido) | Meta |
|---|-----|--------------|------|
| K1 | Filas `agent_html_publish.status='failed'` con causa "no usa Azure DevOps" en un proyecto GitLab | 2 (ids 56, 57) | **0** |
| K2 | Rótulos visibles con "ADO"/"Azure DevOps" **no ruteados por tracker** en `frontend/src` | 96 (censo F0) | **≤ 20** (los legítimos: selector de tracker, migrador, preview de pipeline ADO) |
| K3 | Constructores de `GitLabTrackerProvider` que **bypassean la fábrica** y quedan sin `ca_bundle` | 4 | **0** |
| K4 | Sitios que construyen una URL de tracker con org/proyecto ADO hardcodeados | 1 (`utils/trackerUrls.ts:11`), con 4 consumidores | **0** |
| K5 | Tabs ADO-only alcanzables desde un proyecto GitLab que terminan en callejón sin salida | 3 (PM, Sprint Board, User Stats) | **0** |
| K6 | Caminos de escritura a GitLab que **destruyen datos en silencio** ante un fallo de resolución | 1 (`update_item_assignee` vacía `assignee_ids`) | **0** |

**Nota sobre K1:** su medición exige que la ejecución llegue a `completed`, cosa que hoy depende del plan
280. Por eso el gate de F1 mide el **publicador aislado** (con el estado forzado en el test) y el smoke
manual mide la cadena completa. Un KPI que no se puede medir sin otro plan **no se declara verde**: sale
`exit 5`.

---

## 2. Por qué ahora / gap que cierra

Los planes 270-278 construyeron las piezas correctas y **declararon explícitamente fuera de alcance la
capa que las hace usables**:

- **276 §7** dejó fuera, textual, los rótulos de navegación global (`App.tsx:455`, `shellNav.ts:18`,
  `commandPaletteData.ts:74`) como "decisión de producto pendiente". Y creó `lib/trackerLabels.ts` —
  el helper correcto — pero **solo lo consumen 2 archivos** de toda la app.
- **270 §fuera-de-alcance** delegó a un "plan 272" la unificación de escritores y el vocabulario GitLab.
  **El plan 272 no existe** (número reservado sin archivo). Esas brechas están huérfanas.
- **271** dejó escrito que `_state_map_for_gitlab` entiende solo 4 claves lógicas y que "como la UI
  enseña vocabulario ADO, el caso común cae en `transition_failed`". Ese diagnóstico sigue vigente:
  `services/gitlab_provider.py:152-160`.
- **278** unificó los 3 RUNTIMES del publicador de épica, no los TRACKERS. Y el camino de **comentarios**
  (que es el que usa el operador todos los días al cerrar trabajo) nunca se tocó.

La decisión de producto que el 276 dejó pendiente **ya la tomó el operador**: usa GitLab de verdad, en
producción, y el requerimiento textual es "necesito que el uso de la herramienta sea muy fluido".

### Lo que este plan NO re-planifica (ya está hecho o en vuelo)

- **La idempotencia de `POST /api/tickets/epics/from-brief` YA ESTÁ IMPLEMENTADA** en el working tree
  (sin commitear): `api/tickets.py:8052` (`sealed_work_item_id`), `:8058` (`claim_publication`),
  `:8067` (409 `publish_in_progress`). No la toques.
- **El guard `typeof === "number"` de la épica duplicada YA ESTÁ PARCHEADO** en el working tree:
  `frontend/src/services/uiGuards.ts:78` (`sealedWorkItemId`) consumido desde
  `frontend/src/components/EpicFromBriefModal.tsx:223`. No lo toques.
- **El publicador de ÉPICA sí rutea** por provider desde `api/tickets.py:7176`. El que NO rutea es el de
  **comentarios**, que es otro módulo (F1).

---

## 3. Principios y guardarraíles (obligatorios en cada fase)

- **3 runtimes con paridad.** Todo lo de este plan vive en el chokepoint de cierre, en el publicador o en
  el frontend — capas **runtime-agnósticas**. **Ningún ítem de este plan toca un runner específico**: la
  decisión del estado terminal quedó cedida al plan 280. Cada fase declara igual su impacto por runtime.
- **Cero trabajo extra para el operador.** Todas las flags de este plan nacen **default ON**. Ninguna cae
  en la categoría (A) —no enciende loops, daemons, polling ni prefetch— ni en la (B): F1 **no agrega una
  escritura nueva**, corrige el destino de una escritura que el operador ya autorizó explícitamente con el
  checkbox "Publicar comentario" (`frontend/src/components/FinishWorkButton.tsx:225`) y que **hoy falla**;
  F3 **reduce** la escritura (deja de borrar el asignado). Justificación escrita por flag en cada fase.
- **Human-in-the-loop.** Nada se publica ni se cierra solo que no se publicara o cerrara ya hoy. F7
  **oculta** entradas que llevan a callejones sin salida; no decide nada por el operador.
- **Mono-operador, sin auth.** Ningún ítem introduce roles ni permisos.
- **No degradar.** Todos los cambios son aditivos y con fallback al comportamiento actual. Los helpers
  nuevos del frontend son **funciones puras en `.ts`** (RTL/jsdom no están instalados en este repo).
- **Backward-compatible.** Un proyecto ADO debe comportarse EXACTAMENTE igual que hoy. Cada fase tiene al
  menos un caso de test que congela el comportamiento ADO.

---

## 4. Fases

### F0 — Medir el defecto antes de tocarlo (el gate que hoy está ROJO)

**Objetivo:** dejar por escrito y ejecutable el estado de hoy, para que las fases siguientes se verifiquen
contra el defecto y no contra sí mismas.

**Valor:** sin esto, cada fase siguiente puede pasar por accidente. Este repo tiene precedentes de tests
que pasan con el bug vivo.

**Archivos a crear:**
- `Stacky Agents/backend/tests/test_plan282_censo_paridad.py`
- `Stacky Agents/frontend/src/services/__tests__/plan282Censo.test.ts`

**Contenido exacto del test backend** (`test_plan282_censo_paridad.py`):

```python
"""Plan 282 F0 — censos ejecutables del estado ANTES del arreglo.

REGLA DE LA CASA: un censo por subcadena da por cubierta la ruta larga y un censo
circular grepea su propia lista. Acá se BARRE EL DIRECTORIO y se cuenta por AST /
por referencia, nunca por `grep -c` sobre un closure.
"""
import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

def test_f0_censo_constructores_gitlab_que_bypassean_la_fabrica():
    """K3: cuenta los módulos que llaman GitLabTrackerProvider(...) DIRECTO en vez
    de pasar por get_tracker_provider(). Esos nacen sin ca_bundle y mueren contra
    un GitLab con CA interna.

    ANTES del arreglo: exactamente 4 (gitlab_ci_logs, gitlab_ci_provider,
    gitlab_preflight, gitlab_variables). DESPUÉS de F2: 0.
    Se excluye services/tracker_provider.py — ESE es el que tiene derecho.
    """
    ofensores = []
    for py in (BACKEND / "services").glob("*.py"):
        if py.name == "tracker_provider.py":
            continue
        arbol = ast.parse(py.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) \
               and nodo.func.id == "GitLabTrackerProvider":
                ofensores.append(f"{py.name}:{nodo.lineno}")
    # F0 (rojo esperado): assert len(ofensores) == 4
    # F2 (verde):
    assert ofensores == [], f"bypassean la fabrica: {ofensores}"


def test_f0_el_publicador_de_comentarios_es_ado_only():
    """K1: hoy services/ado_publisher.py resuelve el cliente sin preguntar el
    tracker, y por eso muere en project_context.py:340-342 en todo proyecto GitLab.

    GUARDA ANTI-FALSO-VERDE: el detector se prueba PRIMERO contra un fuente
    sintetico que si tiene el ruteo, y contra otro que no. Un assert de ausencia
    que nunca vio un positivo no prueba nada.
    """
    con_ruteo = "def p():\n    pub = resolve_comment_publisher(tracker_type)\n"
    sin_ruteo = "def p():\n    client = _client_for_ticket_project(x)\n"
    assert _rutea_por_tracker(con_ruteo), "el detector da falso negativo: test invalido"
    assert not _rutea_por_tracker(sin_ruteo), "el detector no detecta: test invalido"

    texto = (BACKEND / "services" / "ado_publisher.py").read_text(encoding="utf-8")
    # F0 (rojo esperado): assert not _rutea_por_tracker(texto)
    # F1 (verde):
    assert _rutea_por_tracker(texto), "ado_publisher no consulta el router de tracker"


def _rutea_por_tracker(fuente: str) -> bool:
    """True si el fuente REFERENCIA resolve_comment_publisher.

    Se censa por REFERENCIA (ast.Name/ast.Attribute), no por ast.Call con
    func.id: si manana la llamada se hace por alias o por atributo de modulo,
    un censo de llamadas daria CERO y premiaria el bug.
    """
    arbol = ast.parse(fuente)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name) and nodo.id == "resolve_comment_publisher":
            return True
        if isinstance(nodo, ast.Attribute) and nodo.attr == "resolve_comment_publisher":
            return True
    return False
```

**Contenido exacto del test frontend** (`plan282Censo.test.ts`):

```ts
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const SRC = join(__dirname, "..", "..");

/** Barre el directorio; NO grepea una lista propia (censo circular). */
function archivosFuente(dir: string): string[] {
  const salida: string[] = [];
  for (const entrada of readdirSync(dir)) {
    if (entrada === "node_modules" || entrada === "__tests__") continue;
    const ruta = join(dir, entrada);
    if (statSync(ruta).isDirectory()) salida.push(...archivosFuente(ruta));
    else if (/\.(tsx?|jsx)$/.test(entrada) && !/\.test\.tsx?$/.test(entrada)) salida.push(ruta);
  }
  return salida;
}

/** Solo cuenta strings de UI: descarta lineas de comentario. Un censo que cuenta
 *  comentarios da 100% de falsos positivos en un codigo escrito en espanol. */
function rotulosAdoNoRuteados(texto: string): number {
  return texto
    .split("\n")
    .filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l))
    .filter((l) => /["'`>][^"'`]*\b(ADO|Azure DevOps)\b/.test(l)).length;
}

describe("Plan 282 F0 — censo de rotulos ADO no ruteados (K2)", () => {
  it("el detector detecta cuando SI hay (guarda anti-falso-verde)", () => {
    expect(rotulosAdoNoRuteados(`const x = "Tickets ADO";`)).toBe(1);
    expect(rotulosAdoNoRuteados(`// comentario sobre ADO`)).toBe(0);
  });

  it("K2: el total del arbol queda bajo el techo", () => {
    const total = archivosFuente(SRC).reduce(
      (acc, f) => acc + rotulosAdoNoRuteados(readFileSync(f, "utf-8")), 0);
    // F0 (rojo esperado): expect(total).toBe(96)
    // F4..F7 (verde):
    expect(total).toBeLessThanOrEqual(20);
  });
});
```

**Comando exacto:**
```bash
# backend (venv del repo — el que ANDA es backend/venv)
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan282_censo_paridad.py -v
# frontend (POR ARCHIVO: vitest contamina por orden)
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/services/__tests__/plan282Censo.test.ts --testTimeout=60000
```

**Criterio de aceptación BINARIO de F0:** los 2 archivos existen y, con los asserts en su versión
"rojo esperado" (las líneas comentadas), **ambos PASAN** reproduciendo exactamente 4 / 96 / y detectando
la ausencia de guard. Eso prueba que el censo ve el defecto. Recién entonces se activan los asserts
"verde" y las fases siguientes los llevan a 0 / ≤20 / con guard.

**Flag:** ninguna (son tests).
**Runtimes:** N/A (no toca runtime).
**Trabajo del operador:** ninguno.

**Registro obligatorio en los DOS ratchets** (sintaxis distinta):
- `Stacky Agents/backend/scripts/run_harness_tests.sh` — agregar `tests/test_plan282_censo_paridad.py`
  en el bloque donde ya están `tests/test_plan277_*.py` (línea ~250).
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` — agregar la misma ruta con la sintaxis PowerShell
  del archivo. **El ratchet no admite rutas con espacios**: la ruta es relativa a `backend/`, sin espacios.

---

### F1 — El comentario del agente se publica en GitLab

**Objetivo:** que el HTML que el agente ya generó y validó llegue al issue de GitLab, igual que llega al
work item de ADO.

**Valor:** cierra K1. Hoy el operador GitLab **nunca** recibe el resultado en su tracker: queda un
`comment.html` en disco y una fila `failed` en la bitácora. Es el "produce el trabajo pero reporta mal"
en su forma más cara.

**Diagnóstico exacto:**
```
agent_completion_internal.py:247  _attempt_publish()
ado_publisher.py:411-418          _client_for_ticket_project(...)
project_context.py:340-342        if ctx.tracker_type != "azure_devops": raise AdoConfigError
```
Y del otro lado, listo y sin usar: `services/gitlab_provider.py:440` `post_comment(item_id, body_html)`,
que renderiza a markdown vía `_render_note` (`:248`).

**Archivo a crear:** `Stacky Agents/backend/services/comment_publish_router.py`

Módulo **puro de ruteo**, sin dependencias de Flask ni de sesión. Símbolo exacto:

```python
def resolve_comment_publisher(tracker_type: str) -> Callable[..., dict] | None:
    """Devuelve el publicador de comentarios del tracker, o None si no hay.

    'azure_devops' -> el camino actual de ado_publisher (sin cambios).
    'gitlab'       -> provider.post_comment (services/gitlab_provider.py:440).
    otro           -> None  (el llamador registra 'publisher_unavailable', NO revienta).
    """
```
Espeja deliberadamente la forma de `services/tracker_write_router.py:56-80`, que el plan 270 ya validó
para el estado. **No inventes un patrón nuevo: copiá ese.**

**Archivo a editar:** `Stacky Agents/backend/services/ado_publisher.py`
En el bloque `# ── 5. Resolver el cliente ADO del proyecto del ticket ──` (**:410-418**), antes de llamar
a `_client_for_ticket_project`, consultar el router. Si el tracker no es ADO y hay publicador, usarlo; si
no hay, registrar el `PublishResult` con `error_kind="publisher_unavailable"` en vez de reventar.

**Contrato de idempotencia (obligatorio, no opcional):** antes de publicar, consultar
`provider.comment_exists(item_id, marker)` — existe en GitLab (`gitlab_provider.py:450`) y en ADO
(`ado_provider.py:95`). El marcador es el mismo que ya usa el camino ADO. Sin esto, un reintento del
watcher duplica el comentario en el issue del operador. **Este punto es innegociable:** el precedente de
la épica duplicada de esta misma semana nació exactamente de publicar sin chequear.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan282_publicacion_comentario.py`

Casos exactos:
1. `test_ado_sigue_publicando_igual_que_hoy` — congela el camino ADO byte a byte. **Primero este.**
2. `test_gitlab_publica_por_post_comment` — provider fake, asserta que se llamó `post_comment` con el
   `item_id` correcto y que el `PublishResult.ok is True`.
3. `test_gitlab_no_duplica_si_el_marcador_ya_existe` — `comment_exists` devuelve True → `skipped=True`,
   `post_comment` **no** se llamó.
4. `test_tracker_sin_publicador_no_revienta` — `tracker_type="mantis"` → `ok=False`,
   `error_kind="publisher_unavailable"`, y **no** se lanza `AdoConfigError`.
5. `test_el_fallo_del_tracker_se_clasifica_y_no_cae_en_exception_generica` — el provider lanza
   `TrackerApiError`; asserta `error_kind="tracker_error"`. Hoy `api/tickets.py:7519` y `:7829` capturan
   solo `(_AdoApiError, _AdoConfigError, ProjectContextError)`, así que un fallo tipado de GitLab escapa
   al `except Exception` genérico y se sella como `"exception"`. **Este test congela la clasificación.**
6. `test_reproduce_el_fallo_de_hoy_con_la_flag_off` — con `STACKY_COMMENT_PUBLISH_ROUTED_ENABLED=False`,
   el proyecto GitLab vuelve a fallar. **El gate se corre CONTRA el defecto.**

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan282_publicacion_comentario.py -v
```
**Criterio BINARIO:** los 6 casos pasan y `--collect-only -q` reporta **≥ 6 seleccionados**.

**Flag:** `STACKY_COMMENT_PUBLISH_ROUTED_ENABLED`, **default ON**.
Justificación del ON (leer con atención, el juez va a mirar acá): **no es categoría (B)**. La escritura al
tracker ya está autorizada por el operador de forma explícita y por acción — el checkbox "Publicar
comentario" de `frontend/src/components/FinishWorkButton.tsx:225`, más el gate
`final_status != "completed"` de `agent_completion_internal.py:233-234`. Este cambio **no agrega una
decisión nueva ni una escritura nueva**: hace que la escritura que el operador ya pidió llegue al tracker
correcto en vez de fallar. Nacer OFF significaría que el operador tiene que encender una flag para que una
función que él ya autorizó deje de estar rota, lo cual es exactamente el "trabajo extra" que el riel prohíbe.

**Impacto por runtime:** el publicador vive en `agent_completion_internal`, chokepoint runtime-agnóstico.
Los 3 runtimes lo atraviesan igual. Sin fallback por runtime porque no hay divergencia por runtime.

**Trabajo del operador:** ninguno.

---

### F2 — Los servicios GitLab dejan de bypassear la fábrica (y de perder el CA bundle)

**Objetivo:** que ningún módulo construya `GitLabTrackerProvider` a mano.

**Valor:** cierra K3. Contra un GitLab self-hosted con CA interna —**el caso del operador**— estos 4
servicios mueren con `CERTIFICATE_VERIFY_FAILED` mientras la sonda y el listado de tickets funcionan. Es
la peor forma de "no fluido": una parte del producto anda y otra no, sin explicación visible.

**Evidencia (los 4 ofensores):**
```
services/gitlab_ci_logs.py:11      GitLabTrackerProvider(project=project)   ← sin ca_bundle
services/gitlab_ci_provider.py:31  GitLabTrackerProvider(project=project)   ← sin ca_bundle
services/gitlab_preflight.py:38    GitLabTrackerProvider(project=project)   ← sin ca_bundle
services/gitlab_variables.py:14    GitLabTrackerProvider(project=project)   ← sin ca_bundle
```
La fábrica correcta ya resuelve el bundle en **ambas** ramas: `services/tracker_provider.py:144-148`
(per-project) y `:153-156` (legacy). El plan 276 F8.1 ya arregló la rama legacy y dejó escrito que era
"el único camino del repo que construía este provider sin certificado". **Faltaban estos 4.**

**Cambio exacto en los 4 archivos:** reemplazar la construcción directa por
`services.tracker_provider.get_tracker_provider(project)`, y validar que lo devuelto sea un
`GitLabTrackerProvider` (si el proyecto no es GitLab, estos servicios no aplican: devolver el error
tipado del módulo, no un `AttributeError`).

**Cuidado con el import circular:** `tracker_provider.py` importa `gitlab_provider`. Los 4 servicios
deben importar `get_tracker_provider` **dentro de la función**, no a nivel de módulo — es el patrón que
`tracker_provider.py:141` ya usa para `project_context`.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan282_fabrica_unica.py`
1. El censo AST de F0 da **0** ofensores (reusar la función, no reescribirla).
2. Para cada uno de los 4 servicios: con un proyecto GitLab que tiene `ca_bundle` configurado, el cliente
   resultante **tiene** ese bundle. Monkeypatchear `get_tracker_provider` y assertar el paso del valor.
3. `test_servicio_en_proyecto_ado_devuelve_error_tipado` — no `AttributeError`.
4. Guarda: con la flag OFF, el camino viejo sigue disponible (reversibilidad).

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan282_fabrica_unica.py -v
```
**Criterio BINARIO:** todos verdes y el censo F0 de constructores en **0**.

**ADVERTENCIA:** `services/gitlab_client.py:143-145` documenta que **no** hay que ensuciar
`REQUESTS_CA_BUNDLE` global (rompe la verificación de ADO/Jira/Mantis/LLM en el mismo backend). El único
sitio que lo hace hoy es `tools/migrar_mantis_gitlab/destination_writer.py:238`, que está **fuera de
alcance** de este plan (§6). No "arregles" los 4 servicios exportando esa variable.

**Flag:** `STACKY_GITLAB_PROVIDER_FACTORY_ONLY_ENABLED`, **default ON**. No agrega escrituras ni loops:
cambia de dónde sale un objeto de configuración.
**Impacto por runtime:** ninguno (capa de servicios).
**Trabajo del operador:** ninguno.

---

### F3 — El asignado deja de borrarse en silencio

**Objetivo:** que un username GitLab que no resuelve **falle diciéndolo**, en vez de vaciar el campo.

**Valor:** cierra K6. Es el silencio más caro de la matriz de paridad. Hoy `update_item_assignee`
(`services/gitlab_provider.py:506-518`) hace:
```python
assignee_id = self._resolve_assignee_id(assignee) if assignee else None
if assignee_id: update_body["assignee_ids"] = [assignee_id]
else:           update_body["assignee_ids"] = []   # ← BORRA al asignado actual
```
`_resolve_assignee_id` devuelve `None` ante cualquier fallo (`:519-...`). Resultado: un typo en el
username, o un fallo transitorio de `/users`, **desasigna el issue del operador sin avisar**. En ADO el
camino equivalente propaga el error.

**Cambio exacto:** distinguir los dos casos, que hoy están colapsados.
- `assignee` vacío/`None` → intención explícita de desasignar → `assignee_ids: []`. **Se conserva.**
- `assignee` con valor **que no resuelve** → **lanzar `TrackerApiError`** con el username en el mensaje.
  Nunca mandar `[]`.

Actualizar el docstring: hoy dice "Si no se encuentra, limpia assignees", que documenta el bug como si
fuera la feature.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan282_assignee_no_borra.py`
1. `test_username_valido_asigna` — camino feliz.
2. `test_username_vacio_desasigna_a_proposito` — `assignee=""` → `assignee_ids: []`. **Congela la
   intención legítima.**
3. `test_username_que_no_resuelve_lanza_y_no_manda_body` — asserta que se lanzó `TrackerApiError` **y**
   que `_request` **no fue llamado con `assignee_ids: []`**. Las dos cosas: sin el segundo assert, el test
   pasa aunque el borrado siga ocurriendo antes de lanzar.
4. `test_fallo_transitorio_de_users_no_desasigna` — `/users` lanza → propaga, no vacía.
5. `test_ado_no_cambia` — congela el camino ADO.

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./venv/Scripts/python.exe -m pytest tests/test_plan282_assignee_no_borra.py -v
```
**Criterio BINARIO:** 5 verdes.

**Flag:** `STACKY_GITLAB_ASSIGNEE_STRICT_ENABLED`, **default ON**.
Justificación del ON: **reduce** la escritura al sistema del operador (deja de emitir un PUT destructivo).
Una flag que quita una escritura destructiva no puede nacer OFF sin dejar el destrozo encendido de fábrica.

**Impacto por runtime:** ninguno.
**Trabajo del operador:** ninguno. Cambio de comportamiento visible: donde antes el issue quedaba
silenciosamente sin asignar, ahora aparece un error con el username que no se pudo resolver.

---

### F4 — Un solo diccionario de rótulos, consumido por toda la app

**Objetivo:** que ningún rótulo visible diga "ADO" cuando el tracker del proyecto no es ADO.

**Valor:** cierra K2. Es el frente de fluidez más grande en superficie: 96 rótulos, y el #1 del ranking
—`shellNav.ts:18` + `App.tsx:455`— está en pantalla el 100% del tiempo **contradiciendo el título de la
propia página**, que desde el 276 ya dice "Tickets GitLab".

**Archivo a editar:** `Stacky Agents/frontend/src/lib/trackerLabels.ts`
Ya existe y ya exporta `nombreDeTracker`, `tituloDeTickets`, `accionSincronizar`. **Extenderlo, no crear
otro helper.** Símbolos exactos a agregar:

```ts
/** Prefijo de referencia de un item. ADO usa "ADO-123"; GitLab usa "#123"
 *  (la notacion que el propio GitLab muestra); el resto cae a "<Nombre>-123". */
export function refDeTicket(tipo: string | null | undefined, id: number | string): string

/** "Abrir en Azure DevOps ↗" | "Abrir en GitLab ↗" | "Abrir en el tracker ↗" */
export function accionAbrirEn(tipo: string | null | undefined): string

/** "Publicar comentario en ADO" | "... en GitLab" — usado por FinishWorkButton. */
export function accionPublicarComentario(tipo: string | null | undefined): string

/** "Estado destino en ADO (opcional)" | "Estado destino en GitLab (opcional)" */
export function etiquetaEstadoDestino(tipo: string | null | undefined): string

/** Sugerencias de estado de cierre POR TRACKER. ADO: Done/Closed/Resolved/Active.
 *  GitLab: las 4 claves logicas reales de services/gitlab_provider.py:152-160
 *  (functional/accepted/rejected/in_progress). Nunca sugerir estados que el
 *  tracker del operador no tiene. */
export function sugerenciasDeEstadoFinal(tipo: string | null | undefined): string[]
```

**Nota de fidelidad obligatoria:** `sugerenciasDeEstadoFinal("gitlab")` DEBE devolver exactamente las 4
claves lógicas de `_state_map_for_gitlab` (`services/gitlab_provider.py:152-160`), no una lista inventada.
El test 3 de abajo lo congela contra el backend.

**Archivos a editar (cablear el helper) — lista EXACTA, en este orden:**

| # | archivo:línea | qué reemplaza |
|---|---|---|
| 1 | `frontend/src/components/shell/shellNav.ts:18` | `label: "Tickets ADO"` → `tituloDeTickets(trackerType)` |
| 2 | `frontend/src/App.tsx:455` | `📋 Tickets ADO` → `📋 ${tituloDeTickets(trackerType)}` |
| 3 | `frontend/src/components/commandPaletteData.ts:74` | `"Ir a Tickets ADO"` → `` `Ir a ${tituloDeTickets(t)}` `` |
| 4 | `frontend/src/pages/TicketBoard.tsx:499` | `ADO-{ticket.ado_id}` → `refDeTicket(tt, ticket.ado_id)` |
| 5 | `frontend/src/pages/TicketBoard.tsx:844` | ídem (chip de épica) |
| 6 | `frontend/src/pages/TicketBoard.tsx:1245` | ídem (banner en ejecución) |
| 7 | `frontend/src/pages/TicketBoard.tsx:175` | ídem (subtítulo modal Run) |
| 8 | `frontend/src/pages/TicketBoard.tsx:732` | `Abrir en Azure DevOps ↗` → `accionAbrirEn(tt)` |
| 9 | `frontend/src/pages/TicketBoard.tsx:1270` | placeholder `"…o ADO-ID…"` → ruteado |
| 10 | `frontend/src/components/SyncStatusBar.tsx:58` | `Sincronizando con ADO…` → `` `Sincronizando con ${nombreDeTracker(tt)}…` `` |
| 11 | `frontend/src/components/FinishWorkButton.tsx:225` | `Publicar comentario en ADO` → `accionPublicarComentario(tt)` |
| 12 | `frontend/src/components/FinishWorkButton.tsx:229` | `Estado destino en ADO (opcional)` → `etiquetaEstadoDestino(tt)` |
| 13 | `frontend/src/components/FinishWorkButton.tsx:236,242-244` | placeholder + `<datalist>` → `sugerenciasDeEstadoFinal(tt)` |
| 14 | `frontend/src/components/FinishWorkButton.tsx:139` | `ADO-{ticket.ado_id}` → `refDeTicket(...)` |
| 15 | `frontend/src/components/TicketSelector.tsx:59,107` | tooltip + ref |
| 16 | `frontend/src/components/TicketGraphView.jsx:99,380,443` | ref + `Abrir en ADO ↗` |
| 17 | `frontend/src/components/CreateChildTaskButton.tsx:167,200,204,219,299` | "en ADO" → ruteado |
| 18 | `frontend/src/components/AgentHistoryModal.tsx:142,166,168` | ref + tooltip + link |
| 19 | `frontend/src/components/ExecutionDetailDrawer.tsx:336,337,339` | `ADO ID:` + ref + link |
| 20 | `frontend/src/components/EmptyState.tsx:46` | lista de trackers: **agregar GitLab, que hoy falta** |
| 21 | `frontend/src/services/peekModel.ts:106,121` | `"Estado ADO"` + título |
| 22 | `frontend/src/services/entityActions.ts:114,120,121,161,169,182,187` | menú contextual |
| 23 | `frontend/src/services/copyFormats.ts:75` | `- Estado ADO:` en el markdown copiado |
| 24 | `frontend/src/components/EmployeeCard.tsx:76` | ref |
| 25 | `frontend/src/components/AgentLaunchModal.tsx:385` | ref |

**De dónde sale `trackerType` en el frontend:** del proyecto activo. `TicketBoard.tsx` **ya lo tiene**
—lo usa para `tituloDeTickets` en `:1103` y `:1198` (Plan 276 F7)—; reusar esa misma fuente. Para
`shellNav.ts` y `commandPaletteData.ts`, que son módulos de datos sin acceso a contexto React, **cambiar
la constante por una función que reciba el tracker** y que el consumidor le pase el valor. No introducir
un store global nuevo.

**Test PRIMERO:** `Stacky Agents/frontend/src/lib/__tests__/trackerLabels.test.ts` (extender el existente
si lo hay; si no, crearlo). Casos:
1. `refDeTicket("azure_devops", 1234) === "ADO-1234"` — **congela ADO primero**.
2. `refDeTicket("gitlab", 1115) === "#1115"`.
3. `sugerenciasDeEstadoFinal("gitlab")` es exactamente `["functional","accepted","rejected","in_progress"]`.
4. `sugerenciasDeEstadoFinal("azure_devops")` es exactamente `["Done","Closed","Resolved","Active"]`.
5. Tracker desconocido / `null` / `undefined` → nunca devuelve "ADO". Cae a "Tracker".
6. `accionAbrirEn("gitlab") === "Abrir en GitLab ↗"`.

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/lib/__tests__/trackerLabels.test.ts --testTimeout=60000
npx tsc --noEmit
```
**Criterio BINARIO:** los 6 casos pasan, `tsc --noEmit` sale **0**, y el censo de F0 baja a **≤ 20**.

**ADVERTENCIA para el implementador — dos trampas reales de este repo:**
- `TicketGraphView.jsx` es **`.jsx`, no `.tsx`**: `tsc --noEmit` **NO lo cubre**. Su única verificación es
  el smoke manual. Tocalo con cuidado y anotalo en el smoke de F8.
- Los rótulos de `commandPaletteData.ts` están **congelados por un test ajeno**:
  `frontend/src/services/__tests__/commandPaletteDevopsActions.test.ts:109-110`. Ese test hay que
  **actualizarlo en el mismo commit**, no ignorarlo. Si lo dejás rojo, el ratchet frontend te frena.

**Flag:** `STACKY_TRACKER_LABELS_GLOBAL_ENABLED`, **default ON**. Solo lectura y presentación: jamás es
excepción.
**Impacto por runtime:** ninguno (frontend puro, agnóstico).
**Trabajo del operador:** ninguno.

---

### F5 — El link deja de apuntar al tracker de otro cliente

**Objetivo:** eliminar la URL de ADO con org y proyecto hardcodeados.

**Valor:** cierra K4. Esto **no es cosmética**: "Abrir en ADO" y "Copiar link ADO" del menú contextual, en
un proyecto GitLab, mandan al operador a `dev.azure.com/UbimiaPacifico/Strategist_Pacifico` — la
organización de **otro cliente**. Es un link roto que además filtra el nombre de un tercero.

**Evidencia:** `frontend/src/utils/trackerUrls.ts:11`
```ts
return `https://dev.azure.com/UbimiaPacifico/Strategist_Pacifico/_workitems/edit/${adoId}`;
```
Consumidores: `services/peekLinks.ts:20`, `services/copyFormats.ts:79`,
`components/StructuredOutput.tsx:78,103`.

**Cambio exacto:** `adoUrl(adoId)` pasa a devolver `string | null` y **solo** construye la URL si recibe
la org y el proyecto reales. Firma nueva:
```ts
export function urlDeTicket(
  tracker: { type: string; ado_url?: string | null; organization?: string; project?: string },
  id: string | number,
): string | null
```
Regla de resolución, en este orden: (1) si el ticket trae `ado_url` del backend, **usarlo tal cual** — el
backend ya construye las URLs GitLab vía `gitlab_deep_links.py`; (2) si el tracker es ADO y hay `organization`
y `project` en la config del proyecto, construirla; (3) si no, **devolver `null`**.

Los 4 consumidores deben manejar `null` **ocultando la acción**, no renderizando un link muerto:
- `peekLinks.ts:20` → si `null`, no ofrecer la entrada "Abrir".
- `copyFormats.ts:79` → si `null`, omitir la línea `- Enlace:` del markdown.
- `StructuredOutput.tsx:103` → si `null`, dejar el texto **sin linkificar** (no un `<a href="null">`).

**Test PRIMERO:** `Stacky Agents/frontend/src/utils/__tests__/trackerUrls.test.ts`
1. Ticket GitLab con `ado_url` del backend → devuelve ese mismo string.
2. Ticket GitLab **sin** `ado_url` → `null`. **Nunca** una URL `dev.azure.com`.
3. Ticket ADO con org+project → la URL correcta con ESA org, no la hardcodeada.
4. Ticket ADO **sin** org configurada → `null`.
5. Guarda anti-regresión: `readFileSync` de `trackerUrls.ts` **no contiene** la subcadena
   `"UbimiaPacifico"`. Assert de ausencia **precedido** por un assert positivo sobre un string sintético
   que sí la contiene, para probar que el detector detecta.

**Comando:** `npx vitest run src/utils/__tests__/trackerUrls.test.ts --testTimeout=60000` + `npx tsc --noEmit`
**Criterio BINARIO:** 5 casos verdes, `tsc` 0, y `grep -c UbimiaPacifico frontend/src/utils/trackerUrls.ts` = **0**.

**Flag:** `STACKY_TRACKER_URLS_ROUTED_ENABLED`, **default ON**. Solo lectura.
**Impacto por runtime:** ninguno.
**Trabajo del operador:** ninguno. **Nota:** si un proyecto ADO no tiene `organization` en su config, la
acción "Abrir en ADO" desaparece en vez de mandar a una org ajena. Es una mejora, y F8 lo verifica.

---

### F6 — El filtro "Solo abiertos" deja de ser ciego en GitLab

**Objetivo:** que el filtro y el color de estado funcionen con el vocabulario del tracker activo.

**Valor:** fricción **funcional**, no cosmética. Hoy `CLOSED_STATES` (`TicketBoard.tsx:98`) es
`["Done","Closed","Resolved","Removed","Completed"]` y `ADO_STATE_COLORS` (`:87-97`) solo conoce estados
ADO. En GitLab (`opened`/`closed`) el filtro no filtra nada y **todos los badges caen al gris**.

**Archivo a crear:** `Stacky Agents/frontend/src/lib/trackerEstados.ts` (lógica pura, sin React).

```ts
/** True si el estado es terminal EN ESE TRACKER. ADO: Done/Closed/Resolved/
 *  Removed/Completed. GitLab: 'closed' (y las claves stacky::accepted/rejected,
 *  que services/gitlab_provider.py:152-160 marca con closed:true).
 *  Comparacion CASE-INSENSITIVE: GitLab devuelve minusculas. */
export function esEstadoCerrado(estado: string | null | undefined, tracker: string | null | undefined): boolean

/** Color del badge por estado y tracker. Nunca devuelve undefined. */
export function colorDeEstado(estado: string | null | undefined, tracker: string | null | undefined): string
```

**Archivos a editar:**
- `frontend/src/pages/TicketBoard.tsx:87-98` — borrar las dos constantes locales, importar del helper.
  Call sites del filtro en `:1159` y el color del badge donde se consuma `ADO_STATE_COLORS`.
- `frontend/src/components/TicketGraphView.jsx:48-55` (`STATE_COLORS`) y `:322` (el array literal de
  estados cerrados, duplicado). Ambos al helper.

**Test PRIMERO:** `Stacky Agents/frontend/src/lib/__tests__/trackerEstados.test.ts`
1. `esEstadoCerrado("Done","azure_devops")` → true. **ADO primero.**
2. `esEstadoCerrado("Active","azure_devops")` → false.
3. `esEstadoCerrado("closed","gitlab")` → true.
4. `esEstadoCerrado("Closed","gitlab")` → true (case-insensitive).
5. `esEstadoCerrado("opened","gitlab")` → false.
6. `esEstadoCerrado("Done","gitlab")` → **false**. Un estado ADO no cierra un ticket GitLab.
7. `esEstadoCerrado(null, "gitlab")` → false, no lanza.
8. `colorDeEstado("opened","gitlab")` !== `colorDeEstado("closed","gitlab")` — prueba que GitLab dejó de
   caer todo al mismo gris. **Este es el assert que prueba el arreglo, no la ausencia de error.**

**Comando:** `npx vitest run src/lib/__tests__/trackerEstados.test.ts --testTimeout=60000` + `tsc --noEmit`
**Criterio BINARIO:** 8 casos verdes, `tsc` 0.

**Flag:** `STACKY_TICKET_STATE_FILTER_ROUTED_ENABLED`, **default ON**. Solo lectura/presentación.
**Impacto por runtime:** ninguno.
**Trabajo del operador:** ninguno.

---

### F7 — Las pantallas ADO-only dejan de ser callejones sin salida

**Objetivo:** que un proyecto GitLab no vea entradas de menú que, al abrirlas, dicen "solo disponible
para proyectos Azure DevOps".

**Valor:** cierra K5. Hoy el tab **PM** se muestra por `sections.pm` (`App.tsx:382`) sin mirar el tracker,
se presenta como *"Fase 1 MVP · sin IA · azure_devops únicamente"* (`PMCommandCenter.tsx:995`), ofrece
**"↻ Sync ADO"** (`:1004`), y al pulsarlo el backend responde *"PM Intelligence Suite v1 solo está
disponible para proyectos Azure DevOps"* (`backend/api/pm.py:71`). Es un callejón sin salida ofrecido en
el menú. Igual: **Sprint Board** (`SprintBoardPage.tsx:144-146`, `api/pm.py:1171`) y **User Stats**
(`UserStatsPage.tsx:104,139`).

**Archivo a crear:** `Stacky Agents/frontend/src/lib/tabsPorTracker.ts` (lógica pura).
```ts
/** Tabs que HOY solo funcionan con Azure DevOps. La lista se deriva del guard
 *  del backend, no se inventa: api/pm.py:71 y api/pm.py:1171. */
export const TABS_SOLO_ADO = ["pm", "sprint", "userstats"] as const;

/** True si el tab debe ofrecerse para ese tracker. */
export function tabDisponible(tab: string, tracker: string | null | undefined): boolean

/** Motivo legible para el tooltip cuando NO esta disponible. Nunca vacio. */
export function motivoNoDisponible(tab: string, tracker: string | null | undefined): string
```

**Comportamiento exacto (importa, no lo cambies):** el tab **no se borra de la navegación**, se muestra
**deshabilitado con tooltip explicativo** (*"El Command Center de PM requiere Azure DevOps; este proyecto
usa GitLab"*). Razón: **los gates de tab que nacen `false` matan el deep link** — es un defecto conocido y
documentado de este repo. Deshabilitar-con-motivo preserva la ruta y explica; ocultar rompe el enlace
directo y no explica nada.

**Archivos a editar:**
- `frontend/src/App.tsx:382` — la decisión de render del tab PM consulta `tabDisponible`.
- `frontend/src/components/shell/shellNav.ts` — los 3 tabs llevan el estado deshabilitado + tooltip.
- `frontend/src/pages/PMCommandCenter.tsx:995` — el subtítulo `"azure_devops únicamente"` pasa a ser el
  motivo ruteado; si el proyecto ES ADO, el texto no cambia.

**Test PRIMERO:** `Stacky Agents/frontend/src/lib/__tests__/tabsPorTracker.test.ts`
1. `tabDisponible("pm","azure_devops")` → true. **ADO primero.**
2. `tabDisponible("pm","gitlab")` → false.
3. `tabDisponible("tickets","gitlab")` → true (no rompas los tabs normales).
4. `tabDisponible("pm", null)` → **true** (sin proyecto no se esconde nada; falla abierto).
5. `motivoNoDisponible("pm","gitlab")` menciona "GitLab" y no está vacío.
6. Sentinela de contrato: `TABS_SOLO_ADO` tiene exactamente 3 entradas. Si alguien agrega un tab
   ADO-only, este test lo obliga a declararlo acá.

**Comando:** `npx vitest run src/lib/__tests__/tabsPorTracker.test.ts --testTimeout=60000` + `tsc --noEmit`
**Criterio BINARIO:** 6 verdes, `tsc` 0, y en el smoke de F8 los 3 tabs aparecen deshabilitados con
tooltip en un proyecto GitLab.

**Flag:** `STACKY_ADO_ONLY_TABS_GATED_ENABLED`, **default ON**. Presentación pura.
**Impacto por runtime:** ninguno.
**Trabajo del operador:** ninguno; deja de perder tiempo entrando a pantallas que no le sirven.

---

### F8 — Gate de cierre, registro de flags y smoke manual

**Objetivo:** dejar el plan verificable de una sola corrida y las **7 flags nuevas** visibles en la UI del arnés.

**F8.1 — Registro de las 7 flags nuevas.** Cada flag es un **bloque atómico**; si falta una pata, la flag
queda registrada pero muerta y **el gate igual pasa**. Los lugares, con el patrón exacto que ya usa
`STACKY_GITLAB_DEEP_LINKS_ENABLED`:

| # | archivo | qué agregar |
|---|---|---|
| 1 | `backend/config.py` | `NOMBRE: bool = os.getenv("NOMBRE", "true")` — **el default EFECTIVO es este**, no el del registry |
| 2 | `backend/services/harness_flags.py` (~línea 451) | la clave en la lista de categoría |
| 3 | `backend/services/harness_flags.py` (~línea 4264) | el `FlagSpec(key=..., default=True, type="bool", ...)` |
| 4 | `backend/services/harness_flags.py` | `_CATEGORY_KEYS` — sin esto el panel no la muestra |
| 5 | `deployment/harness_defaults.env` | la línea `NOMBRE=true` |
| 6 | el consumidor real | `config.config.NOMBRE` en el código de la fase |

**Trampa conocida:** el gate de ayuda de flags exige la cadena **`"Si "` SIN TILDE** en el texto de ayuda.
Y `test_harness_flags_help.py` tiene **4 fallos ajenos preexistentes**: el criterio de aceptación es
**delta cero**, no "verde absoluto" — contá los fallos antes y después y exigí el mismo número.

**F8.2 — Gate ejecutable con exit code.** Crear
`Stacky Agents/backend/scripts/gate_plan282.py`, que corre y devuelve:
- `exit 0` — los 6 KPI en meta.
- `exit 2` — algún KPI fuera de meta (imprime cuál y su valor).
- `exit 5` — **no se pudo medir** (falta backend levantado, o no hay proyecto GitLab configurado). Un
  gate que no puede medir **no debe reportar verde**.

**F8.3 — Smoke manual (requiere backend levantado + token GitLab del operador).** Pasos numerados, con el
resultado esperado de cada uno. Esto **no** se automatiza: requiere credenciales reales.
1. Abrir un proyecto GitLab. La pestaña dice **"Tickets GitLab"** en las dos shells (v1 y v2).
2. Las tarjetas rotulan **`#1115`**, no `ADO-1115`.
3. Marcar "Solo abiertos": la lista **cambia** (hoy no cambia).
4. Menú contextual → "Copiar link": pega una URL de **GitLab**, no de `dev.azure.com`.
5. Cerrar trabajo: el checkbox dice **"Publicar comentario en GitLab"** y el `<datalist>` sugiere las 4
   claves lógicas, no `Done/Closed/Resolved`.
6. Correr un agente hasta el final: la ejecución queda **`completed`** (no `error`) y el comentario
   **aparece en el issue de GitLab**.
7. Reintentar la publicación: **no** aparece un segundo comentario (idempotencia de F1).
8. Los tabs PM / Sprint Board / User Stats están **deshabilitados con tooltip**, y su deep link directo
   sigue aterrizando.
9. Abrir el mismo flujo en un proyecto **ADO**: todo se comporta **exactamente como antes**.

**Criterio BINARIO de F8:** `gate_plan282.py` sale **0**; `run_harness_tests` con los 6 archivos nuevos
registrados no introduce ningún rojo nuevo (delta cero contra el commit base); `tsc --noEmit` sale 0; y
los 9 pasos del smoke se marcan uno por uno en el propio doc del plan al implementar.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **F1 depende del plan 280.** Sin él la ejecución queda `error`, el gate `agent_completion_internal.py:233-234` saltea el publish, y K1 **no se puede medir en vivo** | El test de F1 fuerza `final_status="completed"` y prueba el publicador **aislado**: el router se verifica sin depender del 280. El KPI en vivo se mide en el smoke (F8.3 paso 6) y, si el 280 no está, `gate_plan282.py` sale **exit 5** (no medible), nunca 0. **Un gate que no puede medir no reporta verde** |
| R2 | **F1 duplica comentarios** en el issue del operador | `comment_exists(item_id, marker)` obligatorio antes de publicar; F1 caso 3 lo congela. Precedente directo: la épica duplicada de esta semana nació de publicar sin chequear |
| R3 | **F4 rompe tests ajenos** — `commandPaletteDevopsActions.test.ts:109-110` congela los rótulos viejos | Está declarado en la fase: se actualiza **en el mismo commit**. No es un rojo ajeno, es parte del cambio |
| R4 | **F4 toca 25 sitios**: riesgo de romper el render | Los helpers son funciones puras testeadas antes de cablearse; `tsc --noEmit` cubre todo salvo `TicketGraphView.jsx` (`.jsx`, no tipado) — por eso está en el smoke manual paso 2 |
| R5 | **F2 import circular** `tracker_provider` ↔ `gitlab_provider` | Import **dentro de la función**, patrón ya usado en `tracker_provider.py:141` |
| R6 | **F3 rompe un flujo que dependía del borrado silencioso** | F3 caso 2 conserva el desasignar explícito (`assignee=""`). Solo cambia el caso "no resuelve", que hoy es un bug |
| R7 | **F7 mata deep links** (defecto conocido: los gates de tab nacen `false`) | Por eso **deshabilitar con tooltip**, no ocultar. Caso 4: sin proyecto, falla **abierto**. Smoke paso 8 verifica que el deep link aterriza |
| R8 | **El working tree tiene archivos sin commitear** de otras sesiones, varios del dominio de este plan (`api/tickets.py`, `uiGuards.ts`, `EpicFromBriefModal.tsx`, y **los dos ratchets** `run_harness_tests.sh`/`.ps1`) | F0 se corre **antes** de tocar nada y anota el `git status` de partida en el doc. **PROHIBIDO** `git stash`, `reset`, `checkout --`, `amend`, `rebase`: ese diff es el fix vivo de la épica duplicada. Los ratchets ya están modificados por otra sesión — agregá tus líneas **sin** revertir las suyas |
| R9 | **Tres sesiones paralelas** sobre el MISMO worktree (`N:` ↔ `C:\desarrollo` son el mismo dir por junction) escribiendo 280, 281 y este | **No abrir rama nueva** (mueve el HEAD de las otras sesiones). Commitear con `git commit -m "..." -- "<ruta>"` para no barrer ajenos. Antes de commitear: `git worktree list` + `git log`. **Colisión detectada:** existen DOS archivos `280_*` (ver §6.16) |
| R10 | **Todo test de DB es flaky** por `SQLITE_LOCKED` | Los tests de F1 usan la sesión de test del repo, no la DB viva. **Nunca** correr pytest sin `DATABASE_URL`: un pytest suelto escribe en la base real del operador (193 MB) |
| R11 | **El censo de F0 cuenta comentarios** y da falsos positivos (el código está en español) | El filtro descarta líneas de comentario **y** el test tiene una guarda que prueba que el detector detecta antes de assertar ausencia |
| R12 | **El censo de F0 por AST da CERO si la llamada va por alias** y premia el bug | `_rutea_por_tracker` censa por **REFERENCIA** (`ast.Name` y `ast.Attribute`), no por `ast.Call`. Y el criterio de F0 exige **reproducir primero la foto vieja** (4 / 96) antes de activar los asserts verdes |

---

## 6. Fuera de scope (declarado, para no perderlo)

**Cubierto por el plan 281 (sesión paralela):** el error literal `no usa Azure DevOps` en ticket-grafo, su
intermitencia, el censo por AST de sitios ADO-only con esa firma, y el contrato de ruteo de esos sitios.
**Dependencia blanda:** si el 281 unifica `project_context.py:340-342`, F1 se simplifica pero no cambia de
contrato.

**Ya implementado, no re-planificar:** la idempotencia de `epics/from-brief` (working tree,
`api/tickets.py:8052-8070`) y el guard `sealedWorkItemId` (`frontend/src/services/uiGuards.ts:78`).

**Deliberadamente fuera de este plan:**

1. **El debounce del `output_watcher`** (`output_watcher.py:66-67`: 2 s / 30 s, hardcodeados y ausentes de
   `harness_defaults.env`). Tocarlo cambia el timing de TODAS las corridas, ADO incluidas. El defecto
   medido es el **pisado**, no el debounce. Candidato natural al plan siguiente, junto con el
   `.stacky-done.json` (el bypass determinista que existe en `:62` y que los agentes no escriben).
2. **El bug del stall watchdog de Codex**: `_codex_on_runaway_with_stall` (`codex_cli_runner.py:704-706`)
   **nunca se cablea**, así que el "watchdog de inactividad" es en realidad un reloj de pared duro de
   600 s desde el arranque. Es un defecto real, propio y aislable — merece su propio plan.
3. **`fetch_epics` en GitLab**: es la **única** operación que existe en ADO (`ado_provider.py:487`) y no en
   GitLab. Requiere épicas nativas de grupo (GitLab **Premium**), que el operador no tiene. Ya declarado
   fuera por 276 §7 y 277 §6.
4. **Los silencios de lectura de GitLab**: `fetch_item_updates` (`gitlab_provider.py:556-606`, tres
   `except: pass` ⇒ historial vacío mudo), `fetch_attachments` (`:486-495`, regex sobre la descripción +
   `except: return []`), `fetch_all_comments` (`:436`, idéntico a `fetch_comments`, no pagina), y
   `find_child_by_marker` (`:524-552`, devuelve el PADRE como proxy). Son degradaciones **de lectura**:
   molestan menos que el cierre y la publicación, y son 4 fases más. Van al plan siguiente.
5. **La `CAPABILITY_MATRIX` está STALE**: `services/provider_capabilities.py:94` declara verificación al
   2026-07-25 y `gitlab_provider.py` cambió el 07-31; toda la columna GitLab tiene las líneas corridas
   ~115. Re-verificarla es un trabajo de censo propio, no un subproducto de este plan.
6. **La asimetría `auth_file` vs `ca_bundle`** (`project_manager.py:663-677`): vaciar `auth_file`
   **conserva**, vaciar `ca_bundle` **borra**. **No es un bug ciego** — el docstring en `:655-661` lo
   documenta como decisión deliberada. Lo que falta es el hint en la UI. Es un ítem de una línea que no
   justifica una fase; anotado para el barrido de config.
7. **`initialize_gitlab_project` es constructor, no merge** (`project_manager.py:668-677`): pisa cualquier
   clave de `issue_tracker` que no esté en su lista fija. Es la **misma clase de trampa** que
   `_rebuild_tickets_table_if_needed` en `db.py`, que el 277 parcheó y declaró viva. Merecen un plan
   conjunto de "listas hardcodeadas que se comen los campos nuevos".
8. **La advertencia de `base_url` con namespace pegado**: el anclaje heredado `EditProjectModal.tsx:722`
   está **muerto** (hoy es el bloque de Mantis). El campo vive en `:736`, sin nota de ayuda. La
   normalización silenciosa (`:239` → `newProjectGitlabModel.ts:37-41`) y la validación dura del backend
   (`gitlab_client.py:95-99`) ya lo contienen: el operador no se rompe, solo no se entera temprano.
   Prioridad baja.
9. **Los 2 motores de probe** (`api/global_config.py:349-405` global vs
   `services/local_diagnostics.py:217` por proyecto): divergen a propósito (uno prueba el `.env`, el otro
   el proyecto). `connection_doctor.py:253` **ya consolidó** la parte por proyecto. Lo que falta es que la
   UI diga cuál de los dos corrió. Ítem de UI, no de arquitectura.
10. **`REQUESTS_CA_BUNDLE` global** en `tools/migrar_mantis_gitlab/destination_writer.py:238` — ensucia el
    entorno del proceso entero, justo lo que `gitlab_client.py:143-145` advierte. El migrador tiene su
    propio eje.
11. **Renombrar `ado_id` / `ado_state` / `ado_url`** — migración de esquema, fuera por 276 §7 **y** 277 §6.
    Este plan los deja intactos y solo cambia **cómo se rotulan**.
12. **Sync automático, webhooks, techo de 4.000 issues, Jira y Mantis** — fuera por los planes previos.
13. **El plan 272 nunca escrito**: 270 y 271 le delegaron la unificación de los 6 escritores de estado, el
    `_origin_guard` del motor B y el vocabulario GitLab de `_state_map_for_gitlab`. Sigue huérfano. Este
    plan **consume** las 4 claves lógicas (F4), no las amplía.
14. **RECHAZO EXPLÍCITO del pase del plan 281 §7** — *"construir el equivalente GitLab de los 7 sitios que
    F7 degrada a valor neutro"*: criterios de aceptación (`services/acceptance_criteria.py:25`),
    self-review (`services/self_review.py:43`), similar tickets (`services/similar_tickets.py:91`),
    auto-assign (`services/ticket_assigner.py:356`), business preflight
    (`services/business_preflight.py:37`), enriquecimiento de contexto (`api/agents.py:1798`) y estado
    equivalente de tarea (`api/tickets.py:4912`). **Razón del rechazo:** son **7 features nuevas de
    GitLab**, no arreglos de paridad de algo que ya existe. Sumadas al alcance actual, este plan pasaría
    de 9 fases quirúrgicas a ~16 y dejaría de ser implementable por un modelo menor — que es exactamente
    lo que el encargo prohíbe. Además, el propio 281 las degrada a un valor neutro **honesto**: hoy esos
    7 sitios ya devuelven ese mismo valor por su `except`, así que el 281 no empeora nada y este plan no
    tiene urgencia que justifique tomarlas. **Candidatos naturales al plan siguiente**, en orden de valor:
    similar tickets y auto-assign (los dos que el operador nota) antes que los cinco restantes.
15. **RECHAZO del pase del 281 §7 sobre `ado_sync` y polling** — el breaker `"ado_sync"` usado con key de
    proyecto GitLab (`api/tickets.py:6430`) y la cadencia de `GET /api/tickets` que late a ~8 s por
    colisión de `queryKey` entre `TicketBoard.tsx:987-993` y `useRunningStatus.ts:51-61`. Son problemas
    de **performance y naming**, no de paridad ni de fluidez percibida. Van a un plan de rendimiento.
16. **COLISIÓN DE NUMERACIÓN DETECTADA — no la resuelve este plan, pero queda anotada.** Al momento de
    escribir existen **dos archivos con el número 280**:
    `docs/280_PLAN_EL_DESENLACE_MIRA_EL_TRABAJO_ENTREGADO_UN_SOLO_VEREDICTO.md` (tracked, modificado) y
    `docs/280_PLAN_CALENDARIO_DE_REUNIONES_TEAMS_MINUTAS_Y_PENDIENTES_ACCIONABLES.md` (untracked). Son dos
    planes distintos de dos sesiones distintas. **Requiere decisión del operador**: uno de los dos debe
    renumerarse. Este plan tomó el 282 pinneado y **no renumera nada por su cuenta**.

---

## 7. Glosario

- **Tracker** — sistema de tickets externo. Stacky soporta `azure_devops`, `gitlab`, `jira`, `mantis`.
- **Provider** — adaptador que traduce el puerto `TrackerProvider` (`services/tracker_provider.py:76-118`,
  18 métodos) a la API de un tracker concreto.
- **`ado_id`** — nombre histórico del identificador del item **en cualquier tracker**. En GitLab guarda el
  `iid` (el número que ve el operador), no el `id` global. El nombre es legado; renombrarlo está fuera.
- **`output_watcher`** — daemon que vigila los archivos de salida del agente y cierra la ejecución cuando
  se estabilizan (Modo A: `pending-task.json`, 30 s; Modo B: `comment.html`, 2 s).
- **`_mark_terminal`** — función de cada runner CLI que escribe el estado final de la ejecución.
- **Chokepoint** — punto único por el que pasan los 3 runtimes; acá es
  `services/agent_completion_internal.py`.
- **Estado terminal** — `completed`, `error`, `cancelled`, `needs_review`. Lo opuesto a `ACTIVE_STATUSES`
  (`preparing`, `running`, `queued`).
- **Ratchet** — script que congela un censo para que no empeore. Hay uno `.sh` y uno `.ps1`, **con
  sintaxis distinta**, y todo test nuevo va en los **dos** — o dentro de un archivo ya registrado.
- **Flag del arnés** — interruptor en `services/harness_flags.py` cuyo default **efectivo** vive en
  `config.py`. El comentario del registry puede mentir; leé el `os.getenv`.

---

## 8. Orden de implementación

Las fases ya están escritas en el orden en que se implementan. Bloque backend primero (F1-F3), bloque
frontend después (F4-F7), cierre al final (F8).

1. **F0** — los dos censos, en su versión "rojo esperado". **No avanzar sin ver los números 4 / 96 y sin
   que el detector de `ado_publisher` reporte "no rutea".** Si algún número no reproduce, el censo está
   mal escrito: arreglalo antes de seguir, no ajustes el número esperado.
2. **F1** — router de publicación de comentarios. **Es el de mayor valor del plan.** Se puede implementar
   y testear sin el plan 280; solo su KPI en vivo lo necesita (R1).
3. **F2** — fábrica única. Backend, independiente de todo lo demás.
4. **F3** — assignee estricto. Backend, independiente.
5. **F4** — rótulos. El más largo (25 sitios): entrar con el helper **ya testeado**, y actualizar
   `commandPaletteDevopsActions.test.ts:109-110` en el mismo commit.
6. **F5** — URLs. Depende de F4 (comparte consumidores en `entityActions` y `copyFormats`).
7. **F6** — estados y filtros.
8. **F7** — tabs gateados.
9. **F8** — flags, gate y smoke.

**Corte válido si hay que parar antes de terminar:** F0 → F1 → F8.1/F8.2 entrega el frente de mayor valor
(el trabajo llega al issue de GitLab) de forma cerrada y verificable. F2-F7 son aditivas e independientes
entre sí; ninguna deja el sistema a medio camino si no se hace.

## 9. Definición de Hecho (DoD)

- [ ] Los 6 KPI (K1-K6) en meta, medidos por `backend/scripts/gate_plan282.py` con **exit 0** — o
      **exit 5** documentado si K1 no se puede medir en vivo por falta del plan 280 (R1). Nunca exit 0
      con un KPI sin medir.
- [ ] Los **9 archivos de test** nuevos (4 backend + 5 frontend) existen, pasan, y el conteo exacto de
      casos de cada uno está **escrito en este doc** (no "todos verdes"). `--collect-only -q` confirma el
      número de seleccionados en los 4 de backend.
- [ ] Los tests backend nuevos están registrados en **`run_harness_tests.sh` Y `run_harness_tests.ps1`**.
- [ ] `run_harness_tests` no introduce ningún rojo nuevo: **delta cero** contra el commit base, contado
      antes y después (el repo tiene rojos ajenos preexistentes; "verde absoluto" no es el criterio).
- [ ] `npx tsc --noEmit` sale **0**.
- [ ] Las **7 flags nuevas** (`STACKY_COMMENT_PUBLISH_ROUTED_ENABLED`,
      `STACKY_GITLAB_PROVIDER_FACTORY_ONLY_ENABLED`, `STACKY_GITLAB_ASSIGNEE_STRICT_ENABLED`,
      `STACKY_TRACKER_LABELS_GLOBAL_ENABLED`, `STACKY_TRACKER_URLS_ROUTED_ENABLED`,
      `STACKY_TICKET_STATE_FILTER_ROUTED_ENABLED`, `STACKY_ADO_ONLY_TABS_GATED_ENABLED`) tienen sus
      **6 patas**, **todas nacen ON**, y aparecen en el panel de Configuración → Arnés.
- [ ] `test_harness_flags_help.py` mantiene su conteo de fallos **preexistente**, sin sumar ninguno.
- [ ] Los 9 pasos del smoke manual (F8.3) marcados uno por uno, incluido el **paso 9** (un proyecto ADO se
      comporta exactamente como antes).
- [ ] Ningún archivo de `Stacky Agents/docs/280_*` ni `281_*` fue tocado.
- [ ] Los archivos modificados por otras sesiones al inicio siguen intactos o fueron commiteados por su
      dueño: **no** se ejecutó `git stash`, `reset`, `checkout --`, `amend` ni `rebase`. En particular,
      las líneas que otra sesión ya agregó a `run_harness_tests.sh` y `.ps1` **siguen ahí**.
- [ ] Ninguna fase de este plan modificó `services/claude_code_cli_runner.py`, `codex_cli_runner.py` ni
      `services/run_outcome.py`: **esa capa es del plan 280** y tocarla es un conflicto de merge.
- [ ] Sin `git push` (el push es siempre manual).
