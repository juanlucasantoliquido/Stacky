# 00 — Visión y cambio de paradigma

## El problema con el modelo "pipeline"

Stacky Pipeline está pensado como una **máquina de estados** que decide cuándo cada agente debe correr. El operador humano interactúa con la máquina **a través de los estados de los tickets** (`To Do` → `Doing` → `Tech review` → ...).

Esto funciona cuando:
- el camino feliz es predominante,
- los agentes raramente fallan,
- los outputs no requieren corrección humana antes de pasar al siguiente paso.

Pero al usar el sistema día a día aparecen tres problemas estructurales:

1. **Poca controlabilidad** — el operador no decide *cuándo* corre un agente, sólo lo dispara cambiando un estado. Si quiere repetir un análisis con más contexto, tiene que pelear contra la máquina de estados (revertir, re-disparar, limpiar artefactos previos).
2. **Acoplamiento rígido** — `Functional` es prerequisito de `Technical`, que es prerequisito de `Developer`. Si querés correr `Technical` sólo para explorar, no podés. Si el `Functional` quedó "ok pero rancio" hace 3 días, igual rige.
3. **Iterar es caro** — cada iteración implica pasar por todos los estados intermedios. Eso desincentiva probar, comparar, descartar.

## El cambio de paradigma

> Pasamos de **un sistema que decide cuándo correr agentes** a **un sistema que ejecuta agentes cuando el humano quiere**.

Cinco principios de diseño:

### 1. Independencia de los agentes

Cada agente es un servicio puro: recibe `(agent_type, input_context)` y devuelve `output`. No conoce ni importa el estado del ticket. No conoce a los demás agentes. Esto significa:

- Se pueden agregar agentes nuevos sin tocar el resto.
- Se puede correr cualquier agente sobre cualquier ticket en cualquier momento.
- Testear un agente es trivial: input fijo → output esperado.

### 2. El humano es el orquestador

No hay daemon. No hay pipeline. La unidad de ejecución es **un click en "Run"**.

La UI no esconde el contexto: el editor muestra exactamente qué se le va a mandar al agente, antes de mandarlo. El operador puede leer, editar, agregar, recortar.

### 3. Inmutabilidad del historial

Cada ejecución es una fila inmutable en `agent_executions`. Si el operador re-ejecuta con otro contexto, **se crea una nueva fila** — la anterior queda como evidencia. Se puede comparar dos ejecuciones del mismo agente lado a lado.

### 4. Composición opcional, no obligatoria

El sistema ofrece tres formas de **componer** sin imponer ninguna:

- **Auto-fill**: el editor sugiere outputs previos relevantes pero el humano elige qué incluir.
- **Re-run con edición**: clonar una ejecución previa, ajustar, relanzar.
- **Agent Packs**: recetas (ej: "Pack Desarrollo") que pre-configuran 4 agentes con sus contextos, pero corren paso a paso, esperando confirmación humana entre cada uno.

### 5. Trazabilidad por ticket, no por estado

El estado ADO del ticket deja de ser la fuente de verdad del progreso. La fuente de verdad es el **historial de ejecuciones por ticket**:

```
Ticket ADO-1234
├── exec #18  business    2026-04-22 11:02   (descartada)
├── exec #19  business    2026-04-22 11:08   ← outputs aprobados
├── exec #20  functional  2026-04-22 11:15   (input chain ← #19)
├── exec #21  technical   2026-04-22 14:30   (input chain ← #20)
├── exec #22  technical   2026-04-22 16:45   (re-run con +contexto BD)
└── exec #23  developer   2026-04-23 09:10   (input chain ← #22)
```

Stacky Pipeline necesitaría 4 estados ADO y un campo de "última pasada" para reflejar esto. Acá es transparente: leyendo la lista entendés todo.

---

## La pantalla de inicio: el equipo

La pregunta que define la UX de entrada es: **¿Cómo hace el humano para saber qué agente usar?**

