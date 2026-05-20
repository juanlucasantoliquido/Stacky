# Plan Arquitectonico Stacky Agents — Problemas 6 y 7 + 3 Features Nuevas

**Fecha:** 2026-05-19
**Branch de referencia:** `pruebaflujoagentico`
**Autor del plan:** Generado por Stacky Senior AI Architect
**Repositorio:** `N:\GIT\RS\RSPACIFICO`
**Stack verificado:** Flask (backend) + React/Vite + TanStack Query (frontend) + SQLite (DB local) + Azure DevOps REST API v7.1

---

## 1. Resumen Ejecutivo

Este plan cubre dos mejoras operativas prioritarias en el ecosistema Stacky Agents y propone tres features de alto valor agregado. El **Problema 6** introduce un recomendador de asignacion de tickets a personas, completamente explicable y con human-in-the-loop obligatorio antes de escribir en ADO. El **Problema 7** resuelve el auto-refresh de la vista de tickets con una estrategia de polling configurable sobre React Query, con indicador visual, backoff exponencial y Page Visibility API. Las tres features recomendadas (Sprint Commitment Board, Diagnóstico Causal de Bloqueos y Comparador de Agentes) amplian capacidades existentes del ecosistema sin duplicar infraestructura. Todo lo propuesto es contract-first, trazable, reversible y compatible con la filosofia Stacky actual.

---

## 2. Contexto y Estado Actual

### 2.1 Lo que se inspeccionó

Se inspeccionaron los siguientes archivos y componentes del repo:

| Componente | Ruta |
|---|---|
| Modelo de datos | `backend/models.py` |
| Sync ADO | `backend/services/ado_sync.py` |
| Cliente ADO | `backend/services/ado_client.py` |
| API de tickets | `backend/api/tickets.py` |
| Vista de tickets | `frontend/src/pages/TicketBoard.tsx` |
| Pantalla de equipo | `frontend/src/pages/TeamScreen.tsx` |
| Endpoints frontend | `frontend/src/api/endpoints.ts` |
| Tipos TypeScript | `frontend/src/types.ts` |
| PM normalizer | `backend/services/pm/pm_normalizer.py` |
| PM KPI engine | `backend/services/pm/pm_kpi_engine.py` |
| PM recommendation engine | `backend/services/pm/pm_recommendation_engine.py` |

### 2.2 Hallazgos relevantes

**Vista de tickets ADO (TicketBoard):**
- Componente principal: `frontend/src/pages/TicketBoard.tsx`.
- Consume `GET /api/tickets` y `GET /api/tickets/hierarchy` vía TanStack Query.
- Ambas queries tienen `refetchInterval: 60_000` (60 segundos). No hay logica de Page Visibility API ni backoff. No hay indicador visual de "ultima sincronizacion hace X seg".
- El sync con ADO se dispara manualmente via boton que llama `POST /api/tickets/sync`.
- Al recargar la pagina, el frontend usa caché local de React Query (staleTime no configurado en estas queries, cae al default global de `30_000 ms`). No hay forzado de sync en mount.
- El endpoint `GET /api/tickets/sync/status` devuelve `{ last_synced_at: string | null }` basado en el campo `last_synced_at` de la tabla `tickets`.

**Sincronizacion con ADO:**
- Mecanismo: on-demand (`POST /api/tickets/sync`) y al startup del backend (`_startup_sync` en `app.py`).
- No hay polling automático del backend ni webhooks de ADO configurados.
- `sync_tickets()` en `ado_sync.py` hace fetch de todos los work items abiertos y upsert en SQLite local.
- `AdoClient` soporta: `fetch_open_work_items`, `update_work_item_state` (PATCH JSON Patch), `post_comment`, `fetch_comments`, `link_attachment_to_work_item`. **No existe** `update_work_item_assigned_to` (campo `System.AssignedTo`).

**Asignacion de tickets / personas:**
- La tabla `Ticket` en `models.py` **no tiene campo `assigned_to`**. El campo `System.AssignedTo` se trae de ADO pero no se persiste en la BD local (se usa solo en PM pipeline inference y en logs de analisis).
- La tabla `User` existe (`id`, `email`, `name`, `created_at`) pero **no tiene relacion con tickets** y no está conectada a ninguna logica de asignacion.
- El PM normalizer (`pm_normalizer.py`) normaliza `System.AssignedTo` a `assigned_to` (email o displayName) para el KPI engine.
- El `pm_recommendation_engine.py` genera recomendaciones del sprint (SCOPE, RESOURCE, PROCESS, RISK_MITIGATION) pero no recomendaciones de asignacion por ticket.
- `TeamScreen.tsx` muestra los agentes (`.agent.md` files) del equipo del proyecto, no las personas reales de ADO. `EmployeeCard.tsx` y `EmployeeEditDrawer.tsx` gestionan esos agentes.

**Capacidad de escritura en ADO:**
- `update_work_item_state` usa JSON Patch sobre `PATCH /api/wit/workitems/{id}`. El mismo patron sirve para actualizar `System.AssignedTo`.
- Ya existe infraestructura de retry con backoff (`_request_with_retry`).

### 2.3 Brechas identificadas

| Brecha | Impacto en P6 | Impacto en P7 |
|---|---|---|
| `Ticket` no persiste `assigned_to` | Critico — hay que agregar columna | No aplica |
| No existe `update_work_item_assigned_to` en `AdoClient` | Critico — hay que agregar metodo | No aplica |
| No hay concepto "persona real" vs "agente .md" | Critico — requiere decision de diseño | No aplica |
| Sin Page Visibility API en TicketBoard | No aplica | Critico |
| Sin indicador visual de ultima sync | No aplica | Critico |
| Sin forzado de sync en mount de pagina | No aplica | Mayor |
| Sin backoff si ADO esta caido | No aplica | Mayor |

---

## 3. Plan — Problema 6: Asignacion Inteligente de Tickets a Personas

