# Plan 38 — Versión visible, Épica desde Brief (Agente de Negocio) y Trazabilidad de ejecución por ticket

> Estado: PROPUESTO. Numeración: 38 (consecutiva; máximo previo real = 37_PLAN_CLAUDE_CLI_AUTH_REAL_SIN_DEGRADAR_A_COPILOT.md). El operador pidió coloquialmente "plan 38", y 38 es efectivamente el siguiente consecutivo libre, sin huecos.
> Pensado para que un modelo menor (Haiku / Codex CLI / GitHub Copilot Pro) lo implemente SIN inferir nada.
> Las tres necesidades son independientes entre sí (bloques A, B, C). Se pueden implementar en cualquier orden, pero dentro de cada bloque las fases van en orden de dependencia.

## 1. Título, objetivo y KPI

**Objetivo.** Cerrar tres incidencias/necesidades del operador con cambios mínimos, reusando lo que ya existe:

- **Bloque A — Versión visible.** Mostrar el número de versión de Stacky Agents en la UI (TopBar), tomado de una única fuente de verdad y expuesto por el backend en `/api/health`. Sin pasos manuales.
- **Bloque B — Épica desde un Brief vía Agente de Negocio.** Un lugar en la app donde el operador pega un brief/requisito en un modal; eso lanza el `BusinessAgent` (que YA existe como rol/agente), cuya salida estructurada (Epics con bloques `RF-XXX`) se materializa como una Épica que el Analista Funcional toma y continúa por el flujo EXISTENTE (épica → análisis funcional → `pending-task.json` → tickets → ejecución). El operador nunca se reemplaza: aprueba la épica antes de que entre al flujo.
- **Bloque C — Trazabilidad de ejecución por ticket.** Por cada ejecución de ticket queda registrado, en la metadata de la ejecución, el PROMPT usado (contenido + hash), el AGENTE (`agent_type` + nombre de archivo) y la LISTA de archivos que la ejecución produjo/tocó, para diagnosticar errores. Se expone en el endpoint de ejecución y se muestra en el drawer de detalle.

**KPI / impacto.**
- KPI-A (binario): la versión visible en TopBar coincide con `VERSION.txt` del deploy (o `package.json` en dev) para el 100% de los arranques.
- KPI-B1 (operador): crear una épica desde un brief pasa de "imposible en la app" (hoy se crea en ADO a mano) a "1 modal + 1 aprobación", 0 pasos manuales nuevos en ADO.
- KPI-B2 (binario): la épica creada por el flujo es tomable por el Analista Funcional sin diferencias respecto a una épica sincronizada desde ADO (mismo `work_item_type="Epic"`, mismo `ado_id`).
- KPI-C1 (binario): para el 100% de las ejecuciones nuevas, `get_execution(id)["metadata"]` contiene `prompt_text` (o `prompt_sha` + `prompt_file`), `agent_type` y `produced_files` (lista, posiblemente vacía).
- KPI-C2 (diagnóstico): tiempo de "¿qué prompt/archivos usó esta ejecución que falló?" pasa de leer logs crudos a 1 vista en el drawer.

## 2. Por qué ahora / gap que cierra

Apoyado en los planes recientes (33 flags-UI, 36 selector-runtime, 28-32 motor/calidad):

- **Bloque A.** El plan 36 hizo el runtime visible y auditable; falta la pieza más básica de observabilidad para el operador: saber QUÉ versión está corriendo. Hoy `frontend/package.json:4` dice `0.1.0`, la versión real de deploy está en `DeployStackyAgents/VERSION.txt` (hoy `1.0.47`), y `/api/health` (`backend/api/diag.py:280`) NO devuelve versión. El TopBar (`frontend/src/components/TopBar.tsx:197`) tiene un `<span>dev@local</span>` que es el lugar natural.
- **Bloque B.** El `BusinessAgent` (type `business`) YA existe como rol runtime (`backend/agents/business.py`) y produce "Epics estructurados en HTML con bloques RF-XXX". El Analista Funcional (`backend/agents/functional.py`) YA consume una Épica y genera `pending-task.json` → tickets (`backend/api/tickets.py`). El gap es exclusivamente: (1) una entrada en la UI para pegar el brief y lanzar el agente de negocio; (2) tomar la salida del agente y materializarla como Épica real en ADO (igual que `POST /api/tickets/sync` trae épicas), para que el flujo funcional la continúe sin cambios. El operador aprueba antes de crear la épica (human-in-the-loop).
- **Bloque C.** `AgentExecution.metadata_json` YA existe y `to_dict()` lo expone (`backend/models.py:207`, `:290`); `agent_type` ya es columna. Los runners CLI ya guardan `prompt_file` + `prompt_sha`. El gap: el prompt no se persiste de forma uniforme en el path `github_copilot`, y no hay lista de archivos producidos asociada a la ejecución (hoy se resuelven dinámicamente desde disco en `backend/api/executions.py`). Esto impide diagnosticar "qué prompt/archivos usó la ejecución que falló" sin leer logs crudos.

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad:** Codex CLI, Claude Code CLI, GitHub Copilot Pro. Cada ítem funciona en los 3 o degrada con fallback EXPLÍCITO. Nada atado a un runtime.
- **Cero trabajo extra del operador:** invisible/automático u opt-in con default seguro (off). Backward-compatible. Ninguna nueva carga de config obligatoria.
- **Human-in-the-loop innegociable:** en el Bloque B el operador SIEMPRE revisa/aprueba la épica antes de que entre al flujo. Nada de autonomía proactiva.
- **Mono-operador sin auth real:** nada de RBAC ni multiusuario.
- **No degradar** performance/seguridad/estabilidad/DX. Reusar lo existente (BusinessAgent, flujo funcional, `metadata_json`, `/api/health`, `harness_flags`).
- **TDD:** test primero en cada fase con backend. Frontend: vitest NO está instalado en el repo → criterio degradado a `npm run build` (0 errores TS) + verificación manual descrita, con instalación opcional documentada.

---

# BLOQUE A — VERSIÓN VISIBLE

### A0 — Fuente de verdad única de la versión

**Objetivo (1 frase).** Definir UNA sola fuente de versión y un helper backend que la lea sin romper en frozen/dev.

**Valor.** Evita versiones divergentes (package.json vs VERSION.txt) y da un punto único para A1/A2.

