# Stacky Agents — Plan de Adopción para Devs (Contribución)

> **Complemento de `PRODUCCION_PLAN.md`.**
> Ese plan cubre lo *bloqueante* (seguridad, empaquetado, CI). Este cubre lo
> que hace falta para que, una vez instalado, **el dev no pueda dejar de usarlo**.
>
> Objetivo: que abrir Stacky sea más rápido y satisfactorio que abrir VS Code en frío.
> Intuitivo, rápido, *game changer*, adictivo — y profesional.

---

## Cómo leer este documento

Para cada una de las 20 contribuciones vas a encontrar:

- **🎯 Problema que resuelve** — qué duele hoy.
- **💡 Qué es** — la solución en una frase.
- **🖼️ Cómo se ve** — descripción visual del cambio.
- **📖 Ejemplo concreto** — un caso de uso narrado paso a paso.
- **⚙️ Cómo se implementa** — archivos a tocar.
- **✅ Lo querés si...** / **❌ No lo querés si...** — para que decidas.

Al final hay un **resumen rápido para decidir sí/no por cada uno**.

---

## Diagnóstico honesto

Stacky Agents hoy tiene **52 moats**, multi-tracker, packs, VS Code bridge, SSE,
extensión, observabilidad. Es un producto técnicamente completo. Y aún así, un
dev nuevo puede abrirlo y **no entender qué hacer en los primeros 3 minutos**.

El problema no es funcionalidad. Es **fricción de adopción**: el dev entra, no
sabe por dónde empezar, no obtiene un "wow", cierra la pestaña y vuelve a
trabajar como antes. Ese es el modo en que mueren las herramientas internas.

Lo que falta no es código de features — es **diseño del primer día**, **rituales
de uso diario** y **señales de victoria** que hagan que el dev vuelva mañana sin
que nadie se lo recuerde.

---

# Pilar 1 — Primer-Wow en 5 minutos

**Hipótesis:** si un dev no obtiene un output útil en su *primera* sesión, no
hay segunda sesión. Hoy depende de que el dev lea el README y conecte ADO antes
de ver algo funcionar. Eso es ya demasiado.

---

## C1 — Tour interactivo "Tu primer ticket"

### 🎯 Problema
Hoy el dev abre Stacky, ve la Team Screen con 5 avatares pixel-art y un botón
"Workbench". No sabe si tiene que crear un proyecto primero, conectar ADO,
elegir un agente, qué es un "pack"… Termina yéndose a leer documentación o
preguntando por Teams.

### 💡 Qué es
Una guía paso a paso *encima* de la UI real (no un PDF aparte, no un video).
Es como cuando abrís Notion o Linear por primera vez: una flechita y un
cartelito te muestran qué hacer.

### 🖼️ Cómo se ve
Un overlay semi-transparente oscurece la pantalla salvo *un* elemento (por
ejemplo, la carta del agente "Business"). Al lado aparece una burbuja blanca
con texto:

```
┌─────────────────────────────────┐
│  Paso 1 de 15                   │
│                                 │
│  Estos son tus agentes —        │
│  pensálos como empleados.       │
│  Cada uno hace una cosa.        │
│                                 │
│  [Saltar tour]  [Siguiente →]   │
└─────────────────────────────────┘
```

15 pasos cortos: te muestran qué es un agente, cómo elegir un ticket, qué pasa
al hacer click, cómo se lee el output, dónde está el historial, qué es un pack.
Termina con: *"Listo. Acabás de hacer correr tu primer agente en 4'12''. Si
querés repetir esto en otro ticket, hacé clic acá."*

### 📖 Ejemplo concreto
Lunes, 09:15. Juan, dev nuevo en el equipo, instala Stacky. Lo abre. En vez de
quedarse mirando los 5 avatares sin entender, una burbuja le dice *"Hola Juan,
te muestro cómo cerrar un ticket con esto en 4 minutos"*. Acepta. A las 09:19
ya cerró un ticket sandbox (ver C2). A las 09:30 está aplicándolo a su primer
ticket real.

Sin el tour, Juan se hubiera ido a leer documentación o hubiera preguntado en
Teams, y probablemente no habría vuelto a abrir Stacky esa semana.

### ⚙️ Cómo se implementa
- Librería: `react-joyride` (5kb, MIT, soporta steps anidados).
- Componente nuevo: `frontend/src/components/OnboardingTour.tsx`.
- Gate: en `pages/TeamScreen.tsx` lee `preferences.json:first_run`. Si es
  `true`, lanza el tour y lo marca `false` al terminar (o skippear).
- Métrica: cada paso loguea a `system_logs` con `event=onboarding_step_N` para
  ver dónde abandona la gente.

### ✅ Lo querés si
Tu equipo va a tener *más de 1 dev nuevo* usando Stacky en el próximo año.

### ❌ No lo querés si
Solo lo van a usar 2 personas que ya saben cómo funciona. Ahí es overkill.

---

## C2 — Sandbox de ticket falso

### 🎯 Problema
El primer ticket que un dev tiene a mano es uno real, con presión real. Probar
los agentes ahí es arriesgado: ¿y si comentan algo raro en ADO? ¿Y si tocan el
código? Resultado: el dev no prueba.

### 💡 Qué es
Stacky viene con un proyecto **fake** llamado `__demo__` que tiene 3 tickets
inventados, ya con análisis funcional escrito, código de ejemplo, etc. Es un
laboratorio para experimentar sin tocar nada real.

### 🖼️ Cómo se ve
En el dropdown de proyectos (arriba a la izquierda) aparece un proyecto con un
ícono distinto (🧪 o un sticker "DEMO"). Al seleccionarlo, los tickets son
inventados: *"T-DEMO-001 — Implementar login con Google"*, *"T-DEMO-002 — Bug
en el carrito de compras"*, etc.

Cuando el dev ya conectó su primer proyecto real, aparece arriba un banner
*"¿Ocultar proyecto demo?"* con un botón.

### 📖 Ejemplo concreto
María quiere probar el agente Developer pero le da miedo que toque commits
reales. Cambia al proyecto `__demo__`, elige T-DEMO-002, le da Run, ve que el
agente propone cambios en un archivo `cart.js` ficticio, lee el resultado,
descarta. Cero riesgo. 10 minutos después, ya entiende cómo funciona y lo
prueba en un ticket real con confianza.

