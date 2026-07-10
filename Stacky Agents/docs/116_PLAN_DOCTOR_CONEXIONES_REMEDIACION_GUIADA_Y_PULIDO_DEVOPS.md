# Plan 116 — Doctor de conexiones con remediación guiada + pulido profesional del panel DevOps

> **Estado:** CRITICADO v2 — 2026-07-10 (v1 → v2 por `criticar-y-mejorar-plan`)
> **Veredicto del juez:** APROBADO-CON-CAMBIOS (C1-C4 resueltos en esta v2; sin bloqueantes)
> **Autor:** StackyArchitectaUltraEficientCode
>
> **CHANGELOG v1 → v2:**
> - **C1 (IMPORTANTE):** `probe_tracker` (F1) usaba `label` sin definir su mapa, "patrón de `local_diagnostics._check_tracker`" — pero ESE mapa (`local_diagnostics.py:69-73`) NO incluye `gitlab` (verificado: solo azure_devops/jira/mantis), así que un proyecto GitLab mostraría el label crudo `"gitlab"` en `detail` y `fmt["service"]`. v2 define el mapa LITERAL en F1 incluyendo `"gitlab": "GitLab"` (y `token_url` de GitLab = `{base_url}/-/user_settings/personal_access_tokens`, con degradación a retry si falta base). +1 caso en el test 3.
> - **C2 (IMPORTANTE):** el KPI decía "~≤12 s peor caso" pero el tope REAL es `fut.result(timeout=_PROBE_TIMEOUT_SECONDS*3)` = 15 s por grupo, y las sondas subyacentes traen su PROPIO timeout (`test_connectivity` 3 s; `_probe_ado` el del cliente ADO), no el de la constante `_PROBE_TIMEOUT_SECONDS`. v2 corrige el KPI a "≤15 s peor caso (tope del `future.result`)" y aclara que `_PROBE_TIMEOUT_SECONDS` acota la ESPERA del agregador, no el socket de cada cliente (que ya trae el suyo).
> - **C3 (MENOR):** anclas por número de línea en `endpoints.ts:3074` y `ServersSection.tsx:284-286` en archivos con WIP concurrente. v2 refuerza: anclar SIEMPRE por símbolo (`export const DevOps`, el bloque que renderiza `test.detail`), los números son solo orientativos.
> - **C4 [ADICIÓN ARQUITECTO]:** el "buscar PAT en un snapshot real" (F6) era una verificación MANUAL. v2 lo convierte en un test automático de invariante `test_no_secret_leaks_in_snapshot` (F1): construye un `DiagResult` de falla con `fmt` que incluye un token de juguete `"glpat-SECRET123"` y afirma que NINGÚN campo serializado del resultado (detail/remediation/steps/command/url) lo contiene — la redacción deja de depender del ojo humano.
> - Confirmado por lectura de código (no solo por el plan): el bug latente `local_diagnostics._check_tracker` manda GitLab (rama `else`, `:80-81`) a `_probe_ado`; este plan NO lo replica (sonda `_probe_gitlab` propia) y NO toca `local_diagnostics`. Anclajes de sustrato verificados: `server_registry.{test_connectivity:221,keyring_available:43,get_credential:205,list_servers:84}`, `GitLabClient` (`api/global_config.py:27,285` con `_request("GET","/user")`), `api/devops.py:_health_payload:28`, categoría `"devops"` (`harness_flags.py:187`).
> **Pipeline:** este documento pasó `proponer` → `criticar` (este estado). Sigue `implementar-plan-stacky` → `supervisar-implementaciones-planes`.
> **Serie:** pulido profesional del dashboard DevOps. COMPLEMENTA (no duplica) al portafolio 98-103
> (98 bootstrap+PATCH, 99 preview SWR, 100 suite-1-click, 101 bootstrap-servidor, 102 publicar-1-paso,
> 103 monitor-persistente — todos PROPUESTOS) y al plan 104 (doctores **IA** por sección — IMPLEMENTADO).
> Este plan es la contraparte **DETERMINISTA**: cero LLM, cero costo por uso, respuesta en segundos.
> **Depende de:** nada pendiente. Solo usa sustrato YA implementado (planes 87 shell/health, 91 servidores,
> flags del arnés 33/63/82/86).

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Hoy, cuando algo no conecta en el panel DevOps (ADO/GitLab/Jira/Mantis,
servidores registrados, CLIs de los runtimes, credenciales en keyring), el operador ve **strings crudos
de excepción**: `server_registry.test_connectivity` devuelve `f"TCP {port}: {exc}"`
(`backend/services/server_registry.py:221-231`), el test de tracker devuelve `f"Auth GitLab falló: {exc_gl}"`
(`backend/api/global_config.py:296`), y el cliente HTTP del frontend lanza
`Error(`${res.status} ${res.statusText}: ${text}`)` plano (`frontend/src/api/client.ts:78`). Nada le dice
al operador **qué pasó ni qué hacer**. Este plan agrega (a) un **doctor de conexiones determinista**:
catálogo tipificado de códigos de falla con **remediación paso a paso escrita en este documento**
(no la inventa ningún modelo), sondas paralelas con timeout corto y un endpoint HITL; (b) una
**tira de salud de conexiones** (`ConnectionHealthStrip`) siempre visible en el shell del panel DevOps
con chips verde/ámbar/rojo y tarjetas de remediación accionables (reintentar / copiar comando /
abrir URL / ir a sección) en un click; y (c) un **pulido visual profesional acotado y aditivo**
(tarjetas de remediación consistentes, estado vacío con CTA en Servidores, facelift del
`FlagGateBanner`, accesibilidad de la barra de sub-tabs). Todo detrás de una flag nueva default OFF:
con la flag apagada la UI y la API quedan **byte-idénticas** a hoy.

**KPI / impacto esperado.**
- **Cobertura de remediación 100% (binario):** todo código del catálogo (§F0) tiene `title`, `cause`,
  `steps` (≥2 pasos) y `action` válida — verificado por test de invariante
  (`test_catalog_every_code_has_complete_remediation`). Ninguna falla clasificable muestra texto crudo
  cuando la flag está ON.
- **Tiempo-a-diagnóstico:** de "leer un traceback y adivinar" a **1 click** ("Diagnosticar") que devuelve
  el estado de tracker + servidores + CLIs + credenciales con pasos concretos. Sondas en paralelo
  (`ThreadPoolExecutor`, 4 grupos); **(C2)** el tope REAL por grupo es `fut.result(timeout=_PROBE_TIMEOUT_SECONDS*3)`
  = 15 s ⇒ chequeo integral acotado a **≤15 s peor caso** (las sondas subyacentes traen además su
  propio timeout: `test_connectivity` 3 s, cliente ADO el suyo; `_PROBE_TIMEOUT_SECONDS` acota la
  ESPERA del agregador, no el socket de cada cliente).
- **Regresión 0 (binario):** flag OFF ⇒ ningún endpoint nuevo responde (404), ningún componente nuevo se
  monta, `ServersSection` renderiza exactamente lo de hoy. Suites existentes verdes + `tsc --noEmit` 0 err.
- **Cero costo por uso:** a diferencia del plan 104 (doctores IA), este doctor no lanza ningún run de
  agente ni consume tokens. Complementarios, no competidores.

---

## 2. Por qué ahora / gap que cierra

1. **La serie DevOps 87-108 construyó mucha superficie que CONECTA con cosas externas** (ADO/GitLab,
   servidores remotos plan 91/105/108, CLIs de runtimes) pero el manejo de errores quedó primitivo:
   `ServersSection.tsx:284-286` pinta el `detail` crudo del test; el `FlagGateBanner` es el único
   patrón "qué pasó + qué hacer" que existe, y solo cubre flags.
2. **El portafolio 98-103 ataca velocidad y one-click de FLUJOS** (activar suite, bootstrap, publicar,
   monitorear). Ninguno ataca el momento "no conecta y no sé por qué" — el mayor generador de fricción
   cuando algo falla. Este plan cierra exactamente ese hueco y NO pisa el alcance de ninguno:
   no activa flags en lote (100), no inicializa servidores (101), no publica (102), no pollea pipelines (103).
3. **El plan 104 ya dio doctores IA por sección** (interpretan logs con un agente). Falta la capa
   **barata y determinista** que responde en segundos las fallas de conectividad SIN gastar un run:
   401 ⇒ "tu PAT venció, regeneralo así". La IA queda para lo que es ambiguo; lo tipificable se tipifica.
4. **El sustrato ya existe y se REUSA, no se reinventa:** `services/local_diagnostics.py` ya tiene sondas
   de tracker (`_probe_ado:93`, `_probe_jira:103`, `_probe_mantis:120`) y detección de binarios
   (`_find_executable:425`); `services/server_registry.py:221` ya testea DNS+TCP;
   `api/devops.py:_health_payload` ya es el contrato aditivo de health; el shell `DevOpsPage.tsx`
   ya define el contrato de extensión §3.12. Este plan solo agrega la clasificación tipificada,
   el catálogo de remediación y la superficie UI.

---

## 3. Principios y guardarraíles (NO negociables)

