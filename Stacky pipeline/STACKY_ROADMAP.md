# Stacky — Roadmap de Mejoras

> Documento de planificación técnica. Última revisión: 2026-04-13. Total mejoras: 73 (36 completadas + 10 Parte 5 + 7 Parte 6 + 1 fix crítico P0 + 7 Parte 7 + 12 Parte 8).
> Las mejoras están ordenadas por prioridad dentro de cada categoría.
> Estado: `[ ]` pendiente · `[x]` implementado · `[~]` en progreso

---

## Backlog de Mejoras Pendientes

Índice rápido de todo lo que está por hacer, con estado y prioridad.

### Parte 1 — Robustez del Pipeline
- `[x]` **M-01** · Feedback Loop QA → DEV (Rework automático) · Prioridad 5 ✓
- `[x]` **M-02** · Validación de Output entre Etapas · **Prioridad 1** ✓
- `[x]` **M-03** · Reintentos con Contexto Específico de Falla · Prioridad 2 ✓
- `[x]` **M-04** · Generación de SVN Diff Post-DEV · Prioridad 3 ✓
- `[x]` **M-05** · Contexto de Código desde ARQUITECTURA_SOLUCION.md · Prioridad 4 ✓
- `[x]` **M-06** · Procesamiento Paralelo por Etapas (Pipeline Lanes) · Prioridad 13 ✓
- `[x]` **M-07** · Scoring de Complejidad de Ticket (Pre-Triaje) · Prioridad 7 ✓

### Parte 2 — Mejoras Exponenciales (Batch original)
- `[x]` **E-01** · Knowledge Base de Tickets Resueltos (RAG) · Prioridad 8 ✓
- `[x]` **E-02** · Auto-actualización de Mantis Post-Completado · Prioridad 9 ✓
- `[x]` **E-03** · Grafo de Dependencias entre Tickets · Prioridad 14 ✓
- `[x]` **E-04** · Prompt Scoring y Evolución Automática · Prioridad 15 ✓
- `[x]` **E-05** · Detector de Tickets Auto-Cerrables · Prioridad 6 ✓
- `[x]` **E-06** · Contexto Semántico de Código con Tree-sitter · Prioridad 16 ✓
- `[x]` **E-07** · Monitor de Regresiones Post-Commit · Prioridad 17 ✓
- `[x]` **E-08** · Dashboard Interactivo con Control Total · Prioridad 12 ✓
- `[x]` **E-09** · Análisis de Causa Raíz Sistémico (Meta-PM) · Prioridad 11 ✓
- `[x]` **E-10** · Pipeline como API REST · Prioridad 10 ✓
- `[x]` **E-11** · Fase de Aprendizaje de Proyecto (Project Onboarding IA) · Prioridad 8 ✓

### Parte 3 — Mejoras Exponenciales (Batch 2)
- `[x]` **N-02** · Generador Automático de Commit Messages · Prioridad 2 ✓
- `[x]` **N-04** · Modo Batch por Componente · Prioridad 10 ✓
- `[x]` **N-05** · Detección de Escalada de Prioridad en Mantis · Prioridad 5 ✓
- `[x]` **N-06** · Auto-documentación de Patrones Fix · Prioridad 7 ✓
- `[x]` **N-07** · Modo Shadow (Dry Run del Pipeline) · Prioridad 11 ✓
- `[x]` **N-08** · Dashboard de Métricas de Calidad por Agente · Prioridad 12 ✓
- `[x]` **N-09** · Notificaciones Slack / Teams · Prioridad 8 ✓
- `[x]` **N-10** · Rollback Asistido Post-Regresión · Prioridad 13 ✓

### Parte 4 — Game Changers
- `[x]` **G-02** · Índice Vectorial del Codebase (Búsqueda Semántica Total) ✓

- `[x]` **G-03** · Inyección Live de Schema Oracle en Prompts ✓
- `[x]` **G-04** · Ejecución Automatizada de Tests Post-DEV ✓
- `[x]` **G-05** · Blast Radius Analysis (Mapa de Impacto de Cambios) ✓
- `[x]` **G-06** · Memoria Persistente de Agentes por Codebase ✓
- `[x]` **G-07** · Interfaz Conversacional — Chat con Stacky ✓
- `[x]` **G-08** · Deliberación Multi-Agente para Tickets Complejos ✓
- `[x]` **G-09** · Modo Autonomía Total con Approval Gates ✓
- `[x]` **G-10** · Capa de Inteligencia Predictiva ✓

---

## Contexto del sistema actual

Stacky es un pipeline de automatización para tickets MantisBT que orquesta 3 agentes IA
secuenciales (PM → DEV → QA) vía VS Code Copilot Bridge. Scrapea Mantis con Playwright,
genera documentación estructurada por ticket, y gestiona el ciclo de vida completo con
detección de flags por watchdog.

**Stack:** Python · Playwright · Flask · pywinauto · watchdog  
**Proyectos activos:** RIPLEY, RSMOBILENET  
**Agentes:** PM-TL Stack 3 · DevStack3 · QA

---

## PARTE 1 — Mejoras de Calidad y Robustez del Pipeline

Estas mejoras eliminan puntos ciegos y fallas silenciosas del flujo actual.

---

### `[x]` M-01 · Feedback Loop QA → DEV (Rework automático)

**Problema:** QA crea `TESTER_COMPLETADO.md` y el pipeline termina sin importar el veredicto.
Issues conocidos quedan marcados como "completado".

**Solución:** Introducir estado `qa_rework` que parsea `TESTER_COMPLETADO.md` buscando
issues reportados. Si los hay, invoca DEV con un prompt diferenciado que incluye el
feedback específico de QA. Máximo 1 ciclo de rework para evitar loops infinitos.

```
Flujo actual:   PM → DEV → QA → completado
Flujo objetivo: PM → DEV → QA → [issues?] → DEV(rework) → QA(re-validación) → completado
```

**Archivos a modificar:**
- `pipeline_watcher.py` — nueva rama en el handler de `TESTER_COMPLETADO.md`
- `pipeline_state.py` — estados `qa_rework`, `dev_rework_en_proceso`, `dev_rework_completado`
- `prompt_builder.py` — `build_rework_prompt(ticket_folder, qa_findings)` que extrae
  los issues de `TESTER_COMPLETADO.md` y los inyecta como lista de correcciones
- `config.json` por proyecto — `"max_rework_cycles": 1`

**Esfuerzo estimado:** Medio (2-3 días)  
**Impacto:** Alto — elimina la entrega de tickets con defectos conocidos

---

### `[x]` M-02 · Validación de Output entre Etapas

**Problema:** El daemon avanza de etapa cuando detecta el flag de completado, sin verificar
que el contenido del output sea realmente válido. PM puede crear `PM_COMPLETADO.flag` con
placeholders aún presentes o archivos vacíos.

**Solución:** Función validadora local (sin IA, puro Python) que corre antes de cada
transición de etapa:

```python
# output_validator.py
def validate_pm_output(ticket_folder) -> ValidationResult:
    # Chequea que no queden "_A completar por PM_" en ningún archivo
    # Chequea que cada uno de los 6 archivos tenga contenido sustancial (>= N líneas)
    # Chequea que TAREAS_DESARROLLO.md tenga al menos 1 bloque PENDIENTE
    # Chequea que ARQUITECTURA_SOLUCION.md nombre al menos 1 archivo con ruta relativa
    # Retorna: ok=True/False + lista de issues específicos

def validate_dev_output(ticket_folder) -> ValidationResult:
    # Chequea que DEV_COMPLETADO.md liste al menos 1 archivo modificado
    # Chequea que los archivos listados existan en el trunk (svn info)
    # Chequea que no haya tareas en estado PENDIENTE en TAREAS_DESARROLLO.md

def validate_qa_output(ticket_folder) -> ValidationResult:
    # Chequea que TESTER_COMPLETADO.md tenga veredicto explícito (APROBADO/OBSERVACIONES)
    # Chequea que haya al menos N casos de prueba documentados
```

Si la validación falla, crea `{STAGE}_ERROR.flag` con el detalle de qué faltó, evitando
que el agente siguiente trabaje con inputs defectuosos.

**Archivos nuevos:** `output_validator.py`  
**Archivos a modificar:** `pipeline_watcher.py`, `daemon.py`

**Esfuerzo estimado:** Bajo (1 día)  
**Impacto:** Alto — previene errores silenciosos en cascada

---

### `[x]` M-03 · Reintentos con Contexto Específico de Falla

**Problema:** `build_retry_prompt()` repite esencialmente el mismo prompt original. Si el
agente falló o llegó a timeout, el reintento sin contexto adicional tiene alta probabilidad
de volver a fallar por la misma razón.

**Solución:** El retry prompt debe inyectar:
- Qué archivos quedaron con placeholders (lista exacta)
- Qué secciones específicas están incompletas
- El contenido parcial ya generado para que el agente retome sin empezar de cero
- Si fue timeout: reducir el scope del prompt ("enfocate solo en los archivos que faltan")

```python
def build_retry_prompt(ticket_folder, stage, validation_result: ValidationResult):
    incomplete_files = validation_result.incomplete_files
    partial_content = read_partial_content(ticket_folder, incomplete_files)
    return f"""
{base_prompt}

## REINTENTO — Continuación de análisis previo

El análisis anterior quedó incompleto. No empieces de cero.

**Archivos que necesitan completarse:**
{incomplete_files_list}

**Contenido ya generado (no sobrescribir):**
{partial_content}

**Solo completá las secciones marcadas con placeholder.**
"""
```

**Archivos a modificar:** `prompt_builder.py`, `pipeline_runner.py`

**Esfuerzo estimado:** Bajo (medio día)  
**Impacto:** Medio — reduce la tasa de falla en reintentos

---

### `[x]` M-04 · Generación de SVN Diff Post-DEV

**Problema:** Cuando DEV completa, no hay registro de qué archivos del trunk modificó.
QA tiene que adivinar qué revisar y no hay auditoría de cambios por ticket.

**Solución:** Al detectar `DEV_COMPLETADO.md`, ejecutar automáticamente:

```python
# svn_reporter.py
def generate_svn_report(workspace_root, ticket_folder):
    status = subprocess.run(["svn", "status", workspace_root], capture_output=True)
    diff = subprocess.run(["svn", "diff", workspace_root], capture_output=True)
    
    # Escribe SVN_CHANGES.md en la carpeta del ticket con:
    # - Lista de archivos modificados/agregados/eliminados
    # - Diff legible con contexto (unified diff)
    # - Timestamp de la captura
```

`SVN_CHANGES.md` se inyecta automáticamente en el prompt de QA para que sepa
exactamente qué revisar. También queda como auditoría permanente del ticket.

**Archivos nuevos:** `svn_reporter.py`  
**Archivos a modificar:** `pipeline_watcher.py` (handler DEV_COMPLETADO), `prompt_builder.py`

**Esfuerzo estimado:** Bajo (1 día)  
**Impacto:** Alto — QA más preciso, auditoría completa

---

### `[x]` M-05 · Contexto de Código Directo desde ARQUITECTURA_SOLUCION.md

**Problema:** `code_context.py` usa heurística regex para detectar archivos relevantes.
Genera falsos positivos y pierde referencias implícitas. PM ya identificó los archivos
correctos en `ARQUITECTURA_SOLUCION.md` — ese trabajo se desperdicia.

**Solución:** En el prompt de DEV, parsear primero `ARQUITECTURA_SOLUCION.md` para
extraer rutas de archivos mencionadas explícitamente (paths relativos desde trunk).
Usar esas rutas exactas como contexto primario, y el análisis heurístico solo como
complemento para archivos no mencionados explícitamente.

```python
def extract_files_from_architecture(arch_file) -> list[str]:
    # Regex: extrae paths que matcheen N:\SVN\... o rutas relativas con extensiones .cs, .aspx, .vb
    # Verifica que los archivos existan en disco
    # Retorna lista ordenada por relevancia (mencionados primero en el doc)
```

**Archivos a modificar:** `code_context.py`, `prompt_builder.py`

**Esfuerzo estimado:** Bajo (medio día)  
**Impacto:** Medio — DEV recibe contexto de código más preciso y relevante

---

### `[x]` M-06 · Procesamiento Paralelo por Etapas (Pipeline Lanes)

**Problema:** El pipeline es completamente secuencial. Con 4+ tickets en "asignada",
el tiempo total es `N × (PM + DEV + QA)`. No hay conflicto entre Ticket A en PM
y Ticket B en DEV (usan carpetas distintas).

**Solución:** Implementar lanes concurrentes con restricción de un slot por agente
(Copilot no soporta dos invocaciones simultáneas al mismo agente).

```
Lane 1: Ticket A: [PM ████████] → [DEV ████████] → [QA ████████]
Lane 2: Ticket B:          [PM ████████] → [DEV ████████] → [QA ████████]
Lane 3: Ticket C:                   [PM ████████] → [DEV ████████]

Restricción: solo 1 invocación activa por agente en cualquier momento.
Cola de invocaciones: FIFO por agente, con prioridad heredada del ticket.
```

Requiere un `AgentQueue` thread-safe que serialice invocaciones por agente
pero permita concurrencia entre agentes distintos.

**Archivos nuevos:** `agent_queue.py`  
**Archivos a modificar:** `daemon.py`, `pipeline_runner.py`, `copilot_bridge.py`

**Esfuerzo estimado:** Alto (3-5 días, requiere testing extenso)  
**Impacto:** Muy alto — reduce tiempo total proporcional al número de tickets activos

---

### `[x]` M-07 · Scoring de Complejidad de Ticket (Pre-Triaje)

**Problema:** Todos los tickets reciben el mismo flujo y timeouts, sin importar si es
un fix de una línea o una refactorización multi-componente.

**Solución:** Función de clasificación local que analiza `INC-{id}.md` antes de lanzar PM:

```python
def score_complexity(inc_file) -> Literal["simple", "medio", "complejo"]:
    # Señales de complejidad:
    # - Número de componentes mencionados (OnLine, Batch, Oracle, Reportes)
    # - Cantidad de adjuntos
    # - Longitud de la descripción
    # - Keywords: "rendimiento", "migración", "integración", "todos los registros"
    # - Gravedad del ticket en Mantis
    # - Historial de notas (muchas notas = problema complejo)
```

Con el score se ajustan automáticamente:
- `timeout_pm_minutes`: simple=20, medio=45, complejo=90
- Prompt de PM: simple tiene instrucciones más acotadas
- Prioridad en la cola si hay múltiples tickets

**Archivos nuevos:** `ticket_classifier.py`  
**Archivos a modificar:** `daemon.py`, `ticket_detector.py`, `prompt_builder.py`

**Esfuerzo estimado:** Medio (1-2 días)  
**Impacto:** Medio — timeouts más precisos, menor tiempo muerto en tickets simples

---

## PARTE 2 — Mejoras Exponenciales de Eficiencia y Asertividad

Las siguientes 10 mejoras representan saltos cualitativos en la capacidad del sistema.
No son incrementales — cada una cambia fundamentalmente algún aspecto del pipeline.

---

### `[x]` E-01 · Base de Conocimiento de Tickets Resueltos (RAG sobre historial)

**Concepto:** Cuando PM analiza un ticket nuevo, el sistema busca automáticamente en
el historial de tickets ya resueltos cuáles son semánticamente similares, y los inyecta
como contexto:

```
"Tickets similares resueltos anteriormente:
- #0026541 (RIPLEY): Mismo síntoma en FrmCargaDocumentos → causa raíz fue campo NULL
  en RSTRP_ADJUNTOS. Solución: validación previa + default en INSERT.
- #0025901 (RIPLEY): Error idéntico en módulo diferente, fix en DAL_Documentos.cs línea 89."
```

Esto reduce drásticamente el tiempo de análisis PM en tickets recurrentes o similares,
y evita que DEV reimplemente soluciones que ya existen en el codebase.

**Implementación:** Índice de tickets completados con keywords extraídos + búsqueda TF-IDF.
No requiere embeddings ni modelos externos. Todo local.

**Archivos nuevos:** `knowledge_base.py`, `knowledge_index.json`  
**Esfuerzo:** Medio | **Impacto:** Muy alto

---

### `[x]` E-02 · Auto-actualización de Mantis Post-Completado

**Concepto:** Cuando el pipeline completa exitosamente (QA aprueba), Stacky actualiza
automáticamente el ticket en Mantis:
- Agrega una nota con el resumen de cambios (archivos modificados, enfoque de solución)
- Cambia el estado a "resuelta" o el siguiente estado del flujo
- Adjunta `TESTER_COMPLETADO.md` como documento de evidencia

Esto cierra el ciclo completo: de Mantis → Stacky → de vuelta a Mantis. El equipo
ve en Mantis qué pasó sin tener que consultar el dashboard de Stacky.

**Implementación:** Playwright contra la API de MantisBT (misma sesión SSO).  
**Archivos nuevos:** `mantis_updater.py`  
**Esfuerzo:** Medio | **Impacto:** Alto

---

### `[x]` E-03 · Grafo de Dependencias entre Tickets

**Concepto:** Detectar automáticamente relaciones entre tickets para prevenir conflictos
y priorizar mejor:
- Tickets que tocan los mismos archivos fuente (conflicto potencial en SVN)
- Tickets que dependen de la solución de otro (Ticket B roto porque Ticket A sin resolver)
- Tickets que fueron reabiertos por un fix anterior (regresiones)

```
Ticket #0027698 toca: DAL_Pedidos.cs, FrmPedidos.aspx
Ticket #0027446 toca: DAL_Pedidos.cs ← CONFLICTO POTENCIAL

⚠️ Stacky avisa: procesar #0027698 antes que #0027446 para evitar conflicto SVN.
```

El grafo también permite agrupar tickets relacionados para que PM haga un análisis
unificado en vez de 3 análisis aislados que llegan a la misma causa raíz.

**Archivos nuevos:** `dependency_graph.py`  
**Esfuerzo:** Alto | **Impacto:** Muy alto

---

### `[x]` E-04 · Prompt Scoring y Evolución Automática

**Concepto:** Trackear qué versiones de prompts tienen mejor tasa de éxito en primera
invocación (sin retries, sin rework). Con suficiente historial, el sistema puede
sugerir o aplicar variaciones de prompts que estadísticamente funcionan mejor para
ciertos tipos de tickets.

```
Métrica: tasa de éxito en primer intento por (tipo_ticket, stage, version_prompt)

pm_v1: 67% éxito primera vez en tickets de tipo "error_ui"
pm_v2: 84% éxito primera vez en tickets de tipo "error_ui"  ← usar v2 para este tipo
```

Versioning de prompts en `prompts/history/pm_v1.md`, `pm_v2.md` con metadata de
performance. El sistema sugiere upgrades, el usuario aprueba manualmente.

**Archivos nuevos:** `prompt_tracker.py`, `prompts/history/`  
**Esfuerzo:** Alto | **Impacto:** Muy alto (mejora acumulativa)

---

### `[x]` E-05 · Detector de Tickets Auto-Cerrables (Pre-Filtro sin IA)

**Concepto:** Antes de invertir PM + DEV + QA en un ticket, un pre-filtro local detecta
tickets que no deberían procesarse automáticamente:

- **Duplicados:** INC con descripción muy similar a uno ya resuelto (similarity > 0.85)
- **Información insuficiente:** Descripción < N palabras sin pasos de reproducción
- **Fuera de scope:** Keywords que indican otro equipo ("infraestructura", "servidor", "acceso")
- **Ya resuelto en código:** El fix ya existe en el trunk (búsqueda literal de la solución)

Para cada caso, Stacky puede:
- Agregar nota en Mantis explicando por qué no se procesa automáticamente
- Cambiar estado a "se_necesitan_mas_datos" con template de qué información falta
- Enlazar el ticket duplicado

**Archivos nuevos:** `pre_filter.py`  
**Esfuerzo:** Medio | **Impacto:** Alto (ahorra ciclos completos PM→DEV→QA)

---

### `[x]` E-06 · Contexto Semántico de Código con Tree-sitter

**Concepto:** Reemplazar la detección heurística de `code_context.py` (regex sobre
nombres de clases/métodos) con parsing real del AST del código fuente usando
tree-sitter para C# y VB.NET.

Dado el nombre de un método o clase mencionado en el ticket, el sistema puede:
- Encontrar la definición exacta en el trunk
- Extraer las dependencias directas (métodos llamados, clases referenciadas)
- Identificar todos los callers del método afectado
- Detectar si hay overloads o implementaciones múltiples

El contexto que recibe DEV pasa de "archivo completo que matchea el keyword" a
"método exacto + sus dependencias directas + sus callers relevantes".

