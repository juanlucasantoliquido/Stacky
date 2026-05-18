# PM Intelligence Suite — Plan v2 (Realista · Stacky-Aligned)

> Versión: 2.0 · Fecha: 2026-05-16
> Autor: evaluación arquitectónica sobre el plan original v1
> Estado: PROPUESTA — requiere aprobación humana antes de cualquier implementación

---

## 0. Contexto de evaluación

### Estado real de Stacky Agents (verificado en repo)

| Capacidad | Estado real |
|---|---|
| Flask backend + SQLAlchemy | Existente (`app.py`, `models.py`, `db.py`) |
| ADO client con `fetch_comments`, `post_comment`, `update_work_item` | Existente (`services/ado_client.py`) |
| AgentExecution + system_logs (SSE) | Existente (`models.py`, `api/logs.py`) |
| PII masking (`pii_masker.py`) | Existente y funcional (FA-37) |
| Egress policies (`egress_policies.py`) | Existente y funcional (FA-41) |
| Contract validator (`contract_validator.py`) | Existente — aplica a outputs de agentes, NO a datos PM |
| Multi-LLM routing (Claude Haiku/Sonnet/Opus) | Existente (`services/llm_router.py`) |
| Sprint / velocity / iteration data de ADO | **NO existe** — cero código en `services/` |
| KPI engine / forecast / riesgo probabilístico | **NO existe** |
| Módulos PM (11 services separados del plan v1) | **NO existen** |
| Tablas PM (10 tablas nuevas del plan v1) | **NO existen** |
| Eval fixtures para componentes IA | **NO existen** — solo tests de agentes generales |

### Inconsistencias detectadas en el plan v1

1. **Modelo de LLM**: el plan v1 menciona "GPT-4o". Stacky usa Claude (Haiku/Sonnet/Opus via `llm_router.py`). Inconsistencia que invalida cualquier prompt engineering del plan original.
2. **"PII masking ya existe"**: correcto y verificado, pero el plan lo trata como base para PM analytics — hay que evaluar si el `mask_map` in-memory es suficiente para datos de sprint (no persiste entre requests, by design).
3. **"Egress controls ya existen"**: correcto, pero el plan no define qué `data_class` se asignaría a datos de sprint/velocity — esa configuración no existe.
4. **"Contract validator ya existe"**: correcto, pero el validator actual valida outputs de agentes (markdown, JSON structure). No está diseñado para validar payloads PM como `sprint_summary` o `risk_item`.

---

## 1. Alcance MVP — lo que entra en v1

### Principio de corte

Solo entra lo que puede construirse encima de lo que YA existe sin romper contratos actuales, y que genera señal medible en menos de 6 semanas.

### Capacidades MVP (Fase 1 — 6 semanas)

| ID | Capacidad | Tipo | Capa |
|---|---|---|---|
| PM-01 | ADO Sprint Sync: traer iteration path, fechas, work items por sprint | `service` (extiende `ado_client`) | `integration` |
| PM-02 | KPI Calculator: velocity, bug rate, blocked %, completion rate — heurísticas simples, **sin IA** | `service` puro | `unit/integration` |
| PM-03 | Sprint Dashboard endpoint: `GET /api/pm/sprint/current` + `GET /api/pm/sprint/history` | `api blueprint` | `api_contract` |
| PM-04 | Risk Feed: categorías DELAY / BLOCKED / SCOPE_CREEP detectadas con reglas deterministas (no IA) | `service` puro | `integration` |
| PM-05 | Comment Indexer: almacena comentarios de work items con metadata — sin análisis IA todavía | `service` + 2 tablas | `integration` |
| PM-06 | SprintDashboard React component: muestra KPIs del sprint + risk feed | `component` | `component` |

**Lo que NO entra en MVP:**
- Recommendation engine con IA
- Simulation / what-if engine
- AI Insights Feed
- Forecast de velocidad
- Análisis semántico de comentarios
- Integración Jira/Mantis para PM (solo ADO en v1)

