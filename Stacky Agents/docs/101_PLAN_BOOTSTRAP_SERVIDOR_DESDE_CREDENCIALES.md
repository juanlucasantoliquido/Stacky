# Plan 101 — Bootstrap de servidor desde credenciales: inicializar un servidor remoto (filesystem + config base + publicación inicial) con un click HITL

**Estado:** PROPUESTO (v1)
**Versión:** v1
**Fecha:** 2026-07-06
**Autor:** StackyArchitectaUltraEficientCode
**Serie:** capstone de la serie DevOps — conecta el registro de servidores (Plan 91),
la inicialización de ambientes (Plan 89) y las publicaciones (Plan 88) en un flujo
único "servidor nuevo → listo para operar". Es EXACTAMENTE el plan que el 89 y el 91
dejaron anunciado: `server_registry.get_credential` existe hoy "para consumo de la
extensión remota futura (88/89/90)... este es ese plan"
(`backend/services/server_registry.py:6-8`), y el 89 dejó escrito que "remoto exigiría
credenciales y otro plan" (`server_registry.py:6-8` cita `89_PLAN_...:958-960`). NO
depende de los planes 93-96, 98, 99, 100 (todos PROPUESTOS o paralelos); ninguno
depende de este.

**Dependencias (todas IMPLEMENTADAS y verificadas en el working tree 2026-07-06):**

| Pieza existente reusada | Evidencia (archivo:línea) |
|---|---|
| `server_registry.get_credential(alias) -> (username, domain, password) \| None` — CONTRATO declarado para esta extensión | `backend/services/server_registry.py:205-218` |
| `server_registry.get_server` / `list_servers` / `validate_host` / `has_password` | `backend/services/server_registry.py:84-98,51-52,196-202` |
| Patrón de subprocess SEGURO con credenciales (lista de args sin shell, `except Exception` genérico A PROPÓSITO, NUNCA loggear el comando) — Plan 91 C1 | `backend/api/devops_servers.py:147-164` (RDP/cmdkey) |
| `environment_init`: `build_environment_layout` (puro), `plan_environment` (solo lectura), `apply_environment` (crea SOLO to_create), `validate_root`, `is_safe_segment`, `layout_fingerprint`, `allExistsOk` | `backend/services/environment_init.py:110,162,95,4-9`; front `frontend/src/devops/environmentModel.ts` |
| `apply_environment` usa `os.makedirs` (hoy LOCAL; este plan agrega el puente remoto SIN tocar esta función) | `backend/services/environment_init.py:188` |
| `build_publication_spec` (preset → spec) para la publicación inicial | `backend/services/publication_spec.py` (usado en `api/devops.py:101`) |
| `EnvironmentsSection` (wizard plan-then-apply + publicación inicial) — patrón UI a espejar | `frontend/src/components/devops/EnvironmentsSection.tsx:143-217` |
| `ctx.selectedServer` (Plan 91 F6) — cableado HOY SIN CONSUMIDOR; este plan es su primer consumidor | `frontend/src/pages/DevOpsPage.tsx:145` (grep: solo un test lo referencia) |
| Health SIEMPRE-200 con booleans aditivos + `rdp_available` (win32 + keyring) | `backend/api/devops.py:26-40` |
| Guard per-request por flag `abort(404)` | `backend/api/devops.py:47-48` |
| `keyring==25.6.0` en requirements (NO hay pywinrm/smbprotocol) | `backend/requirements.txt:11` |
| Patrón flag 5 patas + gotchas | `backend/config.py:895-898`, `backend/services/harness_flags.py:177-184`, `harness_flags_help.py:632-637`, `backend/harness_defaults.env`, ratchet `backend/scripts/run_harness_tests.ps1:127-129`, `_REQUIRES_MAP_FROZEN` en `backend/tests/test_harness_flags_requires.py` |
| Patrón de test vitest TS-puro + tests backend con test client Flask | `frontend/src/pages/__tests__/ServersSection.test.ts:1-27`, `backend/tests/test_plan91_servers_flag.py` |

**GAP VERIFICADO:** `apply_environment` crea carpetas SOLO en el filesystem del host del
backend (`os.makedirs`, `environment_init.py:188`). No existe NINGÚN puente para crear
el layout en un servidor REMOTO usando las credenciales del keyring (grep de `net use`,
`pywinrm`, `winrm`, `smbprotocol` en `backend/` = 0 matches; el único subprocess con
credenciales es el RDP del 91). `ctx.selectedServer` (91 F6) está cableado en
`DevOpsPage.tsx:145` pero NINGUNA sección lo consume. Conclusión: el gap es real; este
plan lo cierra reusando `get_credential` (que existe para esto) + el patrón de
subprocess seguro del 91, sin tocar `apply_environment` local ni agregar dependencias.

---

## 1. Objetivo + KPI

Con un servidor YA registrado en el Plan 91 (alias + host + credenciales en keyring),
un botón **"Inicializar servidor"** ejecuta un **plan-then-apply REMOTO HITL** que:
(1) monta una conexión autenticada al filesystem del servidor con las credenciales del
keyring, (2) calcula el plan de carpetas del layout del catálogo (dry-run, solo
lectura remota), (3) tras confirm del operador, crea SOLO las carpetas faltantes en el
servidor, (4) deposita un archivo de configuración base mínimo, (5) verifica
post-apply que todo exista, y (6) opcionalmente encadena la publicación inicial del
Plan 88 apuntada al servidor. Flag propia default OFF. Nada se aplica sin el confirm
(el plan-then-apply YA es HITL). Cero credenciales en logs/respuestas/excepciones.

**KPI (medibles; los binarios están en cada fase):**

| Métrica | Hoy | Después | Cómo se mide |
|---|---|---|---|
| Pasos para preparar el filesystem de un servidor nuevo | 100% manual (RDP al server + crear carpetas a mano + copiar config) | 1 selección de servidor + ver plan + 1 confirm | conteo manual + test del flujo plan→apply |
| Consumidores de `ctx.selectedServer` (91 F6) | 0 (cableado muerto) | 1 (esta sección) | grep |
| Credenciales expuestas en logs/respuestas/excepciones | (RDP ya es seguro; el resto no existía) | 0 por diseño (patrón 91 C1 extendido) | test `no fuga de password en error` |
| Carpetas creadas fuera del layout aprobado | N/A | 0 (server-side re-planifica; solo intersección con el layout del catálogo real) | test `apply solo crea la intersección` (espeja 89) |