**Decisión de fuente (orden de resolución, determinista):**
1. Si existe `DeployStackyAgents/VERSION.txt` (deploy real) → su contenido (primera línea, `.strip()`).
2. Si no, `frontend/package.json` → campo `"version"` (entorno dev).
3. Si no, string `"0.0.0-unknown"`.

> Razón: en deploy frozen, `VERSION.txt` es la verdad (hoy `1.0.47`); en dev local el operador corre desde el repo y `package.json` (`0.1.0`) es lo disponible.

**Archivo exacto a crear:** `backend/services/app_version.py` (nuevo).

**Símbolos exactos:** función `get_app_version() -> str` y constante module-level cache `_CACHED_VERSION`.

**Pseudocódigo:**
```python
# backend/services/app_version.py
from __future__ import annotations
import json
from pathlib import Path
from runtime_paths import backend_root, app_root  # ya existen (runtime_paths.py)

_CACHED_VERSION: str | None = None

def _read_version_txt() -> str | None:
    # VERSION.txt vive en DeployStackyAgents/ en el deploy; en dev puede no existir.
    # app_root() apunta a la raíz "Stacky Agents". Probar ambas ubicaciones conocidas.
    candidates = [
        app_root() / "DeployStackyAgents" / "VERSION.txt",
        backend_root().parent / "DeployStackyAgents" / "VERSION.txt",
    ]
    for p in candidates:
        try:
            if p.is_file():
                txt = p.read_text(encoding="utf-8").strip().splitlines()
                if txt:
                    return txt[0].strip()
        except Exception:
            continue
    return None

def _read_package_json() -> str | None:
    candidates = [
        app_root() / "frontend" / "package.json",
        backend_root().parent / "frontend" / "package.json",
    ]
    for p in candidates:
        try:
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
                v = data.get("version")
                if isinstance(v, str) and v.strip():
                    return v.strip()
        except Exception:
            continue
    return None

def get_app_version() -> str:
    global _CACHED_VERSION
    if _CACHED_VERSION is not None:
        return _CACHED_VERSION
    _CACHED_VERSION = _read_version_txt() or _read_package_json() or "0.0.0-unknown"
    return _CACHED_VERSION
```
Casos borde: archivo ausente, JSON inválido, VERSION.txt vacío → se cae al siguiente candidato; nunca lanza excepción (siempre devuelve string). Caché para no leer disco en cada request.

> Nota: confirmar las firmas reales de `app_root()` / `backend_root()` en `backend/runtime_paths.py` (mapa del repo: `runtime_paths.py` expone `is_frozen, backend_root, app_root, data_dir, projects_dir`). Si `app_root()` no existe con ese nombre exacto, usar `backend_root().parent` como base (la raíz "Stacky Agents") y eliminar el primer candidato. NO inventar funciones.

**TDD — test PRIMERO.** Archivo: `backend/tests/test_app_version.py` (nuevo).
Casos:
1. `test_version_from_version_txt`: con `tmp_path` y monkeypatch de `app_root`/`backend_root` apuntando a un dir con `DeployStackyAgents/VERSION.txt` que contiene `"1.2.3\n"` → `get_app_version() == "1.2.3"`.
2. `test_version_falls_back_to_package_json`: sin VERSION.txt, con `frontend/package.json` `{"version":"9.9.9"}` → `get_app_version() == "9.9.9"`.
3. `test_version_unknown_when_nothing`: sin ninguno → `get_app_version() == "0.0.0-unknown"`.
4. `test_version_ignores_invalid_json`: package.json corrupto → cae a `"0.0.0-unknown"` (sin excepción).

> Importante para el test: `get_app_version` cachea en `_CACHED_VERSION`. En cada test, resetear con `monkeypatch.setattr("services.app_version._CACHED_VERSION", None, raising=False)` antes de llamar.

**Comando exacto (backend, python del .venv del repo):**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_app_version.py -q
```
(PowerShell: `& ".venv\Scripts\python.exe" -m pytest tests\test_app_version.py -q`.)

**Criterio de aceptación (binario):** 4 passed.

**Flag:** ninguno (es lectura inerte). Default seguro: si todo falla, `"0.0.0-unknown"`.

**Impacto por runtime:** ninguno (no toca runners). **Trabajo del operador: ninguno.**

---

### A1 — Exponer la versión en `/api/health`

**Objetivo (1 frase).** Agregar el campo `version` al JSON que ya devuelve `/api/health`, sin cambiar lo demás.

**Valor.** El frontend obtiene la versión por un endpoint que ya existe y ya se consideraría para diagnóstico.

**Archivo exacto a editar:** `backend/api/diag.py`, función `health()` (empieza en `:281`).

**Cambio:** dentro del dict de respuesta de `health()` agregar la clave `version`:
```python
from services.app_version import get_app_version
# ... dentro de health(), donde se arma el dict final de respuesta:
result["version"] = get_app_version()
```
Ubicar el dict que hoy devuelve `health` (campos actuales: `ok`, `healthy`, `repo_root`, `outputs_dir`, `active_project`, `ado_pat_present`, `auto_create_tasks_enabled`, `watchers`, `warnings`) y añadir `version` a ese mismo dict antes del `return`. No remover ni renombrar campos existentes (backward-compatible).

**TDD — test PRIMERO.** Archivo: `backend/tests/test_health_version.py` (nuevo).
Casos:
1. `test_health_includes_version`: con `app.test_client()` (fixture existente, ver otros tests de `backend/tests/` que golpean endpoints), GET `/api/health` → status 200 y `resp.json["version"]` es un string no vacío.
2. `test_health_version_matches_helper`: monkeypatch `diag.get_app_version` (o `services.app_version.get_app_version`) para devolver `"7.7.7"` → `resp.json["version"] == "7.7.7"`.
3. `test_health_other_fields_unchanged`: el JSON sigue conteniendo `ok` y `warnings` (no se rompió el contrato existente).

**Comando exacto:**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_health_version.py -q
```

**Criterio de aceptación (binario):** 3 passed.

**Flag:** ninguno (campo aditivo de solo lectura). **Trabajo del operador: ninguno.**

**Impacto por runtime:** ninguno.

---

### A2 — Mostrar la versión en el TopBar (frontend)

**Objetivo (1 frase).** Renderizar la versión en el TopBar, junto a `dev@local`, leyéndola de `/api/health`.

**Valor.** El operador ve de un vistazo qué versión corre. Cierra KPI-A.

