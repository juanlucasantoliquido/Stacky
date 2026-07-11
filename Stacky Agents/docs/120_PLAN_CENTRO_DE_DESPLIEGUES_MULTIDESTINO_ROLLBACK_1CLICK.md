# Plan 120 — Centro de Despliegues: deploy multi-destino en 2 clicks, rollback instantáneo, verificación post-deploy y DORA local

> **Estado:** CRITICADO v2 (APROBADO-CON-CAMBIOS) — 2026-07-10
> **Autor:** StackyArchitectaUltraEficientCode · **Juez v1→v2:** criticar-y-mejorar-plan (inline)
> **Pipeline:** este documento pasó `proponer` y `criticar-y-mejorar-plan` (este estado). Sigue `implementar-plan-stacky` → `supervisar-implementaciones-planes`.
> **Pedido textual del operador:** "Quiero que me digas cómo mejorarías Stacky Agents para hacer MUCHO
> más fácil la creación de pipelines y despliegues. Debe ser algo extremadamente fácil y efectivo por
> sobre todo. Ejemplo: una parte que sea 'Despliegue' y te permita desplegar a cada servidor y también
> local, todo en una vista muy organizada y fácil de utilizar, con muy pocos clicks. Investigá cómo las
> big tech hacen sus despliegues y sumalo, y modificá mi herramienta Stacky Agents para que sea mejor
> aún que las big techs."
> **Depende de:** SOLO sustrato YA implementado — registro de servidores + keyring (plan 91,
> `services/server_registry.py`), riel WinRM auditado (planes 105/108, `services/remote_exec.py`),
> detección de stack (plan 97, `services/pipeline_stack_detector.py:19`), modelo local costo-cero
> (planes 106/117, patrón `services/local_insights.py`), doctor de conexiones (plan 116, parcial:
> `check_winrm` + remediación ya viven en `remote_exec.py:125-247`). NADA pendiente bloquea este plan.

---

## Changelog v1 → v2 (crítica adversarial 2026-07-10 — 12 hallazgos: 0 BLOQUEANTES / 7 IMPORTANTES / 5 MENORES)

**VEREDICTO: APROBADO-CON-CAMBIOS.** Criterios binarios: cero bloqueantes (no saca al humano del lazo,
no rompe ningún runtime, no agrega trabajo manual, flags con default seguro); ≥1 IMPORTANTE (7 defectos
de diseño reales, todos con fix aplicado in place en esta v2). Toda la evidencia `archivo:línea` de los
hallazgos fue verificada por LECTURA del código al 2026-07-10.

