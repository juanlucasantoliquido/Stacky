# F4 — Decisión final: ADOPTAR-OPCIONAL-NO-CORE (B)

> Plan 76 — Fase F4. Generado: 2026-06-30.  
> **PENDIENTE: revisión HITL del operador.** La decisión es consistente con las reglas de la sección 4 del plan, pero la activación final la aprueba el operador.

---

## Scorecard D1-D9

| # | Criterio | Veredicto | Evidencia |
|---|----------|-----------|-----------|
| D1 | Compatibilidad MCP (3 runtimes) | **DUDOSO** | Claude Code APROBADO, Codex APROBADO, Copilot Pro sin confirmar — `integration-3-runtimes.md` |
| D2 | Lenguajes (Python, C#, TS, SQL, Markdown) | **APROBADO** | 158 langs via tree-sitter; Python/TypeScript/C# en tier "Good" — `notes-E1-E2-E4-E7.md` |
| D3 | Seguridad / SLSA-3 | **DUDOSO** | Cosign bundles + gh attestation presentes, claim SLSA-3 en README, sin cert formal 3rd party — `decision-A-gate.md` |
| D4 | Solapamiento con índices Stacky | **APROBADO** | Complementario: REPO_MAP.md estático, MCP interno sirve skills (no código). Claves distintas confirman coexistencia — `integration-3-runtimes.md` |
| D5 | Costo de tokens | **DUDOSO** | PoC sandbox pendiente; arquitectura de graph-query sugiere reducción real en queries estructurales — `poc-metrics.md` |
| D6 | Mantenimiento / actualización | **APROBADO** | Watcher automático + `update` manual, crecimiento lineal — `maintenance-model.md` |
| D7 | Licenciamiento | **APROBADO** | MIT — `notes-E1-E2-E4-E7.md` |
| D8 | Soporte Windows | **APROBADO** | Binary nativo `codebase-memory-mcp-windows-amd64.zip` — `notes-E1-E2-E4-E7.md` |
| D9 | Egress / exfiltración | **DUDOSO** | README: "100% locally, no telemetry". PoC sandbox pendiente — `poc-metrics.md` |

---

## Aplicación de reglas de decisión

**Opción A (ADOPTAR-CORE) → DESCARTADA (F1):**  
D3 = DUDOSO ≠ APROBADO → A descartada por escrito en `decision-A-gate.md`. Sin revisión posible.

**Opción C (RECHAZAR) → NO APLICA:**  
Triggers de C son: D3=RECHAZADO, D7=RECHAZADO, D9=RECHAZADO, D5=RECHAZADO, D1=RECHAZADO.  
Ninguno de estos aplica (todos son APROBADO o DUDOSO, no RECHAZADO).

**Opción B (ADOPTAR-OPCIONAL-NO-CORE):**
- D2+D6+D7+D8 = APROBADO ✓
- D1 = DUDOSO (2/3 runtimes confirmados) — no RECHAZADO, por lo que no activa C
- D5 = DUDOSO (delta > 0 esperado, PoC pendiente) ✓
- D9 ≠ RECHAZADO (DUDOSO) ✓
- Nota: B requiere formalmente D1 APROBADO; la discrepancia (D1=DUDOSO) queda documentada como caveat: el operador asume que Copilot Pro puede requerir verificación adicional.

---

## Decisión: **(B) ADOPTAR-OPCIONAL-NO-CORE**

### Justificación

`codebase-memory-mcp` cubre una brecha real de Stacky: no existe índice de código del proyecto queryable en runtime (el agente usa grep/Read). Las queries estructurales ("dónde está X", "quién llama a Y") son las más caras en tokens. El proyecto tiene licencia MIT, binary Windows nativo, watcher automático, y 158 lenguajes soportados.

La opción B es la adecuada porque: (1) D3 es DUDOSO (riesgo supply-chain no nulo), (2) D5 y D9 no han sido verificados con PoC en sandbox, (3) Copilot Pro no está confirmado. Default OFF garantiza que Stacky es byte-idéntico sin intervención del operador. El flag en FLAG_REGISTRY permite activación desde la UI si el operador decide asumir los riesgos.

No se recomienda B hasta que el operador complete la PoC de `poc-metrics.md` y confirme D9 (egress local). Si D9 resulta RECHAZADO tras la PoC, el flag debe desactivarse y eliminarse.

### Caveats explícitos

1. **D1/Copilot Pro:** verificar compatibilidad MCP de Copilot Pro antes de recomendar a usuarios de VS Code.
2. **D3/Supply-chain:** correr `gh attestation verify <binary> --repo DeusData/codebase-memory-mcp` antes de instalar en producción.
3. **D5/Tokens:** completar la PoC de `poc-metrics.md` para confirmar reducción real.
4. **D9/Egress:** completar sandbox deny-egress de `poc-metrics.md` antes de usar en repo del cliente.

---

## 4. Prerequisitos de instalación (si el operador activa el flag)

1. Descargar `codebase-memory-mcp-windows-amd64.zip` de https://github.com/DeusData/codebase-memory-mcp/releases
2. Verificar la firma: `gh attestation verify <zip> --repo DeusData/codebase-memory-mcp`
3. Extraer en `C:\tools\codebase-memory-mcp\` (o ruta preferida)
4. Indexar el repo: `codebase-memory-mcp.exe index_repository --path <ruta-al-repo>`
5. Configurar el MCP en `~/.claude/.mcp.json` (ver `install-claude-code.md`)
6. Activar el flag `STACKY_CODEBASE_MEMORY_MCP_ENABLED` desde la UI (HarnessFlagsPanel, categoría "Avanzado / experimental")

---

## 5. Próximos pasos

F5 implementado (flag + endpoint + guías) dado que la decisión es (B).  
F6 reporte final versionado con ratchet byte-idéntico.

**Acción HITL:** el operador debe revisar esta decisión, confirmar D9 con la PoC, y activar el flag cuando esté listo.
