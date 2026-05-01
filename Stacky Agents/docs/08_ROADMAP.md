# 08 — Roadmap de implementación + features game-changer

> Doc de producto. Convierte la visión de Stacky Agents en un plan ejecutable, fase por fase,
> con métricas de éxito por hito y un catálogo de features que llevan al producto desde
> "workbench útil" a **infraestructura crítica de la empresa**.

---

## TL;DR

```
Q1 2026 — Foundation     ▶ MVP runnable, equipo interno usándolo
Q2 2026 — Integration    ▶ Reemplaza Stacky Pipeline para 60% de tickets
Q3 2026 — Intelligence   ▶ Memoria, sugerencias, multi-LLM routing
Q4 2026 — Collaboration  ▶ Multi-usuario, Slack/Teams, mobile
Q1 2027 — Platform       ▶ Marketplace de agentes, multi-cliente, compliance
Q2 2027 — Game-changer   ▶ Self-improving, voice, knowledge graph
```

El objetivo de 2026 no es "tener Stacky Agents corriendo" — es **convertir el ciclo de tickets en una ventaja competitiva medible** (50% menos tiempo a primer entregable, 3x throughput de tickets, > 80% satisfacción de operadores).

---

## Principios rectores del roadmap

1. **Valor antes que perfección.** Cada hito entrega algo usable en producción, no un demo.
2. **Una fase nueva no empieza hasta que la anterior cumple su métrica de éxito.**
3. **No hay big-bangs.** Toda feature game-changer entra detrás de un feature flag y se prueba con un subconjunto.
4. **Telemetría desde el día 1.** No agregamos features nuevas sin saber cómo se usan las existentes.
5. **El humano siempre puede salir del sistema.** Cada automatización tiene un "edit manual" disponible.
6. **Compatibilidad hacia atrás dentro del año.** APIs versionadas; contratos no se rompen sin v2.

---

## Fase 0 — Scaffold (✅ completada)

**Estado:** entregada en este branch.

- Documentación de diseño completa (00–07).
- Backend Flask runnable con `LLM_BACKEND=mock`.
- Frontend React/Vite navegable end-to-end con datos de seed.
- Modelo de datos definido y migrable.
- 5 packs declarados.

**Próximo paso:** validar la UX con 3 operadores internos antes de invertir en integración.

---

## Fase 1 — Foundation (Q1 2026 · 6 semanas)

> Objetivo: Stacky Agents corre sobre el engine real de Stacky, con un equipo interno usándolo a diario sobre un subconjunto de tickets etiquetados.

### Scope

| # | Deliverable | Estimación |
|---|---|---|
| 1.1 | Reemplazar `copilot_bridge.py` mock por el de Stacky existente | 1 sem |
| 1.2 | `/api/tickets` lee ADO real vía `issue_provider/` | 0.5 sem |
| 1.3 | `/api/executions/:id/publish-to-ado` escribe comentarios reales | 0.5 sem |
| 1.4 | Auth básica (Azure AD via `msal-flask` o header confiable detrás de VPN) | 0.5 sem |
| 1.5 | Telemetría: `analytics_events` table + dashboard interno mínimo | 0.5 sem |
| 1.6 | Tests E2E de los 5 agentes en CI (con prompts canónicos) | 1 sem |
| 1.7 | Smoke deploy en VM interna + nginx | 0.5 sem |
| 1.8 | Onboarding 3 operadores internos + feedback loop semanal | 1 sem |

### Métricas de éxito (gate para Fase 2)

- 3 operadores internos completaron > 20 ejecuciones cada uno.
- > 60% de outputs aprobados sin re-run.
- 0 incidentes de seguridad / pérdida de datos.
- Latencia p95 de un Run de Functional < 60s.
- NPS interno > 7 (encuesta corta).

### Riesgos
- El bridge real puede tener side-effects que el mock no expone → mitigación: smoke test exhaustivo en sandbox antes de cada release.
- ADO PAT con permisos insuficientes para publicar → mitigación: documentar scope mínimo y validar en dia 1.

---

## Fase 2 — Integration (Q2 2026 · 8 semanas)

> Objetivo: Stacky Agents reemplaza al pipeline automático para el 60% de los tickets activos. Coexistencia controlada con Stacky Pipeline.

### Scope

| # | Deliverable | Estimación |
|---|---|---|
| 2.1 | Migración de QA agent (100% tráfico) | 1 sem |
| 2.2 | Migración de Technical agent (100% tráfico) | 1.5 sem |
| 2.3 | Migración A/B de Functional agent (50/50 durante 2 sem) | 2 sem |
| 2.4 | Migración Developer agent con doble validación humana | 2 sem |
| 2.5 | **Diff visual** entre execs (UI) | 0.5 sem |
| 2.6 | **Re-run con edición** completo + indicación visual de clones | 0.5 sem |
| 2.7 | **Dry-run de packs** | 0.5 sem |
| 2.8 | Postgres en lugar de SQLite | 0.5 sem |

### Métricas de éxito

- 4 agentes en 100% en Agents (sólo Business no viaja porque es nuevo).
- Tiempo medio ticket → primer output útil bajó ≥ 30% vs pipeline.
- Tasa de aprobación primera-pasada > 70%.
- 0 incidentes de pérdida de auditoría.

### Game-changer features que entran acá

- 🎯 **F1 — Diff side-by-side de outputs** entre dos ejecuciones del mismo agente: detección visual de regresiones de prompt.
- 🎯 **F2 — Dry-run** de packs: pre-visualiza prompts sin gastar tokens; convierte el pack en una herramienta de auditoría además de ejecución.

---

## Fase 3 — Intelligence (Q3 2026 · 10 semanas)

> Objetivo: el sistema **aprende** de cada ejecución. Ya no es un workbench inerte — propone, prioriza, sugiere.

### Scope

#### 3.1 — Memoria por proyecto / por usuario (3 sem)
Tabla `agent_memories` con:
- patrones de outputs aprobados (vectorizados)
- bloques de contexto que el operador agrega siempre manualmente
- outputs descartados con razón (texto libre que el operador opcionalmente provee)

Cada Run consulta esta memoria y enriquece el system prompt con: "en este proyecto los Functional approvados suelen incluir: actores, restricciones legales, criterios SLA".

#### 3.2 — Auto-fill inteligente (2 sem)
El editor sugiere bloques no-obvios:
- "esta exec previa de Technical para ADO-1100 podría ser relevante (similitud 87%)"
- "el RIDIOMA SMS_FAIL ya fue cargado en otro ticket reciente"

Implementación: embeddings de `output` + `input_context` con índice FAISS o pgvector.

#### 3.3 — Multi-LLM routing (2 sem)
Por agente, por bloque, por tipo de tarea: routing entre `claude-haiku` (barato, rápido) y `claude-opus` (caro, complejo).
Política por default:
- Functional → Sonnet
- Technical exploración → Haiku, Technical análisis profundo → Opus
- Developer → Sonnet
- QA → Haiku (verificación), Opus si verdict ambiguo

UI: el operador ve qué modelo va a usar y puede forzar otro.

#### 3.4 — Quality scoring por agente (1.5 sem)
Cada exec obtiene un score 0–100 basado en:
- ¿coincide la estructura con el template esperado?
- ¿cita las fuentes que pidió el system prompt?
- ¿tiene los marcadores TU-001..N (Technical) o `// ADO-{id}` (Developer)?
Score visible en el OutputPanel; execs < 50 muestran warning.