- **3 runtimes con paridad (Codex CLI, Claude Code CLI, GitHub Copilot Pro).** El doctor es
  backend Flask + React: runtime-agnóstico. La sonda de CLIs cubre a los TRES explícitamente:
  `codex` y `claude` por `shutil.which` (+ fallbacks npm), y **Copilot se reporta `skip` con detalle
  "no requiere CLI local (usa VS Code / bridge)"** — nunca `fail` por no tener CLI. Ningún ítem del plan
  depende de un runtime específico.
- **Cero trabajo extra para el operador.** Flag nueva **default OFF**; con OFF todo queda idéntico a hoy.
  Activable 100% desde la UI (Configuración → Arnés, categoría `devops`), como exige el riel
  "toda config del operador va por UI". No hay pasos manuales nuevos ni migraciones.
- **Human-in-the-loop innegociable.** El chequeo corre SOLO con click explícito ("Diagnosticar" o
  "Probar conexión"). **No hay polling automático** (eso es del plan 103 y para pipelines), no hay
  auto-reintentos, y **ninguna acción de remediación muta configuración sola**: las acciones son
  reintentar (click), copiar comando al portapapeles, abrir URL externa, o navegar a una sección.
  El doctor diagnostica y guía; el operador decide y ejecuta.
- **Mono-operador sin auth real.** Nada de RBAC. El guard de los endpoints es el patrón 404-si-flag-OFF
  de `api/devops_servers.py:19-25`.
- **No degradar performance/seguridad/estabilidad/DX.**
  - Sondas con timeout duro 5 s c/u, en paralelo (`ThreadPoolExecutor`), y SOLO on-demand.
  - **Nunca** se incluyen secretos (PAT, passwords, tokens) en `detail`, `remediation` ni logs
    (mismo riel §3.1 del plan 91). Los `detail` se truncan a 300 chars.
  - Payloads aditivos: el único endpoint existente que se toca (`POST /api/devops/servers/<alias>/test`)
    conserva `{ok, detail}` intactos y solo AGREGA `diag` cuando la flag está ON.
- **TDD sin falsos verdes.** Cada fase nombra su archivo de test, los casos, y el comando exacto con el
  venv del repo. Test primero (falla por la razón correcta) → implementación → verde. Los tests de sondas
  **mockean toda la red** (cero sockets reales en CI).
- **Sin ambigüedad para modelos menores.** Nombres canónicos en §4, textos de remediación literales en F0,
  anclas por SÍMBOLO (no por número de línea) en archivos con WIP concurrente conocido
  (`ServersSection.tsx`, `FlagGateBanner.tsx`, `config.py`, `harness_flags.py` — ver §8 Riesgos).

---

## 4. Nombres canónicos (usar EXACTAMENTE estos)

| Concepto | Nombre exacto |
|---|---|
| Módulo núcleo backend | `backend/services/connection_doctor.py` |
| Blueprint API | `backend/api/devops_connections.py` — `Blueprint("devops_connections", __name__, url_prefix="/devops/connections")` |
| Rutas finales | `GET /api/devops/connections/health` · `POST /api/devops/connections/check` |
| Flag (única nueva) | `STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED` — bool, **default OFF**, `requires="STACKY_DEVOPS_PANEL_ENABLED"` |
| Key de health | `connection_doctor_enabled` (aditiva en `api/devops.py:_health_payload`) |
| Timeout de sonda | `_PROBE_TIMEOUT_SECONDS = 5.0` (constante de módulo; NO es flag) |
| Componente tira | `frontend/src/components/devops/ConnectionHealthStrip.tsx` |
| Componente tarjeta | `frontend/src/components/devops/RemediationCard.tsx` |
| API frontend | `DevOps.connectionsHealth()` · `DevOps.connectionsCheck()` en `frontend/src/api/endpoints.ts` |
| Tests backend | `tests/test_plan116_connection_doctor_core.py`, `tests/test_plan116_connection_probes.py`, `tests/test_plan116_connections_endpoints.py`, `tests/test_plan116_connection_doctor_flag.py`, `tests/test_plan116_servers_test_diag.py` |
| Tests frontend | `frontend/src/components/devops/RemediationCard.test.tsx`, `ConnectionHealthStrip.test.tsx`, `FlagGateBanner.test.tsx` |

**Contrato `DiagResult` (dict JSON, congelado en F0):**

```json
{
  "target": "tracker | server:<alias> | cli:codex | cli:claude | cli:git | runtime:copilot | keyring",
  "target_label": "Azure DevOps (Proyecto X) | Servidor SRV01 | Codex CLI | ...",
  "group": "tracker | servers | clis | credentials",
  "status": "ok | warn | fail | skip",
  "code": "<código del catálogo, '' si ok/skip>",
  "detail": "<texto corto legible, sin stack trace, max 300 chars>",
  "latency_ms": 123,
  "remediation": {
    "title": "...", "cause": "...",
    "steps": ["paso 1", "paso 2"],
    "action": { "kind": "retry | copy_command | open_url | goto_section | none",
                "command": "<solo kind=copy_command>",
                "url": "<solo kind=open_url>",
                "section_id": "<solo kind=goto_section>" }
  }
}
```
`remediation` es `null` cuando `status` es `ok` o `skip`.

**Contrato snapshot (respuesta de `POST /check` y campo de `GET /health`):**

```json
{
  "generated_at": "2026-07-09T12:00:00Z",
  "duration_ms": 4200,
  "results": [ DiagResult, ... ],
  "summary": { "ok": 4, "warn": 1, "fail": 2, "skip": 1 }
}
```
`GET /health` responde `{"status": "ready" | "never_run", "stale": bool, "snapshot": {...} | null}`
(`stale=true` si el snapshot tiene más de 300 s; NO dispara refresh solo — HITL).

---

## 5. Fases

### F0 — Núcleo puro: catálogo de remediación + clasificadores (sin red, sin flag)

**Objetivo (1 frase).** Crear el módulo puro con el catálogo tipificado de códigos y los clasificadores
de excepciones/HTTP, 100% testeable sin tocar red. **Valor:** la fuente única de verdad de "qué pasó y
cómo se arregla", escrita acá para que ningún modelo la invente.

**Archivos:** crear `backend/services/connection_doctor.py`; crear
`backend/tests/test_plan116_connection_doctor_core.py`.

**Símbolos exactos a crear en `connection_doctor.py`:**
- `_PROBE_TIMEOUT_SECONDS: float = 5.0`
- `CODES: tuple[str, ...]` = `("CONFIG_MISSING", "DNS_FAIL", "TCP_REFUSED", "TIMEOUT", "TLS_ERROR",
  "AUTH_401", "FORBIDDEN_403", "NOT_FOUND_404", "HTTP_5XX", "CLI_NOT_FOUND", "KEYRING_UNAVAILABLE",
  "CRED_MISSING", "UNKNOWN")`
- `REMEDIATIONS: dict[str, dict]` — un entry por código de `CODES`. **Contenido LITERAL** (copiar tal
  cual; `{placeholders}` se resuelven con `.format(**fmt)` en `build_result`):