> **CAMBIO DE SCOPE — 2026-05-19**
> P6 fue simplificado. Solo se implementan dos cosas:
> 1. **Recomendador de asignacion** (algoritmo deterministico, advisory_only, human-in-the-loop con doble confirmacion antes de PATCH a ADO).
> 2. **Panel de estadisticas por usuario** (cuantos tickets actualmente en cada estado + cuantos historicamente).
>
> **REMOVIDO POR CAMBIO DE SCOPE 2026-05-19:** UI compleja de filtros previa no vinculada al recomendador, gestion de skills desvinculada del scoring, bootstrap manual de personas sin relacion con ADO sync.
> Los prerequisitos reales (migration `assigned_to_ado`, `AdoClient.update_work_item_assigned_to`, `sync_tickets` actualizado) se mantienen porque el recomendador los necesita.
>
> **Decision: Panel de estadisticas historicas — Opcion B elegida**
> Se usa **Opcion B: tabla `ticket_state_history`** (snapshots locales) en lugar de llamar a ADO on-demand (`/_apis/wit/workItems/{id}/updates`).
> Justificacion: la Opcion A (ADO on-demand) tiene tres problemas: (1) costo de N llamadas HTTP por ticket cada vez que se carga el panel, (2) no funciona para tickets ya eliminados de ADO, (3) el rate limiting de ADO puede bloquear el dashboard en horario pico. La Opcion B permite queries SQL puras, no agrega latencia en el panel, y se llena automaticamente en cada `sync_tickets()` sin cambio de comportamiento para el operador.

### 3.1 Decision de Diseño: Concepto de "Persona"

**Open Question #1:** Stacky tiene un modelo `User` (tabla `users`) pero no está conectado a los work items. Los agentes del equipo (`VsCodeAgent` / archivos `.agent.md`) son entidades de automatizacion, no personas reales.

**Decision propuesta:** Usar la lista de personas que ADO devuelve en `System.AssignedTo` de los tickets existentes como fuente de verdad de "quien existe en el equipo". Complementariamente, el modelo `User` se extiende para almacenar el `ado_unique_name` (email ADO) y un perfil de carga/especialidad derivable de los tickets historicos.

**Alternativa descartada:** Gestionar personas manualmente en Stacky. Introduce friction operativa: habria que mantener dos fuentes de verdad (Stacky + ADO). ADO es la fuente de verdad de personas.

### 3.2 Modelo de Datos — Cambios

#### 3.2.1 Tabla `tickets` — nuevas columnas

```sql
ALTER TABLE tickets ADD COLUMN assigned_to_ado TEXT;
-- Email/uniqueName del asignado en ADO. Se sincroniza con cada sync_tickets().
-- Puede ser NULL si no hay asignado.
```

#### 3.2.2 Tabla `users` — nuevas columnas

```sql
ALTER TABLE users ADD COLUMN ado_unique_name TEXT UNIQUE;
-- Email que ADO usa como uniqueName (ej. "jluca@ubimia.com")

ALTER TABLE users ADD COLUMN ado_display_name TEXT;
-- Nombre para mostrar en UI (ej. "Juan Luca Santoliquido")

ALTER TABLE users ADD COLUMN skills_json TEXT;
-- JSON: ["bug", "frontend", "refactor"] — labels configurables por el operador

ALTER TABLE users ADD COLUMN area_paths_json TEXT;
-- JSON: ["Strategist_Pacifico\\UI", "Strategist_Pacifico\\Core"]
-- Rutas ADO donde el usuario ha trabajado historicamente

ALTER TABLE users ADD COLUMN max_active_tickets INTEGER DEFAULT 5;
-- Limite maximo de tickets activos que el operador configura por persona
```

#### 3.2.3 Migration Strategy

Dado que el backend usa SQLite con SQLAlchemy, las migraciones se hacen via Alembic o script manual de `ALTER TABLE`. Se recomienda agregar las columnas con `nullable=True` y default seguro para no romper instancias existentes.

### 3.3 Servicio de Recomendacion — `ticket_assigner.py`

**Ubicacion:** `backend/services/ticket_assigner.py`

**Responsabilidades:**
1. Cargar el perfil de cada persona (carga activa, historial, skills, areas).
2. Calcular un score de adecuacion para cada candidato.
3. Devolver lista ordenada de candidatos con score y razon explicable.

#### 3.3.1 Algoritmo de Scoring (deterministico, sin LLM)

El scoring es una funcion pura, sin llamadas externas. Se compone de cuatro componentes:

| Componente | Peso | Descripcion |
|---|---|---|
| `load_score` | 40% | Inverso de la carga activa ponderada por prioridad |
| `type_affinity_score` | 25% | Match entre tipo de ticket nuevo y distribucion historica de la persona |
| `area_affinity_score` | 20% | Match entre `area_path` del ticket y areas historicas de la persona |
| `throughput_score` | 15% | Tasa de cierre (tickets cerrados / tickets asignados, ultimos 90 dias) |

**Formula:**

```
score = 0.40 * load_score
      + 0.25 * type_affinity_score
      + 0.20 * area_affinity_score
      + 0.15 * throughput_score
```

Todos los sub-scores se normalizan a [0, 1].

**Load score:**

```
pesos_prioridad = {1: 4, 2: 3, 3: 2, 4: 1, None: 2}
carga_ponderada = sum(pesos_prioridad.get(t.priority, 2) for t in tickets_activos)
load_score = max(0, 1 - carga_ponderada / (max_active_tickets * max_peso))
```

Si la carga ponderada supera el maximo configurado, el candidato queda con `overloaded=True` y puede ser filtrado por el UI.

**Type affinity:**

```
distribucion_persona = {tipo: count for tipo in historial_persona}
tipo_ticket = work_item_type del ticket nuevo
affinity = distribucion_persona.get(tipo_ticket, 0) / max(total_tickets_persona, 1)
type_affinity_score = min(affinity * 2, 1.0)  # cap a 1.0, boost si especialista
```

#### 3.3.2 Contrato JSON del Recomendador

**Request (interno al servicio):**

```json
{
  "ticket_ado_id": 1234,
  "work_item_type": "Bug",
  "priority": 2,
  "area_path": "Strategist_Pacifico\\UI",
  "title": "Error al guardar formulario cliente",
  "filters": {
    "max_load_pct": 80,
    "only_skill": null,
    "only_area_path": null,
    "exclude_ado_unique_names": []
  }
}
```

**Response:**

```json
{
  "ok": true,
  "ticket_ado_id": 1234,
  "scored_at": "2026-05-19T14:30:00",
  "candidates": [
    {
      "ado_unique_name": "jluca@ubimia.com",
      "display_name": "Juan Luca",
      "score": 0.82,
      "rank": 1,
      "overloaded": false,
      "load_pct": 40,
      "active_tickets": 2,
      "active_tickets_detail": [
        {"ado_id": 1100, "priority": 2, "state": "Active"},
        {"ado_id": 1098, "priority": 3, "state": "In Progress"}
      ],
      "type_affinity": {
        "score": 0.75,
        "top_types": ["Bug", "Task"],
        "match": true
      },
      "area_affinity": {
        "score": 0.90,
        "matched_areas": ["Strategist_Pacifico\\UI"]
      },
      "throughput_score": 0.80,
      "reason": "Carga baja (40%), especialista en Bug (75% historial), area UI coincide",
      "recommendation_flags": []
    },
    {
      "ado_unique_name": "mperez@ubimia.com",
      "display_name": "Maria Perez",
      "score": 0.51,
      "rank": 2,
      "overloaded": false,
      "load_pct": 60,
      "active_tickets": 3,
      "active_tickets_detail": [...],
      "type_affinity": {...},
      "area_affinity": {...},
      "throughput_score": 0.65,
      "reason": "Carga media (60%), sin historial en Bug para este area",
      "recommendation_flags": ["no_type_specialization"]
    }
  ],
  "excluded": [
    {
      "ado_unique_name": "admin@ubimia.com",
      "reason": "overloaded",
      "load_pct": 95
    }
  ],
  "advisory_only": true,
  "publish_requires_human_approval": true
}
```

