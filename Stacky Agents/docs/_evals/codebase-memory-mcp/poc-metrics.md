# F2 — PoC métricas de tokens + egress

> Plan 76 — Fase F2. Generado: 2026-06-30.  
> Estado: PoC PENDIENTE DE EJECUCIÓN MANUAL (sandbox no disponible en este entorno automatizado).

---

## Estado de la PoC

La PoC requiere:
1. Instalación del binario `codebase-memory-mcp` (descarga de GitHub releases)
2. Entorno sandbox con firewall de deny-egress para verificar D9
3. Ejecución de 10 queries en modo baseline vs MCP midiendo tokens de la transcripción API real

**Estos pasos no son automatizables en el entorno de CI de Stacky** (requieren GUI + instalación de binario externo + control de red).

---

## Estimación cualitativa (no reemplaza la medición)

Basado en la naturaleza de los 14 tools MCP:
- `search_graph("build_agent_env")` → una llamada MCP, retorna la definición directamente
- Baseline grep: el agente itera sobre archivos (`rg build_agent_env`, Read de matches, lectura de contexto) → varios turn-arounds de herramientas

La reducción de tokens en queries de "dónde está X" es structuralmente esperada. **No es medición.**

---

## Métricas requeridas (completar con PoC manual)

| Métrica | Valor | Notas |
|---------|-------|-------|
| commit_sha_subtree | (pendiente) | SHA del HEAD al momento de indexar |
| tokens_grep_promedio | (pendiente) | promedio Q1-Q10 modo baseline |
| tokens_mcp_promedio | (pendiente) | promedio Q1-Q10 modo MCP |
| delta_tokens | (pendiente) | tokens_grep - tokens_mcp |
| delta_pct | (pendiente) | delta / tokens_grep * 100 |
| latencia_p50_ms | (pendiente) | percentil 50 de latencia de query MCP |
| latencia_p95_ms | (pendiente) | percentil 95 de latencia de query MCP |
| index_time_seconds | (pendiente) | tiempo de indexación del sub-árbol |
| sin_ejecucion_de_codigo | (pendiente) | bool — indexación parsea estáticamente, no ejecuta |
| egress_local_only | (pendiente) | bool — deny-egress sandbox |

---

## Veredictos D5 y D9 (basados en evidencia disponible)

**D5 (costo de tokens):**  
= **DUDOSO** — PoC pendiente, pero arquitectura de graph-query estructural sugiere reducción real para queries de "dónde está X" / "quién llama a Y". Si `delta_tokens <= 0` tras la PoC → D5 = RECHAZADO → camino a (C).

**D9 (egress):**  
= **DUDOSO** — README dice "100% locally and collects no telemetry — your code, queries, environment, and usage never leave your machine." Sin verificación sandbox. Si PoC revela tráfico saliente no declarado → D9 = RECHAZADO → adopción descartada.

---

## Procedimiento para completar la PoC (operador)

1. Seguir `queries.md` (protocolo fijo, sub-árbol = Stacky por default)
2. Completar la tabla de métricas
3. Actualizar D5 y D9 en este archivo y en `decision.md`
4. Si D9 = RECHAZADO: actualizar F4/F5 y deshacer el flag
