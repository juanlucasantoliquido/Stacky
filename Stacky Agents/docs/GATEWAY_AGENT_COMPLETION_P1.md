# AgentCompletionGateway — P1 Shadow Mode

**Version:** 1.0  
**Phase:** P1 — Gateway shadow  
**Date:** 2026-05-14  
**Plan:** `docs/10_PLAN_CIERRE_PUBLICACION_AGENTES.md`

---

## Overview

The gateway provides a canonical endpoint for agent completion signals.  
In P1 it runs in **shadow mode only**: it simulates the full closure pipeline but does not mutate DB or ADO.

Feature flag: `STACKY_COMPLETION_GATEWAY` (env var)

| Value | Effect |
|---|---|
| `off` (default) | Endpoint returns 404. Legacy flow active. |
| `shadow` | Gateway simulates, compares with legacy, logs discrepancies. No writes. |
| `on` | Reserved for P5. Returns 501 if attempted. |

---

## Activating Shadow Mode

```bash
# .env or environment
STACKY_COMPLETION_GATEWAY=shadow
STACKY_AGENT_TOKEN=your-secret-token-here
```

No restart required between `off` and `shadow` if your deployment supports hot env-var updates (the flag is read per-request).

---

## Endpoint

```
POST /api/tickets/by-ado/{ado_id}/agent-completion
```

### Authentication

Required header: `X-Stacky-Agent-Token: <token>`  
Optional header: `X-User-Email: agent@domain.com` (traceability)

If the token is missing or incorrect → `401 auth_required`.

If `STACKY_AGENT_TOKEN` is empty (not set), any non-empty token is accepted (dev mode).

### Payload v1

```json
{
  "execution_id": 44,
  "agent_type": "functional",
  "status": "completed",
  "html_output_path": "Agentes/outputs/149/comment.html",
  "metadata": {
    "html_sha256": "abc123...",
    "agent_version": "AnalistaFuncionalPacifico@2026-05-14",
    "duration_ms": 184232
  },
  "reason": "fin de análisis funcional",
  "allow_synthetic_rescue": false,
  "_legacy_observed": {
    "ok": true,
    "current_status": "completed"
  }
}
```

**Required fields:** `agent_type`, `status`  
**Optional:** `execution_id` (if omitted, resolved automatically), `html_output_path`, `metadata`, `reason`, `allow_synthetic_rescue`, `_legacy_observed`

**Valid `status` values:** `completed` | `error` | `cancelled` | `needs_review`

**`_legacy_observed`** (optional): pass the response from the legacy `PATCH /stacky-status` endpoint to enable discrepancy detection.

### Execution Resolution Priority

1. `execution_id` explicit → must belong to ticket + be in `{running, queued}`.
2. Last active `AgentExecution` with matching `agent_type`.
3. If exactly ONE active execution (any agent_type) → use it + log `agent_type_mismatch=true`.
4. Zero active + `allow_synthetic_rescue=true` → plan shows synthetic rescue execution.
5. Zero active without flag → `409 no_active_execution`.

---

## Shadow Response (200)

```json
{
  "mode": "shadow",
  "ok": true,
  "would_succeed": true,
  "correlation_id": "uuid-v4",
  "ticket_id": 42,
  "execution_id": 44,
  "agent_type_resolved": "functional",
  "agent_type_mismatch": false,
  "html_sha256": "sha256-hex",
  "plan": [
    {"step": "resolve_execution", "description": "Usar AgentExecution id=44 status=running"},
    {"step": "validate_html", "description": "HTML válido sha256=abc123..."},
    {"step": "close_execution", "description": "AgentExecution.status → 'completed', completed_at=now()"},
    {"step": "ado_publish", "description": "ado_publisher.publish_from_execution(...)"},
    {"step": "ticket_status_transition", "description": "ticket_status.on_execution_end(...)"},
    {"step": "audit_seal", "description": "audit_chain.seal(execution_id)"}
  ],
  "errors": [],
  "discrepancies": [],
  "duration_ms": 42
}
```

