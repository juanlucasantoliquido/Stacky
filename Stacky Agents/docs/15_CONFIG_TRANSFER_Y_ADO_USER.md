# Exportación/Importación de configuración + Filtro de tickets ADO por usuario

**Fecha:** 2026-05-27
**Plan de origen:** `docs/plans/plan-export-config-y-ado-tickets-2026-05-27.md`

Implementa los dos requerimientos del plan:

- **A.** Portabilidad de la configuración por proyecto (export/import) para evitar
  reconfiguración tras upgrades o nuevos despliegues.
- **B.** Filtrado de tickets ADO por usuario sincronizado, con checkbox
  "Mostrar todas las tareas" marcado por defecto y persistencia en `localStorage`.

---

## A) Exportar / Importar configuración

### Backend

- `backend/services/config_transfer.py` — núcleo:
  - `build_export(project, sections?)` arma un bundle versionado con `meta`
    (schemaVersion, appVersion, projectId, exportedAt, **checksum sha256**) y las
    secciones: `settings`, `integrations`, `workflows`, `agentProfiles`,
    `uiPreferences`, `secretsRef`.
  - **Seguridad:** los secretos (PAT/tokens/passwords) **nunca** se exportan.
    `secretsRef` solo lista qué credenciales existían y qué campos tenían, para
    avisar al importar cuáles re-cargar.
  - `validate_import(bundle)` valida estructura, compatibilidad de `schemaVersion`
    (rechaza versiones más nuevas; aplica migradores para versiones viejas) y
    **verifica el checksum** (detecta corrupción/manipulación).
  - `apply_import(project, bundle, mode)` con `mode` ∈ `dry-run | merge | overwrite`.
    **Idempotente:** re-aplicar el mismo bundle deja un diff vacío.
  - `record_event` / `list_events` → auditoría en
    `data/config_transfer_events.jsonl`.

- `backend/api/config_transfer.py` — endpoints (registrados en `api/__init__.py`):
  - `POST /api/projects/<name>/config/export` → `{ ok, bundle, filename }`
  - `POST /api/projects/<name>/config/import?mode=dry-run|merge|overwrite`
  - `GET  /api/projects/<name>/config/transfer-events?limit=`
  - `GET  /api/config/sections` (catálogo de secciones exportables)

### Frontend

- `ConfigTransfer` en `api/endpoints.ts`.
- `components/ConfigTransferPanel.tsx`: exportar (descarga JSON), importar con
  **wizard** subir → dry-run (preview/diff + secretos requeridos) → confirmar
  (merge/overwrite), e historial de auditoría.
- Accesible desde **Configuración → Exportar / Importar**.

### Notas de portabilidad

`apply_import` escribe `config.json` directamente, **sin** exigir que
`workspace_root`/`docs_paths` existan en la máquina destino (eso rompería el caso
post-deploy). El operador corrige rutas luego desde el modal de proyecto, que sí
valida.

---

## B) Tickets ADO por usuario + checkbox "Mostrar todas"

### Backend

- `AdoClient.get_authenticated_user()` (`services/ado_client.py`): resuelve la
  identidad ADO del PAT vía `_apis/connectionData` (`unique_name` = email, que se
  compara contra `Ticket.assigned_to_ado`).
- `services/ado_identity.py`: persiste el mapeo `stackyUser→adoUser` en
  `data/ado_user_map.json` con timestamp de verificación.
- `GET /api/tickets/ado-user?project=&refresh=` → resuelve/cachea la identidad.
- `GET /api/tickets?assigned_to=<uniqueName|me>` → filtra por asignado. `me`
  resuelve la identidad del operador (si no se puede resolver, no filtra).

### Frontend (`pages/TicketBoard.tsx`)

- Checkbox **"Mostrar todas las tareas"** — **arranca marcado** (decisión de
  negocio). Al desmarcar entra en modo "Mis tareas": se poda la jerarquía a los
  nodos asignados al operador (épica visible si tiene alguna tarea propia).
- Si la identidad ADO no se puede vincular, se muestra un aviso y **no** se filtra
  (evita lista vacía confusa).
- `hooks/useLocalStorageState.ts`: persiste en `localStorage` los filtros de la
  vista (`search`, `onlyPending`, `viewMode`, `showAll`) y los rehidrata al volver.

---

## Tests

- `tests/test_config_transfer.py` — checksum + sin secretos, detección de
  manipulación, rechazo de schema más nuevo, dry-run → merge idempotente,
  auditoría, export selectivo.
- `tests/test_ado_identity.py` — roundtrip y scoping por proyecto del mapeo.
- `tests/test_tickets_assigned_filter.py` — filtro `assigned_to` en la lista.
