# Plan 129 — Paleta global: búsqueda profunda multi-fuente y navegación total (Ctrl+K que encuentra TODO)

**Estado:** PROPUESTO (v1, 2026-07-13)
**Dependencias duras:** ninguna. Reusa sustrato ya implementado: `CommandPalette` existente,
`doc_indexer` (DocTree), `server_registry` (Plan 91), `FLAG_REGISTRY` (HarnessFlagsPanel),
modelos `Ticket`/`AgentExecution`, patrón health-check de flags (Planes 74/87).
**Ortogonal a:** Planes 116-128 (no toca DevOps doctors, despliegues, DB compare, IA local,
tablero de planes). NO usa IA: es búsqueda determinista local.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Los nombres de archivos, símbolos, flags,
> rutas HTTP y navegaciones son LITERALES: prohibido desviarse, prohibido "mejorar" el
> alcance. Todo lo ambiguo ya fue decidido acá.

---

## 1. Objetivo + KPI

La app ya tiene una paleta de comandos (Ctrl+K, `frontend/src/components/CommandPalette.tsx`)
pero es superficial: solo navega a **6 de los 13 tabs** (`CommandPalette.tsx:85-128` vs el
type `Tab` de `App.tsx:30`), solo busca 4 tipos de entidad (tickets con cap 200, agentes,
packs, proyectos), carga TODO por adelantado al abrirse (4 fetches, `CommandPalette.tsx:51-81`)
y **no encuentra**: ejecuciones, documentos, servidores DevOps ni flags del arnés. El operador
que quiere "ir al run 4812", "abrir el doc del plan 120", "ver el servidor PF" o "prender la
flag de insights" tiene que navegar a mano por secciones y listas.

Este plan convierte la paleta en la **puerta de entrada universal de la app**:

1. **Navegación total** (sin flag, mejora invisible): comandos "Ir a…" para los 13 tabs.
2. **Búsqueda profunda multi-fuente** (flag opt-in, default OFF): un endpoint local
   `GET /api/search/global` que busca en 5 fuentes del backend — tickets, ejecuciones,
   documentos, servidores DevOps y flags del arnés — con scoring determinista (sin IA,
   sin red externa), y la paleta lo consume con debounce mostrando resultados agrupados.
3. **Deep-links receptores**: los resultados no solo llevan a la sección, sino que abren
   la entidad (run en el drawer del historial, doc en el visor, flag resaltada en Settings).

La paleta **jamás ejecuta nada**: navega y resalta. Human-in-the-loop intacto.

**KPIs (binarios, verificables por test):**

- **KPI-1 (navegación total):** la paleta ofrece exactamente 13 comandos de tipo `nav`
  (uno por tab de `App.tsx:30`). Test puro F3 lo cuenta.
- **KPI-2 (búsqueda profunda):** sobre fixtures con las 5 fuentes pobladas, `search_all`
  devuelve hits correctos de las 5 fuentes, ordenados por score determinista, con caps
  respetados y CERO campos sensibles (sin `password`). Tests F1.
- **KPI-3 (cero regresión):** con la flag OFF, `GET /api/search/global` devuelve 404,
  la paleta se comporta EXACTAMENTE como hoy (sus fetches actuales intactos), y
  `tests/test_harness_flags.py` sigue verde. Tests F0/F2/F5.

## 2. Por qué ahora / gap que cierra (evidencia)

- `CommandPalette.tsx:85-128`: solo 6 navs hardcodeados (`/`, `/tickets`, `/settings`,
  `/diagnostics`, `/pm`, `/logs`). Los tabs `review`, `unblocker`, `docs`, `memory`,
  `history`, `migrador`, `devops` — donde vive casi todo lo construido por los planes
  87-128 — **no son alcanzables por teclado**.
- `CommandPalette.tsx:57-65`: los tickets se cargan con `Tickets.list()` y `slice(0, 200)`;
  un ticket viejo no aparece nunca. Ejecuciones (`ExecutionHistoryPage`), docs (`DocsPage`),
  servidores (`server_registry`, Plan 91) y flags (`FLAG_REGISTRY`, Plan 63+) no se buscan.
