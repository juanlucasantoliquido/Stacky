# 04 — Flujos de interacción

> Documentamos los **journeys reales** del operador. Cada flujo tiene: trigger, pasos, qué ve, qué decide, edge cases.

---

## Flujo 0 — Team Screen: asignar empleado a un ticket → VS Code Chat

**Trigger:** el operador abre la app y quiere trabajar un ticket con un agente específico. Es el flujo por defecto para la mayoría de los usuarios.

```
1. Abre app → ve Team Screen
   └─ grid de EmployeeCards con avatares pixel art, nombre y rol

2. Click en "Asignar Ticket →" en la card del empleado deseado (ej: Carlos — Technical)
   └─ se abre AgentLaunchModal

3. En el modal:
   a. Campo de búsqueda de ticket (debounce sobre GET /api/tickets)
   b. Selecciona el ticket de la lista (ADO ID + título + tipo)
   c. (Opcional) escribe un mensaje inicial en el campo de texto

4. Click "OK → Chat ✦"
   └─ POST http://localhost:5052/open-chat
      { agent_name: "TechnicalAnalyst.agent.md",
        message: "#ADO-1234 RF-008 nuevo flujo de cobros\n<mensaje opcional>" }
   └─ VS Code Copilot Chat se abre con @TechnicalAnalyst y el contexto del ticket

5. La conversación continúa en VS Code Chat (nativo)
```

**Edge cases:**
- Bridge no activo (puerto 5052 no responde): banner rojo en modal "La extensión VS Code no está activa. Iniciá VS Code con la extensión Stacky Agents instalada."
- Ticket no encontrado: estado vacío en la lista con copy "No se encontraron tickets. Verificá el ID o buscá por título."
- Equipo vacío: Team Screen muestra estado vacío con CTA "Agregá tu primer empleado".

---

## Flujo 0b — Armar el equipo (primera vez)

**Trigger:** el operador llega por primera vez y el equipo está vacío.

```
1. Ve Team Screen con estado vacío + botón prominente "+ Agregar empleado"

2. Click "+ Agregar empleado"
   └─ TeamManageDrawer se abre desde la derecha
   └─ lista todos los .agent.md disponibles en %APPDATA%/Code/User/prompts

3. Para cada agente que quiere en su equipo:
   a. Toggle/checkbox del agente
   b. AvatarPicker se expande inline
      └─ elige avatar de galería (15-20 personajes pixel art) o sube imagen propia
         (FileReader → canvas 64×64 → pixelado nearest-neighbor → base64)
   c. (Opcional) campo "Apodo" (ej: "Carlos") y "Rol" (ej: "Analista Senior")
   d. Confirmar

4. Cierra drawer
   └─ Team Screen muestra los agentes agregados como EmployeeCards

Persistencia: preferences.ts en localStorage — survives page reload.
```

---

## Flujo 0c — Editar un empleado

**Trigger:** el operador quiere cambiar el avatar, apodo o rol de un agente del equipo.

```
1. En la EmployeeCard, click en menú kebab (⋮) → "Editar"
   └─ EmployeeEditDrawer se abre

2. Modifica:
   ├─ Apodo
   ├─ Rol
   └─ Avatar (AvatarPicker completo)

3. Click "Guardar"
   └─ persiste en localStorage
   └─ card se actualiza en tiempo real
```

---

## Flujo 1 — Ejecución única de un agente (Workbench)

**Trigger:** el operador llega con un ticket y quiere correr un solo agente.

```
1. Abre app
   └─ ve TicketSelector con su lista de tickets en curso

2. Click en ADO-1234
   └─ el centro muestra metadata del ticket
   └─ el historial (derecha) muestra ejecuciones previas (puede estar vacío)

3. Click en AgentCard "Technical"
   └─ el editor se puebla con auto-fill:
       · ticket metadata
       · análisis funcional aprobado más reciente (si existe)
       · documentación técnica selectiva sugerida
   └─ panel output muestra "Press Run"

4. Operador revisa el contexto
   ├─ ok → click Run
   └─ falta algo → edita el bloque "Notas adicionales" y/o
                   marca/desmarca archivos en "Documentación técnica"

5. Click Run
   └─ botón pasa a "Running"
   └─ logs panel se abre y empieza a streamear
   └─ output panel muestra "✦ generando análisis técnico..."
       (texto incremental si streaming, spinner con etapa si no)

6. Output completo
   └─ output renderizado como markdown
   └─ aparecen botones: Approve | Edit & Re-run | Send to ADO | Discard

7. Operador decide
   ├─ Approve         → exec marcada como ✓ en historial
   ├─ Edit & Re-run   → editor se vuelve a abrir con el contexto previo,
                        operador ajusta, click Run → nueva exec en historial
   ├─ Send to ADO     → llama a /api/executions/:id/publish-to-ado
                        (publica el comentario en la Task ADO)
   └─ Discard         → exec marcada como ✗
```

