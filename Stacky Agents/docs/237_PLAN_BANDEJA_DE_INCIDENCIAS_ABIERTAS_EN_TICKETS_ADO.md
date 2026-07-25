# Plan 237 — Bandeja de Incidencias Abiertas dentro de Tickets ADO

**Estado:** PROPUESTO v1
**Fecha:** 2026-07-25
**Autor:** StackyArchitectaUltraEficientCode
**Numeración:** 237 (los números 219..236 están RESERVADOS por el catálogo del plan 218; ver `Stacky Agents/docs/_roadmap/serie_paridad_218.json`. Usar cualquiera de esos números rompe el test de integridad de la serie).

---

## 1. Objetivo + KPI

### Objetivo (1 párrafo)

Agregar a Stacky una **vista dedicada de incidencias** —accesible desde el módulo "Tickets ADO"— que muestre **solo las incidencias** (work items de tipo `Issue` y `Bug`), con foco en las que están **ABIERTAS**, para que dejen de perderse entre el resto de los tickets. La vista es **100% ADITIVA**: el tablero general (`TicketBoard`) **NO cambia de aspecto ni de comportamiento**, salvo por un único botón nuevo en su cabecera que lleva a la bandeja. La clasificación "abierta / cerrada" **no se cablea con literales sueltos**: se resuelve en el backend con un orden de precedencia determinista que ya contempla la centralización de estados del plan 216.

### KPI / impacto esperado

| KPI | Hoy | Con el plan |
|---|---|---|
| Clics + scroll para saber cuántas incidencias abiertas hay | indeterminado (hay que recorrer el árbol/grafo completo del board) | 1 clic, número visible en la cabecera |
| Incidencias invisibles por el tope de 500 filas de `GET /api/tickets` (`backend/api/tickets.py:659`) | posible: una incidencia vieja cae fuera del `LIMIT 500` ordenado por `last_synced_at desc` | 0: la bandeja filtra **por tipo en la consulta SQL**, no en el cliente |
| Fuentes de verdad de "qué estado es cerrado" | 2 copias divergentes: `frontend/src/pages/TicketBoard.tsx:83` y `backend/services/ticket_assigner.py:41` | 1 resolvedor backend (`services/incident_inbox.py`) con precedencia perfil > 216 > default |
| Cambios visuales en el tablero general | — | 1 botón nuevo; el resto **byte-idéntico** |
| Pasos manuales nuevos para el operador | — | **0** (flag default ON, sin configuración obligatoria) |

---

## 2. Por qué ahora / gap que cierra

**Necesidad textual del operador:** *"Dentro de tickets ADO me debe de permitir entrar a algún apartado de incidencias donde las vea claramente cuáles son las que están abiertas y solo ver incidencias, para que no se me pierdan entre los tickets. Pero en la vista general sí verla como está hoy."*

Evidencia de que el gap es real (todo verificado en el código actual, no inferido):

1. **Stacky YA sabe qué es una incidencia, pero solo para pintarla, no para agruparla.**
   `Stacky Agents/frontend/src/utils/workItemTypeColor.ts:34` define `INCIDENT_TYPES = new Set(["issue", "bug"])` y `:43` exporta `isIncidentWorkItemType()`. Ese helper hoy solo se usa para el color y el ícono del badge (`:53 formatWorkItemTypeLabel`). **No existe ninguna vista que filtre por él.**

2. **El tablero mezcla todo por diseño.**
   `Stacky Agents/frontend/src/pages/TicketBoard.tsx:805` fija `viewMode` default `"graph"`, y `:968-970` arma `filteredEpics` + `filteredOrphans` sobre la jerarquía **completa** (`GET /api/tickets/hierarchy`, `backend/api/tickets.py:625-633`, que agrupa por `epic` / `parent_ado_id` / huérfanos). Las incidencias no tienen contenedor propio: caen como hijas de una épica o como huérfanas, mezcladas con Tasks.

3. **El tope de 500 puede esconder incidencias.**
   `backend/api/tickets.py:659` hace `.order_by(Ticket.last_synced_at.desc()...).limit(500)`. Una incidencia abierta pero vieja compite por ese cupo contra todas las Tasks. Este plan la saca de esa competencia.

4. **La serie de incidencias construyó el ciclo, pero nunca la vista.**
   - Plan 131 (`docs/131_...`): captura multimodal de incidencias — botón "Resolver incidencia" en el board (`TicketBoard.tsx:1008-1017`).
   - Plan 166 (MERGEADO): ciclo completo — publica la incidencia como `Issue` en el tracker (`backend/api/tickets.py:6873,6886` — `work_item_type="Issue"`) y agrega "Resolver con agente" (`dev_resolver_enabled`, `TicketBoard.tsx:821`).
   - Plan 177 (IMPL): auto-PR del Dev Resolutor.
   - Plan 188 (MERGEADO): del fallo de deploy a la incidencia.
   - Plan 200 (SIN implementar): consola por incidencia.
   **Ninguno de los cinco entrega un lugar donde ver la lista de incidencias abiertas.** El ciclo produce incidencias más rápido de lo que el board las hace visibles: ese es exactamente el dolor reportado.

5. **La infraestructura para hacerlo barato ya está.**
   - Deep-links y estado en URL: `frontend/src/services/routes.ts` (plan 165, MERGEADO) — `parseRoute` preserva query params desconocidos verbatim (`:73-74`), así que `?scope=todas` funciona sin tocar el parser.
   - Navegación de shell: `frontend/src/components/shell/shellNav.ts` (plan 139) — agregar un tab es declarativo; `AppSidebar.tsx:22` itera `orderedVisibleGroups()`.
   - Portapapeles: `frontend/src/services/copyService.ts:29 copyText` (plan 194, MERGEADO).
   - Estados de carga/vacío/error ya primitivados: `LoadErrorState`, `EmptyState`, `SkeletonList` (importados en `TicketBoard.tsx:18-20`).

**Gap en una frase:** Stacky sabe qué es una incidencia y sabe crearlas, pero no tiene **ningún lugar donde verlas juntas**; este plan agrega ese lugar sin tocar la vista general.

---

## 3. Principios y guardarraíles (NO negociables)

| # | Guardarraíl | Cómo se cumple en este plan |
|---|---|---|
| P1 | **La vista general NO cambia.** | `TicketBoard.tsx` recibe **exactamente 2 líneas nuevas** (1 import + 1 elemento JSX autocontenido). `TicketBoard.module.css` **NO se toca**. Cero cambios en el árbol, el grafo, los filtros o el orden. |
| P2 | **Paridad de 3 runtimes** (Codex CLI / Claude Code CLI / GitHub Copilot Pro). | La bandeja es **solo lectura** sobre la tabla `tickets` local. No lanza agentes, no invoca LLMs, no depende de ningún runtime. El único campo runtime-adyacente es `stacky_status`, que escribe `services/ticket_status.py` igual para los 3. Fallback: si `stacky_status` falta o es desconocido, la UI muestra "idle". |
| P3 | **Cero trabajo extra para el operador.** | Flag `STACKY_INCIDENT_INBOX_ENABLED` **default ON**. Ninguna de las 4 excepciones duras aplica: no bypassea revisión humana, no es destructiva ni irreversible (es solo lectura), no tiene prerequisitos (usa la DB que ya se sincroniza), no reduce seguridad. Sin configuración obligatoria: si el perfil del cliente no define nada, se usan los defaults que ya replican el comportamiento actual. |
| P4 | **Human-in-the-loop.** | La bandeja **no decide ni actúa**: no cierra, no reasigna, no publica, no lanza agentes. Solo muestra y deja copiar/abrir. Amplifica al operador; no lo reemplaza. |
| P5 | **Mono-operador sin auth.** | Cero RBAC, cero roles, cero multiusuario. El filtro por asignado reusa el mecanismo existente (`assigned_to_ado`), que es informativo, no un control de acceso. |
| P6 | **"Abierta" NUNCA es un literal cableado.** | Se resuelve en `backend/services/incident_inbox.py` con precedencia declarada (§F1). Contrato explícito con el plan 216 (§4.1.3). |
| P7 | **No degradar performance.** | La consulta filtra por tipo **en SQL** y **no hace N+1** (no trae `last_execution` ni `pipeline_summary`, a diferencia de `list_tickets`, que sí hace 2 llamadas por fila en `backend/api/tickets.py:665-672`). Tope duro de 1000 filas con bandera `truncated`. |
| P8 | **Reusar, no reinventar.** | Reusa: `isIncidentWorkItemType` (177/166), `copyText` (194), `routes.ts` (165), `shellNav.ts` (139), `EmptyState`/`LoadErrorState`/`SkeletonList` (140), `Ticket.to_dict()` (218 F5). |
| P9 | **Backward-compatible.** | Todo es aditivo: endpoints nuevos, archivos nuevos, un tab nuevo. Con la flag OFF la superficie desaparece por completo y la app queda idéntica a hoy. |

---

## 4. Contratos y decisiones congeladas

### 4.1 Resolución de "qué cuenta como INCIDENCIA" y "qué cuenta como ABIERTA"

Todo vive en un módulo nuevo y **puro** (sin Flask, sin DB, sin I/O): `backend/services/incident_inbox.py`.

#### 4.1.1 Tipos de incidencia — precedencia

| Orden | Fuente | Valor |
|---|---|---|
| 1 | `client_profile["incident_inbox"]["incident_types"]` | lista de strings no vacía |
| 2 | *(sin fuente intermedia)* | — |
| 3 | **default** | `("issue", "bug")` |

El default replica **exactamente** `INCIDENT_TYPES` de `frontend/src/utils/workItemTypeColor.ts:34`, para que la bandeja y el badge del board nunca discrepen.

#### 4.1.2 Estados cerrados — precedencia

| Orden | Fuente | Nota |
|---|---|---|
| 1 | `client_profile["incident_inbox"]["closed_states"]` | override explícito del operador |
| 2 | `client_profile["state_flow"]["closed_states"]` | **key del plan 216** (ver 4.1.3) |
| 3 | **default** `("Done", "Closed", "Resolved", "Removed", "Completed")` | idéntico a `TicketBoard.tsx:83` y a `backend/services/ticket_assigner.py:41` |

Comparación **case-insensitive** y con `strip()`. Una lista presente pero vacía o con elementos no-string se trata como **ausente** (se cae al siguiente nivel) — nunca lanza.

#### 4.1.3 Contrato con el plan 216 (CENTRALIZACIÓN DE ESTADOS)

El plan 216 (CRITICADO v2, sin implementar) crea la key `client_profile.state_flow` con shape `{"version": "1.0", "rules": [...]}` (ver `docs/216_...md:80`). Ese shape **no incluye** `closed_states`.

**Contrato declarado por este plan (237):**

- 237 lee `state_flow["closed_states"]` como **key ADITIVA y OPCIONAL** dentro del mismo objeto `state_flow`. Si no existe (que es el caso hoy y también el día en que 216 aterrice sin agregarla), 237 **cae al default** y se comporta exactamente como el board de hoy.
- 216 **no debe borrar ni renombrar** claves desconocidas dentro de `state_flow`. Si 216 se implementa después, su validador `_check_state_flow(value)` (`docs/216_...md:115`) debe **ignorar** (no rechazar) la key `closed_states`.
- Cuando 216 esté implementado, agregar `closed_states` a la pestaña "Estados" del perfil es un cambio de **una línea de UI** en 216 y **cero líneas** en 237.
- **Guarda de regresión:** el test `test_plan237_incident_inbox_core.py::test_state_flow_216_closed_states_tiene_precedencia_sobre_default` congela este contrato. Si 216 rompe la key, ese test se pone rojo con un mensaje que lo explica.

