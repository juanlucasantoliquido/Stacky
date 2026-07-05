# Plan 90 — Agente DevOps interactivo multi-turno en el panel DevOps

**Estado:** IMPLEMENTADO (2026-07-05 — F0..F4 verdes; 23 tests del plan + no-regresión;
tsc 0 err; gotcha backfill external_id resuelto con external_id=-ticket.id)
**Versión:** v1 → v2 → v3 (3ª crítica adversarial `criticar-y-mejorar-plan` — foco:
coherencia con contrato de extensión 87 v3 + usabilidad, 2026-07-04)
**Fecha:** 2026-07-04 (v1) / 2026-07-04 (v2) / 2026-07-04 (v3)
**Serie DevOps:** plan 4 (se monta sobre el panel del plan 87; hermano de 88/89, no
depende de ellos).
**Dependencias:** plan 87 (host del panel — solo sus fases F0/F1/F4; ver F0 de este
plan para el bootstrap controlado si el 87 aún no está implementado). NO depende de
88 ni 89.

---

## CHANGELOG v2 → v3 (coherencia con contrato de extensión 87 v3 + red-team adicional)

> El 87 v3 (F4, líneas 662-698) formalizó el contrato `DEVOPS_SECTIONS`: el SHELL
> decide el gate de flag-off vía `healthKey?/gateFlagKey?/gateMessage?` y renderiza
> `FlagGateBanner` (movido a F4 del 87 — ya existe cuando F4 del 87 está
> implementado). Los hermanos 88/89 v3 ya siguen el contrato. El propio 87 v3 (§3.12,
> líneas 935-938) **ya anticipa textualmente** la entrada de este plan:
> `{id:"agente", healthKey:"agent_enabled", gateFlagKey:"STACKY_DEVOPS_AGENT_ENABLED", ...}`
> con "CERO cambios en `DevOpsPage.tsx`". Esta v3 alinea el 90 a esa firma exacta.

- **C6 (IMPORTANTE — drift de contrato entre planes hermanos ya críticados):** F3 de
  90 (v2) declaraba la entrada de `DEVOPS_SECTIONS` SIN `healthKey`/`gateFlagKey`/
  `gateMessage` y hacía que `DevOpsAgentSection.tsx` hand-rolleara el aviso de
  flag-off ("El agente DevOps está apagado...") en vez de delegarlo al shell. Esto
  es el ÚNICO plan de la serie 87-90 que no sigue el contrato de extensión que el
  propio 87 v3 formalizó (y que 88/89 v3 ya cumplen) — y el 87 v3 lo cita
  explícitamente como caso de verificación de su propia escalabilidad (§3.12). Dejarlo
  así no rompe al 90 en aislamiento, pero rompe la coherencia de la serie que ya fue
  críticada asumiendo que los 4 planes se implementan juntos bajo un contrato único.
  **Fix:** la entrada `DEVOPS_SECTIONS` de F3 pasa a declarar
  `healthKey: "agent_enabled"`, `gateFlagKey: "STACKY_DEVOPS_AGENT_ENABLED"`,
  `gateMessage` en llano; `DevOpsAgentSection.tsx` deja de hand-rollear el aviso de
  flag-off (el shell ya lo cubre antes de montar la sección); el criterio binario (e)
  de F3 se separa en dos (contrato declarativo vs aviso global de continuidad, que
  SÍ sigue siendo texto plano porque no es un gate de flag); la nota sobre
  `FlagGateBanner` "puede no existir aún" se corrige (ya existe vía F4 del 87, exigido
  por el propio F0.a de este plan) y se reformula como "no aplica: es un aviso de
  resume, no un gate de flag".
- **C7 (MENOR):** el DoD (línea 979-980, antes de esta v3) y el checklist de F4 no
  mencionaban el nuevo criterio de "no regresión del hand-roll" — se agrega el
  criterio grep-negativo (ver ADICIÓN ARQUITECTO v3 más abajo) al checklist de F4.
- **C8 (MENOR, cosmético — no amerita cambio de código):** F3 punto 4 describe
  "Continuar" como visible solo si `last_status !== "running"`, y el aviso global del
  punto 5 (ahora 6, renumerado por el fix de C6) ya cubre el caso "flag ON pero para
  otro proyecto" — ambos redactados de forma coherente entre sí; se deja intacto tras
  revisar que no colisiona con el fix de C6 (el aviso global sigue siendo un aviso de
  *continuidad de memoria*, no de *flag-off de sección*, por eso no migra al gate del
  shell).
- **[ADICIÓN ARQUITECTO v3]:** se agrega un criterio binario grep-negativo en F3 que
  impide que el hand-roll de C6 regrese en una futura edición: grep en
  `DevOpsAgentSection.tsx` NO debe encontrar el literal `está apagado` (el aviso de
  flag-off es responsabilidad exclusiva del shell vía `FlagGateBanner`), combinado con
  grep que SÍ encuentra `healthKey` en la entrada de `DEVOPS_SECTIONS` de este plan.

**VEREDICTO (sobre v2): APROBADO-CON-CAMBIOS** — 0 BLOQUEANTES, 1 IMPORTANTE (C6,
resuelto en esta v3), 2 MENORES. El hallazgo no compromete la lógica de negocio del
90 (backend F0-F2 intactos y ya sólidos tras v2) pero sí la coherencia estructural de
la serie 87-90 ya validada como conjunto; esta v3 lo cierra antes de implementar.

---

## CHANGELOG v1 → v2 (verificación contra código real)

> Metodología: se verificó CADA claim de infraestructura del plan contra el código
> (`archivo:línea`) antes de aprobarlo. La mayoría pasó; 4 hallazgos requirieron fix.

- **C1 (BLOQUEANTE, resuelto):** el `Ticket` ancla de F2 fijaba
  `external_id=_CONVERSATION_ADO_ID` (-2). La tabla `tickets` tiene un **UNIQUE index**
  `ux_tickets_stacky_tracker_external` sobre `(stacky_project_name, tracker_type,
  external_id)` (`models.py:71-77`). El Brief Pool (-1) NO choca porque es
  **1-por-proyecto** (get-or-create, `api/agents.py:711-715`), pero este plan crea
  **1 ticket POR conversación** ⇒ la **2ª conversación del mismo proyecto** tiraba
  `IntegrityError` (y rompía su propio `test_f2_start_two_conversations_two_tickets`).
  **Fix (F2):** NO setear `external_id` (queda `NULL`, distinto en el UNIQUE tanto en
  SQLite como en Postgres) ⇒ N conversaciones conviven; el discriminador sigue siendo
  `ado_id=-2` (columna sin unique). `tracker_type` queda en su default.
- **C2 (IMPORTANTE, resuelto):** `_current_user()` hacía
  `from api.agents import current_user` — reexport frágil que además carga el módulo
  **pesado** `api.agents` (riesgo de import circular desde un blueprint de imports
  lazy). **Fix:** `from api._helpers import current_user` (ORIGEN canónico, verificado:
  `api/_helpers.py:4`; `api/agents.py:21` solo lo reexporta).
- **C3 (IMPORTANTE, resuelto) + [ADICIÓN ARQUITECTO]:** `harness/resume.py:96` solo
  resume runs con `status == "completed"`. Un último turno `failed`/zombie (el timeout
  de 1800s, `config.py:164`) **pierde el hilo AUNQUE el resume esté ON**, pero el
  `resume_enabled` global de v1 igual mostraba "ok". **Fix:** señal HONESTA
  por-conversación `continuable_with_memory = resume_enabled AND last_status ==
  "completed"` en el GET; la UI avisa **por item**, no solo global (transparencia
  human-in-the-loop: el operador sabe ANTES de continuar si va a arrancar sin memoria).
- **C4 (IMPORTANTE, resuelto):** la identidad de la conversación colgaba de
  `metadata.devops_chat`, escrito por `_launch_turn` **en carrera** con el thread de
  `run_agent` (ambos hacen read-modify-write del JSON de metadata:
  `agent_runner.py:173,274,348,723,883`) ⇒ lost-update posible ⇒ el criterio binario
  del DoD podía fallar en PROD (verde en tests solo porque `run_agent` está mockeado).
  **Fix:** la identidad race-free es `ticket.ado_id == -2` AND
  `execution.agent_type == "devops"`; `devops_chat` queda best-effort/informativo y el
  DoD se reformula sobre la identidad sólida.
- **C5 (MENOR, resuelto):** el relanzamiento durmiente pasa
  `model_override=last_md.get("model_override")` sin garantía de que esa key exista en
  metadata; se agrega nota de verificación (degradación segura: si falta, `run_agent`
  usa su default capeado — nunca Opus por guardarraíl 11).
