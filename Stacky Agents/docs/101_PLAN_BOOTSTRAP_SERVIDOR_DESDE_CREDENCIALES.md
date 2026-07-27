# Plan 101 — Bootstrap de servidor desde credenciales: inicializar un servidor remoto (filesystem + config base + publicación inicial) con un click HITL

**Estado:** ❌ **OBSOLETO / SUPERADO — NO IMPLEMENTAR**
**Versión:** v2 (v1: 2026-07-06 · veredicto de vigencia: 2026-07-26)
**Veredicto del juez:** **RECHAZADO.** Construido por otro plan, con el transporte OPUESTO al que este proponía.
**Autor v1:** StackyArchitectaUltraEficientCode · **Crítica v2:** StackyArchitectaUltraEficientCode (juez adversarial)

---

## VEREDICTO: OBSOLETO. El **plan 108** construyó esto, y lo construyó mejor.

Este documento se conserva como registro. **No debe implementarse.** Implementarlo hoy sería
**agregar un segundo transporte remoto, más débil y sin auditoría, en paralelo al que ya
existe** — el pecado capital de este repo (rieles paralelos).

---

## 1. Qué lo reemplazó, con `archivo:línea`

El v1 proponía un plan-then-apply remoto del layout de carpetas usando las credenciales del
keyring. **Eso existe, está cableado y tiene tests.**

| Pieza que el v1 iba a construir | Ya existe en | Evidencia |
|---|---|---|
| Plan remoto (dry-run, solo lectura) del layout | **Plan 108 F5** | `backend/services/environment_remote.py:97` — `plan_environment_remote(...)` |
| Apply remoto (crea SOLO lo faltante) | **Plan 108 F5** | `backend/services/environment_remote.py:179` — `apply_environment_remote(...)` |
| Resolución del layout contra el catálogo | **Plan 108 F5** | `backend/services/environment_remote.py:68` — `resolve_remote_layout(...)` |
| Comandos remotos de status y mkdir (puros) | **Plan 108 F5** | `environment_remote.py:30` (`build_remote_status_command`), `:43` (`parse_status_output`), `:59` (`build_remote_mkdir_command`) |
| Cableado a los endpoints del panel | **Plan 108 F5** | `backend/api/devops.py:363-364` (plan) y `:430-432` (apply) |
| Tests | **Plan 108 F5** | `backend/tests/test_plan108_environment_remote.py` |
| Transporte remoto autenticado + auditado | **Plan 105** | `backend/services/remote_exec.py:287` (`run_remote`), `:254` (`_invoke_winrm`), `:204` (`check_winrm`), `:500` (`push_file_winrm`), auditoría JSONL en `:77` (`_audit_dir`) |
| Abstracción local/remoto del transporte | **Plan 120** | `backend/services/deploy_executor.py:85` (`LocalTransport`), `:122` (`WinRMTransport`), `:139` (`make_transport`) |
| Consola remota por servidor (UI) | **Plan 105** | `frontend/src/components/devops/RemoteConsoleSection.tsx` (348 LOC), `backend/api/devops_remote_console.py` |
| Publicación/despliegue apuntado a un servidor | **Plan 120** | `backend/api/devops_deployments.py` (14 rutas), `frontend/src/components/devops/DeploymentsSection.tsx` (536 LOC) |

La cabecera del módulo lo dice con todas las letras
(`backend/services/environment_remote.py:1-7`):

> *"services/environment_remote.py — **Plan 108 F5**. Plan/apply de Ambientes (Plan 89/107)
> contra el servidor **REMOTO** seleccionado (cierra RC3: hoy `environment_init.py` evalúa y crea
> siempre en el filesystem local del backend). **Reusa el riel WinRM auditado del Plan 105**
> (`services/remote_exec.run_remote`) — **NUNCA reinventa transporte, credenciales ni auditoría**."*

Ese último renglón es, literalmente, el veredicto sobre el plan 101.

## 2. La decisión de arquitectura del v1 se resolvió al revés — y su justificación era falsa

