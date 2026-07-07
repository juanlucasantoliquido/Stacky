# Plan 100 — Suite DevOps en un click: activación en lote HITL del paquete de flags + primeros pasos inline

**Estado:** PROPUESTO (v1)
**Versión:** v1
**Fecha:** 2026-07-06
**Autor:** StackyArchitectaUltraEficientCode
**Serie:** azúcar de onboarding ENCIMA del subsistema de flags (planes 33/63/82/86) y
del panel DevOps (87-91, 97). NO es un bypass del sistema de flags: reusa su endpoint
escritor. NO depende de los planes 93-96 (pendientes) ni del 98/99 (PROPUESTOS);
ninguno depende de este.
**Frontera con los planes de flags que NO contradice:** 33 (flags 100% configurables
por UI — este plan agrega UNA acción de UI que llama al MISMO endpoint), 63
(`_CURATED_DEFAULTS_ON` + categorización — este plan no promueve ningún default ni
agrega flags a la lista curada), 82 (claridad de config: `requires`/`profile_deltas` —
este plan RESPETA el grafo `requires` al ordenar la activación), 86 (flags para
mortales: `PlainHelp` con ayuda llana — este plan REUSA ese texto llano en el modal de
resumen). El botón es azúcar, no un sustituto del `HarnessFlagsPanel`.

**Dependencias (todas IMPLEMENTADAS y verificadas en el working tree 2026-07-06):**

| Pieza existente reusada | Evidencia (archivo:línea) |
|---|---|
| `HarnessFlags.update({KEY: value})` — dueño único escritor de flags (PUT `/api/harness-flags`) | `frontend/src/api/endpoints.ts:865-874`; backend `backend/api/harness_flags.py:117` (`put_harness_flags`) |
| El PUT ya persiste al `.env` (`_write_env`) + hot-apply (`setattr` config + `os.environ`) | `backend/api/harness_flags.py:125-156` |
| `FlagGateBanner` (activar 1 flag con 1 click; el punto donde hoy se activa de a una) | `frontend/src/components/devops/FlagGateBanner.tsx:30-50` |
| Categoría `devops` con las 6 flags del panel (fuente de la lista del paquete) | `backend/services/harness_flags.py:177-184` (`_CATEGORY_KEYS["devops"]`) |
| Grafo `requires` declarativo por flag (orden de activación correcto) | `backend/services/harness_flags.py:1975` (`requires="STACKY_DEVOPS_PANEL_ENABLED"`) y análogos; congelado en `backend/tests/test_harness_flags_requires.py` (`_REQUIRES_MAP_FROZEN`) |
| `PlainHelp` (what/on_effect/off_effect/example en llano) para el resumen del modal | `backend/services/harness_flags_help.py:626-637` (devops) |
| Health SIEMPRE-200 con booleans por flag (para saber cuáles YA están ON) | `backend/api/devops.py:26-40` |
| Galería de presets del Plan 97 (preset `todo-completo` reusa el patrón; NO se duplica) | `frontend/src/components/devops/PublicationsSection.tsx:127-132` (`handleCreateTodoPreset`) |
| Punto de fricción del catálogo vacío (manda a otra pantalla) | `frontend/src/components/devops/PublicationsSection.tsx:224-228` |
| `process_catalog` viaja en el client-profile; validado en el PUT (allowlist `kind`) | `backend/api/client_profile.py:141-165` |
| Snapshot versionado del arnés + generador | `backend/harness_defaults.env`, `deployment/export_harness_defaults.py:42-72` (`registry_default_values` lee `config.<KEY>`) |
| Centinelas que fijan `harness_defaults.env` con `=true`/`=false` literal | `backend/tests/test_plan87_devops_flag.py:75-85` (`test_f0_harness_defaults_contains_flag`) y análogos 88/89/90/91 |
| Patrón de test vitest TS-puro sin render | `frontend/src/pages/__tests__/ServersSection.test.ts:1-27` |

**GAP VERIFICADO:** no existe ninguna acción de activación EN LOTE de flags en el
frontend — `FlagGateBanner` (`FlagGateBanner.tsx:34`) y `HarnessFlagsPanel` activan de
a UNA. El operador que quiere el panel DevOps completo hoy pulsa "Activar ahora" en
CADA banner (hasta 6 flags devops: PANEL, PUBLICATIONS, ENVIRONMENTS, AGENT, SERVERS,
+ generador/trigger que gobiernan pipelines), navegando sección por sección
(`DevOpsPage.tsx` monta un `FlagGateBanner` por sección gated). **Prueba viva del
dolor (2026-07-06):** el operador activó las flags una por una y el working tree quedó
con `config.py` tocado sin commitear + 5 centinelas de `harness_defaults.env` en rojo +
falta correr `export_harness_defaults.py` (ver memoria del repo
`harness-defaults-env-drift-devops-87-91`). El botón suite ataca EXACTO ese flujo.

---

## 1. Objetivo + KPI

Un botón **"Activar suite DevOps"** en el shell del panel que, con **un solo confirm
HITL**, activa el PAQUETE coherente de flags devops que están OFF, en el orden correcto
según el grafo `requires`, reusando el endpoint escritor existente
(`HarnessFlags.update`) — nunca un writer nuevo. El modal de resumen lista EXACTAMENTE
qué va a activar (nombre + ayuda llana del Plan 86 + nivel de riesgo) y qué YA está ON
(no se re-activa: idempotencia). Complementariamente, dos "primeros pasos" inline en
`PublicationsSection`: (a) cargar el catálogo de procesos SIN salir de la sección, y
(b) crear el preset `todo-completo` automático cuando falta (reusa el patrón del 97).

**KPI (medibles; los binarios están en cada fase):**

