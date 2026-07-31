**Estado:** PROPUESTO v1 · **Autor:** StackyArchitectaUltraEficientCode · **Fecha:** 2026-07-31
**Fuente:** auditoría forense GitLab self-hosted del 2026-07-31 (caso real RIPLEY contra `srvcgit01.imsolutions.local`), con reproducción empírica de la causa raíz **y del remedio** en el venv del repo.
**Advertencia sobre este header:** el campo `Estado:` **NO es evidencia**. Verificá siempre con `git log --all --grep="plan-276"` y con los comandos de F0.

# Plan 276 — GitLab self-hosted de punta a punta: TLS que coexiste, sync real y tickets en el grafo

## 1. Objetivo

Cerrar al 100% la integración con **GitLab self-hosted** hasta que **la lista de tickets se vea en el grafo**, en una sola corrida. Hoy un proyecto GitLab correctamente configurado (RIPLEY, `https://srvcgit01.imsolutions.local`, 1009 issues, 53 abiertos) muere en el handshake TLS; y **aunque el TLS se arreglara, el operador seguiría igual de bloqueado**, porque no existe ningún camino que traiga issues de GitLab a la BD de Stacky y el grafo lee **solo** la BD local (`backend/api/tickets.py:629`, `session.query(Ticket)`).

Este plan hace las tres cosas juntas porque cualquiera sola deja al operador en el mismo lugar:

1. **TLS que coexiste.** El backend inyecta `truststore` para todo el proceso (`backend/app.py:24-28`) — obligatorio, porque la red corporativa tiene inspección TLS de Zscaler — y eso **anula** el `verify=<bundle>` que ya viaja bien hasta el cliente de GitLab. Se monta un `HTTPAdapter` con un contexto **OpenSSL genuino** solo en la sesión de GitLab: ADO/Jira/LLM siguen por truststore, GitLab interno pasa por OpenSSL con el bundle. **Remedio ya validado en vivo.**
2. **Sync real GitLab → BD.** `backend/api/tickets.py:717-721` levanta `CapabilityUnavailable("tracker.sync.full")` con el texto literal *"Plan 220 lo implementa"*, y **el plan 220 nunca se escribió** (verificado: no existe `220_*` en `docs/`). Este plan salda esa deuda.
3. **Que los errores dejen de mentir.** El botón "Probar conexión" devuelve verde con el listado roto, el check se llama "gitlab alcanzable" sin haber hecho ping, y el sync devuelve un 500 mudo que esconde una carencia declarada.

**KPI / impacto esperado** (medible con los comandos de cada fase, sin telemetría nueva):

| Métrica | Hoy (medido 2026-07-31) | Objetivo |
|---|---|---|
| `GET /api/v4/version` contra srvcgit01 **con truststore inyectado** | `SSLError` | **HTTP 401** (TLS sano) |
| `GET https://gitlab.com/api/v4/version` por la sesión normal (Zscaler) | HTTP 401 | **HTTP 401** (sin cambio — no se rompe) |
| Issues de GitLab en la BD de Stacky tras apretar "Sincronizar" | **0** (capacidad inexistente) | **N > 0** (53 abiertos en RIPLEY) |
| `GET /api/tickets/hierarchy?project=RIPLEY` | `{"epics": [], "orphans": []}` | `epics` + `orphans` **no vacíos** |
| Sub-veredictos que reporta el check de tracker GitLab | **1** (nombre fijo "alcanzable") | **4** (TLS / auth / proyecto legible / N ítems) |
| Rutas de `GitLabClient` que degradan la verificación TLS en silencio | **2** (`tls_pinning.py:103-107` y `:118-119`, fallan ABIERTO) | **0** |
| Parches globales a `urllib3` hechos por código de Stacky | **2** (`tls_pinning.py:79-80`) | **0** |
| Tests de TLS que corren con `truststore.inject_into_ssl()` aplicado | **0 de 27** | **100 %** de los nuevos |

**Flags nuevas: 3, las tres `default=True`** (§3.4). Ninguna cae en las categorías de excepción.

---

## 2. Por qué ahora / gap que cierra

### 2.1 La deuda del "Plan 220" fantasma

`backend/api/tickets.py:717-721`, literal:

```python
raise CapabilityUnavailable(
    "tracker.sync.full", provider.name,
    reason="el sync de ítems de este tracker todavía no está implementado",
    workaround="Plan 220 lo implementa; mientras tanto usá un proyecto Azure DevOps.",
)
```

`backend/services/provider_capabilities.py:249` lo declara ausente en el registro de capacidades: `"tracker.sync.full": _a("api/tickets.py:692")` (la ruta del comentario ya quedó desfasada: hoy es `:700`). El plan 218 construyó **la degradación declarada** (que el hueco se vea en vez de reventar) y delegó **el relleno del hueco** a un plan 220 que nunca existió. Los planes 259 (alta de proyecto GitLab), 266 y 270 (cierre real en ADO y GitLab) siguieron construyendo alrededor del hueco sin taparlo. Este plan lo tapa.

### 2.2 Por qué arreglar solo el TLS no alcanza

El cableado del `ca_bundle` **ya está completo y correcto** — se verificó pata por pata en esta auditoría:

| Pata | Anclaje | Estado |
|---|---|---|
| Tipo del formulario | `frontend/src/types.ts:284` y `:340` | OK |
| Alta | `NewProjectModal.tsx:55`, `:858-859` | OK |
| Edición | `EditProjectModal.tsx:48`, `:801-802` | OK |
| Escritura | `backend/project_manager.py:641`, `:676-677` | OK |
| Echo-back | `backend/api/projects.py:187` | OK |
| Transporte por proyecto | `services/project_context.py:66-79` (campo `ca_bundle`) y `:266` (se puebla) | OK |
| Los 3 constructores de `GitLabClient` | `services/gitlab_provider.py:67-69`, `api/global_config.py:353`, `services/local_diagnostics.py:191-200` | OK |
| El `verify=` llega a `requests` | `services/gitlab_client.py:190` | OK |

Y aun así **falla**. El bundle viaja, llega, se aplica — y no sirve. Por eso este plan no agrega una sexta pata de cableado: ataca el mecanismo que lo anula. Y por eso incluye el sync: con el TLS arreglado y sin sync, `GET /api/tickets/hierarchy` sigue devolviendo `{"epics": [], "orphans": []}`, porque `api/tickets.py:629` consulta `session.query(Ticket)` y nadie escribe filas de GitLab ahí.

### 2.3 Causa raíz, probada

`backend/app.py:24-28` ejecuta `truststore.inject_into_ssl()` al importar. Eso reemplaza `ssl.SSLContext` **para todo el proceso** (`truststore/_api.py:34-46`), y también la referencia propia de urllib3 (`urllib3.util.ssl_.SSLContext`). A partir de ahí la verificación de cadena la hace **Windows CryptoAPI**, no OpenSSL. Mecánica leída en `truststore/_windows.py`:

- **`:366-371`** — `verify_flags` se lee **solo** para CRL (`VERIFY_CRL_CHECK_CHAIN` / `VERIFY_CRL_CHECK_LEAF`). `VERIFY_X509_PARTIAL_CHAIN` **no se consulta nunca** ⇒ bajo truststore el pin de hoja es **INERTE**, y con él todo `services/tls_pinning.py`.
- **`:373-384`** — primer intento contra las raíces del sistema. La emisora `CN=imsolutions.local, O=PFSTechSL` **no está** en el store de Windows (barrido `ROOT`+`CA` con `ssl.enum_certificates`: 0 hits) ⇒ falla.
- **`:385-403`** — segundo intento con los certs del `verify=`, obtenidos con **`ssl_context.get_ca_certs(binary_form=True)`** (`:390-392`).
- **`:404-406`** — `# Raise the original error, not the new error.` + `raise e from None`: re-lanza el error **original de Windows**, por eso el mensaje que ve el operador no menciona el bundle aunque el bundle sí haya viajado.

**El detalle que cierra el caso** (descubierto en esta auditoría, medido): `get_ca_certs()` **omite los certificados que no son CA**. Y el certificado que hace falta es exactamente **una hoja**:

```
ca-bundle-migrador.pem   237.127 bytes  119 bloques CERTIFICATE
   idx=118  CN='srvcgit01.imsolutions.local'  O='Ubimia'  <- emisor CN='imsolutions.local'  notAfter=Jun 14 2028
srvcgit01-ca.pem           1.912 bytes    1 bloque
   idx=0    CN='srvcgit01.imsolutions.local'  O='Ubimia'  <- emisor CN='imsolutions.local'  notAfter=Jun 14 2028
```

Cargados en un contexto OpenSSL:

```
ca-bundle-migrador.pem -> cert_store_stats() = {'x509': 119, 'crl': 0, 'x509_ca': 118}   get_ca_certs() = 118
srvcgit01-ca.pem       -> cert_store_stats() = {'x509':   1, 'crl': 0, 'x509_ca':   0}   get_ca_certs() =   0
```

⇒ Con `ca-bundle-migrador.pem`, truststore intenta la cadena con **118 CAs que no incluyen la hoja** y falla. Con `srvcgit01-ca.pem`, `get_ca_certs()` devuelve **lista vacía**, el `if custom_ca_certs:` de `:393` es falso y truststore **ni siquiera intenta** el segundo camino (`:407-408`, `raise`). Los dos caminos quedan mecánicamente explicados, y ninguno tiene que ver con que el bundle "no llegue".

Matriz TLS medida (`GET /api/v4/version` sin token; **401 = TLS sano**):

| Escenario | Resultado |
|---|---|
| sin truststore + bundle **sin** pin de hoja | `SSLError` |
| sin truststore + bundle **con** pin de hoja (`VERIFY_X509_PARTIAL_CHAIN`) | **HTTP 401** |
| **con** truststore + cualquier `verify=` | `SSLError` (el mensaje en español que ve el operador) |

**Truststore no se puede sacar.** `gitlab.com` llega firmado por `Zscaler Intermediate Root CA`: con `verify=True` sobre certifi da `SSLError`, con truststore da 401. Truststore es **necesario** para ADO/Jira/APIs de LLM y **letal** para el GitLab interno. La solución tiene que hacerlos coexistir **por conexión**.

### 2.4 Trabajo en vuelo sobre el que este plan construye (no lo tira)

Hay cambios **sin commitear** en el árbol: nuevo `backend/services/tls_pinning.py` + 5 tests, y modificaciones en `api/global_config.py`, `api/projects.py`, `project_manager.py`, `services/connection_doctor.py`, `services/gitlab_client.py`, `services/gitlab_provider.py`, `services/local_diagnostics.py`, `services/project_context.py`, `services/tracker_provider.py`, `tools/migrar_mantis_gitlab/destination_writer.py`, `EditProjectModal.tsx`, `NewProjectModal.tsx`, `types.ts`.

Ese trabajo **es correcto y se conserva**: dejó las 8 patas del cableado en verde y los 5 tests están registrados en los DOS ratchets (`scripts/run_harness_tests.sh:228-232`, `scripts/run_harness_tests.ps1:221-225`). Lo que este plan corrige es que **esos 27 tests verdes conviven con el bug**, porque ninguno corre con truststore inyectado (§7, F10).

---

## 3. Principios y guardarraíles

### 3.1 Rieles del producto (no negociables)

- **Human-in-the-loop.** El sync es **on-demand**: se dispara cuando el operador aprieta "Sincronizar". Este plan **no** agrega polling, daemon, barrido ni prefetch. Nada decide por el operador.
- **Mono-operador sin auth real.** No se toca identidad, sesión ni permisos. No se construye RBAC.
- **Toda config del operador va por UI.** No se agrega ninguna variable de entorno nueva de operador. `STACKY_GITLAB_CA_BUNDLE` ya existe, ya es gestionada por UI (`api/global_config.py:87`, `_MANAGED_KEYS`) y ya tiene campo en el modal ("Certificado de la empresa").
- **Backward-compatible.** Para proyectos **Azure DevOps el comportamiento es byte-idéntico**: el adapter se monta solo cuando hay bundle y solo en la sesión de GitLab; el ruteo de sync solo se activa cuando `tracker_type != "azure_devops"`.

### 3.2 Prohibiciones duras de este plan

| Prohibido | Por qué |
|---|---|
| `truststore.extract_from_ssl()` | Es **global al proceso** (`truststore/_api.py:66-74`) y el backend es multi-hilo — `services/connection_doctor.py:374` corre 4 probes en `ThreadPoolExecutor`. Race garantizada: otro hilo hace un `GET` a ADO mientras truststore está extraído. |
| `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE` / `CURL_CA_BUNDLE` | Globales al proceso. Ya mataron una corrida del migrador **después de 1009 issues**. El propio `tls_pinning.py:9-16` documenta por qué. |
| `verify=False` | Desactiva la verificación. Nunca. |
| Parchear `urllib3.util.ssl_.create_urllib3_context` | Es compartido por todo el proceso: apenas el TLS de GitLab funcione, empieza a debilitar la verificación de ADO/Jira/LLM (P1-5). El pin vive **solo** en el `ssl_context` del adapter. |
| Flipear el default de `STACKY_TICKETS_PROVIDER_ENABLED` | Reenruta ~18 call sites de `api/tickets.py` de golpe y rompe los tests de origen del plan 70. F5 usa una resolución local, con radio de impacto de una función. |

