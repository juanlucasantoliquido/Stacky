# Plan 91 — Registro de servidores DevOps (conexiones con alias)

**Estado:** PROPUESTO
**Versión:** v1
**Fecha:** 2026-07-04
**Serie DevOps:** extensión del panel (plan 87) — habilita scoping por servidor para 88/89/90
**Dependencias:** plan 87 (solo F0/F1/F4, mismo patrón que plan 90 F0)

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Toda afirmación sobre código existente
> cita `archivo:línea` verificada el 2026-07-04. Prohibido desviarse de los nombres
> exactos aquí definidos.

---

## 1. Objetivo + KPI

**Objetivo:** que el operador cargue UNA sola vez cada servidor Windows que administra
(alias + host + dominio + usuario + password) en una sección "Servidores" del panel
DevOps, y desde ahí: (a) se conecte por RDP con 1 click, y (b) las features DevOps
futuras (planes 88/89/90, aún en papel) puedan operar POR SERVIDOR seleccionado vía un
selector en el shell del panel.

**KPI (binarios):**
- KPI-1: alta de un servidor + conexión RDP = 1 formulario + 1 click (hoy: abrir mstsc,
  tipear host, tipear `dominio\usuario`, tipear password — 4+ pasos por conexión, cada vez).
- KPI-2: el password NUNCA aparece en el JSON persistido, en respuestas GET ni en logs
  (test centinela `test_f2_password_never_in_json` lo verifica por grep).
- KPI-3: cero regresión — con `STACKY_DEVOPS_SERVERS_ENABLED=false` (default) el sistema
  se comporta EXACTAMENTE igual que hoy (los endpoints nuevos devuelven 404, la sub-tab
  muestra `FlagGateBanner`, el selector no aparece).

---

## 2. Por qué ahora / gap

- El operador administra varios servidores Windows y hoy re-tipea credenciales RDP en
  cada conexión. No hay ningún registro de servidores en Stacky.
- Los planes 88 (publicaciones), 89 (inicialización de ambientes) y 90 (agente DevOps)
  están CRITICADOS v3 pero sin implementar; el 89 dejó explícitamente fuera de scope la
  operación remota: `89_PLAN_INICIALIZACION_AMBIENTES_DEVOPS.md:958-960` — "Crear
  carpetas en servidores REMOTOS (SSH/UNC/agentes) [...] remoto exigiría credenciales y
  otro modelo de seguridad". **ESTE plan es ese "otro plan"**: aporta el registro de
  credenciales y el contrato `get_credential(alias)` que la extensión remota consumirá.