| code | title | cause | steps (lista) | action |
|---|---|---|---|---|
| `CONFIG_MISSING` | Falta configuración | No hay datos suficientes para intentar la conexión ({what}). | 1. Abrí Configuración → Config global (o el proyecto activo) y completá {what}. 2. Guardá y volvé a este panel. 3. Click en "Reintentar". | `{"kind":"retry"}` |
| `DNS_FAIL` | El nombre no resuelve | El host {host} no existe en DNS o no hay red. | 1. Verificá que el nombre esté bien escrito (sin http:// ni espacios). 2. Probá `ping {host}` en una terminal: si falla, es red/VPN, no Stacky. 3. Si usás VPN corporativa, conectala y reintentá. | `{"kind":"copy_command","command":"ping {host}"}` |
| `TCP_REFUSED` | El servidor rechaza la conexión | El host {host} responde pero el puerto {port} está cerrado o el servicio caído. | 1. Confirmá que el servicio esté levantado en {host}. 2. Revisá firewall/puerto {port}. 3. Reintentá cuando el servicio esté arriba. | `{"kind":"retry"}` |
| `TIMEOUT` | La conexión expiró | {host} no respondió en {timeout}s (red lenta, VPN caída o host apagado). | 1. Verificá tu conexión/VPN. 2. Confirmá que el host esté encendido. 3. Reintentá; si persiste, revisá con el doctor IA de la sección (plan 104). | `{"kind":"retry"}` |
| `TLS_ERROR` | Error de certificado TLS | El certificado de {host} no es válido para este cliente (autofirmado, vencido o proxy corporativo). | 1. Si es un servidor interno con certificado autofirmado, revisá la config `verify_ssl` del tracker del proyecto. 2. Si hay proxy corporativo, consultá qué CA raíz instalar. 3. Reintentá tras el cambio. | `{"kind":"retry"}` |
| `AUTH_401` | Credenciales inválidas o vencidas | {service} rechazó la autenticación (401): token/PAT inválido, vencido o revocado. | 1. Regenerá el token en {service}. 2. Pegalo en Configuración → Config global (campo correspondiente) y guardá. 3. Click en "Reintentar" para validar. | `{"kind":"open_url","url":"{token_url}"}` |
| `FORBIDDEN_403` | Sin permisos suficientes | {service} autenticó pero denegó el acceso (403): el token no tiene los scopes/permisos necesarios. | 1. Regenerá el token con los scopes de lectura/escritura de work items o `api` (GitLab). 2. Verificá que tu usuario tenga acceso al proyecto/organización. 3. Reintentá. | `{"kind":"open_url","url":"{token_url}"}` |
| `NOT_FOUND_404` | Recurso inexistente | {service} respondió 404: la organización/proyecto/URL configurada no existe o está mal escrita. | 1. Revisá organización y proyecto en Configuración → Config global. 2. Confirmá el nombre exacto en el navegador. 3. Corregí y reintentá. | `{"kind":"retry"}` |
| `HTTP_5XX` | El servicio remoto falló | {service} devolvió un error {status} de SU lado; no es un problema de tu configuración. | 1. Esperá unos minutos: suele ser transitorio. 2. Revisá el status page del servicio si persiste. 3. Reintentá. | `{"kind":"retry"}` |
| `CLI_NOT_FOUND` | CLI no instalada | No se encontró `{cli}` en el PATH: el runtime {runtime} no puede ejecutarse desde Stacky. | 1. Instalala con el comando de abajo (botón "Copiar"). 2. Cerrá y reabrí la terminal/backend para refrescar el PATH. 3. Reintentá el diagnóstico. | `{"kind":"copy_command","command":"{install_cmd}"}` |
| `KEYRING_UNAVAILABLE` | Almacén de credenciales no disponible | El backend no pudo usar el keyring de Windows: los passwords de servidores no pueden guardarse ni leerse. | 1. Instalá la dependencia en el venv del backend con el comando de abajo. 2. Reiniciá el backend. 3. Reintentá el diagnóstico. | `{"kind":"copy_command","command":"pip install keyring==25.6.0"}` |
| `CRED_MISSING` | Servidor sin credencial guardada | El servidor {alias} está registrado pero no tiene password en el keyring: RDP 1-click y consola remota no van a autenticar. | 1. Andá a la sección Servidores. 2. Editá {alias} y cargá el password (se guarda write-only en keyring). 3. Reintentá el diagnóstico. | `{"kind":"goto_section","section_id":"servidores"}` |
| `UNKNOWN` | Falla no clasificada | Ocurrió un error que el doctor no pudo tipificar. | 1. Leé el detalle técnico de abajo. 2. Reintentá una vez. 3. Si persiste, usá el doctor IA de la sección (plan 104) o revisá los logs del backend en Diagnóstico. | `{"kind":"retry"}` |

  Notas duras: (a) `token_url` para ADO = `https://dev.azure.com/{org}/_usersSettings/tokens`; para
  GitLab = `{base_url}/-/user_settings/personal_access_tokens`; si no hay org/base conocida, la action
  degrada a `{"kind":"retry"}`. (b) `install_cmd`: codex → `npm install -g @openai/codex`; claude →
  `npm install -g @anthropic-ai/claude-code`; git → `winget install --id Git.Git -e`.
  (c) Ningún placeholder sin resolver puede llegar al frontend: `build_result` hace `.format` con
  `defaultdict(str)`-style seguro (ver abajo).
- `classify_http_error(status_code: int | None, exc: Exception | None) -> str` — mapping puro:
  `401→AUTH_401`, `403→FORBIDDEN_403`, `404→NOT_FOUND_404`, `>=500→HTTP_5XX`; si `status_code is None`,
  delega en `classify_socket_error(exc)`; sin match → `UNKNOWN`.
- `classify_socket_error(exc: Exception) -> str` — por tipo/contenido:
  `socket.gaierror→DNS_FAIL`; `(socket.timeout | TimeoutError)→TIMEOUT`;
  `ConnectionRefusedError→TCP_REFUSED`; `ssl.SSLError→TLS_ERROR`;
  `urllib.error.HTTPError` → `classify_http_error(exc.code, None)`;
  `urllib.error.URLError` → recursión sobre `exc.reason` si es Exception, si no `UNKNOWN`;
  cualquier otro → `UNKNOWN`. (Los imports: `import socket, ssl, urllib.error` arriba del módulo.)
- `build_result(*, target: str, target_label: str, group: str, status: str, code: str = "",
  detail: str = "", latency_ms: int | None = None, fmt: dict | None = None) -> dict` — arma el
  `DiagResult` del contrato §4: trunca `detail` a 300 chars; si `status` in `("fail","warn")` adjunta
  `REMEDIATIONS[code]` con placeholders resueltos vía
  `class _SafeDict(dict): def __missing__(self, k): return "?"` + `texto.format_map(_SafeDict(fmt or {}))`
  aplicado a `cause`, cada `step`, `command` y `url`; si `code` no está en `REMEDIATIONS` usa `UNKNOWN`
  (nunca `KeyError`); si `status` in `("ok","skip")` ⇒ `remediation=None`.

**Tests PRIMERO** (`tests/test_plan116_connection_doctor_core.py` — sin Flask, sin red):
1. `test_catalog_every_code_has_complete_remediation` — para CADA code de `CODES`:
   entry existe, `title` y `cause` no vacíos, `steps` con ≥2 strings no vacíos, `action["kind"]` ∈
   `{"retry","copy_command","open_url","goto_section","none"}`, y si kind es copy_command/open_url/
   goto_section el campo extra correspondiente existe.
2. `test_classify_http_401_403_404_5xx_none` — 401/403/404/500/503 → códigos esperados; `(None, TimeoutError())` → `TIMEOUT`.
3. `test_classify_socket_gaierror_timeout_refused_ssl` — cada tipo → su código; `ValueError("x")` → `UNKNOWN`.
4. `test_classify_urlerror_unwraps_reason` — `urllib.error.URLError(socket.gaierror())` → `DNS_FAIL`.
5. `test_build_result_attaches_remediation_and_formats` — `code="DNS_FAIL", fmt={"host":"srv01"}` ⇒
   `remediation["cause"]` contiene `srv01` y ningún `{host}` literal.
6. `test_build_result_unknown_code_never_raises` — `code="NO_EXISTE"` ⇒ remediation = la de `UNKNOWN`.
7. `test_build_result_ok_has_no_remediation` — `status="ok"` ⇒ `remediation is None`.
8. `test_build_result_truncates_detail` — detail de 1000 chars ⇒ len ≤ 300.
9. `test_build_result_missing_placeholder_safe` — `code="AUTH_401", fmt={}` ⇒ no lanza; `?` en lugar del placeholder.

**Comando (correr ANTES de implementar → debe fallar con ImportError; y DESPUÉS → verde):**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
venv\Scripts\python.exe -m pytest tests/test_plan116_connection_doctor_core.py -q
```
**Criterio binario:** los 9 tests pasan; `git diff --stat` de la fase toca SOLO los 2 archivos listados.
**Flag:** ninguna (módulo puro sin consumidores todavía; inerte por construcción).
**Runtimes:** N/A (backend puro, ningún runtime interviene). Fallback: N/A.
**Trabajo del operador:** ninguno.

---

### F1 — Sondas con timeout corto + chequeo integral paralelo

**Objetivo (1 frase).** Agregar a `connection_doctor.py` las sondas de tracker/servidores/CLIs/keyring
(reusando el sustrato existente) y el agregador paralelo `run_connection_check()`. **Valor:** el
diagnóstico integral real, acotado en tiempo y sin red en tests.

**Archivos:** editar `backend/services/connection_doctor.py`; crear
`backend/tests/test_plan116_connection_probes.py`.

**Símbolos exactos a crear (todos en `connection_doctor.py`):**

- `probe_tracker() -> dict` (devuelve 1 `DiagResult`):
  1. `from project_manager import get_active_project, get_project_config` (MISMO import que usa
     `services/local_diagnostics.py` — verificar con grep su línea de import y copiarla).
  2. Sin proyecto activo ⇒ `build_result(target="tracker", target_label="Tracker", group="tracker",
     status="warn", code="CONFIG_MISSING", detail="No hay proyecto activo.", fmt={"what": "el proyecto activo"})`.
  3. `tracker_type = ((cfg.get("issue_tracker") or {}).get("type") or "azure_devops").strip().lower()`
     (patrón de `local_diagnostics._check_tracker`, `services/local_diagnostics.py:61-73`).
     **(C1) Mapa `label` LITERAL — INCLUYE gitlab (el de `local_diagnostics` NO):**
     ```python
     label = {"azure_devops": "Azure DevOps", "gitlab": "GitLab",
              "jira": "Jira", "mantis": "Mantis"}.get(tracker_type, tracker_type or "Tracker")
     ```
  4. Ejecutar la sonda mínima según tipo, cronometrando con `time.monotonic()`:
     - `azure_devops` ⇒ `from services.local_diagnostics import _probe_ado; _probe_ado(active)`
       (REUSO literal; lanza excepción si falla — `services/local_diagnostics.py:93-100`).
     - `jira` ⇒ `_probe_jira(active, tracker)` · `mantis` ⇒ `_probe_mantis(active, tracker)` (ídem reuso).
     - `gitlab` ⇒ sonda propia `_probe_gitlab(tracker: dict) -> None`: instanciar `GitLabClient` con el
       MISMO import y constructor que usa `api/global_config.py:285` (verificar con
       `grep -n "GitLabClient" backend/api/global_config.py` antes de escribir) y llamar
       `client._request("GET", "/user")`. NOTA: `local_diagnostics._check_tracker` manda gitlab al probe
       de ADO (rama `else`, `:80-81`) — ese bug NO se replica acá; `local_diagnostics` NO se toca.
  5. Éxito ⇒ `status="ok"`, `detail=f"{label}: credenciales válidas para {active}."`, `latency_ms` medido.
  6. Excepción `exc` ⇒ `code = classify_socket_error(exc)`;
     `fmt = {"service": label, "host": "", "token_url": <regla de F0 según tracker_type/org>,
     "status": getattr(exc, "code", "")}`; `status="fail"`; `detail=str(exc)[:300]`.
- `probe_servers() -> list[dict]`:
  - `from services import server_registry`; iterar `server_registry.list_servers()`.
  - Sin servidores ⇒ lista vacía (la UI muestra el grupo como "sin datos", no error).
  - Por servidor: `ok, detail = server_registry.test_connectivity(server["host"])`
    (`services/server_registry.py:221`). Mapeo del string (contrato actual, NO se modifica
    `server_registry`): `detail.startswith("DNS:")` ⇒ `DNS_FAIL`; `not ok and "timed out" in detail.lower()`
    ⇒ `TIMEOUT`; `not ok` (resto) ⇒ `TCP_REFUSED`; `ok` ⇒ `status="ok"`. `fmt={"host": server["host"], "port": "3389", "timeout": "3"}`.
  - Además, si `ok` y `server_registry.keyring_available()` y
    `server_registry.get_credential(server["alias"]) is None` ⇒ resultado EXTRA
    `status="warn", code="CRED_MISSING", target=f"server:{alias}", fmt={"alias": alias}`.
    (Verificar el nombre/firma real de `get_credential` con grep en `services/server_registry.py`
    antes de escribir; existe según `backend/services/server_registry.py:6-8` y `api/devops_servers.py:137`.)
- `probe_clis() -> list[dict]` (grupo `"clis"`):
  - Para `("git", "codex", "claude")`: `from services.local_diagnostics import _find_executable,
    _npm_global_fallbacks` (REUSO; `services/local_diagnostics.py:425,156`).
    `path = _find_executable(name, _npm_global_fallbacks(name))` (para `git` pasar `[]` de fallbacks).
    Encontrado ⇒ `ok` con `detail=path`; no encontrado ⇒ `fail`, `code="CLI_NOT_FOUND"`,
    `fmt={"cli": name, "runtime": {"git": "git", "codex": "Codex CLI", "claude": "Claude Code CLI"}[name],
    "install_cmd": <regla F0>}`.
  - Resultado fijo extra: `target="runtime:copilot", status="skip",
    detail="GitHub Copilot no requiere CLI local (corre vía VS Code/bridge)."` — paridad honesta de los 3 runtimes.
- `probe_keyring() -> dict`: `server_registry.keyring_available()` ⇒ `ok`; `False` ⇒
  `warn` + `code="KEYRING_UNAVAILABLE"`. (Verificar nombre real con
  `grep -n "def keyring_available" backend/services/server_registry.py`; se usa en `api/devops_servers.py:31`.)
- `run_connection_check() -> dict` (el agregador):
  ```python
  def run_connection_check() -> dict:
      started = time.monotonic()
      tasks = {"tracker": probe_tracker, "servers": probe_servers,
               "clis": probe_clis, "keyring": probe_keyring}
      results: list[dict] = []
      with ThreadPoolExecutor(max_workers=4) as pool:
          futures = {name: pool.submit(fn) for name, fn in tasks.items()}
          for name, fut in futures.items():
              try:
                  out = fut.result(timeout=_PROBE_TIMEOUT_SECONDS * 3)
                  results.extend(out if isinstance(out, list) else [out])
              except Exception as exc:  # noqa: BLE001 — un probe roto NUNCA rompe el chequeo
                  results.append(build_result(
                      target=name, target_label=name, group=name if name != "keyring" else "credentials",
                      status="fail", code="UNKNOWN", detail=str(exc)[:300]))
      summary = {s: sum(1 for r in results if r["status"] == s) for s in ("ok", "warn", "fail", "skip")}
      return {"generated_at": datetime.utcnow().isoformat() + "Z",
              "duration_ms": int((time.monotonic() - started) * 1000),
              "results": results, "summary": summary}
  ```
  (Grupo de `probe_keyring` = `"credentials"`; el de tracker = `"tracker"`; servidores = `"servers"`.)

**Tests PRIMERO** (`tests/test_plan116_connection_probes.py`). Regla de mocking (gotcha conocido de
lazy imports, memoria plan 94): parchear SIEMPRE en el módulo de ORIGEN:
`mock.patch("services.local_diagnostics._probe_ado", ...)`,
`mock.patch("services.server_registry.test_connectivity", ...)`,
`mock.patch("services.server_registry.list_servers", ...)`,
`mock.patch("services.local_diagnostics._find_executable", ...)`. Casos:
1. `test_probe_tracker_no_active_project_warns` — get_active_project→None ⇒ warn CONFIG_MISSING.
2. `test_probe_tracker_ado_401_maps_auth401` — `_probe_ado` lanza `urllib.error.HTTPError(url, 401, "u", {}, None)` ⇒ fail AUTH_401 y `remediation["action"]["url"]` contiene `_usersSettings/tokens`.
3. `test_probe_tracker_gitlab_uses_own_probe` — tracker_type gitlab con `_probe_gitlab` mockeado OK ⇒ ok, `_probe_ado` NO fue llamado, **(C1)** y `detail`/`target_label` contienen `"GitLab"` (no el crudo `"gitlab"`).
4. `test_probe_servers_dns_fail_maps` — `test_connectivity`→`(False, "DNS: no resuelve x")` ⇒ DNS_FAIL.
5. `test_probe_servers_ok_without_credential_warns_cred_missing` — ok TCP + get_credential→None ⇒ 2 resultados (ok + warn CRED_MISSING con action goto_section "servidores").
6. `test_probe_clis_missing_codex_has_install_command` — `_find_executable`→None para codex ⇒ fail CLI_NOT_FOUND, `command == "npm install -g @openai/codex"`.
7. `test_probe_clis_copilot_always_skip` — el resultado `runtime:copilot` existe con status skip.
8. `test_probe_keyring_unavailable_warns` — keyring_available→False ⇒ warn KEYRING_UNAVAILABLE.
9. `test_run_connection_check_aggregates_and_survives_probe_crash` — con `probe_tracker` parcheado para
   lanzar `RuntimeError`, el snapshot igual se arma, contiene un fail UNKNOWN para "tracker", y
   `summary` suma exactamente `len(results)`.
10. **(C4) [ADICIÓN ARQUITECTO]** `test_no_secret_leaks_in_snapshot` — `build_result(status="fail",
    code="AUTH_401", detail="token glpat-SECRET123 rechazado", fmt={"service":"GitLab",
    "token_url":"https://x/-/user_settings/personal_access_tokens","host":"","status":401})` y afirmar
    que la cadena `"glpat-SECRET123"` NO aparece en la remediación serializada (cause/steps/command/url)
    — el catálogo jamás interpola el detail crudo en la remediación. Además, `json.dumps(result)` no
    debe contener ninguna key `password`/`pat`/`token` con valor secreto (solo `token_url`, que es una
    URL pública de gestión de tokens, sin el token). Automatiza el chequeo manual "buscar PAT" de F6.

**Comando:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
venv\Scripts\python.exe -m pytest tests/test_plan116_connection_probes.py -q
```
**Criterio binario:** 10/10 verdes (incluye C4 no-fuga de secretos) + los de F0 siguen verdes (correr ambos archivos).
**Flag:** ninguna todavía (sin consumidores; F2 expone).
**Runtimes:** paridad explícita — codex/claude por PATH con fallbacks npm, copilot `skip` honesto.
Fallback: cualquier sonda rota degrada a `UNKNOWN` sin romper el chequeo (test 9).
**Trabajo del operador:** ninguno.

---

### F2 — Flag (5 patas) + endpoints HITL + snapshot en memoria

**Objetivo (1 frase).** Exponer el doctor detrás de la flag nueva default OFF con el patrón exacto de la
serie DevOps (guard 404, health aditivo, requires al master). **Valor:** activable 100% por UI, cero
regresión con OFF.

**Archivos:** editar `backend/services/harness_flags.py`; editar `backend/config.py`; editar
`backend/tests/test_harness_flags_requires.py`; editar `backend/api/devops.py`; editar
`backend/api/__init__.py`; crear `backend/api/devops_connections.py`; crear
`backend/tests/test_plan116_connections_endpoints.py` y `backend/tests/test_plan116_connection_doctor_flag.py`;
editar `backend/scripts/run_harness_tests.sh` y `backend/scripts/run_harness_tests.ps1`.

**Cambios exactos (anclar por símbolo; `config.py` y `harness_flags.py` tienen WIP concurrente — ver §8):**

1. `harness_flags.py` — (a) agregar `"STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED",  # Plan 116 — doctor de conexiones`
   al final de la tupla de la categoría `"devops"` (la que hoy termina con
   `STACKY_DEVOPS_ENV_SANDBOX_ENABLED`, `services/harness_flags.py:178-194`); (b) agregar el `FlagSpec`
   inmediatamente después del bloque del Plan 107 (`STACKY_DEVOPS_ENV_SANDBOX_ENABLED`):
   ```python
   # ── Plan 116 — Doctor de conexiones con remediación guiada ──
   FlagSpec(
       key="STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED",
       type="bool",
       label="Doctor de conexiones DevOps (Plan 116)",
       description=(
           "Plan 116 — Tira de salud de conexiones en el panel DevOps: diagnostica "
           "tracker (ADO/GitLab/Jira/Mantis), servidores registrados, CLIs de los "
           "runtimes y keyring con remediación paso a paso. Determinista (sin IA, "
           "sin costo). Solo corre con click del operador. Con OFF el panel queda "
           "idéntico a hoy."
       ),
       group="global",
       env_only=False,
       requires="STACKY_DEVOPS_PANEL_ENABLED",  # master del panel (R4 profundidad-1; NO encadenar a flags hijas)
   ),
   ```
   **PROHIBIDO** pasar `default=` (gotcha Plan 63: `default` explícito exige pertenencia a
   `_CURATED_DEFAULTS_ON` y este plan NO promueve el default — nace OFF).
2. `config.py` — junto a las demás flags DevOps (buscar `STACKY_DEVOPS_ENV_SANDBOX_ENABLED` y copiar su
   forma EXACTA de parseo, cambiando el default a `"false"`):
   `STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED: bool = os.getenv("STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED", "false") ...`
   (misma expresión de truthiness que la línea vecina; verificar leyendo esa línea, no inventar).
3. `tests/test_harness_flags_requires.py` — agregar al dict `_REQUIRES_MAP_FROZEN` (`:120`):
   `"STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 116` — sin esta
   arista el meta-test de requires falla (regla R4, memoria `harness-requires-r4-depth1`).
4. `api/devops.py` — en `_health_payload` agregar
   `"connection_doctor_enabled": bool(getattr(cfg, "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED", False)),  # Plan 116`
   (patrón idéntico a `section_doctor_enabled`, `api/devops.py:56`).
5. Crear `backend/api/devops_connections.py` (espejo de `api/devops_servers.py`):
   ```python
   """api/devops_connections.py — Plan 116: doctor de conexiones con remediación guiada.

   url_prefix="/devops/connections" → /api/devops/connections/... (§3.12 plan 87).
   Guard 404 si STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED=OFF. HITL: el chequeo corre
   SOLO por POST explícito del operador; GET devuelve el último snapshot (o never_run).
   """
   import threading

   from flask import Blueprint, jsonify, abort

   import config as _config
   from services import connection_doctor

   bp = Blueprint("devops_connections", __name__, url_prefix="/devops/connections")

   _SNAPSHOT: dict | None = None
   _SNAPSHOT_LOCK = threading.Lock()
   _STALE_AFTER_SECONDS = 300


   def _guard():
       if not getattr(_config.config, "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED", False):
           abort(404)


   @bp.get("/health")
   def health_route():
       _guard()
       with _SNAPSHOT_LOCK:
           snap = _SNAPSHOT
       if snap is None:
           return jsonify({"status": "never_run", "stale": False, "snapshot": None}), 200
       return jsonify({"status": "ready", "stale": _is_stale(snap), "snapshot": snap}), 200


   @bp.post("/check")
   def check_route():
       _guard()
       global _SNAPSHOT
       snap = connection_doctor.run_connection_check()
       with _SNAPSHOT_LOCK:
           _SNAPSHOT = snap
       return jsonify({"status": "ready", "stale": False, "snapshot": snap}), 200
   ```
   más `_is_stale(snap) -> bool` parseando `generated_at` (ISO con sufijo `Z`) contra
   `datetime.utcnow()` y `_STALE_AFTER_SECONDS`. El POST no exige body ⇒ NO aplica el guard
   `is_json` (no hay payload mutante que forjar; documentarlo en el docstring).
6. `api/__init__.py` — registrar espejando al plan 91 (`api/__init__.py:47,100`):
   `from .devops_connections import bp as devops_connections_bp  # Plan 116 — doctor de conexiones`
   y `api_bp.register_blueprint(devops_connections_bp)  # Plan 116 — url_prefix="/devops/connections" → /api/devops/connections/...`.
7. **Ratchet:** agregar los 5 archivos de test `test_plan116_*.py` a `HARNESS_TEST_FILES` en
   `backend/scripts/run_harness_tests.sh` Y `backend/scripts/run_harness_tests.ps1` (el meta-test
   `tests/test_harness_ratchet_meta.py` falla si no; memoria `stacky-ratchet-obliga-registrar-tests`).
8. **NO tocar `backend/harness_defaults.env`** (drift conocido con el deploy, memoria
   `harness-defaults-env-drift-devops-87-91`; su regeneración es del operador vía
   `deployment/export_harness_defaults.py`, fuera de este plan).

**Tests PRIMERO:**
- `tests/test_plan116_connection_doctor_flag.py` (espejar el estilo de `tests/test_plan107_flags.py`):
  1. `test_flag_registered_in_devops_category` — la key está en la categoría `devops` del registry.
  2. `test_flag_spec_bool_not_env_only_requires_panel` — type bool, `env_only is False`,
     `requires == "STACKY_DEVOPS_PANEL_ENABLED"`.
  3. `test_flag_default_off_in_config` — `config.Config` recién construido con env limpio ⇒ atributo False.
  4. `test_health_payload_has_connection_doctor_key` — `_health_payload()` contiene
     `connection_doctor_enabled` y refleja el valor de config (monkeypatch True/False).
- `tests/test_plan116_connections_endpoints.py` (Flask test client como los tests de plan 91/105;
  monkeypatch `config.config.STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED` y
  `services.connection_doctor.run_connection_check` → snapshot fijo de juguete; resetear
  `api.devops_connections._SNAPSHOT = None` en cada test):
  1. `test_endpoints_404_when_flag_off` — GET /health y POST /check ⇒ 404.
  2. `test_health_never_run` — flag ON, sin snapshot ⇒ `{"status":"never_run"}`.
  3. `test_check_stores_and_health_returns_same_snapshot` — POST ⇒ snapshot; GET ⇒ el MISMO dict.
  4. `test_health_marks_stale_after_ttl` — snapshot con `generated_at` 10 min atrás ⇒ `stale is True`.
  5. `test_check_never_hits_network_in_tests` — `run_connection_check` mockeado; assert llamado 1 vez
     (documenta que la ruta NO sondea sola nada más).

**Comandos:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
venv\Scripts\python.exe -m pytest tests/test_plan116_connection_doctor_flag.py -q
venv\Scripts\python.exe -m pytest tests/test_plan116_connections_endpoints.py -q
venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
venv\Scripts\python.exe -m pytest tests/test_harness_flags_requires.py -q
venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```
**Criterio binario:** 9 tests nuevos verdes + `test_harness_flags.py`, `test_harness_flags_requires.py`
y `test_harness_ratchet_meta.py` verdes (los 3 meta-tests protegen las 5 patas). Con flag OFF,
`curl /api/devops/connections/health` ⇒ 404.
**Flag:** `STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED` — **default OFF**, activable en Configuración →
Arnés, categoría DevOps (sub-tab del plan 33/86; cero pasos manuales fuera de la UI).
**Runtimes:** N/A directo (endpoints Flask); el contenido ya es paritario por F1.
Fallback: flag OFF ⇒ 404 y UI idéntica.
**Trabajo del operador:** ninguno (opt-in default off).

---

### F3 — Frontend: tira de salud + tarjetas de remediación (shell DevOps)

**Objetivo (1 frase).** Montar en el shell del panel DevOps la tira de chips de salud con
"Diagnosticar" HITL y tarjetas de remediación accionables. **Valor:** el "qué pasó y cómo lo arreglo"
visible en un click, con lenguaje visual profesional.

**Archivos:** editar `frontend/src/api/endpoints.ts`; crear
`frontend/src/components/devops/RemediationCard.tsx`; crear
`frontend/src/components/devops/ConnectionHealthStrip.tsx`; editar
`frontend/src/pages/DevOpsPage.tsx`; editar `frontend/src/components/devops/devops.module.css`
(SOLO clases nuevas al final); crear `frontend/src/components/devops/RemediationCard.test.tsx` y
`frontend/src/components/devops/ConnectionHealthStrip.test.tsx`.

**Cambios exactos:**

1. `endpoints.ts` — dentro del objeto existente `export const DevOps` (`frontend/src/api/endpoints.ts:3074`),
   agregar al final (tipos exportados a nivel de módulo, junto a los demás `export interface` del archivo):
   ```ts
   export interface ConnectionRemediationAction {
     kind: 'retry' | 'copy_command' | 'open_url' | 'goto_section' | 'none';
     command?: string; url?: string; section_id?: string;
   }
   export interface ConnectionRemediation {
     title: string; cause: string; steps: string[]; action: ConnectionRemediationAction;
   }
   export interface ConnectionDiagResult {
     target: string; target_label: string;
     group: 'tracker' | 'servers' | 'clis' | 'credentials';
     status: 'ok' | 'warn' | 'fail' | 'skip';
     code: string; detail: string; latency_ms: number | null;
     remediation: ConnectionRemediation | null;
   }
   export interface ConnectionsSnapshot {
     generated_at: string; duration_ms: number;
     results: ConnectionDiagResult[];
     summary: { ok: number; warn: number; fail: number; skip: number };
   }
   export interface ConnectionsHealthResponse {
     status: 'ready' | 'never_run'; stale: boolean; snapshot: ConnectionsSnapshot | null;
   }
   ```
   y en `DevOps`: `connectionsHealth: () => api.get<ConnectionsHealthResponse>("/api/devops/connections/health"),`
   `connectionsCheck: () => api.post<ConnectionsHealthResponse>("/api/devops/connections/check", {}),`.
   Además, en el tipo de retorno de `DevOps.health` agregar `connection_doctor_enabled?: boolean; // Plan 116`.
2. `RemediationCard.tsx` — componente presentacional puro:
   ```
   Props: { result: ConnectionDiagResult; onRetry?: () => void; onGotoSection?: (sectionId: string) => void }
   Render: div.remediationCard
     ├─ div.remediationCardTitle  → icono por status (✖ fail / ⚠ warn) + remediation.title + target_label
     ├─ div.remediationCause     → "Qué pasó: " + remediation.cause  (+ detail técnico en <details> colapsado)
     ├─ ol.remediationSteps      → un <li> por step
     └─ div.remediationActions   → botón según action.kind:
         retry        → "Reintentar"        → onRetry?.()
         copy_command → "Copiar comando"    → navigator.clipboard.writeText(action.command ?? '')
                                              y 2 s de feedback "Copiado ✓" (useState local)
         open_url     → "Abrir página"      → window.open(action.url, '_blank', 'noopener')
         goto_section → "Ir a la sección"   → onGotoSection?.(action.section_id ?? '')
         none         → (sin botón)
   Si result.remediation es null → no renderizar nada (return null).
   ```
3. `ConnectionHealthStrip.tsx` —
   ```
   Props: { onGotoSection: (sectionId: string) => void }
   Estado/data: useQuery(['devops-connections-health'], DevOps.connectionsHealth, { retry: false })
                + useMutation(DevOps.connectionsCheck, { onSuccess: (d) => queryClient.setQueryData(['devops-connections-health'], d) })
   Render: div.healthStrip
     ├─ 4 chips fijos (Tracker / Servidores / CLIs / Credenciales) → span.healthChip + modificador
     │    por PEOR status del grupo: fail→healthChipFail, warn→healthChipWarn,
     │    ok→healthChipOk, sin resultados o solo skip→healthChipSkip ("—")
     ├─ botón "Diagnosticar" (disabled + texto "Diagnosticando…" mientras isPending;
     │    mientras isPending los chips muestran span.skeletonBar)
     ├─ texto meta: "Último chequeo: <generated_at local> (<duration_ms> ms)" o
     │    "Nunca corrido — click en Diagnosticar" (estado never_run) · badge "desactualizado" si stale
     └─ panel expandible (useState open) listado de <RemediationCard> para cada result con
          status fail|warn, pasando onRetry={() => mutation.mutate()} y onGotoSection
   HITL: NINGÚN useEffect dispara connectionsCheck; solo el click.
   ```
4. `DevOpsPage.tsx` — 3 ediciones ancladas por símbolo:
   (a) en `DevOpsHealth` agregar `connection_doctor_enabled?: boolean; // Plan 116 — doctor de conexiones`;
   (b) extraer el handler de click de sub-tab a
   `const selectSection = (id: string) => { setActiveId(id); setMountedIds((prev) => new Set(prev).add(id)); };`
   y usarlo tanto en los botones de la barra como en el strip (buscar el `onClick` actual de los botones
   de sub-tab que hace `setActiveId` + agrega a `mountedIds` y reemplazarlo por `selectSection` —
   comportamiento idéntico, C10 montaje persistente intacto);
   (c) render del strip INMEDIATAMENTE ANTES de la barra de sub-tabs (el contenedor que mapea
   `DEVOPS_SECTIONS` a botones):
   `{ctx.health.connection_doctor_enabled === true && <ConnectionHealthStrip onGotoSection={selectSection} />}`.
   **Desvío declarado de §3.12:** el strip es UI de SHELL (transversal), no una sección; por eso NO entra
   en `DEVOPS_SECTIONS` y sí requiere esta única edición al shell. Gate por health key ⇒ OFF = idéntico.
5. `devops.module.css` — SOLO AGREGAR al final (no modificar clases existentes); usar EXCLUSIVAMENTE
   los tokens `var(--…)` que el archivo ya usa (leer sus primeras ~50 líneas y reusar esos nombres,
   p. ej. el token que usa `.textDanger { color: var(--danger); }` — riel de contraste dark theme,
   memoria `ui-dark-theme-contrast-harness-devops`): `.healthStrip`, `.healthChip`, `.healthChipOk`,
   `.healthChipWarn`, `.healthChipFail`, `.healthChipSkip`, `.remediationCard`, `.remediationCardTitle`,
   `.remediationCause`, `.remediationSteps`, `.remediationActions`, `.emptyState`, `.skeletonBar`
   (+ `@keyframes skeletonPulse`). Chips: pill con borde 1px, padding 2px 10px, font-size 0.85em.

**Tests PRIMERO (vitest — espejar imports/setup de `frontend/src/components/devops/RemoteConsoleSection.test.tsx`,
que es el patrón que YA corre en este repo; mockear `../../api/endpoints` con `vi.mock`):**
- `RemediationCard.test.tsx`:
  1. `renders title cause and steps` — DiagResult fail AUTH_401 de juguete ⇒ título, cause y 2 `<li>`.
  2. `copy_command writes clipboard` — mock `navigator.clipboard.writeText`; click ⇒ llamado con el comando.
  3. `retry calls onRetry` · 4. `null remediation renders nothing`.
- `ConnectionHealthStrip.test.tsx`:
  1. `never_run shows CTA and no chips colored` — mock connectionsHealth → never_run.
  2. `chips reflect worst status per group` — snapshot con tracker fail + clis ok ⇒ chip Tracker con clase
     `healthChipFail`, chip CLIs con `healthChipOk`.
  3. `check button triggers POST once` — click ⇒ `connectionsCheck` llamado exactamente 1 vez (HITL).
  4. `goto_section action bubbles up` — card CRED_MISSING ⇒ click "Ir a la sección" ⇒ callback con "servidores".

**Comandos:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/components/devops/RemediationCard.test.tsx
npx vitest run src/components/devops/ConnectionHealthStrip.test.tsx
npx tsc --noEmit
```
**Criterio binario:** 8 tests vitest verdes + `tsc --noEmit` 0 errores. Con
`connection_doctor_enabled !== true` el DOM de DevOpsPage no contiene `.healthStrip` (asserteable en el
test 1 del strip montando la page o por revisión del gate — el gate es la línea única de (c)).
**Flag:** gated por `connection_doctor_enabled` (health key de F2).
**Runtimes:** UI pura; los contenidos por-runtime vienen de F1 (chips CLIs muestran codex/claude/copilot).
Fallback: sin snapshot ⇒ estado "Nunca corrido" con CTA; error de red del GET ⇒ el strip muestra el
mensaje del error dentro de un `.remediationCard` genérico UNKNOWN (sin romper la página).
**Trabajo del operador:** ninguno (aparece solo si activó la flag en la UI).

---

### F4 — Piloto de integración: ServersSection con diagnóstico tipificado + estado vacío con CTA

**Objetivo (1 frase).** Que el botón "Probar conexión" existente de Servidores muestre la tarjeta de
remediación en vez del string crudo, y que la sección vacía guíe en vez de quedar muda. **Valor:**
la mejora es visible donde el operador YA aprieta botones hoy.

**Archivos:** editar `backend/api/devops_servers.py` (solo `test_route`); crear
`backend/tests/test_plan116_servers_test_diag.py`; editar
`frontend/src/components/devops/ServersSection.tsx`; crear
`frontend/src/components/devops/ServersSection.emptystate.test.tsx`.

**Cambios exactos:**

1. `api/devops_servers.py` → `test_route(alias)` (`:115-122`): conservar `{ok, detail}` EXACTOS y
   agregar de forma aditiva:
   ```python
   payload = {"ok": ok, "detail": detail}
   if getattr(_config.config, "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED", False):
       from services import connection_doctor
       code = ("" if ok else
               "DNS_FAIL" if detail.startswith("DNS:") else
               "TIMEOUT" if "timed out" in detail.lower() else "TCP_REFUSED")
       payload["diag"] = connection_doctor.build_result(
           target=f"server:{alias}", target_label=f"Servidor {alias}", group="servers",
           status="ok" if ok else "fail", code=code, detail=detail,
           fmt={"host": server["host"], "port": "3389", "timeout": "3"})
   return jsonify(payload), 200
   ```
   (El mapeo string→code es el MISMO de `probe_servers` en F1; mantenerlos idénticos.)
2. `ServersSection.tsx` — anclar por símbolos (archivo con WIP concurrente; NO usar números de línea):
   (a) el estado `testResults` (hoy `Record<string, { ok: boolean; detail: string }>`,
   `ServersSection.tsx:43`) pasa a `Record<string, { ok: boolean; detail: string; diag?: ConnectionDiagResult }>`;
   (b) donde hoy se renderiza `test.detail` con `styles.textSuccess/textDanger` (`:284-286`):
   si `test.diag && !test.ok` renderizar `<RemediationCard result={test.diag} onRetry={() => void handleTest(s.alias)} />`;
   en cualquier otro caso, EXACTAMENTE el render actual (flag OFF ⇒ `diag` nunca llega ⇒ byte-idéntico);
   (c) donde hoy `servers.length === 0` (`:240`) muestra su contenido actual, reemplazar por
   `<div className={styles.emptyState}>` con: título "Sin servidores registrados", línea
   "Registrá tu primer servidor para habilitar test de conexión, RDP 1-click y consola remota." y botón
   "Agregar servidor" que hace focus en el primer input del form de alta existente (vía `useRef` en ese
   input + `ref.current?.focus()` + `scrollIntoView({behavior:'smooth'})`).
   (d) tipar `diag` importando `type ConnectionDiagResult` desde `../../api/endpoints`.
3. `DevOpsServers.testConnection` en `endpoints.ts`: ampliar SOLO el tipo de respuesta con
   `diag?: ConnectionDiagResult` (aditivo).

**Tests PRIMERO:**
- Backend `tests/test_plan116_servers_test_diag.py` (client Flask; monkeypatch registry como hacen los
  tests del plan 91):
  1. `test_diag_absent_when_flag_off` — flag OFF (pero `STACKY_DEVOPS_SERVERS_ENABLED` ON) ⇒ respuesta
     sin key `diag` y `{ok, detail}` intactos.
  2. `test_diag_present_and_classified_when_flag_on` — flag ON + `test_connectivity`→`(False, "DNS: no resuelve x")`
     ⇒ `diag.code == "DNS_FAIL"` y `diag.remediation.steps` no vacío.
  3. `test_diag_ok_has_no_remediation` — `(True, "TCP 3389 OK")` ⇒ `diag.status=="ok"`, `remediation is None`.
- Frontend `ServersSection.emptystate.test.tsx` (mock de `../../api/endpoints` con `DevOpsServers.list`
  → `{servers: []}` y ctx mínimo `{health: {servers_enabled: true}, refetchHealth: () => {}}` — copiar
  el andamiaje de mocks de `RemoteConsoleSection.test.tsx`):
  1. `empty list renders emptyState with CTA` — aparece "Sin servidores registrados" y el botón.

**Comandos:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
venv\Scripts\python.exe -m pytest tests/test_plan116_servers_test_diag.py -q
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/components/devops/ServersSection.emptystate.test.tsx
npx tsc --noEmit
```
**Criterio binario:** 3 tests backend + 1 vitest verdes; tsc 0 err; y regresión: los tests existentes
del plan 91 (`venv\Scripts\python.exe -m pytest tests/test_plan91_servers.py -q` — verificar el nombre
real con `ls backend/tests | grep plan91` y correr TODOS los que matcheen) siguen verdes.
**Flag:** `STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED` (misma de F2) para `diag`; el estado vacío con CTA
es puro CSS/markup sin cambio de comportamiento ⇒ no requiere flag (cero riesgo funcional: mismo form,
mismo flujo).
**Runtimes:** N/A (servidores son runtime-agnósticos).
Fallback: flag OFF ⇒ render crudo actual, byte-idéntico.
**Trabajo del operador:** ninguno.

---

### F5 — Pulido profesional acotado: facelift del FlagGateBanner + accesibilidad de sub-tabs

**Objetivo (1 frase).** Unificar el lenguaje visual de las superficies de aviso existentes con el nuevo
sistema de tarjetas y hacer la barra de sub-tabs accesible por teclado. **Valor:** el panel se ve y se
opera como un producto profesional, sin tocar comportamiento.

**Archivos:** editar `frontend/src/components/devops/FlagGateBanner.tsx`; editar
`frontend/src/pages/DevOpsPage.tsx` (solo atributos ARIA de la barra); editar
`frontend/src/components/devops/devops.module.css` (clases nuevas de F3 reutilizadas; si falta alguna,
agregarla al final); crear `frontend/src/components/devops/FlagGateBanner.test.tsx`.

**Cambios exactos:**
1. `FlagGateBanner.tsx` — MISMA interfaz `FlagGateBannerProps` y MISMA lógica (`HarnessFlags.update`,
   estados `activating`/`error`, callback `onEnabled` — todo intacto, `FlagGateBanner.tsx:30-50`);
   cambiar SOLO el markup del `return` al layout de tarjeta: contenedor `styles.remediationCard`
   (en lugar de `styles.alertWarning` + estilos inline), título con `styles.remediationCardTitle`
   ("⚙ {flagLabel}"), cause con `styles.remediationCause` ({message}), pasos fijos en
   `ol.remediationSteps`: `<li>Esta sección está apagada por su flag.</li>`
   `<li>Activala con el botón (queda guardada en el arnés) o desde Configuración → Arnés.</li>`,
   y el botón existente dentro de `styles.remediationActions` (texto y disabled EXACTAMENTE como hoy).
   HITL intacto: nada se activa sin click.
2. `DevOpsPage.tsx` — en la barra de sub-tabs (el contenedor que mapea `DEVOPS_SECTIONS`): agregar
   `role="tablist"` al contenedor y a cada botón `role="tab"`, `aria-selected={activeId === s.id}`,
   `aria-controls={'devops-panel-' + s.id}`; al contenedor de cada sección montada,
   `id={'devops-panel-' + s.id}` y `role="tabpanel"`. Cero cambio de lógica/estado.
3. CSS: `.remediationActions button:focus-visible` y `[role="tab"]:focus-visible` con outline visible
   usando un token `var(--…)` existente del archivo (elegir el mismo que ya usen los botones si existe;
   si no, `outline: 2px solid currentColor; outline-offset: 2px;`).

**Tests PRIMERO** (`FlagGateBanner.test.tsx`, mismo andamiaje vitest que F3):
1. `renders label message and steps` — label, message y 2 `<li>` presentes.
2. `activate calls HarnessFlags.update and onEnabled` — mock `HarnessFlags.update`→`{ok:true}`;
   click ⇒ update llamado con `{[flagKey]: true}` y `onEnabled` llamado (protege el comportamiento
   PREVIO al facelift — escribir y correr este test ANTES de tocar el markup).
3. `shows error when update fails` — `{ok:false, error:"x"}` ⇒ texto "x" visible.

**Comandos:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/components/devops/FlagGateBanner.test.tsx
npx tsc --noEmit
```
**Criterio binario:** 3 vitest verdes (el 2 corrido ANTES y DESPUÉS del cambio de markup); tsc 0 err.
**Flag:** ninguna — es re-estilado sin cambio de comportamiento, protegido por el test 2 previo.
(El facelift NO se gatea: el banner conserva props, textos de botón y flujo; el riesgo es solo visual
y reversible con `git revert` del hunk.)
**Runtimes:** N/A. Fallback: N/A.
**Trabajo del operador:** ninguno.

---

### F6 — Verificación integral + cierre documental

**Objetivo (1 frase).** Correr TODO lo nombrado por el plan de una pasada, verificar la no-regresión de
las suites vecinas y sincronizar el encabezado de estado de este documento. **Valor:** cierre honesto
sin falsos verdes.

**Archivos:** este documento (`Stacky Agents/docs/116_PLAN_...md` — actualizar encabezado **Estado:** a
IMPLEMENTADO con fecha y hashes al terminar, riel de memoria `feedback_actualizar-estado-plan-en-doc`).

**Comandos (todos deben salir verdes; pegar el output en el reporte de implementación):**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
venv\Scripts\python.exe -m pytest tests/test_plan116_connection_doctor_core.py tests/test_plan116_connection_probes.py tests/test_plan116_connections_endpoints.py tests/test_plan116_connection_doctor_flag.py tests/test_plan116_servers_test_diag.py -q
venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
venv\Scripts\python.exe -m pytest tests/test_harness_flags_requires.py -q
venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
:: no-regresión vecina (verificar nombres reales con ls antes de correr):
venv\Scripts\python.exe -m pytest tests/test_plan91_*.py tests/test_plan105_*.py tests/test_plan107_flags.py tests/test_plan108_flags.py -q
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/components/devops/RemediationCard.test.tsx
npx vitest run src/components/devops/ConnectionHealthStrip.test.tsx
npx vitest run src/components/devops/ServersSection.emptystate.test.tsx
npx vitest run src/components/devops/FlagGateBanner.test.tsx
npx vitest run src/components/devops/RemoteConsoleSection.test.tsx
npx tsc --noEmit
```
**Criterio binario:** todos los comandos exit 0 (con la excepción DOCUMENTADA de fallas preexistentes
ajenas que ya estén en rojo en HEAD ANTES de empezar — demostrarlo con el mismo comando corrido sobre
el árbol sin los cambios del plan, patrón del plan 108).
**Flag/Runtimes/Operador:** N/A / N/A / ninguno.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Tests que tocan red real (flaky/lentos) | TODAS las sondas se mockean en origen (`services.local_diagnostics._probe_*`, `services.server_registry.*`); ningún test de este plan abre sockets. El chequeo real solo corre por click del operador. |
| El chequeo cuelga la UI | Timeout duro 5 s por sonda + `fut.result(timeout=…)` + ejecución paralela; el botón muestra estado "Diagnosticando…" y el strip nunca bloquea el render del panel. |
| Falsos rojos que asusten (p. ej. sin servidores registrados) | Grupos sin datos ⇒ chip neutro `healthChipSkip` ("—"), nunca `fail`. Copilot sin CLI ⇒ `skip` explícito. `CRED_MISSING`/`KEYRING_UNAVAILABLE` son `warn`, no `fail`. |
| Fuga de secretos en detalles/remediación | Los `detail` provienen de mensajes de excepción de clientes que NO incluyen tokens; se truncan a 300 chars; el catálogo jamás interpola credenciales (solo host/alias/org). Test manual en F6: buscar "PAT" en un snapshot real. |
| WIP concurrente en `config.py`, `harness_flags.py`, `ServersSection.tsx`, `FlagGateBanner.tsx` (git status actual los muestra modificados) | Anclar TODAS las ediciones por símbolo (no línea); commitear SOLO los hunks propios del plan (staging por hunk); PROHIBIDO `git add -A`/`git add .`/`stash`/`checkout --` (incidente previo, memoria `feedback_subagent-git-stash-risk`). |
| Gotcha flags: `default=` explícito rompe `test_default_known_only_for_curated` | El FlagSpec NUEVO no lleva `default=`; el default OFF vive en `config.py` (`"false"`). Meta-tests de F2 lo verifican. |
| Gotcha R4: `requires` encadenado | `requires="STACKY_DEVOPS_PANEL_ENABLED"` (master raíz, patrón plan 107 `harness_flags.py:2236`) + arista en `_REQUIRES_MAP_FROZEN`. |
| Doble prefijo de blueprint (gotcha plan 74) | `url_prefix="/devops/connections"` relativo a `api_bp` — espejo EXACTO del registro del plan 91 (`api/__init__.py:100`). |
| Snapshot en memoria se pierde al reiniciar backend | Aceptado y honesto: `GET /health` responde `never_run` y la UI ofrece el CTA. Persistir en DB queda fuera de scope (YAGNI). |
| `_check_tracker` de local_diagnostics manda gitlab al probe ADO | Este plan NO replica ese bug (sonda gitlab propia en F1) y NO modifica `local_diagnostics` (cero riesgo de regresión en la página Diagnóstico). |
| vitest/entorno frontend con gaps preexistentes | Espejar el andamiaje del test que YA corre (`RemoteConsoleSection.test.tsx`); si un gap de entorno preexistente bloquea un archivo, documentarlo con el error EXACTO (patrón plan 107 F4) sin marcarlo verde. |

## 7. Fuera de scope (explícito)

- Polling/monitoreo automático de conexiones (el monitoreo persistente es del plan 103, y solo para pipelines).
- Activación en lote de flags (plan 100), bootstrap de servidores (plan 101), publicar en un paso (plan 102).
- Doctores IA (plan 104) — este doctor es determinista; conviven y se complementan.
- Auto-fix de configuración (violaría HITL): el doctor NUNCA escribe config, solo guía.
- Tocar `GlobalConfigPage`/página de Diagnóstico existentes o `services/local_diagnostics.py`.
- Persistencia del snapshot en DB; historial de chequeos.
- Regenerar `backend/harness_defaults.env` (drift conocido, proceso del operador).
- Rediseño CSS de las secciones existentes más allá de lo listado en F4/F5.

## 8. Glosario (para modelos menores)

- **Tracker:** el sistema de tickets configurado (Azure DevOps, GitLab, Jira o Mantis).
- **Keyring:** almacén de credenciales de Windows usado por el registro de servidores (plan 91); los
  passwords JAMÁS se guardan en texto plano.
- **HITL (human-in-the-loop):** nada corre solo; toda acción la dispara un click del operador.
- **Flag del arnés / 5 patas:** una feature-flag registrada en `services/harness_flags.py` (FlagSpec +
  categoría), con default en `config.py`, expuesta en el health, gateando la UI, y con tests.
- **R4 profundidad-1:** una flag con `requires` debe apuntar a un master SIN `requires` propio, y la
  arista debe estar en `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py:120`).