### 4.2 Contrato de la API (congelado)

`GET /api/incident-inbox/status`

```json
{
  "ok": true,
  "enabled": true,
  "incident_types": ["issue", "bug"],
  "incident_types_source": "default",
  "closed_states": ["Done", "Closed", "Resolved", "Removed", "Completed"],
  "closed_states_source": "default"
}
```

- Con la flag OFF devuelve **200** con `"enabled": false` (para que el punto de entrada se oculte sin que la UI lo trate como error). Mismo patrón que `backend/api/incidents.py:13-31`.
- Valores posibles de `*_source`: `"profile_incident_inbox"` | `"profile_state_flow"` | `"default"`.

`GET /api/incident-inbox/items?project=<nombre>&scope=<open|all>`

```json
{
  "ok": true,
  "scope": "open",
  "counts": { "open": 7, "closed": 12, "total": 19 },
  "truncated": false,
  "incident_types": ["issue", "bug"],
  "closed_states": ["Done", "Closed", "Resolved", "Removed", "Completed"],
  "items": [
    { "id": 42, "ado_id": 1234, "title": "...", "work_item_type": "Issue",
      "ado_state": "Active", "ado_url": "https://...", "assigned_to_ado": "x@y.z",
      "stacky_status": "idle", "last_synced_at": "2026-07-24T10:00:00",
      "is_open": true }
  ]
}
```

- `items[]` es el payload de `Ticket.to_dict()` (`backend/models.py:105`) **más** la key `is_open` (bool). Ninguna key se quita ni se renombra.
- `counts` se calcula sobre **todas** las incidencias del proyecto, no solo sobre las devueltas por `scope`.
- Con la flag OFF devuelve **404** `{"ok": false, "error": "feature_disabled"}` (mismo shape que `backend/api/incidents.py:9-10`).
- `scope` inválido o ausente ⇒ se normaliza a `"open"` (nunca 400).
- Tope duro: 1000 filas; si se supera, `truncated: true` y la UI muestra un aviso.

---

## 5. Fases

> **Orden obligatorio:** F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7 → F8. Cada fase deja el repo verde y es verificable sola.

---

### F0 — Flag del arnés `STACKY_INCIDENT_INBOX_ENABLED` (registro cuádruple)

**Objetivo (1 frase):** registrar la flag maestra de la bandeja, default ON y editable desde la UI del panel de flags, sin cambiar todavía ningún comportamiento.

**Valor:** rollback total del plan en un clic desde la UI, sin redeploy ni tocar `.env` a mano.

**Trabajo del operador:** ninguno (default ON; ninguna de las 4 excepciones duras aplica: es solo lectura, no bypassea revisión humana, no tiene prerequisitos, no reduce seguridad).

#### Archivos a editar (4) y crear (1)

**(a) `Stacky Agents/backend/services/harness_flags.py`** — dos ediciones:

Edición 1 — agregar la key a la categoría `interfaz_ui`. Anclaje: el bloque que empieza en `:370` con `"interfaz_ui": (`. Insertar la línea nueva **inmediatamente después** de la línea `:375` (`"STACKY_CONNECTION_RESILIENCE_ENABLED", ...`) y antes del `),` de `:376`:

```python
        "STACKY_INCIDENT_INBOX_ENABLED",  # Plan 237 — bandeja de incidencias abiertas
```

Edición 2 — agregar el `FlagSpec` al final de `FLAG_REGISTRY`. Anclaje: copiar el patrón EXACTO del bloque de `:3915-3927` (plan 192). Insertar **después** del último `FlagSpec(...)` de la tupla y **antes** del `)` que cierra `FLAG_REGISTRY`:

```python
    # -- Plan 237 -- Bandeja de incidencias abiertas dentro de Tickets ADO --------
    FlagSpec(
        key="STACKY_INCIDENT_INBOX_ENABLED",
        type="bool",
        default=True,  # default ON (ninguna de las 4 excepciones duras aplica; curada en _CURATED_DEFAULTS_ON)
        label="Bandeja de incidencias abiertas",
        description=(
            "Plan 237 - Vista dedicada que lista SOLO incidencias (Issue/Bug) con foco "
            "en las abiertas, accesible desde Tickets ADO. Solo lectura: no lanza agentes "
            "ni modifica el tracker. OFF: la vista, el tab y el boton de entrada desaparecen "
            "y el tablero general queda identico."
        ),
        group="global",
    ),
```

**(b) `Stacky Agents/backend/config.py`** — agregar el campo. Anclaje: insertar **inmediatamente después** del bloque `STACKY_BULK_ACTIONS_ENABLED` que termina en `:1523`:

```python
    # -- Plan 237 -- Bandeja de incidencias abiertas (UI, solo lectura) ---------
    # Default ON: no publica nada, no destruye, sin prerequisitos, no reduce
    # seguridad. OFF => el tab, la pagina y el boton de entrada desaparecen.
    STACKY_INCIDENT_INBOX_ENABLED: bool = os.getenv(
        "STACKY_INCIDENT_INBOX_ENABLED", "true"
    ).strip().lower() == "true"
```

**(c) `Stacky Agents/backend/tests/test_harness_flags.py`** — agregar la key al set `_CURATED_DEFAULTS_ON` (el set empieza en `:467`). Insertar **junto a las flags de UI**, inmediatamente después de la línea `:725` (`"STACKY_CONNECTION_RESILIENCE_ENABLED",`):

```python
    "STACKY_INCIDENT_INBOX_ENABLED",
```

> **Por qué es obligatorio:** `test_default_known_only_for_curated` (`:816-825`) exige `known_keys == _CURATED_DEFAULTS_ON`. Un `FlagSpec` con `default=True` que no esté en el set pone ese test en rojo.

**(d) `Stacky Agents/backend/scripts/run_harness_tests.sh`** — registrar los 3 tests nuevos del plan. Insertar **antes** del `)` que cierra la lista `HARNESS_TEST_FILES` (hoy en `:657`):

```sh
  # -- Plan 237 - Bandeja de incidencias abiertas --
  tests/test_plan237_inbox_flag.py
  tests/test_plan237_incident_inbox_core.py
  tests/test_plan237_incident_inbox_api.py
```

> Los tres archivos se registran **en F0** aunque dos se creen en F1/F2. Si el meta-test `backend/tests/test_harness_ratchet_meta.py` exige además `backend/tests/harness_ratchet_allowlist.txt`, agregarlos también ahí, con el mismo orden.

#### NO tocar

- `_REQUIRES_MAP_FROZEN`: la flag **no tiene** `requires=`, así que no lleva arista. **No agregar nada ahí.**
- `_FROZEN_BOUNDS`: es solo para flags numéricas (`type="int"`/`"float"`). La flag es `bool`. **No agregar nada ahí.**
- `deployment/harness_defaults.env`: **PROHIBIDO editarlo a mano**; se genera con `deployment/export_harness_defaults.py`. Este plan **no** lo regenera (el archivo hoy está parcial por diseño).

#### Tests PRIMERO (TDD)

Crear `Stacky Agents/backend/tests/test_plan237_inbox_flag.py`, calcado de `backend/tests/test_connection_resilience_flag.py` (patrón exacto, incluida la nota de contaminación por `importlib.reload`):

```python
"""tests/test_plan237_inbox_flag.py -- Plan 237 F0: flag STACKY_INCIDENT_INBOX_ENABLED.

G5: este archivo hace importlib.reload(config) y contamina tests flag-off de la
misma sesion pytest. Correr SIEMPRE por archivo (como todo el arnes).
"""
import importlib

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS

KEY = "STACKY_INCIDENT_INBOX_ENABLED"


def test_flag_registrada_bool_default_on():
    spec = next((s for s in FLAG_REGISTRY if s.key == KEY), None)
    assert spec is not None, f"{KEY} no esta en FLAG_REGISTRY"
    assert spec.type == "bool"
    assert spec.default is True


def test_flag_categorizada_interfaz_ui():
    assert KEY in _CATEGORY_KEYS["interfaz_ui"]


def test_config_default_efectivo_on(monkeypatch):
    monkeypatch.delenv(KEY, raising=False)
    import config as config_module
    importlib.reload(config_module)
    assert getattr(config_module.config, KEY) is True


def test_config_env_off_apaga(monkeypatch):
    monkeypatch.setenv(KEY, "false")
    import config as config_module
    importlib.reload(config_module)
    assert getattr(config_module.config, KEY) is False
```

#### Comandos exactos

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
& ".\.venv\Scripts\python.exe" -m pytest tests\test_plan237_inbox_flag.py -v
& ".\.venv\Scripts\python.exe" -m pytest tests\test_harness_flags.py -v
```

> **Intérprete:** `backend\.venv\Scripts\python.exe` es **Python 3.13.5** (el correcto). `backend\venv\Scripts\python.exe` es 3.11.9 y **NO se usa**. Correr **siempre por archivo**: la suite completa da falsos rojos por contaminación entre tests.

#### Criterio de aceptación (binario)

1. Los dos comandos de arriba terminan en `passed` sin `failed`/`error`.
2. `Select-String -Path "backend\config.py" -Pattern "STACKY_INCIDENT_INBOX_ENABLED"` devuelve **≥ 1** línea.
3. `Select-String -Path "backend\services\harness_flags.py" -Pattern "STACKY_INCIDENT_INBOX_ENABLED"` devuelve **exactamente 2** líneas (categoría + FlagSpec).

#### Impacto por runtime

| Runtime | Impacto | Fallback |
|---|---|---|
| Codex CLI | ninguno | n/a — la flag no toca el pipeline de ejecución |
| Claude Code CLI | ninguno | n/a |
| GitHub Copilot Pro | ninguno | n/a |

---

### F1 — Núcleo puro de clasificación: `backend/services/incident_inbox.py`

**Objetivo (1 frase):** una única función pura que responda "¿esto es una incidencia?" y "¿está abierta?", con la precedencia de §4.1, sin Flask ni DB.

**Valor:** elimina la divergencia entre las dos copias actuales de `CLOSED_STATES` y deja el criterio testeable en milisegundos.

**Trabajo del operador:** ninguno.

**Flag que la protege:** `STACKY_INCIDENT_INBOX_ENABLED` (el módulo es puro; la flag se consulta en F2, en el endpoint).

#### Archivo a CREAR: `Stacky Agents/backend/services/incident_inbox.py`

```python
"""Plan 237 F1 -- Nucleo PURO de la bandeja de incidencias.

Sin Flask, sin SQLAlchemy, sin I/O: solo funciones deterministas sobre dicts.
Fuente UNICA de verdad de "que es una incidencia" y "que estado esta abierto".
"""
from __future__ import annotations

# Espejo EXACTO de INCIDENT_TYPES en frontend/src/utils/workItemTypeColor.ts:34.
DEFAULT_INCIDENT_TYPES: tuple[str, ...] = ("issue", "bug")

# Espejo EXACTO de CLOSED_STATES en frontend/src/pages/TicketBoard.tsx:83 y de
# _CLOSED_STATES en backend/services/ticket_assigner.py:41.
DEFAULT_CLOSED_STATES: tuple[str, ...] = (
    "Done", "Closed", "Resolved", "Removed", "Completed",
)

# Tope duro de filas devueltas por la bandeja (P7).
MAX_ITEMS: int = 1000


def normalize(value: str | None) -> str:
    """'  Done ' -> 'done'. None/no-str -> ''."""
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _clean_string_list(raw) -> tuple[str, ...] | None:
    """Lista de strings no vacia -> tupla de strings ya stripeados. Si no lo es
    (None, no-list, vacia, con elementos no-str o todos vacios) devuelve None
    para que el caller caiga al siguiente nivel de precedencia. NUNCA lanza."""
    if not isinstance(raw, list):
        return None
    out = [v.strip() for v in raw if isinstance(v, str) and v.strip()]
    return tuple(out) if out else None


