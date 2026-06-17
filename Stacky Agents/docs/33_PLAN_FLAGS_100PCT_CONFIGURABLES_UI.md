# Plan 33: Flags 100% configurables por UI

**Estado:** IMPLEMENTADO  
**Fecha:** 2026-06-15  
**Autor:** StackyArchitectaUltraEficientCode

---

## Objetivo

Hacer visibles y editables desde la UI **todos** los feature flags del `FLAG_REGISTRY`
de `services/harness_flags.py`. El backend (endpoint `GET/PUT /api/harness-flags`) ya
existe y es completo. El gap es exclusivamente de frontend: ningún panel genérico
renderiza ese registry. El operador hoy solo puede cambiar flags editando el `.env` a
mano o a través del panel parcial de Memoria.

Restricciones:
- Sin nuevos endpoints de backend (el registry ya es la fuente canónica).
- Sin rediseñar el componente `MemoryConfigPanel` — los 4 flags de memoria se quedan
  donde están.
- Todo flag nuevo que se agregue al `FLAG_REGISTRY` en el futuro debe aparecer en la UI
  **sin tocar el frontend**: el componente genérico lee el registry dinámicamente.

---

## Diagnóstico

| Capa | Estado |
|---|---|
| `services/harness_flags.py` — `FLAG_REGISTRY` | ~70 flags, labels, descriptions, grupos y tipos declarados |
| `api/harness_flags.py` — `GET/PUT /api/harness-flags` | Completo, hot-apply, persiste al `.env` |
| `api/harness_flags.py` — `POST /api/harness-flags/profile` | V0.1 perfiles off/safe/full |
| `frontend/src/api/endpoints.ts` — `HarnessFlags.list()/.update()` | Listo |
| Panel genérico en SettingsPage | **NO EXISTE** |
| `MemoryConfigPanel` — 4 flags de memoria | Parcial, ad-hoc, no representa el registry |

---

## Ítems

### F1 — Componente genérico `HarnessFlagsPanel`

**F1.1 — Componente React que renderiza el FLAG_REGISTRY completo**

Crear `frontend/src/components/HarnessFlagsPanel.tsx`.

El componente:
1. Llama `HarnessFlags.list()` (ya existe en `endpoints.ts`).
2. Agrupa los flags por `spec.group` ("claude_code_cli", "codex_cli", "global").
3. Por cada flag renderiza un control según `spec.type`:
   - `bool` → toggle (checkbox o switch).
   - `int` → input numérico.
   - `float` → input numérico con decimales.
   - `csv` → input de texto.
   - `json` → textarea con validación JSON inline.
4. Si `spec.pair` apunta a un flag CSV, renderiza ese input de allowlist inmediatamente
   debajo del master bool (acoplado visualmente).
5. Tooltip/hint con `spec.description`.
6. Llama `HarnessFlags.update({ KEY: valor })` en cada cambio (blur para text/json,
   inmediato para bool).
7. Muestra el perfil activo (`active_profile`) y botones "Aplicar perfil: off / safe /
   full" vía `POST /api/harness-flags/profile` (endpoint ya existe).
8. Indicador de "guardando" y errores en línea (sin modal).

Archivos afectados:
- `frontend/src/components/HarnessFlagsPanel.tsx` (nuevo)
- `frontend/src/components/HarnessFlagsPanel.module.css` (nuevo)

Criterio de aceptación:
- Con el backend corriendo, el panel renderiza todos los flags del registry sin
  hardcodear ninguna key.
- Un toggle de un flag bool llama `HarnessFlags.update` con el valor correcto y la UI
  refleja el nuevo valor tras la respuesta.
- Un input json inválido muestra error inline y bloquea el guardado.
- Los botones de perfil llaman al endpoint de perfil y muestran `active_profile`
  actualizado.

**F1.2 — Tests unitarios del componente genérico**

Archivo: `frontend/src/components/__tests__/HarnessFlagsPanel.test.tsx`

Escenarios:
1. Renderiza grupos y labels del mock del registry.
2. Toggle bool llama `HarnessFlags.update` con `{ KEY: true/false }`.
3. Input json inválido bloquea el botón de guardar.
4. Botón de perfil "safe" llama al endpoint de perfiles.
5. Error de API muestra mensaje en línea (sin crash).

---

### F2 — Sub-tab "Arnés / Flags" en SettingsPage

**F2.1 — Agregar sub-tab al panel de Configuración**

`SettingsPage.tsx` ya tiene un sistema de sub-tabs (`"flow" | "sections" | ...`).
Agregar `"harness"` como nuevo sub-tab que renderiza `<HarnessFlagsPanel />`.

Archivos afectados:
- `frontend/src/pages/SettingsPage.tsx`

Cambio: añadir la opción `"harness"` al tipo `SubTab`, el botón en `div.subTabs`, y el
renderizado condicional `{sub === "harness" && <HarnessFlagsPanel />}`.