- **Claims VERIFICADOS que PASARON (no cambian; se documentan para el implementador):**
  `run_agent` es **async** (lanza `threading.Thread` y retorna `execution_id`,
  `agent_runner.py:375-394`) ⇒ el 202 es correcto y el turno NO bloquea el request;
  todos los kwargs que usa F2 existen en la firma (`agent_runner.py:77-98`);
  `send_input` de claude **y** codex firman `(id, text, *, user)` y devuelven `dict` /
  levantan `RuntimeError`/`ValueError` tal como el plan asume
  (`claude_code_cli_runner.py:297`, `codex_cli_runner.py:199,224`); `_one_shot ==
  (ado_id == -1)` (`claude_code_cli_runner.py:858`) ⇒ con `ado_id=-2` el autopublish
  es **doblemente inerte** (falla `_one_shot` Y `agent_type=="business"`, gate `:1302`)
  y el **stdin queda ABIERTO** para multi-turno (el cierre solo ocurre en one-shot,
  `:1141-1149`); `run_agent` persiste `runtime` en metadata (`:173`) ⇒ el ruteo de
  runner en `send_message` es válido; `CodexConsoleDock` soporta `claude_code_cli`
  (`:75`) y expone `setCodexConsoleExecution` (`:52`); `project_enabled` firma
  `(*, enabled, projects_csv, project_name)` (`cli_feature_flags.py:25`).

**VEREDICTO (sobre v1): RECHAZADO** — 1 hallazgo BLOQUEANTE (C1: colisión del UNIQUE en
la 2ª conversación). Esta v2 lo resuelve junto con 3 IMPORTANTES y 1 MENOR ⇒ el plan
queda **listo para implementar**.

---

## 1. Objetivo + KPI

Dar al equipo DevOps un **agente genérico conversacional** dentro del panel DevOps:
el operador abre una conversación, el agente trabaja sobre el workspace del proyecto
(evaluar opciones, revisar configuraciones, preparar despliegues, tareas variadas) y
el operador **sigue interactuando en la misma sesión** — multi-turno real, NO el
patrón one-shot de `run_brief`. Toda acción que modifique estado se propone primero
y espera confirmación explícita en el chat (HITL innegociable).

La interactividad NO se inventa: se **cablea infraestructura que ya existe y está
probada**:

| Capacidad | Infra existente (evidencia) |
|---|---|
| Sesión viva multi-turno (stdin abierto, mensajes stream-json) | `services/claude_code_cli_runner.py:744` (`stdin=subprocess.PIPE # interactivo`), `:773-777` ("NO cerramos stdin: queda abierto para que el operador responda"), `send_input` `:297-332` |
| Endpoint de respuesta del operador | `POST /api/executions/<id>/input` (`api/executions.py:99-119`, despacha a `send_input` de claude o codex) |
| Continuación con proceso muerto (codex) | `codex_cli_runner.send_input:199-251` — fallback interno a `codex exec resume <session>` (mode `"resume"`) |
| Continuación con proceso muerto (claude) | `--resume <session_id>` automático: `_resolve_resume` (`claude_code_cli_runner.py:627-628, 2043-2076`) → `harness/resume.py:47` (dueño único, filtra por `ticket_id`+`agent_type`+status completed; `metadata["session_id"]` persistido en `:1267-1269`) |
| UI de chat (stream SSE + input del operador + fases en vivo) | `frontend/src/components/CodexConsoleDock.tsx` (soporta `codex_cli` Y `claude_code_cli`, `:74-77`; envía por `Executions.sendCodexInput`, `endpoints.ts:1207-1211`; stream `endpoints.ts:1218`) |
| Ancla local de ejecuciones sin ticket real | patrón "Brief Pool Ticket" `ado_id=-1` (`api/agents.py:708-728`) |
| Presupuesto anti-runaway | RunawayGuard H5 ya cableado en claude+codex |
| Cancelar/cerrar sesión | `Executions.cancel` (`endpoints.ts:1212`), `cancel()` del runner (`claude_code_cli_runner.py:207`) |

**Lo NUEVO de este plan es fino:** (1) el agente `DevOpsAgent` (registry + `.agent.md`
con guardrails de producción), (2) un blueprint de **conversaciones** (3 endpoints que
orquestan lo existente), (3) la sección "Agente DevOps" en el panel del 87 que abre el
dock de chat existente, (4) la flag master.

**KPI / impacto esperado** (aspiracional; los criterios binarios están en F4):
- El operador abre una conversación DevOps y recibe la primera respuesta del agente
  en la misma UI, y puede responder ≥ 2 turnos sin relanzar nada a mano.
- Una conversación cuyo proceso terminó (timeout 1800s, `config.py:164`) se continúa
  con 1 click y el agente conserva el hilo (vía `--resume` / `codex exec resume`).
- 0 endpoints nuevos de streaming/input: se reusa el 100% del canal existente.
- 0 acciones mutantes sin confirmación del operador en el chat (regla R-HITL del
  `.agent.md`).

## 2. Por qué ahora / gap que cierra

- La serie 87/88/89 construye el panel DevOps (criticada v2/v3, aún sin implementar)
  pero TODO su alcance es declarativo (pipelines, publicaciones, ambientes). El pedido
  del operador es explícito: usar el agente EN PRODUCCIÓN para tareas básicas de
  DevOps, **iterando** — y hoy el único camino conversacional es por ticket
  (`CodexConsoleDock` sobre runs de tickets) o `run_brief` (one-shot orientado a
  épicas, con autopublish).
- La infraestructura multi-turno está pagada y sin volante (igual que el motor de
  pipelines antes del 87): stdin vivo + `--resume` + dock de chat existen; falta el
  agente, el ancla de conversación y la entrada de UI.
- Riesgo bajo: el plan NO toca los contratos de runners ni de `/api/executions`; solo
  agrega un agente al registry, 3 endpoints finos y una sección de UI.

## 3. Principios y guardarraíles (NO negociables)

1. **Human-in-the-loop:** el agente NUNCA ejecuta acciones mutantes (deploys, cambios
   de configuración, comandos que modifiquen estado de un ambiente) sin proponer
   primero el plan en el chat y recibir la palabra exacta `CONFIRMO` del operador
   (regla R-HITL del `.agent.md`, F1). Leer/diagnosticar/comparar es libre. El
   operador puede cancelar la sesión en cualquier momento (infra existente).
2. **Mono-operador, sin auth real:** nada de roles/permisos.
3. **Flags editables por UI, default OFF:** flag master nueva
   `STACKY_DEVOPS_AGENT_ENABLED` (categoría `devops` del plan 87, `env_only=False`,
   `requires="STACKY_DEVOPS_PANEL_ENABLED"`). **NO pasar `default=` en el FlagSpec**
   (gotcha `_CURATED_DEFAULTS_ON`). `label` y `group` son REQUERIDOS del dataclass
   (`harness_flags.py:21-33`). Pata de deploy: línea en `backend/harness_defaults.env`
   + test (patrón 87 C13). `deployment/export_harness_defaults.py` NO requiere
   cambios (la flag es bool `env_only=False`; el snapshot manual es la pata).
4. **Byte-idéntico con flag OFF:** con `STACKY_DEVOPS_AGENT_ENABLED=false` los
   endpoints nuevos devuelven 404, la sección no se muestra (health aditivo
   `agent_enabled:false`), y ningún flujo existente cambia un byte.
5. **No degradar lo existente:** `run_agent`, los runners, `/api/executions/<id>/input`
   y `CodexConsoleDock` NO cambian de contrato. Todo es aditivo.
6. **3 runtimes — paridad y degradación EXPLÍCITA:**
   - `claude_code_cli` (primario): sesión viva por stdin stream-json + continuación
     `--resume` (flags existentes `CLAUDE_CODE_CLI_RESUME_ENABLED/_PROJECTS`,
     `harness_flags.py:275-285`, editables por UI).
   - `codex_cli` (paridad): stdin vivo o `codex exec resume` interno
     (`codex_cli_runner.send_input:199-251`) + flags `CODEX_CLI_RESUME_*`.
   - `github_copilot` (degradación controlada): el chat in-panel requiere runtime CLI;
     el endpoint rechaza `github_copilot` con 400 `devops_chat_requires_cli_runtime`
     (patrón `autopublish_requires_claude_cli`, `api/agents.py:599-608`) y el detail
     indica el camino nativo: el flujo interactivo VS Code existente (`open_chat`,
     `api/agents.py:992`) — que ya ES multi-turno dentro de VS Code.
7. **Cero trabajo extra al operador:** opt-in (flag OFF). Si el operador no activa
   nada, Stacky es byte-idéntico.