**Dependencias nuevas:** `tree-sitter`, `tree-sitter-c-sharp`  
**Archivos a modificar:** `code_context.py`  
**Esfuerzo:** Alto | **Impacto:** Muy alto

---

### `[x]` E-07 · Monitor de Regresiones Post-Commit

**Concepto:** Después de que un ticket se marca como completado y los cambios se
commitean a SVN, Stacky monitorea los tickets subsiguientes buscando regresiones:

- Si un ticket nuevo menciona los mismos archivos que fueron modificados por un
  ticket anterior completado en los últimos N días → alerta de posible regresión
- Si el mismo error reaparece en un módulo que fue "fixeado" → alerta automática
- Genera reporte semanal: "Fix del #0027698 podría haber causado #0027821"

Esto transforma Stacky de un pipeline forward-only a un sistema con memoria
de efectos laterales.

**Archivos nuevos:** `regression_monitor.py`  
**Esfuerzo:** Alto | **Impacto:** Alto

---

### `[x]` E-08 · Dashboard Interactivo con Control Total del Pipeline

**Concepto:** El dashboard actual es mayormente read-only. Transformarlo en el panel
de control real de Stacky:

- **Drag & drop** para reordenar prioridad de tickets en cola
- **Botones de acción por ticket:** Retry stage / Skip stage / Force complete / Reopen
- **Vista de prompt en vivo:** ver el prompt exacto que se envió a cada agente
- **Diff viewer integrado:** ver `SVN_CHANGES.md` renderizado con syntax highlighting
- **Timeline visual:** ver cuánto tardó cada etapa, dónde se concentran los timeouts
- **Comparador de tickets similares:** side-by-side con historial

Incluir autenticación básica para acceso remoto (múltiples devs viendo el mismo dashboard).

**Archivos a modificar:** `dashboard.html`, `dashboard_server.py`  
**Esfuerzo:** Alto | **Impacto:** Alto (usabilidad operativa)

---

### `[x]` E-09 · Análisis de Causa Raíz Sistémico (Meta-PM)

**Concepto:** Un agente que corre no por ticket sino periódicamente (semanal/mensual)
que analiza el conjunto completo de tickets resueltos y detecta patrones sistémicos:

- "El 40% de los tickets de este mes son errores de validación nula en la capa DAL
  → recomendación: agregar un análisis estático de null-safety al pipeline CI"
- "5 tickets distintos tocaron FrmPedidos.aspx → módulo candidato a refactorización"
- "Tiempo promedio PM para tickets de tipo 'rendimiento': 85 minutos → aumentar timeout"

Este Meta-PM escribe un reporte mensual en `reports/analisis_sistemico_{fecha}.md`
y puede actualizar automáticamente los parámetros de configuración del daemon
(timeouts, scoring de complejidad) basándose en data real de performance.

**Archivos nuevos:** `meta_analyst.py`, `reports/`  
**Esfuerzo:** Medio-Alto | **Impacto:** Muy alto (mejora sistémica continua)

---

### `[x]` E-10 · Pipeline como API — Integración con Herramientas Externas

**Concepto:** Exponer Stacky como una API REST completa para que otras herramientas
puedan interactuar con el pipeline programáticamente:

```
POST /api/v1/tickets/{id}/process         → lanza pipeline para un ticket
GET  /api/v1/tickets/{id}/status          → estado actual del pipeline
GET  /api/v1/tickets/{id}/artifacts       → descarga todos los archivos generados
POST /api/v1/pipeline/config              → actualiza config en caliente (sin reinicio)
GET  /api/v1/metrics                      → métricas de performance del pipeline
POST /api/v1/webhooks                     → registrar callbacks para eventos
```

Casos de uso:
- Botón en Mantis que dispara Stacky directamente desde la interfaz web
- Slack bot que consulta el estado de un ticket ("¿en qué paso está el #27698?")
- CI/CD que espera la aprobación de QA antes de desplegar
- Script de monitoreo externo

**Archivos a modificar:** `dashboard_server.py` (ampliar como API server)  
**Esfuerzo:** Medio | **Impacto:** Alto (habilita integraciones futuras)

---

---

### `[x]` E-11 · Fase de Aprendizaje de Proyecto (Project Onboarding IA)

**Concepto:** Al agregar un proyecto nuevo a Stacky, en lugar de escribir manualmente
los prompts y la configuración, un botón "Iniciar Fase de Aprendizaje" en el dashboard
lanza un pipeline de descubrimiento autónomo que analiza el workspace y genera toda
la documentación de base y los prompts personalizados.

**El problema actual:** Agregar RSMOBILENET o cualquier proyecto nuevo requiere:
- Escribir `prompts/pm.md`, `dev.md`, `qa.md` desde cero
- Configurar manualmente timeouts, agentes, workspace root
- Conocer de antemano las convenciones del proyecto

Sin esta mejora, Stacky solo escala con trabajo manual de setup.

---

#### Arquitectura de la Fase de Aprendizaje

```
USUARIO: hace clic en "Iniciar Fase de Aprendizaje" para proyecto NUEVO_PROYECTO
            ↓
┌─ FASE 1: DISCOVERY (local, sin IA, ~10 segundos) ─────────────────────┐
│ • Escanea árbol de directorios del workspace                           │
│ • Detecta extensiones dominantes → infiere tech stack                  │
│ • Encuentra archivos de proyecto: .csproj, packages.config, web.config │
│   pom.xml, package.json, *.sln, requirements.txt, etc.                 │
│ • Detecta capas de arquitectura: nombres de carpetas (DAL, BLL, UI,    │
│   Services, Controllers, Models, etc.)                                  │
│ • Samplea N archivos representativos por capa (no lee TODO el código)  │
│ • Encuentra documentación existente: README.md, /docs/, wikis          │
│ • Detecta herramientas de build/test: MSBuild, NUnit, xUnit, etc.     │
│ • Infiere sistema de versionado: SVN, Git, TFS                         │
│ OUTPUT: discovery_report.json con estructura del proyecto              │
└────────────────────────────────────────────────────────────────────────┘
            ↓
┌─ FASE 2: ANÁLISIS IA (agente Claude API, ~2-5 minutos) ───────────────┐
│ INPUT: discovery_report.json + samples de código                       │
│                                                                         │
│ El agente analiza y produce:                                           │
│ • Stack tecnológico completo con versiones detectadas                  │
│ • Convenciones de naming: clases, métodos, variables, tablas DB        │
│ • Patrones arquitectónicos: cómo se estructura una operación típica    │
│ • Capa de acceso a datos: ORM, DAL puro, stored procs, etc.           │
│ • Manejo de errores y logging: patrones existentes en el código        │
│ • Patrones de UI: WebForms, MVC, Blazor, WPF, etc.                    │
│ • Convenciones de mensajes al usuario: i18n, hardcoded, recursos       │
│ • Módulos principales y su responsabilidad                             │
│ • Riesgos y áreas sensibles detectadas ("este módulo tiene 4000 LOC") │
└────────────────────────────────────────────────────────────────────────┘
            ↓
┌─ FASE 3: GENERACIÓN DE ARTEFACTOS ────────────────────────────────────┐
│ Genera automáticamente:                                                 │
│                                                                         │
│ PROJECT_KNOWLEDGE.md                                                    │
│   ├── Stack tecnológico detectado                                      │
│   ├── Mapa de módulos y responsabilidades                              │
│   ├── Convenciones de código (con ejemplos reales del codebase)        │
│   ├── Patrones de acceso a datos                                       │
│   ├── Flujos típicos de una operación CRUD                             │
│   └── Áreas de riesgo / módulos críticos                               │
│                                                                         │
│ prompts/pm.md                                                           │
│   ├── Contexto del proyecto (tech stack, workspace)                    │
│   ├── Convenciones específicas detectadas                              │
│   ├── Lista de módulos principales para contexto de análisis           │
│   └── Instrucciones adaptadas al tipo de proyecto                      │
│                                                                         │
│ prompts/dev.md                                                          │
│   ├── Patrones de implementación del proyecto                          │
│   ├── Ejemplos de código real como referencia de estilo                │
│   ├── Reglas de la capa DAL/BLL/UI específicas                        │
│   └── Herramientas de build y test disponibles                         │
│                                                                         │
│ prompts/qa.md                                                           │
│   ├── Framework de testing detectado                                   │
│   ├── Convenciones de validación del proyecto                          │
│   └── Criterios de aceptación adaptados al stack                       │
│                                                                         │
│ config.json (draft)                                                     │
│   ├── workspace_root detectado                                         │
│   ├── timeouts sugeridos según complejidad estimada del proyecto       │
│   └── agentes pre-configurados con nombres por defecto                 │
└────────────────────────────────────────────────────────────────────────┘
            ↓
┌─ FASE 4: REVISIÓN HUMANA (UI en dashboard) ───────────────────────────┐
│ • Pantalla de review: muestra cada artefacto generado con editor       │
│ • El usuario puede editar, aprobar o regenerar sección por sección     │
│ • "Regenerar esta sección con instrucciones adicionales": text input   │
│ • Al aprobar: guarda en projects/{NOMBRE}/ y activa el proyecto        │
│ • Botón "Re-aprender" disponible en cualquier momento para actualizar  │
│   el conocimiento si el codebase evolucionó                            │
└────────────────────────────────────────────────────────────────────────┘
```

#### Estrategia de sampling para no saturar el contexto

El workspace puede tener miles de archivos. El agente no puede leer todo. Estrategia:

```python
def sample_workspace(workspace_root, max_files=40, max_size_kb=500):
    # 1. Un archivo por subcarpeta de primer nivel (representatividad)
    # 2. Archivos de configuración completos (.csproj, web.config, packages.config)
    # 3. Los 3 archivos más grandes de cada extensión dominante
    # 4. README y docs existentes completos
    # 5. El archivo con más referencias (más importado/usado) por extensión
    # Cada archivo se trunca a max 150 líneas si es muy largo
    # Total: contexto manejable, representativo del proyecto real
```

#### Modo Re-aprendizaje incremental

Después del onboarding inicial, el botón "Actualizar conocimiento" en el dashboard
puede correr solo las partes que cambiaron:
- Si hay nuevos módulos: amplía `PROJECT_KNOWLEDGE.md`
- Si los prompts tienen una tasa de éxito baja en un área: sugiere refinar esa sección
- Si el tech stack cambió (nueva dependencia, migración de framework): alerta y regenera

#### Implementación técnica

```python
# project_learner.py

class ProjectLearner:
    def __init__(self, project_name, workspace_root):
        self.project_name = project_name
        self.workspace_root = workspace_root
    
    def run_discovery(self) -> DiscoveryReport:
        # Fase 1: análisis local puro
        ...
    
    def run_analysis(self, discovery: DiscoveryReport) -> ProjectKnowledge:
        # Fase 2: llama a Claude API con el reporte de discovery
        # Usa claude-sonnet-4-6 con prompt_caching para reducir costo en re-runs
        ...
    
    def generate_artifacts(self, knowledge: ProjectKnowledge) -> dict:
        # Fase 3: genera PROJECT_KNOWLEDGE.md, prompts, config.json draft
        ...
    
    def save_artifacts(self, artifacts: dict, approved=False):
        # Fase 4: guarda en projects/{nombre}/ si el usuario aprobó
        ...
```

**UI — endpoint nuevo:**
```
POST /api/v1/projects/{name}/learn        → inicia fase de aprendizaje
GET  /api/v1/projects/{name}/learn/status → progreso de cada fase
GET  /api/v1/projects/{name}/learn/review → artefactos generados para revisión
POST /api/v1/projects/{name}/learn/approve → confirma y guarda
POST /api/v1/projects/{name}/learn/refine  → regenera sección específica con instrucción adicional
```

**Archivos nuevos:** `project_learner.py`, `workspace_sampler.py`  
**Archivos a modificar:** `dashboard.html`, `dashboard_server.py`, `project_manager.py`  
**Dependencias nuevas:** `anthropic` (Claude API para la fase de análisis)

**Esfuerzo estimado:** Alto (4-6 días)  
**Impacto:** Muy alto — Stacky pasa de ser una herramienta personal a un producto
que cualquier proyecto puede adoptar en minutos en lugar de días.

---

## PARTE 3 — Mejoras Exponenciales Batch 2

---

### `[x]` N-02 · Generador Automático de Commit Messages SVN

**Concepto:** Después de que DEV completa y se genera `SVN_CHANGES.md` (M-04),
el sistema genera automáticamente un mensaje de commit SVN siguiendo las convenciones
detectadas del proyecto:

```
[RIPLEY][BUG] #0027698 - Error validación nula en DAL_Pedidos al procesar pedido sin cliente

- Agregada validación previa de ClienteId en DAL_Pedidos.GetPedidoDetalle()
- Fix en FrmPedidos.aspx.cs: manejo de NullReferenceException en btnGuardar_Click
- INSERT en RIDIOMA para mensaje de error nuevo (m2847 / m2848)
- Query de verificación en QUERIES_ANALISIS.sql

Ref: MantisBT #0027698 | QA: APROBADO | Archivos: 3 modificados
```

El mensaje se guarda en `COMMIT_MESSAGE.txt` en la carpeta del ticket. El developer
solo tiene que copiarlo. Opcionalmente, un botón en el dashboard puede ejecutar
el commit directamente si el usuario lo autoriza explícitamente.

**Archivos nuevos:** `commit_generator.py`  
**Archivos a modificar:** `pipeline_watcher.py`, `dashboard_server.py`  
**Esfuerzo:** Bajo | **Impacto:** Alto

---

### `[x]` N-04 · Modo Batch por Componente

**Concepto:** Si hay 3 tickets que todos tocan `FrmPedidos.aspx` + `DAL_Pedidos.cs`,
procesarlos con análisis PM separados es ineficiente y puede generar soluciones que
se contradicen entre sí. El modo batch agrupa tickets por componente compartido:

```
Grupo detectado: Módulo "Pedidos" (3 tickets)
  - #0027698: Error nulo en DAL al guardar
  - #0027701: Performance lenta en FrmPedidos al cargar
  - #0027715: Validación de stock no funciona en pedido especial

→ PM recibe los 3 INC juntos con instrucción de análisis unificado
→ PM genera 1 ARQUITECTURA_SOLUCION.md que resuelve los 3 sin conflictos
→ DEV implementa en un solo pass con contexto completo del módulo
→ QA valida los 3 juntos
```

El agrupamiento puede ser automático (por archivos detectados en el análisis) o manual
desde el dashboard con drag & drop de tickets a un "batch group".

**Archivos nuevos:** `batch_processor.py`  
**Archivos a modificar:** `daemon.py`, `ticket_detector.py`, `dashboard.html`  
**Esfuerzo:** Alto | **Impacto:** Muy alto

---

### `[x]` N-05 · Detección de Escalada de Prioridad en Mantis

**Concepto:** Mantis permite agregar notas a los tickets. Actualmente Stacky no
monitorea cambios en tickets que ya están scrapeados. Si un cliente escala un ticket
("esto está bloqueando producción", "gerencia está al tanto"), Stacky no lo sabe y
sigue procesando en orden original.

Agregar un monitor de cambios en Mantis que detecte:
- Nuevas notas con keywords de urgencia ("urgente", "bloqueando", "escalado", "cliente")
- Cambio de gravedad en Mantis (de "mayor" a "bloqueante")
- Cambio de estado a "confirmada" o "asignada" en tickets que estaban en espera