| Métrica | Hoy | Después | Cómo se mide |
|---|---|---|---|
| Clicks para dejar el panel DevOps completamente operativo | hasta 6 (un "Activar ahora" por sección) + navegación entre secciones | 2 (abrir modal + 1 confirm) | conteo manual + test de que el modal lista todas las OFF |
| Requests de activación | 1 PUT por flag (hasta 6) | 1 PUT con todas las OFF en un `updates` | test `activa en un solo update` |
| Flags activadas en orden `requires` inseguro (dependencia antes que dependiente) | posible si el operador activa PUBLICATIONS antes que PANEL | imposible: orden topológico server-friendly | test `orden respeta requires` |
| Fricción del catálogo vacío | redirección a otra pantalla (`PublicationsSection.tsx:224-228`) | carga inline sin navegar | grep + test de que el aviso ofrece acción inline |
| Drift de `harness_defaults.env` tras activar | 5 centinelas en rojo, sin aviso al operador | aviso explícito en el modal + doc del comando de sync (NO se agrava) | §3 postura + F4 |

## 2. Por qué ahora / gap que cierra (evidencia)

La serie DevOps creció a 6 flags de categoría `devops` (`harness_flags.py:177-184`) más
las 2 del generador/trigger que el panel consume. Cada plan nuevo (93-96 sumarán más)
agrega otra flag que el operador debe descubrir y activar a mano. El
`FlagGateBanner` resuelve activar UNA con contexto, pero no hay "activá todo el panel".
El resultado real está documentado hoy: activación manual → `config.py` sin commitear +
centinelas de `harness_defaults.env` rojos (memoria `harness-defaults-env-drift-devops-87-91`).
El botón no inventa mecanismo: envuelve `HarnessFlags.update` (que YA persiste y
hot-aplica) con un resumen HITL y el orden `requires`. Los "primeros pasos" cierran el
otro hueco de onboarding: tras activar, el operador topa con el catálogo vacío y un
preset ausente antes de poder publicar.

## 3. Principios y guardarraíles (no negociables, verificables)

1. **DECISIÓN DE FLAG — el botón suite es UI ADITIVA SIN flag propia, justificado:**
   - El botón NO ejecuta ninguna acción por sí solo: abre un modal; nada se activa sin
     el confirm explícito (HITL). Es UI pura sobre el endpoint existente.
   - Gatear "un botón que activa flags" detrás de OTRA flag sería recursión inútil (el
     operador tendría que activar una flag para poder activar flags) y agregaría una
     décima flag sin decisión real detrás — degradaría la señal del panel (anti-patrón
     que 82/86 combaten). Precedente: `FlagGateBanner` (activar 1 flag) NO está gateado
     por flag; este es su hermano en lote.
   - Los "primeros pasos" inline (catálogo, preset todo) SÍ viven DENTRO de secciones
     ya gateadas por sus flags respectivas (`publications_enabled`); heredan ese gate,
     no agregan uno nuevo.
   - **NO se crea NINGUNA `FlagSpec` nueva en este plan** ⇒ el gotcha de `default=False`
     (Plan 63) no aplica (no hay flag nueva que registrar); `_CATEGORY_KEYS`,
     `FLAG_REGISTRY` y `_REQUIRES_MAP_FROZEN` quedan intactos.
2. **Reusar el mecanismo de flags, jamás un bypass (respeta 33/63/82/86):** la
   activación va SIEMPRE por `HarnessFlags.update` (`endpoints.ts:865`), que persiste al
   `.env` y hot-aplica (`api/harness_flags.py:125-156`). Este plan NO escribe `config.py`
   ni `.env` por su cuenta, NO toca `HarnessFlagsPanel`, NO promueve defaults.
3. **HITL innegociable:** el modal muestra la lista completa ANTES de activar; requiere
   un click de confirmación; muestra qué YA está ON (no re-activa). Sin confirm, cero
   efecto. El operador puede cerrar el modal sin activar nada.
4. **Idempotencia:** solo se incluyen en el `updates` las flags que están OFF según el
   health; las ON se listan como "ya activas" y NO se re-envían.
5. **Orden `requires` correcto:** el `updates` se construye en orden topológico
   (dependencia antes que dependiente) leyendo el grafo `requires` que el backend ya
   expone; como el endpoint aplica todas las keys del `updates` en la misma llamada, el
   orden es defensivo (garantiza que si el backend validara `requires` en orden, no
   fallaría) y correcto para el usuario que lee la lista.
6. **POSTURA SOBRE EL DRIFT de `harness_defaults.env` (explícita):** el botón suite
   **NO regenera `harness_defaults.env`** y **NO agrava el drift** respecto de activar
   las mismas flags a mano (hace exactamente lo mismo: persiste al `.env` del deploy vía
   `_write_env`). El `harness_defaults.env` es un **snapshot versionado del REPO que el
   build hornea** (`export_harness_defaults.py:74-80`), no un archivo que la UI deba
   escribir en runtime — regenerarlo desde el botón mezclaría responsabilidades
   (runtime escribiendo un artefacto de build versionado) y podría hornear en el repo un
   estado local del operador. En su lugar: (a) el modal AVISA en llano que "activar
   estas flags cambia tu configuración local; el archivo versionado de defaults del repo
   se actualiza al generar un deploy" y (b) el doc deja registrado el comando canónico de
   sync para quien mantenga el repo:
   `python "Stacky Agents/deployment/export_harness_defaults.py" --seed-registry-defaults --out "Stacky Agents/backend/harness_defaults.env"`.
   Esto es consistente con el diseño existente (el generador lee `config.<KEY>` como
   fuente de verdad, `export_harness_defaults.py:57-60`) y con que el drift actual es un
   problema de *commit del repo*, no de *runtime del operador*.
