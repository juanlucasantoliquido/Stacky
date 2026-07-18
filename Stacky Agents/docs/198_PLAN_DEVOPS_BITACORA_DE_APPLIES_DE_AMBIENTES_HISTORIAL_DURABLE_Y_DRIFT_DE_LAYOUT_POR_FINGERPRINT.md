# Plan 198 — DevOps: bitácora de applies de ambientes — historial durable y drift de layout por fingerprint

- **Versión:** v1 (PROPUESTO)
- **Fecha:** 2026-07-18
- **Autor:** StackyArchitectaUltraEficientCode (pipeline proponer-plan-stacky)
- **Serie:** DevOps (cierra la tríada de efectos remotos con registro: deploys 120 ✓, CI 191 ✓, applies de ambientes ← este; se SUMA a la ruta 195)

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** `POST /devops/environments/apply` (`api/devops.py:271-313`, planes 89/107/
108) **crea carpetas en disco local o en un servidor remoto** con el HITL más fuerte de la casa
(`confirm=True` :278, `fingerprint` del plan visto :285-293, `sandbox_ack` :281-284) — y sin embargo
**no deja NINGÚN registro durable**: la respuesta se muestra y se evapora. Es el único efecto
remoto/mutante del ecosistema sin bitácora (los deploys 120 tienen ledger; los triggers CI la
tendrán con el 191). Este plan la agrega con la MISMA receta ya criticada y congelada del 191
(JSONL + lock + allowlist + retención + hook best-effort que JAMÁS rompe la ruta) y suma una
capacidad NUEVA que solo este dominio permite: como cada apply registra el `fingerprint` del layout
aplicado (que la ruta YA calcula, `layout_fingerprint` :291), el historial puede responder
**"¿el layout cambió desde mi último apply?"** comparando fingerprints — drift de estructura de
carpetas detectado con una igualdad de strings, sin tocar el disco remoto.

**KPI / impacto esperado (binarios, verificados por tests):**

| KPI | Criterio binario |
|-----|------------------|
| KPI-1 | Apply exitoso (local y remoto fake) con flag ON → 1 entry con los campos EXACTOS del contrato; apply FALLIDO remoto → 1 entry con `result_ok: false`; `append_apply` que lanza → la respuesta HTTP del apply es IDÉNTICA (best-effort probado) |
| KPI-2 | ALLOWLIST estricta: un entry con clave extra (`password`) la DESCARTA; `paths` se capea a 200 items con `paths_truncated: true` |
| KPI-3 | Drift correcto: fingerprint del último apply == actual → `layout_drift: false`; distinto → `true`; sin applies previos → `null` |
| KPI-4 | Retención y orden: tras 301 appends quedan 300; `list_applies` sale DESC por `applied_at` (sort explícito, no orden de archivo) |
| KPI-5 | UI pura: helpers de fila/badge/drift testeados en vitest y `npx tsc --noEmit` sin errores nuevos |

**Ganancia robusta:** auditoría completa de la acción más delicada de Ambientes (mutación de
filesystem, a veces remota) + detección pasiva de "alguien tocó las carpetas después de mí".

**Onboarding casi nulo:** el historial aparece solo dentro de la sección Ambientes existente; el
badge de drift se explica solo.

---

## 2. Por qué ahora / gap que cierra

Evidencia del estado actual (verificada en el repo):

- `api/devops.py:271-313` — `environment_apply_route`: HITL triple (confirm :278, fingerprint
  :285-293 con 409 `plan_stale`, sandbox_ack :281-284), rama local (`apply_environment` :310) y
  rama remota (`apply_environment_remote` :306, plan 108) con early-return de error remoto
  (:307-308). **Cero persistencia en ambas ramas.**
- `api/devops.py:291` — `layout_fingerprint(root, rel_paths)` YA se computa en cada apply: el
  ingrediente del drift es gratis.
