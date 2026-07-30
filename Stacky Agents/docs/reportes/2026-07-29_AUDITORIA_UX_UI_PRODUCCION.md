# Auditoría integral UX/UI — gate de producción

- **Fecha:** 2026-07-29
- **Alcance:** frontend (`Stacky Agents/frontend/src`), superficie API que lo alimenta (`Stacky Agents/backend/api`, `backend/services`), documentación canónica (`Stacky Agents/docs/sistema/`).
- **Método:** read-only sobre el árbol principal. Ningún hallazgo se acepta sin `archivo:línea` abierto de verdad; ningún número se acepta sin el comando que lo produjo (los comandos van citados junto al dato).
- **Perfil de corrida:** max (auditoría de gate; profundidad sobre economía de tokens).
- **Convención de etiquetas:** `[CÓDIGO]` confirmado en código · `[DOC]` confirmado en documentación · `[DRIFT]` código vs doc/comentario · `[HIPÓTESIS]` requiere paso manual (se indica cuál) · `[BUENA PRÁCTICA]` recomendación no derivada de un defecto observado.

> **Estado de este informe:** **PARCIAL pero coherente y utilizable.** Los ejes de navegación, cliente HTTP y manejo de errores, design system y tokens, accesibilidad de modales, acciones destructivas, autenticación, límites/planes, barridos de preparación para producción y observabilidad están **auditados y cerrados**. Los flujos de ciclo de vida del agente, integraciones externas, y grafo/RAG **no se auditaron**. Ver §8 "Áreas no cubiertas y por qué" para el detalle exacto, incluidas las limitaciones metodológicas.
>
> El veredicto de §1 es **firme respecto de lo verificado** y no se apoya en ninguna área pendiente: los 7 condicionantes P0 salen todos de hallazgos con `archivo:línea` abierto y comando mostrado. Un hallazgo bloqueante podría aún aparecer en las áreas no cubiertas; el veredicto se emite sobre la evidencia disponible, no sobre una cobertura total que esta corrida no alcanzó.

---

## Inventario base de la superficie auditada

| Métrica | Valor | Comando |
|---|---|---|
| Archivos `.tsx` en `frontend/src` | 286 | `find frontend/src -type f -name "*.tsx" \| wc -l` |
| Archivos `.ts` en `frontend/src` | 499 | `find frontend/src -type f -name "*.ts" \| wc -l` |
| Archivos `.css` en `frontend/src` | 198 | `find frontend/src -name "*.css" \| wc -l` |
| Pantallas (tabs de nivel superior) | 18 | lectura de `frontend/src/services/routes.ts:5-9` y `:15-22` |
| Flags en `FLAG_REGISTRY` | 403 | `grep -oE '\btype="[a-z]+"' backend/services/harness_flags.py \| sort \| uniq -c` |
| Documentos canónicos de sistema | 16 | `ls -1 docs/sistema/` |
| Informes previos en `docs/reportes/` | 1 | `ls -1 docs/reportes/` |

Desglose de los 403 flags por tipo (mismo comando): `bool` 294 · `int` 64 · `csv` 25 · `str` 10 · `float` 9 · `json` 1.

---

## 1. Resumen ejecutivo

### Estado general de UX/UI

Stacky Agents **no** es un prototipo, y conviene decirlo antes de la lista de defectos porque cambia cómo hay que leerla. Tiene un design system real con escalas completas de spacing, tipografía, radios, sombras y motion; una librería de 16 primitivas de UI incluyendo `Skeleton` y `Spinner`; un sistema de diálogos promise-based en cola con *settle* idempotente, focus-trap, restore-focus e `inert` sobre el fondo; confirmación obligatoria en acciones destructivas con el foco puesto deliberadamente en *Cancelar* y type-to-confirm en el despliegue; un router tipado propio con round-trip idempotente; un error boundary por página que evita el pantallazo blanco; tour de onboarding con detección real de primera vez; tema claro completo; modo de densidad compacta; foco visible global por teclado y `prefers-reduced-motion` respetado. Y los barridos que suelen hundir un lanzamiento dieron limpio: **cero** diálogos nativos sin estilo, **cero** marcadores `TODO`/`FIXME` reales, ocho `console.*` todos justificados.

Esa base es mejor que la de la mayoría de los productos que llegan a un gate de producción. Por eso el veredicto no es NO-GO: **no falta construir, falta terminar de conectar lo construido.**

El problema **no** es falta de piezas: es **adopción desigual de las piezas que ya existen** y un puñado de defectos de arranque de aplicación que se disparan en el 100% de las cargas. La medida más clara de esa desigualdad: coexisten un sistema de tokens completo y **1314 colores literales** en CSS, más una librería de 16 primitivas y **723 estilos inline**. Los dos ejes de riesgo concentran casi todo el daño:

1. **El arranque de la app decide la navegación con 10 llamadas de red, y decide mal cuando la red tarda o falla.** Los 18 tabs nacen ocultos y se revelan por health-check. Eso rompe deep links, rompe el reload, y produce un cambio de arquitectura de información visible en cada carga.
2. **El cliente HTTP destruye los mensajes de error que el backend redacta con cuidado.** El backend emite `message` humano y `correlation_id`; `api.*` los aplasta en un string `"<status> <statusText>: <json crudo>"`. El resultado es que el operador ve texto técnico crudo — incluidos nombres de variables de entorno — en lugar de la frase accionable que el backend ya escribió.

Ninguno de los dos es un rediseño. Los dos son correcciones localizadas de alto rendimiento.

### Nivel de preparación para producción

**Apto con condiciones.** No encontré pérdida de datos silenciosa, ni acción destructiva sin confirmación en la superficie que alcancé a auditar, ni rutas rotas. Encontré defectos de arranque de frecuencia 100%, exposición de vocabulario interno al operador, y una brecha de accesibilidad y de responsive que hay que **decidir explícitamente** (asumir desktop-only es una decisión válida; dejarlo indefinido no lo es).

### Principales riesgos

- **R1 — Deep links y reload no funcionan en 12 de 18 pantallas.** Marcar `/devops` como favorito y volver mañana aterriza en Tickets, sin explicación. Frecuencia 100% en las pantallas afectadas.
- **R2 — La arquitectura de información cambia delante de los ojos del operador en cada carga**, y queda permanentemente en la versión vieja (plana, 18 botones con emoji) si un solo health-check falla. Dos modelos mentales del producto para el mismo usuario.
- **R3 — Errores técnicos crudos visibles al operador**, con nombres de variables de entorno (`STACKY_DB_COMPARE_ENABLED`) dentro del texto. 24 mensajes verificados.
- **R4 — Un backend colgado deja spinners infinitos**: no hay timeout en el cliente HTTP.
- **R5 — Atribución de autoría ficticia.** Todo el frontend se identifica como `dev@local` hardcodeado en el bundle, y el backend resuelve la identidad ausente a **seis** valores distintos según el módulo. Cualquier auditoría, métrica de adopción o `created_by` es indistinguible entre operadores.

### Principales oportunidades

- **O1** — El design system ya tiene escala de spacing, tipográfica, radios, sombras, motion y tema claro (`theme.css`). Falta *cobrar* esa inversión: la deuda está en los `.module.css` que no la usan, no en el sistema.
- **O2** — `rawGet`/`rawPost`/`rawPut` ya devuelven `errorBody` con `message` y `correlation_id` tipados. El contrato para errores accionables **ya está construido**; falta migrar los llamadores.
- **O3** — `PageErrorBoundary` ya publica al Centro de Actividad. Es el punto de enganche natural para telemetría de fricción, sin infraestructura nueva.
- **O4** — El health-check por feature ya existe y devuelve `flag_enabled` estructurado. Con un único endpoint agregado en lugar de 10 llamadas sueltas se arregla R1 y R2 de una vez.

### Recomendación

## `GO CONDICIONADO`

Condicionantes (todos verificados en código, todos localizados, ninguno requiere rediseño):

| # | Condicionante | Hallazgo | Por qué bloquea |
|---|---|---|---|
| C1 | Que un deep link / reload a una pantalla con gate aterrice en esa pantalla, no en Tickets | H-01 | Rompe favoritos, historial y compartir URL en 12 de 18 pantallas |
| C2 | Que la app no cambie de arquitectura de navegación después del primer paint, y que una falla de health no degrade silenciosamente a la nav vieja | H-02 | Dos IAs distintas para el mismo operador, sin señal de que algo falló |
| C3 | Que el operador no vea `"500 INTERNAL SERVER ERROR: {...}"` ni nombres `STACKY_*`; que se use el `message` que el backend ya redacta | H-03, H-06 | Errores no accionables y filtración de vocabulario interno |
| C4 | Timeout en el cliente HTTP | H-04 | Un backend colgado deja la UI en spinner indefinido |
| C5 | Que ningún tab quede inalcanzable por recorte horizontal de la nav | H-05 | Funcionalidad presente pero no clickeable |
| C6 | Decisión explícita y documentada sobre tema claro y sobre responsive (soportar o declarar no soportado y ocultar el toggle) | H-07, H-10 | Hoy el tema claro deja la nav ilegible; el soporte responsive es indefinido |

**No** son condicionantes (los dejo fuera a propósito, con fundamento): la ausencia de login/roles es una decisión de producto coherente con el despliegue mono-operador (§3.1); la ausencia de planes comerciales/cuotas no es un defecto sino un encuadre equivocado del pedido (§3.15).

---

## 2. Hallazgos críticos

### H-01 · Deep link y reload rebotan a Tickets en 12 de 18 pantallas — `[CÓDIGO]`

- **Pantalla/flujo:** todas las pantallas con gate: `devops`, `dbcompare`, `costcenter`, `planes`, `evolution`, `migrador`, `incidencias` (gate por flag) + `team`, `pm`, `logs`, `docs`, `memory` (gate por secciones de UI).
- **Problema:** los 18 tabs nacen **ocultos** y se revelan recién cuando responde un health-check. Un efecto de redirección corre en el mismo montaje y, al ver el gate en `false`, reescribe la ruta a `tickets`.
- **Evidencia:**
  - Estado inicial `false` de cada gate: `frontend/src/App.tsx:76`, `:78`, `:80`, `:83`, `:97`, `:99`, `:100`, `:102`.
  - Efecto de rebote: `frontend/src/App.tsx:264-277` — `else if (tab === "devops" && !devopsEnabled) selectTab("tickets");` y once condiciones análogas.
  - El gate se resuelve por red, después del montaje: `frontend/src/App.tsx:143-167` (ocho `probeFlagHealth`).
  - Latencia antes de rendirse: `probeFlagHealth` hace 2 reintentos con backoff 400ms → 800ms (`frontend/src/utils/flagHealth.ts:40-41`, `:53-56`), es decir hasta ~1.2s de ventana con el gate en `false`.
- **Impacto usuario:** un favorito, un link compartido, o simplemente F5 en la pantalla donde estaba trabajando, aterriza en el tablero de Tickets sin ningún mensaje. El operador concluye "se perdió" o "no tengo acceso".
- **Impacto negocio:** las URLs de Stacky no son compartibles ni citables en un ticket/chat para 12 de 18 pantallas. Anula el valor del router tipado que ya se construyó (`services/routes.ts`).
- **Severidad:** **crítica**
- **Frecuencia:** 100% de los reloads y deep links a esas 12 pantallas.
- **Recomendación concreta:** introducir un tercer estado explícito. Hoy el booleano confunde "todavía no sé" con "está apagado".
  1. Cambiar cada gate de `boolean` a `"unknown" | "on" | "off"` con valor inicial `"unknown"`.
  2. El efecto de `App.tsx:264-277` sólo redirige cuando el estado es `"off"`; con `"unknown"` **no hace nada**.
  3. Mientras el tab activo esté en `"unknown"`, la pantalla muestra un esqueleto de carga en lugar de rebotar.
  4. Si resuelve `"off"`, recién entonces redirigir **y explicar** (microcopy propuesto abajo).
- **Comportamiento esperado:** `/devops` + F5 ⇒ esqueleto ~200ms ⇒ DevOps. Con la flag realmente apagada ⇒ Tickets **con** un aviso, no un rebote mudo.
- **Microcopy propuesto** para el caso `"off"` real (hoy no existe ningún mensaje):
  > **DevOps está desactivado.** Esta sección se activa desde Configuración → Flags del arnés (`STACKY_DEVOPS_ENABLED`). Te llevamos a Tickets mientras tanto. · [Ir a Flags] [Entendido]
  >
  > (nota: el nombre técnico va en el enlace a Flags, no en la frase principal — ver H-06.)
- **Cómo validar:** test `.ts` puro sobre la función de decisión extraída (ver criterio de aceptación) + smoke manual: (1) activar la flag de DevOps, (2) navegar a `/devops`, (3) F5, (4) verificar que la URL sigue siendo `/devops` y la pantalla es DevOps.
- **Criterio de aceptación:** extraer la decisión a una función pura `shouldRedirectAway(tab, gateState): boolean` en un `.ts` y probar en tests puros la tabla completa: `("devops","unknown") → false`, `("devops","off") → true`, `("devops","on") → false`. La suite debe fallar si `"unknown"` vuelve a redirigir.
- **Archivos a modificar:** `frontend/src/App.tsx` (76-102, 143-167, 264-277), `frontend/src/utils/flagHealth.ts`, nuevo `.ts` puro con la función de decisión y su test.

### H-02 · La navegación cambia de arquitectura después del primer paint, y degrada en silencio a la versión vieja — `[CÓDIGO]` + `[DRIFT]`

- **Pantalla/flujo:** shell global, todas las pantallas.
- **Problema:** existen **dos** navegaciones completas y distintas, elegidas por flag. La flag está **encendida por default en el backend**, pero el frontend arranca asumiendo que está **apagada**. Resultado: cada carga pinta la nav vieja y después salta a la nueva. Y si el health-check falla, se queda en la vieja para toda la sesión, sin avisar.
- **Evidencia:**
  - Default real del backend: `backend/config.py:1811-1812` — `STACKY_UI_SHELL_V2_ENABLED: bool = os.getenv("STACKY_UI_SHELL_V2_ENABLED", "true")`. Se expone en `backend/api/diag.py:634`.
  - Estado inicial del frontend, contradictorio con ese default: `frontend/src/App.tsx:85` — `useState(false)`.
  - Se resuelve por red recién en el montaje: `frontend/src/App.tsx:170-177`.
  - Degradación silenciosa ante fallo: `frontend/src/App.tsx:178-180` — `.catch(() => { if (alive) setShellV2Enabled(false); })`.
  - La bifurcación de layout: `frontend/src/App.tsx:335` — `{shellV2Enabled ? (…AppSidebar…) : (…<nav>…)}`.
  - **Las dos IAs no son variantes cosméticas.** v1 es una lista **plana** de 18 botones con emoji, con las etiquetas hardcodeadas: `frontend/src/App.tsx:352-493` (`"⚡ Mi Equipo"` :358, `"📋 Tickets ADO"` :365, `"🧭 Revisión"` :379, `"🧹 Desatascador"` :393, `"📊 PM"` :400, `"🔍 System Logs"` :408, `"⚙️ Configuración"` :415, `"📄 Docs"` :422, `"Memoria"` :430, `"🩺 Diagnóstico"` :437, `"📋 Historial"` :443, `"Migrador"` :450, `"DevOps"` :458, `"Comparador BD"` :466, `"💰 Centro de Costos"` :474, `"🧭 Planes"` :482, `"🧬 Evolución"` :490).
  - v2 es una sidebar **agrupada en 5 grupos semánticos** con iconos nombrados: `frontend/src/components/shell/shellNav.ts:43-49` (`Trabajo`, `Observabilidad`, `Conocimiento`, `Plataforma`, `Configuración`) y etiquetas en `TAB_META` `shellNav.ts:16-35`.
- **`[DRIFT]` adicional (etiquetas duplicadas):** las 18 etiquetas viven en **dos** lugares sin fuente única — literales JSX en `App.tsx:352-493` y `TAB_META` en `shellNav.ts:16-35`. El propio código admite la sincronización manual: `shellNav.ts:3-4` — *"Debe coincidir 1:1 con `type Tab` de App.tsx. Si App.tsx agrega/quita un tab, actualizar aquí"*. Renombrar una sección requiere dos ediciones y nada lo verifica.
- **`[DRIFT]` de jerarquía:** `Configuración` es el ítem **8 de 18** (posición media) en v1 (`App.tsx:411-416`) y el **último grupo** en v2 (`shellNav.ts:48`). La importancia relativa que comunica la UI depende de qué rama se rendericé.
- **Impacto usuario:** parpadeo estructural en cada carga (no un flash de estilos: cambian el layout, el agrupamiento y los iconos). Si el health falla, el operador ve un producto distinto del documentado y del que vio ayer, sin ninguna señal.
- **Impacto negocio:** dos IAs que hay que mantener, documentar y soportar. Cualquier captura de pantalla, material de capacitación o documentación queda ambigua.
- **Severidad:** **alta** (crítica para el caso de fallo de health)
- **Frecuencia:** el parpadeo, 100% de las cargas. La degradación permanente, cada vez que `/api/diag/health` falle o tarde.
- **Recomendación concreta:**
  1. **Corto plazo (antes de producción):** alinear el default del frontend con el del backend — `useState(true)` en `App.tsx:85` — y en el `.catch` **conservar** el valor optimista en lugar de forzar `false`. Un fallo de red no debe cambiar la arquitectura de información. Esto elimina el parpadeo y la degradación silenciosa con un cambio de dos líneas.
  2. **Estructural:** decidir si v1 se retira. Mantener dos IAs completas es la fuente de este hallazgo y del drift de etiquetas.
  3. **Fuente única de etiquetas:** que `App.tsx` (si v1 sobrevive) consuma `TAB_META` de `shellNav.ts` en lugar de literales.