## 2. Por qué ahora / gap que cierra (evidencia)

El Plan 91 guardó credenciales en keyring y dejó `get_credential` explícitamente "para
la extensión remota futura... este es ese plan" (`server_registry.py:6-8,205-218`). El
Plan 89 construyó todo el motor plan-then-apply (`environment_init.py`) pero LOCAL, y
anotó que el remoto "exigiría credenciales y otro plan". El Plan 91 F6 cableó
`ctx.selectedServer` sin ningún consumidor (`DevOpsPage.tsx:145`). Las tres piezas están
listas y desconectadas: este plan las une. Es el salto de POTENCIA del panel: pasar de
"registro credenciales y me conecto por RDP" a "inicializo el servidor entero desde
Stacky". El costo es acotado: reusa el motor del 89 (agregando un backend de I/O
remoto), el patrón de subprocess seguro del 91, y la UI del wizard del 89.

## 3. Principios y guardarraíles (no negociables, verificables)

1. **DECISIÓN DE TRANSPORTE — UNC + credenciales del keyring vía `net use` (default),
   WinRM como opción documentada fuera de scope. Justificación dura:**
   - **UNC + `net use`** usa SOLO stdlib (`subprocess`, patrón EXACTO del RDP del 91) y
     `os`/`pathlib` sobre la ruta UNC montada. **Cero dependencias nuevas.** El servidor
     objetivo es Windows (el mismo universo del 91: RDP/cmdkey/TERMSRV) y ya comparte
     recursos por SMB en el mundo del operador. Es el transporte de menor superficie y
     máxima coherencia con la casa.
   - **WinRM (pywinrm/pypsrp)** exigiría una **dependencia nueva** (no está en
     `requirements.txt:11` — solo `keyring`), habilitar/servir WinRM en cada servidor
     (configuración extra del operador — viola "cero trabajo extra"), y abre una
     superficie de ejecución remota de comandos mucho mayor. **Se descarta como default**
     y se documenta como evolución futura (Fuera de scope) para escenarios sin SMB.
   - **Fallback explícito:** si el `net use` falla (SMB bloqueado, credenciales
     inválidas, host inalcanzable), el flujo ABORTA con un mensaje accionable SIN tocar
     nada y SIN filtrar la credencial; el operador sigue teniendo el RDP del 91 para
     hacerlo a mano. No hay fallback a WinRM en v1 (no está la dependencia).
   - **Mecánica exacta:** montar con `net use \\{host}\{share} /user:{domain\\user} {password}`
     (lista de args, sin shell, sin log — patrón 91 C1); operar el FS por la ruta UNC;
     desmontar con `net use \\{host}\{share} /delete` en un `finally`. El `share` y la
     subruta salen del `environment_root` del server (ver F1).
2. **Seguridad de credenciales (patrón 91 C1, EXTENDIDO — obligatorio):**
   - El password se lee SOLO de `get_credential` (keyring), NUNCA viaja en el body de
     request/response, NUNCA se persiste, NUNCA se loggea.
   - Todo subprocess con el password va como **lista de args, sin `shell=True`**, con
     `capture_output=True`, y su excepción se captura con `except Exception` **genérico
     A PROPÓSITO** porque `TimeoutExpired`/`OSError` incluyen el comando (con el
     password) en su mensaje — JAMÁS se deja propagar ni se mete en el error de la
     respuesta (idéntico a `devops_servers.py:147-156`).
   - Los mensajes de error al operador son GENÉRICOS ("no se pudo montar el recurso
     remoto: credenciales o red"), nunca el stderr crudo del `net use` (podría reflejar
     el argumento).
   - `validate_host` (91 C2, `server_registry.py:51-52`) se aplica al host antes de
     interpolarlo en la UNC; el `share`/subruta se validan con `is_safe_segment`
     (89 C12) — sin `..`, sin caracteres inválidos, sin absolutas.
3. **HITL innegociable:** plan (dry-run, solo lectura remota) → el operador VE las
   carpetas a crear + el archivo de config → confirm explícito (checkbox +
   `fingerprint` del plan visto, como 89) → apply → verify. Nada se crea sin el confirm.
   La publicación inicial (paso 6) es un paso APARTE con su propio confirm (reusa el
   commit HITL del 88). Stacky nunca inicializa un servidor por su cuenta.
4. **Flag propia default OFF + gotchas:** `STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED`
   (default OFF). `FlagSpec` SIN kwarg `default` (gotcha Plan 63). Arista
   `STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED → STACKY_DEVOPS_SERVERS_ENABLED` en
   `_REQUIRES_MAP_FROZEN` (necesita el registro de servidores del 91; profundidad 1:
   SERVERS requiere PANEL, así que la cadena BOOTSTRAP→SERVERS→PANEL respeta R4 —
   VERIFICAR que R4 permita la cadena de longitud 2; si el validador exige profundidad
   1 estricta, apuntar `requires` a `STACKY_DEVOPS_PANEL_ENABLED` y documentar la
   dependencia funcional de SERVERS en la descripción, como hace el 89 con sus deps).
   Registrar en las 5 patas + ratchet.
5. **Cero trabajo extra del operador:** opt-in (flag OFF); el flujo REUSA el servidor y
   las credenciales que el operador ya cargó en el 91 y el `environment_root`/catálogo
   que ya configuró en el 89 — no pide nada nuevo. Backward-compatible: `apply_environment`
   LOCAL (89) no cambia; el remoto es una función NUEVA aparte.
6. **No degradar `apply_environment` local:** el motor del 89 (`environment_init.py`)
   NO se toca en su comportamiento local. El remoto se implementa como funciones nuevas
   que REUSAN las puras (`build_environment_layout`, `plan_environment` sobre la ruta
   UNC ya montada) — `plan_environment` ya opera sobre cualquier `root` que sea un path
   accesible, así que sobre la UNC montada funciona sin cambios.