- El sustrato para buscar ya existe y este plan solo lo EXPONE: `doc_indexer.build_index()`
  (`services/doc_indexer.py:312`, cache TTL 5 min), `server_registry.list_servers()`
  (`services/server_registry.py:84`, ya redacta password vía `_public`,
  `services/server_registry.py:80`), `FLAG_REGISTRY` + `read_current()`
  (`services/harness_flags.py:2903-2906`), `session_scope` (`from db import session_scope`,
  patrón de `api/executions.py:11`).
- Los planes recientes (120-128) agregan secciones y tableros nuevos; cada sección nueva
  agrava el costo de navegación. Una paleta que encuentra todo es la mejora de UX
  transversal de mayor apalancamiento con la menor complejidad: **0 dependencias nuevas,
  0 IA, 0 llamadas externas, 1 endpoint read-only**.

## 3. Principios y guardarraíles (no negociables)

1. **3 runtimes con paridad:** este plan NO toca ningún runner (Codex CLI, Claude Code CLI,
   GitHub Copilot Pro): es UI de la app + un endpoint Flask read-only. Impacto por runtime:
   idéntico en los 3 por construcción. Se declara igual fase por fase.
2. **Cero trabajo extra para el operador:** la navegación total es invisible/automática.
   La búsqueda profunda es opt-in con default OFF (1 click en HarnessFlagsPanel para
   prenderla). Sin pasos manuales nuevos, sin migraciones, backward-compatible.
3. **Human-in-the-loop:** la paleta solo navega/resalta. PROHIBIDO agregar comandos que
   lancen runs, publiquen, deployen o muten estado.
4. **Mono-operador sin auth:** el endpoint es local y read-only; no se agrega RBAC.
5. **No degradar:** fuentes con caps duros (§4.2), cada fuente aislada en try/except
   (una fuente rota degrada a lista vacía, NUNCA 500), docs reusa el cache TTL existente,
   la paleta con flag OFF no hace ni un fetch nuevo.
6. **Seguridad:** `q` cap 200 chars; servidores SOLO vía `_public` (sin password);
   test negativo explícito de no-fuga (F1, caso 9). Sin contenido de archivos en la
   respuesta (solo títulos/paths de docs).
7. **Gotcha de flags (Plan 63/81):** la FlagSpec nueva va SIN `default=` (no se agrega a
   `_CURATED_DEFAULTS_ON`); el default efectivo OFF vive en `config.py`. PROHIBIDO
   `default=False` explícito (rompe `test_default_known_only_for_curated`).

## 4. Diseño congelado

### 4.1 Flag

- **Nombre:** `STACKY_PALETTE_DEEP_SEARCH_ENABLED` (bool, group `"global"`).
- **Default:** OFF. En `config.py` con default `"false"`; en `services/harness_flags.py`
  SIN `default=` (ver §3.7).
- **Alcance del gate:** SOLO `GET /api/search/global` (404 si OFF) y el fetch remoto de la
  paleta (que primero consulta `GET /api/search/health`). La navegación total (F3a) NO
  está gateada: es estática, sin riesgo y backward-compatible.

### 4.2 Contrato del endpoint (congelado)

`GET /api/search/global?q=<str>&limit=<int>`

- `q`: requerido tras trim; si queda vacío → `200 {"ok": true, "query": "", "groups": []}`.
  Si `len(q) > 200` → `400 {"ok": false, "error": "query_too_long"}`.
- `limit`: opcional, hits por fuente; default `8`; clamp a `[1, 20]` (fuera de rango NO es
  error: se clampa).
- Flag OFF → `404 {"ok": false, "error": "palette_deep_search_disabled"}` (patrón exacto de
  `api/docs.py:263-275`).
- Respuesta 200:

```json
{
  "ok": true,
  "query": "pf",
  "groups": [
    {"kind": "ticket",    "hits": [{"kind": "ticket",    "id": "123",           "label": "T-4567 — Alta cliente PF", "hint": "Active",             "nav": "/tickets?ticket=123"}]},
    {"kind": "execution", "hits": [{"kind": "execution", "id": "4812",          "label": "Run #4812 · developer · failed", "hint": "T-4567",       "nav": "/history?execution=4812"}]},
    {"kind": "doc",       "hits": [{"kind": "doc",       "id": "docs/plan.md",  "label": "plan.md",                  "hint": "docs",               "nav": "/docs?path=docs%2Fplan.md"}]},
    {"kind": "server",    "hits": [{"kind": "server",    "id": "PF",            "label": "PF",                       "hint": "10.10.1.5",          "nav": "/devops?server=PF"}]},
    {"kind": "flag",      "hits": [{"kind": "flag",      "id": "STACKY_X",      "label": "Etiqueta de la flag",      "hint": "STACKY_X",           "nav": "/settings?flag=STACKY_X"}]}
  ]
}
```

