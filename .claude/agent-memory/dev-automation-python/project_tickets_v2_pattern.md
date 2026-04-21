---
name: Patrón /api/tickets/v2 (FASE 4)
description: Endpoint unificado scan+metadata en dashboard_server.py; cómo extender sin romper v1
type: project
---

`/api/tickets/v2` unifica `_scan_tickets()` + `get_store().get_all()` en una sola respuesta. `/api/tickets` (v1) queda intacto.

**Why:** El frontend hacía N llamadas (una per-ticket) a `/api/tickets/<id>/metadata` para pintar badges de color, tags, commits y notas. Con 30+ tickets eso eran 30+ requests por refresh. v2 colapsa todo en una sola llamada que hereda los cachés de sus componentes (scan: 3s TTL; store: mtime-cache).

**How to apply:**
- Si agregás un campo nuevo a `TicketMetadata` (ticket_metadata_schema.py), hay que actualizar `_v2_metadata_patch_from()`, `_v2_empty_metadata_patch()` y la lista `_V2_METADATA_FIELDS` en dashboard_server.py — las tres viven juntas.
- Indicadores derivados (`has_commits`, `has_notes`, `metadata_stale`) se calculan en `_v2_metadata_patch_from()`; threshold de stale por default 15 min, configurable vía param.
- El indexador (`MetadataIndexer`) se publica en `globals()["_metadata_indexer"]` desde el startup en `__main__` para que `_v2_metadata_status()` lo lea. En tests/test_client el slot queda en `None` y degrada a `running=False`.
- El filtro `?project=` es nominal: `_scan_tickets()` es siempre del proyecto activo (`_get_runtime()`), por eso `v2` devuelve `filter_mismatch=True` cuando piden otro proyecto en lugar de intentar cruzar scans.
- Frontend (dashboard.html): `TM.refreshMetadataBulk()` usa v2 en un solo fetch y cae a `TM.refreshMetadata(ids)` per-ticket si el servidor no tiene v2 (compat con deploys viejos).