| C# | Sev. | Hallazgo (v1) | Fix aplicado (v2) |
|---|---|---|---|
| C1 | IMPORTANTE | `cmd /c rmdir current` incondicional rompía el PRIMER deploy (el junction aún no existe ⇒ exit≠0 ⇒ `failed`); `test_switch_commands_exactos` congelaba el defecto | `build_switch_commands` emite `cmd /c if exist ... rmdir ...` (§5.2, F1) + test `test_switch_commands_primer_deploy` + bullet en DoD |
| C2 | IMPORTANTE | Paso `prune` no implementable: `build_deploy_plan` pre-genera comandos, pero `prune_versions` (pura) necesita el listado REAL de `releases\` del destino, desconocido en plan-time | `prune` viaja con `command: None` y el executor lo despacha por nombre en 3 sub-acciones (listar read-only → `prune_versions` pura → borrar) (F4); fallo de housekeeping NO degrada `success` (§1 KPI refinado) |
| C3 | IMPORTANTE | Ruta del zip remoto sin convenir: `transfer`/`unpack` exigían INFERIR una convención (prohibido para modelos menores) | Convención inmutable `<install_path>\incoming\<version_id>.zip`, `ensure_dirs` crea `releases` + `incoming`, comando `Expand-Archive` exacto y paso nuevo `cleanup` (§5.2, F1, F4) |
| C4 | IMPORTANTE | Regla "sin llaves `{}`" sin base declarada y contradictoria con `write_marker` (el JSON del marker TIENE llaves) | Regla delimitada con evidencia: `is_read_only_command` rechaza llaves SOLO en read-only (`remote_exec.py:51-55`, guard anti script-block); los comandos write PUEDEN llevarlas; `build_marker_command` definido EXACTO (§5.2, F1) + `test_drift_command_es_read_only` (F5) |
| C5 | IMPORTANTE | F4 contradictorio: "thread por destino" vs "SECUENCIAL entre destinos"; semántica del 409 parcial multi-destino sin definir | UN solo thread por ORDEN que itera las olas en el orden recibido; locks upfront; 409 SOLO si TODOS los destinos están ocupados, mezcla ⇒ 200 con detalle por destino (F4, F5, §5.4) |
| C6 | IMPORTANTE | `update_ledger_entry` (leer-mapear-reescribir el JSONL) desde threads de órdenes concurrentes ⇒ pérdida de líneas | El `threading.Lock` de módulo de `deploy_store` cubre TAMBIÉN append/update/read del ledger + `test_update_concurrente_no_pierde_entradas` (F3) |
| C7 | IMPORTANTE | F8 asumía un mecanismo de navegación que NO existe: `activeId` es `useState` interno (`DevOpsPage.tsx:163`), el ctx no expone callback, no hay routing por hash; "elegir el mecanismo YA disponible" = frase vaga prohibida | Campo OPCIONAL `setActiveSection?: (id: string) => void` en `DevOpsSectionContext` + 2 líneas en `DevOpsPage` (precedente aditivo idéntico a `selectedServer` del plan 91, `DevOpsPage.tsx:46-48`), con fallback explícito si falta (F8) |
| C8 | MENOR | `STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_S` (v1) rompía la convención `_TIMEOUT_SEC` de la casa (plan 110) | Renombrada a `STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC` en todo el doc (F0) |
| C9 | MENOR | Smoke http impreciso ("stdout contiene un StatusCode 200-399") e `Invoke-WebRequest` LANZA excepción en ≥400 (nunca emitiría el código) | Comando exacto con try/catch (permitido: corre en write) + helper puro `parse_smoke_http_stdout` (F1, F4) |
| C10 | MENOR | Backend reiniciado a mitad de deploy ⇒ entry `running` zombi eterna (trampa conocida de la casa: runs pegados en "running") | Resuelto por **[ADICIÓN ARQUITECTO A1]** `derive_effective_status` (F1, F5, F7, R10) |
| C11 | MENOR | `DELETE /apps/<id>` sin guard con deploy en curso | 409 `deploy_in_progress` si hay lock activo de la app + `test_delete_app_409_con_run_activo` (F5) |
| C12 | MENOR | El fix F2 usaba la variable `server` sin decir de dónde sale; el fake con orden viejo no estaba localizado | Verificado y anotado: `server = get_server(alias)` YA existe en scope (`remote_exec.py:300`); el fake viejo `("user","pass","host")` está en `test_plan105_remote_exec_service.py:119,153,192` (F2) |

**[ADICIÓN ARQUITECTO] A1 — Runs zombis detectados en frío (cierra C10):** helper puro
`derive_effective_status(entry, now_utc, stale_after_s=3600)` — un `running` más viejo que el umbral se
DERIVA como `stale` en `/overview`, `/runs/<id>` y `/history` (sin demonio, sin mutar el ledger) + badge
gris "obsoleto" en la tarjeta (F1, F5, F7). Cero trabajo del operador, determinista, idéntico en los 3
runtimes.
**[ADICIÓN ARQUITECTO] A2 — Preflight de espacio en disco del destino:** `/plan` sonda el espacio libre
(remoto: `Get-PSDrive` read-only brace-free; local: `shutil.disk_usage`) y agrega warning si
libre < 2× artefacto — helper puro `check_disk_headroom(free_bytes, artifact_bytes)` (F1, F5). Warning
informativo en el semáforo, JAMÁS bloquea: decide el operador (HITL).

---

## 0. Relación con los planes 98-103, 116 y 119 (obligatoria, verificada doc por doc)

| Plan | Estado | Relación | Por qué |
|---|---|---|---|
| 98 bootstrap único + PATCH client-profile | PROPUESTO | **COMPLEMENTA, cero intersección** | 98 optimiza el transporte del client-profile. Este plan NO agrega keys al client-profile: sus datos son operativos y viven en `data_dir()` (`deploy_apps.json`, `deploy_ledger.jsonl`), y la única preferencia de UI (app seleccionada) usa `localStorage` (patrón `stacky.devops.selectedServer`, `DevOpsPage.tsx:174-181`). Si 98 aterriza, su `/bootstrap` no cambia. |
| 99 preview SWR | PROPUESTO | **ORTOGONAL** | Archivos disjuntos (99 toca `PipelineYamlPreview.tsx`/`PipelineBuilderSection.tsx` zona preview). |
| 100 suite DevOps en un click | PROPUESTO | **COMPLEMENTA (beneficiario automático)** | 100 arma el paquete leyendo la categoría `devops` (`_CATEGORY_KEYS["devops"]`). Las flags nuevas de este plan entran en esa misma tupla (F0) ⇒ cuando 100 se implemente, "Despliegues" se activa en el mismo click de suite sin tocar el 100. |
| 101 bootstrap de servidor desde credenciales | PROPUESTO | **COMPLEMENTA (secuencia natural)** | 101 deja un servidor "listo para operar" (layout + config base); este plan publica VERSIONES de apps sobre ese servidor. Además 101 propone puente UNC/SMB: si aterriza, el transporte de este plan (puerto F4) gana una impl alternativa rápida SIN refactor. No hay dependencia en ningún sentido. |
| 102 publicar en un paso (orquestador HITL) | PROPUESTO | **COMPLEMENTA (otro eslabón de la cadena)** | 102 orquesta materializar→commit→trigger del pipeline CI. Este plan cubre lo que pasa DESPUÉS del pipeline verde: llevar el artefacto a los servidores/local. El puente explícito es F8 (desplegar desde la carpeta de artefactos convenida). Cero intersección de archivos. |
| 103 monitor vivo persistente | PROPUESTO | **COMPLEMENTA, no duplica** | 103 monitorea RUNS de CI (`CIPipeline.monitor`); este plan monitorea el ESTADO DESPLEGADO por destino (versión activa, salud smoke, drift). Objetos distintos, stores distintos. |
| 116 doctor de conexiones + remediación | IMPLEMENTADO-PARCIAL | **CONSUME (no reimplementa)** | El preflight de deploy reusa las sondas y la remediación YA implementadas: `remote_exec.check_winrm:200` (con `kind` + `remediation`), `server_registry.test_connectivity:221`, y el patrón de tarjetas `RemediationCard.tsx`/`ConnectionHealthStrip.tsx`. Este plan NO crea otro catálogo de fallas de conexión. |
| 119 rediseño minimalista del shell DevOps | PROPUESTO | **COMPLEMENTA (ortogonal por contrato)** | 119 es 100% presentación del shell y PRESERVA el contrato §3.12 C20 ("sumar una sección = 1 entrada en `DEVOPS_SECTIONS` + 1 componente, CERO cambios en `DevOpsPage`", `DevOpsPage.tsx:5-14`). La sección Despliegues entra por ese registro ⇒ funciona idéntica con shell v1 o v2, se implementen en cualquier orden. |
| (contexto) 89/107/108 Ambientes | IMPLEMENTADOS | **COMPLEMENTA, frontera nítida** | Ambientes crea la ESTRUCTURA de carpetas (`environment_init.py` local, `environment_remote.py` remoto). Despliegues publica VERSIONES DENTRO de un `install_path`. Este plan no toca `environment_init/remote`. |
| (contexto) 93/95/96/97/104 | IMPLEMENTADOS | **REUSA conceptos/código** | Semáforo preflight (93) como patrón visual del confirm; `detect_stack` (97) para prefill; doctores IA (104) como precedente de botón IA por sección. |

**Este plan NO absorbe ni supersede a ninguno:** agrega la capacidad que falta (deploy de apps a destinos) reusando el sustrato de todos ellos.

---

## 1. Objetivo y KPI

**Objetivo (1 párrafo).** Crear la sección **"Despliegues"** de primera clase en el panel DevOps: una
vista única con **una tarjeta por destino** (cada servidor registrado del plan 91 + el destino especial
**Local**) que muestra por aplicación la **versión desplegada, cuándo, desde qué origen, la salud
post-deploy y el drift**, y permite **desplegar en 2 clicks + confirmación HITL**, **rollback en 1 click**
a cualquier versión retenida (swap de puntero, sin recopiar), **verificación smoke automática** tras cada
switch con **rollback pre-armado** si falla, y **métricas DORA locales** calculadas del ledger propio.
Todo determinista (cero LLM en el camino feliz), con **diagnóstico IA opcional costo-cero** (modelo local
del plan 106) cuando un deploy falla. El modelo mental es el de las big tech —releases inmutables +
puntero activo (Vercel), plan declarativo visible (Spinnaker), verificación post-deploy con vuelta atrás
inmediata (AWS CodeDeploy), reglas de protección por ambiente (GitHub), detección de drift (GitOps)—
reducido a la escala mono-operador Windows/WinRM **sin agregar un solo servicio nuevo, demonio ni YAML**.

**KPI / impacto esperado (binarios).**
- **Deploy en ≤2 clicks + 1 confirmación (binario):** desde la vista, `[Desplegar]` → modal resumen →
  `[Confirmar]` ejecuta end-to-end (zip → transfer → unpack → switch → smoke → ledger). Verificable en F7.
- **Rollback en 1 click + 1 confirmación, sin transferencia (binario):** el plan de rollback NO contiene
  paso `transfer` ni `unpack` (test `test_rollback_plan_has_no_transfer`, F1) — como el Instant Rollback
  de Vercel, es re-apuntar el junction a una release retenida.
- **Cero falsos verdes de deploy (binario):** un deploy solo queda `success` si TODOS los pasos de
  ACTIVACIÓN (hasta `smoke` inclusive) devolvieron ok; cualquier paso de activación fallido ⇒ `failed`
  (o `failed_smoke`) con el paso culpable persistido en el ledger (tests F4). **C2 v2:** los pasos de
  housekeeping POST-activación (`prune`, `cleanup`) registran su fallo como `ok:false` en el entry SIN
  degradar el status — la versión ya quedó activa y verificada; el criterio sigue siendo binario.
- **Flag OFF ⇒ byte-idéntico (binario):** con `STACKY_DEPLOYMENTS_ENABLED` OFF, `/api/devops/health`
  solo gana keys aditivas `false`, todos los endpoints nuevos devuelven 404 y la UI no muestra la
  sub-tab gateada distinta a cualquier otra sección OFF (patrón `FlagGateBanner`).
- **DORA local sin telemetría externa (binario):** `GET /api/devops/deployments/metrics` calcula
  frecuencia de deploy, change failure rate y MTTR SOLO desde `deploy_ledger.jsonl` (test F1).
- **Bug latente de credenciales corregido con test contractual (binario):** ver §2.3 y F2.

---

## 2. Por qué ahora / gap verificado (evidencia en el código)

**2.1 — Todo el sustrato existe; falta el eslabón final.** La serie DevOps 87-116 construyó: registro de
servidores con credenciales en keyring (`server_registry.get_credential:205-218`), ejecución remota WinRM
auditada con modo escritura (`remote_exec.run_remote:250-368`), diagnóstico WinRM con remediación
copy-paste (`remote_exec.check_winrm:200`, plan 108/116), detección de stack (`pipeline_stack_detector.py:19`),
generador de pipelines (73/97), preflight (93), doctor de pipelines (96) y agente DevOps anclado al
servidor (108). Pero **no existe NINGÚN mecanismo para llevar una aplicación a un servidor y activarla**:
grep de `Expand-Archive|mklink|junction|releases\\` en `backend/` = 0 hits fuera de este plan. El operador
hoy termina el pipeline y despliega A MANO (RDP + copiar carpetas), sin historial, sin rollback, sin salud.

**2.2 — La vista pedida es exactamente el patrón §3.12 C20.** `DevOpsPage.tsx:5-14` declara el contrato:
sección nueva = 1 entrada en `DEVOPS_SECTIONS` (`DevOpsPage.tsx:82-154`) + 1 componente; el contexto ya
entrega `servers` y `selectedServer` (`DevOpsPage.tsx:43-49,186-191`). El costo de integración de la vista
es mínimo por diseño previo.

**2.3 — HALLAZGO (bug latente, verificado por lectura, debe fijarse en F2).**
`services/remote_exec.py:305` desempaqueta `username, password, host = get_credential(alias)` pero el
contrato REAL es `get_credential(alias) -> (username, domain, password)` (`services/server_registry.py:205-218`).
Consecuencias si se ejecutara contra un servidor real: `SR_HOST` recibiría la **contraseña** (posible fuga
en mensajes de error "cannot connect to host …"), `SR_PASS` recibiría el dominio, y con dominio vacío el
guard `if not password` (`remote_exec.py:306-307`) devolvería `no_password` con password cargada. Nunca se
manifestó porque ningún servidor registrado tiene WinRM habilitado aún (PF 10.10.1.5 solo expone 3389) y
los tests del plan 105 usan fakes. Este plan reusa ese módulo como transporte ⇒ **F2 corrige el unpack con
test contractual** que fija el orden real `(username, domain, password)`.

**2.4 — Crear pipelines sigue pidiendo demasiados pasos para el caso común.** El preset por stack (97) y
el generador (73) existen, pero no hay un camino "desde Despliegues" que sugiera el pipeline con el stack
detectado ni una convención de carpeta de artefactos para deploy. F8 cierra ese puente con un handoff
mínimo (sin tocar el generador).

---

## 3. Investigación big tech → principios adoptados (y en qué los superamos)

Fuentes revisadas 2026-07-10: [Kayenta/ACA — Netflix TechBlog](https://netflixtechblog.com/automated-canary-analysis-at-netflix-with-kayenta-3260bc7acc69),
[Managed Delivery — Spinnaker Blog](https://blog.spinnaker.io/managed-delivery-evolving-continuous-delivery-at-netflix-eb74877fb33c),
[Instant Rollback — Vercel Docs](https://vercel.com/docs/instant-rollback), [Promoting Deployments — Vercel](https://vercel.com/docs/deployments/promoting-a-deployment),
[Rollback por alarmas — AWS CodeDeploy](https://docs.aws.amazon.com/codedeploy/latest/userguide/deployment-groups-configure-advanced-options.html),
[DORA four keys — dora.dev](https://dora.dev/guides/dora-metrics/). Más conocimiento consolidado:
GitHub Actions environments + protection rules, GitOps/Argo CD (estado deseado + drift), release trains
de Meta, rollouts progresivos de Google Cloud Deploy.

| Práctica big tech | Cómo la adapta Stacky (mono-operador, Windows on-prem, WinRM) | En qué la SUPERAMOS en simplicidad |
|---|---|---|
| **Releases inmutables + puntero** (Vercel: deployments inmutables, rollback = re-asignar dominio en ~1 s) | Layout `<install_path>\releases\<version_id>` inmutable + junction `current` que apunta a la activa. Rollback = recrear el junction (segundos, sin copiar). | Cero vendor, cero cloud: funciona offline en un fileserver Windows. Sin rebuild jamás (promote de artefacto retenido). |
| **Plan declarativo visible antes de ejecutar** (Spinnaker Managed Delivery: describís el destino, la plataforma deriva los pasos) | `build_deploy_plan()` puro genera la lista EXACTA de pasos y comandos; el modal de confirmación los muestra ANTES de tocar nada (dry-run = mismo código). | Sin pipeline-as-code ni servicio Spinnaker: el plan se deriva de 4 campos de la app. El operador VE cada comando PowerShell que se va a ejecutar. |
| **Verificación post-deploy + rollback inmediato** (CodeDeploy: alarma CloudWatch ⇒ redeploy de la última versión buena) | Smoke check configurable (HTTP en el destino / comando PS / ninguno) corre EN el servidor tras el switch. Si falla ⇒ deploy `failed_smoke` y la tarjeta ofrece **Rollback ahora** pre-armado (1 click). | HITL en vez de automatismo ciego: cero rollbacks falsos por alarmas mal calibradas, y el operador decide en 1 click con el contexto a la vista. No requiere stack de métricas. |
| **Protection rules por ambiente** (GitHub environments: required reviewers para prod) | Campo `protected: true` por destino ⇒ el confirm exige tipear el id de la app (confirm_text). Sin RBAC (mono-operador sin auth, riel duro). | La regla vive en un booleano, no en configuración de organización. |
| **Estado deseado + drift** (GitOps/Argo CD: detectar divergencia entre lo declarado y lo real) | `release.json` (marker) escrito en el destino en cada switch; botón **Verificar** lo relee (read-only) y compara contra el ledger ⇒ badge `ok/drift/desconocido`. | Sin agente residente ni demonio de reconciliación: drift on-demand, cero procesos nuevos. |
| **Progressive delivery / canary / release trains** (Netflix Kayenta, Google rollouts, Meta trains) | **Olas HITL**: el operador elige el orden de destinos; despliega primero a 1 (canary humano), mira el smoke, y "promueve" al resto con el mismo artefacto (misma versión, cero rebuild). Cola secuencial: nunca 2 deploys concurrentes al mismo destino (lock + 409). | El juicio del canary es del operador con evidencia (smoke + diagnóstico IA local), sin plataforma de análisis estadístico que a esta escala (1-N servidores) no aporta. |
| **DORA four keys** (frecuencia, lead time, CFR, MTTR) | `dora_metrics()` puro sobre el ledger local: deploys 7/30d, change failure rate 30d, MTTR (fallo→siguiente éxito) por app. Chips en la vista. | Cero telemetría externa, cero SaaS: los números salen de un JSONL local y son auditables línea por línea. |
| **Diagnóstico asistido de fallas** (big tech: dashboards + oncall) | Deploy fallido ⇒ botón "Diagnóstico IA" (flag hija): el modelo LOCAL (plan 106, patrón `local_insights.py`) explica el paso fallido y propone remediación, con `HITL_RULES` (`local_insights.py:41-48`). | Costo CERO por uso, datos nunca salen de la máquina, apagable por flag. Ninguna big tech regala esto on-prem. |

---

## 4. Principios y guardarraíles (no negociables)

- **Human-in-the-loop innegociable:** TODO deploy y TODO rollback exige `confirm: true` explícito en el
  POST + modal de resumen previo; destinos `protected` exigen además `confirm_text == app_id`. NO existe
  auto-rollback ni deploy programado: el smoke fallido solo PRE-ARMA el rollback (1 click, decide el
  operador). El drift check es manual (botón), nunca un demonio.
- **Cero trabajo extra al operador:** todo opt-in con default OFF; los destinos salen SOLOS del registro
  de servidores existente + Local; una app se define con 4 campos (con prefill por `detect_stack` cuando
  la flag del 97 está ON); sin YAML, sin manifiestos, sin instalación de agentes en los servidores (usa
  el WinRM que el doctor 116/108 ya diagnostica y remedia).
- **Flags default OFF, 100% configurables desde la UI** (HarnessFlagsPanel, planes 33/86), con los
  gotchas obligatorios: FlagSpec nueva **SIN `default=`** (solo `_CURATED_DEFAULTS_ON` puede; el default
  efectivo vive en `config.py`); `requires` **profundidad 1 SIEMPRE al master del panel**
  `STACKY_DEVOPS_PANEL_ENABLED` (gotcha plan 104: NUNCA encadenar a una flag hija como
  `STACKY_DEPLOYMENTS_ENABLED`); cada arista nueva se registra en `_REQUIRES_MAP_FROZEN`
  (`backend/tests/test_harness_flags_requires.py`).
- **Mono-operador sin auth:** cero RBAC. `protected` es una salvaguarda de fricción, no un permiso.
- **Reusar, no reinventar:** transporte = `services/remote_exec.py` (ÚNICO módulo que ejecuta comandos
  remotos, por su propio docstring `remote_exec.py:1-5`); credenciales = keyring del plan 91; sondas y
  remediación = plan 116/108; IA local = camino del plan 117 (`local_insights.py`). PROHIBIDO agregar
  dependencias nuevas (no pywinrm, no smbprotocol: `Copy-Item -ToSession` nativo de PowerShell).
- **Seguridad de credenciales (riel §3.1 del plan 105):** la credencial viaja SOLO por env del proceso
  hijo `powershell.exe` (`remote_exec.py:318-323`); NUNCA en argumentos, logs, ledger ni auditoría
  (asserts defensivos existentes `remote_exec.py:89-91` se mantienen). Los hooks `pre_switch/post_switch`
  definidos por el operador se muestran ÍNTEGROS en el confirm modal y se auditan.
- **No degradar:** con flags OFF todo byte-idéntico; los endpoints nuevos van en blueprint propio;
  ningún archivo existente cambia de contrato salvo el fix del bug §2.3 (que restaura el contrato
  DOCUMENTADO de `server_registry`).
- **Paridad 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro):** este plan es
  **ortogonal al runtime por diseño** — el motor de deploy es 100% determinista (cero llamadas a agentes)
  y la única IA (F6) usa el modelo LOCAL del plan 106, idéntico bajo cualquier runtime. Fallback
  universal: sin modelo local alcanzable (`_local_llm_reachable`, `local_insights.py:225`) el botón de
  diagnóstico se deshabilita con hint y el deploy sigue 100% funcional.
- **Cero falsos verdes:** cada fase corre sus tests nombrados POR ARCHIVO con el venv real
  (`Stacky Agents/backend/.venv/Scripts/python.exe`, verificado existente) y el implementador pega el
  output real.

---

## 5. Diseño técnico

### 5.1 Modelo de datos (nuevo, en `data_dir()` — patrón `server_registry.py:39-40`)

**`data_dir()/deploy_apps.json`** — lista de aplicaciones desplegables:
```json
[{
  "id": "miapp",
  "name": "Mi App",
  "artifact": { "kind": "folder", "path": "C:\\build\\miapp\\out" },
  "targets": {
    "__local__": {
      "install_path": "D:\\apps\\miapp",
      "smoke": { "kind": "http", "url": "http://localhost:8080/health", "command": null },
      "pre_switch": null,
      "post_switch": null,
      "protected": false
    },
    "pf-server": {
      "install_path": "D:\\apps\\miapp",
      "smoke": { "kind": "none", "url": null, "command": null },
      "pre_switch": "Stop-Service miapp",
      "post_switch": "Start-Service miapp",
      "protected": true
    }
  }
}]
```
- `id`: slug `^[a-z0-9][a-z0-9_-]{0,63}$`. `artifact.kind`: `"folder" | "zip"` (allowlist).
- Key de destino: `"__local__"` (literal reservado; JAMÁS colisiona con un alias porque
  `_ALIAS_RE` exige inicio alfanumérico, `server_registry.py:30`) o un `alias` del registro del plan 91.
- `smoke.kind`: `"http" | "ps" | "none"`. `pre_switch/post_switch`: string PowerShell o `null`.

**`data_dir()/deploy_ledger.jsonl`** — append-only (patrón `append_audit`, `remote_exec.py:83-98`), una
línea por acción:
```json
{"run_id":"dr-20260710-153000-a1b2","app_id":"miapp","target":"pf-server","action":"deploy",
 "version_id":"20260710-153000-ab12cd34","prev_version_id":"20260709-101500-99ffee11",
 "status":"success","steps":[{"name":"transfer","ok":true,"ms":8123,"detail":""}],
 "source":{"kind":"folder","path":"C:\\build\\miapp\\out","sha256":"...","size_mb":41.2},
 "smoke":{"kind":"http","ok":true,"detail":"200"},"operator_confirmed":true,
 "started_at":"...","finished_at":"...","duration_ms":24551,"error":null,"insight":null}
