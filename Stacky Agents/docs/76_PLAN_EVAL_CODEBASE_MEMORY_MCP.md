# Plan 76 — Evaluación de adopción de `codebase-memory-mcp`

> Estado: BOCETO (pendiente formalizar con proponer-plan-stacky). Este plan es DISTINTO a los otros: su contenido es la EVALUACIÓN misma; el "plan" es la decisión adoptar/rechazar/parcial + cómo integrarlo.
> Bloque roadmap: GitLab-Main 70-76 (eslabón 7, Eval).
> Depende de: ninguno (paralelo a todo el bloque).
> Versión: boceto v0.

## 1. Objetivo + KPI
Evaluar rigurosamente si Stacky debe adoptar `codebase-memory-mcp` (DeusData) como servidor MCP de indexación de codebase para los 3 runtimes del agente, y producir una decisión documentada (adoptar-core / adoptar-opcional / rechazar) con evidencia.

**KPI:** al cerrar el plan, el operador tiene una decisión binaria accionable con criterios verificables, casos de uso cubiertos, riesgos enumerados, y — si se adopta — un plan de integración (flag opt-in, configuración por proyecto).

## 2. Por qué / gap que cierra
- Stacky actualmente no tiene un índice semántico del codebase de los proyectos del operador; el agente descubre código grep-eando (caro en tokens).
- `codebase-memory-mcp` indexa el codebase en un **knowledge graph persistente** con queries sub-ms, soporta **158 lenguajes** (útil para RS/Pacífico: Python + C# + TS + SQL + Markdown), y se consume vía MCP estándar (compatible con los 3 runtimes: Claude Code, Codex, Copilot Pro).
- Existe `repo_map.py` en el repo de Stacky (genera un mapa estructural determinista), con el que esta herramienta **solapa parcialmente** — hay que evaluar complementariedad vs duplicación.
- Riesgo supply-chain (binario externo) hace que la decisión no sea trivial; requiere evaluación honesta.

## 3. Evaluación (cuerpo principal del plan — MÁS completo que el resto)

### 3.1 Criterios de decisión
Cada criterio se puntúa APROBADO / DUDOSO / RECHAZADO con evidencia:

| # | Criterio | Pregunta | Peso |
|---|----------|----------|------|
| D1 | Compatibilidad MCP | ¿Se conecta a los 3 runtimes de Stacky sin código custom? | Alto |
| D2 | Lenguajes | ¿Cubre los lenguajes de RS/Pacífico (Python, C#, TS, SQL)? | Alto |
| D3 | Seguridad/supply-chain | ¿El binario es auditable/firmado? ¿Origen confiable? | Alto |
| D4 | Solapamiento con `repo_map.py` | ¿Aporta valor no cubierto por el repo_map existente? | Medio |
| D5 | Costo de tokens | ¿Reduce tokens en queries estructurales de forma medible? | Alto |
| D6 | Mantenimiento/actualización | ¿Cómo se actualiza el índice al cambiar el codebase? | Medio |
| D7 | Licenciamiento | ¿Licencia compatible con uso interno de Stacky? | Alto |
| D8 | Soporte Windows | ¿Funciona en Windows (entorno del operador)? | Medio |

### 3.2 Qué investigar (tareas de la eval)
- **E1** — Confirmar el repo: https://github.com/DeusData/codebase-memory-mcp — leer README, releases, `server.json`, licencia. (Búsqueda preliminar ya confirmó existencia y claims: 158 lenguajes, sub-ms queries, knowledge graph persistente, compatible Claude Code/Codex/ChatGPT.)
- **E2** — Verificar el **canal de distribución**: ¿binario precompilado? ¿Script de build? Comentario del operador preliminar menciona "binario C estático firmado SLSA-3" — **verificar claim de firma SLSA-3 contra releases reales** (es el riesgo supply-chain principal).
- **E3** — PoC controlado: levantar el MCP en un sandbox (VM desechable o contenedor) contra un sub-árbol de RS/Pacífico, confirmar (a) indexación sin ejecutar código del repo, (b) latencia sub-ms, (c) reducción de tokens en queries estructurales reales ("dónde se define X", "quién llama Y").
- **E4** — Comparar contra `repo_map.py` existente: ¿qué queries hace uno que el otro no? ¿`repo_map` determinístico + barato basta para el 80%?
- **E5** — Verificar integración MCP con cada runtime:
  - Claude Code CLI: declara server en `claude_desktop_config.json` / settings.
  - Codex CLI: confirmar soporte MCP.
  - GitHub Copilot Pro: confirmar soporte MCP (vía VS Code extension).
- **E6** — Política de actualización del índice: ¿watch del filesystem? ¿re-index manual? ¿crece linealmente?
- **E7** — Licencia: leer LICENSE del repo.

### 3.3 Opciones de decisión (mutuamente excluyentes)
- **(A) ADOPTAR-CORE**: se incluye en el bundle de Stacky, default ON. Requiere D3 y D7 APROBADOS con evidencia fuerte + PoC exitosa. **No recomendado preliminar** (riesgo supply-chain sobre core).
- **(B) ADOPTAR-OPCIONAL-NO-CORE** *(recomendación preliminar)*: el operador puede activarlo por proyecto vía flag `STACKY_CODEBASE_MEMORY_MCP_ENABLED` default OFF. Stacky no lo empaqueta; el operador lo instala aparte y Stacky sólo lo detecta/describe. Compatible con Windows, multi-lenguaje, reduce tokens en queries estructurales, riesgo supply-chain asumido por el operador. Requiere D1+D2+D8 APROBADOS.
- **(C) RECHAZAR**: si D3 o D7 son RECHAZADOS, o la PoC no muestra reducción de tokens medible (D5 DUDOSO/RECHAZADO), o el solapamiento con `repo_map` es total (D4 RECHAZADO).

### 3.4 Recomendación preliminar (a confirmar con E1-E7)
**ADOPTAR-OPCIONAL-NO-CORE (opción B)**, pendiente verificación de firma SLSA-3 (E2) y PoC de reducción de tokens (E3). Razones:
- Valor real para RS/Pacífico (multi-lenguaje Python/C#/TS/SQL).
- Bajo costo de integración (MCP estándar, sin código custom).
- Riesgo supply-chain mitigado al no ser core y exigir opt-in explícito del operador.
- Complementario (no reemplazante) de `repo_map.py`: `repo_map` para mapa estructural determinista del repo de Stacky mismo; `codebase-memory-mcp` para queries semánticas sobre los repos de los proyectos del operador.

## 4. Fases del plan
- **F0** — Ejecutar E1-E2 (lectura repo + verificación firma SLSA-3).
- **F1** — Ejecutar E7 (licencia) + decisión binaria go/no-go preliminar.
- **F2** — Ejecutar E3 (PoC sandbox) con métricas de tokens.
- **F3** — Ejecutar E4-E5-E6 (repo_map, integración 3 runtimes, updates).
- **F4** — Decisión final (A/B/C) documentada con scorecard D1-D8.
- **F5** — Si (B): implementar flag `STACKY_CODEBASE_MEMORY_MCP_ENABLED` default OFF en UI + documentación de instalación para el operador; ningún empaquetado del binario.
- **F6** — Reporte + ratchet (si se implementa flag, test de byte-idéntico con flag OFF).

## 5. Supuestos clave a verificar al formalizar
- **CRÍTICO:** verificar la claim "binario C estático firmado SLSA-3" contra los releases reales del repo. Si la firma no existe o el build no es reproducible, D3 baja a DUDOSO y la opción A queda descartada.
- Confirmar soporte MCP simultáneo en los 3 runtimes sin código custom por runtime (D1).
- Confirmar que Windows está soportado de primera clase (issue #185 del repo menciona proceso colgado en Windows al cerrar VS Code — signal de un edge case).
- Verificar que el conocimiento del grafo persistente NO se comparte entre proyectos del operador (aislamiento por repo).
- Confirmar que `repo_map.py` (Stacky) y este MCP no duplican esfuerzos: definir responsabilidades disjuntas.

## 6. Riesgos principales
- **R1 — Supply-chain (binario externo).** Mitigación: opción B (opt-in no core), verificación de firma en E2, PoC en sandbox E3, recomendación final condicional.
- **R2 — Falsa promesa de reducción de tokens.** Mitigación: E3 mide tokens antes/después en queries reales; si no hay delta, opción C.
- **R3 — Solapamiento con `repo_map.py`.** Mitigación: E4 delimita responsabilidades; si duplican, opción C.
- **R4 — Windows edge case (issue #185).** Mitigación: F3 incluye verificación Windows real; documentar workaround si procede.

## 7. Fuera de schema
- Empaquetar el binario dentro del deploy de Stacky (queda descartado en opción B; sólo la opción A lo haría y está no-recomendada).
- Indexar repos arbitrarios del filesystem del operador sin consentimiento explícito por proyecto.
- Reemplazar `repo_map.py` (este plan asume coexistencia).

## 8. Rieles duros heredados
3 runtimes (el cambio es opt-in, no rompe ninguno) / cero trabajo operador excepto activar flag si lo quiere (opt-in, default OFF) / HITL (el operador decide instalar) / mono-operador / TDD donde aplique (flag byte-idéntico OFF) / backward-compatible / **seguridad supply-chain como riel explícito** — sin firma verificable, sin adopción core.

## 9. Próximo paso
`proponer-plan-stacky` → `criticar-y-mejorar-plan` (el juez debe exigir evidencia E2/E3 antes de aprobar) → si la evaluación concluye (B), `implementar-plan-stacky` para el flag + docs.