- Orden de `groups` FIJO: `ticket`, `execution`, `doc`, `server`, `flag`. Un grupo sin hits
  se OMITE (no se manda vacío). Dentro de cada grupo, hits ordenados por `score` desc y, a
  igual score, por `id` asc (estable). El campo `score` NO se serializa.
- `GET /api/search/health` → SIEMPRE `200 {"ok": true, "flag_enabled": <bool>}` (patrón de
  `App.tsx:86-94` con `/api/migrator/health` y `/api/devops/health`).

### 4.3 Scoring determinista (congelado)

```
normalize(text) -> str:
    # minúsculas + sin acentos (NFD, descartar combining marks) + strip
    t = unicodedata.normalize("NFD", text.lower().strip())
    return "".join(ch for ch in t if not unicodedata.combining(ch))

score(query, text) -> int:
    q = normalize(query); t = normalize(text)
    si q == "": return 0
    idx = t.find(q)
    si idx >= 0: return 100 - min(idx, 50)          # substring: más temprano = mejor
    tokens = q.split()                                # multi-palabra: AND de tokens
    si len(tokens) > 1 y todos (tok in t): return 40
    return 0                                          # sin match
```

Sin fuzzy por caracteres en backend (eso queda en el filtro local del frontend, que ya
existe: `fuzzyScore`, `CommandPalette.tsx:22-40`).

### 4.4 Fuentes (congeladas)

| kind | Origen (símbolo exacto) | Universo | Campos buscados | label | hint | nav |
|---|---|---|---|---|---|---|
| `ticket` | `session_scope()` + `select(Ticket).order_by(Ticket.id.desc()).limit(500)` | últimos 500 | `title`, `str(ado_id)` | `T-{ado_id} — {title}` | `ado_state or ""` | `/tickets?ticket={id}` |
| `execution` | `session_scope()` + `select(AgentExecution).order_by(AgentExecution.id.desc()).limit(300)` | últimos 300 | `str(id)`, `agent_type`, `status` | `Run #{id} · {agent_type} · {status}` | `T-{ado_id del ticket}` si se resuelve barato, sino `""` | `/history?execution={id}` |
| `doc` | `doc_indexer.build_index()` (`doc_indexer.py:312`, respeta su cache TTL 5 min) | todos los nodos hoja del árbol | `label` del nodo, `rel_path` | `label` del nodo | carpeta padre (`rel_path` sin el filename) | `/docs?path={urllib.parse.quote(rel_path, safe='')}` |
| `server` | `server_registry.list_servers()` (`server_registry.py:84`; ya pasa por `_public`) | todos | `alias`, `host` | `alias` | `host` | `/devops?server={alias}` |
| `flag` | `harness_flags.FLAG_REGISTRY` (iterar specs como `read_current`, `harness_flags.py:2906`) | todas | `key`, `label`, `description` | `spec.label` | `spec.key` | `/settings?flag={key}` |

Notas duras:
- Para `execution`, el hint `T-{ado_id}` se resuelve con UN join/select adicional dentro del
  mismo `session_scope`; si falla o no hay ticket, hint `""`. NO hacer N+1: un solo
  `select(Ticket.id, Ticket.ado_id).where(Ticket.id.in_(ids))` para los hits ya filtrados.
- Para `doc`, aplanar el árbol con un walk iterativo (stack), tomando SOLO nodos con
  `rel_path` de archivo (los folder nodes de `_make_folder_node` se descartan). El
  implementador DEBE leer la forma real de los nodos en `doc_indexer.py:138-176`
  (`_make_node` / `_make_folder_node`) y discriminar por el campo que distingue archivo de
  carpeta en esa forma real; prohibido asumir nombres sin leerlos.
- Cada fuente COMPLETA va envuelta en `try/except Exception` → `[]` + `logger.warning`
  (usar `services.stacky_logger.logger` como en `api/docs.py`). Una fuente caída jamás
  tumba la respuesta.

### 4.5 Deep-links receptores (congelados)