#### 3.5 — Context budget optimizer (1.5 sem)
Cuando el contexto excede el límite, el sistema sugiere automáticamente qué bloques recortar primero (los menos similares al pedido del agente). Operador acepta o ajusta.

### Métricas de éxito

- Tasa de aprobación primera-pasada > 80% (sube de 70%).
- Costo medio por exec baja ≥ 40% gracias a multi-LLM routing.
- > 50% de Runs usan al menos un bloque sugerido por auto-fill inteligente.

### Game-changer features

- 🎯 **F3 — Memoria por proyecto** que se enriquece sin entrenamiento manual.
- 🎯 **F4 — Multi-LLM routing transparente** — el operador ve y override el modelo.
- 🎯 **F5 — Quality scoring** automático que detecta outputs sospechosos antes de aprobarlos.

---

## Fase 4 — Collaboration (Q4 2026 · 8 semanas)

> Objetivo: Stacky Agents deja de ser un workbench solo y se convierte en infraestructura **del equipo**.

### Scope

#### 4.1 — Multi-usuario en vivo (2 sem)
Presencia (👤 ana@ está viendo este ticket) + colaboración asíncrona robusta. Sin edición concurrente del mismo bloque (lock optimista). El historial es shared.

#### 4.2 — Handoff explícito de packs (1 sem)
Operador A inicia pack, en paso 2 lo "asigna" a operador B con nota. B recibe notif y retoma desde donde quedó. Cada paso queda con su `started_by`.

#### 4.3 — Slack / Teams integration (2 sem)
- Bot que postea en `#stacky-agents` cuando se aprueba una exec o falla un pack.
- Slash command `/stacky-run technical ADO-1234` que dispara desde chat (con ack en thread).
- Notif de "tu pack está esperando handoff" → click → abre la app en el ticket.

#### 4.4 — Mobile companion (read + approve) (2 sem)
PWA simple para iOS/Android: ver historial del ticket, leer outputs (markdown), aprobar/discard. Sin editor — sólo decisión. Útil para el lead que quiere desbloquear sin abrir laptop.

#### 4.5 — Templates compartidos por equipo (1 sem)
Una exec aprobada puede convertirse en "template" — el editor permite cargarla como punto de partida para futuras execs del mismo agente. Templates por proyecto / por equipo / privados.

### Métricas de éxito

- > 30% de packs cruzan más de un operador (handoff).
- > 50% de aprobaciones llegan vía mobile o Slack en horario fuera de oficina.
- > 20% de Runs parten desde un template guardado.

### Game-changer features

- 🎯 **F6 — Handoff colaborativo de packs** — devuelve el "pasamanos" del pipeline pero asincrónico.
- 🎯 **F7 — Slack/Teams como cliente de primera clase** — corrés agentes sin abrir la app.
- 🎯 **F8 — Mobile approve** — desbloqueás tickets desde el celular.

---

## Fase 5 — Platform (Q1 2027 · 12 semanas)

> Objetivo: Stacky Agents se convierte en **plataforma**. Otros equipos crean sus propios agentes; otros clientes la consumen.

### Scope

#### 5.1 — Agent SDK (3 sem)
Definir un agente custom es un archivo Python `my_agent.py` que extiende `BaseAgent`, con su system prompt y `default_blocks`. El sistema lo descubre automáticamente y aparece en el AgentSelector.

Ejemplos posibles: `LegalReviewAgent`, `DBAReviewAgent`, `DocsWriterAgent`, `OnboardingAgent`.

#### 5.2 — Agent marketplace interno (2 sem)
Repo `stacky-agents-registry` con agentes contribuídos por distintos equipos. Versionado, descripción, `installed_in: [pacifico, cliente_X]`.

#### 5.3 — Multi-tenant / multi-proyecto (3 sem)
Mismo backend sirve a varios proyectos con isolation por `project_id`. Cada proyecto:
- su set de agentes
- su set de packs
- su tabla de memoria propia
- su PAT de ADO

Permite reusar la app en otros clientes Ubimia.

#### 5.4 — Compliance pack (2 sem)
Para clientes regulados (financieras, salud):
- Audit trail inmutable con firma criptográfica del prompt+output.
- Retención configurable por tipo de exec.
- Exportación de evidencia en formato auditor-friendly.
- Opción de PII masking automático antes de mandar al LLM.

#### 5.5 — A/B testing de system prompts (2 sem)
Una variante de un agente puede correr en shadow mode al 5% de los Runs. Comparación automática de quality scores; promote-to-prod cuando mejora estadísticamente.

### Métricas de éxito

- ≥ 3 agentes contribuídos por equipos no-core.
- ≥ 1 cliente nuevo (no-Pacífico) corriendo Stacky Agents en producción.
- A/B framework probó al menos 2 mejoras de prompt en producción.

### Game-changer features

- 🎯 **F9 — Agent SDK + marketplace** — convierte a Stacky Agents en una plataforma extensible, no un producto cerrado.
- 🎯 **F10 — Multi-tenant** — vendible a otros clientes de Ubimia con costo marginal cero.
- 🎯 **F11 — Compliance pack** — habilita verticales reguladas (banca, salud).
- 🎯 **F12 — A/B de prompts** — los prompts mejoran con datos, no con instinto.

---

## Fase 6 — Game-changer (Q2 2027 · 10 semanas)

> Objetivo: features que cambian la relación humano-IA en el ciclo de tickets. No incrementales — diferenciales.

### Scope

#### 6.1 — Self-improving loop (3 sem)
Cada exec descartada o fallida alimenta una memoria de "patrones a evitar". El agente, en su próxima ejecución, recibe en su system prompt: "evitá estos errores comunes en este proyecto: [...]".
Loop cerrado con QA: si QA tira FAIL, el motivo se guarda y se incorpora.
Esto es **continual learning sin entrenamiento de modelo** — sólo prompt-engineering automático.

#### 6.2 — Knowledge graph del codebase (3 sem)
Un servicio que indexa el código (Tools/Stacky existente ya tiene `codebase_indexer.py` y `dependency_graph.py`) en un grafo consultable: clases, métodos, llamadas, tablas, RIDIOMA, relaciones funcionales.
Los agentes Technical y Developer consultan el grafo en lugar de explorar files-by-files. Resultado: contextos 5x más densos, 5x más rápidos.

#### 6.3 — Voice mode (2 sem)
- Dictado: el operador habla, el editor transcribe en el bloque "Notas adicionales".
- Resumen hablado: cuando una exec termina, el operador puede pedir "leéme el output" y escuchar mientras camina.
- Útil para revisar tickets en transición / commute / cocinando.

#### 6.4 — Replay & time-machine (1 sem)
Cualquier exec puede "reproducirse": el sistema reconstruye exactamente el contexto y muestra cómo evolucionó el output token a token. Útil para training, debug y auditoría.

#### 6.5 — Auto-PR generation (1 sem)
El Developer agent, además del comentario en ADO, genera un branch + diff + PR description. Operador click "Create PR" y se abre en GitHub/ADO Repos. Cierra la última fricción (manual commit + manual PR).

### Métricas de éxito

- Tasa de aprobación primera-pasada > 90%.
- Tiempo ticket → PR mergeable < 1 día calendario p50.
- ≥ 70% de los Runs de Technical usan el knowledge graph (vs exploración por archivos).