---

## 2. Contratos JSON — endpoints MVP

### PM-03a: `GET /api/pm/sprint/current`

**Request:** `?project=UbimiaPacifico`

**Response 200:**
```json
{
  "ok": true,
  "result": {
    "project": "UbimiaPacifico",
    "sprint": {
      "id": "UbimiaPacifico\\Sprint 42",
      "name": "Sprint 42",
      "start_date": "2026-05-05",
      "end_date": "2026-05-19",
      "days_remaining": 3
    },
    "kpis": {
      "velocity_current": 18,
      "velocity_avg_3sprints": 21,
      "completion_rate_pct": 72,
      "bug_rate_pct": 11,
      "blocked_items_count": 2,
      "scope_creep_items": 1
    },
    "risk_feed": [
      {
        "risk_id": "RSK-2026-05-001",
        "category": "DELAY",
        "severity": "HIGH",
        "description": "Velocity 14% por debajo de promedio 3 sprints con 3 días restantes",
        "affected_items": [12345, 12346],
        "detected_at": "2026-05-16T10:00:00Z",
        "rule": "velocity_deficit_gt_10pct"
      }
    ],
    "generated_at": "2026-05-16T10:05:00Z",
    "source": "ado_live",
    "human_review_required": false
  }
}
```

**Response 4xx/5xx:**
```json
{
  "ok": false,
  "error": "ADO_UNREACHABLE",
  "message": "No se pudo conectar con Azure DevOps",
  "detail": { "project": "UbimiaPacifico", "stage": "ado_sync" }
}
```

### PM-03b: `GET /api/pm/sprint/history`

**Request:** `?project=UbimiaPacifico&last_n=5`

**Response 200:**
```json
{
  "ok": true,
  "result": {
    "sprints": [
      {
        "name": "Sprint 41",
        "velocity": 21,
        "completion_rate_pct": 85,
        "bug_rate_pct": 8,
        "blocked_items_count": 1
      }
    ],
    "trend": {
      "velocity_direction": "declining",
      "avg_completion_rate_pct": 79
    }
  }
}
```

### PM-04: `GET /api/pm/risks`

**Response 200:**
```json
{
  "ok": true,
  "result": {
    "risks": [
      {
        "risk_id": "RSK-2026-05-001",
        "category": "DELAY | BLOCKED | SCOPE_CREEP | DATA_QUALITY",
        "severity": "LOW | MEDIUM | HIGH | CRITICAL",
        "description": "string",
        "affected_items": [12345],
        "rule": "string — nombre de la regla determinista que lo disparó",
        "detected_at": "ISO8601",
        "acknowledged": false,
        "acknowledged_by": null
      }
    ],
    "total": 1,
    "generated_at": "ISO8601",
    "ai_enriched": false
  }
}
```

**Nota de contrato**: `ai_enriched: false` es obligatorio en MVP. El campo existe para cuando se habilite la Fase 2 con aprobación humana.

### PM-05: `GET /api/pm/comments`

**Request:** `?ado_id=12345&limit=20`

**Response 200:**
```json
{
  "ok": true,
  "result": {
    "ado_id": 12345,
    "comments": [
      {
        "id": 1,
        "author": "juan.perez@ubimia.com",
        "date": "2026-05-15",
        "text_plain": "string — HTML strip, PII maskeado",
        "sentiment_label": null,
        "sentiment_score": null,
        "ai_analyzed": false
      }
    ],
    "total": 12,
    "pii_masked": true
  }
}
```

**Nota de contrato**: `sentiment_label` y `sentiment_score` son `null` en MVP. Existen en el schema para evitar breaking change cuando se habilite análisis IA en Fase 2.

---

## 3. Modelo de datos — tablas nuevas MVP

Solo 3 tablas (no 10). Cada una con migración reversible.