- `services/ci_run_ledger.py` NO existe aún (plan 191 CRITICADO v2, sin implementar) — la RECETA
  del ledger (JSONL + `_LOCK` + tmp+replace + ALLOWLIST + MAX_ROWS + sort explícito + tolerancia a
  líneas corruptas) quedó CONGELADA en el doc del 191 F0 y este plan la REPLICA con otros campos.
  Si el 191 ya se implementó al llegar acá, ESPEJAR su código real en vez del doc.
- `frontend/src/components/devops/EnvironmentsSection.tsx` — la sección de Ambientes existente
  (verificada por glob en `components/devops/`).
- Ruta 195 (§5): este plan se SUMA a la serie — grupo B (toca `api/devops.py`, va DESPUÉS del 186
  que edita el mismo archivo); al implementarlo, agregar la fila correspondiente en §5/§8 del 195.
- Vecinos que NO se pisan: 89/107/108 (este plan NO cambia su semántica: solo observa), 120
  (deploys, otro dominio), 178 (drift de BD — esto es drift de CARPETAS por fingerprint),
  191 (CI — misma receta, otro dominio), 197 (ruta UX de la paralela).

**Gap:** la tríada de efectos con mutación queda 3/3 con registro durable, y Ambientes gana la
pregunta que ningún otro plan responde: "¿mi layout sigue como lo dejé?".

---

## 3. Principios y guardarraíles (no negociables)

1. **3 runtimes con paridad total por construcción:** backend + UI, cero LLM.
2. **Cero trabajo extra para el operador:** flag default **ON** (ninguna excepción dura: la
   bitácora es metadata local de acciones que el operador YA confirmó con el HITL triple; leerla
   es local; el drift es una comparación de strings).
3. **Human-in-the-loop:** nada nuevo que confirmar — este plan NO agrega acciones; "Replanificar"
   solo precarga el flujo `/plan` existente.
4. **Mono-operador sin auth:** nada de roles.
5. **No degradar:** hook best-effort (try/except + `stacky_logger`); el apply responde IDÉNTICO
   con ledger roto/lleno/read-only. Las 3 guardas HITL (:278/:285/:281) quedan intactas byte a
   byte.
6. **Reusar, no reinventar:** receta de ledger del 191 (o su código real si ya existe),
   `layout_fingerprint` existente, guard-pattern `_config.config` (devops.py:251), sección UI
   existente.
7. **Gotchas de la casa:** curated ON, edge en `test_harness_flags_requires.py`, registro en
   `HARNESS_TEST_FILES`, tests POR ARCHIVO (reload de config), ratchet UI sin `style={{}}`,
   criterio NO-EMPEORAR para `ratchet_meta` (rojo preexistente — plan 193 C2 / gate 0 de la 195).

---

## 4. Fases

### F0 — Flag + ledger + endpoint de consulta con drift

