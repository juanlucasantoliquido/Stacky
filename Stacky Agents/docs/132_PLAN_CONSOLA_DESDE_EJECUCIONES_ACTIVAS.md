# Plan 132 — Abrir la consola en vivo desde el panel "Ejecuciones Activas"

**Estado:** CRITICADO (v2, 2026-07-14) — APROBADO-CON-CAMBIOS (v1 sin bloqueantes; C1 IMPORTANTE corregido in place)
**Origen:** pedido directo del operador (verbatim): *"en la parte de ejecuciones activas me permitas abrir la consola de la ejecución activa para ver cómo está"*.
**Alcance:** 100% frontend. Cero backend nuevo, cero endpoint nuevo, cero store nuevo.
**Flag:** NO lleva flag (decisión de diseño justificada en §3.1).

**v1 → v2 — CHANGELOG (crítica adversarial 2026-07-14):**

- **C1 IMPORTANTE (fix F0 Cambio 3 + F1 diff 4):** el botón v1 seteaba `aria-pressed={consoleExecutionId === e.id}` pero el `onClick` SOLO abría (`setCodexConsoleExecution(e.id, false)`), nunca cerraba. Resultado: clickear el botón de un run cuya consola YA está abierta es un no-op que desperdicia el click, y `aria-pressed=true` promete a lectores de pantalla una capacidad de toggle que el código no cumple (violación de semántica ARIA — WAI-ARIA define `aria-pressed` explícitamente para botones toggle). v2 corrige: `onClick` ahora es un toggle real — `setCodexConsoleExecution(consoleExecutionId === e.id ? null : e.id, false)`. **[ADICIÓN ARQUITECTO]**: esto además le da al operador una forma de cerrar la consola de un run desde la MISMA fila donde la abrió, sin tener que ir a buscar el botón ✕ del dock (que puede estar en otra esquina de la pantalla si el operador lo movió). Cero costo: mismo 1 click, mismo archivo, reusa `setCodexConsoleExecution(null)` que YA es parte del contrato del store (`id: number | null`). El `aria-label`/`title` se dejan EXACTAMENTE como en v1 (constantes, "Ver consola de la ejecución #N") — es el patrón ARIA correcto para toggle buttons (el nombre accesible no cambia, `aria-pressed` es lo único que comunica el estado), así que los tests 1 y 3 de F0 no cambian su query.
- **C2 MENOR (verificación, sin cambio de código):** verifiqué empíricamente contra `Stacky Agents/frontend/package.json` de este worktree que `@testing-library/react` y `jsdom` NO figuran como devDependencies (grep directo, cero matches). Esto confirma que el gap de entorno citado en F0/F2 es ESTRUCTURAL y real, no un artefacto de un `node_modules` roto — un `npm ci` fresco (paso obligatorio del orquestador antes de implementar) **NO** lo va a resolver porque el paquete ni siquiera está declarado. Se deja explícito para que quien implemente no pierda tiempo reintentando vitest de componente esperando que un install limpio lo arregle.

---

## 1. Objetivo e impacto

Agregar, en el panel flotante global **ActiveRunsPanel** (visible en toda la app), un botón por cada run activo que abra la **consola en vivo de ESA ejecución** — el mismo `CodexConsoleDock` que ya existe y ya está montado globalmente — sin tener que navegar al ticket/épica/sección donde nació el run para encontrarla.

**KPI / impacto esperado:**
- Tiempo para ver el estado en vivo de un run activo: de "navegar a proyecto → tab → ticket → encontrar el run" (decenas de segundos, a veces imposible si el run es de OTRO proyecto) a **1 click** desde cualquier pantalla.
- Cero clicks/configuración adicionales para quien no use el botón: el panel se ve y se comporta igual que hoy, solo suma un ícono por fila.

## 2. Por qué ahora / gap que cierra (grounding verificado)