7. **3 runtimes (Codex CLI, Claude Code CLI, GitHub Copilot Pro):** impacto NINGUNO —
   panel + endpoints backend de infraestructura; ningún runner/prompt/harness los
   consume (precedente 78/91/98/99/100). El bootstrap corre en el HOST del backend
   (igual que el RDP del 91, `devops_servers.py:128-129`): Stacky es mono-operador y
   corre local. Verificable por grep.
8. **Mono-operador sin auth:** N/A (sin RBAC; las credenciales del server son del
   operador único, en su keyring).
9. **Solo Windows (paridad honesta):** el bootstrap remoto por UNC/`net use` es win32
   (como el RDP del 91). En no-win32 el endpoint responde con un error claro
   ("bootstrap remoto disponible solo en Windows") y el health expone
   `server_bootstrap_available: (sys.platform=='win32') and keyring_available()` —
   la UI no muestra el botón si no está disponible (mismo patrón que `rdp_available`).

---

## F0 — Flag `STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED` (5 patas) + keys de health

**Objetivo:** dar de alta la flag que protege el plan (default OFF, editable por UI) y
exponer al frontend `server_bootstrap_enabled` + `server_bootstrap_available`.
**Valor:** el guard existe antes que los endpoints; la UI sabe si mostrar el botón.

**Archivos a editar (exactos):**

1. `Stacky Agents/backend/config.py` — tras `STACKY_DEVOPS_STACK_DETECT_ENABLED`
   (`config.py:895-898`):

```python
# Plan 101 — Bootstrap de servidor remoto (filesystem + config + publicacion). Default OFF.
STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED: bool = os.getenv(
    "STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED", "false"
).lower() in ("1", "true", "yes")
```

2. `Stacky Agents/backend/services/harness_flags.py`:
   - Última entrada de `_CATEGORY_KEYS["devops"]` (hoy `:177-184`):
     `"STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED",  # Plan 101 — bootstrap de servidor remoto`.
   - `FlagSpec` en `FLAG_REGISTRY` tras la de `STACKY_DEVOPS_STACK_DETECT_ENABLED`:

```python
    # ── Plan 101 — Bootstrap de servidor remoto ─────────────────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED",
        type="bool",
        label="Inicializar servidor (Plan 101)",
        description=(
            "Plan 101 — Prepara un servidor remoto ya registrado (Plan 91) desde "
            "Stacky: crea el arbol de carpetas del catalogo (Plan 89) en el "
            "filesystem del servidor via recurso compartido con las credenciales "
            "guardadas, deja una config base y puede encadenar la publicacion "
            "inicial (Plan 88). HITL: muestra el plan y exige confirm; nada se crea "
            "sin aprobacion. Requiere el registro de servidores. Solo Windows. "
            "Con OFF la seccion no aparece y los endpoints dan 404."
        ),
        group="global",  # mismo group que STACKY_DEVOPS_PANEL_ENABLED
        env_only=False,  # editable por UI (categoría 'devops')
        requires="STACKY_DEVOPS_SERVERS_ENABLED",  # necesita el registro del 91
    ),
```

   **PROHIBIDO** pasar `default=False` (gotcha Plan 63).

3. `Stacky Agents/backend/services/harness_flags_help.py` — junto a las devops
   (`:632-637`):

```python
    "STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED": PlainHelp(
        what="Con un servidor ya guardado, Stacky le arma las carpetas y una config base en un paso, usando las credenciales que ya cargaste.",
        on_effect="Si la activás: aparece 'Inicializar servidor' en el panel DevOps. Elegís un servidor, ves qué carpetas se van a crear, confirmás, y Stacky las crea en el servidor por red y deja una config base. Podés seguir con la publicación inicial. Solo Windows.",
        off_effect="Si la apagás: no cambia nada; la sección no aparece y preparás el servidor a mano (por escritorio remoto).",
        example="Como cuando enchufás una impresora nueva y el sistema la deja lista sola, pero para las carpetas y la config de un servidor.",
    ),
```

4. `Stacky Agents/backend/harness_defaults.env` — línea
   `STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED=false` junto a las DEVOPS.

5. `Stacky Agents/backend/api/devops.py` — en `devops_health_route` (`:26-40`), 2 keys:

```python
        "server_bootstrap_enabled": bool(getattr(cfg, "STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED", False)),  # Plan 101
        "server_bootstrap_available": (sys.platform == "win32") and server_registry.keyring_available(),  # Plan 101
```

6. `Stacky Agents/backend/tests/test_harness_flags_requires.py` — agregar
   `"STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED": "STACKY_DEVOPS_SERVERS_ENABLED",` a
   `_REQUIRES_MAP_FROZEN`. **Si `validate_requires_graph` rechaza la cadena de longitud
   2** (BOOTSTRAP→SERVERS→PANEL), cambiar `requires` (paso 2) a
   `"STACKY_DEVOPS_PANEL_ENABLED"` y ajustar esta línea en consecuencia; documentar la
   dependencia real de SERVERS en la `description`. Correr
   `test_harness_flags_requires.py` para decidir cuál aplica (criterio binario: el test
   pasa).

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/backend/tests/test_plan101_server_bootstrap_flag.py`, 5 casos:

1. `test_flag_registered_bool` — `FlagSpec` con la key, `type=="bool"`, `env_only is False`.
2. `test_flag_categorized_devops` — la key está en `_CATEGORY_KEYS["devops"]`.
3. `test_flag_requires_valid` — `spec.requires` es `STACKY_DEVOPS_SERVERS_ENABLED` o
   `STACKY_DEVOPS_PANEL_ENABLED` (según lo que R4 acepte) y la arista está en
   `_REQUIRES_MAP_FROZEN`.
4. `test_default_off_effective` — env limpio ⇒
   `config.STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED is False`.
5. `test_health_exposes_bootstrap_keys` — `GET /api/devops/health` 200 con
   `server_bootstrap_enabled: False` y la key `server_bootstrap_available` presente
   (bool).

**Comandos (venv real `.venv`):**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan101_server_bootstrap_flag.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_requires.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q
```

**Criterio de aceptación (binario):** 5 tests nuevos verdes + los 3 meta-tests del
arnés verdes.
**Flag:** `STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED`, default OFF.
**Impacto por runtime:** NINGUNO. Fallback: N/A.
**Trabajo del operador:** ninguno (opt-in default off).