| Página | Query param | Comportamiento al montar |
|---|---|---|
| `frontend/src/pages/ExecutionHistoryPage.tsx` | `execution` (int) | si está presente y existe en la lista cargada (o vía su fetch de detalle ya existente), abrir el detalle/drawer de esa ejecución; si no existe → ignorar en silencio |
| `frontend/src/pages/DocsPage.tsx` | `path` (string urlencoded) | seleccionar/abrir ese documento en el visor si el path existe en el índice; si no → ignorar en silencio |
| `frontend/src/pages/SettingsPage.tsx` | `flag` (string) | hacer scroll hasta la flag en `HarnessFlagsPanel` y resaltarla (clase CSS temporal 2 s); si no existe → ignorar |
| `frontend/src/pages/DevOpsPage.tsx` | `server` (string) | preseleccionar el servidor con ese alias en la sección de servidores; si no existe → ignorar |

Regla común: los receptores leen el param UNA vez al montar (helper compartido
`readQueryParam`, §F4), NUNCA lanzan acciones (solo selección/scroll/highlight), y ante
cualquier valor inválido degradan a no-op silencioso.

## 5. Fases

### F0 — Flag + config + health (backend)

**Objetivo:** existir la flag con default OFF y un health-check consultable por la UI.
**Valor:** gate seguro para todo lo demás; patrón idéntico a Planes 74/87.

**Archivos:**
- `Stacky Agents/backend/config.py` — agregar `STACKY_PALETTE_DEEP_SEARCH_ENABLED`
  replicando EXACTAMENTE el idiom de `STACKY_DOCS_DOCUMENTER_ENABLED` (`config.py:514-516`)
  pero con default `"false"`.
- `Stacky Agents/backend/services/harness_flags.py` — agregar al final de `FLAG_REGISTRY`:

```python
    # ── Plan 129 — Paleta global: búsqueda profunda multi-fuente ──
    FlagSpec(
        key="STACKY_PALETTE_DEEP_SEARCH_ENABLED",
        type="bool",
        label="Búsqueda profunda en la paleta (Ctrl+K)",
        description="Plan 129 — La paleta de comandos busca también ejecuciones, documentos, servidores DevOps y flags vía /api/search/global (local, sin IA). OFF = paleta actual sin cambios.",
        group="global",
        # SIN default= (no curada en _CURATED_DEFAULTS_ON; el default efectivo OFF vive en config.py — gotcha Plan 63/81).
    ),
```

- `Stacky Agents/backend/api/global_search.py` (NUEVO) — blueprint mínimo con SOLO el
  health en esta fase:

```python
from flask import Blueprint, jsonify
from config import config

bp = Blueprint("global_search", __name__, url_prefix="/search")

def _enabled() -> bool:
    return bool(getattr(config, "STACKY_PALETTE_DEEP_SEARCH_ENABLED", False))

@bp.get("/health")
def search_health():
    return jsonify({"ok": True, "flag_enabled": _enabled()})
```