**Reglas de contrato:**
- `advisory_only` es siempre `true`. No puede ser sobreescrito.
- `publish_requires_human_approval` es siempre `true`.
- Si hay cero candidatos validos, `candidates` es `[]` y `ok` es `true` (no es error).
- Score de `0.0` a `1.0`. Dos decimales.

### 3.4 Endpoint Backend — `POST /api/tickets/<int:ticket_id>/assignment-recommendations`

**Blueprint:** `api/tickets.py` (existente, se extiende).

**Payload opcional (filtros del operador):**

```json
{
  "max_load_pct": 80,
  "only_skill": "frontend",
  "only_area_path": "Strategist_Pacifico\\UI",
  "exclude_ado_unique_names": ["admin@ubimia.com"]
}
```

**Response exitosa:** el contrato JSON del seccion 3.3.2 mas el campo:

```json
{
  "ok": true,
  "ticket_id": 45,
  "ticket_ado_id": 1234,
  "...": "...el resto del contrato del recomendador"
}
```

**Errores:**

```json
{ "ok": false, "error": "ticket_not_found", "message": "Ticket 99 no existe en BD local" }
{ "ok": false, "error": "no_users_configured", "message": "No hay usuarios con ado_unique_name configurado. Sincronizá primero o agregá usuarios." }
```

**Evento a observabilidad:**

```json
{"event": "assignment_recommendation_generated", "ticket_id": 45, "ticket_ado_id": 1234, "candidates_count": 3, "top_score": 0.82, "filters_applied": {"max_load_pct": 80}, "duration_ms": 42}
```

**Validaciones de preflight:**
1. Ticket existe en BD local.
2. Al menos un usuario con `ado_unique_name` configurado.
3. El ticket tiene `assigned_to_ado` actualizado en la ultima sync (alerta si `last_synced_at` > 5 min).

### 3.5 Endpoint Backend — `POST /api/tickets/<int:ticket_id>/assign`

Este endpoint aplica la asignacion despues de que el operador confirma.

**Payload:**

```json
{
  "ado_unique_name": "jluca@ubimia.com",
  "dry_run": true,
  "reason": "Asignado por recomendacion Stacky — score 0.82"
}
```

**Comportamiento con `dry_run=true` (default):**
- Devuelve lo que haria sin ejecutar nada en ADO.
- Registra evento `assignment_dry_run`.

**Comportamiento con `dry_run=false` (requiere confirmacion explicita en payload):**
1. Llama `AdoClient.update_work_item_assigned_to(ado_id, ado_unique_name)`.
2. Si ADO responde OK: actualiza `tickets.assigned_to_ado` en BD local.
3. Si ADO falla: registra el error, NO actualiza BD local, devuelve error con `rollback_needed: false` (no se hizo nada en BD).
4. Registra evento `assignment_applied` o `assignment_failed`.

**Response exitosa:**

```json
{
  "ok": true,
  "dry_run": false,
  "ticket_id": 45,
  "ticket_ado_id": 1234,
  "assigned_to": "jluca@ubimia.com",
  "ado_updated": true,
  "local_db_updated": true,
  "actions": [
    {"action": "ado_patch_assigned_to", "ok": true},
    {"action": "local_db_update_assigned_to", "ok": true}
  ],
  "operator": "juanluca.santoliquido@ubimia.com"
}
```

**Rollback:** Si ADO acepta pero la BD local falla (extremadamente raro con SQLite), el campo `ado_updated=true, local_db_updated=false` permite al operador corregir localmente con el proximo sync.

**Metodo nuevo en `AdoClient`:**

```python
def update_work_item_assigned_to(self, ado_id: int, ado_unique_name: str) -> dict:
    """
    Cambia System.AssignedTo de un work item en ADO.
    ado_unique_name: uniqueName del usuario en ADO (ej. "jluca@ubimia.com").
    """
    url = f"{self._base_proj}/_apis/wit/workitems/{ado_id}?api-version={_API_VERSION}"
    patch_ops = [
        {"op": "add", "path": "/fields/System.AssignedTo", "value": ado_unique_name}
    ]
    return self._request_with_retry("PATCH", url, body=patch_ops,
                                    content_type="application/json-patch+json")
```

### 3.6 Sincronizacion de `assigned_to_ado` en `sync_tickets()`

En `ado_sync.py`, en el bloque de upsert, agregar:

```python
assigned_raw = fields.get("System.AssignedTo") or {}
if isinstance(assigned_raw, dict):
    assigned_to_ado = assigned_raw.get("uniqueName") or assigned_raw.get("displayName")
else:
    assigned_to_ado = str(assigned_raw) if assigned_raw else None

# Actualizar en el modelo Ticket
existing.assigned_to_ado = assigned_to_ado
```

Y para tickets nuevos, incluir `assigned_to_ado=assigned_to_ado` en el constructor.

### 3.7 Auto-poblado de Usuarios desde Historial ADO

Endpoint auxiliar: `POST /api/users/sync-from-ado`

- Lee todos los `assigned_to_ado` distintos y no nulos de la tabla `tickets`.
- Para cada uno, hace upsert en `users` con `ado_unique_name`.
- No sobreescribe campos que el operador haya configurado manualmente (skills, area_paths, max_active_tickets).
- Devuelve `{ "ok": true, "created": N, "updated": M, "total": K }`.

Esto permite poblar la tabla de usuarios sin configuracion manual inicial.

### 3.8 Componente React — `AssignmentRecommendationPanel`

**Ubicacion propuesta:** `frontend/src/components/AssignmentRecommendationPanel.tsx`

**Donde se integra:** Dentro de `TicketCard` en `TicketBoard.tsx`, como panel expandible (acordeon), al mismo nivel que `PipelineStatus` y `ExecutionHistory`. Se activa con un boton "Asignar" visible solo si el ticket no tiene `assigned_to_ado`.