**Objetivo:** bitácora durable + lectura con drift computado, verificable sin tocar el apply aún.
**Valor:** sustrato completo; F1 solo enchufa el productor.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/harness_flags.py`
- CREAR `Stacky Agents/backend/services/env_apply_ledger.py`
- EDITAR `Stacky Agents/backend/api/devops.py`
- EDITAR `Stacky Agents/backend/tests/test_harness_flags_requires.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh`
- CREAR `Stacky Agents/backend/tests/test_plan198_env_ledger.py`

**Cambios exactos:**

1. `harness_flags.py` — FlagSpec al final del bloque DEVOPS (~:2743; tras el último de la serie ya
   mergeado — gate anti-duplicado de la ruta 195 aplica):

```python
FlagSpec(
    key="STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED",
    type="bool",
    label="Bitácora de applies de ambientes",
    description="Registra localmente cada apply de carpetas (local o remoto): qué se creó, "
                "dónde, con qué fingerprint y resultado — y avisa si el layout cambió desde "
                "el último apply. Solo metadata local; sin contenido de archivos.",
    group="global",
    default=True,
    requires="STACKY_DEVOPS_PANEL_ENABLED",  # R4 profundidad-1 (patrón :2674)
),
```

2. Key a `_CURATED_DEFAULTS_ON` (~:200-216, comentario `# Plan 198 — bitácora de applies de
   ambientes`). Edge `STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED → STACKY_DEVOPS_PANEL_ENABLED` en
   `tests/test_harness_flags_requires.py`.

3. CREAR `services/env_apply_ledger.py` — RECETA CONGELADA del 191 F0 con estos parámetros:
   - Archivo: `data_dir()/env_applies.jsonl`. `MAX_ROWS = 300`. `_LOCK = threading.Lock()`.
   - `ENTRY_FIELDS = ("root", "server_alias", "paths", "paths_truncated", "fingerprint",
     "sandbox_active", "result_ok", "created_count", "applied_at", "source")` — ALLOWLIST: claves
     fuera de la lista se DESCARTAN (jamás un secreto por accidente).
   - `append_apply(entry: dict) -> None`: normaliza `paths` a lista de str CAP 200 items
     (`paths_truncated=True` si se cortó); `applied_at` default `datetime.now(timezone.utc)
     .isoformat()`; `source="stacky"`; retención en el mismo write (tmp + `Path.replace`).
   - `list_applies(root: str | None = None, server_alias: str | None = None, limit: int = 20)
     -> list[dict]`: filtros de igualdad exacta cuando vienen; SORT DESC por `applied_at`
     (nunca orden de archivo); `limit` clamp [1, MAX_ROWS]; tolera líneas corruptas (las saltea).
   - `last_fingerprint(root: str, server_alias: str | None) -> str | None`: fingerprint del apply
     más reciente para ese (root, server_alias); `None` sin historial.
   - PURO: cero imports de red/providers/`environment_remote`.

4. `api/devops.py` — endpoint de consulta DESPUÉS de `environment_apply_route` (:313). POST
   read-only (precedente en el MISMO archivo: `/environments/plan` :247 es POST read-only porque
   necesita el contexto del body):

```python
@bp.post("/environments/applies")
def environment_applies_route():
    """Historial de applies + drift de layout por fingerprint. Read-only. Plan 198."""
    if not getattr(_config.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False):
        abort(404)
    if not getattr(_config.config, "STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED", False):
        abort(404)
    body = request.get_json(silent=True) or {}
    ctx, err = _load_env_context(body)      # MISMO helper que /plan y /apply (:253, :288)
    if err: return err
    root, rel_paths, sandbox_active, server_alias = ctx
    from services.env_apply_ledger import list_applies, last_fingerprint
    current_fp = layout_fingerprint(root, rel_paths)      # mismo símbolo que :291
    last_fp = last_fingerprint(root, server_alias)
    return jsonify({
        "applies": list_applies(root=root, server_alias=server_alias, limit=20),
        "current_fingerprint": current_fp,
        "last_applied_fingerprint": last_fp,
        "layout_drift": (None if last_fp is None else (last_fp != current_fp)),
        "sandbox_active": sandbox_active,
    })
```

5. `test_plan198_env_ledger.py` a `HARNESS_TEST_FILES` (**gotcha** meta-test).

**Tests PRIMERO** — `tests/test_plan198_env_ledger.py` (ledger en `tmp_path` monkeypatcheando
`runtime_paths.data_dir`; para el endpoint, monkeypatch de `_load_env_context` y
`layout_fingerprint` — espejar el estilo de los tests EXISTENTES de environments: correr
`ls tests/ | grep -iE "plan89|plan107|plan108|environment"` y leer el que testee `/environments/plan`):
- `test_flag_declarada_bool_default_on` + `test_flag_en_curated_defaults_on`.
- `test_endpoint_404_ledger_off` (environments ON, ledger OFF) y `test_endpoint_404_environments_off`.
- `test_kpi2_allowlist_y_cap_paths` — entry con `password` y 250 paths → clave descartada, 200
  paths, `paths_truncated is True`.
- `test_kpi4_retencion_y_orden` — 301 appends → 300; 3 sembrados en desorden de archivo → DESC
  por `applied_at` (prueba el SORT).
- `test_kpi3_drift_true_false_null` — last==current → `layout_drift is False`; distinto → `True`;
  ledger vacío → `None`.
- `test_lineas_corruptas_no_rompen`.
- `test_filtro_root_y_server` — entries de 2 roots/2 servers → filtros exactos.

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan198_env_ledger.py -q`
(cwd = `Stacky Agents\backend`; POR ARCHIVO; si la ruta 195 Gate 0 creó `venv313`, usar ese
intérprete y anotarlo).