8. **Ratchet:** todo archivo de test backend nuevo se registra en
   `backend/scripts/run_harness_tests.sh` **y** `run_harness_tests.ps1`
   (`HARNESS_TEST_FILES`), o el meta-test del plan 49 F4 falla.
9. **Ayuda llana (plan 86):** entrada `PlainHelp` para la flag nueva en
   `services/harness_flags_help.py` (hay meta-test de cobertura).
10. **Sin autopublish accidental:** el finalizador de épicas del runner claude solo
    corre con `agent_type == "business"` y `_one_shot`
    (`claude_code_cli_runner.py:1300-1303`); el agente nuevo usa
    `agent_type="devops"` y `work_item_type="Task"` ⇒ inerte por construcción
    (test proxy en F1).
11. **Cap de modelo:** el chat DevOps NUNCA usa Opus/Fable: `llm_router.clamp_model`
    SIN `allow_opus` (a diferencia de `run_brief`, `api/agents.py:655-657`).

## 4. Fases

> Comando de tests backend (por archivo, con el venv del repo — la suite completa está
> contaminada, plan 49), ejecutado desde `Stacky Agents/backend`:
> `.venv/Scripts/python.exe -m pytest tests/<archivo> -q`
> Gate frontend: `npx tsc --noEmit` en `Stacky Agents/frontend` (0 errores). Este plan
> NO agrega lógica TS pura que requiera vitest (la lógica vive en backend testeado);
> si el 87 F3.0 ya instaló vitest, no se usa aquí igualmente.

### F0 — Host del panel (dependencia 87) + flag master `STACKY_DEVOPS_AGENT_ENABLED`

**Objetivo:** garantizar que el host del panel DevOps existe y dar de alta la flag
master del agente en las 4 patas sin romper meta-tests.

**F0.a — Pre-flight de dependencia (determinista, sin inferencia):**
1. Verificar si existe `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` Y si exporta
   `DEVOPS_SECTIONS` (grep literal `export const DEVOPS_SECTIONS`).
2. **Si existe:** el 87 (al menos su host) está implementado → seguir a F0.b.
3. **Si NO existe:** implementar PRIMERO, tal cual están escritas en
   `Stacky Agents/docs/87_PLAN_PANEL_DEVOPS_CREADOR_GRAFICO_PIPELINES.md` (v3), SOLO
   estas fases del 87: **F0** (flag `STACKY_DEVOPS_PANEL_ENABLED` + categoría
   `devops`), **F1** (blueprint `api/devops.py` con `/health` y `/parse-yaml` +
   centinela) y **F4** (página `DevOpsPage.tsx` + registro `DEVOPS_SECTIONS` + tab
   gated en `App.tsx`), con sus tests nombrados (`test_plan87_devops_flag.py`,
   `test_plan87_devops_endpoints.py`). NO implementar 87 F2/F3/F5/F6 (el builder de
   pipelines NO es prerequisito del chat). La única desviación permitida: si F4 del 87
   se implementa sin F5, la entrada `pipelines` de `DEVOPS_SECTIONS` puede renderizar
   el placeholder literal `<p>Creador de pipelines: pendiente (plan 87 F5).</p>` en
   vez de `<PipelineBuilderSection/>`.
4. Cuando el 87 se implemente completo después, sus fases son idempotentes: lo ya
   creado por este bootstrap se conserva (mismos archivos, mismos nombres).

**F0.b — Alta de la flag (archivos a editar):**
1. `Stacky Agents/backend/config.py` — inmediatamente después de
   `STACKY_DEVOPS_PANEL_ENABLED` (creada por 87 F0 o por F0.a):
   ```python
   STACKY_DEVOPS_AGENT_ENABLED: bool = os.getenv(
       "STACKY_DEVOPS_AGENT_ENABLED", "false"
   ).strip().lower() == "true"
   ```
2. `Stacky Agents/backend/services/harness_flags.py`:
   - En `_CATEGORY_KEYS["devops"]` agregar `"STACKY_DEVOPS_AGENT_ENABLED"` después de
     `"STACKY_DEVOPS_PANEL_ENABLED"`.
   - `FlagSpec` nuevo junto al de `STACKY_DEVOPS_PANEL_ENABLED` — snippet COMPLETO:
     ```python
     FlagSpec(
         key="STACKY_DEVOPS_AGENT_ENABLED",
         type="bool",
         label="Agente DevOps interactivo (Plan 90)",
         description=(
             "Plan 90 — Habilita el agente DevOps conversacional del panel DevOps: "
             "conversaciones multi-turno sobre runtimes CLI (claude/codex) con "
             "confirmacion explicita para acciones mutantes. Expone "
             "/api/devops/agent/conversations. Default OFF: los endpoints devuelven "
             "404 y la seccion muestra aviso."
         ),
         group="global",  # mismo group que STACKY_DEVOPS_PANEL_ENABLED (87 F0)
         env_only=False,  # editable por UI (categoría 'devops')
         requires="STACKY_DEVOPS_PANEL_ENABLED",  # sin panel no hay seccion donde usarlo
     )
     ```
     ⚠️ SIN `default=` (gotcha `_CURATED_DEFAULTS_ON`). ⚠️ SIN `reserved=` (tiene
     consumidor real en F2).