### 3.3 Testing (rieles duros del repo, verificados en esta corrida)

- **Backend:** tests en `Stacky Agents/backend/tests/`, corridos **por archivo** con el venv del repo.

  > **TRAMPA DE ENTORNO — hay DOS venvs en el mismo checkout, verificado hoy:**
  > `backend\.venv` (**con punto**) = **Python 3.13.5** ⇒ **es el correcto, usar siempre este**.
  > `backend\venv` (**sin punto**) = Python 3.11.9, viejo ⇒ **nunca**.
  > Un prompt o un plan que diga "backend/venv" a secas está citando el viejo: corregirlo, no
  > asumir que es un typo inofensivo. Ruta absoluta del intérprete de este plan:
  > `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe`
  > *(Toda la evidencia técnica de este plan —`RecursionError`, `cert_store_stats`, ausencia de
  > `cryptography`— se re-verificó en **los dos** intérpretes y da **idéntica** en ambos.)*
- **Todo test nuevo se registra en los DOS ratchets** (`backend/scripts/run_harness_tests.sh` y `.ps1`), que tienen **sintaxis distinta** y de los cuales el meta-test parsea **solo el `.sh`**. El ratchet exige que la ruta **exista** y **no admite rutas con espacios** (por eso los 10 archivos nuevos viven en `backend/tests/`, sin espacios). Hay un **tercer** punto: `backend/tests/harness_ratchet_allowlist.txt` — un `.py` nuevo en `backend/tests/` que no esté ni en la lista del ratchet ni en la allowlist rompe `test_harness_ratchet_meta.py`. Este plan registra en los ratchets, así que la allowlist **no** se toca.
- **`pytest tests` completo NO es un veredicto** (contaminación cruzada conocida, miles de errores de SQLAlchemy). El gate es por archivo.
- **`pytest -k` sin match devuelve exit 0**: cada fase exige el **conteo de seleccionados**, no solo el exit code.
- **Frontend: NO hay RTL ni jsdom.** Prohibido montar componentes React. Toda lógica testeable va en `.ts` puro; lo visual se valida con smoke manual descripto paso a paso. Vitest **por archivo** (contaminación por orden). `api.*` lanza en non-2xx ⇒ usar `rawGet`/`rawPost` si se necesita el body del error.
- **El gate se corre CONTRA el defecto.** Cada fase declara el ROJO esperado **antes** del fix.

### 3.4 Flags nuevas (3, todas `default=True`)

| Flag | Tipo | Default | Qué protege | Por qué nace ON |
|---|---|---|---|---|
| `STACKY_GITLAB_TLS_ADAPTER_ENABLED` | bool | **True** | F1+F2: contexto OpenSSL genuino montado en la sesión de GitLab | Corrige una conexión rota. Es **solo lectura** (abrir un socket TLS y leer). No quema tokens en reposo (no hay loop ni modelo), no escribe en ningún sistema del operador. Con OFF vuelve el `verify=` de hoy. |
| `STACKY_TRACKER_PROBE_STRICT_ENABLED` | bool | **True** | F4: veredicto de 4 sub-checks en lugar de un nombre que afirma | **Solo lectura**: leer, calcular y mostrar. Ninguna de las dos categorías de excepción aplica. |
| `STACKY_GITLAB_SYNC_ENABLED` | bool | **True** | F5: sync GitLab → BD de Stacky | Escribe en **la BD de Stacky**, no en un sistema del operador, y se dispara **on-demand** con el botón "Sincronizar". No hay polling ni sync de fondo (eso sí caería en la categoría A y obligaría a OFF). |

Ninguna nace OFF. Ninguna es config de operador (son flags del arnés, no aparecen como decisión en el alta de proyecto).

**Puntos de registro de cada flag nueva** (replicar exactamente lo que hace `STACKY_CAPABILITY_DEGRADATION_ENABLED`, que es la flag reciente más parecida):

1. `backend/config.py` — la declaración `os.getenv(...)`, que es el **default efectivo**. Patrón exacto a copiar (`config.py:1320-1322`), con `"true"` como default:
   ```python
   STACKY_GITLAB_TLS_ADAPTER_ENABLED: bool = os.getenv(
       "STACKY_GITLAB_TLS_ADAPTER_ENABLED", "true"
   ).lower() in ("1", "true", "yes")
   ```
2. `backend/services/harness_flags.py` — un `FlagSpec(...)` dentro de `FLAG_REGISTRY` (`:544`; hoy hay **437** `FlagSpec(` en 6617 líneas). Copiar la forma de `:5457-5469` (`key`, `type="bool"`, `default=True`, `label`, `description`, `group="global"`).
3. `backend/services/harness_flags.py` — `_CATEGORY_KEYS` (`:120`), categoría **`paridad_proveedores`** (`:526-536`), donde ya viven las flags de GitLab/plan 218/259/270. Sin esto, `test_every_registry_flag_is_categorized` rompe CI a propósito.
4. `_CURATED_DEFAULTS_ON` — localizar con `grep -n "_CURATED_DEFAULTS_ON" backend/services/harness_flags.py` y agregar la key (las 3 son default ON).
5. `PLAIN_HELP` — localizar con `grep -n "PLAIN_HELP" backend/services/harness_flags.py`; **límite de 240 caracteres** por entrada.
6. `deployment/harness_defaults.env` — regenerar con el generador que vive en `deployment/` (`grep -rn "harness_defaults" deployment/`), nunca a mano.

**Regla de binding:** con `import config` se lee `config.config.X`; con `from config import config` se lee `config.X`. En `backend/app.py` ya es la **instancia** (ver el comentario de `app.py:884-886`).

### 3.5 Paridad de los 3 runtimes

Este plan **no toca ninguna superficie que dependa del runtime**: cero prompts, cero `.agent.md`, cero tools de agente, cero llamadas a modelo. Todo es Python de backend, TypeScript de frontend y tests. **Codex CLI, Claude Code CLI y GitHub Copilot Pro** aplican el mismo diff, corren los mismos comandos y obtienen el mismo resultado. La paridad es **estructural**, no declarada: no hay ninguna rama por runtime que pudiera divergir, y por eso ninguna fase necesita fallback por runtime. Cada fase lo repite en una línea para que quede explícito.

### 3.6 Reusar, no reinventar

- El bundle por conexión (`verify=`) y la resolución de rutas ya existen en `services/tls_pinning.py`: se **conserva** `resolver_ca_bundle` y se **endurece** `preparar_verificacion`; se **elimina** solo el parche global de urllib3.
- El puerto `TrackerProvider` y `GitLabTrackerProvider.fetch_open_items` ya existen: F5 los **consume**, no los reescribe.
- La degradación declarada del plan 218 (`CapabilityUnavailable` + envelope) ya existe: F6 la **arregla**, no la reemplaza.
- El registro de capacidades (`services/provider_capabilities.py`) ya existe: F5 actualiza la entrada de `tracker.sync.full`, no crea un registro paralelo.

---

## 4. Fases

> **Orden obligatorio:** F1 → F2 son prerequisito de todo lo demás (sin TLS no hay ninguna llamada real). F5 depende de F2. F6 depende de F5. F7 depende de F5.

---

### F0 — Línea base: reproducir el defecto y congelar el "antes"

**Objetivo:** dejar registrado, con comandos reales, el estado ANTES de tocar nada. **Valor:** sin esto, cualquier fase puede marcarse verde por casualidad. **No se crea ni edita ningún archivo.**

Todos los comandos usan `$PY` = `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe` (**con punto** — ver la trampa de los dos venvs en §3.3) y se corren desde `Stacky Agents\backend`.

**1. Confirmar el entorno (medido hoy; si difiere, re-anclar antes de seguir):**
```
$PY = "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe"
& $PY -c "import sys, requests, urllib3, truststore; print(sys.version); print(requests.__version__, urllib3.__version__, truststore.__version__)"
```
Esperado: `3.13.5`, `2.32.3 2.7.0 0.10.4`.
Control de que NO se agarró el venv viejo: `& $PY --version` debe decir **3.13.5**, no 3.11.9.

**2. Confirmar que NO hay con qué generar certificados** (determina el diseño del test hermético, §5 regla 6):
```
& $PY -c "import cryptography" ; if (-not $?) { "cryptography AUSENTE (esperado)" }
Get-Command openssl -ErrorAction SilentlyContinue
```
Esperado: `ModuleNotFoundError: No module named 'cryptography'` y `openssl` **no** en PATH.

**3. Reproducir la trampa del `RecursionError`** (es el fallo que va a encontrar un adapter ingenuo; ver §6):
```
& $PY -c "
import ssl, truststore
Orig = ssl.SSLContext
truststore.inject_into_ssl()
print('Orig en el MRO de truststore?', Orig in ssl.SSLContext.__mro__)
c = Orig(ssl.PROTOCOL_TLS_CLIENT)
try:
    c.verify_mode = ssl.CERT_REQUIRED
    print('SIN TRAMPA')
except RecursionError:
    print('RecursionError REPRODUCIDO')
"
```
Esperado: `Orig en el MRO de truststore? True` y `RecursionError REPRODUCIDO`.

**4. Confirmar el contenido de los dos `.pem`** (la hoja, no la CA):
```
& $PY -c "
import ssl, tempfile, os, re
B = re.compile(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----\n?', re.S)
for n in ('ca-bundle-migrador.pem','srvcgit01-ca.pem'):
    p = os.path.join(r'..\deployment', n)
    bl = B.findall(open(p, encoding='utf-8', errors='replace').read())
    print(n, os.path.getsize(p), 'bytes,', len(bl), 'bloques')
"
```
Esperado: `ca-bundle-migrador.pem 237127 bytes, 119 bloques` y `srvcgit01-ca.pem 1912 bytes, 1 bloques`.

**5. Confirmar que `get_ca_certs()` es ciego a la hoja** (el gate que NO hay que usar):
```
& $PY -c "
import ssl
c = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
c.load_verify_locations(cafile=r'..\deployment\ca-bundle-migrador.pem')
print('stats', c.cert_store_stats(), 'get_ca_certs', len(c.get_ca_certs()))
"
```
Esperado: `stats {'x509': 119, 'crl': 0, 'x509_ca': 118} get_ca_certs 118`.
*(Sin truststore inyectado `ssl.SSLContext` es la genuina y `cert_store_stats()` responde. Con truststore inyectado lanza `NotImplementedError` — ver F1.)*

**6. Confirmar los 5 anclajes de defecto que las fases van a corregir:**
```
Select-String -Path api\tickets.py -Pattern "Plan 220 lo implementa"
Select-String -Path api\global_config.py -Pattern 'ok = bool\(checks\["auth"\]'
Select-String -Path api\errors.py -Pattern 'payload.setdefault\("ok", True\)'
Select-String -Path services\tls_pinning.py -Pattern "_u3ssl.create_urllib3_context = _con_partial_chain"
Select-String -Path services\tracker_provider.py -Pattern "GitLabTrackerProvider\(project=project\)"
```
Esperado: **1 coincidencia cada uno**, en `tickets.py:720`, `global_config.py:382`, `errors.py:82`, `tls_pinning.py:79`, `tracker_provider.py:149`.

**7. Confirmar que el grafo está vacío para RIPLEY** (con el backend arriba y RIPLEY activo):
```
curl.exe -s "http://localhost:5000/api/tickets/hierarchy?project=RIPLEY"
```
Esperado hoy: `{"epics":[],"orphans":[]}`.

**Criterio de aceptación (binario):** los 7 comandos devuelven exactamente los valores citados. Si alguno difiere, **detenerse** y re-anclar esa fase antes de seguir.

**Flag:** ninguna. **Impacto por runtime:** ninguno (solo lectura, idéntico en los 3). **Trabajo del operador: ninguno.**

---

### F1 — Un contexto SSL OpenSSL genuino, inmune a truststore

**Objetivo:** construir un `ssl.SSLContext` **real de OpenSSL** que sobreviva a `truststore.inject_into_ssl()`, sin tocar nada global. **Valor:** es la pieza única sobre la que se apoya todo el resto; aislada en un módulo propio, es testeable sin red.

**Archivo a crear:** `Stacky Agents/backend/services/tls_openssl_context.py`
**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan276_tls_context.py`

#### F1.1 — Tests PRIMERO

```python
"""tests/test_plan276_tls_context.py — Plan 276 F1.

REGLA ANTIFALSO-VERDE #1: producción inyecta truststore (backend/app.py:24-28).
Un test de TLS que no lo inyecte NO prueba producción: los 27 tests verdes de
GitLab que ya existen conviven con el bug por exactamente esto.
La inyección va a nivel de MÓDULO, ANTES de importar lo que se prueba.
"""
import ssl
import pytest