**Archivos exactos:**
- `frontend/src/api/endpoints.ts` — agregar un cliente `Health.get()` que haga `GET /api/health`.
- `frontend/src/components/TopBar.tsx` — consumir y renderizar la versión.
- `frontend/src/components/TopBar.module.css` — clase `.version` (estilo discreto).

**Cambio 1 — cliente en `endpoints.ts`.** Junto a los demás clientes (existe `LocalDiagnostics` en `endpoints.ts:2273`), agregar:
```ts
export const Health = {
  get: () => api.get<{ version?: string; ok?: boolean }>("/api/health"),
};
```
Usar el mismo helper `api`/fetch wrapper que usan los otros clientes del archivo (no inventar un cliente HTTP nuevo; copiar el patrón de `LocalDiagnostics`).

**Cambio 2 — TopBar.** En `frontend/src/components/TopBar.tsx`:
- Importar `Health` desde `../api/endpoints` y `useEffect`/`useState` de React (probablemente ya importados).
- Agregar estado `const [version, setVersion] = useState<string | null>(null);`
- En un `useEffect(() => { Health.get().then(r => setVersion(r.version ?? null)).catch(() => setVersion(null)); }, []);`
- Reemplazar el `<span>dev@local</span>` (línea 197) por:
```tsx
<span className={styles.version} title="Versión de Stacky Agents">
  {version ? `v${version}` : "dev@local"}
</span>
```
Caso borde: si `/api/health` falla o no trae versión, se muestra `dev@local` (comportamiento actual, sin romper). Nunca crashea el TopBar.

**Cambio 3 — CSS.** En `TopBar.module.css`, agregar `.version { font-size: 12px; opacity: .65; }` (copiar el patrón del estilo del span actual si lo tiene).

**TDD — vitest no instalado → criterio degradado.**
- Obligatorio: `cd "Stacky Agents/frontend" && npm run build` termina con 0 errores TS.
- Verificación manual: con backend corriendo, abrir Stacky → el TopBar muestra `v1.0.47` (o la versión vigente). Detener backend / forzar fallo → muestra `dev@local` (fallback).
- Opcional (no bloqueante): instalar vitest (`npm i -D vitest @testing-library/react jsdom`) y testear que con mock de `Health.get` resolviendo `{version:"1.2.3"}` el TopBar renderiza `v1.2.3`.

**Criterio de aceptación (binario):** `npm run build` 0 errores TS + verificación manual (muestra versión real con backend up; `dev@local` con backend down).

**Flag:** ninguno (UI informativa). **Trabajo del operador: ninguno.**

**Impacto por runtime:** ninguno (no toca ejecución de agentes).

---

# BLOQUE B — ÉPICA DESDE UN BRIEF (AGENTE DE NEGOCIO)

> Concepto clave verificado: el `BusinessAgent` (type `business`) YA existe (`backend/agents/business.py`) y produce "Epics estructurados en HTML con bloques RF-XXX". El Analista Funcional (`backend/agents/functional.py`) YA toma una Épica (`work_item_type="Epic"`) y genera `pending-task.json` → tickets vía `backend/api/tickets.py`. Este bloque NO crea un agente nuevo ni un flujo nuevo: agrega la ENTRADA (brief → modal → business agent) y la SALIDA (HTML del agente → Épica real en ADO, con aprobación del operador), enchufándose al flujo funcional existente.

### B0 — Endpoint backend: crear Épica desde el resultado del Agente de Negocio

**Objetivo (1 frase).** Un endpoint que recibe el HTML/estructura producida por el BusinessAgent (más el brief original) y crea una Épica real en ADO (igual que una épica sincronizada), devolviendo su `ado_id`, SOLO cuando el operador confirma.

**Valor.** Materializa la épica en el mismo formato que el flujo funcional ya sabe consumir. Sin esto, la salida del business agent es solo un HTML suelto.

**Archivo exacto a editar:** `backend/api/tickets.py` (mismo blueprint `bp` donde vive `agent_completion` en `:1177` y `sync` en `:502`).

**Símbolo exacto:** nueva ruta `@bp.post("/epics/from-brief")` → función `create_epic_from_brief()`.

**Contrato de entrada (JSON body):**
```
{
  "title": str,                # título de la épica (lo propone el operador o se deriva del brief)
  "description_html": str,     # HTML estructurado producido por el BusinessAgent (bloques RF-XXX)
  "brief": str,                # texto original del brief (se guarda como trazabilidad)
  "project_name": str | null,  # proyecto activo
  "confirm": true              # OBLIGATORIO: el operador confirmó la creación (human-in-the-loop)
}
```

**Contrato de salida (JSON):**
```
{ "ado_id": int, "work_item_type": "Epic", "title": str, "url": str | null }
```

**Pseudocódigo / pasos:**
```python
@bp.post("/epics/from-brief")
def create_epic_from_brief():
    payload = request.get_json(force=True) or {}
    if payload.get("confirm") is not True:
        return jsonify({"error": "confirmation_required"}), 400  # human-in-the-loop duro
    title = (payload.get("title") or "").strip()
    description_html = payload.get("description_html") or ""
    if not title:
        return jsonify({"error": "title_required"}), 400
    if not description_html.strip():
        return jsonify({"error": "description_required"}), 400

    project_name = payload.get("project_name")
    # 1) Crear el work item Epic en ADO reusando el cliente ADO existente.
    #    Buscar en backend/services/ el módulo que ya CREA work items en ADO
    #    (grep "create_work_item" / "POST" / "wit/workitems" en services/ado_*.py;
    #     candidatos: services/ado_publisher.py, services/ado_client.py,
    #     services/ado_write_outbox.py). USAR esa función; NO escribir un cliente ADO nuevo.
    #    La creación de Tasks hijas desde pending-task.json ya existe
    #    (tickets.py:3508 create-child-task) → seguir EXACTAMENTE ese patrón de
    #    autenticación/PAT/proyecto, pero con work_item_type="Epic" y sin parent.
    epic = ado_create_work_item(
        work_item_type="Epic",
        title=title,
        description_html=description_html,
        project_name=project_name,
    )
    ado_id = epic["id"]

    # 2) Sincronizar/persistir el ticket localmente para que aparezca en el board,
    #    igual que /api/tickets/sync. Reusar la misma capa de upsert de Ticket.
    #    (grep en tickets.py por la función que hace upsert de Ticket tras sync.)
    upsert_ticket_from_ado(epic, project_name=project_name)

    # 3) Trazabilidad: guardar el brief original asociado a la épica.
    #    Mínimo viable: escribir el brief en Agentes/outputs/epic-<ado_id>/brief.txt
    #    (misma convención de carpeta que usa el Analista Funcional:
    #     tickets.py:2166 _scan_pending_tasks_for_epic busca epic-{ado_id}/...).
    _write_epic_brief_file(ado_id, payload.get("brief") or "", project_name=project_name)

    return jsonify({
        "ado_id": ado_id, "work_item_type": "Epic",
        "title": title, "url": epic.get("url"),
    }), 201
```
Casos borde: `confirm != true` → 400 `confirmation_required` (NUNCA crea sin confirmación). Falta título o descripción → 400. Error de ADO (sin PAT, sin proyecto) → propagar como 502/500 con mensaje claro (reusar el manejo de error de `create-child-task`). NO crear la épica si ADO falla (atomicidad mínima: si paso 1 falla, no se persiste local).