La respuesta del paradigma anterior ("lista de cards con nombre técnico") requería que el operador conociera de memoria para qué sirve cada agente. Eso funcionaba para técnicos, pero no para analistas ni gente de negocio.

**La nueva respuesta: los agentes son empleados con cara y rol.**

La app abre en una **Team Screen** — un grid de tarjetas tipo equipo de trabajo. Cada tarjeta muestra:
- Avatar pixel art (personalizable: galería de 15-20 personajes IT o imagen propia pixelada)
- Nombre / apodo del agente (ej: "Carlos — Analista Técnico")
- Rol y especialidad
- Badge de tipo de agente

El operador arma **su equipo** desde todos los agentes `.agent.md` disponibles en la carpeta de VS Code. No ve todos los agentes del sistema — solo los que eligió poner en su equipo. Eso reduce la carga cognitiva de "¿cuál de los 20 uso?".

### Flujo principal desde la Team Screen

```
Team Screen
└─ click en empleado (ej: "Carlos — Technical")
   └─ modal "¿Qué ticket querés trabajar?"
      └─ buscar y seleccionar ticket ADO
         └─ click OK
            └─ se abre VS Code Copilot Chat con @agente + contexto del ticket
               └─ la conversación ocurre en el chat nativo de VS Code
```

**El bridge:** la extensión VS Code ya expone `POST localhost:5052/open-chat`. La app lo llama con `{ agent_name, message }`. El mensaje pre-cargado incluye el número y título del ticket.

### Flujo avanzado: Workbench

Para operadores que necesitan editar contexto, ver logs SSE, comparar ejecuciones o usar Agent Packs, el Workbench clásico sigue disponible como vista secundaria desde un botón en la Team Screen. No se elimina — se complementa.

---

## Product north — qué somos / qué NO somos

### Somos
- Un **equipo visual** de agentes-empleados configurables con avatares.
- Un **workbench** para operadores técnicos / funcionales (flujo avanzado).
- Un **puente inteligente** entre tickets ADO y VS Code Copilot Chat.
- Una **interfaz humana** sobre los agentes que ya existen en Stacky.
- Un **registro auditado** de qué se le pidió a cada agente y qué respondió.

### NO somos
- Un reemplazo de Azure DevOps.
- Un sistema de tickets.
- Un orquestador automático ni un cron.
- Un sucesor de Stacky Pipeline (pueden coexistir; ver [06_MIGRATION_FROM_STACKY.md](06_MIGRATION_FROM_STACKY.md)).

---

## Métricas de éxito

| Métrica | Cómo se mide | Target inicial |
|---|---|---|
| Tiempo promedio operador → primer output útil | timestamp click-Run → timestamp output-aprobado | < 90s para Functional, < 3min para Technical |
| % de outputs aprobados sin re-run | aprobados / total | > 60% sostenido |
| Tickets que recorren los 4 agentes en < 1 día laboral | timestamp first exec → timestamp last exec | > 40% |
| Reutilización de outputs vía chaining | execs con input_chain ≠ ∅ / total execs | > 70% (señal de adopción del workflow) |
| Operadores únicos activos / semana | distinct user en agent_executions | medirlo desde día 1 |

---

## Decisiones de diseño explícitas (para no re-discutir)

1. **No hay estado "global" de ticket en Stacky Agents.** El estado vive en ADO; nosotros lo leemos como referencia pero no lo escribimos hasta que el humano lo apruebe.
2. **No hay "siguiente agente recomendado" automático.** Hay packs guiados, pero la UI no asume orden.
3. **El historial es por ticket, no por proyecto.** No mezclamos ejecuciones de tickets distintos en una vista única (filtro opcional sí, default no).
4. **Los outputs se almacenan completos en BD** — no por referencia a archivos. La trazabilidad debe sobrevivir cambios de filesystem.
5. **El sistema no edita código.** El agente Developer prepara cambios; el commit lo hace el humano (o un job aparte que el humano dispara).