- **Riesgo que reduce:** elimina el parpadeo estructural (100% de cargas) y la divergencia de modelo mental.
- **Cómo validar:** test `.ts` puro que afirme que el default del frontend coincide con el default declarado del backend (gate de grep contra `config.py:1811` o constante compartida). Smoke manual: cargar la app con el backend detenido y verificar que la nav **no** cambia de forma respecto de la carga con backend vivo.
- **Criterio de aceptación:** (a) con backend vivo, la nav renderizada en el primer paint es la misma que a los 3s (sin cambio de layout); (b) con `/api/diag/health` devolviendo 500, la nav sigue siendo la sidebar agrupada; (c) un gate de grep/ratchet falla si las etiquetas de tabs vuelven a existir como literales duplicados en `App.tsx`.
- **Archivos a modificar:** `frontend/src/App.tsx:85`, `:170-180`, `:352-493`; `frontend/src/components/shell/shellNav.ts`.

### H-03 · `api.*` destruye el mensaje humano y el `correlation_id` que el backend sí redacta — `[CÓDIGO]`

- **Pantalla/flujo:** transversal. Es el choke-point de red de todo el frontend.
- **Problema:** el backend devuelve cuerpos de error estructurados con `message` humano y `correlation_id`. El cliente HTTP los **aplana en un string** y los tira. Todo llamador que muestre la excepción muestra el status HTTP, el statusText y el JSON crudo.
- **Evidencia:**
  - El aplastamiento: `frontend/src/api/client.ts:206-209` —
    ```ts
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText}: ${text}`);
    }
    ```
  - Todos los verbos de `api` pasan por ahí: `frontend/src/api/client.ts:213-235` (`get`, `post`, `put`, `patch`, `delete`, `postWithHeaders`, `postAbortable` → todos llaman `request<T>`).
  - El contrato rico **ya existe y está tipado**: `GatewayErrorBody { error, message, correlation_id, detail }` en `frontend/src/api/client.ts:36-41`, devuelto en `errorBody` por `rawPost` (`:47-89`), `rawGet` (`:96-136`) y `rawPut` (`:144-186`).
  - El propio código documenta por qué existen los `raw*`: `client.ts:92-95` — *"404 feature_disabled llega como errorBody, NO como excepcion"*; `client.ts:141-143` — *"`api.put` lanza en todo non-2xx y aplana el cuerpo en `${status} ${statusText}: ${text}`"*.
  - La cadena hasta el ojo del operador: `frontend/src/components/PageErrorBoundary.tsx:62` renderiza `{this.state.error?.message || "Error inesperado"}` — es decir, exactamente el string aplanado de `client.ts:208`.
- **Impacto usuario:** en lugar de *"El comparador de BD está desactivado. Actívalo en Configuración."* el operador lee `403 FORBIDDEN: {"ok":false,"error":"Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)."}`. No sabe si es un bug, un permiso o una configuración, y no tiene un próximo paso.
- **Impacto negocio:** cada error se convierte en una consulta de soporte. Y se pierde el `correlation_id`, que es justamente el dato que permitiría correlacionar la queja con el log del servidor.
- **Severidad:** **crítica**
- **Frecuencia:** cada error non-2xx que llegue por `api.*` (la mayoría de los llamadores — pendiente cuantificar el ratio exacto, ver §8).
- **Recomendación concreta:**
  1. Definir una clase `GatewayError extends Error` que **preserve** `status`, `errorBody.message`, `errorBody.error` y `correlation_id` como campos, y hacer que `request()` la lance en lugar de `new Error(string)`. Cambio contenido a `client.ts:206-209`, retrocompatible si `message` sigue siendo legible.
  2. Un helper puro `userFacingMessage(e: unknown): { title: string; detail?: string; correlationId?: string }` que priorice `errorBody.message` y **nunca** devuelva el status crudo.
  3. Que `PageErrorBoundary.tsx:62` y los renders de error usen ese helper.
- **Ejemplo tangible del cambio de mensaje de error:**
  - Hoy: `Error: 403 FORBIDDEN: {"ok":false,"error":"Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)."}`
  - Propuesto: **"El Comparador de BD está desactivado."** / *Se activa desde Configuración → Flags del arnés.* / `[Ir a Flags]` `[Reintentar]` · pie discreto: `ref. a3f9c1` (el `correlation_id`, copiable).
- **Cómo validar:** tests `.ts` puros de `userFacingMessage` sobre los cuerpos reales del backend (403 de flag, 409, 500 con `message`, 500 sin cuerpo, fallo de red). El gate se corre **contra el defecto**: un test debe fallar si el string de salida contiene `INTERNAL SERVER ERROR`, un `{` de JSON, o `STACKY_`.
- **Criterio de aceptación:** `userFacingMessage` nunca retorna texto que matchee `/^\d{3} [A-Z ]+:/` ni `/STACKY_[A-Z_]+/` ni `/^\s*\{/`; y para un 403 de flag retorna el `message` del backend, no el `error`.
- **Archivos a modificar:** `frontend/src/api/client.ts:206-209`, `:213-235`; `frontend/src/components/PageErrorBoundary.tsx:62`; nuevo helper `.ts` + su test.

### H-04 · Sin timeout en el cliente HTTP: un backend colgado deja spinner infinito — `[CÓDIGO]`

- **Pantalla/flujo:** transversal.
- **Problema:** `request()` llama a `fetch` sin `AbortController` ni deadline. La única vía cancelable es opt-in y sólo para POST.
- **Evidencia:**
  - `frontend/src/api/client.ts:190-211` — `request()` completo; el `fetch` de `:193-200` no recibe `signal` propio, sólo hace spread del `init` del llamador.
  - La única variante cancelable, y es POST y opt-in: `frontend/src/api/client.ts:233-234` — `postAbortable: <T,>(path, body, signal) => request<T>(path, { method: "POST", body: …, signal })`.
  - `rawGet` (`:96-136`), `rawPost` (`:47-89`) y `rawPut` (`:144-186`) tampoco tienen timeout.
- **Impacto usuario:** con el backend vivo pero trabado (lock de SQLite, daemon colgado, red intermedia caída sin RST), la pantalla queda cargando para siempre. No hay error, no hay reintento, no hay salida salvo F5 — y F5 dispara H-01.
- **Impacto negocio:** indistinguible de "el producto se colgó". Es el peor modo de falla para la percepción de calidad.
- **Severidad:** **alta**
- **Frecuencia:** `[HIPÓTESIS]` sobre la tasa real en el entorno del operador. **Paso manual que la confirma:** detener el proceso backend con la SPA abierta (o pausarlo con un breakpoint) y navegar a cualquier pantalla que cargue datos; observar si aparece un error o si el spinner queda indefinido. El sustrato de SQLite bajo carga concurrente hace este escenario plausible, no teórico.
- **Recomendación concreta:** un `AbortController` con deadline por defecto dentro de `request()` (y en los `raw*`), configurable por llamador para las operaciones legítimamente largas. Al expirar, lanzar/retornar un error de clase distinguible (`timeout`) para que la UI ofrezca **Reintentar** en lugar de un mensaje genérico.
- **Ejemplo tangible del estado de error propuesto:**
  > ⏱ **La operación tardó más de lo esperado.** El servidor no respondió en 20 segundos. · `[Reintentar]` `[Ver diagnóstico]`
- **Cómo validar:** test `.ts` puro con un `fetchImpl` inyectado que nunca resuelve + reloj falso, afirmando que la promesa rechaza con el error de timeout dentro del deadline. (No requiere DOM: `request` es lógica pura sobre `fetch`.)
- **Criterio de aceptación:** con un `fetch` que nunca resuelve, `api.get` rechaza con un error cuyo tipo es reconocible como timeout antes de `deadline + margen`; las operaciones declaradas como largas pueden pedir un deadline mayor y no se ven afectadas.
- **Archivos a modificar:** `frontend/src/api/client.ts:190-211` (y opcionalmente `:47-89`, `:96-136`, `:144-186`).

### H-05 · La nav v1 recorta horizontalmente y deja tabs inalcanzables — `[CÓDIGO]`

- **Pantalla/flujo:** shell global, rama v1 (que es la que se pinta en el primer paint de **toda** carga, por H-02).
- **Problema:** contenedor `flex` sin `flex-wrap` y sin `overflow-x`, con los ítems en `nowrap`. Cuando la suma de anchos excede el viewport, los últimos tabs quedan fuera y **no hay forma de llegar a ellos**: no envuelven y no scrollean.
- **Evidencia:**
  - `frontend/src/App.module.css:7-16` — `.nav { display: flex; gap: 0; … padding: 0 16px; position: sticky; … }`. **No** hay `flex-wrap` ni `overflow-x` en la regla.
  - `frontend/src/App.module.css:29` — `.navTab { … white-space: nowrap; }`.
  - `frontend/src/App.module.css:19` — `.navTab { padding: 10px 20px; … }` (40px de padding horizontal por tab).
  - **`App.module.css` no contiene ninguna `@media`** — verificado: `grep -n "@media" frontend/src/App.module.css` no devuelve líneas (el archivo tiene 72 líneas en total y las reglas presentes son las de `:1-71`).
  - Cantidad de tabs que puede renderizar v1: 18 (`frontend/src/App.tsx:352-493`, un botón por tab).
- **Impacto usuario:** con muchas secciones habilitadas, las últimas del orden de v1 (`Migrador`, `DevOps`, `Comparador BD`, `Centro de Costos`, `Planes`, `Evolución` — `App.tsx:445-492`) son las que caen fuera. Son justamente las funcionalidades más caras de construir: presentes, pagadas, y no clickeables.
- **Impacto negocio:** funcionalidad invisible ⇒ percibida como inexistente ⇒ cero adopción de los módulos más costosos.
- **Severidad:** **alta**
- **Frecuencia:** `[HIPÓTESIS]` en cuanto al viewport exacto de corte. **Paso manual que la confirma:** habilitar todas las secciones opcionales, forzar la nav v1 (poner `STACKY_UI_SHELL_V2_ENABLED=false` o bloquear `/api/diag/health`), y estrechar la ventana hasta 1280px observando si los últimos tabs quedan recortados sin scroll. Lo que **sí** está verificado sin ambigüedad es la ausencia de `flex-wrap`/`overflow-x`/`@media`, es decir: **no existe ningún mecanismo de recuperación** ante desborde, cualquiera sea el ancho de corte.
- **Recomendación concreta:** agregar `overflow-x: auto` + `scrollbar-width: thin` a `.nav` como piso mínimo (una línea, sin riesgo de layout), o `flex-wrap: wrap` si se acepta que la nav crezca en alto. Si v1 se retira (H-02), este hallazgo se cierra por eliminación — es la razón por la que recomiendo resolver H-02 primero.
- **Cómo validar:** gate de grep/ratchet: la regla `.nav` de `App.module.css` debe contener `overflow-x` o `flex-wrap`. Smoke manual: el paso descrito arriba, verificando que ahora se puede alcanzar el último tab.
- **Criterio de aceptación:** con las 18 secciones habilitadas y viewport de 1280px, todos los tabs son alcanzables (por scroll o por wrap) sin usar el teclado ni la paleta de comandos.
- **Archivos a modificar:** `frontend/src/App.module.css:7-16`.

### H-06 · 24 mensajes de error filtran nombres de variables de entorno al operador — `[CÓDIGO]`

- **Pantalla/flujo:** transversal; concentrado en Comparador BD, Evolución, Docs, Planes, Migrador, Diagnóstico.
- **Problema:** los cuerpos de error de "feature desactivada" incluyen el nombre de la variable de entorno entre paréntesis. Combinado con H-03, ese texto llega crudo a la pantalla.
- **Evidencia:** 24 ocurrencias. Comando:
  ```
  grep -rnE '"(error|message)":\s*"[^"]*STACKY_[A-Z_]+' backend/api --include=*.py | wc -l
  ```
  Ejemplos verificados con `archivo:línea`:
  - `backend/api/db_compare.py:38` — `"Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)."`
  - `backend/api/db_compare.py:47` — `"Import de web.config deshabilitado (STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED)."`
  - `backend/api/db_compare.py:57` — `"Paridad de datos deshabilitada (STACKY_DB_COMPARE_DATA_DIFF_ENABLED)."`
  - `backend/api/db_compare.py:478` — `"Triage del diff deshabilitado (STACKY_DB_COMPARE_TRIAGE_ENABLED)."`
  - `backend/api/db_compare.py:703` — `"Gates de precondición deshabilitadas (STACKY_DB_COMPARE_GATES_ENABLED)."`
  - `backend/api/db_compare_masking.py:25` — `"Masking deshabilitado (STACKY_DB_COMPARE_MASKING_ENABLED)."`
  - `backend/api/db_compare_repo.py:27` — `"Puente al repo deshabilitado (STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED)."`
  - `backend/api/db_compare_watch.py:21` — `"Radar de ambientes deshabilitado (STACKY_DB_COMPARE_RADAR_ENABLED)."`
  - `backend/api/diag.py:1018` — `"La reconciliación de corridas está deshabilitada (STACKY_RUN_RECONCILIATION_ENABLED)."`
  - `backend/api/docs.py:222` — `"El grafo documental está deshabilitado (STACKY_DOCS_GRAPH_ENABLED)."`
  - `backend/api/evolution.py:32` — `"El Centro de Evolución está deshabilitado (STACKY_EVOLUTION_CENTER_ENABLED)."`
  - `backend/api/evolution.py:179` — `"El ciclo MAPE está deshabilitado (STACKY_EVOLUTION_CYCLE_ENABLED)."`
  - `backend/api/evolution_fitness.py:23` — `"El arnés de fitness está deshabilitado (STACKY_EVAL_HARNESS_ENABLED)."`
  - `backend/api/evolution_knowledge.py:29` — `"El flywheel de conocimiento está deshabilitado (STACKY_KNOWLEDGE_FLYWHEEL_ENABLED)."`
  - `backend/api/plans_board.py:25` — `"El tablero de planes está deshabilitado (STACKY_PLANS_BOARD_ENABLED)."`
  - `backend/api/migrator.py:101` — `"Migrador no habilitado (STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED=false)"`
- **Nota de vocabulario:** además del nombre de la variable, varios mensajes exponen jerga interna sin traducir al dominio del operador: *"arnés de fitness"*, *"flywheel de conocimiento"*, *"ciclo MAPE"*, *"Puente al repo"*, *"Gates de precondición"*, *"Triage del diff"*, *"Masking"*. Son nombres de implementación, no de producto.
- **Impacto usuario:** el mensaje le dice al operador *qué variable de entorno* está apagada, pero **el riel del producto es que las flags se configuran por UI** — así que el dato es simultáneamente intimidante e inútil: no es el camino que debe tomar.
- **Impacto negocio:** filtra la topología interna de configuración y transmite "producto para desarrolladores".
- **Severidad:** **media** por sí solo; **alta** en combinación con H-03 (que es lo que lo hace visible).
- **Frecuencia:** cada vez que el operador toca una funcionalidad con su flag apagada.
- **Recomendación concreta:** separar en el cuerpo JSON el campo legible del campo técnico. El backend ya tiene la estructura para hacerlo (`GatewayErrorBody` con `error` machine-readable + `message` humano, `client.ts:36-41`): poner el nombre de la flag en `error`/`detail` (para logs y para el enlace profundo al panel de flags) y dejar `message` sin nombres técnicos.
- **Ejemplo tangible:**
  - Hoy: `{"ok": false, "error": "El grafo documental está deshabilitado (STACKY_DOCS_GRAPH_ENABLED)."}`
  - Propuesto: `{"ok": false, "error": "feature_disabled", "message": "El grafo de documentación está desactivado.", "detail": {"flag": "STACKY_DOCS_GRAPH_ENABLED"}}` — y la UI renderiza el `message` + un botón `[Activar en Configuración]` que hace deep-link al panel de flags filtrado por esa flag.
- **Cómo validar:** gate de grep sobre la respuesta de la API, no sobre el fuente: test de backend que recorra los endpoints con flag apagada y afirme que `message` no matchea `/STACKY_[A-Z_]+/`. El gate se corre contra el defecto: hoy debe dar **rojo** en ≥16 endpoints.
- **Criterio de aceptación:** ningún campo `message` de ninguna respuesta de error contiene `STACKY_`; el nombre de la flag sigue disponible en `detail.flag` para el enlace profundo.
- **Archivos a modificar:** los 16 archivos de `backend/api/` listados arriba.

### H-07 · En tema claro, las etiquetas de la nav v1 son prácticamente invisibles — `[CÓDIGO]`

- **Pantalla/flujo:** shell global rama v1, con `data-theme="light"`.
- **Problema:** los colores de la nav v1 están hardcodeados como **blanco con alfa**, no como tokens. El tema claro re-apunta los tokens (`theme.css:172-244`) pero no puede tocar un literal.
- **Evidencia:**
  - `frontend/src/App.module.css:24` — `.navTab { … color: rgba(255, 255, 255, 0.45); … }`
  - `frontend/src/App.module.css:33` — `.navTab:hover { color: rgba(255, 255, 255, 0.8); }`
  - Fondo del contenedor en tema claro: `.nav` usa `var(--bg-panel)` (`App.module.css:10`), y en claro `--bg-panel: #f6f8fa` (`frontend/src/theme.css:175`).
- **Aritmética de contraste (propia, verificable):** blanco al 45% de alfa compuesto sobre `#f6f8fa`:
  - R = 0.45·255 + 0.55·246 = 114.75 + 135.30 = **250.05**
  - G = 0.45·255 + 0.55·248 = 114.75 + 136.40 = **251.15**
  - B = 0.45·255 + 0.55·250 = 114.75 + 137.50 = **252.25**
  - Color efectivo ≈ `#FAFBFC` sobre `#F6F8FA` ⇒ contraste ≈ **1.02:1** (el mínimo WCAG AA para texto normal es 4.5:1). El texto es, a efectos prácticos, **invisible**.
  - En `:hover` (alfa 0.8) empeora: se acerca aún más al blanco puro.
- **Hallazgo colateral en la misma regla — color fuera del sistema:** `frontend/src/App.module.css:37-38` — `.navTab.active { color: #a5b4fc; border-bottom-color: #6366f1; }`. Son índigos que **no existen en `theme.css`**: el acento del sistema es `--accent: #388bfd` (`theme.css:17`) / `--accent-hot: #58a6ff` (`theme.css:18`). El indicador de "pestaña activa" — el elemento de navegación más importante de la pantalla — usa una familia de color ajena al design system. Igual `.navBadge { background: #b91c1c; }` (`App.module.css:49`).
- **Impacto usuario:** si el operador activa el tema claro, no puede leer la navegación.
- **Impacto negocio:** una funcionalidad completa y construida (tema claro, `theme.css:166-244`, con contraste verificado token a token según su propio comentario) queda inutilizable por tres literales en un archivo.
- **Severidad:** **alta** si el tema claro es una funcionalidad ofrecida; **baja** si se decide no ofrecerlo (y entonces hay que ocultar el toggle).
- **Frecuencia:** 100% de las sesiones en tema claro con nav v1 — y v1 es el primer paint de toda carga (H-02).
- **Recomendación concreta:** reemplazar los tres literales por tokens existentes: `color: var(--text-muted)` (reposo), `var(--text-primary)` (hover), `var(--accent)` + `border-bottom-color: var(--accent)` (activo), `var(--status-danger-solid)` (badge). Todos existen ya en `theme.css` y todos están tematizados.
- **Cómo validar:** gate de grep/ratchet: `App.module.css` no debe contener `rgba(255, 255, 255` ni hex literales en reglas de color de `.navTab`/`.navBadge`. Smoke manual: activar tema claro y verificar que se lee la nav en reposo, hover y activo.
- **Criterio de aceptación:** ningún literal de color en `App.module.css`; contraste medido del texto de tab en reposo ≥ 4.5:1 en **ambos** temas.
- **Archivos a modificar:** `frontend/src/App.module.css:24`, `:33`, `:37`, `:38`, `:49`.

### H-08 · No existe autenticación; la identidad del operador es un literal del bundle y el backend la resuelve a seis valores distintos — `[CÓDIGO]`

> Este hallazgo responde directamente a lo que el pedido llamó "registro e inicio de sesión", "permisos incorrectos" y "problemas de sesión o autenticación". **El flujo no existe.** Eso, en el modelo mono-operador, es una decisión de producto coherente — pero tiene consecuencias verificables que sí hay que decidir antes de producción.

- **Problema:** no hay login, registro, sesión, roles ni verificación de identidad humana. La identidad viaja en un header HTTP sin validar, y el frontend lo **hardcodea**.
- **Evidencia — no hay verificación de identidad:**
  - `backend/api/_helpers.py:4-5` — la función de identidad completa:
    ```python
    def current_user() -> str:
        return request.headers.get("X-User-Email") or "dev@local"
    ```
  - El hook global de request no hace ninguna comprobación: `backend/app.py:824-826` — `_before_request` sólo asigna `g.request_id` y `g.request_start`.
  - El logging de respuesta confía en el header tal cual: `backend/app.py:835` — `user = request.headers.get("X-User-Email") or "anonymous"`.
- **Evidencia — el frontend hardcodea la identidad:** `"X-User-Email": "dev@local"` aparece en los cuatro puntos de salida del cliente HTTP y en un llamador directo:
  - `frontend/src/api/client.ts:58` (rawPost), `:106` (rawGet), `:155` (rawPut), `:197` (request → todos los `api.*`)
  - `frontend/src/api/endpoints.ts:5168`
  - Comando: `grep -rn "dev@local" frontend/src --include=*.ts --include=*.tsx | grep -v __tests__` → 8 líneas, de las cuales 3 son de `components/buildIdentity.ts:12,14,27` (etiqueta de versión de build, falso positivo) ⇒ **5 sitios reales de header**.
- **Evidencia — los únicos dos mecanismos de auth del producto son máquina-a-máquina, no humanos:**
  - `backend/api/phase6.py:322-324` — token de slash-command tipo Slack: `token = request.headers.get("X-Stacky-Slash-Token")` / `if not slash_commands.verify_token(token): abort(401, "invalid token")`.
  - `backend/api/tickets.py:1620-1642` — gateway de agentes: compara `X-Stacky-Agent-Token` contra `STACKY_AGENT_TOKEN` y responde 401 `auth_required` / `"Header X-Stacky-Agent-Token requerido"` / `"X-Stacky-Agent-Token inválido"`.
  - Comando: `grep -rnE "(abort\(401|abort\(403|, 401\)|, 403\))" backend/api --include=*.py | wc -l` → **2**.
- **Evidencia — `403` en Stacky NO significa "no tenés permiso":** todos los 403 de la API son gates de **feature flag**, no de autorización. Ver el listado de H-06 (`db_compare.py:38`, `db_compare_watch.py:19`, `devops_deployments.py:199` → `"deployments_execute_disabled"`, etc.).
- **`[DRIFT]` interno — seis identidades de reserva para el mismo usuario ausente:** cada módulo inventa su propio valor cuando el header falta:
  - `backend/api/_helpers.py:5` → `"dev@local"`
  - `backend/api/extras.py:21` → `"dev@local"`
  - `backend/api/client_profile.py:82` → `"operator"`
  - `backend/api/config_transfer.py:56` → `"operator"`
  - `backend/api/db_query.py:38` → `"operator"`
  - `backend/api/tickets.py:1178` → `"anonymous"`
  - `backend/api/tickets.py:1262` y `:1644` → `"agent"`
  - `backend/api/logs.py:226` → `"unknown"`
  - `backend/app.py:835` → `"anonymous"`
- **Impacto usuario:** ninguno directo hoy (un solo operador). El impacto es sobre el **operador que audita**: no puede responder "¿quién hizo esto?" con los datos que el producto guarda.
- **Impacto negocio:** tres consecuencias concretas: (1) toda métrica de adopción por usuario, todo `created_by` y toda traza de auditoría refieren a un usuario ficticio único; (2) los registros del mismo evento aparecen atribuidos a `dev@local`, `operator`, `anonymous`, `agent` o `unknown` según el módulo que lo escribió, así que ni siquiera son agrupables; (3) si el despliegue deja de ser localhost, **cualquiera en la red puede enviar el header que quiera y actuar como cualquiera** — no hay nada que validar porque no hay nada que validar contra.
- **Severidad:** **media** en despliegue mono-operador local (es el riel del producto, y es una decisión defendible) · **crítica** si el backend queda accesible en red.
- **Frecuencia:** permanente.
- **Recomendación concreta — tres cosas, ninguna es "agregar login":**
  1. **Decidir y documentar el límite de confianza.** Si el backend sólo debe escuchar en loopback, que lo haga explícitamente (bind a `127.0.0.1`) y que quede escrito en `docs/sistema/`. Un producto sin auth que escucha en `0.0.0.0` es un incidente esperando ocurrir; el mismo producto atado a loopback es una decisión de arquitectura razonable.
  2. **Unificar el valor de identidad ausente a UNO.** Nueve sitios, seis valores. Que todos deriven de `_helpers.current_user()`. Costo bajo, y recupera la agrupabilidad de la traza.
  3. **Dejar de hardcodear `dev@local` en el bundle.** Que el operador pueda poner su nombre/email una vez en Configuración y que el cliente lo envíe. No es autenticación (sigue sin validarse) pero convierte la atribución en algo útil, y es exactamente el riel del producto: configuración del operador por UI.
- **Lo que explícitamente NO recomiendo:** construir login, roles o RBAC. Sería trabajo grande contra un riesgo que hoy no existe, y contradice el modelo mono-operador. La protección correcta es de red (punto 1), no de aplicación.
- **Cómo validar:** (a) test de backend que afirme que el valor de identidad ausente es idéntico en los nueve sitios (gate de grep sobre los literales); (b) verificación manual del binding con `netstat -ano | findstr :<puerto>` confirmando que sólo escucha en `127.0.0.1`.
- **Criterio de aceptación:** un solo literal de identidad ausente en todo `backend/`; el frontend envía un valor configurado por el operador; el binding de red está documentado y verificado.
- **Archivos a modificar:** `backend/api/_helpers.py:5`, `backend/api/extras.py:21`, `backend/api/client_profile.py:82`, `backend/api/config_transfer.py:56`, `backend/api/db_query.py:38`, `backend/api/tickets.py:1178,1262,1644`, `backend/api/logs.py:226`, `backend/app.py:835`, `frontend/src/api/client.ts:58,106,155,197`, `frontend/src/api/endpoints.ts:5168`.

### H-09 · El token `--text-faint` no alcanza WCAG AA y se usa 97 veces — `[CÓDIGO]`

- **Problema:** un token de color de texto del design system queda por debajo del mínimo de contraste AA sobre las dos superficies principales del tema oscuro.
- **Evidencia de los valores:** `frontend/src/theme.css:14` — `--text-faint: #6e7681`; `theme.css:6` — `--bg-panel: #161b22`; `theme.css:5` — `--bg-base: #0d1117`.
- **Aritmética de contraste (propia, reproducible — luminancia relativa WCAG):**
  - `#6e7681`: canales 110/118/129 ⇒ normalizados 0.4314/0.4627/0.5059 ⇒ linealizados `((c+0.055)/1.055)^2.4` = 0.1561/0.1812/0.2196 ⇒ **L = 0.2126·0.1561 + 0.7152·0.1812 + 0.0722·0.2196 = 0.17864**
  - `#161b22`: canales 22/27/34 ⇒ 0.08627/0.10588/0.13333 ⇒ linealizados 0.008021/0.010965/0.015989 ⇒ **L = 0.010701**
  - `#0d1117`: canales 13/17/23 ⇒ 0.05098/0.06667/0.09020 ⇒ linealizados 0.004025/0.005605/0.008572 ⇒ **L = 0.0054834**
  - Contraste `--text-faint` sobre `--bg-panel` = (0.17864+0.05)/(0.010701+0.05) = 0.22864/0.060701 = **3.77:1** ⇒ **FALLA AA (4.5:1)**
  - Contraste `--text-faint` sobre `--bg-base` = (0.17864+0.05)/(0.0054834+0.05) = 0.22864/0.0554834 = **4.12:1** ⇒ **FALLA AA (4.5:1)**
  - Control de sanidad, el token vecino **sí** pasa: `--text-muted: #8b949e` (`theme.css:13`) ⇒ L = 0.287008 ⇒ sobre `--bg-panel` = 0.337008/0.060701 = **5.55:1** ⇒ **CUMPLE AA**. Esto confirma que el problema es específico de `--text-faint`, no del enfoque de la paleta.
- **Alcance del uso:** 97 ocurrencias en 45 archivos CSS. Comandos:
  ```
  grep -rn "var(--text-faint)" frontend/src --include=*.css | wc -l     # 97
  grep -rln "var(--text-faint)" frontend/src --include=*.css | wc -l    # 45
  ```
- **Impacto usuario:** el texto secundario (marcas de tiempo, metadatos, pistas de ayuda, contadores) es difícil de leer para cualquiera con visión reducida, con brillo bajo, o en una pantalla con reflejo. En una herramienta de operaciones, esos metadatos suelen ser el dato que importa.
- **Severidad:** **media** (accesibilidad, alcance amplio, no bloquea tarea)
- **Frecuencia:** permanente, en 45 archivos.
- **Recomendación concreta:** subir `--text-faint` hasta cruzar 4.5:1 sobre `--bg-base` (la superficie más oscura y por tanto el caso peor es en realidad `--bg-panel`, que es más claro: hay que satisfacer **ambos**). Un valor alrededor de `#7d8590` sube la luminancia lo suficiente; el valor exacto se fija recalculando con la misma fórmula de arriba hasta que **ambos** ratios superen 4.5. Cambio en **un** literal, propaga a 97 usos.
- **Nota de por qué no propongo un valor "seguro" sin recalcular:** sería exactamente el tipo de número inventado que esta auditoría no acepta. El criterio de aceptación abajo define el gate; el valor sale de correrlo.
- **Cómo validar:** test `.ts` puro que implemente la fórmula de luminancia relativa WCAG, lea los valores de `theme.css` y afirme el umbral para cada par (texto × superficie) del tema oscuro **y** del claro. Es lógica pura: sin DOM, sin RTL. El gate se corre contra el defecto: con `#6e7681` debe dar **rojo** en dos pares.
- **Criterio de aceptación:** el test de contraste pasa para todos los pares de texto/superficie en ambos temas con umbral 4.5:1 (texto normal); los pares que se decida exceptuar están declarados explícitamente en el test con su justificación.
- **Archivos a modificar:** `frontend/src/theme.css:14` (+ el equivalente del tema claro `theme.css:184` si el recálculo lo requiere), nuevo test `.ts` de contraste.

### H-10 · El soporte responsive es indefinido: 13 media queries de viewport en 198 archivos CSS — `[CÓDIGO]`

- **Problema:** no hay una estrategia responsive; hay islas. La mayoría de las pantallas no tiene ninguna regla de adaptación, y las que tienen usan breakpoints distintos entre sí.
- **Evidencia y conteos.** Comandos:
  ```
  grep -rn "@media" frontend/src --include=*.css | wc -l                          # 21 total
  grep -rn "@media" frontend/src --include=*.css | grep -cE "max-width|min-width" # 13 de viewport
  find frontend/src -name "*.css" | wc -l                                         # 198 archivos CSS
  ```
  De las 21 `@media` totales, **8 no son de viewport** sino de preferencias del sistema (5 × `prefers-reduced-motion: reduce`, 1 × `prefers-reduced-motion: no-preference`, 1 × `prefers-reduced-motion`, 1 × `prefers-color-scheme: dark`). Quedan **13 de viewport, en 12 archivos** (`TeamScreen.module.css` tiene 2).
- **Las 13, con `archivo:línea`:**
  - `frontend/src/components/AgentRuntimeSelector.module.css:76` — `max-width: 420px`
  - `frontend/src/components/CodexConsoleDock.module.css:253` — `max-width: 640px`
  - `frontend/src/components/shell/AppSidebar.module.css:120` — `max-width: 820px`
  - `frontend/src/components/SyncStatusBar.module.css:96` — `max-width: 720px`
  - `frontend/src/pages/DevOpsCockpit.module.css:39` — `max-width: 900px`
  - `frontend/src/pages/DevOpsPage.module.css:70` — `max-width: 900px`
  - `frontend/src/pages/DiagnosticsPage.module.css:327` — `max-width: 720px`
  - `frontend/src/pages/MemoryPage.module.css:294` — `max-width: 720px`
  - `frontend/src/pages/PMCommandCenter.module.css:565` — `max-width: 720px`
  - `frontend/src/pages/TeamScreen.module.css:107` — `max-width: 900px`
  - `frontend/src/pages/TeamScreen.module.css:110` — `max-width: 560px`
  - `frontend/src/pages/TicketBoard.module.css:1118` — `max-width: 820px`
  - `frontend/src/pages/UnblockerPage.module.css:316` — `max-width: 720px`
- **Seis breakpoints ad-hoc sin token compartido:** 420, 560, 640, 720, 820, 900. `theme.css` define escalas de spacing, tipografía, radios, sombras y motion (`theme.css:99-144`) pero **ningún** token de breakpoint.
- **Lo que sí está bien:** el meta viewport existe — `frontend/index.html:5` — `<meta name="viewport" content="width=device-width, initial-scale=1.0" />`. Es decir, la página **intenta** ser responsive; simplemente no tiene las reglas.
- **Pantallas grandes sin ninguna regla responsive** (verificado por ausencia en el listado de 13): `App.module.css` (el shell y la nav), `SettingsPage.module.css`, `ExecutionHistoryPage.module.css`, `IncidentInboxPage.module.css`, `PlansBoardPage.module.css`, `CostCenterPage.module.css`, `EvolutionCenterPage.module.css`, `DocsPage.module.css`, `StatesConfigPage.module.css`, `SprintBoardPage.module.css`, `ReviewInboxPage.module.css`, `SystemLogsPage.module.css`, `UserStatsPage.module.css`, `MigratorPage` (sin `.module.css` propio).
- **Impacto usuario:** en tablet o en una ventana angosta, las pantallas más densas (tablas, grillas de DevOps, historial) desbordan sin adaptarse. Combinado con H-05, la propia navegación tampoco se recupera.
- **Impacto negocio:** si el operador espera revisar el estado desde una tablet, no puede. Si nunca lo va a hacer, se está pagando el costo de mantener 13 media queries huérfanas que dan una falsa sensación de soporte.
- **Severidad:** **media** — y es, ante todo, una **decisión pendiente**, no un bug.
- **Frecuencia:** permanente por debajo del ancho de corte de cada pantalla.
- **Recomendación concreta — elegir una de dos, explícitamente:**
  - **Opción A (recomendada para producción inmediata): declarar desktop-only.** Documentarlo en `docs/sistema/07-frontend.md`, fijar un ancho mínimo soportado (p. ej. 1280px), y en viewports menores mostrar un aviso honesto en lugar de un layout roto. Costo: bajo. Ejemplo de microcopy:
    > 🖥 **Stacky está optimizado para pantallas de 1280px o más.** En esta ventana algunas tablas pueden desbordarse. Podés seguir, o ampliar la ventana para ver todo. · `[Seguir igual]`
  - **Opción B: soportar tablet de verdad.** Tokenizar 2-3 breakpoints en `theme.css`, migrar los 6 valores ad-hoc, y priorizar las 5 pantallas de uso más frecuente. Costo: alto; no cabe antes del lanzamiento.
- **Cómo validar (opción A):** gate de grep — cualquier `@media` de viewport nueva debe usar un token/valor de la lista aprobada, no un literal nuevo. Smoke manual: abrir las 5 pantallas principales a 1280px y confirmar que no hay scroll horizontal del `body`.
- **Criterio de aceptación:** el ancho mínimo soportado está documentado; a ese ancho, las 5 pantallas principales no producen scroll horizontal del documento; los breakpoints existentes están reducidos a un conjunto declarado.
- **Archivos a modificar:** `frontend/src/theme.css` (tokens de breakpoint, si opción B), `docs/sistema/07-frontend.md` (la decisión), los 12 archivos listados (si se consolidan breakpoints).

### H-11 · Estado de capacidades fabricado y callback muerto en la ruta de producción del publicador de pipelines — `[CÓDIGO]`

- **Pantalla/flujo:** DevOps → Publicaciones → previsualización de YAML del pipeline.
- **Problema:** el componente de previsualización recibe un objeto de "health" **inventado en el sitio de llamada**, con todas las capacidades forzadas, y un `refetchHealth` que no hace nada — mientras el `ctx` real está disponible y se usa seis líneas más abajo.
- **Evidencia:**
  - `frontend/src/components/devops/PublicationsSection.tsx:539-543`:
    ```tsx
    <PipelineYamlPreview
      spec={materializedDraft}
      ctx={{ health: { flag_enabled: true, generator_enabled: true, trigger_enabled: false, publications_enabled: true }, refetchHealth: () => {} }}
      localErrors={[]}
    />
    ```
  - El `ctx` real existe y se pasa correctamente al componente hermano: `frontend/src/components/devops/PublicationsSection.tsx:546-550` — `<PreflightPanel ctx={ctx} … />`. También `:527` y `:566` y `:570` usan `ctx`.
- **Por qué importa (no es cosmético):** la previsualización renderiza como si `flag_enabled`, `generator_enabled` y `publications_enabled` estuvieran **siempre** encendidas, independientemente del estado real del backend, y como si `trigger_enabled` estuviera **siempre apagada**. Es exactamente la categoría "la interfaz promete algo distinto de lo que el backend ejecuta": el operador puede ver una previsualización válida de un pipeline cuya generación el backend rechazaría, o no ver una afordancia de disparo que sí está habilitada. `localErrors={[]}` además fuerza "sin errores locales".
- **Impacto usuario:** confianza mal calibrada en la previsualización, en un flujo (publicar un pipeline) donde equivocarse tiene costo real en el repositorio de destino.
- **Impacto negocio:** el operador descubre la discrepancia recién al ejecutar, que es el momento más caro.
- **Severidad:** **media** (alta si la previsualización se usa como gate de decisión antes de commitear)
- **Frecuencia:** cada previsualización de YAML materializado en ese panel.
- **Recomendación concreta:** pasar el `ctx` real, igual que hacen las cuatro llamadas vecinas: `ctx={ctx}`. Si `PipelineYamlPreview` necesita un subconjunto, que lo derive del `ctx` real. Cambio de una línea.
- **Cómo validar:** gate de grep/ratchet: prohibir literales `flag_enabled:` / `_enabled: true` dentro de props `ctx=` en `frontend/src/components/devops/**` (fuera de tests). Smoke manual: apagar la flag del generador, abrir la previsualización, y verificar que refleja el estado real.
- **Criterio de aceptación:** ninguna prop `ctx` en la ruta de producción contiene un objeto `health` literal; el gate falla si se reintroduce.
- **Archivos a modificar:** `frontend/src/components/devops/PublicationsSection.tsx:541`.
- **Observación colateral en el mismo bloque:** estilos inline conviviendo con el módulo CSS del propio componente — `PublicationsSection.tsx:552` (`style={{ marginTop: '12px', display: 'flex', gap: '8px' }}`), `:556` y `:560` (`style={{ padding: '10px 20px' }}`), mientras las mismas líneas usan `className={styles.btnSuccess}`. Relevante para la deuda de design system (§5).

### H-12 · "Funcionalidad desactivada" viaja con cuatro códigos HTTP distintos, y el frontend casi no los distingue — `[CÓDIGO]`

- **Problema:** la misma semántica ("esta feature está apagada") se expresa con 403, 404, 409 y 503 según el módulo. El frontend no tiene una forma uniforme de reconocerla, así que la trata como un error genérico.
- **Evidencia y conteo.** Comando:
  ```
  grep -rnE 'deshabilitad' backend/api --include=*.py | grep -oE '\), (40[0-9]|50[0-9])|, (40[0-9]|50[0-9])$' | grep -oE '[45][0-9][0-9]' | sort | uniq -c
  ```
  Resultado: **403 × 9 · 404 × 4 · 409 × 1**. Más `503` verificado aparte en `backend/api/migrator.py:101`. Total de menciones de "deshabilitad*": **37 en 16 archivos** (`grep -rcE 'deshabilitad' backend/api --include=*.py | grep -v ":0"`).
  - 403: `backend/api/db_compare.py:38`, `db_compare_masking.py:23,25`, `db_compare_repo.py:25,27`, `db_compare_watch.py:19,21`, `db_compare_demo.py:24,29`
  - 404: `backend/api/diag.py:1058`, `docs.py:222`, `plans_board.py:25`, `evolution.py` (familia)
  - 503: `backend/api/migrator.py:101`
- **Del lado del frontend, la capacidad de distinguirlo es casi nula:** `grep -rn "feature_disabled" frontend/src --include=*.ts --include=*.tsx | grep -v __tests__ | wc -l` → **3**, y dos de esas tres son **comentarios**, no lógica: `frontend/src/api/client.ts:93` (*"Necesario para distinguir 404 feature_disabled de un backend caido"*) y `frontend/src/api/endpoints.ts:5303` (*"404 feature_disabled llega como errorBody, NO como excepcion"*).
- **Impacto usuario:** "está apagado" (acción: encenderlo en Configuración) es indistinguible de "no existe" (404), "conflicto" (409) y "el servidor no está disponible" (503). El operador no puede saber si debe configurar algo, esperar, o reportar un bug.
- **Impacto negocio:** imposible construir un manejo uniforme de "feature apagada" en la UI — que es justamente el estado más común en un producto con 403 flags.
- **Severidad:** **media**
- **Frecuencia:** cada interacción con una funcionalidad apagada.
- **Recomendación concreta:** fijar el contrato: **un** status (`403` es el más defendible: el recurso existe, está prohibido por configuración) **y** un `error` machine-readable estable `"feature_disabled"` en el cuerpo, con `detail.flag`. Así el frontend detecta la condición por el campo `error`, no por el status, y un cambio futuro de status no rompe la UI. Encaja con H-06 y H-03: los tres se arreglan con la misma normalización de cuerpo de error.
- **Cómo validar:** test de backend que recorra los endpoints con flag apagada y afirme `status == 403` y `body["error"] == "feature_disabled"`. Se corre contra el defecto: hoy debe fallar en ≥5 endpoints por status y en ~todos por el campo `error`.
- **Criterio de aceptación:** todos los endpoints con gate de flag responden el mismo status y el mismo `error` machine-readable; existe un único helper en el frontend que detecta la condición y renderiza el estado vacío correspondiente.
- **Archivos a modificar:** los 16 archivos de `backend/api/` con gates de flag; un helper nuevo en `frontend/src/api/`.

### H-13 · Una URL desconocida aterriza en Tickets sin decir que no existía — `[CÓDIGO]`

- **Problema:** el router no tiene concepto de "ruta no encontrada": cualquier path desconocido se normaliza silenciosamente a la vista índice.
- **Evidencia:**
  - `frontend/src/services/routes.ts:44-46` — `tabFromSegments`: *"Vacío o desconocido => 'tickets' (índice)"* ⇒ `return matchKnownTab(segments) ?? "tickets";`
  - `frontend/src/services/routes.ts:54-55` — `parseRoute`: `const known = matchKnownTab(segments); const tab = known ?? "tickets";`
  - La normalización se escribe en la barra de direcciones al montar: `frontend/src/App.tsx:198-202` — `window.history.replaceState({}, "", canonical)`.
- **Impacto usuario:** un link con un typo, o un link a una pantalla renombrada/retirada, lleva a Tickets y **la URL se reescribe** para que parezca que eso era lo pedido. El operador no puede distinguir "escribí mal" de "esa pantalla ya no existe" de "no tengo la flag". Esto agrava H-01: el rebote por gate y el rebote por ruta inexistente son indistinguibles entre sí.
- **Severidad:** **baja** aislado; **media** por cómo enmascara H-01.
- **Frecuencia:** links viejos, typos, documentación desactualizada.
- **Recomendación concreta:** conservar el fallback (es un buen default: nunca pantalla en blanco) pero **avisar**. Distinguir en `RouteState` el caso "ruta desconocida" y mostrar un aviso descartable sobre la vista índice.
- **Ejemplo tangible del microcopy:**
  > 🧭 **No encontramos la pantalla `/reportes-viejos`.** Te trajimos al tablero de Tickets. · `[Ver todas las secciones]` `[Cerrar]`
- **Cómo validar:** test `.ts` puro sobre `parseRoute`: `parseRoute("/pepe", "")` debe devolver un `RouteState` con la marca de ruta desconocida, y `parseRoute("/devops", "")` sin ella. `routes.ts` ya es un módulo puro con tests — es el lugar más barato del repo para agregar esto.
- **Criterio de aceptación:** `parseRoute` expone si el path era conocido; la UI muestra el aviso sólo cuando no lo era; el round-trip idempotente de `serializeRoute`/`parseRoute` (contrato de `routes.ts:56-59`) se mantiene.
- **Archivos a modificar:** `frontend/src/services/routes.ts:44-46`, `:51-79`; `frontend/src/App.tsx:198-202`.

### H-14 · El contrato de tipos de `FlagSpec` omite un tipo que sí existe 10 veces — `[DRIFT]`

- **Problema:** la documentación en código del tipo de una flag enumera cinco tipos; el registro usa seis.
- **Evidencia:**
  - `backend/services/harness_flags.py:23` — `type: str            # "bool" | "csv" | "int" | "float" | "json"` — **no menciona `"str"`**.
  - Conteo real por tipo (mismo comando que el inventario base): `bool` 294 · `int` 64 · `csv` 25 · **`str` 10** · `float` 9 · `json` 1.
  ```
  grep -oE '\btype="[a-z]+"' backend/services/harness_flags.py | sort | uniq -c
  ```
- **Impacto:** cualquiera que implemente un renderizador, validador o exportador de flags leyendo ese comentario como contrato dejará afuera 10 flags de tipo texto. Es el tipo de omisión que produce un campo que no se puede editar por UI — y el riel del producto es que **toda** configuración del operador va por UI.
- **Severidad:** **baja** (documental, pero con consecuencia funcional plausible)
- **Recomendación concreta:** corregir el comentario a `"bool" | "csv" | "int" | "float" | "str" | "json"`. Mejor aún: derivar la lista de tipos válidos de una constante y validar en el arranque que todo `FlagSpec.type` pertenezca a ella, así el comentario deja de ser la fuente de verdad.
- **Cómo validar:** test de backend que afirme que el conjunto de `type` presentes en `FLAG_REGISTRY` es igual al conjunto declarado en la constante. Hoy, con el comentario como referencia, daría rojo.
- **Criterio de aceptación:** existe una constante única de tipos válidos; un test afirma igualdad de conjuntos contra el registro; el comentario ya no enumera tipos a mano.
- **Archivos a modificar:** `backend/services/harness_flags.py:21-41`.

### H-15 · Deuda de estilo: 723 estilos inline y 1314 colores literales conviven con un design system completo y una librería de 16 primitivas — `[CÓDIGO]`

- **Problema:** no es que falte el sistema (existe y es bueno, ver F-01 y F-12). Es que una parte grande de la UI no lo usa, y el resultado es inconsistencia visual real entre pantallas y un tema claro que sólo funciona donde se usaron tokens.
- **Evidencia y conteos.** Comandos (ejecutados desde `frontend/src`, excluyendo `__tests__` y `*.test.*`):
  ```
  grep -rn "style={{" . --include=*.tsx | grep -v __tests__ | grep -v "\.test\." | wc -l
  # 723
  grep -rnoE "#[0-9a-fA-F]{3,8}\b" --include=*.css . | grep -v "theme.css" | wc -l
  # 1314
  ```
- **Estilos inline — top 10 archivos** (`grep -rc "style={{" --include=*.tsx .`):
  `components/devops/BlockProperties.tsx` 58 · `components/devops/PipelineBuilderSection.tsx` 53 · `components/devops/PublicationsSection.tsx` 34 · `components/devops/RemoteConsoleSection.tsx` 33 · `components/MigratorWizard.tsx` 32 · `components/ConfigTransferPanel.tsx` 32 · `components/devops/ServersSection.tsx` 31 · `components/devops/EnvironmentsSection.tsx` 28 · `components/devops/PipelineDoctorPanel.tsx` 27 · `components/PipelineGeneratorPanel.tsx` 25
- **Hex literales en CSS (excluyendo `theme.css`) — top 10 archivos:**
  `pages/PMCommandCenter.module.css` 140 · `components/AgentHistoryPage.module.css` 84 · `pages/UnblockerPage.module.css` 68 · `components/ChatDrawer.module.css` 57 · `pages/SystemLogsPage.module.css` 56 · `components/DataReadinessModal.module.css` 53 · `pages/PlansBoardPage.module.css` 39 · `pages/DocsPage.module.css` 38 · `components/SeedPreviewPanel.module.css` 36 · `components/DocViewer.module.css` 36
- **Concentración del daño:** la deuda de estilos inline está fuertemente concentrada en **DevOps** (6 de los 10 primeros archivos están bajo `components/devops/`). La deuda de color está concentrada en **PM Command Center** (140 literales en un solo archivo, ~11% del total del repo).
- **Por qué importa más allá de la prolijidad:** cada literal de color es un punto que **el tema claro no puede re-apuntar**. H-07 es el caso demostrado de esto en la nav; con 1314 literales, la probabilidad de que el tema claro tenga más zonas ilegibles es alta. Y cada `style={{}}` es un punto que el `prefers-reduced-motion` global y los tokens de densidad tampoco alcanzan.
- **Severidad:** **media** (deuda estructural, no bloquea tarea; pero es la causa raíz de H-07 y bloquea la garantía del tema claro)
- **Frecuencia:** permanente.
- **Recomendación concreta — por concentración, no en masa:**
  1. **No hacer una migración global.** 1314 + 723 cambios en un solo lote es exactamente el tipo de barrido que rompe cosas en silencio.
  2. Atacar por concentración: `PMCommandCenter.module.css` (140 hex) y los 6 archivos de `devops/` de la tabla cubren una fracción desproporcionada de la deuda.
  3. Extender el alcance del ratchet de deuda de UI a los archivos nuevos, para que la deuda no crezca mientras se paga la vieja.
- **Cómo validar:** ratchet con línea base congelada por archivo: el conteo de `style={{` y de hex literales por archivo no puede subir. Se corre contra el defecto: agregar un `style={{}}` a un archivo ya congelado debe poner el gate en rojo.
- **Criterio de aceptación:** línea base registrada por archivo con los conteos de arriba; el gate falla ante cualquier incremento; los archivos priorizados bajan su conteo a 0 en su iteración asignada.
- **Archivos a modificar:** los 10 + 10 archivos listados, por orden de concentración; el archivo del ratchet de deuda de UI.

### H-16 · La documentación canónica del frontend omite 4 de las 18 pantallas y su anclaje de evidencia caducó — `[DOC]` + `[DRIFT]`

- **Problema:** el único documento canónico del frontend enumera 14 pantallas; existen 18. Además, la cita de evidencia que el propio documento usa para respaldar esa lista apunta a líneas que ya no contienen lo que dice.
- **Evidencia del lado del documento:** `docs/sistema/07-frontend.md:14` (el archivo completo tiene **37 líneas** — `wc -l docs/sistema/07-frontend.md`):
  > `- Páginas: TeamScreen, TicketBoard, ReviewInboxPage, UnblockerPage, PMCommandCenter, SystemLogsPage, SettingsPage, DocsPage, MemoryPage, DiagnosticsPage, ExecutionHistoryPage, MigratorPage, DevOpsPage, DbComparePage. [V: App.tsx:2-15,205-215]`
- **Evidencia del lado del código:** la fuente única de pantallas son 18 tabs — `frontend/src/services/routes.ts:5-9` (`type Tab`) y `:15-22` (`TAB_PATHS`), espejados en `frontend/src/components/shell/shellNav.ts:5-9` y `TAB_META` `:16-35`.
- **Las 4 pantallas ausentes del documento**, cada una verificada como existente y montada:
  - **`CostCenterPage`** — Centro de Costos. Import `App.tsx:19`, montaje `App.tsx:316`, ruta `/costcenter` (`routes.ts:20`), archivo `frontend/src/pages/CostCenterPage.tsx`.
  - **`PlansBoardPage`** — Planes. Import `App.tsx:20`, montaje `App.tsx:317`, ruta `/planes` (`routes.ts:20`), archivo `frontend/src/pages/PlansBoardPage.tsx`.
  - **`EvolutionCenterPage`** — Evolución. Import `App.tsx:21`, montaje `App.tsx:318`, ruta `/evolution` (`routes.ts:20`), archivo `frontend/src/pages/EvolutionCenterPage.tsx`.
  - **`IncidentInboxPage`** — Incidencias. Import `App.tsx:5`, montaje `App.tsx:319`, ruta `/incidencias` (`routes.ts:21`), archivo `frontend/src/pages/IncidentInboxPage.tsx`.
- **El anclaje de evidencia del documento caducó:** la cita dice `[V: App.tsx:2-15,205-215]`. Hoy los imports de páginas viven en `App.tsx:3-21` y el fragmento que las monta está en `App.tsx:300-321`. El rango `205-215` cae dentro del efecto que lee el flag del Centro de Actividad (`App.tsx:206-220`), que no tiene nada que ver con la lista de páginas. Es decir: el documento **parece** verificado (lleva la marca `[V:]`) pero su verificación ya no es comprobable en las líneas que cita.
- **Impacto:** cualquiera que use `docs/sistema/07-frontend.md` para saber qué pantallas tiene el producto — un operador nuevo, un agente, un redactor de material de capacitación — va a omitir 4 secciones, tres de las cuales (Centro de Costos, Planes, Evolución) son módulos completos. Y la marca `[V:]` transmite una confianza que el anclaje ya no sostiene.
- **Severidad:** **media** (documental, pero es la fuente única canónica y su marca de verificación es engañosa)
- **Frecuencia:** permanente.
- **Recomendación concreta:**
  1. Agregar las 4 pantallas a `docs/sistema/07-frontend.md:14`.
  2. **Dejar de anclar a rangos de línea de `App.tsx`.** Es el archivo que más se mueve (esta auditoría encontró tres anclajes caducados en él). Anclar a `frontend/src/services/routes.ts` `TAB_PATHS` / `type Tab`, que es la fuente única declarada y estructuralmente estable.
  3. Mejor aún: un gate que compare la lista del documento contra `TAB_PATHS` y falle ante divergencia, para que este drift no pueda repetirse.
- **Cómo validar:** test/gate que parsee la lista de páginas de `07-frontend.md:14` y afirme igualdad de conjuntos contra las claves de `TAB_PATHS` en `routes.ts`. Se corre contra el defecto: hoy debe fallar señalando exactamente las 4 faltantes.
- **Criterio de aceptación:** el conjunto de pantallas del documento es igual al de `TAB_PATHS`; el gate falla si alguien agrega un tab sin documentarlo; ningún anclaje de evidencia del documento apunta a un rango de línea de `App.tsx`.
- **Archivos a modificar:** `docs/sistema/07-frontend.md:14`; nuevo gate.

### H-17 · Tres mecanismos distintos de estado de carga, y el más usado es texto plano en lugar de la primitiva que ya existe — `[CÓDIGO]`

- **Problema:** existe una primitiva `Skeleton` y una `Spinner` (F-12), pero el patrón dominante para "estoy cargando" es un literal *"Cargando…"* escrito a mano. El operador ve tres experiencias de espera distintas según la pantalla.
- **Evidencia y conteos.** Comandos (desde `frontend/src`, `.tsx`, excluyendo `__tests__` y `*.test.*`):
  ```
  grep -rlniE "\b(loading|isLoading|cargando)\b" . --include=*.tsx | ... | wc -l   # 108 archivos con noción de carga
  grep -rln "Skeleton" . --include=*.tsx | ... | wc -l                             #  28 archivos usan Skeleton (62 usos)
  grep -rln "Spinner"  . --include=*.tsx | ... | wc -l                             #   7 archivos usan Spinner
  grep -rln "Cargando" . --include=*.tsx | ... | wc -l                             #  59 archivos usan texto plano (84 usos)
  ```
- **Lectura de los números:** de 108 archivos con estado de carga, **35** usan una primitiva (28 `Skeleton` + 7 `Spinner`) y **59** usan texto plano. El texto plano es el mecanismo **más frecuente**, con casi el doble de archivos que el esqueleto. Los ~14 restantes no muestran nada identificable por grep.
- **Impacto usuario:** la espera se siente distinta en cada pantalla — en unas el layout se prefigura con esqueletos (bueno: da sensación de progreso y evita salto de layout), en la mayoría aparece un texto que luego es reemplazado de golpe por el contenido (salto de layout, y sin pista de cuánto falta). En procesos largos, un texto estático es indistinguible de una pantalla colgada — que es justamente el modo de falla de H-04.
- **Impacto negocio:** la percepción de velocidad y calidad depende de en qué pantalla cayó el operador. Y el trabajo de construir `Skeleton` está pagado pero cobrado a un tercio.
- **Severidad:** **media**
- **Frecuencia:** permanente, en las 59 pantallas/componentes con texto plano.
- **Recomendación concreta:** fijar la regla por tipo de espera, no por gusto del archivo: **`Skeleton`** cuando se conoce la forma del contenido que viene (tablas, listas, tarjetas) porque evita el salto de layout; **`Spinner`** para acciones puntuales dentro de un botón o una fila; **texto plano nunca** como único indicador. Migrar por concentración, empezando por las pantallas de mayor tráfico.
- **Ejemplo tangible (estado de carga de una tabla):** en lugar de `<p>Cargando…</p>`, tres a cinco filas de `<Skeleton>` con la misma altura y número de columnas que la tabla real, de modo que el contenido aterrice sin mover nada.
- **Cómo validar:** gate de grep/ratchet con línea base por archivo: el conteo de literales `Cargando` no puede subir, y baja a 0 en los archivos priorizados. Smoke manual: con la red limitada a 3G lento en las herramientas del navegador, recorrer las 5 pantallas principales y confirmar que ninguna muestra texto plano como único indicador ni salta de layout al llegar los datos.
- **Criterio de aceptación:** ningún archivo nuevo introduce `Cargando` como único indicador; las 5 pantallas de mayor uso usan `Skeleton` con la forma del contenido real; el ratchet falla ante cualquier incremento del conteo base.
- **Archivos a modificar:** los 59 archivos con literal `Cargando`, por orden de tráfico; el archivo del ratchet.
- **Sobre los estados vacíos, lo que sí y lo que no puedo afirmar:** hay **183** guardas `length === 0` y **149** literales de vacío (**51** con `"No hay "` y **98** con `"Sin "`), lo que indica que los estados vacíos existen de forma extendida y no son un hueco. **No verifiqué su calidad** — es decir, si cada uno ofrece mensaje *más próxima acción* o si es sólo una frase seca —, porque eso requiere leer los 149 sitios. No afirmo ni que estén bien ni que estén mal. Ver §8.

---

## Preparación para producción: lo que se buscó y NO se encontró — `[CÓDIGO]`

Registro explícito de los barridos de riesgo que dieron **limpio**. Los incluyo porque en un gate de producción "se buscó y no está" es información tan valiosa como un hallazgo, y porque varios de estos son los que normalmente hunden un lanzamiento.

| Riesgo buscado | Resultado | Comando |
|---|---|---|
| Diálogos nativos sin estilo (`alert`/`confirm`/`prompt`) | **0** | `grep -rnE "(^\|[^.\w])(window\.)?(alert\|confirm\|prompt)\(" . --include=*.ts --include=*.tsx \| grep -v __tests__ \| grep -v "\.test\." \| wc -l` |
| `console.*` olvidados en ruta de producción | **8**, todos legítimos (ver abajo) | `grep -rnE "console\.(log\|warn\|error\|debug\|info)" . --include=*.ts --include=*.tsx \| grep -v __tests__ \| grep -v "\.test\."` |
| Marcadores `TODO`/`FIXME`/`XXX`/`HACK` reales | **0** (ver la nota de falso positivo) | `grep -rnE "(TODO\|FIXME\|XXX\|HACK)[:( ]" . --include=*.ts --include=*.tsx \| grep -v __tests__ \| grep -v "\.test\."` → 20 líneas, **todas** falsos positivos |

**Nota metodológica importante — el barrido de `TODO` en un código en español es engañoso:** las 20 coincidencias son la palabra castellana *"todo"* (= *la totalidad*), no el marcador de tarea pendiente. Ejemplos verificados: `services/routes.ts:28` (`// TODO otro query param, preservado verbatim` = *"todo otro query param"*), `pages/EvolutionCenterPage.tsx:1` (`TODO estilo va en el .module.css` = *"todo el estilo va en…"*), `components/AgentHistoryPage.tsx:630` (`Eliminar TODO el historial`), `services/undoManager.ts:143` (`Commitea TODO lo pendiente`). **No hay deuda declarada de tipo TODO/FIXME en el frontend.**

**Los 8 `console.*`, uno por uno, con veredicto:**

- `components/PageErrorBoundary.tsx:32` — `console.error("[PageErrorBoundary] render error:", error, info)` — **correcto**: es el canal de diagnóstico de un error boundary, con `eslint-disable` deliberado.
- `components/RecoverExecutionButton.tsx:145` y `:209` — `console.error("[RecoverExecution] Gateway error", {…})` — **correcto y ejemplar**: el propio contrato del componente lo documenta en `:15` — *"401/500 → toast genérico + console.error (sin stacktrace al usuario)"*. Es exactamente el patrón que H-03 pide generalizar: mensaje limpio al operador, detalle técnico a la consola.
- `pages/PMCommandCenter.tsx:911` — `console.warn("generate recommendations failed:", e)` y `:975` — `console.warn("sentiment analyze failed:", e)` — **aceptable**, aunque son fallas silenciosas: el operador no recibe ningún aviso de que la recomendación o el análisis no se produjeron. Candidato menor a mejorar (estado de error visible en lugar de sólo consola).
- `services/shortcuts.ts:282` — `console.warn("[shortcuts] combos en colisión:", grupos)` — **correcto**: diagnóstico de desarrollo para colisiones de atajos.
- `components/OperationalHealthCard.tsx:209` — `console.log(\`Abrir ejecución #${id}\`)` — **código muerto, NO un botón muerto.** Es el fallback `defaultOpenExecution` (`:207-210`) que sólo corre si el padre no pasa `onOpenExecution`. Verifiqué el único consumidor: `pages/DiagnosticsPage.tsx:287` — `<OperationalHealthCard onOpenExecution={setDetailId} />` — **sí** pasa el handler (`grep -rn "OperationalHealthCard" . --include=*.tsx`). En producción el fallback nunca se ejecuta.
  - **`[BUENA PRÁCTICA]`:** el fallback silencioso es una trampa latente — si alguien reutiliza la tarjeta sin la prop, las filas quedan clickeables y no pasa nada. Preferible hacer la prop obligatoria (ya está tipada como opcional en `:128`) y borrar el fallback, en lugar de degradar a un `console.log`. Severidad **baja**; no es un defecto observable hoy.

**Lo que este barrido NO cubre** (declarado, no asumido): mocks/datos de muestra en ruta de producción más allá del caso de H-11, URLs y credenciales hardcodeadas, mezcla español/inglés en textos de usuario, y `JSON.stringify` visible al operador. Ver §8.

---

## Fortalezas verificadas (no son hallazgos: son activos a preservar) — `[CÓDIGO]`

Las incluyo porque un informe de gate que sólo lista defectos lleva a decisiones malas: varias de estas piezas son la razón por la que el veredicto es GO condicionado y no NO-GO.

- **F-01 · Design system real, no un archivo de colores.** `frontend/src/theme.css` define escala de spacing de 9 pasos (`:100-108`), escala tipográfica de 7 pasos + pesos + line-heights (`:111-124`), radios (`:127-130`), 4 niveles de sombra (`:133-136`), tokens de motion con duraciones y curvas (`:139-159`), y estados semánticos completos (success/warning/danger/info/neutral con variantes text/solid/bg/border, `:61-84`).
- **F-02 · Tema claro completo y con contraste declarado.** `theme.css:172-244` re-apunta **sólo** los tokens de color, dejando spacing/tipografía/radios/motion invariantes — que es la forma correcta. Su comentario (`:166-171`) afirma verificación WCAG AA token a token. (La excepción es H-07, que no es del tema sino de tres literales fuera del sistema.)
- **F-03 · Foco visible global por teclado.** `theme.css:366-370` — `:where(a, button, input, textarea, select, [tabindex], [role="button"], [role="tab"]):focus-visible` con el token `--focus-ring`. Baja especificidad deliberada para permitir override por componente. Esto cubre la base de navegación por teclado en toda la app de una sola vez.
- **F-04 · `prefers-reduced-motion` respetado globalmente.** `theme.css:377-384` neutraliza animaciones y transiciones, incluidos spinners infinitos, con `!important` para ganarle a estilos inline. Patrón WCAG SC 2.2.2 / 2.3.3 aplicado correctamente.
- **F-05 · Error boundary por página que preserva el shell.** `frontend/src/components/PageErrorBoundary.tsx` — `role="alert"` (`:58`), botón de reintento (`:67`), reset automático al cambiar de pestaña (`:45-49`), y traza consultable publicada al Centro de Actividad (`:35-42`). Un throw en el render de un tab **no** blanquea la app. Montado en las dos ramas de nav (`App.tsx:346` y `:495`). Su única debilidad es que muestra el mensaje crudo (`:62`), que es H-03, no un defecto del boundary.
- **F-06 · Router propio tipado con contrato explícito e idempotente.** `frontend/src/services/routes.ts` — parser/serializer puros que no tocan `window` (`:3`), round-trip idempotente razonado en comentarios (`:56-59`, `:112-116`), validación estricta de `?exec=` con regex en lugar de `Number()` y las trampas documentadas (`:67-70`), y compatibilidad hacia atrás con la clave legacy `execution` (`:32`, `:71-73`). Es de mejor calidad que el uso típico de un router de librería.
- **F-07 · `popstate` re-deriva todo el estado.** `App.tsx:188-193` — Atrás/Adelante mueven tab, sub-tab y drawer con la página ya montada. El historial del navegador funciona de verdad.
- **F-08 · Onboarding con detección real de primera vez.** `App.tsx:226-232` + `services/onboarding` — `migrateLegacy` para la clave del prototipo y `shouldAutoShow` para auto-mostrar **sólo** en first-run genuino; el comentario (`:222-225`) documenta que nada en producción resetea el flag. El tour existe (`OnboardingTour`, `App.tsx:27,512`).
- **F-09 · Modo de densidad compacta.** `theme.css:250-260` re-apunta **sólo** la escala de spacing, dormido salvo `data-density="compacto"`, con render byte-idéntico en el modo base. Buena disciplina de token.
- **F-10 · Panel global de ejecuciones activas con cancelación.** `App.tsx:522-525` — el comentario declara que permite cancelar cualquier run en curso, *incluidos huérfanos/colgados de otro proyecto que el board no muestra*. Es una afordancia de recuperación deliberada para el peor caso operativo.
- **F-11 · `color-scheme` nativo declarado.** `theme.css:279` — `color-scheme: var(--color-scheme)` en `html, body, #root`, con el comentario explicando que evita el bug "blanco sobre blanco" en los `<option>` de `<select>` nativos. Es un detalle que casi nadie cubre.
- **F-12 · Librería de primitivas real: 16 componentes en `frontend/src/components/ui/`.** Verificado por `ls -1 frontend/src/components/ui/`: `Button`, `Card`, `Checkbox`, `Field`, `IconButton`, `Input`, `Select`, `Skeleton`, `Spinner`, `StatusChip`, `Tabs`, `Textarea`, más las cuatro piezas de diálogo (`Dialog`, `ConfirmDialog`, `AlertDialog`, `PromptDialog`) y el host. Cada una con su `.module.css`. Incluye **`Skeleton`** y **`Spinner`**, es decir: las primitivas de estado de carga existen. Esto reencuadra H-15: la deuda de estilo no es por falta de primitivas, es por no usarlas.
- **F-13 · Sistema de diálogos promise-based, en cola, con settle idempotente.** `frontend/src/components/ui/DialogHost.tsx` — montado una sola vez alrededor de `<App/>` (`:20-21`); expone `useConfirm`/`useAlert`/`useTextPrompt` que devuelven promesas awaitables. La regla dura está implementada, no sólo documentada: `settle` (`:66-71`) es idempotente vía `settledRef`, así que **toda** vía de cierre resuelve la promesa y ningún `await` queda colgado. Los hooks fallan ruidosamente fuera del provider (`:141`, `:147`, `:153`). Adopción verificada: **26** `useConfirm()`, 3 `useTextPrompt()`, 1 `useAlert()`; **31 sitios de llamada** a `askConfirm(` en 22 archivos. Esto explica el 0 de diálogos nativos: fueron reemplazados de verdad, no parcialmente.
- **F-14 · Las acciones destructivas están protegidas, y el diseño del diálogo es deliberadamente conservador.** `frontend/src/components/ui/ConfirmDialog.tsx:42,48` — cuando `tone="danger"`, el `autoFocus` va al botón **Cancelar**, no al de confirmar, con el motivo escrito en `:9-10`: *"Foco inicial: en Cancelar si es danger (para no confirmar por Enter accidental)"*. Escape, backdrop y ✕ resuelven a `false` (`:19-20`). Ejemplo de microcopy real de la casa, en `components/AgentHistoryPage.tsx:630`: título *"Eliminar historial"*, mensaje *"¿Eliminar TODO el historial del ticket #N …? Se borrarán N ejecución(es). Esta acción no se puede deshacer."*, `tone: "danger"`, `confirmLabel: "Eliminar todo"` — nombra el objeto, **cuantifica** el daño y advierte que es irreversible. Es el estándar que el resto del producto debería copiar.
- **F-15 · Type-to-confirm implementado y aplicado a la acción más peligrosa.** `frontend/src/components/ui/dialogHostReducer.ts:24-26` — `textPromptCanConfirm(value, requiredText)` habilita el botón sólo si el texto tipeado coincide exactamente. Usado donde corresponde: `frontend/src/components/devops/DeploymentsSection.tsx:205` — `requiredText: app.id` para un despliegue. `PromptDialog.tsx:12` además prohíbe explícitamente el `<input>` crudo.
- **F-16 · Modales con accesibilidad completa.** `frontend/src/components/ui/Dialog.tsx` — `role="dialog"` + `aria-modal="true"` (`:192-193`), `aria-labelledby` con fallback a `aria-label` (`:194-195`), **focus-trap con wrap explícito en ambos extremos** (`:121-143`), **restore-focus** al disparador original (`:90`, `:111`), **`inert` sobre `#root`** mientras haya al menos un diálogo montado (`:48`, `:57`, `:66`) — el enfoque moderno correcto, superior al malabarismo con `aria-hidden` —, scroll-lock, y botón de cierre con `aria-label="Cerrar"` (`:171`). Cubre prácticamente toda la checklist de accesibilidad de modales.
- **F-17 · Guarda contra pérdida de trabajo en los diálogos.** `frontend/src/components/ui/Dialog.tsx:22` — *"Guarda de cierre: si dirty/busy, Escape y backdrop NO cierran"*. El riesgo de "cerré el modal sin querer y perdí lo que había escrito" está contemplado en la primitiva. (Sin verificar todavía si los formularios grandes que **no** usan `Dialog` tienen protección equivalente — ver §8.)

---

## 3. Evaluación por flujo

> **Cómo leer esta sección.** Los flujos con contenido abajo están **auditados con evidencia**. Los que aparecen como un encabezado sin cuerpo **no se auditaron en esta corrida** y están declarados en §8 con los archivos objetivo ya identificados; su encabezado se deja en su lugar a propósito, para que el vacío sea visible y no se confunda con "sin hallazgos". Ninguna conclusión de §1 depende de ellos.

### 3.1 Registro e inicio de sesión — **EL FLUJO NO EXISTE** `[CÓDIGO]`

- **Objetivo del usuario:** n/a.
- **Estado:** no hay login, registro, recuperación de contraseña, sesión ni cierre de sesión. Ver H-08 para la evidencia completa (`backend/api/_helpers.py:4-5`, `backend/app.py:824-826`, `frontend/src/api/client.ts:58,106,155,197`).
- **Consecuencia de que no exista:** en el modelo mono-operador local, ninguna para el usuario. Para el negocio, tres: atribución ficticia, atribución **inconsistente** (seis valores de reserva distintos), y ausencia total de límite de confianza si el backend se expone en red.
- **Lo que hay que decidir antes de producción:** el límite de red (bind a loopback, documentado). No un login.
- **Lo que NO hay que hacer:** construir RBAC. No protegería nada que hoy esté en riesgo y contradice el modelo del producto.

### 3.2 Permisos y errores de autorización — **NO EXISTEN COMO CONCEPTO** `[CÓDIGO]`

- **Estado:** los 403 de la API **no** son de autorización: son gates de feature flag (H-06, H-12). No hay roles, ni capacidades por usuario, ni pantallas restringidas.
- **Consecuencia UX concreta y verificada:** cuando el operador recibe un 403, el mensaje le habla de una **variable de entorno**, no de un permiso ni de un próximo paso. Con H-03 encima, lo ve crudo. Ese es el "permiso incorrecto" real del producto: no es un problema de autorización, es un problema de **estado de configuración mal comunicado**.
- **Recomendación:** tratar "feature apagada" como un **estado vacío de primera clase** de cada pantalla (con explicación y acción para activarla), no como un error. Ver H-12.

### 3.3 Onboarding y primeros pasos — EXISTE, cobertura por verificar `[CÓDIGO]` + `[HIPÓTESIS]`

- **Verificado:** el tour existe y se auto-muestra sólo en first-run real (`App.tsx:226-232`, `:512`; `services/onboarding` con `migrateLegacy` y `shouldAutoShow`). Hay un ancla de tour en la nav v1 (`App.tsx:352` — `data-tour="nav"`).
- **`[HIPÓTESIS]` a validar manualmente:** qué pasos cubre el tour, si cubre la nav v2 (el ancla `data-tour="nav"` está en la rama **v1**; si v2 es el default real por `config.py:1811`, hay que confirmar que el tour no apunta a un elemento que no se renderiza). **Paso manual:** limpiar el `localStorage` de onboarding, cargar la app con `STACKY_UI_SHELL_V2_ENABLED=true`, y verificar que cada paso del tour resalta un elemento existente.
- **Riesgo señalado:** un tour cuyo primer paso apunta al `data-tour="nav"` de la rama v1 no tendría objetivo cuando se renderiza la sidebar v2. Sería un defecto de primera-experiencia de frecuencia 100% para usuarios nuevos.

### 3.4 Selección / creación de cliente <!-- PENDIENTE -->
### 3.5 Creación de agentes <!-- PENDIENTE -->
### 3.6 Configuración del agente <!-- PENDIENTE -->
### 3.7 Selección de modelo / runtime / herramientas <!-- PENDIENTE -->
### 3.8 Configuración de integraciones (ADO / GitLab / Mantis) <!-- PENDIENTE -->
### 3.9 Pruebas en Agent Lab <!-- PENDIENTE -->
### 3.10 Ejecución y completion <!-- PENDIENTE -->

### 3.11 Gestión de errores — EVALUADO `[CÓDIGO]`

- **Objetivo del usuario:** entender qué falló, si es su culpa, y qué hacer.
- **Qué información recibe hoy:** el status HTTP, el statusText y el JSON crudo del cuerpo (H-03, `client.ts:206-209`), a veces con el nombre de una variable de entorno adentro (H-06).
- **Dónde puede equivocarse:** no puede distinguir feature apagada / no existe / conflicto / servidor caído, porque los cuatro llegan con status distintos y sin campo estable (H-12).
- **Cómo se recupera:** si el error fue en render, hay un botón **Reintentar** real (`PageErrorBoundary.tsx:67`) — bien. Si fue en una carga de datos, depende del llamador; si el backend está colgado, no hay recuperación porque no hay timeout (H-04).
- **Entiende qué ocurrió y el próximo paso:** **no.** Es la brecha más rentable de todo el informe, y el contrato para cerrarla (`errorBody` con `message` + `correlation_id`) ya está construido y sin usar.

### 3.12 Publicación del agente <!-- PENDIENTE -->
### 3.13 Edición de agentes publicados <!-- PENDIENTE -->
### 3.14 Documentación, RAG y grafo <!-- PENDIENTE -->

### 3.15 "Gestión de planes y límites" — REENCUADRE OBLIGATORIO `[CÓDIGO]`

El pedido original mezcla dos cosas distintas. Hay que separarlas antes de auditar, porque una existe y la otra no.

- **Lo que "Planes" SÍ es en Stacky:** los documentos internos de mejora `docs/<NN>_PLAN_*.md`, con su tablero (`frontend/src/pages/PlansBoardPage.tsx`, `frontend/src/plansBoard/`) y su gate por flag (`backend/api/plans_board.py:25` — `STACKY_PLANS_BOARD_ENABLED`; probe en `App.tsx:155-157`). Es una herramienta de **desarrollo del propio producto**, no una funcionalidad de cliente.
- **Lo que "Planes" NO es — barrido ejecutado, resultado concluyente:** no existe ninguna noción de plan comercial, suscripción vendida, cuota facturable, asiento, paywall, prueba gratuita ni conversión entre planes. Comando:
  ```
  grep -rniE "subscription|suscripci|paywall|\btier\b|billing|facturaci|\bseat\b|plan_type" \
    frontend/src backend/api backend/services --include=*.ts --include=*.tsx --include=*.py \
    | grep -v __tests__ | grep -v "/tests/" | wc -l
  # 77
  ```
  **Las 77 coincidencias son falsos positivos**, y verificarlas una por una es lo que convierte este barrido en evidencia. Las cuatro familias:
  1. **`tier` = nivel de complejidad de la UI, no nivel de precio.** `frontend/src/api/endpoints.ts:813` — `tier?: "simple" | "advanced"` (profundidad de una sección de flags); `frontend/src/components/harnessVisuals.ts:76-80` — `partitionSectionsByTier` reparte secciones entre `simple` y el resto.
  2. **`tier` = veredicto de un badge.** `frontend/src/components/ContractBadge.tsx:18-28` — `tier === "pass" ? "OK" : tier === "warn" ? "REVISAR" : "FALLO"`. Y `frontend/src/components/TicketFingerprint.tsx:116` — `tier?: "low" | "high"` es complejidad de ticket.
  3. **`subscription_type` = el plan de la cuenta de Anthropic del operador, no un plan de Stacky.** `frontend/src/api/endpoints.ts:2256` y `frontend/src/components/ClaudeCliConfigModal.tsx:208-209` lo muestran como badge de la sesión del CLI; `:219` — *"Iniciá sesión con tu cuenta o suscripción de Anthropic."* Es identidad **ante el proveedor de LLM**, no ante Stacky.
  4. **`suscripción`/`facturable` en el Centro de Costos = el costo propio de Stacky, declarado explícitamente NO facturable.** Y esto es la prueba más fuerte de todas, porque el propio producto lo dice: `frontend/src/components/costcenter/CostBadge.tsx:11` — `nominal: "Nominal: costo de suscripción plana, NUNCA facturable."`; `frontend/src/components/costcenter/CostKpiCards.tsx:25` — `{ label: "Nominal (suscripción)", …, hint: "No facturable" }`. El Centro de Costos mide **lo que Stacky gasta**, no lo que Stacky cobra.
  5. (Residual) `frontend/src/components/UndoToastHost.tsx:37` — *"Suscripción al manager"*, en el sentido de observador/pub-sub.
- **Conclusión sin rodeos:** **Stacky no cobra nada y no tiene a quién cobrarle.** Es coherente con el modelo mono-operador de §3.1: un solo operador, sin cuenta, sin autenticación, sin facturación. Auditar "conversión entre planes" o "mensajes de upgrade" sería auditar una fantasía.
- **Cuáles son los límites REALES del producto** — esto es lo que corresponde auditar en su lugar: las **403 feature flags** del arnés (`backend/services/harness_flags.py`, contadas en el inventario base), que son el mecanismo real por el que una capacidad está o no disponible; más presupuestos de tokens, topes de turnos y timeouts. <!-- PENDIENTE: enumerar cada límite numérico con archivo:línea, default, y si es editable por UI. Verificado hasta ahora: los 403 flags y sus 6 tipos; los 64 `int` y 9 `float` del registro son, por definición, límites numéricos editables por UI. -->
- **Consecuencia para el informe:** las secciones del pedido sobre "mensajes comerciales", "conversión entre planes" y "límites de plan" no tienen objeto. La pregunta útil equivalente es: *¿el operador entiende qué capacidades tiene habilitadas y por qué una acción no está disponible?* — y la respuesta verificada es **no** (H-06, H-12, §3.2). Ese es el verdadero "límite" que el producto comunica mal: no un tope de plan, sino **el estado de 403 interruptores** cuyos mensajes de error le hablan de variables de entorno.

### 3.17 Acciones destructivas y recuperación — EVALUADO, y es una fortaleza `[CÓDIGO]`

Lo audito como flujo propio porque el pedido lo señala explícitamente ("acciones destructivas sin confirmación ni recuperación", "riesgo de pérdida de trabajo") y porque el resultado contradice lo que se esperaría.

- **Objetivo del usuario:** ejecutar una acción irreversible sin miedo, y no ejecutarla por accidente.
- **Qué protección existe:** un sistema de diálogos único y adoptado. **0** diálogos nativos; **31** sitios de `askConfirm(` en 22 archivos; `tone="danger"` enfoca **Cancelar** para que Enter no confirme (`ConfirmDialog.tsx:42,48`); type-to-confirm disponible y aplicado al despliegue (`DeploymentsSection.tsx:205` con `requiredText: app.id`). Ver F-13, F-14, F-15.
- **Calidad del microcopy:** el ejemplo de `AgentHistoryPage.tsx:630` cuantifica el daño ("se borrarán N ejecuciones") y advierte irreversibilidad. Es el estándar correcto.
- **Recuperación:** existe un gestor de "deshacer" (`services/undoManager.ts`, con cadenas de promesas por id e idempotencia documentada en `:44` y `:143`) y un host global de toasts de deshacer (`App.tsx:514-516`). O sea: para una clase de acciones hay **undo real**, no sólo confirmación previa.
- **Pérdida de trabajo en modales:** contemplada en la primitiva — `Dialog.tsx:22` no cierra por Escape/backdrop si el contenido está `dirty` o `busy` (F-17).
- **Veredicto del flujo:** **cumple.** No es un condicionante de producción.
- **Lo que queda sin verificar** (declarado): (a) si **todas** las mutaciones destructivas pasan por `askConfirm`, o si hay alguna que lo esquiva — para afirmarlo haría falta enumerar los endpoints de borrado y cruzarlos con los 31 sitios; (b) si los formularios grandes que **no** usan `Dialog` (p. ej. los editores de cliente/agente) tienen protección de cambios sin guardar equivalente. Ver §8.

### 3.16 Administración y configuración avanzada <!-- PENDIENTE -->

---

## 4. Quick wins

Alto impacto, bajo esfuerzo, implementables antes de producción. Todos anclados a un hallazgo verificado.

| # | Cambio | Archivo:línea | Esfuerzo | Cierra |
|---|---|---|---|---|
| QW-1 | Alinear el default del frontend del shell v2 con el del backend (`useState(true)`) y **no** forzar `false` en el `.catch` | `frontend/src/App.tsx:85`, `:178-180` | ~2 líneas | Elimina el parpadeo estructural de 100% de las cargas y la degradación silenciosa (H-02) |
| QW-2 | `overflow-x: auto` en la nav v1 | `frontend/src/App.module.css:7-16` | 1 línea | Ningún tab queda inalcanzable (H-05) |
| QW-3 | Reemplazar los 5 literales de color de la nav por tokens existentes | `frontend/src/App.module.css:24,33,37,38,49` | 5 líneas | Nav legible en tema claro + acento dentro del sistema (H-07) |
| QW-4 | Pasar el `ctx` real a `PipelineYamlPreview` | `frontend/src/components/devops/PublicationsSection.tsx:541` | 1 línea | Previsualización deja de mentir sobre capacidades (H-11) |
| QW-5 | Subir `--text-faint` hasta cruzar 4.5:1 (valor exacto por recálculo) | `frontend/src/theme.css:14` | 1 literal | Corrige contraste en 97 usos / 45 archivos (H-09) |
| QW-6 | Corregir el comentario de tipos de `FlagSpec` para incluir `"str"` | `backend/services/harness_flags.py:23` | 1 línea | Cierra el drift documental (H-14) |
| QW-7 | Unificar el literal de identidad ausente a un solo valor derivado de `current_user()` | 9 sitios listados en H-08 | ~9 líneas | Traza de auditoría agrupable (H-08 punto 2) |
| QW-8 | Timeout por defecto en `request()` con error distinguible | `frontend/src/api/client.ts:190-211` | ~10 líneas | Fin de los spinners infinitos (H-04) |

**Nota sobre QW-1 y el orden:** QW-1 debe ir **antes** de invertir en la nav v1 (QW-2, QW-3). Si se decide retirar v1, QW-2 y QW-3 se cierran por eliminación. Recomiendo igual hacer QW-2/QW-3 (6 líneas) porque v1 sigue siendo el camino de fallo mientras exista.

---

## 5. Mejoras estructurales

### ME-1 · Un solo endpoint de capacidades en lugar de 10 llamadas de arranque

- **Problema que resuelve:** H-01 y H-02 en su raíz. Hoy el arranque hace 8 `probeFlagHealth` (`App.tsx:143-167`) + `fetch("/api/diag/health")` (`:170`) + `HarnessFlags.list()` (`:208`) = **10 llamadas** sólo para decidir qué mostrar en la navegación.
- **Cambio:** un endpoint que devuelva el mapa completo de capacidades de UI en una respuesta. El frontend espera **una** vez, con un estado `"unknown"` explícito, y recién entonces decide navegación y redirecciones.
- **Beneficio adicional:** hace posible el esqueleto de carga de H-01 sin coordinar 10 promesas, y elimina la ventana de ~1.2s en la que los gates mienten.
- **Riesgo:** cambio de contrato; hay que mantener los health por feature mientras se migra.
- **Criterio de aceptación:** el arranque hace ≤2 llamadas antes de decidir la navegación (test contable con `fetchImpl` inyectado, sin DOM); un deep link a cualquier pantalla con gate habilitado nunca rebota.

### ME-2 · Normalizar el contrato de errores de la API y consumirlo en la UI

- **Problema que resuelve:** H-03, H-06 y H-12 de una sola vez — son tres síntomas del mismo hueco.
- **Cambio:** (a) backend: `error` machine-readable estable + `message` humano sin jerga ni nombres de variables + `detail.flag` cuando aplique + `correlation_id` siempre; un solo status para "feature apagada". (b) frontend: `GatewayError` que preserva los campos, un helper `userFacingMessage`, y un componente de estado vacío reutilizable para "funcionalidad desactivada" con acción de activación.
- **Criterio de aceptación:** ningún `message` contiene `STACKY_` ni jerga interna; todos los gates de flag responden el mismo status y el mismo `error`; existe **un** componente de estado "desactivado" y las pantallas con gate lo usan.

### ME-3 · Decidir el compromiso de responsive y hacerlo cumplir por gate

- **Problema que resuelve:** H-10. 13 media queries en 198 archivos con 6 breakpoints ad-hoc es peor que cero: promete adaptación que no existe.
- **Cambio:** decidir (desktop-only con ancho mínimo declarado, o soporte tablet real), tokenizar los breakpoints en `theme.css`, y un gate que rechace literales nuevos.
- **Criterio de aceptación:** el ancho mínimo está documentado en `docs/sistema/07-frontend.md`; a ese ancho las 5 pantallas principales no producen scroll horizontal del documento; el gate falla ante un breakpoint literal nuevo.

### ME-4 · Cobrar la inversión del design system: migrar la deuda de estilo

- **Problema que resuelve:** H-15. El design system (F-01) y la librería de 16 primitivas (F-12) son buenos; la adopción es desigual. H-07 es la demostración de que esto no es cosmético: un literal de color en la nav dejó el tema claro ilegible.
- **Línea base medida (no estimada):** **723** `style={{` en `.tsx` y **1314** hex literales en `.css` fuera de `theme.css`. Concentración: 6 de los 10 peores archivos de estilo inline están en `components/devops/`; `pages/PMCommandCenter.module.css` sola tiene 140 hex (~11% del total).
- **Cambio:** congelar la línea base por archivo con un ratchet, extender su alcance a los archivos nuevos, y pagar la deuda por orden de concentración — **no** en un barrido masivo.
- **Criterio de aceptación:** el ratchet registra el conteo por archivo y falla ante cualquier incremento; los 4 archivos de mayor concentración (`PMCommandCenter.module.css`, `BlockProperties.tsx`, `PipelineBuilderSection.tsx`, `AgentHistoryPage.module.css`) llegan a 0 en su iteración asignada; ningún archivo nuevo entra con deuda.

### ME-5 · Retirar una de las dos navegaciones

- **Problema que resuelve:** H-02 y su drift de etiquetas y de jerarquía. Dos IAs completas es la causa raíz, no el síntoma.
- **Cambio:** confirmar v2 como única nav, borrar la rama v1 de `App.tsx:349-497`, y dejar `TAB_META` (`shellNav.ts:16-35`) como fuente única de etiquetas e iconos.
- **Beneficio:** cierra H-05 y H-07 por eliminación, borra ~150 líneas de JSX duplicado, y elimina la necesidad de sincronizar etiquetas a mano que `shellNav.ts:3-4` documenta.
- **Riesgo:** hay que confirmar que v2 cubre las 18 pantallas (`computeVisibleTabs`, `shellNav.ts:68-83`, y `ALWAYS_VISIBLE` de 6 en `:64-66`) antes de borrar el fallback.
- **Criterio de aceptación:** existe **una** implementación de nav; un test `.ts` puro afirma que el conjunto de tabs de `TAB_META` es igual al `type Tab` de `routes.ts` (el drift de cobertura que `shellNav.ts:4` dice que ya vigila).

---

## 6. Backlog priorizado

| ID | Mejora | Área | Problema que resuelve | Sev. | Impacto | Esfuerzo | Dependencias | Riesgo | Prioridad | Criterio de aceptación |
|---|---|---|---|---|---|---|---|---|---|---|
| B-01 | Estado `unknown` en los gates; no redirigir hasta resolver | Navegación | H-01 deep link/reload rebota en 12 de 18 pantallas | Crítica | Alto | Medio | — | Bajo | **P0** | Test puro de `shouldRedirectAway` cubre la tabla `unknown/on/off`; `/devops`+F5 permanece en `/devops` |
| B-02 | Preservar `message`/`correlation_id` en errores (`GatewayError` + `userFacingMessage`) | API/UX | H-03 errores crudos no accionables | Crítica | Alto | Medio | — | Bajo | **P0** | El texto mostrado nunca matchea `/^\d{3} [A-Z ]+:/`, `/STACKY_/` ni `/^\s*\{/` |
| B-03 | Alinear default de shell v2 y no degradar ante fallo de health | Navegación | H-02 parpadeo estructural + IA degradada en silencio | Alta | Alto | Bajo | — | Bajo | **P0** | Primer paint == estado a los 3s; con health en 500 la nav sigue siendo la sidebar |
| B-04 | Timeout por defecto en el cliente HTTP | API | H-04 spinner infinito | Alta | Alto | Bajo | — | Medio (ops largas) | **P0** | Con `fetch` que nunca resuelve, `api.get` rechaza con error de timeout; ops largas configurables |
| B-05 | `overflow-x` en la nav v1 | Navegación | H-05 tabs inalcanzables | Alta | Medio | Bajo | — | Nulo | **P0** | Con 18 secciones a 1280px todos los tabs son alcanzables |
| B-06 | Quitar nombres `STACKY_*` de los `message`; mover a `detail.flag` | API/UX | H-06 filtración de vocabulario interno | Media→Alta con B-02 | Alto | Medio | B-02 | Bajo | **P0** | Ningún `message` de error contiene `STACKY_` |
| B-07 | Tokenizar los colores de la nav | Design system | H-07 nav ilegible en tema claro | Alta (si el tema claro se ofrece) | Medio | Bajo | — | Nulo | **P0** si se ofrece tema claro, si no **P2** | Cero literales de color en `App.module.css`; ≥4.5:1 en ambos temas |
| B-08 | Pasar el `ctx` real en `PipelineYamlPreview` | DevOps | H-11 previsualización miente sobre capacidades | Media | Medio | Bajo | — | Nulo | **P1** | Ninguna prop `ctx` con `health` literal en ruta de producción; gate lo impide |
| B-09 | Unificar el status y el `error` de "feature desactivada" | API | H-12 cuatro códigos para una semántica | Media | Alto | Medio | B-02 | Medio (contrato) | **P1** | Todos los gates de flag: mismo status y `error == "feature_disabled"` |
| B-10 | Estado vacío de primera clase para "funcionalidad desactivada" | UX | §3.2, H-06, H-12 | Media | Alto | Medio | B-06, B-09 | Bajo | **P1** | Un componente único usado por todas las pantallas con gate, con acción de activación |
| B-11 | Corregir `--text-faint` a ≥4.5:1 + test de contraste | Accesibilidad | H-09 contraste AA en 97 usos | Media | Medio | Bajo | — | Bajo (cambio visual) | **P1** | Test puro de contraste verde para todos los pares en ambos temas |
| B-12 | Unificar la identidad de reserva a un solo valor | Backend/auditoría | H-08 seis identidades para el mismo usuario ausente | Media | Medio | Bajo | — | Bajo | **P1** | Un solo literal en todo `backend/`; test de grep lo verifica |
| B-13 | Documentar y verificar el límite de red (bind a loopback) | Seguridad | H-08 sin límite de confianza | Media local / Crítica en red | Alto | Bajo | — | Bajo | **P1** | Binding documentado en `docs/sistema/` y verificado con `netstat` |
| B-14 | Aviso de ruta desconocida en lugar de rebote mudo | Navegación | H-13 URL inexistente enmascarada | Baja→Media | Medio | Bajo | B-01 | Nulo | **P2** | `parseRoute` marca ruta desconocida; aviso visible; round-trip intacto |
| B-15 | Endpoint único de capacidades de UI | Arquitectura | ME-1, raíz de H-01/H-02 | Alta (estructural) | Alto | Alto | B-01, B-03 | Medio (contrato) | **P2** | ≤2 llamadas antes de decidir la nav (test contable con `fetchImpl` inyectado) |
| B-16 | Decidir y hacer cumplir el compromiso de responsive | Design system | H-10 soporte indefinido | Media | Medio | Medio (A) / Alto (B) | — | Bajo | **P2** | Ancho mínimo documentado; sin scroll horizontal del documento a ese ancho; gate de breakpoints |
| B-17 | Retirar la nav v1 y dejar `TAB_META` como fuente única | Arquitectura | H-02 raíz, drift de etiquetas y jerarquía | Alta (estructural) | Alto | Medio | B-03, B-05, B-07 | Medio | **P2** | Una sola implementación de nav; test de igualdad `TAB_META` ↔ `type Tab` |
| B-18 | Constante única de tipos de flag + test de igualdad de conjuntos | Backend | H-14 drift del contrato de tipos | Baja | Bajo | Bajo | — | Nulo | **P3** | Test de igualdad de conjuntos verde; el comentario ya no enumera tipos |
| B-19 | Congelar la deuda de estilo con ratchet por archivo y pagarla por concentración | Design system | H-15 / ME-4: 723 inline + 1314 hex literales | Media | Medio | Alto | — | Bajo | **P2** (congelar) / **P3** (pagar) | Ratchet por archivo con la línea base medida; falla ante incremento; los 4 archivos de mayor concentración llegan a 0 |
| B-20 | Hacer obligatoria la prop `onOpenExecution` y borrar el fallback a `console.log` | Diagnóstico | Trampa latente de acción silenciosa (`OperationalHealthCard.tsx:207-210`) | Baja | Bajo | Bajo | — | Nulo | **P3** | La prop es requerida en el tipo; no queda ningún fallback que degrade a `console.log` |
| B-21 | Estado de error visible cuando fallan recomendaciones / análisis de sentimiento | PM | Fallas silenciosas: hoy sólo `console.warn` (`PMCommandCenter.tsx:911,975`) | Baja | Bajo | Bajo | B-02 | Nulo | **P2** | Al fallar, la sección muestra un estado de error con reintento en lugar de quedar vacía sin explicación |
| B-22 | Documentar las 4 pantallas faltantes + gate de paridad doc↔`TAB_PATHS` | Documentación | H-16: la doc canónica omite 4 de 18 pantallas y su anclaje caducó | Media | Medio | Bajo | — | Nulo | **P1** | El conjunto de pantallas del doc == claves de `TAB_PATHS`; el gate falla si se agrega un tab sin documentar; ningún anclaje a rangos de línea de `App.tsx` |
| B-23 | Instrumentar los 7 eventos P1 de experiencia (§9.3) | Observabilidad | Cero telemetría de UX: los riesgos H-01…H-04 no son medibles hoy | Media | Alto | Medio | B-02, B-04 | Bajo | **P1** | `services/uxEvents.ts` puro con test; los 7 eventos P1 emiten; ningún evento incluye contenido ni campo de usuario falso (§9.4) |
| B-24 | Regla única de estado de carga: `Skeleton` para contenido con forma, `Spinner` para acciones, texto plano nunca solo | UX / Design system | H-17: 59 archivos con texto plano vs 28 con `Skeleton` | Media | Medio | Medio | — | Bajo | **P2** | Las 5 pantallas de mayor uso usan `Skeleton` con la forma del contenido real; ratchet congela el conteo de literales `Cargando` y falla ante incremento |

**Resumen de prioridades:** **P0 = 7** (B-01…B-07) · **P1 = 8** (B-08…B-13, B-22, B-23) · **P2 = 7** (B-14…B-17, B-19-congelar, B-21, B-24) · **P3 = 3** (B-18, B-19-pagar, B-20).

**Conteo de hallazgos por severidad** (sobre las áreas efectivamente auditadas): **crítica 2** (H-01, H-03) · **alta 5** (H-02, H-04, H-05, H-07, H-08 en escenario de red) · **media 8** (H-06, H-09, H-10, H-11, H-12, H-15, H-16, H-17) · **baja 2** (H-13, H-14). Total **17 hallazgos**, todos con `archivo:línea` verificado y todo número con su comando. Más **17 fortalezas** verificadas (F-01…F-17) y **3 barridos de riesgo con resultado limpio**.

**Distribución por etiqueta:** `[CÓDIGO]` 13 · `[DOC]` 1 (H-16) · `[DRIFT]` 4 (H-02, H-08, H-14, H-16 — de los cuales 3 son código-contra-comentario y 1 contra la doc canónica) · `[HIPÓTESIS]` 3 puntos acotados dentro de H-04, H-05 y §3.3, cada uno con su paso manual escrito · `[BUENA PRÁCTICA]` 3 (fallback de `OperationalHealthCard`, reglas de privacidad de §9.4, anclar a `routes.ts` en lugar de `App.tsx`).

---

## 7. Plan de acción

### Antes del lanzamiento (los 7 P0)

Orden recomendado, porque hay dependencias reales y porque el orden minimiza retrabajo:

1. **B-03** (2 líneas) — alinear el default del shell v2. Primero porque es lo más barato y porque determina si conviene invertir en la nav v1.
2. **B-05** + **B-07** (6 líneas) — `overflow-x` y tokens de color en la nav. Aun si v1 se retira después, mientras exista es el camino de fallo.
3. **B-02** — `GatewayError` + `userFacingMessage`. Es la pieza de la que dependen B-06 y B-10.
4. **B-06** — limpiar los `message` del backend, apoyado en B-02.
5. **B-04** — timeout en el cliente. Cuidado con las operaciones legítimamente largas: hay que permitir deadline por llamador.
6. **B-01** — estado `unknown` en los gates. El de mayor esfuerzo de los P0 y el de mayor impacto en percepción.

**Gate de salida del lanzamiento:** los 6 condicionantes C1–C6 de §1 verificados, cada uno con su criterio de aceptación cumplido y su smoke manual ejecutado y registrado. Recordar que en este repo **el gate se corre contra el defecto**: cada test nuevo tiene que verse **rojo** ante el bug que dice atrapar antes de aceptarlo como verde.

### Primera semana

- **B-08** (1 línea, `ctx` real en la previsualización).
- **B-09** + **B-10** — unificar el contrato de "feature desactivada" y construir el estado vacío único. Es lo que convierte 403 flags de fuente de confusión en superficie de descubrimiento.
- **B-11** — contraste de `--text-faint` con su test de contraste puro.
- **B-12** + **B-13** — identidad de reserva única y límite de red documentado y verificado.
- **B-22** — documentar las 4 pantallas faltantes y poner el gate de paridad doc↔`TAB_PATHS`. Barato, y evita que el drift crezca.
- **B-23** — instrumentar los 7 eventos P1 de §9.3. Es lo que convierte los P0 de "creemos que impactan" a números: `nav.gate_bounce` mide H-01, `api.error_shown` con `had_human_message=false` mide H-03, `api.timeout` mide H-04. Sin esto, no hay forma de demostrar que los arreglos funcionaron.
- Ejecutar los smokes manuales pendientes listados en §8, en particular el del tour de onboarding contra la nav v2 (§3.3): es un riesgo de primera experiencia de frecuencia 100% para usuarios nuevos.

### Primeros 30 días

- **B-14** — aviso de ruta desconocida.
- **B-15** — endpoint único de capacidades. Cierra la raíz de H-01/H-02 y habilita esqueletos de carga honestos.
- **B-17** — retirar la nav v1, previa confirmación de cobertura de v2 sobre las 18 pantallas.
- **B-16** — decidir el compromiso de responsive y escribirlo en `docs/sistema/07-frontend.md`.
- Instrumentar la observabilidad de experiencia (§9), apoyándose en el punto de enganche que ya existe (`PageErrorBoundary` → Centro de Actividad).
- Cerrar las áreas de §8 que quedaron sin auditar.

### Próximo trimestre

- **B-19** — migración de deuda de estilo a tokens, por pantalla y con ratchet.
- **B-18** — constante de tipos de flag.
- Reevaluar responsive con datos de uso real (si la telemetría de §9 muestra accesos desde viewports angostos, la opción B de H-10 se justifica; si no, la decisión desktop-only queda confirmada con evidencia).
- Completar la revisión de accesibilidad. **Ya verificado en esta corrida:** foco visible global por teclado (F-03), accesibilidad completa de modales — focus-trap, restore-focus, `inert`, `role="dialog"`, `aria-modal`, `aria-labelledby` (F-16) —, `prefers-reduced-motion` (F-04) y contraste de los tokens de texto (H-09). **Falta:** etiquetado de controles de formulario (`<label htmlFor>` / `aria-label`), botones icono-solo sin nombre accesible, y `onClick` sobre elementos no interactivos que el teclado no alcanza. Ver §8.

---

## 8. Áreas no cubiertas y por qué

Esta corrida fue interrumpida por una caída del proceso; el informe se está construyendo de forma incremental y esta sección declara con precisión qué falta, en lugar de rellenarlo.

**Sin auditar todavía (declarado, no inventado):**

1. **Flujos de agente punta a punta** (§3.4–3.10, 3.12, 3.13): creación/edición de cliente y de agente, selección de modelo/runtime/effort, Agent Lab, ejecución y completion, publicación. Archivos objetivo identificados pero no abiertos: `frontend/src/components/NewProjectModal.tsx` (923 líneas), `EditProjectModal.tsx` (941), `ClientProfileEditor.tsx` (1288), `frontend/src/pages/TeamScreen.tsx`, `PMCommandCenter.tsx` (1148), `frontend/src/components/ChatDrawer.tsx` (718), `frontend/src/pages/ExecutionHistoryPage.tsx` (856), `FlowConfigPage.tsx`.
2. **Integraciones ADO / GitLab / Mantis** (§3.8): credenciales, enmascarado, "probar conexión", y qué ve el operador ante un token inválido. Objetivo: `frontend/src/components/devops/**` (parcialmente tocado sólo en `PublicationsSection.tsx`), `MigratorPage.tsx`, `SettingsPage.tsx`, `backend/services/gitlab_provider.py`.
3. **Documentación, RAG y grafo** (§3.14): `frontend/src/pages/DocsPage.tsx`, `frontend/src/components/docs/DocGraphView.tsx` (1193 líneas), `frontend/src/docs/`. Sin abrir.
4. **Accesibilidad más allá del contraste de tokens:** conteo de `aria-*`, botones icon-only sin nombre accesible, inputs sin etiqueta, foco y `Escape` en modales, `onClick` en elementos no interactivos. Lo único verificado del eje es el foco visible global (F-03) y el contraste de `--text-faint`/`--text-muted` (H-09).
5. **Calidad de los estados vacíos y confirmación de guardado.** La **adopción** de estados de carga sí quedó medida (H-17) y la **existencia** de estados vacíos también (183 guardas, 149 literales). Lo que **no** verifiqué: (a) si cada estado vacío ofrece una próxima acción o es sólo una frase — requiere leer los 149 sitios; (b) cuántos guardados confirman visiblemente el éxito vs. quedar en silencio. Esto último es el hueco más relevante que queda del eje UX y no lo afirmo en ninguna dirección.
6. **Doble envío (`disabled={loading}`):** **no verificado en ninguna dirección.** No afirmo que esté bien ni mal. Requiere cruzar los handlers que llaman mutaciones con la presencia de una guarda de estado en el JSX, archivo por archivo.
7. **Cobertura completa de acciones destructivas:** verifiqué que el mecanismo existe, es bueno y tiene 31 sitios de adopción (F-13…F-15, §3.17). **No** verifiqué exhaustivamente que *ninguna* mutación destructiva lo esquive — para eso hay que enumerar los endpoints de borrado del backend y cruzarlos con los sitios de `askConfirm`. Tampoco verifiqué la protección de cambios sin guardar en los formularios grandes que no usan la primitiva `Dialog`.
8. **Mocks y textos en ruta de producción:** sólo tengo el caso de H-11. Sin verificar: datos de muestra hardcodeados en otras pantallas, URLs/localhost/IPs en el bundle, credenciales o identificadores personales visibles, mezcla español/inglés en textos de usuario, y `JSON.stringify` mostrado al operador. (Los barridos de `TODO`/`console.*`/diálogos nativos **sí** se hicieron y están en la sección de resultados limpios.)
9. **Componentes duplicados:** no conté cuántas implementaciones distintas de modal/tabla/badge coexisten fuera de `components/ui/`. Los 723 estilos inline sugieren que hay markup ad-hoc, pero no lo cuantifiqué por tipo de componente. Tampoco leí el archivo del ratchet de deuda de UI para conocer su alcance y línea base actuales.
10. **Drift doc ↔ código, más allá de la lista de pantallas:** cubrí `docs/sistema/07-frontend.md` (H-16). **Sin auditar:** los otros 15 documentos de `docs/sistema/`, en particular `08-configuracion-flags.md` contra los 403 flags contados, `02-arquitectura.md`, `04-api.md` y `11-estado-planes.md`. Dado que el único documento de frontend que revisé tenía 4 omisiones y un anclaje caducado, la probabilidad de drift en los otros es alta — pero **no la verifiqué y no la afirmo**.
11. **Enumeración de los límites numéricos reales** (§3.15): el barrido de "plan comercial / cuota" **sí** está completo y es concluyente. Lo que falta es la tabla de los límites que *sí* existen (presupuestos de tokens, topes de turnos, timeouts) con `archivo:línea`, default y editabilidad por UI. Verificado hasta ahora: los 403 flags con sus 6 tipos, de los cuales los 64 `int` y 9 `float` son por definición límites numéricos editables por UI.

**Limitaciones metodológicas de esta auditoría (explícitas):**

- **No se ejecutó la aplicación.** Todo es análisis estático de código y hoja de estilos. Los hallazgos etiquetados `[HIPÓTESIS]` (H-04 frecuencia, H-05 ancho de corte, §3.3 cobertura del tour) traen escrito el paso manual exacto que los confirma o los refuta.
- **No se corrió la suite de vitest**, por contaminación cross-file conocida en este repo. Los criterios de validación propuestos son, por eso, tests `.ts` puros, pasos de smoke manual enumerados, o gates de grep/ratchet — nunca tests de componente con RTL (que además no está instalado).
- **Los conteos son de `frontend/src` y `backend/api`/`backend/services`** del árbol principal, excluyendo los worktrees `wt-plan-*/` de sesiones paralelas.

---

## 9. Observabilidad de experiencia

### 9.1 Inventario de lo que YA existe (hecho primero, para no proponer duplicados)

**Telemetría de ejecución de LLM — existe y es sólida.** `backend/harness/telemetry.py` define `RunTelemetry` (`:28-50`) con estos campos exactos: `runtime`, `session_id`, `num_turns`, `total_cost_usd`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cost_estimated`, `raw`. Se construye desde los dos runtimes (`from_claude_stream` `:69`, `from_codex_event` `:86`), estima costo desde tokens cuando el proveedor no lo reporta (`_maybe_estimate_cost` `:53-66`, con la regla "reportado siempre gana") y persiste por ejecución (`persist(execution_id, t)` `:122`).

**Telemetría de experiencia de usuario — NO existe. Cero.** Comando:
```
grep -rniE "\b(track|analytics|posthog|amplitude|gtag|mixpanel|logEvent)\b" frontend/src \
  --include=*.ts --include=*.tsx | grep -v __tests__ | grep -v "\.test\." | wc -l
# 7
```
Las **7 coincidencias son todas falsos positivos**, verificadas una por una:
- `frontend/src/api/endpoints.ts:4514-4515` — `track: (slug, tracked) => api.post("/api/devops/build/track", …)`: marca una compilación como "seguida" en el taller de compilación. Es una **mutación de dominio**, no analítica.
- `frontend/src/components/devops/BuildWorkshopSection.tsx:136` — llama a esa misma API de dominio.
- `frontend/src/components/costcenter/OpsTrendsSection.tsx:50,58` — `styles.track`: clase CSS de la pista de una barra de progreso.
- `frontend/src/components/ui/Spinner.tsx:9,28` — el token CSS `--spinner-track`.

**Conclusión del inventario:** el producto sabe con precisión **cuánto cuesta cada ejecución de agente** y **nada** sobre cómo le va al humano que la lanzó. No hay vistas de pantalla, ni embudos, ni abandono de formularios, ni tiempo hasta completar una tarea, ni frecuencia de error por pantalla. Por lo tanto **ninguno** de los eventos que propongo abajo duplica instrumentación existente.

### 9.2 Punto de enganche que ya existe (no hace falta infraestructura nueva)

`frontend/src/components/PageErrorBoundary.tsx:35-42` ya publica al Centro de Actividad con la forma `{ key, kind: "error", severity, title, body, ts }` vía `publishActivity` de `services/activityCenter`. Ese canal es el lugar natural para la primera tanda de eventos: existe, está montado globalmente, y ya se usa para errores.

**Recomendación de arquitectura mínima:** un módulo `.ts` puro `services/uxEvents.ts` con una función `emit(event: UxEvent)` que hoy escriba al mismo canal del Centro de Actividad y, si más adelante hace falta, se redirija a un endpoint. Ser un `.ts` puro es lo que lo hace testeable en este repo (sin RTL, sin jsdom).

### 9.3 Eventos propuestos

Prioridad **P1** = instrumentar en la primera semana (miden los riesgos que esta auditoría dejó abiertos); **P2** = primeros 30 días.

| Evento | Momento de disparo | Propiedades | Qué permite medir | Prio |
|---|---|---|---|---|
| `nav.gate_bounce` | Cuando el efecto de `App.tsx:264-277` redirige a Tickets | `intended_tab`, `gate_state` (`unknown`\|`off`), `ms_since_mount`, `was_deep_link` | **Mide H-01 directamente.** Cuántos operadores pierden su destino y si fue por gate real (`off`) o por carrera de arranque (`unknown`). Es el único evento que convierte H-01 de hipótesis de impacto a número. | **P1** |
| `nav.shell_variant_resolved` | Cuando `/api/diag/health` resuelve `shell_v2_enabled` | `variant` (`v1`\|`v2`), `resolved_ms`, `fell_back_on_error` (bool) | **Mide H-02.** Con qué frecuencia el operador queda en la nav vieja por un fallo de health, y cuánto dura el parpadeo. | **P1** |
| `api.error_shown` | Cuando se renderiza un error al operador | `screen`, `status`, `error_code`, `had_human_message` (bool), `correlation_id` | **Mide H-03 y H-06.** El `had_human_message=false` cuantifica exactamente cuántos errores llegan crudos. Es la métrica de salida del arreglo. | **P1** |
| `api.timeout` | Al expirar el deadline del cliente (tras B-04) | `screen`, `endpoint`, `elapsed_ms` | **Mide H-04.** Confirma o refuta la hipótesis de frecuencia de spinners colgados, que hoy no puedo verificar sin ejecutar la app. | **P1** |
| `screen.view` | Al montarse una pantalla | `tab`, `subtab`, `entry` (`nav`\|`deep_link`\|`palette`\|`back_forward`) | Descubribilidad: qué módulos caros (Centro de Costos, Evolución, Planes, Comparador BD) **nunca** se visitan. Con `entry` se mide además cuánto se usa el deep-link, que hoy está roto. | **P1** |
| `screen.error_rate` (derivado) | Agregación de `api.error_shown` por `screen` | — | Frecuencia de error por pantalla, que es lo que el pedido pide explícitamente. Sale gratis del anterior. | **P1** |
| `onboarding.started` / `onboarding.completed` / `onboarding.abandoned` | Auto-apertura del tour (`App.tsx:229-231`) / último paso / cierre antes del final | `step_index`, `total_steps`, `variant` (`v1`\|`v2`) | Embudo de primera experiencia. `variant` es clave por el riesgo de §3.3 (el ancla `data-tour="nav"` está en la rama v1). | **P1** |
| `form.abandoned` | Al desmontar un formulario con campos tocados y sin guardar | `form_id`, `fields_touched`, `fields_total`, `ms_open`, `had_validation_error` | Abandono de formularios. Señala qué formularios son demasiado largos (candidatos: los editores de cliente/agente, de 923-1288 líneas). | **P2** |
| `agent.created` | Confirmación exitosa de creación | `runtime`, `model`, `effort`, `ms_from_open` | Tiempo hasta crear el primer agente; qué combinaciones de modelo/runtime elige el operador realmente. | **P2** |
| `agent.first_run_ok` | Primera ejecución con estado final exitoso de un agente nuevo | `ms_from_creation`, `attempts_before_success` | El hito de activación del producto: cuánto tarda un operador nuevo en tener un agente que funciona, y cuántos intentos le cuesta. | **P2** |
| `capability.blocked` | Cuando el operador toca una acción cuya flag está apagada | `flag_key`, `screen`, `action` | **Intentos de acceder a funciones no disponibles.** Convierte los 403 flags de fuente de confusión (H-06, H-12) en una lista priorizada de qué activar por default. | **P2** |
| `flag.changed` | Guardado exitoso en el panel de flags | `flag_key`, `type`, `from`, `to`, `restart_required` | Cambios de configuración. Con `restart_required` se detecta el caso "lo cambió y no entiende por qué no pasa nada". | **P2** |
| `integration.used` | Llamada exitosa a ADO / GitLab / Mantis | `provider`, `operation` | Uso real de integraciones vs. lo que se construyó para ellas. | **P2** |
| `docs.graph_interaction` | Interacción con el grafo documental | `action` (`zoom`\|`pan`\|`select`\|`search`), `node_type` | Si el grafo (1193 líneas de `DocGraphView.tsx`) se usa o es decorativo. | **P2** |
| `destructive.confirmed` / `destructive.cancelled` | Resolución de un `askConfirm` con `tone: "danger"` | `action`, `screen`, `had_required_text` | Tasa de cancelación de acciones destructivas. Una tasa alta indica que el botón está demasiado a mano o mal etiquetado. | **P2** |

### 9.4 Advertencia de privacidad, dado el sustrato

Con la identidad hardcodeada a `dev@local` (H-08), **todos** estos eventos se atribuirán al mismo usuario ficticio. Eso no invalida las métricas agregadas (frecuencias, embudos, tiempos), pero hace imposible cualquier análisis por operador. Si se instrumenta antes de resolver H-08 punto 3, conviene **no** incluir un campo de usuario en absoluto, en lugar de poblarlo con un valor falso que después ensucie el análisis histórico.

`[BUENA PRÁCTICA]` — Ninguno de los eventos propuestos incluye contenido: ni texto de prompts, ni nombres de tickets, ni cuerpos de error completos. Sólo códigos, identificadores de pantalla y duraciones. Mantener esa regla al implementar.

---

*Informe generado en corrida `max`. Read-only sobre todo el repositorio salvo este archivo.*