---

## F1 — Servicio `server_bootstrap.py`: montaje UNC seguro + settings del servidor (backend puro + subprocess aislado)

**Objetivo:** encapsular el montaje/desmontaje UNC autenticado y la resolución del
`environment_root` remoto del servidor, con toda la seguridad de credenciales.
**Valor:** el corazón backend; toda la superficie peligrosa (subprocess con password)
vive en un módulo chico y testeable con subprocess mockeado.

**Archivo NUEVO:** `Stacky Agents/backend/services/server_bootstrap.py`

```python
"""services/server_bootstrap.py — Plan 101.

Bootstrap de un servidor remoto: monta un recurso UNC con las credenciales del keyring
(Plan 91, get_credential), opera el filesystem por la ruta montada reusando el motor
puro del Plan 89 (plan_environment/apply_environment sobre esa ruta) y desmonta SIEMPRE.

SEGURIDAD (patron Plan 91 C1, EXTENDIDO):
- El password se lee SOLO de server_registry.get_credential; NUNCA se loggea, NUNCA
  entra en el mensaje de una excepcion propagada, NUNCA vuelve en una respuesta.
- Todo subprocess con el password: lista de args, sin shell, capture_output, y
  except Exception GENERICO a proposito (TimeoutExpired/OSError traen el comando).
- Los mensajes hacia arriba son genericos (nunca el stderr crudo del net use).
"""
import os
import subprocess
import sys
from contextlib import contextmanager

from services import server_registry
from services.environment_init import is_safe_segment

# El "share" y la subruta del root remoto salen de las settings del servidor (F1 UI/F2).
# Formato del environment_root remoto del server: r"\\host\share\sub\ruta" (UNC) o una
# ruta local del server que se expone como \\host\share. v1 exige UNC explicita.


class ServerBootstrapError(Exception):
    """Error de bootstrap con mensaje YA saneado (sin credenciales)."""


def _run_net_use_mount(unc_share: str, user_arg: str, password: str) -> None:
    """Monta unc_share con credenciales. Lista de args, sin shell, sin log (91 C1)."""
    try:
        rc = subprocess.run(
            ["net", "use", unc_share, f"/user:{user_arg}", password],
            capture_output=True, timeout=20,
        )
    except Exception:  # noqa: BLE001 — la excepcion contiene el password: JAMAS propagar
        raise ServerBootstrapError("No se pudo montar el recurso remoto (timeout o error de red).")
    if rc.returncode != 0:
        # stderr puede reflejar el comando: mensaje GENERICO, nunca rc.stderr crudo.
        raise ServerBootstrapError("No se pudo montar el recurso remoto (credenciales o permisos).")


def _run_net_use_unmount(unc_share: str) -> None:
    try:
        subprocess.run(["net", "use", unc_share, "/delete", "/y"],
                       capture_output=True, timeout=20)
    except Exception:  # noqa: BLE001 — best-effort: si ya no estaba montado, silencio
        pass


def _parse_unc(environment_root_remote: str) -> tuple[str, str]:
    r"""De r'\\host\share\sub\ruta' devuelve (unc_share=r'\\host\share', full_root=el mismo path).
    Valida host (91 C2) y que las subrutas sean seguras (89 C12). Lanza ServerBootstrapError."""
    p = environment_root_remote
    if not (isinstance(p, str) and p.startswith("\\\\")):
        raise ServerBootstrapError("environment_root remoto debe ser una ruta UNC (\\\\host\\share\\...).")
    parts = [seg for seg in p[2:].split("\\") if seg != ""]
    if len(parts) < 2:
        raise ServerBootstrapError("environment_root remoto debe incluir host y recurso compartido.")
    host, share = parts[0], parts[1]
    if not server_registry.validate_host(host):
        raise ServerBootstrapError("host invalido en el environment_root remoto.")
    for seg in parts[2:]:  # subrutas: sin '..', sin caracteres invalidos (89 C12)
        if not is_safe_segment(seg):
            raise ServerBootstrapError("subruta invalida en el environment_root remoto.")
    unc_share = "\\\\" + host + "\\" + share
    return unc_share, p


@contextmanager
def mounted_remote_root(alias: str, environment_root_remote: str):
    """Context manager: monta el share con las credenciales del alias, entrega el root
    UNC completo (usable con os/plan_environment/apply_environment) y desmonta SIEMPRE."""
    if sys.platform != "win32":
        raise ServerBootstrapError("El bootstrap remoto esta disponible solo en Windows.")
    cred = server_registry.get_credential(alias)
    if cred is None:
        raise ServerBootstrapError(f"'{alias}' no tiene credencial guardada (o keyring no disponible).")
    username, domain, password = cred
    user_arg = f"{domain}\\{username}" if domain else username
    unc_share, full_root = _parse_unc(environment_root_remote)
    _run_net_use_mount(unc_share, user_arg, password)
    try:
        yield full_root
    finally:
        _run_net_use_unmount(unc_share)
```

**Casos borde fijados:** no-win32 ⇒ `ServerBootstrapError` claro; sin credencial ⇒
error claro; UNC mal formada / host inválido / subruta insegura ⇒ `ServerBootstrapError`
ANTES de tocar la red; el `finally` desmonta aunque el apply falle; NINGÚN mensaje
incluye el password ni el stderr crudo del `net use`.

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/backend/tests/test_plan101_server_bootstrap_service.py`, 9 casos
(subprocess y keyring MOCKEADOS — monkeypatch de `subprocess.run` EN
`services.server_bootstrap` y de `server_registry.get_credential`; se fuerza
`sys.platform` con monkeypatch):

1. `test_parse_unc_valid` — `\\srv01\deploy\pacifico` ⇒ `(\\srv01\deploy, mismo)`.
2. `test_parse_unc_rejects_non_unc` — ruta local `C:\x` ⇒ `ServerBootstrapError`.
3. `test_parse_unc_rejects_bad_host` — host con caracteres inválidos ⇒ error.
4. `test_parse_unc_rejects_unsafe_subpath` — subruta con `..` ⇒ error.
5. `test_mount_uses_args_list_no_shell` — capturar los args del `subprocess.run`
   mock ⇒ es una LISTA que empieza con `["net","use", ...]` y NO tiene `shell=True`;
   el password está en la lista (no interpolado en un string de shell).
6. `test_mount_failure_returncode_generic_message` — `run` devuelve returncode!=0 ⇒
   `ServerBootstrapError` cuyo `str()` NO contiene el password (assert
   `password not in str(err)`).
7. `test_mount_exception_never_leaks_password` — `run` lanza
   `subprocess.TimeoutExpired(cmd=[...password...], timeout=20)` ⇒ `ServerBootstrapError`
   con mensaje genérico y `password not in str(err)`.
8. `test_context_manager_always_unmounts` — con mount OK, dentro del `with` se lanza
   una excepción ⇒ el `run` de `/delete` FUE llamado (finally) y la excepción propaga.
9. `test_non_win32_raises_clear` — `sys.platform` != win32 ⇒ `ServerBootstrapError`
   "solo en Windows", sin tocar `subprocess`.

**Comando:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan101_server_bootstrap_service.py" -q
```