- El host del panel DevOps (plan 87) YA existe en el working tree: blueprint
  `api/devops.py:11`, página `frontend/src/pages/DevOpsPage.tsx:51`
  (`export const DEVOPS_SECTIONS`), gate `FlagGateBanner.tsx` en
  `frontend/src/components/devops/`. El contrato de extensión §3.12 del 87 v3 fue
  diseñado exactamente para agregar secciones como esta sin refactor
  (`87_PLAN_PANEL_DEVOPS_CREADOR_GRAFICO_PIPELINES.md:233`: "feature DevOps nueva = 1
  entrada en `DEVOPS_SECTIONS` + 1 componente + (si necesita backend) 1 blueprint").

---

## 3. Principios y guardarraíles (codificados, no negociables)

- **§3.1 Password JAMÁS en disco/JSON/DB/logs/GET.** El password vive SOLO en Windows
  Credential Manager vía la librería `keyring` (service name `stacky-devops`, key =
  alias). El JSON persistido guarda `{alias, host, domain, username, notes}` y NADA más.
  Si `keyring` no importa, el endpoint devuelve error explícito 503 — NUNCA fallback a
  texto plano. GET devuelve `has_password: true/false`, jamás el valor.
- **§3.2 Human-in-the-loop innegociable.** Conectar por RDP es SIEMPRE un click
  explícito del operador. Nada se conecta solo. No hay scheduling ni auto-conexión.
- **§3.3 Mono-operador sin auth real.** Stacky no tiene login/roles; `current_user` es
  un header sin validar. NO construir RBAC ni "permisos por servidor". El riel de
  seguridad es el §3.1 (secreto en el vault del SO), no un login.
- **§3.4 Opt-in, default OFF, activable por UI.** Flag `STACKY_DEVOPS_SERVERS_ENABLED`
  con `env_only=False` (regla dura operator-config-always-via-ui). Cero pasos manuales
  nuevos obligatorios: si el operador no activa la flag, Stacky no cambia en nada.
- **§3.5 Paridad de 3 runtimes: N/A por diseño.** Esta feature es panel+backend Flask;
  NO toca el arnés de agentes (ni `claude_code_cli_runner`, ni Codex, ni Copilot). Cada
  fase lo declara explícitamente. Ningún prompt, runner ni inyección cambia.
- **§3.6 RDP/cmdkey es Windows-only: degradación explícita.** El health expone
  `rdp_available` (bool). En no-Windows el endpoint `/rdp` devuelve 501 con detalle
  claro y la UI OCULTA el botón "Conectar por RDP" si `rdp_available !== true`. El
  resto de la feature (CRUD, test de conectividad, selector) funciona en cualquier SO.
- **§3.7 Contrato de extensión §3.12 del 87 v3, sin hand-roll.** La sección se registra
  DECLARATIVAMENTE en `DEVOPS_SECTIONS` con `healthKey`/`gateFlagKey`/`gateMessage`
  (`DevOpsPage.tsx:36-44`); el gate lo renderiza el SHELL (prohibido hand-rollear el
  aviso dentro de la sección, `87_PLAN...md:248-249`). Rutas backend bajo
  `/api/devops/servers/...` (namespacing del 87, `87_PLAN...md:241`).
- **§3.8 Extensión ADITIVA del contexto.** `DevOpsSectionContext` gana campos
  OPCIONALES (`selectedServer?`, `servers?`). Las secciones existentes NO se tocan.
  `DevOpsHealth` ya admite keys nuevas por su index signature (`DevOpsPage.tsx:26`).
- **§3.9 Caso borde documentado (backend remoto).** `cmdkey`/`mstsc` se ejecutan en el
  HOST del backend. Si el backend corriera en otra máquina que la del operador, el
  mstsc se abriría en ese host. Aceptado: Stacky es mono-operador y corre local (riel
  existente §3.3). Queda escrito aquí y en el docstring del endpoint.
- **§3.10 Este plan NO implementa ejecución remota** (UNC/WinRM) ni amplía el alcance
  de 88/89/90. Solo deja el contrato `get_credential(alias)` documentado como EL punto
  de consumo futuro.

---

## 4. Fases

> Comando de tests backend (por archivo, con el venv del repo — la suite completa está
> contaminada, plan 49), ejecutado desde `Stacky Agents/backend`:
> `.venv/Scripts/python.exe -m pytest tests/<archivo> -q`
> Gate frontend: `npx tsc --noEmit` en `Stacky Agents/frontend` (0 errores) + vitest
> por archivo (`npx vitest run src/pages/__tests__/<archivo>`), mismo patrón TS-puro de
> `frontend/src/pages/__tests__/DevOpsPage.test.ts` (sin render de React).
> REGLA RATCHET (plan 49): todo archivo de test backend nuevo se registra en
> `backend/scripts/run_harness_tests.ps1` Y `backend/scripts/run_harness_tests.sh`
> (los tests del 87 están en `run_harness_tests.ps1:103-105` — mismo bloque).

### F0 — Pre-flight de dependencia (host del panel 87)

**Objetivo:** garantizar que el host del panel DevOps existe antes de tocar nada.

**Pasos (deterministas, sin inferencia) — REUSO por referencia del plan 90 F0.a
(`90_PLAN_AGENTE_DEVOPS_INTERACTIVO_MULTITURNO.md:237-249`), NO duplicar su texto:**
1. Verificar que existe `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` Y que exporta
   `DEVOPS_SECTIONS` (grep literal `export const DEVOPS_SECTIONS`).
2. **Si existe** (estado verificado al redactar este plan: SÍ existe,
   `DevOpsPage.tsx:51`; el blueprint `api/devops.py:11` y su registro
   `api/__init__.py:91` también): seguir a F1 sin hacer nada.
3. **Si NO existe:** implementar PRIMERO, tal cual está escrito en
   `90_PLAN_AGENTE_DEVOPS_INTERACTIVO_MULTITURNO.md` F0.a (puntos 3 en adelante), el
   subconjunto mínimo del 87: F0 (flag `STACKY_DEVOPS_PANEL_ENABLED` + categoría
   `devops`), F1 (blueprint `api/devops.py` con `/health` y `/parse-yaml` + centinela)
   y F4 (`DevOpsPage.tsx` + `DEVOPS_SECTIONS` + tab gated en `App.tsx`), con sus tests
   nombrados. NO implementar 87 F2/F3/F5/F6.

**Criterio de aceptación (binario):** `grep -l "export const DEVOPS_SECTIONS" "Stacky
Agents/frontend/src/pages/DevOpsPage.tsx"` devuelve el archivo, y
`.venv/Scripts/python.exe -m pytest tests/test_plan87_devops_endpoints.py -q` pasa.
**Flag:** ninguna nueva en esta fase.
**Impacto por runtime:** N/A — no toca el arnés de agentes.
**Trabajo del operador:** ninguno.

### F1 — Flag `STACKY_DEVOPS_SERVERS_ENABLED` en las 4 patas

**Objetivo:** dar de alta la flag master de la feature (default OFF, editable por UI)
sin romper meta-tests.

**Archivos y cambios EXACTOS:**

1. `Stacky Agents/backend/config.py` — junto a la flag del 87 (`config.py:857-858`),
   agregar con el MISMO patrón:
   ```python
   STACKY_DEVOPS_SERVERS_ENABLED: bool = os.getenv(
       "STACKY_DEVOPS_SERVERS_ENABLED", "false"
   ).strip().lower() in ("1", "true", "yes")
   ```
   (copiar la expresión exacta de parsing que usa `STACKY_DEVOPS_PANEL_ENABLED` en
   `config.py:857-858` — si difiere de la mostrada, gana la del archivo).

2. `Stacky Agents/backend/services/harness_flags.py`:
   - **FlagSpec** nuevo, inmediatamente después del bloque del Plan 87
     (`harness_flags.py:1931-1944`), copiando su estructura:
     ```python
     # ── Plan 91 — Registro de servidores DevOps ────────────────────────────
     FlagSpec(
         key="STACKY_DEVOPS_SERVERS_ENABLED",
         type="bool",
         label="Servidores DevOps (Plan 91)",
         description=(
             "Plan 91 — Registro de servidores con alias (host+usuario+dominio; "
             "password en Windows Credential Manager, nunca en disco). Habilita "
             "/api/devops/servers (CRUD, test de conectividad, conexion RDP 1-click) "
             "y la seccion Servidores del panel DevOps. Default OFF."
         ),
         group="global",
         env_only=False,  # editable por UI (regla operator-config-always-via-ui)
         requires="STACKY_DEVOPS_PANEL_ENABLED",  # la sección vive dentro del panel 87
     ),
     ```
     **GOTCHA VERIFICADO (no negociable):** NO pasar `default=False` (ni ningún
     `default=`) — cualquier default no-None cuenta contra la lista congelada de
     `_CURATED_DEFAULTS_ON` y rompe `test_default_known_only_for_curated` en
     `tests/test_harness_flags.py`. El type-zero de `bool` ya es False
     (`harness_flags.py:29`).
   - **Categoría:** agregar la key a la tupla de la categoría `"devops"` existente en
     el mapa de categorías (`harness_flags.py:177-179`):
     ```python
     "devops": (
         "STACKY_DEVOPS_PANEL_ENABLED",   # Plan 87 — panel DevOps
         "STACKY_DEVOPS_SERVERS_ENABLED", # Plan 91 — registro de servidores
     ),
     ```

3. `Stacky Agents/backend/services/harness_flags_help.py` — entrada `PlainHelp` nueva
   junto a la del 87 (`harness_flags_help.py:602`), MISMO patrón/estructura que esa
   entrada (Plan 86 exige ayuda en llano; los tests de
   `tests/test_harness_flags_help.py` validan el módulo). Texto en llano:
   qué hace ON ("aparece la sección Servidores en el panel DevOps; podés guardar
   servidores con alias y conectarte por RDP con 1 click"), qué hace OFF ("no cambia
   nada; los endpoints devuelven 404"), y la nota de seguridad ("la contraseña se
   guarda en el Administrador de credenciales de Windows, nunca en archivos de
   Stacky"). Completar TODOS los campos que la dataclass `PlainHelp` exija (leer su
   definición al tope de `harness_flags_help.py` y espejar la entrada :602).

4. `Stacky Agents/backend/harness_defaults.env` — agregar la línea (junto a
   `harness_defaults.env:32` que tiene la del 87):
   ```
   STACKY_DEVOPS_SERVERS_ENABLED=false
   ```

**Tests PRIMERO** — archivo nuevo
`Stacky Agents/backend/tests/test_plan91_servers_flag.py`:
- `test_f1_flag_in_registry`: `STACKY_DEVOPS_SERVERS_ENABLED` está en `FLAG_REGISTRY`
  con `type=="bool"`, `env_only is False`, `default is None`,
  `requires=="STACKY_DEVOPS_PANEL_ENABLED"`.
- `test_f1_flag_in_devops_category`: la key aparece en la tupla de la categoría
  `"devops"` del mapa de categorías.
- `test_f1_harness_defaults_contains_flag`: patrón EXACTO de
  `tests/test_plan75_deep_links_wiring.py:50-58` (leer `harness_defaults.env` y
  assert de la línea `STACKY_DEVOPS_SERVERS_ENABLED=false`) — causa raíz recurrente
  que el 87 v3 C13 documentó.
- `test_f1_config_default_is_false`: patrón de
  `tests/test_plan75_deep_links_wiring.py:61-64` (pop de la env var, releer default).
- `test_f1_flag_has_plain_help`: `PLAIN_HELP` (import desde
  `services.harness_flags_help`) contiene la key.

**Registrar** `tests/test_plan91_servers_flag.py` en `run_harness_tests.ps1` y `.sh`
(bloque de los `test_plan87_*`, `run_harness_tests.ps1:103-105`).

**Comando:** `.venv/Scripts/python.exe -m pytest tests/test_plan91_servers_flag.py tests/test_harness_flags.py -q`
**Criterio de aceptación (binario):** los 5 tests nuevos pasan Y
`tests/test_harness_flags.py` pasa completo (incluye
`test_default_known_only_for_curated` y el meta-test de registro).
**Nota centinela plan 85 (`tests/test_flag_wiring.py`):** la flag tendrá consumidor
real en F3 (`api/devops_servers.py`). Si F1 se commitea sola antes de F3 y
`test_flag_wiring.py` falla por flag sin consumo, implementar F1+F3 en el mismo
commit — NO marcar la flag como `reserved`.
**Flag protectora:** ella misma, default OFF.
**Impacto por runtime:** N/A — no toca el arnés de agentes.
**Trabajo del operador:** ninguno (opt-in, default off).

### F2 — Backend: servicio `server_registry` (persistencia + keyring)

**Objetivo:** módulo de dominio puro-de-Flask que persiste servidores en JSON (sin
password) y delega el password a Windows Credential Manager vía `keyring`.

**Archivo nuevo:** `Stacky Agents/backend/services/server_registry.py`

**Dependencia nueva:** agregar a `Stacky Agents/backend/requirements.txt` la línea
`keyring==25.6.0` (verificado 2026-07-04: `keyring` NO está en requirements.txt; en
Windows usa el backend nativo Credential Manager sin configuración extra).

**Contenido EXACTO (esqueleto; el implementador completa cuerpos triviales):**
```python
"""services/server_registry.py — Plan 91: registro de servidores DevOps.

Persistencia: JSON en data_dir()/devops_servers.json (patrón project_manager.py:34,87)
con SOLO {alias, host, domain, username, notes}. El password vive EXCLUSIVAMENTE en
el Credential Manager del SO via keyring (service=KEYRING_SERVICE, key=alias).
get_credential(alias) es EL punto de consumo para la extension remota futura
(89_PLAN_INICIALIZACION_AMBIENTES_DEVOPS.md:958-960: "remoto exigiria credenciales y
otro plan" — este es ese plan). NUNCA loggear passwords.
"""
import json
import re
import socket

try:
    import keyring  # backend Windows: Credential Manager
except ImportError:  # keyring no instalado — NUNCA fallback a texto plano (§3.1)
    keyring = None

from runtime_paths import data_dir

KEYRING_SERVICE = "stacky-devops"
MAX_SERVERS = 100
_ALIAS_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")


def _registry_path():
    return data_dir() / "devops_servers.json"

def keyring_available() -> bool:
    return keyring is not None

def validate_alias(alias: str) -> bool:
    return bool(isinstance(alias, str) and _ALIAS_RE.match(alias))

def _load() -> list[dict]:
    # devuelve [] si el archivo no existe o el JSON es inválido (log warning, sin raise)
    ...

def _save(servers: list[dict]) -> None:
    # write_text(json.dumps(servers, indent=2, ensure_ascii=False), encoding="utf-8")
    # patrón project_manager.py:87. ANTES de escribir: assert defensivo de que ningún
    # dict contiene la key "password" (raise ValueError si aparece — §3.1).
    ...

def list_servers() -> list[dict]:
    # cada item: {alias, host, domain, username, notes, has_password: bool}
    # has_password consulta keyring SOLO si keyring_available(); si no, False.
    # Ordenado por alias. NUNCA incluye el password.
    ...

def get_server(alias: str) -> dict | None: ...

def upsert_server(alias: str, host: str, domain: str, username: str, notes: str) -> dict:
    # valida: validate_alias(alias); host str no vacío ≤253; username str no vacío;
    # domain/notes str (pueden ser ""); cap MAX_SERVERS al CREAR (update no cuenta).
    # raise ValueError con mensaje claro en cada violación.
    ...

def delete_server(alias: str) -> bool:
    # quita del JSON Y borra la credencial: keyring.delete_password(KEYRING_SERVICE, alias)
    # (envuelto en try/except keyring.errors.PasswordDeleteError → ignorar: no había).
    # Devuelve False si el alias no existía.
    ...

def set_password(alias: str, password: str) -> None:
    # raise RuntimeError("keyring no disponible") si not keyring_available().
    # keyring.set_password(KEYRING_SERVICE, alias, password)
    ...

def has_password(alias: str) -> bool: ...

def get_credential(alias: str) -> tuple[str, str, str] | None:
    """CONTRATO para consumo futuro (extensión remota 88/89/90, §3.10).
    Devuelve (username, domain, password) o None si no hay servidor o no hay password.
    """
    ...

def test_connectivity(host: str, port: int = 3389, timeout: float = 3.0) -> tuple[bool, str]:
    # 1) socket.getaddrinfo(host, port) → si falla: (False, "DNS: no resuelve <host>")
    # 2) socket.create_connection((host, port), timeout=timeout) → cerrar y (True, "TCP 3389 OK")
    #    si falla: (False, "TCP 3389: <mensaje de la excepción>")
    # NO intenta login: el login real lo valida el operador al conectarse.
    ...
```

**Casos borde codificados:** JSON corrupto → `_load()` devuelve `[]` (warning, no
crash); alias inválido → `ValueError`; `keyring is None` → `set_password` levanta
`RuntimeError`, `has_password`/`get_credential` devuelven `False`/`None`; borrar
servidor sin credencial guardada → no lanza.

**Tests PRIMERO** — archivo nuevo
`Stacky Agents/backend/tests/test_plan91_server_registry.py`. Setup común: fixture que
(a) monkeypatchea `services.server_registry._registry_path` a un `tmp_path/"devops_servers.json"`,
y (b) monkeypatchea `services.server_registry.keyring` con un fake in-memory:
```python
class _FakeKeyring:
    def __init__(self): self.store = {}
    def set_password(self, svc, key, val): self.store[(svc, key)] = val
    def get_password(self, svc, key): return self.store.get((svc, key))
    def delete_password(self, svc, key):
        if (svc, key) not in self.store: raise Exception("no existe")
        del self.store[(svc, key)]
```
Casos (nombres exactos):
- `test_f2_upsert_and_list_roundtrip`: upsert 2 servidores → `list_servers()` los
  devuelve ordenados por alias con `has_password=False`.
- `test_f2_upsert_invalid_alias_raises`: alias `"con espacios"` y `""` → `ValueError`.
- `test_f2_set_password_then_has_password`: `set_password("srv1","S3cr3t!")` →
  `has_password("srv1") is True` y `get_credential("srv1") == ("usr","DOM","S3cr3t!")`.
- `test_f2_delete_removes_credential`: delete → alias fuera del JSON y
  `fake.store` sin la key.
- `test_f2_password_never_in_json` **(CENTINELA KPI-2)**: tras upsert +
  `set_password(..., "S3cr3t!XYZ")`, leer el TEXTO crudo de `devops_servers.json` y
  assert `"password" not in text.lower()` y `"S3cr3t!XYZ" not in text`.
- `test_f2_keyring_unavailable_raises`: monkeypatch `keyring=None` →
  `set_password` levanta `RuntimeError`; `keyring_available() is False`;
  `get_credential(...) is None`.
- `test_f2_corrupt_json_returns_empty`: escribir `"{no-json"` en el archivo →
  `list_servers() == []` sin excepción.
- `test_f2_cap_100_servers`: con 100 servidores, upsert del alias 101 → `ValueError`;
  update de uno existente → OK.
- `test_f2_connectivity_dns_fail`: `test_connectivity("host-inexistente-stacky-91.invalid")`
  → `(False, detail)` con `"DNS"` en detail (dominio `.invalid` garantiza NXDOMAIN,
  RFC 2606 — sin red real no flaquea).

**Registrar** el archivo en `run_harness_tests.ps1` y `.sh`.
**Comando:** `.venv/Scripts/python.exe -m pytest tests/test_plan91_server_registry.py -q`
**Criterio de aceptación (binario):** 9 tests pasan; `grep -i password "Stacky
Agents/backend/services/server_registry.py"` solo matchea llamadas keyring/params,
nunca escritura a JSON/log.
**Flag protectora:** el servicio es inerte sin la API (F3); la flag gatea la API.
**Impacto por runtime:** N/A — no toca el arnés de agentes.
**Trabajo del operador:** ninguno (`pip install -r requirements.txt` lo hace el deploy
existente; en dev, un `pip install keyring==25.6.0` en el venv — documentado, no un
paso nuevo de runtime).

### F3 — Backend: API `/api/devops/servers` (CRUD + test de conectividad) + health

**Objetivo:** exponer el registro por HTTP con guard de flag, y sumar
`servers_enabled`/`rdp_available` al health del panel.

**Archivo nuevo:** `Stacky Agents/backend/api/devops_servers.py` — blueprint PROPIO,
mismo patrón que `api/devops.py:11` (FIX C2 del plan 73: el prefix NO lleva `/api`):
```python
"""api/devops_servers.py — Plan 91: registro de servidores DevOps.

url_prefix="/devops/servers" → rutas finales /api/devops/servers/... (namespacing
§3.12 del plan 87). Guard per-request 404 si STACKY_DEVOPS_SERVERS_ENABLED=OFF
(mismo patrón api/devops.py:28-29). El password entra SOLO por POST/PUT (write-only),
JAMÁS sale en respuestas ni logs (§3.1).
"""
from flask import Blueprint, jsonify, request, abort
import config as _config
from services import server_registry

bp = Blueprint("devops_servers", __name__, url_prefix="/devops/servers")

def _guard():
    if not getattr(_config.config, "STACKY_DEVOPS_SERVERS_ENABLED", False):
        abort(404)
```

**Rutas EXACTAS (todas llaman `_guard()` primero):**
- `GET ""` → `{"servers": server_registry.list_servers(), "keyring_available": server_registry.keyring_available()}` (200).
- `POST ""` → body `{alias, host, domain?, username, notes?, password?}`. Valida vía
  `upsert_server` (ValueError → 400 con `{"error": str(e)}`). Si viene `password` no
  vacío: si `not keyring_available()` → **503**
  `{"error": "keyring no disponible: instale keyring==25.6.0; el password NO se guardó (nunca se persiste en texto plano)."}`
  y el servidor SÍ queda guardado sin password; si disponible → `set_password`.
  201 con el server (con `has_password`).
- `PUT "/<alias>"` → mismo body; alias de la URL manda (400 si el body trae otro
  alias). `password` ausente o `""` = CONSERVAR la actual (write-only). 404 si el
  alias no existe. 200.
- `DELETE "/<alias>"` → `delete_server`; 404 si no existía; 200 `{"ok": true}`.
- `POST "/<alias>/test"` → 404 si el alias no existe; `ok, detail = server_registry.test_connectivity(host)`;
  200 `{"ok": ok, "detail": detail}` (siempre 200: el resultado va en el body).

**Registro del blueprint** en `Stacky Agents/backend/api/__init__.py`, junto al del 87:
- import debajo de `api/__init__.py:45`:
  `from .devops_servers import bp as devops_servers_bp  # Plan 91 — registro de servidores DevOps`
- registro debajo de `api/__init__.py:91`:
  `api_bp.register_blueprint(devops_servers_bp)  # Plan 91 — /api/devops/servers/...`

**Health (aditivo)** — en `api/devops.py:14-22` (`devops_health_route`) agregar 2 keys
al dict (NUNCA quitar las existentes — la index signature de `DevOpsHealth`
(`DevOpsPage.tsx:26`) las admite):
```python
"servers_enabled": bool(getattr(cfg, "STACKY_DEVOPS_SERVERS_ENABLED", False)),
"rdp_available": (sys.platform == "win32") and server_registry.keyring_available(),
```
(agregar `import sys` y `from services import server_registry` al tope de `api/devops.py`).

**Tests PRIMERO** — archivo nuevo
`Stacky Agents/backend/tests/test_plan91_servers_endpoints.py`. Fixtures: espejo de
`tests/test_plan87_devops_endpoints.py:8-29` (setear/restaurar
`cfg.config.STACKY_DEVOPS_SERVERS_ENABLED`) + los monkeypatch de F2 (registry path
tmp + fake keyring). Casos:
- `test_f3_flag_off_all_routes_404`: con flag OFF, GET/POST/PUT/DELETE/test → 404.
- `test_f3_health_has_servers_keys`: `GET /api/devops/health` (SIN flag del 91) → 200
  y el body contiene `servers_enabled` (False) y `rdp_available` (bool).
- `test_f3_crud_roundtrip`: POST 201 → GET lo lista con `has_password: true` → PUT
  cambia `notes` SIN enviar password → GET sigue `has_password: true` (write-only
  preservado) → DELETE 200 → GET vacío.
- `test_f3_post_password_never_in_response`: la respuesta del POST (texto crudo) no
  contiene el password enviado.
- `test_f3_post_invalid_alias_400`.
- `test_f3_put_unknown_alias_404`.
- `test_f3_keyring_unavailable_503`: monkeypatch `server_registry.keyring = None` →
  POST con password → 503 y el error menciona `keyring`; el servidor quedó guardado
  con `has_password: false`.
- `test_f3_test_endpoint_returns_ok_detail`: monkeypatch
  `server_registry.test_connectivity` → `(True, "TCP 3389 OK")`; POST
  `/api/devops/servers/srv1/test` → 200 `{"ok": true, "detail": "TCP 3389 OK"}`.

**Registrar** el archivo en `run_harness_tests.ps1` y `.sh`.
**Comando:** `.venv/Scripts/python.exe -m pytest tests/test_plan91_servers_endpoints.py tests/test_plan87_devops_endpoints.py -q`
**Criterio de aceptación (binario):** 8 tests nuevos + los del 87 pasan (no-regresión
del health).
**Flag protectora:** `STACKY_DEVOPS_SERVERS_ENABLED` (guard 404 per-request), default OFF.
**Impacto por runtime:** N/A — no toca el arnés de agentes.
**Trabajo del operador:** ninguno (opt-in, default off).

### F4 — Backend: conexión RDP 1-click (`POST /api/devops/servers/<alias>/rdp`)

**Objetivo:** un click del operador ejecuta `cmdkey` + `mstsc` en el host del backend,
sin exponer el password.

**Archivo:** `Stacky Agents/backend/api/devops_servers.py` (misma F3) — ruta nueva:
```python
@bp.post("/<alias>/rdp")
def rdp_route(alias):
    """HITL §3.2: SIEMPRE un click explícito del operador; nada se conecta solo.
    §3.9: cmdkey/mstsc corren en el HOST del backend — si el backend corriera en otra
    máquina, el mstsc se abre allá. Aceptado: Stacky es mono-operador y corre local.
    """
    _guard()
    if sys.platform != "win32":
        return jsonify({"error": "RDP solo disponible en Windows (host del backend)."}), 501
    srv = server_registry.get_server(alias)
    if srv is None:
        return jsonify({"error": f"Servidor '{alias}' no existe."}), 404
    cred = server_registry.get_credential(alias)
    if cred is None:
        return jsonify({"error": f"'{alias}' no tiene password guardada (o keyring no disponible). Editá el servidor y cargala."}), 409
    username, domain, password = cred
    user_arg = f"{domain}\\{username}" if domain else username
    # lista de args, SIN shell, SIN log del comando (contiene el password) — §3.1
    rc = subprocess.run(
        ["cmdkey", f"/generic:TERMSRV/{srv['host']}", f"/user:{user_arg}", f"/pass:{password}"],
        capture_output=True, timeout=15,
    )
    if rc.returncode != 0:
        return jsonify({"error": "cmdkey falló al registrar la credencial TERMSRV."}), 502
    subprocess.Popen(  # detached: NO bloquea el request
        ["mstsc", f"/v:{srv['host']}"],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    return jsonify({"ok": True, "detail": f"mstsc lanzado hacia {srv['host']}."})
```
(agregar `import subprocess` al tope). **Prohibido:** loggear `rc.args`, `rc.stdout`
o el comando (contienen el password); loggear SOLO `returncode` si se desea.

**Casos borde codificados:** no-Windows → 501 (§3.6); sin password → 409 con CTA;
`cmdkey` rc!=0 → 502 sin filtrar el comando; `mstsc` es fire-and-forget (si el
operador cancela el diálogo RDP, no es error de Stacky).

**Tests PRIMERO** — archivo nuevo
`Stacky Agents/backend/tests/test_plan91_rdp_endpoint.py` (mismos fixtures de F3;
monkeypatch de `sys.platform` vía `monkeypatch.setattr("api.devops_servers.sys.platform", ...)`
y de `subprocess.run`/`subprocess.Popen` en el módulo `api.devops_servers`):
- `test_f4_non_windows_501`: platform `"linux"` → 501.
- `test_f4_unknown_alias_404`.
- `test_f4_no_password_409`.
- `test_f4_happy_path_calls_cmdkey_then_mstsc`: platform `"win32"`, fake `run`
  (rc=0) y fake `Popen` que capturan args → 200; el fake de `run` recibió
  `/generic:TERMSRV/<host>` y `/user:DOM\usr`; el fake de `Popen` recibió
  `["mstsc", "/v:<host>"]`.
- `test_f4_domain_empty_user_arg_plain`: domain `""` → `/user:usr` (sin backslash).
- `test_f4_cmdkey_fail_502`: fake `run` rc=1 → 502 y el body NO contiene el password.
- `test_f4_flag_off_404`.

**Registrar** el archivo en `run_harness_tests.ps1` y `.sh`.
**Comando:** `.venv/Scripts/python.exe -m pytest tests/test_plan91_rdp_endpoint.py -q`
**Criterio de aceptación (binario):** 7 tests pasan; grep en `api/devops_servers.py`
de `logger`/`print` no matchea ninguna línea que referencie `password`/`cred`/`rc.args`.
**Flag protectora:** la misma del 91 + gate de plataforma (§3.6).
**Impacto por runtime:** N/A — no toca el arnés de agentes. El comando corre en el
host del backend (§3.9, documentado en el docstring).
**Trabajo del operador:** ninguno; conectar es SIEMPRE su click (HITL §3.2).

### F5 — Frontend: sección "Servidores" (contrato §3.12) + API client

**Objetivo:** registrar la sección vía `DEVOPS_SECTIONS` con gate declarativo y
construir el CRUD visual.

**Archivos y cambios EXACTOS:**

1. `Stacky Agents/frontend/src/api/endpoints.ts` — objeto nuevo `DevOpsServers`
   (mismo patrón que el objeto `DevOps` que consume `DevOpsPage.tsx:81`):
   ```typescript
   export interface ServerSummary {
     alias: string; host: string; domain: string; username: string;
     notes: string; has_password: boolean;
   }
   export const DevOpsServers = {
     list: () => http.get<{ servers: ServerSummary[]; keyring_available: boolean }>("/devops/servers"),
     create: (body: { alias: string; host: string; domain?: string; username: string; notes?: string; password?: string }) =>
       http.post<ServerSummary>("/devops/servers", body),
     update: (alias: string, body: { host: string; domain?: string; username: string; notes?: string; password?: string }) =>
       http.put<ServerSummary>(`/devops/servers/${encodeURIComponent(alias)}`, body),
     remove: (alias: string) => http.delete(`/devops/servers/${encodeURIComponent(alias)}`),
     testConnection: (alias: string) => http.post<{ ok: boolean; detail: string }>(`/devops/servers/${encodeURIComponent(alias)}/test`, {}),
     connectRdp: (alias: string) => http.post<{ ok: boolean; detail: string }>(`/devops/servers/${encodeURIComponent(alias)}/rdp`, {}),
   };
   ```
   (adaptar `http.get/post/...` al helper HTTP REAL de `endpoints.ts` — copiar la
   forma exacta del objeto `DevOps` existente; si usa axios/fetch wrapper distinto,
   gana el del archivo).

2. **Componente nuevo** `Stacky Agents/frontend/src/components/devops/ServersSection.tsx`:
   - Props: `{ ctx: DevOpsSectionContext }` (mismo patrón que
     `PipelineBuilderSection.tsx:37-45`).
   - **Lista** de servidores (useQuery `["devops-servers"]` → `DevOpsServers.list()`):
     por fila alias (negrita), `dominio\usuario`, host, notes, badge
     `has_password` ("credencial guardada" verde / "sin password" gris), y botones:
     **Editar**, **Eliminar** (con `window.confirm("¿Eliminar el servidor '<alias>' y su credencial guardada?")`),
     **Probar conexión** (muestra `detail` inline con color por `ok`), y
     **Conectar por RDP** — este último SOLO renderizado si
     `ctx.health.rdp_available === true` (§3.6).
   - **Formulario** (crear/editar): campos alias (deshabilitado al editar), host,
     dominio, usuario, notes, password `type="password"`. **Write-only:** al editar,
     el campo password se muestra VACÍO con `placeholder={server.has_password ? "•••• (guardada)" : "sin password"}`;
     enviar vacío = conservar la actual (F3 lo garantiza).
   - **Aviso keyring:** si `list()` devuelve `keyring_available: false`, banner
     amarillo fijo: "keyring no disponible en el backend: los passwords no se pueden
     guardar (nunca se guardan en texto plano). Instalá keyring==25.6.0.".
   - **Errores siempre visibles (patrón C16 del 87 v3):** TODO async en try/catch con
     un área de error visible (`<div className="devops-error">{error}</div>`); un 503
     del POST muestra el `error` del body tal cual.

3. **Registro declarativo** — en `DevOpsPage.tsx`, agregar UNA entrada a
   `DEVOPS_SECTIONS` (`DevOpsPage.tsx:51`), exactamente el shape comentado como
   ejemplo en `DevOpsPage.tsx:57-65`:
   ```typescript
   {
     id: 'servidores',
     label: 'Servidores',
     icon: '🖥️',
     healthKey: 'servers_enabled',
     gateFlagKey: 'STACKY_DEVOPS_SERVERS_ENABLED',
     gateMessage: 'La sección Servidores necesita su flag (categoría DevOps).',
     render: (ctx) => <ServersSection ctx={ctx} />,
   },
   ```
   PROHIBIDO tocar el shell fuera de este array: el gate (`FlagGateBanner`), el
   montaje persistente (`display:none`, `DevOpsPage.tsx:87`) y el loop de render
   (`DevOpsPage.tsx:140`) ya son genéricos (§3.7).

**Tests PRIMERO** — archivo nuevo
`Stacky Agents/frontend/src/pages/__tests__/ServersSection.test.ts` (TS-puro, sin
render, mismo estilo que `DevOpsPage.test.ts:10-28`):
- `'DEVOPS_SECTIONS contiene la entrada servidores con gate declarativo'`: importar
  `DEVOPS_SECTIONS`, encontrar `id === 'servidores'`, assert
  `healthKey === 'servers_enabled'`, `gateFlagKey === 'STACKY_DEVOPS_SERVERS_ENABLED'`,
  `typeof render === 'function'` y `gateMessage` no vacío.
- `'ServersSection no hand-rollea el gate'`: leer el fuente de `ServersSection.tsx`
  (patrón grep del test `DevOpsPage.test.ts:53-65`) y assert que NO contiene
  `FlagGateBanner` ni `STACKY_DEVOPS_SERVERS_ENABLED` (el gate es del shell, §3.7).

**Comandos:** `npx vitest run src/pages/__tests__/ServersSection.test.ts` y
`npx tsc --noEmit` en `Stacky Agents/frontend`.
**Criterio de aceptación (binario):** ambos tests pasan y tsc da 0 errores. Con la
flag OFF, la sub-tab "Servidores" muestra `FlagGateBanner` con "Activar ahora" (lo
hace el shell solo — verificable manualmente, no exige test de render).
**Flag protectora:** gate declarativo `servers_enabled` (el shell la aplica).
**Impacto por runtime:** N/A — no toca el arnés de agentes.
**Trabajo del operador:** opt-in (default off); cargar sus servidores ES la feature,
no un paso técnico.

### F6 — Frontend: selector de servidor activo en el shell (contexto aditivo)

**Objetivo:** dropdown de alias en el shell del panel cuya selección queda disponible
para TODAS las secciones (presentes y futuras) vía `DevOpsSectionContext`, sin tocar
las secciones existentes.

**Archivo:** `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` — cambios EXACTOS:

1. **Interface (aditiva, §3.8)** — ampliar `DevOpsSectionContext` (`DevOpsPage.tsx:30-33`)
   con campos OPCIONALES (las secciones del 87 y los planes 88/89/90 NO se tocan;
   compilan igual porque son opcionales):
   ```typescript
   export interface DevOpsSectionContext {
     health: DevOpsHealth;
     refetchHealth: () => void;
     // Plan 91 — aditivo/opcional: scoping por servidor para secciones que lo consuman
     selectedServer?: { alias: string; host: string } | null;
     servers?: ServerSummary[];
   }
   ```
   (importar `ServerSummary` desde `../api/endpoints`).
2. **Datos** — en el componente `DevOpsPage` (`DevOpsPage.tsx:78`): useQuery
   `["devops-servers"]` → `DevOpsServers.list()`, con
   `enabled: healthQuery.data?.servers_enabled === true` (si la flag está OFF no se
   dispara ninguna llamada — KPI-3).
3. **Estado persistido** — `const [selectedAlias, setSelectedAlias] = useState<string | null>(() => localStorage.getItem('stacky.devops.selectedServer'))`;
   al cambiar: `localStorage.setItem('stacky.devops.selectedServer', alias)` (y
   `removeItem` si se elige "— ninguno —"). Si el alias persistido ya no existe en la
   lista, tratarlo como null (no crashear).
4. **Dropdown** — en la barra del shell (junto a las sub-tabs, `DevOpsPage.tsx:118`),
   renderizado SOLO si `health.servers_enabled === true` Y `servers.length >= 1`:
   `<select>` con opción `"— ninguno —"` + un `<option>` por alias.
5. **Contexto** — al armar `ctx` (`DevOpsPage.tsx:89-92`), agregar:
   `selectedServer: selected ? { alias: selected.alias, host: selected.host } : null`
   y `servers` (la lista completa). Los planes 88/89/90 podrán leer
   `ctx.selectedServer` cuando se implementen — **este plan NO les agrega alcance**
   (§3.10).

**Tests PRIMERO** — ampliar `ServersSection.test.ts` (mismo archivo de F5):
- `'shell no llama a servers con flag off'`: leer el fuente de `DevOpsPage.tsx` y
  assert que contiene el literal `servers_enabled === true` (el guard de `enabled`).
- `'localStorage key exacta'`: assert que el fuente contiene
  `'stacky.devops.selectedServer'`.
(Tests de fuente, no de render: vitest del repo no tiene `@testing-library/react` —
limitación preexistente documentada.)

**Comandos:** `npx vitest run src/pages/__tests__/ServersSection.test.ts` y
`npx tsc --noEmit` (0 errores — prueba de que la extensión fue realmente aditiva:
`PipelineBuilderSection.tsx` y `TriggerPipelineSection.tsx` compilan sin cambios).
**Criterio de aceptación (binario):** tests + tsc verdes SIN modificar ningún archivo
de `components/devops/` existente (verificable con `git status`).
**Flag protectora:** el dropdown solo existe con `servers_enabled` ON.
**Impacto por runtime:** N/A — no toca el arnés de agentes.
**Trabajo del operador:** ninguno (el selector es opcional; sin selección todo sigue
funcionando).

### F7 — Cierre: no-regresión total + verificación binaria

**Objetivo:** verificar la serie completa y la no-regresión del panel 87.

**Comandos EXACTOS (desde `Stacky Agents/backend`):**
```
.venv/Scripts/python.exe -m pytest tests/test_plan91_servers_flag.py tests/test_plan91_server_registry.py tests/test_plan91_servers_endpoints.py tests/test_plan91_rdp_endpoint.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan87_devops_flag.py tests/test_plan87_devops_endpoints.py tests/test_plan87_drafts_validation.py -q
.venv/Scripts/python.exe -m pytest tests/test_harness_flags.py tests/test_flag_wiring.py tests/test_harness_flags_help.py -q
```
y desde `Stacky Agents/frontend`:
```
npx tsc --noEmit
npx vitest run src/pages/__tests__/DevOpsPage.test.ts src/pages/__tests__/ServersSection.test.ts
```

**Checklist binario:**
- [ ] Los 4 archivos de test del 91 pasan (29 tests: 5 F1 + 9 F2 + 8 F3 + 7 F4).
- [ ] Tests del 87 pasan sin cambios (no-regresión del health y del shell).
- [ ] Meta-tests de flags pasan (registro, curated defaults, wiring, help).
- [ ] `tsc` 0 errores; vitest verde.
- [ ] Los 4 `tests/test_plan91_*.py` están registrados en `run_harness_tests.ps1` Y
      `run_harness_tests.sh`.
- [ ] `grep -i "password" "Stacky Agents/backend/services/server_registry.py"` y
      `... api/devops_servers.py`: ninguna línea escribe password a JSON/log.
- [ ] Con flag OFF: `curl /api/devops/servers` → 404; health → 200 con
      `servers_enabled:false`; UI muestra `FlagGateBanner`.
- [ ] Actualizar el encabezado de ESTE documento a IMPLEMENTADO (regla
      estado-en-doc).

**Impacto por runtime:** N/A — cierre.
**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Password termina en disco por un refactor futuro | Assert defensivo en `_save()` (raise si key `password`) + centinela `test_f2_password_never_in_json` + write-only en PUT |
| Password en logs (cmdkey lleva `/pass:` en args) | Prohibición codificada F4: no loggear `rc.args`/stdout/comando; criterio grep en F4; `subprocess` con lista, sin shell |
| `keyring` no instalado / backend de keyring falla | `keyring_available()` + 503 explícito con instrucción; servidor se guarda sin password; banner amarillo en UI; NUNCA fallback a texto plano (§3.1) |
| Backend corre en otra máquina que el operador | Documentado §3.9 (mstsc abre en el host del backend); aceptado por riel mono-operador local; no se "arregla" con complejidad extra |
| No-Windows (futuro deploy Linux) | 501 en `/rdp` + `rdp_available:false` en health + botón oculto en UI (§3.6); CRUD/test/selector funcionan igual |
| Flag nueva rompe meta-tests (default curado / wiring / help) | F1 codifica el gotcha (sin `default=`), consumidor real en F3, `PlainHelp` obligatoria, y corre `test_harness_flags.py` + `test_flag_wiring.py` + `test_harness_flags_help.py` en F7 |
| `test_connectivity` cuelga el request | timeout 3s hard-coded; el endpoint no reintenta; DNS con `.invalid` en tests (sin red real) |
| JSON corrupto a mano | `_load()` → `[]` con warning + `test_f2_corrupt_json_returns_empty` |
| Plan 87 sin implementar en el entorno destino | F0 pre-flight determinista (patrón 90 F0.a por referencia) |
| Secciones 88/89/90 asumen `selectedServer` siempre presente | Campos OPCIONALES en la interface (§3.8) + este plan NO les agrega alcance (§3.10): consumirlo será decisión de SUS planes al implementarse |

---

## 6. Fuera de scope (v1)

- **Ejecución remota real** (UNC/WinRM/SSH/agentes remotos): solo queda el contrato
  `get_credential(alias)` (§3.10). La extensión remota es otro plan (el que
  `89_PLAN...md:958-960` anticipó).
- **Multi-usuario / RBAC / permisos por servidor** (violaría §3.3, mono-operador).
- **Guardar el password en disco/DB en cualquier forma** (cifrado incluido): el vault
  es el del SO, punto.
- **Tunneling / gateway RDP / puertos alternativos** (v1: TCP 3389 directo).
- **Targets Linux** (SSH): el registro es de servidores Windows-RDP.
- **Scoping efectivo de 88/89/90 por servidor**: esos planes lo consumirán desde
  `ctx.selectedServer` cuando SE IMPLEMENTEN; nada de eso se construye acá.
- **Validación de login real en "Probar conexión"** (solo DNS+TCP 3389; el login lo
  valida el operador al conectarse).

---

## 7. Glosario, orden de implementación y DoD

### Glosario
- **RDP**: Remote Desktop Protocol — escritorio remoto de Windows (puerto TCP 3389).
- **mstsc**: cliente RDP de Windows (`mstsc /v:<host>` abre la conexión).
- **cmdkey**: CLI de Windows que guarda credenciales en el Credential Manager;
  `TERMSRV/<host>` es el nombre de destino que mstsc busca para autologin.
- **keyring / Credential Manager**: librería Python (`keyring==25.6.0`) que en Windows
  persiste secretos en el vault nativo del SO; Stacky la usa con service
  `stacky-devops` y key = alias.
- **DEVOPS_SECTIONS**: registro declarativo de secciones del panel DevOps
  (`DevOpsPage.tsx:51`); agregar una feature = 1 entrada + 1 componente (§3.12 del 87 v3).
- **health**: `GET /api/devops/health` (`api/devops.py:14-22`) — booleans que la UI usa
  para gatear secciones (`servers_enabled`, `rdp_available` son las keys de este plan).

### Orden de implementación
1. F0 — pre-flight del host 87 (no-op si ya está, como hoy).
2. F1 — flag en las 4 patas + tests meta (commitear junto con F3 si el centinela de
   wiring lo exige).
3. F2 — `services/server_registry.py` + `keyring==25.6.0` en requirements + tests.
4. F3 — `api/devops_servers.py` (CRUD + test conectividad) + health aditivo + tests.
5. F4 — endpoint RDP + tests.
6. F5 — `ServersSection.tsx` + entrada en `DEVOPS_SECTIONS` + API client + tests TS.
7. F6 — selector de servidor activo (contexto aditivo) + tests TS.
8. F7 — cierre: no-regresión total + checklist + estado del doc a IMPLEMENTADO.

### Definición de Hecho (DoD) global
- Todos los criterios binarios F0..F7 verdes con los comandos exactos citados.
- Password inexpugnable: no en JSON, no en GET, no en logs (centinelas verdes).
- Con la flag OFF (default), CERO diferencia observable vs. hoy.
- Contrato §3.12 respetado: el shell del panel no ganó lógica específica de
  "servidores" fuera de `DEVOPS_SECTIONS` + el dropdown genérico; ninguna sección
  existente modificada.
- `get_credential(alias)` documentado como punto único de consumo para la extensión
  remota futura.
- Encabezado de este documento actualizado a IMPLEMENTADO.