**Props:**

```typescript
interface AssignmentRecommendationPanelProps {
  ticket: Ticket;
  onAssigned: () => void;  // callback para invalidar query y refrescar
}
```

**Estados internos:**

| Estado | Tipo | Descripcion |
|---|---|---|
| `phase` | `'idle' | 'loading' | 'recommendations' | 'confirming' | 'applying' | 'done' | 'error'` | Maquina de estados de la UI |
| `candidates` | `AssignmentCandidate[]` | Lista del recomendador |
| `selected` | `AssignmentCandidate | null` | Candidato que el operador eligio |
| `filters` | `AssignmentFilters` | Filtros activos |
| `error` | `string | null` | Mensaje de error |
| `dryRunResult` | `AssignDryRunResult | null` | Preview antes de confirmar |

**Flujo de UI:**

```
[Boton "Sugerir asignacion"]
  → fase: loading
  → GET /api/tickets/{id}/assignment-recommendations
  → fase: recommendations

[Lista de candidatos con scores, razones, badges]
  → filtros: tipo, prioridad, area, carga maxima, skill
  → botones: [Seleccionar] por candidato

[Candidato seleccionado]
  → boton "Ver preview" → POST /api/tickets/{id}/assign {dry_run: true}
  → muestra DryRunPreview: que cambiara en ADO

[Preview confirmado]
  → boton "Confirmar asignacion" (requiere clic explicito, no doble)
  → POST /api/tickets/{id}/assign {dry_run: false}
  → muestra resultado, llama onAssigned()
```

**Human-in-the-loop obligatorio:** Antes de cualquier escritura en ADO, el panel muestra claramente:
- A quien se va a asignar.
- En que ticket (titulo + ADO ID).
- Que se va a escribir en ADO (`System.AssignedTo`).
- Boton de cancelar hasta el ultimo momento.

**Tipos TypeScript nuevos:**

```typescript
interface AssignmentCandidate {
  ado_unique_name: string;
  display_name: string;
  score: number;
  rank: number;
  overloaded: boolean;
  load_pct: number;
  active_tickets: number;
  active_tickets_detail: { ado_id: number; priority: number; state: string }[];
  reason: string;
  recommendation_flags: string[];
}

interface AssignmentRecommendationResponse {
  ok: boolean;
  ticket_ado_id: number;
  candidates: AssignmentCandidate[];
  excluded: { ado_unique_name: string; reason: string; load_pct: number }[];
  advisory_only: boolean;
  publish_requires_human_approval: boolean;
}
```

### 3.9 Permisos y Seguridad

- El PAT de ADO ya tiene permisos de lectura/escritura sobre work items (lo usa `update_work_item_state`). Verificar que el scope incluya `vso.work_write`.
- El `ado_unique_name` enviado al endpoint de asignacion se valida contra la lista de usuarios conocidos en BD local antes de llamar a ADO (no se permite asignar a emails arbitrarios).
- La llamada a `POST /api/tickets/{id}/assign` sin `dry_run=false` explicito es siempre dry-run por defecto.

### 3.10 Observabilidad — Eventos en SystemLog

Todos los eventos se registran via `stacky_logger` en `system_logs`:

| Evento | source | action |
|---|---|---|
| Recomendacion generada | `ticket_assigner` | `assignment_recommendation_generated` |
| Dry-run ejecutado | `ticket_assigner` | `assignment_dry_run` |
| Asignacion aplicada en ADO | `ticket_assigner` | `assignment_applied` |
| Asignacion fallida en ADO | `ticket_assigner` | `assignment_failed` |
| Usuario auto-poblado desde historial | `user_sync` | `user_upserted_from_ado` |

### 3.11 Tests Requeridos

| Test | Capa | Descripcion |
|---|---|---|
| `test_ticket_assigner_scoring.py` | unit | Algoritmo de scoring con fixtures de tickets y personas |
| `test_ticket_assigner_filters.py` | unit | Filtros de carga maxima, skill, area, exclusion |
| `test_assignment_endpoint_dryrun.py` | integration | POST con dry_run=true no llama a ADO |
| `test_assignment_endpoint_apply.py` | integration | POST con dry_run=false llama a AdoClient mock |
| `test_assign_ado_client.py` | integration | update_work_item_assigned_to genera el JSON Patch correcto |
| `test_sync_tickets_assigned_to.py` | integration | sync_tickets persiste assigned_to_ado correctamente |

---

## 4. Plan — Problema 7: Auto-Refresh y Sync ADO de la Vista de Tickets

### 4.1 Estrategia Elegida: Polling Configurable + Sync Forzado en Mount

**Opciones evaluadas:**

| Opcion | Pros | Contras | Decision |
|---|---|---|---|
| Polling React Query (refetchInterval) | Ya existe parcialmente. Sin dependencia nueva. Controlable. | No reacciona a cambios de ADO en tiempo real. | **Elegida** |
| SSE (Server-Sent Events) | Casi-realtime. Menor overhead que WebSocket. | Requiere nuevo endpoint SSE en Flask + gestion de conexiones. Complejidad no justificada para el caso de uso. | Descartada para esta version |
| WebSocket | Tiempo real real. | Flask no es asincronico; requeriria Flask-SocketIO o migrar a FastAPI. Fuera de scope. | Descartada |
| Cache invalidation via ETag | Optimo en trafico. | ADO no expone ETag sobre el endpoint WIQL. Complejidad alta. | Descartada |

**Justificacion del polling:** El equipo usa Flask sincrono. React Query ya gestiona el polling de forma robusta. Un intervalo de 45 segundos es un buen balance entre freshness y carga sobre ADO. El startup sync ya existe en el backend (`_startup_sync`). Solo hay que agregar el forzado en mount del frontend y la observabilidad visual.

**Intervalo default propuesto: 45 segundos**

Justificacion:
- Los 60 segundos actuales son aceptables pero suboptimos para un equipo que trabaja activamente.
- Los 30 segundos pueden saturar ADO si hay muchos usuarios concurrentes del dashboard.
- 45 segundos es un punto medio razonable. Configurable via variable de entorno `STACKY_TICKET_SYNC_INTERVAL_MS`.

### 4.2 Cambios en el Frontend

#### 4.2.1 Hook `useTicketSync` (nuevo)

**Ubicacion:** `frontend/src/hooks/useTicketSync.ts`

**Responsabilidades:**
- Encapsular la logica de polling, forzado de sync en mount, Page Visibility API y backoff.
- Exponer `lastSyncedAt`, `isSyncing`, `syncError`, `triggerSync` y `secondsSinceSync`.