> Punto crítico para el implementador: la función exacta que crea work items en ADO debe localizarse con grep antes de codificar (`grep -n "work_item_type\|wit/workitems\|create_work_item\|_post_work_item" backend/services/ado_*.py backend/api/tickets.py`). El patrón ya está en `create-child-task` (tickets.py:3508) que crea Tasks; replicarlo con `work_item_type="Epic"` y sin `parent_link_type`. PROHIBIDO inventar endpoints ADO nuevos.

**TDD — test PRIMERO.** Archivo: `backend/tests/test_epic_from_brief.py` (nuevo).
Casos (monkeypatch del creador ADO para NO golpear ADO real; usar el patrón de stub de otros tests de tickets):
1. `test_create_epic_requires_confirm`: POST sin `confirm: true` → 400 `confirmation_required`, y el creador ADO NO fue llamado.
2. `test_create_epic_requires_title`: `confirm:true` pero `title:""` → 400 `title_required`.
3. `test_create_epic_requires_description`: `confirm:true`, title ok, `description_html:""` → 400 `description_required`.
4. `test_create_epic_happy_path`: con stub del creador ADO devolviendo `{"id": 1234, "url": "..."}` → status 201, `resp.json["ado_id"] == 1234`, `resp.json["work_item_type"] == "Epic"`, y el creador recibió `work_item_type="Epic"` y el `title`/`description_html` enviados.
5. `test_create_epic_ado_failure_no_persist`: el stub lanza excepción → respuesta de error (>=500) y `upsert_ticket_from_ado` NO fue llamado.

**Comando exacto:**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_epic_from_brief.py -q
```

**Criterio de aceptación (binario):** 5 passed.

**Flag:** `STACKY_EPIC_FROM_BRIEF_ENABLED` (env var en `backend/config.py`). Default seguro: `"true"` (es opt-in por uso: si el operador no abre el modal, no pasa nada; pero la ruta existe). Documentar en `.env.example`:
```
# Plan 38 — habilita el endpoint POST /api/tickets/epics/from-brief (crear Épica
# desde un brief vía Agente de Negocio). Si false, el endpoint responde 404/403.
STACKY_EPIC_FROM_BRIEF_ENABLED=true
```
Implementar la guarda al inicio de `create_epic_from_brief`: si el flag está off → `return jsonify({"error":"feature_disabled"}), 404`.

**Impacto por runtime:** ninguno directo (la creación de la épica es una operación ADO independiente del runtime de ejecución). El runtime entra después, cuando el Analista Funcional y los developers ejecutan, y eso ya respeta el selector del plan 36.

**Trabajo del operador:** opt-in por uso; abre el modal solo si quiere crear una épica desde un brief. Cero pasos manuales nuevos en el flujo existente.

---

### B1 — Bundlear el `.agent.md` del Agente de Negocio (paridad 3 runtimes)

**Objetivo (1 frase).** Garantizar que el Agente de Negocio exista como `.agent.md` bundled en `backend/Stacky/agents/`, para que sea lanzable en los 3 runtimes (Codex/Claude/Copilot) igual que los otros roles.

**Valor.** Hoy el BusinessAgent existe como clase Python (runtime interno/github_copilot) pero el subagente Haiku confirmó que NO hay `.agent.md` bundled. Los runners CLI (Codex/Claude) lanzan por `vscode_agent_filename` (un `.agent.md`). Sin el archivo, el agente de negocio no tendría paridad en los runtimes CLI.

**Archivo exacto a crear:** `backend/Stacky/agents/BusinessAgent.agent.md` (nuevo). Seguir el formato EXACTO de `backend/Stacky/agents/FunctionalAnalyst.agent.md` (frontmatter YAML con: `description`, `tools`, `version`, `stacky_agent_type`, `stacky_completion_contract`, `stacky_requires_client_profile`, `stacky_human_gate_mode_a`, `stacky_human_gate_mode_b`).

**Contenido (frontmatter + cuerpo):**
- `stacky_agent_type: business` (coincide con `BusinessAgent.type` en `backend/agents/business.py:5`).
- `stacky_completion_contract: v1`.
- `stacky_requires_client_profile: false` (un brief no requiere perfil de cliente).
- El cuerpo del prompt: copiar/adaptar `BusinessAgent.system_prompt()` (`backend/agents/business.py:19-25`): "Sos el Agente de Negocio. Recibís texto libre del cliente y devolvés un Epic estructurado en HTML, separando los requerimientos en bloques `RF-XXX` con `<hr><h2>`...". Agregar la misma regla crítica de NO tocar ADO que tiene el FunctionalAnalyst (`functional.py:25-27`), porque la creación de la Épica en ADO la hace Stacky (B0), no el agente.

> Verificación previa obligatoria: leer las primeras ~10 líneas de `backend/Stacky/agents/FunctionalAnalyst.agent.md` y copiar su esquema de frontmatter EXACTO (campos y orden). NO inventar campos. Confirmar el valor exacto de `tools:` que usan los otros agentes y reusar el mismo set.

**TDD — test PRIMERO.** Archivo: `backend/tests/test_business_agent_bundled.py` (nuevo).
Casos:
1. `test_business_agent_md_exists`: el archivo `backend/Stacky/agents/BusinessAgent.agent.md` existe.
2. `test_business_agent_listed`: `list_agents()` (o el endpoint `GET /api/agents`) incluye un agente con `stacky_agent_type == "business"` (o `type=="business"`). Usar la función real de listado (`backend/api/agents.py:list_agents_route` → `agents.list_agents()`).
3. `test_business_agent_frontmatter_valid`: el frontmatter parsea y contiene `stacky_agent_type: business` y `stacky_completion_contract`.

**Comando exacto:**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_business_agent_bundled.py -q
```