### `pm_sprint_snapshots`
```sql
CREATE TABLE pm_sprint_snapshots (
  id           INTEGER PRIMARY KEY,
  project      VARCHAR(80) NOT NULL,
  sprint_id    VARCHAR(200) NOT NULL,   -- ADO iteration path
  sprint_name  VARCHAR(200) NOT NULL,
  start_date   DATE,
  end_date     DATE,
  snapshot_json TEXT NOT NULL,          -- KPIs serializados
  source       VARCHAR(20) DEFAULT 'ado_live',
  captured_at  DATETIME NOT NULL
);
CREATE INDEX ix_pm_sprint_project_date ON pm_sprint_snapshots(project, captured_at);
```

### `pm_risk_items`
```sql
CREATE TABLE pm_risk_items (
  id             INTEGER PRIMARY KEY,
  project        VARCHAR(80) NOT NULL,
  sprint_id      VARCHAR(200),
  risk_id        VARCHAR(50) NOT NULL UNIQUE,
  category       VARCHAR(30) NOT NULL,   -- DELAY|BLOCKED|SCOPE_CREEP|DATA_QUALITY
  severity       VARCHAR(10) NOT NULL,
  description    TEXT,
  affected_items TEXT,                   -- JSON array de ado_ids
  rule           VARCHAR(100),
  detected_at    DATETIME NOT NULL,
  acknowledged   BOOLEAN DEFAULT 0,
  acknowledged_by VARCHAR(200),
  acknowledged_at DATETIME,
  ai_enriched    BOOLEAN DEFAULT 0
);
```

### `pm_work_item_comments`
```sql
CREATE TABLE pm_work_item_comments (
  id              INTEGER PRIMARY KEY,
  ado_id          INTEGER NOT NULL,
  project         VARCHAR(80) NOT NULL,
  author          VARCHAR(200),
  comment_date    DATE,
  text_plain      TEXT,                 -- HTML stripped, PII maskeado
  ai_analyzed     BOOLEAN DEFAULT 0,
  sentiment_label VARCHAR(20),          -- null hasta Fase 2
  sentiment_score REAL,                 -- null hasta Fase 2
  indexed_at      DATETIME NOT NULL
);
CREATE INDEX ix_pm_comments_ado_id ON pm_work_item_comments(ado_id);
```

**Rollback:** cada tabla tiene un `DROP TABLE IF EXISTS` en el script de rollback.

---

## 4. Componentes IA — Fase 2 (solo advisory, requiere evals)

Los siguientes componentes IA NO se habilitan en Fase 1. Se diseñan aquí para que la Fase 2 tenga contratos claros.

### 4.1 Comment Sentiment Analyzer

**Contrato de input:**
```json
{
  "analyzer_input_version": "1.0",
  "comments": [
    { "id": 1, "text_plain": "string — PII already masked" }
  ],
  "context": {
    "project": "string",
    "sprint_name": "string"
  }
}
```

**Contrato de output esperado (schema que el modelo DEBE respetar):**
```json
{
  "analyzer_output_version": "1.0",
  "results": [
    {
      "comment_id": 1,
      "sentiment_label": "positive | neutral | negative | blocking",
      "sentiment_score": 0.85,
      "flags": ["BLOCKER_MENTIONED", "RISK_SIGNAL", "COMMITMENT_CHANGE"],
      "confidence": 0.92
    }
  ],
  "model_used": "claude-haiku-4-5",
  "analysis_timestamp": "ISO8601"
}
```

**Gate de habilitación (todos deben pasar antes de habilitar publicación):**
- [ ] Eval fixture: 10 comentarios reales anonimizados + etiquetas correctas manuales
- [ ] Precision >= 0.80 en `sentiment_label`
- [ ] Flag detection recall >= 0.75 en `BLOCKER_MENTIONED`
- [ ] Zero hallucination de `flags` no definidos en el enum
- [ ] Aprobación explícita del PM/owner antes de activar `ai_enriched: true`