**Esquema del hook:**

```typescript
interface UseTicketSyncOptions {
  intervalMs?: number;         // default: 45_000
  syncOnMount?: boolean;       // default: true — fuerza sync al montar
  respectVisibility?: boolean; // default: true — pausa si tab oculta
}

interface UseTicketSyncResult {
  lastSyncedAt: string | null; // ISO string
  secondsSinceSync: number | null;
  isSyncing: boolean;
  syncError: string | null;
  triggerSync: () => void;     // llamada manual
  isStale: boolean;            // true si lastSyncedAt > 2 * intervalMs
}
```

**Logica de Page Visibility:**

```typescript
useEffect(() => {
  if (!respectVisibility) return;
  const onVisibility = () => {
    if (document.visibilityState === 'visible') {
      // Si fue invisible por mas de intervalMs, forzar sync inmediato
      if (secondsSinceSync !== null && secondsSinceSync * 1000 > intervalMs) {
        triggerSync();
      }
    }
  };
  document.addEventListener('visibilitychange', onVisibility);
  return () => document.removeEventListener('visibilitychange', onVisibility);
}, [respectVisibility, secondsSinceSync, intervalMs, triggerSync]);
```

**Backoff si ADO esta caido:**

```typescript
// Si hay syncError, duplicar el intervalo hasta max 5 minutos
const effectiveInterval = syncError
  ? Math.min(intervalMs * (2 ** consecutiveErrors), 5 * 60_000)
  : intervalMs;
```

#### 4.2.2 Indicador Visual — `SyncStatusBar`

**Ubicacion:** `frontend/src/components/SyncStatusBar.tsx`

**Posicion en UI:** Barra fija en la parte superior de `TicketBoard`, debajo del `TopBar`, o como badge en el boton de sync existente. La primera opcion es mas visible.

**Estados visuales:**

| Estado | Visual |
|---|---|
| Syncing | Spinner + "Sincronizando con ADO..." |
| OK reciente (< 60s) | Punto verde + "Sincronizado hace X seg" |
| OK pero envejeciendo (60s–2min) | Punto amarillo + "Sincronizado hace X seg" |
| Stale (> 2 * intervalo) | Punto rojo + "Sin actualizar hace X min — Sincronizar ahora" |
| Error | Icono rojo + mensaje de error corto + boton "Reintentar" |

**Props:**

```typescript
interface SyncStatusBarProps {
  lastSyncedAt: string | null;
  secondsSinceSync: number | null;
  isSyncing: boolean;
  syncError: string | null;
  onSyncClick: () => void;
  isStale: boolean;
}
```

#### 4.2.3 Cambios en `TicketBoard.tsx`

1. Reemplazar el `syncMutation` actual por el hook `useTicketSync`.
2. Integrar `SyncStatusBar` en el render.
3. El `refetchInterval` de las queries de tickets se alinea con `intervalMs` del hook.
4. En el `useEffect` de mount (o en la query con `enabled`), forzar una llamada a `triggerSync()` si `syncOnMount=true`.

**Contrato de las queries actualizado:**

```typescript
const { data: tickets, isLoading } = useQuery<Ticket[]>({
  queryKey: ["tickets"],
  queryFn: Tickets.list,
  refetchInterval: ticketSyncInterval, // variable, default 45_000
  staleTime: ticketSyncInterval / 2,   // la mitad del intervalo
  refetchOnWindowFocus: true,          // refetch al enfocar ventana
});
```

### 4.3 Cambios en el Backend

#### 4.3.1 Contrato del Endpoint `POST /api/tickets/sync` (sin cambios de ruta)

Actualmente devuelve:

```json
{
  "ok": true,
  "project": "Strategist_Pacifico",
  "fetched": 42,
  "created": 2,
  "updated": 5,
  "removed": 0,
  "synced_at": "2026-05-19T14:30:00"
}
```

Agregar campos para mejor observabilidad:

```json
{
  "ok": true,
  "project": "Strategist_Pacifico",
  "fetched": 42,
  "created": 2,
  "updated": 5,
  "removed": 0,
  "synced_at": "2026-05-19T14:30:00",
  "duration_ms": 380,
  "idempotent": true
}
```

`idempotent: true` indica que el sync no creo ni modifico nada (updated=0, created=0, removed=0). Permite al frontend saber que la respuesta es segura de cachear.

#### 4.3.2 Rate Limiting en el Backend

Para evitar que un frontend mal configurado sature ADO, agregar un rate limiter simple en el endpoint `POST /api/tickets/sync`:

```python
_SYNC_MIN_INTERVAL_SEC = 15  # No permitir mas de un sync cada 15 segundos

_last_sync_ts: float = 0.0

@bp.post("/sync")
def sync_from_ado():
    global _last_sync_ts
    now = time.time()
    if now - _last_sync_ts < _SYNC_MIN_INTERVAL_SEC:
        remaining = int(_SYNC_MIN_INTERVAL_SEC - (now - _last_sync_ts))
        return jsonify({
            "ok": False,
            "error": "rate_limited",
            "message": f"Sync demasiado frecuente. Esperá {remaining}s.",
            "retry_after_sec": remaining
        }), 429
    _last_sync_ts = now
    # ... logica de sync existente
```

**Nota:** Para produccion con multiples workers, usar Redis o la tabla de BD para el timestamp en lugar de variable de modulo.

#### 4.3.3 Evento de Observabilidad por Sync

Registrar en `system_logs` cada llamada a sync con:

```json
{
  "source": "ado_sync",
  "action": "sync_completed",
  "context": {
    "fetched": 42, "created": 2, "updated": 5, "removed": 0,
    "duration_ms": 380, "triggered_by": "frontend_auto_poll"
  }
}
```

El campo `triggered_by` se pasa opcionalmente desde el frontend via header `X-Stacky-Trigger: auto_poll | manual | startup`.

#### 4.3.4 Endpoint `GET /api/tickets/sync/status` — Extension

Actualmente devuelve solo `last_synced_at`. Extender a:

```json
{
  "last_synced_at": "2026-05-19T14:30:00",
  "seconds_since_sync": 45,
  "is_stale": false,
  "stale_threshold_sec": 120,
  "sync_in_progress": false
}
```

`sync_in_progress` es un flag en memoria (o en BD) que se activa al inicio del sync y se desactiva al final. Permite que el frontend evite lanzar dos syncs simultaneos.

### 4.4 Configuracion

Variable de entorno: `STACKY_TICKET_SYNC_INTERVAL_MS` (default: `45000`).

El frontend lee esta configuracion desde un endpoint:

```
GET /api/config/frontend
{ "ticket_sync_interval_ms": 45000, "sync_min_interval_sec": 15 }
```

Este endpoint ya puede existir o crearse como parte de esta feature.

### 4.5 Tests Requeridos

| Test | Capa | Descripcion |
|---|---|---|
| `test_sync_rate_limit.py` | integration | Segundo sync dentro de 15s devuelve 429 |
| `test_sync_status_extended.py` | integration | GET /sync/status devuelve todos los campos nuevos |
| `useTicketSync.test.ts` | unit (vitest) | Hook pausa en tab oculta, retoma al volver a tab |
| `SyncStatusBar.test.tsx` | component | Estados visuales correctos segun secondsSinceSync |

---

## 5. Tres Features Nuevas Recomendadas

### Feature A — Sprint Commitment Board (Tablero de Compromiso de Sprint)

**Nombre:** Sprint Commitment Board

**Problema que resuelve:**
Actualmente Stacky muestra tickets en una vista jerarquica (Epic → Task) pero no hay una vista orientada a la iteracion/sprint activa. El operador no puede ver rapidamente: cuantos puntos se comprometieron, cuantos estan done, quien esta bloqueado, y si el sprint va a cerrar bien. El PM Command Center tiene KPIs pero no es una vista operativa dia a dia.

**Valor de negocio:**
- Reduce el tiempo de la daily standup: el equipo ve el estado del sprint en segundos.
- Detecta bloqueos tempranos antes de la retrospectiva.
- Complementa el recomendador de asignacion (P6) con contexto de sprint.

**Propuesta de implementacion:**

Backend:
- Reutiliza `ado_pm_collector.py` (ya hace `fetch_sprint_work_items` y `fetch_current_iteration`).
- Nuevo endpoint `GET /api/pm/sprint/board?project=X` que devuelve items del sprint activo agrupados por estado (Nuevo / En Progreso / Bloqueado / Done) con `assigned_to`, `story_points`, `priority`.
- El agrupamiento por "Bloqueado" requiere lectura de tags o estado especifico de ADO (open question: convension de estado de bloqueo en este proyecto).

Frontend:
- Nueva pagina `SprintBoardPage.tsx` con columnas Kanban simplificadas (no drag-and-drop en v1).
- Cards que muestran: avatar del asignado, ADO ID, tipo, prioridad, story points, dias en estado actual.
- Integrado en el menu de navegacion junto a TicketBoard y PMCommandCenter.

Integraciones:
- Lee de ADO via `pm_collector`. No requiere nueva infraestructura de sync.
- Complementa el recomendador P6: al asignar un ticket nuevo, el board muestra la carga actualizada.

**Riesgos:**
- La definicion de "sprint activo" en ADO depende de que haya iteraciones configuradas en el proyecto. Si no hay, el board queda vacio (open question).
- El campo "Bloqueado" puede no existir como estado nativo en ADO; puede requerir mapeo por tag.

**Esfuerzo:** M (2–3 dias backend + 2–3 dias frontend).

**Encaje con Stacky:**
- Tool-first: nuevo endpoint reutiliza pm_collector existente.
- Contract-first: schema del board definido antes de implementar.
- Observable: cada carga del board registra evento en system_logs.
- Human-in-the-loop: no modifica nada, es solo lectura.

---

### Feature B — Diagnóstico Causal de Bloqueos por Ticket

**Nombre:** Ticket Block Diagnostics

**Problema que resuelve:**
Cuando un ticket lleva muchos dias sin moverse (aging alto) o tiene estado "Bloqueado", el equipo no sabe por que. Stacky ya tiene comentarios de ADO (`fetch_comments`), historial de ejecuciones (`AgentExecution`), y un PM risk engine. Pero no existe un "por que este ticket no avanza" en un solo lugar.

**Valor de negocio:**
- Reduce el tiempo de diagnostico de un bloqueo de horas a segundos.
- Genera sugerencias de desbloqueo accionables (no solo descripcion del problema).
- El recomendador de asignacion (P6) puede usar el diagnostico para penalizar tickets bloqueados en la carga de un candidato.

**Propuesta de implementacion:**

Backend:
- Nuevo servicio `ticket_diagnostics.py` en `backend/services/`.
- Recibe un `ticket_id` y recopila: `aging_days`, `state_transitions` (ultimas N), `last_execution` de Stacky, `ado_comments` (ultimos 10), `blocked_by_ado_id` (relacion ADO de tipo "blocked by" si existe).
- Genera un diagnostico estructurado con un LLM (reutiliza `llm_router.py` existente) contra un prompt con schema de output fijo.
- Output del LLM validado con contrato JSON antes de devolver.
- Gate de eval obligatorio (fixture en `evals/`) antes de habilitar el endpoint en produccion.

Endpoint: `GET /api/tickets/<int:ticket_id>/diagnostics`

```json
{
  "ok": true,
  "ticket_id": 45,
  "ticket_ado_id": 1234,
  "aging_days": 12,
  "last_state_change": "2026-05-07T10:00:00",
  "probable_causes": [
    {
      "category": "DATA",
      "description": "El ticket no tiene criterios de aceptacion definidos",
      "confidence": 0.85,
      "evidence": ["Descripcion vacia", "Sin comentarios tecnico-funcionales"]
    },
    {
      "category": "ENV",
      "description": "El agente tecnico no fue ejecutado aun",
      "confidence": 0.90,
      "evidence": ["pipeline_summary.next_suggested = 'technical'"]
    }
  ],
  "suggested_actions": [
    "Completar descripcion del ticket antes de ejecutar el agente tecnico",
    "Ejecutar Agente Tecnico desde TicketBoard"
  ],
  "advisory_only": true,
  "generated_by": "llm",
  "model": "gpt-4o-mini",
  "eval_gate_passed": true
}
```

Frontend:
- Boton "Diagnosticar" en `TicketCard` para tickets con aging > umbral configurable.
- Panel lateral `DiagnosticsPanel.tsx` con las causas probables y acciones sugeridas.
- Las acciones sugeridas son botones que llevan al flujo correspondiente (ej. "Ejecutar Agente Tecnico" abre el RunModal).

**Riesgos:**
- El LLM puede inventar causas si el contexto es insuficiente. Mitigacion: schema de output estricto + gate de eval con fixtures de casos conocidos.
- Costo LLM por llamada (mitigacion: cache de 60 min por ticket, invalidable manualmente).

**Esfuerzo:** M (2 dias backend + eval fixtures + 1 dia frontend).