7. **Cero trabajo extra del operador:** el botón REDUCE trabajo (6 clicks → 2); los
   primeros pasos evitan navegación. Backward-compatible: `FlagGateBanner` y el flujo
   por-sección siguen intactos (el operador puede seguir activando de a una).
8. **3 runtimes (Codex CLI, Claude Code CLI, GitHub Copilot Pro):** impacto NINGUNO —
   frontend (modal + botón) sobre un endpoint de configuración que ya existe; ningún
   runner/prompt/harness consume esto (precedente 78/98/99). Verificable por grep.
9. **Mono-operador sin auth:** N/A (sin RBAC; el endpoint de flags ya es mono-operador).
10. **No degradar / sin deps nuevas:** cero dependencias npm/py; reusa clases CSS del
    panel; el único backend nuevo es un endpoint SOLO-LECTURA que arma la lista del
    paquete (para no hardcodear la lista de flags en el frontend).

---

## F0 — Endpoint SOLO-LECTURA `GET /api/devops/flag-bundle` (la lista del paquete, sin hardcodear en el front)

**Objetivo:** exponer, desde la fuente de verdad del backend, qué flags componen la
suite DevOps, su estado actual (ON/OFF), su ayuda llana (Plan 86), su `requires` y un
orden de activación topológico — para que el frontend no duplique la lista ni el grafo.
**Valor:** una sola fuente de verdad; sumar una flag devops futura la incluye sola.

**Archivo a editar:** `Stacky Agents/backend/api/devops.py` — endpoint nuevo (SIEMPRE
200, como `/health`; el botón necesita leer esto aunque el panel esté parcialmente OFF):

```python
@bp.get("/flag-bundle")
def devops_flag_bundle_route():
    """Lista declarativa de las flags de la suite DevOps para el activador en lote
    (Plan 100). SOLO-LECTURA, SIEMPRE 200. NO activa nada (eso lo hace el PUT de
    /api/harness-flags con confirm del operador)."""
    from services.harness_flags import _CATEGORY_KEYS, read_current
    from services.harness_flags_help import get_plain_help  # helper existente del 86
    cfg = _config.config
    # Fuente de verdad de la lista: la categoría 'devops' del registry (harness_flags.py:177).
    # MÁS las 2 flags de pipeline que el panel consume (generador/trigger), en el orden
    # en que deben activarse (dependencias primero). El orden se deriva de requires abajo.
    devops_keys = list(_CATEGORY_KEYS.get("devops", ()))
    pipeline_keys = ["STACKY_PIPELINE_GENERATOR_ENABLED", "STACKY_PIPELINE_TRIGGER_ENABLED"]
    all_keys = devops_keys + [k for k in pipeline_keys if k not in devops_keys]
    current = read_current()  # dict key -> valor efectivo (bool)
    specs_by_key = {s.key: s for s in _flag_registry()}  # helper local: import FLAG_REGISTRY
    items = []
    for key in all_keys:
        spec = specs_by_key.get(key)
        if spec is None:
            continue
        help_obj = get_plain_help(key)  # PlainHelp o None
        items.append({
            "key": key,
            "label": getattr(spec, "label", key),
            "enabled": bool(current.get(key, False)),
            "requires": getattr(spec, "requires", None),
            "what": getattr(help_obj, "what", "") if help_obj else "",
            "on_effect": getattr(help_obj, "on_effect", "") if help_obj else "",
            "risk": _bundle_risk(key),  # 'panel-base' | 'accion' | 'servidores' — abajo
        })
    ordered = _topo_by_requires(items)  # dependencias antes que dependientes (F0 helper)
    return jsonify({"flags": ordered})
```

Helpers nuevos EN EL MISMO archivo (`api/devops.py`), puros:

```python
def _flag_registry():
    from services.harness_flags import FLAG_REGISTRY
    return FLAG_REGISTRY

# Riesgo declarativo llano para el modal (NO es severidad técnica; es "qué implica"):
_BUNDLE_RISK = {
    "STACKY_DEVOPS_SERVERS_ENABLED": "servidores",   # guarda credenciales (keyring)
    "STACKY_DEVOPS_AGENT_ENABLED": "accion",         # lanza CLIs
    "STACKY_PIPELINE_TRIGGER_ENABLED": "accion",     # dispara pipelines
}
def _bundle_risk(key: str) -> str:
    return _BUNDLE_RISK.get(key, "panel-base")

def _topo_by_requires(items: list[dict]) -> list[dict]:
    """Ordena para que toda flag aparezca DESPUÉS de la que declara en 'requires'.
    El grafo es de profundidad 1 (R4 del Plan 82): un requires apunta a una key que no
    requiere nada más dentro del bundle. Kahn simple; ciclos imposibles por R4."""
    by_key = {it["key"]: it for it in items}
    ordered: list[dict] = []
    seen: set[str] = set()
    def visit(it):
        if it["key"] in seen:
            return
        req = it.get("requires")
        if req and req in by_key and req not in seen:
            visit(by_key[req])
        seen.add(it["key"])
        ordered.append(it)
    for it in items:
        visit(it)
    return ordered
```