_CLASE_SSL_ANTES = ssl.SSLContext
import truststore                                    # noqa: E402
truststore.inject_into_ssl()
assert ssl.SSLContext is not _CLASE_SSL_ANTES, (
    "truststore no se inyectó: este archivo NO está probando producción"
)

from services import tls_openssl_context as toc      # noqa: E402

BUNDLE = r"N:\GIT\RS\STACKY\Stacky\Stacky Agents\deployment\ca-bundle-migrador.pem"


def test_el_entorno_de_test_replica_produccion():
    """Gate de la regla #1: si esto falla, ningún otro test de este archivo vale."""
    assert ssl.SSLContext.__module__ == "truststore._api"


def test_recupera_la_clase_ssl_original_pese_al_inject():
    original = toc.clase_ssl_context_original()
    assert original.__module__ == "ssl" and original.__name__ == "SSLContext"
    assert original in ssl.SSLContext.__mro__


def test_setear_verify_mode_no_lanza_recursion_error():
    """LA TRAMPA. Un contexto construido con la clase original SIN las
    propiedades delegadas lanza RecursionError acá (verificado en F0 paso 3).
    Este test es el gate corrido CONTRA el defecto."""
    ctx = toc.crear_contexto_openssl(BUNDLE)
    ctx.verify_mode = ssl.CERT_REQUIRED              # no debe lanzar
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_el_contexto_no_es_de_truststore():
    ctx = toc.crear_contexto_openssl(BUNDLE)
    assert not any(m.__module__.startswith("truststore") for m in type(ctx).__mro__), (
        f"el contexto es de truststore: {type(ctx).__mro__}"
    )
    # discriminador independiente: truststore._api.SSLContext.cert_store_stats
    # lanza NotImplementedError (truststore/_api.py:195); el genuino responde.
    assert isinstance(ctx.cert_store_stats(), dict)


def test_el_bundle_llega_a_openssl_incluida_la_hoja():
    """get_ca_certs() OMITE los certs que no son CA — y el que hace falta es una
    HOJA. Por eso el gate es cert_store_stats(), no get_ca_certs()."""
    ctx = toc.crear_contexto_openssl(BUNDLE)
    stats = ctx.cert_store_stats()
    assert stats["x509"] == 119, f"certs cargados: {stats}"
    assert stats["x509"] - stats["x509_ca"] == 1, (
        f"la HOJA de srvcgit01 no entró al store: {stats}"
    )
    assert len(ctx.get_ca_certs()) == 118, "control: get_ca_certs es ciego a la hoja"


def test_el_pin_de_hoja_y_la_verificacion_conviven():
    ctx = toc.crear_contexto_openssl(BUNDLE)
    assert ctx.verify_flags & ssl.VERIFY_X509_PARTIAL_CHAIN
    assert ctx.verify_mode == ssl.CERT_REQUIRED, "la verificación NO se debilita"
    assert ctx.check_hostname is True, "check_hostname sigue activo"
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2


def test_no_muta_nada_global():
    """P1-5: el pin vive en el contexto, no en urllib3 ni en el módulo ssl."""
    import urllib3.util.ssl_ as u3ssl
    antes_ssl = ssl.SSLContext
    antes_u3 = u3ssl.create_urllib3_context
    toc.crear_contexto_openssl(BUNDLE)
    assert ssl.SSLContext is antes_ssl, "se tocó ssl.SSLContext"
    assert u3ssl.create_urllib3_context is antes_u3, "se parcheó urllib3 (prohibido)"


def test_sin_bundle_devuelve_none_y_no_construye_nada():
    """Sin bundle NO se monta adapter: la sesión sigue por truststore (Zscaler)."""
    assert toc.crear_contexto_openssl(None) is None
    assert toc.crear_contexto_openssl("") is None


def test_ruta_inexistente_no_se_ignora_en_silencio():
    """P0-2: fallar ABIERTO está prohibido."""
    with pytest.raises(toc.CaBundleInvalido):
        toc.crear_contexto_openssl(r"C:\ruta\que\no\existe.pem")
```

**Comando y ROJO esperado ANTES del fix (9 casos, todos fallan por `ModuleNotFoundError`):**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest tests\test_plan276_tls_context.py -v
```

#### F1.2 — Implementación

`Stacky Agents/backend/services/tls_openssl_context.py`:

```python
"""services/tls_openssl_context.py — contexto SSL OpenSSL GENUINO por conexión.

POR QUÉ EXISTE: backend/app.py:24-28 llama truststore.inject_into_ssl(), que
reemplaza ssl.SSLContext para TODO el proceso. Truststore es NECESARIO (la red
tiene inspección TLS de Zscaler) y LETAL para el GitLab interno: verifica por
Windows CryptoAPI, ignora VERIFY_X509_PARTIAL_CHAIN (truststore/_windows.py:366-371)
y busca los certs del bundle con get_ca_certs(), que OMITE los que no son CA — y
el cert que hace falta es la HOJA de srvcgit01. Este módulo devuelve un contexto
OpenSSL de verdad para montarlo SOLO en la sesión de GitLab.

PROHIBIDO en este módulo: truststore.extract_from_ssl() (global, y el backend es
multi-hilo), REQUESTS_CA_BUNDLE/SSL_CERT_FILE/CURL_CA_BUNDLE (globales),
verify=False, y parchear urllib3.
"""
from __future__ import annotations

import _ssl                     # extensión C de CPython: los descriptores reales
import logging
import ssl
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CaBundleInvalido(ValueError):
    """El bundle declarado no existe o no es legible. NUNCA se degrada en silencio."""


# Propiedades que hay que delegar al descriptor C. Ver el docstring de
# _construir_clase_genuina para el porqué.
_PROPIEDADES_DELEGADAS = (
    "verify_mode", "verify_flags", "options", "minimum_version", "maximum_version",
)

_clase_genuina: Optional[type] = None


def clase_ssl_context_original() -> type:
    """Devuelve la clase ssl.SSLContext GENUINA, haya o no inyectado truststore.

    - Sin inject: ssl.SSLContext ya es la genuina (__module__ == "ssl").
    - Con inject: en CPython truststore SUBCLASEA la genuina
      (truststore/_ssl_constants.py:20-22), así que está en el MRO.
    """
    actual = ssl.SSLContext
    if getattr(actual, "__module__", "") == "ssl":
        return actual
    for base in actual.__mro__:
        if base.__module__ == "ssl" and base.__name__ == "SSLContext":
            return base
    raise RuntimeError(
        "no se pudo recuperar ssl.SSLContext original; ¿intérprete no-CPython? "
        f"MRO actual: {actual.__mro__}"
    )


def _construir_clase_genuina() -> type:
    """Subclase de ssl.SSLContext cuyas properties saltean el setter de ssl.py.

    LA TRAMPA (documentada en §6 del plan 276): urllib3/connection.py:937 ejecuta
    `context.verify_mode = resolve_cert_reqs(cert_reqs)` SIEMPRE, aun con un
    ssl_context provisto. El setter de CPython resuelve el nombre `SSLContext`
    desde el módulo `ssl` — que truststore ya pisó — y entra en recursión
    infinita: RecursionError, NO un error de TLS. Un implementador que vea ese
    stack va a creer que se equivocó de certificado.

    La salida: delegar cada property al descriptor de _ssl._SSLContext, que es C
    y no pasa por el namespace envenenado. Es el mismo mecanismo que usa el
    propio truststore en _ssl_constants.py:28-31.
    """
    global _clase_genuina
    if _clase_genuina is not None:
        return _clase_genuina

    base = clase_ssl_context_original()
    espacio: dict = {}
    for nombre in _PROPIEDADES_DELEGADAS:
        descriptor = getattr(_ssl._SSLContext, nombre)
        espacio[nombre] = property(
            (lambda d: lambda self: d.__get__(self))(descriptor),
            (lambda d: lambda self, valor: d.__set__(self, valor))(descriptor),
        )
    _clase_genuina = type("_ContextoOpenSSLGenuino", (base,), espacio)
    return _clase_genuina


def crear_contexto_openssl(ca_bundle: Optional[str]) -> Optional[ssl.SSLContext]:
    """Contexto OpenSSL con el bundle cargado y el pin de hoja habilitado.

    Devuelve None si no hay bundle: en ese caso NO se monta ningún adapter y la
    sesión sigue por truststore (que es lo correcto para gitlab.com/Zscaler).

    Lanza CaBundleInvalido si el bundle está declarado pero no existe: fallar
    ABIERTO deja al operador sin señal (P0-2).
    """
    if not ca_bundle or not str(ca_bundle).strip():
        return None

    ruta = Path(str(ca_bundle).strip()).expanduser()
    if not ruta.is_file():
        raise CaBundleInvalido(
            f"El certificado declarado no existe: '{ca_bundle}'. "
            "Corregí la ruta en el campo 'Certificado de la empresa' del proyecto "
            "o dejalo vacío para usar la verificación estándar."
        )

    ctx = _construir_clase_genuina()(ssl.PROTOCOL_TLS_CLIENT)
    ctx.verify_mode = ssl.CERT_REQUIRED          # <- la línea de la trampa
    ctx.check_hostname = True
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        ctx.load_verify_locations(cafile=str(ruta.resolve()))
    except (ssl.SSLError, OSError) as exc:
        raise CaBundleInvalido(f"El certificado '{ca_bundle}' no se pudo leer: {exc}") from exc

    # Permite que una HOJA presente en el bundle actúe como ancla. NO debilita:
    # la hoja tiene que coincidir exactamente con la que presenta el servidor
    # (es pinning) y check_hostname sigue activo.
    ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN

    stats = ctx.cert_store_stats()
    logger.info(
        "Contexto OpenSSL genuino para GitLab: %s certs (%s CA, %s hoja) desde %s",
        stats["x509"], stats["x509_ca"], stats["x509"] - stats["x509_ca"], ruta.name,
    )
    return ctx


__all__ = ["CaBundleInvalido", "clase_ssl_context_original", "crear_contexto_openssl"]
```

**Casos borde cubiertos:** bundle `None`/vacío → `None` (sin adapter). Ruta inexistente → `CaBundleInvalido`. Archivo ilegible o PEM corrupto → `CaBundleInvalido`. Intérprete no-CPython → `RuntimeError` ruidoso, nunca una verificación laxa silenciosa.

**Comando y VERDE esperado:** el de F1.1. **Criterio de aceptación (binario):** `9 passed`. Exigir el conteo: `-q` debe imprimir `9 passed`, no solo exit 0.

**Registro en los DOS ratchets:** agregar `tests/test_plan276_tls_context.py` inmediatamente después de `tests/test_global_config_gitlab_ca_bundle.py`, con la sintaxis de cada archivo:
- `backend/scripts/run_harness_tests.sh` (tras la línea `:232`): `  tests/test_plan276_tls_context.py` — sin comillas, sin coma.
- `backend/scripts/run_harness_tests.ps1` (tras la línea `:225`): `  "tests/test_plan276_tls_context.py",` — con comillas y coma.

**Flag:** ninguna todavía (módulo puro, sin call site). **Impacto por runtime:** idéntico en los 3 (Python puro, sin superficie de runtime). Fallback: no aplica. **Trabajo del operador: ninguno.**

---

### F2 — El adapter, montado SOLO en la sesión de GitLab

**Objetivo:** que `GitLabClient` use una `requests.Session` propia con el contexto de F1 montado para su `base_url`, dejando ADO/Jira/LLM intactos; y que una `SSLError` deje de subir cruda. **Valor:** es el momento en que el GitLab interno empieza a responder.