**Edge cases:**
- Sin auto-fill disponible (primer agente del ticket): bloques `[auto]` vacíos pero el editor funciona igual.
- Token overflow: el botón Run se deshabilita; tooltip explica qué bloque sacar.
- Agente devuelve error: output panel muestra el error en card roja, logs auto-expanded, botón Retry.

---

## Flujo 2 — Re-run con edición

**Trigger:** una exec anterior tiene un output "casi bien" pero falta un detalle.

```
1. Operador click en una fila del historial (ej. exec #21)
   └─ output panel muestra ese output en modo lectura
   └─ aparece banner: "Viendo ejecución pasada — [Clone & edit]"

2. Click "Clone & edit"
   └─ el editor se carga con EXACTAMENTE el contexto que se mandó en #21
   └─ banner pasa a: "Editando clon de #21 — los cambios crearán exec #N"

3. Operador modifica
   └─ ej: agrega un archivo más al bloque de docs
   └─ ej: agrega una nota explicando qué cambiar

4. Click Run
   └─ se ejecuta una exec NUEVA (no se sobreescribe la #21)
   └─ historial muestra ambas; #21 marcada como "→ ver #N"
```

**Por qué crear nueva fila y no sobreescribir:** auditabilidad. Si el operador descubre que la exec previa era mejor, tiene la opción de volver. La inmutabilidad es no-negociable.

---

## Flujo 3 — Comparación side-by-side

**Trigger:** dos ejecuciones del mismo agente en el mismo ticket — el operador quiere comparar.

```
1. Operador en exec #22 (Technical, fallida) → ve botón "[Diff vs #21]"
   (sólo aparece si hay otra exec del mismo agente en el ticket)

2. Click "Diff vs #21"
   └─ output panel se divide en 2 columnas
   └─ izquierda: #21
   └─ derecha: #22 (la activa)
   └─ diff por línea estilo GitHub

3. Operador puede:
   ├─ Approve la #22 → cierra diff, marca aprobada
   ├─ Volver a #21 como activa → "Set #21 as latest approved"
   └─ Crear exec #23 → "Clone & edit" desde la versión preferida
```

---

## Flujo 4 — Context chaining manual

**Trigger:** el operador quiere alimentar al Technical con el output del Functional, pero no a ciegas.

```
1. Operador selecciona ticket + agente "Technical"

2. Editor abre con auto-fill
   └─ bloque "Análisis funcional aprobado" se rellenó con la última exec
      Functional aprobada (#20)

3. Operador puede:
   ├─ Aceptar (default — solo deja el bloque visible)
   ├─ Cambiar a otra exec Functional anterior (dropdown en el bloque)
   ├─ Editar el contenido del bloque (textarea expandida)
   └─ Sacar el bloque entero (×) si no lo quiere

4. El bloque queda visible: el operador SABE qué le mandó al agente
```

**Diferencia con pipeline:** acá el chaining es **explícito y editable**, no automático y opaco. El humano siempre ve qué pasa.

---

## Flujo 5 — Agent Pack (Desarrollo guiado)

**Trigger:** el operador tiene un Epic recién aprobado y quiere correr el flujo completo, pero validando paso a paso.

```
1. Operador click "▶ Desarrollo" en panel Packs
   └─ modal: descripción del pack + checkboxes de opciones
       ☐ Skip si ya hay output aprobado
       ☑ Detener al primer error
   └─ click "Iniciar pack"

2. Banner superior aparece:
   ┌─────────────────────────────────────────────────────────┐
   │ Pack Desarrollo — paso 1/4 — Functional   [Pausar]      │
   │ ● Functional  ○ Technical  ○ Developer  ○ QA            │
   └─────────────────────────────────────────────────────────┘

3. El editor se pre-carga con el contexto del paso 1 (Functional).
   └─ Operador revisa, ajusta, click Run.

4. Output del Functional listo
   └─ aparecen 2 botones nuevos: [Approve & Continue] [Approve & Pause]
       · Continue → marca aprobado, AVANZA al paso 2 con auto-chain
       · Pause    → marca aprobado, queda en pausa (operador puede tomar
                   un café y volver — el pack se mantiene en estado paused)

5. Si el pack continúa:
   └─ paso 2 (Technical), pre-cargado con OUTPUT del paso 1 chained
   └─ ciclo igual

6. Al final del paso 4 (QA):
   └─ banner se cierra
   └─ resumen: "Pack completado — 4 ejecuciones en 12min"
   └─ link a la vista resumen del ticket con todas las exec del pack
```

