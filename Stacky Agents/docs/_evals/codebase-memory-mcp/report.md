# F6 — Reporte final versionado: codebase-memory-mcp

> Plan 76 — Fase F6 (DoD global ítem **h**: reporte reproducible con comandos exactos).
> Generado: 2026-07-02 por supervisión de implementaciones (4º eslabón del pipeline).
> Repo evaluado: https://github.com/DeusData/codebase-memory-mcp · Último release inspeccionado: v0.8.1.
> Este reporte CONSOLIDA los hallazgos de F0-F4; es **reproducible** con los comandos de la §4.

---

## 1. Resumen ejecutivo

**Decisión final: (B) ADOPTAR-OPCIONAL-NO-CORE** (copiada de `decision.md`).

`codebase-memory-mcp` es un servidor MCP externo que indexa un codebase en un knowledge
graph persistente (tree-sitter, grafo de símbolos) y expone 14 tools MCP para queries
estructurales sub-ms. Cubre una brecha real de Stacky: no existe índice de código del
proyecto queryable en runtime (el agente usa grep/Read; las queries "dónde está X" /
"quién llama a Y" son las más caras en tokens).

- **Opción A (ADOPTAR-CORE) → DESCARTADA** en F1: D3 (SLSA-3) = DUDOSO ≠ APROBADO (ver `decision-A-gate.md`).
- **Opción C (RECHAZAR) → NO APLICA:** ningún criterio está RECHAZADO (todos APROBADO o DUDOSO).
- **Opción B (ADOPTAR-OPCIONAL-NO-CORE) → ADOPTADA:** D2+D6+D7+D8 APROBADO; D1/D5/D9 DUDOSO
  (no RECHAZADO). Default OFF → Stacky byte-idéntico sin intervención del operador; flag
  `STACKY_CODEBASE_MEMORY_MCP_ENABLED` en FLAG_REGISTRY permite activación desde la UI.

**Scorecard D1-D9 resumida** (ver §3 para el detalle con evidencia):

| APROBADO | DUDOSO | RECHAZADO |
|----------|--------|-----------|
| D2, D4, D6, D7, D8 | D1, D3, D5, D9 | — (ninguno) |

**Caveats que el operador debe cerrar antes de activar el flag** (HITL, ver `decision.md` §Justificación):
1. **D1/Copilot Pro:** compatibilidad MCP de Copilot Pro NO confirmada (solo Claude Code y Codex).
2. **D3/Supply-chain:** correr `gh attestation verify <binary> --repo DeusData/codebase-memory-mcp` antes de producción.
3. **D5/Tokens:** completar la PoC de `poc-metrics.md` (métricas aún pendientes).
4. **D9/Egress:** completar el sandbox deny-egress de `poc-metrics.md` antes de usar en repo del cliente.

> **No se recomienda activar el flag** hasta que el operador complete la PoC de `poc-metrics.md`
> y confirme D9 (egress local). Si D9 resulta RECHAZADO tras la PoC, el flag debe desactivarse y
> eliminarse (regla de `decision.md`).

---

## 2. Hallazgos E1-E7 (links a notas F0-F3)

| Hallazgo | Qué responde | Veredicto | Fuente |
|----------|--------------|-----------|--------|
| **E1** — Repo + README | Confirmación del repo, 14 tools MCP, config Claude/Codex, clave de server `"codebase-memory-mcp"` ≠ `"stacky"` (coexistencia sin colisión) | — (input) | `notes-E1-E2-E4-E7.md` §E1 |
| **E2** — SLSA-3 vs releases reales | Cosign bundles + gh attestation + SBOM SPDX + SHA-256 presentes; sin cert formal 3rd party ni reproducibilidad | **D3 DUDOSO** | `notes-E1-E2-E4-E7.md` §E2, `decision-A-gate.md` |
| **E3** — PoC tokens + egress | **PENDIENTE de ejecución manual** (sandbox no automatizable en CI de Stacky). Métricas `(pendiente)` en `poc-metrics.md`. Estimación cualitativa: reducción estructural esperada en queries "dónde está X". | **D5 DUDOSO, D9 DUDOSO** | `poc-metrics.md`, `queries.md` |
| **E4** — Solapamiento con índices Stacky | Complementario: REPO_MAP.md es estático no-queryable; MCP interno sirve skills (no código). Dominios distintos. | **D4 APROBADO** | `notes-E1-E2-E4-E7.md` §E4, `integration-3-runtimes.md` |
| **E5** — Integración 3 runtimes | Claude Code ✓, Codex ✓, Copilot Pro sin confirmar. Guías de instalación por runtime. | **D1 DUDOSO** | `integration-3-runtimes.md`, `install-claude-code.md`, `install-codex.md`, `install-copilot-pro.md` |
| **E6** — Mantenimiento | Watcher automático + `update` manual, crecimiento lineal. | **D6 APROBADO** | `maintenance-model.md` |
| **E7** — Licencia | MIT (compatible con uso interno comercial, sin copyleft). | **D7 APROBADO** | `notes-E1-E2-E4-E7.md` §E7 |