**Encaje con Stacky:**
- AI bajo contrato: output del LLM validado contra schema antes de devolver.
- Evals obligatorios: no habilitar en produccion sin pasar fixtures.
- Advisory only: las sugerencias no se aplican solas.
- Evidence-first: confidence y evidence explícitos en cada causa.

---

### Feature C — Comparador de Agentes (Agent Performance Comparison)

**Nombre:** Agent Performance Comparison

**Problema que resuelve:**
El equipo tiene multiples agentes `.agent.md` por tipo (ej. dos versiones de Agente Developer, o el agente de QA vs el agente QA UAT). No hay forma de saber cual de ellos produce mejores outputs (medido por aprobaciones, velocidad, rate de rechazos). El operador elige el agente manualmente sin datos.

**Valor de negocio:**
- Permite al equipo tomar decisiones basadas en datos sobre cual agente usar para cada tipo de ticket.
- Detecta agentes degradados (alta tasa de rechazo, outputs rechazados frecuentemente).
- Cierra el loop de mejora continua de prompts: cambias el prompt, mides el impacto.

**Propuesta de implementacion:**

Backend:
- Reutiliza `AgentExecution` (ya tiene `agent_type`, `verdict`, `status`, `duration_ms`, `started_by`).
- Nuevo endpoint `GET /api/metrics/agent-comparison?project=X&days=30&agent_type=developer` que agrega por agente filename (desde `metadata_json`) y calcula:
  - `total_runs`, `approved_count`, `discarded_count`, `error_count`
  - `approval_rate`, `avg_duration_ms`, `p95_duration_ms`
  - `tickets_completed` (executions que derivaron en stacky_status=completed)
- El `agent_filename` ya se almacena en `metadata_json` de `AgentExecution` (verificar; si no, agregarlo al registrar).

Endpoint response:

```json
{
  "ok": true,
  "period_days": 30,
  "agent_type": "developer",
  "agents": [
    {
      "filename": "agente_desarrollador_v2.agent.md",
      "total_runs": 45,
      "approved_count": 38,
      "discarded_count": 5,
      "error_count": 2,
      "approval_rate": 0.84,
      "avg_duration_ms": 12400,
      "p95_duration_ms": 28000,
      "tickets_completed": 31
    },
    {
      "filename": "agente_desarrollador_v1.agent.md",
      "total_runs": 20,
      "approved_count": 14,
      "discarded_count": 6,
      "error_count": 0,
      "approval_rate": 0.70,
      "avg_duration_ms": 15800,
      "p95_duration_ms": 35000,
      "tickets_completed": 12
    }
  ]
}
```

Frontend:
- Nueva seccion en `CatalogDashboard.tsx` o nueva pagina `AgentMetricsPage.tsx`.
- Tabla comparativa con sparkline de aprobaciones en el tiempo.
- Highlight del agente con mejor approval_rate del periodo.
- Filtros: periodo, tipo de agente.

**Riesgos:**
- `agent_filename` puede no estar en `metadata_json` en todas las ejecuciones antiguas. Mitigacion: agregar el campo desde ahora en `agent_runner.py`; datos historicos quedaran con `filename=unknown` (manejado en UI).
- Con pocos datos (< 10 runs por agente), las metricas no son estadisticamente significativas. Mitigacion: mostrar badge de advertencia si `total_runs < 10`.

**Esfuerzo:** S (1 dia backend — query de agregacion pura + 1 dia frontend — tabla comparativa).

**Encaje con Stacky:**
- Tool-first: nuevo endpoint de agregacion, reutiliza datos existentes.
- Observable: las metricas son auditables desde los registros de `AgentExecution`.
- No requiere cambios en agentes ni en el pipeline.
- Sin riesgo de escritura: endpoint de solo lectura.

---

## 6. Roadmap Sugerido

### Dependencias entre items

```
P6 (Asignacion) depende de:
  - Migration BD (assigned_to_ado en Ticket, extensiones en User)
  - AdoClient.update_work_item_assigned_to (nuevo metodo)
  - sync_tickets() actualizado para persistir assigned_to_ado

P7 (Auto-refresh) depende de:
  - Hook useTicketSync (nuevo)
  - Rate limiting en POST /api/tickets/sync
  - SyncStatusBar (nuevo componente)

Feature A (Sprint Board) depende de:
  - pm_collector.py existente (sin cambios)
  - Opcional: P6 para mostrar asignacion en cards del board

Feature B (Diagnosticos) depende de:
  - llm_router.py existente (sin cambios)
  - fetch_comments en AdoClient (existente)
  - Evals fixtures (nuevo)

Feature C (Comparador Agentes) depende de:
  - AgentExecution.metadata_json con agent_filename (verificar/agregar)
  - Sin otras dependencias
```

### Orden de implementacion propuesto

| Sprint | Item | Esfuerzo | Razon |
|---|---|---|---|
| Sprint 1 | P7 Auto-refresh | S | Bajo riesgo, alto impacto inmediato, no toca BD |
| Sprint 1 | Feature C — Comparador Agentes | S | Solo lectura, reutiliza datos existentes |
| Sprint 2 | P6 Migration BD + sync_tickets actualizado | S | Prerequisito de P6 completo |
| Sprint 2 | P6 Servicio recomendador + endpoints | M | Logica central del recomendador |
| Sprint 2 | P6 Componente React AssignmentRecommendationPanel | M | UI del recomendador |
| Sprint 3 | Feature A — Sprint Commitment Board | M | Requiere clarificacion de open questions |
| Sprint 3 | Feature B — Diagnosticos causales | M | Requiere evals fixtures antes de ir a produccion |

---

## 7. Riesgos Transversales y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigacion |
|---|---|---|---|
| ADO cambia formato de `System.AssignedTo` (objeto vs string) | Media | Alto | `pm_normalizer.py` ya maneja ambos casos; replicar en `ado_sync.py` |
| El PAT de ADO no tiene scope `vso.work_write` para asignacion | Alta (no verificado) | Critico para P6 | Verificar scope del PAT antes de implementar P6; documentar como prerequisito |
| Rate limiting de ADO (HTTP 429) al aumentar frecuencia de sync | Media | Medio | Backoff existente en `_request_with_retry`; el rate limit del backend (P7) protege adicionalmente |
| Usuarios en ADO con `uniqueName` distinto al `email` (ej. SSO) | Media | Medio para P6 | Usar `uniqueName` como clave de asignacion (ya validado en pm_normalizer); mostrar `displayName` en UI |
| SQLite bajo carga concurrente (multiples syncs simultaneos) | Baja | Medio | Rate limit del backend (P7) previene syncs simultaneos; SQLite en WAL mode ya configurado (verificar) |
| El campo `agent_filename` no esta en `metadata_json` historico | Alta | Bajo para Feature C | Datos historicos con `filename=unknown` son esperados; advertencia en UI |
| Sprint sin iteraciones configuradas en ADO | Media | Medio para Feature A | Endpoint devuelve `{ "ok": true, "sprint": null, "items": [] }` con mensaje claro |