### Game-changer features

- 🎯 **F13 — Self-improving loop** — el sistema mejora sin entrenamiento.
- 🎯 **F14 — Knowledge graph** — agentes razonan sobre el código, no leen archivos.
- 🎯 **F15 — Voice mode** — accesibilidad y mobility.
- 🎯 **F16 — Replay & time-machine** — auditabilidad nivel forense.
- 🎯 **F17 — Auto-PR** — del Epic al PR sin tocar git.

---

## Catálogo completo de features game-changer (priorizadas)

> Resumen ejecutivo para presentar al sponsor. Cada feature con: impacto esperado, costo, fase.

| # | Feature | Por qué es game-changer | Impacto | Costo | Fase |
|---|---|---|---|---|---|
| F1 | Diff side-by-side | Detecta regresiones de prompt antes de mergear | M | S | Q2 |
| F2 | Dry-run de packs | Auditoría previa sin gastar tokens | S | S | Q2 |
| F3 | Memoria por proyecto | Sistema aprende patrones aprobados | XL | M | Q3 |
| F4 | Multi-LLM routing | Reduce costo 40% sin perder calidad | XL | M | Q3 |
| F5 | Quality scoring | Cazás outputs malos antes de aprobar | L | S | Q3 |
| F6 | Pack handoff | Recupera el "pasamanos" colaborativo | L | M | Q4 |
| F7 | Slack/Teams agents | Disparo desde chat → 0 fricción | XL | M | Q4 |
| F8 | Mobile approve | Desbloqueo desde celular | M | M | Q4 |
| F9 | Agent SDK + marketplace | Extensibilidad → equipos contribuyen | XL | L | Q1'27 |
| F10 | Multi-tenant | Mismo producto a N clientes Ubimia | XL | L | Q1'27 |
| F11 | Compliance pack | Habilita verticales reguladas | XL | M | Q1'27 |
| F12 | A/B de prompts | Prompts mejoran con datos | L | M | Q1'27 |
| F13 | Self-improving loop | Continual learning sin retraining | XL | L | Q2'27 |
| F14 | Knowledge graph | Razonamiento sobre código, no exploración | XL | XL | Q2'27 |
| F15 | Voice mode | Accesibilidad / mobility | M | M | Q2'27 |
| F16 | Replay & time-machine | Auditoría nivel forense | M | S | Q2'27 |
| F17 | Auto-PR generation | Cierra el loop hasta el PR | XL | M | Q2'27 |

**Costo:** S = ≤ 2 sem · M = 2–4 sem · L = 4–8 sem · XL = > 8 sem
**Impacto:** S = nice-to-have · M = mejora real · L = movés la aguja · XL = redefine el producto

---

## Features adicionales sugeridas (backlog "vault")

Sin asignar a fase. Para sumar al planning trimestral según prioridad.

### Productividad

- **Speculative execution** — mientras el operador edita el contexto del paso N, el sistema pre-corre el paso N+1 con el output esperado en background. Si lo aprueba, ya está listo (latencia percibida = 0). Si lo edita, se descarta.
- **Snippets library** — atajos de bloques frecuentes ("/include-cobranza-tables", "/include-ridioma-master").
- **Inline AI rewrite** — seleccionás un párrafo del output, click "rewrite as more concise" → mini agente reformula.
- **CLI `stacky-agents run`** para power users que prefieren terminal.

### Calidad

- **Confidence scoring del LLM** — el agente devuelve un score 0–100 de confianza por sección; secciones < 70 muestran warning visual.
- **Drift detection** — si un agente da outputs estructuralmente distintos para inputs similares en una semana, alerta al equipo (señal de drift de modelo o cambio en docs base).
- **Ground truth feedback loop** — operador puede marcar "esto está mal porque..." y la razón alimenta el self-improving loop.

### Experiencia

- **Onboarding sandbox** — proyecto con tickets ficticios para que un operador nuevo practique sin riesgo. Persiste su progreso, le da hints contextuales.
- **Theme custom** + temas oficiales por equipo.
- **Keyboard-first navigation completa** — Vim mode opcional para el editor.
- **Diff de prompts** entre versiones del agente (qué cambió en el system prompt, fácil de auditar).

### Operación

- **Cost tracking** por proyecto / equipo / usuario, con budgets y alertas.
- **Rate limiting inteligente** que aprende los patrones de uso.
- **Health dashboard pública del estado de cada agente** (latencia, error rate, costo medio).
- **Failure recovery patterns** — DB de "este error pasó N veces, soluciones que funcionaron".

### Avanzado

- **Agent chaining declarativo** — definir un workflow custom (no sólo packs predefinidos).
- **Sandbox de evaluación** — corre 100 tickets históricos contra una variante del agente y reporta diferencias.
- **Agent introspection** — el operador puede "preguntarle" a un agente "¿por qué decidiste X?" → mini agente meta explica el razonamiento.
- **Embedding-based search** sobre ejecuciones históricas: "encontrá todos los tickets parecidos a este".

---

## Inversión & ROI estimado

| Fase | Tiempo | Equipo (FTE) | Costo aprox | Retorno esperado al final |
|---|---|---|---|---|
| 1 — Foundation | 6 sem | 1 backend + 1 frontend + 0.3 PM | bajo | mismo throughput, mejor UX |
| 2 — Integration | 8 sem | 1.5 BE + 1 FE + 0.5 PM + 1 QA | medio | -30% tiempo a primer output |
| 3 — Intelligence | 10 sem | 2 BE + 1 FE + 0.5 ML + 0.5 PM | medio-alto | -40% costo LLM, +10% aprob. |
| 4 — Collaboration | 8 sem | 1.5 BE + 1.5 FE + 0.5 PM | medio | adopción del equipo total |
| 5 — Platform | 12 sem | 2 BE + 1 FE + 0.5 PM + 0.5 SRE | alto | nuevos clientes pagantes |
| 6 — Game-changer | 10 sem | 2 BE + 1 FE + 1 ML + 0.5 PM | alto | diferenciación competitiva |

**ROI principal:** la combinación de F4 (multi-LLM), F13 (self-improving) y F14 (knowledge graph) reduce el costo por ticket entregado de manera compuesta — estimación conservadora: **5x menos costo a 18 meses**.

**ROI secundario:** F10 (multi-tenant) abre la línea de producto a otros clientes con costo marginal cero — cada cliente nuevo es margen casi puro.

---

## Riesgos transversales

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| El equipo se resiste al cambio (pipeline → workbench) | M | A | Onboarding guiado, packs como puente, opcional Fase 2 |
| Los modelos LLM cambian de precio o capability | A | M | Multi-LLM routing desde Fase 3 desacopla de un único proveedor |
| Crece la deuda técnica del scaffold | A | M | Refactor budget de 10% por fase + tests E2E |
| Compliance / privacidad de datos del cliente | M | A | F11 desde Q1'27 anticipa esto; PII masking opt-in en Fase 3 |
| Otra herramienta interna (futuro) compite | B | M | Diferenciador es la integración profunda con Stacky/ADO/PACÍFICO docs |
| Dependencia de Stacky Pipeline (transitiva) | A | A | Fase 2 documenta cada interfaz reutilizada; Fase 5 las absorbe |

---

## Dependencias externas críticas