```
`status ∈ {running, success, failed, failed_smoke}`. `action ∈ {deploy, rollback}`.

### 5.2 Layout en el DESTINO (convención inmutable, estilo Vercel/Capistrano)

```
<install_path>\
  releases\<version_id>\    ← contenido desplegado, NUNCA se modifica
  incoming\<version_id>.zip ← staging del artefacto en el destino (C3 v2; lo borra el paso cleanup)
  current                   ← junction → releases\<version_id> (lo que sirve la app)
  release.json              ← marker {version_id, app_id, deployed_at, source_sha256}
```
- `version_id = "<YYYYMMDD-HHMMSS UTC>-<sha256[:8] del zip>"` — ordenable y trazable al artefacto.
- **Switch casi-atómico sin admin:** los junctions NO requieren privilegios elevados. Comandos exactos
  (generados por `build_switch_commands`):
  `cmd /c if exist "<install_path>\current" rmdir "<install_path>\current"` (**C1 v2:** en el PRIMER
  deploy el junction todavía no existe y el `if exist` evita el exit≠0; el rmdir borra SOLO el link,
  jamás el contenido — y si `current` fuera un directorio REAL no vacío, rmdir FALLA y protege el
  contenido: error legible, nunca pisada silenciosa) y luego
  `cmd /c mklink /J "<install_path>\current" "<install_path>\releases\<version_id>"`.
- **Regla de llaves `{}` delimitada (C4 v2, con evidencia):** `is_read_only_command` rechaza `{`/`}`
  SOLO en comandos read-only (`remote_exec.py:51-55`, guard anti script-block). Por lo tanto: todo
  comando que corra con `read_only=True` (drift `Get-Content`, listado de prune, sonda de disco A2)
  DEBE ser brace-free y arrancar con verbo de lectura de la allowlist; los comandos de ESCRITURA
  (switch, marker, smoke, hooks) PUEDEN llevar llaves sin restricción.
- **Marker exacto (C4 v2):** `build_marker_command(install_path, marker: dict) -> str` genera
  `Set-Content -LiteralPath '<install_path>\release.json' -Value '<json>' -Encoding utf8`, donde
  `<json>` = `json.dumps(marker, separators=(",", ":"))`; ValueError si el JSON serializado contiene
  una comilla simple `'` (imposible con ids slug + sha hex + ISO-8601, pero se valida defensivamente).