- **Ratchet:** todo archivo de test backend nuevo se registra en `HARNESS_TEST_FILES` de
  `backend/scripts/run_harness_tests.sh` y `.ps1`, o `test_harness_ratchet_meta.py` falla.
- **§3.12:** contrato de extensión del panel DevOps (plan 87): secciones declarativas en
  `DEVOPS_SECTIONS`, health aditivo, rutas `/api/devops/<feature>/...`.
- **Snapshot:** resultado completo del último chequeo de conexiones, guardado en memoria del proceso.
- **DiagResult:** el dict tipificado del contrato §4 (un chequeo puntual + su remediación).

## 9. Orden de implementación

1. **F0** — catálogo + clasificadores (tests primero; sin red).
2. **F1** — sondas + agregador paralelo (tests con mocks en origen).
3. **F2** — flag 5 patas + endpoints + ratchet (meta-tests de flags/requires/ratchet verdes).
4. **F3** — endpoints.ts + RemediationCard + ConnectionHealthStrip + montaje en shell + CSS.
5. **F4** — piloto ServersSection (diag aditivo backend + tarjeta + estado vacío).
6. **F5** — facelift FlagGateBanner + ARIA de sub-tabs.
7. **F6** — verificación integral + actualización del encabezado de este doc.

Cada fase se commitea por separado (mensaje `feat(plan-116): F<N> <resumen>`), stageando SOLO los
archivos de la fase (por hunk donde haya WIP ajeno). Push: SIEMPRE manual del operador.