| Dependencia | Para qué fase | Owner | Fallback |
|---|---|---|---|
| `Tools/Stacky/copilot_bridge.py` | F1+ | Stacky team | extraer a paquete propio en Fase 5 |
| ADO API + PAT | F1+ | DevOps | ninguno — bloqueante |
| Modelo Claude (Anthropic) | F1+ | proveedor | F4 multi-LLM mitiga |
| pgvector / FAISS | F3+ | infra | usar in-memory para empezar |
| Slack / Teams API | F4 | IT corp | webhook genérico como fallback |
| msal-flask / Azure AD | F1 | IT corp | header confiable detrás de VPN como bridge |

---

## North-star vision a 24 meses

A finales de Q2 2027, **Stacky Agents** es:

1. **El sistema operativo de tickets de Ubimia.** Todos los proyectos lo usan. Cada equipo tiene 2-3 agentes custom. El pipeline original ya no existe.
2. **Un producto vendible.** Al menos 2 clientes externos pagan licencia.
3. **Una ventaja competitiva medible.** Tickets entregables 3x más rápido vs hace 18 meses, con 5x menos costo de LLM.
4. **Una plataforma que se mejora sola.** Cada exec aprobada / descartada alimenta un loop que hace mejor a los siguientes.
5. **Una experiencia que el equipo no quiere abandonar.** NPS > 60.

---

## Cómo se mide el "game-changer"

El éxito no es "tener todas las features". Es mover **3 números**:

| Métrica | Hoy (Stacky Pipeline) | Meta 18 meses (Agents) |
|---|---|---|
| **Tiempo p50 de ticket → PR mergeable** | ~3 días | < 1 día |
| **Costo medio de LLM por ticket entregado** | ~USD 4 | < USD 1 |
| **Tasa de aprobación primera-pasada** | ~50% | > 90% |

Si en Q2 2027 esos tres números no se mueven en ese sentido, el roadmap falló por más features que tengamos. Por eso cada fase tiene su gate de métricas.

---

## Cómo iniciar mañana

**Acciones inmediatas (sin esperar Fase 1 formal):**

1. Designar un sponsor del producto (recomiendo: tech lead que ya usa Stacky Pipeline).
2. Reclutar 3 operadores internos voluntarios para feedback semanal.
3. Asignar 1 backend + 1 frontend con dedicación parcial (50%) a Fase 1.
4. Crear canal `#stacky-agents` para comunicación + soporte.
5. Setear instancia compartida en VM interna con backend + frontend buildados.
6. Primera sesión de demo y collection de pain points concretos.

Fecha objetivo de Fase 1 completada: **junio 2026** (6 sem desde kickoff).

---

# Apéndice A — Moats del agente individual

> Catálogo de features pensadas para que correr **UN solo agente** en Stacky Agents sea
> exponencialmente mejor que correrlo afuera (Copilot Chat, Claude.ai, ChatGPT, terminal).
> Diseñado para handoff: cada feature tiene spec, archivos afectados, criterios de aceptación
> y dependencias, listo para que otro agente lo continúe.

## Pregunta que responde este apéndice

> "¿Por qué pegar mi ticket en Stacky Agents en vez de pegarlo en Copilot Chat?"

Si la respuesta es sólo "porque tiene historial", **no es suficiente**. Acá vive la diferencia real: features que entregan **valor que no podés reproducir afuera ni a mano**.

## Principios de diseño de los moats

1. **Compuestos.** Cada uso debe mejorar al siguiente. Memoria > comodidad.
2. **Datos privilegiados.** El sistema debe poder ver/integrar datos que otra herramienta no.
3. **Ejecución, no sólo redacción.** El sistema verifica, ejecuta, valida — no sólo redacta texto.
4. **Encontrar al operador donde está.** VS Code, Slack, mail, mobile, CLI — no obligar a abrir la app.
5. **Costo y calidad como features visibles.** Mostrar siempre cost/preview/cache.
6. **Auditabilidad como feature, no como burocracia.** Inmutable, citado, replayable.

## Taxonomía de moats

| Categoría | Cuántos moats | Por qué importa |
|---|---|---|
| **A. Context superpowers** | FA-01 → FA-09 | Datos que el agente no podría tener afuera |
| **B. Memory compounding** | FA-10 → FA-16 | Cada ejecución mejora la siguiente |
| **C. Execution enrichment** | FA-17 → FA-23 | Outputs verificados, no sólo redactados |
| **D. Workflow integration** | FA-24 → FA-30 | Encontrar al operador donde está |
| **E. Cost & quality control** | FA-31 → FA-36 | Imposible ad-hoc |
| **F. Compliance & safety** | FA-37 → FA-41 | Habilitador de verticales reguladas |
| **G. Discoverability & coaching** | FA-42 → FA-46 | El sistema enseña a usarse mejor |
| **H. Power-user composability** | FA-47 → FA-52 | Combinaciones únicas |

Total: **52 moats** documentados con spec accionable.

---

## A. Context superpowers (FA-01 → FA-09)

> El agente recibe contexto que **no podés conseguir afuera sin trabajo manual semi-imposible**.

### FA-01 — Cross-ticket retrieval

**Valor exponencial:** "este ticket se parece al ADO-892 que resolvimos hace 6 meses; te enchufo el output del Technical de aquel" — conocimiento histórico inyectado automáticamente.

**Cómo se ve:** al abrir el editor de un ticket nuevo aparece un bloque `[auto] Tickets similares (3)` con previews y checkboxes para incluirlos como contexto.

**Aceptación:**
- Embedding por ejecución almacenado (input_context + output) en pgvector / FAISS.
- Endpoint `GET /api/executions/similar?ticket_id=X&k=5` devuelve top-K.
- Hook en `useAutoFillBlocks.ts` propone los matches con score > 0.7.
- El operador ve el motivo del match ("similar en: dominio cobranzas, módulo SMS").

**Archivos:**
- nuevo `backend/services/similarity.py` (encoder + index manager)
- nuevo `backend/api/similarity.py`
- migration: agregar `agent_executions.embedding VECTOR(1536)`
- frontend: extender `useAutoFillBlocks` con un `useSimilarExecutions(ticketId)`

**Dependencias:** Postgres con pgvector, o FAISS local.
**Fase:** 3 (Intelligence) · **Effort:** L

---

### FA-02 — Live BD context injection

**Valor exponencial:** un bloque `[auto] BD live` que ejecuta SELECTs (read-only) contra una réplica y le mete al agente datos de prueba reales — imposible afuera sin VPN + cliente SQL + ejecución manual.

**Cómo se ve:** bloque sugerido cuando el ticket menciona una tabla. Operador ve el SELECT propuesto, lo aprueba o edita, el resultado (max 10 filas, PII enmascarada) entra al contexto.

**Aceptación:**
- `backend/services/db_context.py` con whitelist de connections + cap de filas.
- LLM auxiliar genera el SELECT a partir de `ticket.description` + tablas detectadas.
- UI muestra preview del SELECT + resultado antes de incluirlo.
- PII masking (FA-37) aplicado siempre.

**Fase:** 3 · **Effort:** M

---

### FA-03 — Codebase semantic search

**Valor exponencial:** "encontrá los archivos relevantes para 'flujo de notificación SMS de cobranza'" devuelve los 5 archivos correctos, sin que el operador conozca la nomenclatura interna del repo.