When `would_succeed=false`, `errors` contains structured error objects and some plan steps will have `"skipped": true`.

---

## Error Codes

| HTTP | `error.code` | Cause |
|---|---|---|
| 400 | `payload_invalid` | Missing fields / bad types. |
| 401 | `auth_required` | Missing/invalid `X-Stacky-Agent-Token`. |
| 404 | `ticket_not_found` | ADO id not in local DB. |
| 404 | `gateway_disabled` | `STACKY_COMPLETION_GATEWAY=off`. |
| 409 | `no_active_execution` | No resolvable execution. |
| 409 | `execution_state_invalid` | Execution already terminal or wrong ticket. |
| 409 | `html_already_published` | Duplicate HTML (reserved for P2). |
| 422 | `html_invalid` | HTML validator rejected the file. |
| 500 | `internal_error` | Unhandled exception, includes `correlation_id`. |
| 501 | `not_implemented` | `STACKY_COMPLETION_GATEWAY=on` — not yet active. |

---

## Discrepancy Detection

When `_legacy_observed` is present in the payload, the gateway compares:

- `overall_success`: gateway would_succeed vs legacy ok.
- `stacky_status`: what gateway would set vs what legacy set.
- `execution_id`: which execution each resolved.

Divergences are logged as `SystemLog(source='completion_gateway', action='shadow.discrepancy_detected')` with full context.

---

## Observability

All gateway events write to `system_logs` (table `system_logs`) with `source='completion_gateway'`.

Key `action` values:

| Action | Meaning |
|---|---|
| `shadow.invocation` | Main gateway call with plan + result |
| `shadow.ticket_not_found` | Ticket missing in DB |
| `shadow.discrepancy_detected` | Divergence with legacy |
| `metric.completion_gateway` | Metric event per invocation |
| `metric.shadow_discrepancy` | Metric per discrepancy field |

Every log includes `correlation_id` in `context_json`.

---

## Example curl Invocation

```bash
# Activate shadow
export STACKY_COMPLETION_GATEWAY=shadow
export STACKY_AGENT_TOKEN=my-secret

# Call gateway
curl -s -X POST http://localhost:5050/api/tickets/by-ado/149/agent-completion \
  -H "Content-Type: application/json" \
  -H "X-Stacky-Agent-Token: my-secret" \
  -H "X-User-Email: agent@domain.com" \
  -d '{
    "execution_id": 44,
    "agent_type": "functional",
    "status": "completed",
    "html_output_path": "Agentes/outputs/149/comment.html",
    "metadata": {
      "agent_version": "AnalistaFuncionalPacifico@2026-05-14",
      "duration_ms": 184232
    },
    "reason": "fin de análisis funcional"
  }' | jq .
```

Expected response (happy path, shadow):
```json
{
  "mode": "shadow",
  "ok": true,
  "would_succeed": true,
  "correlation_id": "a1b2c3d4-...",
  "ticket_id": 38,
  "execution_id": 44,
  "agent_type_resolved": "functional",
  "agent_type_mismatch": false,
  "html_sha256": "e3b0c44...",
  "plan": [...],
  "errors": [],
  "discrepancies": [],
  "duration_ms": 89
}
```

---

## What Is NOT Done in P1

- DB schema migration (`UNIQUE(execution_id, html_sha256)` on `AgentHtmlPublish`) — P2.
- `AgentExecution.completion_source` column — P2.
- `workflow.json` declarative transitions — P3.
- Removal of ADO tools from agent allowlists — P3.
- UI recovery button — P4.
- Cutover to `on` mode — P5.

---

## Rollback

Set `STACKY_COMPLETION_GATEWAY=off` (or remove the env var). The endpoint returns 404 and the legacy `PATCH /api/tickets/by-ado/{ado_id}/stacky-status` remains the only write path. No DB changes needed.