- **Retención:** se conservan las últimas `STACKY_DEPLOYMENTS_RETAIN_RELEASES` releases (default 3);
  `prune_versions()` puro decide cuáles borrar y JAMÁS incluye la activa. **C2 v2:** el listado real de
  `releases\` se obtiene EN EJECUCIÓN (ver despacho del paso `prune` en F4): el plan pre-generado lleva
  `prune` con `command: None`.

### 5.3 Motor (separación pura/efectos, estilo de la casa)

- **`backend/services/deploy_planner.py` (NUEVO, 100% PURO, sin I/O):** `validate_app`,
  `make_version_id`, `build_deploy_plan`, `build_rollback_plan`, `build_switch_commands`,
  `build_smoke_command`, `prune_versions`, `parse_release_marker`, `compute_drift`, `dora_metrics`.
- **`backend/services/deploy_store.py` (NUEVO):** CRUD de apps + append/read del ledger + lock en
  memoria por `(app_id, target)` (409 si ya corre) — mismos patrones de tolerancia a JSON corrupto que
  `server_registry._load` (`server_registry.py:55-67`).
- **`backend/services/deploy_executor.py` (NUEVO):** ejecuta el plan paso a paso contra un
  **puerto de transporte** con DOS implementaciones: `LocalTransport` (subprocess `powershell.exe`
  local + `shutil.copy2` para el zip) y `WinRMTransport` (delega en las funciones nuevas de F2 en
  `remote_exec.py`). Corre en background thread; el progreso se persiste en el ledger y la UI pollea.
- **`backend/services/remote_exec.py` (EDITADO, F2):** fix del bug §2.3 + 2 funciones nuevas
  (`run_deploy_step`, `push_file_winrm`) + `services/deploy_transfer_invoke.ps1` (NUEVO, espejo de
  `remote_exec_invoke.ps1`: credencial vía env, `New-PSSession` + `Copy-Item -ToSession`).

### 5.4 API — `backend/api/devops_deployments.py` (NUEVO)

Blueprint `bp = Blueprint("devops_deployments", __name__, url_prefix="/devops/deployments")`, registrado
en `backend/api/__init__.py` junto a los demás (`api_bp.register_blueprint(...)`, `api/__init__.py:58+`).
Convención de la casa: rutas finales `/api/devops/deployments/...` (regla del prefix en `api/devops.py:3-4`).
Guard por flag con `abort(404)` (patrón `api/devops.py:76-77`).

| Método y ruta | Gate | Qué hace |
|---|---|---|
| `GET /overview` | master | Apps + destinos (servers del registro + `__local__`) + último estado por (app,destino) desde el ledger + métricas resumidas. |
| `POST /apps`, `PUT /apps/<id>`, `DELETE /apps/<id>` | master | CRUD validado de `deploy_apps.json`. |
| `POST /plan` | master | **Dry-run**: versión tentativa + lista de pasos/comandos por destino + preflight (artefacto existe/tamaño, `test_connectivity`, `check_winrm` con remediación 116/108). SIN efectos. |
| `POST /execute` | master + **EXECUTE** | 400 sin `confirm:true`; 403 con EXECUTE OFF; 409 SOLO si TODOS los destinos pedidos están lockeados — mezcla ⇒ 200 con detalle por destino (C5 v2); destinos `protected` exigen `confirm_text == app_id`. UN thread por orden itera las olas en secuencia (C5 v2). |
| `POST /rollback` | master + **EXECUTE** | Igual gating; plan de rollback (switch a versión retenida, sin transfer). |
| `GET /runs/<run_id>` | master | Entry del ledger (progreso vivo). |
| `GET /history` | master | Ledger filtrado por `app_id`/`target`/`limit`. |
| `POST /drift` | master | Relee `release.json` en los destinos (comando read-only `Get-Content -Raw`) y compara contra el ledger. |
| `GET /metrics` | master | DORA-lite por app. |
| `POST /diagnose` | master + **AI_DIAGNOSIS** | Diagnóstico IA local de un run fallido; persiste `insight` en el entry. |

Health (`api/devops.py:_health_payload`, después de `connection_doctor_enabled`, `api/devops.py:63`):
keys aditivas `deployments_enabled`, `deployments_execute_enabled`, `deployments_ai_enabled`.

### 5.5 UI — 1 entrada en el registro + 1 componente (contrato §3.12 C20)

- `frontend/src/components/devops/DeploymentsSection.tsx` (NUEVO) + helpers puros en
  `frontend/src/components/devops/deploymentsModel.ts` (NUEVO, testeable sin render — patrón de la casa
  por el gap RTL/jsdom conocido, precedente planes 99/103/116-C3).
- Entrada en `DEVOPS_SECTIONS` (`DevOpsPage.tsx:82-154`):
  `{ id: 'despliegues', label: 'Despliegues', icon: '🚀', healthKey: 'deployments_enabled', gateFlagKey: 'STACKY_DEPLOYMENTS_ENABLED', gateMessage: 'La sección Despliegues necesita la flag STACKY_DEPLOYMENTS_ENABLED (Configuración → Arnés, categoría DevOps).', render: (ctx) => <DeploymentsSection ctx={ctx} /> }`.
- Vista: chips de app arriba (empty-state con CTA "Nueva aplicación": form de 4 campos con prefill de
  `detect_stack` si `stack_detect_enabled`); **grid de tarjetas de destino** (Local siempre primero +
  `ctx.servers`); cada tarjeta: versión activa, "hace X", badge de estado (`success/failed/failed_smoke/
  drift/desconocido/nunca`), botones `[Desplegar] [Rollback] [Historial]`; barra de chips DORA.
- Flujo deploy: `[Desplegar]` (multi-select de destinos con orden = olas) → `POST /plan` → modal con
  pasos + warnings preflight (semáforo, concepto plan 93) → confirm (checkbox; input de texto si
  `protected`) → `POST /execute` → progreso en la tarjeta (poll `GET /runs/<id>` cada 2 s) → resultado;
  si `failed_smoke` ⇒ botón **Rollback ahora** pre-armado.
- Cliente: `export const DevOpsDeployments = { ... }` en `frontend/src/api/endpoints.ts`, inmediatamente
  después de `export const DevOpsServers` (anclar por SÍMBOLO — hoy `endpoints.ts:3363` — los números son
  orientativos por WIP concurrente, lección C3 del plan 116).

---

## 6. Fases (F0 → F8) — TDD, criterios binarios, sin ambigüedad

> **Comandos de test (SIEMPRE por archivo, venv real verificado):**
> Backend: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"` y
> `.venv\Scripts\python.exe -m pytest tests/test_plan120_<fase>.py -q`
> Frontend: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"` y
> `npx vitest run src/components/devops/deploymentsModel.test.ts` + `npx tsc --noEmit`
> **Anclaje por símbolo SIEMPRE** (varios archivos tienen WIP concurrente; los `:línea` de este doc son
> orientativos al 2026-07-10).

---

### F0 — Flags del arnés (5 patas) + health keys + tipos frontend

**Objetivo (1 frase).** Plumbear las 5 flags nuevas end-to-end sin ningún comportamiento nuevo visible
(todo OFF ⇒ byte-idéntico). **Valor:** deja el gating listo y testeado para F1-F8.

**Flags EXACTAS (todas categoría `devops`, todas default OFF / valor seguro):**

| Key | Tipo | Default efectivo (config.py) | Bounds | `requires` |
|---|---|---|---|---|
| `STACKY_DEPLOYMENTS_ENABLED` | bool | `false` | — | `STACKY_DEVOPS_PANEL_ENABLED` |
| `STACKY_DEPLOYMENTS_EXECUTE_ENABLED` | bool | `false` | — | `STACKY_DEVOPS_PANEL_ENABLED` |
| `STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED` | bool | `false` | — | `STACKY_DEVOPS_PANEL_ENABLED` |
| `STACKY_DEPLOYMENTS_RETAIN_RELEASES` | int | `3` | min 1, max 10 | copiar forma de la FlagSpec int vecina |
| `STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC` | int | `30` | min 5, max 300 | copiar forma de la FlagSpec int vecina |

> **GOTCHAS OBLIGATORIOS:** (a) FlagSpec **SIN `default=`** — rompe `test_default_known_only_for_curated`
> (lista curada congelada, plan 63); el default efectivo va SOLO en `config.py` con el patrón
> `os.getenv("KEY", "false").lower() in ("1","true","yes","on")` para bools e `int(os.getenv("KEY","3"))`
> para ints (copiar el bloque de una flag devops reciente). (b) `requires` de las 3 bools apunta AL MASTER
> DEL PANEL, NUNCA a `STACKY_DEPLOYMENTS_ENABLED` (R4 profundidad 1, gotcha plan 104); la relación
> master→hijas de Despliegues se aplica EN CÓDIGO (los endpoints EXECUTE/AI chequean además la master).
> (c) Para las 2 ints, replicar EXACTAMENTE la forma de `STACKY_PR_REVIEW_TIMEOUT_SEC` (plan 110) en
> `harness_flags.py` — mismos campos, mismos min/max declarativos (plan 83); si esa entrada lleva
> `requires`, apuntarlo a `STACKY_DEVOPS_PANEL_ENABLED` y registrar la arista.

**Archivos EXACTOS:**
1. `backend/config.py` — 5 defaults efectivos (bloque nuevo `# ── Plan 120 — Centro de Despliegues ──`).
2. `backend/services/harness_flags.py` — (a) 5 keys en la tupla de la categoría `"devops"` (hoy
   `harness_flags.py:187-206`, después de `"STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED"`); (b) 5 `FlagSpec`
   nuevas junto al bloque del plan 116 (`key="STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED"`, hoy `:2429`),
   con `label`/`description` en español mencionando "Plan 120".
3. `backend/services/harness_flags_help.py` — 5 entradas `PlainHelp` (copiar la forma exacta de la
   entrada de `STACKY_PR_REVIEWER_ENABLED`).
4. `backend/tests/test_harness_flags_requires.py` — aristas nuevas en `_REQUIRES_MAP_FROZEN`
   (`"STACKY_DEPLOYMENTS_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED"`, etc.).
5. `backend/harness_defaults.env` — 5 líneas nuevas (`STACKY_DEPLOYMENTS_ENABLED=false`, …,
   `STACKY_DEPLOYMENTS_RETAIN_RELEASES=3`, `STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC=30`). Nota honesta: existe
   un drift conocido del generador (`deployment/export_harness_defaults.py`) con el deploy vivo; NO
   bloquea esta fase (mismo tratamiento que planes 93-116).
6. `backend/api/devops.py` — en `_health_payload()` (después de `connection_doctor_enabled`,
   hoy `:63`): `deployments_enabled`, `deployments_execute_enabled`, `deployments_ai_enabled` con el
   patrón `bool(getattr(cfg, ..., False))`.
7. `frontend/src/pages/DevOpsPage.tsx` — 3 campos opcionales en `DevOpsHealth` (junto a
   `connection_doctor_enabled?`, hoy `:38`). (La entrada en `DEVOPS_SECTIONS` recién en F7.)
8. `frontend/src/api/endpoints.ts` — mismos 3 campos en el tipo de retorno de `DevOps.health`.
9. `backend/scripts/run_harness_tests.ps1` y `.sh` — registrar `tests/test_plan120_flags.py` (ratchet
   plan 49: test no registrado = meta-test en rojo).