**Criterio binario:** los 9 tests pasan; `ratchet_meta` bajo criterio NO-EMPEORAR (195 Gate 0).

**Flag:** `STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED` default **ON** (ninguna excepción dura).

**Runtimes:** idéntico en los 3. Fallback: cualquiera de las 2 flags OFF → 404 y la UI no muestra
el historial.

**Trabajo del operador:** ninguno.

---

### F1 — Productor: hook best-effort en `environment_apply_route` (AMBAS ramas, incluidos fallos)

**Objetivo:** que cada apply — exitoso O fallido, local O remoto — se registre solo.
**Valor:** auditoría completa sin cambiar ningún hábito.

**Archivos:**
- EDITAR `Stacky Agents/backend/api/devops.py`
- CREAR `Stacky Agents/backend/tests/test_plan198_env_hook.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` (registrar el test)

**Cambios exactos:**

1. Definir UN helper local en `api/devops.py` (arriba de la ruta) y llamarlo desde los TRES puntos
   de salida del apply — el early-return de error remoto (:307-308), el camino remoto exitoso y el
   camino local (:310) — SIEMPRE antes del `return`:

```python
def _record_env_apply(root, server_alias, approved, fingerprint, sandbox_active, result):
    """Plan 198 — best-effort: JAMÁS rompe el apply."""
    if not getattr(_config.config, "STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED", False):
        return
    try:
        from services.env_apply_ledger import append_apply
        append_apply({
            "root": str(root),
            "server_alias": server_alias,          # None = local
            "paths": list(approved),
            "fingerprint": fingerprint,
            "sandbox_active": bool(sandbox_active),
            "result_ok": bool(result.get("ok", True)) if isinstance(result, dict) else False,
            "created_count": len(result.get("created", []) or []) if isinstance(result, dict) else 0,
        })
    except Exception:
        from services.stacky_logger import logger as stacky_logger
        stacky_logger.info("env_apply_ledger", "append_failed", root=str(root))
```

   Regla dura: la clave del conteo de creadas (`result.get("created")`) se toma LEYENDO el shape
   real que devuelven `apply_environment` y `apply_environment_remote` — si la clave difiere
   (p.ej. `created_paths`), usar la real; si no existe, `created_count = 0`.

2. Los early-returns de validación HITL (:278-296, confirm/sandbox_ack/fingerprint/paths) NO
   registran nada (no hubo intento de mutación).

**Tests PRIMERO** — `tests/test_plan198_env_hook.py` (Flask test client; `apply_environment` y
`apply_environment_remote` monkeypatcheados; contexto y fingerprint monkeypatcheados igual que F0):
- `test_kpi1_apply_local_ok_persiste` — entry con `server_alias None`, `result_ok True`,
  `created_count` correcto.
- `test_kpi1_apply_remoto_ok_persiste` — `server_alias` seteado.
- `test_kpi1_apply_remoto_fallido_persiste` — remoto devuelve `{"ok": False, ...}` → entry con
  `result_ok False` Y la respuesta HTTP mantiene su status de error original.
- `test_kpi1_append_roto_no_rompe_apply` — `append_apply` → raise → respuesta IDÉNTICA byte a
  byte a la del caso sin excepción.