**Criterio de aceptación (binario):** 3 passed.

**Flag:** ninguno (es un recurso bundled; si el operador no lo usa, no afecta). **Trabajo del operador: ninguno.**

**Impacto por runtime:**
- Codex CLI / Claude Code CLI: ahora pueden lanzar el agente de negocio por `vscode_agent_filename="BusinessAgent.agent.md"` (paridad).
- GitHub Copilot: ya funcionaba vía la clase Python; el `.agent.md` no rompe nada.
- Fallback: si un runtime CLI no tiene el binario listo, el operador ve el error de ejecución estándar (no fallback silencioso), igual que cualquier otro agente.

---

### B2 — Modal "Crear Épica desde Brief" (frontend) + lanzar Agente de Negocio + aprobar

**Objetivo (1 frase).** Un botón "Nueva Épica desde brief" que abre un modal donde el operador pega el brief, lanza el Agente de Negocio, ve el Epic estructurado propuesto y, tras aprobarlo, llama a `POST /api/tickets/epics/from-brief` para materializarlo.

**Valor.** Cierra KPI-B1/B2. El operador crea épicas sin salir de Stacky, con aprobación explícita.

**Archivos exactos:**
- `frontend/src/components/EpicFromBriefModal.tsx` (nuevo) — el modal.
- `frontend/src/components/EpicFromBriefModal.module.css` (nuevo).
- `frontend/src/pages/TicketBoard.tsx` (editar) — agregar el botón que abre el modal (junto al manejo de épicas; `EpicGroup` está en `TicketBoard.tsx:252`).
- `frontend/src/api/endpoints.ts` (editar) — agregar `Tickets.createEpicFromBrief(body)`.

**Patrón a reusar:** copiar la estructura de modal de `frontend/src/components/AgentLaunchModal.tsx` (overlay, header, body, botones, manejo de estado). NO inventar un sistema de modal nuevo.

**Flujo del modal (estados):**
1. **Brief.** Textarea grande para pegar el brief + input de título (opcional, autocompletable). Botón "Generar épica con Agente de Negocio".
2. **Generando.** Lanza el BusinessAgent reusando el mismo mecanismo de lanzamiento existente. Dos caminos posibles según lo que el repo ya soporte:
   - Camino preferido (reusa flujo existente): llamar al endpoint que lanza agentes con el brief como contexto. El BusinessAgent produce HTML. Recuperar ese HTML del resultado de la ejecución (la ejecución expone `output`/`html_output_path` en `get_execution`).
   - Camino mínimo (si lanzar+esperar resultado en línea es complejo): permitir que el operador pegue/edite el HTML del Epic estructurado directamente (el agente puede haberse corrido aparte). El modal igual exige revisión humana.
3. **Revisar.** Muestra el `description_html` propuesto (render o textarea editable) + el título. El operador puede editar. Checkbox/acción explícita "Aprobar y crear épica".
4. **Crear.** Al aprobar, `Tickets.createEpicFromBrief({ title, description_html, brief, project_name, confirm: true })`. Al 201, cerrar modal y refrescar el board (la nueva épica aparece como cualquier otra).

**Cambio en `endpoints.ts`:**
```ts
// dentro del objeto Tickets existente
createEpicFromBrief: (body: {
  title: string; description_html: string; brief: string;
  project_name?: string | null; confirm: true;
}) => api.post<{ ado_id: number; work_item_type: string; title: string; url: string | null }>(
  "/api/tickets/epics/from-brief", body),
```

**Cambio en `TicketBoard.tsx`:** agregar un botón en la cabecera del board (cerca de donde se listan las épicas) `+ Épica desde brief` que setea `epicModalOpen=true`; render condicional `{epicModalOpen && <EpicFromBriefModal onClose={...} onCreated={() => { setEpicModalOpen(false); /* refrescar tickets */ }} />}`.

**Human-in-the-loop (obligatorio en UI):** el botón "Crear épica" SOLO se habilita tras una acción explícita de aprobación del operador (checkbox "Revisé y apruebo" o paso "Revisar" separado). El modal nunca crea la épica automáticamente al generar el HTML. El `confirm: true` solo se manda tras esa aprobación.

**TDD — vitest no instalado → criterio degradado.**
- Obligatorio: `cd "Stacky Agents/frontend" && npm run build` 0 errores TS.
- Verificación manual:
  1. Abrir TicketBoard → botón "Épica desde brief" visible.
  2. Pegar un brief → generar → ver HTML propuesto.
  3. Sin aprobar, el botón "Crear épica" está deshabilitado.
  4. Aprobar → crear → la épica aparece en el board con su `ado_id`.
  5. El Analista Funcional puede lanzarse sobre esa épica (mismo modal/flujo de siempre) y produce `pending-task.json`.

**Criterio de aceptación (binario):** `npm run build` 0 errores TS + las 5 verificaciones manuales OK.

**Flag:** reusa `STACKY_EPIC_FROM_BRIEF_ENABLED` (B0). En frontend, ocultar el botón si una llamada a `/api/health` o config indica que la feature está off (mínimo: si el endpoint devuelve 404, el modal muestra "feature deshabilitada"). Default seguro: visible (flag default true).

**Impacto por runtime:** el lanzamiento del BusinessAgent respeta el selector de runtime del plan 36 (Codex/Claude/Copilot). Fallback: si el runtime CLI elegido no está listo, el operador ve el error estándar; puede pegar/editar el HTML manualmente (camino mínimo). La creación de la épica (B0) es independiente del runtime.

**Trabajo del operador:** opt-in por uso; cero pasos nuevos en el flujo que ya usa.

---

# BLOQUE C — TRAZABILIDAD DE EJECUCIÓN POR TICKET

> Verificado: `AgentExecution.metadata_json` YA existe (`models.py:207`) y `to_dict()` expone `metadata` (`models.py:290`). `agent_type` ya es columna. Los runners CLI ya guardan `prompt_file` + `prompt_sha`. Este bloque persiste de forma UNIFORME (3 runtimes) el prompt, el agente y la lista de archivos producidos en `metadata`, y lo muestra en el drawer. NO se agregan columnas nuevas: todo va en `metadata_json` (backward-compatible).

### C0 — Persistir prompt + agente + archivos en la metadata (path github_copilot)