- `Stacky Agents/backend/app.py` — registrar el blueprint junto a los demás (buscar el
  bloque de `register_blueprint` existente y agregar el import + registro con el MISMO
  patrón de prefijo que produce `/api/search/health`; verificar contra cómo quedan
  montados `/api/docs/*` desde `api/docs.py` cuyo `url_prefix` es `"/docs"`).

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan129_flag.py`:
1. `test_flag_conocida` — la key aparece en `read_current()`.
2. `test_flag_default_off` — sin env var, `config.STACKY_PALETTE_DEEP_SEARCH_ENABLED is False`.
3. `test_flag_no_curada` — la key NO está en `_CURATED_DEFAULTS_ON`.
4. `test_search_health_siempre_200` — GET `/api/search/health` → 200 con `flag_enabled: false`.

**Comando:** desde `Stacky Agents/backend`: `.venv\Scripts\python.exe -m pytest tests/test_plan129_flag.py -q`
(el venv real del repo es `.venv`, gotcha Plan 109).
**Criterio binario:** 4/4 verdes + `tests/test_harness_flags.py` sigue verde
(`.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q`).
**Flag:** `STACKY_PALETTE_DEEP_SEARCH_ENABLED`, default OFF.
**Runtimes:** idéntico en Codex/Claude Code/Copilot (no toca runners). Fallback: N/A.
**Trabajo del operador:** ninguno.

### F1 — Servicio `global_search` (backend, TDD)

**Objetivo:** `search_all(q, limit_per_source)` puro y determinista sobre las 5 fuentes.
**Valor:** todo el cerebro de la búsqueda, testeable sin HTTP.

**Archivos:**
- `Stacky Agents/backend/services/global_search.py` (NUEVO). Símbolos EXACTOS:
  - `normalize(text: str) -> str` — §4.3.
  - `score(query: str, text: str) -> int` — §4.3.
  - `MAX_QUERY_LEN = 200`, `TICKET_CAP = 500`, `EXECUTION_CAP = 300`,
    `DEFAULT_LIMIT = 8`, `MAX_LIMIT = 20`, `GROUP_ORDER = ("ticket", "execution", "doc", "server", "flag")`.
  - `_search_tickets(qn, limit) -> list[dict]`, `_search_executions(qn, limit)`,
    `_search_docs(qn, limit)`, `_search_servers(qn, limit)`, `_search_flags(qn, limit)` —
    cada una según §4.4; cada hit es
    `{"kind", "id", "label", "hint", "nav", "score"}` con `id` SIEMPRE str.
  - `search_all(q: str, limit_per_source: int = DEFAULT_LIMIT) -> dict` — trim, clamp de
    limit a `[1, MAX_LIMIT]`, corta cada fuente a `limit_per_source`, arma `groups` en
    `GROUP_ORDER` omitiendo vacíos, elimina el campo `score` de los hits serializados.
    Cada `_search_*` va envuelta en `try/except Exception` → `[]` + `logger.warning`.

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan129_global_search_service.py`
(usar la infraestructura de DB de tests existente del repo — mirar cómo otros tests de
`tests/` crean tickets/ejecuciones fixture y replicar ese patrón; para docs/servers/flags,
monkeypatch de `doc_indexer.build_index`, `server_registry.list_servers` y
`FLAG_REGISTRY`):
1. `test_score_substring_temprano_gana` — `score("plan", "plan.md") > score("plan", "x_plan.md")`.
2. `test_score_acentos_insensible` — `score("busqueda", "Búsqueda profunda") > 0`.
3. `test_score_multitoken_and` — `score("doctor local", "Doctor DevOps local") == 40`;
   `score("doctor zz", "Doctor DevOps local") == 0`.
4. `test_tickets_hit_shape_y_nav` — ticket fixture → hit con label `T-{ado_id} — {title}` y
   nav `/tickets?ticket={id}`.
5. `test_executions_hit_y_hint_ticket` — ejecución fixture → label `Run #{id} · {agent_type} · {status}`,
   hint `T-{ado_id}`.
6. `test_docs_solo_hojas_y_nav_urlencoded` — árbol fixture con carpeta + archivo → solo el
   archivo aparece; nav contiene el rel_path urlencoded.
7. `test_limit_y_orden_estable` — 30 matches → corta a `limit`; orden score desc, id asc.
8. `test_fuente_rota_no_tumba` — monkeypatch `_search_docs` que raise → respuesta OK sin
   grupo `doc`, los demás grupos presentes.
9. `test_servers_sin_password` — server fixture → `"password" not in json.dumps(resultado)`.
10. `test_query_vacia_groups_vacios` — `search_all("  ")` → `{"ok": True, "query": "", "groups": []}`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan129_global_search_service.py -q`
**Criterio binario:** 10/10 verdes.
**Flag:** ninguna (servicio puro; el gate vive en la API, F2).
**Runtimes:** idéntico. Fallback: N/A.
**Trabajo del operador:** ninguno.

### F2 — API `GET /api/search/global` (backend)

**Objetivo:** exponer `search_all` gateado por la flag con el contrato §4.2.
**Valor:** la búsqueda consumible por la UI (y por curl para debug).

**Archivos:**
- `Stacky Agents/backend/api/global_search.py` — agregar a `bp`:

```python
from flask import request
from services import global_search as gs

@bp.get("/global")
def search_global():
    if not _enabled():
        return jsonify({"ok": False, "error": "palette_deep_search_disabled"}), 404
    q = (request.args.get("q") or "").strip()
    if len(q) > gs.MAX_QUERY_LEN:
        return jsonify({"ok": False, "error": "query_too_long"}), 400
    try:
        limit = int(request.args.get("limit", gs.DEFAULT_LIMIT))
    except ValueError:
        limit = gs.DEFAULT_LIMIT
    return jsonify(gs.search_all(q, limit_per_source=limit))