- `test_validaciones_hitl_no_registran` — sin `confirm` → 400 y 0 entries.
- `test_hitl_intacto` — las 3 guardas (confirm/fingerprint 409 plan_stale/sandbox_ack) responden
  EXACTAMENTE igual que antes (guardia de no-regresión).

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan198_env_hook.py -q`

**Criterio binario:** los 6 tests pasan (KPI-1 completo).

**Flag:** la de F0 (+ environments). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F2 — UI: historial en la sección Ambientes + badge de drift

**Objetivo:** ver los applies y el drift donde ya se opera, con replanificación en 1 click.
**Valor:** cierre del ciclo.

**Archivos:**
- CREAR `Stacky Agents/frontend/src/components/devops/envApplyLedger.ts` (helpers puros)
- CREAR `Stacky Agents/frontend/src/components/devops/envApplyLedger.test.ts`
- EDITAR `Stacky Agents/frontend/src/components/devops/EnvironmentsSection.tsx`

**Comportamiento exacto:**

1. `envApplyLedger.ts` (puro):

```typescript
export interface EnvApply {
  root: string; server_alias: string | null; paths: string[]; paths_truncated?: boolean;
  fingerprint: string; sandbox_active: boolean; result_ok: boolean;
  created_count: number; applied_at: string; source: string;
}
export function applyRow(a: EnvApply): string {
  const where = a.server_alias ?? 'Local';
  const ok = a.result_ok ? 'OK' : 'FALLÓ';
  return `${a.applied_at} · ${where} · ${a.created_count} creadas · ${ok}`;
}
export function driftBadge(drift: boolean | null): { tone: 'ok'|'warn'|'none'; text: string } {
  if (drift === null) return { tone: 'none', text: '' };
  return drift
    ? { tone: 'warn', text: 'El layout cambió desde el último apply' }
    : { tone: 'ok', text: 'Layout igual al último apply' };
}
```

2. `EnvironmentsSection.tsx`: tras el bloque del plan/apply existente, un `<details>` "Últimos
   applies" que al abrirse hace `POST /api/devops/environments/applies` con el MISMO body de
   contexto que la sección ya arma para `/plan` (localizar por lectura el fetch a
   `environments/plan` y reusar su payload); 404 → no renderizar nada (flags OFF); render: badge
   `driftBadge(layout_drift)` arriba + filas `applyRow(a)` (+ sufijo "(lista recortada)" si
   `paths_truncated`); si `layout_drift === true`, botón "Replanificar" que dispara el flujo
   `/plan` EXISTENTE de la sección (el mismo handler del botón de plan actual — cero lógica
   nueva). Clases del CSS module de la sección (**gotcha ratchet:** cero `style={{}}`).

**Tests PRIMERO** — `envApplyLedger.test.ts` (vitest, sin @testing-library — gap conocido):
- `applyRow` — formato exacto con server y con Local; FALLÓ cuando `result_ok false`.
- `driftBadge` — null → none; true → warn con el texto exacto; false → ok.

**Comando:** `npx vitest run src/components/devops/envApplyLedger.test.ts`
(cwd = `Stacky Agents\frontend`; por archivo).

**Criterio binario:** los 2 tests pasan Y `npx tsc --noEmit` sin errores nuevos (KPI-5).

**Smoke manual (1 paso, opcional):** aplicar 1 carpeta en sandbox → aparece en el historial;
renombrar una carpeta del catálogo → el badge pasa a "layout cambió".

**Flag:** la de F0 (404 → sección idéntica a hoy). **Runtimes:** UI pura.
**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| El hook rompe el apply (peor caso) | try/except total + KPI-1 respuesta idéntica con append roto; el ledger nunca es camino crítico |
| Rutas con datos sensibles en `paths` | Son rutas RELATIVAS del catálogo del proyecto (ya visibles en la UI de plan); ALLOWLIST impide todo lo demás; cap 200 |
| Duplicación de receta con el 191 | Intencional y declarada (§2): misma receta congelada, otro dominio; si 191 ya está implementado, ESPEJAR su código real; consolidar en un `services/jsonl_ledger.py` común queda ANOTADO como refactor futuro cuando ambos existan (regla de la ruta 195 para masking, misma lógica) |
| Falso drift por orden de rel_paths | `layout_fingerprint` es el MISMO símbolo que usa el apply (:291) — si el fingerprint es estable para el apply, lo es para el drift; cero implementación propia de hashing |
| Sesión paralela toca `api/devops.py` (186 pendiente + series activas) | Cambios ADITIVOS (helper + ruta nueva tras :313); gates de la ruta 195 §7 tras el merge |
| Este plan no está en la ruta 195 | Al implementarlo, agregar su fila en §5 (grupo B, después de 186) y §8 del 195 con commit `docs(plan-195): registro plan 198` |

## 6. Fuera de scope

- Revertir applies (borrar carpetas = destructivo; jamás desde el historial).
- Drift de CONTENIDO de archivos (esto es drift de estructura por fingerprint del layout).
- Ledger de la consola remota 105 (otro dominio; que lo proponga otro plan si hace falta).
- Consolidación `jsonl_ledger.py` común 191+198 (refactor futuro anotado, no acá).

## 7. Glosario (para modelos menores)

- **Apply de ambientes (89/107/108):** creación de las carpetas faltantes del layout del catálogo,
  local o en un servidor registrado; HITL triple (confirm + fingerprint + sandbox_ack).
- **`layout_fingerprint`:** hash estable del (root + rel_paths) que el apply exige para evitar
  aplicar un plan viejo (`plan_stale` 409, devops.py:291-293). Este plan lo REUSA para drift.
- **Drift de layout:** `last_applied_fingerprint != current_fingerprint` — el catálogo/estructura
  cambió después del último apply.
- **Receta de ledger (191):** JSONL + lock + ALLOWLIST + tmp+replace + MAX_ROWS + sort explícito +
  tolerancia a corruptas — congelada en el doc del 191 F0.
- **Ruta 195:** hoja de ruta de la serie DevOps; este plan se registra en ella al implementarse.
- **Convenciones de la casa:** curated ON, HARNESS_TEST_FILES, requires depth-1, ratchet UI,
  NO-EMPEORAR ratchet_meta, tests por archivo.

## 8. Orden de implementación

1. F0 — flag + `env_apply_ledger.py` + endpoint applies con drift + 9 tests.
2. F1 — hook en los 3 puntos de salida del apply + 6 tests.
3. F2 — historial + badge de drift en Ambientes + 2 tests + `tsc`.

Posición en la ruta 195: grupo B (comparte `api/devops.py` con el 186 → implementar DESPUÉS del
186, o antes anotando el desvío en el §8 de la 195). Cada fase se commitea sola con sus tests
verdes ANTES de la siguiente.

## 9. Definición de Hecho (DoD) global

- [ ] Los 3 archivos de test (`test_plan198_env_ledger.py`, `test_plan198_env_hook.py`,
      `envApplyLedger.test.ts`) pasan POR ARCHIVO con el intérprete correcto (el de la ruta 195
      Gate 0 si existe `venv313`).
- [ ] `test_harness_flags_requires.py` y `test_default_known_only_for_curated` verdes;
      `ratchet_meta` bajo criterio NO-EMPEORAR (193 C2 / 195 Gate 0).
- [ ] KPI-1..KPI-5 verificados por los tests nombrados.
- [ ] `npx tsc --noEmit` sin errores nuevos; `python -m compileall backend` limpio; gates §7 de la
      ruta 195 tras el merge.
- [ ] Flag visible/toggleable en la UI de flags, default ON.
- [ ] Con cualquiera de las 2 flags OFF: cero diferencias vs. hoy (404 + sección idéntica).
- [ ] Las 3 guardas HITL del apply (:278/:285/:281) intactas byte a byte (test de no-regresión).
- [ ] Fila del plan agregada en §5/§8 de la ruta 195 (commit `docs(plan-195): registro plan 198`).