def resolve_incident_types(profile: dict | None) -> tuple[tuple[str, ...], str]:
    """(tipos_normalizados, fuente). Ver Plan 237 seccion 4.1.1."""
    if isinstance(profile, dict):
        section = profile.get("incident_inbox")
        if isinstance(section, dict):
            explicit = _clean_string_list(section.get("incident_types"))
            if explicit is not None:
                return tuple(normalize(v) for v in explicit), "profile_incident_inbox"
    return DEFAULT_INCIDENT_TYPES, "default"


def resolve_closed_states(profile: dict | None) -> tuple[tuple[str, ...], str]:
    """(estados_cerrados_tal_cual, fuente). Ver Plan 237 seccion 4.1.2.

    CONTRATO CON EL PLAN 216: la key `state_flow.closed_states` es ADITIVA y
    OPCIONAL. Si el plan 216 aterriza sin ella, esta funcion cae al default y el
    comportamiento es identico al del tablero de hoy.
    """
    if isinstance(profile, dict):
        section = profile.get("incident_inbox")
        if isinstance(section, dict):
            explicit = _clean_string_list(section.get("closed_states"))
            if explicit is not None:
                return explicit, "profile_incident_inbox"
        state_flow = profile.get("state_flow")
        if isinstance(state_flow, dict):
            from_216 = _clean_string_list(state_flow.get("closed_states"))
            if from_216 is not None:
                return from_216, "profile_state_flow"
    return DEFAULT_CLOSED_STATES, "default"


def is_incident_type(work_item_type: str | None, types: tuple[str, ...]) -> bool:
    """True si el tipo del work item esta en el conjunto de tipos-incidencia."""
    norm = normalize(work_item_type)
    if not norm:
        return False
    return norm in {normalize(t) for t in types}


def is_open_state(state: str | None, closed_states: tuple[str, ...]) -> bool:
    """True si el estado NO esta en el conjunto de estados cerrados.

    Estado vacio/None => ABIERTA (un item sin estado sincronizado es trabajo
    pendiente, no trabajo terminado: nunca se oculta silenciosamente).
    """
    norm = normalize(state)
    if not norm:
        return True
    return norm not in {normalize(s) for s in closed_states}


def summarize_counts(flags: list[bool]) -> dict[str, int]:
    """[True, False, True] -> {'open': 2, 'closed': 1, 'total': 3}."""
    total = len(flags)
    open_count = sum(1 for f in flags if f)
    return {"open": open_count, "closed": total - open_count, "total": total}


def normalize_scope(raw: str | None) -> str:
    """'all'/'todas' -> 'all'; cualquier otra cosa (incluido None) -> 'open'."""
    norm = normalize(raw)
    return "all" if norm in {"all", "todas"} else "open"
```

#### Tests PRIMERO (TDD)

Crear `Stacky Agents/backend/tests/test_plan237_incident_inbox_core.py` con **exactamente** estos casos:

| Test | Qué verifica |
|---|---|
| `test_defaults_espejan_el_frontend` | `DEFAULT_INCIDENT_TYPES == ("issue", "bug")` y `DEFAULT_CLOSED_STATES == ("Done","Closed","Resolved","Removed","Completed")` |
| `test_perfil_none_usa_default` | `resolve_incident_types(None) == (("issue","bug"), "default")` y `resolve_closed_states(None)[1] == "default"` |
| `test_perfil_sin_secciones_usa_default` | `resolve_closed_states({"otra_cosa": 1})[1] == "default"` |
| `test_incident_inbox_tiene_maxima_precedencia` | perfil con **ambas** `incident_inbox.closed_states=["Cerrado"]` y `state_flow.closed_states=["X"]` ⇒ `(("Cerrado",), "profile_incident_inbox")` |
| `test_state_flow_216_closed_states_tiene_precedencia_sobre_default` | perfil `{"state_flow": {"version":"1.0","rules":[],"closed_states":["Terminado","Cancelado"]}}` ⇒ `(("Terminado","Cancelado"), "profile_state_flow")`. **Congela el contrato con el plan 216.** |
| `test_state_flow_sin_closed_states_cae_a_default` | perfil `{"state_flow": {"version":"1.0","rules":[]}}` (shape literal del 216) ⇒ fuente `"default"` |
| `test_listas_corruptas_caen_al_siguiente_nivel` | `[]`, `["", "  "]`, `[1, 2]`, `"Done"`, `None` ⇒ todos fuente `"default"`, sin excepción |
| `test_is_incident_type_case_insensitive` | `"Issue"`, `"ISSUE"`, `" bug "` ⇒ True; `"Task"`, `"Epic"`, `""`, `None` ⇒ False |
| `test_is_open_state_case_insensitive` | `"Active"`, `"New"`, `"En Progreso"` ⇒ True; `"Done"`, `"closed"`, `" Resolved "` ⇒ False |
| `test_estado_vacio_es_abierta` | `is_open_state(None, DEFAULT_CLOSED_STATES)` y `is_open_state("", ...)` ⇒ True |
| `test_summarize_counts` | `[True, True, False]` ⇒ `{"open":2,"closed":1,"total":3}`; `[]` ⇒ `{"open":0,"closed":0,"total":0}` |
| `test_normalize_scope` | `"all"`/`"ALL"`/`"todas"` ⇒ `"all"`; `"open"`/`None`/`""`/`"basura"` ⇒ `"open"` |

Encabezado obligatorio del archivo de test (para que los imports resuelvan igual que en `test_plan218_parity_endpoint.py:15-18`):

```python
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.incident_inbox import (  # noqa: E402
    DEFAULT_CLOSED_STATES, DEFAULT_INCIDENT_TYPES, is_incident_type,
    is_open_state, normalize_scope, resolve_closed_states,
    resolve_incident_types, summarize_counts,
)
```

#### Comando exacto

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
& ".\.venv\Scripts\python.exe" -m pytest tests\test_plan237_incident_inbox_core.py -v
```

#### Criterio de aceptación (binario)

1. **12 tests passed, 0 failed.**
2. `Select-String -Path "backend\services\incident_inbox.py" -Pattern "import flask|sqlalchemy|from models"` devuelve **0 líneas** (el módulo es puro).

#### Impacto por runtime

Ninguno en los 3 (módulo puro, sin ejecución de agentes). Fallback: n/a.

---

### F2 — Endpoint de solo lectura `backend/api/incident_inbox.py`

**Objetivo (1 frase):** exponer `GET /api/incident-inbox/status` y `GET /api/incident-inbox/items` respetando el contrato de §4.2, sin tocar el archivo `backend/api/tickets.py` (351 KB, disputado).

**Valor:** la lista de incidencias sale filtrada desde SQL, sin el tope de 500 del listado general y sin N+1.

**Trabajo del operador:** ninguno.

**Flag que la protege:** `STACKY_INCIDENT_INBOX_ENABLED` (default ON). Leída como `config.config.STACKY_INCIDENT_INBOX_ENABLED`, **nunca** del módulo `config` pelado.

#### Archivo a CREAR: `Stacky Agents/backend/api/incident_inbox.py`

```python
"""Plan 237 F2 -- Bandeja de incidencias abiertas (solo lectura).

Blueprint independiente: NO se toca backend/api/tickets.py (351 KB, disputado
por los planes 212/213 y por una sesion paralela).
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

bp = Blueprint("incident_inbox", __name__, url_prefix="/incident-inbox")


def _enabled() -> bool:
    # GOTCHA REAL: `config` importado como modulo devuelve el DEFAULT y mata el
    # branch OFF. La instancia es `config.config`.
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_INCIDENT_INBOX_ENABLED", True))


def _feature_disabled_response():
    return jsonify({"ok": False, "error": "feature_disabled"}), 404


def _profile_for(project_name: str | None) -> dict | None:
    """client_profile del proyecto activo. Nunca lanza: si no se puede leer,
    devuelve None y el resolvedor cae al default."""
    try:
        from services.client_profile import load_client_profile
        if not project_name:
            from services.project_context import resolve_project_context
            ctx = resolve_project_context()
            project_name = getattr(ctx, "stacky_project_name", None) if ctx else None
        if not project_name:
            return None
        return load_client_profile(project_name)
    except Exception:
        return None


@bp.get("/status")
def incident_inbox_status():
    from services.incident_inbox import resolve_closed_states, resolve_incident_types

    project_name = (request.args.get("project") or "").strip() or None
    profile = _profile_for(project_name)
    types, types_source = resolve_incident_types(profile)
    closed, closed_source = resolve_closed_states(profile)
    return jsonify({
        "ok": True,
        "enabled": _enabled(),
        "incident_types": list(types),
        "incident_types_source": types_source,
        "closed_states": list(closed),
        "closed_states_source": closed_source,
    })


@bp.get("/items")
def incident_inbox_items():
    if not _enabled():
        return _feature_disabled_response()

    from sqlalchemy import func

    from db import session_scope
    from models import Ticket
    from services.incident_inbox import (
        MAX_ITEMS, is_open_state, normalize, normalize_scope,
        resolve_closed_states, resolve_incident_types, summarize_counts,
    )

    # SEAM DELIBERADO: se reusan los helpers privados de api/tickets.py para NO
    # duplicar la semantica multi-proyecto del filtro (que es sutil: compara
    # stacky_project_name y cae a project cuando el primero es NULL,
    # backend/api/tickets.py:347-354). Import LAZY dentro de la vista: evita
    # ciclos de import al cargar el blueprint.
    try:
        from api.tickets import _request_project_name, _ticket_project_filter
    except ImportError:
        return jsonify({
            "ok": False,
            "error": "project_filter_seam_missing",
            "message": (
                "Los helpers _request_project_name/_ticket_project_filter de "
                "api/tickets.py cambiaron de nombre. Ver Plan 237 F2."
            ),
        }), 200

    scope = normalize_scope(request.args.get("scope"))
    project_name = _request_project_name()
    profile = _profile_for(project_name)
    types, _ = resolve_incident_types(profile)
    closed, _ = resolve_closed_states(profile)

    with session_scope() as session:
        q = session.query(Ticket)
        project_filter = _ticket_project_filter(project_name)
        if project_filter is not None:
            q = q.filter(project_filter)
        # FILTRO POR TIPO EN SQL: las incidencias no compiten por el cupo del
        # listado general (que corta en 500, api/tickets.py:659).
        q = q.filter(func.lower(Ticket.work_item_type).in_([normalize(t) for t in types]))
        rows = q.order_by(
            Ticket.last_synced_at.desc().nulls_last(), Ticket.ado_id.desc()
        ).limit(MAX_ITEMS + 1).all()

        truncated = len(rows) > MAX_ITEMS
        rows = rows[:MAX_ITEMS]

        # Sin N+1: NO se consulta AgentExecution ni pipeline_summary por fila.
        items = []
        flags = []
        for t in rows:
            payload = t.to_dict()
            open_flag = is_open_state(t.ado_state, closed)
            payload["is_open"] = open_flag
            flags.append(open_flag)
            items.append(payload)

    counts = summarize_counts(flags)
    if scope == "open":
        items = [i for i in items if i["is_open"]]

    # Abiertas primero; dentro de cada grupo se conserva el orden de la query.
    items.sort(key=lambda i: 0 if i["is_open"] else 1)

    return jsonify({
        "ok": True,
        "scope": scope,
        "counts": counts,
        "truncated": truncated,
        "incident_types": list(types),
        "closed_states": list(closed),
        "items": items,
    })
```