- `frontend/src/components/ActiveRunsPanel.tsx` es el panel flotante global (montado en `App.tsx:274`). Consulta runs `running/preparing/queued` de TODOS los proyectos (`fetchActiveRuns`, líneas 37-46, con `all_projects: true`), refresca cada 5 s y lista cada run en un `<li>` (líneas 131-157) con `#{e.id}`, meta `ticket {e.ticket_id} · {e.agent_type} · {e.status}` y un único botón "✕ Cancelar" (líneas 138-155). **Hoy NO hay ninguna forma de abrir la consola de un run desde ahí** — ese es el gap.
- `frontend/src/components/CodexConsoleDock.tsx` es la consola en vivo, YA montada globalmente en `App.tsx:269` (renderiza `null` si no hay ejecución seleccionada — línea 96 `if (executionId == null) return null;`). Lee `state.codexConsoleExecutionId` / `state.codexConsoleMinimized` del store `useWorkbench` y hace streaming con `useExecutionStream(executionId)`. El panel de logs (líneas 190-223) se renderiza para CUALQUIER runtime; el formulario de stdin solo se habilita si `isInteractiveRun` (runtimes `codex_cli` / `claude_code_cli`).
- `frontend/src/store/workbench.ts:96-100` — la acción **ya existente** `setCodexConsoleExecution(id, minimized = false)` es el único y establecido mecanismo para abrir la consola de cualquier ejecución. Ya la usan `pages/TicketBoard.tsx:308,593`, `components/AgentLaunchModal.tsx:249`, `components/EpicFromBriefModal.tsx:325,364`, `components/devops/DevOpsAgentSection.tsx:75,86,95`, `components/devops/PipelineDoctorPanel.tsx:63`, `components/QaBrowserRunModal.tsx:71` y `hooks/useAgentRun.ts:48`.

**Conclusión:** falta solamente un botón que llame `setCodexConsoleExecution(e.id, false)` (o `(null, false)` para cerrar — toggle, ver C1/v2) desde cada fila del panel. **Reusar, no crear**: prohibido reimplementar `CodexConsoleDock`, `useExecutionStream`, el store o cualquier mecanismo de apertura nuevo.

## 3. Principios y guardarraíles (no negociables)

1. **Paridad 3 runtimes** (Codex CLI, Claude Code CLI, GitHub Copilot Pro): ya resuelta por el componente existente, ver §6. No inventar fallback nuevo.
2. **Cero trabajo extra para el operador:** el botón es descubrible (ícono + tooltip + aria-label) y de 1 click. Nada de configuración nueva, nada que setear.
3. **Human-in-the-loop:** solo mejora visibilidad. No ejecuta, no automatiza, no cancela, no manda input por sí solo.
4. **Mono-operador sin auth real:** no aplica RBAC ni chequeo de permisos.
5. **No degradar:** no tocar la lógica interna de `CodexConsoleDock`, `useExecutionStream` ni `workbench.ts`. No agregar queries nuevas ni cambiar el intervalo de refresco del panel.
6. **Prohibido** crear endpoints, stores, hooks o componentes nuevos para esta feature.

### 3.1 Decisión de diseño: SIN flag de harness (justificación explícita)

Este botón NO lleva flag `STACKY_*_ENABLED`. Precedente directo: el propio `ActiveRunsPanel.tsx` ya incorporó features de UI puramente aditivas y reversibles sin flag (colapsar a badge y mover de esquina — líneas 11-29 y 51-61, preferencias en localStorage). Este botón cumple los mismos tres criterios:
- **Puramente aditivo:** no altera ningún comportamiento existente (cancelar, colapsar, mover siguen idénticos).
- **Reversible con un click:** la consola abierta se cierra/minimiza con sus propios controles ya existentes en `CodexConsoleDock`.
- **Cero backend / cero datos:** no escribe nada, no llama endpoints nuevos; solo setea estado de UI ya existente en el store.

Un flag acá agregaría trabajo al operador (activarla) y superficie de test/config sin mitigar ningún riesgo real — violaría el principio 2.

## 4. Fases

> **Entorno de tests frontend (leer antes de empezar):** los tests de componente con `@testing-library/react` + jsdom **no pueden ejecutarse en este checkout** (gap preexistente, documentado en el propio `ActiveRunsPanel.test.tsx:12-17` — no lo resuelvas, no es parte de este plan). Los tests de F0 se escriben igual, siguiendo el patrón exacto del archivo, y "quedan listos para correr cuando se resuelva el gap de entorno". El gate binario ejecutable de este plan es `tsc --noEmit` (F2) + verificación manual (F3).

---

### F0 — Tests primero (TDD)

