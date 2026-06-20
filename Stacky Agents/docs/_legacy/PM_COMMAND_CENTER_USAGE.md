# PM Command Center — Guía de uso

Cómo operar PM Intelligence Suite desde el día a día como Project Manager o
Tech Lead. Para diseño y contratos arquitectónicos ver
[`11_PM_INTELLIGENCE_SUITE.md`](./11_PM_INTELLIGENCE_SUITE.md).

> ⚠️ **Versión**: Fase 1 (determinístico) + Fase 2 (IA advisory)
> Fase 3 (publicación a ADO con approval) NO está implementada.
> Todas las recomendaciones IA son **advisory only** y NO se publican a ADO.

---

## Tabla de contenidos

1. [Arranque rápido](#1-arranque-rápido)
2. [Configuración](#2-configuración)
3. [Flujo end-to-end recomendado](#3-flujo-end-to-end-recomendado)
4. [Endpoints REST por capacidad](#4-endpoints-rest-por-capacidad)
5. [Tracking de tokens y costo USD](#5-tracking-de-tokens-y-costo-usd)
6. [Troubleshooting](#6-troubleshooting)
7. [Cómo ajustar el gasto](#7-cómo-ajustar-el-gasto)

---

## 1. Arranque rápido

### Pre-requisitos

- Proyecto activo en Stacky Agents con `issue_tracker.type = "azure_devops"` en
  su `projects/<NOMBRE>/config.json`.
- `ADO_PAT` configurado en `backend/.env` o `Tools/PAT-ADO`.
- Backend Stacky Agents corriendo en `localhost:5050`.
- Frontend en `localhost:5173` (Vite dev).

### Primer uso (3 pasos)

```bash
# 1) Backend levantado
cd "Stacky Agents/backend"
python -m flask run --port 5050

# 2) Frontend levantado (otra terminal)
cd "Stacky Agents/frontend"
npm run dev
```

3) Abrir http://localhost:5173 → tab **📊 PM** → click **↻ Sync ADO**.

El backend trae el sprint actual de ADO, calcula KPIs y detecta riesgos
determinísticos. El frontend muestra el dashboard.

---

## 2. Configuración

### Variables de entorno relevantes

Las del PM Intelligence Suite se setean en `backend/.env`:

| Variable | Default | Para qué |
|---|---|---|
| `STACKY_PM_LLM_BACKEND` | `mock` | Backend de LLM. Valores: `mock` (sin red, JSON predecible) o `anthropic` (Claude real). |
| `ANTHROPIC_API_KEY` | (vacía) | API key de Claude. Obligatoria si `STACKY_PM_LLM_BACKEND=anthropic`. |
| `LLM_BACKEND` | `mock` | Variable global de Stacky. PM la usa como fallback si no hay override. |

### Para probar con Claude real

```bash
# backend/.env
STACKY_PM_LLM_BACKEND=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

Y reiniciar el backend. Las llamadas IA ahora pegan a Claude real y el costo
se calcula con pricing oficial. **El backend mock sigue funcionando para
tests sin red ni API key.**

### Modelos soportados

Definidos en `services/pm/pm_llm_client.py::PRICING` (USD por 1M tokens):

| Modelo | Input | Output | Cuándo usarlo |
|---|---|---|---|
| `claude-haiku-4-5` | $1.00 | $5.00 | Sentiment analysis (rápido + barato). Default. |
| `claude-sonnet-4-6` | $3.00 | $15.00 | Recommendations (requiere más razonamiento). |
| `claude-opus-4-7` | $15.00 | $75.00 | Casos complejos. Costo alto — usar con criterio. |
| `mock-1.0` | $0.00 | $0.00 | Tests y eval fixtures locales. |

El modelo se pasa por endpoint (body `{model: "..."}`). Si no se especifica,
default es `claude-haiku-4-5` para sentiment y `claude-sonnet-4-6` para
recommendations.

---

## 3. Flujo end-to-end recomendado

### A. Por la UI

1. **Sync ADO** — botón superior del PM Command Center. Trae el sprint
   actual, calcula KPIs, detecta riesgos. ~5-30s según tamaño del sprint.
2. **Revisar Sprint Health Card** — completion %, items bloqueados, días
   restantes, aging promedio, cycle time. Si hay `data_quality_warnings`
   (ej. >25% sin estimación), aparecen en banner amarillo.
3. **Revisar Risk Feed** — riesgos detectados por reglas deterministas.
   Hacer **Acknowledge** sobre los que ya fueron tratados.
4. **(Opcional) Run sentiment evals** — en el panel AI Components, click
   "Run sentiment evals". Si el gate pasa (verde), se habilita análisis IA.
5. **(Opcional) Indexar comentarios** — Comments Explorer → ingresar ADO ID
   → "Fetch & index" → "Analyze sentiment".
6. **(Opcional) Generate recommendations** — botón en AI Components.
   Requiere que el eval gate de `recommendation_engine` esté verde.
7. **Revisar AI Usage Panel** — abajo del todo. Tokens consumidos, costo USD
   por modelo y agente. Refresh automático cada 30s.

### B. Por API (cURL / Postman)

```bash
# Health check
curl http://localhost:5050/api/health

# 1. Sync sprint actual del proyecto activo
curl -X POST http://localhost:5050/api/pm/sync-ado \
  -H "Content-Type: application/json" \
  -H "X-User-Email: pm@empresa.com" \
  -d '{}'

# 2. Ver snapshot del sprint
curl 'http://localhost:5050/api/pm/sprint/current?project=RSPacifico'

# 3. Listar riesgos no acknowledged
curl 'http://localhost:5050/api/pm/risks?project=RSPacifico&acknowledged=false'

# 4. Acknowledge un riesgo
curl -X POST 'http://localhost:5050/api/pm/risks/RSK-abc123/acknowledge' \
  -H "Content-Type: application/json" \
  -d '{"acknowledged_by": "pm@empresa.com"}'

# 5. Indexar comentarios de un work item
curl -X POST http://localhost:5050/api/pm/comments/index \
  -H "Content-Type: application/json" \
  -d '{"ado_ids": [12345], "top_per_item": 50}'

# 6. Correr eval gate de sentiment
curl -X POST http://localhost:5050/api/pm/evals/run \
  -H "Content-Type: application/json" \
  -d '{"component": "comment_sentiment", "model": "claude-haiku-4-5"}'

# 7. Analizar sentiment de comments (requiere gate verde)
curl -X POST http://localhost:5050/api/pm/sentiment/analyze \
  -H "Content-Type: application/json" \
  -d '{"comment_ids": [1,2,3], "model": "claude-haiku-4-5"}'

# 8. Generar recommendations
curl -X POST http://localhost:5050/api/pm/recommendations/generate \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-6"}'

# 9. Ver token usage últimas 24h
curl 'http://localhost:5050/api/pm/ai/usage?since_hours=24'
```

---

## 4. Endpoints REST por capacidad

### Fase 1 (determinístico, sin IA)

| Método | Ruta | Qué hace |
|---|---|---|
| `POST` | `/api/pm/sync-ado` | Trae sprint actual + work items + revisiones, calcula KPIs y riesgos, persiste snapshot. |
| `GET` | `/api/pm/sprint/current` | Último snapshot persistido. |
| `GET` | `/api/pm/sprint/history?last_n=10` | Histórico de snapshots. |
| `GET` | `/api/pm/risks` | Filtros: `project`, `sprint_id`, `severity`, `acknowledged`. |
| `POST` | `/api/pm/risks/<risk_id>/acknowledge` | Marca riesgo como reconocido. |
| `GET` | `/api/pm/comments?ado_id=X` | Comentarios indexados de un work item. |
| `POST` | `/api/pm/comments/index` | Body `{ado_ids: [...]}`. Trae de ADO, aplica HTML strip + PII mask, persiste. |

### Fase 2 (IA advisory, bloqueada por eval gate)

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/api/pm/ai/usage` | Métricas de tokens + costo. Filtros: `since_hours`, `agent_kind`, `project`. |
| `GET` | `/api/pm/evals/components` | Lista de componentes IA con fixtures disponibles. |
| `POST` | `/api/pm/evals/run` | Body `{component, model}`. Ejecuta fixtures y devuelve si el gate pasó. |
| `POST` | `/api/pm/sentiment/analyze` | Body `{comment_ids, model}`. **412** si el eval gate de `comment_sentiment` no pasó. |
| `POST` | `/api/pm/recommendations/generate` | Body `{model}`. **412** si el gate de `recommendation_engine` no pasó. |
| `GET` | `/api/pm/recommendations` | Filtros: `project`, `sprint_id`, `priority`, `acknowledged`. |
| `POST` | `/api/pm/recommendations/<rec_id>/acknowledge` | PM marca recomendación como leída. |

### Códigos de respuesta

| Código | Significado |
|---|---|
| `200` | Operación OK. |
| `400` | `TRACKER_NOT_SUPPORTED` (proyecto no es ADO) o `INVALID_*` (parámetros mal formados). |
| `404` | `PROJECT_NOT_FOUND`, `NO_SNAPSHOT`, `RISK_NOT_FOUND`, etc. |
| `412` | `EVAL_GATE_NOT_PASSED` — los evals del componente IA no pasaron el threshold. |
| `502` | `ADO_UNREACHABLE` — error de red con Azure DevOps. |
| `503` | `ADO_CONFIG_ERROR` — PAT/org/project mal configurados. |
| `500` | Error inesperado (revisar logs). |

---

## 5. Tracking de tokens y costo USD

Cada llamada a LLM queda registrada en `pm_ai_usage` automáticamente. El
endpoint `GET /api/pm/ai/usage` agrega esos datos.

### Respuesta típica

```json
{
  "ok": true,
  "result": {
    "project": null,
    "since_hours": 24,
    "totals": {
      "calls": 47,
      "success": 45,
      "success_rate_pct": 95.74,
      "tokens_in": 18234,
      "tokens_out": 9512,
      "tokens_total": 27746,
      "cost_usd": 0.0823,
      "latency_ms_avg": 1247
    },
    "by_model": {
      "claude-haiku-4-5": {"calls": 35, "tokens_in": 10000, "tokens_out": 5000, "cost_usd": 0.035, "success": 34},
      "claude-sonnet-4-6": {"calls": 12, "tokens_in": 8234, "tokens_out": 4512, "cost_usd": 0.0472, "success": 11}
    },
    "by_agent": {
      "sentiment": {"calls": 30, ...},
      "recommendation": {"calls": 17, ...}
    },
    "recent_calls": [/* últimas 20 */],
    "advisory_only": true
  }
}
```

### En la UI

El **AIUsagePanel** muestra:
- **Costo USD** acumulado en la ventana seleccionada (1h / 24h / 3d / 7d)
- Tokens in/out/total
- Success rate
- Latencia promedio
- Breakdown por modelo y por agente
- Lista de últimas 20 llamadas con timestamp, agente, modelo, tokens, costo

Auto-refresh cada 30 segundos.

---

## 6. Troubleshooting

### "EVAL_GATE_NOT_PASSED" al llamar sentiment/recommendations

El componente IA tiene un threshold de calidad. Antes de tocar producción
hay que correr los evals y verificar que pasen.

```bash
# Correr evals primero
curl -X POST http://localhost:5050/api/pm/evals/run \
  -H "Content-Type: application/json" \
  -d '{"component": "comment_sentiment", "model": "claude-haiku-4-5"}'

# Si pass_rate < threshold → el gate bloquea por default.
# Para bypass en debug: body con "force_unsafe": true
```

**Cuándo es esperado**: el backend `mock` siempre falla el gate de sentiment
porque devuelve JSON neutro fijo. Para evals reales, configurar
`STACKY_PM_LLM_BACKEND=anthropic` + `ANTHROPIC_API_KEY`.

### "TRACKER_NOT_SUPPORTED"

El proyecto activo no es Azure DevOps. PM Intelligence Suite V1 solo soporta
ADO. Verificar `backend/projects/<NOMBRE>/config.json`:

```json
{
  "issue_tracker": {
    "type": "azure_devops",
    "organization": "...",
    "project": "..."
  }
}
```

### "NO_SNAPSHOT"

No hay snapshots PM para el proyecto. Hacer `POST /api/pm/sync-ado` primero.

### "ADO_UNREACHABLE" o "ADO_CONFIG_ERROR"

PAT inválido o expirado. Verificar `Tools/PAT-ADO` o `ADO_PAT` en `.env`.

### El AIUsagePanel muestra costos mucho más altos de lo esperado

Causas comunes:
- Estás usando `claude-opus-4-7` por accidente (×15 más caro que Haiku).
- El prompt incluye contexto innecesario (toda la historia del sprint cuando
  solo necesitabas el resumen). Revisar `services/pm/pm_prompts.py`.
- Loop sin idempotencia que regenera recommendations cada minuto. El
  `rec_id` es determinístico — re-generar mismo sprint actualiza in-place.

### El frontend muestra "Sin sprint sincronizado"

El sync nunca corrió o falló silenciosamente. Verificar logs del backend:

```bash
grep "pm.sprint_sync" backend/data/system_logs.db   # o consultar via UI
```

### PII en outputs del LLM

El `pm_llm_client` bloquea con `PiiLeakError` si detecta email/CUIT/CBU
crudos en input. Si ves PII en outputs:
1. Verificar que `pm_comment_indexer` aplicó `pii_masker.mask_text()` antes
   de persistir (campo `text_plain` no debe tener emails).
2. Si el modelo está incluyendo PII en su respuesta (ej. menciona un email
   que vio en el contexto), revisar el system prompt — puede haber falla
   en la regla "no menciones personas específicas".

---

## 7. Cómo ajustar el gasto

El usuario explícitamente pidió que cada llamada IA quede registrada para
ajustar gasto. Acá los patrones:

### Patrón 1 — Cap por sprint

Antes de cada sync, verificar el costo acumulado del sprint actual:

```bash
curl 'http://localhost:5050/api/pm/ai/usage?since_hours=168'  # 7 días
```

Si el `cost_usd_total` supera un umbral acordado (ej. $5/sprint), no correr
nuevas recomendaciones y/o cambiar de Sonnet a Haiku.

### Patrón 2 — Modelo por agente

Default actual:
- Sentiment → Haiku ($1/$5 por 1M tokens)
- Recommendations → Sonnet ($3/$15)

Si Haiku ya pasa el gate de recommendations, cambiar:

```bash
curl -X POST http://localhost:5050/api/pm/evals/run \
  -d '{"component": "recommendation_engine", "model": "claude-haiku-4-5"}'
```

Si gate verde → usar Haiku en producción (3-5× más barato).

### Patrón 3 — Análisis de comments por batch, no individual

Cada llamada a `/sentiment/analyze` tiene overhead fijo (system prompt
~500 tokens). Mejor llamar con 10-20 comment_ids juntos que con uno por
vez.

### Patrón 4 — Cache de recomendaciones por sprint

El `rec_id` es determinístico — re-generar para el mismo sprint actualiza
in-place. Si el sprint no cambió significativamente (mismo KPIs, mismos
riesgos), evitar re-generar. Solo regenerar cuando:
- Cambió el sprint health pill (verde → amarillo)
- Se agregaron riesgos HIGH/CRITICAL nuevos
- El operador descartó las anteriores

### Patrón 5 — Ventana de monitoreo

El selector del AIUsagePanel default a 24h. Para identificar picos:
- **1h**: si estás haciendo runs manuales y querés feedback inmediato
- **24h**: monitoreo diario
- **3d / 7d**: para revisar tendencias y ajustar presupuesto sprint a sprint

---

## Apéndice: relación con otras capacidades de Stacky

| Capacidad Stacky | Uso desde PM |
|---|---|
| `services/ado_client.py` | Reutilizado por `ado_pm_collector` para fetch_comments + work items. |
| `services/pii_masker.py` | Aplicado en `pm_comment_indexer` antes de persistir. |
| `services/stacky_logger.py` | Eventos PM emitidos con prefijo `pm.*` en `system_logs`. |
| `services/cost_estimator.py` | Pricing de modelos referencia el mismo cuadro. |
| `services/llm_router.py` | NO usado por PM (PM tiene su propio cliente `pm_llm_client` con tracking obligatorio). |

---

*Para reportar bugs o sugerir mejoras: abrir issue en el repo Stacky o
contactar al equipo de Stacky Agents.*