> **Nota sobre `services.project_context`:** si el módulo o la función `resolve_project_context` no existiera con ese nombre, el `try/except Exception` de `_profile_for` ya lo cubre (devuelve `None` ⇒ defaults). **No inventar un import alternativo.** Verificar con `Select-String -Path "backend\services\*.py" -Pattern "def resolve_project_context"` y usar la ruta real que aparezca.

#### Archivo a EDITAR: `Stacky Agents/backend/api/__init__.py`

Dos líneas, en los bloques que ya existen (`import` en `:65`, `register_blueprint` en `:136`):

```python
from .incident_inbox import bp as incident_inbox_bp  # Plan 237 - bandeja de incidencias
```

```python
api_bp.register_blueprint(incident_inbox_bp)  # Plan 237 - url_prefix="/incident-inbox"
```

> **GOTCHA de merge:** `api/__init__.py` es un registro compartido. Git puede fusionar dos ramas que agregan **la misma línea** sin marcar conflicto, dejando un duplicado silencioso. Tras cualquier merge, verificar con:
> `Select-String -Path "backend\api\__init__.py" -Pattern "incident_inbox_bp"` ⇒ debe devolver **exactamente 2** líneas.

#### Tests PRIMERO (TDD)

Crear `Stacky Agents/backend/tests/test_plan237_incident_inbox_api.py`. Fixture de cliente calcada de `backend/tests/test_plan218_parity_endpoint.py:24-31`:

```python
@pytest.fixture
def client():
    from app import create_app
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c
```

> **GOTCHA:** `create_app()` fuera de pytest dispara daemons y sync real contra ADO. **Solo instanciarlo dentro de un test de pytest**, nunca en un script suelto.

Casos obligatorios:

| Test | Qué verifica |
|---|---|
| `test_status_200_con_flag_on` | `GET /api/incident-inbox/status` ⇒ 200, `enabled True`, `incident_types == ["issue","bug"]`, `closed_states_source == "default"` |
| `test_status_200_con_flag_off` | con `patch` de la flag en `False` ⇒ **200** y `enabled False` (no 404) |
| `test_items_404_con_flag_off` | con la flag en `False` ⇒ **404** y `data["error"] == "feature_disabled"` |
| `test_items_devuelve_solo_incidencias` | sembrar en DB: 1 `Issue` "Active", 1 `Bug` "Done", 1 `Task` "Active", 1 `Epic` "New" ⇒ `len(items)` con `scope=all` es **2**; ningún item tiene `work_item_type` en `{"Task","Epic"}` |
| `test_scope_open_filtra_cerradas` | `?scope=open` ⇒ solo el `Issue` "Active"; `counts == {"open":1,"closed":1,"total":2}` |
| `test_scope_invalido_cae_a_open` | `?scope=basura` ⇒ `data["scope"] == "open"`, sin 400 |
| `test_counts_cuenta_todas_no_solo_el_scope` | con `scope=open`, `counts["total"]` sigue siendo 2 |
| `test_item_conserva_las_keys_del_ticket` | cada item tiene `id`, `ado_id`, `title`, `work_item_type`, `ado_state`, `stacky_status` **y** `is_open` |
| `test_abiertas_primero` | con 1 cerrada y 1 abierta y `scope=all`, `items[0]["is_open"] is True` |
| `test_seam_de_filtro_de_proyecto_existe` | `from api.tickets import _request_project_name, _ticket_project_filter` no lanza `ImportError` (ratchet del seam) |

Para sembrar tickets, usar el patrón de sesión del repo:

```python
from db import session_scope
from models import Ticket

with session_scope() as s:
    s.add(Ticket(ado_id=9001, project="TEST", title="Issue abierta",
                 work_item_type="Issue", ado_state="Active"))
```

> Limpiar lo sembrado al final de cada test (borrar por `ado_id` en el rango 9000-9099) para no contaminar la DB compartida.

#### Comando exacto

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
& ".\.venv\Scripts\python.exe" -m pytest tests\test_plan237_incident_inbox_api.py -v
```

#### Criterio de aceptación (binario)

1. **10 tests passed, 0 failed.**
2. `Select-String -Path "backend\api\incident_inbox.py" -Pattern "getattr\(config,"` devuelve **0 líneas** (la flag se lee de la instancia, no del módulo).
3. `Select-String -Path "backend\api\__init__.py" -Pattern "incident_inbox_bp"` devuelve **exactamente 2** líneas.

#### Impacto por runtime

| Runtime | Impacto | Fallback |
|---|---|---|
| Codex CLI | ninguno | n/a |
| Claude Code CLI | ninguno | n/a |
| GitHub Copilot Pro | ninguno | n/a |

**Nota multi-proveedor:** el endpoint lee la tabla `tickets`, que es agnóstica de tracker (plan 218 F5 agregó el vocabulario canónico en `models.py:119-139`). Si el proyecto activo usa GitLab en vez de ADO, la bandeja funciona igual siempre que el sync haya poblado la tabla. **No** se agrega ninguna llamada a ADO/GitLab.

---

### F3 — Cliente HTTP: `rawGet` en `frontend/src/api/client.ts`

**Objetivo (1 frase):** agregar el gemelo de lectura de `rawPost` para poder leer el cuerpo de un 404 `feature_disabled` sin que la promesa lance.

**Valor:** cierra un gotcha real del repo — hoy `api.get` **lanza** en cualquier non-2xx (`client.ts:106-109`), así que leer `error` del body dentro de un `.then()` es código muerto. Sin `rawGet`, la bandeja no puede distinguir "feature apagada" de "backend caído".

**Trabajo del operador:** ninguno.

**Flag:** ninguna (es una utilidad aditiva; ningún caller existente cambia de comportamiento).

#### Archivo a EDITAR: `Stacky Agents/frontend/src/api/client.ts`

Insertar **inmediatamente después** de la función `rawPost`, es decir después de la línea `:86` (`}`) y antes de `:88` (`export const apiBase = BASE;`):

```ts
/**
 * Plan 237 F3 — gemelo de lectura de rawPost: fetch GET que NO lanza en 4xx/5xx
 * y devuelve el cuerpo parseado. Necesario para distinguir 404 feature_disabled
 * de un backend caido (api.get lanza en todo non-2xx, :106-109).
 */
export async function rawGet<T>(
  path: string,
  extraHeaders: Record<string, string> = {}
): Promise<RawResponse<T>> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        "X-User-Email": "dev@local",
        ...extraHeaders,
      },
    });
  } catch (e) {
    if (!isAbortError(e)) reportConnectionFailure();
    throw e; // semantica intacta: el caller ve el mismo error de red
  }
  reportOutcome(res);

  let data: T | null = null;
  let errorBody: GatewayErrorBody | null = null;

  const text = await res.text().catch(() => "");
  if (text) {
    try {
      const parsed = JSON.parse(text);
      if (res.ok) {
        data = parsed as T;
      } else {
        errorBody = parsed as GatewayErrorBody;
      }
    } catch {
      if (!res.ok) {
        errorBody = { message: text };
      }
    }
  }

  return { status: res.status, ok: res.ok, data, errorBody };
}
```

#### Tests PRIMERO (TDD)

Crear `Stacky Agents/frontend/src/api/__tests__/rawGet.test.ts` (crear la carpeta `__tests__` si no existe). Entorno **node**, sin jsdom: stubbear `fetch` con `vi.stubGlobal`, patrón exacto de `frontend/src/services/__tests__/copyService.test.ts:6-10`.

| Test | Qué verifica |
|---|---|
| `devuelve ok:true y data en 200` | fetch stub 200 con `{"ok":true,"a":1}` ⇒ `{ok:true, status:200, data:{ok:true,a:1}, errorBody:null}` |
| `devuelve ok:false y errorBody en 404` | fetch stub 404 con `{"ok":false,"error":"feature_disabled"}` ⇒ `errorBody.error === "feature_disabled"` y **no lanza** |
| `body no-JSON en error se expone como message` | 500 con texto plano `"boom"` ⇒ `errorBody.message === "boom"` |
| `body vacio en 200 deja data null` | 200 con `""` ⇒ `data === null`, `ok === true` |
| `error de red re-lanza` | fetch stub que rechaza ⇒ la promesa **rechaza** (`await expect(...).rejects.toThrow()`) |

> `connectionMonitor` se importa al tope de `client.ts`; si el test falla por ese import, stubbear el módulo con `vi.mock("../../services/connectionMonitor", () => ({ GATEWAY_DOWN_STATUSES: new Set([502,503,504]), reportConnectionSuccess: () => {}, reportConnectionFailure: () => {} }))`.

#### Comando exacto

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/api/__tests__/rawGet.test.ts
```

> **Correr SIEMPRE por archivo.** `npx vitest run` sin filtro contamina entre archivos y da falsos rojos (gotcha conocido del repo). `vitest` no está instalado global: usar `npx` desde `frontend/`.

#### Criterio de aceptación (binario)

1. **5 tests passed, 0 failed.**
2. `npx tsc --noEmit` desde `frontend/` no reporta errores **nuevos** respecto de la corrida previa al cambio (guardar la salida antes de editar para comparar).

#### Impacto por runtime

Ninguno en los 3 (utilidad de red del dashboard). Fallback: n/a.

---

### F4 — Modelo puro del frontend: `frontend/src/incidents/incidentInboxModel.ts`

**Objetivo (1 frase):** toda la lógica de orden, filtro, conteo y formato de la bandeja en funciones puras testeables sin DOM.

**Valor:** la página queda como una capa de render tonta; el comportamiento se verifica con vitest en milisegundos (el repo **no tiene** RTL ni jsdom, así que testear el componente es imposible — la lógica tiene que vivir afuera).

**Trabajo del operador:** ninguno.

**Flag:** ninguna (módulo puro).

#### Archivo a CREAR: `Stacky Agents/frontend/src/incidents/incidentInboxModel.ts`

