# Plan 76 — Evaluación de adopción de `codebase-memory-mcp`

> **Estado:** PROPUESTO v3 (segunda pasada del juez adversarial — verificación de la v2 contra código real, v2 → v3).
> **Pre-requisito:** ninguno (paralelo, aislado del bloque GitLab 70-75). No depende de ningún plan previo.
> **Roadmap:** Séptimo eslabón del bloque GitLab-Main 70-76 (desacople → pipeline infer agnóstico → trigger CI → creador pipelines → migrador ADO→GitLab → deep links → **eval codebase-memory-mcp**).
> **Versión doc:** v3 (2026-06-29). Reemplaza a v2 (2026-06-29, 1ª crítica), que reemplazó a v1 (2026-06-27) y al boceto v0.

> **CHANGELOG v2 → v3 (juez 2ª pasada — los bloqueantes C1/C2 de la v1 quedaron BIEN resueltos, verificados contra código; se hallaron residuales nuevos):**
> - **VERIFICADO C1 (BLOQUEANTE v1) RESUELTO:** patrón blueprint correcto confirmado en código vivo: `api/__init__.py:44` (`api_bp` con `url_prefix="/api"`) + línea 84 (`api_bp.register_blueprint(ci_bp)`), sub-blueprint `api/ci.py:26` (`url_prefix="/ci"` → `/api/ci/...`). El centinela real `test_plan72_routes_registered.py` bootea `create_app()` y asierta ruta + anti-doble-prefijo; la réplica F5 (`test_plan76_routes_registered.py`) calca ese patrón. Correcto.
> - **VERIFICADO C2 (BLOQUEANTE v1) RESUELTO:** firma real de `FlagSpec` (`harness_flags.py:19-27`) = `key,type,label,description,group,pair?,env_only,default`; el `FlagSpec` propuesto en F5 (`type="bool"`, `group="global"`, `env_only=False`, `default=False`) coincide EXACTO. Categoría `"avanzado"` real (`CategorySpec` línea 62 + `_CATEGORY_KEYS["avanzado"]` línea 171); la `NOTA` en línea 177 ya FUERZA por test que toda flag nueva esté categorizada. Correcto.
> - **VERIFICADO C3 RESUELTO:** patrón `os.getenv("...","false").lower() in ("1","true","yes")` confirmado en `config.py:817-824` (`STACKY_PIPELINE_TRIGGER_ENABLED`). El F5 lo copia tal cual.
> - **C10 (IMPORTANTE — NUEVO, lo perdió la 1ª pasada) — assert de byte-identidad F6 con falso-fallo:** F6 caso 2 aserta que `build_agent_env` "no contiene la subcadena `mcpServers`". Pero el MCP INTERNO de Stacky YA emite `mcpServers` (`services/stacky_mcp.py:64-65`, clave de server `"stacky"`; `tests/test_cli_resume_mcp_config.py`). Con `CLAUDE_CODE_CLI_MCP_ENABLED` ON ese assert da FALSO-FALLO. Corregido: el assert se hace SOLO sobre el token específico del plan (`codebase-memory-mcp`), NUNCA sobre el genérico `mcpServers`/`mcp_servers`.
> - **C11 (MENOR — NUEVO) — test de pureza sin mecanismo:** F5 caso 8 ("no hace red") no decía CÓMO asertarlo. Corregido: `monkeypatch` de `socket.socket` para que levante; afirmar que `mcp_installation_status()` retorna igual (no toca red).
> - **C12 (MENOR/INFO — NUEVO) — `CLAUDE.md` referencia un script inexistente:** `CLAUDE.md` dice "Regenerar: `python repo_map.py`" pero `repo_map.py` NO existe (Glob `**/repo_map.py` → vacío, reconfirmado 2026-06-29). NO es defecto del plan (el plan ya lo refuta); se añade nota en D4 de que la propia referencia de `CLAUDE.md` está stale, reforzando el "no solapamiento".
> - **[ADICIÓN ARQUITECTO v2→v3]** — **clave de server MCP namespaced y única:** se fija por contrato que el server externo use la clave `"codebase-memory-mcp"` en `mcpServers`, DISTINTA de la interna `"stacky"` (`stacky_mcp.py:65`). Esto (1) vuelve concreto el C4 ("conflicto de nombres" deja de ser vago: el blanco real es la clave `"stacky"`), y (2) le da al assert de byte-identidad C10 un token preciso, libre de colisión. Un solo contrato resuelve la coexistencia (C4) y el falso-fallo (C10). Reusa la estructura `mcpServers` ya viva en `stacky_mcp.py`.
>
> **CHANGELOG v1 → v2 (juez adversarial — resuelve C1..C9):**
> - **C1 (BLOQUEANTE) — doble-prefijo `/api/api`:** v1 decía "registrar blueprint en `app.py`" + endpoint `GET /api/codebase-memory-mcp/status`. Es EXACTAMENTE el bug que rompió 72/73/74/75. Corregido en F5: el blueprint se declara con `url_prefix="/codebase-memory-mcp"` y se registra en `api/__init__.py` vía `api_bp.register_blueprint(...)` (api_bp ya monta `/api`). NUNCA en `app.py`, NUNCA `url_prefix="/api/..."`. + centinela `test_plan76_routes_registered.py` (réplica del patrón `test_plan72_routes_registered.py`).
> - **C2 (BLOQUEANTE) — flag invisible en UI (viola regla dura operator-config-always-via-ui):** v1 agregaba la flag solo a `config.py` y "tocaba `HarnessFlagsPanel.tsx` + categoría nueva". `services/harness_flags.py:5-7` dice que toda flag va al `FLAG_REGISTRY` "para que aparezca en la UI **sin tocar el frontend**". Corregido en F5: agregar `FlagSpec(env_only=False)` a `FLAG_REGISTRY` + key en `_CATEGORY_KEYS["avanzado"]` (NO categoría nueva, NO tocar `HarnessFlagsPanel.tsx`).
> - **C3 (IMPORTANTE) — sintaxis de flag en `config.py` rompe el env:** v1 mostraba `STACKY_..._ENABLED: bool = False` (flag muerta, no lee env → rompe hot-apply y `harness_defaults.env`). Corregido al patrón real `os.getenv("...","false").lower() in ("1","true","yes")` (`config.py:817-824`).
> - **C4 (IMPORTANTE) — D4 solo comparaba contra `REPO_MAP.md`, ignorando el canal MCP interno de Stacky:** Stacky YA tiene MCP propio (`CLAUDE_CODE_CLI_MCP_ENABLED`, tool `stacky_get_skill`). F3/D4 ahora compara contra AMBOS y contempla coexistencia/colisión de servers MCP en el config del runtime.
> - **C5 (IMPORTANTE) — métrica de tokens F2 falseable + trabajo extra al operador:** v1 pedía al operador un sub-árbol de RS/Pacífico y comparaba "grep ingenuo vs query MCP". Corregido: protocolo de medición fijo y versionado, sub-árbol DEFAULT = el propio repo de Stacky (cero trabajo del operador, multi-lenguaje, reproducible), queries congeladas en archivo.
> - **C6 (IMPORTANTE) — [ADICIÓN ARQUITECTO] gate de EGRESS:** v1 verificaba "sin ejecución de código" pero NO que el MCP no exfiltre el codebase del operador. Añadido gate de egress (D9) reusando el concepto del egress check existente (`STACKY_CLI_EGRESS_ENABLED`, `test_cli_egress.py`). Es el riesgo central de un binario externo que ve tu código.
> - **C7 (MENOR) — `.env.example` no incluido:** v1 solo añadía la flag a `harness_defaults.env`. v2 también a `.env.example` (consistencia con todas las flags existentes).
> - **C8 (MENOR) — caso 2 del ratchet F6 vago ("no se inyecta config MCP"):** reformulado a assert concreto sobre `build_agent_env` / prompt final.
> - **C9 (MENOR) — `CodebaseMemoryMcpCard.tsx` duplicaba el toggle:** clarificado que es read-only (solo muestra estado + guía); el toggle lo da el panel de flags automáticamente. Opcional, no bloqueante.
> - **[ADICIÓN ARQUITECTO]** marcada en F2 (D9 egress) y en F5 (centinela de rutas).
>
> **CHANGELOG boceto v0 → v1 (conservado):**
> - Este plan es DISTINTO a los demás: su contenido **es la evaluación misma**; el "plan" es la decisión documentada (adoptar-core / adoptar-opcional / rechazar) + el procedimiento F0..F6 para llegar a ella con evidencia.
> - Supuesto crítico del boceto ("existe `repo_map.py` en Stacky") **REFUTADO**: `repo_map.py` NO existe (Glob `**/repo_map.py` → vacío a 2026-06-27). El `CLAUDE.md` cita un `REPO_MAP.md` generado por script externo. D4 se reformula: no hay solapamiento real; sería **complementario**.
> - Riel supply-chain explícito (SLSA-3): F1 es el gate go/no-go de la opción A.