### ⚙️ Cómo se implementa
- Backend: `services/demo_seed.py` (nuevo). Al arrancar, si no existe el
  proyecto `__demo__`, lo crea con fixtures hardcodeadas en JSON.
- Los agentes en modo demo usan outputs cacheados (no llaman al LLM real para
  no gastar tokens). Reusa la infra de FA-31 (output cache).
- Botón "Ocultar demo" en el dropdown de proyectos.

### ✅ Lo querés si
Querés que el dev se atreva a hacer click el primer día sin miedo.

### ❌ No lo querés si
Te molesta tener un proyecto fake en producción, aunque sea opcional.

---

## C3 — Health-check visual antes del primer click

### 🎯 Problema
El plan de producción ya menciona `/diagnostics` (§13). Pero hoy, si el bridge
de VS Code está caído o el PAT de ADO expiró, el dev se entera **cuando hace
click en Run y falla**. Frustrante. Pierde confianza en la herramienta.

### 💡 Qué es
Antes de dejarte hacer el primer click, Stacky te muestra un *semáforo* arriba.
Si todo está verde, ni lo ves. Si hay algo rojo, te lo dice con palabras
humanas y un solo botón para arreglarlo.

### 🖼️ Cómo se ve
Cuando todo está OK: nada (un puntito verde discreto en una esquina, opcional).

Cuando hay un problema:

```
┌───────────────────────────────────────────────────────────┐
│ ⚠ Stacky no puede conectar a Azure DevOps                 │
│   El token expiró el 2026-05-20.                          │
│   [Renovar token]  [Detalles]  [Cerrar]                   │
└───────────────────────────────────────────────────────────┘
```

El botón **Renovar token** abre directamente el modal correcto, ya con el
campo enfocado. No "leé los logs", no "abrí settings.json". Una acción, un click.

### 📖 Ejemplo concreto
Lunes 09:00. Lucas abre Stacky. Banner amarillo: *"VS Code no tiene la
extensión Stacky instalada. [Instalar ahora]"*. Click. 5 segundos después, todo
verde. Lucas no se enteró nunca de que existía un puerto 5052 ni un .vsix.

Sin esto: Lucas hace click en Run, ve error críptico, abre logs, busca en
Teams, alguien le dice "instalá la extensión", se frustra.

### ⚙️ Cómo se implementa
- Backend: ya existe `/api/health`. Sumar `/api/diagnostics` que retorne un
  array `{check, status, fix_action}`.
- Frontend: `components/HealthBanner.tsx` (nuevo) que hace polling cada 30s y
  muestra el primer check rojo.
- Cada `fix_action` mapea a una función del frontend: abrir un modal, ejecutar
  una llamada a `/api/projects/:id/refresh-auth`, etc.

### ✅ Lo querés si
Sí. Esto es básico. No tiene contra.

### ❌ No lo querés si
(No hay buen motivo para no quererlo.)

---

# Pilar 2 — Intuición (todo descubrible sin manual)

## C4 — Command Palette global (`Ctrl+K`)

### 🎯 Problema
Stacky tiene 5 agentes, 5 packs, múltiples páginas, varios proyectos. Para
llegar a algo específico hay que navegar con el mouse: abrir dropdown, scrollear,
hacer click. Para un dev power-user, eso es lentísimo. Para un dev casual, es
*ruido visual* que esconde lo importante.

### 💡 Qué es
Apretás `Ctrl+K` desde cualquier pantalla y se abre una caja de búsqueda que te
deja **hacer cualquier cosa** tipeando. Es el patrón de Linear, Raycast, GitHub,
Slack, VS Code, Notion. Una vez que un dev lo prueba, ya no quiere usar otra
cosa.

### 🖼️ Cómo se ve
```
┌──────────────────────────────────────────────┐
│  🔍  dev t-170                               │
├──────────────────────────────────────────────┤
│  🤖  Correr Developer en T-170               │
│  🎫  Ir al ticket T-170                      │
│  📜  Ver historial de T-170                  │
│  📦  Pack Desarrollo en T-170                │
└──────────────────────────────────────────────┘
   ↑↓ navegar    ↵ ejecutar    Esc cerrar
```

Mientras tipeás, los resultados se filtran. `Enter` ejecuta el primero. Es
*fuzzy*: "qa 170" encuentra "Correr QA en T-170".

### 📖 Ejemplo concreto
Ana está en medio de revisar un PR. Necesita ver qué hizo el agente Functional
en T-185. En vez de: minimizar VS Code → abrir Stacky → dropdown proyecto →
click en tab Executions → buscar 185 → filtrar por Functional → click... hace:
`Ctrl+K`, tipea "func 185", `Enter`. 2 segundos.

A los 3 días Ana usa `Ctrl+K` para **todo**. A los 7 días lo usa también para
cambiar de proyecto, buscar tickets, lanzar packs. Stacky se vuelve una
extensión de su teclado, no una app que abre con el mouse.

### ⚙️ Cómo se implementa
- Librería: `cmdk` (10kb, MIT, mantenida por Vercel).
- Componente nuevo: `components/CommandPalette.tsx`.
- Hook global en `App.tsx` que escucha `Ctrl+K`/`Cmd+K`.
- Indexa en memoria al cargar: agentes, tickets sincronizados, packs, proyectos,
  últimas 50 ejecuciones. Re-indexa cada vez que cambia el proyecto.

### ✅ Lo querés si
Tu equipo tiene devs que valoran teclado sobre mouse (la mayoría de los
backend/full-stack devs).

### ❌ No lo querés si
Tu audiencia es 100% no-técnica (no es el caso de Stacky).

---

## C5 — Empty states que enseñan, no que reprochan

### 🎯 Problema
Hoy si entrás a la pantalla de Executions sin ejecuciones previas, ves "No hay
ejecuciones" en gris. Si entrás a Packs sin packs corridos, lo mismo. Esas
pantallas vacías son **oportunidades perdidas**: el dev ve un dashboard
desierto y piensa "esto está vacío, capaz no es para mí".

### 💡 Qué es
Cada pantalla vacía se reemplaza por una tarjeta con: un dibujo (reusando los
avatares pixel-art para mantener identidad visual), una frase corta explicando
qué *aparecería* ahí, y un botón que ejecuta la acción típica.