**Tests PRIMERO — `backend/tests/test_plan120_flags.py`:**
- `test_flags_known_and_categorized` — las 5 keys existen en el registry y están en la categoría `devops`.
- `test_defaults_effective_off` — recarga `config` con env limpio: master/execute/ai `False`, retain `3`, smoke timeout `30`.
- `test_flagspec_sin_default_explicito` — ninguna de las 3 bools declara default en su spec (introspección, mismo estilo del test curado).
- `test_requires_edges_frozen` — las aristas están en `_REQUIRES_MAP_FROZEN` y apuntan a `STACKY_DEVOPS_PANEL_ENABLED`.
- `test_bounds_ints` — retain 1..10, smoke 5..300 declarados.
- `test_harness_defaults_contains_flags` — las 5 líneas literales en `harness_defaults.env` (patrón `test_f0_harness_defaults_contains_flag` del plan 87).
- `test_health_payload_keys_off` — `_health_payload()` incluye las 3 keys en `False` con flags OFF.
- `test_plainhelp_present` — las 5 keys tienen entrada de ayuda llana.

**Criterio binario:** `.venv\Scripts\python.exe -m pytest tests/test_plan120_flags.py -q` verde Y
`pytest tests/test_harness_flags.py tests/test_harness_flags_requires.py -q` verde (no-regresión del
registry). **Flag:** las propias. **Runtimes:** ortogonal (idéntico en los 3). **Operador:** ninguno.

---

### F1 — Planner puro (`deploy_planner.py`): planes, versionado, retención, drift, DORA

**Objetivo.** Toda la lógica de decisión en funciones puras deterministas, testeables sin red ni disco.

**Archivo NUEVO:** `backend/services/deploy_planner.py`. Símbolos y contratos EXACTOS:
- `validate_app(app: dict) -> list[str]` — valida id (regex §5.1), `artifact.kind` allowlist, path
  absoluto no vacío, `targets` dict con `install_path` absoluto, `smoke.kind` allowlist. Lista de
  errores legibles; `[]` = válida.
- `make_version_id(now_utc: datetime, zip_sha256: str) -> str` — `"%Y%m%d-%H%M%S"` + `"-"` + sha[:8].
- `build_deploy_plan(app, target_key, target_cfg, version_id, retain, smoke_timeout_s) -> list[dict]` —
  pasos ordenados: `preflight` (informativo) → `ensure_dirs` → `transfer` → `unpack` → `pre_switch`
  (solo si configurado) → `switch` → `write_marker` → `post_switch` (si configurado) → `smoke` (si
  `kind != "none"`) → `prune` → `cleanup` (C3 v2). Cada paso: `{"name", "command"|None,
  "read_only": bool, "housekeeping": bool}` — `housekeeping=True` SOLO en `prune` y `cleanup` (su fallo
  no degrada el status, §1). Comandos EXACTOS (C3 v2): `ensure_dirs` =
  `New-Item -ItemType Directory -Force -Path '<install_path>\releases','<install_path>\incoming' | Out-Null`;
  `transfer` y `prune` viajan con `command: None` (los despacha el executor por nombre, F4); `unpack` =
  `Expand-Archive -LiteralPath '<install_path>\incoming\<version_id>.zip' -DestinationPath '<install_path>\releases\<version_id>' -Force`;
  `cleanup` = `Remove-Item -LiteralPath '<install_path>\incoming\<version_id>.zip' -Force`.
- `build_rollback_plan(app, target_key, target_cfg, to_version_id, smoke_timeout_s) -> list[dict]` —
  `pre_switch → switch → write_marker → post_switch → smoke`. **SIN `transfer` NI `unpack`.**
- `build_switch_commands(install_path, version_id) -> list[str]` — los 2 comandos EXACTOS de §5.2
  (`cmd /c if exist ... rmdir` + `cmd /c mklink /J`, C1 v2), con `install_path` validado absoluto y SIN
  comillas dobles embebidas en los paths (rechazar con ValueError si las hay).
- `build_smoke_command(smoke: dict, timeout_s: int) -> str|None` — `http` ⇒ one-liner EXACTO (C9 v2;
  corre en modo write, donde las llaves están permitidas — ver §5.2):
  `try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec <t> -Uri '<url>').StatusCode } catch { if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 'ERR: ' + $_.Exception.Message } }`;
  `ps` ⇒ el comando del operador tal cual; `none` ⇒ `None`.
- `parse_smoke_http_stdout(stdout: str) -> int|None` (C9 v2) — devuelve el ÚLTIMO token numérico del
  stdout o `None`; éxito del smoke http = valor en [200, 399].
- `build_marker_command(install_path, marker: dict) -> str` (C4 v2) — el comando exacto de §5.2.
- `derive_effective_status(entry: dict, now_utc, stale_after_s: int = 3600) -> str` **[ADICIÓN
  ARQUITECTO A1]** — si `entry["status"] == "running"` y `now_utc - started_at > stale_after_s` ⇒
  `"stale"` (backend reiniciado a mitad de deploy: el lock en memoria murió pero la línea quedó
  `running`); en cualquier otro caso devuelve `status` tal cual. Se aplica en LECTURA (F5), jamás muta
  el ledger.
- `check_disk_headroom(free_bytes: int|None, artifact_bytes: int) -> str|None` **[ADICIÓN ARQUITECTO
  A2]** — `None` si hay al menos 2× el artefacto libre (o `free_bytes` desconocido); si no, warning
  legible con ambos números, para el preflight de `/plan` (F5).
- `prune_versions(existing: list[str], retain: int, current: str) -> list[str]` — ordena
  lexicográficamente (los version_id son ordenables), conserva las `retain` más nuevas y NUNCA
  devuelve `current`.
- `parse_release_marker(stdout: str) -> dict|None` — JSON defensivo (None si corrupto).
- `compute_drift(desired_version: str|None, marker: dict|None) -> str` — `"never"` (sin desired),
  `"unknown"` (sin marker legible), `"ok"` (coinciden), `"drift"` (difieren).
- `dora_metrics(entries: list[dict], now_utc) -> dict` — `{deploys_7d, deploys_30d,
  change_failure_rate_30d, mttr_minutes_30d, last_deploy_at}`; CFR = fallidos/(éxitos+fallidos) en 30d
  (action=deploy); MTTR = promedio en minutos de fallo→siguiente éxito del MISMO (app,target); `None`
  donde no hay datos (sin división por cero).
- Constante `MAX_ARTIFACT_MB = 500` (tope de preflight; error legible si el zip lo supera).

**Tests PRIMERO — `backend/tests/test_plan120_planner.py`:** `test_validate_app_casos` (válida, id
inválido, kind inválido, path relativo), `test_make_version_id_determinista`,
`test_deploy_plan_orden_y_pasos`, `test_deploy_plan_omite_hooks_y_smoke_none`,
`test_deploy_plan_housekeeping_solo_prune_y_cleanup` (C2/C3 v2),
`test_rollback_plan_has_no_transfer`, `test_switch_commands_exactos`,
`test_switch_commands_primer_deploy` (C1 v2: el primer comando contiene `if exist`),
`test_switch_commands_rechaza_comillas`, `test_prune_nunca_current`, `test_compute_drift_4_estados`,
`test_dora_metrics_fixture` (fixture de 6 entries con 1 fallo y recuperación),
`test_dora_metrics_vacio_sin_division_por_cero`, `test_parse_release_marker_corrupto`,
`test_parse_smoke_http_stdout` (C9 v2), `test_marker_command_exacto_y_valida_comillas` (C4 v2),
`test_derive_effective_status_stale_y_passthrough` (A1), `test_check_disk_headroom` (A2).

**Criterio binario:** archivo de test verde; `deploy_planner.py` NO importa `requests`, `subprocess` ni
`flask` (test `test_planner_es_puro` con introspección de imports). **Flag:** ninguna (módulo inerte
hasta F5). **Runtimes:** ortogonal. **Operador:** ninguno.

---

### F2 — Transporte WinRM: fix del bug de credenciales + `run_deploy_step` + `push_file_winrm`

**Objetivo.** Corregir §2.3 restaurando el contrato real de `get_credential` y agregar el par de
funciones de transporte de deploy (ejecución gateada por flags de Despliegues + copia de archivos por
PSSession), manteniendo `remote_exec.py` como ÚNICO módulo de ejecución remota.

**Archivos:** `backend/services/remote_exec.py` (editar), `backend/services/deploy_transfer_invoke.ps1`
(NUEVO), `backend/tests/test_plan105_remote_exec_service.py` (SOLO si su fake fija el orden viejo del
unpack: alinearlo al contrato real; cambio mínimo).

**Cambio 1 — fix quirúrgico en `run_remote` (hoy `remote_exec.py:305`):**
```python
# ANTES (bug latente §2.3):
username, password, host = get_credential(alias)
# DESPUÉS (contrato server_registry.py:205-218):
username, domain, password = get_credential(alias)
host = (server or {}).get("host") or ""
sr_user = f"{domain}\\{username}" if domain else username
```
y en el env del subprocess: `"SR_USER": sr_user` (antes `username`), `"SR_HOST": host` (ya derivado del
server, no de la credencial). Si `host` queda vacío ⇒ `error_key = "server_not_found"` (sin keys nuevas).

> **Verificado (C12 v2):** `server = get_server(alias)` YA existe en el scope del fix (hoy
> `remote_exec.py:300`); el cambio NO agrega llamadas, solo corrige el unpack y deriva `host`/`sr_user`.
> El fake con el orden VIEJO vive en `test_plan105_remote_exec_service.py:119,153,192` (tres
> `mock.patch("services.server_registry.get_credential", return_value=("user","pass","host"))`):
> alinearlos al orden real `(username, domain, password)` como parte de esta fase.

**Cambio 2 — `run_deploy_step(alias, command, *, timeout_s, read_only, run_id) -> dict`:** misma
mecánica y shape de retorno que `run_remote` (`{"ok","error","stdout","stderr","exit_code","duration_ms"}`)
con DIFERENCIAS exactas: (a) gating — `read_only=True` exige `STACKY_DEPLOYMENTS_ENABLED`;
`read_only=False` exige ADEMÁS `STACKY_DEPLOYMENTS_EXECUTE_ENABLED` (error `deployments_execute_disabled`);
NO depende de `STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED`; (b) con `read_only=True` valida
`is_read_only_command(command)` (reuso de `remote_exec.py:45-73`); (c) audita SIEMPRE con
`append_audit(alias, {"kind": "deploy", "run_id": run_id, ...})` (mismos campos que el kind `exec`,
`remote_exec.py:347-359`). Implementación: extraer la parte común de invocación de `run_remote` a un
helper privado `_invoke_winrm(host, sr_user, password, command, timeout_s)` y que AMBAS funciones lo
usen (cero duplicación).