```ts
/**
 * Plan 237 F4 — Modelo PURO de la bandeja de incidencias.
 * Sin React, sin DOM, sin fetch: testeable con vitest en entorno node
 * (el repo no tiene @testing-library/react ni jsdom instalados).
 */

export type IncidentScope = "open" | "all";

export interface IncidentInboxItem {
  id: number;
  ado_id: number;
  title: string;
  work_item_type?: string;
  ado_state?: string;
  ado_url?: string;
  assigned_to_ado?: string | null;
  stacky_status?: string;
  last_synced_at?: string;
  is_open: boolean;
}

export interface IncidentInboxCounts {
  open: number;
  closed: number;
  total: number;
}

export interface IncidentInboxResponse {
  ok: boolean;
  scope: IncidentScope;
  counts: IncidentInboxCounts;
  truncated: boolean;
  incident_types: string[];
  closed_states: string[];
  items: IncidentInboxItem[];
}

export interface IncidentInboxStatus {
  ok: boolean;
  enabled: boolean;
  incident_types: string[];
  incident_types_source: string;
  closed_states: string[];
  closed_states_source: string;
}

/** "all"/"todas" -> "all"; cualquier otra cosa -> "open". Espejo de
 *  normalize_scope() en backend/services/incident_inbox.py. */
export function parseScope(raw: string | null | undefined): IncidentScope {
  const norm = (raw ?? "").trim().toLowerCase();
  return norm === "all" || norm === "todas" ? "all" : "open";
}

/** Orden de presentacion: abiertas primero; dentro de cada grupo, la mas
 *  recientemente sincronizada primero; desempate por ado_id descendente.
 *  PURA: devuelve un array nuevo, no muta la entrada. */
export function sortIncidents(items: IncidentInboxItem[]): IncidentInboxItem[] {
  return items.slice().sort((a, b) => {
    if (a.is_open !== b.is_open) return a.is_open ? -1 : 1;
    const ta = a.last_synced_at ?? "";
    const tb = b.last_synced_at ?? "";
    if (ta !== tb) return tb.localeCompare(ta);
    return b.ado_id - a.ado_id;
  });
}

/** Filtra por scope. "all" devuelve todo. */
export function filterByScope(
  items: IncidentInboxItem[],
  scope: IncidentScope
): IncidentInboxItem[] {
  return scope === "all" ? items.slice() : items.filter((i) => i.is_open);
}

/** Busqueda case-insensitive sobre titulo, ado_id y estado. Texto vacio => todo. */
export function filterBySearch(
  items: IncidentInboxItem[],
  search: string
): IncidentInboxItem[] {
  const q = search.trim().toLowerCase();
  if (!q) return items.slice();
  return items.filter(
    (i) =>
      i.title.toLowerCase().includes(q) ||
      String(i.ado_id).includes(q) ||
      (i.ado_state ?? "").toLowerCase().includes(q)
  );
}

/** Conteo por estado del tracker, ordenado por cantidad desc y luego alfabetico.
 *  Estado vacio se reporta como "(sin estado)". */
export function countByState(
  items: IncidentInboxItem[]
): { state: string; count: number }[] {
  const map = new Map<string, number>();
  for (const i of items) {
    const key = (i.ado_state ?? "").trim() || "(sin estado)";
    map.set(key, (map.get(key) ?? 0) + 1);
  }
  return [...map.entries()]
    .map(([state, count]) => ({ state, count }))
    .sort((a, b) => (b.count - a.count) || a.state.localeCompare(b.state));
}

/** Texto para el portapapeles (se copia con copyText de services/copyService.ts).
 *  Una linea por incidencia: "#<ado_id>\t<estado>\t<titulo>\t<url>". */
export function formatIncidentsForCopy(items: IncidentInboxItem[]): string {
  return items
    .map((i) =>
      [`#${i.ado_id}`, i.ado_state ?? "", i.title, i.ado_url ?? ""].join("\t")
    )
    .join("\n");
}

/** Resumen para la cabecera: "7 abiertas de 19". */
export function summaryLabel(counts: IncidentInboxCounts): string {
  return `${counts.open} abierta${counts.open === 1 ? "" : "s"} de ${counts.total}`;
}
```

#### Tests PRIMERO (TDD)

Crear `Stacky Agents/frontend/src/incidents/incidentInboxModel.test.ts` (co-locado, como `incidentModel.test.ts` y `incidentQueue.test.ts` del mismo directorio).

| Test | Qué verifica |
|---|---|
| `parseScope` | `"all"`, `"ALL"`, `"todas"` ⇒ `"all"`; `"open"`, `null`, `undefined`, `""`, `"basura"` ⇒ `"open"` |
| `sortIncidents pone abiertas primero` | 1 cerrada + 1 abierta ⇒ `[0].is_open === true` |
| `sortIncidents ordena por fecha desc dentro del grupo` | 2 abiertas con `last_synced_at` distintos ⇒ la más nueva primero |
| `sortIncidents desempata por ado_id desc` | 2 abiertas con la misma fecha ⇒ mayor `ado_id` primero |
| `sortIncidents no muta la entrada` | el array original conserva su orden |
| `sortIncidents tolera last_synced_at ausente` | items sin la key ⇒ no lanza, orden determinista |
| `filterByScope` | `"open"` deja solo abiertas; `"all"` deja todo |
| `filterBySearch por titulo` | búsqueda parcial case-insensitive encuentra |
| `filterBySearch por ado_id` | `"1234"` encuentra la incidencia `ado_id: 1234` |
| `filterBySearch vacio devuelve todo` | `""` y `"   "` ⇒ largo original |
| `countByState agrupa y ordena` | 2 "Active" + 1 "New" ⇒ `[{state:"Active",count:2},{state:"New",count:1}]` |
| `countByState mapea estado vacio` | item sin `ado_state` ⇒ `"(sin estado)"` |
| `formatIncidentsForCopy` | 2 items ⇒ 2 líneas, cada una con 4 campos separados por tab |
| `formatIncidentsForCopy con lista vacia` | `""` |
| `summaryLabel singular y plural` | `{open:1,...}` ⇒ `"1 abierta de 3"`; `{open:2,...}` ⇒ `"2 abiertas de 3"` |

#### Comando exacto

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/incidents/incidentInboxModel.test.ts
```

#### Criterio de aceptación (binario)

1. **15 tests passed, 0 failed.**
2. `Select-String -Path "src\incidents\incidentInboxModel.ts" -Pattern "import React|document\.|window\."` devuelve **0 líneas**.

#### Impacto por runtime

Ninguno en los 3. Fallback: n/a.

---

### F5 — Namespace de API en el frontend

**Objetivo (1 frase):** exponer `IncidentInbox.status()` e `IncidentInbox.items()` usando `rawGet`, para que la UI pueda leer `feature_disabled` sin excepciones.

**Valor:** cierra el gotcha `api.get` lanza en non-2xx en el punto exacto donde importa.

**Trabajo del operador:** ninguno.

**Flag:** ninguna (wiring).

#### Archivo a EDITAR: `Stacky Agents/frontend/src/api/endpoints.ts`

1. Asegurar que `rawGet` esté importado del cliente. Buscar la línea de import de `./client` y agregar `rawGet` a la lista de nombres importados (si `rawGet` ya figura, no duplicar).
2. Agregar el namespace **al final del archivo**:

```ts
// ─── Plan 237 — Bandeja de incidencias abiertas ────────────────────────────
import type {
  IncidentInboxResponse,
  IncidentInboxStatus,
  IncidentScope,
} from "../incidents/incidentInboxModel";

export const IncidentInbox = {
  /** Nunca lanza por status: 200 siempre (enabled:false con la flag OFF). */
  status: (project?: string | null) => {
    const qs = project ? `?project=${encodeURIComponent(project)}` : "";
    return rawGet<IncidentInboxStatus>(`/api/incident-inbox/status${qs}`);
  },
  /** 404 feature_disabled llega como errorBody, NO como excepcion. */
  items: (project?: string | null, scope: IncidentScope = "open") => {
    const params = new URLSearchParams();
    if (project) params.set("project", project);
    params.set("scope", scope);
    return rawGet<IncidentInboxResponse>(
      `/api/incident-inbox/items?${params.toString()}`
    );
  },
};
```

> Si el linter del repo exige que los `import type` estén al tope del archivo, mover ese bloque de import arriba junto a los demás y dejar solo `export const IncidentInbox = {...}` al final.

#### Tests

No hay test propio de esta fase (es wiring de 15 líneas sin lógica). Se cubre indirectamente por `npx tsc --noEmit` y por el smoke de F8.

#### Criterio de aceptación (binario)

1. `npx tsc --noEmit` desde `frontend/` sin errores nuevos.
2. `Select-String -Path "src\api\endpoints.ts" -Pattern "incident-inbox"` devuelve **exactamente 2** líneas.

#### Impacto por runtime

Ninguno en los 3. Fallback: n/a.

---

### F6 — Página `IncidentInboxPage` (la vista dedicada)

**Objetivo (1 frase):** la pantalla que el operador pidió — solo incidencias, abiertas primero, con contador visible.

**Valor:** el entregable central del plan.

**Trabajo del operador:** ninguno (opt-in con default ON vía la flag de F0).

**Flag que la protege:** `STACKY_INCIDENT_INBOX_ENABLED` (la página consulta `IncidentInbox.status()` al montar; con `enabled:false` renderiza un `EmptyState` explicando que la función está apagada y cómo encenderla desde el panel de flags).

#### Archivos a CREAR (2)

**(a) `Stacky Agents/frontend/src/pages/IncidentInboxPage.tsx`**

Estructura obligatoria (pseudocódigo fiel; el implementador escribe el JSX real):

```
imports:
  React, { useMemo, useState }
  useQuery de "@tanstack/react-query"
  IncidentInbox de "../api/endpoints"
  { filterBySearch, filterByScope, sortIncidents, summaryLabel, countByState,
    formatIncidentsForCopy, parseScope, type IncidentScope,
    type IncidentInboxItem } de "../incidents/incidentInboxModel"
  { copyText } de "../services/copyService"
  { isIncidentWorkItemType, getWorkItemTypeColor, formatWorkItemTypeLabel }
      de "../utils/workItemTypeColor"     // SOLO LECTURA: no editar ese archivo
  { useWorkbench } de "../store/workbench"
  EmptyState, LoadErrorState, SkeletonList, Toast de "../components/..."
  styles de "./IncidentInboxPage.module.css"

estado local:
  scope: IncidentScope  -> inicial: parseScope(new URLSearchParams(window.location.search).get("scope"))
  search: string        -> ""
  toast: ToastState | null

datos:
  activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null)

  statusQ = useQuery({
    queryKey: ["incident-inbox-status", activeProjectName],
    queryFn: () => IncidentInbox.status(activeProjectName),
    staleTime: 5 * 60 * 1000,
  })

  itemsQ = useQuery({
    queryKey: ["incident-inbox-items", activeProjectName, scope],
    queryFn: () => IncidentInbox.items(activeProjectName, scope),
    refetchInterval: 45_000,     // mismo ritmo que el board (TicketBoard.tsx:870)
    staleTime: 22_500,
    refetchOnWindowFocus: true,
  })

render, en este orden de precedencia:
  1. statusQ cargando o itemsQ cargando        -> <SkeletonList />
  2. statusQ.data?.data?.enabled === false     -> <EmptyState> "La bandeja de
        incidencias esta apagada. Activala en Configuracion > Flags del arnes >
        Interfaz UI > 'Bandeja de incidencias abiertas'." </EmptyState>
  3. itemsQ.data?.ok === false, errorBody.error === "feature_disabled"
                                               -> mismo EmptyState del caso 2
  4. itemsQ.isError o itemsQ.data?.ok === false-> <LoadErrorState> con el
        errorBody.message si existe, y boton "Reintentar" -> itemsQ.refetch()
  5. lista vacia despues de filtrar            -> <EmptyState> "No hay
        incidencias abiertas en este proyecto." (si scope==="open") /
        "Este proyecto no tiene incidencias." (si scope==="all")
  6. caso feliz                                -> cabecera + lista

derivados (useMemo):
  raw      = itemsQ.data?.data?.items ?? []
  counts   = itemsQ.data?.data?.counts ?? {open:0, closed:0, total:0}
  visible  = sortIncidents(filterBySearch(filterByScope(raw, scope), search))
  byState  = countByState(visible)

cabecera:
  h1 "Incidencias"
  span con summaryLabel(counts)                      // "7 abiertas de 19"
  toggle de 2 botones: "Solo abiertas" | "Todas"
      -> al cambiar: setScope(next) Y actualizar la URL sin recargar:
         const url = new URL(window.location.href);
         if (next === "all") url.searchParams.set("scope", "todas");
         else url.searchParams.delete("scope");
         window.history.replaceState({}, "", url.pathname + url.search);
         // Compatible con routes.ts: parseRoute preserva query params
         // desconocidos verbatim (services/routes.ts:73-74).
  input de busqueda (value=search, onChange)
  boton "Copiar lista" -> copyText(formatIncidentsForCopy(visible)) y setToast(...)
  si itemsQ.data?.data?.truncated -> banner "Mostrando las primeras 1000
      incidencias. Afina la busqueda para ver el resto."
  chips de byState (estado + cantidad), solo informativos, sin onClick

lista (una fila por incidencia):
  - punto/badge de tipo: formatWorkItemTypeLabel(item.work_item_type); el color
    se aplica por ref+effect (NUNCA con style={{...}}), leyendo
    getWorkItemTypeColor(item.work_item_type)
  - "#<ado_id>" + titulo
  - badge de estado (item.ado_state)
  - badge "Abierta" / "Cerrada" segun item.is_open
  - si item.stacky_status === "running": indicador "agente corriendo"
    (si stacky_status falta o es desconocido, tratar como "idle")
  - asignado: item.assigned_to_ado ?? "sin asignar"
  - link "Abrir en el tracker" -> item.ado_url (target="_blank",
    rel="noopener noreferrer"); si ado_url es falsy, no renderizar el link
```