**Objetivo (1 frase).** En el runner estándar (`github_copilot`), al ejecutar un agente, escribir en la metadata de la ejecución: el prompt final (texto + sha + nombre de agente) y la lista de archivos producidos.

**Valor.** Cierra KPI-C1 para el path que hoy NO persiste prompt. Diagnóstico directo de "qué se le pidió al agente".

**Archivo exacto a editar:** `backend/agent_runner.py` (rama estándar `github_copilot`, donde se llama `agent.run(...)` — el subagente lo ubicó alrededor de `:776`; la metadata final del run normal se escribe alrededor de `:802-814`).

**Dónde sale el prompt (verificado):** en `backend/agents/base.py`, dentro de `run()`:
- `system_prompt, sp_meta = self.compose_system_prompt(ctx)` (`base.py:202`).
- `prompt = self.build_prompt(context_blocks, delta_prefix=ctx.delta_prefix)` (`base.py:210`).
El agente ya conoce ambos. Hay que hacerlos llegar a la metadata de la ejecución.

**Cambio (2 sub-pasos):**

**C0.a — exponer el prompt desde `agent.run()`.** En `backend/agents/base.py`, `run()` devuelve un resultado (objeto/dict con `.metadata`). Agregar a `result.metadata` (sin romper lo existente) las claves:
```python
# dentro de run(), tras construir prompt y system_prompt:
result_metadata.setdefault("prompt_text", prompt)             # user prompt final
result_metadata.setdefault("system_prompt_text", system_prompt)
result_metadata.setdefault("prompt_sha", _sha256(prompt))     # reusar helper de sha si existe
result_metadata.setdefault("agent_type", self.type)
result_metadata.setdefault("agent_name", self.name)
```
Usar `setdefault` (no reescribir si ya estaba). Si ya existe un helper de SHA en el repo (los CLI runners calculan `prompt_sha`), reusarlo; si no, `hashlib.sha256(prompt.encode("utf-8")).hexdigest()`.

> Caso borde (privacidad): `prompt_text` puede contener datos del ticket. El repo ya tiene enmascarado PII (`metadata["pii_masked"]` aparece en `agent_runner.py`). Guardar `prompt_text` SOLO si el flag `STACKY_TRACE_PROMPT_TEXT_ENABLED` está on (default off, ver flag abajo); si está off, guardar solo `prompt_sha` + `prompt_len`. Esto evita persistir texto sensible por defecto.

**C0.b — persistir en la metadata de la ejecución.** En `agent_runner.py`, donde se arma la metadata final del run normal (`:802-814`), fusionar las claves del `result.metadata` (prompt_sha, agent_type, agent_name, y prompt_text/system_prompt_text si el flag lo permite) al `md` que se escribe en `exec_row.metadata_dict`.

**C0.c — archivos producidos.** Tras el run, calcular la lista de archivos producidos reusando la resolución que YA existe (`backend/api/executions.py:list_output_files()` / `_resolve_ticket_output_dir_ws1()` en `:368`). Extraer esa lógica a un helper reutilizable o llamarla desde el runner para snapshot:
```python
md["produced_files"] = list_output_files_for_ticket(ticket_id, exec_row)  # rutas relativas
```
Si la resolución de archivos es costosa o no determinista al momento del cierre, guardar al menos `md["ticket_output_dir"]` (los CLI runners ya lo hacen, `claude_code_cli_runner.py:987`) y dejar `produced_files` como lista mejor-esfuerzo (puede quedar vacía). KPI-C1 acepta lista vacía siempre que la clave exista.

**TDD — test PRIMERO.** Archivo: `backend/tests/test_execution_trace_metadata.py` (nuevo).
Casos (stub del agente/runner para no llamar LLM real; usar patrón de mocks de `test_claude_code_cli_phase1.py` o de otros tests de agent_runner):
1. `test_trace_records_prompt_sha_and_agent`: ejecutar un agente (github_copilot, stub) → `metadata["prompt_sha"]` no vacío, `metadata["agent_type"]` == el tipo, `metadata["agent_name"]` presente.
2. `test_trace_prompt_text_off_by_default`: con `STACKY_TRACE_PROMPT_TEXT_ENABLED` ausente/false → `"prompt_text"` NO está en metadata, pero `"prompt_sha"` y `"prompt_len"` sí.
3. `test_trace_prompt_text_on_when_flagged`: con el flag on → `metadata["prompt_text"]` == el prompt construido.
4. `test_trace_records_produced_files_key`: metadata contiene la clave `"produced_files"` (lista, posiblemente vacía).
5. `test_trace_does_not_overwrite_runtime`: la metadata sigue conteniendo `metadata["runtime"]` (no se pisó lo del plan 36).