**Objetivo (1 frase):** especificar por test el comportamiento del botón "Ver consola" ANTES de implementarlo, extendiendo el archivo de tests existente.

- **Archivo a editar (único):** `Stacky Agents/frontend/src/components/__tests__/ActiveRunsPanel.test.tsx`
- **NO crear archivos nuevos de test.**

**Cambio 1 — mock del store `useWorkbench`.** El componente va a importar `useWorkbench` de `../store/workbench` (F1), así que el test debe mockear ese módulo. Agregar DESPUÉS del bloque `vi.mock("../../api/endpoints", ...)` existente (líneas 29-34) y ANTES del `import { Executions }` (línea 36), exactamente esto:

```tsx
// Mock del store de workbench: el panel solo usa setCodexConsoleExecution y
// codexConsoleExecutionId. vi.hoisted permite mutar el estado por test.
const workbenchMock = vi.hoisted(() => ({
  setCodexConsoleExecution: vi.fn(),
  codexConsoleExecutionId: null as number | null,
}));

vi.mock("../../store/workbench", () => ({
  useWorkbench: (selector: (s: typeof workbenchMock) => unknown) =>
    selector(workbenchMock),
}));
```

**Cambio 2 — reset en `beforeEach`.** Dentro del `beforeEach` existente (líneas 74-78), agregar al final del cuerpo:

```tsx
    workbenchMock.setCodexConsoleExecution.mockClear();
    workbenchMock.codexConsoleExecutionId = null;
```

**Cambio 3 — cuatro tests nuevos.** Agregar dentro del `describe("ActiveRunsPanel", ...)`, después del test `"no cancela si el operador rechaza el diálogo de confirmación"` (línea 111), exactamente estos cuatro tests con estos nombres:

```tsx
  it("abre la consola en vivo del run al clickear Ver consola", async () => {
    mockRuns([RUN]);
    wrap(<ActiveRunsPanel />);

    await waitFor(() => expect(screen.getByText("#42")).toBeDefined());
    fireEvent.click(
      screen.getByRole("button", { name: /ver consola de la ejecución #42/i }),
    );

    expect(workbenchMock.setCodexConsoleExecution).toHaveBeenCalledWith(42, false);
  });

  it("abrir la consola no pide confirmación ni cancela el run", async () => {
    mockRuns([RUN]);
    const confirmSpy = vi.spyOn(window, "confirm");
    wrap(<ActiveRunsPanel />);

    await waitFor(() => expect(screen.getByText("#42")).toBeDefined());
    fireEvent.click(
      screen.getByRole("button", { name: /ver consola de la ejecución #42/i }),
    );

    expect(confirmSpy).not.toHaveBeenCalled();
    expect(mockCancel).not.toHaveBeenCalled();
  });

  it("marca el botón como activo (aria-pressed) cuando la consola de ese run ya está abierta", async () => {
    workbenchMock.codexConsoleExecutionId = RUN.id;
    mockRuns([RUN]);
    wrap(<ActiveRunsPanel />);

    await waitFor(() => expect(screen.getByText("#42")).toBeDefined());
    const btn = screen.getByRole("button", {
      name: /ver consola de la ejecución #42/i,
    });
    expect(btn.getAttribute("aria-pressed")).toBe("true");
  });

  it("vuelve a clickear el botón de un run cuya consola ya está abierta y la cierra (toggle)", async () => {
    workbenchMock.codexConsoleExecutionId = RUN.id;
    mockRuns([RUN]);
    wrap(<ActiveRunsPanel />);

    await waitFor(() => expect(screen.getByText("#42")).toBeDefined());
    fireEvent.click(
      screen.getByRole("button", { name: /ver consola de la ejecución #42/i }),
    );

    expect(workbenchMock.setCodexConsoleExecution).toHaveBeenCalledWith(null, false);
  });
```

- **Comando exacto** (desde `Stacky Agents/frontend/`): `npx vitest run src/components/__tests__/ActiveRunsPanel.test.tsx`
- **Criterio de aceptación (binario):** el archivo editado compila con `npx tsc --noEmit` (0 errores). NOTA: la ejecución vitest fallará hoy por el gap preexistente de `@testing-library/react`/jsdom (idéntico al resto del archivo); eso NO es un rojo introducido por este plan — confirmado ESTRUCTURAL en la crítica v2 (`@testing-library/react`/`jsdom` no están en `package.json`, un `npm ci` fresco no lo arregla). Si el gap estuviera resuelto al momento de implementar, los 4 tests nuevos deben FALLAR antes de F1 (el botón no existe) y PASAR después de F1.
- **Flag:** no aplica (§3.1). **Trabajo del operador: ninguno.**