### 🖼️ Cómo se ve
```
┌──────────────────────────────────────────────┐
│                                              │
│            (avatar pixel-art)                │
│                                              │
│       Acá vas a ver tus ejecuciones          │
│       de agentes. Cada vez que corras        │
│       uno, queda registro con su output.     │
│                                              │
│       [▶  Correr mi primer agente]           │
│                                              │
└──────────────────────────────────────────────┘
```

### 📖 Ejemplo concreto
Pedro entra a la pestaña "Packs" la primera vez. En vez de "No hay packs
corridos" en gris triste, ve una tarjeta amigable que dice *"Un pack es una
receta: corre 4 agentes en orden con un click. Probá el Pack Desarrollo"*. Le
da curiosidad. Click. Ya está usándolo.

### ⚙️ Cómo se implementa
- Componente nuevo: `components/EmptyState.tsx` con prop `variant`.
- Reemplazar cada `{items.length === 0 && <p>No hay…</p>}` por
  `<EmptyState variant="executions" />`.
- Estimado: 6-8 lugares en el frontend.

### ✅ Lo querés si
Querés que la app *enseñe* en vez de quedarse callada.

### ❌ No lo querés si
Preferís pantallas minimalistas tipo Apple Pro Tools (raro en herramientas
internas).

---

## C6 — Inline "Why this output?"

### 🎯 Problema
El agente devuelve un output. ¿Por qué dijo *eso*? ¿De dónde sacó la info?
¿Qué modelo usó? ¿Cuánto costó? Hoy esto está oculto en logs. El dev confía
o desconfía a ciegas. Eso es problemático para el tech lead que necesita
justificar el uso.

### 💡 Qué es
Un botoncito discreto al lado del output: **"Cómo se construyó esto"**. Click,
abre un drawer lateral con TODO lo que pasó: el prompt final, qué fuentes se
inyectaron (FA-01 cross-ticket, FA-15 glossary, FA-05 git context), qué modelo
se eligió y por qué, tokens consumidos, costo en USD, score de confianza.

### 🖼️ Cómo se ve
Output normal con un botón:
```
🚀 Output del Developer Agent                   [ⓘ Cómo se construyó]
─────────────────────────────────────────────────────────────────────
public class ClienteController : ApiController {
   ...
```

Al clickear, se desliza un drawer desde la derecha:
```
┌─────────────────────────────────────┐
│ ⓘ Provenance                    [×] │
├─────────────────────────────────────┤
│ Modelo: Sonnet 4.6                  │
│ Por qué: ticket=bug, ctx=3.4k       │
│ Tokens: 8.2k entrada / 1.1k salida  │
│ Costo: $0.041                       │
│ Confianza: 87%                      │
│                                     │
│ Fuentes usadas:                     │
│ ✓ Análisis técnico de T-168         │
│ ✓ Glosario del proyecto (47 terms)  │
│ ✓ Diff de git últimos 7 días        │
│ ✓ 3 ejecuciones similares pasadas   │
│                                     │
│ [Ver prompt final]                  │
└─────────────────────────────────────┘
```

### 📖 Ejemplo concreto
El tech lead Roberto revisa lo que el agente Developer propuso. Antes de
aprobar, abre "Cómo se construyó". Ve que el modelo fue Sonnet (no Haiku),
que se usaron 3 ejecuciones pasadas similares como referencia, que el score de
confianza es 87%. Aprueba con confianza. Si fuera 45% de confianza, lo pondría
en pausa y le pediría al dev re-correr con más contexto.

Sin esto, Roberto no aprueba (no entiende qué hizo el agente) o aprueba a
ciegas (peligroso).

### ⚙️ Cómo se implementa
- Backend: nuevo endpoint `GET /api/executions/:id/provenance` que arma este
  objeto a partir de los datos ya guardados.
- Frontend: extender `OutputPanel.tsx` con un botón y un `ProvenanceDrawer.tsx`.

### ✅ Lo querés si
Tenés tech leads o auditores que necesitan justificar el uso de IA.

### ❌ No lo querés si
Sos un equipo de 2 y la transparencia ya se da en charlas.

---

## C7 — Atajos contextuales tipo IDE

### 🎯 Problema
Para correr un agente hoy hacés click en un botón. Para re-correr, click. Para
cambiar de Workbench a Team, click. Devs son gente de teclado.

### 💡 Qué es
Atajos memorables que un dev acostumbrado a Vim/VS Code ya conoce:
- `Enter` corre el agente.
- `Shift+Enter` corre con edición del prompt antes.
- `Ctrl+R` re-ejecuta el último.
- `Ctrl+Shift+R` re-ejecuta cambiando de agente.
- `Ctrl+/` toggle Workbench ↔ Team Screen.
- `Esc` cierra el modal o drawer abierto.

### 🖼️ Cómo se ve
Cada botón muestra al hover un *chip* con el atajo:
```
[▶ Correr]  ⌨ Enter
```

Y hay un cheatsheet accesible con `?` (mismo patrón que GitHub).

### 📖 Ejemplo concreto
Marina está iterando: corre el Functional, no le gusta, edita el contexto, corre
de nuevo, no le gusta, edita, corre. Hoy son 3 clicks por iteración. Con atajos,
es `Ctrl+R` (re-correr) o `Shift+Enter` (re-correr con edición). 2 iteraciones
por minuto vs 30 segundos por iteración.

### ⚙️ Cómo se implementa
- Hook nuevo: `hooks/useKeyboardShortcuts.ts`.
- Tooltips con `<kbd>` HTML en cada botón principal.
- Modal `<ShortcutsCheatsheet />` activable con `?`.

### ✅ Lo querés si
Tu equipo es mayormente backend/full-stack (devs de teclado).

### ❌ No lo querés si
Es de bajo ROI si los devs solo usan Stacky 1-2 veces por día. Más atajos no
mueven la aguja en uso esporádico.

---

# Pilar 3 — Game Changer (las que hacen que recomienden esto a otros)

## C8 — "Continuar donde lo dejé"