**Archivos a editar:**
- `Stacky Agents/backend/services/gitlab_client.py`
- `Stacky Agents/backend/services/tls_pinning.py` (borrar el parche global — P1-5)
- `Stacky Agents/backend/config.py`, `backend/services/harness_flags.py` (flag, §3.4)

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan276_gitlab_session_adapter.py`

#### F2.1 — Tests PRIMERO

Mismo preámbulo de inyección de truststore que F1.1 (regla #1). Casos:

1. `test_el_entorno_de_test_replica_produccion` — `ssl.SSLContext.__module__ == "truststore._api"`.
2. `test_con_bundle_monta_el_adapter_en_el_prefijo_de_gitlab` — construir `GitLabClient(base_url="https://gl.interno", project="g/p", ca_bundle=BUNDLE)`; `assert "https://gl.interno" in c._session.adapters`; y que ese adapter **no** es el `HTTPAdapter` por defecto.
3. `test_el_contexto_del_adapter_es_openssl_genuino` — `adapter._contexto.cert_store_stats()["x509"] == 119` y sin truststore en el MRO.
4. `test_sin_bundle_no_monta_nada` — con `ca_bundle=None` y sin env vars, `set(c._session.adapters) == {"http://", "https://"}` (solo los de fábrica). **Este es el gate de "no rompo Zscaler".**
5. `test_no_toca_la_sesion_global_de_requests` — `requests.adapters._preloaded_ssl_context` y `ssl.SSLContext` idénticos antes y después de construir el cliente.
6. `test_sslerror_se_envuelve_en_trackerapierror` (P1-7) — monkeypatchear `c._session.request` para que lance `requests.exceptions.SSLError("boom")`; esperar `TrackerApiError` con `kind == "tls"` y que el mensaje **nombre el archivo del bundle**.
7. `test_connectionerror_se_envuelve_en_trackerapierror` — misma forma, `kind == "network"`.
8. `test_con_la_flag_off_vuelve_el_camino_de_hoy` — `monkeypatch.setattr(config.config, "STACKY_GITLAB_TLS_ADAPTER_ENABLED", False)`; no se monta adapter y `verify=` vuelve a viajar con la ruta del bundle.
9. `test_bundle_inexistente_falla_ruidoso` — `ca_bundle=r"C:\no\existe.pem"` ⇒ `TrackerConfigError` (o `CaBundleInvalido` traducido), **nunca** un cliente construido con verificación degradada.

**Comando y ROJO esperado:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest tests\test_plan276_gitlab_session_adapter.py -q
```
Antes del fix fallan los 9: `GitLabClient` no tiene `_session`.

#### F2.2 — Implementación en `services/gitlab_client.py`

**a) El adapter.** Agregar cerca del tope del módulo (después de `_RETRY_MAX = 3`, `:31`):

```python
class _AdaptadorOpenSSL(requests.adapters.HTTPAdapter):
    """Monta un ssl_context OpenSSL genuino en una sola sesión.

    init_poolmanager y proxy_manager_for son los DOS puntos por donde urllib3
    construye pools: sin el segundo, una red con proxy corporativo se saltea el
    contexto y vuelve el SSLError.
    """

    def __init__(self, contexto, **kw):
        self._contexto = contexto
        super().__init__(**kw)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self._contexto
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = self._contexto
        return super().proxy_manager_for(*args, **kwargs)
```

**b) En `GitLabClient.__init__`**, después de resolver `self._base_url` (`:72`) — **el orden importa**: el adapter se monta por prefijo de URL, así que necesita la `base_url` ya resuelta:

```python
        # Plan 276 F2 — sesión propia. El contexto OpenSSL se monta SOLO para el
        # prefijo de este GitLab: cualquier otro destino del proceso (ADO, Jira,
        # LLM, gitlab.com) sigue por truststore, que es lo que resuelve Zscaler.
        self._session = requests.Session()
        self._contexto_tls = None
        if bool(getattr(config.config, "STACKY_GITLAB_TLS_ADAPTER_ENABLED", True)):
            from services.tls_openssl_context import crear_contexto_openssl, CaBundleInvalido
            try:
                self._contexto_tls = crear_contexto_openssl(_ruta_bundle)
            except CaBundleInvalido as exc:
                raise TrackerConfigError(str(exc)) from exc
            if self._contexto_tls is not None and self._base_url:
                self._session.mount(self._base_url, _AdaptadorOpenSSL(self._contexto_tls))
```

donde `_ruta_bundle = resolver_ca_bundle(ca_bundle)` (se conserva `services.tls_pinning.resolver_ca_bundle`, que ya implementa la precedencia parámetro > `STACKY_GITLAB_CA_BUNDLE` > `REQUESTS_CA_BUNDLE`). `self._verify` sigue existiendo para la rama con la flag en OFF.

**c) En `_request` (`:182-191`)**, cambiar `requests.request(...)` por `self._session.request(...)` y envolver (P1-7):

```diff
-        resp = requests.request(
-            method,
-            url,
-            headers=self._headers(),
-            params=params,
-            json=json_body,
-            files=files,
-            timeout=20,
-            verify=self._verify,
-        )
+        try:
+            resp = self._session.request(
+                method,
+                url,
+                headers=self._headers(),
+                params=params,
+                json=json_body,
+                files=files,
+                timeout=20,
+                verify=self._verify,
+            )
+        except requests.exceptions.SSLError as exc:
+            # P1-7: sin esto la SSLError sube CRUDA y ningún `except
+            # TrackerApiError` aguas arriba la ve — el operador recibe un 500 mudo.
+            raise TrackerApiError(
+                0,
+                f"TLS contra {self._base_url}: {exc}. "
+                f"Certificado en uso: {self._ruta_bundle or '(verificación estándar)'}",
+                kind="tls",
+            ) from exc
+        except requests.exceptions.RequestException as exc:
+            raise TrackerApiError(0, f"Red contra {self._base_url}: {exc}", kind="network") from exc
```

**Nota:** `verify=self._verify` se mantiene. Con el adapter montado, urllib3 usa el `ssl_context` provisto; `verify` sigue siendo el camino válido cuando la flag está OFF, y mantenerlo hace que la rama OFF sea byte-idéntica a hoy.

**d) `_kind_for_status` (`:34-43`)** gana los dos kinds nuevos como constantes documentadas: `"tls"` y `"network"` no vienen de un status HTTP, se asignan en el `except`. Agregar el comentario correspondiente.

#### F2.3 — Borrar el parche global de urllib3 (P1-5)

En `services/tls_pinning.py`, eliminar `habilitar_pin_de_certificado_hoja()` completa (`:35-86`) y su llamada desde `preparar_verificacion` (`:120`). El pin ahora vive **solo** en el `ssl_context` del adapter (F1). Motivo: `:79-80` parchea `urllib3.util.ssl_.create_urllib3_context` **y** `urllib3.connection.create_urllib3_context`, que son compartidos por todo el proceso; hoy es inerte bajo truststore, pero **apenas F2 funcione empieza a aplicar `VERIFY_X509_PARTIAL_CHAIN` a las conexiones de ADO, Jira y las APIs de LLM**, debilitando su verificación.

**Consecuencia declarada:** `tools/migrar_mantis_gitlab/destination_writer.py` delega hoy en ese helper. F2 lo re-apunta: el migrador pasa a usar `crear_contexto_openssl` + `_AdaptadorOpenSSL` con el mismo patrón. Y `test_gitlab_tls_pinning.py:140-151` (`test_el_migrador_sigue_usando_el_helper_compartido`) se reescribe en F10.

**Criterio de aceptación (binario):**
```
& $PY -m pytest tests\test_plan276_gitlab_session_adapter.py -q        # 9 passed
& $PY -m pytest tests\test_gitlab_client.py -q                          # sin regresión
Select-String -Path services\tls_pinning.py -Pattern "create_urllib3_context"   # 0 coincidencias
```
El tercero debe devolver **cero líneas**: si devuelve alguna, el parche global sigue vivo.

**Ratchet:** registrar `tests/test_plan276_gitlab_session_adapter.py` en los dos scripts.

**Flag:** `STACKY_GITLAB_TLS_ADAPTER_ENABLED`, **default True** (§3.4). Con OFF vuelve exactamente el camino de hoy.
**Impacto por runtime:** idéntico en los 3. Fallback: no aplica. **Trabajo del operador: ninguno.**

---

### F3 — El bundle deja de fallar ABIERTO y la `base_url` se valida

**Objetivo:** que una ruta de certificado mal escrita y una `base_url` con el namespace pegado **den un error accionable**, en vez de degradar la verificación en silencio (P0-2) o producir un 404 mudo (P1-4 backend). **Valor:** los dos errores de tipeo más probables del operador dejan de costar una tarde de diagnóstico.

**Archivos a editar:** `Stacky Agents/backend/services/tls_pinning.py`, `Stacky Agents/backend/services/gitlab_client.py`
**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan276_tls_bundle_estricto.py`

**Defecto exacto (P0-2), `tls_pinning.py:103-107`:**
```python
        logger.warning(
            "CA bundle declarado en '%s' pero el archivo no existe; se ignora "
            "y se usa la verificación por defecto.", cand
        )
    return None
```
y `:118-119`: `if not ruta: return True`. Un typo en la UI ⇒ warning en un log que nadie mira + `verify=True` ⇒ el operador ve "no confía en el certificado" y **no tiene ninguna señal de que su ruta está mal**.

**Cambio:** `resolver_ca_bundle` gana un parámetro `estricto: bool = True`. Con `estricto=True`, una ruta **declarada explícitamente** (parámetro o `STACKY_GITLAB_CA_BUNDLE`) que no existe lanza `CaBundleInvalido`. Una ruta que viene de `REQUESTS_CA_BUNDLE` (que puede estar seteada por el entorno, ajena a Stacky) sigue degradando con warning: no es una declaración del operador.

**Cambio (P1-4 backend), `gitlab_client.py:72`:** hoy `self._base_url = (base_url or os.getenv("GITLAB_URL") or "").rstrip("/")` — sin ninguna validación. Agregar `_validar_base_url()`:

```python
def _validar_base_url(url: str) -> str:
    """La base_url es SOLO el origen. Con el namespace pegado, la URL que arma
    _request (:177-180) queda 'https://host/grupo/api/v4/...' => HTTP 404 mudo
    (kind='not_found', _kind_for_status :37-38)."""
    limpia = (url or "").strip().rstrip("/")
    if not limpia:
        return ""
    if not re.match(r"^https?://", limpia, re.I):
        raise TrackerConfigError(f"GITLAB_URL debe empezar con http:// o https://: '{url}'")
    resto = re.sub(r"^https?://[^/]+", "", limpia, flags=re.I)
    if re.search(r"/api/v[0-9]+$", resto, re.I):
        raise TrackerConfigError(
            f"Quitá el '/api/v4' del final de la URL de GitLab: Stacky lo agrega. Recibido: '{url}'"
        )
    if resto:
        raise TrackerConfigError(
            f"La URL de GitLab debe ser solo el servidor (ej: https://srvcgit01.imsolutions.local). "
            f"Sacá '{resto}' — eso va en el campo 'Proyecto' (ej: grupo/proyecto). Recibido: '{url}'"
        )
    return limpia
```

**Tests (archivo nuevo, 8 casos):** ruta declarada inexistente ⇒ `CaBundleInvalido`; `REQUESTS_CA_BUNDLE` inexistente ⇒ warning + `None`; bundle válido ⇒ ruta absoluta; `base_url` con `/api/v4` ⇒ error que **nombra** `/api/v4`; `base_url` con namespace pegado ⇒ error que **nombra el sobrante**; `base_url` sin esquema ⇒ error; `base_url` limpia ⇒ pasa; `base_url` vacía ⇒ `""` (comportamiento de hoy, se resuelve más tarde con `TrackerConfigError` en `_request`, `:173-174`).

**Comando:** `& $PY -m pytest tests\test_plan276_tls_bundle_estricto.py -q` ⇒ **8 passed**.
**Criterio de aceptación (binario):** 8 passed, y `Select-String -Path services\tls_pinning.py -Pattern "return True"` devuelve 0 coincidencias en el cuerpo de `preparar_verificacion`.

**Ratchet:** registrar en los dos scripts.
**Flag:** ninguna nueva (queda bajo `STACKY_GITLAB_TLS_ADAPTER_ENABLED`; con OFF, `estricto=False`).
**Impacto por runtime:** idéntico en los 3. **Trabajo del operador: ninguno** — solo recibe un mensaje que dice qué corregir.

---

### F4 — El check deja de mentir: cuatro sub-veredictos

**Objetivo:** que "Probar conexión" y el doctor de conexiones reporten **TLS / auth / proyecto legible / N ítems** por separado, y salgan verdes **solo si los cuatro pasan**. **Valor:** cierra el modo de falla que ya costó una jornada: check verde + listado vacío.

**Archivos a editar:** `Stacky Agents/backend/api/global_config.py`, `Stacky Agents/backend/services/local_diagnostics.py`
**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan276_probe_verdict.py`

**Defecto P0-3, `api/global_config.py:382` y `:389`:**
```python
            ok = bool(checks["auth"] and checks["read"])          # :382 — se calcula
            msg = f"GitLab -- conexion {'OK' if ok else 'PARCIAL'}. Checks: {checks}"
        ...
        return jsonify({"ok": True, "message": msg, "tracker_type": t_type})   # :389 — y se TIRA
```
Más `:369-371`, que se traga el fallo del listado:
```python
            except Exception:
                pass
```

**TRAMPA A DOCUMENTAR:** la línea `:389` es **compartida por todos los tipos de tracker** (jira, mantis, ADO y GitLab); `ok` **solo existe** en la rama GitLab. Cambiar `"ok": True` por `"ok": ok` **sin más produce `NameError` para ADO/Jira/Mantis**. El fix obligatorio es inicializar `ok = True` **antes** de la cadena de ramas (junto a `msg`), y dejar que la rama GitLab lo sobrescriba.

**Diff (`api/global_config.py`):**
```diff
+        ok = True          # las ramas no-GitLab reportan OK si no lanzaron; GitLab lo sobrescribe
         ...
             try:
                 c._request("GET", f"/projects/{c._project_path()}/issues", params={"per_page": 1})
                 checks["read"] = True