**REGLAS DURAS de este archivo (el ratchet las verifica):**

- **CERO `style={{...}}`.** El archivo es nuevo y el ratchet de deuda de UI exige alcance 0 en archivos nuevos. Para el color por tipo usar `useRef` + `useEffect` con `el.style.setProperty("--incident-type-color", color)`, o una clase CSS por tipo. **No hay excepción.**
- **CERO literales hexadecimales en el `.module.css`.** Usar `var(--...)` con los tokens que ya usan los CSS modules vecinos.
- **CERO `navigator.clipboard.writeText`.** Copiar **solo** con `copyText` de `services/copyService.ts` (lo exige `src/__tests__/copyDebtRatchet.test.ts`).
- **CERO modales ad-hoc.** Esta página no abre diálogos. Si en el futuro los necesitara, debe usar la primitiva `Dialog` de `components/ui` (lo exige `src/__tests__/adhocModalRatchet.test.ts`).

**(b) `Stacky Agents/frontend/src/pages/IncidentInboxPage.module.css`**

Clases mínimas: `.root`, `.header`, `.headerLeft`, `.headerActions`, `.title`, `.count`, `.scopeToggle`, `.scopeBtn`, `.scopeActive`, `.search`, `.copyBtn`, `.banner`, `.chips`, `.chip`, `.list`, `.row`, `.typeDot`, `.adoId`, `.rowTitle`, `.stateBadge`, `.openBadge`, `.closedBadge`, `.runningDot`, `.assignee`, `.link`.

Para `.typeDot`, el color se consume desde la custom property: `background: var(--incident-type-color, var(--color-text-muted));`.

#### Tests

**Honestidad obligatoria:** este archivo **no se puede testear con unit tests** — el repo **no tiene** `@testing-library/react` ni `jsdom` en `frontend/package.json` (verificado: solo `vitest` como devDependency, sin config de `environment`). Toda la lógica ya está probada en F4. El gate real de esta fase es:

1. `npx tsc --noEmit` (compilación).
2. Los ratchets de deuda de UI.
3. El smoke manual de F8.

**Prohibido** inventar un test de render que no puede correr.

#### Comandos exactos

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx tsc --noEmit
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx vitest run src/__tests__/copyDebtRatchet.test.ts
npx vitest run src/__tests__/adhocModalRatchet.test.ts
```

> **GOTCHA de ratchets:** `uiDebtRatchet` puede estar **rojo por deuda ajena** (archivos de otras ramas/sesiones que subieron su conteo). Antes de tocar nada, correrlo y **guardar la salida**. Al terminar, comparar: los archivos de este plan (`IncidentInboxPage.tsx`, `IncidentInboxEntryButton.tsx`, `incidentInboxModel.ts`) deben aparecer con **0**. Si el ratchet falla **solo** por archivos ajenos, el criterio de esta fase se considera cumplido y se deja constancia. **PROHIBIDO** regenerar el baseline con `UI_DEBT_REGEN=1` (aborta si cualquier archivo ajeno subió).

#### Criterio de aceptación (binario)

1. `npx tsc --noEmit` sin errores nuevos.
2. `Select-String -Path "src\pages\IncidentInboxPage.tsx" -Pattern 'style=\{\{'` devuelve **0 líneas**.
3. `Select-String -Path "src\pages\IncidentInboxPage.module.css" -Pattern "#[0-9a-fA-F]{3,8}"` devuelve **0 líneas**.
4. `Select-String -Path "src\pages\IncidentInboxPage.tsx" -Pattern "navigator.clipboard"` devuelve **0 líneas**.
5. `uiDebtRatchet` no reporta deuda **atribuible a los 3 archivos nuevos de este plan**.

#### Impacto por runtime

| Runtime | Impacto | Fallback |
|---|---|---|
| Codex CLI | ninguno | la fila muestra `stacky_status` tal cual; desconocido ⇒ "idle" |
| Claude Code CLI | ninguno | ídem |
| GitHub Copilot Pro | ninguno | ídem |

---

### F7 — Registro del tab y deep-link `/incidencias`

**Objetivo (1 frase):** que la bandeja tenga URL propia, entrada en la barra lateral (grupo "Trabajo", justo debajo de "Tickets ADO") y entrada en la paleta de comandos.

**Valor:** la vista es enlazable, compartible y alcanzable por teclado; sobrevive un F5.

**Trabajo del operador:** ninguno.

**Flag:** el tab siempre se registra; lo que decide si la **página** muestra contenido es la flag (F6, caso 2 del render). Motivo: el modelo de navegación (`shellNav.ts`) es **puro y sin fetch**; meterle una consulta de flag rompería su pureza y el test que la congela.

#### Archivos a EDITAR (5)

**(a) `Stacky Agents/frontend/src/services/routes.ts`**

- `:5-8` — agregar `"incidencias"` a la unión `Tab`:
  ```ts
  | "migrador" | "devops" | "dbcompare" | "costcenter" | "planes" | "evolution"
  | "incidencias";
  ```
- `:14-20` — agregar la ruta en `TAB_PATHS`:
  ```ts
  incidencias: "/incidencias", // Plan 237
  ```

**(b) `Stacky Agents/frontend/src/components/shell/shellNav.ts`**

- `:5-9` — agregar `"incidencias"` a la unión `ShellTab`.
- `:16-34` — agregar en `TAB_META`, inmediatamente después de la línea `tickets`:
  ```ts
  incidencias: { label: "Incidencias",   iconName: "Ambulance" },
  ```
  > **Verificar el ícono antes de escribirlo:** `Select-String -Path "src\components\shell\shellIcons.ts" -Pattern "Ambulance"`. Si no está en `ICON_BY_NAME`, agregarlo ahí importándolo de `lucide-react` (el paquete ya es dependencia). Si `Ambulance` no existiera en la versión instalada de `lucide-react`, usar `"AlertTriangle"` (verificar igual). **No dejar un `iconName` que no exista: `ICON_BY_NAME[meta.iconName]` es `undefined` y el render de `AppSidebar.tsx:34` rompe.**
- `:43` — agregar el tab al grupo "trabajo", **inmediatamente después de `"tickets"`**:
  ```ts
  { id: "trabajo", label: "Trabajo", tabs: ["team", "tickets", "incidencias", "review", "unblocker"] },
  ```
- `:62-64` — agregar `"incidencias"` a `ALWAYS_VISIBLE` (la bandeja no es una sección ocultable; no se toca `OPTIONAL_SECTIONS` ni `uiSectionsStore`).

**(c) `Stacky Agents/frontend/src/components/shell/__tests__/shellNav.test.ts`** — actualizar los tres asserts congelados:

- `ALL_TABS` (`:11-15`): agregar `"incidencias"`.
- El título del primer test: `"TAB_META cubre exactamente los 17 tabs"` ⇒ `18`.
- El test `"computeVisibleTabs: los 6 base siempre visibles"`: la lista esperada pasa de 6 a **7** elementos, agregando `"incidencias"`; actualizar también el título a `los 7 base siempre visibles`.
- El test `"cada tab aparece en exactamente un grupo (cobertura 16, sin duplicados)"`: actualizar el número del título a **17** si el comentario lo menciona; el assert compara contra `ALL_TABS`, así que se arregla solo.

**(d) `Stacky Agents/frontend/src/App.tsx`** — tres inserciones:

1. Import, junto a los demás imports de páginas:
   ```tsx
   import IncidentInboxPage from "./pages/IncidentInboxPage"; // Plan 237
   ```
2. Dentro del fragment `pages` (`:284-299`), **inmediatamente después** de la línea `{tab === "tickets"  && <TicketBoard />}` (`:287`):
   ```tsx
   {tab === "incidencias" && <IncidentInboxPage />} {/* Plan 237 */}
   ```
3. En la `<nav>` v1 (`:335-369`), **inmediatamente después** del botón de Tickets ADO que cierra en `:349`:
   ```tsx
   <button
     className={`${styles.navTab} ${tab === "incidencias" ? styles.active : ""}`}
     onClick={() => selectTab("incidencias")}
   >
     🚑 Incidencias
   </button>
   ```

> **NO tocar** la línea `<nav className={styles.nav} data-tour="nav">` (`:335`). El test `src/components/shell/__tests__/shellIntegration.test.ts:8` espera `'<nav className={styles.nav}>'` **sin** el `data-tour` y por eso **ya está rojo desde antes de este plan**. Es deuda preexistente y **está FUERA DE SCOPE**: no arreglarlo, no cambiar el markup para hacerlo pasar. Dejar constancia en el reporte final.

**(e) `Stacky Agents/frontend/src/components/commandPaletteData.ts`** — agregar la entrada en `NAV_COMMANDS` (`:59-73`), después de `nav-tickets`:

```ts
{ id: "nav-incidencias", path: "/incidencias", label: "Ir a Incidencias", icon: "🚑" },
```

#### Tests PRIMERO (TDD)

Antes de editar, correr `npx vitest run src/components/shell/__tests__/shellNav.test.ts` y confirmar que está **verde**. Después de editar `shellNav.ts` (y **antes** de tocar el test), volver a correrlo: debe estar **rojo** en los asserts de cobertura (18 vs 17). Recién entonces actualizar el test. Eso prueba que el test realmente cubre el drift.

#### Comandos exactos

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/components/shell/__tests__/shellNav.test.ts
npx vitest run src/services/__tests__/routes.test.ts
npx vitest run src/services/__tests__/routesDeepLink.test.ts
npx tsc --noEmit
```

#### Criterio de aceptación (binario)

1. `shellNav.test.ts` **verde** con 18 tabs.
2. `routes.test.ts` y `routesDeepLink.test.ts` **verdes** (no deberían requerir cambios: no congelan el largo de `TAB_PATHS`; si alguno rompiera, actualizarlo **agregando** el tab nuevo, nunca removiendo asserts).
3. `npx tsc --noEmit` sin errores nuevos.
4. `Select-String -Path "src\App.tsx" -Pattern "IncidentInboxPage"` devuelve **exactamente 2** líneas (import + render).
5. `shellIntegration.test.ts` sigue **exactamente igual de rojo que antes** (mismo test fallando, ni uno más).

#### Impacto por runtime

Ninguno en los 3. Fallback: n/a.

---

### F8 — Punto de entrada desde Tickets ADO (la única cirugía en `TicketBoard.tsx`)

**Objetivo (1 frase):** que desde el tablero de Tickets ADO se entre a la bandeja con un clic, sin alterar nada más del tablero.

**Valor:** cumple literalmente el pedido ("dentro de tickets ADO... entrar a algún apartado de incidencias") y hace la función descubrible sin explorar la barra lateral.

**Trabajo del operador:** ninguno.

**Flag que la protege:** `STACKY_INCIDENT_INBOX_ENABLED`. El botón se auto-oculta cuando la flag está OFF (consulta `IncidentInbox.status()` él mismo).

#### Archivos a CREAR (2)

**(a) `Stacky Agents/frontend/src/components/IncidentInboxEntryButton.tsx`**

Componente **autocontenido**: sin props obligatorias, sin estilos inline, con su propio CSS module. Se auto-oculta si la flag está OFF o si el status falla.