3. `Stacky Agents/backend/services/harness_flags_help.py` — entrada `PlainHelp` para
   la key, imitando la estructura de la de `STACKY_DEVOPS_PANEL_ENABLED` (87 F0):
   qué es en llano, qué pasa ON/OFF, ejemplo cotidiano ("Encendela para chatear con
   el agente DevOps desde la solapa DevOps; apagala y la seccion desaparece").
4. `Stacky Agents/backend/harness_defaults.env` — línea
   `STACKY_DEVOPS_AGENT_ENABLED=false` (orden alfabético del archivo).
5. `Stacky Agents/deployment/export_harness_defaults.py` — SIN cambios (verificar
   solamente que el script no tenga una lista blanca que excluya la key; a la fecha
   lee del `.env` del deploy y no necesita alta por key).

**Tests PRIMERO** — archivo nuevo `Stacky Agents/backend/tests/test_plan90_devops_agent_flag.py`:
- `test_f0_flag_in_registry`: la key está en `FLAG_REGISTRY`; `env_only is False`;
  `requires == "STACKY_DEVOPS_PANEL_ENABLED"`; `group == "global"`; `label` no vacío.
- `test_f0_flag_in_category_devops`: la key está en `_CATEGORY_KEYS["devops"]`.
- `test_f0_config_default_off` (patrón 87 C8, inmune al env del runner):
  ```python
  def test_f0_config_default_off(monkeypatch):
      monkeypatch.delenv("STACKY_DEVOPS_AGENT_ENABLED", raising=False)
      import importlib, config
      importlib.reload(config)
      assert config.config.STACKY_DEVOPS_AGENT_ENABLED is False
  ```
- `test_f0_flag_has_plain_help`: la key existe en el dict de ayuda de
  `harness_flags_help.py`.
- `test_f0_harness_defaults_contains_flag`: `backend/harness_defaults.env` contiene
  el literal `STACKY_DEVOPS_AGENT_ENABLED=false` (patrón
  `tests/test_plan75_deep_links_wiring.py:50-58`).
- No-regresión: correr también `tests/test_harness_flags.py` y
  `tests/test_flag_wiring.py`.

**Registro ratchet:** agregar `tests/test_plan90_devops_agent_flag.py` a
`scripts/run_harness_tests.sh` y `scripts/run_harness_tests.ps1`.

**Criterio binario:** 5 tests nuevos + `test_harness_flags.py` + `test_flag_wiring.py`
verdes; con F0.a hecho, `DEVOPS_SECTIONS` existe (grep) y los tests del 87
F0/F1 nombrados arriba pasan.
**Flag:** `STACKY_DEVOPS_AGENT_ENABLED` (default OFF).
**Runtimes:** sin impacto.
**Trabajo del operador:** ninguno (opt-in).

### F1 — `DevOpsAgent`: registry backend + `.agent.md` con guardrails de producción

**Objetivo:** que `agent_runner.run_agent(agent_type="devops", ...)` sea despachable
(hoy lanzaría `UnknownAgentError`, `agent_runner.py:99-101`) y que el runtime CLI
tenga su `.agent.md` con las reglas HITL.

**Archivo NUEVO:** `Stacky Agents/backend/agents/devops.py` (estructura EXACTA de
`agents/qa.py:1-35`, el agente más simple del registry):
```python
from .base import BaseAgent


class DevOpsAgent(BaseAgent):
    type = "devops"
    name = "DevOps"
    icon = "🛠️"
    description = "Agente DevOps conversacional: diagnostico, configuraciones y despliegues con confirmacion"
    inputs_hint = [
        "mensaje del operador (chat DevOps)",
        "workspace del proyecto",
    ]
    outputs_hint = [
        "respuesta conversacional",
        "plan de accion propuesto (pendiente de CONFIRMO)",
        "resumen de acciones ejecutadas",
    ]
    default_blocks: list[str] = []

    def system_prompt(self) -> str:
        return (
            "Sos el agente DevOps de Stacky. Trabajas en modo CONVERSACIONAL "
            "multi-turno: respondes, proponés y esperás la respuesta del operador. "
            "Regla de oro (R-HITL): NUNCA ejecutes una accion que modifique estado "
            "(deploy, cambio de configuracion, borrado, reinicio de servicios, "
            "escritura fuera del workspace) sin antes mostrar el plan exacto de "
            "comandos y recibir la palabra CONFIRMO del operador. Diagnosticar, "
            "leer y comparar es libre. Nunca imprimas secretos ni credenciales."
        )
```

**Archivo a editar:** `Stacky Agents/backend/agents/__init__.py` — agregar
`from .devops import DevOpsAgent` (orden alfabético de imports) y `DevOpsAgent(),`
en la lista del `registry` (después de `DeveloperAgent(),`).

**Archivo NUEVO:** `Stacky Agents/backend/Stacky/agents/DevOpsAgent.agent.md`
(mismo directorio que `BusinessAgent.agent.md` — es el que lee el runtime; los
runners CLI resuelven por `vscode_agent_filename` dentro de ese directorio, mismo
mecanismo probado del BusinessAgent). Contenido completo:
```markdown
---
name: DevOpsAgent
description: Agente DevOps generico y conversacional. Diagnostica, evalua opciones, revisa configuraciones y prepara/ejecuta despliegues del proyecto activo. Multi-turno - propone y espera; NUNCA ejecuta acciones mutantes sin la palabra CONFIRMO del operador.
---

# DevOpsAgent — agente DevOps conversacional (v1.0.0)

Sos un ingeniero DevOps senior, generalista y pragmatico. Trabajas DENTRO del
workspace del proyecto que Stacky te indica y conversas con el operador en
multi-turno: cada mensaje tuyo puede terminar en una pregunta o en un plan
propuesto, y el operador respondera en el mismo hilo.

## R-INTERACTIVO (forma de trabajo)
- NO asumas que este es tu unico turno: si falta un dato decisivo, pedilo y espera.
- Respuestas CORTAS y accionables. Nada de ensayos.
- Si la tarea es grande, dividila y avanza por partes confirmadas.

## R-HITL (regla de oro, innegociable)
- Accion MUTANTE = cualquier cosa que cambie estado: deploy, push, cambio de
  configuracion o variables, borrado/movida de archivos fuera de tu carpeta de
  outputs, reinicio de servicios, DML, creacion de recursos.
- Antes de CUALQUIER accion mutante: mostra el PLAN EXACTO (comandos literales,
  objetivo, riesgo, rollback) y termina tu turno pidiendo confirmacion.
- Solo ejecuta ese plan si el operador responde con la palabra CONFIRMO.
  "ok", "dale", "si" NO alcanzan: pedi el CONFIRMO literal.
- Si el operador pide algo destructivo sin plan previo, primero presenta el plan.

## R-SCOPE
- Opera solo dentro del workspace del proyecto y tu carpeta de outputs.
- Lectura/diagnostico/comparacion: libre (logs, configs, pipelines, estados).
- NUNCA imprimas ni copies secretos, tokens, credenciales o connection strings;
  si aparecen en un archivo, referencialos por ruta y nombre de variable.

## R-SALIDA
- Al cerrar una tarea (o cuando el operador lo pida) entrega un resumen breve:
  que se hizo, que quedo pendiente, y comandos ejecutados (sin secretos).
```

**Tests PRIMERO** — archivo nuevo `Stacky Agents/backend/tests/test_plan90_devops_agent_registry.py`:
- `test_f1_agent_registered`: `import agents; a = agents.get("devops")` → no es None,
  `a.type == "devops"`, `a.name == "DevOps"`, `a.system_prompt()` contiene `"CONFIRMO"`.
- `test_f1_agent_in_list_agents`: `agents.list_agents()` contiene un dict con
  `type == "devops"`.
- `test_f1_agent_never_business`: `agents.get("devops").type != "business"` — proxy
  binario de que el autopublish de épicas jamás corre para este agente (el gate exige
  `agent_type == "business"`, `claude_code_cli_runner.py:1302`).
- `test_f1_agent_md_exists_with_guardrails`: el archivo
  `backend/Stacky/agents/DevOpsAgent.agent.md` existe (resolver la ruta con el mismo
  helper que use `services/stacky_agents.py` — `stacky_agents_dir()` — o path relativo
  al repo), no está vacío, y contiene los literales `R-HITL` y `CONFIRMO`.
- NOTA: NO editar `backend/Stacky/agents/manifest.json` a mano — lo regenera
  `services/stacky_agents.py` (`write_manifest:208`, `materialize_agents:281-349`).

**Registro ratchet:** agregar el archivo a ambos scripts.

**Criterio binario:** 4 tests verdes; `agents.get("devops")` retorna la instancia.
**Flag:** ninguna (registrar el agente es inerte: nadie lo invoca hasta F2; con flag
OFF los endpoints de F2 devuelven 404 ⇒ byte-idéntico en flujos existentes).
**Runtimes:** sin impacto todavía (el agente existe pero no se lanza).
**Trabajo del operador:** ninguno.

### F2 — Backend: blueprint de conversaciones `/api/devops/agent/...`

**Objetivo:** los 3 endpoints que orquestan lo existente: abrir conversación,
mandar un mensaje (vivo por stdin o continuación por nuevo run con resume), y listar
conversaciones para retomar.

**Modelo de datos (SIN tablas nuevas):** una conversación = un `Ticket` ancla local
con `ado_id=-2` (patrón Brief Pool `ado_id=-1`, `api/agents.py:708-728`, precedente
probado: esos tickets negativos conviven con sweeps/outbox sin tratamiento especial).
A diferencia del Brief Pool (1 por proyecto), acá se crea **un ticket POR
conversación** — así `harness.resume.resolve` (que filtra por `ticket_id` +
`agent_type`, `harness/resume.py:92-101`) mantiene la continuidad de sesión POR
conversación sin código nuevo de resume.

**Archivo NUEVO:** `Stacky Agents/backend/api/devops_agent.py`
```python
"""api/devops_agent.py — Conversaciones del agente DevOps (Plan 90).
url_prefix="/devops/agent" → rutas /api/devops/agent/... (NO poner /api/ en el
prefix; mismo gotcha C2 del plan 73)."""
from datetime import datetime

from flask import Blueprint, jsonify, request

import config as _config

bp = Blueprint("devops_agent", __name__, url_prefix="/devops/agent")

_CLI_RUNTIMES = ("claude_code_cli", "codex_cli")
_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
_CONVERSATION_ADO_ID = -2


def _flag_off() -> bool:
    return not getattr(_config.config, "STACKY_DEVOPS_AGENT_ENABLED", False)


def _current_user() -> str:
    # Mismo header sin validar que usa el resto de la app (mono-operador).
    # C2 (v2): importar del ORIGEN canónico api._helpers (api/_helpers.py:4).
    # api.agents:21 solo lo reexporta; importarlo de ahí carga el módulo pesado
    # api.agents y arriesga import circular desde este blueprint de imports lazy.
    from api._helpers import current_user
    return current_user()


@bp.post("/conversations")
def start_conversation():
    if _flag_off():
        return jsonify({"error": "devops_agent_disabled"}), 404
    body = request.get_json(silent=True) or {}
    project = (body.get("project") or "").strip()
    message = (body.get("message") or "").strip()
    if not project or not message:
        return jsonify({"ok": False, "error": "project y message son obligatorios"}), 400
    runtime = (body.get("runtime") or "claude_code_cli").strip()
    if runtime not in _CLI_RUNTIMES:
        return jsonify({
            "ok": False,
            "error": "devops_chat_requires_cli_runtime",
            "detail": (
                f"El chat DevOps requiere runtime CLI {_CLI_RUNTIMES}; recibido "
                f"{runtime!r}. Para GitHub Copilot usa el flujo interactivo de "
                "VS Code existente (open_chat)."
            ),
        }), 400
    # Cap de modelo SIN Opus (guardarraíl 11).
    from services import llm_router as _llm_router
    model_raw = (body.get("model") or "").strip()
    model_override = _llm_router.clamp_model(model_raw) if model_raw else None
    effort_raw = (body.get("effort") or "").strip().lower()
    effort_override = effort_raw if effort_raw in _EFFORTS else None

    from db import session_scope
    from models import Ticket
    title = f"[Stacky] DevOps Chat — {message[:60]}"
    with session_scope() as session:
        # C1 (v2): NO setear external_id. tickets tiene UNIQUE
        # ux_tickets_stacky_tracker_external (stacky_project_name, tracker_type,
        # external_id) (models.py:71-77). El Brief Pool (-1) evita el choque siendo
        # 1-por-proyecto (get-or-create); acá se crea 1 ticket POR conversación, así
        # que fijar external_id=-2 haría colisionar la 2ª conversación del mismo
        # proyecto (IntegrityError). external_id=None ⇒ NULLs distintos en el UNIQUE
        # (SQLite y Postgres) ⇒ N conversaciones conviven. Discriminador = ado_id=-2
        # (sin unique). tracker_type queda en su default ("azure_devops").
        ticket = Ticket(
            ado_id=_CONVERSATION_ADO_ID,
            project=project,
            stacky_project_name=project,
            title=title,
            work_item_type="Task",
            ado_state="Active",
        )
        session.add(ticket)
        session.flush()
        conversation_id = ticket.id

    execution_id, launch_error = _launch_turn(
        conversation_id=conversation_id,
        project=project,
        message=message,
        runtime=runtime,
        model_override=model_override,
        effort_override=effort_override,
    )
    if launch_error is not None:
        return launch_error
    return jsonify({
        "ok": True,
        "conversation_id": conversation_id,
        "execution_id": execution_id,
        "runtime": runtime,
    }), 202


@bp.post("/conversations/<int:conversation_id>/message")
def send_message(conversation_id: int):
    if _flag_off():
        return jsonify({"error": "devops_agent_disabled"}), 404
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "message es obligatorio"}), 400

    from db import session_scope
    from models import AgentExecution, Ticket
    with session_scope() as session:
        ticket = session.query(Ticket).filter_by(
            id=conversation_id, ado_id=_CONVERSATION_ADO_ID
        ).first()
        if ticket is None:
            return jsonify({"ok": False, "error": "conversation_not_found"}), 404
        project = ticket.stacky_project_name or ticket.project
        last = (
            session.query(AgentExecution)
            .filter(AgentExecution.ticket_id == conversation_id)
            .filter(AgentExecution.agent_type == "devops")
            .order_by(AgentExecution.id.desc())
            .first()
        )
        last_id = last.id if last is not None else None
        last_status = last.status if last is not None else None
        last_md = dict(last.metadata_dict or {}) if last is not None else {}

    # 1) Camino VIVO: proceso corriendo con stdin abierto → send_input existente.
    if last_id is not None and last_status == "running":
        runtime = last_md.get("runtime")
        try:
            if runtime == "claude_code_cli":
                from services.claude_code_cli_runner import send_input
            else:
                from services.codex_cli_runner import send_input
            result = send_input(last_id, message, user=_current_user())
            return jsonify({
                "ok": True,
                "mode": result.get("mode", "stdin"),
                "execution_id": last_id,
            })
        except (RuntimeError, ValueError):
            pass  # stdin cerrado / sesión no disponible → camino 2

    # 2) Camino DURMIENTE: nuevo run sobre el MISMO ticket. La continuidad la aporta
    #    harness.resume.resolve dentro del runner (--resume / codex exec resume) si
    #    las flags CLAUDE_CODE_CLI_RESUME_* / CODEX_CLI_RESUME_* están ON.
    #    C5 (v2): last_md.get("model_override") depende de que run_agent persista el
    #    modelo resuelto bajo esa key en metadata — VERIFICAR en agent_runner.py; si la
    #    key no existe, esto queda None y run_agent usa su default (capeado, nunca Opus
    #    por guardarraíl 11): degradación segura, solo se pierde la preferencia de
    #    modelo del operador entre turnos durmientes (no hay fuga de modelo prohibido).
    execution_id, launch_error = _launch_turn(
        conversation_id=conversation_id,
        project=project,
        message=message,
        runtime=last_md.get("runtime") or "claude_code_cli",
        model_override=last_md.get("model_override"),
        effort_override=None,
    )
    if launch_error is not None:
        return launch_error
    return jsonify({"ok": True, "mode": "new_run", "execution_id": execution_id}), 202


@bp.get("/conversations")
def list_conversations():
    if _flag_off():
        return jsonify({"error": "devops_agent_disabled"}), 404
    project = (request.args.get("project") or "").strip() or None

    # C3 (v2): resume_enabled se calcula ANTES del loop para derivar la señal honesta
    # por-conversación. project_enabled con project=None y allowlist no vacía devuelve
    # False (conservador — avisa de más, nunca de menos).
    from config import config as _cfg
    from services.cli_feature_flags import project_enabled
    resume_enabled = project_enabled(
        enabled=getattr(_cfg, "CLAUDE_CODE_CLI_RESUME_ENABLED", False),
        projects_csv=getattr(_cfg, "CLAUDE_CODE_CLI_RESUME_PROJECTS", ""),
        project_name=project,
    )

    from db import session_scope
    from models import AgentExecution, Ticket
    items = []
    with session_scope() as session:
        q = session.query(Ticket).filter(Ticket.ado_id == _CONVERSATION_ADO_ID)
        if project:
            q = q.filter(Ticket.stacky_project_name == project)
        tickets = q.order_by(Ticket.id.desc()).limit(50).all()
        for t in tickets:
            last = (
                session.query(AgentExecution)
                .filter(AgentExecution.ticket_id == t.id)
                .filter(AgentExecution.agent_type == "devops")
                .order_by(AgentExecution.id.desc())
                .first()
            )
            last_status = last.status if last else None
            items.append({
                "conversation_id": t.id,
                "title": t.title,
                "project": t.stacky_project_name,
                "last_execution_id": last.id if last else None,
                "last_status": last_status,
                "last_runtime": (last.metadata_dict or {}).get("runtime") if last else None,
                "started_at": t.created_at.isoformat() if getattr(t, "created_at", None) else None,
                # [ADICIÓN ARQUITECTO v2] Señal HONESTA por-conversación (C3): continuar
                # SOLO conserva el hilo si (a) el resume está activo para el proyecto Y
                # (b) el último turno terminó "completed" — harness/resume.py:96 solo
                # resume runs status=="completed". Un último run failed/zombie (timeout
                # 1800s) pierde memoria aunque el flag esté ON; el resume_enabled global
                # por sí solo mentía. La UI avisa por item (F3.4/F3.5).
                "continuable_with_memory": bool(
                    resume_enabled and last_status == "completed"
                ),
            })

    return jsonify({"conversations": items, "resume_enabled": resume_enabled})


def _launch_turn(
    *,
    conversation_id: int,
    project: str | None,
    message: str,
    runtime: str,
    model_override: str | None,
    effort_override: str | None,
):
    """Lanza un turno como ejecución nueva. Retorna (execution_id, None) o
    (None, respuesta_de_error_flask)."""
    import agent_runner
    context_blocks = [{
        "id": "devops-chat",
        "kind": "raw-conversation",
        "title": "Mensaje del operador (chat DevOps)",
        "content": message,
        "source": {"type": "devops_panel"},
    }]
    try:
        execution_id = agent_runner.run_agent(
            agent_type="devops",
            ticket_id=conversation_id,
            context_blocks=context_blocks,
            user=_current_user(),
            runtime=runtime,
            vscode_agent_filename="DevOpsAgent.agent.md",
            project_name=project,
            use_few_shot=False,
            use_anti_patterns=False,
            model_override=model_override,
            effort_override=effort_override,
            work_item_type="Task",
        )
    except agent_runner.UnknownAgentError:
        return None, (jsonify({"ok": False, "error": "devops_agent_not_registered"}), 500)
    except Exception as exc:  # noqa: BLE001 — patrón run_brief (api/agents.py:782-792)
        return None, (jsonify({
            "ok": False, "error": "agent_launch_failed", "message": str(exc),
        }), 502)

    # Trazabilidad best-effort (patrón plan 53, api/agents.py:801-812): sellar
    # devops_chat. C4 (v2): la IDENTIDAD de la conversación NO depende de este sello.
    # Hay carrera con el thread de run_agent, que también hace read-modify-write del
    # metadata (agent_runner.py:173,274,348,723,883) ⇒ lost-update posible. La
    # identidad race-free es (ticket.ado_id == -2) AND (execution.agent_type ==
    # "devops"); devops_chat es solo un flag informativo (nunca criterio binario duro).
    try:
        from db import session_scope
        from models import AgentExecution
        with session_scope() as s:
            ex = s.get(AgentExecution, execution_id)
            if ex is not None:
                md = dict(ex.metadata_dict or {})
                md["devops_chat"] = True
                md["devops_conversation_ticket_id"] = conversation_id
                ex.metadata_dict = md
    except Exception:
        pass  # trazabilidad opcional, nunca bloquea el turno
    return execution_id, None
```
Notas de implementación obligatorias:
- Si `models.Ticket` no tiene atributo `created_at`, usar el campo de fecha que tenga
  (mirar la clase en `backend/models.py`); si no hay ninguno, devolver `None`
  (el campo `started_at` del item es informativo).
- `clamp_model` se llama SIN `allow_opus` (default False) — verificar la firma en
  `services/llm_router.py` antes de llamar; si la firma fuera
  `clamp_model(model, *, allow_opus=False)`, la llamada de arriba ya es correcta.

**Registro:** en `Stacky Agents/backend/api/__init__.py`, junto al registro del
blueprint del 87:
```python
from .devops_agent import bp as devops_agent_bp  # Plan 90 — agente DevOps
...
api_bp.register_blueprint(devops_agent_bp)  # Plan 90 — /api/devops/agent/...
```

**Health aditivo (para la UI):** editar `Stacky Agents/backend/api/devops.py`
(creado por 87 F1 o F0.a) — agregar al JSON de `devops_health_route`:
```python
"agent_enabled": bool(getattr(cfg, "STACKY_DEVOPS_AGENT_ENABLED", False)),
```
(aditivo: el 87 F4 declara explícitamente que las keys nuevas del health viajan de
forma aditiva).

**Tests PRIMERO** — archivo nuevo `Stacky Agents/backend/tests/test_plan90_devops_agent_endpoints.py`
(fixtures `app_flag_on`/`app_flag_off` con el patrón de
`tests/test_plan73_generator_endpoint.py:8-31`, seteando `STACKY_DEVOPS_AGENT_ENABLED`
y también `STACKY_DEVOPS_PANEL_ENABLED` en el fixture ON; mocks: parchear
`agent_runner.run_agent` EN EL MÓDULO ORIGEN — los imports del blueprint son lazy,
patrón plan 28):
- `test_f2_flag_off_404`: los 3 endpoints devuelven 404 con flag OFF.
- `test_f2_start_requires_project_and_message`: body vacío → 400.
- `test_f2_start_rejects_copilot`: `runtime="github_copilot"` → 400 con
  `error == "devops_chat_requires_cli_runtime"`.
- `test_f2_start_happy_path`: monkeypatch `agent_runner.run_agent` → retorna 123;
  POST válido → 202, `execution_id == 123`, `conversation_id` es int; el mock
  recibió `agent_type="devops"`, `vscode_agent_filename="DevOpsAgent.agent.md"`,
  `work_item_type="Task"`, `use_few_shot=False`; en DB existe el Ticket con
  `ado_id == -2` y ese id.
- `test_f2_start_two_conversations_two_tickets` (**guardia de C1**): 2 POSTs al MISMO
  proyecto → 2 tickets ancla con `ado_id == -2` e `id` DISTINTO, ambos conviviendo en
  la DB real del fixture (si volviera `external_id=-2` fijo, el 2º INSERT tiraría
  `IntegrityError` del UNIQUE `ux_tickets_stacky_tracker_external` y este test se
  pondría rojo). Verificar además que el fixture usa una DB real (no mock del
  `session_scope`) para que la constraint se ejerza de verdad.
- `test_f2_start_clamps_model`: monkeypatch `services.llm_router.clamp_model` para
  espiar; POST con `model="opus-4.8"` → `clamp_model` fue llamado SIN
  `allow_opus=True` y `run_agent` recibió el valor clampeado.
- `test_f2_message_live_stdin`: crear conversación (run_agent mockeado) + fila
  `AgentExecution` status="running" con `metadata {"runtime": "claude_code_cli"}`;
  monkeypatch `services.claude_code_cli_runner.send_input` → `{"ok": True, "mode":
  "stdin", "execution_id": X}`; POST message → 200 `mode == "stdin"` y run_agent NO
  fue llamado de nuevo.
- `test_f2_message_dead_run_launches_new`: ídem pero `send_input` lanza
  `RuntimeError` → run_agent SÍ fue llamado con `ticket_id == conversation_id` →
  202 `mode == "new_run"`.
- `test_f2_message_completed_launches_new`: última ejecución status="completed"
  (sin proceso vivo) → run_agent llamado directo, sin intentar send_input.
- `test_f2_message_not_found_404`: conversation_id inexistente → 404.
- `test_f2_list_returns_conversation_and_resume_flag`: tras crear una conversación,
  GET lista la incluye con `last_execution_id`; la respuesta tiene key
  `resume_enabled` (bool).
- `test_f2_list_item_continuable_flag` (**C3 / [ADICIÓN ARQUITECTO]**): con
  `CLAUDE_CODE_CLI_RESUME_ENABLED=false`, todo item trae
  `continuable_with_memory == False`; con resume ON + una última ejecución
  `status="completed"`, el item trae `continuable_with_memory == True`; con resume ON
  pero última ejecución `status="failed"`, vuelve a `False` (la señal no miente ante un
  turno que no terminó OK).
- `test_f2_route_registered`: centinela — `create_app()` y
  `"/api/devops/agent/conversations"` está en `[r.rule for r in app.url_map.iter_rules()]`
  (patrón plan 74).
- `test_f2_health_has_agent_enabled`: GET `/api/devops/health` incluye
  `agent_enabled` (bool).

**Registro ratchet:** agregar el archivo a ambos scripts.

**Criterio binario:** 14 tests verdes (incluye el guard de C1 y el de C3);
`tests/test_plan87_devops_endpoints.py` (si existe por F0.a/87) sigue verde.
**Flag:** `STACKY_DEVOPS_AGENT_ENABLED` (guard 404 per-request en los 3 endpoints).
**Runtimes:** claude_code_cli y codex_cli soportados; github_copilot rechazado con
detail que apunta al flujo VS Code nativo (degradación controlada, guardarraíl 6).
**Trabajo del operador:** ninguno.

### F3 — Frontend: sección "Agente DevOps" en el panel + wiring al dock de chat existente

**Objetivo:** UX mínima sin fricción: 1 textarea + 1 botón para abrir conversación;
el chat en sí es el `CodexConsoleDock` EXISTENTE (cero UI de chat nueva); lista de
conversaciones para retomar con 1 click.

**Archivo a editar:** `Stacky Agents/frontend/src/api/endpoints.ts` — agregar (junto
al namespace `DevOps` del 87; helper real `api.get`/`api.post` con path `/api/...`):
```ts
export const DevOpsAgentApi = {
  start: (body: { project: string; message: string; runtime?: "claude_code_cli" | "codex_cli"; model?: string; effort?: string }) =>
    api.post<{ ok: boolean; conversation_id: number; execution_id: number; runtime: string }>(
      "/api/devops/agent/conversations", body),
  message: (conversationId: number, message: string) =>
    api.post<{ ok: boolean; mode: "stdin" | "resume" | "new_run"; execution_id: number }>(
      `/api/devops/agent/conversations/${conversationId}/message`, { message }),
  list: (project?: string) =>
    api.get<{ conversations: DevOpsConversationItem[]; resume_enabled: boolean }>(
      `/api/devops/agent/conversations${project ? `?project=${encodeURIComponent(project)}` : ""}`),
};
export interface DevOpsConversationItem {
  conversation_id: number;
  title: string;
  project: string | null;
  last_execution_id: number | null;
  last_status: string | null;
  last_runtime: string | null;
  started_at: string | null;
  continuable_with_memory: boolean; // C3 (v2): señal honesta por-conversación
}
```

**Archivo NUEVO:** `Stacky Agents/frontend/src/components/devops/DevOpsAgentSection.tsx`
— componente de la sección (recibe `ctx: DevOpsSectionContext` del 87 F4). Contenido
determinista:
1. **[C6 v3 — contrato de extensión 87 F4/§3.12]** El gate de flag-off NO lo hace
   este componente: el SHELL (`DevOpsPage.tsx`) ya decide, ANTES de montar
   `DevOpsAgentSection`, si `ctx.health.agent_enabled !== true` — en ese caso
   renderiza `<FlagGateBanner .../>` en lugar de esta sección (contrato F4 del 87 v3,
   líneas 662-698; el propio 87 v3 §3.12 ya anticipa esta entrada exacta). Por lo
   tanto `DevOpsAgentSection.tsx` **asume que ya fue montado con la flag ON** y NO
   debe contener ningún string hand-rolled de aviso de flag-off (nada de "El agente
   DevOps está apagado..."). Defensa opcional trivial permitida: un early-return
   silencioso si por algún motivo `ctx.health.agent_enabled !== true` (p. ej.
   `if (!ctx.health.agent_enabled) return null;`), pero SIN duplicar mensaje — el
   shell es la ÚNICA fuente del texto de flag-off. (Tipo: ampliar `DevOpsHealth` del
   87 con `agent_enabled?: boolean` — key opcional, contrato aditivo declarado por el
   87 F4.)
2. Formulario "Nueva conversación": select de proyecto (opciones de
   `Projects.list()`, `endpoints.ts:1581-1582`, preseleccionando
   `Projects.getActive()`, `:1583`), select de runtime con 2 opciones
   (`claude_code_cli` etiquetada "Claude Code (recomendado)" default, `codex_cli`
   etiquetada "Codex"), textarea del primer mensaje, botón "Iniciar conversación"
   deshabilitado si proyecto o mensaje vacíos.
3. `onSubmit` → `DevOpsAgentApi.start(...)` → al resolver:
   `useWorkbench.getState().setCodexConsoleExecution(res.execution_id)` — abre el
   dock de chat EXISTENTE (`CodexConsoleDock.tsx:50-53`; usar el hook `useWorkbench`
   igual que lo consume ese componente, no `getState()` si el store expone el setter
   como hook — copiar la forma de consumo de `CodexConsoleDock.tsx:52`). Refetch de
   la lista.
4. Lista "Conversaciones" (`useQuery` sobre `DevOpsAgentApi.list(project)`): por item,
   título + estado + 2 acciones:
   - "Abrir consola": `setCodexConsoleExecution(item.last_execution_id)` (solo si no
     es null) — reengancha el dock al run (vivo o terminado, el dock ya maneja ambos).
   - "Continuar": visible solo si `last_status !== "running"`; abre un textarea
     inline + botón enviar → `DevOpsAgentApi.message(id, texto)` → al resolver,
     `setCodexConsoleExecution(res.execution_id)`. **C3 (v2):** si
     `item.continuable_with_memory === false`, mostrar junto al botón el caption
     literal `Continuará sin memoria del hilo (resume off o el último turno no terminó OK).`
   (Si `last_status === "running"`, la respuesta se escribe DENTRO del dock, que ya
   tiene input por stdin — no duplicar canal en la sección.)
5. Aviso de continuidad GLOBAL (complementa el per-item de arriba): si
   `list.resume_enabled === false`, mostrar el texto:
   `Aviso: sin "Resume de sesión (claude)" activo (Configuración → Arnés, categoría Claude Code CLI), al continuar una conversación terminada el agente arranca sin memoria del hilo.`
   — texto plano SIEMPRE. **[C6 v3]** Esto NO usa `FlagGateBanner` — no porque el
   componente "no exista aún" (ya existe: `FlagGateBanner` es del 87 F4, exigido por
   el propio F0.a de este plan), sino porque **no aplica**: este es un aviso
   operacional sobre continuidad de sesión (`resume_enabled`), no un gate de
   flag-off de sección — `FlagGateBanner` solo tiene sentido para el caso
   `healthKey`/sección-completa-apagada (punto 1), que es un caso distinto. La señal
   PRECISA es la per-item `continuable_with_memory` (C3): el aviso global cubre
   además el caso "el flag está ON pero para otro proyecto".
6. Todo `await` de este componente va en try/catch que setea un área de error visible
   (`No se pudo <acción>: <mensaje>`) — patrón C16 del 87.

**Archivo a editar:** `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` — agregar la
entrada al registro (contrato del 87 F4 §3.12, **exactamente** la firma que el 87 v3
ya anticipa en su propio checklist, líneas 935-938; sin refactor del shell):
```ts
{
  id: "agente",
  label: "Agente DevOps",
  healthKey: "agent_enabled",
  gateFlagKey: "STACKY_DEVOPS_AGENT_ENABLED",
  gateMessage: "El agente DevOps interactivo necesita su flag (categoría DevOps).",
  render: (ctx) => <DevOpsAgentSection ctx={ctx} />,
},
```
y ampliar `DevOpsHealth` con `agent_enabled?: boolean`. **[C6 v3]** Con `healthKey`
declarado, el shell renderiza `FlagGateBanner` automáticamente cuando
`ctx.health.agent_enabled !== true` — CERO cambios adicionales en `DevOpsPage.tsx`
más allá de esta entrada (tal como exige el 87 v3 §3.12).

**Verificación de que el dock cubre el chat:** `CodexConsoleDock` ya renderiza líneas
del operador vs agente (`:14-23`), input con envío por
`Executions.sendCodexInput` (`:68-71` → `POST /api/executions/<id>/input`), fases "está
escribiendo…" (`:30-47`) y telemetría. NO se modifica ese componente en este plan.

**Tests:** no hay runner de componentes (sin `@testing-library/react`, gap
preexistente). Gate = `npx tsc --noEmit` 0 errores en `Stacky Agents/frontend` +
criterios por grep de abajo.

**Criterio binario:** (a) `tsc` 0 errores; (b) grep en `DevOpsAgentSection.tsx`
encuentra `setCodexConsoleExecution` (el chat reusa el dock, no hay UI de chat
paralela); (c) grep en `DevOpsPage.tsx` encuentra `healthKey: "agent_enabled"` Y
`gateFlagKey: "STACKY_DEVOPS_AGENT_ENABLED"` en la entrada `id: "agente"` (**C6 v3**:
contrato declarativo del 87 F4/§3.12, reemplaza al viejo criterio (c) que solo
buscaba el `id`); (d) grep en `DevOpsAgentSection.tsx` NO encuentra `fetch(` (todo
pasa por `endpoints.ts`); (e) el aviso GLOBAL de continuidad (antes punto 5, ahora
punto 5 del listado de arriba) existe como string literal en el componente — este
criterio se mantiene INTACTO porque ese aviso es operacional (resume), no un gate de
flag; (f) grep en `DevOpsAgentSection.tsx` encuentra `continuable_with_memory` (C3: la
señal honesta se consume, no se ignora); **(g) [ADICIÓN ARQUITECTO v3 / C6] grep en
`DevOpsAgentSection.tsx` NO encuentra el literal `está apagado`** (el aviso de
flag-off es responsabilidad exclusiva del shell vía `FlagGateBanner`; este criterio
es la guardia anti-regresión que impide que el hand-roll de v2 vuelva a aparecer en
una futura edición del componente).
**Flag:** `STACKY_DEVOPS_AGENT_ENABLED` vía `ctx.health.agent_enabled` (sección
apagada = solo aviso).
**Runtimes:** selector claude/codex; copilot ausente del selector (el backend además
lo rechaza — doble defensa).
**Trabajo del operador:** opt-in — activar 2 flags por UI (panel 87 + agente 90);
recomendado además "Resume de sesión (claude)" para continuidad entre sesiones
(también por UI; sin ella el sistema degrada avisando, nunca en silencio).

### F4 — Verificación integral, ratchet y no-regresión

**Objetivo:** cerrar el plan con verificación binaria de punta a punta y cero
regresiones.

**Pasos:**
1. Ratchet: verificar que `tests/test_plan90_devops_agent_flag.py`,
   `tests/test_plan90_devops_agent_registry.py` y
   `tests/test_plan90_devops_agent_endpoints.py` están en `HARNESS_TEST_FILES` de
   `scripts/run_harness_tests.sh` Y `scripts/run_harness_tests.ps1`; correr el
   meta-test del plan 49 F4 (vive en la suite de ratchet — correr el archivo que lo
   contiene, `tests/test_harness_ratchet.py` o el nombre real registrado; localizarlo
   con grep de `HARNESS_TEST_FILES` en `tests/`).
2. No-regresión dirigida (por archivo, venv del repo):
   - `tests/test_harness_flags.py` y `tests/test_flag_wiring.py` (registro de flags).
   - `tests/test_plan73_generator_endpoint.py` (contrato del generador intacto).
   - el archivo de tests de `api/executions` que cubra `POST /<id>/input` si existe
     (localizar con grep `"/input"` en `tests/`; si no existe, omitir — este plan no
     tocó ese endpoint).
3. Frontend: `npx tsc --noEmit` → 0 errores.
4. Checklist binario final (todo verificable por comando/grep):
   - [ ] `STACKY_DEVOPS_AGENT_ENABLED=false` (default) ⇒ `GET /api/devops/agent/conversations` → 404 (test F2).
   - [ ] Flag ON ⇒ conversación creada = 1 Ticket `ado_id=-2` (SIN `external_id`, C1) + 1 ejecución `agent_type="devops"` (identidad race-free, C4; `metadata.devops_chat` es best-effort y NO se usa como criterio duro) (tests F2).
   - [ ] 2 conversaciones del MISMO proyecto conviven (guard C1: sin `IntegrityError` del UNIQUE) (test F2).
   - [ ] Turno sobre run vivo usa `send_input` (mode `stdin`/`resume`), turno sobre run muerto lanza run nuevo sobre el MISMO ticket (tests F2).
   - [ ] `agents.get("devops")` registrado; `.agent.md` contiene `R-HITL` y `CONFIRMO` (tests F1).
   - [ ] `DEVOPS_SECTIONS` contiene la entrada `agente` con `healthKey:"agent_enabled"` y `gateFlagKey:"STACKY_DEVOPS_AGENT_ENABLED"` (grep F3, **C6 v3** — contrato 87 F4/§3.12); `DevOpsAgentSection.tsx` NO contiene el literal `está apagado` (grep negativo F3-g).
   - [ ] Ningún archivo de este plan modifica `claude_code_cli_runner.py`,
     `codex_cli_runner.py`, `api/executions.py` ni `CodexConsoleDock.tsx`
     (verificable por `git diff --name-only`).

**Criterio binario:** los 3 archivos de test del plan verdes por archivo + meta-test
ratchet verde + `tsc` 0 errores + checklist completo.
**Flag:** n/a.
**Runtimes:** n/a.
**Trabajo del operador:** ninguno.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Tickets ancla `ado_id=-2` aparecen en listados/sweeps pensados para tickets reales | Precedente directo: Brief Pool `ado_id=-1` convive desde el plan 38 sin tratamiento especial. Si algún listado los muestra, es cosmético (título `[Stacky] DevOps Chat — …` autoexplicativo). NO agregar filtros globales en este plan (scope creep). |
| Continuación "durmiente" sin flags de resume ⇒ el agente pierde el hilo | Nunca silencioso: la señal PRECISA `continuable_with_memory` (C3, = resume ON **AND** último run `completed`) viaja por item en el GET y la UI avisa por conversación (F3.4) + aviso global (F3.5). Cubre el caso sutil que v1 ignoraba: un último turno `failed`/zombie pierde memoria aunque el flag esté ON (`harness/resume.py:96` solo resume `completed`). Flags editables por UI (`harness_flags.py:275-285`). |
| El agente ejecuta algo mutante sin permiso (producción) | Triple capa: (1) R-HITL con `CONFIRMO` literal en `.agent.md` y en `system_prompt()`; (2) el operador ve el stream EN VIVO en el dock y puede cancelar (infra existente); (3) RunawayGuard H5 corta presupuesto/turnos desbocados. Honestidad: `--dangerously-skip-permissions` está siempre ON en el runner (decisión previa del repo) — la contención es prompt + supervisión humana + guard, y así se declara. |
| Timeout de 1800s mata sesiones largas a mitad de tarea | Es el diseño anti-zombie (plan 37). La conversación NO se pierde: el turno siguiente relanza con `--resume`. No se toca el timeout. |
| `run_agent` con `agent_type="devops"` dispara flujos pensados para business (autopublish, gates de épica) | **Doble** inertud VERIFICADA: el gate exige `_one_shot AND agent_type=="business"` (`claude_code_cli_runner.py:1302`) y `_one_shot == (ado_id == -1)` (`:858`) — con `ado_id=-2` FALLAN AMBAS condiciones; `work_item_type="Task"` como tercera defensa; test proxy F1. Bonus: el mismo `_one_shot=False` mantiene el **stdin abierto** para multi-turno (el cierre solo ocurre en one-shot, `:1141-1149`). |
| Reinicio del backend a mitad de conversación ⇒ `_PROCESSES` en memoria se pierde pero la fila DB puede seguir `status="running"` | No rompe: el camino vivo hace `send_input`, que ante `proc is None` levanta `RuntimeError` (`claude_code_cli_runner.py:311-314`), el `try/except` de `send_message` cae al camino durmiente (nuevo run + resume). Degradación transparente, sin código nuevo. |
| El 87 cambia al implementarse y rompe el contrato de sección | El contrato `render(ctx)` + health aditivo es EXPLÍCITO en el 87 v3 (C4/C9 y F4); este plan solo consume ese contrato y el centinela `test_f2_health_has_agent_enabled` detecta drift del health. |
| Dos turnos simultáneos sobre la misma conversación (doble click) | El camino vivo serializa por lock de stdin (`claude_code_cli_runner.py:72`; codex `_RESUME_LOCKS:239-241` rechaza input concurrente); el camino durmiente crea runs distintos — el guard de duplicados/concurrencia existente del plan 22 V0 aplica. No se agrega mecanismo nuevo. |

## 6. Fuera de scope (explícito)

- Chat in-panel para `github_copilot` (queda el flujo VS Code nativo; rechazo 400
  explícito).
- UI de chat nueva (se reusa `CodexConsoleDock`; un "chat embebido" en la sección es
  evolución futura).
- Renombrar/generalizar `sendCodexInput` o `CodexConsoleDock` (cosmético; no se toca).
- Herramientas DevOps específicas como tools tipadas (kubectl, terraform, helm,
  docker): el agente usa el workspace y los comandos del proyecto, guiado por prompt.
- Borrado/archivado de conversaciones por UI (cap natural: listado limitado a 50,
  orden descendente; un plan futuro puede agregar archivado).
- Multi-conversación simultánea sobre el MISMO ticket, presupuestos por conversación,
  y métricas agregadas en `harness_health`.
- Cambios en `_maybe_autopublish_epic`, timeouts, permisos del CLI o cualquier
  contrato de runners.

## 7. Glosario

- **Runtime CLI:** ejecutor headless de agentes (`claude_code_cli` = binario
  `claude`; `codex_cli` = binario `codex`), a diferencia de `github_copilot` (VS Code
  interactivo).
- **Ticket ancla / pool ticket:** fila local de `Ticket` con `ado_id` negativo que NO
  existe en el tracker; solo ancla ejecuciones (`ado_id=-1` briefs; `ado_id=-2`
  conversaciones DevOps de este plan).
- **stdin stream-json:** canal por el que el runner claude escribe mensajes de
  usuario al proceso vivo (`_user_message_line`), manteniendo la conversación en el
  mismo proceso.
- **`--resume <session_id>`:** re-arranque del CLI retomando una sesión previa (el
  session_id queda en `metadata` del run anterior); en codex es
  `codex exec resume <session>`.
- **Dock / `CodexConsoleDock`:** consola flotante existente de la UI con stream en
  vivo + input del operador; sirve para ambos runtimes CLI.
- **HITL:** human-in-the-loop; acá materializado como la regla `CONFIRMO`.
- **FlagSpec / `FLAG_REGISTRY`:** registro declarativo de flags del arnés
  (`services/harness_flags.py`) que alimenta la UI de Configuración → Arnés.
- **Ratchet:** meta-test (plan 49 F4) que exige registrar todo archivo de test nuevo
  en los scripts de la suite del arnés.

## 8. Orden de implementación

1. F0.a — pre-flight dependencia 87 (bootstrap F0/F1/F4 del 87 SOLO si falta).
2. F0.b — flag `STACKY_DEVOPS_AGENT_ENABLED` (tests primero).
3. F1 — `DevOpsAgent` registry + `.agent.md` (tests primero).
4. F2 — blueprint conversaciones + health aditivo (tests primero).
5. F3 — endpoints.ts + `DevOpsAgentSection` + registro en `DEVOPS_SECTIONS` (tsc).
6. F4 — ratchet, no-regresión, checklist binario.

## 9. Definición de Hecho (DoD)

- Los 3 archivos de test backend del plan pasan por archivo con
  `.venv/Scripts/python.exe -m pytest tests/<archivo> -q` desde
  `Stacky Agents/backend`, y están registrados en ambos scripts de ratchet
  (meta-test verde).
- `npx tsc --noEmit` da 0 errores en `Stacky Agents/frontend`.
- Con TODAS las flags nuevas en default (OFF): comportamiento byte-idéntico
  (endpoints 404, sección con aviso, cero cambios en flujos existentes).
- Con flags ON: el operador puede — solo con la UI — abrir una conversación DevOps,
  ver al agente trabajar en el dock, responderle ≥ 2 turnos, cerrar, y CONTINUAR la
  conversación después con 1 click; **dos conversaciones del mismo proyecto conviven**
  (C1) y la UI le dice ANTES de continuar si el hilo tendrá memoria
  (`continuable_with_memory`, C3).
- Identidad de conversación race-free (C4): `ticket.ado_id == -2` (SIN `external_id`)
  AND `execution.agent_type == "devops"`; `metadata.devops_chat` NO es criterio duro.
- `git diff --name-only` del plan NO incluye `claude_code_cli_runner.py`,
  `codex_cli_runner.py`, `api/executions.py` ni `CodexConsoleDock.tsx`.
- Ningún FlagSpec nuevo tiene `default=` ni `reserved=`; `harness_defaults.env`
  contiene la línea nueva; `PlainHelp` presente.