**Cambio 3 — `push_file_winrm(alias, local_path, remote_path, *, timeout_s, run_id) -> dict`:** mismo
gating de escritura que `run_deploy_step(read_only=False)`; valida que `local_path` exista y que
`remote_path` sea absoluto (letra de unidad) sin comillas dobles; invoca
`services/deploy_transfer_invoke.ps1` vía env `SR_HOST/SR_USER/SR_PASS/SR_LOCAL_ZIP/SR_REMOTE_ZIP/SR_TIMEOUT`
(riel §3.1: credencial SOLO por env). El `.ps1` (NUEVO, espejo de `remote_exec_invoke.ps1`):
```powershell
# deploy_transfer_invoke.ps1 — Plan 120. Copia un archivo al servidor por PSSession (WinRM 5985).
$sec  = ConvertTo-SecureString $env:SR_PASS -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential($env:SR_USER, $sec)
$s = New-PSSession -ComputerName $env:SR_HOST -Credential $cred -ErrorAction Stop
try {
  Copy-Item -LiteralPath $env:SR_LOCAL_ZIP -Destination $env:SR_REMOTE_ZIP -ToSession $s -Force -ErrorAction Stop
} finally { Remove-PSSession $s }
```
Audita `{"kind": "deploy_transfer", "run_id": ..., "bytes": <tamaño local>, ...}` — JAMÁS el path del
password ni env.

**Tests PRIMERO — `backend/tests/test_plan120_remote_exec_deploy.py`** (mock de `subprocess.run` y
fakes de `server_registry` que respetan el ORDEN REAL `(username, domain, password)`):
- `test_get_credential_contract_unpack` — con fake `get_credential -> ("user","DOM","s3cr3t")` y
  `get_server -> {"host":"10.0.0.5"}`, el env del subprocess lleva `SR_HOST="10.0.0.5"`,
  `SR_USER="DOM\\user"`, `SR_PASS="s3cr3t"` (fija el fix §2.3 para `run_remote` Y `run_deploy_step`).
- `test_sin_dominio_user_plano` — domain `""` ⇒ `SR_USER="user"`.
- `test_run_deploy_step_gating` — master OFF ⇒ error `remote_exec_disabled`-equivalente
  (`deployments_disabled`); master ON + EXECUTE OFF + `read_only=False` ⇒ `deployments_execute_disabled`;
  master ON + `read_only=True` ⇒ ejecuta sin EXECUTE.
- `test_run_deploy_step_no_depende_de_consola` — con `STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED=False` y
  flags de deployments ON, ejecuta igual.
- `test_read_only_valida_comando` — `read_only=True` con comando mutante ⇒ `command_not_read_only`.
- `test_auditoria_kind_deploy` — cada llamada agrega línea JSONL con `kind="deploy"` y `run_id`, sin
  password (assert existente `remote_exec.py:89-91` sigue verde).
- `test_push_file_valida_rutas` — local inexistente / remoto relativo / comillas ⇒ error sin subprocess.
- `test_no_password_real` — fake sin password ⇒ `no_password` (ahora con la semántica correcta).

**Criterio binario:** archivo de test verde + no-regresión
`pytest tests/test_plan105_remote_exec_service.py tests/test_plan108_winrm_diagnosis.py -q` verde.
**Flag:** `STACKY_DEPLOYMENTS_ENABLED` / `STACKY_DEPLOYMENTS_EXECUTE_ENABLED`. **Runtimes:** ortogonal.
**Operador:** ninguno.

---

### F3 — Store (`deploy_store.py`): apps CRUD + ledger + locks anti-concurrencia

**Objetivo.** Persistencia robusta y lockeo para que jamás corran 2 deploys al mismo (app,destino).

**Archivo NUEVO:** `backend/services/deploy_store.py`. Símbolos EXACTOS:
- `_apps_path() / _ledger_path()` — `data_dir() / "deploy_apps.json"` y `"deploy_ledger.jsonl"`.
- `list_apps() -> list[dict]`, `get_app(app_id) -> dict|None`, `upsert_app(app: dict) -> dict`
  (valida con `deploy_planner.validate_app`, ValueError con los errores), `delete_app(app_id) -> bool`.
  Todo bajo `threading.Lock` de módulo (patrón `server_registry._LOCK`, `server_registry.py:34,114`).
- `append_ledger(entry: dict) -> None` / `update_ledger_entry(run_id, patch: dict) -> None` (el update
  reescribe la línea del run_id: leer todo, mapear, escribir — el archivo es chico y mono-operador) /
  `read_ledger(app_id=None, target=None, limit=100) -> list[dict]` (más recientes primero, tolerante a
  líneas corruptas — patrón `read_audit`, `remote_exec.py:101-117`). **C6 v2:** el MISMO
  `threading.Lock` de módulo cubre TAMBIÉN `append_ledger`/`update_ledger_entry`/`read_ledger` — dos
  ÓRDENES concurrentes corren en threads distintos (F4) y sin lock el leer-mapear-reescribir del update
  pierde líneas.
- `acquire_run_lock(app_id, target) -> str|None` (devuelve run_id `"dr-<ts>-<hex4>"` o None si ocupado) /
  `release_run_lock(app_id, target) -> None` — set en memoria + Lock (no persiste: un restart libera).
- `last_success_version(app_id, target) -> str|None` y `retained_versions(app_id, target, n) -> list[str]`
  — derivados del ledger (para poblar el modal de rollback).

**Tests PRIMERO — `backend/tests/test_plan120_store.py`** (con `data_dir` parcheado a `tmp_path` —
OJO gotcha de la casa: parchear en el MÓDULO DE ORIGEN consumido por `deploy_store`, lazy imports):
`test_crud_apps_roundtrip`, `test_upsert_valida`, `test_apps_json_corrupto_degrada_a_vacio`,
`test_append_y_read_ledger_orden`, `test_update_ledger_entry_por_run_id`,
`test_ledger_linea_corrupta_se_salta`, `test_lock_409_semantica` (segundo acquire = None; release
libera), `test_last_success_y_retained`, `test_update_concurrente_no_pierde_entradas` (C6 v2: 2 threads
× 25 `update_ledger_entry` sobre run_ids distintos; al final el ledger conserva TODAS las líneas).

**Criterio binario:** archivo verde. **Flag:** ninguna (módulo inerte hasta F5). **Runtimes:** ortogonal.
**Operador:** ninguno.

---

### F4 — Executor (`deploy_executor.py`): transportes Local/WinRM, smoke, artefacto, hilo de fondo

**Objetivo.** Ejecutar planes reales con el MISMO código para Local y remoto (paridad de pasos), con
progreso persistido y cero falsos verdes.

**Archivo NUEVO:** `backend/services/deploy_executor.py`. Símbolos EXACTOS:
- `build_artifact_zip(app: dict) -> dict` — `{"zip_path","sha256","size_mb"}`: si `artifact.kind=="zip"`
  copia a staging (`data_dir()/deploy_staging/<app_id>.zip`) y hashea; si `"folder"` lo zipa con
  `zipfile` (stdlib). Error legible si no existe o supera `MAX_ARTIFACT_MB`.
- Clase `LocalTransport` — `run(command, timeout_s, read_only)` = `subprocess.run(["powershell.exe",
  "-NoProfile","-NonInteractive","-Command", command], capture_output=True, text=True, timeout=...)`;
  `push_file(local, remote)` = `shutil.copy2` (validando remoto absoluto). Gating idéntico al remoto
  (mismas flags) implementado en el executor (no en el transport).
- Clase `WinRMTransport(alias)` — `run` ⇒ `remote_exec.run_deploy_step(alias, ...)`; `push_file` ⇒
  `remote_exec.push_file_winrm(alias, ...)`.
- `make_transport(target_key) -> LocalTransport|WinRMTransport` — `"__local__"` ⇒ Local.
- `execute_plan(run_id, app, target_key, plan, transport) -> dict` — SÍNCRONO: recorre pasos, tras cada
  uno `update_ledger_entry(run_id, ...)` con el paso agregado; primer paso de ACTIVACIÓN fallido ⇒ corta
  con `status="failed"` (o `"failed_smoke"` si el paso era `smoke`); pasos con `housekeeping=True`
  (`prune`, `cleanup`) fallidos se registran `ok:false` SIN cambiar el status (C2 v2, §1); todos los de
  activación ok ⇒ `"success"`. Despacho POR NOMBRE (C2/C3 v2): `transfer` ⇒
  `push_file(zip_local, '<install_path>\incoming\<version_id>.zip')`; `prune` ⇒ 3 sub-acciones: (1)
  `run("Get-ChildItem -LiteralPath '<install_path>\releases' -Name", read_only=True)` (brace-free y
  verbo `Get-` ⇒ pasa `is_read_only_command`), (2) `prune_versions(lineas_del_stdout, retain, current)`
  pura, (3) por cada versión a borrar `run('cmd /c rmdir /S /Q "<install_path>\releases\<v>"',
  read_only=False)`; cualquier otro paso ⇒ `run(command)`. Smoke http: éxito =
  `parse_smoke_http_stdout(stdout)` en [200, 399] (C9 v2).
- `start_deploy_async(app, target_keys, plans) -> list[dict]` — semántica EXACTA (C5 v2): (1) adquiere
  UPFRONT el lock de CADA destino pedido; los ocupados se devuelven como
  `{"target", "error": "deploy_in_progress"}` y NO se ejecutan; (2) con los destinos lockeados appendea
  su entry `running` y lanza UN ÚNICO `threading.Thread(daemon=True)` por ORDEN, que itera esos destinos
  EN el orden recibido (olas: el operador decide canary primero) corriendo `execute_plan` por destino y
  liberando el lock de cada destino en `finally` al terminar su turno; (3) devuelve la lista por destino
  (`run_id` o error). Dos ÓRDENES distintas SÍ corren en paralelo (por eso el lock del ledger, C6).
- `start_rollback_async(app, target_key, to_version) -> dict` — ídem con `build_rollback_plan`.