```tsx
/**
 * Plan 237 F8 — Punto de entrada a la bandeja de incidencias desde el tablero.
 * AUTOCONTENIDO a proposito: TicketBoard.tsx solo agrega el import y el
 * elemento. Cero props, cero estilos inline, CSS module propio (no se toca
 * TicketBoard.module.css, que esta disputado por otra sesion).
 */
import { useQuery } from "@tanstack/react-query";
import { IncidentInbox } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import { TAB_PATHS } from "../services/routes";
import styles from "./IncidentInboxEntryButton.module.css";

export default function IncidentInboxEntryButton() {
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);

  const statusQ = useQuery({
    queryKey: ["incident-inbox-status", activeProjectName],
    queryFn: () => IncidentInbox.status(activeProjectName),
    staleTime: 5 * 60 * 1000,
  });

  const itemsQ = useQuery({
    queryKey: ["incident-inbox-items", activeProjectName, "open"],
    queryFn: () => IncidentInbox.items(activeProjectName, "open"),
    enabled: statusQ.data?.data?.enabled === true,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  if (statusQ.data?.data?.enabled !== true) return null;

  const openCount = itemsQ.data?.data?.counts?.open ?? null;

  const go = () => {
    // Misma mecanica de navegacion que la paleta de comandos: pushState + popstate
    // (router casero, ver services/routes.ts:1-3).
    window.history.pushState({}, "", TAB_PATHS.incidencias);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  return (
    <button
      className={styles.entryBtn}
      onClick={go}
      title="Ver solo las incidencias, con las abiertas primero"
    >
      🚑 Incidencias
      {openCount !== null && openCount > 0 && (
        <span className={styles.badge} aria-label={`${openCount} incidencias abiertas`}>
          {openCount}
        </span>
      )}
    </button>
  );
}
```

> **Verificar antes de escribir `go()`:** cómo navega hoy la paleta de comandos (`Select-String -Path "src\components" -Pattern "pushState" -Recurse`). Si existe un helper compartido de navegación (p. ej. `navigateToRoute`), **usarlo en lugar de replicar `pushState` + `PopStateEvent`**. `App.tsx:171-175` escucha `popstate` y re-deriva la ruta completa, así que el fallback escrito arriba funciona; pero el helper compartido es preferible si existe.

**(b) `Stacky Agents/frontend/src/components/IncidentInboxEntryButton.module.css`**

Dos clases: `.entryBtn` y `.badge`.

**Cómo obtener el estilo sin tocar `TicketBoard.module.css`:** **leer** (no editar) `Stacky Agents/frontend/src/pages/TicketBoard.module.css`, localizar la regla `.syncBtn` y copiar sus declaraciones a `.entryBtn`, conservando **textualmente** los `var(--...)`. Si alguna declaración usa un literal hexadecimal, sustituirlo por el token `var(--...)` equivalente que ya se use en ese mismo archivo. Para `.badge`, calcar la regla `.navBadge` de `App.module.css` con el mismo criterio.

#### Archivo a EDITAR: `Stacky Agents/frontend/src/pages/TicketBoard.tsx` — **EXACTAMENTE 2 LÍNEAS**

**Línea 1 (import).** Agregar junto a los demás imports de componentes (bloque `:8-21`), por ejemplo después de la línea que importa `IncidentResolverModal` (`:21`):

```tsx
import IncidentInboxEntryButton from "../components/IncidentInboxEntryButton"; // Plan 237
```

**Línea 2 (JSX).** Dentro de `<div className={styles.headerActions}>` (abre en `:999`), insertar **inmediatamente después** del bloque del botón "Resolver incidencia" que cierra en `:1017` (`)}`) y **antes** del comentario `{/* Toggle vista */}` (`:1018`):

```tsx
          <IncidentInboxEntryButton /> {/* Plan 237 — bandeja de incidencias */}
```

**Anclaje robusto (la sesión paralela puede haber movido los números de línea):** buscar la cadena literal `{/* Toggle vista */}` en `TicketBoard.tsx` e insertar la línea **inmediatamente antes** de esa cadena. Si esa cadena no existiera, insertar como **último hijo** de `<div className={styles.headerActions}>`. **NO** reordenar, reformatear ni reindentar ninguna otra línea del archivo.

**PROHIBIDO en esta fase:**
- Tocar `TicketBoard.module.css`.
- Tocar cualquier otra parte de `TicketBoard.tsx` (filtros, `CLOSED_STATES`, `viewMode`, `filterNode`, las tarjetas, los modales).
- Tocar `SprintBoardPage.tsx`, `UnblockerPage.tsx`, `TicketGraphView.jsx`, `TicketGraphView.module.css`, `incidents/devResolverModel.ts` ni `utils/workItemTypeColor.ts` (todos con cambios sin commitear de otra sesión).

#### Tests

Sin unit test (no hay RTL/jsdom). Gate: `npx tsc --noEmit`, ratchets y el smoke de F9.

#### Comandos exactos

```powershell
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx tsc --noEmit
npx vitest run src/__tests__/uiDebtRatchet.test.ts
git diff --stat -- src/pages/TicketBoard.tsx
```

#### Criterio de aceptación (binario)

1. `git diff --stat -- src/pages/TicketBoard.tsx` muestra **exactamente 2 líneas agregadas y 0 eliminadas** (`2 insertions(+), 0 deletions(-)`), **descontando** los cambios que la sesión paralela ya tenía sin commitear (comparar contra el `git diff` capturado **antes** de empezar la fase).
2. `git status --short -- src/pages/TicketBoard.module.css` no muestra cambios nuevos atribuibles a este plan.
3. `npx tsc --noEmit` sin errores nuevos.
4. `Select-String -Path "src\components\IncidentInboxEntryButton.tsx" -Pattern 'style=\{\{'` devuelve **0 líneas**.

#### Impacto por runtime

Ninguno en los 3. Fallback: si `IncidentInbox.status()` falla (backend caído), el botón devuelve `null` y el tablero queda **idéntico a hoy**.

---

### F9 — Verificación integral y smoke manual

**Objetivo (1 frase):** probar de punta a punta que la bandeja muestra las incidencias reales del proyecto activo y que el tablero general no cambió.

**Valor:** cierra el plan sin falsos verdes.

**Trabajo del operador:** ninguno (el smoke lo hace quien implementa).

**Flag:** n/a.

#### Comandos exactos

```powershell
# Backend: los 3 archivos del plan, uno por uno (nunca la suite completa)
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
& ".\.venv\Scripts\python.exe" -m pytest tests\test_plan237_inbox_flag.py -v
& ".\.venv\Scripts\python.exe" -m pytest tests\test_plan237_incident_inbox_core.py -v
& ".\.venv\Scripts\python.exe" -m pytest tests\test_plan237_incident_inbox_api.py -v
& ".\.venv\Scripts\python.exe" -m pytest tests\test_harness_flags.py -v
& ".\.venv\Scripts\python.exe" -m compileall -q api services

# Frontend: por archivo
Set-Location "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx tsc --noEmit
npx vitest run src/incidents/incidentInboxModel.test.ts
npx vitest run src/api/__tests__/rawGet.test.ts
npx vitest run src/components/shell/__tests__/shellNav.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx vitest run src/__tests__/copyDebtRatchet.test.ts
```

#### Smoke manual (6 pasos, obligatorio)

1. Levantar backend + frontend. Abrir el tablero de Tickets ADO. **Verificar que se ve exactamente igual que antes**, salvo el botón nuevo "🚑 Incidencias" en la cabecera.
2. Clic en el botón ⇒ la URL pasa a `/incidencias` y se ve la bandeja con solo Issues/Bugs.
3. Contar las incidencias abiertas en la bandeja y cruzarlo contra `GET /api/incident-inbox/items?scope=open` en el navegador. Deben coincidir.
4. Cambiar a "Todas" ⇒ aparecen las cerradas, la URL pasa a `/incidencias?scope=todas`. **Recargar con F5** ⇒ sigue en "Todas" (deep-link).
5. "Copiar lista" ⇒ pegar en un editor y verificar una línea por incidencia con 4 campos.
6. Apagar la flag desde **Configuración > Flags del arnés > Interfaz UI > "Bandeja de incidencias abiertas"**, recargar ⇒ el botón del tablero **desaparece** y `/incidencias` muestra el `EmptyState` de función apagada. Volver a encenderla.

#### Criterio de aceptación (binario)

1. Todos los comandos de arriba en verde (salvo `shellIntegration.test.ts`, rojo preexistente y fuera de scope, y `uiDebtRatchet` si solo falla por deuda ajena documentada).
2. Los 6 pasos del smoke se cumplen tal cual están descritos.
3. Actualizar el encabezado de **este documento**: `**Estado:** IMPLEMENTADO` + fecha, con la lista de fases completadas.

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | **Conflicto con la sesión paralela** en `TicketBoard.tsx` (hoy modificado sin commitear). | Alta | Medio | La cirugía es de 2 líneas con anclaje textual (`{/* Toggle vista */}`), no por número de línea. `TicketBoard.module.css` no se toca. El botón es un componente autocontenido. |
| R2 | **Colisión con los planes 212 y 213**, que también tocan `TicketBoard.tsx`. | Media | Medio | 212 agrega un selector de modelo/effort y 213 toca los analistas: ambos operan en zonas distintas del archivo. Este plan solo inserta un hijo más en `headerActions`. Merge aditivo. |
| R3 | **Duplicado silencioso al mergear** `backend/api/__init__.py` (git no marca conflicto si dos ramas agregan la misma línea de cierre). | Media | Alto (import doble ⇒ error de blueprint) | Criterio binario en F2: `incident_inbox_bp` debe aparecer **exactamente 2 veces**. Verificar tras **cada** merge. |
| R4 | **El plan 216 aterriza y cambia el shape de `state_flow`.** | Media | Bajo | El lector trata `state_flow.closed_states` como opcional y cae al default. El test `test_state_flow_216_closed_states_tiene_precedencia_sobre_default` congela el contrato y se pone rojo con mensaje explicativo si 216 lo rompe. |
| R5 | **`_request_project_name` / `_ticket_project_filter` se renombran** en `api/tickets.py`. | Baja | Alto (la bandeja mostraría items de otros proyectos o ninguno) | Import lazy con `try/except ImportError` ⇒ respuesta 200 con `project_filter_seam_missing` (error visible, nunca mudo). Test ratchet `test_seam_de_filtro_de_proyecto_existe`. |
| R6 | **`iconName` inexistente en `ICON_BY_NAME`** ⇒ `AppSidebar.tsx:34` renderiza `undefined` y rompe la barra lateral. | Media | Alto | F7 obliga a verificar el ícono con `Select-String` **antes** de escribirlo, y da un ícono alternativo. |
| R7 | **`uiDebtRatchet` rojo por deuda ajena** confunde el criterio de aceptación. | Alta | Bajo | F6 obliga a capturar la salida del ratchet **antes** de empezar y a comparar solo los archivos de este plan. Prohibido regenerar el baseline. |
| R8 | **N+1 o consulta lenta** si un proyecto tiene miles de incidencias. | Baja | Medio | Filtro por tipo en SQL, sin `AgentExecution` ni `pipeline_summary` por fila, `LIMIT 1000` con bandera `truncated` y buscador en el cliente. |
| R9 | **El operador cree que la bandeja "actúa"** (cierra o lanza agentes). | Baja | Bajo | La vista es explícitamente de solo lectura; las acciones siguen viviendo en el tablero. El único enlace saliente abre el tracker. |
| R10 | **`shellIntegration.test.ts` rojo preexistente** se confunde con una regresión de este plan. | Alta | Bajo | Documentado en F7 y en el DoD: es deuda previa (`data-tour="nav"` en `App.tsx:335`), fuera de scope, no se arregla. |