## 10. Definición de Hecho (DoD) global

- [ ] Los 5 archivos de test backend del plan (31 tests: 9 F0 + 10 F1 [incl. C4 no-fuga] + 9 F2
      [4 flag + 5 endpoints] + 3 F4 — el conteo exacto puede crecer, nunca bajar) verdes con el venv
      del repo, corridos POR ARCHIVO.
- [ ] `test_harness_flags.py`, `test_harness_flags_requires.py`, `test_harness_ratchet_meta.py` verdes
      (5 patas de la flag + arista R4 + ratchet).
- [ ] 12 tests vitest nuevos verdes (4 RemediationCard + 4 Strip + 1 ServersSection + 3 FlagGateBanner)
      + `RemoteConsoleSection.test.tsx` sin regresión + `npx tsc --noEmit` 0 errores.
- [ ] Con `STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED=false` (default): endpoints nuevos ⇒ 404;
      `POST /api/devops/servers/<alias>/test` responde EXACTAMENTE `{ok, detail}`; el DOM del panel no
      contiene `.healthStrip`; `FlagGateBanner` conserva props/flujo (test 2 de F5 verde pre y post).
- [ ] Con la flag ON (activada desde Configuración → Arnés): el strip aparece, "Diagnosticar" devuelve
      snapshot con los 4 grupos, y toda falla clasificable muestra tarjeta con causa + pasos + acción.