**Tests PRIMERO — `backend/tests/test_plan120_executor.py`** (con `FakeTransport` que graba llamadas y
respuestas guionadas; `data_dir` a tmp): `test_zip_desde_folder_y_desde_zip`,
`test_zip_supera_tope_error_legible`, `test_execute_plan_exito_completo_ledger_success`,
`test_falla_en_transfer_corta_y_marca_failed`, `test_smoke_falla_marca_failed_smoke`,
`test_smoke_http_parsea_status`, `test_rollback_no_llama_push_file`, `test_prune_lista_solo_viejas`,
`test_lock_impide_segundo_deploy_mismo_destino`, `test_local_transport_push_valida_ruta_absoluta`,
`test_orden_multi_destino_un_solo_thread_y_en_orden` (C5 v2: el FakeTransport graba la secuencia),
`test_lock_parcial_ejecuta_libres_y_reporta_ocupados` (C5 v2),
`test_prune_despacho_lista_filtra_borra` (C2 v2), `test_housekeeping_falla_no_degrada_success` (C2 v2),
`test_cleanup_borra_zip_incoming` (C3 v2).

**Criterio binario:** archivo verde SIN tocar red (todo fake/tmp). **Flag:** EXECUTE (heredada del
transporte F2; LocalTransport la chequea vía executor con test propio). **Runtimes:** ortogonal.
**Operador:** ninguno.

---

### F5 — API (`api/devops_deployments.py`) + registro del blueprint

**Objetivo.** Exponer §5.4 con gating estricto, HITL y shapes estables para la UI.

**Archivos:** `backend/api/devops_deployments.py` (NUEVO, blueprint como §5.4),
`backend/api/__init__.py` (1 import + 1 `api_bp.register_blueprint(devops_deployments_bp)` junto a los
demás), `backend/api/devops.py` (ya tocado en F0 para health).

**Reglas EXACTAS de gating (tests las fijan):** master OFF ⇒ `abort(404)` en TODOS; `/execute` y
`/rollback` además: EXECUTE OFF ⇒ 403 `{"error":"deployments_execute_disabled"}`; sin `confirm:true` ⇒
400; destino `protected` y `confirm_text != app_id` ⇒ 400 `{"error":"confirm_text_required"}`; 409
`{"error":"deploy_in_progress"}` SOLO si TODOS los destinos pedidos tienen lock ocupado — mezcla ⇒ 200
con detalle por destino (C5 v2); `DELETE /apps/<id>` con lock activo en cualquier destino de esa app ⇒
409 `{"error":"deploy_in_progress"}` (C11 v2). `/overview`, `/runs/<run_id>` y `/history` devuelven
`effective_status` calculado con `derive_effective_status` (A1; el ledger NO se muta). `/plan` hace
preflight: artefacto (existencia/tamaño), espacio en disco del destino con `check_disk_headroom` (A2:
remoto vía `run_deploy_step(read_only=True)` con `Get-PSDrive -Name '<letra de install_path>'`
— brace-free, verbo `Get-`; local vía `shutil.disk_usage`; warning informativo, jamás bloquea),
`server_registry.test_connectivity(host, 5985)` y `remote_exec.check_winrm(alias)` para remotos
(incluye `kind` + `remediation` del 108/116 en la respuesta, la UI los muestra tal cual), y para
`__local__` solo artefacto + install_path absoluto. `/drift` construye el comando con
`build_smoke_command`-style `Get-Content -LiteralPath '<install>\release.json' -Raw` y lo corre con
`run_deploy_step(read_only=True)` (o LocalTransport read-only). `/metrics` y `/history` derivan del
store. `current_user` del header (`api/_helpers.py`) se persiste en `operator` del entry (mono-operador,
sin validar — riel de la casa).

**Tests PRIMERO — `backend/tests/test_plan120_api.py`** (Flask test client; fakes de executor/transport;
`data_dir` a tmp): `test_404_todo_con_master_off`, `test_overview_shape_targets_local_primero`,
`test_apps_crud_endpoints`, `test_plan_dry_run_sin_efectos` (ningún thread, ningún subprocess),
`test_plan_incluye_remediacion_winrm_cuando_falla_sonda`, `test_execute_403_sin_execute_flag`,
`test_execute_400_sin_confirm`, `test_execute_protected_exige_confirm_text`,
`test_execute_409_solo_si_todos_lockeados` (C5 v2), `test_delete_app_409_con_run_activo` (C11 v2),
`test_rollback_usa_version_retenida`,
`test_runs_y_history_devuelven_ledger`, `test_effective_status_stale_en_overview` (A1),
`test_plan_incluye_warning_disco` (A2), `test_drift_command_es_read_only` (C4 v2: el comando de `/drift`
pasa `is_read_only_command`), `test_metrics_shape`, `test_diagnose_404_sin_flag_ai`.

**Criterio binario:** archivo verde + `create_app()` importa sin romper (smoke de import del blueprint;
si `api/devops_servers.py` u otro módulo ajeno sigue roto en el working tree, usar el patrón
importlib-directo del plan 117 y DEJARLO ANOTADO — no tocar archivos ajenos). **Flag:** master +
EXECUTE + AI. **Runtimes:** ortogonal. **Operador:** ninguno.

---

### F6 — Diagnóstico IA local de deploys fallidos (costo cero, opt-in)

**Objetivo.** Con `STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED` ON y modelo local vivo, un click en un run
fallido produce explicación + remediación sugerida en español, persistida en el entry del ledger.

**Archivos:** `backend/services/deploy_diagnosis.py` (NUEVO) + ruta `/diagnose` ya declarada en F5.
- `build_diagnosis_prompt(entry: dict) -> str` — PURA: pasos con `ok=false` + stderr truncado con
  `local_insights.truncate_middle` + `local_insights.HITL_RULES` (`local_insights.py:41-48`) al final;
  JAMÁS incluye credenciales (los steps no las contienen por diseño F2).
- `diagnose_run(run_id) -> dict` — gating flag; health-gate `_local_llm_reachable`
  (`local_insights.py:225`; si el símbolo es privado, replicar su forma EXACTA en el módulo nuevo);
  llama al modelo local por el MISMO camino que usa `local_insights` para generar (grep del punto único
  de generación en `services/local_insights.py` al implementar; NO crear otro cliente HTTP); parseo
  defensivo con caps (`TLDR_MAX`-style); persiste `{"insight": {...}}` vía `update_ledger_entry`.

**Tests PRIMERO — `backend/tests/test_plan120_ai_diagnosis.py`:** `test_prompt_incluye_hitl_y_paso_fallido`,
`test_prompt_trunca_outputs_largos`, `test_flag_off_404`, `test_modelo_caido_error_legible_sin_llamada`
(health-gate falso ⇒ no se invoca generación — patrón C2 plan 117 "no quemar filas"),
`test_persiste_insight_en_entry`, `test_respuesta_corrupta_degrada_sin_crash`.

**Criterio binario:** archivo verde con el cliente LLM mockeado (cero red). **Flag:**
`STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED`. **Runtimes:** idéntico en los 3 (modelo LOCAL, no runtime);
fallback: botón deshabilitado con hint si el health-gate falla. **Operador:** opt-in (default off).

---

### F7 — UI: sección "Despliegues" (tarjetas por destino, 2 clicks, rollback 1 click, DORA chips)

**Objetivo.** La vista pedida por el operador, enchufada por el contrato C20 sin tocar el shell.

**Archivos:** `frontend/src/components/devops/DeploymentsSection.tsx` (NUEVO),
`frontend/src/components/devops/deploymentsModel.ts` (NUEVO, PURO),
`frontend/src/api/endpoints.ts` (agregar `export const DevOpsDeployments` con `overview/apps/plan/
execute/rollback/run/history/drift/metrics/diagnose` — después de `export const DevOpsServers`),
`frontend/src/pages/DevOpsPage.tsx` (SOLO la entrada en `DEVOPS_SECTIONS` — 1 import + 1 objeto,
contrato §3.12 C20; id `'despliegues'`, icon `'🚀'`, gate como §5.5), estilos reusando
`components/devops/devops.module.css` (clases `alertSuccess/alertWarning/alertError` y tarjetas
existentes; CERO hex nuevos — tokens `theme.css` si hace falta algo puntual).

**`deploymentsModel.ts` (helpers PUROS, cada uno con test):**
- `buildTargetCards(app, servers, overviewState) -> TargetCard[]` — Local primero, luego alias
  ordenados; cada card `{key, label, kind, version, deployedAgo, status, canRollback, protected}`.