### 🎯 Problema
Cerrás Stacky al final del día. Al día siguiente lo abrís y... estás en la
pantalla de Team Screen pelada. Tenés que volver a buscar en qué ticket
estabas, qué agente habías corrido, dónde quedó el output. Pérdida de contexto
+ frustración matutina.

### 💡 Qué es
Stacky recuerda exactamente en qué estabas. Al reabrirlo, te muestra una
tarjeta grande arriba: *"Volver al ticket T-172 — el Developer corrió hace 12
min, falta QA"*. Un click y estás exactamente donde lo dejaste.

### 🖼️ Cómo se ve
```
┌──────────────────────────────────────────────────────┐
│  📌 Continuar donde lo dejaste                       │
│                                                      │
│  Ticket T-172 — "Marca oficial en mantenedor"       │
│  Último agente: Developer (hace 12 min)              │
│  Próximo sugerido: QA                                │
│                                                      │
│  [Continuar]                          [Empezar fresco]│
└──────────────────────────────────────────────────────┘
```

### 📖 Ejemplo concreto
Carlos termina el día con un Developer corriendo en T-172. Cierra la laptop.
Al día siguiente abre Stacky a las 09:00. En vez de empezar de cero, ve la
tarjeta. Click. Está leyendo el output del Developer en 3 segundos. Decide:
"sí, está bien, le tiro QA". 4 minutos después, ticket cerrado.

Sin esto, Carlos perdería 5-10 minutos cada mañana solo *encontrando dónde
estaba*.

### ⚙️ Cómo se implementa
- Backend: nuevo `GET /api/session/resume` que devuelve `last_active_ticket`,
  `last_agent`, `last_execution_id`.
- Persistencia: nuevo campo `last_activity_at` en `tickets` ya existentes.
- Frontend: en `TeamScreen.tsx`, fetch al montar y mostrar `<ResumeCard />` si
  hay actividad < 24h.

### ✅ Lo querés si
Tu equipo usa Stacky en sesiones de >30 min (no como herramienta de drive-by).

### ❌ No lo querés si
El uso típico es muy esporádico (1 minuto cada 3 días).

---

## C9 — Agente "Explain my repo" (uno nuevo, no en los 52 existentes)

### 🎯 Problema
Dev nuevo en el equipo. Le toca un ticket. Antes de tocar código tiene que
entender el repo. Hoy: lee README (si existe), pregunta en Teams, mira git log
sin saber qué buscar. Onboarding al codebase = 1-2 días perdidos.

### 💡 Qué es
Un agente nuevo (no está en los 52 actuales) que toma el `workspace_root` +
`git log` + glosario del proyecto + estructura de carpetas, y devuelve un
**mapa mental** del repo en formato Mermaid + texto.

### 🖼️ Cómo se ve
Output del agente:
```
📊 Mapa del repo RSPACIFICO

Módulos principales:
  ├── ClientesAPI    ← más cambiado (47 commits últimos 30 días)
  ├── DireccionesAPI ← propietario: @juanluca (12 commits)
  └── ContactosAPI   ← código frío (sin tocar hace 4 meses)

[Diagrama Mermaid renderizado con FA-21]
  Clientes → Direcciones → Marcas
            ↘ Contactos

Archivos "hot" para el ticket T-185:
  • Tools/Stacky/.../ClienteController.cs (cambiado 8 veces)
  • DTOs/ClienteDTO.cs (cambiado 6 veces)

Tests con menor coverage:
  • DireccionesServiceTests.cs (23%)
```

### 📖 Ejemplo concreto
Sofía es nueva en el equipo. Le asignan T-185, un bug en el flujo de
direcciones. Antes de empezar, corre "Explain my repo" filtrado por el ticket.
En 30 segundos sabe: qué módulos toca, quién los conoce (para preguntar), qué
tests faltan, qué archivos suelen cambiar juntos. Empieza a programar con
contexto. Sin esto, hubiera tardado medio día en orientarse.

### ⚙️ Cómo se implementa
- Backend: nuevo `agents/explain_repo.py` siguiendo la base de `agents/base.py`.
- Reusa `services/git.py` (FA-05) y `services/glossary.py` (FA-15).
- Output usa renderer Mermaid (FA-21).

### ✅ Lo querés si
Tenés *cualquier* rotación de devs, contratistas, o gente que entra a partes
del código que no conoce.

### ❌ No lo querés si
Tu equipo es estable y todos conocen todo el codebase de memoria.

---

## C10 — "Asignación inversa": el ticket viene a vos

### 🎯 Problema
Hoy el flujo es: dev abre Stacky → busca tickets pendientes → elige uno. El
dev tiene que **recordar abrirlo**. Si no abre Stacky, no usa Stacky.

### 💡 Qué es
Stacky te avisa con una notificación nativa de Windows cuando hay un ticket
listo para vos. *"T-190 pasó a Code Review — ¿corremos QA?"*. Click en la
notif → Stacky se abre directamente en ese ticket.

### 🖼️ Cómo se ve
Notificación nativa Windows 10/11:
```
┌─────────────────────────────────┐
│ 🤖 Stacky Agents                │
│                                 │
│ T-190 listo para QA             │
│ "Validar formulario clientes"   │
│                                 │
│ [Abrir]  [Más tarde]            │
└─────────────────────────────────┘
```

### 📖 Ejemplo concreto
Daniel está programando otra cosa. A las 11:20 le aparece una notif: el
ticket T-190 que él tiene asignado pasó a "Ready for QA" en ADO. Click → Stacky
se abre con el QA Agent pre-seleccionado y T-190 cargado. Lo corre. 3 min
después, QA completo, devuelve a "Done". Sin la notif, Daniel se enteraría a
las 15:00 cuando alguien le preguntara.

### ⚙️ Cómo se implementa
- Backend: extender `services/ado_sync.py` (que ya hace polling) para detectar
  transiciones que matchean reglas configurables en `preferences.json`.
- Nuevo `services/desktop_notifier.py` usando `win10toast` (Python pip package).
- Click handler que abre `http://localhost:5050/?ticket=T-190`.

### ✅ Lo querés si
Los tickets cambian de estado durante el día y querés cerrar ciclos rápido.

### ❌ No lo querés si
Tu equipo ya tiene fatiga de notificaciones (Teams, email, Slack…). Es ruido
adicional.

---