**Criterio de aceptación (binario):** 9 tests verdes; NINGÚN test observa el password
en un mensaje de error (casos 6-7 lo fijan).
**Flag:** protegido aguas arriba por la flag en F2 (el servicio en sí es una librería).
**Impacto por runtime:** NINGUNO. Fallback: `ServerBootstrapError` claro si el mount
falla.
**Trabajo del operador:** ninguno.

---

## F2 — Endpoints `POST /api/devops/server-bootstrap/plan` y `/apply` (HITL, gateados por flag)

**Objetivo:** exponer el plan-then-apply remoto: `/plan` monta, calcula el layout
(dry-run, solo lectura remota), desmonta y devuelve las carpetas + fingerprint; `/apply`
monta, crea SOLO to_create + deja la config base, verifica, desmonta.
**Valor:** el flujo HITL completo, reusando el motor puro del 89 sobre la ruta montada.

**Archivo a editar:** `Stacky Agents/backend/api/devops.py`

```python
@bp.post("/server-bootstrap/plan")
def server_bootstrap_plan_route():
    """Dry-run del layout en el servidor remoto. SOLO LECTURA remota. Plan 101."""
    if not getattr(_config.config, "STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED", False):
        abort(404)
    body = request.get_json(silent=True) or {}
    alias = body.get("alias")
    project = body.get("project")
    if not alias or not project:
        return jsonify({"error": "alias y project son obligatorios"}), 400
    # environment_root REMOTO: settings propias del server (guardadas en el registro del
    # server como campo aparte del environment_root LOCAL del 89). v1: viene en el body,
    # validado; el front lo toma de las settings del servidor seleccionado (F3).
    remote_root = body.get("environment_root_remote")
    profile = load_client_profile(project) or {}
    catalog = profile.get("process_catalog")
    settings = profile.get("devops_environment_settings")
    settings = settings if isinstance(settings, dict) else {}
    rel_paths = build_environment_layout(catalog if isinstance(catalog, list) else [], settings)
    from services.environment_init import plan_environment, layout_fingerprint
    from services.server_bootstrap import mounted_remote_root, ServerBootstrapError
    try:
        with mounted_remote_root(alias, remote_root or "") as full_root:
            plan = plan_environment(full_root, rel_paths)          # solo lectura remota
            plan["layout_fingerprint"] = layout_fingerprint(full_root, rel_paths)
            return jsonify(plan)
    except ServerBootstrapError as exc:
        return jsonify({"error": str(exc), "kind": "server_bootstrap_error"}), 502


@bp.post("/server-bootstrap/apply")
def server_bootstrap_apply_route():
    """Crea SOLO to_create en el servidor + config base. HITL: confirm + fingerprint. Plan 101."""
    if not getattr(_config.config, "STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED", False):
        abort(404)
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400
    alias = body.get("alias"); project = body.get("project")
    remote_root = body.get("environment_root_remote")
    fingerprint = body.get("fingerprint")
    if not alias or not project:
        return jsonify({"error": "alias y project son obligatorios"}), 400
    if not isinstance(fingerprint, str) or not fingerprint:
        return jsonify({"error": "fingerprint del plan es obligatorio"}), 400
    profile = load_client_profile(project) or {}
    catalog = profile.get("process_catalog")
    settings = profile.get("devops_environment_settings")
    settings = settings if isinstance(settings, dict) else {}
    rel_paths = build_environment_layout(catalog if isinstance(catalog, list) else [], settings)
    from services.environment_init import apply_environment, plan_environment, layout_fingerprint, allExistsOk  # noqa
    from services.server_bootstrap import mounted_remote_root, ServerBootstrapError, write_base_config
    try:
        with mounted_remote_root(alias, remote_root or "") as full_root:
            if fingerprint != layout_fingerprint(full_root, rel_paths):
                return jsonify({"error": "el layout cambio desde el plan; recalcular",
                                "kind": "plan_stale"}), 409
            result = apply_environment(full_root, rel_paths)   # crea SOLO to_create (89)
            cfg_written = write_base_config(full_root)          # deja config base (F2 helper)
            re_plan = plan_environment(full_root, rel_paths)    # verify
            result["verified"] = all(e["status"] == "exists_ok" for e in re_plan["entries"])
            result["base_config_written"] = cfg_written
            return jsonify(result)
    except ServerBootstrapError as exc:
        return jsonify({"error": str(exc), "kind": "server_bootstrap_error"}), 502
```

Helper de config base EN `server_bootstrap.py` (idempotente, NUNCA pisa):

```python
def write_base_config(full_root: str) -> bool:
    """Escribe un stacky-server.json minimo en la raiz si NO existe. Idempotente:
    si ya existe, NO lo toca y devuelve False. Nunca contiene credenciales."""
    import json
    target = os.path.join(full_root, "stacky-server.json")
    if os.path.exists(target):
        return False
    payload = {"initialized_by": "stacky", "schema": 1}
    with open(target, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return True
```