**Cómo se ve:** el bloque `[auto] Archivos relevantes` se llena con resultados ranked. El operador toggle qué incluye.

**Aceptación:**
- Indexador incremental que vectoriza por símbolo (clase, método, comentario significativo).
- `GET /api/code/search?q=...&top_k=10`.
- Reusa `Tools/Stacky/codebase_indexer.py` como fuente; agrega encoder semántico encima.
- Cache por commit SHA.

**Fase:** 6 (Knowledge graph) · **Effort:** L

---

### FA-04 — Production telemetry context

**Valor exponencial:** "el método `CobranzaService.Procesar()` se invoca 5.2k veces/día; cuidado con el throughput" — el agente recibe métricas reales de prod del código que va a tocar.

**Cómo se ve:** bloque `[auto] Telemetría de producción (últimos 7 días)` con count, p95, error rate por método tocado.

**Aceptación:**
- Conector a APM / logs (App Insights / Grafana / OTel).
- Resolución método → métrica vía symbol map del FA-03.
- Cache 1h.

**Fase:** 5 · **Effort:** L

---

### FA-05 — Git context awareness

**Valor exponencial:** el agente sabe que la última persona que tocó `CobranzaController.cs` fue `juan@` hace 3 días en el commit `abc123` para ADO-1100. Contexto de equipo gratis.

**Cómo se ve:** bloque `[auto] Contexto Git (archivos afectados)` con: últimos 3 commits, autores, blame por método tocado, branches activos relacionados.

**Aceptación:**
- `backend/services/git_context.py` con `git log -p -- {file}` cacheado.
- Hook por archivo en el bloque de docs técnicos.
- Detecta automáticamente PRs abiertos sobre los mismos archivos (alerta).

**Fase:** 3 · **Effort:** M

---

### FA-06 — Test coverage map injection

**Valor exponencial:** "este método no tiene tests unitarios; este otro tiene 23% de cobertura" — el Developer/QA agent prioriza dónde necesita escribir tests.

**Aceptación:**
- Importador de coverage XML/lcov al modelo de datos.
- Bloque `[auto] Cobertura del área` con tabla método/% .
- El Technical agent puede declarar TUs faltantes con prioridad.

**Fase:** 3 · **Effort:** S

---

### FA-07 — Schedule & release context

**Valor exponencial:** "estamos a 2 días del release; sólo crítico" — el agente Technical ajusta sus recomendaciones (no sugerir refactors). El agente QA prioriza regresión.

**Aceptación:**
- Lectura de calendar / iteración ADO.
- Bloque `[auto] Contexto temporal` con próxima fecha de release y nivel de freeze.
- System prompt suffix que incorpora la política activa.

**Fase:** 4 · **Effort:** S

---

### FA-08 — Customer/project constraints injection

**Valor exponencial:** "este cliente exige logs de auditoría obligatorios en cualquier cambio de cobranzas" — restricciones del cliente Pacífico se inyectan automáticamente sin que el operador deba recordarlas.

**Aceptación:**
- Tabla `project_constraints` con reglas tipo `if affects(module=cobranzas) then require(audit_log)`.
- Inyección en system prompt del agente afectado.
- UI para editar restricciones por proyecto.

**Fase:** 5 · **Effort:** M

---

### FA-09 — RIDIOMA / glossary auto-injection

**Valor exponencial:** acrónimos y términos de dominio (RIDIOMA, RTABL, RPARAM, módulos internos) siempre definidos en el contexto. El agente nunca confunde "RIDIOMA" con "idioma".

**Aceptación:**
- Detección de términos en `input_context` por regex/lookup.
- Bloque `[auto] Glosario (5 términos detectados)` con definiciones.
- Reusa `Tools/Stacky/ridioma_knowledge_registry.py`.

**Fase:** 1 · **Effort:** S

---

## B. Memory compounding (FA-10 → FA-16)

> Cada ejecución hace mejor a las siguientes. Imposible reproducir afuera porque vive en BD persistente.

### FA-10 — Personal style memory

**Valor exponencial:** "Juan prefiere outputs concisos; Ana prefiere análisis exhaustivos" — el system prompt incorpora preferencias del operador detectadas de su historial de aprobaciones/discards.

**Aceptación:**
- Job batch que analiza últimos 50 outputs aprobados/descartados por usuario.
- Genera un perfil { length_pref, depth_pref, format_pref }.
- Inyecta en system prompt como nota.
- UI permite ver/editar el perfil.

**Fase:** 3 · **Effort:** M

---

### FA-11 — Anti-pattern registry

**Valor exponencial:** errores que la empresa cometió antes nunca se repiten. Ej: "no uses `decimal.Round` sin MidpointRounding en este proyecto, históricamente causa diferencias en cobranzas".

**Aceptación:**
- Tabla `anti_patterns` (project, agent_type, pattern, reason, examples).
- Operador puede agregar uno desde un output descartado ("guardar este motivo como anti-patrón").
- Inyección automática en system prompts del agente y proyecto.

**Fase:** 3 · **Effort:** M

---

### FA-12 — Best-output few-shot examples

**Valor exponencial:** el sistema usa **tus propios outputs aprobados** como ejemplos few-shot. El agente no tiene que adivinar el estilo: lo aprende.

**Aceptación:**
- Selección de 2-3 best outputs por agent_type + project.
- Inyectados como few-shot en cada Run.
- Refresh semanal (rota ejemplos).

**Fase:** 3 · **Effort:** S

---

### FA-13 — Historical decisions database

**Valor exponencial:** "decidimos NO usar X en 2025-Q3 porque Y" — decisiones quedan vivas y el agente las consulta antes de proponer algo.

**Aceptación:**
- Tabla `decisions` (id, summary, reasoning, tags, made_at, made_by).
- Búsqueda por embedding al armar contexto técnico.
- Bloque `[auto] Decisiones previas relevantes (2)` con link a cada una.

**Fase:** 5 · **Effort:** M

---

### FA-14 — Output graveyard

**Valor exponencial:** todos los outputs descartados son consultables. "¿ya intentamos esta solución antes? sí, en exec #1842, descartada porque..."

**Aceptación:**
- Search semántico sobre outputs con verdict='discarded'.
- Bloque `[auto] Soluciones ya descartadas (similar)` cuando hay match.
- Razón del descarte editable post-hoc.

**Fase:** 3 · **Effort:** S

---

### FA-15 — Project glossary auto-build

**Valor exponencial:** términos detectados en outputs aprobados pasan a un glosario que crece solo. A los 6 meses, el glosario del proyecto es el mejor de la empresa.

**Aceptación:**
- Job batch extrae términos en bold/`code` de outputs aprobados.
- Pide confirmación humana antes de promote a glosario oficial.
- Editable.

**Fase:** 4 · **Effort:** M

---

### FA-16 — Drift detection sobre prompts

**Valor exponencial:** si el mismo agente con input similar empieza a dar outputs distintos, alerta. Detecta cambios silenciosos del modelo o degradación de docs base.

**Aceptación:**
- Diaria: clusteriza outputs recientes por similitud.
- Si la varianza intra-cluster sube > N stdev, dispara alerta.
- Dashboard en `/admin/drift`.

**Fase:** 4 · **Effort:** M

---

## C. Execution enrichment (FA-17 → FA-23)

> El sistema **ejecuta cosas**. No sólo redacta — verifica, valida, prueba.