- `cardStatus(lastEntry, driftResult) -> 'nunca'|'ok'|'failed'|'failed_smoke'|'running'|'stale'|'drift'|'desconocido'`
  (`stale` = `effective_status` de A1: badge gris "obsoleto" con hint "el backend se reinició durante
  este deploy; verificá con el botón Drift y relanzá si hace falta").
- `rollbackChoices(history, retain) -> {version, when}[]` — solo versiones `success` retenidas.
- `confirmRequirement(targetCfg) -> {kind: 'checkbox'|'text', expected?: string}`.
- `waveOrder(selectedKeys: string[]) -> string[]` — respeta el orden de selección (olas).
- `formatDora(metrics) -> {label, value}[]`.
- `buildPendingPresetHandoff(stack: string|null) -> {presetId: string}|null` (para F8).

**Flujos (concretos):** deploy multi-destino con modal de plan (pasos + preflight con remediación del
116 renderizada con el patrón `RemediationCard`), confirm HITL, progreso con poll 2 s (`useQuery`
`refetchInterval`), `failed_smoke` ⇒ botón "Rollback ahora" que abre el confirm de rollback YA
posicionado en `prev_version_id`. Estado local persistente mínimo: app seleccionada en
`localStorage 'stacky.devops.deployments.selectedApp'` (patrón `DevOpsPage.tsx:174-181`).

**Tests PRIMERO — `frontend/src/components/devops/deploymentsModel.test.ts`** (vitest TS-PURO sin
render, patrón de la casa): `buildTargetCards` (local primero, server sin config de app ⇒ card
"sin asignar"), `cardStatus` (8 estados, incluye `stale` A1), `rollbackChoices` (excluye fallidas y la activa),
`confirmRequirement` (protected ⇒ text), `waveOrder`, `formatDora`, `buildPendingPresetHandoff`.

**Criterio binario:** `npx vitest run src/components/devops/deploymentsModel.test.ts` verde +
`npx tsc --noEmit` = 0 errores + suites vitest existentes verdes (no-regresión). **Flag:**
`STACKY_DEPLOYMENTS_ENABLED` (gate declarativo del shell). **Runtimes:** ortogonal. **Operador:**
ninguno (la sección aparece gateada con CTA de activación, patrón FlagGateBanner).

---

### F8 — Puente "pipeline → deploy" (creación de pipelines trivial, sin tocar el generador)

**Objetivo.** Cerrar el círculo del pedido: desde Despliegues, crear el pipeline sugerido por el stack
detectado en 1 click, y desplegar el artefacto que ese pipeline deja en la carpeta convenida.

**Alcance EXACTO (mínimo, sin refactor):**
1. CTA "Crear pipeline de deploy" en el empty-state y el header de `DeploymentsSection`: llama
   `GET /api/devops/detect-stack` (plan 97; si `stack_detect_enabled` OFF, el CTA se oculta), guarda
   `localStorage 'stacky.devops.pendingPreset' = JSON {presetId}` con `buildPendingPresetHandoff` y
   navega a la sub-tab `pipelines` con `ctx.setActiveSection('pipelines')`. **C7 v2 (verificado):** ese
   mecanismo NO existía en v1 — `activeId` es `useState` interno (`DevOpsPage.tsx:163`) y el ctx no
   expone callback ni hay routing por hash. Fix EXACTO: agregar el campo OPCIONAL
   `setActiveSection?: (id: string) => void` a `DevOpsSectionContext` (junto a `selectedServer?`,
   mismo precedente aditivo del plan 91, `DevOpsPage.tsx:46-48`) y pasarlo al armar el ctx
   (`setActiveSection: handleSelect`, el handler que ya llama `setActiveId` en `DevOpsPage.tsx:195`) —
   2 líneas en `DevOpsPage.tsx`, cambio aditivo backward-compatible que se declara HONESTAMENTE: F8
   toca `DevOpsPage` en el registro + esas 2 líneas. Fallback explícito: si `ctx.setActiveSection` es
   `undefined` (shell del plan 119 u otro que aún no lo propague), el CTA guarda el pendingPreset
   igual y muestra el hint "Preset guardado — abrí la sub-tab Pipelines" (degradación sin rotura).
2. `PipelineBuilderSection.tsx`: al montar, si existe `stacky.devops.pendingPreset`, preseleccionar ese
   preset (la galería del plan 97/104 ya sabe aplicar presets) y LIMPIAR la key (one-shot). Cambio
   acotado a un `useEffect` inicial.
3. Convención de artefacto documentada EN LA UI (tooltip del campo `artifact.path`): "apuntá a la
   carpeta donde tu pipeline deja el build (p. ej. `<repo>\dist` o la carpeta de artefactos del job)".
   NO se modifica el generador declarativo (plan 73) ni sus renderers: cero riesgo de regresión YAML.

**Tests PRIMERO:** casos nuevos en `deploymentsModel.test.ts` (`buildPendingPresetHandoff` con stack
conocido/None) + `frontend/src/pages/__tests__/` caso TS-puro del one-shot (helper puro
`consumePendingPreset(storageValue) -> {presetId}|null` exportado de `deploymentsModel.ts` y usado por
`PipelineBuilderSection`).

**Criterio binario:** vitest verde + `tsc --noEmit` 0 + con `stack_detect_enabled=false` el CTA no se
renderiza (helper puro `showCreatePipelineCta(health) -> boolean` con test). **Flag:** ninguna nueva
(compone 97 + 120). **Runtimes:** ortogonal. **Operador:** ninguno.

---

## 7. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **Bug latente de credenciales** (§2.3) enmascarado por fakes desalineados | F2 lo corrige con test contractual que fija el ORDEN REAL del contrato; se revisa el fake del plan 105 y se alinea. |
| R2 | **Switch con archivos lockeados** (servicio/IIS sirviendo desde `current`) | Hooks `pre_switch/post_switch` por destino (Stop/Start-Service, Stop-WebSite); el rmdir del junction NO toca contenido; si el switch falla el run queda `failed` con el stderr y el rollback re-apunta al estado anterior. Documentado en el tooltip del campo. |
| R3 | **Artefactos grandes por WinRM** | `Copy-Item -ToSession` es streaming nativo (no base64-en-comando como el chunking del 108); tope `MAX_ARTIFACT_MB=500` con error de preflight legible. Fast-path UNC queda para cuando el plan 101 aterrice (puerto de transporte lo permite sin refactor). |
| R4 | **Smoke http desde la máquina equivocada** | El smoke corre EN el destino (vía transporte), no desde el backend ⇒ `localhost` del servidor es válido y no depende de firewalls intermedios. |
| R5 | **Hooks arbitrarios del operador** (PowerShell libre) | Mono-operador + HITL: los hooks se muestran ÍNTEGROS en el confirm modal, se auditan en el JSONL del alias, y solo existen si el operador los escribió. Sin escalación nueva: es el mismo poder que ya da la Consola (105) en modo write. |
| R6 | **Concurrencia** (doble click, dos ventanas) | Lock por (app,destino) + 409; ledger `running` visible; locks en memoria ⇒ un restart los libera (sin deadlock persistente). |
| R7 | **Drift check contra servidor apagado** | `compute_drift ⇒ "unknown"` con badge gris y detail de la sonda; jamás bloquea la vista (overview no llama red; drift es botón aparte). |
| R8 | **`harness_defaults.env` drift conocido** (saga 87-116) | Se agregan las líneas y el centinela igual que los planes previos; el drift del deploy vivo es un issue PREEXISTENTE trackeado, no de este plan. |
| R9 | **WinRM no habilitado aún en PF** | El preflight lo detecta con `check_winrm` y muestra la remediación copy-paste YA escrita (108/116). El destino Local funciona HOY sin WinRM (demo de valor inmediata). |
| R10 | **Backend reiniciado a mitad de deploy** (entry `running` eterna; lock en memoria perdido) | `derive_effective_status` (A1, C10 v2) la muestra `stale` en frío, sin demonio; el operador puede relanzar (el lock murió con el proceso: no hay deadlock) y el botón Drift dice qué versión quedó realmente activa. |
| R11 | **Disco lleno en el destino** | Preflight A2: warning si libre < 2× artefacto, ANTES de transferir; informativo, jamás bloquea (HITL). |

## 8. Fuera de scope (explícito)

- Auto-rollback SIN confirmación humana (HITL innegociable; solo pre-armado 1-click).
- Canary con análisis estadístico de métricas (Kayenta) y balanceo de tráfico blue/green real.
- Destinos Linux/ssh; deploy de la PROPIA Stacky (DeployStackyAgents) — dogfooding para un plan futuro.
- Transporte UNC/robocopy (plan 101) e inyección automática de stages de deploy en el YAML del
  generador (plan 73): el puerto/handoff los deja enchufables sin refactor.
- Scheduling/deploy windows y notificaciones push.

## 9. Glosario (para modelos menores)

- **Destino:** un servidor del registro (plan 91, `devops_servers.json`) o `__local__` (la máquina del backend).
- **Release:** carpeta inmutable `releases\<version_id>` en el destino con el contenido de UNA versión.
- **Switch:** re-crear el junction `current` apuntando a otra release (activación casi-atómica).
- **Rollback:** switch a una release retenida anterior (sin transferir nada).
- **Smoke:** verificación post-switch (HTTP local al destino o comando PS) que decide `success` vs `failed_smoke`.
- **Marker (`release.json`):** archivo en el destino con la versión activa (fuente del drift check).
- **Drift:** la versión del marker ≠ la última versión `success` del ledger (alguien tocó a mano).
- **Ledger:** `deploy_ledger.jsonl`, historia append-only de deploys/rollbacks (fuente de la UI y DORA).
- **Stale:** entry `running` cuyo backend murió a mitad de deploy; estado DERIVADO en lectura (A1), nunca persistido.
- **Housekeeping:** pasos post-activación (`prune`, `cleanup`) cuyo fallo se registra sin degradar el `success` (C2 v2).
- **Ola (wave):** orden de destinos elegido por el operador; canary humano = ola de 1 + promover al resto.
- **DORA:** frecuencia de deploy, change failure rate, MTTR — calculadas del ledger local.
- **HITL:** human-in-the-loop; acá = confirm explícito SIEMPRE antes de ejecutar/rollbackear.

## 10. Orden de implementación

1. F0 (flags + health + tipos) — commit propio.
2. F1 (planner puro) — commit propio.
3. F2 (transporte + FIX §2.3) — commit propio; correr no-regresión 105/108.
4. F3 (store) → 5. F4 (executor) — commits propios.
6. F5 (API + blueprint) — commit propio.
7. F6 (diagnóstico IA) — commit propio.
8. F7 (UI sección) → 9. F8 (puente pipelines) — commits propios.
10. Registrar TODOS los tests backend nuevos en `run_harness_tests.ps1` + `.sh` (si no se hizo por fase).

## 11. Definición de Hecho (DoD)

- [ ] Las 5 flags existen, default OFF/seguro, configurables desde `HarnessFlagsPanel`, con PlainHelp,
      bounds, aristas en `_REQUIRES_MAP_FROZEN` y líneas en `harness_defaults.env`.
- [ ] Con TODO OFF: `/api/devops/health` solo suma keys `false`; endpoints nuevos 404; UI sin cambios de
      comportamiento; suites previas verdes (por archivo).
- [ ] `test_plan120_flags/planner/remote_exec_deploy/store/executor/api/ai_diagnosis.py` TODOS verdes con
      `.venv\Scripts\python.exe -m pytest tests/<archivo> -q` y output pegado en el reporte.
- [ ] `deploymentsModel.test.ts` verde + `tsc --noEmit` 0 + vitest previos verdes.
- [ ] El fix §2.3 mergeado con su test contractual y la no-regresión 105/108 verde.
- [ ] Primer deploy end-to-end sobre un `install_path` VIRGEN queda `success` (C1 v2: `if exist` en el
      switch; cubierto por `test_switch_commands_primer_deploy` + `test_execute_plan_exito_completo_ledger_success`).
- [ ] Deploy y rollback SOLO ejecutan con `confirm:true` (+ `confirm_text` si protected) y con
      `STACKY_DEPLOYMENTS_EXECUTE_ENABLED` ON — verificado por tests de gating.
- [ ] Ningún secreto en ledger/auditoría/logs (asserts defensivos verdes).
- [ ] Tests nuevos registrados en el ratchet (ps1 + sh).
- [ ] Documento actualizado a IMPLEMENTADO con evidencia al cerrar (regla de la casa).