Al detectar una escalada, reordena automáticamente la cola de procesamiento y
notifica al usuario con el motivo específico ("Ticket #27698 escalado — nueva nota
del cliente menciona bloqueo de producción").

**Archivos nuevos:** `mantis_change_monitor.py`  
**Archivos a modificar:** `daemon.py`, `notifier.py`  
**Esfuerzo:** Medio | **Impacto:** Alto

---

### `[x]` N-06 · Auto-documentación de Patrones Fix

**Concepto:** Cada vez que DEV completa exitosamente y QA aprueba, el sistema extrae
el patrón de solución y lo agrega automáticamente a la knowledge base del proyecto:

```markdown
## Patrón: NullReference en DAL con Oracle sin EF
**Detectado en:** #0027698, #0026541, #0025901
**Síntoma:** NullReferenceException al acceder campo de objeto retornado por query
**Causa raíz:** Query retorna null cuando no hay registros, código asume siempre devuelve objeto
**Solución probada:**
```csharp
// Antes
var result = dal.GetPedido(id);
var nombre = result.Nombre; // ← crash si no hay registros

// Después
var result = dal.GetPedido(id);
if (result == null) { Error.Agregar(...); return; }
var nombre = result.Nombre;
```
**Archivos típicamente afectados:** DAL_*.cs, cualquier método Get* que retorne objeto único
```

Esta biblioteca de patrones se inyecta en el prompt de PM cuando el análisis inicial
del INC sugiere un patrón conocido (similarity con descripción del patrón > umbral).
DEV también recibe los patrones aplicables como sección "Soluciones probadas".

**Archivos nuevos:** `pattern_extractor.py`, `knowledge/patterns/`  
**Esfuerzo:** Medio | **Impacto:** Muy alto (mejora acumulativa)

---

### `[x]` N-07 · Modo Shadow (Dry Run del Pipeline)

**Concepto:** Antes de ejecutar DEV en un ticket crítico o complejo, el usuario puede
activar "Modo Shadow" que ejecuta el pipeline completo pero sin modificar código real:

- **PM Shadow:** corre normalmente (solo genera documentación, no hay riesgo)
- **DEV Shadow:** el agente recibe instrucción de DESCRIBIR los cambios que haría
  en un `DEV_SHADOW_PLAN.md` en lugar de implementarlos. Lista archivos, líneas,
  tipo de cambio, riesgo estimado.
- **QA Shadow:** valida el plan de DEV Shadow (¿el enfoque es correcto?)

El usuario revisa `DEV_SHADOW_PLAN.md` antes de autorizar la ejecución real.
Ideal para tickets complejos o que tocan módulos críticos. Activable por ticket
desde el dashboard con un toggle "Ejecutar en modo Shadow primero".

**Archivos a modificar:** `prompt_builder.py`, `pipeline_state.py`, `dashboard.html`  
**Esfuerzo:** Medio | **Impacto:** Alto (confianza en tickets críticos)

---

### `[x]` N-08 · Dashboard de Métricas de Calidad por Agente

**Concepto:** Panel de analytics que responde preguntas operativas reales:

```
MÉTRICAS POR AGENTE (últimos 30 días):
┌─────────────────┬────────────┬──────────────┬──────────────┬───────────────┐
│ Agente          │ Tickets    │ Éxito 1er    │ Tiempo prom. │ Tasa rework   │
│                 │ procesados │ intento      │              │               │
├─────────────────┼────────────┼──────────────┼──────────────┼───────────────┤
│ PM-TL Stack 3   │ 47         │ 78%          │ 38 min       │ 4%            │
│ DevStack3       │ 43         │ 65%          │ 72 min       │ 19%           │
│ QA              │ 41         │ 88%          │ 31 min       │ -             │
└─────────────────┴────────────┴──────────────┴──────────────┴───────────────┘

TICKETS POR TIPO (últimos 30 días):
  error_ui: 12  |  error_dal: 18  |  performance: 7  |  validacion: 10

MÓDULOS MÁS FRECUENTES:
  FrmPedidos.aspx: 8 tickets  |  DAL_Pedidos.cs: 11 tickets  |  coMens.cs: 6 tickets

DISTRIBUCIÓN DE TIEMPOS (por etapa):
  PM: mediana 35min, p90: 58min, p99: 61min (→ timeout en 60min es muy ajustado)
  DEV: mediana 68min, p90: 115min (→ timeout en 120min correcto)
```

Estos datos alimentan directamente al Meta-PM (E-09) y al scoring de complejidad (M-07).

**Archivos nuevos:** `metrics_collector.py`  
**Archivos a modificar:** `dashboard.html`, `dashboard_server.py`, `pipeline_state.py`  
**Esfuerzo:** Medio | **Impacto:** Alto

---

### `[x]` N-09 · Notificaciones Slack / Teams

**Concepto:** Las notificaciones Windows Toast son solo visibles en la máquina local
del dev que corre el daemon. Si el equipo tiene más integrantes o el daemon corre
en un servidor compartido, nadie más se entera.

Agregar backends de notificación para Slack y Microsoft Teams vía webhooks:

```python
# notifier.py — nuevos backends
class SlackNotifier:
    def notify(self, event: PipelineEvent):
        # POST a webhook_url configurado en config.json
        # Mensaje con: ticket ID, etapa, status, link al dashboard
        # Menciona @channel solo en errores bloqueantes

class TeamsNotifier:
    def notify(self, event: PipelineEvent):
        # Adaptive Card con colores por tipo de evento
        # Botón "Ver en Dashboard" linkeando a localhost:5050
```

Configurable en `config.json` por proyecto:
```json
"notifications": {
  "slack_webhook": "https://hooks.slack.com/...",
  "teams_webhook": "https://...",
  "notify_on": ["stage_complete", "pipeline_complete", "error", "new_tickets"]
}
```

**Archivos a modificar:** `notifier.py`, `config.json` schema  
**Esfuerzo:** Bajo | **Impacto:** Alto (multiplica visibilidad del equipo)

---

### `[x]` N-10 · Rollback Asistido Post-Regresión

**Concepto:** Si después de commitear los cambios de un ticket se detecta una regresión
(manual o via N-07 monitor), Stacky puede asistir el rollback:

1. Identifica exactamente qué archivos modificó ese ticket (via `SVN_CHANGES.md` de M-04)
2. Genera el comando SVN de revert específico para esos archivos:
   ```
   svn revert N:\SVN\RS\RIPLEY\trunk\WebApplication\DAL\DAL_Pedidos.cs
   svn revert N:\SVN\RS\RIPLEY\trunk\WebApplication\Forms\FrmPedidos.aspx.cs
   ```
3. Genera un patch de rollback (`ROLLBACK.patch`) aplicable con `svn patch`
4. Si el ticket fue parte de un batch (N-04), lista los otros tickets del batch
   que podrían verse afectados por el rollback
5. Crea automáticamente un nuevo ticket en el backlog de Stacky: el rollback
   como trabajo a procesar con PM → DEV → QA

El rollback no se ejecuta automáticamente — siempre requiere autorización explícita
del usuario. Stacky genera el plan y los comandos; el humano decide si ejecutarlos.

**Archivos nuevos:** `rollback_assistant.py`  
**Archivos a modificar:** `dashboard.html`, `dashboard_server.py`  
**Esfuerzo:** Medio | **Impacto:** Alto (reduce el costo de errores post-commit)

---

## Tabla de Priorización Global

| ID | Nombre | Batch | Esfuerzo | Impacto | Estado |
|----|--------|-------|----------|---------|--------|
| M-02 | Validación de Output entre Etapas | Robustez | Bajo | Alto | `[x]` |
| N-02 | Generador de Commit Messages SVN | Batch 2 | Bajo | Alto | `[x]` |
| M-03 | Reintentos con Contexto de Falla | Robustez | Bajo | Medio | `[x]` |
| M-04 | SVN Diff Post-DEV | Robustez | Bajo | Alto | `[x]` |
| M-05 | Contexto desde ARQUITECTURA_SOLUCION | Robustez | Bajo | Medio | `[x]` |
| N-09 | Notificaciones Slack / Teams | Batch 2 | Bajo | Alto | `[x]` |
| M-01 | Feedback Loop QA → DEV | Robustez | Medio | Alto | `[x]` |
| E-05 | Detector de Tickets Auto-Cerrables | Exp. 1 | Medio | Alto | `[x]` |
| N-05 | Detección de Escalada en Mantis | Batch 2 | Medio | Alto | `[x]` |
| M-07 | Scoring de Complejidad | Robustez | Medio | Medio | `[x]` |
| E-01 | Knowledge Base de Tickets Resueltos | Exp. 1 | Medio | Muy alto | `[x]` |
| N-06 | Auto-documentación de Patrones Fix | Batch 2 | Medio | Muy alto | `[x]` |
| E-11 | Fase de Aprendizaje de Proyecto | Exp. 1 | Alto | Muy alto | `[x]` |
| E-02 | Auto-actualización de Mantis | Exp. 1 | Medio | Alto | `[x]` |
| N-07 | Modo Shadow (Dry Run) | Batch 2 | Medio | Alto | `[x]` |
| N-08 | Métricas de Calidad por Agente | Batch 2 | Medio | Alto | `[x]` |
| E-10 | Pipeline como API REST | Exp. 1 | Medio | Alto | `[x]` |
| E-09 | Meta-PM Sistémico | Exp. 1 | Medio-Alto | Muy alto | `[x]` |
| E-08 | Dashboard Interactivo | Exp. 1 | Alto | Alto | `[x]` |
| N-10 | Rollback Asistido | Batch 2 | Medio | Alto | `[x]` |
| M-06 | Procesamiento Paralelo por Etapas | Robustez | Alto | Muy alto | `[x]` |
| N-04 | Modo Batch por Componente | Batch 2 | Alto | Muy alto | `[x]` |
| E-03 | Grafo de Dependencias entre Tickets | Exp. 1 | Alto | Muy alto | `[x]` |
| E-04 | Prompt Scoring y Evolución | Exp. 1 | Alto | Muy alto | `[x]` |
| E-06 | Contexto Semántico con Tree-sitter | Exp. 1 | Alto | Muy alto | `[x]` |
| E-07 | Monitor de Regresiones Post-Commit | Exp. 1 | Alto | Alto | `[x]` |
| **G-02** | **Índice Vectorial del Codebase** | **Game Changer** | **Alto** | **Transformador** | `[x]` |
| **G-03** | **Inyección Live de Schema Oracle** | **Game Changer** | **Medio** | **Transformador** | `[x]` |
| **G-04** | **Ejecución Automatizada de Tests** | **Game Changer** | **Medio** | **Transformador** | `[x]` |
| **G-05** | **Blast Radius Analysis** | **Game Changer** | **Alto** | **Transformador** | `[x]` |
| **G-06** | **Memoria Persistente de Agentes** | **Game Changer** | **Alto** | **Transformador** | `[x]` |
| **G-07** | **Chat Conversacional con Stacky** | **Game Changer** | **Medio** | **Transformador** | `[x]` |
| **G-08** | **Deliberación Multi-Agente** | **Game Changer** | **Alto** | **Transformador** | `[x]` |
| **G-09** | **Modo Autonomía Total con Approval Gates** | **Game Changer** | **Alto** | **Transformador** | `[x]` |
| **G-10** | **Capa de Inteligencia Predictiva** | **Game Changer** | **Alto** | **Transformador** | `[x]` |

---

## Notas de Implementación

**Secuencias con dependencias:**
- M-01 (feedback loop) depende de M-02 (validación de output).
- M-04 (SVN diff) es prerrequisito de N-02 (commit messages) y N-10 (rollback).
- E-01 (knowledge base) es prerrequisito de E-03 (grafo) y N-06 (patrones fix).
- E-11 (fase de aprendizaje) es prerrequisito de N-03 (cross-project patterns).
- N-08 (métricas) es prerrequisito de E-04 (prompt scoring) y E-09 (meta-PM).

**Implementaciones independientes que se pueden hacer en paralelo:**
M-02, M-03, M-04, M-05, N-09 — sin dependencias entre sí. Empezar por acá.

**Umbrales de dataset para mejoras basadas en historial:**
- E-04 (prompt scoring): mínimo 30-50 tickets procesados.
- N-06 (patrones fix): mínimo 10-15 tickets completados con QA aprobado.
- E-09 (meta-PM): mínimo 1 mes de operación continua.

**Consideraciones de costo IA:**
- E-11 (fase de aprendizaje): usa Claude API directamente. Costo único por proyecto,
  amortizado en el tiempo. Usar prompt caching para re-runs. Estimado: ~$0.50-2.00 por proyecto.
- El resto de las mejoras de Partes 1-3 son locales (sin costo IA adicional).
- Las mejoras G-xx tienen su propio análisis de costo en cada sección.

---

## PARTE 4 — Game Changers

Estas 10 mejoras no son incrementales. Cada una redefine una parte fundamental de cómo
Stacky opera. Implementarlas convierte Stacky de una herramienta de automatización en
un sistema de ingeniería autónomo de nivel profesional.

---

### `[x]` G-01 · Generación de Código Directo via Claude API (Elimina el Bridge)

**El problema de fondo:** Todo el pipeline actual depende del Bridge HTTP a VS Code
Copilot. Esto introduce: latencia impredecible, dependencia de que VS Code esté abierto,
un proceso externo que puede fallar, imposibilidad de correr en servidor, y cero
control sobre el output. Los agentes escriben en el chat de Copilot y Stacky no sabe
qué pasó hasta que detecta un flag en disco.

**El cambio:** Eliminar la dependencia de Copilot para las etapas de generación de
código. Usar Claude API directamente desde Python. Stacky se convierte en el agente
— no necesita un intermediario.

#### Arquitectura del nuevo flujo

```
FLUJO ACTUAL:
  Stacky → Bridge HTTP → VS Code Copilot → Agente escribe archivos → Flag en disco
  (latencia: impredecible, control: cero, confiabilidad: parcial)

FLUJO NUEVO:
  Stacky → Claude API → Respuesta estructurada → Stacky aplica cambios en disco
  (latencia: 10-60 segundos, control: total, confiabilidad: 99%+)
```

#### Formato de respuesta estructurada

El prompt instruye a Claude a responder en un formato parseble:

```xml
<stacky_response>
  <analysis>
    Causa raíz identificada: campo ClienteId puede ser NULL en RSTRP_PEDIDOS
    cuando el pedido viene del canal web sin autenticación completa.
  </analysis>
  
  <file_changes>
    <file path="WebApplication/DAL/DAL_Pedidos.cs" action="modify">
      <change description="Agregar validación null antes de acceder a ClienteId">
        <find>var cliente = GetCliente(pedido.ClienteId);</find>
        <replace>
if (pedido.ClienteId == null)
{
    Error.Agregar(Const.ERROR_VALID, Idm.Texto(coMens.m2847, "Cliente requerido"), "Pedidos", Const.SEVERIDAD_Alta);
    return null;
}
var cliente = GetCliente(pedido.ClienteId.Value);
        </replace>
      </change>
    </file>
    
    <file path="WebApplication/Forms/FrmPedidos.aspx.cs" action="modify">
      <change description="Manejo de retorno null de DAL">
        <find>var detalle = dal.GetPedidoDetalle(id);</find>
        <replace>
var detalle = dal.GetPedidoDetalle(id);
if (detalle == null) { msgd.Show(Error, Idm.Texto(coMens.m2500, "Error")); return; }
        </replace>
      </change>
    </file>
  </file_changes>
  
  <new_files>
    <file path="WebApplication/Resources/coMens.cs" action="append">
      <content>public const string m2847 = "m2847";</content>
    </file>
  </new_files>
  
  <completion_flag>DEV_COMPLETADO</completion_flag>
  <summary>3 archivos modificados, 1 constante nueva, validación null agregada en 2 puntos</summary>
</stacky_response>
```

#### Aplicación automática de cambios

```python
# code_applicator.py
class CodeApplicator:
    def apply_response(self, response: StackyResponse, workspace_root: str):
        for change in response.file_changes:
            file_path = Path(workspace_root) / change.path
            content = file_path.read_text(encoding='utf-8')
            
            # Validación antes de aplicar
            if change.find not in content:
                raise ApplicationError(f"Fragmento no encontrado en {change.path}")
            
            # Aplicar cambio (replace exacto o diff patch)
            new_content = content.replace(change.find, change.replace, 1)
            
            # Backup automático antes de sobrescribir
            backup_path = file_path.with_suffix('.stacky_backup')
            file_path.rename(backup_path)
            file_path.write_text(new_content, encoding='utf-8')
        
        # Crear flag de completado
        self.create_completion_flag(response)
```

#### Modo híbrido (transición gradual)

No es necesario eliminar Copilot de golpe. Configurar por etapa:
```json
"stages": {
  "pm": { "engine": "copilot" },    ← análisis: Copilot por ahora
  "dev": { "engine": "claude_api" }, ← implementación: Claude API directo
  "qa":  { "engine": "copilot" }    ← validación: Copilot por ahora
}
```

**Dependencias nuevas:** `anthropic` SDK  
**Archivos nuevos:** `claude_engine.py`, `code_applicator.py`, `response_parser.py`  
**Archivos a modificar:** `daemon.py`, `pipeline_runner.py`, `copilot_bridge.py`  
**Costo IA:** ~$0.10-0.50 por ticket según complejidad (Claude Sonnet). Con prompt
caching en el contexto de código, el costo real es 60-80% menor en tickets similares.  
**Esfuerzo:** Alto (5-7 días)  
**Impacto:** Transformador — elimina la mayor fuente de falla del sistema, hace el
pipeline ejecutable en servidor, y da control total sobre los cambios aplicados.

---

### `[x]` G-02 · Índice Vectorial del Codebase (Búsqueda Semántica Total)

**El problema de fondo:** Hoy el contexto de código que recibe cada agente se construye
con heurísticas (regex, keywords, rutas mencionadas en documentos). Un agente que recibe
"hay un error en FrmPedidos al procesar pedido sin cliente" no puede encontrar que
`ValidarClientePedido()` en `BLL_Validaciones.cs` ya existe y hace exactamente eso.
El resultado: DEV reimplementa lógica existente, crea duplicados, o rompe abstracciones.

**El cambio:** Construir un índice semántico de todo el codebase — cada función, clase,
método, stored procedure, tabla — representados como vectores. Cualquier consulta en
lenguaje natural retorna los fragmentos más relevantes con precisión quirúrgica.

#### Qué se indexa

```
Por cada archivo .cs, .aspx, .vb, .sql en el trunk:
  → Extraer cada función/método/clase como chunk individual
  → Metadata: archivo, línea inicio, línea fin, nombre, tipo
  → Generar embedding (vector de 1536 dimensiones)
  → Almacenar en índice local (FAISS o sqlite-vec)

Resultado: índice de ~50,000-200,000 chunks para un proyecto mediano
Tamaño estimado: 500MB-2GB en disco
Tiempo de build inicial: 2-8 horas (se hace una vez)
Tiempo de actualización incremental (solo archivos cambiados): 30-120 segundos
```

#### Cómo se usa en el pipeline

```python
# semantic_search.py
index = CodebaseIndex.load("projects/RIPLEY/codebase_index/")

# PM pregunta sobre el problema
results = index.search(
    "validación de cliente nulo en pedidos Oracle",
    top_k=8,
    filter_extensions=[".cs", ".sql"]
)
# → Retorna: BLL_Validaciones.ValidarClientePedido(), DAL_Pedidos.GetCliente(),
#            RSTRP_PEDIDOS schema, coMens.m2847 (si ya existe)

# DEV pregunta sobre implementación
results = index.search(
    "cómo se usa Error.Agregar con SEVERIDAD_Alta en WebForms",
    top_k=5,
    filter_path="WebApplication/Forms/"
)
# → Retorna: 5 ejemplos reales del codebase de cómo se hace exactamente
```

#### Stack técnico sin servidor externo

```python
# Opción A: FAISS (Meta) — rápido, sin servidor, 100% local
import faiss
import numpy as np

# Opción B: sqlite-vec — integrado en SQLite, portable
# Opción C: ChromaDB — más features, igualmente local

# Embeddings: text-embedding-3-small de OpenAI ($0.00002/1K tokens)
# o nomic-embed-text (local, gratis, via Ollama)
# Costo de indexar trunk completo: ~$2-5 (una sola vez)
```

#### Actualización incremental automática

```python
# El daemon corre index.update() después de cada DEV_COMPLETADO
# Solo re-indexa los archivos que cambiaron (SVN_CHANGES.md)
# Tiempo: 5-30 segundos por ticket completado
```

**Dependencias nuevas:** `faiss-cpu` o `chromadb`, `openai` (embeddings) o `ollama`  
**Archivos nuevos:** `codebase_indexer.py`, `semantic_search.py`  
**Esfuerzo:** Alto (5-7 días para build inicial + integración)  
**Impacto:** Transformador — convierte el contexto de código de "heurístico y ruidoso"
a "quirúrgico y semántico". DEV deja de reinventar la rueda.

---

### `[x]` G-03 · Inyección Live de Schema Oracle en Prompts

**El problema de fondo:** PM y DEV trabajan con suposiciones sobre la base de datos.
El análisis técnico dice "la tabla RSTRP_PEDIDOS tiene un campo ClienteId" pero no
sabe si es NUMBER(10), si acepta NULL, si tiene un índice, si hay un FK que lo
restringe. DEV escribe queries basadas en ese conocimiento parcial, QA valida código
que puede fallar en producción por una diferencia de tipo.

**El cambio:** Conectar Stacky directamente a Oracle y extraer el schema real en el
momento en que se procesa cada ticket. Los prompts reciben metadata de DB authoritative.

#### Qué se extrae y cuándo

```python
# oracle_schema_injector.py

def get_relevant_schema(ticket_content: str, connection: cx_Oracle.Connection) -> str:
    # 1. Extrae nombres de tablas mencionadas en el ticket o análisis PM
    tables = extract_table_names(ticket_content)  # regex + conocimiento del proyecto
    
    # 2. Para cada tabla: columnas, tipos, nullability, constraints, índices
    schema_info = []
    for table in tables:
        columns = query("""
            SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, NULLABLE, DATA_DEFAULT
            FROM ALL_TAB_COLUMNS 
            WHERE TABLE_NAME = :t AND OWNER = :owner
            ORDER BY COLUMN_ID
        """, table=table)
        
        constraints = query("""
            SELECT c.CONSTRAINT_NAME, c.CONSTRAINT_TYPE, cc.COLUMN_NAME,
                   c.R_CONSTRAINT_NAME
            FROM ALL_CONSTRAINTS c
            JOIN ALL_CONS_COLUMNS cc ON c.CONSTRAINT_NAME = cc.CONSTRAINT_NAME
            WHERE c.TABLE_NAME = :t AND c.OWNER = :owner
        """, table=table)
        
        indexes = query("""
            SELECT INDEX_NAME, UNIQUENESS, COLUMN_NAME
            FROM ALL_IND_COLUMNS ic
            JOIN ALL_INDEXES i ON ic.INDEX_NAME = i.INDEX_NAME
            WHERE i.TABLE_NAME = :t AND i.TABLE_OWNER = :owner
        """, table=table)
        
        schema_info.append(format_schema_markdown(table, columns, constraints, indexes))
    
    return "\n".join(schema_info)
```

#### Cómo se ve en el prompt

```markdown
## Schema Oracle — Tablas relevantes (extraído en tiempo real)

### RSTRP_PEDIDOS
| Columna | Tipo | Nullable | Default |
|---------|------|----------|---------|
| PEDIDO_ID | NUMBER(10) | NO | - |
| CLIENTE_ID | NUMBER(10) | **YES** ← | - |
| FECHA_PEDIDO | DATE | NO | SYSDATE |
| ESTADO | VARCHAR2(20) | NO | 'PENDIENTE' |

**Constraints:**
- PK: PK_RSTRP_PEDIDOS (PEDIDO_ID)
- FK: FK_PED_CLI → RSTRP_CLIENTES(CLIENTE_ID) — ON DELETE SET NULL ←

**Índices:**
- IDX_PED_CLIENTE (CLIENTE_ID) — NOT UNIQUE
- IDX_PED_FECHA (FECHA_PEDIDO) — NOT UNIQUE

⚠️ CLIENTE_ID acepta NULL y tiene FK con ON DELETE SET NULL.
   Cualquier acceso debe validar nulidad antes de usar el valor.
```

Este bloque le dice a PM en 5 segundos lo que de otra forma requiere ejecutar queries
de diagnóstico manualmente. Y le dice a DEV exactamente por qué hay que validar null.

#### Cache de schema para evitar consultas repetidas

```python
# Cache con TTL de 1 hora — el schema no cambia frecuentemente
# Si la tabla no existe: alerta en el análisis PM ("tabla mencionada no existe en DB")
# Si hay diferencias entre lo que dice el ticket y el schema real: alerta explícita
```

**Dependencias nuevas:** `cx_Oracle` o `oracledb`  
**Archivos nuevos:** `oracle_schema_injector.py`  
**Archivos a modificar:** `prompt_builder.py`, `config.json` (conexión DB)  
**Esfuerzo:** Medio (2-3 días)  
**Impacto:** Transformador — elimina una categoría entera de bugs en el análisis y
la implementación. DEV escribe queries correctas desde el primer intento.

---

### `[x]` G-04 · Ejecución Automatizada de Tests Post-DEV

**El problema de fondo:** QA valida revisando el código y el plan. No ejecuta nada.
Si DEV rompió un test existente o introdujo un bug en un path no relacionado, QA
lo puede pasar por alto. El primer momento en que se detecta es en producción.

**El cambio:** Después de que DEV completa y antes de invocar QA, Stacky ejecuta
automáticamente la suite de tests del proyecto y le pasa los resultados a QA como
parte del prompt. QA recibe evidencia objetiva, no solo código para revisar.

#### Detección automática del runner de tests

```python
# test_runner.py
def detect_and_run_tests(workspace_root: str, changed_files: list[str]) -> TestReport:
    
    # Detectar framework
    if find_files("*.Tests.csproj"):
        return run_dotnet_test(workspace_root, changed_files)
    elif find_files("nunit.framework.dll"):
        return run_nunit(workspace_root, changed_files)
    elif find_files("pytest.ini", "setup.py"):
        return run_pytest(workspace_root, changed_files)
    else:
        return TestReport(status="no_tests_found", message="No se detectó suite de tests")

def run_dotnet_test(workspace_root, changed_files):
    # Identifica qué proyectos de test cubren los archivos modificados
    # Corre solo esos tests (no la suite completa — puede tardar horas)
    relevant_test_projects = find_test_projects_for_files(changed_files)
    
    result = subprocess.run([
        "dotnet", "test", *relevant_test_projects,
        "--logger", "trx",
        "--no-build",
        "--filter", build_filter_from_changed_files(changed_files)
    ], capture_output=True, timeout=300)
    
    return parse_trx_report(result)
```

#### Cómo se inyecta en QA

```markdown
## Resultados de Tests Automáticos

**Ejecutados:** 47 tests en 3 proyectos relacionados con los archivos modificados  
**Duración:** 28 segundos  
**Estado:** ⚠️ 44 PASSED · 3 FAILED

### Tests Fallidos:
- `PedidosTests.ValidarPedido_ClienteNulo_DebeRetornarError` — FAILED
  Expected: ValidationError | Actual: NullReferenceException
  → El fix en DAL_Pedidos no propagó correctamente hacia la capa BLL

- `PedidosTests.GuardarPedido_ConDescuento_DebeCalcularCorrectamente` — FAILED
  El cambio en línea 89 afectó el cálculo de descuento (side effect no previsto)

**Tu análisis debe incluir si estos fallos son:** bloqueos para el ticket o tests
desactualizados que deben actualizarse como parte del fix.
```

#### Modo sin suite de tests

Si el proyecto no tiene tests (caso común en sistemas legacy), el runner detecta esto
y QA recibe una sección diferente:

```markdown
## Tests Automáticos
No se encontró suite de tests en el proyecto. QA debe validar manualmente
según los criterios de aceptación de TAREAS_DESARROLLO.md.

Archivos modificados que requieren validación manual:
- DAL_Pedidos.cs → probar GetPedidoDetalle con CLIENTE_ID NULL en DB
- FrmPedidos.aspx.cs → probar flujo completo desde UI
```

**Archivos nuevos:** `test_runner.py`, `test_report_parser.py`  
**Archivos a modificar:** `pipeline_watcher.py`, `prompt_builder.py`  
**Esfuerzo:** Medio (2-4 días, variable según runners a soportar)  
**Impacto:** Transformador — QA pasa de "revisión de código" a "verificación con
evidencia objetiva". Bugs de regresión se detectan antes de que lleguen a producción.

---

### `[x]` G-05 · Blast Radius Analysis (Mapa de Impacto de Cambios)

**El problema de fondo:** Antes de que DEV toque un archivo, nadie sabe qué más podría
romperse. `DAL_Pedidos.cs` puede ser importado por 12 módulos distintos. Si DEV cambia
la firma de `GetPedidoDetalle()`, los 12 se rompen. Hoy esto se descubre en compilación
o en producción.

**El cambio:** Antes de invocar DEV, Stacky analiza estáticamente qué archivos del
trunk dependen de los que van a ser modificados, construye un mapa de impacto, y se
lo entrega a DEV y QA antes de que empiece el trabajo.

#### Análisis estático de dependencias

```python
# blast_radius_analyzer.py

class BlastRadiusAnalyzer:
    def analyze(self, files_to_modify: list[str], workspace_root: str) -> BlastRadiusReport:
        
        dependents = {}
        for target_file in files_to_modify:
            # Qué clases/métodos públicos expone este archivo
            public_api = self.extract_public_api(target_file)
            
            # Quién en el trunk importa o referencia este archivo
            references = []
            for ext in ['.cs', '.aspx', '.aspx.cs', '.vb']:
                for f in glob(f"{workspace_root}/**/*{ext}"):
                    if self.file_references(f, target_file, public_api):
                        references.append({
                            "file": f,
                            "references": self.get_specific_references(f, public_api),
                            "risk": self.estimate_risk(f, public_api)
                        })
            
            dependents[target_file] = sorted(references, key=lambda x: x['risk'], reverse=True)
        
        return BlastRadiusReport(
            direct_dependents=dependents,
            risk_score=self.calculate_total_risk(dependents),
            high_risk_files=[f for f in dependents.values() if f['risk'] == 'HIGH']
        )
```

#### El mapa de impacto que recibe DEV

```markdown
## Blast Radius — Análisis de Impacto

**Archivos a modificar:** DAL_Pedidos.cs, FrmPedidos.aspx.cs

### DAL_Pedidos.cs — 8 dependientes directos

| Archivo | Métodos usados | Riesgo |
|---------|----------------|--------|
| BLL_Pedidos.cs | GetPedidoDetalle(), SavePedido() | 🔴 ALTO |
| FrmPedidos.aspx.cs | GetPedidoDetalle() | 🟡 MEDIO |
| FrmReportes.aspx.cs | GetPedidoDetalle(), GetPedidosPorFecha() | 🔴 ALTO |
| BatchProcesarPedidos.cs | GetPedidosPendientes(), UpdateEstado() | 🔴 ALTO |
| FrmConsultaPedidos.aspx.cs | GetPedidoDetalle() | 🟡 MEDIO |
| DAL_Auditoria.cs | GetPedidoDetalle() (para log) | 🟢 BAJO |
| TestPedidos.cs | Todos los métodos | 🔴 ALTO |
| WebService_Pedidos.asmx | GetPedidoDetalle() | 🔴 ALTO |

**Riesgo total: 🔴 CRÍTICO — 5 dependientes de alto riesgo**

### Instrucción para DEV:
Si modificás la firma de GetPedidoDetalle(), debés actualizar los 8 dependientes
listados. Si solo modificás la implementación interna, el riesgo es BAJO.
Preferir cambios internos sobre cambios de firma pública.
```

#### Integración con QA

QA recibe el mismo mapa con instrucción de validar los archivos de alto riesgo
aunque no sean parte explícita del ticket:

```markdown
## Validación de Blast Radius — Requerida por QA

Además de validar los cambios del ticket, verificar que estos archivos de alto
riesgo no fueron afectados negativamente:
- [ ] BLL_Pedidos.cs — probar flujo de negocio completo
- [ ] FrmReportes.aspx.cs — verificar que los reportes cargan correctamente
- [ ] BatchProcesarPedidos.cs — verificar proceso batch con pedidos de prueba
```

**Archivos nuevos:** `blast_radius_analyzer.py`  
**Archivos a modificar:** `prompt_builder.py`, `pipeline_watcher.py`  
**Esfuerzo:** Alto (4-6 días — el análisis estático de C# es no trivial)  
**Impacto:** Transformador — convierte a DEV y QA en conscientes del riesgo sistémico
de cada cambio. Elimina una categoría de bugs que hoy solo se detectan en producción.

---

### `[x]` G-06 · Memoria Persistente de Agentes por Codebase

**El problema de fondo:** Cada invocación de agente empieza desde cero. PM que analizó
20 tickets de RIPLEY no recuerda nada de ellos. DEV no recuerda que `DAL_Pedidos.cs`
tiene un bug conocido en el null check de la línea 89 que ya se fijó 3 veces. Esta
amnesia es la raíz de muchos análisis duplicados y errores recurrentes.

**El cambio:** Cada agente mantiene una memoria persistente y estructurada que crece
con cada ticket procesado. Antes de cada invocación, Stacky inyecta los recuerdos
relevantes para el ticket actual.

#### Estructura de memoria por agente

```
knowledge/
└── RIPLEY/
    ├── agent_memory/
    │   ├── pm_memory.json       ← lo que PM aprendió sobre el proyecto
    │   ├── dev_memory.json      ← lo que DEV aprendió sobre el código
    │   └── qa_memory.json       ← lo que QA aprendió sobre los patrones de bugs
    └── episodic_memory/
        ├── 0027698_episode.json ← qué pasó en ese ticket específico
        ├── 0026541_episode.json
        └── ...
```

#### Tipos de memoria

```python
# memory_manager.py

# MEMORIA SEMÁNTICA — conocimiento general del proyecto
pm_memory = {
    "known_patterns": [
        {
            "pattern": "null_cliente_en_pedidos",
            "description": "ClienteId puede ser NULL en RSTRP_PEDIDOS. Siempre validar.",
            "seen_in_tickets": ["0027698", "0026541", "0025901"],
            "confidence": 0.95
        }
    ],
    "known_modules": {
        "FrmPedidos": "módulo de alta complejidad, tocado en 8 tickets",
        "DAL_Pedidos": "DAL crítico, 11 tickets relacionados, null checks son el patrón más común"
    },
    "risky_areas": ["FrmPedidos.aspx.cs línea 234 — lógica de descuento compleja"]
}

# MEMORIA EPISÓDICA — qué pasó en tickets anteriores
episode = {
    "ticket_id": "0027698",
    "description": "Error nulo en pedido sin cliente",
    "root_cause": "ClienteId NULL + falta de validación previa",
    "solution_approach": "validación en DAL antes de acceso + mensaje RIDIOMA nuevo",
    "files_modified": ["DAL_Pedidos.cs", "FrmPedidos.aspx.cs", "coMens.cs"],
    "outcome": "QA aprobado en primer intento",
    "lessons": ["siempre verificar nullability en ALL_TAB_COLUMNS antes de asumir"]
}
```

#### Cómo se usa en el prompt

```markdown
## Memoria del Agente PM — Conocimiento acumulado de RIPLEY

**Patrones conocidos relevantes para este ticket:**
- PATRÓN DETECTADO: "null en campo de relación Oracle"
  Visto en 3 tickets anteriores (#0027698, #0026541, #0025901)
  Causa raíz típica: campo acepta NULL en schema + código no valida antes de usar
  Solución probada: validar con `if (campo == null)` antes del acceso + error RIDIOMA

**Módulos involucrados — historial:**
- FrmPedidos.aspx.cs: modificado en 8 tickets anteriores. Área de alta actividad.
  Última modificación: #0027698 (hace 2 días). Precaución con merge conflicts.
- DAL_Pedidos.cs: 11 tickets relacionados. Null checks son el patrón más común.

**Episodio más similar:**
- Ticket #0026541: síntoma idéntico, misma causa raíz, fix en 38 minutos.
  Ver ANALISIS_TECNICO.md de ese ticket para referencia.
```

#### Actualización de memoria post-ticket

```python
# Después de cada pipeline completado con QA aprobado:
memory_manager.extract_and_store(ticket_folder, outcome="success")

# Si hubo rework o errores:
memory_manager.extract_and_store(ticket_folder, outcome="rework", rework_reason=...)
# → genera un "lesson learned" negativo que previene el mismo error
```

**Archivos nuevos:** `memory_manager.py`, `knowledge/RIPLEY/agent_memory/`  
**Archivos a modificar:** `prompt_builder.py`, `pipeline_watcher.py`  
**Esfuerzo:** Alto (4-5 días)  
**Impacto:** Transformador — el sistema mejora acumulativamente. Después de 50 tickets,
es cualitativamente más inteligente que después de 5. El conocimiento no se pierde.

---

### `[x]` G-07 · Interfaz Conversacional — Chat con Stacky

**El problema de fondo:** Para saber qué está pasando hay que abrir el dashboard,
leer tablas, navegar carpetas. Para hacer algo hay que ejecutar comandos CLI o usar
botones específicos. La interacción es siempre iniciada por el humano, en formatos
predefinidos.

**El cambio:** Una interfaz de chat en lenguaje natural donde el usuario puede preguntar
o dar órdenes sobre el pipeline, los tickets, el codebase, y la configuración.

#### Casos de uso

```
Usuario: "¿En qué etapa está el ticket 27698?"
Stacky:  "El #0027698 está en QA desde hace 23 minutos. DevStack3 completó a las 14:32
          y modificó 3 archivos (DAL_Pedidos.cs, FrmPedidos.aspx.cs, coMens.cs).
          El timeout de QA es en 37 minutos."

Usuario: "¿Qué tickets tocan FrmPedidos este mes?"
Stacky:  "8 tickets tocaron FrmPedidos.aspx.cs en abril:
          #0027698 (completado), #0027446 (en PM), #0027321 (completado)...
          Es el módulo más activo del mes."

Usuario: "Pausá el pipeline del 27446 hasta mañana"
Stacky:  "Pipeline de #0027446 pausado. El daemon no lo procesará hasta que 
          lo reanudes o hasta las 09:00 de mañana si configurás un horario."

Usuario: "¿Cuál es el ticket más urgente ahora?"
Stacky:  "El #0027732 (bloqueante, escalado por el cliente ayer). Está en 'asignada'
          pero no se está procesando porque hay 2 tickets antes en la cola.
          ¿Querés que lo suba al tope?"

Usuario: "Mostrá el análisis PM del 27698"
Stacky:  [muestra ANALISIS_TECNICO.md renderizado en el chat]

Usuario: "¿Qué aprendió DEV sobre DAL_Pedidos?"
Stacky:  [consulta dev_memory.json y resume lo relevante]
```

#### Arquitectura

```python
# chat_interface.py

class StackyChat:
    def __init__(self, pipeline_state, knowledge_base, daemon):
        self.claude = anthropic.Anthropic()
        self.tools = [
            get_ticket_status_tool,
            search_tickets_tool,
            pause_resume_pipeline_tool,
            reorder_queue_tool,
            get_agent_memory_tool,
            read_ticket_artifact_tool,
            get_metrics_tool,
        ]
    
    def chat(self, user_message: str) -> str:
        # Claude decide qué herramientas usar para responder
        # Ejecuta las herramientas contra el estado real del pipeline
        # Retorna respuesta en lenguaje natural
        response = self.claude.messages.create(
            model="claude-haiku-4-5-20251001",  # rápido y barato para chat
            system=STACKY_SYSTEM_PROMPT,
            tools=self.tools,
            messages=[{"role": "user", "content": user_message}]
        )
        return self.process_response(response)
```

#### UI — integrada en el dashboard

Panel de chat lateral en el dashboard. También disponible como:
- CLI: `python stacky.py chat "¿qué está pasando?"`
- Endpoint: `POST /api/v1/chat` (para integración con Slack bot o Teams)

**Dependencias nuevas:** `anthropic` SDK  
**Archivos nuevos:** `chat_interface.py`, `chat_tools.py`  
**Archivos a modificar:** `dashboard.html`, `dashboard_server.py`  
**Costo IA:** ~$0.001-0.01 por consulta (claude-haiku, respuestas cortas)  
**Esfuerzo:** Medio (3-4 días)  
**Impacto:** Transformador — reduce la barrera de uso a cero. Cualquier persona del
equipo puede interactuar con el sistema sin conocer su estructura interna.

---

### `[x]` G-08 · Deliberación Multi-Agente para Tickets Complejos

**El problema de fondo:** Para tickets marcados como "Complejo" (M-07), una sola
invocación de PM puede errar la causa raíz. El agente tiene un solo intento para
entender un problema multi-componente con información incompleta. Si falla el análisis
PM, todo lo que sigue (DEV, QA) trabaja sobre un diagnóstico incorrecto.

**El cambio:** Para tickets de alta complejidad, ejecutar múltiples instancias de PM
en paralelo con diferentes "perspectivas" del problema, y luego un agente Sintetizador
que combina los mejores elementos de cada análisis en una solución unificada.

#### Arquitectura de deliberación

```
TICKET COMPLEJO DETECTADO (score > umbral)
            ↓
┌─ PM Perspectiva 1: "Enfoque DAL/DB" ─────┐
│ Instrucción: Analizá priorizando la capa  │
│ de datos. Asumí que la causa raíz está    │
│ en queries, schema, o transacciones.      │
└──────────────────────────────────────────┘
┌─ PM Perspectiva 2: "Enfoque UI/BLL" ─────┐  ← en paralelo
│ Instrucción: Analizá priorizando la capa  │
│ de negocio y presentación. Asumí que la  │
│ causa está en validaciones o flujo UI.    │
└──────────────────────────────────────────┘
┌─ PM Perspectiva 3: "Enfoque integración" ┐  ← en paralelo
│ Instrucción: Analizá considerando que     │
│ puede ser un problema de integración      │
│ entre módulos o sistemas externos.        │
└──────────────────────────────────────────┘
            ↓ (cuando los 3 terminan, ~25-40 min)
┌─ AGENTE SINTETIZADOR ─────────────────────┐
│ Recibe los 3 análisis completos           │
│ Identifica: consensos, contradicciones,   │
│ puntos ciegos de cada perspectiva         │
│ Produce: análisis unificado que integra   │
│ los mejores elementos de los 3            │
│ Señala: dónde los 3 coinciden (alta       │
│ confianza) y dónde difieren (riesgo)      │
└───────────────────────────────────────────┘
            ↓
DEV recibe el análisis sintetizado + los 3 originales como referencia
```

#### Cómo el Sintetizador genera confianza

```markdown
## Análisis Sintetizado — Ticket #0027698 (Alta complejidad)

**Consenso entre las 3 perspectivas (alta confianza):**
- La causa raíz es CLIENTE_ID nullable en RSTRP_PEDIDOS ← las 3 perspectivas lo detectaron
- El fix debe incluir validación en la capa DAL ← consenso DAL + BLL perspectives

**Solo detectado por 1 perspectiva (validar antes de implementar):**
- Perspectiva 3 detectó posible problema en el WebService_Pedidos.asmx que consume
  GetPedidoDetalle — las otras 2 no lo mencionaron. Verificar si aplica.

**Contradicción entre perspectivas:**
- Perspectiva 1: recomienda fix en DAL_Pedidos.cs
- Perspectiva 2: recomienda fix en BLL_Pedidos.cs (y dejar DAL sin cambios)
- Síntesis: fix en ambas capas por defensa en profundidad
```

#### Configuración

```json
"multi_agent_deliberation": {
  "enabled": true,
  "complexity_threshold": "complejo",
  "perspectives": 3,
  "perspective_timeout_minutes": 45,
  "synthesis_timeout_minutes": 20
}
```

**Costo IA (si se usa Claude API en G-01):** ~3x el costo de un ticket normal para
tickets complejos. Con scoring de complejidad (M-07), solo el ~15-20% de tickets
activa esto. ROI positivo si mejora la tasa de QA en primer intento en tickets complejos.

**Archivos nuevos:** `multi_agent_deliberator.py`, `synthesizer.py`  
**Archivos a modificar:** `daemon.py`, `prompt_builder.py`  
**Esfuerzo:** Alto (4-6 días)  
**Impacto:** Transformador — los tickets más difíciles (los que más cuestan) se
analizan con la mayor profundidad posible. Reduce drásticamente los falsos análisis
en problemas complejos.

---

### `[x]` G-09 · Modo Autonomía Total con Approval Gates

**El problema de fondo:** Stacky requiere supervisión constante. El daemon corre y
procesa tickets, pero el usuario tiene que revisar cada resultado, decidir si relanzar,
revisar el dashboard. Para volúmenes altos o durante la noche, el pipeline se detiene
esperando atención humana.

**El cambio:** Un modo de operación completamente autónomo donde Stacky toma todas
las decisiones dentro de parámetros definidos, y solo pausa en "approval gates"
configurables cuando hay ambigüedad o riesgo alto.

#### Árbol de decisiones autónomas

```
Ticket nuevo detectado
  ↓
¿Pre-filtro lo descarta? (E-05)
  → SI: auto-comentar en Mantis + continuar → (autónomo)
  → NO: continuar pipeline

PM completa análisis
  ↓
¿Validación de output pasa? (M-02)
  → SI: lanzar DEV automáticamente → (autónomo)
  → NO: retry con contexto → si sigue fallando: GATE 1 (pausa, notificar)

Blast Radius calculado (G-05)
  ↓
¿Risk score > CRÍTICO?
  → NO: lanzar DEV automáticamente → (autónomo)
  → SI: GATE 2 (pausa, mostrar mapa de impacto, pedir aprobación)

DEV completa
  ↓
Tests automáticos (G-04)
  ↓
¿Tests pasan?
  → SI: lanzar QA automáticamente → (autónomo)
  → NO si son tests nuevos desactualizados: GATE 3 (pedir decisión humana)
  → NO si hay regresiones reales: GATE 4 (bloquear, notificar urgente)

QA completa
  ↓
¿Veredicto APROBADO?
  → SI: auto-actualizar Mantis (E-02) + commitear → GATE 5 (opcional, si se quiere)
  → SI con observaciones menores: rework automático (M-01) → (autónomo)
  → NO: GATE 6 (intervención humana requerida)
```

#### Configuración de gates

```json
"autonomy": {
  "mode": "full",
  "gates": {
    "high_blast_radius": true,       ← pausa si muchos dependientes
    "test_failures": true,           ← pausa si tests fallan
    "consecutive_retries": true,     ← pausa tras N reintentos
    "before_commit": false,          ← NO pausar antes de commitear (confía en QA)
    "new_project_first_ticket": true ← siempre pausa el primer ticket de un proyecto nuevo
  },
  "auto_commit": false,              ← no commitear automáticamente (requiere humano)
  "notify_on_gate": ["slack", "toast"],
  "resume_timeout_hours": 8          ← si nadie aprueba en 8h, escalar notificación
}
```

#### Dashboard en modo autónomo

```
STACKY — Modo Autónomo Activo
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Procesados hoy: 7 tickets  |  En cola: 3  |  Gates abiertos: 1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏸ GATE ABIERTO — Ticket #0027732
   Motivo: Blast Radius crítico (9 dependientes de alto riesgo)
   Esperando aprobación desde hace 23 minutos
   [ APROBAR Y CONTINUAR ]  [ VER MAPA DE IMPACTO ]  [ DESCARTAR TICKET ]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ #0027698  PM→DEV→QA  Completado 14:32  (sin intervención)
✅ #0027446  PM→DEV→QA  Completado 16:15  (sin intervención)
⚙ #0027701  DEV en proceso  Iniciado 16:47  (auto-lanzado)
```

**Archivos nuevos:** `autonomy_controller.py`, `gate_manager.py`  
**Archivos a modificar:** `daemon.py`, `dashboard.html`, `dashboard_server.py`  
**Esfuerzo:** Alto (5-7 días — requiere que G-04 y G-05 estén implementados)  
**Impacto:** Transformador — Stacky puede procesar tickets durante la noche o mientras
el dev hace otra cosa. El output del día siguiente: 8 tickets con análisis completo,
code implementado, QA validado, listos para revisión humana final.

---

### `[x]` G-10 · Capa de Inteligencia Predictiva

**El problema de fondo:** Stacky reacciona. Un ticket llega, se procesa. Nadie
sabe de antemano cuánto va a tardar, si va a necesitar rework, si va a tocar módulos
conflictivos, o si hay algo en la descripción que indique un problema más profundo.
Cada ticket es una caja negra hasta que termina.

**El cambio:** Un modelo predictivo entrenado sobre el historial de tickets de Stacky
que, antes de que PM empiece, genera predicciones accionables sobre el ticket.

#### Qué se predice

```python
# predictor.py

class TicketPredictor:
    def predict(self, inc_content: str, project: str) -> PredictionReport:
        # Usando historial de N tickets anteriores como features:
        return {
            "complexity_class": "complejo",       # simple/medio/complejo
            "confidence": 0.82,
            
            "estimated_pm_minutes": 52,            # basado en similares
            "estimated_dev_minutes": 95,
            "estimated_qa_minutes": 35,
            
            "rework_probability": 0.31,            # 31% chance de QA→DEV rework
            "rework_reason_prediction": "validación de edge case en BatchProcesar",
            
            "modules_likely_affected": [
                {"module": "DAL_Pedidos.cs", "probability": 0.89},
                {"module": "FrmPedidos.aspx.cs", "probability": 0.76},
                {"module": "BLL_Pedidos.cs", "probability": 0.45}
            ],
            
            "similar_tickets": [
                {"id": "0027698", "similarity": 0.91, "outcome": "success_first_attempt"},
                {"id": "0026541", "similarity": 0.84, "outcome": "rework_once"}
            ],
            
            "risk_flags": [
                "Módulo FrmPedidos.aspx.cs tuvo 8 cambios este mes — riesgo de conflicto",
                "Descripción menciona 'todos los registros' — potencial performance issue"
            ],
            
            "recommended_timeout_pm": 65,          # ajusta el config default de 60
            "trigger_multi_agent": True            # recomienda G-08 para este ticket
        }
```

#### Implementación técnica (100% local, sin LLM)

```python
# El modelo usa ML clásico — no requiere IA para inferencia, es barato y rápido

# Features extraídas de INC-{id}.md:
# - longitud descripción, cantidad de pasos, número de adjuntos
# - keywords de severidad, módulos mencionados, tipo de error
# - hora del día, día de semana (patrones de urgencia)
# - historial del reporter (¿escala frecuentemente?)

# Modelo: gradient boosting (sklearn) o simple kNN sobre embedding TF-IDF
# Entrenamiento: automático con cada ticket completado
# Reentrenamiento: cada 10 tickets nuevos completados
# Tamaño del modelo: <10MB, inferencia en <100ms

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.pipeline import Pipeline
import joblib

model = Pipeline([
    ('features', TicketFeatureExtractor()),
    ('classifier', GradientBoostingClassifier(n_estimators=100))
])

# Se entrena con historial de tickets completados
# labels: complexity_class, rework_happened, modules_touched, actual_duration
```

#### Panel de predicciones en el dashboard

```
TICKET #0027732 — Predicción antes de procesar
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Complejidad estimada:    🔴 COMPLEJO (82% confianza)
Tiempo total estimado:   3h 2m (PM: 52m + DEV: 95m + QA: 35m)
Probabilidad de rework:  31%
Módulos probables:       DAL_Pedidos.cs (89%) · FrmPedidos.aspx.cs (76%)
Ticket más similar:      #0027698 (91% similar, resuelto exitosamente)

⚠️ Alertas predictivas:
  - FrmPedidos tuvo 8 cambios este mes — riesgo de conflicto SVN
  - "todos los registros" sugiere problema de performance — ampliar análisis

Recomendaciones automáticas:
  ✓ Activar deliberación multi-agente (G-08)
  ✓ Aumentar timeout PM a 65 minutos
  ✓ Notificar al equipo antes de empezar (impacto estimado alto)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ PROCESAR CON RECOMENDACIONES ]  [ AJUSTAR MANUALMENTE ]
```

#### El loop de mejora continua

```
Ticket procesado → resultado real guardado → compara con predicción
→ si predicción fue correcta: aumenta peso de esos features
→ si fue incorrecta: ajusta modelo
→ cada 10 tickets: reentrenamiento completo automático
→ métricas de accuracy del predictor visibles en N-08 (métricas)
```

**Dependencias nuevas:** `scikit-learn`, `joblib`  
**Archivos nuevos:** `predictor.py`, `feature_extractor.py`, `model_trainer.py`  
**Archivos a modificar:** `daemon.py`, `dashboard.html`, `dashboard_server.py`  
**Esfuerzo:** Alto (5-7 días — el modelo se entrena solo pero la infraestructura es compleja)  
**Impacto:** Transformador — Stacky deja de ser reactivo y se vuelve anticipatorio.
Cada ticket llega con un plan de acción recomendado basado en evidencia histórica.
Con suficiente historial (100+ tickets), las predicciones son lo suficientemente
precisas para activar automáticamente configuraciones especiales sin intervención humana.

---

## PARTE 5 — Proximas 10 Mejoras: Eficiencia Exponencial y Escalamiento

Estas mejoras atacan los cuellos de botella que emergen una vez que las 36 anteriores
estan operativas. El foco es: cero friccion operativa, escalamiento a multiples proyectos
y equipos, y conversion de Stacky en infraestructura de ingenieria compartida.

### Indice rapido — Parte 5

- `[x]` **X-01** · Pipeline CI/CD con SVN Hooks · Prioridad alta ✓
- `[x]` **X-02** · Modo Multi-Tenant: Multiples Proyectos y Equipos en Paralelo · Prioridad alta ✓
- `[x]` **X-03** · Generacion y Ejecucion de Migration Scripts Oracle · Prioridad alta ✓
- `[x]` **X-04** · Auto-Generacion de Tests Unitarios para el Fix · Prioridad alta ✓
- `[x]` **X-05** · Modo Live Pair: Stacky como Copiloto en Tiempo Real · Prioridad media ✓
- `[-]` **X-06** · Reporte Ejecutivo Automatico Semanal · **CANCELADO** (removido por decision de equipo)
- `[x]` **X-07** · Indice de Deuda Tecnica con Priorizacion Automatica · Prioridad media ✓
- `[x]` **X-08** · Plugin de Integracion para VS Code / Visual Studio · Prioridad alta ✓
- `[x]` **X-09** · Modo Turbo: Pre-Procesamiento Especulativo de Tickets · Prioridad alta ✓
- `[x]` **X-10** · Stacky como MCP Server (Model Context Protocol) · Prioridad maxima ✓

### Parte 6 — Precisión Quirúrgica: Bug Localization Pre-PM
- `[x]` **S-01** · Parser de Stack Traces .NET → Archivo/Método exacto · Prioridad 1 ✓
- `[x]` **S-02** · Reverse Lookup de Mensajes RIDIOMA → Constante → Método · Prioridad 2 ✓
- `[x]` **S-03** · Entry Point Resolver: Form ASPX / Batch Job → Handler inicial · Prioridad 3 ✓
- `[x]` **S-04** · Bug Localizer: Orquestador que genera BUG_LOCALIZATION.md · Prioridad 4 ✓
- `[x]` **S-05** · Inyección de BUG_LOCALIZATION.md en prompts PM y DEV · Prioridad 5 ✓
- `[x]` **S-06** · Protocolo Fix Quirúrgico en prompt DEV (declarar scope mínimo) · Prioridad 6 ✓
- `[x]` **S-07** · Prompt PM: bajar ARQUITECTURA_SOLUCION a nivel de método · Prioridad 7 ✓

### Parte 7 — Paradigm Shift: Ciclos Infinitos, PM Inteligente y Nuevos Integrantes
- `[x]` **P0** · Fix crítico: cablear rework M-01 en pipeline_runner · BLOQUEANTE ✓
- `[x]` **Y-01** · Full Pipeline Reset Loop con Correcciones Infinitas · Prioridad 1 (CRÍTICO) ✓
- `[x]` **Y-02** · PM Pre-Warming: arranque sin cold start · Prioridad 2 ✓
- `[x]` **Y-03** · Subsystem Classifier: Batch / OnLine / BD / Integración · Prioridad 3 ✓
- `[x]` **Y-04** · Nuevo Agente — DBA Especialista · Prioridad 4 ✓
- `[x]` **Y-05** · Nuevo Agente — Tech Lead Reviewer · Prioridad 5 ✓
- `[x]` **Y-06** · Slack/Teams Integration Hub + Alertas Inteligentes · Prioridad 6 ✓
- `[x]` **Y-07** · Stats Dashboard Operacional + Ejecutivo · Prioridad 7 ✓

### Parte 8 — Secuencialidad y Anti-Duplicación del Pipeline (Correcciones Estructurales)
- `[x]` **SEQ-01** · Deshabilitar `pipeline_runner.py` CLI en producción · Prioridad 1 (CRÍTICO) ✓
- `[x]` **SEQ-02** · Lock global por ticket en memoria (`threading.Lock`) · Prioridad 2 ✓
- `[x]` **SEQ-03** · Deshabilitar `_STUCK_COMPLETADO` auto-launch · Prioridad 3 ✓
- `[x]` **SEQ-04** · `api_set_state` limpia EN_CURSO + cooldown 30 s en watcher · Prioridad 4 ✓
- `[x]` **SEQ-05** · Reset borra archivos de análisis del ticket · Prioridad 5 ✓
- `[x]` **SEQ-06** · `api_set_state` no activa auto_advance automáticamente · Prioridad 6 ✓
- `[x]` **SEQ-07** · Unificar punto de entrada — solo `_invoke_stage` del dashboard · Prioridad 7 ✓
- `[x]` **SEQ-08** · Mutex inter-proceso via lockfile para CLI + dashboard · Prioridad 8 ✓
- `[x]` **SEQ-09** · `state.json` con campo `invoking_pid` + TTL · Prioridad 9 ✓
- `[x]` **SEQ-10** · Validar estado antes de escribir `auto_advance=True` · Prioridad 10 ✓
- `[x]` **SEQ-11** · Log estructurado de invocaciones con correlation ID · Prioridad 11 ✓
- `[x]` **SEQ-12** · PM fallback "sin placeholders" deshabilitado · Prioridad 12 ✓

---

### `[x]` X-01 · Pipeline CI/CD Integrado con SVN Hooks

**Concepto:** Conectar Stacky directamente al sistema de commits SVN via hooks
`post-commit` y `pre-commit`. Cuando un developer hace commit, Stacky valida
automaticamente que el cambio corresponde a un ticket procesado y aprobado por QA.

Flujo del hook:
- `post-commit` verifica que los archivos del commit coincidan con `SVN_CHANGES.md` de algun ticket QA-aprobado
- `post-commit` registra el commit en el historial de Stacky y notifica al equipo
- `pre-commit` puede bloquear commits sobre archivos con blast radius critico (G-05) sin ticket Stacky aprobado

Esto cierra el ciclo entre el pipeline y el repositorio. El codigo que entra al trunk
queda auditado con evidencia de analisis IA + QA aprobado. Escalable a todos los
developers del equipo sin que cambien su workflow: el hook corre en el server SVN.

**Archivos nuevos:** `svn_hooks/post-commit`, `svn_hooks/pre-commit`, `hook_validator.py`
**Archivos a modificar:** `dashboard_server.py` (endpoint de validacion para hooks)
**Dependencias:** Acceso de escritura al repo SVN para instalar hooks
**Esfuerzo:** Medio (2-3 dias) | **Impacto:** Transformador para equipos

---

### `[x]` X-02 · Modo Multi-Tenant: Multiples Proyectos y Equipos en Paralelo

**Concepto:** Stacky actual asume un solo daemon por proyecto. X-02 introduce un
orquestador central que gestiona multiples proyectos simultaneamente con recursos
compartidos: pool de agentes, indice vectorial federado, metricas unificadas.

```
STACKY ORCHESTRATOR
  Proyecto RIPLEY    -> daemon_ripley (3 tickets activos)
  Proyecto RSMOBILE  -> daemon_rsmobile (1 ticket activo)
  Proyecto RSLOGIS   -> daemon_rslogis (idle)

  Pool de agentes compartido: 3 slots PM, 2 slots DEV, 2 slots QA
  Cola global con priorizacion cross-proyecto
  Dashboard unificado: vista de todos los proyectos
```

Con un pool compartido, si RIPLEY no esta usando DEV, RSMOBILE puede usarlo sin
esperar. El total de tickets/hora del sistema sube sin agregar hardware ni licencias.
El costo marginal de agregar un proyecto nuevo es casi cero.

**Archivos nuevos:** `orchestrator.py`, `agent_pool.py`, `global_queue.py`
**Archivos a modificar:** `daemon.py`, `dashboard.html`, `config.json` schema
**Esfuerzo:** Alto (5-7 dias) | **Impacto:** Transformador para escalamiento organizacional

---

### `[x]` X-03 · Generacion y Ejecucion de Migration Scripts Oracle

**Concepto:** Cuando DEV detecta que el fix requiere cambios en el schema Oracle
(nueva columna, indice, constraint, secuencia, insert en tabla de mensajes), en lugar
de documentarlo en `TAREAS_DESARROLLO.md`, genera directamente el script SQL versionado
y lo valida contra el schema real (G-03) antes de presentarlo.

El script incluye automaticamente: versionado por ticket, rollback script complementario,
verificacion de que columnas/tablas existen antes de aplicar, y un modo dry-run
que valida sin ejecutar nada. Desde el dashboard se puede ejecutar el script con
un click, con confirmacion previa y log del resultado.

**Por que es exponencial:** Elimina la categoria entera de "DEV documento el cambio
de DB pero nadie lo aplico en QA/staging". La migracion es ejecutable directamente
desde Stacky con trazabilidad completa.

**Archivos nuevos:** `migration_generator.py`, `migrations/`
**Archivos a modificar:** `prompt_builder.py`, `dashboard_server.py`
**Esfuerzo:** Medio (2-3 dias) | **Impacto:** Muy alto

---

### `[x]` X-04 · Auto-Generacion de Tests Unitarios para el Fix

**Concepto:** Despues de que DEV completa la implementacion, antes de invocar QA,
un agente especializado (Claude API) genera tests unitarios para el codigo nuevo.
Los tests cubren: el caso feliz del fix, el caso que generaba el bug original, y
al menos un edge case identificado en el analisis PM.

QA recibe los tests generados como parte de su prompt y valida que representan
correctamente el comportamiento esperado antes de aprobar el ticket. Los tests
aprobados se agregan al proyecto de tests existente automaticamente.

**Por que es exponencial:** Cada ticket completado aumenta la cobertura de tests
del proyecto. Despues de 50 tickets, hay un suite de tests vivo que cubre los
bugs mas frecuentes del sistema. El costo de regresiones cae exponencialmente.

**Archivos nuevos:** `test_generator.py`
**Archivos a modificar:** `pipeline_watcher.py`, `prompt_builder.py`
**Dependencias:** `anthropic` SDK
**Esfuerzo:** Medio-Alto (3-4 dias) | **Impacto:** Muy alto (mejora acumulativa)

---

### `[x]` X-05 · Modo Live Pair: Stacky como Copiloto en Tiempo Real

**Concepto:** Un modo de operacion donde Stacky no espera a que el developer termine
de trabajar, sino que lo asiste activamente mientras edita codigo. Un watcher de
archivos detecta cuando el developer abre un archivo relacionado con un ticket activo
y muestra contexto instantaneo en un panel lateral del dashboard.

El panel muestra: contexto relevante del analisis PM, advertencias del blast radius
para ese archivo especifico, patrones probados para el tipo de problema, y un countdown
del timeout actual. Se actualiza en tiempo real mientras el developer navega archivos.
No interrumpe: esta disponible cuando el developer lo quiere consultar.

**Por que es exponencial:** Reduce el tiempo de "buscar contexto" a cero. El developer
nunca tiene que saltar entre Mantis, el dashboard de Stacky y el codigo — todo
el contexto relevante aparece al lado del archivo que esta editando.

**Archivos nuevos:** `live_pair_watcher.py`, `context_panel_server.py`
**Archivos a modificar:** `dashboard.html`, `knowledge_base.py`
**Esfuerzo:** Medio (2-3 dias) | **Impacto:** Alto (experiencia de developer)

---

### `[-]` X-06 · Reporte Ejecutivo Automatico Semanal — **CANCELADO**

> **Removido por decision del equipo.** El archivo `weekly_reporter.py` fue eliminado.
> No usar Claude API directamente — toda generacion de contenido va por el bridge
> VS Code Copilot (puerto 5051).

---

### `[x]` X-07 · Indice de Deuda Tecnica con Priorizacion Automatica

**Concepto:** Stacky analiza el historial de tickets y construye un indice cuantificado
de deuda tecnica, con priorizacion basada en impacto real: cuantos tickets requirieron
tocar cada modulo, cuantos reworks ocurrieron por su causa, cuanto tiempo promedio
toma cada fix en ese modulo, cuantos bugs recurrentes tiene el area.

El indice se muestra en el dashboard como un mapa de calor del codebase. Los modulos
con mayor deuda tecnica se destacan visualmente. Stacky puede sugerir automaticamente
crear un ticket de refactorizacion cuando un modulo supera el umbral de deuda configurado.

Ademas detecta patrones de deuda sistemica: "8 tickets en distintos modulos son
null checks faltantes -> recomendacion: agregar analisis estatico de null-safety al pipeline CI".

**Por que es exponencial:** Convierte datos de operacion en decisiones de arquitectura.
El equipo deja de debatir "que refactorizar" con intuicion y pasa a tener evidencia
cuantitativa de donde esta el mayor retorno de inversion en mejora de codigo.

**Archivos nuevos:** `tech_debt_analyzer.py`, `debt_heatmap.js`
**Archivos a modificar:** `dashboard.html`, `metrics_collector.py`
**Esfuerzo:** Medio (2-3 dias) | **Impacto:** Muy alto (mejora sistemica del codebase)

---

### `[x]` X-08 · Plugin de Integracion para VS Code

**Concepto:** Una extension VS Code que integra Stacky directamente en el IDE. El
developer ve el contexto del ticket activo, el estado del pipeline, y puede ejecutar
acciones sin salir del editor. El panel lateral muestra: ticket activo con countdown
de timeout, botones de accion rapida (marcar DEV completado, pedir mas contexto,
pausar pipeline), y el proximo ticket en cola.

La extension tambien puede: mostrar decoraciones inline en archivos con advertencias
de blast radius, auto-abrir `ARQUITECTURA_SOLUCION.md` cuando el developer empieza
a trabajar en un ticket, y mostrar el countdown del timeout en la barra de estado de VS Code.

**Por que es exponencial:** Elimina el cambio de contexto entre VS Code y el dashboard.
El developer vive en el IDE — Stacky va donde esta el developer, no al reves.
Con multiples developers en el equipo, cada uno ve solo su contexto sin ruido de los demas.

**Archivos nuevos:** `vscode_extension/` (TypeScript + VS Code Extension API)
**Archivos a modificar:** `dashboard_server.py` (endpoints de polling para la extension)
**Esfuerzo:** Alto (4-6 dias — requiere TypeScript + VS Code Extension API)
**Impacto:** Transformador para adopcion en equipo

---

### `[x]` X-09 · Modo Turbo: Pre-Procesamiento Especulativo de Tickets

**Concepto:** En lugar de esperar a que un developer tome un ticket para empezar a
procesarlo, Stacky inicia el analisis PM de forma especulativa en los tickets con
mayor probabilidad de ser los proximos en trabajarse (segun el predictor G-10 y
la prioridad de la cola).

Cuando el developer termina el ticket actual y toma el siguiente, `ANALISIS_TECNICO.md`
ya esta listo. El developer empieza directo en DEV, sin esperar a PM. Ahorro estimado:
35-60 minutos por ticket en proyectos activos.

Si el ticket especulativo no es tomado (cambio de prioridades), el analisis PM se
archiva en cache con TTL configurable. Si el ticket recibe nuevas notas en Mantis
antes de ser tomado, el analisis se invalida automaticamente y se regenera.

**Por que es exponencial:** Con un queue de 5+ tickets, el tiempo de espera de PM
es siempre cero. En equipos con multiples developers, el throughput total se multiplica
porque los analisis PM de todos los tickets proximos se preparan en paralelo.

**Archivos nuevos:** `speculative_processor.py`, `pm_cache.py`
**Archivos a modificar:** `daemon.py`, `ticket_detector.py`
**Esfuerzo:** Medio-Alto (3-4 dias) | **Impacto:** Muy alto en equipos de 2+ developers

---

### `[x]` X-10 · Stacky como MCP Server (Model Context Protocol)

**Concepto:** Exponer todo el conocimiento de Stacky como un servidor MCP estandar.
Cualquier cliente MCP compatible (Claude Desktop, VS Code Copilot, Cursor, o cualquier
herramienta IA futura) puede consultar el estado del pipeline, el historial de tickets,
el indice vectorial del codebase, y la memoria de agentes directamente desde su
interfaz de chat nativa — sin integracion especifica por herramienta.

Las herramientas MCP expuestas incluyen: `get_ticket_analysis`, `search_codebase`,
`get_agent_memory`, `get_pipeline_status`, `get_oracle_schema`, `get_blast_radius`,
`list_similar_tickets`. Con esto, desde Claude Desktop el developer puede preguntar
"como se implemento el fix del ticket 27698?" y recibir directamente los artefactos
de Stacky. O pedir "busca en el codebase como se usa Error.Agregar" y recibir ejemplos
reales del trunk en segundos.

**Por que es exponencial:** Stacky deja de ser una herramienta aislada y se convierte
en contexto universal para cualquier herramienta IA del equipo. El conocimiento
acumulado por Stacky (memoria, patrones, historial, indice vectorial) es accesible
desde Claude Desktop, Cursor, VS Code Copilot, o cualquier cliente MCP futuro.
Multiplica el ROI de cada mejora anterior: G-02, G-06, E-01, N-06 se vuelven
consultables desde cualquier contexto sin friccion.

**Archivos nuevos:** `stacky_mcp_server.py`, `mcp_tools.py`
**Dependencias nuevas:** `mcp` (Python SDK del protocolo MCP)
**Archivos a modificar:** `dashboard_server.py` (modo de arranque adicional)
**Esfuerzo:** Medio (2-3 dias — el protocolo MCP es simple una vez que los datos existen)
**Impacto:** Transformador — hace que todo el conocimiento de Stacky sea consumible
por el ecosistema completo de herramientas IA del equipo.

---

## Tabla de Priorizacion Global — Parte 5

| ID | Nombre | Esfuerzo | Impacto | Depende de |
|----|--------|----------|---------|------------|
| **X-06** | Reporte Ejecutivo Semanal | Bajo | Alto | N-08 |
| **X-05** | Live Pair Copiloto | Medio | Alto | G-06, G-05 |
| **X-03** | Migration Scripts Oracle | Medio | Muy alto | G-03 |
| **X-07** | Indice de Deuda Tecnica | Medio | Muy alto | N-08, E-01 |
| **X-10** | Stacky como MCP Server | Medio | Transformador | G-02, G-06 |
| **X-04** | Auto-Generacion de Tests | Medio-Alto | Muy alto | G-01, G-03 |
| **X-09** | Modo Turbo Pre-procesamiento | Medio-Alto | Muy alto | G-10, M-06 |
| **X-01** | CI/CD con SVN Hooks | Medio | Transformador (equipo) | M-04, G-05 |
| **X-02** | Multi-Tenant Multi-Proyecto | Alto | Transformador | E-11, M-06 |
| **X-08** | Plugin VS Code | Alto | Transformador (adopcion) | E-10, G-07 |

---

## PARTE 7 — Paradigm Shift: Ciclos Infinitos, PM Inteligente y Nuevos Integrantes

El foco de esta parte es convertir Stacky de una herramienta de automatización a un
sistema que aprende, se corrige solo indefinidamente, y agrega nuevos especialistas al
pipeline — cambiando el paradigma de cómo el equipo resuelve tickets.

> **Bug crítico a resolver primero (P0):** ~~M-01 (rework QA→DEV) tiene los estados
> definidos en `pipeline_state.py` pero `pipeline_runner.py` jamás los activa.
> El rework actualmente no funciona. Y-01 depende de corregir esto primero.~~
> **[RESUELTO 2026-04-15]** `pipeline_runner.py` ahora consume los estados `qa_rework`,
> `dev_rework_en_proceso`, `dev_rework_completado`. Se agregó `_parse_qa_issues()`,
> bloque M-01 en `_auto_advance()`, manejo de `qa_rework`/`dev_rework_completado` en
> `process_ticket()`, y `pipeline.max_rework_cycles` en `config.json`.

### Índice rápido — Parte 7

- `[x]` **Y-01** · Full Pipeline Reset Loop con Correcciones Infinitas · Prioridad 1 (CRÍTICO) ✓
- `[x]` **Y-02** · PM Pre-Warming: arranque sin cold start · Prioridad 2 ✓
- `[x]` **Y-03** · Subsystem Classifier: Batch / OnLine / BD / Integración · Prioridad 3 ✓
- `[x]` **Y-04** · Nuevo Agente — DBA Especialista · Prioridad 4 ✓
- `[x]` **Y-05** · Nuevo Agente — Tech Lead Reviewer · Prioridad 5 ✓
- `[x]` **Y-06** · Slack/Teams Integration Hub + Alertas Inteligentes · Prioridad 6 ✓
- `[x]` **Y-07** · Stats Dashboard Operacional + Ejecutivo · Prioridad 7 ✓

---

### `[x]` Y-01 · Full Pipeline Reset Loop con Correcciones Infinitas y Memoria Progresiva

**Problema:** Hoy el rework no funciona en absoluto (BUG: estados definidos pero nunca
activados en `pipeline_runner.py`). Incluso si funcionara, M-01 limita a 1 ciclo y solo
reenvía a DEV. Vos querés que cada corrección reinicie desde PM con todo el contexto
acumulado de ciclos anteriores, sin límite de iteraciones.

**Solución:**

```
QA rechaza → correcion_memory guarda todos los issues → PM revision (contexto acumulado)
           → DEV → QA → [loop indefinido hasta APROBADO]
```

Cada ciclo, PM recibe el historial completo de todos los rechazos anteriores acumulados
(no solo el último), de modo que no repite los mismos errores. La memoria de correcciones
es progresiva: si el ciclo 3 levanta los mismos issues que el ciclo 1, el contexto de
ciclo 4 los resalta explícitamente como "problema recurrente — prestar especial atención".

**Stagnation Detection:** Si en 3 ciclos consecutivos la lista de issues no se achica,
Stacky pausa el ticket, notifica al humano con un diagnóstico de estancamiento, y sugiere
intervención manual. Esto evita loops infinitos sin progreso.

**Efficiency Score por ciclo:** Al iniciar cada ciclo, se calcula si la cantidad de
issues abiertos disminuyó respecto al ciclo anterior. Se loguea en métricas (Y-07).

**Fix P0 requerido:** Cablear `pipeline_runner.py` para consumir los estados de rework
ya definidos en `pipeline_state.py` (`qa_rework`, `dev_rework_en_proceso`, etc.).

**Archivos nuevos:** `correction_memory.py`
**Archivos a modificar:** `pipeline_runner.py` (cablear M-01 + loop Y-01),
`pipeline_state.py` (nuevos estados `pm_revision`, `stagnation_detected`),
`prompt_builder.py` (build_pm_revision_prompt con historial acumulado),
`pipeline_runner.py` (stagnation check tras cada ciclo)
**Esfuerzo:** Medio (2-3 días) | **Impacto:** Transformador — elimina la necesidad de
intervención humana para reiniciar tickets que fallaron

---

### `[ ]` Y-02 · PM Pre-Warming: Arranque sin Cold Start

**Problema:** Cada vez que PM arranca sobre un ticket, re-descubre el codebase, las
convenciones del proyecto, los patrones de solución y dónde está el bug — aunque ya
existen 6 módulos de Stacky que tienen esa información lista. El PM "arranca frío"
cuando podría arrancar ya informado.

**Solución:** Un paso de pre-enriquecimiento que se ejecuta antes de invocar al agente
PM, inyectando al inicio del prompt todo lo que ya se sabe:

| Fuente | Info inyectada |
|--------|----------------|
| G-06 Agent Memory | Convenciones y gotchas del codebase ya aprendidos |
| E-01 Knowledge Base | Top-3 tickets similares ya resueltos con su solución |
| Y-03 Subsystem Classifier | "Este ticket es Batch/OnLine/BD" |
| S-04 BUG_LOCALIZATION | Entry point exacto + método más probable del bug |
| N-06 Pattern Extractor | Patrón de fix más similar si existe |

PM arranca con toda esa información en la primera línea del contexto, sin buscar nada.
El tiempo de análisis PM baja significativamente porque ya sabe dónde mirar.

**Archivos a modificar:** `prompt_builder.py` (nueva función `build_pm_prewarming_section`
que agrega un bloque "## Contexto pre-cargado" al inicio del pm_prompt),
`pipeline_runner.py` (invocar pre-warming antes del stage PM)
**Esfuerzo:** Bajo (1 día) | **Impacto:** Alto — reduce tiempo de análisis PM 40-60%

---

### `[ ]` Y-03 · Subsystem Classifier: Batch / OnLine / BD / Integración

**Problema:** El PM no sabe en qué capa del sistema está el bug. Esto genera análisis
genéricos que dicen "revisar el código" sin precisar si ir a `OnLine/AgendaWeb/`,
`Batch/`, `BD/`, o una integración externa. Es también la raíz del "no elige bien
qué proyecto tocar" dentro del codebase.

**Solución:** Clasificador local (sin IA, puro Python) que analiza el texto del ticket
antes de PM y determina el subsistema destino:

| Señal en el ticket | Subsistema |
|---|---|
| `.aspx`, `Frm`, URL `/AgendaWeb/`, `btnXxx_Click`, "pantalla", "grilla" | `OnLine/AgendaWeb` |
| "servicio", "tarea programada", "job", "proceso batch", `.exe`, "Windows Service" | `Batch/` |
| `SP_`, `RST_`, `RPL_`, `INSERT`, `UPDATE`, "migration", "tabla", "columna" | `BD/` |
| GENESYS, SFTP, webservice, "integración", "middleware", "API" | `Integracion/` |
| Ambiguo / múltiples señales | `mix` → listar todas las señales encontradas |

El resultado es una única línea inyectada al inicio del prompt PM:
```
SUBSISTEMA DETECTADO: OnLine/AgendaWeb (confianza: alta — señales: FrmDetalleClie, btnGuardar)
```

Con esto PM ya sabe exactamente dónde buscar sin analizar el codebase desde cero.

**Archivos nuevos:** `subsystem_classifier.py`
**Archivos a modificar:** `prompt_builder.py` (inyectar resultado en pm_prompt),
`pipeline_runner.py` (invocar antes de PM), `ticket_classifier.py` (agregar campo
`subsystem` al `TicketScore`)
**Esfuerzo:** Bajo (0.5 días) | **Impacto:** Alto — elimina una fuente de error
frecuente en análisis PM

---

### `[x]` Y-04 · Nuevo Agente — DBA Especialista ✓

**Concepto:** Cuando el ticket tiene alta carga Oracle (score SQL > 40% según
`ticket_classifier`), se inserta un nuevo stage entre PM y DEV: el **DBA Agent**.

```
PM → [si Oracle-heavy] → DBA → DEV → QA
```

El DBA Agent recibe el análisis de PM y genera:
- `DB_SOLUTION.sql` — script Oracle completo (DDL/DML/INSERT RIDIOMA/secuencias/índices)
- Validado contra ALL_TAB_COLUMNS vía G-03 antes de entregárselo a DEV
- Incluye rollback script y verificaciones pre-ejecución
- `DB_READY.flag` como señal de completitud

DEV recibe `DB_SOLUTION.sql` listo y solo conecta el C# — nunca más DEV piensa
en estructura de tablas, constraints o mensajes RIDIOMA durante la implementación.

**Por qué cambia el paradigma:** Elimina el 80% de los errores DEV relacionados con
Oracle. El developer se convierte en un integrador de lógica, no en un DBA.

**Agente VS Code a usar:** A determinar — puede ser el mismo DevStack3 con un prompt
especializado, o un agente dedicado `DBA-RIPLEY`.

**Archivos nuevos:** `dba_agent.py`
**Archivos a modificar:** `pipeline_runner.py` (stage condicional post-PM),
`pipeline_state.py` (estados `dba_en_proceso`, `dba_completado`, `error_dba`),
`prompt_builder.py` (`build_dba_prompt`), `projects/RIPLEY/config.json`
(activar el stage DBA y definir umbrales)
**Esfuerzo:** Medio (2 días) | **Impacto:** Muy alto — especialización real del pipeline

---

### `[x]` Y-05 · Nuevo Agente — Tech Lead Reviewer ✓

**Concepto:** Para tickets complejos (score > 12), se inserta un **Tech Lead Reviewer**
entre PM y DEV que revisa `ARQUITECTURA_SOLUCION.md` antes de que DEV arranque.

```
PM → [si complejo] → TechLead Review → [aprueba?] → DEV → QA
                                      → [rechaza]  → PM revision (Y-01)
```

El Tech Lead puede:
- **Aprobar** → escribe `TL_APPROVED.flag` → DEV procede
- **Rechazar con comentarios** → escribe `TL_REJECTED.md` → vuelve a PM directamente
  sin pasar por DEV+QA (evita el ciclo costoso)

**Por qué importa:** Un ciclo PM→DEV→QA fallido son ~3 horas. El Tech Lead lo corta
en ~20 minutos. En tickets complejos con arquitectura errónea, el ROI es inmediato.

**Archivos nuevos:** `tech_lead_reviewer.py`
**Archivos a modificar:** `pipeline_runner.py` (stage condicional post-PM para complejo),
`pipeline_state.py` (estados `tl_review_en_proceso`, `tl_aprobado`, `tl_rechazado`),
`prompt_builder.py` (`build_tl_prompt`), `projects/RIPLEY/config.json`
**Esfuerzo:** Medio (1.5 días) | **Impacto:** Alto — evita ciclos costosos en tickets complejos

---

### `[x]` Y-06 · Slack/Teams Integration Hub + Alertas Inteligentes ✓

**Problema:** N-09 ya envía notificaciones básicas, pero faltan alertas para los
eventos nuevos de Y-01/Y-04/Y-05, y no existe todavía un reporte ejecutivo automatizado
(X-06 está planeado pero no implementado).

**Nuevas alertas sobre N-09:**

| Evento | Canal sugerido |
|--------|----------------|
| Stagnation detectada (Y-01) — ticket atascado N ciclos | #alertas-dev (urgent) |
| Tech Lead rechazó PM (Y-05) — descripción del problema | #alertas-dev |
| DBA generó `DB_SOLUTION.sql` listo para DEV (Y-04) | #tickets-activos |
| Nuevo ciclo de corrección iniciado (Y-01) — ciclo N | #tickets-activos |
| Pipeline completado con N ciclos de rework | #metricas |

**Reporte ejecutivo automático semanal** (lunes 08:00, canal #management):
- Tickets procesados vs semana anterior
- Tasa de rework por módulo (qué áreas necesitan más correcciones)
- Tiempo promedio PM / DEV / QA
- ROI estimado: horas-developer ahorradas (((duración_pm_min + dev_min + qa_min) × tickets) / 60)
- Módulo con más bugs de la semana → candidato a refactoring

**Webhook genérico adicional:** permite integrar con cualquier herramienta sin código
extra. Cualquier evento de Stacky puede enviarse a un endpoint externo configurable.

**Archivos nuevos:** `weekly_reporter.py`, `report_template.html`
**Archivos a modificar:** `notifier.py` (eventos Y-01/Y-04/Y-05, reporte semanal,
webhook genérico), `daemon.py` (scheduler del reporte semanal)
**Esfuerzo:** Bajo-Medio (1.5 días) | **Impacto:** Alto — visibilidad completa del sistema

---

### `[x]` Y-07 · Stats Dashboard Operacional + Ejecutivo ✓

**Problema:** `MetricsCollector` (N-08) ya recolecta datos ricos pero el dashboard
actual los muestra de forma básica. No hay vista ejecutiva, no hay timeline por ticket,
y no hay visibilidad de rework ni de los nuevos stages (DBA/TechLead).

**Vista operacional (equipo técnico):**
- Timeline visual por ticket: barra por stage (PM/DBA/TL/DEV/QA) con duración real
- Tabla de rework: módulos con más ciclos de corrección (heatmap)
- Bottleneck del día: cuál stage está acumulando tickets
- Ciclos activos en tiempo real con countdown de timeout
- Stagnation alerts visuales (Y-01): tickets atascados en rojo

**Vista ejecutiva (gerencia — panel separado `/dashboard/executive`):**
- KPIs semanales: tickets resueltos, tiempo promedio de resolución, tasa de primer intento
- ROI: horas-developer ahorradas acumuladas (desde el inicio del proyecto)
- Tendencia: gráfico de eficiencia semana a semana (¿el sistema mejora?)
- Top 5 módulos con más actividad → candidatos a refactoring / deuda técnica

**Archivos a modificar:** `dashboard.html` (nuevas tabs operacional/ejecutivo),
`dashboard_server.py` (endpoints `/api/metrics/operational`, `/api/metrics/executive`),
`metrics_collector.py` (nuevos campos: rework_count, stagnation_count, dba_used, tl_used)
**Esfuerzo:** Medio (2-3 días) | **Impacto:** Muy alto — convierte Stacky en
herramienta auditable y presentable a gerencia

---

## Tabla de Priorizacion Global — Parte 7

| ID | Nombre | Esfuerzo | Impacto | Depende de | Orden |
|----|--------|----------|---------|------------|-------|
| **P0** | Fix M-01 en pipeline_runner | Bajo | BLOQUEANTE | M-01 | 1º | `[x]` |
| **Y-01** | Full Reset Loop + Correcciones Infinitas | Medio | Transformador | P0, M-01 | 2º |
| **Y-03** | Subsystem Classifier | Bajo | Alto | — | 3º |
| **Y-02** | PM Pre-Warming | Bajo | Alto | Y-03, S-04, G-06 | 4º |
| **Y-04** | Agente DBA Especialista | Medio | Muy alto | G-03, Y-01 | 5º |
| **Y-05** | Agente Tech Lead Reviewer | Medio | Alto | Y-01 | 6º |
| **Y-07** | Stats Dashboard Operacional + Ejecutivo | Medio | Muy alto | N-08, Y-01 | 7º |
| **Y-06** | Slack/Teams Hub + Reporte Ejecutivo | Bajo-Medio | Alto | N-09, Y-07 | 8º |

---

## PARTE 8 — Secuencialidad y Anti-Duplicación del Pipeline

> **Contexto:** Los ítems de esta parte surgieron del análisis forense de los logs
> `2026-04-09.log` y `2026-04-10.log`. Se identificaron 7 causas raíz (RC1–RC7) que
> provocan que el pipeline invoque agentes de forma duplicada, concurrente o fuera de
> orden. Cada ítem SEQ-xx address una o más causas raíz específicas.
>
> **Causas raíz identificadas:**
> - **RC1** — `pipeline_runner.py` CLI + dashboard watcher corren simultáneamente sin coordinación
> - **RC2** — `api_set_state` + `recovery-stuck` compiten para lanzar el mismo agente
> - **RC3** — Zombie state en `state.json` de run anterior dispara agente incorrecto
> - **RC4** — `api_set_state` no limpia flags EN_CURSO al cambiar estado manualmente
> - **RC5** — `_STUCK_COMPLETADO` reintenta automáticamente cada 60 s sin límite
> - **RC6** — `pipeline_runner.py` CLI tiene su propio `_invoke_stage` sin EN_CURSO flags
> - **RC7** — Fallback PM "sin placeholders" se activa sobre archivos de runs anteriores
>
> **Ya implementado en sesiones anteriores:**
> - EN_CURSO flag atómico en `_invoke_stage()` (open con "x")
> - `allow_ui_fallback=False` en `copilot_bridge.py`
> - `api_run_pipeline` guard contra `*_en_proceso` / `completado`
> - `api_reimport` limpia todos los flags incluyendo EN_CURSO
> - Recovery-stuck verifica EN_CURSO antes de lanzar
> - INTERVAL cambiado a 10 s

---

### `[ ]` SEQ-01 · Deshabilitar `pipeline_runner.py` CLI en Producción

**Problema (RC1, RC6):** El CLI `pipeline_runner.py` y el watcher del dashboard son
dos motores completamente independientes. Ambos pueden lanzar agentes sobre el mismo
ticket sin ninguna coordinación. El log del 10/04 muestra la secuencia destructiva:

```
19:24:07  pipeline_runner.py CLI lanza PM  →  "Pipeline finalizado" (fire-and-forget)
19:24:12  watcher carga QA (estado previo zombie "tester_en_proceso")
19:24:18  prompt PM enviado (3801 chars)
19:24:22  prompt QA enviado (9126 chars)  ← PM y QA corriendo al mismo tiempo
```

Además, `pipeline_runner.py` tiene su propia implementación de `_invoke_stage()` que
**no usa EN_CURSO flags** — ignora completamente la protección implementada en el dashboard.

**Solución:** Marcar el CLI como solo para uso en desarrollo/debug. En producción,
el único orquestador autorizado es el watcher de `dashboard_server.py`.

```python
# pipeline_runner.py — agregar al inicio de main()
import sys

PRODUCTION_MODE = os.environ.get("STACKY_PRODUCTION", "0") == "1"

def main():
    if PRODUCTION_MODE:
        print("ERROR: pipeline_runner.py CLI está deshabilitado en modo producción.")
        print("Usar el dashboard (localhost:5050) o POST /api/run_pipeline para lanzar tickets.")
        sys.exit(1)
    # ... resto del main actual
```

Configurar en `config.json`:
```json
"runtime": {
  "production_mode": true,
  "disable_cli_runner": true
}
```

Alternativamente, agregar una advertencia visible en el output del CLI si detecta que
el dashboard watcher ya está activo (verificando si el socket del Flask está respondiendo).

**Archivos a modificar:**
- `pipeline_runner.py` — guard al inicio de `main()`, check de dashboard activo
- `config.json` — campo `runtime.production_mode`
- `README.md` o doc de operación — documentar que CLI es solo debug

**Esfuerzo estimado:** Bajo (2–3 horas)
**Impacto:** Alto — elimina RC1 y RC6 de raíz. Sin CLI corriendo en paralelo,
todos los problemas de invocación concurrente desaparecen.

---

### `[ ]` SEQ-02 · Lock Global por Ticket en Memoria (`threading.Lock`)

**Problema (RC2, RC5, RC6):** Múltiples code paths pueden intentar invocar un agente
sobre el mismo ticket casi simultáneamente: el watcher normal, el recovery-stuck, y
`api_run_pipeline` cuando el usuario hace click en "Ejecutar". El EN_CURSO flag en
disco ayuda pero tiene una ventana de race condition pequeña (entre el check y la
creación del archivo).

```python
# Ventana de race condition (ms) entre:
if not os.path.exists(en_curso_path):    # thread A verifica → no existe
    # ... justo aquí thread B también verifica → no existe
    open(en_curso_path, "x")             # thread A crea
    # thread B también llega acá y falla con FileExistsError → OK
    # pero si están en procesos distintos, open("x") no es atómico cross-process
```

El `open(path, "x")` es atómico dentro del mismo proceso pero **no garantizado entre
procesos separados** en Windows NTFS en ciertos escenarios de red o drives mapeados.

**Solución:** Agregar un `threading.Lock` por ticket_id en memoria, como primera
línea de defensa (mismo proceso), complementando el EN_CURSO flag en disco
(defensa cross-proceso):

```python
# dashboard_server.py — agregar a nivel de módulo
import threading
from collections import defaultdict

# Lock por ticket: evita que dos threads del mismo proceso
# intenten invocar el mismo ticket simultáneamente
_ticket_invoke_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)

def _invoke_stage(ticket_id: str, stage: str, ...):
    lock = _ticket_invoke_locks[ticket_id]
    
    if not lock.acquire(blocking=False):
        logger.warning(f"[{ticket_id}] _invoke_stage: lock en memoria ya tomado por otro thread, abortando")
        return False
    
    try:
        # ... lógica actual incluyendo EN_CURSO file check
        en_curso_path = ...
        try:
            open(en_curso_path, "x").close()
        except FileExistsError:
            logger.warning(f"[{ticket_id}] EN_CURSO flag ya existe (cross-process protection)")
            return False
        
        # ... invocar agente
    finally:
        lock.release()
```

Cleanup del lock: los locks en `_ticket_invoke_locks` son baratos (solo flotan en
memoria). Agregar cleanup periódico en el watcher para tickets completados si el
dict crece indefinidamente.

**Archivos a modificar:**
- `dashboard_server.py` — dict `_ticket_invoke_locks`, integrate en `_invoke_stage()`

**Esfuerzo estimado:** Bajo (3–4 horas)
**Impacto:** Medio-Alto — elimina race condition intra-proceso completamente.
En combinación con EN_CURSO flag, da doble protección.

---

### `[ ]` SEQ-03 · Deshabilitar `_STUCK_COMPLETADO` Auto-Launch

**Problema (RC2, RC5):** El bloque `_STUCK_COMPLETADO` en el watcher detecta tickets
en estado `pm_completado` o `dev_completado` que llevan demasiado tiempo sin avanzar
y automáticamente lanza el siguiente agente. El problema es doble:

1. **Falso positivo:** Un ticket está en `pm_completado` porque el usuario lo puso
   manualmente para re-procesar, y antes de que pueda hacer click en "Ejecutar DEV",
   el recovery-stuck ya lo lanzó (RC5). En el log se ve esto exactamente a las 19:24.

2. **Doble lanzamiento:** El usuario hace click en "Ejecutar" (`api_run_pipeline`)
   y microsegundos después el watcher también dispara en su ciclo de recovery (RC2).

```
19:24:35  POST /api/set_state → "pm_completado"   (usuario)
19:24:36  POST /api/run_pipeline → lanza DEV       (usuario hace click)
19:24:36  _STUCK_COMPLETADO recovery → lanza DEV  (watcher, 1 segundo después)
          → DEV lanzado DOS veces simultáneamente
```

**Solución:** Reemplazar el auto-launch del stuck por una **notificación sin acción**:

```python
# dashboard_server.py — bloque _STUCK_COMPLETADO (línea ~2030-2040 aprox)

# ANTES (auto-launch):
# if estado in _STUCK_COMPLETADO and tiempo > STUCK_THRESHOLD:
#     _invoke_stage(ticket_id, next_stage)

# DESPUÉS (notificación + flag visible, sin lanzamiento automático):
STUCK_THRESHOLD_MINUTES = 30  # tiempo sin avanzar para considerar stuck

for ticket_id, info in tickets_stuck.items():
    estado = info["estado"]
    minutos_stuck = info["minutos_stuck"]
    
    if estado in _STUCK_COMPLETADO and minutos_stuck > STUCK_THRESHOLD_MINUTES:
        # Solo notificar — NO lanzar automáticamente
        logger.warning(
            f"[{ticket_id}] STUCK: estado '{estado}' hace {minutos_stuck} min. "
            f"Intervención manual recomendada. "
            f"Usar POST /api/run_pipeline para avanzar."
        )
        # Marcar en state.json para que el dashboard muestre alerta visual
        state_manager.set_flag(ticket_id, "stuck_alert", True)
        # Notificación toast/Slack si está configurado
        notifier.notify(f"Ticket {ticket_id} stuck en {estado} — {minutos_stuck} min")
```

Si se quiere mantener auto-launch como opción, ponerlo detrás de un flag configurable:
```json
"watcher": {
  "stuck_auto_launch": false,   ← default cambiado a false
  "stuck_threshold_minutes": 30,
  "stuck_notify": true
}
```

**Archivos a modificar:**
- `dashboard_server.py` — bloque `_STUCK_COMPLETADO` en `_stage_transition_watcher()`
- `config.json` — campo `watcher.stuck_auto_launch`
- `dashboard.html` — mostrar alerta visual cuando `stuck_alert=True`

**Esfuerzo estimado:** Bajo (2–3 horas)
**Impacto:** Alto — elimina RC2 y RC5 directamente. El auto-launch del stuck es
la causa del 70% de las invocaciones duplicadas observadas en los logs.

---

### `[ ]` SEQ-04 · `api_set_state` Limpia EN_CURSO + Cooldown 30 s en Watcher

**Problema (RC4):** Cuando el usuario cambia el estado manualmente desde el dashboard
(`POST /api/set_state`), el endpoint actualiza `state.json` pero **no limpia los flags
EN_CURSO** de la etapa anterior. Si PM estaba corriendo y dejó un `PM_AGENTE_EN_CURSO.flag`,
y el usuario setea manualmente `pm_completado`, el watcher del siguiente ciclo (10 s)
ve `pm_completado` + `PM_AGENTE_EN_CURSO.flag` activo → comportamiento inconsistente.

Además, el watcher detecta el nuevo estado en el próximo ciclo (hasta 10 s) y puede
disparar el siguiente stage antes de que el usuario termine de configurar el ticket
o antes de que haya actualizado la UI.

**Solución parte A — Limpiar EN_CURSO en `api_set_state`:**

```python
# dashboard_server.py — api_set_state

@app.route("/api/set_state/<ticket_id>", methods=["POST"])
def api_set_state(ticket_id):
    new_state = request.json.get("estado")
    
    # ... lógica actual de validación y actualización de state.json ...
    
    # NUEVO: limpiar todos los EN_CURSO de etapas anteriores al nuevo estado
    ticket_folder = get_ticket_folder(ticket_id)
    if ticket_folder:
        for flag_name in ["PM_AGENTE_EN_CURSO.flag", "DEV_AGENTE_EN_CURSO.flag", "TESTER_AGENTE_EN_CURSO.flag"]:
            flag_path = os.path.join(ticket_folder, flag_name)
            if os.path.exists(flag_path):
                os.remove(flag_path)
                logger.info(f"[{ticket_id}] set_state({new_state}): limpiado {flag_name}")
    
    # NUEVO: registrar timestamp del cambio manual para el cooldown del watcher
    state_manager.set_manual_set_timestamp(ticket_id, time.time())
    
    return jsonify({"ok": True})
```

**Solución parte B — Cooldown en watcher post-set_state:**

```python
# dashboard_server.py — _stage_transition_watcher

# Dict en memoria: ticket_id → timestamp del último set_state manual
_manual_set_timestamps: dict[str, float] = {}
MANUAL_SET_COOLDOWN_SECONDS = 30  # watcher ignora el ticket durante 30 s post-set_state

def _stage_transition_watcher():
    while True:
        for ticket_id, ticket_info in get_active_tickets():
            # Cooldown: si el usuario cambió el estado hace menos de 30 s,
            # no disparar auto-transitions — el usuario está tomando control manual
            last_set = _manual_set_timestamps.get(ticket_id, 0)
            if time.time() - last_set < MANUAL_SET_COOLDOWN_SECONDS:
                logger.debug(f"[{ticket_id}] watcher: cooldown activo ({int(time.time() - last_set)}s)")
                continue
            
            # ... lógica actual del watcher ...
        
        time.sleep(INTERVAL)
```

**Archivos a modificar:**
- `dashboard_server.py` — `api_set_state()` (limpiar EN_CURSO), `_stage_transition_watcher()` (cooldown)

**Esfuerzo estimado:** Bajo (3–4 horas)
**Impacto:** Medio-Alto — elimina RC4 y reduce RC2. La ventana de race entre
click manual y auto-advance del watcher se cierra con el cooldown de 30 s.

---

### `[ ]` SEQ-05 · Reset Borra Archivos de Análisis del Ticket

**Problema (Reliability, UX):** El botón "Reimport/Reset" de `api_reimport` limpia
todos los flags EN_CURSO, COMPLETADO, ERROR y archivos `.bak`. Pero **no borra los
archivos de análisis** generados por agentes anteriores:
`INCIDENTE.md`, `ANALISIS_TECNICO.md`, `ARQUITECTURA_SOLUCION.md`, `TAREAS_DESARROLLO.md`,
`NOTAS_IMPLEMENTACION.md`, `QUERIES_ANALISIS.sql`, `BUG_LOCALIZATION.md`, `PM_COMPLETADO.flag`.

El resultado: cuando PM re-analiza el ticket, los archivos viejos siguen ahí. PM puede
leer contenido previo y llegar a conclusiones contaminadas, o simplemente no regenerar
un archivo por creer que ya existe y está bien.

**Solución:** Extender `api_reimport` para borrar también los artefactos de análisis:

```python
# dashboard_server.py — api_reimport

ANALYSIS_FILES_TO_DELETE = [
    "INCIDENTE.md",
    "ANALISIS_TECNICO.md",
    "ARQUITECTURA_SOLUCION.md",
    "TAREAS_DESARROLLO.md",
    "NOTAS_IMPLEMENTACION.md",
    "QUERIES_ANALISIS.sql",
    "BUG_LOCALIZATION.md",
    "DB_SOLUTION.sql",        # Y-04 DBA Agent
    "SVN_CHANGES.md",         # M-04
    "COMMIT_MESSAGE.txt",     # N-02
    "DEV_SHADOW_PLAN.md",     # N-07
]

FLAG_FILES_TO_DELETE = [
    "PM_COMPLETADO.flag",
    "DEV_COMPLETADO.md",
    "TESTER_COMPLETADO.md",
    "*_ERROR.flag",
    "*_AGENTE_EN_CURSO.flag",
    "TL_APPROVED.flag",       # Y-05
    "TL_REJECTED.md",         # Y-05
    "DB_READY.flag",          # Y-04
]

@app.route("/api/reimport/<ticket_id>", methods=["POST"])
def api_reimport(ticket_id):
    ticket_folder = get_ticket_folder(ticket_id)
    
    deleted_files = []
    
    # Borrar flags
    for pattern in FLAG_FILES_TO_DELETE:
        for f in glob.glob(os.path.join(ticket_folder, pattern)):
            os.remove(f)
            deleted_files.append(os.path.basename(f))
    
    # Borrar artefactos de análisis (NUEVO)
    for filename in ANALYSIS_FILES_TO_DELETE:
        f = os.path.join(ticket_folder, filename)
        if os.path.exists(f):
            os.remove(f)
            deleted_files.append(filename)
    
    # Borrar backups
    for f in glob.glob(os.path.join(ticket_folder, "*.bak")):
        os.remove(f)
        deleted_files.append(os.path.basename(f))
    
    # Resetear state.json
    state_manager.reset_ticket(ticket_id)
    
    logger.info(f"[{ticket_id}] Reimport: borrados {len(deleted_files)} archivos: {deleted_files}")
    return jsonify({"ok": True, "deleted": deleted_files})
```

**Opción de reset parcial** (solo flags, preservar análisis):
Agregar parámetro `?mode=flags_only` para cuando el usuario quiere solo limpiar el
estado sin descartar el análisis anterior.

**Archivos a modificar:**
- `dashboard_server.py` — `api_reimport()`, agregar `ANALYSIS_FILES_TO_DELETE`
- `dashboard.html` — botón de reset con opción "¿Borrar también el análisis?" (checkbox)

**Esfuerzo estimado:** Bajo (2 horas)
**Impacto:** Alto — evita que PM opere con contexto contaminado de runs anteriores.
Esencial para reproducibilidad: mismo input → mismo análisis.

---

### `[ ]` SEQ-06 · `api_set_state` No Activa `auto_advance` Automáticamente

**Problema (RC2):** Actualmente, cuando el usuario llama `POST /api/set_state` con
un estado como `pm_completado`, el endpoint puede activar `auto_advance=True` en
`state.json`. Esto hace que el watcher del siguiente ciclo automáticamente avance
al siguiente agente. Pero el usuario que hace set_state manual quiere tomar control —
no quiere que el watcher decida solo.

Este comportamiento interactúa con RC2: el usuario hace set_state + click en run_pipeline,
y el watcher también avanza por el `auto_advance` → triple invocación del mismo agente.

**Solución:** Separar semánticamente los dos tipos de cambio de estado:

```python
# Tipo A: Cambio automático (watcher detectó flag en disco → avanza naturalmente)
# → auto_advance = True → watcher puede seguir procesando
# Tipo B: Cambio manual (usuario hace click en dashboard o set_state API)
# → auto_advance = False → watcher no hace nada, usuario tiene el control

@app.route("/api/set_state/<ticket_id>", methods=["POST"])
def api_set_state(ticket_id):
    new_state = request.json.get("estado")
    # NUEVO: el set_state manual NUNCA activa auto_advance
    state_manager.set_state(ticket_id, new_state, auto_advance=False, manual=True)
    
    # ... limpiar EN_CURSO (SEQ-04) ...
    # ... cooldown (SEQ-04) ...
    
    return jsonify({"ok": True})

# En el watcher, auto-transitions sí ponen auto_advance=True  
def _handle_stage_complete(ticket_id, detected_flag):
    next_state = compute_next_state(detected_flag)
    state_manager.set_state(ticket_id, next_state, auto_advance=True, manual=False)
```

El watcher solo procede con `auto_advance=True`. Si el estado fue seteado manualmente
(`auto_advance=False`), el watcher lo ignora hasta que el usuario explícitamente
llame `api_run_pipeline` o un nuevo flag aparezca en disco.

**Archivos a modificar:**
- `dashboard_server.py` — `api_set_state()`, `_stage_transition_watcher()`, `_handle_stage_complete()`
- `pipeline_state.py` — campo `auto_advance` y `manual` en el state dict

**Esfuerzo estimado:** Bajo-Medio (4–6 horas)
**Impacto:** Alto — desacopla completamente el control manual del auto-advance.
API semánticamente clara: set_state = setear, run_pipeline = ejecutar.

---

### `[x]` SEQ-07 · Unificar Punto de Entrada — Solo `_invoke_stage` del Dashboard ✓

**Problema (RC1, RC6):** Existen al menos dos implementaciones de `_invoke_stage`:
una en `dashboard_server.py` (con EN_CURSO flags, cooldown, logging detallado) y
otra en `pipeline_runner.py` (sin nada de eso). Cualquier fix a la serialización
debe hacerse en dos lugares, y si se olvida uno, el bug reaparece.

**Solución:** Extraer `_invoke_stage` a un módulo compartido `pipeline_invoker.py`
y hacer que AMBOS (`dashboard_server.py` y `pipeline_runner.py`) lo importen:

```python
# pipeline_invoker.py — NUEVO MÓDULO (la implementación canónica)

import threading
import os
import logging

logger = logging.getLogger(__name__)

_ticket_invoke_locks: dict[str, threading.Lock] = {}  # SEQ-02
_lock_dict_lock = threading.Lock()

def get_ticket_lock(ticket_id: str) -> threading.Lock:
    with _lock_dict_lock:
        if ticket_id not in _ticket_invoke_locks:
            _ticket_invoke_locks[ticket_id] = threading.Lock()
        return _ticket_invoke_locks[ticket_id]

def invoke_stage(
    ticket_id: str,
    stage: str,
    ticket_folder: str,
    bridge_client,
    prompt: str,
    en_curso_flag_path: str,
) -> bool:
    """Punto de entrada canónico para invocar un stage.
    
    Garantías:
    - Threading lock por ticket (SEQ-02)
    - EN_CURSO flag atómico en disco (implementado en sesiones anteriores)
    - Logging consistente con ticket_id + stage
    - Cleanup de EN_CURSO en todos los paths de error
    """
    lock = get_ticket_lock(ticket_id)
    if not lock.acquire(blocking=False):
        logger.warning(f"[{ticket_id}/{stage}] invoke_stage: lock en memoria ya tomado, abortando")
        return False
    
    try:
        # EN_CURSO flag atómico
        try:
            open(en_curso_flag_path, "x").close()
        except FileExistsError:
            logger.warning(f"[{ticket_id}/{stage}] EN_CURSO flag ya existe, abortando")
            return False
        
        try:
            logger.info(f"[{ticket_id}/{stage}] Invocando agente...")
            result = bridge_client.invoke_agent(stage, prompt)
            logger.info(f"[{ticket_id}/{stage}] Agente respondió: {result}")
            return True
            
        except Exception as e:
            logger.error(f"[{ticket_id}/{stage}] Error al invocar agente: {e}")
            return False
        finally:
            # Limpiar EN_CURSO siempre al salir
            if os.path.exists(en_curso_flag_path):
                os.remove(en_curso_flag_path)
                logger.debug(f"[{ticket_id}/{stage}] EN_CURSO flag limpiado")
    finally:
        lock.release()
```

```python
# dashboard_server.py — adaptar _invoke_stage() para delegar
from pipeline_invoker import invoke_stage as _canonical_invoke_stage

def _invoke_stage(ticket_id, stage, ...):
    # Solo prepara parámetros y delega al módulo canónico
    en_curso_path = get_en_curso_path(ticket_id, stage)
    prompt = build_prompt(ticket_id, stage)
    return _canonical_invoke_stage(ticket_id, stage, ticket_folder, bridge_client, prompt, en_curso_path)
```

```python
# pipeline_runner.py — reemplazar implementación propia por import
from pipeline_invoker import invoke_stage as _canonical_invoke_stage

# Eliminar la implementación local de _invoke_stage
# Usar _canonical_invoke_stage directamente
```

**Archivos nuevos:** `pipeline_invoker.py`
**Archivos a modificar:**
- `dashboard_server.py` — refactorizar `_invoke_stage()` para delegar
- `pipeline_runner.py` — eliminar implementación propia, importar de `pipeline_invoker.py`

**Esfuerzo estimado:** Medio (4–6 horas)
**Impacto:** Alto — cualquier mejora futura a la serialización se hace en **un solo lugar**.
Elimina la clase de bugs "arreglé en dashboard pero no en pipeline_runner".

---

### `[x]` SEQ-08 · Mutex Inter-Proceso via Lockfile para CLI + Dashboard ✓

**Problema (RC1, RC6):** Incluso con SEQ-07 (código unificado), dos procesos del
sistema operativo pueden ejecutar `invoke_stage` sobre el mismo ticket al mismo tiempo.
`threading.Lock` (SEQ-02) protege **dentro de un proceso** pero no entre procesos distintos.
Si alguien ejecuta `python pipeline_runner.py` mientras el dashboard está activo,
ambos tienen locks en memoria separados → no se ven entre sí.

**Solución:** Mutex inter-proceso mediante un lockfile dedicado por ticket:

```python
# pipeline_invoker.py — agregar a invoke_stage()
import fcntl  # Linux/Mac  ← NO funciona en Windows
# Para Windows usar:
import msvcrt
import ctypes

def acquire_process_lock(lock_path: str) -> bool:
    """Lockfile inter-proceso. Retorna True si se adquirió el lock."""
    # En Windows: CreateFile con FLAG_FILE_ATTRIBUTE_TEMPORARY + OPEN_ALWAYS
    # El lock se libera automáticamente si el proceso muere (OS lo limpia)
    try:
        # Método portable: open con O_CREAT | O_EXCL (atómico en NTFS)
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.write(fd, str(os.getpid()).encode())
        # No cerrar fd — mantener abierto como lock (se libera al morir el proceso)
        # Almacenar fd en dict global para liberarlo manualmente en release
        _open_lock_fds[lock_path] = fd
        return True
    except FileExistsError:
        # Lock tomado por otro proceso — verificar si está vivo
        try:
            with open(lock_path, "r") as f:
                holding_pid = int(f.read().strip())
            # Verificar si el proceso con ese PID está vivo
            os.kill(holding_pid, 0)  # signal 0 = verificar sin enviar señal
            return False  # proceso vivo, lock válido
        except (ProcessLookupError, ValueError):
            # Proceso muerto → lock stale, eliminar y reintentar
            os.remove(lock_path)
            return acquire_process_lock(lock_path)  # retry una vez

def release_process_lock(lock_path: str):
    if lock_path in _open_lock_fds:
        os.close(_open_lock_fds.pop(lock_path))
    if os.path.exists(lock_path):
        os.remove(lock_path)
```

El lockfile vive en la carpeta del ticket: `{ticket_folder}/INVOKE_LOCK.pid`
El nombre incluye `.pid` para que sea reconocible y limpiable por `api_reimport`.

**Nota Windows:** `os.kill(pid, 0)` funciona en Python 3.9+ en Windows para verificar
si un proceso existe. `O_EXCL` con `os.open` es atómico en NTFS local (pero **no**
garantizado en drives de red). Si el workspace está en un drive de red (ej. `N:\`),
usar una carpeta local como tmpdir para los lockfiles.

**Archivos a modificar:**
- `pipeline_invoker.py` — `acquire_process_lock()`, `release_process_lock()`, integrar en `invoke_stage()`
- `api_reimport` — borrar `INVOKE_LOCK.pid` en el reset

**Esfuerzo estimado:** Medio (4–5 horas — cuidado con edge cases de Windows + drives de red)
**Impacto:** Medio-Alto — cierra la brecha de race condition cross-proceso.
Importante si se mantiene la opción de CLI para ciertos flujos de debug.

---

### `[ ]` SEQ-09 · `state.json` con Campo `invoking_pid` + TTL para Detectar Procesos Muertos

**Problema (RC3):** El `state.json` puede quedar en un estado zombie de una sesión
anterior: `estado: "tester_en_proceso"` de una semana atrás, cuando el proceso QA
murió o fue interrumpido. El watcher lee ese estado y lo interpreta como activo,
disparando QA sobre un ticket que debería estar en PM.

El EN_CURSO flag en disco ayuda parcialmente, pero si el archivo flag también quedó
de una sesión anterior, el problema persiste.

**Solución:** Agregar a `state.json` metadata de contexto de ejecución con TTL:

```json
{
  "ticket_id": "0027698",
  "estado": "tester_en_proceso",
  "invoking_pid": 14832,
  "invoke_started_at": "2026-04-10T19:24:22",
  "invoke_ttl_minutes": 120,
  "invoke_host": "DESKTOP-ABC123"
}
```

El watcher verifica antes de actuar sobre un estado `*_en_proceso`:

```python
# dashboard_server.py — _stage_transition_watcher

def is_invoke_still_valid(state: dict) -> bool:
    """Retorna False si el invocador está muerto o el TTL expiró."""
    pid = state.get("invoking_pid")
    started_at = state.get("invoke_started_at")
    ttl_min = state.get("invoke_ttl_minutes", 120)
    
    if not pid or not started_at:
        return True  # estado sin metadata = estado viejo, asumir válido por compatibilidad
    
    # Verificar TTL
    elapsed = (datetime.now() - datetime.fromisoformat(started_at)).total_seconds() / 60
    if elapsed > ttl_min:
        logger.warning(f"Estado en_proceso caducado: {elapsed:.0f} min > TTL {ttl_min} min")
        return False
    
    # Verificar si el PID sigue vivo
    try:
        os.kill(pid, 0)
        return True  # proceso vivo
    except ProcessLookupError:
        logger.warning(f"PID {pid} ya no existe — estado en_proceso es zombie")
        return False

# En el watcher, si is_invoke_still_valid() retorna False para un estado *_en_proceso:
# → limpiar el estado zombie → emitir alerta → NO avanzar automáticamente (dejar para SEQ-03)
```

**Archivos a modificar:**
- `pipeline_state.py` — agregar `invoking_pid`, `invoke_started_at`, `invoke_ttl_minutes` al set_state
- `dashboard_server.py` — `is_invoke_still_valid()`, usar en watcher antes de procesar estados `*_en_proceso`
- `pipeline_invoker.py` — pasar pid y timestamp al set_state al iniciar una invocación

**Esfuerzo estimado:** Bajo-Medio (3–4 horas)
**Impacto:** Alto — elimina RC3 directamente. El zombie state detection es la
corrección más directa para el problema de QA disparándose mientras PM corre.

---

### `[ ]` SEQ-10 · Validar Estado ANTES de Escribir `auto_advance=True`

**Problema (RC2):** El flujo `api_set_state(pm_completado)` + `api_run_pipeline()`
puede crear una condición donde el watcher avanza automáticamente porque leyó
`auto_advance=True` en un ciclo previo, incluso después de que el usuario ya hizo
click en "Ejecutar". El `auto_advance` puede quedar en `True` de un subciclo del
watcher que procesó el transition parcialmente.

**Solución:** El campo `auto_advance` solo puede ser `True` si el estado actual
en el JSON es coherente con la transición que lo activó:

```python
# pipeline_state.py

class PipelineState:
    # Mapa de transiciones válidas que activan auto_advance
    VALID_AUTO_ADVANCE_TRANSITIONS = {
        "pm_completado": "dev_en_proceso",
        "dev_completado": "tester_en_proceso",
        "qa_approved": "completado",
    }
    
    def set_auto_advance(self, ticket_id: str, target_state: str):
        current = self.get_state(ticket_id)
        
        # Solo activar auto_advance si current state puede legítimamente avanzar a target
        expected_current = {v: k for k, v in self.VALID_AUTO_ADVANCE_TRANSITIONS.items()}.get(target_state)
        
        if current != expected_current:
            logger.warning(
                f"[{ticket_id}] set_auto_advance rechazado: estado actual '{current}' "
                f"no es coherente con avanzar a '{target_state}' "
                f"(se esperaba '{expected_current}')"
            )
            return False
        
        self._write_state(ticket_id, {"auto_advance": True, "auto_advance_to": target_state})
        return True
```

```python
# En el watcher, antes de actuar sobre auto_advance=True:
advance_to = state.get("auto_advance_to")
if state.get("auto_advance") and advance_to:
    # Verificar que el estado actual sigue siendo coherente con lo que se planificó
    current_state = state.get("estado")
    if current_state != get_expected_state_for_advance(advance_to):
        logger.warning(f"[{ticket_id}] auto_advance obsoleto: estado cambió a '{current_state}'")
        state_manager.clear_auto_advance(ticket_id)
        continue
    # Proceder con el advance
```

**Archivos a modificar:**
- `pipeline_state.py` — `set_auto_advance()` con validación, `clear_auto_advance()`
- `dashboard_server.py` — watcher: verificación de coherencia antes de actuar

**Esfuerzo estimado:** Bajo-Medio (3 horas)
**Impacto:** Medio — previene el caso de auto_advance stale que hace que el watcher
avance sobre un ticket que ya fue manejado manualmente.

---

### `[ ]` SEQ-11 · Log Estructurado de Invocaciones con Correlation ID

**Problema (Observabilidad):** Los logs actuales mezclan eventos de distintos tickets
y threads sin una forma fácil de correlacionarlos. Al revisar `2026-04-10.log` para
diagnóstico, hay que leer línea por línea para entender qué thread invocó qué ticket
cuándo. En el caso del bug de las 19:24, tomó mucho análisis manual para reconstruir
la secuencia de eventos.

**Solución:** Agregar un `correlation_id` por invocación que aparece en todos los
logs relacionados con esa invocación:

```python
# pipeline_invoker.py

import uuid

def invoke_stage(ticket_id, stage, ...):
    correlation_id = str(uuid.uuid4())[:8]  # 8 chars: legible, único por invocación
    
    log_prefix = f"[{ticket_id}/{stage}/{correlation_id}]"
    
    logger.info(f"{log_prefix} INVOKE_START thread={threading.current_thread().name} pid={os.getpid()}")
    
    # ... acquire lock ...
    logger.debug(f"{log_prefix} LOCK_ACQUIRED")
    
    # ... EN_CURSO flag ...
    logger.info(f"{log_prefix} EN_CURSO_CREATED path={en_curso_flag_path}")
    
    # ... invocar bridge ...
    logger.info(f"{log_prefix} BRIDGE_CALL agent={stage} prompt_len={len(prompt)}")
    
    # ... resultado ...
    logger.info(f"{log_prefix} INVOKE_END result={result} elapsed={elapsed:.1f}s")
```

Resultado en log:
```
2026-04-10 19:24:07 INFO  [0027698/PM/a3f2b1c4] INVOKE_START thread=watcher pid=14832
2026-04-10 19:24:07 INFO  [0027698/PM/a3f2b1c4] LOCK_ACQUIRED
2026-04-10 19:24:07 INFO  [0027698/PM/a3f2b1c4] EN_CURSO_CREATED path=.../PM_AGENTE_EN_CURSO.flag
2026-04-10 19:24:18 INFO  [0027698/PM/a3f2b1c4] BRIDGE_CALL agent=PM-TL-Stack-3 prompt_len=3801
2026-04-10 19:24:07 INFO  [0027698/QA/7d9e4a12] INVOKE_START thread=recovery pid=14832  ← CONCURRENCIA VISIBLE
2026-04-10 19:24:22 INFO  [0027698/QA/7d9e4a12] BRIDGE_CALL agent=QA prompt_len=9126
```

Con correlation IDs, el log de las 19:24 habría mostrado claramente los dos threads
en paralelo desde el primer momento.

**Dashboard:** agregar endpoint `/api/logs/<ticket_id>?last=50` que filtra el log
por ticket_id y muestra las invocaciones ordenadas con sus correlation IDs.

**Archivos a modificar:**
- `pipeline_invoker.py` (o `dashboard_server.py`) — agregar correlation_id a todos los log_prefix de invocación
- `dashboard_server.py` — endpoint `/api/logs/<ticket_id>`
- `dashboard.html` — panel de logs por ticket con correlation IDs visibles

**Esfuerzo estimado:** Bajo (2–3 horas para logging, 4–6 horas para UI opcional)
**Impacto:** Medio — no previene bugs, pero los hace **diagnosticables en segundos**
en lugar de minutos/horas. Esencial para el mantenimiento futuro del sistema.

---

### `[ ]` SEQ-12 · PM Fallback "Sin Placeholders" Deshabilitado — Solo Flag Explícita

**Problema (RC7):** En `pipeline_runner.py` (o en la lógica del watcher) existe un
mecanismo que detecta la "completación" de PM basándose en que los archivos de análisis
no tienen más `_A completar por PM_` — es decir, si los archivos existen y no tienen
placeholders, se trata como completado. Este fallback puede activarse sobre archivos
de runs anteriores, si el reset no los limpió, confundiendo al sistema en creer que
PM ya completó cuando en realidad es contenido viejo.

En el log, esto puede ser la causa de que el watcher avanzó a QA cuando PM ni siquiera
había terminado el análisis nuevo: los archivos del run anterior no tenían placeholders,
el fallback los interpretó como válidos, y avanzó.

**Solución:** Eliminar el fallback de "sin placeholders" como criterio de completado.
La **única** fuente de verdad para que PM completó es el archivo `PM_COMPLETADO.flag`
creado explícitamente por el agente PM:

```python
# Antes (lógica con fallback):
def is_pm_complete(ticket_folder) -> bool:
    flag_path = os.path.join(ticket_folder, "PM_COMPLETADO.flag")
    if os.path.exists(flag_path):
        return True
    
    # FALLBACK (RC7 — ELIMINAR ESTO):
    # Si los archivos existen y no tienen placeholders, asumir completado
    archivos = ["ANALISIS_TECNICO.md", "ARQUITECTURA_SOLUCION.md", "TAREAS_DESARROLLO.md"]
    if all(os.path.exists(os.path.join(ticket_folder, a)) for a in archivos):
        contenidos = [open(os.path.join(ticket_folder, a)).read() for a in archivos]
        if not any("_A completar" in c for c in contenidos):
            return True  # ← ESTO ES RC7, ELIMINAR
    
    return False

# Después (solo flag explícita):
def is_pm_complete(ticket_folder) -> bool:
    flag_path = os.path.join(ticket_folder, "PM_COMPLETADO.flag")
    return os.path.exists(flag_path)
    # Punto. Solo el flag. Nada más.
```

Si el agente PM olvidó crear el flag, Stacky no avanza y el usuario tiene que
intervenir manualmente o relanzar PM. Es mejor este comportamiento conservador
que avanzar sobre contenido de un run anterior.

**Instrucción para el prompt PM:** Asegurarse de que el prompt PM tenga instrucción
explícita y prominente de crear `PM_COMPLETADO.flag` como **último paso**:

```markdown
## OBLIGATORIO — Último paso del análisis
Al terminar de completar TODOS los archivos, crea el archivo de señal:
```
{TICKET_FOLDER}/PM_COMPLETADO.flag
```
Este archivo indica que el análisis está completo. SIN este archivo, el
pipeline NO avanza al siguiente stage. No lo crees hasta que todos los
archivos estén completos y sin placeholders.
```

**Archivos a modificar:**
- `dashboard_server.py` o `pipeline_runner.py` — función `is_pm_complete()` o equivalente
- `prompts/pm.md` — reforzar instrucción de crear `PM_COMPLETADO.flag` al final

**Esfuerzo estimado:** Bajo (1–2 horas)
**Impacto:** Medio — elimina RC7. Evita avances incorrectos basados en archivos de
runs anteriores. Hace el comportamiento 100% predecible: sin flag = sin avance.

---

## Tabla de Priorización Global — Parte 8

> Orden recomendado de implementación según impacto/esfuerzo y dependencias entre items.

| ID | Nombre | Aborda | Esfuerzo | Impacto | Depende de |
|----|--------|--------|----------|---------|------------|
| **SEQ-03** | Deshabilitar `_STUCK_COMPLETADO` auto-launch | RC2, RC5 | Bajo | Alto | — |
| **SEQ-12** | PM fallback deshabilitado | RC7 | Bajo | Medio | — |
| **SEQ-09** | `state.json` con `invoking_pid` + TTL | RC3 | Bajo | Alto | — |
| **SEQ-04** | `api_set_state` limpia EN_CURSO + cooldown | RC4 | Bajo | Medio-Alto | — |
| **SEQ-05** | Reset borra archivos de análisis | Reliability | Bajo | Alto | — |
| **SEQ-11** | Log estructurado con correlation ID | Observabilidad | Bajo | Medio | — |
| **SEQ-01** | Deshabilitar CLI en producción | RC1, RC6 | Bajo | Alto | — |
| **SEQ-06** | `api_set_state` no activa auto_advance | RC2 | Bajo-Medio | Alto | SEQ-04 |
| **SEQ-10** | Validar estado antes de auto_advance | RC2 | Bajo-Medio | Medio | SEQ-06 |
| **SEQ-02** | Lock global por ticket en memoria | RC2, RC5, RC6 | Bajo | Medio-Alto | SEQ-07 |
| **SEQ-07** | Unificar `_invoke_stage` en módulo canónico | RC1, RC6 | Medio | Alto | SEQ-01 |
| **SEQ-08** | Mutex inter-proceso via lockfile | RC1, RC6 | Medio | Medio-Alto | SEQ-07 |

### Secuencia recomendada para el próximo agente

**Sprint rápido (2–3 horas, sin dependencias):**
1. SEQ-03 — comentar/flag el auto-launch de stuck (1 cambio de código, alto impacto)
2. SEQ-12 — eliminar fallback "sin placeholders" (1 función, fácil)
3. SEQ-09 — agregar `invoking_pid` + TTL a state.json (previene zombie states)
4. SEQ-05 — extender api_reimport con ANALYSIS_FILES_TO_DELETE (ya tiene la estructura)
5. SEQ-11 — agregar correlation_id al logging de invoke_stage (diagnóstico futuro)

**Sprint medio (4–6 horas, algunas dependencias):**
6. SEQ-04 — limpiar EN_CURSO en set_state + cooldown 30s watcher
7. SEQ-06 — separar manual vs auto en set_state
8. SEQ-01 — guard en pipeline_runner.py CLI

**Sprint estructural (1–2 días, requiere refactor):**
9. SEQ-07 — extraer pipeline_invoker.py unificado
10. SEQ-02 — threading.Lock global usando el módulo unificado
11. SEQ-08 — lockfile inter-proceso (solo si CLI sigue activo)
12. SEQ-10 — validación de coherencia de auto_advance