---

### F1 — Implementación del botón "Ver consola"

**Objetivo (1 frase):** agregar en cada `<li>` del panel un botón toggle con ícono `Terminal` que abra (`setCodexConsoleExecution(e.id, false)`) o cierre (`setCodexConsoleExecution(null, false)`) la consola de ese run, con indicador `aria-pressed` cuando la consola de ese run ya está abierta.

**Archivo 1 a editar:** `Stacky Agents/frontend/src/components/ActiveRunsPanel.tsx`

Diff exacto (4 ediciones):

1. Línea 2 — ampliar el import de lucide-react:
```tsx
// ANTES
import { Move, X } from "lucide-react";
// DESPUÉS
import { Move, Terminal, X } from "lucide-react";
```

2. Después de la línea 5 (`import useLocalStorageState ...`), agregar:
```tsx
import { useWorkbench } from "../store/workbench";
```

3. Dentro del componente, inmediatamente después de `const qc = useQueryClient();` (línea 49), agregar:
```tsx
  // Abrir la consola en vivo de un run reusa el mecanismo único y ya existente
  // del repo: setCodexConsoleExecution del store (mismo patrón que
  // pages/TicketBoard.tsx:308). CodexConsoleDock ya está montado globalmente
  // en App.tsx, así que con setear el id alcanza — no se crea nada nuevo.
  const setCodexConsoleExecution = useWorkbench((s) => s.setCodexConsoleExecution);
  const consoleExecutionId = useWorkbench((s) => s.codexConsoleExecutionId);
```

4. Dentro del `runs.map((e) => ...)`, insertar el botón nuevo ENTRE `</span>` del meta (línea 137) y el `<button ... className={styles.cancelBtn}` existente (línea 138):
```tsx
              <button
                type="button"
                className={styles.consoleBtn}
                title={`Ver consola en vivo de la ejecución #${e.id}`}
                aria-label={`Ver consola de la ejecución #${e.id}`}
                aria-pressed={consoleExecutionId === e.id}
                onClick={() =>
                  setCodexConsoleExecution(
                    consoleExecutionId === e.id ? null : e.id,
                    false,
                  )
                }
              >
                <Terminal size={13} aria-hidden />
              </button>
```
**[ADICIÓN ARQUITECTO — toggle real, fix C1]:** si la consola de ESE run ya está abierta (`consoleExecutionId === e.id`), el click la CIERRA (`setCodexConsoleExecution(null, false)`); si no, la abre. Esto hace que `aria-pressed` sea semánticamente correcto (antes prometía toggle y no lo cumplía) y le da al operador una forma de cerrar la consola desde la misma fila, sin ir a buscar el botón ✕ del dock en otra esquina de la pantalla. `title`/`aria-label` quedan CONSTANTES a propósito (mismo texto abierto o cerrado) — es el patrón ARIA correcto para toggle buttons, `aria-pressed` es lo único que comunica el estado; así los tests 1 y 3 de F0 no necesitan cambiar su query por nombre accesible. Cuando SÍ abre (id != null), el segundo argumento `false` des-minimiza la consola si estaba minimizada (ver `workbench.ts:96-100`); cuando cierra (id == null) ese segundo argumento es ignorado por el store (`workbench.ts:99`: `id == null ? false : minimized`), así que pasar `false` es inocuo en ambos casos.

**Archivo 2 a editar:** `Stacky Agents/frontend/src/components/ActiveRunsPanel.module.css`

1. La fila usa grid; agregar una columna para el botón nuevo:
```css
/* ANTES (línea 116) */
  grid-template-columns: 10px 44px 1fr auto;
/* DESPUÉS */
  grid-template-columns: 10px 44px 1fr auto auto;