**Comando exacto:**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_execution_trace_metadata.py -q
```

**Criterio de aceptación (binario):** 5 passed.

**Flag:** `STACKY_EXECUTION_TRACE_ENABLED` (env, `config.py`), default seguro `"true"` (guardar sha + agent + files es barato y no sensible). Y `STACKY_TRACE_PROMPT_TEXT_ENABLED` (env, `config.py`), default seguro `"false"` (el TEXTO del prompt es opt-in por privacidad). Documentar ambos en `.env.example`:
```
# Plan 38 — trazabilidad de ejecución: guarda prompt_sha, agent y archivos en metadata.
STACKY_EXECUTION_TRACE_ENABLED=true
# Plan 38 — guarda el TEXTO completo del prompt en metadata (puede contener datos del
# ticket). Default off por privacidad; activar solo para diagnóstico profundo.
STACKY_TRACE_PROMPT_TEXT_ENABLED=false
```
Si `STACKY_EXECUTION_TRACE_ENABLED` está off, no se agregan estas claves (comportamiento idéntico a hoy).

**Impacto por runtime:** este cambio cubre el path `github_copilot`. Codex/Claude CLI ya guardan `prompt_file`+`prompt_sha`; C1 los unifica.

**Trabajo del operador:** ninguno (automático; el texto del prompt es opt-in con default off).

---

### C1 — Uniformar trazabilidad en los runners CLI (Codex / Claude)

**Objetivo (1 frase).** Asegurar que los runners CLI escriban las MISMAS claves de trazabilidad que C0 (`agent_type`, `agent_name`, `prompt_sha`, `produced_files`, y `prompt_text` si el flag), para que el diagnóstico sea idéntico en los 3 runtimes.

**Valor.** Paridad de diagnóstico. Hoy `claude_code_cli_runner.py:962/979` ya guarda `prompt_file` y `prompt_sha`; falta `agent_name`, `produced_files` uniforme y `prompt_text` (gated).

**Archivos exactos:**
- `backend/services/claude_code_cli_runner.py` (donde escribe metadata, `:953-1022`).
- `backend/services/codex_cli_runner.py` (su equivalente de escritura de metadata — grep `metadata[` en ese archivo).

**Cambio (idempotente, defensivo) en ambos runners, donde arman la metadata final:**
```python
md.setdefault("agent_type", agent_type)
md.setdefault("agent_name", _agent_display_name)  # si está disponible; si no, agent_type
md.setdefault("prompt_sha", prompt_sha)           # ya existe en claude runner
# prompt_text solo si el flag global lo permite:
if config.STACKY_TRACE_PROMPT_TEXT_ENABLED:
    md.setdefault("prompt_text", prompt)          # el runner ya tiene `prompt` (claude:494-506)
md.setdefault("produced_files", _snapshot_files(ticket_id, ...))  # mejor esfuerzo, lista
```
Caso borde: si el runner no tiene `agent_name` accesible, usar `agent_type` como fallback. `setdefault` evita reescritura. `produced_files` mejor esfuerzo (puede quedar vacía).

**TDD — test PRIMERO.** Archivo: `backend/tests/test_cli_trace_parity.py` (nuevo).
Casos (reusar los stubs de runner CLI de `test_claude_code_cli_phase1.py` que no spawnean procesos):
1. `test_claude_runner_records_agent_and_sha`: tras un run claude (stub) → `metadata["agent_type"]`, `metadata["prompt_sha"]`, `metadata["produced_files"]` presentes.
2. `test_codex_runner_records_agent_and_sha`: idem para codex.
3. `test_cli_prompt_text_gated`: con `STACKY_TRACE_PROMPT_TEXT_ENABLED=false` → no hay `prompt_text`; con true → sí.

**Comando exacto:**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_cli_trace_parity.py -q
```

**Criterio de aceptación (binario):** 3 passed.

**Flag:** reusa `STACKY_EXECUTION_TRACE_ENABLED` y `STACKY_TRACE_PROMPT_TEXT_ENABLED` de C0.

**Impacto por runtime:** Codex y Claude CLI quedan a la par del path github_copilot. **Trabajo del operador: ninguno.**

---

### C2 — Mostrar la trazabilidad en el drawer de detalle de ejecución (frontend)

**Objetivo (1 frase).** En el drawer de detalle de una ejecución, mostrar una sección "Trazabilidad" con el agente, el hash/longitud del prompt (y el texto si está disponible) y la lista de archivos producidos.

**Valor.** Cierra KPI-C2: el operador diagnostica "qué prompt/agente/archivos usó esta ejecución fallida" en una vista, sin leer logs crudos.

**Archivos exactos:**
- `frontend/src/components/ExecutionDetailDrawer.tsx` (editar; ya extrae `metadata` en `:48-49` y archivos vía `Executions.outputFiles` en `:42-46`).
- `frontend/src/components/ExecutionDetailDrawer.module.css` (editar; clases para la sección).

**Cambio:** agregar una sección "Trazabilidad" que lee de `metadata`:
```tsx
const md = (content?.metadata ?? {}) as Record<string, any>;
// Sección Trazabilidad:
//  - Agente: md.agent_name ?? md.agent_type
//  - Prompt: si md.prompt_text → mostrar (colapsable); si no → `sha: ${md.prompt_sha} (${md.prompt_len ?? "?"} chars)`
//  - Archivos producidos: md.produced_files (lista) — si vacía, "sin archivos registrados"
```
Render:
```tsx
<section className={styles.trace}>
  <h4>Trazabilidad</h4>
  <div>Agente: <strong>{md.agent_name ?? md.agent_type ?? "—"}</strong></div>
  <div>Prompt: {md.prompt_text
      ? <details><summary>ver prompt</summary><pre>{md.prompt_text}</pre></details>
      : <code>sha {md.prompt_sha ?? "—"} ({md.prompt_len ?? "?"} chars)</code>}
  </div>
  <div>Archivos: {Array.isArray(md.produced_files) && md.produced_files.length
      ? <ul>{md.produced_files.map((f:string) => <li key={f}>{f}</li>)}</ul>
      : "sin archivos registrados"}
  </div>
</section>
```
Caso borde: metadata sin estas claves (ejecuciones viejas pre-plan-38) → muestra "—" / "sin archivos registrados", nunca crashea. No requiere endpoint nuevo: `get_execution` ya expone `metadata` (verificado, `executions.py:90` → `to_dict()` → `metadata`).

**TDD — vitest no instalado → criterio degradado.**
- Obligatorio: `cd "Stacky Agents/frontend" && npm run build` 0 errores TS.
- Verificación manual:
  1. Ejecutar un agente sobre un ticket; abrir el drawer de esa ejecución.
  2. Ver "Trazabilidad": agente correcto, `sha ...` (o el prompt si el flag de texto está on), y la lista de archivos (o "sin archivos registrados").
  3. Abrir una ejecución vieja (sin claves nuevas) → muestra "—"/"sin archivos", sin error.

**Criterio de aceptación (binario):** `npm run build` 0 errores TS + las 3 verificaciones manuales OK.

**Flag:** ninguno en frontend (solo renderiza lo que haya en metadata; si C0/C1 están off, simplemente no hay datos y muestra placeholders). **Trabajo del operador: ninguno.**

**Impacto por runtime:** muestra la trazabilidad de los 3 runtimes de forma uniforme (porque C0+C1 unifican las claves).

---

## 4. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| `app_root()`/`backend_root()` no tienen la firma asumida → A0 rompe. | El plan obliga a confirmar firmas en `runtime_paths.py` antes de codificar; fallback `backend_root().parent`. Tests A0 monkeypatchean, así que la lógica se valida aislada. |
| Versión divergente (package.json 0.1.0 vs VERSION.txt 1.0.47). | A0 define orden determinista: VERSION.txt gana en deploy; package.json en dev. KPI-A lo verifica. |
| B0 crea épicas en ADO sin querer (sin confirmación). | `confirm:true` obligatorio (400 si falta); test `test_create_epic_requires_confirm`. UI exige aprobación explícita antes de mandar `confirm`. |
| B0 inventa un cliente ADO nuevo en vez de reusar el de create-child-task. | El plan PROHÍBE expresamente inventar; obliga a grep y reusar `tickets.py:3508`. |
| La épica creada por B0 no es idéntica a una sincronizada → el funcional no la toma. | B0 usa `work_item_type="Epic"` y hace el mismo upsert que `/sync`; KPI-B2 lo verifica con el flujo funcional real. |
| `prompt_text` persiste datos sensibles del ticket. | Default OFF (`STACKY_TRACE_PROMPT_TEXT_ENABLED=false`); por defecto solo `prompt_sha`+`prompt_len`. Reusa el enmascarado PII existente. |
| C0 pisa `metadata["runtime"]` (plan 36) u otras claves. | Todo con `setdefault`; test `test_trace_does_not_overwrite_runtime`. |
| `produced_files` no determinista al cierre → lista vacía. | KPI-C1 acepta lista vacía si la clave existe; siempre se guarda `ticket_output_dir` como respaldo. |
| Frontend sin vitest deja gaps de test. | Criterios degradados a `npm run build` (0 TS) + verificación manual; instalación opcional documentada. |
| Ejecuciones viejas sin claves nuevas rompen el drawer. | C2 usa optional chaining y placeholders; nunca crashea. |

## 5. Fuera de scope

- Cambiar el esquema de DB con columnas nuevas (todo va en `metadata_json`; no se migra el modelo).
- Versionado semántico automático / bump de versión en CI (A0 solo LEE la versión existente).
- Editor visual de épicas / WYSIWYG avanzado (B2 usa textarea + render simple).
- Que el Agente de Negocio escriba en ADO directamente (lo hace Stacky en B0, con aprobación).
- RBAC / multiusuario (mono-operador).
- Capturar diffs línea-a-línea de los archivos tocados (C guarda la LISTA de archivos producidos, no diffs).
- Reescribir el runner Copilot o el router de modelos.

## 6. Glosario

- **BusinessAgent / Agente de Negocio:** rol existente (`backend/agents/business.py`, type `business`) que convierte texto libre/brief en un Epic estructurado en HTML con bloques `RF-XXX`. No es nuevo; este plan le agrega entrada (modal) y salida (épica real).
- **Épica / Epic:** `Ticket` con `work_item_type="Epic"` (`backend/models.py`). Es la raíz del flujo: épica → análisis funcional → tickets → ejecución.
- **`pending-task.json`:** contrato en disco que deja el Analista Funcional (`Agentes/outputs/epic-<ADO_ID>/<RF>/pending-task.json`) para que Stacky cree Tasks hijas en ADO. Convención existente.
- **`metadata_json` / `metadata`:** columna TEXT (JSON) de `AgentExecution` (`models.py:207`), expuesta por `to_dict()`. Contenedor de toda la trazabilidad de este plan; no se agregan columnas.
- **`prompt_sha`:** hash SHA256 del prompt final, ya usado por los runners CLI. Permite comparar prompts sin guardar el texto.
- **`produced_files`:** lista (mejor esfuerzo) de archivos que la ejecución produjo/tocó, en rutas relativas, para diagnóstico.
- **runtime:** Codex CLI / Claude Code CLI / GitHub Copilot. Cada bloque mantiene paridad o degrada con fallback explícito (no silencioso), conforme al plan 36.
- **human-in-the-loop:** el operador aprueba antes de que una épica entre al flujo; nunca se reemplaza su decisión.

## 7. Orden de implementación y DoD

**Orden de implementación (numerado; los bloques son independientes, dentro de cada uno respetar el orden):**
1. **A0** — `services/app_version.py` + tests (base de todo el Bloque A).
2. **A1** — `version` en `/api/health` + tests.
3. **A2** — TopBar muestra versión (frontend).
4. **B0** — endpoint `POST /api/tickets/epics/from-brief` + tests (núcleo del Bloque B).
5. **B1** — `BusinessAgent.agent.md` bundled + tests (paridad 3 runtimes).
6. **B2** — modal "Épica desde brief" + botón en TicketBoard (frontend).
7. **C0** — persistir prompt+agente+archivos en metadata (github_copilot) + tests.
8. **C1** — uniformar trazabilidad en runners CLI + tests.
9. **C2** — sección "Trazabilidad" en el drawer (frontend).

**Definición de Hecho (DoD) global (todo binario):**
- [ ] A0: `tests/test_app_version.py` → 4 passed.
- [ ] A1: `tests/test_health_version.py` → 3 passed.
- [ ] A2: `npm run build` 0 errores TS + TopBar muestra versión real (backend up) y `dev@local` (backend down).
- [ ] B0: `tests/test_epic_from_brief.py` → 5 passed.
- [ ] B1: `tests/test_business_agent_bundled.py` → 3 passed.
- [ ] B2: `npm run build` 0 errores TS + 5 verificaciones manuales (incluida: el Analista Funcional toma la épica creada).
- [ ] C0: `tests/test_execution_trace_metadata.py` → 5 passed.
- [ ] C1: `tests/test_cli_trace_parity.py` → 3 passed.
- [ ] C2: `npm run build` 0 errores TS + 3 verificaciones manuales (incluida ejecución vieja sin crash).
- [ ] KPI-A: versión en TopBar == VERSION.txt (deploy) / package.json (dev).
- [ ] KPI-B2: una épica creada por B0 es lanzable por el Analista Funcional y produce `pending-task.json`.
- [ ] KPI-C1: `get_execution(id)["metadata"]` tiene `prompt_sha`, `agent_type`, `produced_files` para una ejecución de cada runtime.
- [ ] `.env.example` documenta `STACKY_EPIC_FROM_BRIEF_ENABLED`, `STACKY_EXECUTION_TRACE_ENABLED`, `STACKY_TRACE_PROMPT_TEXT_ENABLED`.
- [ ] Los 4 flags nuevos aparecen automáticamente en el panel de flags (Plan 33) si se registran en `FLAG_REGISTRY` (`services/harness_flags.py`) — registrar las keys nuevas allí con su `group`, `type=bool`, `label` y `description` para que sean configurables por UI sin tocar frontend.
- [ ] Suite backend de los archivos nuevos verde (correr por archivo con el python del `.venv`; NO correr la suite completa — está contaminada según baseline conocido).

**Comando de validación global (backend):**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_app_version.py tests/test_health_version.py tests/test_epic_from_brief.py tests/test_business_agent_bundled.py tests/test_execution_trace_metadata.py tests/test_cli_trace_parity.py -q
```
**Comando de validación global (frontend):**
```
cd "Stacky Agents/frontend"
npm run build
```