El v1 §3.1 dedica su decisión central a **elegir UNC + `net use` y descartar WinRM**:

> *"**WinRM (pywinrm/pypsrp)** exigiría una **dependencia nueva** (no está en
> `requirements.txt:11` — solo `keyring`)... **Se descarta como default**."*

**La casa eligió WinRM. Y lo hizo sin agregar ninguna dependencia.** El transporte real no usa
`pywinrm` ni `pypsrp`: invoca PowerShell `Invoke-Command` por subprocess, con scripts propios
(`backend/services/remote_exec_invoke.ps1`, `backend/services/deploy_transfer_invoke.ps1`).
La premisa que sostenía toda la decisión —"WinRM ⇒ dependencia nueva"— **era incorrecta**.

Consecuencia práctica si alguien implementara el 101 hoy:

- **Dos transportes remotos incompatibles** en el mismo panel: WinRM auditado (105/108/120) y
  UNC/`net use` sin auditoría (101).
- **Se pierde la auditoría.** `run_remote` deja rastro JSONL append-only por alias
  (`remote_exec.py:77`) y clasifica fallos (`:129` `classify_winrm_failure`, `:154`
  `build_winrm_remediation`). El `net use` del 101 no deja nada.
- **Se pierde el gating de escritura.** `remote_exec.py:423` (`run_deploy_step`) exige
  `STACKY_DEPLOYMENTS_ENABLED` para leer y **además** `STACKY_DEPLOYMENTS_EXECUTE_ENABLED` para
  escribir (`backend/config.py:1619-1623`, **ambas default `"false"`** — correcto: escriben en un
  sistema real del operador). El 101 introduciría escritura remota bajo **una sola** flag propia.
- **Se pierde la paridad de shape.** `environment_remote` garantiza *"PARIDAD EXACTA de keys
  contra el plan/apply local"* + `{'remote': True, 'server_alias': alias}`, y `DirTreePreview`
  (Plan 107) consume ese shape **sin distinguir local de remoto**. Un tercer shape rompería esa UI.

## 3. Sus KPIs ya no miden nada

| KPI del v1 | Estado hoy |
|---|---|
| *"Consumidores de `ctx.selectedServer` (91 F6): **0** (cableado muerto) → 1 (esta sección)"* | **FALSO.** Hoy tiene **4 consumidores productivos**: `DevOpsAgentSection.tsx:63`, `EnvironmentsSection.tsx:84`, `RemoteConsoleSection.tsx:27`, `ServersSection.tsx:294` (más su propio test). El cableado dejó de estar muerto hace planes. |
| *"Pasos para preparar el filesystem de un servidor nuevo: 100% manual (RDP + carpetas a mano)"* | **FALSO.** El wizard de Ambientes ya hace plan→confirm→apply contra el servidor seleccionado (`api/devops.py:349`, `:397` → `environment_remote`). |
| *"Credenciales expuestas en logs: 0 por diseño"* | Ya garantizado por el riel del 105, con auditoría que el 101 no tenía. |

## 4. Y además: 2 defectos que lo habrían frenado en F0

Se documentan porque son la clase de bug que esta casa persigue, y porque **el 102 comparte el
primero**.

### D1 — BLOQUEANTE — El `requires` propuesto es una **cadena prohibida** por R4
El v1 §F0 paso 2 propone `requires="STACKY_DEVOPS_SERVERS_ENABLED"`, y §F0 paso 6 dice:

> *"**Si `validate_requires_graph` rechaza la cadena de longitud 2**... cambiar `requires` a
> `STACKY_DEVOPS_PANEL_ENABLED`... Correr `test_harness_flags_requires.py` para decidir cuál
> aplica."*

**La respuesta era determinable leyendo 12 líneas, no "decidiendo por test".** Medido:

- `backend/services/harness_flags.py:4959-4960` — *"**R4: profundidad máxima 1** — un master
  apuntado **NO puede tener a su vez `requires`** (sin cadenas ni ciclos por construcción)"*.