**Edge cases:**
- Paso falla → si "detener al primer error" está activo, banner muestra "Pack pausado por error en paso 2 — [Retry] [Edit] [Abandon pack]".
- Operador pausa y vuelve días después → el pack persiste, se reanuda donde quedó.
- Operador cierra la tab → al volver, banner muestra "Pack en curso desde hace 2h — [Resume] [Discard]".

---

## Flujo 6 — Cancelar una ejecución en curso

**Trigger:** el agente está tardando demasiado o el operador se dio cuenta que el contexto está mal.

```
1. Run iniciado, botón muestra "Running" con icono de stop pequeño.

2. Click stop:
   └─ confirma "¿Cancelar ejecución? Los logs hasta ahora se guardan."
   └─ Sí → backend mata la subprocess o cancela el await del LLM
        └─ exec queda como "cancelada" en historial (nuevo estado, no error)
   └─ No → sigue corriendo
```

**Importante:** los logs y el contexto se guardan. Una exec cancelada sirve como referencia (ej: "ya intenté así y tardó demasiado, el contexto era el problema").

---

## Flujo 7 — Onboarding (primera vez)

**Trigger:** primer login del operador.

```
1. Modal de bienvenida (no bloqueante):
   "Hola — Stacky Agents es tu workbench. Acá vos elegís qué agente
    correr y cuándo. ¿Querés un tour rápido?"
   [ Tour (60s) ]   [ Skip ]

2. Si tour:
   ▸ Paso 1: spotlight en TicketSelector — "Acá ves tus tickets."
   ▸ Paso 2: spotlight en AgentSelector — "Elegí qué agente correr."
   ▸ Paso 3: spotlight en Editor — "Esto es lo que recibe el agente.
              Editalo si querés."
   ▸ Paso 4: spotlight en Run — "Cuando estés listo, click."

3. Cierra tour → estado normal.
```

**Por qué corto:** el operador es técnico y tiene experiencia con Stacky Pipeline. No necesitamos explicarle qué es un ticket. Sólo qué cambió.

---

## Flujo 8 — Operador entra a un ticket que otro estaba trabajando

**Trigger:** colaboración. Dos operadores miran el mismo ticket.

```
1. Operador A está corriendo exec #23.

2. Operador B abre el mismo ticket.
   └─ Sidebar muestra "👤 ana@ está viendo este ticket"
   └─ Si A tiene una exec corriendo: "▶ exec #23 en curso por ana@"

3. Operador B puede:
   ├─ Mirar el progreso (logs en vivo, read-only) — sin disparar nada
   └─ Iniciar otra exec en paralelo (otro agente o el mismo) — se permite,
      pero la UI advierte: "Otra exec en curso — ¿continuar?"
```

**Por qué permitirlo en paralelo:** el sistema no asume orden. Si dos personas quieren explorar al mismo tiempo, está bien. La inmutabilidad del historial lo soporta.

---

## Estados de error y recuperación

| Origen del error | Qué muestra la UI | Acción del operador |
|---|---|---|
| Backend caído (no responde a `/api/agents/run`) | Toast rojo persistente: "No hay conexión con backend. Reintentar." | Reintentar; ver consola si persiste |
| LLM timeout (>120s sin respuesta) | Output panel: "El agente no respondió. Esto suele pasar con contextos muy grandes." | Edit & Re-run con contexto reducido |
| LLM error 429 (rate limit) | Toast: "Rate limit. Reintenta en N segundos." con countdown | Esperar |
| Agent devuelve output malformado | Card amarilla: "El output llegó pero no respeta el template." con preview crudo | Approve manual o Re-run |
| Conflicto de exec en paralelo | Banner informativo, no bloquea | Decidir |

---

## Lo que NO hace la UI (decisiones explícitas)

1. **No avanza estados ADO automáticamente.** Hay un botón explícito "Send to ADO" por exec aprobada. El operador decide.
2. **No borra ejecuciones.** Sólo se pueden marcar como descartadas (✗). El historial es permanente.
3. **No fusiona ejecuciones.** Si dos execs son válidas, ambas quedan; el operador elige cuál enviar a ADO.
4. **No corre dos execs en paralelo del mismo agente sobre el mismo ticket sin warning.** Se permite pero se advierte.
5. **No oculta el prompt final que se manda al LLM.** Hay un toggle "ver prompt completo" que muestra exactamente qué se enviará. Tranquilidad para auditoría.