```

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan129_global_search_api.py`
(test client Flask, patrón de los tests de API existentes; flag ON vía monkeypatch de
`config.STACKY_PALETTE_DEEP_SEARCH_ENABLED`):
1. `test_off_404` — flag OFF → 404 con `error: "palette_deep_search_disabled"`.
2. `test_on_200_shape` — flag ON + fixtures → 200, `groups` respeta `GROUP_ORDER`, hits sin
   campo `score`.
3. `test_q_larga_400` — `q` de 201 chars → 400 `query_too_long`.
4. `test_limit_clamp` — `limit=999` → cada grupo ≤ 20 hits; `limit=abc` → usa default 8.
5. `test_health_reporta_on` — flag ON → `/api/search/health` `flag_enabled: true`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan129_global_search_api.py -q`
**Criterio binario:** 5/5 verdes.
**Flag:** `STACKY_PALETTE_DEEP_SEARCH_ENABLED` (gate 404).
**Runtimes:** idéntico. Fallback: N/A.
**Trabajo del operador:** ninguno.

### F3 — Paleta: navegación total + búsqueda profunda (frontend)

**Objetivo:** (a) comandos "Ir a…" para los 13 tabs SIEMPRE; (b) con flag ON, resultados
remotos agrupados con debounce.
**Valor:** el Ctrl+K pasa de "6 destinos + 4 listas precargadas" a "toda la app".

**Archivos:**
- `Stacky Agents/frontend/src/api/endpoints.ts` — agregar (mismo estilo de los grupos
  existentes, p.ej. `Docs` en `endpoints.ts:2701`):

```ts
export const GlobalSearchApi = {
  health: () => api.get<{ ok: boolean; flag_enabled: boolean }>("/api/search/health"),
  query: (q: string, limit = 8) =>
    api.get<{ ok: boolean; query: string; groups: { kind: string; hits: { kind: string; id: string; label: string; hint: string; nav: string }[] }[] }>(
      `/api/search/global?q=${encodeURIComponent(q)}&limit=${limit}`
    ),
};
```

- `Stacky Agents/frontend/src/components/commandPaletteData.ts` (NUEVO) — funciones PURAS
  (testeables sin jsdom, patrón "tests puros" del Plan 119):
  - mover acá `fuzzyScore` desde `CommandPalette.tsx:22-40` (export) y reexportar/importar.
  - `export const NAV_COMMANDS: { id: string; path: string; label: string; icon: string }[]`
    — EXACTAMENTE 13 entradas, una por tab de `App.tsx:30`, con los paths del mapa de
    rutas de `App.tsx` (leer el objeto `tabFromPath`/mapa de paths real, p.ej.
    `history: "/history"` en `App.tsx:43`, y usar ESOS strings literales).
  - `export function mergeDeepResults(localIds: Set<string>, groups: RemoteGroup[]): Command[]`
    — aplana los grupos remotos a `Command[]` (iconos por kind: ticket 🎫, execution 🏃,
    doc 📄, server 🖥️, flag 🚩), descartando hits cuyo `kind + id` ya esté en `localIds`
    (dedup: lo local gana).
- `Stacky Agents/frontend/src/components/CommandPalette.tsx`:
  - reemplazar el bloque de navs hardcodeado (`:85-128`) por un map sobre `NAV_COMMANDS`.
  - al abrir (`useEffect` de `:51`), UNA llamada `GlobalSearchApi.health()` → estado
    `deepEnabled` (catch → `false`; con `false` NO se hace ningún fetch remoto más).
  - nuevo `useEffect` sobre `query`: si `deepEnabled && query.trim().length >= 2`,
    debounce 250 ms (setTimeout + clearTimeout) + `AbortController` (abortar el fetch
    anterior), llamar `GlobalSearchApi.query(query)` y guardar `remoteGroups`; en error →
    `[]` en silencio.
  - en `filtered` (`:169`): concatenar tras los resultados locales los de
    `mergeDeepResults(...)` manteniendo el cap visual actual (40).
  - `run` de cada comando remoto = `onNavigate(hit.nav)` (los query params los consumen
    los receptores de F4).

**Tests PRIMERO** — `Stacky Agents/frontend/src/components/__tests__/commandPaletteData.test.ts`
(vitest, funciones puras):
1. `nav_commands_cubre_los_13_tabs` — `NAV_COMMANDS.length === 13` y paths únicos no vacíos.
2. `merge_dedup_prefiere_local` — hit remoto `ticket:123` con `localIds` conteniendo
   `ticket-123` → descartado; hit nuevo → incluido con icono correcto.
3. `merge_respeta_orden_de_grupos` — el orden de salida respeta el orden de `groups`.
4. `fuzzyScore_regresion` — 3 asserts que copien el comportamiento actual (substring gana,
   orden de caracteres, sin match = 0) para blindar la mudanza.

**Comandos:** desde `Stacky Agents/frontend`:
`npx vitest run src/components/__tests__/commandPaletteData.test.ts` y `npx tsc --noEmit`.
**Criterio binario:** 4/4 vitest verdes + `tsc` con 0 errores.
**Flag:** navegación total sin flag (estática, sin riesgo); búsqueda remota gateada por el
health de `STACKY_PALETTE_DEEP_SEARCH_ENABLED`.
**Runtimes:** idéntico. Fallback: si el backend no tiene el endpoint (build viejo), el
health catch → `deepEnabled=false` → paleta actual intacta.
**Trabajo del operador:** ninguno (opt-in 1 click para la parte remota).

### F4 — Receptores de deep-links (frontend)

**Objetivo:** que el resultado abra la entidad, no solo la sección (§4.5).
**Valor:** cierra el loop "busco → estoy viendo la cosa".

**Archivos:**
- `Stacky Agents/frontend/src/utils/queryParams.ts` (NUEVO):

```ts
export function readQueryParam(name: string): string | null {
  return new URLSearchParams(window.location.search).get(name);
}
```

- `ExecutionHistoryPage.tsx`, `DocsPage.tsx`, `SettingsPage.tsx`, `DevOpsPage.tsx` — en cada
  una, UN `useEffect(() => {...}, [])` al montar que lee su param (§4.5) y ejecuta la
  selección/scroll/highlight REUSANDO el mecanismo de selección que cada página ya tiene
  (leer la página antes de tocarla; prohibido duplicar lógica de fetch). Ante param ausente
  o inválido: no-op. Para el highlight de Settings: clase CSS temporal `flagHighlight`
  (outline 2px con el acento actual del tema) removida a los 2000 ms con setTimeout.

**Tests PRIMERO** — `Stacky Agents/frontend/src/utils/__tests__/queryParams.test.ts`
(vitest; stubear `window.location.search` con `vi.stubGlobal` o asignación en jsdom si está
disponible; si el entorno no tiene jsdom, extraer `parseQueryParam(search: string, name: string)`
puro y testear ESE, dejando `readQueryParam` como wrapper de 1 línea):
1. `param_presente` — `?execution=42` → `"42"`.
2. `param_ausente_null` — `?x=1` → `null`.
3. `param_urlencoded` — `?path=docs%2Fplan.md` → `"docs/plan.md"` (decodificado por URLSearchParams).

**Comandos:** `npx vitest run src/utils/__tests__/queryParams.test.ts` y `npx tsc --noEmit`.
**Criterio binario:** 3/3 verdes + `tsc` 0 errores + verificación manual descrita en F5.
**Flag:** ninguna (los receptores son inertes sin query param; los navs con param solo los
genera la búsqueda profunda gateada).
**Runtimes:** idéntico. Fallback: sin param → páginas exactamente como hoy.
**Trabajo del operador:** ninguno.

### F5 — Verificación integral + no-regresión

**Objetivo:** demostrar KPI-1/2/3 y que nada existente se rompió.

**Pasos y comandos (todos desde el directorio indicado):**
1. Backend nuevo: `.venv\Scripts\python.exe -m pytest tests/test_plan129_flag.py tests/test_plan129_global_search_service.py tests/test_plan129_global_search_api.py -q` → todo verde.
2. No-regresión flags: `.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q` → mismo resultado que ANTES del plan (documentar en el reporte los fails preexistentes conocidos del drift `harness_defaults.env`, si siguen).
3. Frontend: `npx vitest run` (suite completa) y `npx tsc --noEmit` → 0 errores nuevos.
4. Humo manual (1 minuto, opcional pero recomendado): levantar backend+frontend, flag OFF →
   Ctrl+K se ve/actúa como siempre pero con 13 "Ir a…"; prender la flag desde
   HarnessFlagsPanel → tipear 2+ chars muestra grupos remotos; Enter en un run abre el
   historial con el detalle abierto.

**Criterio binario:** pasos 1-3 verdes (el 4 es evidencia adicional, no bloqueante).
**Trabajo del operador:** ninguno.

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| DB grande enlentece la búsqueda | caps duros (500 tickets / 300 ejecuciones, `order_by id desc` = índice PK) + limit por fuente ≤ 20 |
| Índice de docs costoso | se reusa `build_index()` con su cache TTL 5 min existente; jamás se lee contenido de archivos |
| Fuga de secretos de servidores | solo `_public` (ya redacta password) + test negativo F1.9 |
| Un origen roto tumba la paleta | try/except por fuente → grupo omitido, log warning (F1.8) |
| Regresión en la paleta actual | flag OFF = cero fetch nuevo; `fuzzyScore` blindado con test de regresión F3.4 |
| Colisión con WIP ajeno en archivos compartidos (`config.py`, `harness_flags.py`, `endpoints.ts`) | commits con staging quirúrgico por hunk (patrón Planes 109/110/111); nunca `git add -A` |
| Drift `harness_defaults.env` | NO regenerar el archivo en este plan (lección Plan 127 §3.11); la flag nueva no lo necesita (default OFF) |

## 7. Fuera de scope (explícito)

- Búsqueda semántica/TF-IDF (Planes 112/115) — este scoring es substring determinista.
- Buscar DENTRO del contenido de documentos o logs (solo títulos/paths/metadata).
- Acciones ejecutables desde la paleta (lanzar runs, publicar, deploy) — prohibido por §3.3.
- Historial de búsquedas, ranking aprendido, telemetría nueva.
- Tocar cualquier runner (Codex / Claude Code / Copilot) o `copilot_bridge`.

## 8. Glosario

- **Paleta de comandos:** modal Ctrl+K (`CommandPalette.tsx`) para navegar/buscar por teclado.
- **Tab:** sección top-level de la SPA; el type `Tab` de `App.tsx:30` enumera las 13.
- **FlagSpec / FLAG_REGISTRY:** registro declarativo de flags del arnés
  (`services/harness_flags.py`) que la UI (HarnessFlagsPanel) renderiza y edita.
- **_CURATED_DEFAULTS_ON:** set de flags cuyo default declarado es ON; una flag fuera del
  set NO debe declarar `default=` (gotcha Plan 63/81).
- **session_scope:** context manager de sesión SQLAlchemy (`from db import session_scope`).
- **doc_indexer:** servicio que indexa el árbol de documentación con cache TTL 5 min.
- **server_registry:** registro de servidores DevOps (Plan 91); `_public` redacta secretos.
- **Deep-link receptor:** página que al montar lee un query param y preselecciona la entidad.
- **Runtimes:** los 3 motores de agentes de Stacky (Codex CLI, Claude Code CLI, GitHub
  Copilot Pro); este plan no los toca.

## 9. Orden de implementación

1. F0 (flag + config + health + registro del blueprint).
2. F1 (servicio con sus 10 tests).
3. F2 (API con sus 5 tests).
4. F3 (endpoints.ts + commandPaletteData.ts + CommandPalette + 4 tests + tsc).
5. F4 (queryParams + 4 receptores + 3 tests + tsc).
6. F5 (verificación integral + no-regresión + humo manual).

## 10. Definición de Hecho (DoD)

- [ ] 19 tests nuevos verdes (4 F0 + 10 F1 + 5 F2) + 7 vitest (4 F3 + 3 F4) + `tsc` 0 errores.
- [ ] Flag OFF: `/api/search/global` → 404; paleta idéntica a hoy salvo los 13 "Ir a…".
- [ ] Flag ON (1 click en HarnessFlagsPanel): buscar 2+ chars muestra grupos de las 5 fuentes.
- [ ] Ningún hit contiene `password` ni contenido de archivos.
- [ ] `tests/test_harness_flags.py` sin fails NUEVOS respecto de la línea base.
- [ ] Ningún runner ni archivo de `copilot_bridge`/runners modificado.
- [ ] Commits con staging quirúrgico (solo hunks del plan) y push manual pendiente (regla del pipeline).
