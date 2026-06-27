# Plan 76 — Evaluación de adopción de `codebase-memory-mcp`

> **Estado:** PROPUESTO v1.
> **Pre-requisito:** ninguno (paralelo, aislado del bloque GitLab 70-75). No depende de ningún plan previo.
> **Roadmap:** Séptimo eslabón del bloque GitLab-Main 70-76 (desacople → pipeline infer agnóstico → trigger CI → creador pipelines → migrador ADO→GitLab → deep links → **eval codebase-memory-mcp**).
> **Versión doc:** v1 (2026-06-27). Reemplaza al boceto v0.

> **CHANGELOG boceto v0 → v1:**
> - Este plan es DISTINTO a los demás: su contenido **es la evaluación misma**; el "plan" es la decisión documentada (adoptar-core / adoptar-opcional / rechazar) + el procedimiento F0..F6 para llegar a ella con evidencia.
> - Supuesto crítico del boceto ("existe `repo_map.py` en Stacky") **REFUTADO por auditoría**: `repo_map.py` NO existe en el repo de Stacky (Glob `**/repo_map.py` devuelve vacío a 2026-06-27). En su lugar, el `CLAUDE.md` de Stacky Agents cita un `REPO_MAP.md` generado por un script externo. D4 (solapamiento) se reformula: no hay solapamiento real hoy; `codebase-memory-mcp` sería **complementario** a un futuro mapa estructural.
> - Riel supply-chain explícito (SLSA-3): F1 es el gate go/no-go de la opción A.
> - Scorecard D1-D8 y 3 opciones A/B/C incluidas como contenido del plan.
> - F0..F6 con archivos/símbolos EXACTOS (los del plan, no los del MCP externo), tests TDD, criterios binarios.

---

## 1. Objetivo y KPI