---

## 7. Fuera de scope (explícito)

Este plan **NO** hace nada de lo siguiente. Si el implementador siente el impulso de hacerlo, **está fuera del plan**:

1. **No rediseña ni "mejora de paso" el tablero general.** Nada de cambiar el árbol, el grafo, los filtros, el orden, los colores ni la densidad de `TicketBoard.tsx`.
2. **No lanza agentes desde la bandeja.** "Resolver con agente" (plan 166 F5) y "Abrir PR" (plan 177) siguen viviendo solo en el tablero.
3. **No implementa el plan 216.** Solo declara el contrato de lectura de `state_flow.closed_states`.
4. **No agrega UI para editar `incident_inbox.incident_types` / `closed_states`** en el perfil del cliente. El lector ya las honra; la pantalla de edición es trabajo del 216.
5. **No toca el flujo de captura de incidencias** (plan 131 / 166): el modal, el store en disco y `/api/incidents/*` quedan intactos.
6. **No implementa vistas guardadas (plan 173), selección múltiple (plan 187) ni menú contextual (plan 175)** dentro de la bandeja.
7. **No arregla `shellIntegration.test.ts`** (rojo preexistente por `data-tour="nav"`).
8. **No regenera `deployment/harness_defaults.env`.**
9. **No hace `git add`, `commit`, `stash`, `reset`, `rebase` ni `checkout`.** El árbol de trabajo es compartido con una sesión paralela viva; los commits los hace el operador.
10. **No agrega paginación server-side.** El tope de 1000 con `truncated` es suficiente y está medido.

---

## 8. Glosario (términos del dominio Stacky)

| Término | Significado |
|---|---|
| **Incidencia** | En Stacky **no existe** un `work_item_type` llamado "Incidencia". Una incidencia es un work item de tipo **`Issue`** o **`Bug`** (`frontend/src/utils/workItemTypeColor.ts:34`). El plan 166 publica las incidencias como `Issue` (`backend/api/tickets.py:6886`). |
| **Work item / ticket** | Ítem del tracker (Azure DevOps o GitLab) sincronizado a la tabla local `tickets` (`backend/models.py:38`). |
| **`ado_state`** | Estado del ítem **en el tracker** ("Active", "New", "Done", ...). Distinto de `stacky_status`. |
| **`stacky_status`** | Estado **interno** de Stacky para ese ticket: `idle` / `running` / `completed` / `error` / `cancelled` (`backend/models.py:59-61`). Lo escribe el runtime al ejecutar un agente. |
| **Runtime** | Motor que ejecuta al agente: `codex_cli`, `claude_code_cli` o `copilot` (GitHub Copilot Pro). **No** es lo mismo que `LLM_BACKEND`. |
| **Flag del arnés** | Interruptor declarado en `backend/services/harness_flags.py` (`FLAG_REGISTRY`), con default efectivo en `backend/config.py`, editable por el operador desde la UI (panel de flags). |
| **Las 4 excepciones duras** | Los únicos motivos válidos para que una flag nueva nazca en OFF: (1) bypassea revisión humana, (2) es destructiva o irreversible, (3) tiene un prerequisito no garantizado, (4) reduce la seguridad. Ninguna aplica acá. |
| **Ratchet** | Test que congela una métrica de deuda (estilos inline, modales ad-hoc, escrituras al portapapeles) para que no empeore. Los de UI viven en `frontend/src/__tests__/*Ratchet.test.ts`. |
| **`HARNESS_TEST_FILES`** | Lista en `backend/scripts/run_harness_tests.sh` donde **todo** `test_*.py` nuevo debe registrarse, o un meta-test se pone rojo. |
| **Deep-link** | URL que restaura el estado de la vista (plan 165). El router es **casero**, no react-router: `frontend/src/services/routes.ts`. |
| **Seam** | Punto de acoplamiento explícito y documentado entre dos módulos, protegido por un test que falla si se rompe. |
| **HITL (human-in-the-loop)** | Principio innegociable: Stacky amplifica al operador y nunca decide por él. |

---

## 9. Orden de implementación

1. **F0** — Flag `STACKY_INCIDENT_INBOX_ENABLED` (4 archivos editados + 1 test creado + registro en `run_harness_tests.sh`).
2. **F1** — `backend/services/incident_inbox.py` (núcleo puro) + `test_plan237_incident_inbox_core.py`.
3. **F2** — `backend/api/incident_inbox.py` + registro en `backend/api/__init__.py` + `test_plan237_incident_inbox_api.py`.
4. **F3** — `rawGet` en `frontend/src/api/client.ts` + `src/api/__tests__/rawGet.test.ts`.
5. **F4** — `frontend/src/incidents/incidentInboxModel.ts` + su test co-locado.
6. **F5** — Namespace `IncidentInbox` en `frontend/src/api/endpoints.ts`.
7. **F6** — `IncidentInboxPage.tsx` + `IncidentInboxPage.module.css`.
8. **F7** — Registro del tab: `routes.ts`, `shellNav.ts`, `shellNav.test.ts`, `App.tsx`, `commandPaletteData.ts`.
9. **F8** — `IncidentInboxEntryButton.tsx` + `.module.css` + **2 líneas** en `TicketBoard.tsx`.
10. **F9** — Verificación integral + smoke manual de 6 pasos + actualización del encabezado de estado de este documento.

> **Punto de corte seguro:** después de F7 la función ya es 100% usable por barra lateral, URL y paleta de comandos. F8 es la guinda de descubribilidad y es la fase de mayor riesgo de conflicto: si la sesión paralela está muy activa sobre `TicketBoard.tsx`, **posponer F8** sin perder valor.

---

## 10. Mapa de colisiones

### Archivos con cambios SIN COMMITEAR de otra sesión (al 2026-07-25)

| Archivo | Este plan lo... | Riesgo |
|---|---|---|
| `frontend/src/pages/TicketBoard.tsx` | **edita: 2 líneas** (F8), con anclaje textual | **Medio** — también disputado por los planes 212 y 213 |
| `frontend/src/utils/workItemTypeColor.ts` | **solo importa** (no edita) | Nulo |
| `frontend/src/incidents/devResolverModel.ts` | **no toca** | Nulo |
| `frontend/src/pages/TicketBoard.module.css` | **no toca** | Nulo |
| `frontend/src/pages/SprintBoardPage.tsx` | **no toca** | Nulo |
| `frontend/src/pages/UnblockerPage.tsx` | **no toca** | Nulo |
| `frontend/src/components/TicketGraphView.jsx` / `.module.css` | **no toca** | Nulo |
| `frontend/src/utils/__tests__/workItemTypeColor.test.ts` (untracked) | **no toca** | Nulo |

### Archivos compartidos (registros) — cambios ADITIVOS

| Archivo | Cambio | Nota de merge |
|---|---|---|
| `backend/services/harness_flags.py` | +1 línea en `_CATEGORY_KEYS`, +1 bloque `FlagSpec` | Verificar **2** ocurrencias de la key tras merge |
| `backend/config.py` | +1 campo | — |
| `backend/tests/test_harness_flags.py` | +1 línea en `_CURATED_DEFAULTS_ON` | — |
| `backend/scripts/run_harness_tests.sh` | +3 líneas | — |
| `backend/api/__init__.py` | +2 líneas | **Verificar exactamente 2** ocurrencias de `incident_inbox_bp` |
| `frontend/src/api/client.ts` | +1 función `rawGet` | — |
| `frontend/src/api/endpoints.ts` | +1 namespace | Verificar **2** ocurrencias de `incident-inbox` |
| `frontend/src/App.tsx` | +3 inserciones | No tocar `<nav ... data-tour="nav">` |
| `frontend/src/services/routes.ts` | +2 líneas | — |
| `frontend/src/components/shell/shellNav.ts` | +4 líneas | — |
| `frontend/src/components/shell/shellNav.test.ts` | actualizar 3 asserts congelados | — |
| `frontend/src/components/shell/shellIcons.ts` | +1 ícono **solo si falta** | — |
| `frontend/src/components/commandPaletteData.ts` | +1 entrada | — |

### Archivos NUEVOS (colisión imposible)

- `backend/services/incident_inbox.py`
- `backend/api/incident_inbox.py`
- `backend/tests/test_plan237_inbox_flag.py`
- `backend/tests/test_plan237_incident_inbox_core.py`
- `backend/tests/test_plan237_incident_inbox_api.py`
- `frontend/src/incidents/incidentInboxModel.ts`
- `frontend/src/incidents/incidentInboxModel.test.ts`
- `frontend/src/api/__tests__/rawGet.test.ts`
- `frontend/src/pages/IncidentInboxPage.tsx`
- `frontend/src/pages/IncidentInboxPage.module.css`
- `frontend/src/components/IncidentInboxEntryButton.tsx`
- `frontend/src/components/IncidentInboxEntryButton.module.css`

**Total: 12 archivos nuevos, 13 archivos editados (12 de ellos con cambios puramente aditivos).**

---

## 11. Definición de Hecho (DoD) global

El plan está **HECHO** cuando **todas** estas afirmaciones son verificables:

- [ ] **D1** — Los 3 archivos de test backend del plan corren **por archivo** con `backend\.venv\Scripts\python.exe` (Python 3.13.5) y dan **verde**, con el output pegado en el reporte (no basta con decir "pasó").
- [ ] **D2** — `tests\test_harness_flags.py` **verde** (prueba que la flag está bien registrada y curada).
- [ ] **D3** — Los 3 archivos de test frontend del plan corren **por archivo** con `npx vitest run <ruta>` y dan **verde**.
- [ ] **D4** — `npx tsc --noEmit` desde `frontend/` no reporta **ningún error nuevo**.
- [ ] **D5** — `uiDebtRatchet`, `copyDebtRatchet` y `adhocModalRatchet` no reportan deuda **atribuible a los archivos nuevos de este plan** (0 estilos inline, 0 escrituras directas al portapapeles, 0 modales ad-hoc).
- [ ] **D6** — `git diff --stat -- "Stacky Agents/frontend/src/pages/TicketBoard.tsx"` muestra **+2 / -0** atribuibles a este plan, y `TicketBoard.module.css` sin cambios.
- [ ] **D7** — El smoke manual de 6 pasos (F9) se completó, incluido el paso de apagar y volver a encender la flag desde la UI.
- [ ] **D8** — Con la flag **OFF**: el botón del tablero desaparece, `/incidencias` muestra el `EmptyState` de función apagada, `GET /api/incident-inbox/items` devuelve 404 `feature_disabled` y el tablero general queda **idéntico a hoy**.
- [ ] **D9** — `Select-String -Path "backend\api\__init__.py" -Pattern "incident_inbox_bp"` devuelve **exactamente 2** líneas (sin duplicado de merge).
- [ ] **D10** — Ningún archivo fuera de la lista de §10 fue modificado; en particular, **ninguno** de los archivos con cambios sin commitear de la sesión paralela salvo las 2 líneas de `TicketBoard.tsx`.
- [ ] **D11** — El encabezado de este documento se actualizó a `**Estado:** IMPLEMENTADO` con la fecha y la lista de fases completadas.
- [ ] **D12** — El reporte final declara explícitamente qué quedó **rojo preexistente** (`shellIntegration.test.ts:8`, y el `uiDebtRatchet` si falla solo por deuda ajena) para que nadie lo confunda con una regresión de este plan.
- [ ] **D13** — **No** se ejecutó ningún `git add`, `commit`, `stash`, `reset`, `rebase` ni `checkout`.