### FA-17 — Auto-typecheck del output del Developer

**Valor exponencial:** el código propuesto pasa por compilador / typechecker antes de mostrarlo. Si falla, se marca con squiggles rojos y el botón "Approve" se deshabilita.

**Aceptación:**
- Sandbox de compilación (dotnet build / tsc / etc.) por proyecto.
- Output enriquecido con anotaciones inline.
- Re-prompt automático al agente con los errores si falla.

**Fase:** 3 · **Effort:** L

---

### FA-18 — Auto-execute de SELECTs sugeridos

**Valor exponencial:** el agente Technical sugiere queries de verificación; el sistema las ejecuta y muestra el resultado al lado del output. El operador no tiene que copiar/pegar a SSMS.

**Aceptación:**
- Detección de bloques ```sql en output.
- Ejecución sandboxed (read-only, max 100 filas).
- UI: panel lateral con resultado de cada query.

**Fase:** 2 · **Effort:** M

---

### FA-19 — Output schema validation

**Valor exponencial:** si el Technical agent debe entregar 5 secciones, el sistema lo verifica y rechaza outputs malformados. Garantía de estructura.

**Aceptación:**
- JSON schema por agente (`agents/<type>.schema.json`).
- Post-process valida; si falla, retry automático con error como hint.
- UI: badge "✓ schema OK" o "⚠ schema mismatch".

**Fase:** 2 · **Effort:** S

---

### FA-20 — Citation linker

**Valor exponencial:** cada afirmación del output (`CobranzaController.cs:84`) se renderiza como link clickeable que abre el archivo en el editor del operador. Trazabilidad nivel paper académico.

**Aceptación:**
- Detección regex/AST de `archivo.ext:linea` en outputs.
- Link target configurable (vscode://, file://, ADO Repos).
- Tooltip con preview de las líneas referenciadas.

**Fase:** 2 · **Effort:** S

---

### FA-21 — Auto UML / sequence diagram render

**Valor exponencial:** si el Technical menciona un flujo, se renderiza un diagrama mermaid auto-generado a partir del texto. Comprensión visual gratis.

**Aceptación:**
- Sub-agente "diagrama" que toma el texto y devuelve mermaid.
- Render inline en el OutputPanel.

**Fase:** 4 · **Effort:** M

---

### FA-22 — Output translator

**Valor exponencial:** mismo análisis funcional disponible en español/inglés/portugués con un click. Útil para clientes multi-país.

**Aceptación:**
- Botón en OutputPanel: `[Traducir → en|es|pt]`.
- Cache por hash(output + target lang).
- No re-corre al agente original.

**Fase:** 4 · **Effort:** S

---

### FA-23 — Multi-format export

**Valor exponencial:** el output es markdown, pero un click → PDF para legal, HTML para confluence, mensaje formateado para Slack, draft de email para cliente.

**Aceptación:**
- Endpoint `/api/executions/:id/export?format=pdf|html|slack|email`.
- Templates por formato.
- Frontend: dropdown en OutputActions.

**Fase:** 4 · **Effort:** M

---

## D. Workflow integration (FA-24 → FA-30)

> Encontrar al operador donde está. La app no es la única superficie.

### FA-24 — VS Code extension nativa

**Valor exponencial:** desde VS Code, click derecho sobre un archivo → "Run Technical agent on current ticket using this file as context". El operador no abandona su editor.

**Aceptación:**
- Extension publica en `Tools/Stacky Agents/vscode_extension/`.
- Comandos: `stacky.runAgent`, `stacky.openHistory`, `stacky.includeFile`.
- Status bar muestra ticket activo.
- Logs y output se renderizan en panel propio.

**Fase:** 4 · **Effort:** L

---

### FA-25 — Browser bookmarklet "send as context"

**Valor exponencial:** estás leyendo Confluence / un artículo / docs externos → click bookmarklet → la página entra como bloque al editor del ticket activo.

**Aceptación:**
- Bookmarklet JS que envía URL + selección a `/api/context/inbox`.
- UI muestra "1 nueva fuente disponible" en el editor.

**Fase:** 4 · **Effort:** S

---

### FA-26 — Email-in

**Valor exponencial:** el cliente manda un mail con un brief → forward a `analyze@stacky-agents` → se crea automáticamente una ejecución de Business agent con el mail como contexto.

**Aceptación:**
- Mailbox monitoreado (IMAP) → polls cada 60s.
- Parser extrae sender, subject, body, attachments.
- Crea exec en estado `queued` que el operador aprueba para ejecutar.

**Fase:** 5 · **Effort:** M

---

### FA-27 — Slash commands en Slack/Teams

**Valor exponencial:** `/stacky run technical ADO-1234 con contexto: {tabla afectada: COBRANZA_HEADER}` desde Slack y obtener el output en thread. Sin abrir la app.

**Aceptación:**
- Bot Slack/Teams con verbos: `run`, `status`, `approve`, `discard`.
- OAuth flow para identificar al operador.
- Logs y output renderizados en thread.

**Fase:** 4 · **Effort:** L

---

### FA-28 — PR review hook

**Valor exponencial:** un reviewer @-menciona `@stacky-bot review` en un PR → el agente Technical analiza el diff y postea un comentario. Asistente de code review on-demand.

**Aceptación:**
- Webhook ADO Repos / GitHub.
- Detección de mention.
- Crea exec con el diff como contexto.
- Postea respuesta como comment del PR.

**Fase:** 5 · **Effort:** M

---

### FA-29 — CI failure auto-debug

**Valor exponencial:** un test falla en CI → trigger automático de un Debug Agent que analiza el log + el código → propone causa probable + fix tentativo en un comentario del PR.

**Aceptación:**
- Webhook desde CI con job_id, build_log, commit.
- Nuevo agente `DebugAgent` (extiende BaseAgent).
- Output como comment + sugerencia ejecutable.

**Fase:** 5 · **Effort:** L

---

### FA-30 — CLI `stacky-agents` para terminal

**Valor exponencial:** power users que viven en terminal corren agentes sin abrir browser: `stacky-agents run technical 1234 --include cobranza/`.

**Aceptación:**
- Paquete Python instalable: `pipx install stacky-agents-cli`.
- Comandos: `run`, `status`, `tail`, `approve`, `history`.
- Auth por token + perfil local.

**Fase:** 5 · **Effort:** M

---

## E. Cost & quality control (FA-31 → FA-36)

> Imposibles ad-hoc. Acá vive ahorro real y predecibilidad.

### FA-31 — Output cache por hash

**Valor exponencial:** dos operadores corren el mismo agente con contexto idéntico → la segunda ejecución devuelve el output en < 100ms desde cache. Sin segunda llamada al LLM.

**Aceptación:**
- Hash de `(agent_type, system_prompt_version, input_context_normalizado)`.
- Tabla `execution_cache` con expiración.
- UI marca "🔁 cached" y permite forzar fresh con un click.

**Fase:** 3 · **Effort:** S

---

### FA-32 — Diff-based re-execution

**Valor exponencial:** el operador re-corre con un cambio mínimo en el contexto → el sistema detecta el delta y arma un prompt diferencial ("este es tu output anterior, aplicá sólo este cambio") en lugar de re-procesar todo.

**Aceptación:**
- Cálculo de diff entre input_context previo y nuevo.
- Si diff < 30%, usa estrategia "delta-prompt".
- Métricas: tokens ahorrados por uso.

**Fase:** 3 · **Effort:** M

---

### FA-33 — Cost preview pre-Run

**Valor exponencial:** "este Run va a costar ~$0.42 (modelo Sonnet, 8.4k tokens in)" antes de hacer click. Decidís informado.

**Aceptación:**
- Estimador en tiempo real conforme se editan bloques.
- Visible al lado del botón Run.
- Histórico de variación: "tu costo medio de Functional es $0.18".

**Fase:** 3 · **Effort:** S

---

### FA-34 — Token/cost budgets con enforcement

**Valor exponencial:** "Juan tiene budget de $50/mes; este proyecto $1k/mes" — alertas y bloqueo automático cuando se acerca al límite.

**Aceptación:**
- Tabla `budgets` (scope, period, limit_usd, used_usd).
- Decorator en `agent_runner.run_agent` valida antes de ejecutar.
- UI muestra burndown.

**Fase:** 5 · **Effort:** M

---

### FA-35 — Confidence scoring del LLM

**Valor exponencial:** el agente devuelve un score 0-100 por sección de su output. Secciones con score < 70 muestran banner "⚠ baja confianza, considerá validar". Reduces falsos approves.

**Aceptación:**
- System prompt extendido para que el agente devuelva confidence por sección.
- Parser extrae y renderiza.
- Sección con score bajo no se manda a ADO sin override explícito.

**Fase:** 3 · **Effort:** M

---

### FA-36 — Speculative pre-execution

**Valor exponencial:** mientras el operador escribe notas, el sistema ya está pre-corriendo el agente en background con el contexto actual. Cuando el operador termina y hace click en Run, el output ya está listo (latencia percibida cercana a 0).

**Aceptación:**
- Trigger debounced cuando los bloques quedan estables 5s.
- Pre-exec en background cancelable.
- Si el operador hace Run sin cambios → devuelve el pre-result.

**Fase:** 6 · **Effort:** L

---

## F. Compliance & safety (FA-37 → FA-41)

> Habilitador de verticales reguladas. Sin esto, no hay banca/salud/gobierno.

### FA-37 — PII auto-masking en pre-prompt y logs

**Valor exponencial:** DNI/CUIT/email/teléfono del cliente Pacífico se enmascaran automáticamente antes de mandar al LLM y antes de persistir en logs. Garantía base de privacidad.

**Aceptación:**
- Detección regex + NER opcional.
- Map de masking persistido (para des-enmascarar al renderizar).
- Toggle por proyecto: enforce / warn / off.

**Fase:** 3 · **Effort:** M

---

### FA-38 — Prompt injection detection

**Valor exponencial:** alerta si el `input_context` parece intentar manipular al agente ("ignore previous instructions"). Defensa contra adversariales.

**Aceptación:**
- Heurísticas + clasificador ligero.
- Banner amarillo en el editor antes de Run.
- Bloqueable si el proyecto lo configura strict.

**Fase:** 3 · **Effort:** S

---

### FA-39 — Audit immutability con firma criptográfica

**Valor exponencial:** cada exec firmada con HMAC privado al cierre. Tampering detectable. Cumple requisitos de auditoría externa (BCRA, etc.).

**Aceptación:**
- Hash chain por ticket (cada exec referencia el hash de la anterior).
- Firma con clave HSM/KMS.
- Endpoint de verificación pública.

**Fase:** 5 · **Effort:** M

---

### FA-40 — Right-to-be-forgotten (GDPR)

**Valor exponencial:** un cliente pide borrar sus datos → endpoint que tachiona PII en outputs históricos sin destruir la traza estructural.

**Aceptación:**
- Endpoint admin `/admin/erase` con scope (user_id / customer_id).
- Replace de PII por `[REDACTED]` manteniendo estructura.
- Log de la operación.

**Fase:** 5 · **Effort:** M

---

### FA-41 — Data egress controls

**Valor exponencial:** policy declarativa que define qué proyectos pueden mandar qué tipo de dato a qué LLM. Imposible "enviar prod data al LLM cloud" si la política lo prohíbe.

**Aceptación:**
- Tabla `egress_policies` (project, data_class, allowed_llms[]).
- Pre-flight check en `agent_runner`.
- Hard-block con razón humana-leíble.

**Fase:** 5 · **Effort:** M

---

## G. Discoverability & coaching (FA-42 → FA-46)

> El sistema te enseña a usarlo mejor.

### FA-42 — Suggested next agent

**Valor exponencial:** después de aprobar un Functional, banner: "operadores como vos suelen correr Technical después; ¿lo abro?". Aprende de los caminos populares sin imponer pipeline.

**Aceptación:**
- Markov sobre transiciones agent → agent por proyecto.
- Sugerencia visible post-aprobación.
- Métrica: % aceptadas.

**Fase:** 4 · **Effort:** S

---

### FA-43 — Operator coaching

**Valor exponencial:** "tus últimos 3 Technical fueron descartados. Tip: agregá el bloque de Git context — los Technical aprobados lo incluyen 80% más" — el sistema entrena al operador con datos.

**Aceptación:**
- Análisis comparativo: tu patrón vs patrón de aprobados.
- Notif semanal con 1-2 tips concretos.
- Toggle off-able.

**Fase:** 5 · **Effort:** M

---

### FA-44 — Onboarding sandbox

**Valor exponencial:** un operador nuevo entra y tiene un proyecto demo con 5 tickets ficticios para practicar. Persiste su progreso. Cero riesgo, máximo aprendizaje.

**Aceptación:**
- Proyecto `__sandbox__` aislado.
- Tickets pre-cargados con outputs esperados.
- Modo coaching activado: tooltips paso a paso.

**Fase:** 4 · **Effort:** M

---

### FA-45 — "Show me similar past executions"

**Valor exponencial:** botón en el editor: "ver 5 ejecuciones anteriores parecidas a la que estoy armando". Aprendés por ejemplo en lugar de leer docs.

**Aceptación:**
- Botón abre modal con top-K similares (FA-01).
- Click en una abre su exec en read-only.
- Botón "clone & edit from this".

**Fase:** 3 · **Effort:** S

---

### FA-46 — Org-wide best practices feed

**Valor exponencial:** en home, "esta semana los Technical más aprobados de la empresa contenían: X, Y, Z" — adoptás patrones de equipos vecinos sin reuniones.

**Aceptación:**
- Job semanal genera resumen.
- Dashboard interno + email opcional.
- Filtros por agente / proyecto / equipo.

**Fase:** 5 · **Effort:** S

---

## H. Power-user composability (FA-47 → FA-52)

> Combinaciones únicas a Stacky Agents. Imposibles ad-hoc.

### FA-47 — Agent debate / critic loop

**Valor exponencial:** al aprobar un Technical, opcional: pasa por un "Critic Agent" que lo cuestiona. El operador ve los desafíos y decide si responder o ignorar.

**Aceptación:**
- Nuevo agente meta `CriticAgent`.
- Botón "Run critic" en el OutputPanel.
- Output como challenge list, no re-escritura.

**Fase:** 6 · **Effort:** M

---

### FA-48 — Multi-step prompt refinement

**Valor exponencial:** mismo agente, mismo contexto, 3 prompts en cadena: "primero analizá", "ahora critica tu propio análisis", "ahora refiná". Imposible en Copilot Chat sin 3 turnos manuales.

**Aceptación:**
- UI: botones "+1 paso de refinamiento".
- Cada step persiste como sub-exec.
- Output final agrega los 3.

**Fase:** 6 · **Effort:** M

---

### FA-49 — Parallel exploration

**Valor exponencial:** mismo agente, mismo contexto, **3 ejecuciones en paralelo con diferentes seeds/modelos**. Operador elige la mejor o las funde manualmente.

**Aceptación:**
- UI: toggle "explorar variantes (3)".
- 3 execs simultáneas.
- OutputPanel muestra los 3 lado a lado.

**Fase:** 6 · **Effort:** M

---

### FA-50 — Agent forking inline

**Valor exponencial:** "para este ticket, quiero el Technical pero con un system prompt custom (one-off)". Editás el prompt, corrés, y la variante existe sólo para esta exec — sin tocar la definición global.

**Aceptación:**
- UI: "edit system prompt for this run only".
- Exec persiste el prompt usado en metadata.
- No se promueve a definición de agente sin acción explícita.

**Fase:** 5 · **Effort:** S

---

### FA-51 — Macros declarativas

**Valor exponencial:** el operador define una vez "Macro Hotfix": run Technical con flag bug → si verdict OK run Developer → si falla compile run Critic. Reusable por todo el equipo.

**Aceptación:**
- DSL YAML simple para macros.
- Editor visual de macros.
- Ejecución es un PackRun custom.

**Fase:** 6 · **Effort:** L

---

### FA-52 — Webhook out on exec.completed

**Valor exponencial:** otros sistemas (CI, Slack, dashboards, propios) reaccionan a una exec aprobada sin polling. Stacky Agents pasa a ser hub.

**Aceptación:**
- Tabla `webhooks` (project, event, url, secret).
- Delivery con retry + backoff.
- Dashboard de salud por webhook.

**Fase:** 5 · **Effort:** S

---

## Mapa de moats por fase

| Fase | Moats que entran | Subtotal |
|---|---|---|
| **1 — Foundation** | FA-09 | 1 |
| **2 — Integration** | FA-18, FA-19, FA-20 | 3 |
| **3 — Intelligence** | FA-01, FA-02, FA-05, FA-06, FA-10, FA-11, FA-12, FA-14, FA-17, FA-31, FA-32, FA-33, FA-35, FA-37, FA-38, FA-45 | 16 |
| **4 — Collaboration** | FA-07, FA-15, FA-16, FA-21, FA-22, FA-23, FA-24, FA-25, FA-27, FA-42, FA-44 | 11 |
| **5 — Platform** | FA-04, FA-08, FA-13, FA-26, FA-28, FA-29, FA-30, FA-34, FA-39, FA-40, FA-41, FA-43, FA-46, FA-50, FA-52 | 15 |
| **6 — Game-changer** | FA-03, FA-36, FA-47, FA-48, FA-49, FA-51 | 6 |

Total: **52 moats** distribuidos a lo largo del roadmap.

---

## Cómo otro agente debe continuar este trabajo

> Sección operativa: handoff explícito.

### Cuando se asigna un FA-XX a un agente Claude / dev humano:

1. **Leer el moat completo** acá. La spec contiene el "qué" y el "por qué exponencial".
2. **Cruzar con el roadmap** ([docs/08_ROADMAP.md](08_ROADMAP.md)) para confirmar fase + dependencias.
3. **Cruzar con la arquitectura** ([docs/02_ARCHITECTURE.md](02_ARCHITECTURE.md)) para encontrar dónde encaja.
4. **Para backend:** crear/modificar archivos en `Tools/Stacky Agents/backend/`. Idealmente:
   - Lógica nueva en `backend/services/<feature>.py` (no en endpoints).
   - Endpoints en `backend/api/<area>.py`.
   - Tests en `backend/tests/test_<feature>.py`.
5. **Para frontend:** componentes en `Tools/Stacky Agents/frontend/src/components/`, hooks en `frontend/src/hooks/`, tipos en `frontend/src/types.ts`.
6. **Para data model changes:** una migration nueva en `backend/migrations/versions/` (Alembic) — nunca modificar `models.py` sin migration.
7. **Para system prompts:** editar `agents/<type>.py`. Cualquier cambio es change-managed (FA-12 ya plantea versioning).
8. **Tests obligatorios:** un E2E mínimo por feature. El moat es inútil si rompe en silencio.

### Convenciones para PRs de moats

- Branch: `moat/FA-XX-<slug>` (ej: `moat/FA-01-cross-ticket-retrieval`).
- Commit: `[FA-XX] <título corto>`.
- PR description debe incluir:
  - Link al moat acá.
  - Resumen de la implementación.
  - Tests agregados.
  - Métrica esperada (cómo sabremos que el moat funciona).
- Aprobación: el sponsor del producto + 1 review técnica.

### Cómo priorizar entre moats de la misma fase

Cuando un agente pueda elegir, priorizar por:

1. **Habilitadores** (otros moats dependen de este). Ej: FA-01 habilita FA-45 y FA-14.
2. **Reducción de costo medible.** FA-31 / FA-32 / FA-04 routing.
3. **Reducción de fricción para el operador.** FA-09, FA-18, FA-20.
4. **Riesgos de compliance.** FA-37 antes de empezar a procesar datos productivos.

### Cómo agregar un moat nuevo

Si descubrís uno nuevo durante implementación:

1. Asignale el siguiente ID disponible (`FA-53`, `FA-54`, ...).
2. Agregalo a la categoría que corresponde (A–H).
3. Llená la spec con la misma plantilla:
   - Valor exponencial (1 oración)
   - Cómo se ve (UX concreta)
   - Aceptación (3-5 bullets)
   - Archivos
   - Dependencias
   - Fase + Effort (S/M/L/XL)
4. Actualizá el "Mapa de moats por fase".
5. Actualizá el contador total ("52 moats" → "53 moats").

### Plantilla copy-paste para un moat nuevo

```markdown
### FA-XX — <Nombre>