---

## 8. Checklist de Entregables

### Problema 6 — Asignacion Inteligente

- [ ] Migration SQL: columna `assigned_to_ado` en `tickets` y columnas nuevas en `users`
- [ ] `AdoClient.update_work_item_assigned_to()` — nuevo metodo con JSON Patch
- [ ] `ado_sync.py` actualizado para persistir `assigned_to_ado`
- [ ] `backend/services/ticket_assigner.py` — servicio de scoring
- [ ] `POST /api/tickets/<id>/assignment-recommendations` — endpoint recomendador
- [ ] `POST /api/tickets/<id>/assign` — endpoint de aplicacion con dry_run
- [ ] `POST /api/users/sync-from-ado` — endpoint de auto-poblado de usuarios
- [ ] Tipos TypeScript: `AssignmentCandidate`, `AssignmentRecommendationResponse`
- [ ] Endpoint en `endpoints.ts`: `Tickets.assignmentRecommendations`, `Tickets.assign`
- [ ] `AssignmentRecommendationPanel.tsx` — componente React
- [ ] Integracion de `AssignmentRecommendationPanel` en `TicketBoard.tsx`
- [ ] Tests: `test_ticket_assigner_scoring.py`, `test_ticket_assigner_filters.py`, `test_assignment_endpoint_dryrun.py`, `test_assignment_endpoint_apply.py`, `test_sync_tickets_assigned_to.py`
- [ ] Documentacion: contrato JSON del recomendador en `/docs`
- [ ] Verificacion de scope del PAT de ADO para `vso.work_write`
- [ ] PR con rama `feature/stacky-assignment-recommender`

### Problema 7 — Auto-Refresh y Sync

- [ ] `frontend/src/hooks/useTicketSync.ts` — hook con backoff y Page Visibility
- [ ] `frontend/src/components/SyncStatusBar.tsx` — indicador visual
- [ ] `TicketBoard.tsx` actualizado: usa `useTicketSync`, integra `SyncStatusBar`, sync en mount
- [ ] Rate limiting en `POST /api/tickets/sync` (15 segundos minimo entre syncs)
- [ ] Extension de `GET /api/tickets/sync/status` con campos nuevos
- [ ] Header `X-Stacky-Trigger` en llamadas de sync del frontend
- [ ] Evento de observabilidad en `system_logs` por cada sync con `triggered_by`
- [ ] `GET /api/config/frontend` — endpoint de configuracion
- [ ] Variable de entorno `STACKY_TICKET_SYNC_INTERVAL_MS` documentada
- [ ] Tests: `test_sync_rate_limit.py`, `test_sync_status_extended.py`, `useTicketSync.test.ts`, `SyncStatusBar.test.tsx`
- [ ] PR con rama `feature/stacky-ticket-auto-refresh`

### Feature A — Sprint Commitment Board

- [ ] `GET /api/pm/sprint/board` — endpoint con items del sprint agrupados por estado
- [ ] `SprintBoardPage.tsx` — nueva pagina React
- [ ] Integracion en menu de navegacion
- [ ] Tests de endpoint con sprint vacio y sprint con datos
- [ ] Clarificacion de open question sobre convension de "Bloqueado" en ADO del proyecto
- [ ] PR con rama `feature/stacky-sprint-board`

### Feature B — Diagnosticos Causales

- [ ] `backend/services/ticket_diagnostics.py` — servicio con LLM bajo contrato
- [ ] Schema de output JSON del diagnostico
- [ ] Fixtures de evals en `evals/ticket_diagnostics/`
- [ ] Gate de eval obligatorio antes de habilitar endpoint
- [ ] `GET /api/tickets/<id>/diagnostics` — endpoint
- [ ] `DiagnosticsPanel.tsx` — componente React
- [ ] Cache de 60 min en backend con invalidacion manual
- [ ] PR con rama `feature/stacky-ticket-diagnostics`

### Feature C — Comparador de Agentes

- [ ] Verificar/agregar `agent_filename` a `metadata_json` en `agent_runner.py`
- [ ] `GET /api/metrics/agent-comparison` — endpoint de agregacion
- [ ] Tabla comparativa en `CatalogDashboard.tsx` o nueva pagina
- [ ] Tests: query de agregacion con datos mock
- [ ] PR con rama `feature/stacky-agent-comparison`

---

## 9. Open Questions

| ID | Pregunta | Bloquea | Quien responde |
|---|---|---|---|
| OQ-1 | El PAT de ADO configurado en `Tools/PAT-ADO` tiene scope `vso.work_write` que permita escribir `System.AssignedTo`? Verificar antes de implementar P6. | P6 endpoint `/assign` | Operador / DevOps |
| OQ-2 | Cuál es la convención de estado "Bloqueado" en el proyecto ADO `Strategist_Pacifico`? (estado nativo, tag, o campo personalizado?) Necesario para Feature A y Feature B. | Feature A agrupamiento, Feature B categoría BLOCK | PO / Scrum Master |
| OQ-3 | El modelo `User` en `users` se gestiona manualmente hoy (no hay UI para agregar usuarios)? El endpoint `POST /api/users/sync-from-ado` propuesto resuelve el bootstrap inicial, pero se necesita confirmar si ya hay endpoints de CRUD de usuarios existentes. Buscar en `api/` si hay `users.py`. | P6 bootstrap de datos | Dev team |
| OQ-4 | El proyecto ADO tiene iteraciones/sprints configuradas? Si no, Feature A devuelve siempre sprint vacio. Impacto en valor percibido de la feature. | Feature A valor | PO |
| OQ-5 | El `metadata_json` de `AgentExecution` incluye hoy el `agent_filename`? Verificar en `agent_runner.py`. Si no, agregar antes de Feature C para empezar a acumular datos utiles. | Feature C datos historicos | Dev team (verificar `agent_runner.py`) |
| OQ-6 | El frontend se sirve con multiples usuarios concurrentes? Si si, el rate limiting por variable de modulo en P7 no es suficiente (se reinicia por proceso). Necesita persistencia en BD o Redis. | P7 en produccion multi-worker | DevOps / Arquitecto |

---

*Documento generado con inspeccion directa del repositorio en branch `pruebaflujoagentico`, fecha 2026-05-19.*
*Ningún codigo fue modificado durante la generacion de este plan.*