Evaluar rigurosamente si Stacky debe adoptar `codebase-memory-mcp` (https://github.com/DeusData/codebase-memory-mcp) como servidor MCP de indexación de codebase para los 3 runtimes del agente (Claude Code, Codex, GitHub Copilot Pro), y producir una **decisión documentada** (ADOPTAR-CORE / ADOPTAR-OPCIONAL-NO-CORE / RECHAZAR) con evidencia verificable.

**KPI global (DoD):** al cerrar el plan, el operador tiene:
1. Una decisión binaria accionable (A/B/C) con la scorecard D1-D8 completa y evidencia por criterio.
2. Si la decisión es (B): un flag `STACKY_CODEBASE_MEMORY_MCP_ENABLED` default OFF + documentación de instalación para el operador (SIN empaquetar el binario externo).
3. Un reporte versionado (`docs/_evals/codebase-memory-mcp/report.md`) con todos los hallazgos E1-E7, reproducible.

---

## 2. Por qué ahora / gap que cierra

- Stacky actualmente **no tiene un índice semántico del codebase** de los proyectos del operador (ej. RS/Pacífico: Python + C# + TS + SQL + Markdown); el agente descubre código grep-eando o leyendo archivos enteros (caro en tokens).
- `codebase-memory-mcp` promete indexar el codebase en un **knowledge graph persistente** con queries sub-ms, soporte multi-lenguaje, y consumo vía MCP estándar (compatible con los 3 runtimes).
- Existe una **referencia estructural** en Stacky (`REPO_MAP.md` citado en `CLAUDE.md`) generada por un script externo a Stacky (no `repo_map.py` interno — **refutado**, ver F0-E4), pero NO es un grafo queryable ni cubre repos externos del operador.
- Riesgo supply-chain (binario externo) hace que la decisión no sea trivial; requiere evaluación honesta y gate explícito.
- **Aislamiento:** este plan no toca código de runtime; si la decisión es (B), sólo añade un flag + docs. Si es (C), no añade nada.

**Anclajes verificados con evidencia de hoy:**
- Glob `**/repo_map.py` sobre el repo de Stacky → vacío. **No existe.**
- `Stacky Agents/CLAUDE.md` cita `REPO_MAP.md` como mapa estático generado por `python repo_map.py "<repo>" --write` — ese script vive fuera del repo o no está versionado en `Stacky Agents/backend`.
- Repo objetivo de la eval: https://github.com/DeusData/codebase-memory-mcp (mencionado en el boceto; F0-E1 confirma su existencia y lectura real).

---

## 3. Principios y guardarraíles

- **3 runtimes con paridad** (Codex, Claude Code, GitHub Copilot Pro): la evaluación verifica compatibilidad MCP con los 3; si uno solo no lo soporta, D1 baja.
- **Cero trabajo extra al operador**: cualquier integración es opt-in vía flag `STACKY_CODEBASE_MEMORY_MCP_ENABLED` default **OFF**, `env_only=False`. El operador sólo lo activa si decide instalar el MCP aparte.
- **Human-in-the-loop innegociable**: la decisión final la toma el operador con la scorecard; el plan produce evidencia, no decisión automática.
- **Mono-operador sin auth**: el MCP se instala en la máquina del operador; Stacky no distribuye credenciales ni binarios.
- **No degradar / backward-compatible**: con flag OFF (default), Stacky es byte-idéntico a hoy; F6 lo verifica con test.
- **TDD + funciones puras + ratchet + no falsos verdes**: donde haya código (F5 flag + report builder), TDD primero.
- **Seguridad supply-chain como riel EXPLÍCITO**: **sin firma SLSA-3 verificable, sin adopción core**. La opción A (ADOPTAR-CORE) requiere D3 APROBADO con evidencia fuerte de firma; si no, A queda descartada y sólo queda B o C.
- **Prohibido lo vago:** todo hallazgo citado con URL/evidencia; el reporte es reproducible.

---

## 4. Scorecard de decisión D1-D8 (cuerpo principal del plan)

Cada criterio se puntúa **APROBADO / DUDOSO / RECHAZADO** con evidencia en F4:

| # | Criterio | Pregunta | Peso |
|---|----------|----------|------|
| D1 | Compatibilidad MCP | ¿Se conecta a los 3 runtimes (Claude Code, Codex, Copilot Pro) sin código custom por runtime? | Alto |
| D2 | Lenguajes | ¿Cubre los lenguajes de RS/Pacífico (Python, C#, TS, SQL, Markdown)? | Alto |
| D3 | Seguridad / supply-chain | ¿El binario tiene firma SLSA-3 verificable Y build reproducible? ¿Origen confiable? | **Alto (gate A)** |
| D4 | Solapamiento con mapa estructural Stacky | ¿Aporta valor no cubierto por `REPO_MAP.md` u otro índice existente? | Medio |
| D5 | Costo de tokens | ¿Reduce tokens en queries estructurales reales de forma medible (delta > 0)? | Alto |
| D6 | Mantenimiento / actualización | ¿Cómo se actualiza el índice al cambiar el codebase (watch / re-index manual)? ¿Crece linealmente? | Medio |
| D7 | Licenciamiento | ¿Licencia compatible con uso interno de Stacky? | Alto |
| D8 | Soporte Windows | ¿Funciona en Windows (entorno del operador)? | Medio |

**Reglas de decisión (aplicadas en F4):**
- **(A) ADOPTAR-CORE** requiere: D3 = APROBADO (firma SLSA-3 verificable) **Y** D1+D2+D5+D7 todos APROBADO **Y** PoC F2 exitosa. Si D3 ≠ APROBADO, A queda **descartada**.
- **(B) ADOPTAR-OPCIONAL-NO-CORE** requiere: D1+D2+D7+D8 APROBADO **Y** D5 APROBADO o DUDOSO (delta > 0 pero modesto). D3 puede ser DUDOSO (riesgo asumido por el operador, opt-in).
- **(C) RECHAZAR** si: D3 = RECHAZADO, **o** D7 = RECHAZADO, **o** PoC F2 muestra delta = 0 (D5 = RECHAZADO), **o** D1 = RECHAZADO (no soporta los 3 runtimes).

---

## 5. Fases

### F0 — Investigación preliminar (E1, E2, E4, E7)

**Objetivo:** leer el repo objetivo y recolectar evidencia primaria para D1, D2, D3, D4, D7.

**Trabajo:**

```text
# Tareas de investigación (E1-E7 del boceto, reorganizadas por fase)
E1 — Confirmar repo: https://github.com/DeusData/codebase-memory-mcp
     - Leer README, releases, server.json, CLAIMS.
E2 — Verificar firma SLSA-3 contra releases REALES (no claims):
     - Descargar un release, verificar proveniencia (sigstore/cosign/slsa-verifier).
     - Si no hay firma o build no es reproducible → D3 = DUDOSO o RECHAZADO.
E4 — Comparar con REPO_MAP.md (mapa estructural de Stacky):
     - ¿Qué queries hace uno que el otro no?
     - REPO_MAP.md es estático (no queryable); codebase-memory-mcp es grafo dinámico.
     - Refutar "solapamiento con repo_map.py" (no existe): documentar que NO hay solapamiento real.
E7 — Leer LICENSE del repo para D7.
```

**Archivos exactos F0:**
- `docs/_evals/codebase-memory-mcp/notes-E1-E2-E4-E7.md` (NUEVO) — apuntes crudos de la investigación, con URLs y quotes textuales del repo.

**Tests F0 (no-TDD; es investigación):**
- No hay test de código. Criterio: el archivo `notes-E1-E2-E4-E7.md` existe y cita URLs reales del repo (no claims genéricas). Validación manual.

**Criterio binario F0:** el archivo de notas existe, cita la URL del release inspeccionado, y para D3 reporta `firmado-SLSA-3: sí/no` con evidencia (comando `slsa-verifier` corrido o screenshot del release).

**Impacto por runtime:** ninguno (sólo investigación).

**Flag F0:** ninguna.

**Trabajo del operador F0:** ninguno (lo hace el implementador del plan).

---

### F1 — Gate go/no-go de la opción A (verificación SLSA-3)

**Objetivo:** decidir si la opción A (ADOPTAR-CORE) es viable. Es el gate crítico del riel supply-chain.

**Trabajo:**

```python
# docs/_evals/codebase-memory-mcp/decision-A-gate.md (NUEVO)
# Contenido requerido:
# 1. Release inspeccionado (versión, fecha, URL).
# 2. Comando de verificación corrido (slsa-verifier / cosign verify-blob / gpg --verify).
# 3. Resultado: PASS / FAIL / N/A (no hay firma publicada).
# 4. Build reproducible: ¿hay provenance.json? ¿reproducible desde source?
# 5. Veredicto D3: APROBADO / DUDOSO / RECHAZADO.
# 6. Decisión: si D3 ≠ APROBADO → opción A DESCARTADA, sólo B o C siguen.
```

**Archivos exactos F1:**
- `docs/_evals/codebase-memory-mcp/decision-A-gate.md` (NUEVO).

**Tests F1:**
- No hay test de código. Criterio: el archivo existe y declara `D3 = APROBADO|DUDOSO|RECHAZADO` con el comando de verificación documentado (no claim vacío).

**Criterio binario F1:** si D3 = APROBADO (firma verificable), A sigue en carrera; si D3 = DUDOSO/RECHAZADO, A queda **descartada por escrito** en este archivo. Es el **riel supply-chain** operacionalizado.

**Impacto por runtime:** ninguno.

**Flag F1:** ninguna.

**Trabajo del operador F1:** ninguno.

---

### F2 — PoC sandbox con métricas de tokens (E3)

**Objetivo:** medir empíricamente si el MCP reduce tokens en queries estructurales reales sobre un sub-árbol de RS/Pacífico. Gate de D5.

**Trabajo:**

```text
# Setup PoC (sandbox, NO producción):
1. Levantar el MCP en un sandbox (VM desechable o contenedor Docker Windows/Linux).
2. Apuntarlo a un sub-árbol acotado de RS/Pacífico (ej. una carpeta de ~50 archivos Python/C#).
3. Correr un set de 10 queries estructurales canónicas:
   - "dónde se define X"
   - "quién llama a Y"
   - "lista los archivos del módulo Z"
   - "qué tipos se usan en W"
4. Medir tokens consumidos con vs sin MCP (grep puro vs query MCP) para las mismas queries.
5. Medir latencia (claim sub-ms vs real).
6. Confirmar que la indexación NO ejecuta código del repo (sólo parsea).

# Salida: docs/_evals/codebase-memory-mcp/poc-metrics.md
# Métricas requeridas:
# - tokens_grep_promedio, tokens_mcp_promedio, delta_tokens, delta_pct
# - latencia_p50, latencia_p95
# - index_time_seconds
# - sin_ejecucion_de_codigo: bool (true/false con evidencia)
```

**Archivos exactos F2:**
- `docs/_evals/codebase-memory-mcp/poc-metrics.md` (NUEVO) — tabla de métricas + conclusión D5.

**Tests F2:**
- No hay test de código. Criterio: el archivo existe, reporta `delta_tokens` numérico (no cualitativo), y declara `D5 = APROBADO|DUDOSO|RECHAZADO` con el delta como evidencia.

**Criterio binario F2:** `delta_tokens > 0` Y `sin_ejecucion_de_codigo == true` → D5 APROBADO o DUDOSO (según magnitud). Si `delta_tokens == 0` o negative → D5 = RECHAZADO (camino a opción C).

**Impacto por runtime:** ninguno (PoC en sandbox aislado).

**Flag F2:** ninguna.

**Trabajo del operador F2:** el operador provee acceso al sub-árbol de RS/Pacífico para la PoC (o aprueba usar un sub-árbol público ficticio si prefiere no exponer código real).

---

### F3 — Comparación con `REPO_MAP.md` + integración MCP en los 3 runtimes (E5, E6)

**Objetivo:** resolver D4 (solapamiento) y D1 (compatibilidad MCP con los 3 runtimes) + D6 (mantenimiento del índice).

**Trabajo:**

```text
# E5 — Integración MCP por runtime (D1):
- Claude Code CLI: declarar server en claude_desktop_config.json / settings.json (mcpServers).
  * Documentar JSON de config exacto que el operador pegaría.
- Codex CLI: confirmar soporte MCP (¿codex config?).
  * Si Codex NO soporta MCP → D1 = DUDOSO (2/3 runtimes).
- GitHub Copilot Pro (VS Code): confirmar soporte MCP vía extensión.
  * Documentar config VS Code.

# E6 — Mantenimiento del índice (D6):
- ¿Watch del filesystem? ¿re-index manual? ¿crece linealmente con el repo?
- Documentar el modelo de actualización.

# E4 (comparación con REPO_MAP.md — D4):
- REPO_MAP.md es estático, generado por script externo, NO queryable en runtime.
- codebase-memory-mcp es grafo dinámico, queryable vía MCP.
- Conclusión: complementarios, no duplicativos. D4 = APROBADO (aporta valor no cubierto).
```

**Archivos exactos F3:**
- `docs/_evals/codebase-memory-mcp/integration-3-runtimes.md` (NUEVO) — config MCP por runtime.
- `docs/_evals/codebase-memory-mcp/maintenance-model.md` (NUEVO) — modelo de actualización (E6).

**Tests F3:**
- No hay test de código. Criterio: ambos archivos existen; `integration-3-runtimes.md` declara `D1 = APROBADO|DUDOSO|RECHAZADO` por runtime; `maintenance-model.md` declara `D6`.

**Criterio binario F3:** los 2 archivos existen y declaran D1 y D6 con evidencia. Si alguno de los 3 runtimes no soporta MCP, D1 se documenta como DUDOSO (2/3) o RECHAZADO (<2/3).

**Impacto por runtime:** ninguno (sólo documentación).

**Flag F3:** ninguna.

**Trabajo del operador F3:** ninguno.

---

### F4 — Decisión final A/B/C con scorecard D1-D8

**Objetivo:** consolidar la evidencia de F0-F3 en una decisión binaria accionable aplicando las reglas de la sección 4.

**Trabajo:**

```python
# docs/_evals/codebase-memory-mcp/decision.md (NUEVO)
# Contenido requerido:
# 1. Scorecard D1-D8 con veredicto por criterio + URL de evidencia.
# 2. Decisión: A | B | C (mutuamente excluyente).
# 3. Justificación de la decisión (2-3 párrafos).
# 4. Si (B): prerequisitos de instalación que el operador debe cumplir.
# 5. Si (C): razón principal (ej. "D3 RECHAZADO: sin firma SLSA-3 verificable").
# 6. Próximos pasos (si A/B → F5; si C → F6 reporte + cerrar).
```

**Archivos exactos F4:**
- `docs/_evals/codebase-memory-mcp/decision.md` (NUEVO).

**Tests F4:**
- No hay test de código. Criterio: `decision.md` existe, declara A|B|C, y cada fila de la scorecard cita evidencia. La decisión es **consistente** con las reglas de la sección 4 (validación manual: si D3 ≠ APROBADO y la decisión es A → inconsistencia, rechazar).

**Criterio binario F4:** la decisión es consistente con las reglas; la scorecard está completa (8 filas).

**Impacto por runtime:** ninguno.

**Flag F4:** ninguna.

**Trabajo del operador F4:** el operador **revisa** `decision.md` y aprueba/rechaza la decisión (HITL). Si el implementador propone B pero el operador prefiere C (o viceversa), la decisión final la tiene el operador.

---

### F5 — Si decisión es (B): flag + docs de instalación para el operador

**Objetivo:** implementar el flag `STACKY_CODEBASE_MEMORY_MCP_ENABLED` default OFF + documentación de instalación. **SÓLO si F4 decidió (B).** Si (A) o (C), F5 se salta (o se adapta: A requeriría empaquetar el binario, descartado por riel supply-chain; C no añade nada).

**Trabajo:**

```python
# backend/config.py (editar)
# Añadir atributo:
class Config:
    ...
    STACKY_CODEBASE_MEMORY_MCP_ENABLED: bool = False  # default OFF, env_only=False
```

```python
# backend/services/codebase_memory_mcp_status.py (NUEVO, helper PURO)
def mcp_installation_status() -> dict:
    """Lee el flag y devuelve {enabled: bool, installed_hint: str}.
    No ejecuta el binario; sólo lee config + chequea si el config MCP del runtime
    está apuntado (path exists). Función PURA (sin red)."""

def build_installation_guide(runtime: str) -> str:
    """Genera el markdown de instalación para un runtime dado.
    runtime ∈ {'claude_code','codex','copilot_pro'}.
    Lee plantillas de docs/_evals/codebase-memory-mcp/install-*.md."""
```

**Archivos exactos F5:**
- `backend/config.py` (añadir atributo).
- `backend/harness_defaults.env` (añadir `STACKY_CODEBASE_MEMORY_MCP_ENABLED=false`).
- `backend/services/codebase_memory_mcp_status.py` (NUEVO) — helpers puros.
- `backend/api/codebase_memory_mcp.py` (NUEVO blueprint) — `GET /api/codebase-memory-mcp/status` retorna el estado + guía de instalación.
- `backend/app.py` (registrar blueprint).
- `frontend/src/components/HarnessFlagsPanel.tsx` (toggle categoría "Codebase Memory MCP").
- `frontend/src/components/CodebaseMemoryMcpCard.tsx` (NUEVO) — muestra estado + guía.
- `docs/_evals/codebase-memory-mcp/install-claude-code.md` (NUEVO) — pasos para Claude Code.
- `docs/_evals/codebase-memory-mcp/install-codex.md` (NUEVO) — pasos para Codex.
- `docs/_evals/codebase-memory-mcp/install-copilot-pro.md` (NUEVO) — pasos para Copilot Pro.

**Tests F5 (TDD primero):**
- Archivo: `backend/tests/test_plan76_codebase_memory_mcp.py`.
- Casos:
  1. `config.STACKY_CODEBASE_MEMORY_MCP_ENABLED` lee `False` por defecto.
  2. `mcp_installation_status()` con flag OFF → `{"enabled": False, ...}`.
  3. `mcp_installation_status()` con flag ON → `{"enabled": True, ...}`.
  4. `build_installation_guide("claude_code")` retorna markdown no vacío que cita `claude_desktop_config.json`.
  5. `build_installation_guide("codex")` retorna markdown no vacío.
  6. `build_installation_guide("copilot_pro")` retorna markdown no vacío.
  7. `build_installation_guide` con runtime inválido → levanta `ValueError`.
  8. **Pureza:** `mcp_installation_status` no hace red **[Patrón mock: sólo lee config]**.
  9. `GET /api/codebase-memory-mcp/status` con flag OFF → 200 con `enabled: false` + guía incluida.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan76_codebase_memory_mcp.py -q`.
- Frontend: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx tsc --noEmit` (0 errores).

**Criterio binario F5:** los 9 casos pasan; tsc 0 errores; flag default OFF confirmado; 3 guías de instalación existen.

**Impacto por runtime:** la integración MCP la instala el operador aparte (Stacky no empaqueta el binario); los 3 runtimes siguen operativos sin el MCP instalado (flag OFF).

**Flag F5:** `STACKY_CODEBASE_MEMORY_MCP_ENABLED` default **OFF**, `env_only=False` (UI).

**Trabajo del operador F5:** si decide usarlo, instala el MCP aparte siguiendo la guía (Stacky no lo empaqueta). Con flag OFF, nada cambia.

---

### F6 — Reporte final + ratchet (test byte-idéntico con flag OFF)

**Objetivo:** consolidar el reporte versionado y garantizar que el flag (si F5 se implementó) es byte-idéntico a OFF.

**Trabajo:**

```text
# docs/_evals/codebase-memory-mcp/report.md (NUEVO)
# Estructura:
# 1. Resumen ejecutivo (decisión A/B/C + scorecard resumida).
# 2. Hallazgos E1-E7 (links a los archivos de notas F0-F3).
# 3. Scorecard D1-D8 completa.
# 4. Decisión y justificación.
# 5. Si (B): pasos de instalación (link a F5 guides).
# 6. Reproducibilidad: comandos exactos para re-correr la evaluación.
```

**Archivos exactos F6:**
- `docs/_evals/codebase-memory-mcp/report.md` (NUEVO).
- `backend/tests/test_plan76_ratchet_byteidentical.py` (NUEVO) — si F5 se implementó, afirma que con flag OFF el comportamiento es byte-idéntico (no hay endpoints nuevos activos, no hay config MCP inyectada).

**Tests F6 (TDD primero, si F5 implementado):**
- Archivo: `backend/tests/test_plan76_ratchet_byteidentical.py`.
- Casos:
  1. Flag OFF → `GET /api/codebase-memory-mcp/status` devuelve `enabled: false` (no rota nada).
  2. Flag OFF → no se inyecta config MCP en ningún runtime (helper `build_installation_guide` no se llama automáticamente).
  3. Ratchet verde: registrar `test_plan76_*.py` en `HARNESS_TEST_FILES` (Plan 49).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan76_ratchet_byteidentical.py tests/conformance/test_harness_ratchet.py -q`.

**Criterio binario F6:** `report.md` existe y es reproducible; si F5 implementado, los 3 casos pasan; ratchet verde.

**Impacto por runtime:** ninguno.

**Trabajo del operador F6:** ninguno.

---

## 6. Las 3 opciones de decisión (mutuamente excluyentes)

- **(A) ADOPTAR-CORE**: se incluye en el bundle de Stacky, default ON. **Requiere D3 APROBADO con evidencia fuerte de firma SLSA-3 + PoC F2 exitosa + D1+D2+D5+D7 APROBADO.** No recomendado preliminar (riesgo supply-chain sobre core). **Si F1 descarta A (D3 ≠ APROBADO), esta opción se elimina.**
- **(B) ADOPTAR-OPCIONAL-NO-CORE** *(recomendación preliminar, sujeta a F0-F4)*: el operador puede activarlo por proyecto vía flag `STACKY_CODEBASE_MEMORY_MCP_ENABLED` default OFF. Stacky no lo empaqueta; el operador lo instala aparte y Stacky sólo describe cómo. Compatible con Windows, multi-lenguaje, reduce tokens en queries estructurales, riesgo supply-chain asumido por el operador. Requiere D1+D2+D7+D8 APROBADO.
- **(C) RECHAZAR**: si D3 = RECHAZADO, **o** D7 = RECHAZADO, **o** PoC F2 delta_tokens = 0, **o** D1 = RECHAZADO.

---

## 7. Riesgos y mitigaciones

1. **R1 — Supply-chain (binario externo).** Mitigación: riel explícito F1 (gate SLSA-3); opción B (opt-in no core) si D3 es DUDOSO; PoC en sandbox F2; recomendación final condicional; el operador decide en F4 con HITL.
2. **R2 — Falsa promesa de reducción de tokens.** Mitigación: F2 mide delta_tokens numérico (no cualitativo); si delta = 0, D5 = RECHAZADO → opción C.
3. **R3 — Solapamiento con `repo_map.py`.** Mitigación: F0-E4 **refuta** la existencia de `repo_map.py` (no está en el repo); el "solapamiento" se reformula como complementariedad con `REPO_MAP.md` (estático vs dinámico). D4 = APROBADO.
4. **R4 — Windows edge case (issue #185 del repo).** Mitigación: F3 incluye verificación Windows real (D8); documentar workaround si procede.
5. **R5 — Codex o Copilot no soportan MCP.** Mitigación: F3-E5 verifica cada runtime; D1 baja a DUDOSO/RECHAZADO si <3/3.
6. **R6 — Indexación ejecuta código del repo.** Mitigación: F2 verifica `sin_ejecucion_de_codigo == true`; si false, D5 = RECHAZADO.
7. **R7 — 3 runtimes.** Mitigación: el plan no toca prompts/runtime; cualquier integración es opt-in (flag OFF default).
8. **R8 — Falsos verdes en la PoC.** Mitigación: F2 reporta números crudos (tokens, latencia); el reporte es reproducible con comandos exactos.

---

## 8. Fuera de scope

- **NO** empaquetar el binario dentro del deploy de Stacky (descartado en opción B; sólo la opción A lo haría, y está no-recomendada/gateada por SLSA-3).
- **NO** indexar repos arbitrarios del filesystem del operador sin consentimiento explícito por proyecto.
- **NO** reemplazar `REPO_MAP.md` o un futuro mapa estructural interno (este plan asume coexistencia).
- **NO** auth/RBAC (mono-operador, sin login).
- **NO** modificar el runtime del agente ni los prompts (los 3 runtimes siguen operativos sin el MCP).
- **NO** garantizar que la decisión es (B): la decisión la produce la evidencia F0-F4, no este plan.

---

## 9. Glosario

- **codebase-memory-mcp:** servidor MCP (https://github.com/DeusData/codebase-memory-mcp) que indexa un codebase en un knowledge graph persistente y responde queries estructurales vía MCP.
- **MCP:** Model Context Protocol (estándar de Anthropic); permite a un runtime (Claude Code, Codex, Copilot) consumir herramientas externas.
- **SLSA-3:** Supply-chain Levels for Software Artifacts, nivel 3; garantiza proveniencia verificable del build. Gate de la opción A.
- **Scorecard D1-D8:** 8 criterios de decisión (sección 4) con veredicto APROBADO/DUDOSO/RECHAZADO.
- **Opción A/B/C:** ADOPTAR-CORE / ADOPTAR-OPCIONAL-NO-CORE / RECHAZAR (sección 6).
- **`repo_map.py`:** script citado en el boceto como existente en Stacky — **REFUTADO** (Glob `**/repo_map.py` → vacío a 2026-06-27). Reemplazado por `REPO_MAP.md` (mapa estático externo) en la comparación D4.
- **`REPO_MAP.md`:** mapa estructural estático citado en `Stacky Agents/CLAUDE.md`, generado por un script externo (no versionado en `Stacky Agents/backend`).
- **`STACKY_CODEBASE_MEMORY_MCP_ENABLED`:** flag opt-in (default OFF, editable por UI) que activa la integración con el MCP externo si el operador lo instala.
- **Ratchet:** mecanismo del Plan 49 que obliga a registrar todo test nuevo en `HARNESS_TEST_FILES`.
- **HITL:** Human-in-the-loop; el operador revisa y aprueba la decisión F4.

---

## 10. Orden de implementación

1. **F0** — Investigación preliminar (E1, E2, E4, E7) → `notes-E1-E2-E4-E7.md`.
2. **F1** — Gate SLSA-3 (opción A go/no-go) → `decision-A-gate.md`.
3. **F2** — PoC sandbox con métricas de tokens → `poc-metrics.md`.
4. **F3** — Comparación + integración 3 runtimes + mantenimiento → `integration-3-runtimes.md`, `maintenance-model.md`.
5. **F4** — Decisión final A/B/C con scorecard D1-D8 → `decision.md` (HITL: operador aprueba).
6. **F5** — **Si (B):** flag + helpers + endpoints + UI + 3 guías de instalación. **Si (A) o (C):** saltar.
7. **F6** — Reporte final + ratchet byte-idéntico.

Cada fase es auto-contenida y se puede ejecutar/commitear de forma independiente. La decisión final (F4) puede parar el plan en C (sin código) o continuarlo en B (con flag + docs).

> **Aislamiento:** este plan **NO depende de 70, 71, 72, 73, 74 ni 75**. Se puede ejecutar en paralelo a todo el bloque GitLab. No toca `TrackerProvider`, `tickets.py`, ni ningún consumidor del puerto.

---

## 11. DoD global (Definition of Done)

- [ ] **(a)** `docs/_evals/codebase-memory-mcp/notes-E1-E2-E4-E7.md` existe y cita URLs reales del repo (F0).
- [ ] **(b)** `decision-A-gate.md` declara D3 con comando de verificación documentado; si D3 ≠ APROBADO, opción A descartada por escrito (F1).
- [ ] **(c)** `poc-metrics.md` reporta `delta_tokens` numérico + `sin_ejecucion_de_codigo` (F2).
- [ ] **(d)** `integration-3-runtimes.md` declara D1 por runtime; `maintenance-model.md` declara D6 (F3).
- [ ] **(e)** `decision.md` declara A|B|C con scorecard D1-D8 completa y consistente con las reglas (F4).
- [ ] **(f)** Si (B): flag `STACKY_CODEBASE_MEMORY_MCP_ENABLED` default OFF + endpoint + UI + 3 guías; tests `test_plan76_codebase_memory_mcp.py` verdes (F5).
- [ ] **(g)** `report.md` reproducible con comandos exactos (F6).
- [ ] **(h)** Ratchet verde con los archivos `test_plan76_*` registrados.
- [ ] **(i)** `tsc` 0 errores (si F5 implementado).
- [ ] **(j)** Los 3 runtimes operativos sin cambios (el plan no toca prompts/runtime).
- [ ] **(k)** **Riel supply-chain cumplido:** si D3 ≠ APROBADO, la opción A está descartada por escrito en F1.

---

## 12. Notas de implementación (para el modelo menor que ejecute esto)

- **Este plan es una evaluación, no una feature.** La mayor parte del "trabajo" es investigación + documentación en `docs/_evals/codebase-memory-mcp/`. Sólo F5 (si decisión B) añade código.
- **Venv del repo:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest <test> -q` (py3.13, ver memoria `stacky-backend-dev-test-env`).
- **Patrón mock (F5):** `mcp_installation_status` y `build_installation_guide` son PURAS (sin red, sin binarios); testear con config mock y strings.
- **Cada commit deja el sistema verde y backward-compatible.**
- **Falsos verdes prohibidos:** F2 reporta números crudos; F4 decisión consistente con reglas; F6 byte-idéntico con flag OFF.
- **`repo_map.py` NO existe** (refutado por Glob). Cualquier mención en código/docs heredadas a "repo_map.py interno" es stale; el único mapa estructural es `REPO_MAP.md` (externo).
- **El operador decide en F4** (HITL). El implementador produce evidencia, no impone decisión.
- **Si una fase revela un GAP no listado en la scorecard**, detener y actualizar este doc antes de seguir.
- **No empaquetar el binario del MCP.** Si la decisión fuera (A) (sólo si SLSA-3 APROBADO + operador aprueba), el empaquetado se diseñaría en un plan separado; este plan no lo cubre.