**Nota de investigación para el implementador:** verificar el nombre real del helper de
ayuda llana en `services/harness_flags_help.py` (el módulo expone las `PlainHelp` del
Plan 86; si el accessor no se llama `get_plain_help`, usar el que exista — p. ej. leer
el dict del módulo directamente). Si no hubiera accessor público, leer el dict de ayudas
por key con un `getattr` defensivo y degradar a `""` (nunca romper el endpoint).

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/backend/tests/test_plan100_flag_bundle_endpoint.py`, 6 casos:

1. `test_bundle_200_always` — `GET /api/devops/flag-bundle` responde 200 aunque
   `STACKY_DEVOPS_PANEL_ENABLED` esté OFF.
2. `test_bundle_includes_all_devops_category` — el set de keys de la respuesta ⊇
   `_CATEGORY_KEYS["devops"]`.
3. `test_bundle_includes_pipeline_flags` — incluye
   `STACKY_PIPELINE_GENERATOR_ENABLED` y `STACKY_PIPELINE_TRIGGER_ENABLED`.
4. `test_bundle_enabled_reflects_current` — con `STACKY_DEVOPS_PANEL_ENABLED` ON en
   config, ese item trae `enabled: True`; una flag OFF trae `enabled: False`.
5. `test_bundle_topo_order_requires_before_dependent` — en la lista, el índice de
   `STACKY_DEVOPS_PANEL_ENABLED` es MENOR que el de toda flag cuyo `requires` sea
   PANEL (verificar al menos `STACKY_DEVOPS_PUBLICATIONS_ENABLED` y
   `STACKY_DEVOPS_ENVIRONMENTS_ENABLED`).
6. `test_bundle_has_plain_help_fields` — cada item trae las keys `what`, `on_effect`,
   `risk` (strings; pueden ser vacíos pero existen).

**Comandos (venv real `.venv`):**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan100_flag_bundle_endpoint.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q
```

**Criterio de aceptación (binario):** 6 tests verdes + `test_harness_flags.py` verde
(no se tocó el registry). **Flag:** ninguna (endpoint SOLO-LECTURA aditivo; sin gate —
espeja `/health` que también es siempre-200).
**Impacto por runtime:** NINGUNO. Fallback: N/A.
**Trabajo del operador:** ninguno.

---

## F1 — `DevOps.flagBundle` en el cliente + tipo de respuesta

**Objetivo:** exponer el endpoint F0 al frontend.
**Valor:** el shell puede leer la lista real del paquete.

**Archivo a editar:** `Stacky Agents/frontend/src/api/endpoints.ts` — dentro de
`export const DevOps` (hoy `endpoints.ts:3072-3112`):

```ts
export interface DevOpsFlagBundleItem {
  key: string;
  label: string;
  enabled: boolean;
  requires: string | null;
  what: string;
  on_effect: string;
  risk: 'panel-base' | 'accion' | 'servidores';
}
```

y el método:

```ts
  /** GET /api/devops/flag-bundle — Plan 100. Lista del paquete de flags DevOps. */
  flagBundle: () => api.get<{ flags: DevOpsFlagBundleItem[] }>("/api/devops/flag-bundle"),
```

**Tests PRIMERO (TDD)** — caso 1 de archivo nuevo
`Stacky Agents/frontend/src/pages/__tests__/DevOpsSuite.test.ts`:

1. `endpoints expone DevOps.flagBundle` — `import('../../api/endpoints')` ⇒
   `typeof mod.DevOps.flagBundle === 'function'`.

**Comandos:**

```
npx vitest run src/pages/__tests__/DevOpsSuite.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** test 1 verde + `tsc` 0 errores.
**Flag:** ninguna. **Impacto por runtime:** NINGUNO. **Trabajo del operador:** ninguno.

---

## F2 — Modal `ActivateSuiteModal` (resumen HITL + confirm + activación en lote idempotente)

**Objetivo:** el modal que lista qué se va a activar (OFF), qué ya está ON, con ayuda
llana y riesgo, y activa en lote con `HarnessFlags.update` en orden `requires` tras un
único confirm.
**Valor:** el corazón del plan: 6 clicks → 2, HITL, idempotente.

**Archivo NUEVO:**
`Stacky Agents/frontend/src/components/devops/ActivateSuiteModal.tsx`

```tsx
/**
 * ActivateSuiteModal (Plan 100 F2)
 * Modal HITL: lista las flags de la suite DevOps (F0), separa OFF (a activar) de
 * ON (ya activas, no se re-envían), muestra ayuda llana (Plan 86) + riesgo, y activa
 * SOLO las OFF con HarnessFlags.update en orden requires, tras UN confirm.
 */
import React, { useState } from 'react';
import { DevOps, HarnessFlags, type DevOpsFlagBundleItem } from '../../api/endpoints';
import styles from './devops.module.css';

export interface ActivateSuiteModalProps {
  bundle: DevOpsFlagBundleItem[];   // ya viene ordenado por requires desde F0
  onDone: () => void;               // refetch health del shell tras activar
  onClose: () => void;
}