## C11 — Replay de ejecuciones (timeline)

### 🎯 Problema
Cuando un agente devuelve un output extraño o muy bueno, querés saber **cómo
llegó ahí**. Hoy ves el resultado final pero no el proceso. ¿Qué archivos
leyó? ¿En qué orden? ¿Dudó en algún punto? Imposible saberlo.

### 💡 Qué es
Cada ejecución guarda un `events.jsonl` con todo lo que pasó. Hay un botón
**▶ Replay** que reproduce paso a paso como un video: tokens streaming en
tiempo (acelerado), herramientas invocadas, archivos tocados, decisiones.

### 🖼️ Cómo se ve
```
┌──────────────────────────────────────────────┐
│  Replay — Execution #842                     │
│  [▶ Play] [⏸] [⏩ 2x] [⏮ Reset]              │
│                                              │
│  ▓▓▓▓▓▓▓▓▓░░░░░░░░░░  00:12 / 00:34         │
│                                              │
│  [00:00] Inició Developer Agent              │
│  [00:03] Leyó archivo ClienteController.cs   │
│  [00:07] Buscó en glosario "marca oficial"   │
│  [00:11] Encontró 3 ejecuciones similares    │
│  [00:12] Empezó a escribir output...         │
└──────────────────────────────────────────────┘
```

### 📖 Ejemplo concreto
Diego está enseñando a un junior cómo usar agentes. En vez de mostrarle
outputs estáticos, le pone un Replay. El junior ve cómo el agente "razonó":
buscó contexto, dudó en una línea, eligió un enfoque. Es educativo, casi como
ver a un senior programar en pareja.

También útil: si un agente devolvió algo raro, hacés Replay y entendés el bug
del prompt en 30 segundos en vez de 20 minutos de investigación.

### ⚙️ Cómo se implementa
- Backend: persistir un `events.jsonl` por execution_id en `data/events/`. Ya
  hay logger; sumar wrapper que emite eventos estructurados a archivo.
- Frontend: `components/ReplayPlayer.tsx` que parsea el JSONL y lo reproduce
  con timing relativo.

### ✅ Lo querés si
Querés enseñar a juniors, hacer post-mortems de outputs raros, o defender
decisiones del agente en code review.

### ❌ No lo querés si
Es complejo (1 sprint) y solo lo van a usar power users.

---

## C12 — Comparador A/B de outputs (UI sobre FA-49 que ya existe)

### 🎯 Problema
FA-49 (parallel exploration) ya existe en el backend: corre el mismo agente N
veces en paralelo con variaciones. Pero la UI no lo muestra bien. Hoy ves 3
ejecuciones en la lista, las abrís de a una, comparás a ojo. Frustrante.

### 💡 Qué es
Una pantalla nueva donde lanzás 2 (o 3) ejecuciones del mismo agente en
paralelo y las ves *lado a lado* con highlight de diferencias. Elegís cuál
queda como ganador.

### 🖼️ Cómo se ve
```
┌──────────────┬──────────────┬──────────────┐
│ Variante A   │ Variante B   │ Variante C   │
│ Sonnet 4.6   │ Opus 4.7     │ Haiku 4.5    │
│              │              │              │
│ output A     │ output B     │ output C     │
│ (con diff    │ (con diff    │ (con diff    │
│  resaltado)  │  resaltado)  │  resaltado)  │
│              │              │              │
│ [✓ Elegir]   │ [Elegir]     │ [Elegir]     │
└──────────────┴──────────────┴──────────────┘
```

Al elegir, esa variante se marca y entrena automáticamente FA-12 (best-output
few-shot) para que la próxima vez Stacky use ese estilo.

### 📖 Ejemplo concreto
Florencia no está segura de qué modelo es mejor para el agente Functional.
Lanza una comparación: Sonnet vs Opus vs Haiku. Ve que Opus le da más
estructura pero Sonnet es más conciso. Elige Sonnet. Stacky aprende que para
*este* tipo de ticket, Sonnet es el preferido.

### ⚙️ Cómo se implementa
- El backend ya tiene FA-49.
- Frontend: nueva ruta `/compare`, componente `ABCompare.tsx`.
- Diff visual: librería `diff-match-patch` (Google, 30kb).

### ✅ Lo querés si
Te importa optimizar costo vs calidad por agente. Es el caso de tech leads.

### ❌ No lo querés si
No te interesa todavía meter el dedo en model routing — funcionalmente, los
defaults alcanzan.

---

# Pilar 4 — Adicción saludable (loops profesionales, no infantiles)

> **Aclaración importante:** "adictivo" acá no significa puntos, niveles ni
> emojis explotando. Significa **señales claras y honestas de progreso** que
> un dev profesional valora.

## C13 — Streak de tickets cerrados con asistencia de agentes

### 🎯 Problema
No hay feedback de "estoy mejorando" o "estoy usando esto consistentemente".
La herramienta se siente neutral, no acompaña.

### 💡 Qué es
Un contador discreto en la barra superior: *"🔥 5 días seguidos cerrando
tickets con agentes"*. Se resetea si pasa 1 día laboral sin cerrar nada con
Stacky.

### 🖼️ Cómo se ve
```
┌─────────────────────────────────────────────┐
│  Stacky Agents          🔥 5     ⚙ Settings │
└─────────────────────────────────────────────┘
```

Hover muestra:
```
5 días seguidos cerrando tickets con
asistencia de agentes. Mejor racha: 12.
```

Tipografía sobria, monoespaciada. **NO**: badges, fanfarrias, animaciones.

### 📖 Ejemplo concreto
Romina ve su streak crecer. No es competencia, es identidad: *"yo soy alguien
que usa esto"*. Después de 7 días sin abrir Stacky por vacaciones, ve que su
streak se resetea. Le molesta un poco. Vuelve a abrirlo. Cierra un ticket. Empezó
de nuevo. Es un ancla sutil.

### ⚙️ Cómo se implementa
- Backend: tabla `user_streaks` o columna `last_close_at` en `users`. Cron
  diario que evalúa.
- Frontend: componente `<StreakBadge />` en navbar.

### ✅ Lo querés si
Querés un ancla psicológica suave para uso recurrente.

### ❌ No lo querés si
Te suena gamificación barata (es legítimo el reparo).

---