**D2 (Lenguajes) y D8 (Windows)** se deciden en E1: 158 lenguajes vía tree-sitter (Python/TS/C# en tier "Good"; SQL/Markdown vía generic/text); binary nativo `codebase-memory-mcp-windows-amd64.zip` disponible. → **D2 APROBADO, D8 APROBADO.**

---

## 3. Scorecard D1-D9 completa

| # | Criterio | Veredicto | Evidencia |
|---|----------|-----------|-----------|
| D1 | Compatibilidad MCP (3 runtimes) | **DUDOSO** | Claude Code APROBADO, Codex APROBADO, Copilot Pro sin confirmar — `integration-3-runtimes.md` |
| D2 | Lenguajes (Python, C#, TS, SQL, Markdown) | **APROBADO** | 158 langs vía tree-sitter; Python/TypeScript/C# en tier "Good" — `notes-E1-E2-E4-E7.md` |
| D3 | Seguridad / SLSA-3 | **DUDOSO** | Cosign bundles + gh attestation presentes, claim SLSA-3 en README, sin cert formal 3rd party — `decision-A-gate.md` |
| D4 | Solapamiento con índices Stacky | **APROBADO** | Complementario: REPO_MAP.md estático, MCP interno sirve skills (no código). Claves distintas confirman coexistencia — `integration-3-runtimes.md` |
| D5 | Costo de tokens | **DUDOSO** | PoC sandbox pendiente; arquitectura de graph-query sugiere reducción real en queries estructurales — `poc-metrics.md` |
| D6 | Mantenimiento / actualización | **APROBADO** | Watcher automático + `update` manual, crecimiento lineal — `maintenance-model.md` |
| D7 | Licenciamiento | **APROBADO** | MIT — `notes-E1-E2-E4-E7.md` |
| D8 | Soporte Windows | **APROBADO** | Binary nativo `codebase-memory-mcp-windows-amd64.zip` — `notes-E1-E2-E4-E7.md` |
| D9 | Egress / exfiltración | **DUDOSO** | README: "100% locally, no telemetry". PoC sandbox pendiente — `poc-metrics.md` |

**Aplicación de reglas de decisión** (sección 4 del plan): A descartada (D3≠APROBADO); C no aplica
(ninguno RECHAZADO); B adoptada con los caveats de la §1.

---

## 4. Reproducibilidad — comandos exactos

### 4.1 Verificación SLSA-3 / D3 (release v0.8.1)
```bash
gh release download v0.8.1 --repo DeusData/codebase-memory-mcp \
  --pattern "codebase-memory-mcp-windows-amd64.zip" \
  --pattern "codebase-memory-mcp-windows-amd64.zip.bundle"
gh attestation verify codebase-memory-mcp-windows-amd64.zip \
  --repo DeusData/codebase-memory-mcp
```
> Estado 2026-06-30: comando **no ejecutado** en el entorno de evaluación (sin `gh` CLI con
> permisos de download de releases externos). Evidencia estructural (bundles + attestation +
> SBOM + checksums + claim SLSA-3) constatada en los releases. Ver `decision-A-gate.md`.

### 4.2 PoC de tokens + egress (D5, D9) — `queries.md`
Sub-árbol DEFAULT: `Stacky Agents/backend` (Python) + `Stacky Agents/frontend/src` (TypeScript).
Commit SHA base: HEAD de `codex/subida-cambios-pendientes` al 2026-06-30. Runtime: Claude Code CLI.
```bash
# Indexar el sub-árbol registrando el commit SHA:
git -C "N:\GIT\RS\STACKY\Stacky" rev-parse HEAD > commit_sha.txt
C:\tools\codebase-memory-mcp\codebase-memory-mcp.exe index_repository \
  --path "N:\GIT\RS\STACKY\Stacky\Stacky Agents"
# Modo baseline (sin MCP) vs Modo MCP (--mcp-config apuntando al server):
#   correr las 10 queries Q1-Q10 de queries.md en ambos modos y comparar tokens.
# Gate egress (deny-egress): Windows Firewall con regla de bloqueo de salida para el proceso.
```
10 queries estructurales canónicas (Q1-Q10): ver tabla en `queries.md` (ej. Q1 "¿dónde se define
`build_agent_env`?", Q2 "¿quién llama a `mcp_installation_status`?", ..., Q10 "¿qué endpoints
registra el blueprint `api_bp`?"). Métricas a completar: `tokens_grep_promedio`, `tokens_mcp_promedio`,
`delta_tokens`, `delta_pct`, `latencia_p50/p95_ms`, `index_time_seconds`,
`sin_ejecucion_de_codigo`, `egress_local_only` — todas `(pendiente)` en `poc-metrics.md`.

**Criterios de aceptación de la PoC** (`queries.md`): `delta_tokens > 0` → D5 APROBADO/DUDOSO;
`sin_ejecucion_de_codigo == true`; `egress_local_only == true` → D9 APROBADO.

### 4.3 Estimación automatizada (Plan 80, opt-in, no telemetría)
`services/codebase_memory_mcp_wiring.py::estimate_query_savings(chars_baseline, chars_mcp_response)`
— heurística pura ~4 chars/token. El operador la invoca a mano por cada query Q1-Q10:
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -c "from services.codebase_memory_mcp_wiring import estimate_query_savings; print(estimate_query_savings(<chars_baseline>, <chars_mcp_response>))"
```
`GET /api/codebase-memory-mcp/savings` expone el agregado honesto (`samples: 0`, `delta_pct: null`)
hasta que existan muestras reales.

### 4.4 Instalación (si el operador activa el flag) — `decision.md` §4 + `install-*.md`
1. Descargar `codebase-memory-mcp-windows-amd64.zip` de https://github.com/DeusData/codebase-memory-mcp/releases
2. Verificar firma: `gh attestation verify <zip> --repo DeusData/codebase-memory-mcp`
3. Extraer en `C:\tools\codebase-memory-mcp\`
4. Indexar: `codebase-memory-mcp.exe index_repository --path <repo>`
5. Configurar MCP por runtime: `install-claude-code.md`, `install-codex.md`, `install-copilot-pro.md`
6. Activar `STACKY_CODEBASE_MEMORY_MCP_ENABLED` desde la UI (HarnessFlagsPanel, categoría "avanzado")

---

## 5. Artefactos F5 ya implementados (estado del flag)

- Flag `STACKY_CODEBASE_MEMORY_MCP_ENABLED` default OFF, env_only=False (UI-editable), categoría
  `avanzado` — `services/harness_flags.py`. Byte-idéntico con flag OFF verificado por
  `test_plan76_ratchet_byteidentical.py` (token `"codebase-memory-mcp"`, NO el genérico `mcpServers` — [C10]).
- Endpoint `GET /api/codebase-memory-mcp/status` — `api/codebase_memory_mcp.py` (centinela de rutas:
  `test_plan76_routes_registered.py`).
- Helpers puros de estado/guías — `services/codebase_memory_mcp_status.py`.
- **Stacky NO empaqueta el binario externo** (regla del plan: solo expone estado + guía de instalación).

---

## 6. Estado de completitud

- F0-F4 completos (notas + decisión + gate A + PoC protocol). **E3 (PoC) queda como procedimiento
  pendiente para el operador** — sus métricas numéricas no existen hasta la ejecución manual; no se
  inventaron (cero alucinación: `[NO_VERIFICADO]` / `(pendiente)`).
- F5 implementado (flag + endpoint + guías + tests + centinela de rutas + ratchet byte-idéntico).
- F6 (este reporte) + ratchet `test_plan76_ratchet_byteidentical.py` (3 casos) + `test_plan76_routes_registered.py`.

**Acción HITL pendiente:** el operador debe revisar esta decisión, completar la PoC (§4.2) para
confirmar D5/D9, y activar el flag cuando esté listo.