**Casos borde fijados:** flag OFF ⇒ 404; alias/project faltantes ⇒ 400; mount falla ⇒
502 `server_bootstrap_error` (sin credencial en el mensaje); `apply` sin confirm ⇒ 400;
fingerprint distinto ⇒ 409 `plan_stale` (mismo contrato que 89); config base ya
existente ⇒ `base_config_written: false` (idempotente, no pisa); el desmontaje ocurre
siempre (finally del context manager).

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/backend/tests/test_plan101_server_bootstrap_endpoints.py`, 8 casos
(test client Flask; `mounted_remote_root` MOCKEADO para entregar un `tmp_path` local
como "full_root" — así se ejercita el plan/apply real del 89 sobre un dir temporal sin
red; `get_credential` mockeado):

1. `test_plan_404_when_flag_off`.
2. `test_apply_404_when_flag_off`.
3. `test_plan_400_missing_alias_or_project`.
4. `test_plan_returns_entries_and_fingerprint` — con catálogo fixture ⇒ el plan trae
   `entries` (to_create para las carpetas del layout) + `layout_fingerprint`.
5. `test_apply_400_without_confirm`.
6. `test_apply_409_on_stale_fingerprint` — fingerprint distinto ⇒ 409 `plan_stale`.
7. `test_apply_creates_and_verifies` — confirm + fingerprint correcto ⇒ crea las
   carpetas en el `tmp_path`, `verified: True`, `base_config_written: True`; segundo
   apply ⇒ `base_config_written: False` (idempotente).
8. `test_mount_error_maps_to_502` — `mounted_remote_root` lanza `ServerBootstrapError`
   ⇒ 502 con `kind: server_bootstrap_error` y el mensaje saneado (sin password).

**Comando:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan101_server_bootstrap_endpoints.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan89_environments_flag.py" -q
```

**Criterio de aceptación (binario):** 8 tests verdes + `test_plan89_environments_flag.py`
verde (el motor local del 89 NO se rompió).
**Flag:** `STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED` (OFF ⇒ 404).
**Impacto por runtime:** NINGUNO. Fallback: 502 claro si el mount remoto falla.
**Trabajo del operador:** ninguno.

---

## F3 — Frontend: sección/panel "Inicializar servidor" (wizard HITL) consumiendo `ctx.selectedServer`

**Objetivo:** una sección DevOps nueva (registro §3.12) que, con un servidor
seleccionado (91 F6), corre el wizard plan→confirm→apply→verify reusando el patrón del
89, y ofrece encadenar la publicación inicial del 88.
**Valor:** primer consumidor de `ctx.selectedServer`; el flujo estrella end-to-end.

**Archivos a editar/crear:**

1. `Stacky Agents/frontend/src/api/endpoints.ts` — en `export const DevOps`:

```ts
  serverBootstrapPlan: (body: { alias: string; project: string; environment_root_remote: string }) =>
    api.post<EnvironmentPlanResponse>("/api/devops/server-bootstrap/plan", body),
  serverBootstrapApply: (body: { alias: string; project: string; environment_root_remote: string; fingerprint: string; confirm: boolean }) =>
    api.post<{ created: string[]; failed: Array<{ path: string; error: string }>; verified: boolean; base_config_written: boolean }>(
      "/api/devops/server-bootstrap/apply", body),
```

   (reusa `EnvironmentPlanResponse` del 89, ya definido para el plan de carpetas.)

