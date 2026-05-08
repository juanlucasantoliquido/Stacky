# Mejoras Stacky Agents — Backlog y estado

> Este archivo registra las mejoras propuestas, aprobadas e implementadas para Stacky Agents.
> Se actualiza a medida que los agentes implementan o los operadores proponen cambios.

---

## Mejoras implementadas ✅

### 1. Rollback de acciones ADO
**Propuesta original:** "Debe permitir hacer un rollback de la acción — si un agente analista se equivoca debe tener un botón para borrar el comentario o ticket que haya hecho."

**Estado:** ✅ Implementado  
**Endpoint:** `POST /api/executions/:id/rollback-ado`  
**Comportamiento:**
- Borra el comentario/task del tracker (ADO/Jira/Mantis)
- Actualiza `verdict` a `"rolled_back"` en BD local
- Preserva el output para auditoría
- Registra la operación en system_logs con el operador que ejecutó el rollback

---

### 2. Visual de trabajo activo (animación en ejecución)
**Propuesta original:** "Cuando esté con un ticket asignado en trabajo, debe mostrarse en movimiento y con una visual amigable de que está trabajando."

**Estado:** ✅ Implementado  
**Componentes UI:**
- El botón Run cambia a "Running ▮▮" con animación pulsante mientras la exec está activa
- El `LogsPanel` se abre automáticamente durante la ejecución con auto-scroll de logs en tiempo real
- El `EmployeeCard` en Team Screen muestra un badge visual de "en trabajo" cuando el agente tiene una exec running
- El estado `running` persiste via SSE (`GET /api/executions/:id/logs/stream`)

---

## Fix — Empleados y workflow por proyecto ✅

**Problema:** Al cambiar de proyecto en TopBar la Team Screen no actualizaba sus empleados, los empleados eran globales en lugar de por proyecto, y al crear un empleado no se podía configurar su workflow de entrada.

**Implementado en 4 fases con aprobación humana entre cada una.**

- La membresía del equipo se persiste por proyecto vía `Projects.putAgents`.
- Las preferencias globales (`preferences.ts`) sólo guardan avatar, apodo y rol.
- El workflow (allowed_states, transition_state, requires_prior_output) se configura tanto en alta (TeamManageDrawer) como en edición (EmployeeEditDrawer).
- Al cambiar de proyecto: limpieza inmediata del store + stale-request guard (secuencia incremental) evita contaminar el nuevo proyecto con datos del anterior.
- Skeleton animado en TeamScreen durante la carga del nuevo equipo.
- Error banners visibles para getAgents, putAgents, trackerStates, putAgentWorkflow.
- Componente reutilizable `AgentWorkflowForm` usado en alta y edición.

---

## Mejoras pendientes ⏳

### FA-34 — Token/cost budgets con enforcement
**Descripción:** Tabla `budgets` para límites de gasto por usuario/proyecto/período. Bloquear o alertar cuando se supera el presupuesto.  
**Estado:** Diseñado, tabla definida, no implementado.

### FA-38 — Prompt injection detection
**Descripción:** Detección heurística + clasificador ML de intentos de prompt injection en los contextos enviados al LLM.  
**Estado:** Heurísticas diseñadas, no implementado como servicio.

### FA-30 — CLI `stacky-agents`
**Descripción:** Interfaz de línea de comandos distribuible via `pipx install stacky-agents-cli` con subcomandos `run`, `status`, `tail`, `approve`.  
**Estado:** En backlog.

---

## Nuevas mejoras propuestas 💡

Agregar aquí cualquier nueva propuesta de mejora con el formato:

```
### N. Título de la mejora
**Propuesta:** descripción clara de qué se quiere lograr
**Beneficio:** por qué mejora la experiencia del operador o del sistema
**Estado:** propuesto
```