## C14 — "Tiempo ahorrado" calculado, no inventado

### 🎯 Problema
Decir "los agentes te ahorran tiempo" sin números es propaganda. Los devs
detectan eso a kilómetros y dejan de creer. Resultado: no le pueden vender el
uso al equipo ni al jefe.

### 💡 Qué es
Para cada ticket cerrado con un pack, Stacky compara la duración real (desde
"In Progress" hasta "Done" en ADO) contra una **mediana histórica** del mismo
tipo de ticket sin agentes. La diferencia es el ahorro. Si es negativo, lo
dice (el agente fue más lento).

### 🖼️ Cómo se ve
Tarjeta semanal en el dashboard:
```
┌──────────────────────────────────────────────┐
│  📊 Esta semana                              │
│                                              │
│  Tickets cerrados con agentes:    7          │
│  Tiempo total:                    4h 12m     │
│  Baseline (sin agentes):          8h 50m     │
│  Ahorrado:                        4h 38m     │
│                                              │
│  (Calculado contra tickets similares del     │
│   último trimestre. Ver detalle.)            │
└──────────────────────────────────────────────┘
```

### 📖 Ejemplo concreto
Sebastián lleva la tarjeta a la 1:1 con su lead: *"Esta semana ahorré 4 horas
y media respecto a mi promedio histórico"*. Es un dato real, defendible.
Convierte a Stacky en un argumento medible — no un capricho.

### ⚙️ Cómo se implementa
- Backend: nuevo `services/savings_calculator.py`. Lee tickets cerrados con
  pack-assist + duraciones de ADO + mediana de tickets equivalentes sin
  asistencia (del último trimestre).
- Endpoint `GET /api/savings/weekly?user=…`.
- Frontend: tarjeta en `TeamScreen.tsx`.

### ✅ Lo querés si
Necesitás justificar el uso de Stacky con números reales al tech lead o sponsor.

### ❌ No lo querés si
Falta data histórica suficiente (necesitás al menos 30 tickets sin asistencia
de tipo comparable).

---

## C15 — Daily standup auto-generado

### 🎯 Problema
Todas las mañanas el dev abre 4 pestañas (ADO, Git, Teams, email) para
preparar su standup. 10-15 minutos. Es ritual repetitivo + alta fricción para
arrancar el día.

### 💡 Qué es
A las 09:00 (configurable), Stacky abre solo un modal con tu standup ya armado:
- En qué tickets avanzaste ayer.
- Qué bloqueos detectó (QA FAIL, tests rotos, comments sin responder).
- Sugerencias de PM Intelligence (ya existe en `11_PM_INTELLIGENCE_SUITE.md`).
- Botón **"Copiar para Teams"** que te da el texto formateado.

### 🖼️ Cómo se ve
```
┌──────────────────────────────────────────────┐
│  ☀️ Buen día, Juan. Tu standup está listo.   │
│                                              │
│  Ayer:                                       │
│  • Cerré T-170 (login Google)                │
│  • Avancé T-172 (validaciones marcas)        │
│                                              │
│  Hoy:                                        │
│  • Terminar T-172, falta QA                  │
│  • Empezar T-188 (asignado anoche)           │
│                                              │
│  Bloqueos:                                   │
│  • T-185 tiene QA FAIL desde hace 2 días     │
│                                              │
│  [Copiar para Teams]      [Editar]  [Cerrar] │
└──────────────────────────────────────────────┘
```

### 📖 Ejemplo concreto
Lucía llega a las 09:00 con su café. Abre Stacky. Standup listo. Copia. Pega
en el canal de Teams. Total: 30 segundos. Antes le tomaba 12 minutos. Esto
convierte a Stacky en una herramienta *del ritual matutino*, no opcional.

### ⚙️ Cómo se implementa
- Reusa lógica de `PM_COMMAND_CENTER_USAGE.md` y `11_PM_INTELLIGENCE_SUITE.md`.
- Frontend: `DailyStandupModal.tsx` con cron interno (setInterval que dispara
  a las 09:00 si no se mostró hoy).
- Configurable: hora, días de la semana, on/off.

### ✅ Lo querés si
Tu equipo hace daily standups (la mayoría de equipos ágiles).

### ❌ No lo querés si
No hay standups o son asíncronos sin formato.

---

## C16 — Notificación de "agente terminó"

### 🎯 Problema
Lanzás un agente que tarda 90 segundos. ¿Qué hacés? Mirás la pantalla esperando.
O hacés otra cosa y volvés tarde, perdiendo flujo. En ambos casos, mala UX.

### 💡 Qué es
- Sonido sutil al terminar (toggle off por defecto, opt-in).
- Flash del icono de taskbar de Windows.
- Badge con número en la extensión de VS Code.

### 🖼️ Cómo se ve
Mientras corre: status bar de VS Code muestra `🤖 1 running`. Al terminar:
`🤖 1 done` parpadea 3 veces.

Si está habilitado el sonido: un "ding" corto y elegante (no Mario coin).

### 📖 Ejemplo concreto
Joaquín lanza Developer en T-200, se va a revisar emails. El agente tarda 80
segundos. En el momento exacto que termina, oye un ding suave. Vuelve a
Stacky, lee el output. No perdió tiempo esperando ni tampoco perdió el contexto
porque se distrajo en otra cosa 10 minutos.

### ⚙️ Cómo se implementa
- `services/desktop_notifier.py` (compartido con C10).
- `vscode_extension`: `statusBarItem.text = `🤖 ${count} done``.
- Sonido: archivo `.mp3` corto (200ms) en `frontend/public/`.

### ✅ Lo querés si
Tus agentes tardan ≥30s típicamente.

### ❌ No lo querés si
La mayoría termina en < 5s (ahí no agrega valor).

---

# Pilar 5 — Profesional (que el lead lo apruebe sin dudar)

## C17 — Modo "auditoría legible" — Export PDF

### 🎯 Problema
Un agente toma una decisión importante. ¿Cómo se justifica eso en un PR? ¿En
una auditoría interna? ¿En un cliente exigente? Hoy se manda un screenshot o
se copia el texto. Poco profesional.