### 4.2 Recommendation Engine

**Contrato de input:**
```json
{
  "rec_input_version": "1.0",
  "sprint_summary": {
    "velocity_current": 18,
    "velocity_avg": 21,
    "completion_rate_pct": 72,
    "days_remaining": 3,
    "blocked_items_count": 2
  },
  "risk_feed": [ /* array de pm_risk_items */ ],
  "historical_sprints": [ /* últimos 3 snapshots */ ]
}
```

**Contrato de output:**
```json
{
  "rec_output_version": "1.0",
  "recommendations": [
    {
      "rec_id": "REC-2026-05-001",
      "priority": "P0 | P1 | P2",
      "category": "SCOPE | RESOURCE | PROCESS | RISK_MITIGATION",
      "action": "string — acción concreta, máx 100 chars",
      "rationale": "string — basado en datos concretos del input",
      "supporting_data": { "field": "value" },
      "confidence": 0.78,
      "publish_recommended": false,
      "human_approval_required": true
    }
  ],
  "model_used": "claude-sonnet-4-6",
  "advisory_only": true
}
```

**Regla de contrato**: `publish_recommended` SIEMPRE es `false` hasta que el operador lo aprueba explícitamente. `advisory_only: true` es inmutable en Fase 2. Se habilita `publish_recommended: true` solo en Fase 3, después de pasar evals.

**Gate de habilitación Fase 2 (advisory):**
- [ ] 5 eval fixtures con sprint data real anonimizada
- [ ] Validación: no inventa métricas que no estén en el input
- [ ] Validación: `confidence` correlaciona con accuracy en fixtures (R² >= 0.6)
- [ ] Sin recomendaciones de "despedir personas" o acciones punitivas
- [ ] Aprobación PM antes de mostrar en UI

**Gate adicional Fase 3 (publicación a ADO):**
- [ ] 15+ eval fixtures adicionales
- [ ] Human approval workflow implementado (operador firma cada recomendación)
- [ ] Rollback: borrado de comentario ADO publicado vía `DELETE /api/pm/recommendations/:id/publish`

### 4.3 Simulation Engine (What-If)

**Pospuesto a Fase 4.** No entra antes de que Recommendation Engine tenga evals completos y 30 días de uso en advisory mode. Motivo: la simulación requiere un modelo de causalidad sprint que hoy no existe como dato en el repo — inventarlo sin datos históricos produce señal falsa con alta confianza aparente.

---

## 5. Eval Fixtures mínimos (a crear antes de Fase 2)

```
evals/pm_intelligence/
  comment_sentiment/
    fixture_blocker_comment.json          -- "esto no va a llegar" → negative + BLOCKER_MENTIONED
    fixture_positive_update.json          -- "terminé la tarea" → positive
    fixture_scope_change.json             -- "agregamos 3 ítems nuevos" → neutral + COMMITMENT_CHANGE
    fixture_neutral_status.json           -- "en progreso" → neutral
    fixture_pii_already_masked.json       -- verificar que no se re-enmascara mal
  recommendation_engine/
    fixture_sprint_on_track.json          -- velocity OK, sin riesgos → sin recomendaciones urgentes
    fixture_velocity_drop_15pct.json      -- velocity baja → recomienda scope cut
    fixture_high_blocked_rate.json        -- 40% ítems bloqueados → recomienda reunión de desbloqueo
    fixture_scope_creep_detected.json     -- 5 ítems agregados mid-sprint → alerta
    fixture_no_hallucinated_metrics.json  -- verifica que el modelo no inventa datos fuera del input
  regression/
    unknown_category_blocker.json         -- categoría no definida en enum → debe fallar con error, no silencio
```

---

## 6. Integración con AgentExecution y system_logs existentes

Los eventos PM se registran en la tabla `system_logs` existente (no nueva tabla de logs) usando los tipos ya definidos:

```python
# Ejemplo de evento a emitir desde pm_sprint_service.py
stacky_logger.log_event(
    event_type="pm.sprint_sync",
    payload={
        "project": project,
        "sprint_id": sprint_id,
        "kpis_computed": True,
        "risks_detected": len(risks),
        "duration_ms": duration_ms
    }
)
```

Tipos de evento PM a registrar en `system_logs`:
- `pm.sprint_sync` — cada vez que se sincroniza un sprint desde ADO
- `pm.risk_detected` — cuando una regla determinista dispara un riesgo
- `pm.ai_analysis_requested` — cuando se solicita análisis IA (Fase 2+)
- `pm.ai_analysis_result` — resultado del análisis IA con `confidence`
- `pm.recommendation_published` — cuando el operador aprueba y publica (Fase 3+)
- `pm.recommendation_discarded` — cuando el operador descarta
- `pm.rollback_executed` — cuando se revierte una publicación

---

## 7. Gates de calidad por fase

### Fase 1 (MVP — sin IA)

| Gate | Criterio |
|---|---|
| Preflight ADO | `GET /api/pm/sprint/current` retorna `ok: false` con `error: ADO_UNREACHABLE` si PAT inválido, no excepción 500 |
| Contratos | Todos los endpoints respetan el schema definido en §2 (validado con `contract_validator.py` extendido) |
| Datos vacíos | `velocity_current: 0` nunca se trata como PASS — emite `risk: DATA_QUALITY` |
| Tests | Unit tests para KPI Calculator (velocity, bug_rate, completion_rate con datos de fixture) |
| Sin datos de prod en logs | `pii_masked: true` verificado en responses de comments |

### Fase 2 (IA advisory)

| Gate | Criterio |
|---|---|
| Evals | Todos los fixtures de §5 deben pasar antes de habilitar en UI |
| Human gate | No existe ruta de código que permita `publish_recommended: true` sin aprobación explícita |
| advisory_only lock | Campo `advisory_only` en la tabla `pm_ai_results` es immutable por API — solo DB admin puede cambiarlo |
| Rollback | `DELETE /api/pm/ai-results/:id` disponible antes de habilitar Fase 2 |

### Fase 3 (publicación a ADO) — no antes de 60 días post-Fase 2

| Gate | Criterio |
|---|---|
| Approval workflow | Endpoint `POST /api/pm/recommendations/:id/approve` con `approved_by` requerido |
| Audit trail | Cada publicación registra `pm.recommendation_published` en system_logs con `approved_by`, `rec_id`, `ado_id_target` |
| Rate limit | Máximo 3 publicaciones automáticas por sprint por proyecto |
| Rollback confirmado | `DELETE /api/pm/recommendations/:id/publish` borra el comentario ADO y registra `pm.rollback_executed` |

---

## 8. Seguridad

- Comentarios de ADO: se procesan siempre con `pii_masker.mask()` antes de persistir en `pm_work_item_comments.text_plain`. El texto original nunca se almacena.
- Datos de sprint (velocidad, estados): no contienen PII por definición — no requieren masking, pero sí egress policy class `"project_metrics"` que se agrega a `egress_policies` con `action: warn`.
- Recomendaciones IA que mencionan personas: si el output del LLM contiene referencias a personas identificables, `pii_masker` las detecta y bloquea la persistencia hasta revisión humana.
- Sin DML destructivo: ningún endpoint PM puede modificar work items de ADO excepto `POST /api/pm/recommendations/:id/publish` con aprobación explícita.

---

## 9. Roadmap reordenado por valor/riesgo