**Valor exponencial:** <1 oración. Por qué afuera no se puede.>

**Cómo se ve:** <UX concreta. Qué ve el operador.>

**Aceptación:**
- <criterio 1>
- <criterio 2>
- <criterio 3>

**Archivos:**
- <archivo nuevo o modificado>
- ...

**Dependencias:** <otros FA-XX, servicios externos>
**Fase:** <1-6> · **Effort:** <S/M/L/XL>
```

---

## Cierre del apéndice

La pregunta original era: **¿por qué usar Stacky Agents en vez de correr el agente afuera?**

Después de 52 moats catalogados, la respuesta es:

> Porque cada Run en Stacky Agents:
> - **sabe más** que vos (FA-01 a FA-09)
> - **mejora con cada uso** (FA-10 a FA-16)
> - **verifica lo que dice** (FA-17 a FA-23)
> - **te encuentra donde estás** (FA-24 a FA-30)
> - **te cobra menos y mejor** (FA-31 a FA-36)
> - **te cubre la espalda en compliance** (FA-37 a FA-41)
> - **te enseña a usarlo mejor** (FA-42 a FA-46)
> - **te deja componer cosas que afuera no podés** (FA-47 a FA-52)

Ningún operador, en ninguna empresa con esta combinación instalada, vuelve a Copilot Chat para una tarea seria. Ese es el moat real: no una feature, **la suma**.