### 💡 Qué es
En cualquier ejecución, un botón **Exportar a PDF**. Genera un documento con:
- Header: proyecto, ticket, agente, modelo, timestamp, hash HMAC (FA-39).
- Body: prompt usado + output formateado.
- Footer: citaciones (FA-20) + firma del equipo.

### 🖼️ Cómo se ve
PDF generado, listo para adjuntar a un PR o un ticket:
```
═══════════════════════════════════════
   Stacky Agents — Audit Record
═══════════════════════════════════════
Proyecto:   RSPACIFICO
Ticket:     T-185
Agente:     Developer
Modelo:     Sonnet 4.6
Timestamp:  2026-05-23T11:24:00-03:00
Hash:       a3f2…b9c1  ← verificable contra
                        cadena HMAC

──── Prompt ────
[texto completo del prompt]

──── Output ────
[output formateado]

──── Fuentes ────
• Glosario v2.4
• Ticket T-168 (similar)
• git log --since=2026-04-01
```

### 📖 Ejemplo concreto
Tomás cierra un ticket crítico con asistencia de agente. El cliente pide
auditoría. Tomás exporta el PDF, lo adjunta al ticket, firmado y hash-eado.
Aprobación inmediata. Sin esto: una semana de back-and-forth justificando.

### ⚙️ Cómo se implementa
- Backend: `services/pdf_export.py` usando `weasyprint` o `reportlab`.
- Template HTML que se renderiza a PDF.

### ✅ Lo querés si
Tenés clientes/auditorías que exigen trazabilidad de decisiones de IA.

### ❌ No lo querés si
Tu uso es 100% interno y nadie pide papers.

---

## C18 — Cost cap por proyecto

### 🎯 Problema
FA-33 (cost preview) ya existe: te muestra cuánto va a costar. Pero no hay
límite. Un dev distraído podría correr un Opus 50 veces en un día y gastar
$200. El tech lead no tiene control.

### 💡 Qué es
Configurable por proyecto: cap mensual en USD. Alerta visual al 80%. Bloqueo
opcional al 100% (con override que pide motivo).

### 🖼️ Cómo se ve
En el modal de proyecto (que `PRODUCCION_PLAN.md` §4 ya extiende):
```
Cost cap mensual:  [$  50.00  ] USD
☑ Alertar al 80%
☐ Bloquear al 100%
```

En la app, indicador en la navbar:
```
💰 $32.15 / $50.00  ████████░░  64%
```

Al 80% se pone amarillo. Al 100% se pone rojo y bloquea (si está configurado).

### 📖 Ejemplo concreto
El lead Roberto pone $100/mes al proyecto piloto. A mitad de mes, ve que van
$78. Habla con el equipo: "estamos usando muchas variantes A/B, ¿es realmente
necesario?". Discusión productiva sobre eficiencia. Sin cap: hubieran terminado
en $300 sin enterarse.

### ⚙️ Cómo se implementa
- Columna `monthly_cap_usd` en tabla `projects`.
- `agent_runner.py` chequea pre-ejecución.
- Frontend: indicador en navbar, campos en modal de proyecto.

### ✅ Lo querés si
Querés gobierno de costos en LLMs.

### ❌ No lo querés si
El cap mensual del equipo es bajo y se controla manualmente sin problema.

---

## C19 — "Why this model?" — Explicabilidad del routing

### 🎯 Problema
FA-04 (multi-LLM routing) decide automáticamente qué modelo usar. Pero es una
caja negra. ¿Por qué Sonnet y no Opus? Si no lo entendés, no podés confiar ni
ajustar.

### 💡 Qué es
Junto al output, una línea breve: *"Se usó Sonnet 4.6 porque: ticket type=bug,
context size=3.4k tokens, drift score=low. Costo estimado: $0.04. Si querés
forzar otro modelo: [Opus] [Haiku]"*.

### 🖼️ Cómo se ve
Debajo del output:
```
ⓘ Modelo: Sonnet 4.6 ($0.04) — porque ticket=bug y contexto pequeño.
   [Re-correr con Opus]  [Re-correr con Haiku]
```

### 📖 Ejemplo concreto
Patricia ve que el QA Agent siempre usa Sonnet. Le interesaría probar Opus
para tickets críticos. Click en "Re-correr con Opus" en un ticket grande.
Compara mentalmente. Decide para qué casos vale la pena el upgrade. Aprendizaje
real, no decisión a ciegas.

### ⚙️ Cómo se implementa
- Extender respuesta de `agent_runner.py` con `routing_decision: {model, reason,
  cost_estimate}`.
- Frontend: mostrar en `OutputPanel.tsx` con dos botones de re-run.

### ✅ Lo querés si
Querés que los devs aprendan trade-offs costo/calidad, no solo confíen ciegos.

### ❌ No lo querés si
Querés que el routing sea totalmente automático y opaco (defendible también).

---

## C20 — Modo "Demo read-only" para mostrar a clientes

### 🎯 Problema
Mostrar Stacky a un cliente, a un candidato, en una reunión: arriesgás filtrar
data real (tickets internos, código privado) o gastar tokens reales en
ejecuciones de show. Resultado: nadie lo muestra.

### 💡 Qué es
Toggle en navbar: **Modo Demo**. En ese modo:
- Los agentes no llaman al LLM real — usan outputs cacheados (FA-31).
- Los datos visibles son del proyecto `__demo__` (C2).
- Un badge **"DEMO"** aparece en todos los outputs y la navbar.

### 🖼️ Cómo se ve
Navbar cambia de color (banda superior amarilla suave) cuando está activo:
```
═════════════ 🟡 MODO DEMO ═════════════
[resto de la UI normal]
```

Todos los outputs llevan watermark visible:
```
   ┌─────────────────────────────────┐
   │  D E M O  •  D E M O  •  D E M O│
   │   [output cacheado]             │
   │  D E M O  •  D E M O  •  D E M O│
   └─────────────────────────────────┘
```

### 📖 Ejemplo concreto
Pablo tiene que mostrar Stacky a un cliente potencial el viernes. Activa
modo Demo. Corre todos los agentes en vivo durante la demo. Los outputs salen
en 2 segundos (cacheados), no en 60. Cero riesgo de filtrar data interna. Cero
costo en tokens. Demo perfecta.