| Sprint | Entregable | Valor | Riesgo | Dependencia |
|---|---|---|---|---|
| S1 (sem 1-2) | PM-01: ADO Sprint Sync + `pm_sprint_snapshots` | Alto | Bajo | `ado_client` existente |
| S1 (sem 1-2) | PM-02: KPI Calculator (determinístico) | Alto | Bajo | PM-01 |
| S2 (sem 3-4) | PM-03: Sprint Dashboard endpoint | Alto | Bajo | PM-01, PM-02 |
| S2 (sem 3-4) | PM-04: Risk Feed (reglas determinísticas) | Alto | Bajo | PM-02 |
| S2 (sem 3-4) | PM-05: Comment Indexer (sin IA) + Unit tests | Medio | Bajo | `ado_client.fetch_comments` |
| S3 (sem 5-6) | PM-06: React SprintDashboard component | Medio | Bajo | PM-03 API estable |
| S3 (sem 5-6) | Eval fixtures comment sentiment (§5) | Alto | Bajo | PM-05 |
| S4 (sem 7-8) | **Eval gate** + aprobación humana → habilitar Fase 2 | — | — | Evals completos |
| S5+ | Fase 2: Comment Sentiment (advisory, sin publish) | Medio | Medio | Evals pasados + aprobación |
| S7+ | Fase 2: Recommendation Engine (advisory, sin publish) | Alto | Alto | Sentiment estable + 15 fixtures |
| S12+ | Fase 3: Publicación a ADO con approval workflow | Alto | Alto | 60 días Fase 2, audit trail |
| No antes de S16 | Simulation Engine | Medio | Muy alto | Datos históricos reales + model de causalidad |

---

## 10. Métricas que deben moverse

| Métrica | Baseline esperado | Target Fase 1 |
|---|---|---|
| `pm_sprint_sync_success_rate` | 0% (no existe) | >= 95% |
| `pm_risk_detection_false_positive_rate` | — | <= 20% (medido vs. juicio PM) |
| `pm_kpi_data_freshness_min` | — | <= 60 min en horario laboral |
| `pm_ai_hallucination_rate` | — (Fase 2) | 0% en campos enum |
| `pm_recommendation_approval_rate` | — (Fase 3) | >= 40% |
| `pm_rollback_rate` | — (Fase 3) | <= 5% de publicaciones |

---

## 11. Lo que se descarta del plan v1

| Item plan v1 | Por qué se descarta |
|---|---|
| 11 servicios PM separados desde sprint 1 | Over-engineering sin datos reales; empezar con 1 service, iterar |
| 10 tablas nuevas | 3 tablas alcanzan para MVP; el resto se agrega cuando el dato exista y sea necesario |
| Forecast de velocity con "heurística inventada" | Sin datos históricos en el sistema, el forecast es ruido con apariencia de señal |
| AI Insights Feed sin fuente clara | No existe fuente definida; posponer hasta tener comment index + sentiment con evals |
| Simulador desde sprint 6 | Requiere modelo de causalidad que no existe; sin él, simula cosas incorrectas |
| Integración Jira/Mantis para PM | `jira_client.py` y `mantis_client.py` existen para agentes, no para PM analytics — reutilizar con contrato claro en Fase 3 |
| 11 componentes React nuevos | 1 componente bien hecho en Fase 1 > 11 a medias |
| "GPT-4o" como modelo | Stacky usa Claude — reemplazar todo por `llm_router.py` con Claude Sonnet/Haiku |

---

## 12. Branch y PR cuando se implemente

```
feature/stacky-pm-sprint-sync          -- PM-01 + PM-02 + tablas
feature/stacky-pm-dashboard-api        -- PM-03 + PM-04 endpoints
feature/stacky-pm-comment-indexer      -- PM-05 + PII integration
feature/stacky-pm-sprint-dashboard-ui  -- PM-06 React component
qa/stacky-pm-eval-fixtures             -- fixtures §5
```

Cada PR debe incluir:
- Contrato JSON del endpoint (del §2 de este documento)
- Tests ejecutados (unit + integración)
- Evidence de que `pii_masked: true` se verifica en comments
- Confirmación de que no hay rutas de publicación automática a ADO sin human gate

---

*Fin del documento v2. Ningún item de este plan se implementa sin aprobación explícita del owner (Juan Luca Santoliquido).*
