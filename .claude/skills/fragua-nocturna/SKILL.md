---
name: fragua-nocturna
description: Corre UN turno de la Fragua Nocturna (plan 202) — el orquestador que trabaja el backlog de planes de Stacky produciendo SOLO papel revisable para la mañana siguiente: críticas v2 de planes v1, auditorías read-only de ramas con veredicto de mergeabilidad, paquetes listos-para-implementar y un digest triado de decisiones. Deriva la cola del estado real del repo, la drena de a un work item por iteración con presupuesto como corte duro, y deja todo inerte para que el operador decida. NUNCA mergea, NUNCA pushea, NUNCA implementa código de producto y NUNCA toca `main`. Usala cuando el operador diga "corré un turno de la fragua", "trabajá el backlog de planes", "prepará material para mañana", o cuando arme un `/loop` o `/schedule` nocturno sobre esta skill. NO la uses para implementar un plan (eso es `implementar-plan-stacky`) ni para consolidar ramas (eso es `consolidar-ramas-a-main`).
---

# Fragua Nocturna — un turno

Orquestación Claude-nativa del plan 202 (TMV). El **núcleo determinista** vive en el
backend y es idéntico en los 3 runtimes; esta skill es la capa que arma el turno y
dispara el carril de crítica (el único que necesita un modelo).

## Riel innegociable

La noche produce **PAPEL INERTE**. Concretamente:

- **NUNCA** `git merge`, `git push`, `git checkout main`, ni edición de código de producto.
- **NUNCA** escribe en el árbol de tests. Los tests que un paquete propone son TEXTO
  dentro de su `.json`, no archivos ejecutables.
- El auditor es **AUDIT-ONLY DURO**: solo lee objetos git (`git … base...branch`). No
  corre pytest, no hace checkout. Si al terminar `git status --porcelain` cambió, el
  ítem se marca `failed` y el digest lo denuncia.
- La única escritura al repo es la del carril de crítica, que reescribe el doc de un
  plan v1 a v2 **dentro del worktree/rama `nightly/<fecha>`**, jamás en el árbol
  diurno del operador ni en `main`.
- A la mañana el operador lee el digest y **él** decide qué mergear e implementar.

## Precondiciones (verificalas ANTES de hacer nada)

1. `GET /api/night-foundry/status` → `availability.available` debe ser `true`.
   Si es `false`, **parás** y le mostrás al operador `availability.reason`. Los
   motivos posibles son `frozen_deploy` (la Fragua no corre en el deploy congelado:
   ahí no hay repo git ni carpeta de planes), `docs_dir_missing` y `not_a_git_repo`.
2. La flag `STACKY_NIGHT_FOUNDRY_ENABLED` está **default OFF** (excepción dura #3:
   depende del árbol de desarrollo y de `/loop`, que es propio de Claude Code). Se
   enciende desde el panel de flags del Arnés. Si está apagada, las rutas dan 404:
   avisá y parás.
3. Ninguno de los kill-switches está activo (ver abajo).

## El turno, paso a paso

1. **Worktree aislado.** `git worktree add ../_wt/nightly-<fecha> -b nightly/<fecha> main`
   (o `EnterWorktree`). Todo lo que el carril de crítica escriba aterriza ahí. Los
   datos durables (bitácora, digest, paquetes, auditorías) NO viven en el worktree:
   viven en `data_dir()/night_foundry/`, que es estable entre ramas y noches.
2. **Chequeo de corte.** `night_foundry_orchestrator.should_stop(<fecha>, <presupuesto>)`.
   Si devuelve `True`, terminás y reportás el motivo.
3. **Derivar la cola.** `night_foundry_planner.plan_night("<fecha>")`. Deriva del
   estado REAL del repo: planes v1 sin criticar → `critic`; ramas `impl/*` → `auditor`;
   primer plan no implementado del orden canónico de cada hoja de ruta → `package`;
   planes que dicen IMPLEMENTADO con archivos ausentes de `main` → `reconciler`.
   El carril `proposer` está **reservado** y gateado: mientras haya deuda de papel
   (v1 sin criticar, o más de 8 v2 sin implementar, o ratio generar:consumir peor que
   1:3) no se encola nada. La Fragua des-atasca; no fabrica papel.
4. **Drenar.** `run_night("<fecha>", budget=<presupuesto>, dispatch_critic=<callable>)`.
   Un work item por iteración. El `dispatch_critic` que le pasás invoca la skill
   `criticar-y-mejorar-plan` sobre el plan del ítem y devuelve
   `{"output_ref": <ruta del doc>, "cost_tokens": <costo real>}`. Si no le pasás
   `dispatch_critic`, los ítems de crítica quedan `pending` y el resto corre igual
   (ese es el fallback para Codex/Copilot: el operador corre las críticas a mano).
5. **Digest.** `night_foundry_digest.build_digest("<fecha>", budget=…, stopped_reason=…)`.
   Deja `digests/digest-<fecha>.json`: decisiones rankeadas y deduplicadas por
   objetivo, con veredicto de mergeabilidad por rama (`clean` / `conflict` +
   archivos en conflicto / `unknown`).
6. **Notificar.** Resumen de las 3 decisiones de más valor + costo gastado. El
   archivo del digest es la fuente durable y portable; la notificación es cortesía.

## Kill-switches (redundantes, a propósito)

- Archivo `data_dir()/night_foundry/STOP` — se crea y se borra de un clic con
  `POST` / `DELETE /api/night-foundry/stop`. Solo detiene y reanuda; **nunca arranca**.
- Variable `STACKY_NIGHT_FOUNDRY_HARD_DISABLE=1` (propia de la Fragua).
- Variable `STACKY_EVOLUTION_HARD_DISABLE=1` (mismo nombre que reserva el plan 167;
  hoy sin lector en `main` — forward-compatible: un solo botón para ambos).
- Detener el `/loop`, `TaskStop`, o cerrar la sesión.
- La flag maestra apagada (default): todas las rutas responden 404.

## Autonomía: opt-in por construcción

No existe ninguna flag que haga correr la noche sola. El operador arma el `/loop` o
el `/schedule` a mano. Encender la flag maestra solo habilita la maquinaria: el panel
de solo lectura y el botón manual "correr un turno"
(`POST /api/night-foundry/run-one-turn`, que procesa **un** ítem determinista).

## Paridad de runtimes (honesta)

| Pieza | Codex | Claude Code | Copilot |
|---|---|---|---|
| Bitácora, planner, gate, workers, digest, mergeabilidad | sí | sí | sí |
| Rutas HTTP y panel | sí | sí | sí |
| Bucle nocturno (`/loop`) y carril de crítica | manual | **nativo** | manual |

Claude Code es el runtime **primario** de la orquestación. En Codex/Copilot el
operador corre los mismos módulos como CLI y dispara `criticar-y-mejorar-plan` a
mano; la bitácora y el digest son archivos que cualquier runtime lee y escribe.

## Al cerrar

Reportá: cuántos ítems por carril quedaron `done`/`failed`/`pending`, el gasto contra
el techo, el motivo de corte, y las decisiones del digest ordenadas. Si hubo una
violación read-only, decila primero. Y dejá explícito que **nada se mergeó ni se
implementó**: eso lo decide el operador.