### ⚙️ Cómo se implementa
- Flag global `DEMO_MODE` en `store/preferences.ts` (frontend).
- `api/client.ts` intercepta y redirige a endpoints `/demo/*` que devuelven
  fixtures.
- Backend: `api/demo.py` (nuevo) con fixtures hardcodeadas.

### ✅ Lo querés si
Vas a mostrar Stacky externamente o entrenar gente nueva.

### ❌ No lo querés si
Es 100% interno y nunca lo van a mostrar a nadie de afuera.

---

# Pilar 6 — Métricas que validan que esto funciona

> Sin medición no hay adopción real. Si agregamos 10 cosas y no medimos cuáles
> funcionan, vamos a ciegas.

### Métricas mínimas a instrumentar

| Métrica | Cómo se calcula | Target | Qué mide |
|---|---|---|---|
| **TTFUO** | tiempo desde primer login hasta primer output aceptado | < 5 min p90 | Onboarding |
| **DAU/MAU** | activos diarios / mensuales | > 0.5 | Adicción saludable |
| **Agent-assisted close rate** | tickets cerrados con ≥1 ejecución / total | > 60% en 60 días | Adopción real |
| **Re-run rate** | re-runs / runs totales por agente | tendencia ↓ | Calidad de prompts |
| **Cost per closed ticket** | suma USD / tickets cerrados con asistencia | tendencia ↓ | Eficiencia |
| **NPS interno** | encuesta 1 pregunta cada trimestre | > 40 | Satisfacción |

### Dashboard `/admin/adoption`
Solo lo ve el tech lead (gate por `preferences.json:role === "lead"`). Una
pantalla con esos 6 números, evolución mensual y desglose por dev (anonimizable
si hay tema cultural).

---

# Pilar 7 — Lo que NO hay que hacer (importante)

- ❌ **No agregar otro moat técnico**. Ya hay 52. Un FA-53 hoy tiene ROI
  marginal *negativo*: más superficie, más bugs, menos foco. El usuario no
  pidió más features — pidió usar las que ya hay sin sufrir.
- ❌ **No gamificar con puntos, niveles o badges infantiles.** Esto es para
  devs profesionales, no Duolingo. Streaks discretos sí; XP, "level up", no.
- ❌ **No hacer un "modo experto" oculto.** Todo descubrible vía `Ctrl+K` o
  tour. Lo oculto es elitismo, no UX.
- ❌ **No mover Stacky a la nube todavía.** La promesa "corre en tu máquina"
  es parte del *trust*. Cloud es otro producto, otra conversación.
- ❌ **No empezar todas las 20 contribuciones a la vez.** Sprint 1 y 2 primero,
  medir, decidir el resto.

---

# Resumen rápido para decidir (acá decidís sí/no)

Marcá sí/no/quizás al lado de cada uno. Lo que quede en *sí* se vuelve sprint.

| # | Contribución | Esfuerzo | Impacto adopción | Decisión |
|---|---|---|---|---|
| C1 | Tour interactivo | M | 🔥🔥🔥 | ☐ Sí ☐ No |
| C2 | Sandbox demo | S | 🔥🔥 | ☐ Sí ☐ No |
| C3 | Health-check banner | S | 🔥🔥🔥 | ☐ Sí ☐ No |
| C4 | Command Palette `Ctrl+K` | M | 🔥🔥🔥 | ☐ Sí ☐ No |
| C5 | Empty states que enseñan | S | 🔥 | ☐ Sí ☐ No |
| C6 | "Why this output?" | M | 🔥🔥 | ☐ Sí ☐ No |
| C7 | Atajos teclado | S | 🔥 | ☐ Sí ☐ No |
| C8 | "Continuar donde lo dejé" | S | 🔥🔥🔥 | ☐ Sí ☐ No |
| C9 | Agente "Explain my repo" | L | 🔥🔥🔥 | ☐ Sí ☐ No |
| C10 | Notif inversa de ADO | M | 🔥🔥 | ☐ Sí ☐ No |
| C11 | Replay timeline | L | 🔥🔥 | ☐ Sí ☐ No |
| C12 | Comparador A/B (UI) | M | 🔥 | ☐ Sí ☐ No |
| C13 | Streak | S | 🔥 | ☐ Sí ☐ No |
| C14 | Tiempo ahorrado | M | 🔥🔥🔥 | ☐ Sí ☐ No |
| C15 | Daily standup | M | 🔥🔥🔥 | ☐ Sí ☐ No |
| C16 | Notif fin de ejecución | S | 🔥 | ☐ Sí ☐ No |
| C17 | Export PDF auditoría | M | 🔥🔥 | ☐ Sí ☐ No |
| C18 | Cost cap por proyecto | S | 🔥🔥 | ☐ Sí ☐ No |
| C19 | "Why this model?" | S | 🔥 | ☐ Sí ☐ No |
| C20 | Modo Demo read-only | M | 🔥🔥 | ☐ Sí ☐ No |

**Leyenda:**
- Esfuerzo: **S** (small, 1-3 días) · **M** (medium, 1 semana) · **L** (large, 2+ semanas).
- Impacto adopción: 🔥 bajo · 🔥🔥 medio · 🔥🔥🔥 alto.

---

# Mi recomendación si tuvieras que elegir 5

Si pudieras hacer solo 5 cosas de las 20, yo elegiría — por ROI puro:

1. **C3 Health-check banner** — bloqueante; sin esto la primera experiencia falla.
2. **C8 "Continuar donde lo dejé"** — barato, alto impacto en uso diario.
3. **C4 Command Palette** — vuelve a Stacky 10x más rápido para power users.
4. **C14 Tiempo ahorrado** — la única forma de defender ROI ante el sponsor.
5. **C15 Daily standup** — convierte a Stacky en ritual matutino imprescindible.

Con eso solo, Stacky pasa de "herramienta interna que algunos prueban" a
"app que el dev abre antes que VS Code".

---

# Cierre

Las 20 contribuciones se pueden hacer todas, ninguna, o solo las 5 críticas.
Lo importante es que vos decidas con criterio, no que aceptes una lista.

Si querés, te ayudo a:
1. Marcar el sí/no en la tabla arriba.
2. Ordenar las que dijiste sí en sprints concretos.
3. Empezar a implementar la primera ya mismo.

Decime qué te interesa y avanzamos.
