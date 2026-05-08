# 09 — Evolución Estratégica V2: Stacky Agents como Ventaja Competitiva

> **Rol:** Principal Product Architect + Staff Engineer — Sistemas Agénticos
> **Fecha:** 2026-04-28
> **Propósito:** Elevar el producto de "workbench útil" a "infraestructura de ventaja competitiva irreemplazable".

---

## TL;DR

El roadmap actual construye las bases correctas. Pero tiene tres brechas críticas que impiden responder la pregunta central:

> **¿Por qué usar esto en lugar de abrir VS Code + Copilot y hacerlo manual?**

Las brechas son:
1. **Sin memoria activa** — el sistema acumula historial pero no lo usa para pensar
2. **Sin ejecución adaptativa** — los packs son lineales; el trabajo real no lo es
3. **Sin inteligencia de código** — el operador sigue eligiendo manualmente qué contexto incluir

Las features propuestas acá cierran esas brechas y agregan tres capas que VS Code + Copilot no puede replicar sin convertirse en Stacky Agents.

---

## PARTE 1 — Análisis Crítico del Roadmap Actual

### ✅ Lo que está bien

| Aspecto | Por qué funciona |
|---|---|
| Paradigma workbench (no pipeline) | Resuelve la queja real de los operadores — control sin rigidez |
| Historial inmutable de ejecuciones | Base correcta para auditoría, replay y aprendizaje |
| Agent Packs como puente | Reduce fricción sin volver al daemon automático |
| Multi-LLM routing (F4) | Decisión técnica correcta — desacopla del proveedor y baja costo |
| Quality scoring (F5) | Cierra el loop de calidad sin requerir evaluación humana siempre |
| A/B de prompts (F12) | Los prompts mejorar con datos, no con instinto — diferenciador real |
| Knowledge graph (F14) | Dirección correcta, aunque llega demasiado tarde (Q2'27) |

---

### ⚠️ Lo que es insuficiente

#### 1. Auto-fill es pasivo, no inteligente
El roadmap propone un auto-fill basado en similitud por embeddings. El problema: el operador **todavía elige** qué incluir con checkboxes. En un ticket complejo, hay 20+ bloques candidatos. La decisión sigue siendo humana.

**Gap real:** no hay un motor que entienda *por qué* ciertos bloques son relevantes para *este agente* en *este momento*, y que los priorice con razonamiento, no solo similaridad coseno.

#### 2. Los Packs son lineales en un trabajo que no lo es
```
Functional → Technical → Developer → QA
```
Esto asume el camino feliz. En la realidad:
- QA falla → ¿re-corro Developer o Technical también?
- Technical detecta que el Functional está incompleto → ¿vuelvo o agrego contexto?
- Developer produce código con errores de BD → ¿quién lo detecta y cómo se propaga?

El roadmap no tiene respuesta estructurada para branches de fallo.

#### 3. Sin awareness de cambios en el codebase
Si se aprueba un análisis técnico y 2 días después alguien mergea un PR que toca los mismos archivos, ese análisis quedó desactualizado. El sistema no lo sabe. El operador lo descubre cuando el Developer agent produce código incompatible.

#### 4. El diferencial vs VS Code + Copilot no está construido, está listado
El roadmap dice "vamos a hacer knowledge graph en Q2'27". Pero hasta Q2'27, ¿por qué Stacky Agents es superior? La respuesta actual es "historial de ejecuciones y packs". Eso no es suficiente para retener usuarios exigentes que ya usan Copilot.

#### 5. Agentes aislados = operador como bus de datos
Cada agente recibe contexto que el operador ensambló manualmente. Si Technical produce "la tabla T_COBROS tiene índice en COD_CLIENTE", ese dato no llega automáticamente a Developer. El operador tiene que leerlo, entenderlo y copiarlo. **El operador es el adaptador entre agentes.**

---

### ❌ Lo que falta críticamente

| Gap | Consecuencia si no se cierra |
|---|---|
| Ejecución adaptativa (branches de fallo) | El pack falla y el operador queda sin guía — vuelve a modo manual |
| Contratos de output verificables | Outputs incorrectos pasan a ADO sin detección automática |
| Propagación de confianza entre agentes | Un Functional de baja calidad contamina toda la cadena sin señal |
| Code-aware context assembly automática | El operador sigue siendo cuello de botella en el ensamblado de contexto |
| Invalidación automática de análisis por cambios de código | Análisis obsoletos → bugs en producción sin trazabilidad |
| Modo "challenger" en outputs críticos | Los agentes tienen blind spots que solo se detectan con revisión adversarial |

---

## PARTE 2 — Nuevas Features Propuestas

### EJE 1: Context Intelligence

---

**Feature: Execution Contract Validator**
- **Problema:** Un agente puede producir un output estructuralmente correcto pero semánticamente incompleto. No hay forma automática de detectarlo antes de enviarlo a ADO.
- **Cómo funciona:** Cada agente tiene un contrato declarativo:
  ```yaml
  # contracts/technical.yaml
  required_sections: ["Análisis de impacto", "Tablas BD afectadas", "RIDIOMA afectados"]
  required_patterns:
    - regex: "TU-\\d{3}"          # al menos un marcador TU
    - regex: "ADO-\\d{4,}"        # referencia al ticket
  forbidden_patterns:
    - "No tengo información suficiente"   # frases de evasión
    - "requeriría más contexto"
  min_word_count: 400
  ```
  Post-run, el validador corre en < 200ms. Si falla: muestra qué cláusula falló + sugiere "agregar contexto sobre X antes de re-run". Si el score de contratos es < 80%, el botón `Approve` requiere confirmación adicional.
- **Impacto:** Elimina el 70% de los re-runs por outputs incompletos. El operador sabe exactamente por qué falló antes de leer el output.
- **Prioridad:** ALTA — implementable en Fase 1 con costo bajo

---

**Feature: Stale Analysis Detector**
- **Problema:** Un análisis técnico aprobado hace 3 días puede quedar obsoleto si alguien tocó los archivos en cuestión.
- **Cómo funciona:**
  1. Al momento de aprobar una exec, se registra un snapshot de los archivos relevantes mencionados en el output (parser de menciones de archivos + tablas).
  2. Un worker lightweight consulta git cada 6 horas: ¿alguno de esos archivos fue modificado?
  3. Si sí: banner amarillo en el historial: `⚠ exec #21 puede estar desactualizada — 2 archivos cambiaron desde su aprobación. [Ver diff] [Re-run] [Ignorar]`
  4. El operador decide con información, no por olvido.
- **Impacto:** Elimina una clase entera de bugs de "análisis rancio". En proyectos con desarrollo activo, esto ocurre 2-3 veces por semana.
- **Prioridad:** ALTA — crítico para adopción a largo plazo

---

**Feature: Context Influence Trace**
- **Problema:** Cuando el LLM recibe 180k tokens de contexto, es imposible saber qué partes realmente influyeron en el output. La memoria aprende de todo por igual — incluye el ruido.
- **Cómo funciona:**
  Post-run, una segunda llamada ligera al LLM (haiku) ejecuta: *"Del siguiente contexto de entrada, listá en orden los 5 bloques que más influyeron en tu respuesta anterior."*
  El resultado se guarda como `influence_trace: ["bloque_2", "bloque_5", ...]` en la fila de ejecución.
  La memoria de Fase 3 se alimenta **solo de los bloques con alta influencia**, no de todo el contexto.
  Efecto secundario: el editor muestra visualmente qué bloques fueron más usados → guía para futuras ejecuciones.
- **Impacto:** La memoria aprende de señal, no de ruido. Quality score sube más rápido. El operador aprende qué contexto importa.
- **Prioridad:** MEDIA — requiere Fase 3 como prerequisito, pero el diseño debe preverse desde Fase 1

---

### EJE 2: Execution Engine

---

**Feature: Adaptive Pack Engine (branches de fallo)**
- **Problema:** Los packs son lineales. La realidad tiene branches: QA falla → ¿vuelvo a Developer o a Technical?
- **Cómo funciona:**
  El pack definition agrega `on_fail` por paso:
  ```yaml
  steps:
    - agent: functional
      on_fail: stop                    # error en functional → detener
    - agent: technical
      on_fail: retry_with_context      # re-run con error como contexto adicional
    - agent: developer
      on_fail:
        action: branch
        back_to: technical             # si developer falla, re-run technical con señal
        inject: "Developer reportó: {error}"
    - agent: qa
      on_fail:
        action: branch
        back_to: developer
        inject: "QA falló con: {qa_output}"
        max_iterations: 2              # máximo 2 ciclos Developer↔QA automáticos
  ```
  UI: el pack muestra un grafo simple del flujo actual, con el estado de cada nodo. No es un DAG visual complejo — es un progress tracker con branches.
- **Impacto:** Convierte el pack en un verdadero asistente de trabajo, no solo un wizard lineal. Los operadores dejan de hacer backtrack manual cuando un agente falla.
- **Prioridad:** ALTA — define si los packs son un feature real o un shortcut glorificado

---

**Feature: Agent Confidence Propagation**
- **Problema:** Si el análisis Functional tiene baja confianza en un área, Technical lo recibe sin esa señal y toma el contexto como verdad.
- **Cómo funciona:**
  Cada agente retorna, además del output, un JSON de confianza estructurado:
  ```json
  {
    "output": "...",
    "confidence_map": {
      "actores_identificados": 0.95,
      "restricciones_legales": 0.40,   ← baja confianza
      "flujo_cobro": 0.85
    }
  }
  ```
  Cuando el output de Functional se convierte en input de Technical, el sistema inyecta automáticamente:
  `[NOTA SISTEMA] Baja confianza en 'restricciones_legales' (0.40) — verificar antes de proceder.`
  El operador también ve esto visualmente en el editor (sección marcada en amarillo).
- **Impacto:** Los agentes posteriores trabajan con la incertidumbre correctamente señalizada. Reduce re-works por suposiciones incorrectas.
- **Prioridad:** ALTA — bajo costo de implementación, alto impacto en cadena

---

**Feature: Speculative Pre-execution con Cancellation**
- **Problema:** En un pack de 4 pasos, el tiempo total es la suma de 4 latencias + 4 reviews humanas. Las reviews humanas dominan.
- **Cómo funciona:**
  Mientras el operador lee el output del paso N, el sistema **pre-corre silenciosamente el paso N+1** usando el output actual de N como contexto provisional.
  Si el operador aprueba N sin cambios → el output del paso N+1 ya está listo (latencia = 0).
  Si el operador edita N → la pre-ejecución se cancela y el sistema corre N+1 con el contexto corregido.
  El operador ve un indicador discreto: `⚡ Pre-cargando paso siguiente...`
  Cost: se cobra la pre-ejecución solo si es consumida. Si se cancela, no se factura (mediante streaming abort).
- **Impacto:** En el camino feliz (sin edición), el pack completo se percibe como la suma de reviews humanas, sin tiempos de espera. Para un pack de 4 pasos, el tiempo percibido baja ~40%.
- **Prioridad:** MEDIA — requiere streaming abort implementado en el bridge

---

### EJE 3: Developer Experience

---

**Feature: Code-Aware Context Assembly (CACA)**
- **Problema:** El operador tiene que saber qué archivos del repo son relevantes para un ticket y agregarlos manualmente al contexto. Esto requiere conocimiento del codebase y consume 5-10 minutos por ticket.
- **Cómo funciona:**
  Al seleccionar un agente, el sistema:
  1. Lee el título + descripción del ticket.
  2. Consulta el knowledge graph (o, en Fase 1, un índice trigram del repo) para encontrar archivos, clases, RIDIOMA, y tablas mencionadas o relacionadas semánticamente.
  3. Presenta una lista rankeada: `📁 Sugeridos (3): BatchCobranza.cs (+95%), T_COBROS.sql (+88%), RIDIOMA_SMS.md (+76%)`
  4. El operador activa con un click — no necesita navegar el repo.
  
  En Fase 1 el ranker es keyword-based (nombres en el título → grep en el repo).
  En Fase 3 usa embeddings + knowledge graph.
  En Fase 6 usa el grafo completo con razonamiento.
- **Impacto:** El cuello de botella de "ensamblar contexto" desaparece como tarea consciente. El operador pasa de ensamblador a validador.
- **Prioridad:** ALTA — directamente compite con la ventaja de VS Code (acceso al repo inline)

---

**Feature: Cross-Ticket Impact Radar**
- **Problema:** Dos desarrolladores trabajan en ADO-1234 y ADO-1289. Ambos tocan `BatchCobranza.cs`. Ninguno lo sabe. Stacky Agents no lo detecta.
- **Cómo funciona:**
  Al momento de que un Developer agent produce un output con menciones de archivos:
  1. El sistema busca en ejecuciones activas (las últimas 72h) de otros tickets si esos archivos son mencionados.
  2. Si hay overlap: banner `⚠ ADO-1289 (en progreso, ana@) también toca BatchCobranza.cs. [Ver exec] [Notificar]`
  3. La notificación es opt-in y no bloquea.
- **Impacto:** Detecta conflictos antes de que lleguen al merge. En equipos de 3+ desarrolladores, esto ocurre 1-2 veces por sprint.
- **Prioridad:** MEDIA — alta visibilidad de valor, costo de implementación bajo

---

### EJE 4: Observabilidad

---

**Feature: Agent Decision Explainer**
- **Problema:** El output del agente dice "hay que modificar BatchCobranza.cs". ¿Por qué esa conclusión? ¿Qué del contexto lo llevó a esa decisión? Imposible saberlo desde el output final.
- **Cómo funciona:**
  En el panel de output, botón secundario: `[¿Por qué?]`
  Esto dispara una micro-llamada al LLM (haiku, < $0.001):
  *"Explicá en 3 bullets qué parte del contexto de entrada llevó a concluir [sección seleccionada del output]"*
  Respuesta en un panel lateral expandible. Immutable: se guarda junto al exec.
  El operador puede seleccionar cualquier párrafo del output y pedir explicación.
- **Impacto:** Convierte outputs opacos en razonamiento auditable. Fundamental para compliance. Reduce el "no sé si confiarle esto al agente".
- **Prioridad:** ALTA — diferenciador directo vs VS Code donde el razonamiento de Copilot es opaco

---

**Feature: Prompt Regression Dashboard**
- **Problema:** Cuando un operador o el equipo edita el system prompt de un agente, no hay forma de saber si mejoró o empeoró para la clase de tickets más comunes.
- **Cómo funciona:**
  Una pantalla dedicada (solo para admins/leads):
  1. Seleccionás "agente Technical, última semana".
  2. El sistema agrupa las ejecuciones por cluster de tickets similares.
  3. Para cada cluster: quality score promedio, tasa de aprobación primera-pasada, costo promedio por exec.
  4. Podés comparar la semana actual vs semana anterior (automático) o vs una versión específica del prompt (manual).
  5. Alert automática si la tasa de aprobación baja > 10% en 48h (señal de drift o cambio de modelo).
- **Impacto:** Los prompts se gobiernan con datos, no con intuición. Elimina el "no sé si el cambio que hice empeoró algo".
- **Prioridad:** MEDIA — requiere suficiente volumen de ejecuciones (Fase 2+)

---

### EJE 5: Productividad Real

---

**Feature: Ticket Pre-Analysis Fingerprint (TPAF)**
- **Problema:** El operador llega a un ticket y empieza desde cero: lee, entiende el dominio, decide qué contexto incluir. Esto toma 5-15 minutos antes de presionar Run.
- **Cómo funciona:**
  Al cargar un ticket, **antes** de seleccionar agente, el sistema corre automáticamente un micro-agente (haiku, < 5s, < $0.002):
  - Clasifica el ticket: tipo de cambio (nuevo feature / bug / refactor / config), dominio funcional (cobros, créditos, usuarios), complejidad estimada (S/M/L/XL).
  - Sugiere el pack más apropiado.
  - Pre-identifica los 3-5 archivos más probablemente relevantes.
  - Si hay tickets similares aprobados, los muestra como "antecedentes directos".
  
  Resultado: cuando el operador llega al editor, ya tiene un punto de partida con 80% del contexto armado. Su trabajo es validar y completar, no armar desde cero.
- **Impacto:** Reduce el "tiempo muerto pre-run" de 5-15 minutos a < 1 minuto. Multiplicador de throughput del operador.
- **Prioridad:** ALTA — tangible, medible, demo-able desde el primer día

---

**Feature: Output Snippet Library con Deduplicación Semántica**
- **Problema:** El operador de QA escribe "verificar entorno staging", "validar en staging", "probar en ambiente de pruebas" en múltiples tickets. Son lo mismo. No hay forma de reutilizar.
- **Cómo funciona:**
  - Un sistema de snippets personales + de equipo, con shortcodes: `/staging-check`, `/ridioma-sms`, `/cobros-tables`.
  - Al guardar un snippet, el sistema busca semánticamente en los existentes: "ya tenés 'verificar staging' — ¿querés reemplazarlo o crear variante?"
  - Los snippets de equipo se aprueban por un lead antes de estar disponibles para todos.
  - En el editor, autocompletar con `/` activa la búsqueda de snippets.
- **Impacto:** Elimina el re-tipeo de contexto repetitivo. El conocimiento del equipo se codifica en snippets, no en las cabezas de los seniors.
- **Prioridad:** MEDIA — popular con operadores frecuentes, bajo costo de implementación

---

### EJE 6: Diferencial vs VS Code

*(ver Parte 4 para el análisis completo — acá la feature específica)*

---

**Feature: Structured Agent Output Renderer con Domain Schemas**
- **Problema:** VS Code + Copilot devuelve texto markdown. Stacky Agents también devuelve texto markdown. ¿Dónde está la diferencia estructural?
- **Cómo funciona:**
  Cada agente tiene un schema de output declarado:
  ```yaml
  # schemas/technical_output.yaml
  sections:
    - id: impact_analysis
      label: "Análisis de Impacto"
      type: structured_list
      required: true
    - id: db_tables
      label: "Tablas BD Afectadas"
      type: table
      columns: ["Tabla", "Operación", "Justificación"]
      required: true
    - id: ridioma_list
      label: "RIDIOMA Involucrados"
      type: clickable_list        # cada item abre el archivo en el repo
      required: false
  ```
  El renderer del OutputPanel **no** muestra markdown plano. Muestra secciones colapsables, tablas clicables, listas con acciones (abrir archivo, buscar en ADO, copiar al clipboard). Los outputs son **interactivos**, no solo texto.
  
  Efecto secundario: el parser del schema valida el output antes de mostrarlo (parte del Execution Contract Validator).
- **Impacto:** La diferencia visual entre Stacky Agents y Copilot Chat es inmediata. Los outputs de Stacky son navegables, no solo legibles.
- **Prioridad:** ALTA — primer diferenciador visual que cualquier usuario nota en 30 segundos

---

## PARTE 3 — Roadmap Actualizado

### Fase 1 — MVP con Calidad Garantizada (Q1-Q2 2026 · 8 semanas)

> Objetivo: Stacky Agents corre sobre el engine real, con calidad verificable desde el primer día, y con una UX que ya se diferencia visualmente de VS Code + Copilot.

**Features originales del roadmap (sin cambios):** 1.1–1.8

**Features nuevas que entran en Fase 1:**

| # | Feature | Estimación |
|---|---|---|
| N1 | Execution Contract Validator | 1 sem |
| N2 | Structured Output Renderer con Domain Schemas | 1.5 sem |
| N3 | Ticket Pre-Analysis Fingerprint (TPAF) — versión keyword | 1 sem |
| N4 | Agent Confidence Propagation | 0.5 sem |

**Métricas de éxito adicionales:**
- 100% de ejecuciones pasan por el Contract Validator.
- El output renderer muestra tablas y secciones colapsables en los 5 agentes.
- > 70% de los operadores reportan que el pre-analysis "llegó al agente correcto" (encuesta).

---

### Fase 2 — Diferenciación Estructural (Q2-Q3 2026 · 10 semanas)

> Objetivo: Stacky Agents hace algo que VS Code + Copilot no puede hacer sin una semana de setup manual.

**Features originales del roadmap:** 2.1–2.8

**Features nuevas que entran en Fase 2:**

| # | Feature | Estimación |
|---|---|---|
| N5 | Adaptive Pack Engine (branches de fallo) | 2 sem |
| N6 | Code-Aware Context Assembly — versión keyword/grep | 1 sem |
| N7 | Stale Analysis Detector | 1 sem |
| N8 | Agent Decision Explainer | 1 sem |
| N9 | Output Snippet Library | 1 sem |

**Métricas de éxito adicionales:**
- > 80% de packs completados sin intervención manual de re-run.
- > 60% de contextos incluyen al menos 1 archivo sugerido por CACA.
- > 40% de los "¿Por qué?" usados en outputs aprobados (señal de adopción del explainer).

---

### Fase 3 — Inteligencia Compuesta (Q3-Q4 2026 · 12 semanas)

> Objetivo: El sistema aprende, predice y reduce activamente la carga cognitiva del operador.

**Features originales del roadmap:** 3.1–3.5

**Features nuevas que entran en Fase 3:**

| # | Feature | Estimación |
|---|---|---|
| N10 | Context Influence Trace | 1.5 sem |
| N11 | Speculative Pre-execution | 2 sem |
| N12 | Prompt Regression Dashboard | 1.5 sem |
| N13 | Cross-Ticket Impact Radar | 1 sem |
| N14 | Code-Aware Context Assembly — versión embeddings | 2 sem |
| N15 | Ticket Pre-Analysis Fingerprint — versión semántica | 1.5 sem |

**Métricas de éxito adicionales:**
- > 50% de packs en camino feliz tienen latencia percibida = 0 en paso N+1 (speculative).
- 0 tickets con conflict de archivos llegaron a merge sin haber pasado por Impact Radar.
- Prompt Regression Dashboard usado por al menos 1 lead semanalmente.

---

### Resumen de Fases (vista unificada)

```
Q1 2026 — Fase 1 (MVP + Calidad)     ▶ Contract Validator, Output Renderer, TPAF
Q2 2026 — Fase 2 (Diferenciación)    ▶ Adaptive Packs, CACA, Stale Detector, Explainer
Q3 2026 — Fase 3 (Inteligencia)      ▶ Memoria, Multi-LLM, Speculative, Impact Radar
Q4 2026 — Fase 4 (Colaboración)      ▶ Multi-user, Slack/Teams, Mobile (sin cambios)
Q1 2027 — Fase 5 (Plataforma)        ▶ SDK, Multi-tenant, Compliance, A/B (sin cambios)
Q2 2027 — Fase 6 (Game-changers)     ▶ Self-improving, Knowledge Graph, Auto-PR (+ abajo)
```

---

## PARTE 4 — Diferencial Estratégico

### Por qué Stacky Agents es superior a VS Code + Copilot Chat

| Capacidad | VS Code + Copilot | Stacky Agents |
|---|---|---|
| Historial de ejecuciones por ticket | ❌ Conversación efímera | ✅ Inmutable, auditable, searchable |
| Contexto estructurado y editable | ❌ Prompt libre, sin estructura | ✅ Editor con bloques, contratos de calidad |
| Calidad verificada antes de publicar | ❌ El usuario decide si es bueno | ✅ Contract Validator + Quality Score automático |
| Aprendizaje de aprobaciones pasadas | ❌ Contexto = lo que pegas | ✅ Memoria por proyecto + auto-fill inteligente |
| Workflows multi-agente orquestados | ❌ Una conversación = un agente | ✅ Packs adaptativos con branches de fallo |
| Integración ADO nativa | ❌ Copy/paste manual | ✅ Publicación directa, lectura de tickets, PAT gestión |
| Razonamiento sobre el codebase real | ⚠️ Solo si pegás los archivos | ✅ CACA sugiere automáticamente los archivos relevantes |
| Conflictos entre tickets | ❌ Sin awareness | ✅ Cross-Ticket Impact Radar |
| Outputs obsoletos por cambios de código | ❌ Sin detección | ✅ Stale Analysis Detector |
| Trazabilidad de decisiones | ❌ El LLM decide, nadie sabe por qué | ✅ Agent Decision Explainer por sección |
| Colaboración de equipo | ❌ Solo contexto del usuario activo | ✅ Multi-user, Handoff, Shared history |
| Costo controlable por exec / por equipo | ❌ Opaco para el usuario | ✅ Cost tracking + alertas + budgets |
| Outputs como interfaces, no texto | ❌ Markdown plano | ✅ Secciones colapsables, tablas, links a archivos |
| Agentes especializados en el dominio | ❌ Agente genérico + instrucciones manuales | ✅ Agentes calibrados para Pacífico/Ubimia + RIDIOMA |

**La respuesta a "¿por qué usar esto?":**

> VS Code + Copilot es un **asistente genérico que sabe de código**. Stacky Agents es una **fábrica de tickets calibrada para tu dominio** que recuerda, aprende, verifica y colabora.

La diferencia no es de poder bruto — es de **especialización, memoria y estructura**. Copilot puede hacer lo mismo que Stacky Agents, pero requiere que el operador sea el sistema de gestión: recuerde el historial, ensamble el contexto, verifique la calidad, detecte los conflictos. En Stacky Agents, eso es infraestructura.

---

### Barreras que Stacky Agents crea (lock-in positivo)

1. **Memoria acumulativa** — después de 6 meses de ejecuciones, el sistema "conoce" los patrones de Pacífico mejor que cualquier operador nuevo. Moverse a otra herramienta implica perder ese conocimiento codificado.

2. **Snippets de equipo** — el knowledge del equipo está en los snippets y en las memorias de agente. Son activos del equipo, no de ningún individuo.

3. **Contratos de output calibrados** — después de ajustar los contratos a los estándares de Pacífico, cualquier otra herramienta produciría outputs que "no cumplen el formato". El formato se convierte en parte del contrato laboral.

4. **Historial como evidencia** — para clientes regulados o auditorías internas, el historial inmutable de Stacky Agents es evidencia legal. No tiene sustituto.

5. **Integración ADO profunda** — no es solo "publicar comentarios". Es leer estados, inferir contexto de ADO, escribir en el formato correcto de Pacífico. Esto requiere meses de calibración que un setup genérico no tiene.

---

### Ventaja acumulativa

```
Mes 1:   El sistema funciona y ahorra tiempo individual
Mes 3:   La memoria empieza a sugerir contexto relevante → menos setup manual
Mes 6:   Los contratos están calibrados → casi 0 re-runs por calidad
Mes 9:   El knowledge graph indexa el codebase → los agentes razonan sin explorar
Mes 12:  Self-improving activo → los prompts mejoran con datos → la calidad sube sola
Mes 18:  Multi-tenant lanzado → otros clientes consumen el mismo sistema → ROI explosivo
```

Cada mes, el costo de abandonar el sistema sube. No por bloqueo técnico, sino porque el sistema acumula valor que no existe en ningún otro lado.

---

## PARTE 5 — Features Game-Changer (no obvias)

### GC-1: Adversarial Challenger Pass

**El problema:** Los agentes tienen blind spots. Technical puede producir un análisis coherente pero incompleto — olvidó preguntar por el módulo de notificaciones porque no estaba en el ticket. El operador no lo nota porque no conoce el codebase tan bien como el agente.

**La idea:**
Para ejecuciones marcadas como "críticas" (o automáticamente para Developer), se corre una segunda pasada con un prompt adversarial: *"Sos un revisor escéptico. Analizá este output técnico y encontrá: suposiciones no verificadas, módulos que podrían verse afectados y no se mencionan, y preguntas que el análisis no responde."*

El resultado es un diff entre el output original y las objeciones del challenger. Se muestra en el panel derecho como `⚔️ Challenger encontró 3 observaciones`:
- `Suposición no verificada: "el flujo A siempre pasa por módulo X" — no hay evidencia en el contexto`
- `Módulo no mencionado: BatchNotificaciones.cs toca la misma tabla T_COBROS`
- `Pregunta sin responder: ¿qué pasa si el saldo es negativo en el momento del cobro?`

El operador decide qué hacer con cada observación. El output challenger también es immutable y se guarda.

**Por qué no es obvio:** la mayoría de los sistemas de calidad buscan completitud (¿está todo lo que debe estar?). El challenger busca *falsedad* (¿hay algo que afirma que podría estar mal?). Son métricas ortogonales.

**Impacto:** Elimina una clase de bugs que solo se descubren en código review o en producción. Para tickets de alto riesgo, este paso vale su costo.

**Prioridad:** ALTA para Fase 3 en tickets críticos.

---

### GC-2: Execution Branching con Síntesis Automática

**El problema:** Cuando hay incertidumbre en un ticket ("no sabemos si el cliente usa el flujo A o B"), el operador elige uno y reza. Si eligió mal, rehace todo.

**La idea:**
El operador puede "bifurcar" una ejecución antes de hacer Run: `[+ Agregar rama]`.
Cada rama tiene un contexto ligeramente diferente ("asumiendo flujo A" vs "asumiendo flujo B").
Ambas ramas corren en paralelo (2 llamadas concurrentes).
Los dos outputs se muestran en un panel de comparación lado a lado.
El operador puede fusionar: un tercer micro-agente recibe ambas ramas y genera una síntesis que toma lo mejor de cada una: "en ambas ramas se concluye X; la rama A agrega Y que la rama B no considera".

**Por qué no es obvio:** los sistemas de workflows no piensan en incertidumbre como input válido. Aquí la incertidumbre se convierte en una feature, no en un bloqueante.

**Impacto:** Tickets ambiguos ya no se estancan esperando una reunión de aclaración. El análisis explora las dos hipótesis y la síntesis reduce la incertidumbre.

**Prioridad:** MEDIA para Fase 4. Alta complejidad, alto impacto en tickets enterprise.

---

### GC-3: Agent Memory Graph (no solo embeddings planos)

**El problema:** La memoria propuesta en Fase 3 es un índice de embeddings. Los embeddings capturan similitud semántica pero no **estructura de conocimiento**: "cuando hay un cambio en el módulo de cobros, siempre hay que revisar el RIDIOMA de notificaciones Y el procedimiento de cierre de día".

Esto es una regla estructurada, no una similitud. No vive bien en un índice de embeddings.

**La idea:**
Un grafo de memoria donde los nodos son **entidades del dominio** (módulos, tablas, RIDIOMA, flujos de negocio, restricciones legales) y las aristas son **relaciones observadas** (co-ocurrencia en análisis aprobados, dependencias explicitadas por agentes, conflictos históricos).

El grafo se construye automáticamente:
1. Cada exec aprobada es parseada: entidades extraídas → nodos creados o fortalecidos.
2. Si dos entidades co-ocurren en 5+ execs aprobadas → arista fuerte.
3. Si el Adversarial Challenger detectó que una entidad era relevante y el agente la omitió → arista de "atención requerida".

Cuando un nuevo ticket menciona el módulo de cobros, el sistema consulta el grafo y devuelve: "históricamente, los tickets de cobros siempre involucran: T_COBROS (1.0), RIDIOMA_SMS (0.87), ProcCierreDia (0.72)". El operador no necesita recordar esto.

**Por qué no es obvio:** los sistemas RAG actuales buscan documentos similares. El Memory Graph busca **patrones de dominio** que emergen de la historia de ejecuciones del equipo. Es conocimiento institucional codificado.

**Impacto:** El sistema eventualmente sabe más sobre el dominio de Pacífico que cualquier operador individual. Es el primer paso hacia agentes que razonan como seniors.

**Prioridad:** ALTA para Fase 6. Requiere 6+ meses de ejecuciones como input.

---

### GC-4 (bonus): Ticket Simulation Mode

**El problema:** Los operadores nuevos no saben qué salida esperar de cada agente. No hay forma de practicar sin gastar tokens y sin tocar tickets reales.

**La idea:**
Un modo "sandbox" donde el sistema toma un ticket histórico real (con su exec aprobada) y simula ser el agente: el nuevo operador construye el contexto, hace Run, y el sistema compara su output (mock del histórico aprobado) con el del operador experto que lo hizo originalmente.

El sistema da feedback: "omitiste incluir las restricciones legales que el operador senior incluyó — en los análisis aprobados, este módulo siempre requiere esa sección."

**Por qué no es obvio:** no es un onboarding genérico. Es entrenamiento con datos reales del mismo dominio. El junior aprende de los seniors implícitamente, sin que los seniors tengan que enseñar.

**Impacto:** Reduce el tiempo de ramping de nuevos operadores de semanas a días. Crea una cultura de calidad sin overhead de mentoring.

**Prioridad:** MEDIA para Fase 5.

---

## Catálogo Completo — Features Nuevas vs Originales

| # | Feature | Eje | Impacto | Costo | Fase |
|---|---|---|---|---|---|
| N1 | Execution Contract Validator | Calidad | XL | S | Fase 1 |
| N2 | Structured Output Renderer | DX / Diferencial | XL | M | Fase 1 |
| N3 | Ticket Pre-Analysis Fingerprint | Productividad | XL | M | Fase 1 |
| N4 | Agent Confidence Propagation | Execution | L | S | Fase 1 |
| N5 | Adaptive Pack Engine | Execution | XL | M | Fase 2 |
| N6 | Code-Aware Context Assembly | Context Intel | XL | M | Fase 2 |
| N7 | Stale Analysis Detector | Observabilidad | L | S | Fase 2 |
| N8 | Agent Decision Explainer | Observabilidad | XL | S | Fase 2 |
| N9 | Output Snippet Library | Productividad | M | S | Fase 2 |
| N10 | Context Influence Trace | Context Intel | L | M | Fase 3 |
| N11 | Speculative Pre-execution | Execution | XL | M | Fase 3 |
| N12 | Prompt Regression Dashboard | Observabilidad | L | S | Fase 3 |
| N13 | Cross-Ticket Impact Radar | DX | L | S | Fase 3 |
| N14 | CACA embeddings | Context Intel | XL | L | Fase 3 |
| N15 | TPAF semántico | Productividad | XL | M | Fase 3 |
| GC1 | Adversarial Challenger Pass | Calidad | XL | M | Fase 3 |
| GC2 | Execution Branching + Síntesis | Execution | XL | L | Fase 4 |
| GC3 | Agent Memory Graph | Context Intel | XL | XL | Fase 6 |
| GC4 | Ticket Simulation Mode | DX / Onboarding | L | M | Fase 5 |

**Costo:** S = ≤ 2 sem · M = 2–4 sem · L = 4–8 sem · XL = > 8 sem
**Impacto:** S = nice-to-have · M = mejora real · L = movés la aguja · XL = redefine el producto

---

## Apéndice — Matriz de Priorización Inmediata

Para el equipo que comienza Fase 1 mañana, las tres features de mayor retorno/esfuerzo son:

### #1: Execution Contract Validator (N1)
- **1 semana de backend** + config YAML por agente
- **Impacto inmediato:** reduce re-runs por outputs incompletos desde el día 1
- **Por qué primero:** construye confianza en el sistema. Si los operadores ven que el sistema detecta outputs malos antes de que ellos los lean, adoptan el workflow sin fricción.

### #2: Structured Output Renderer (N2)
- **1.5 semanas de frontend** + schemas YAML por agente
- **Impacto inmediato:** primer diferenciador visual vs VS Code + Copilot, visible en 30 segundos de demo
- **Por qué segundo:** la adopción inicial es visual. Si el output se ve como texto plano igual que Copilot, el switch de herramienta no tiene argumento emocional.

### #3: Ticket Pre-Analysis Fingerprint (N3) — versión keyword
- **1 semana** de micro-agente haiku + UI de "llegada al ticket"
- **Impacto inmediato:** el operador no empieza de cero — llega al editor con un punto de partida
- **Por qué tercero:** el ahorro de 5-10 minutos por ticket es el argumento de ROI más directo para un sponsor.

Estas tres features juntas, en Fase 1, hacen que la pregunta **"¿por qué usar esto en lugar de VS Code + Copilot?"** tenga una respuesta de 30 segundos:

> *"Porque cuando abrís un ticket, el sistema ya sabe qué contexto necesitás, arma el editor con esa información, y cuando presionás Run, el output se verifica automáticamente contra los estándares de Pacífico y se muestra como una interfaz navegable, no como texto plano. Ninguna de esas tres cosas existe en VS Code + Copilot."*