Criterio de aceptación:
- Al hacer click en el tab "Arnés", aparece el panel con todos los grupos de flags.
- La navegación entre tabs no rompe los otros sub-tabs.

**F2.2 — Test de integración mínimo del sub-tab**

Archivo: `frontend/src/pages/__tests__/SettingsPage.harness.test.tsx` (nuevo)

Escenarios:
1. Click en tab "Arnés" → `HarnessFlagsPanel` visible.
2. Click en tab "Flujo" → `HarnessFlagsPanel` ya no está en el DOM.

---

### F3 — Flags críticos: activar por defecto en `config.py`

Los siguientes flags tienen comportamiento correctivo con impacto directo en
confiabilidad; su default `false` fue elegido para retro-compat en el momento del
plan, pero con los planes 28-30 completos y verdes, el riesgo de activarlos es bajo y
el costo de no activarlos es alto (éxitos fantasma, procesos zombie, tasks duplicadas).

**Cambio**: en `config.py`, cambiar el `os.getenv(..., "false")` a `"true"` para estos
flags. El operador puede revertir a `false` en su `.env` si necesita el comportamiento
antiguo.

Flags propuestos para default `true`:

| Flag | Plan | Motivo |
|---|---|---|
| `STACKY_RUNNER_REAP_ON_CLOSE_ENABLED` | R0.1 | Elimina procesos zombie; ya validado con tests. |
| `STACKY_ORPHAN_REAPER_ENABLED` | R0.3 | Reconcilia runs huérfanos al arrancar; sin efecto si no hay huérfanos. |
| `STACKY_PENDING_TASK_STRICT_VALIDATION_ENABLED` | R1.2 | Evita tasks mal formadas en ADO; ya documentado como causa raíz recurrente. |
| `STACKY_RUN_PREFLIGHT_GATE_ENABLED` | G0.1 | Bloquea runs imposibles antes de desperdiciar crédito de agente. |
| `STACKY_VERIFY_TASK_BEFORE_CONSUMED_ENABLED` | G1.1 | Resuelve el éxito fantasma (stale-consumed-pending-task). |

Archivos afectados:
- `Stacky Agents/backend/config.py` (5 líneas, cambia el string del default)
- `Stacky Agents/backend/.env.example` (documentar el nuevo default)

Criterio de aceptación:
- `Config()` sin `.env` instancia esos 5 flags como `True`.
- Test existente de cada flag (test_plan28_*, test_plan30_*) sigue verde.
- No hay regresión en tests de otros módulos que dependan del comportamiento OFF.

---

### F4 — `.env.example` completo y ordenado

El `.env.example` actual solo tiene las claves gestionadas por `global-config`. Los
~70 flags del registry no están documentados allí, por lo que el operador no sabe
qué puede configurar.

**F4.1 — Actualizar `.env.example`**

Generar una sección `# ── Arnés de agentes (flags configurables vía UI) ──` en
`.env.example` con todas las claves del `FLAG_REGISTRY`, su tipo, y el valor default
documentado en un comentario (extraído del propio `config.py`).

Archivo afectado:
- `Stacky Agents/backend/.env.example`

Criterio de aceptación:
- Cada key del `FLAG_REGISTRY` tiene al menos una línea comentada en `.env.example`.
- Un nuevo operador puede configurar el arnés sin leer el código Python.

---

## Prioridad de implementación

1. **F1.1 + F1.2** — mayor impacto, puro frontend, cero riesgo de regresión backend.
2. **F2.1 + F2.2** — trivial una vez que F1 existe (solo wiring en SettingsPage).
3. **F3** — alto impacto operacional, cambio mínimo en config.py, validar contra tests existentes.
4. **F4.1** — bajo riesgo, alta utilidad para onboarding.

---

## Flags críticos que deberían activarse por defecto

Ver F3 arriba. Los más urgentes (por impacto en confiabilidad documentado en memoria):
- `STACKY_VERIFY_TASK_BEFORE_CONSUMED_ENABLED` — resuelve directamente el éxito
  fantasma (stale-consumed-pending-task-trap, bug recurrente).
- `STACKY_PENDING_TASK_STRICT_VALIDATION_ENABLED` — previene el mismatch ordinal vs
  ADO id en origen (causa raíz documentada de "crea archivos pero no la task").
- `STACKY_RUNNER_REAP_ON_CLOSE_ENABLED` — elimina procesos zombie (causa documentada
  de sesiones Claude CLI zombie).

---

## Lo que este plan NO hace

- No rediseña el `MemoryConfigPanel` ni mueve sus flags al panel genérico.
- No agrega nuevos flags al `FLAG_REGISTRY` (eso es responsabilidad de cada plan).
- No crea un sistema de perfiles en la UI más allá de los 3 ya existentes (off/safe/full).
- No agrega autenticación/RBAC (innecesario en mono-operador).