-            except Exception:
-                pass
+            except Exception as exc_read:
+                checks["read"] = False
+                checks["read_error"] = str(exc_read)
         ...
-        return jsonify({"ok": True, "message": msg, "tracker_type": t_type})
+        return jsonify({"ok": ok, "message": msg, "tracker_type": t_type, "checks": locals().get("checks")})
```
*(Si `checks` no está definido en las ramas no-GitLab, `locals().get("checks")` devuelve `None` — aditivo y sin romper consumidores.)*

**Diff (`services/local_diagnostics.py`).** `_probe_gitlab` (`:187-201`) hoy hace un único `GET /user` y el resultado se rotula con un **nombre** que afirma el veredicto (`:122`, `f"{label} alcanzable"`). Pasa a devolver los cuatro sub-checks:

```python
def _probe_gitlab(project_name, tracker) -> dict:
    """Cuatro sub-veredictos. GET /user da 200 con cualquier token válido aunque
    el proyecto esté mal: NO alcanza como criterio (regla antifalso-verde #2)."""
    detalle = {"tls": False, "auth": False, "proyecto_legible": False, "items": 0}
    client = GitLabClient(...)          # igual que hoy, :191-200

    try:
        user, _ = client._request("GET", "/user")
        detalle["tls"] = True
        detalle["auth"] = bool(user.get("id"))
    except TrackerApiError as exc:
        detalle["tls"] = exc.kind != "tls"       # llegó HTTP ⇒ el TLS anduvo
        detalle["auth"] = False
        return detalle

    try:
        issues, headers = client._request(
            "GET", f"/projects/{client._project_path()}/issues", params={"per_page": 1}
        )
        detalle["proyecto_legible"] = True
        detalle["items"] = int(headers.get("X-Total") or len(issues or []) or 0)
    except TrackerApiError as exc:
        detalle["error_lectura"] = f"{exc.kind}: {exc}"
    return detalle
```

y el rótulo de `:122` deja de afirmar: `f"Tracker {label}: TLS / credenciales / proyecto / ítems"`, con `status="ok"` **solo si** `tls and auth and proyecto_legible`. `items == 0` no es error (un proyecto puede estar vacío) pero **se muestra**, porque es el número que le importa al operador.

**Tests (7 casos):** los cuatro sub-checks en verde ⇒ `status="ok"`; auth OK + lectura rota ⇒ `status="error"` y el mensaje nombra el proyecto; `kind="tls"` ⇒ `tls=False` y el mensaje nombra el certificado; `ok` del endpoint global es **False** cuando `read` es False; `ok` sigue siendo True para un tracker ADO (**gate del `NameError`**); el rótulo no contiene la palabra "alcanzable"; `X-Total` ausente ⇒ cae a `len(issues)`.

**Comando:** `& $PY -m pytest tests\test_plan276_probe_verdict.py -q` ⇒ **7 passed**.
**Criterio de aceptación (binario):** 7 passed **y** `& $PY -m pytest tests\test_plan116_connection_probes.py tests\test_diag_tracker_gitlab_probe.py -q` sin regresión (correr **uno por archivo**).

**Ratchet:** registrar en los dos scripts.
**Flag:** `STACKY_TRACKER_PROBE_STRICT_ENABLED`, **default True**. Con OFF, el rótulo y el `ok` vuelven a los de hoy.
**Impacto por runtime:** idéntico en los 3. **Trabajo del operador: ninguno.**

---

### F5 — El sync GitLab → BD existe (la deuda del "Plan 220")

**Objetivo:** que apretar "Sincronizar" en un proyecto GitLab traiga los issues abiertos a la tabla `tickets`. **Valor:** es lo único que puede hacer que el grafo deje de estar vacío.

**Archivos a crear:** `Stacky Agents/backend/services/gitlab_sync.py`, `Stacky Agents/backend/tests/test_plan276_gitlab_sync.py`
**Archivos a editar:** `Stacky Agents/backend/services/gitlab_provider.py`, `Stacky Agents/backend/api/tickets.py`, `Stacky Agents/backend/services/provider_capabilities.py`

#### F5.1 — `_normalize_issue` gana `work_item_type` (P1-6)

`services/gitlab_provider.py:95-113` hoy no emite `work_item_type`, y `api/tickets.py:646-649` clasifica por `t.work_item_type == "epic"` ⇒ **todo cae en `orphans`** (`:653-654`).

```diff
     def _normalize_issue(self, body: dict) -> dict:
         ...
+        # Plan 276 F5.1 — el tipo sale de la label `type::<x>` que este mismo
+        # provider escribe al crear (_type_label, :76-77). Sin label => "Issue".
+        tipo = "Issue"
+        for etiqueta in labels:
+            if isinstance(etiqueta, str) and etiqueta.lower().startswith("type::"):
+                tipo = etiqueta.split("::", 1)[1].strip().capitalize() or "Issue"
+                break
         return {
             ...
+            "work_item_type": tipo,
             "parent": parent_id,
         }
```

#### F5.2 — El sync

`services/gitlab_sync.py`, función única `sync_gitlab_tickets(project_name, *, provider=None) -> dict`. Devuelve **la misma forma** que el sync de ADO (`{"fetched", "created", "updated", "removed", "stacky_project_name"}`) para que `api/tickets.py:5995-6021` no cambie.

**Mapeo exacto GitLab → `models.Ticket`** (tipos verificados en `backend/models.py:41-57`):

| Campo de `Ticket` | Tipo | Origen |
|---|---|---|
| `ado_id` | `Integer` **not null** | `int(item["iid"])` — el número visible del issue en el proyecto |
| `external_id` | `Integer` | `int(item["id"])` — el id global de GitLab |
| `project` | `String(80)` not null | `ctx.tracker_project` (path `grupo/proyecto`) |
| `stacky_project_name` | `String(80)` | nombre Stacky (`RIPLEY`) |
| `tracker_type` | `String(40)` | `"gitlab"` |
| `title` / `description` | `String(500)` / `Text` | directos; **truncar `title` a 500** |
| `ado_state` | `String(40)` | `item["state"]` (`opened` / `closed`) |
| `ado_url` | `String(400)` | `item["web_url"]` |
| `work_item_type` | `String(40)` | de F5.1 |
| `parent_ado_id` | `Integer` | `int(item["parent"])` si es numérico, si no `None` |
| `last_synced_at` | `DateTime` | `datetime.utcnow()` |

**CASO BORDE OBLIGATORIO:** `_normalize_issue` devuelve `id` e `iid` como **`str`** (`:103-104`) y `Ticket.ado_id` es **`Integer`**. Convertir con guarda: un `iid` no numérico se **saltea con warning** y suma a `skipped`; **nunca** revienta el sync entero.

**Semántica de borrado — NO se borra nada.** Un issue que ya no aparece en el listado de abiertos pasa a `ado_state="closed"` y cuenta en `removed`. Riel: nunca destruir datos del operador. Documentarlo en el docstring.

**Idempotencia:** `created` cuenta filas nuevas; `updated`, filas cuyo `title`/`state`/`parent`/`type` cambió; una segunda corrida sin cambios devuelve `created=0, updated=0, removed=0` (lo que `api/tickets.py:5996` ya usa para marcar `idempotent`).

#### F5.3 — El ruteo, sin flipear la flag global (P1-1)

`config.py:1320-1322` deja `STACKY_TICKETS_PROVIDER_ENABLED` en **False** ⇒ `_provider_for_ticket` (`api/tickets.py:420-421`) devuelve `None` ⇒ el sync cae al branch ADO ⇒ `services/project_context.py:309-311` lanza `AdoConfigError("El proyecto 'RIPLEY' no usa Azure DevOps...")` ⇒ **HTTP 400 con un error de ADO en un proyecto GitLab**.

**No se flipea el default** (§3.2). Se resuelve el provider localmente, solo para trackers no-ADO, en `_sync_via_provider_or_ado` (`:700-723`):

```diff
     provider = _provider_for_ticket(project_name=project_name)
+    # Plan 276 F5.3 — el sync no puede depender de STACKY_TICKETS_PROVIDER_ENABLED
+    # (default False, config.py:1320): con esa flag OFF un proyecto GitLab caía al
+    # branch ADO y moría con AdoConfigError. Se resuelve el provider SOLO para
+    # trackers no-ADO; para Azure DevOps este bloque no se ejecuta y el camino
+    # queda byte-idéntico.
+    if provider is None and bool(getattr(config.config, "STACKY_GITLAB_SYNC_ENABLED", True)):
+        from services.project_context import resolve_project_context
+        ctx = resolve_project_context(project_name)
+        if ctx is not None and ctx.tracker_type != "azure_devops":
+            try:
+                provider = get_tracker_provider(project_name)
+            except TrackerConfigError:
+                provider = None
     if provider is not None and getattr(provider, "name", "azure_devops") != "azure_devops":
+        if provider.name == "gitlab" and bool(
+            getattr(config.config, "STACKY_GITLAB_SYNC_ENABLED", True)
+        ):
+            from services.gitlab_sync import sync_gitlab_tickets
+            return sync_gitlab_tickets(project_name, provider=provider)
         raise CapabilityUnavailable(
             "tracker.sync.full", provider.name,
             reason="el sync de ítems de este tracker todavía no está implementado",
-            workaround="Plan 220 lo implementa; mientras tanto usá un proyecto Azure DevOps.",
+            workaround="Plan 276 implementó el sync de GitLab; este tracker todavía no lo tiene.",
         )
```

#### F5.4 — El registro de capacidades deja de mentir

`services/provider_capabilities.py:249`: `"tracker.sync.full": _a("api/tickets.py:692")` → pasa a **presente** para `"gitlab"` (usar el helper de "disponible" que ya usa ese diccionario para las capacidades soportadas; leer cómo lo hacen las entradas vecinas y replicar).

#### F5.5 — Tests (12 casos, con la BD en un sqlite temporal)

`tests/test_plan276_gitlab_sync.py`. Fixture obligatoria (evita P2-6):
```python
@pytest.fixture()
def bd(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'plan276.db'}")
    ...
```

Casos: 3 issues → 3 filas con el mapeo completo; `iid` no numérico → `skipped=1` y el resto se guarda; segunda corrida idéntica → `created=0, updated=0`; cambio de título → `updated=1`; issue que desaparece → `ado_state="closed"` y `removed=1`, **la fila sigue existiendo**; `type::epic` → `work_item_type="Epic"`; sin label → `"Issue"`; `parent` con `iid` → `parent_ado_id` int; `parent` vacío → `None`; `title` de 900 chars → truncado a 500 sin excepción; proyecto ADO → el bloque nuevo **no se ejecuta** (gate de backward-compat, monkeypatchear `resolve_project_context` y afirmar que `get_tracker_provider` **no** se llamó); flag `STACKY_GITLAB_SYNC_ENABLED=False` → vuelve a levantarse `CapabilityUnavailable`.

**Comando:** `& $PY -m pytest tests\test_plan276_gitlab_sync.py -q` ⇒ **12 passed**.
**Criterio de aceptación (binario):** 12 passed, y `& $PY -m pytest tests\test_plan218_capability_unavailable.py -q` sin regresión.

**Ratchet:** registrar en los dos scripts.
**Flag:** `STACKY_GITLAB_SYNC_ENABLED`, **default True** (§3.4: escribe en la BD de Stacky, no en un sistema del operador, y es on-demand).
**Impacto por runtime:** idéntico en los 3 — el sync es HTTP + SQLAlchemy, sin ninguna llamada a modelo. **Trabajo del operador: ninguno** (el botón "Sincronizar" ya existe).

---

### F6 — El error deja de ser un falso verde y deja de ser un 500 mudo

**Objetivo:** que una capacidad ausente se vea como capacidad ausente, en el endpoint que la UI realmente usa. **Valor:** cierra el peor modo de falla del sistema — "sincronizado hace 2s", cero tickets, cero error.

**Archivos a editar:** `Stacky Agents/backend/api/tickets.py`, `Stacky Agents/backend/api/errors.py`, `Stacky Agents/backend/tests/test_plan218_capability_unavailable.py`, `Stacky Agents/frontend/src/hooks/useTicketSync.ts`
**Archivos de test a crear:** `Stacky Agents/backend/tests/test_plan276_capability_envelope.py`, `Stacky Agents/frontend/src/__tests__/plan276SyncEnvelope.test.ts`

**CORRECCIÓN DE LA EVIDENCIA — leer esto antes de tocar nada.** La cadena causal real, verificada hoy, **no** es la que se venía asumiendo:

- La UI llama **`POST /api/tickets/sync-v2`** (`frontend/src/hooks/useTicketSync.ts:84`), **no** `/sync`.
- `sync-v2` (`api/tickets.py:5916`) llama `_sync_via_provider_or_ado` en `:5980` y tiene un **`except Exception` genérico en `:5988-5991`** que devuelve `HTTP 500 {"ok": false, "error": "unexpected"}`. Como `CapabilityUnavailable` **es** una `Exception`, queda atrapada ahí.
- Por lo tanto **el handler de `app.py:879-882`, que traduce `CapabilityUnavailable` a 200 + `available:false`, NUNCA se ejecuta para `sync-v2`**: solo `/sync` (`:734-740`) la trata explícitamente.
- Conclusión: hoy, con la flag del provider ON, el operador recibe un **500 mudo** que esconde una carencia declarada; y con la flag OFF (el default de hoy) recibe un **400 de ADO** en un proyecto GitLab (P1-1, ya resuelto en F5.3).

El falso verde de `errors.py` **sí es real**, pero es **latente**: `capability_unavailable_envelope` produce `{"ok": True, "available": False, ...}` (`api/errors.py:81-83`) y cualquier consumidor de `/sync` o del handler global de `app.py:882` lo lee como éxito. `useTicketSync.ts:98` (`if (data.ok || data.synced_at)`) tomaría la rama de éxito. Se arregla igual, antes de que F5 lo active.

**Diff 1 — `api/tickets.py`, en `sync_from_ado_v2`, ANTES del `except Exception` de `:5988`:**
```diff
+    except CapabilityUnavailable:
+        # Plan 276 F6 — una carencia DECLARADA no puede caer en el `except
+        # Exception` de abajo y salir como 500 "unexpected": eso esconde el hueco
+        # y anula la degradación del plan 218. Se re-lanza para que la traduzca
+        # el handler de app.py:879-882 (200 + available:false).
+        _sync_in_progress_by_project.discard(sync_scope)
+        raise
     except Exception as e:
```
(agregar `CapabilityUnavailable` al import local que ya existe en la función).

**Diff 2 — `api/errors.py:81-83`:**
```diff
     payload = exc.to_payload()
-    payload.setdefault("ok", True)
+    # Plan 276 F6 — una capacidad AUSENTE no es un éxito. El status HTTP sigue
+    # siendo 200 (riel del plan 218: no reventar con un 500 que el operador tiene
+    # que interpretar), pero `ok` deja de contradecir a `available`.
+    payload["ok"] = bool(payload.get("available", False))
     payload["message"] = str(exc)
```
**Verificado hoy:** el test de la capacidad (`test_plan218_capability_unavailable.py:44-52`) assertea `body["available"] is False` y **no** assertea `ok`; el `assert body["ok"] is True` de `:70` pertenece al caso normal, donde `"available" not in body` (`:71`). Aun así, **correr ese archivo es criterio de aceptación de esta fase**; si algún assert cambia, actualizarlo con el motivo escrito en el propio test.

**Diff 3 — `frontend/src/hooks/useTicketSync.ts:98`:**
```diff
-      if (data.ok || data.synced_at) {
+      // Plan 276 F6 — `available: false` es una carencia declarada, NUNCA un
+      // éxito: sin esta guarda la UI muestra "sincronizado hace 2s" con cero
+      // tickets y cero error.
+      if (data.available === false) {
+        setSyncError(data.message || "El tracker de este proyecto no soporta sincronización.");
+      } else if (data.ok || data.synced_at) {
```
(y agregar `available?: boolean` al tipo del payload en el mismo archivo).

**Tests backend (5 casos):** `sync-v2` con `CapabilityUnavailable` ⇒ **200** con `available:false` y `ok:false` (no 500); el log **no** dice "fallo inesperado"; `sync-v2` con una excepción cualquiera ⇒ sigue siendo 500 (no se rompió el manejo genérico); el envelope pone `ok:false` cuando `available:false`; con `STACKY_CAPABILITY_DEGRADATION_ENABLED=False` sigue el camino legacy.

**Test frontend (`.ts` puro, 4 casos):** extraer la decisión a una función pura `clasificarRespuestaDeSync(data)` en `useTicketSync.ts` (exportada) que devuelva `"exito" | "carencia" | "rate_limited" | "error"`, y testearla sin montar el hook: `{ok:true, synced_at}` ⇒ exito; `{ok:true, available:false}` ⇒ **carencia**; `{error:"rate_limited"}` ⇒ rate_limited; `{ok:false, message}` ⇒ error.

**Comandos:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
& $PY -m pytest tests\test_plan276_capability_envelope.py -q          # 5 passed
& $PY -m pytest tests\test_plan218_capability_unavailable.py -q       # sin regresión
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/__tests__/plan276SyncEnvelope.test.ts              # 4 passed
```

**Criterio de aceptación (binario):** los 3 comandos en 0 fallas, y `Select-String -Path api\errors.py -Pattern 'setdefault\("ok"'` devuelve **0 coincidencias**.

**Ratchet:** registrar el archivo backend en los dos scripts.
**Flag:** ninguna nueva (usa la existente `STACKY_CAPABILITY_DEGRADATION_ENABLED`, ya ON).
**Impacto por runtime:** idéntico en los 3. **Trabajo del operador: ninguno.**

---

### F7 — El grafo muestra los tickets de GitLab

**Objetivo:** que `GET /api/tickets/hierarchy` devuelva las filas de GitLab agrupadas, y que la UI deje de decir "ADO" en un proyecto GitLab. **Valor:** es el criterio de cierre del plan.

**Archivos a editar:** `Stacky Agents/frontend/src/pages/TicketBoard.tsx` (`:1082`, `:1177`, `:1179`, `:1294`), `Stacky Agents/frontend/src/components/TicketGraphView.jsx` (`:649`, `:697`)
**Archivos a crear:** `Stacky Agents/backend/tests/test_plan276_hierarchy_gitlab.py`, `Stacky Agents/frontend/src/__tests__/plan276TrackerLabels.test.ts`

**Backend:** `api/tickets.py:615-656` **no necesita cambios** — clasifica por `work_item_type` y `parent_ado_id`, que F5 ahora puebla. El test lo demuestra: sembrar 4 filas `tracker_type="gitlab"` (1 con `work_item_type="Epic"`, 2 hijas con `parent_ado_id` apuntando a ella, 1 suelta) y verificar `len(epics) == 1`, `len(epics[0]["children"]) == 2`, `len(orphans) == 1`. **4 casos**, más uno que verifica que el filtro por proyecto no mezcla tickets de ADO.

**Frontend (P2-4):** los textos "Tickets ADO", "Sincronizar ADO" y "Sincronizar tickets desde ADO" están hardcodeados. Extraer a una función pura en un archivo nuevo `frontend/src/lib/trackerLabels.ts`:

```ts
export type TrackerType = "azure_devops" | "gitlab" | "jira" | "mantis";

const NOMBRES: Record<TrackerType, string> = {
  azure_devops: "ADO", gitlab: "GitLab", jira: "Jira", mantis: "Mantis",
};

/** Nombre visible del tracker. Un tipo desconocido cae a "Tracker", nunca a "ADO". */
export function nombreDeTracker(tipo: string | undefined | null): string {
  return NOMBRES[(tipo ?? "") as TrackerType] ?? "Tracker";
}
export function tituloDeTickets(tipo: string | undefined | null): string {
  return `Tickets ${nombreDeTracker(tipo)}`;
}
export function accionSincronizar(tipo: string | undefined | null): string {
  return `Sincronizar ${nombreDeTracker(tipo)}`;
}
```

y reemplazar los 6 literales por llamadas a estas funciones con el `tracker_type` del proyecto activo. **No se toca** `App.tsx:455`, `SettingsPage.tsx:47`, `shellNav.ts:18` ni `commandPaletteData.ts:74`: son rótulos de **navegación global** (no dependen del proyecto activo) y cambiarlos rompería los tests de la paleta de comandos (`commandPaletteDevopsActions.test.ts:109-110`, que assertean sobre el string literal `"Ir a Tickets ADO"`). **Fuera de scope declarado**, no olvido.

**Test frontend (`.ts` puro, 5 casos):** los 4 tipos conocidos; tipo desconocido/`undefined` ⇒ `"Tracker"` (**nunca** `"ADO"`); `tituloDeTickets("gitlab") === "Tickets GitLab"`; `accionSincronizar("azure_devops") === "Sincronizar ADO"` (backward-compat del texto de hoy).

**Smoke manual (no hay RTL/jsdom), paso a paso:**
1. Levantar backend y frontend. 2. Seleccionar el proyecto **RIPLEY**. 3. Ir a la pestaña de tickets. 4. Verificar que el título dice **"Tickets GitLab"** y el botón **"Sincronizar GitLab"**. 5. Apretar el botón. 6. Verificar que aparecen tickets y que el contador coincide con el `X-Total` del smoke de F11. 7. Cambiar a un proyecto ADO. 8. Verificar que el título vuelve a **"Tickets ADO"** y que la lista de ese proyecto no cambió.

**Comandos:**
```
& $PY -m pytest tests\test_plan276_hierarchy_gitlab.py -q     # 5 passed
cd "...\frontend"; npx vitest run src/__tests__/plan276TrackerLabels.test.ts   # 5 passed
```
**Criterio de aceptación (binario):** 5 + 5 passed, y el smoke manual de 8 pasos con captura del paso 6.

**Ratchet:** registrar el archivo backend en los dos scripts.
**Flag:** ninguna (los rótulos son corrección de defecto sobre superficie ya `default=True`).
**Impacto por runtime:** idéntico en los 3. **Trabajo del operador: ninguno.**

---

### F8 — Los tres agujeros de configuración que devuelven el bug

**Objetivo:** cerrar las tres rutas por las que el bug vuelve solo. **Valor:** evita que la próxima corrida reintroduzca lo que este plan arregló.

**F8.1 — P1-2, `services/tracker_provider.py:149`.** La rama legacy construye `GitLabTrackerProvider(project=project)` **sin `ca_bundle`** y sin ningún test. Con `STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED` en OFF vuelve el bug entero.
```diff
-        return GitLabTrackerProvider(project=project)   # ruta legacy, byte-idéntica
+        # Plan 276 F8.1 — la ruta legacy TAMBIÉN necesita el bundle: sin él, apagar
+        # STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED devuelve el SSLError entero.
+        return GitLabTrackerProvider(
+            project=project,
+            ca_bundle=(getattr(config.config, "STACKY_GITLAB_CA_BUNDLE", "") or None),
+        )
```

**F8.2 — P1-3, `EditProjectModal.tsx:223-229`.** `buildPayload` devuelve `{...form, docs_paths}` **sin normalizar**, mientras `NewProjectModal.tsx:105-119` **sí** normaliza (`:116-117`). El alta limpia la URL y la edición la vuelve a romper. Aplicar en `EditProjectModal.tsx` el mismo bloque de `NewProjectModal.tsx:111-118`, importando `normalizeGitlabUrl` y `normalizeGitlabProjectPath` del mismo módulo.

**F8.3 — P1-4 frontend.** `normalizeGitlabUrl` vive en **`frontend/src/projects/newProjectGitlabModel.ts:30-32`** (no en `src/lib/`; el archivo **sí** está trackeado por git, verificado con `git ls-files`) y solo hace:
```ts
return (raw ?? "").trim().replace(/\/+$/, "").replace(/\/api\/v4$/i, "");
```
**No saca el namespace pegado** — el gotcha histórico sigue vivo. Extender:
```ts
/** Quita la barra final, un /api/v4 pegado y CUALQUIER path: la base_url es solo el origen. */
export function normalizeGitlabUrl(raw: string): string {
  const limpio = (raw ?? "").trim().replace(/\/+$/, "").replace(/\/api\/v[0-9]+$/i, "");
  const m = limpio.match(/^(https?:\/\/[^/]+)(\/.*)?$/i);
  return m ? m[1] : limpio;
}
```
El test existente `src/__tests__/plan259GitlabOnboarding.test.ts:63,67` sigue verde (`https://gitlab.com/` ⇒ `https://gitlab.com`; `https://gl.io/api/v4` ⇒ `https://gl.io`) — **verificarlo**, no asumirlo.

**Archivos de test a crear:** `backend/tests/test_plan276_config_gaps.py` (3 casos: la rama legacy recibe el bundle; con el bundle vacío pasa `None`; el provider por proyecto sigue igual) y `frontend/src/__tests__/plan276GitlabUrlNormalize.test.ts` (6 casos: namespace pegado; `/api/v4`; barra final; ya limpia; con puerto; string vacío).

**Comandos:**
```
& $PY -m pytest tests\test_plan276_config_gaps.py -q                              # 3 passed
cd "...\frontend"; npx vitest run src/__tests__/plan276GitlabUrlNormalize.test.ts  # 6 passed
cd "...\frontend"; npx vitest run src/__tests__/plan259GitlabOnboarding.test.ts    # sin regresión
```
**Criterio de aceptación (binario):** 3 + 6 passed y el tercero sin fallas nuevas.
**Ratchet:** registrar el archivo backend. **Flag:** ninguna. **Runtime:** idéntico en los 3. **Trabajo del operador: ninguno.**

---

### F9 — Los cinco P2

**Objetivo:** cerrar los defectos de segundo orden que ya están identificados y son de bajo riesgo.

| # | Defecto | Anclaje | Fix |
|---|---|---|---|
| P2-1 | Techo de 4.000 issues truncado **sin log** (`per_page=100` × `_DEFAULT_PAGE_CAP=40`) | `gitlab_client.py:238` y `:30` | Al salir del `while` por `pages_fetched >= page_cap`, emitir `logger.warning` con el path, el cap y el total traído. **No** subir el cap. |
| P2-2 | Un `dict` con HTTP 200 se appendea como issue fantasma | `gitlab_client.py:250-251` | Solo appendear si el dict tiene una clave `id` o `iid`; si no, `logger.warning` y descartar. |
| P2-3 | `Retry-After` sin clamp (un `86400` cuelga el worker un día) | `gitlab_client.py:194-195` | `retry_after = min(float(resp.headers.get("Retry-After") or 1), 30.0)`, con warning si se recortó. |
| P2-5 | `deployment/srvcgit01-ca.pem` **contiene la hoja, no una CA** (verificado: 1 bloque, `CN=srvcgit01.imsolutions.local`, `x509_ca=0`) | — | Renombrar a `srvcgit01-hoja.pem` **y** agregar `deployment/README_certificados.md` de 10 líneas explicando hoja vs CA y por qué hace falta `VERIFY_X509_PARTIAL_CHAIN`. Actualizar toda referencia con `grep -rn "srvcgit01-ca"`. |
| P2-6 | `create_app()` sin `DATABASE_URL` hace `create_all` contra la **BD real del operador** (181 MB) | `backend/tests/test_gitlab_ca_bundle_ui.py:59-66`, vía `app.py:400` / `db.py:265` | En la fixture `client`, `monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")` **antes** de `create_app()`. Medido hoy: 24,59 s → objetivo **< 6 s**. |

**Archivo de test a crear:** `backend/tests/test_plan276_client_limits.py` (6 casos: se emite el warning al llegar al cap; no se emite si no se llegó; el dict sin `id`/`iid` se descarta; el dict con `id` se conserva; `Retry-After: 86400` ⇒ espera ≤ 30 s; `Retry-After: 2` ⇒ espera 2 s).

**Comandos:**
```
& $PY -m pytest tests\test_plan276_client_limits.py -q                # 6 passed
Measure-Command { & $PY -m pytest tests\test_gitlab_ca_bundle_ui.py -q }   # < 6 s
Select-String -Path ..\ -Pattern "srvcgit01-ca" -Recurse               # 0 coincidencias
```
**Criterio de aceptación (binario):** 6 passed, el `Measure-Command` bajo 6 segundos y el `Select-String` en cero.
**Ratchet:** registrar el archivo. **Flag:** ninguna. **Runtime:** idéntico en los 3. **Trabajo del operador: ninguno.**

---

### F10 — Endurecer los 5 tests que hoy están verdes con el bug vivo

**Objetivo:** que los 27 tests verdes existentes dejen de ser compatibles con el defecto. **Valor:** sin esto, la próxima regresión pasa igual de invisible que esta.

**Archivos a editar** (los 5 en `Stacky Agents/backend/tests/`):

| Test | Por qué hoy no detecta nada | Cómo se endurece |
|---|---|---|
| `test_gitlab_tls_pinning.py:103` — `assert capturado.get("verify") is not False` | Queda **verde si `verify=` desaparece por completo** (`.get()` devuelve `None`, y `None is not False`) | `assert "verify" in capturado` **y** `capturado["verify"] is not False` **y** `capturado["verify"] is not None` |
| `test_gitlab_tls_pinning.py:57-59` — precedencia con `REQUESTS_CA_BUNDLE="/no/existe.pem"` | La env se descarta igual por el `is_file()`, así que **no prueba precedencia**: prueba que se ignora una ruta rota | Usar **dos bundles que existan** (`tmp_path`), y afirmar que gana el explícito |
| `test_gitlab_tls_pinning.py:133-137` — `test_el_pin_es_idempotente` | El propio test setea el guard y después afirma que devuelve `False`: **autocumplido** | Reescribir contra el nuevo diseño: `crear_contexto_openssl` llamado dos veces devuelve **contextos distintos** que **no comparten** estado global |
| `test_gitlab_tls_pinning.py:140-151` — `test_el_migrador_sigue_usando_el_helper_compartido` | Setea el guard en `True` y afirma que ambos devuelven `False`: **autocumplido** | Afirmar que el migrador importa `crear_contexto_openssl` de `services.tls_openssl_context` (una sola implementación) y que **no** define la suya |
| `test_diag_tracker_gitlab_probe.py:64`, `test_gitlab_provider_ca_bundle.py:54`, `test_global_config_gitlab_ca_bundle.py:56` | **Mockean la clase `GitLabClient` entera** ⇒ no ejercitan una sola línea del camino TLS real | Sustituir el mock de la clase por un **doble parcial**: instancia real con `_session.request` monkeypatcheado, para que el constructor (y por lo tanto el montaje del adapter) **sí** corra |
| `test_gitlab_ca_bundle_ui.py:109-117` — `test_la_edicion_permite_borrar_el_ca_bundle` | El POST previo (`:110-111`) **nunca se assertea**: el test pasa igual si el alta jamás guardó el bundle | Agregar, entre el POST y el PATCH, `assert _tracker(proyectos).get("ca_bundle") == str(proyectos["bundle"])` — **guardar primero y probarlo** |

**Además:** ninguno de los 5 corre con truststore inyectado. **Agregar el preámbulo de inyección de F1.1 a los 5 archivos** — es lo que convierte a `test_el_pin_de_hoja_aplica_partial_chain` (`:109-130`) de un verde decorativo en un test que dice la verdad: bajo truststore, `u3ssl.create_urllib3_context()` devuelve un contexto de truststore, cuyo `verify_flags` **no participa** de la construcción de cadena (`truststore/_windows.py:366-371`). Ese test se reemplaza por el equivalente de F1 sobre el contexto del adapter.

**Comando (uno por archivo, nunca la suite):**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
& $PY -m pytest tests\test_gitlab_tls_pinning.py -q
& $PY -m pytest tests\test_diag_tracker_gitlab_probe.py -q
& $PY -m pytest tests\test_gitlab_provider_ca_bundle.py -q
& $PY -m pytest tests\test_global_config_gitlab_ca_bundle.py -q
& $PY -m pytest tests\test_gitlab_ca_bundle_ui.py -q
```
**Criterio de aceptación (binario):** los 5 en verde **y** el total de casos **≥ 27** (no puede bajar: endurecer no es borrar). Anotar el conteo por archivo antes y después.

**Flag:** ninguna. **Runtime:** idéntico en los 3. **Trabajo del operador: ninguno.**

---

### F11 — Smoke de cierre: los tres fallos aislados en UNA corrida

**Objetivo:** demostrar, en una sola corrida contra el servidor real, que ruteo, TLS y 404 están los tres resueltos. **Valor:** es el único criterio que prueba el objetivo del plan; los tres fallos históricos se enmascaran en cascada, así que hay que aislarlos juntos.

**Prerequisitos:** backend arriba con RIPLEY activo, `truststore` inyectado (o sea: el backend normal, sin trucos), y el bundle configurado en el campo "Certificado de la empresa" del proyecto apuntando a `deployment/ca-bundle-migrador.pem`.

**Truco de diagnóstico obligatorio:** setear `GITLAB_TOKEN` a un valor dummy **aísla TLS de AUTH** y, además, evita que `gitlab_client.py:78-80` lea y **reescriba** el archivo de credenciales (`:98-106` documenta que `read_secret_from_file` cifra y reescribe). Regla de lectura: **TLS OK ⇒ `TrackerApiError` 401. TLS roto ⇒ `SSLError`.**

```
$env:GITLAB_TOKEN = "dummy-para-aislar-tls"
& $PY -c "
import ssl, truststore; truststore.inject_into_ssl()          # replica producción
from services.tls_openssl_context import crear_contexto_openssl
import requests
from services.gitlab_client import GitLabClient, _AdaptadorOpenSSL
B = r'..\deployment\ca-bundle-migrador.pem'
s = requests.Session(); s.mount('https://srvcgit01.imsolutions.local', _AdaptadorOpenSSL(crear_contexto_openssl(B)))
r = s.get('https://srvcgit01.imsolutions.local/api/v4/version', timeout=20)
print('(a) version ->', r.status_code)                         # ESPERADO: 401
"
Remove-Item Env:\GITLAB_TOKEN
```

**(a) TLS.** `GET /api/v4/version` sin token ⇒ **HTTP 401**. Un `SSLError` acá significa que F1/F2 no cerraron.
**(b) Ruteo + proyecto.** `GET /projects/<path-urlencoded>/issues?per_page=1` con el token real ⇒ **HTTP 200** y `X-Total > 0` (esperado ~53 abiertos). Un **404** significa `base_url` con el namespace pegado (F3/F8.3).
**(c) Grafo.** `curl.exe -s "http://localhost:5000/api/tickets/hierarchy?project=RIPLEY"` **después** de apretar "Sincronizar" ⇒ `epics` **y/o** `orphans` **no vacíos**.
**(d) Control de no-regresión (Zscaler).** `GET https://gitlab.com/api/v4/version` **por la sesión normal** (sin adapter) ⇒ **HTTP 401**. Si acá aparece un `SSLError`, el adapter se montó de más y se rompió el resto del producto.

**Criterio de aceptación (binario):** **(a) 401, (b) 200 con `X-Total`>0, (c) no vacío, (d) 401 — los cuatro en la misma corrida.** Si los cuatro no salen juntos, el plan **no cerró**.

**Flag:** ninguna. **Runtime:** idéntico en los 3. **Trabajo del operador: ninguno** (el smoke lo corre quien implementa).

---

## 5. Reglas antifalso-verde (obligatorias, van dentro de cada fase)

1. **Todo test de TLS corre con `truststore.inject_into_ssl()` aplicado.** Sin eso no prueba producción: los 27 verdes actuales conviven con el bug por exactamente esto. La inyección va a nivel de módulo, **antes** de importar lo que se prueba, y cada archivo lleva un `test_el_entorno_de_test_replica_produccion` que falla si la inyección no ocurrió. Un test de TLS sin ese caso **no se acepta**.
2. **El criterio se assertea sobre el LISTADO REAL, nunca sobre la sonda.** `GET /user` devuelve 200 con cualquier token válido aunque el proyecto esté mal escrito. La condición binaria es `fetch_open_items` devolviendo **N > 0** issues **y** el grafo mostrándolos. Ninguna fase puede cerrarse con "la sonda dio verde".
3. **El check de la UI reporta por separado TLS / auth / proyecto legible / N ítems**, y sale verde **solo si los cuatro pasan** (F4). Hoy `local_diagnostics.py:201` hace un único `GET /user` y el rótulo de `:122` es un **NOMBRE** ("gitlab alcanzable"), no un veredicto: nunca se hizo ping.
4. **Smoke de cierre que aísla los TRES fallos en UNA corrida** (ruteo → TLS → 404), con RIPLEY activo y truststore inyectado (F11). Cada fix histórico reveló el siguiente; aislarlos de a uno cuesta tres viajes.
5. **`GITLAB_TOKEN` dummy para separar TLS de AUTH** en tests y smokes. Además evita que `gitlab_client.py:78-80` lea y **reescriba** el archivo de credenciales. TLS OK ⇒ `TrackerApiError` 401; TLS roto ⇒ `SSLError`.
6. **Test de TLS hermético — limitación medida y declarada.** El ideal sería levantar un servidor TLS local con un cert auto-emitido cuya CA no esté en el store de Windows. **No es posible en este venv sin agregar dependencias**, y se verificó: no hay `cryptography`, no hay `pyOpenSSL`, no hay `trustme` y **`openssl` no está en el PATH ni en Git for Windows** (F0 paso 2). La stdlib no genera certificados. Por lo tanto:
   - **Capa hermética (F1, obligatoria, sin red y sin certs generados):** que el contexto sea OpenSSL genuino y no de truststore (discriminador independiente: `cert_store_stats()` responde en el genuino y lanza `NotImplementedError` en el de truststore, `truststore/_api.py:195`); que `verify_mode` se pueda setear **sin `RecursionError`**; que `VERIFY_X509_PARTIAL_CHAIN` esté puesto con `verify_mode == CERT_REQUIRED` y `check_hostname is True`; que el bundle haya entrado **incluida la hoja**, medido con `cert_store_stats()` (`x509 - x509_ca == 1`) y **nunca** con `get_ca_certs()`, que es ciego a los certificados no-CA (medido: 118 de 119, y **0 de 1** para `srvcgit01-ca.pem`); y que nada global haya cambiado.
   - **Capa de handshake real:** vive en el smoke de F11 contra el servidor real, no en `pytest`.
   - **Prohibido** agregar `cryptography`, `trustme` o cualquier dependencia nueva para saltear esta limitación. Si alguna vez se agrega por otro motivo, el test de servidor local se suma entonces — no antes.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **`RecursionError` al montar el adapter — y creer que es un problema de certificados.** `urllib3/connection.py:937` ejecuta `context.verify_mode = resolve_cert_reqs(cert_reqs)` **siempre**, aun con `ssl_context` provisto (verificado: la línea está fuera del `if ssl_context is None:` de `:926`). El setter de CPython resuelve `SSLContext` desde el módulo `ssl`, ya pisado por truststore ⇒ recursión infinita. **Un adapter ingenuo NO falla con un error de TLS: falla con `RecursionError`**, y el implementador va a creer que se equivocó de certificado, de bundle o de host. | Las properties delegadas de `_construir_clase_genuina` (F1.2) son **exactamente** la salida, validada en vivo. F0 paso 3 **reproduce el error a propósito** antes de empezar, y `test_setear_verify_mode_no_lanza_recursion_error` (F1.1) es el gate corrido contra ese defecto. **Qué NO es:** no es el certificado equivocado, no es el bundle mal armado, no es el hostname, no es el proxy. Es el setter de `ssl.py` resolviendo un nombre global envenenado. |
| Montar el adapter de más y romper ADO/Jira/LLM/gitlab.com (Zscaler). | El adapter se monta **solo** cuando hay bundle y **solo** para el prefijo `self._base_url` (F2.2b). `test_sin_bundle_no_monta_nada` y `test_no_toca_la_sesion_global_de_requests` (F2.1) lo vigilan, y F11 (d) lo prueba contra `gitlab.com` real. |
| Que alguien "arregle" el problema con `truststore.extract_from_ssl()`. | Prohibido explícitamente (§3.2) con el motivo escrito: es global y `connection_doctor.py:374` corre 4 probes en paralelo en un `ThreadPoolExecutor`. |
| Que el gate del bundle use `get_ca_certs()` y dé rojo para siempre. | Documentado tres veces (§2.3, F1.1, §5 regla 6) con la medición: `get_ca_certs()` devuelve **0** para `srvcgit01-ca.pem`. El gate correcto es `cert_store_stats()`. |
| **`NameError` para ADO/Jira/Mantis** al cambiar `"ok": True` por `"ok": ok` en `global_config.py:389`, porque `ok` solo existe en la rama GitLab. | F4 obliga a inicializar `ok = True` antes de las ramas, y agrega un caso de test específico ("`ok` sigue siendo True para un tracker ADO"). |
| Que F5 borre tickets del operador. | El sync **nunca borra**: marca `ado_state="closed"`. Explícito en el docstring y con test propio ("la fila sigue existiendo"). |
| Flipear `STACKY_TICKETS_PROVIDER_ENABLED` "de paso" y romper el plan 70. | Prohibido (§3.2). F5.3 resuelve el provider localmente y solo para trackers no-ADO, con un test que verifica que para ADO el bloque nuevo **no se ejecuta**. |
| El expiry de la hoja: `notAfter = Jun 14 2028`. | Documentado en `deployment/README_certificados.md` (F9/P2-5). Cuando el cert se renueve, hay que reemplazar el `.pem`; el mensaje de `CaBundleInvalido` y los 4 sub-veredictos de F4 hacen que el día que pase se vea en 10 segundos en vez de en una jornada. |
| Una sesión paralela tocando los mismos archivos. | Antes de F1, correr `git worktree list` y `git status`. Los archivos de la frontera (`gitlab_client.py`, `tls_pinning.py`, `global_config.py`, `local_diagnostics.py`, `tracker_provider.py`, `project_context.py`, `gitlab_provider.py`) tienen **cambios sin commitear** al momento de escribir este plan (§2.4): **no** hacer `stash`, `reset`, `rebase` ni `checkout`; commitear con pathspec explícito. |

---

## 7. Fuera de scope

- **Sync automático, polling o prefetch de GitLab.** Caería en la categoría A (quema tokens/recursos en reposo) y obligaría a una flag OFF. El sync es y queda **on-demand**.
- **Épicas nativas de GitLab (Premium).** `STACKY_GITLAB_EPICS_NATIVE` sigue en `False` (`config.py:1325-1326`) y `provider_capabilities.py:252-255` lo declara. F5 deriva la jerarquía de las labels `type::*` y del `epic` cuando exista; sin Premium, los issues caen en `orphans`, que es un resultado **correcto y visible**, no un fallo.
- **Escritura hacia GitLab** (crear/actualizar issues desde Stacky). Ya existe por otra vía (`gitlab_provider`, planes 218/266/270) y no es el eje de este plan.
- **Los rótulos de navegación global** `App.tsx:455`, `SettingsPage.tsx:47`, `shellNav.ts:18`, `commandPaletteData.ts:74`: no dependen del proyecto activo y `commandPaletteDevopsActions.test.ts:109-110` assertea sobre el literal. Decisión de producto pendiente, no olvido.
- **Migrador Mantis→GitLab** (`tools/migrar_mantis_gitlab/`). Solo se re-apunta su helper de TLS (F2.3); su lógica de migración no se toca.
- **Refactor de `_request` a un cliente HTTP nuevo.** Se conserva `requests` y la forma de `_request`; solo se cambia el transporte y se agrega el `try`.
- **Subir el techo de 4.000 issues** (P2-1). Se agrega el log, no se cambia el cap: subirlo sin medir es un problema distinto.
- **Cualquier dependencia nueva** (`cryptography`, `trustme`, `pytest-httpserver`). Prohibido (§5 regla 6).

---

## 8. Glosario

- **truststore** — biblioteca que hace que Python verifique TLS usando el almacén de certificados del **sistema operativo** en vez del bundle de `certifi`. Stacky la inyecta en `backend/app.py:24-28` porque la red corporativa tiene inspección TLS de Zscaler. Al inyectarse, **reemplaza `ssl.SSLContext` para todo el proceso**.
- **Zscaler** — proxy corporativo que intercepta el tráfico TLS y lo re-firma con su propia CA. Por eso `gitlab.com` llega firmado por `Zscaler Intermediate Root CA` y falla contra `certifi`: es un "man in the middle" legítimo e instalado en el store de Windows.
- **Hoja vs CA** — el certificado *hoja* es el del servidor (`CN=srvcgit01.imsolutions.local`); la *CA* es quien lo emitió (`CN=imsolutions.local`). Normalmente se confía en la CA. Acá la CA **no está** en ningún almacén y el servidor manda **un solo certificado**, así que hay que confiar en la hoja directamente.
- **`VERIFY_X509_PARTIAL_CHAIN`** — flag de OpenSSL que permite que un certificado **no auto-firmado** presente en el bundle actúe como ancla de confianza. Sin ella, OpenSSL busca la emisora, no la encuentra y falla con `unable to get local issuer certificate` aunque la hoja exacta esté en el bundle. **No debilita** la verificación: es *pinning* (la hoja tiene que coincidir exactamente) y `check_hostname` sigue activo.
- **`cert_store_stats()` vs `get_ca_certs()`** — `cert_store_stats()` devuelve `{'x509': total, 'x509_ca': cuántos son CA}`. `get_ca_certs()` devuelve **solo los que son CA**, así que es **ciego a las hojas**. Por eso el gate del bundle usa el primero.
- **`HTTPAdapter`** — objeto de `requests` que define cómo se abren las conexiones de una sesión. Montarlo por prefijo (`session.mount("https://host", adapter)`) permite que **una sola URL** use un contexto TLS distinto del resto del proceso.
- **Ratchet** — test que congela una métrica (cantidad de archivos registrados, deuda de estilos, etc.) y solo la deja bajar, nunca subir. Acá: `backend/scripts/run_harness_tests.sh` / `.ps1`, donde **todo test nuevo debe registrarse en los dos**.
- **Arnés** — la suite de tests de referencia del repo (`run_harness_tests`), el único veredicto válido; correr `pytest tests` entero **no** lo es (contaminación cruzada).
- **`TrackerTarget`** — dataclass de `services/project_context.py:66-79` que resuelve, por proyecto, a qué tracker se escribe y con qué credenciales. Su docstring todavía dice "CONGELADO por el Plan 218" pero ya fue ampliado con `ca_bundle` (`:79`): **el docstring miente**, el campo existe.
- **`CapabilityUnavailable`** — excepción tipada del plan 218 para decir "este proveedor no tiene esta capacidad". No es un bug: se traduce a **HTTP 200 con `available:false`** y un mensaje accionable, en vez de un 500 mudo.
- **Falso verde** — un test o un check que pasa **sin probar lo que dice probar**. Ejemplos vivos en este repo: `assert x is not False` que pasa cuando `x` desaparece; un `assert` de ausencia que nunca verificó que el valor se hubiera guardado; y 27 tests de TLS que no corren con truststore inyectado.

---

## 9. Orden de implementación

1. **F0** — línea base (solo verificación, sin código). **No saltear**: reproduce la trampa del `RecursionError` antes de que aparezca sola.
2. **F1** — `services/tls_openssl_context.py` + sus 9 tests. Es la pieza de la que dependen todas las demás.
3. **F2** — el adapter en la sesión de GitLab + `try` en `_request` + borrado del parche global de urllib3. **A partir de acá el GitLab interno responde.**
4. **F3** — bundle estricto (fail-closed) + validación de `base_url`.
5. **F4** — los 4 sub-veredictos del check (incluye el fix del `NameError` de `global_config.py:389`).
6. **F5** — el sync GitLab → BD (`work_item_type`, `gitlab_sync.py`, ruteo, registro de capacidades). **Depende de F2.**
7. **F6** — `sync-v2` deja de tragarse `CapabilityUnavailable` + `errors.py` deja de poner `ok:true` + guarda en `useTicketSync`. **Depende de F5.**
8. **F7** — el grafo + los rótulos por tracker. **Depende de F5.**
9. **F8** — los tres agujeros de configuración (rama legacy, `buildPayload`, `normalizeGitlabUrl`).
10. **F9** — los cinco P2.
11. **F10** — endurecer los 5 tests existentes. **Va después de F1-F9** porque varios se reescriben contra el diseño nuevo.
12. **F11** — smoke de cierre con los cuatro checks en una sola corrida.

## 10. Definición de Hecho (DoD)

- Los **10 archivos de test nuevos** existen, están en verde y **registrados en los DOS ratchets** (`run_harness_tests.sh` **y** `.ps1`, con la sintaxis de cada uno), con el conteo de casos verificado por archivo: `test_plan276_tls_context.py` (9), `test_plan276_gitlab_session_adapter.py` (9), `test_plan276_tls_bundle_estricto.py` (8), `test_plan276_probe_verdict.py` (7), `test_plan276_gitlab_sync.py` (12), `test_plan276_capability_envelope.py` (5), `test_plan276_hierarchy_gitlab.py` (5), `test_plan276_config_gaps.py` (3), `test_plan276_client_limits.py` (6) — **64 casos backend**.
- Los **3 archivos de test de frontend** nuevos en verde, corridos **uno por uno**: `plan276SyncEnvelope.test.ts` (4), `plan276TrackerLabels.test.ts` (5), `plan276GitlabUrlNormalize.test.ts` (6) — **15 casos**.
- Los **5 tests existentes endurecidos** (F10) en verde, con **≥ 27 casos** en total (nunca menos).
- **Cero** parches globales: `Select-String -Path services\tls_pinning.py -Pattern "create_urllib3_context"` devuelve **0**; `grep -rn "extract_from_ssl\|REQUESTS_CA_BUNDLE *=" backend/services backend/api` no devuelve ninguna **escritura** nueva.
- `Select-String -Path api\errors.py -Pattern 'setdefault\("ok"'` devuelve **0**.
- `Select-String -Path api\tickets.py -Pattern "Plan 220 lo implementa"` devuelve **0**.
- **Smoke de F11 con los cuatro checks en una sola corrida**: (a) 401, (b) 200 con `X-Total`>0, (c) `hierarchy` no vacío, (d) `gitlab.com` 401.
- **Smoke manual de F7** (8 pasos) ejecutado, con captura del paso 6.
- Las **3 flags nuevas** registradas en los **6 puntos** de §3.4, las tres con `default=True`, las tres en la categoría `paridad_proveedores`, y `& $PY -m pytest tests\test_harness_flags.py -q` en verde.
- `& $PY -m pytest tests\test_harness_ratchet_meta.py -q` en verde (los 10 archivos nuevos parsean en el `.sh`).
- **Cero dependencias nuevas**: `pip list` idéntico antes y después.
- **Cero trabajo nuevo para el operador.** Ninguna flag nace OFF. Ninguna variable de entorno nueva de operador.