export const ActivateSuiteModal: React.FC<ActivateSuiteModalProps> = ({ bundle, onDone, onClose }) => {
  const off = bundle.filter((f) => !f.enabled);
  const on = bundle.filter((f) => f.enabled);
  const [confirmChecked, setConfirmChecked] = useState(false);
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const handleActivate = async () => {
    if (!confirmChecked || off.length === 0) return;
    setActivating(true);
    setError(null);
    try {
      // Un solo PUT con TODAS las OFF (orden requires preservado por el array).
      const updates: Record<string, boolean> = {};
      for (const f of off) updates[f.key] = true;
      const result = await HarnessFlags.update(updates);
      if (!result.ok) { setError(result.error ?? 'Error al activar'); return; }
      setDone(true);
      onDone();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error de red al activar');
    } finally {
      setActivating(false);
    }
  };

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modalBody}>
        <h3 style={{ marginTop: 0 }}>Activar suite DevOps</h3>
        {done ? (
          <>
            <div className={styles.alertSuccess}>Suite activada: {off.length} funciones nuevas encendidas.</div>
            <p className={styles.textMuted} style={{ fontSize: '0.85em' }}>
              Nota: esto cambió tu configuración local. El archivo versionado de defaults
              del repo se actualiza al generar un deploy (no hace falta que hagas nada).
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={onClose} style={{ padding: '8px 16px' }}>Cerrar</button>
            </div>
          </>
        ) : (
          <>
            {off.length === 0 ? (
              <div className={styles.alertSuccess}>Todas las funciones DevOps ya están activas.</div>
            ) : (
              <>
                <p>Se van a <strong>activar {off.length}</strong> funciones:</p>
                <ul style={{ listStyle: 'none', padding: 0 }}>
                  {off.map((f) => (
                    <li key={f.key} style={{ borderBottom: '1px solid var(--border-muted)', padding: '6px 0' }}>
                      <strong>{f.label}</strong>{' '}
                      <span className={styles.textMuted} style={{ fontSize: '0.8em' }}>[{f.risk}]</span>
                      {f.what && <div style={{ fontSize: '0.85em', opacity: 0.85 }}>{f.what}</div>}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {on.length > 0 && (
              <p className={styles.textMuted} style={{ fontSize: '0.85em' }}>
                Ya activas (no se tocan): {on.map((f) => f.label).join(', ')}.
              </p>
            )}
            {off.length > 0 && (
              <label style={{ display: 'flex', gap: '8px', alignItems: 'start', margin: '12px 0' }}>
                <input type="checkbox" checked={confirmChecked} onChange={(e) => setConfirmChecked(e.target.checked)} disabled={activating} />
                <span style={{ fontSize: '0.9em' }}>Confirmo activar estas {off.length} funciones DevOps.</span>
              </label>
            )}
            {error && <div className={styles.alertError} style={{ fontSize: '0.85em' }}>{error}</div>}
            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
              <button onClick={onClose} disabled={activating} style={{ padding: '8px 16px' }}>Cancelar</button>
              {off.length > 0 && (
                <button onClick={() => void handleActivate()} disabled={!confirmChecked || activating} className={styles.btnSuccess}>
                  {activating ? 'Activando…' : `Activar ${off.length}`}
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};
```

**Casos borde fijados:** 0 flags OFF ⇒ mensaje "todas activas" + sin checkbox ni botón
de activar (idempotencia visible); confirm obligatorio (botón disabled sin él); error
del PUT ⇒ visible, sin cerrar; tras éxito ⇒ `onDone()` refetchea el health del shell
(las secciones se desgatean solas).

**Tests PRIMERO (TDD)** — casos 2-4 de `DevOpsSuite.test.ts` (greps de integración,
estilo de la casa):

2. `el modal solo envía las flags OFF` — el fuente contiene `bundle.filter((f) => !f.enabled)`
   y `HarnessFlags.update(updates)`.
3. `el modal exige confirm` — el fuente contiene `!confirmChecked` en el guard de
   `handleActivate` y `disabled={!confirmChecked || activating}`.
4. `el modal lista las ya activas sin re-enviarlas` — el fuente contiene
   `bundle.filter((f) => f.enabled)` usado SOLO para mostrar (no aparece en `updates`).

**Comandos:**

```
npx vitest run src/pages/__tests__/DevOpsSuite.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** tests 2-4 verdes + `tsc` 0 errores.
**Flag:** ninguna (§3.1). **Impacto por runtime:** NINGUNO. Fallback: si el operador
prefiere, `FlagGateBanner` por-sección sigue existiendo intacto.
**Trabajo del operador:** ninguno (reduce clicks).

---

## F3 — Botón "Activar suite DevOps" en el shell (`DevOpsPage`)

**Objetivo:** montar el disparador del modal en la barra del panel, visible cuando al
menos una flag del paquete está OFF.
**Valor:** el punto de entrada visible; no molesta cuando ya está todo activo.

**Archivo a editar:** `Stacky Agents/frontend/src/pages/DevOpsPage.tsx`

1. Query nueva (react-query, junto a `healthQuery`/`serversQuery`,
   `DevOpsPage.tsx:112-129`):

```ts
  const bundleQuery = useQuery({
    queryKey: ['devops-flag-bundle'],
    queryFn: () => DevOps.flagBundle(),
    retry: false,
  });
  const [showSuiteModal, setShowSuiteModal] = useState(false);
  const bundle = bundleQuery.data?.flags ?? [];
  const anyOff = bundle.some((f) => !f.enabled);
```

2. Import: `ActivateSuiteModal` desde
   `'../components/devops/ActivateSuiteModal'` y `DevOps` ya está importado.

3. En la barra de sub-tabs (`DevOpsPage.tsx:172-206`), agregar el botón al final de la
   fila (ADITIVO; el `flexWrap` ya existe):

```tsx
        {anyOff && (
          <button
            onClick={() => setShowSuiteModal(true)}
            className={styles.btnSuccess}   /* usa devops.module.css importado en el shell */
            style={{ padding: '8px 16px', marginLeft: 'auto' }}
            title="Activar en un paso todas las funciones DevOps que están apagadas"
          >
            Activar suite DevOps
          </button>
        )}
```

   (si el selector de servidores ya usa `marginLeft: 'auto'`, poner el botón ANTES de
   ese select para no competir por el margen — regla determinista: el botón va
   inmediatamente después del `.map` de sub-tabs y antes del bloque
   `servers_enabled === true`).

4. Render del modal (al final del `return`, junto al resto):

```tsx
      {showSuiteModal && (
        <ActivateSuiteModal
          bundle={bundle}
          onDone={() => { void healthQuery.refetch(); void bundleQuery.refetch(); }}
          onClose={() => setShowSuiteModal(false)}
        />
      )}
```

   `DevOpsPage.tsx` no importa `styles` hoy; agregar
   `import styles from '../components/devops/devops.module.css';` (el CSS module ya
   existe y lo usan las secciones).

**Nota de estilo:** hoy los botones de sub-tab usan estilos inline (`DevOpsPage.tsx:178-186`).
El botón suite usa `styles.btnSuccess` para diferenciarse visualmente (acción, no tab).
No se refactoriza el resto de la barra (fuera de scope).

**Tests PRIMERO (TDD)** — casos 5-6 de `DevOpsSuite.test.ts`:

5. `el shell arma la query del bundle y el botón condicional` — el fuente de
   `DevOpsPage.tsx` contiene `'devops-flag-bundle'` y `anyOff` y `Activar suite DevOps`.
6. `el shell monta el modal con onDone que refetchea health` — el fuente contiene
   `ActivateSuiteModal` y `healthQuery.refetch()` dentro de `onDone`.

**Comandos:**

```
npx vitest run src/pages/__tests__/DevOpsSuite.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** tests 5-6 verdes + `tsc` 0 errores + los vitest
preexistentes del panel (`DevOpsPage.test.ts`, `ServersSection.test.ts`) verdes sin
modificarlos.
**Flag:** ninguna. **Impacto por runtime:** NINGUNO. **Trabajo del operador:** ninguno.

---

## F4 — Primer paso inline (a): cargar el catálogo de procesos sin salir de Publicaciones

**Objetivo:** cuando el catálogo está vacío, ofrecer cargar entradas mínimas
directamente en `PublicationsSection` en vez de mandar al operador a otra pantalla.
**Valor:** elimina la navegación forzada del onboarding de publicaciones.

**Archivo a editar:**
`Stacky Agents/frontend/src/components/devops/PublicationsSection.tsx`

Hoy el catálogo vacío muestra solo un aviso que redirige
(`PublicationsSection.tsx:224-228`). Se agrega, DENTRO de ese bloque, un mini-editor
inline que agrega una entrada `{name, kind, publish_group}` al `process_catalog` y lo
persiste por el MISMO riel de escritura del profile ya usado en la sección (o, si el
Plan 98 estuviera implementado, por `saveProfileKey('process_catalog', ...)` — pero
como el 98 es PROPUESTO, este plan usa el riel GET→merge→PUT existente para no acoplar):

```tsx
  // Plan 100 F4 — alta inline de catálogo (evita mandar a otra pantalla).
  const [newProc, setNewProc] = useState<{ name: string; kind: string; publish_group: string }>(
    { name: '', kind: 'processing', publish_group: 'batch' });

  const handleAddCatalogEntry = async () => {
    if (!activeProject || !newProc.name.trim()) return;
    try {
      setActionError(null);
      const json = await api.get<{ profile?: Record<string, unknown> }>(`/api/projects/${activeProject}/client-profile`);
      const base = json.profile ?? {};
      const cat = Array.isArray(base.process_catalog) ? (base.process_catalog as CatalogEntry[]) : [];
      const next = [...cat, { name: newProc.name.trim(), kind: newProc.kind, publish_group: newProc.publish_group }];
      const merged = mergeKeysIntoProfile(base, { process_catalog: next });
      await api.put(`/api/projects/${activeProject}/client-profile`, { profile: merged });
      setCatalog(next);
      setNewProc({ name: '', kind: 'processing', publish_group: 'batch' });
    } catch (e: unknown) {
      setActionError(`No se pudo agregar al catálogo: ${e instanceof Error ? e.message : 'error'}`);
    }
  };
```

y el bloque de aviso (`:224-228`) pasa a incluir el mini-form (input `name` +
`<select>` de `kind` limitado a la allowlist ya validada por el backend
`api/client_profile.py:141-159`, `entry`/`processing`/`output` + `default`, +
`<select>` de `publish_group` `batch`/`agenda`) y un botón "Agregar al catálogo". El
aviso de "cargalo en Configuración → Perfil del cliente" se conserva como alternativa
(no se elimina el camino existente).

**Casos borde fijados:** `kind`/`publish_group` restringidos por `<select>` a las
allowlists del backend (nunca 400 por valor inválido); nombre vacío ⇒ botón inactivo;
tras agregar, el catálogo deja de estar vacío y el resto de la sección (materializar)
se habilita solo.

**Tests PRIMERO (TDD)** — casos 7-8 de `DevOpsSuite.test.ts`:

7. `Publicaciones ofrece alta inline de catálogo` — el fuente de
   `PublicationsSection.tsx` contiene `handleAddCatalogEntry` y `process_catalog`.
8. `el select de kind usa la allowlist del backend` — el fuente contiene los 4 valores
   `entry`, `processing`, `output`, `default` en el bloque de alta inline.

**Comandos:**

```
npx vitest run src/pages/__tests__/DevOpsSuite.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** tests 7-8 verdes + `tsc` 0 errores.
**Flag:** ninguna (vive dentro de la sección ya gateada por `publications_enabled`).
**Impacto por runtime:** NINGUNO. **Trabajo del operador:** ninguno (reduce navegación).

---

## F5 — Primer paso inline (b): preset `todo-completo` automático cuando falta

**Objetivo:** garantizar que exista un preset `todo-completo` de un click cuando no hay
ninguno, reusando el patrón del 97/88.
**Valor:** tras cargar el catálogo, el operador materializa/publica sin armar el preset
a mano.

**Estado del arte (verificado):** `PublicationsSection` YA tiene
`handleCreateTodoPreset` (`PublicationsSection.tsx:127-132`) y un botón "Crear preset
TODO" (`:237-243`, `:262-264`). Este paso NO duplica esa lógica: **eleva la
visibilidad** del CTA cuando la lista está vacía Y el catálogo NO está vacío (el momento
en que crear el preset todo tiene sentido), y NADA MÁS. Es un cambio de copy/orden, no
lógica nueva.

**Archivo a editar:** `PublicationsSection.tsx` — en el bloque de lista de presets
vacía (`:234-244`), cuando `presets.length === 0 && !catalogEmpty`, el CTA "Crear
preset TODO" pasa a mostrar una línea guía: "Tu catálogo tiene procesos pero no hay
preset — creá 'todo-completo' para publicarlos todos". Reusa `handleCreateTodoPreset`
existente (cero lógica nueva).

**Tests PRIMERO (TDD)** — caso 9 de `DevOpsSuite.test.ts`:

9. `el CTA de preset todo se guía por catálogo no vacío` — el fuente de
   `PublicationsSection.tsx` contiene `todo-completo` y usa `catalogEmpty` para el copy
   guía (grep de la nueva línea de texto + `handleCreateTodoPreset` reusado, sin una
   segunda definición).

**Comandos:**

```
npx vitest run src/pages/__tests__/DevOpsSuite.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** test 9 verde + `tsc` 0 errores + `handleCreateTodoPreset`
sigue con UNA sola definición (grep negativo de duplicado).
**Flag:** ninguna. **Impacto por runtime:** NINGUNO. **Trabajo del operador:** ninguno.

---

## F6 — Cierre: ratchet, verificación manual HITL y checklist binario

**Objetivo:** registrar el test backend en el ratchet, verificar end-to-end y dejar el
checklist auditable.

**Archivos a editar:**
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` y `.sh` — agregar a
  `HARNESS_TEST_FILES`:

```
  "tests/test_plan100_flag_bundle_endpoint.py",
```

(Es el ÚNICO test backend nuevo; los demás son vitest, que no van al ratchet — §3 del
Plan 49.)

**Verificación manual (HITL, con la app corriendo, partiendo de flags devops OFF):**
1. Abrir el panel con TODAS las flags devops OFF ⇒ el botón "Activar suite DevOps"
   aparece; abrir el modal ⇒ lista las N flags OFF con su ayuda llana y riesgo, sin
   checkbox marcado; el botón "Activar" está deshabilitado.
2. Marcar el confirm + "Activar" ⇒ un solo PUT a `/api/harness-flags` (Network) con
   todas las OFF en `updates`; el panel se refresca y las secciones se desgatan; el
   modal muestra "Suite activada".
3. Reabrir el modal ⇒ "Todas las funciones DevOps ya están activas" (idempotencia); el
   botón del shell ya NO aparece (`anyOff` false).
4. En Publicaciones con catálogo vacío ⇒ alta inline agrega una entrada sin navegar;
   luego el CTA guía a crear `todo-completo`.
5. Verificar el drift documentado: tras activar, `git status` muestra `.env` del deploy
   tocado (esperado) pero `harness_defaults.env` del repo SIN cambios por el botón
   (postura §3.6); el comando de sync del repo queda para el mantenedor.

**Checklist binario:**
- [ ] `GET /api/devops/flag-bundle` 200 siempre, incluye toda la categoría devops + las
      2 de pipeline, `enabled` refleja el estado real, orden topológico por `requires`
      (`test_plan100_flag_bundle_endpoint.py` 6/6).
- [ ] El botón "Activar suite DevOps" aparece SOLO si hay ≥1 flag OFF; el modal activa
      SOLO las OFF en un único PUT, exige confirm, lista las ON sin re-enviarlas
      (`DevOpsSuite.test.ts` 2-6).
- [ ] Idempotencia: 0 OFF ⇒ modal informa "todas activas", sin activar nada.
- [ ] Alta inline de catálogo en Publicaciones + CTA guiado de preset todo
      (`DevOpsSuite.test.ts` 7-9); `handleCreateTodoPreset` con UNA definición.
- [ ] Cero `FlagSpec` nueva; `FLAG_REGISTRY`, `_CATEGORY_KEYS`, `_REQUIRES_MAP_FROZEN`
      intactos; `HarnessFlagsPanel` sin tocar.
- [ ] El botón NO regenera `harness_defaults.env` ni escribe `config.py`/`.env` por su
      cuenta (solo vía `HarnessFlags.update`); postura del drift documentada y NO
      agravada respecto de activar a mano.
- [ ] `tsc --noEmit` 0 errores; vitest por archivo verdes; test backend registrado en
      ambos ratchets.
- [ ] `FlagGateBanner` y el flujo por-sección intactos (backward-compatible).

**Trabajo del operador:** ninguno (el plan reduce trabajo: 6 clicks → 2 + onboarding
sin navegación).

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El botón activa una flag "de acción" (AGENT lanza CLIs, TRIGGER dispara pipelines) que el operador no quería encender aún | El modal LISTA cada flag con su riesgo (`panel-base`/`accion`/`servidores`) y su efecto llano ANTES de activar; requiere confirm explícito. NO hay activación silenciosa. Si quiere granularidad, `FlagGateBanner` por-sección sigue disponible. |
| Drift de `harness_defaults.env` tras activar (el problema documentado hoy) | Postura §3.6: el botón NO agrava el drift (hace lo mismo que activar a mano: escribe el `.env` del deploy). El snapshot versionado es artefacto de BUILD (`export_harness_defaults.py`), se regenera al generar deploy; el modal lo avisa en llano y el doc deja el comando de sync para el mantenedor del repo. |
| La lista del paquete queda desactualizada si se agrega una flag devops futura | Imposible: F0 deriva la lista de `_CATEGORY_KEYS["devops"]` + las 2 de pipeline en runtime; una flag devops nueva entra sola (test 2). |
| Orden `requires` incorrecto haría fallar la activación de un dependiente antes que su dependencia | `_topo_by_requires` (F0) ordena dependencias primero (Kahn, R4 garantiza acyclic); además el endpoint aplica todo el `updates` en una llamada. Test 5 fija el orden. |
| El accessor de ayuda llana (`get_plain_help`) podría no llamarse así en `harness_flags_help.py` | Nota de investigación en F0: el implementador verifica el nombre real; degradación defensiva a `""` si no hay accessor — el endpoint NUNCA rompe por falta de ayuda. |
| Alta inline de catálogo con `kind`/`publish_group` inválido ⇒ 400 del PUT | Los `<select>` limitan a las allowlists exactas del backend (`api/client_profile.py:141-165`); imposible mandar un valor inválido desde la UI. |
| Doble escritura del profile (F4) colisiona con el Plan 98 (PATCH) si ambos se implementan | F4 usa el riel GET→merge→PUT existente (no acopla al 98 PROPUESTO); si el 98 se implementa después, F4 migra a `saveProfileKey('process_catalog', ...)` en ese plan — declarado en Fuera de scope. |
| `DevOpsPage.tsx` importa `styles` por primera vez y rompe algo | Import ADITIVO del CSS module que YA existe y usan las secciones; `tsc` valida; el resto de la barra (estilos inline) no se toca. |

## 6. Fuera de scope (v1)

- Regenerar `harness_defaults.env` desde el botón (postura §3.6: es artefacto de build,
  no de runtime).
- Un "desactivar suite" en lote (apagar flags) — v1 solo activa; apagar de a una sigue
  por `HarnessFlagsPanel`.
- Perfiles de arnés (off/safe/full) del endpoint `/api/harness-flags/profile`
  (`api/harness_flags.py:87`) — este plan es específico del paquete devops, no toca
  perfiles globales.
- Editor de catálogo completo inline (CRUD, edición, borrado): F4 solo agrega altas
  mínimas; el editor completo sigue en Configuración → Perfil del cliente.
- Migrar la escritura del catálogo al PATCH del Plan 98 (se hará en ese plan si se
  implementa; aquí se usa el riel existente para no acoplar a un plan PROPUESTO).
- Refactor de los botones de sub-tab del shell a clases CSS (siguen inline; solo el
  botón suite usa `styles.btnSuccess`).
- Tocar las flags NO-devops o el `HarnessFlagsPanel` genérico.

## 7. Glosario

- **Suite DevOps / paquete de flags:** el conjunto de flags de la categoría `devops`
  (`harness_flags.py:177-184`) + las 2 de pipeline (generador/trigger) que el panel
  consume; lo que el botón activa en lote.
- **Activación en lote HITL:** activar varias flags en un solo PUT tras un único
  confirm del operador, listando antes qué se activa y qué ya está ON.
- **`requires` (Plan 82):** relación declarativa "esta flag necesita aquella"; profund.
  1 (R4). El botón activa en orden topológico (dependencias primero).
- **`HarnessFlags.update`:** el ÚNICO escritor de flags del arnés
  (`endpoints.ts:865` → `api/harness_flags.py:117`); persiste al `.env` y hot-aplica.
- **`PlainHelp` (Plan 86):** ayuda en llano por flag (what/on_effect/off_effect/example)
  que el modal muestra para que el operador entienda qué activa.
- **`harness_defaults.env`:** snapshot VERSIONADO del arnés que el build hornea como
  default del deploy (`export_harness_defaults.py`); NO lo escribe la UI en runtime.
- **Drift de defaults:** divergencia entre el estado local de flags del operador y el
  snapshot versionado del repo; se resuelve con `export_harness_defaults.py` al generar
  deploy o al mantener el repo, no desde el botón.
- **Preset `todo-completo`:** preset de publicación en modo `todo` que abarca todo el
  catálogo (patrón del 88/97); F5 solo eleva su CTA cuando corresponde.
- **Primer paso inline:** acción de onboarding (cargar catálogo, crear preset) resuelta
  DENTRO de la sección, sin mandar al operador a otra pantalla.

## 8. Orden de implementación

1. F0 — endpoint `GET /api/devops/flag-bundle` + helpers `_topo_by_requires`/`_bundle_risk`
   + 6 tests backend.
2. F1 — `DevOps.flagBundle` + tipo en `endpoints.ts` + test 1.
3. F2 — `ActivateSuiteModal.tsx` + tests 2-4 (necesita F1).
4. F3 — botón + query + modal en `DevOpsPage.tsx` + tests 5-6 (necesita F2).
5. F4 — alta inline de catálogo en `PublicationsSection.tsx` + tests 7-8 (independiente
   de F0-F3; puede ir en paralelo).
6. F5 — CTA guiado del preset todo en `PublicationsSection.tsx` + test 9 (tras F4:
   comparten sección).
7. F6 — ratchet (sh+ps1) + verificación manual HITL + checklist binario.

## 9. Definición de Hecho (DoD)

- F0: 6 tests verdes (`test_plan100_flag_bundle_endpoint.py`) + `test_harness_flags.py`
  verde; el registry/categorías/requires NO se tocaron.
- F1: test 1 verde + `tsc` 0 errores.
- F2: tests 2-4 verdes + `tsc` 0 errores; el modal es HITL (confirm) e idempotente
  (solo OFF).
- F3: tests 5-6 verdes + `tsc` 0 errores + vitest preexistentes del panel verdes sin
  modificar; el botón aparece SOLO con ≥1 flag OFF.
- F4: tests 7-8 verdes + `tsc` 0 errores; alta inline con `<select>` de allowlist.
- F5: test 9 verde + `tsc` 0 errores; `handleCreateTodoPreset` con una sola definición.
- F6: 1 test backend registrado en ambos ratchets; verificación manual HITL de los 5
  pasos anotada en el reporte (Network: un solo PUT en lote, idempotencia, drift no
  agravado).
- Global: cero `FlagSpec` nueva; cero bypass del sistema de flags (todo vía
  `HarnessFlags.update`); HITL en el modal (nada se activa sin confirm); postura del
  drift de `harness_defaults.env` explícita y respetada; `FlagGateBanner` intacto.
- Impacto en los 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro):
  NINGUNO — solo frontend + un endpoint de lectura; verificable por grep de
  `flag-bundle|ActivateSuiteModal` fuera de `frontend/` + `api/` + `tests/`.