2. `Stacky Agents/frontend/src/components/devops/ServerBootstrapSection.tsx` (NUEVO) —
   componente que:
   - Lee `ctx.selectedServer` (alias/host). Si es `null`, muestra "Seleccioná un
     servidor activo (arriba)" y NADA más (no rompe).
   - Un input para `environment_root_remote` (UNC del servidor, ej.
     `\\{host}\deploy\proyecto`), con `host` prellenado de `ctx.selectedServer.host`.
   - Botón "Calcular plan" ⇒ `DevOps.serverBootstrapPlan` ⇒ muestra tabla de entries
     (to_create/exists_ok/conflict/unsafe) + `layout_fingerprint`, EXACTAMENTE como
     `EnvironmentsSection` (`EnvironmentsSection.tsx:305-342`) — reusar el mismo render.
   - Checkbox "Confirmo crear estas carpetas en el servidor" + botón "Inicializar
     servidor" ⇒ `DevOps.serverBootstrapApply` con el fingerprint ⇒ muestra
     verified/creadas/config base.
   - Tras verify OK, ofrece "Publicación inicial" reusando el patrón del 88/89 (Paso 3
     de `EnvironmentsSection.tsx:365-428`) apuntado al proyecto — reusa
     `TriggerPipelineSection`/`CommitPipelineModal` existentes, cero UI nueva de
     publicación.
   - Errores 502 (`server_bootstrap_error`) se muestran en llano ("no se pudo montar el
     recurso remoto: credenciales o red") — nunca un stderr crudo.

3. `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` — agregar la entrada al registro
   `DEVOPS_SECTIONS` (§3.12, patrón EXACTO de las secciones 88-91):

```tsx
  {
    id: 'bootstrap-servidor',
    label: 'Inicializar servidor',
    icon: '🚀',
    healthKey: 'server_bootstrap_enabled',
    gateFlagKey: 'STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED',
    gateMessage: 'Inicializar un servidor remoto necesita su flag (categoría DevOps) y el registro de servidores (Plan 91).',
    render: (ctx) => <ServerBootstrapSection ctx={ctx} />,
  },
```

   (el shell ya pasa `ctx.selectedServer`; CERO cambios en el resto del shell —
   contrato §3.12: sumar una sección = 1 entrada + 1 componente.)

**Casos borde fijados:** sin servidor seleccionado ⇒ mensaje guía, sin llamadas;
`server_bootstrap_available === false` (no-win32) ⇒ el gate del shell ya no muestra la
sección operativa (la flag health lo refleja); el fingerprint se pasa tal cual del plan
al apply (anti-stale del 89); la publicación inicial es un paso APARTE con su confirm.

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/frontend/src/pages/__tests__/ServerBootstrap.test.ts` (TS-puro estilo
`ServersSection.test.ts`), 6 casos:

1. `DEVOPS_SECTIONS incluye bootstrap-servidor con gate declarativo` — entry con
   `healthKey==='server_bootstrap_enabled'`,
   `gateFlagKey==='STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED'`, render función.
2. `endpoints expone serverBootstrapPlan/Apply` — ambos métodos son funciones.
3. `ServerBootstrapSection consume ctx.selectedServer` — su fuente contiene
   `ctx.selectedServer` y el guard de `null`.
4. `el apply exige confirm y pasa fingerprint` — su fuente contiene `confirm: true` y
   `fingerprint` en la llamada a `serverBootstrapApply`.
5. `no hand-rollea el gate (lo hace el shell, §3.12)` — su fuente NO contiene
   `FlagGateBanner` ni `STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED`.
6. `los errores 502 se muestran en llano` — su fuente contiene el manejo de
   `server_bootstrap_error`/mensaje genérico (grep de la copy en llano).

**Comandos:**

```
npx vitest run src/pages/__tests__/ServerBootstrap.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** 6 tests verdes + `tsc` 0 errores + los vitest
preexistentes del panel (`DevOpsPage.test.ts`, `ServersSection.test.ts`) verdes sin
modificarlos.
**Flag:** `STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED` vía `server_bootstrap_enabled`.
**Impacto por runtime:** NINGUNO. Fallback: sin servidor seleccionado / no-win32 ⇒
mensajes guía, sin acción.
**Trabajo del operador:** ninguno (opt-in default off).

---

## F4 — Cierre: ratchet, verificación manual HITL y checklist binario

**Objetivo:** registrar tests backend en el ratchet, verificar end-to-end contra un
share real y dejar el checklist auditable.

**Archivos a editar:** `Stacky Agents/backend/scripts/run_harness_tests.ps1` y `.sh` —
agregar a `HARNESS_TEST_FILES`:

```
  "tests/test_plan101_server_bootstrap_flag.py",
  "tests/test_plan101_server_bootstrap_service.py",
  "tests/test_plan101_server_bootstrap_endpoints.py",
```

**Verificación manual (HITL, en Windows, con un servidor de prueba con un share
accesible y credenciales cargadas en el 91):**
1. Activar `STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED` (y `SERVERS` del 91) por UI ⇒
   aparece la sección "Inicializar servidor".
2. Seleccionar un servidor en el selector del shell (91 F6) ⇒ la sección lo toma;
   ingresar el UNC (`\\host\share\proyecto`); "Calcular plan" ⇒ ver las carpetas
   to_create (SIN que se haya creado nada aún — verificar en el server que no existen).
3. Confirmar + "Inicializar servidor" ⇒ las carpetas aparecen en el server; `verified`
   OK; `stacky-server.json` creado en la raíz; correr de nuevo ⇒
   `base_config_written: false` (idempotente) y `verified` OK.
4. Provocar un fallo (share inexistente o credenciales borradas) ⇒ mensaje en llano
   "no se pudo montar el recurso remoto: credenciales o red"; verificar en los logs de
   Flask que NO aparece el password ni el comando `net use` completo.
5. Verificar el desmontaje: tras cada operación, `net use` en el host del backend NO
   deja el share colgado (el `finally` desmontó).
6. Publicación inicial: encadenar el paso ⇒ commit HITL del 88 apuntado al proyecto.

**Checklist binario:**
- [ ] Flag `STACKY_DEVOPS_SERVER_BOOTSTRAP_ENABLED` default OFF; con OFF los endpoints
      dan 404 y la sección no aparece; `test_plan101_server_bootstrap_flag.py` 5/5 +
      meta-tests del arnés verdes.
- [ ] `server_bootstrap.py`: subprocess con lista de args sin shell; el password NUNCA
      aparece en un mensaje de error (`test_..._service.py` casos 5-7); el context
      manager SIEMPRE desmonta (caso 8); no-win32 y sin-credencial dan error claro.
- [ ] Endpoints plan/apply HITL: `/plan` es dry-run (no crea nada), `/apply` exige
      confirm + fingerprint, 409 en stale, 502 saneado en mount error, config base
      idempotente (`test_..._endpoints.py` 8/8) + `test_plan89_environments_flag.py`
      verde (motor local intacto).
- [ ] `apply_environment` local (89) NO modificado; el remoto reusa las funciones puras
      del 89 sobre la ruta montada.
- [ ] La sección consume `ctx.selectedServer` (primer consumidor del 91 F6); no
      hand-rollea el gate; errores en llano (`ServerBootstrap.test.ts` 6/6).
- [ ] Transporte UNC+`net use` (default) sin dependencias nuevas; WinRM documentado como
      fuera de scope; fallback claro si el mount falla.
- [ ] `validate_host` (91 C2) + `is_safe_segment` (89 C12) aplicados a host/subrutas
      del UNC antes de tocar la red.
- [ ] `tsc --noEmit` 0 errores; vitest por archivo verdes; 3 tests backend registrados
      en ambos ratchets.
- [ ] Verificación manual HITL de los 6 pasos anotada en el reporte (incluida la
      inspección de logs para confirmar CERO fuga de credenciales).

**Trabajo del operador:** ninguno (opt-in default off; reusa servidor/credenciales/
catálogo ya cargados).

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Fuga de credenciales por stderr/excepción del `net use` (el riesgo #1) | Patrón 91 C1 EXTENDIDO: lista de args sin shell, `except Exception` genérico, mensajes GENÉRICOS hacia arriba (nunca `rc.stderr` ni el mensaje de la excepción), NUNCA loggear el comando. Fijado por los tests 6-7 de F1 (`password not in str(err)`). Verificación manual paso 4 (inspección de logs). |
| Share queda montado si el apply falla (leak de recurso/handle) | El montaje vive en un `@contextmanager` con `finally` que SIEMPRE desmonta (`net use /delete`). Test 8 de F1. Verificación manual paso 5. |
| El operador apunta a una UNC peligrosa (`\\host\C$\Windows`) | `validate_host` (91 C2) valida el host; `is_safe_segment` (89 C12) valida cada subruta (sin `..`, sin absolutas, sin reservadas); el server-side re-planifica y crea SOLO la intersección con el layout del catálogo (89). El operador VE el plan antes de confirmar (HITL). |
| WinRM sería más "correcto" que UNC para algunos entornos | Decisión §3.1: UNC+`net use` es el default por cero-deps + coherencia con el 91; WinRM exige dependencia nueva + config del servidor (viola cero-trabajo) y queda documentado como evolución futura (Fuera de scope) para entornos sin SMB. |
| `apply_environment` remoto rompe el motor local del 89 | El remoto son funciones NUEVAS en `server_bootstrap.py` que REUSAN las puras del 89 sobre la ruta montada; `apply_environment`/`plan_environment` no se tocan; `test_plan89_environments_flag.py` es el arnés de no-regresión. |
| R4 (`requires` profundidad 1) podría rechazar la cadena BOOTSTRAP→SERVERS→PANEL | F0 lo resuelve por test: si `test_harness_flags_requires.py` rechaza la cadena de longitud 2, apuntar `requires` a PANEL y documentar la dependencia de SERVERS en la descripción (criterio binario: el test pasa). |
| El bootstrap corre en el host del backend (si el backend no es local, el mount se hace desde allá) | Idéntico al RDP del 91 (`devops_servers.py:128-129`): Stacky es mono-operador y corre local; aceptado y documentado. |
| `net use` colisiona si el share ya está montado con otras credenciales | Mensaje genérico de fallo + el operador puede desmontar a mano; v1 no gestiona múltiples montajes concurrentes del mismo share (mono-operador). Documentado en Fuera de scope. |

## 6. Fuera de scope (v1)

- **Transporte WinRM/PSRP** (ejecución remota de comandos): documentado como evolución
  futura; v1 es UNC+`net use` por cero-deps. Requeriría `pywinrm`/`pypsrp` + WinRM
  habilitado en el servidor.
- Copiar binarios/artefactos de aplicación al servidor (deploy real de la app): v1 solo
  crea el árbol de carpetas + una config base mínima. El deploy de artefactos es otro
  plan.
- Config base rica (v1 escribe un `stacky-server.json` mínimo idempotente; plantillas
  de config por tipo de servidor quedan para un plan futuro).
- Gestión de múltiples montajes concurrentes del mismo share / drive letters.
- Persistir el `environment_root_remote` en el registro del servidor (v1 lo toma del
  body/UI por servidor; guardarlo como campo del server es una mejora futura — hoy el
  registro del 91 solo guarda alias/host/domain/username/notes).
- Bootstrap en no-Windows (Linux/SSH): v1 es win32 (paridad honesta con el 91).
- Migrar la escritura del catálogo/settings al PATCH del Plan 98 (PROPUESTO): sin
  acoplar a un plan no implementado.
- Rollback automático de carpetas creadas si la publicación posterior falla: las
  carpetas creadas son idempotentes y seguras; no se borran (el motor del 89 NUNCA
  borra).

## 7. Glosario

- **Bootstrap de servidor:** preparar un servidor remoto (carpetas + config base +
  publicación inicial) desde Stacky, con las credenciales ya guardadas.
- **UNC (`\\host\share\...`):** ruta de red de Windows a un recurso compartido; se monta
  con `net use` y credenciales.
- **`net use`:** comando de Windows para montar/desmontar un recurso UNC con
  credenciales; se invoca como subprocess con lista de args (patrón 91 C1).
- **`get_credential` (Plan 91):** `server_registry.get_credential(alias)` devuelve
  `(username, domain, password)` desde el keyring; el ÚNICO punto de lectura del
  password (`server_registry.py:205-218`).
- **plan-then-apply (Plan 89):** patrón HITL: primero un dry-run (solo lectura) que
  muestra qué se va a crear, luego el apply que crea SOLO lo faltante tras confirm +
  fingerprint.
- **`fingerprint` del plan:** hash del layout visto (`layout_fingerprint`, 89); el apply
  lo exige para no aplicar sobre un plan viejo (anti-stale, 409 `plan_stale`).
- **`is_safe_segment` (Plan 89 C12):** valida que una subruta sea segura (sin `..`, sin
  caracteres inválidos de Windows, sin nombres reservados, no absoluta).
- **`ctx.selectedServer` (Plan 91 F6):** el servidor activo elegido en el selector del
  shell; este plan es su primer consumidor.
- **WinRM/PSRP:** protocolo de gestión remota de Windows (ejecución de comandos);
  alternativa a UNC descartada como default por exigir dependencia + config extra.

## 8. Orden de implementación

1. F0 — flag 5 patas + keys de health + arista R4 + tests (resolver la cuestión R4 por
   test antes de seguir).
2. F1 — `services/server_bootstrap.py` (montaje UNC + parse + config base) + 9 tests con
   subprocess mockeado (el módulo peligroso primero, 100% aislado).
3. F2 — endpoints plan/apply + tests con `mounted_remote_root` mockeado a `tmp_path`
   (necesita F1).
4. F3 — endpoints frontend + `ServerBootstrapSection.tsx` + entrada en `DEVOPS_SECTIONS`
   + tests vitest (necesita F2).
5. F4 — ratchet (sh+ps1) + verificación manual HITL contra un share real + checklist.

## 9. Definición de Hecho (DoD)

- F0: 5 tests verdes (`test_plan101_server_bootstrap_flag.py`) + 3 meta-tests del arnés
  verdes; flag visible en Configuración → Arnés, categoría DevOps, default OFF; cuestión
  R4 resuelta por test.
- F1: 9 tests verdes (`test_plan101_server_bootstrap_service.py`); el password NUNCA
  aparece en un mensaje de error; el context manager siempre desmonta.
- F2: 8 tests verdes (`test_plan101_server_bootstrap_endpoints.py`) +
  `test_plan89_environments_flag.py` verde (motor local intacto).
- F3: 6 tests vitest verdes (`ServerBootstrap.test.ts`) + `tsc` 0 errores + vitest
  preexistentes del panel verdes sin modificar; primer consumidor de `ctx.selectedServer`.
- F4: 3 tests backend registrados en ambos ratchets; verificación manual HITL de los 6
  pasos anotada en el reporte (incluida la confirmación de CERO fuga de credenciales en
  logs).
- Global: transporte UNC+`net use` sin dependencias nuevas (WinRM fuera de scope);
  seguridad de credenciales del 91 C1 respetada y testeada; HITL en plan→confirm→apply;
  `apply_environment` local del 89 intacto; flag propia default OFF con retro-compat
  byte-idéntica; `ctx.selectedServer` del 91 finalmente consumido.
- Impacto en los 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro):
  NINGUNO — panel + endpoints de infraestructura; verificable por grep de
  `server_bootstrap|server-bootstrap` fuera de `frontend/` + `api/` + `services/` +
  `tests/`.