- [ ] Ningún test del plan abre sockets reales; ningún secreto aparece en snapshots ni logs.
- [ ] Paridad 3 runtimes verificable en el snapshot: entradas `cli:codex`, `cli:claude` y
      `runtime:copilot` (skip honesto) presentes.
- [ ] Encabezado de este doc actualizado a IMPLEMENTADO con commits, y reporte con outputs reales.
- [ ] `git status` final sin arrastrar WIP ajeno a los commits del plan.

---

## Resumen (5 líneas)

1. **Qué propone:** un doctor de conexiones DETERMINISTA para el panel DevOps — catálogo tipificado de 13
   códigos de falla (ADO/GitLab/Jira/Mantis, servidores, CLIs, keyring) con remediación paso a paso escrita
   en el plan, tira de chips de salud HITL en el shell, tarjetas accionables (reintentar/copiar comando/abrir
   URL/ir a sección), piloto en ServersSection, estado vacío con CTA y facelift del FlagGateBanner.
2. **Valor/KPI:** de errores crípticos (`TCP 3389: WinError...`) a "qué pasó + cómo arreglarlo" en 1 click;
   cobertura de remediación 100% verificada por test de invariante; cero costo LLM (complementa al doctor IA 104).
3. **Cero trabajo al operador:** flag única `STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED` default OFF activable
   desde la UI; con OFF, API y UI quedan byte-idénticas (guards 404 + gates por health key).
4. **3 runtimes:** feature runtime-agnóstica; la sonda de CLIs cubre codex y claude por PATH (+fallbacks npm)
   y reporta Copilot como `skip` honesto ("no requiere CLI local") — nunca un falso rojo.
5. **Cómo se construye:** 7 fases TDD (F0 núcleo puro → F6 verificación integral), sondas mockeadas sin red,
   reuso del sustrato real (`local_diagnostics._probe_*`, `server_registry.test_connectivity`, shell §3.12,
   patrón de flags plan 107) y anclas por símbolo en archivos con WIP concurrente.