```

2. Agregar al final del archivo (después de `.cancelBtn:disabled`, línea 167) exactamente:
```css
/* Botón "Ver consola" por run: mismo lenguaje visual que cancelBtn/iconBtn.
   aria-pressed=true = la consola abierta en el dock es la de ESTE run. */
.consoleBtn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-muted);
  cursor: pointer;
}

.consoleBtn:hover,
.consoleBtn[aria-pressed="true"] {
  border-color: var(--accent);
  color: var(--accent);
}
```

- **Prohibido en esta fase:** tocar `CodexConsoleDock.tsx`, `workbench.ts`, `useExecutionStream`, `App.tsx` o cualquier otro archivo.
- **Comando exacto** (desde `Stacky Agents/frontend/`): `npx vitest run src/components/__tests__/ActiveRunsPanel.test.tsx` (si el gap de entorno está resuelto: 10/10 verdes — 6 existentes + 4 nuevos).
- **Criterio de aceptación (binario):** `npx tsc --noEmit` termina con exit code 0 y 0 errores; el diff toca EXACTAMENTE los 2 archivos listados (más el test de F0).
- **Flag:** no aplica (§3.1). **Trabajo del operador: ninguno.**

---

### F2 — Verificación estática

**Objetivo (1 frase):** demostrar con comandos que el cambio no rompe nada compilable ni tests puros existentes.

- **Comandos exactos** (desde `Stacky Agents/frontend/`), en este orden:
  1. `npx tsc --noEmit` → **criterio binario: exit 0, 0 errores.**
  2. `npx vitest run src/components/__tests__/ActiveRunsPanel.test.tsx` → si falla SOLO por `Cannot find module '@testing-library/react'` (o equivalente jsdom), es el gap preexistente documentado y NO bloquea; cualquier otro error SÍ bloquea.
- **No correr la suite vitest completa** (regla del repo: tests por archivo).
- **Flag:** no aplica. **Trabajo del operador: ninguno.**

---

### F3 — Verificación manual (smoke, 5 pasos)

**Objetivo (1 frase):** confirmar a mano, con la app corriendo, que el botón abre la consola en vivo del run correcto desde cualquier pantalla.

Pasos exactos (con backend y frontend levantados como siempre):
1. Lanzar cualquier agente desde un ticket (runtime `claude_code_cli` o `codex_cli`) y, si el dock se abrió solo, cerrarlo/minimizarlo.
2. Navegar a OTRA pantalla (p. ej. tab de Documentación o Diagnóstico): el panel "EJECUCIONES ACTIVAS" flota con el run listado.
3. Click en el ícono de terminal de esa fila → **criterio binario:** el `CodexConsoleDock` aparece mostrando los logs en vivo de ESE `execution_id` (el header del dock muestra el id) y, por ser runtime interactivo, el input de stdin está habilitado.
4. Repetir con un run de runtime `github_copilot` (p. ej. lanzar un agente con ese runtime): el dock abre en modo solo-lectura de logs (sin stdin) — comportamiento ya existente del dock, sin cambios.
5. Con la consola abierta, verificar que el botón de esa fila queda resaltado (`aria-pressed=true` → borde/color acento) y que "✕ Cancelar", colapsar y mover esquina siguen funcionando igual que antes.

- **Criterio de aceptación (binario):** los 5 pasos pasan tal cual están escritos.
- **Trabajo del operador: ninguno** (esta verificación la hace quien implementa).

## 5. Paridad de runtimes (documentación explícita, sin código nuevo)

| Runtime | Qué ve el operador al abrir la consola desde el panel | Quién lo resuelve |
|---|---|---|
| `codex_cli` | Logs en vivo por streaming + input stdin habilitado | `CodexConsoleDock` existente (`isInteractiveRun`) |
| `claude_code_cli` | Logs en vivo por streaming + input stdin habilitado | `CodexConsoleDock` existente (`isInteractiveRun`) |
| `github_copilot` (y `mock`) | Logs en vivo por streaming, solo-lectura (sin stdin) | `CodexConsoleDock` existente: el panel de logs (líneas 190-223) se renderiza para cualquier runtime; solo el stdin se gatea |

No hay fallback nuevo que implementar: la paridad ya está resuelta por el componente existente. El botón es idéntico para los 3.

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Abrir la consola de un run de OTRO proyecto que no es el activo | **Intencional y deseado**, coherente con el diseño existente del panel (`all_projects: true`, comentario en `ActiveRunsPanel.tsx:31-36`): el objetivo es visibilidad global. La consola streamea por `execution_id`, que es global — no depende del proyecto activo. No mitigar. |
| El operador tenía otra consola abierta y el click la reemplaza | Comportamiento idéntico al de todos los demás call sites de `setCodexConsoleExecution` (una sola consola global); reabrir la anterior es 1 click desde el mismo panel. Aceptado. |
| Ruptura del layout de la fila por la columna nueva | El grid pasa explícitamente a 5 columnas (`10px 44px 1fr auto auto`); el meta ya tiene `ellipsis` y absorbe el ancho. Verificado en F3. |
| El run termina entre el refresco (5 s) y el click | El dock muestra los logs del run terminado (comportamiento existente del stream) y el panel lo saca de la lista en el próximo refetch. Sin cambio requerido. |
| Tests de componente no ejecutables hoy | Gap preexistente documentado en el propio archivo de tests; el gate ejecutable es `tsc --noEmit` + F3. Los tests quedan listos. |

## 7. Fuera de scope (prohibido en este plan)

- Tocar la lógica interna de `CodexConsoleDock.tsx` (incluido su header/label), `useExecutionStream`, `workbench.ts` o `App.tsx`.
- Agregar botones de consola en otras vistas que no sean el panel global `ActiveRunsPanel`.
- Resolver el gap de entorno `@testing-library/react`/jsdom.
- Multi-consola (varias consolas abiertas a la vez), historial de consolas, o persistencia de la consola abierta.
- Cualquier flag de harness, endpoint, migración o cambio de backend.

## 8. Glosario

- **Panel de ejecuciones activas:** `ActiveRunsPanel`, panel flotante global montado en `App.tsx:274`, visible en toda la app cuando hay runs `running/preparing/queued` en CUALQUIER proyecto.
- **Run activo:** una `AgentExecution` con status `running`, `preparing` o `queued`.
- **Dock / consola:** `CodexConsoleDock`, componente global (montado en `App.tsx:269`) que muestra logs en vivo de una ejecución vía streaming y, para runtimes CLI interactivos, permite mandar stdin. Renderiza `null` si `codexConsoleExecutionId` es null.
- **`useWorkbench`:** store global zustand del frontend (`frontend/src/store/workbench.ts`). "Abrir la consola" = llamar su acción `setCodexConsoleExecution(id, minimized)`.
- **`aria-pressed`:** atributo ARIA de botón-toggle; acá indica que la consola abierta en el dock corresponde a ese run.

## 9. Orden de implementación

1. **F0** — tests en `ActiveRunsPanel.test.tsx` (mock del store + 4 tests nuevos).
2. **F1** — botón en `ActiveRunsPanel.tsx` + estilos en `ActiveRunsPanel.module.css`.
3. **F2** — `tsc --noEmit` + vitest por archivo.
4. **F3** — smoke manual de 5 pasos.

## 10. Definición de Hecho (DoD)

- [ ] Los 4 tests nuevos existen en `ActiveRunsPanel.test.tsx` con los nombres exactos de F0 y compilan.
- [ ] El botón "Ver consola" aparece en cada fila del panel, con `aria-label="Ver consola de la ejecución #<id>"` (constante), y es un toggle real: abre con `setCodexConsoleExecution(e.id, false)` y cierra con `setCodexConsoleExecution(null, false)` cuando ya está abierto.
- [ ] `aria-pressed` refleja si la consola abierta es la de ese run, con estilo acento.
- [ ] `npx tsc --noEmit` = 0 errores.
- [ ] `npx vitest run src/components/__tests__/ActiveRunsPanel.test.tsx` verde, o rojo SOLO por el gap preexistente de RTL/jsdom.
- [ ] Smoke F3 (5 pasos) pasado, incluyendo el paso 4 de paridad copilot solo-lectura.
- [ ] Diff limitado a EXACTAMENTE 3 archivos: `ActiveRunsPanel.tsx`, `ActiveRunsPanel.module.css`, `ActiveRunsPanel.test.tsx`.
- [ ] Ningún cambio en `CodexConsoleDock.tsx`, `workbench.ts`, `App.tsx`, backend ni flags.