---

## 1. Objetivo y KPI

Evaluar rigurosamente si Stacky debe adoptar `codebase-memory-mcp` (https://github.com/DeusData/codebase-memory-mcp) como servidor MCP de indexación de codebase para los 3 runtimes del agente (Claude Code, Codex, GitHub Copilot Pro), y producir una **decisión documentada** (ADOPTAR-CORE / ADOPTAR-OPCIONAL-NO-CORE / RECHAZAR) con evidencia verificable.

**KPI global (DoD):** al cerrar el plan, el operador tiene:
1. Una decisión binaria accionable (A/B/C) con la scorecard D1-D9 completa y evidencia por criterio.
2. Si la decisión es (B): un flag `STACKY_CODEBASE_MEMORY_MCP_ENABLED` default OFF, **editable por UI** (FLAG_REGISTRY, sin tocar el frontend) + documentación de instalación para el operador (SIN empaquetar el binario externo).
3. Un reporte versionado (`docs/_evals/codebase-memory-mcp/report.md`) con todos los hallazgos E1-E7, reproducible.

---

## 2. Por qué ahora / gap que cierra

- Stacky actualmente **no tiene un índice semántico del codebase** de los proyectos del operador (ej. RS/Pacífico: Python + C# + TS + SQL + Markdown); el agente descubre código grep-eando o leyendo archivos enteros (caro en tokens).
- `codebase-memory-mcp` promete indexar el codebase en un **knowledge graph persistente** con queries sub-ms, soporte multi-lenguaje, y consumo vía MCP estándar (compatible en teoría con los 3 runtimes — a verificar en F3/D1).
- Existe una **referencia estructural** en Stacky (`REPO_MAP.md` citado en `CLAUDE.md`) generada por un script externo (no `repo_map.py` interno — **refutado**, ver F0-E4), pero NO es un grafo queryable.
- **Stacky YA tiene un canal MCP propio** (`CLAUDE_CODE_CLI_MCP_ENABLED`, tool `stacky_get_skill`): D4 debe comparar contra ESTO también, no solo contra `REPO_MAP.md` (C4).
- Riesgo supply-chain (binario externo que **indexa y por ende ve todo el codebase del operador**) hace que la decisión no sea trivial; requiere evaluación honesta, gate SLSA-3 (D3) y gate de egress (D9, C6).
- **Aislamiento:** este plan no toca código de runtime; si la decisión es (B), sólo añade un flag (registrado) + endpoint + docs. Si es (C), no añade nada.

**Anclajes verificados con evidencia (archivo:línea):**
- Blueprints se registran en `backend/api/__init__.py` (`api_bp.register_blueprint(...)`, líneas 45-84); `backend/app.py:187` monta `api_bp` (que ya prefija `/api`). Patrón sub-blueprint: `api/ci.py:26` → `Blueprint("ci", __name__, url_prefix="/ci")` → rutas `/api/ci/...`.
- `backend/services/harness_flags.py:5-7` (regla del módulo): toda flag nueva va a `FLAG_REGISTRY` para aparecer en la UI **sin tocar el frontend**.
- Patrón de flag bool en `backend/config.py:817-824`.
- Egress check existente: `STACKY_CLI_EGRESS_ENABLED` (`harness_flags.py:356`, `env_only=True`), `backend/tests/test_cli_egress.py` (incl. `test_flag_registry_has_cli_egress_flag`). El D9 reusa el **espíritu** (sandbox deny-egress), no el código.
- **MCP interno de Stacky:** `services/stacky_mcp.py:64-65` emite `{"mcpServers": {"stacky": {...}}}` (clave de server `"stacky"`). **El server externo DEBE usar otra clave** (`"codebase-memory-mcp"`) para no colisionar — y el assert de byte-identidad (C10) debe mirar ese token específico, NO el genérico `mcpServers` (que ya existe).
- Glob `**/repo_map.py` → vacío (reconfirmado 2026-06-29). **No existe.** (Ojo: `CLAUDE.md` aún dice "Regenerar: `python repo_map.py`" — referencia stale del propio `CLAUDE.md`, no del plan.)
- Repo objetivo de la eval: https://github.com/DeusData/codebase-memory-mcp (F0-E1 confirma existencia y lectura real).

---

## 3. Principios y guardarraíles

- **3 runtimes con paridad** (Codex, Claude Code, GitHub Copilot Pro): la evaluación verifica compatibilidad MCP con los 3; si uno solo no lo soporta, D1 baja. **No se asume compatibilidad: se prueba** (F3-E5).
- **Cero trabajo extra al operador**: cualquier integración es opt-in vía flag `STACKY_CODEBASE_MEMORY_MCP_ENABLED` default **OFF**, `env_only=False` (UI). La PoC F2 corre sobre el propio repo de Stacky por default (no exige sub-árbol del operador, C5).
- **Human-in-the-loop innegociable**: la decisión final la toma el operador con la scorecard; el plan produce evidencia, no decisión automática (F4).
- **Mono-operador sin auth**: el MCP se instala en la máquina del operador; Stacky no distribuye credenciales ni binarios. Sin RBAC.
- **No degradar / backward-compatible**: con flag OFF (default), Stacky es byte-idéntico a hoy; F6 lo verifica con test concreto (C8).
- **TDD + funciones puras + ratchet + no falsos verdes**: donde haya código (F5 flag + helpers + endpoint), TDD primero, con centinela de rutas reales (C1).
- **Seguridad supply-chain como riel EXPLÍCITO doble:** (1) **sin firma SLSA-3 verificable (D3), sin adopción core**; (2) **sin verificación de egress (D9), no se recomienda ni opt-in**. La opción A requiere D3 APROBADO; cualquier adopción (A o B) requiere D9 ≠ RECHAZADO.
- **Reuso obligatorio:** la flag reusa `FLAG_REGISTRY` (no frontend nuevo de toggle); el gate de egress reusa el concepto del egress check existente; el endpoint reusa el patrón `api_bp` + centinela.
- **Prohibido lo vago:** todo hallazgo citado con URL/evidencia; el reporte es reproducible con comandos exactos.

---

## 4. Scorecard de decisión D1-D9 (cuerpo principal del plan)

Cada criterio se puntúa **APROBADO / DUDOSO / RECHAZADO** con evidencia en F4:

| # | Criterio | Pregunta | Peso |
|---|----------|----------|------|
| D1 | Compatibilidad MCP | ¿Se conecta a los 3 runtimes (Claude Code, Codex, Copilot Pro) sin código custom por runtime? | Alto |
| D2 | Lenguajes | ¿Cubre los lenguajes de RS/Pacífico (Python, C#, TS, SQL, Markdown)? | Alto |
| D3 | Seguridad / supply-chain | ¿El binario tiene firma SLSA-3 verificable Y build reproducible? ¿Origen confiable? | **Alto (gate A)** |
| D4 | Solapamiento con índices Stacky | ¿Aporta valor no cubierto por `REPO_MAP.md` **ni por el MCP interno de Stacky** (`stacky_get_skill`)? | Medio |
| D5 | Costo de tokens | ¿Reduce tokens en queries estructurales reales de forma medible (delta > 0), con protocolo reproducible? | Alto |
| D6 | Mantenimiento / actualización | ¿Cómo se actualiza el índice al cambiar el codebase (watch / re-index manual)? ¿Crece linealmente? | Medio |
| D7 | Licenciamiento | ¿Licencia compatible con uso interno de Stacky? | Alto |
| D8 | Soporte Windows | ¿Funciona en Windows (entorno del operador)? | Medio |
| D9 | **Egress / exfiltración** | ¿El MCP indexa **sin red saliente no consentida**? ¿Todo el tráfico es local/declarado? | **Alto (gate adopción)** |

**Reglas de decisión (aplicadas en F4):**
- **(A) ADOPTAR-CORE** requiere: D3 = APROBADO (SLSA-3 verificable) **Y** D9 = APROBADO **Y** D1+D2+D5+D7 todos APROBADO **Y** PoC F2 exitosa. Si D3 ≠ APROBADO **o** D9 ≠ APROBADO, A queda **descartada**.
- **(B) ADOPTAR-OPCIONAL-NO-CORE** requiere: D1+D2+D7+D8 APROBADO **Y** D5 APROBADO o DUDOSO (delta > 0) **Y** D9 ≠ RECHAZADO (egress local o declarado/bloqueable). D3 puede ser DUDOSO (riesgo asumido por el operador, opt-in).
- **(C) RECHAZAR** si: D3 = RECHAZADO, **o** D7 = RECHAZADO, **o** D9 = RECHAZADO (exfiltra), **o** PoC F2 delta = 0 (D5 = RECHAZADO), **o** D1 = RECHAZADO (no soporta los 3 runtimes).

---

## 5. Fases

### F0 — Investigación preliminar (E1, E2, E4, E7)

**Objetivo:** leer el repo objetivo y recolectar evidencia primaria para D1, D2, D3, D4, D7.

**Trabajo:**

```text
E1 — Confirmar repo: https://github.com/DeusData/codebase-memory-mcp
     - Leer README, releases, server.json, CLAIMS.
E2 — Verificar firma SLSA-3 contra releases REALES (no claims):
     - Descargar un release, verificar proveniencia (sigstore/cosign/slsa-verifier).
     - Si no hay firma o build no es reproducible → D3 = DUDOSO o RECHAZADO.
E4 — Comparar con índices de Stacky:
     - REPO_MAP.md (estático, no queryable) vs codebase-memory-mcp (grafo dinámico).
     - MCP interno de Stacky (stacky_get_skill, CLAUDE_CODE_CLI_MCP_ENABLED): ¿el
       codebase-memory-mcp coexiste o colisiona con el server MCP propio? (C4)
     - Refutar "solapamiento con repo_map.py" (no existe): documentar NO solapamiento real.
E7 — Leer LICENSE del repo para D7.
```

**Archivos exactos F0:**
- `docs/_evals/codebase-memory-mcp/notes-E1-E2-E4-E7.md` (NUEVO) — apuntes crudos con URLs y quotes textuales del repo.

**Tests F0 (no-TDD; es investigación):**
- No hay test de código. Criterio: el archivo `notes-E1-E2-E4-E7.md` existe y cita URLs reales del repo (no claims genéricas). Validación manual.

**Criterio binario F0:** el archivo de notas existe, cita la URL del release inspeccionado, y para D3 reporta `firmado-SLSA-3: sí/no` con evidencia (comando `slsa-verifier` corrido o screenshot del release).

**Impacto por runtime:** ninguno (sólo investigación). **Flag F0:** ninguna. **Trabajo del operador F0:** ninguno.

---

### F1 — Gate go/no-go de la opción A (verificación SLSA-3)

**Objetivo:** decidir si la opción A (ADOPTAR-CORE) es viable. Gate crítico del riel supply-chain.

**Trabajo:**

```text
# docs/_evals/codebase-memory-mcp/decision-A-gate.md (NUEVO) — contenido requerido:
# 1. Release inspeccionado (versión, fecha, URL).
# 2. Comando de verificación corrido (slsa-verifier / cosign verify-blob / gpg --verify).
# 3. Resultado: PASS / FAIL / N/A (no hay firma publicada).
# 4. Build reproducible: ¿hay provenance.json? ¿reproducible desde source?
# 5. Veredicto D3: APROBADO / DUDOSO / RECHAZADO.
# 6. Decisión: si D3 ≠ APROBADO → opción A DESCARTADA, sólo B o C siguen.
```

**Archivos exactos F1:** `docs/_evals/codebase-memory-mcp/decision-A-gate.md` (NUEVO).

**Tests F1:** No hay test de código. Criterio: el archivo existe y declara `D3 = APROBADO|DUDOSO|RECHAZADO` con el comando de verificación documentado (no claim vacío).

**Criterio binario F1:** si D3 = APROBADO, A sigue en carrera; si D3 = DUDOSO/RECHAZADO, A queda **descartada por escrito** en este archivo. Es el **riel supply-chain** operacionalizado.

**Impacto por runtime:** ninguno. **Flag F1:** ninguna. **Trabajo del operador F1:** ninguno.

---

### F2 — PoC sandbox con métricas de tokens + EGRESS (E3, D9)

**Objetivo:** medir empíricamente si el MCP reduce tokens en queries estructurales reales (gate D5) **y** verificar que no exfiltra el codebase (gate D9, **[ADICIÓN ARQUITECTO]**).

**Protocolo de medición FIJO y reproducible (resuelve C5 — no falseable):**

```text
# Sub-árbol DEFAULT = el propio repo de Stacky (cero trabajo del operador, multi-lenguaje):
#   "Stacky Agents/backend" (Python) + "Stacky Agents/frontend/src" (TS) — ~deja constancia
#   del commit SHA usado. El operador NO provee nada; si PREFIERE medir sobre RS/Pacífico,
#   puede apuntar a otro sub-árbol (opt-in), pero el default no lo exige.
# Queries CONGELADAS (versionadas en queries.md, NO improvisadas):
#   docs/_evals/codebase-memory-mcp/queries.md — 10 queries estructurales canónicas:
#     "dónde se define <símbolo>", "quién llama a <símbolo>",
#     "lista los archivos del módulo <X>", "qué tipos usa <W>", etc.
# Setup (sandbox, NO producción):
#   1. Levantar el MCP en sandbox aislado (VM/contenedor), SIN red saliente salvo la declarada.
#   2. Indexar el sub-árbol DEFAULT (registrar index_time + SHA del commit).
#   3. Correr las 10 queries congeladas en DOS modos sobre el MISMO modelo/runtime:
#        (a) baseline: el agente resuelve con grep/lectura de archivos (sin MCP);
#        (b) con MCP: el agente resuelve vía query MCP.
#      Contar tokens de la TRANSCRIPCIÓN REAL en ambos modos (no estimación a ojo).
#   4. Medir latencia (claim sub-ms vs real): latencia_p50, latencia_p95.
#   5. Confirmar que la indexación NO ejecuta código del repo (sólo parsea).
#   6. [D9 EGRESS] Con el sandbox en modo "deny egress" (firewall/red desconectada salvo
#      loopback), correr indexación + las 10 queries y registrar: ¿falla por intentar salir
#      a la red? ¿hay conexiones salientes? Herramienta sugerida: capturar con el firewall del
#      sandbox o `Test-NetConnection`/captura de paquetes. Reusa el ESPÍRITU del egress check
#      de Stacky (STACKY_CLI_EGRESS_ENABLED / test_cli_egress.py), aplicado al binario externo.
#
# Salida: docs/_evals/codebase-memory-mcp/poc-metrics.md — métricas requeridas:
#   - tokens_grep_promedio, tokens_mcp_promedio, delta_tokens, delta_pct
#   - latencia_p50, latencia_p95, index_time_seconds, commit_sha del sub-árbol
#   - sin_ejecucion_de_codigo: bool (con evidencia)
#   - egress_local_only: bool (con evidencia)  ← D9
```

**Archivos exactos F2:**
- `docs/_evals/codebase-memory-mcp/queries.md` (NUEVO) — las 10 queries congeladas + sub-árbol + commit SHA.
- `docs/_evals/codebase-memory-mcp/poc-metrics.md` (NUEVO) — tabla de métricas + conclusión D5 y D9.

**Tests F2:** No hay test de código. Criterio: ambos archivos existen; `poc-metrics.md` reporta `delta_tokens` numérico (no cualitativo) y declara `D5` + `D9` con sus booleanos como evidencia.

**Criterio binario F2:** `delta_tokens > 0` Y `sin_ejecucion_de_codigo == true` → D5 APROBADO/DUDOSO. `egress_local_only == true` → D9 APROBADO; si el MCP intenta salir a la red sin declararlo → D9 = RECHAZADO (camino a C). Si `delta_tokens <= 0` → D5 = RECHAZADO.

**Impacto por runtime:** ninguno (PoC en sandbox aislado).

**Flag F2:** ninguna.

**Trabajo del operador F2:** **ninguno por default** (PoC sobre el propio repo de Stacky). Opcional: si el operador quiere medir sobre RS/Pacífico, apunta el sub-árbol — pero no es requisito.

---

### F3 — Integración MCP en los 3 runtimes + D4 (solapamiento) + D6 (mantenimiento)

**Objetivo:** resolver D1 (compatibilidad MCP con los 3 runtimes), D4 (solapamiento vs REPO_MAP.md **y** MCP interno) y D6 (mantenimiento del índice).

**Trabajo:**

```text
# E5 — Integración MCP por runtime (D1):
- Claude Code CLI: declarar server en el config MCP (mcpServers).
  * Documentar JSON EXACTO que el operador pegaría, con clave de server
    `"codebase-memory-mcp"` (NO `"stacky"`).
  * [C4] Coexistencia con el server MCP interno de Stacky concreta: el interno usa
    la clave `"stacky"` (services/stacky_mcp.py:65). El externo DEBE usar
    `"codebase-memory-mcp"` → ambos coexisten en `mcpServers` sin colisión de claves.
    Verificar que el config del runtime admite 2+ servers simultáneos.
- Codex CLI: confirmar soporte MCP (config.toml mcp_servers).
  * Si Codex NO soporta MCP → D1 = DUDOSO (2/3 runtimes).
- GitHub Copilot Pro (VS Code): confirmar soporte MCP vía extensión.
  * Documentar config VS Code.

# E6 — Mantenimiento del índice (D6):
- ¿Watch del filesystem? ¿re-index manual? ¿crece linealmente con el repo?

# E4 — Solapamiento (D4): comparar contra AMBOS índices de Stacky:
- REPO_MAP.md: estático, generado por script externo, NO queryable en runtime.
- MCP interno (stacky_get_skill): sirve SKILLS, no estructura de código → no solapa.
- codebase-memory-mcp: grafo dinámico de CÓDIGO, queryable vía MCP.
- Conclusión esperada: complementario (D4 = APROBADO) salvo que el MCP interno ya
  cubra queries de código (verificar, no asumir).
```

**Archivos exactos F3:**
- `docs/_evals/codebase-memory-mcp/integration-3-runtimes.md` (NUEVO) — config MCP por runtime + coexistencia con MCP interno.
- `docs/_evals/codebase-memory-mcp/maintenance-model.md` (NUEVO) — modelo de actualización (E6).

**Tests F3:** No hay test de código. Criterio: ambos archivos existen; `integration-3-runtimes.md` declara `D1` por runtime y la coexistencia con el MCP interno; `maintenance-model.md` declara `D6`.

**Criterio binario F3:** los 2 archivos existen y declaran D1, D4 y D6 con evidencia. Si algún runtime no soporta MCP, D1 se documenta como DUDOSO (2/3) o RECHAZADO (<2/3).

**Impacto por runtime:** ninguno (sólo documentación). **Flag F3:** ninguna. **Trabajo del operador F3:** ninguno.

---

### F4 — Decisión final A/B/C con scorecard D1-D9

**Objetivo:** consolidar la evidencia de F0-F3 en una decisión binaria accionable aplicando las reglas de la sección 4.

**Trabajo:**

```text
# docs/_evals/codebase-memory-mcp/decision.md (NUEVO) — contenido requerido:
# 1. Scorecard D1-D9 con veredicto por criterio + URL de evidencia.
# 2. Decisión: A | B | C (mutuamente excluyente).
# 3. Justificación (2-3 párrafos).
# 4. Si (B): prerequisitos de instalación que el operador debe cumplir.
# 5. Si (C): razón principal (ej. "D9 RECHAZADO: el MCP intenta egress no declarado").
# 6. Próximos pasos (si A/B → F5; si C → F6 reporte + cerrar).
```

**Archivos exactos F4:** `docs/_evals/codebase-memory-mcp/decision.md` (NUEVO).

**Tests F4:** No hay test de código. Criterio: `decision.md` existe, declara A|B|C, y cada fila de la scorecard (9 filas) cita evidencia. La decisión es **consistente** con las reglas de la sección 4 (validación manual: si D3 ≠ APROBADO y la decisión es A → inconsistencia; si D9 = RECHAZADO y la decisión es A o B → inconsistencia).

**Criterio binario F4:** la decisión es consistente con las reglas; la scorecard está completa (9 filas).

**Impacto por runtime:** ninguno. **Flag F4:** ninguna.

**Trabajo del operador F4:** el operador **revisa** `decision.md` y aprueba/rechaza la decisión (HITL). La decisión final la tiene el operador.

---

### F5 — Si decisión es (B): flag (registrada en UI) + endpoint + docs de instalación

**Objetivo:** implementar el flag `STACKY_CODEBASE_MEMORY_MCP_ENABLED` default OFF, **editable por UI vía FLAG_REGISTRY** + endpoint de estado + documentación de instalación. **SÓLO si F4 decidió (B).** Si (A) o (C), F5 se salta.

**[C3] Atributo en `backend/config.py` (patrón EXACTO, copiar de `config.py:817-824`):**

```python
# backend/config.py — junto a las demás flags STACKY_* (NO usar ": bool = False")
    # Plan 76 — Integración opcional con codebase-memory-mcp (externo). Default OFF.
    # Editable por UI (HarnessFlagsPanel, categoría "Avanzado / experimental").
    STACKY_CODEBASE_MEMORY_MCP_ENABLED: bool = os.getenv(
        "STACKY_CODEBASE_MEMORY_MCP_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
```

**[C2] Registrar la flag en `backend/services/harness_flags.py` (esto la hace visible en la UI SIN tocar el frontend):**

```python
# 1) En _CATEGORY_KEYS["avanzado"] (harness_flags.py:171), AÑADIR la key a la tupla:
#    "STACKY_CODEBASE_MEMORY_MCP_ENABLED",
# 2) En FLAG_REGISTRY, AÑADIR (mismo patrón que el FlagSpec de Plan 71/72, harness_flags.py:1684):
    FlagSpec(
        key="STACKY_CODEBASE_MEMORY_MCP_ENABLED",
        type="bool",
        label="Codebase Memory MCP (externo, opt-in) — Plan 76",
        description=(
            "Plan 76 — Si ON, el operador puede integrar el servidor externo "
            "codebase-memory-mcp (instalado aparte) para indexar el codebase. "
            "Stacky NO empaqueta el binario; solo expone estado + guía de instalación. "
            "OFF (default): byte-idéntico a hoy, sin endpoints activos ni config MCP inyectada."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
        default=False,
    ),
```

**[C1] Endpoint (patrón blueprint CORRECTO — NUNCA en app.py, NUNCA doble prefijo):**

```python
# backend/api/codebase_memory_mcp.py (NUEVO blueprint)
from flask import Blueprint, jsonify
bp = Blueprint("codebase_memory_mcp", __name__, url_prefix="/codebase-memory-mcp")
# (api_bp ya monta /api → ruta final /api/codebase-memory-mcp/status. NUNCA url_prefix="/api/...")

@bp.get("/status")
def status_route():
    from services.codebase_memory_mcp_status import mcp_installation_status, build_installation_guide
    st = mcp_installation_status()
    return jsonify({**st, "guides": {r: build_installation_guide(r)
                    for r in ("claude_code", "codex", "copilot_pro")}})
```

```python
# backend/api/__init__.py — registrar en api_bp (NO en app.py), junto a ci_bp (línea ~84):
from .codebase_memory_mcp import bp as codebase_memory_mcp_bp
api_bp.register_blueprint(codebase_memory_mcp_bp)  # Plan 76 — /api/codebase-memory-mcp/...
```

```python
# backend/services/codebase_memory_mcp_status.py (NUEVO, helpers PUROS — sin red, sin binarios)
def mcp_installation_status() -> dict:
    """Lee el flag de config y devuelve {enabled: bool, installed_hint: str}.
    PURA: no ejecuta el binario, no hace red; sólo lee config."""

def build_installation_guide(runtime: str) -> str:
    """Genera el markdown de instalación para runtime ∈ {'claude_code','codex','copilot_pro'}.
    Lee plantillas docs/_evals/codebase-memory-mcp/install-*.md. ValueError si runtime inválido."""
```

**Archivos exactos F5:**
- `backend/config.py` (añadir atributo con el patrón `os.getenv(...)`).
- `backend/harness_defaults.env` (añadir `STACKY_CODEBASE_MEMORY_MCP_ENABLED=false`).
- `backend/.env.example` (añadir `STACKY_CODEBASE_MEMORY_MCP_ENABLED=false`) **[C7]**.
- `backend/services/harness_flags.py` (añadir FlagSpec a FLAG_REGISTRY + key a `_CATEGORY_KEYS["avanzado"]`) **[C2]**.
- `backend/services/codebase_memory_mcp_status.py` (NUEVO) — helpers puros.
- `backend/api/codebase_memory_mcp.py` (NUEVO blueprint) — `GET /api/codebase-memory-mcp/status`.
- `backend/api/__init__.py` (registrar el blueprint en `api_bp`) **[C1]**.
- `frontend/src/components/CodebaseMemoryMcpCard.tsx` (NUEVO, **read-only**) — muestra estado + guía. **NO lleva toggle** (el toggle lo da `HarnessFlagsPanel` automáticamente desde el FLAG_REGISTRY) **[C9]**. Componente OPCIONAL: si se omite, la flag igual es editable por el panel de flags.
- **NO se toca `HarnessFlagsPanel.tsx`** (la flag aparece sola desde el registro) **[C2]**.
- `docs/_evals/codebase-memory-mcp/install-claude-code.md` (NUEVO).
- `docs/_evals/codebase-memory-mcp/install-codex.md` (NUEVO).
- `docs/_evals/codebase-memory-mcp/install-copilot-pro.md` (NUEVO).

**Tests F5 (TDD primero):**
- Archivo: `backend/tests/test_plan76_codebase_memory_mcp.py`. Casos:
  1. `config.STACKY_CODEBASE_MEMORY_MCP_ENABLED` lee `False` por defecto.
  2. `mcp_installation_status()` con flag OFF → `{"enabled": False, ...}`.
  3. `mcp_installation_status()` con flag ON → `{"enabled": True, ...}` (parchear config).
  4. `build_installation_guide("claude_code")` retorna markdown no vacío que cita el config MCP con la clave de server **`"codebase-memory-mcp"`** (y NO `"stacky"`, para no colisionar con el MCP interno — C4/v3).
  5. `build_installation_guide("codex")` retorna markdown no vacío.
  6. `build_installation_guide("copilot_pro")` retorna markdown no vacío.
  7. `build_installation_guide` con runtime inválido → levanta `ValueError`.
  8. **Pureza (mecanismo concreto) [C11]:** `monkeypatch.setattr("socket.socket", _raise)` donde `_raise` levanta `RuntimeError`; afirmar que `mcp_installation_status()` retorna normalmente (no abre red). Idéntico para `build_installation_guide`.
  9. `GET /api/codebase-memory-mcp/status` con flag OFF → 200 con `enabled: false` + `guides` incluido.
  10. **[C2] Registro UI:** `FLAG_REGISTRY` contiene `STACKY_CODEBASE_MEMORY_MCP_ENABLED` con `env_only=False`, y la key está en `_CATEGORY_KEYS["avanzado"]` (no en "otros").
- Archivo centinela **[C1, ADICIÓN ARQUITECTO]**: `backend/tests/test_plan76_routes_registered.py` (réplica de `test_plan72_routes_registered.py`):
  - `test_status_route_registered_under_api`: bootea `create_app()`, afirma `"/api/codebase-memory-mcp/status" in rules`.
  - `test_no_double_prefix`: afirma `"/api/api/codebase-memory-mcp/status" not in rules`.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan76_codebase_memory_mcp.py tests/test_plan76_routes_registered.py -q`.
- Frontend (sólo si se incluye la card): `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx tsc --noEmit` (0 errores).

**Criterio binario F5:** los 10 casos + los 2 del centinela pasan; ruta `/api/codebase-memory-mcp/status` registrada y SIN doble prefijo; flag en FLAG_REGISTRY categorizada en "avanzado"; flag default OFF; 3 guías existen; tsc 0 errores (si card incluida).

**Impacto por runtime:** la integración MCP la instala el operador aparte; los 3 runtimes siguen operativos sin el MCP (flag OFF).

**Flag F5:** `STACKY_CODEBASE_MEMORY_MCP_ENABLED` default **OFF**, `env_only=False` (UI vía FLAG_REGISTRY).

**Trabajo del operador F5:** si decide usarlo, instala el MCP aparte siguiendo la guía. Con flag OFF, nada cambia.

---

### F6 — Reporte final + ratchet (test byte-idéntico con flag OFF)

**Objetivo:** consolidar el reporte versionado y garantizar que el flag (si F5 se implementó) es byte-idéntico a OFF.

**Trabajo:**

```text
# docs/_evals/codebase-memory-mcp/report.md (NUEVO) — estructura:
# 1. Resumen ejecutivo (decisión A/B/C + scorecard D1-D9 resumida).
# 2. Hallazgos E1-E7 (links a notas F0-F3).
# 3. Scorecard D1-D9 completa.
# 4. Decisión y justificación.
# 5. Si (B): pasos de instalación (link a F5 guides).
# 6. Reproducibilidad: comandos exactos para re-correr (incluye queries.md y commit SHA).
```

**Archivos exactos F6:**
- `docs/_evals/codebase-memory-mcp/report.md` (NUEVO).
- `backend/tests/test_plan76_ratchet_byteidentical.py` (NUEVO) — si F5 implementado.

**Tests F6 (TDD primero, si F5 implementado):**
- Archivo: `backend/tests/test_plan76_ratchet_byteidentical.py`. Casos:
  1. Flag OFF → `GET /api/codebase-memory-mcp/status` devuelve `enabled: false` (200, no rota nada).
  2. **[C8/C10] Byte-identidad concreta (token específico, NO genérico):** con flag OFF, `build_agent_env(...)` (o el prompt final que arma el runner) **no contiene** la subcadena **`codebase-memory-mcp`** — assert sobre el dict/str real. **NO asertar contra `mcpServers`/`mcp_servers`**: ese substring YA existe del MCP interno (`stacky_mcp.py:64-65`, clave `"stacky"`), por lo que asertarlo daría FALSO-FALLO con `CLAUDE_CODE_CLI_MCP_ENABLED` ON. El token del plan es único y libre de colisión.
  3. Ratchet verde: `test_plan76_codebase_memory_mcp.py`, `test_plan76_routes_registered.py` y `test_plan76_ratchet_byteidentical.py` registrados en `HARNESS_TEST_FILES` (Plan 49).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan76_ratchet_byteidentical.py tests/conformance/test_harness_ratchet.py -q`.

**Criterio binario F6:** `report.md` existe y es reproducible; si F5 implementado, los 3 casos pasan; ratchet verde.

**Impacto por runtime:** ninguno. **Trabajo del operador F6:** ninguno.

---

## 6. Las 3 opciones de decisión (mutuamente excluyentes)

- **(A) ADOPTAR-CORE**: se incluye en el bundle de Stacky, default ON. **Requiere D3 APROBADO (SLSA-3) + D9 APROBADO (sin egress) + PoC F2 exitosa + D1+D2+D5+D7 APROBADO.** No recomendado preliminar (riesgo supply-chain sobre core). **Si F1 descarta A (D3 ≠ APROBADO) o D9 ≠ APROBADO, esta opción se elimina.**
- **(B) ADOPTAR-OPCIONAL-NO-CORE** *(recomendación preliminar, sujeta a F0-F4)*: el operador lo activa por flag `STACKY_CODEBASE_MEMORY_MCP_ENABLED` default OFF (editable por UI). Stacky no lo empaqueta; el operador lo instala aparte y Stacky sólo describe cómo. Requiere D1+D2+D7+D8 APROBADO **y D9 ≠ RECHAZADO**.
- **(C) RECHAZAR**: si D3 = RECHAZADO, **o** D7 = RECHAZADO, **o** D9 = RECHAZADO, **o** PoC F2 delta_tokens = 0, **o** D1 = RECHAZADO.

---

## 7. Riesgos y mitigaciones

1. **R1 — Supply-chain (binario externo).** Mitigación: gate F1 (SLSA-3, D3); opción B (opt-in) si D3 es DUDOSO; PoC en sandbox F2; decisión HITL en F4.
2. **R2 — Falsa promesa de reducción de tokens.** Mitigación: F2 mide `delta_tokens` numérico con protocolo fijo y queries congeladas (C5); si delta ≤ 0, D5 = RECHAZADO → C.
3. **R3 — Solapamiento con `repo_map.py`.** Mitigación: F0-E4 **refuta** su existencia; se reformula como complementariedad con `REPO_MAP.md` **y** verificación vs MCP interno (C4). D4 según evidencia.
4. **R4 — Windows edge case.** Mitigación: F3 incluye verificación Windows real (D8); documentar workaround si procede.
5. **R5 — Codex o Copilot no soportan MCP.** Mitigación: F3-E5 verifica cada runtime; D1 baja a DUDOSO/RECHAZADO si <3/3. **No se asume soporte.**
6. **R6 — Indexación ejecuta código del repo.** Mitigación: F2 verifica `sin_ejecucion_de_codigo == true`; si false, D5 = RECHAZADO.
7. **R7 — Exfiltración del codebase (egress).** Mitigación **[C6]**: F2/D9 corre el MCP en sandbox "deny egress" y registra `egress_local_only`; si intenta salir sin declararlo, D9 = RECHAZADO → C.
8. **R8 — Doble-prefijo `/api/api` o blueprint en app.py.** Mitigación **[C1]**: F5 registra el blueprint en `api/__init__.py` con `url_prefix="/codebase-memory-mcp"`; centinela `test_plan76_routes_registered.py` lo hace imposible de falsear.
9. **R9 — Flag invisible en la UI (viola regla dura).** Mitigación **[C2]**: F5 registra `FlagSpec(env_only=False)` en FLAG_REGISTRY + key en `_CATEGORY_KEYS["avanzado"]`; test caso 10 lo verifica.
10. **R10 — Falsos verdes en la PoC.** Mitigación: F2 reporta números crudos + commit SHA; reproducible con `queries.md`.
11. **R11 — Falso-fallo del ratchet por colisión `mcpServers`.** Mitigación **[C10]**: el MCP interno (`stacky_mcp.py:64-65`, clave `"stacky"`) ya emite `mcpServers`; el server externo usa clave única `"codebase-memory-mcp"` y el assert de byte-identidad (F6 caso 2) mira SOLO ese token, nunca el genérico `mcpServers`.
12. **R12 — Colisión de claves de server MCP.** Mitigación **[ADICIÓN ARQUITECTO v3]**: contrato fijo — clave externa `"codebase-memory-mcp"` ≠ interna `"stacky"`; F3 verifica coexistencia de ambos servers en el config del runtime.

---

## 8. Fuera de scope

- **NO** empaquetar el binario dentro del deploy de Stacky.
- **NO** indexar repos arbitrarios del filesystem del operador sin consentimiento explícito por proyecto.
- **NO** reemplazar `REPO_MAP.md`, el MCP interno de Stacky, ni un futuro mapa estructural (coexistencia).
- **NO** auth/RBAC (mono-operador, sin login).
- **NO** modificar el runtime del agente ni los prompts (los 3 runtimes siguen operativos sin el MCP).
- **NO** garantizar que la decisión es (B): la decisión la produce la evidencia F0-F4.

---

## 9. Glosario

- **codebase-memory-mcp:** servidor MCP (https://github.com/DeusData/codebase-memory-mcp) que indexa un codebase en un knowledge graph persistente y responde queries estructurales vía MCP.
- **MCP:** Model Context Protocol; permite a un runtime (Claude Code, Codex, Copilot) consumir herramientas externas. **Stacky ya tiene un server MCP propio** (`stacky_get_skill`, `CLAUDE_CODE_CLI_MCP_ENABLED`).
- **SLSA-3:** Supply-chain Levels for Software Artifacts, nivel 3; proveniencia verificable del build. Gate de la opción A (D3).
- **Egress (D9):** tráfico de red saliente; un MCP que indexa el codebase no debe exfiltrarlo. Gate de adopción (C6).
- **Scorecard D1-D9:** 9 criterios de decisión (sección 4) con veredicto APROBADO/DUDOSO/RECHAZADO.
- **FLAG_REGISTRY / FlagSpec:** registro declarativo en `services/harness_flags.py` que hace visible una flag en la UI **sin tocar el frontend** (regla del módulo, líneas 5-7).
- **`STACKY_CODEBASE_MEMORY_MCP_ENABLED`:** flag opt-in (default OFF, editable por UI vía FLAG_REGISTRY).
- **Ratchet:** mecanismo del Plan 49 que obliga a registrar todo test nuevo en `HARNESS_TEST_FILES`.
- **HITL:** Human-in-the-loop; el operador revisa y aprueba la decisión F4.
- **`REPO_MAP.md`:** mapa estructural estático citado en `CLAUDE.md`, generado por script externo. **`repo_map.py`:** REFUTADO, no existe.

---

## 10. Orden de implementación

1. **F0** — Investigación preliminar → `notes-E1-E2-E4-E7.md`.
2. **F1** — Gate SLSA-3 (opción A go/no-go) → `decision-A-gate.md`.
3. **F2** — PoC sandbox: tokens + **egress (D9)** → `queries.md`, `poc-metrics.md`.
4. **F3** — Integración 3 runtimes + D4 (vs REPO_MAP.md y MCP interno) + D6 → `integration-3-runtimes.md`, `maintenance-model.md`.
5. **F4** — Decisión final A/B/C con scorecard D1-D9 → `decision.md` (HITL: operador aprueba).
6. **F5** — **Si (B):** flag (registrada en FLAG_REGISTRY) + endpoint (`api/__init__.py`) + helpers puros + 3 guías + card read-only opcional + centinela de rutas. **Si (A) o (C):** saltar.
7. **F6** — Reporte final + ratchet byte-idéntico concreto.

Cada fase es auto-contenida y se puede ejecutar/commitear de forma independiente.

> **Aislamiento:** este plan **NO depende de 70, 71, 72, 73, 74 ni 75**. No toca `TrackerProvider`, `tickets.py`, ni ningún consumidor del puerto.

---

## 11. DoD global (Definition of Done)

- [ ] **(a)** `notes-E1-E2-E4-E7.md` existe y cita URLs reales del repo (F0).
- [ ] **(b)** `decision-A-gate.md` declara D3 con comando de verificación; si D3 ≠ APROBADO, A descartada por escrito (F1).
- [ ] **(c)** `poc-metrics.md` reporta `delta_tokens` numérico + `sin_ejecucion_de_codigo` + `egress_local_only` (F2); `queries.md` congela las 10 queries + commit SHA.
- [ ] **(d)** `integration-3-runtimes.md` declara D1 por runtime + coexistencia con MCP interno; `maintenance-model.md` declara D6 (F3).
- [ ] **(e)** `decision.md` declara A|B|C con scorecard D1-D9 completa y consistente (F4).
- [ ] **(f)** Si (B): flag `STACKY_CODEBASE_MEMORY_MCP_ENABLED` default OFF **en FLAG_REGISTRY (categoría "avanzado")** + endpoint en `api/__init__.py` + 3 guías; `test_plan76_codebase_memory_mcp.py` (10 casos) verde (F5).
- [ ] **(g)** **Centinela de rutas** `test_plan76_routes_registered.py` verde: `/api/codebase-memory-mcp/status` registrada, sin doble prefijo (F5).
- [ ] **(h)** `report.md` reproducible con comandos exactos (F6).
- [ ] **(i)** Ratchet verde con los `test_plan76_*` registrados en `HARNESS_TEST_FILES`.
- [ ] **(j)** `tsc` 0 errores (si card incluida).
- [ ] **(k)** Los 3 runtimes operativos sin cambios (el plan no toca prompts/runtime); byte-identidad con flag OFF verificada (F6 caso 2).
- [ ] **(l)** **Riel supply-chain cumplido:** si D3 ≠ APROBADO, A descartada por escrito (F1); si D9 = RECHAZADO, adopción descartada (F2).

---

## 12. Notas de implementación (para el modelo menor que ejecute esto)

- **Este plan es una evaluación, no una feature.** La mayor parte del "trabajo" es investigación + documentación en `docs/_evals/codebase-memory-mcp/`. Sólo F5 (si decisión B) añade código.
- **Venv del repo:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest <test> -q` (py3.13, memoria `stacky-backend-dev-test-env`).
- **[C1] Blueprint:** SIEMPRE `url_prefix="/codebase-memory-mcp"` y `api_bp.register_blueprint(...)` en `api/__init__.py`. NUNCA en `app.py`, NUNCA `url_prefix="/api/..."` (daría `/api/api/...`). Verificalo con el centinela.
- **[C2] Flag visible en UI:** SIEMPRE agregar el `FlagSpec` a `FLAG_REGISTRY` + la key a `_CATEGORY_KEYS["avanzado"]`. NO tocar `HarnessFlagsPanel.tsx` (renderiza desde el registro).
- **[C3] Atributo config.py:** patrón `os.getenv("...","false").lower() in ("1","true","yes")`. NUNCA `: bool = False` (no leería el env).
- **Patrón mock (F5):** `mcp_installation_status` y `build_installation_guide` son PURAS (sin red, sin binarios); testear con config mock y strings.
- **Cada commit deja el sistema verde y backward-compatible.**
- **Falsos verdes prohibidos:** F2 reporta números crudos + SHA; F4 decisión consistente con reglas; F6 byte-idéntico con assert concreto (C8).
- **`repo_map.py` NO existe** (refutado). El único mapa estructural es `REPO_MAP.md` (externo).
- **El operador decide en F4** (HITL). El implementador produce evidencia, no impone decisión.
- **Si una fase revela un GAP no listado en la scorecard**, detener y actualizar este doc antes de seguir.
- **No empaquetar el binario del MCP.**