- `:4979-4980` — el validador emite
  `f"{spec.key}: cadena prohibida — {spec.requires} también declara requires"`.
- `STACKY_DEVOPS_SERVERS_ENABLED` **sí declara** `requires="STACKY_DEVOPS_PANEL_ENABLED"`.

⇒ `requires="STACKY_DEVOPS_SERVERS_ENABLED"` produce **cadena prohibida** y
`test_harness_flags_requires.py` en **rojo desde el primer commit**. La respuesta correcta es
`STACKY_DEVOPS_PANEL_ENABLED`, y el plan debía traerla resuelta.

> **El mismo defecto está en el plan 102 §3.1**, que propone
> `requires="STACKY_DEVOPS_PUBLICATIONS_ENABLED"` con idéntica coletilla *"resolver por test"*.
> Medido: `STACKY_DEVOPS_PUBLICATIONS_ENABLED` **también** declara
> `requires="STACKY_DEVOPS_PANEL_ENABLED"` ⇒ **también** es cadena prohibida.

### D2 — IMPORTANTE — La flag se cablea en **6 patas**, no 5
El v1 §F0 enumera 5 patas y agrega `harness_defaults.env` como paso manual. Dos correcciones:
la sexta pata es **`backend/services/harness_flags_help.py`** (que el v1 sí incluye, pero
contándola dentro de las "5"), y **`harness_defaults.env` es un archivo GENERADO**
(`deployment/export_harness_defaults.py`) que **no se edita a mano**. Moot para este plan, pero
no debe repetirse.

---

## 5. Lo único que NO cubrió el 108 (y por qué no justifica un plan)

Del alcance del v1, dos ítems no tienen equivalente literal:

1. **"Depositar un archivo de configuración base"** en el servidor. El mecanismo ya existe:
   `backend/services/remote_exec.py:500` (`push_file_winrm`) y
   `backend/services/deploy_executor.py:133` (`push_file` en ambos transportes). Lo que falta
   es **qué archivo** depositar — y eso es una decisión de contenido del operador, no
   infraestructura. Si algún día se quiere, son ~20 líneas sobre un riel existente, no un plan.
2. **"Encadenar la publicación inicial"**. El Centro de Despliegues (Plan 120) ya hace
   plan→confirm→execute→rollback contra el mismo destino
   (`backend/api/devops_deployments.py:164` plan, `:195` execute, `:245` rollback), con
   type-to-confirm para destinos protegidos (`DeploymentsSection.tsx:174-201`). Encadenar
   "ambiente recién creado → despliegue" es, si acaso, una mejora de UX de **esa** sección.

Ninguno de los dos sostiene un plan propio. **El número 101 queda consumido.**

## 6. [ADICIÓN ARQUITECTO] El guardarraíl que este caso reclama

El 101 no falló por mal diseño: falló porque **20 días de trabajo pasaron por encima y el
documento no tenía forma de enterarse**. Propuesta concreta y barata, aplicable a todo el
pipeline de planes:

> **Todo plan cuyo `Estado:` sea `PROPUESTO` y cuya `Fecha:` tenga más de ~10 días debe pasar
> un `GATE-0 DE VIGENCIA` antes de la crítica de diseño**: para cada fila de su tabla de
> "Dependencias / GAP VERIFICADO", volver a correr el grep que la sostiene. Si **una sola**
> premisa cambió, el plan se re-scopea o se cierra **antes** de gastar un token en criticar sus
> fases.

Costo: minutos. Retorno medido en esta corrida: de 6 planes auditados, **2 fueron construidos
por otros** (101 por el 108, y el 98 a medias) y **1 tenía su premisa invertida** (el 100).
Sin el gate, los tres habrían recibido una v2 pulida de trabajo que no había que hacer.

Corolario específico, y el más caro de todos: **cuando un plan declara una decisión de
arquitectura, esa decisión tiene fecha de vencimiento.** El 101 eligió UNC sobre WinRM con un
argumento razonable en su momento y falso a los tres días. Un plan que espera veinte días no
conserva su premisa: conserva su redacción.
