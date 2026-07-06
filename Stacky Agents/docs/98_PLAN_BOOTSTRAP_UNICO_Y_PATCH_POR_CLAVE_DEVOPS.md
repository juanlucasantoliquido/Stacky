# Plan 98 — Un viaje, una caché: bootstrap único del panel DevOps + escritura por clave del client-profile

**Estado:** PROPUESTO (v1)
**Versión:** v1
**Fecha:** 2026-07-06
**Autor:** StackyArchitectaUltraEficientCode
**Serie:** infraestructura transversal del panel DevOps (87-91, 97). NO pertenece a la
serie E2E 93-96 y NO depende de ninguno de esos planes pendientes; tampoco ninguno de
ellos depende de este. Puede implementarse en paralelo.
**Frontera con el plan 34 (`34_PLAN_CLIENT_PROFILE_EFECTIVO_Y_SIN_FRICCION.md`,
PROPUESTO, sin implementar):** el 34 trata QUÉ contiene el perfil (inferencia,
validación semántica, inyección dirigida a agentes). Este plan 98 trata CÓMO viaja el
perfil entre el panel DevOps y el backend (transporte, caché, escritura parcial). Cero
solapamiento: el 98 no toca schema, `_meta`, inferencia ni inyección; si el 34 se
implementa después, el PATCH sigue válido porque `save_client_profile` sigue siendo el
único punto de persistencia.

**Dependencias (todas IMPLEMENTADAS y verificadas en el working tree 2026-07-06):**

| Pieza existente reusada | Evidencia (archivo:línea) |
|---|---|
| GET/PUT full del client-profile (único transporte hoy) | `backend/api/client_profile.py:96` (GET), `:129` (PUT) |
| Validaciones por-key devops DENTRO del PUT (drafts/presets/settings/environment) | `backend/api/client_profile.py:167-247` |
| `load_client_profile` / `save_client_profile` (persistencia única) | `backend/services/client_profile.py:266`, `:315` |
| Riel GET→merge→PUT del cliente (el patrón que este plan reemplaza) | `PipelineBuilderSection.tsx:126-129`, `PublicationsSection.tsx:100-103`, `EnvironmentsSection.tsx:111-114` |
| 3 GETs duplicados del profile completo al montar secciones | `PipelineBuilderSection.tsx:112`, `PublicationsSection.tsx:81`, `EnvironmentsSection.tsx:86` |
| `api.patch` YA existe en el cliente HTTP del frontend | `frontend/src/api/client.ts:89-90` |
| react-query YA en uso en el shell y secciones | `DevOpsPage.tsx:113-117` (health), `:124-129` (servers), `ServersSection.tsx:34-38` |
| Contexto de sección con keys ADITIVAS (contrato §3.12 del 87) | `DevOpsPage.tsx:35-41` (`DevOpsSectionContext`, `selectedServer` aditivo como precedente) |
| Health SIEMPRE-200 con booleans aditivos por plan | `backend/api/devops.py:26-40` |
| Guard per-request por flag con `abort(404)` (patrón a copiar) | `backend/api/devops.py:47-48` (detect-stack, Plan 97), `:68-69` (parse-yaml) |
| `server_registry.list_servers()` + `keyring_available()` | `backend/services/server_registry.py:84-91`, referencia en `api/devops.py:38` |
| Patrón flag 5 patas + gotchas | `backend/config.py:895-898` (alta Plan 97), `backend/services/harness_flags.py:177-184` (`_CATEGORY_KEYS["devops"]`), `harness_flags_help.py:632-637` (PlainHelp 97), `backend/harness_defaults.env`, ratchet `backend/scripts/run_harness_tests.ps1:127-129` |
| Mapa congelado de `requires` (R4, profundidad 1) | `backend/tests/test_harness_flags_requires.py` (`_REQUIRES_MAP_FROZEN`) |
| `mergeKeysIntoProfile` (merge genérico por keys, frontend) | `frontend/src/devops/presetsModel.ts` (import en `PublicationsSection.tsx:18`, `EnvironmentsSection.tsx:19`) |
| Patrón de test vitest TS-puro sin render (estilo de la casa) | `frontend/src/pages/__tests__/ServersSection.test.ts:1-27` |

**GAP VERIFICADO (no existe hoy, búsqueda dirigida):** no existe ningún endpoint
PATCH/parcial del client-profile (`api/client_profile.py` solo registra
`GET /client-profile/default`, `GET`, `PUT`, `DELETE` del profile y `db-readonly-auth`
— grep de `@bp.` sobre el archivo). No existe ningún endpoint agregador del panel
DevOps (`api/devops.py` expone health/detect-stack/parse-yaml/materialize/plan/apply,
ninguno devuelve el profile). No existe caché compartida del profile en el frontend:
las 3 secciones usan `useState` + fetch manual, no react-query
(`PipelineBuilderSection.tsx:108-119`, `PublicationsSection.tsx:77-93`,
`EnvironmentsSection.tsx:82-104`). Conclusión: el gap es real; se construye sin
duplicar nada existente.

---

## 1. Objetivo + KPI

Hidratar todo el panel DevOps en **un solo round-trip** (`GET /api/devops/bootstrap`)
y escribir cada key devops del client-profile con **un solo request de payload chico**
(`PATCH /api/projects/<name>/client-profile/keys/<key>` con merge server-side),
reemplazando el patrón actual: 3 GETs duplicados del profile COMPLETO al montar las
secciones + riel GET→merge→PUT del cliente (2 requests full-profile por cada guardado,
con el catálogo entero viajando de ida y de vuelta). Todo detrás de una flag nueva
default OFF: con la flag apagada el comportamiento es byte-idéntico al actual.

**KPI (medibles; los criterios binarios están en cada fase):**

| Métrica | Hoy (flag OFF / preexistente) | Con flag ON | Cómo se mide |
|---|---|---|---|
| Requests para hidratar Pipelines+Publicaciones+Ambientes (+Servidores) | 1 health + 3 GET profile full + 1 GET servers = **5** | 1 health + 1 bootstrap = **2** (−60%) | pestaña Network del navegador al abrir el panel y visitar las 3 secciones |
| Requests por guardado de draft/preset/settings | GET full + PUT full = **2** | PATCH solo-key = **1** (−50% requests) | pestaña Network al guardar |
| Bytes subidos por guardado | profile ENTERO (incluye `process_catalog` completo + todos los drafts) | solo el valor de la key editada | tamaño del request body en Network |
| Pisadas entre keys distintas del profile (last-write-wins entre secciones/tabs) | posible: el PUT full pisa TODAS las keys con la copia local | **imposible por diseño**: el server hace merge de UNA key bajo lock | test backend `test_patch_preserves_other_keys` |

## 2. Por qué ahora / gap que cierra (evidencia)

1. **3 GETs duplicados del mismo profile al montar.** Cada sección hace su propio
   `api.get('/api/projects/<p>/client-profile')` al montar
   (`PipelineBuilderSection.tsx:112`, `PublicationsSection.tsx:81`,
   `EnvironmentsSection.tsx:86`) porque no hay caché compartida: usan `useState` +
   fetch manual. El GET devuelve el profile completo MÁS `default_template`,
   `prefilled_profile`, `path_check` y `validation`
   (`api/client_profile.py:114-124`) — campos que el panel DevOps no consume.
2. **Cada guardado = 2 requests full-profile.** El riel GET→merge→PUT es OBLIGATORIO
   hoy (comentario literal "FIX C1 - riel GET→merge→PUT OBLIGATORIO" en
   `PipelineBuilderSection.tsx:125`) porque el PUT reemplaza el profile entero
   (`api/client_profile.py:129`): para no pisar las DEMÁS keys, el cliente baja todo,
   mergea su key y sube todo. Con un catálogo de N procesos, cada "Guardar preset"
   sube el catálogo entero dos direcciones sin necesidad.
3. **Last-write-wins entre keys.** Si dos secciones (o dos tabs) guardan casi a la
   vez, el segundo PUT full pisa la key que el primero acababa de escribir, porque
   ambos partieron del mismo GET base. El PATCH por clave elimina esta clase de
   pisada: el server mergea UNA key sobre el estado persistido REAL, bajo lock.
4. **El health ya agrega booleans pero no datos.** `GET /api/devops/health`
   (`api/devops.py:26-40`) es el único agregador del panel y solo trae flags. Los
   datos (drafts/presets/settings/catálogo/servidores) viajan en 4 requests aparte.
5. **La infraestructura para arreglarlo YA está:** `api.patch` existe en el cliente
   (`client.ts:89-90`) con cero usos DevOps; react-query ya hidrata health y servers
   en el shell (`DevOpsPage.tsx:113-129`); el contrato §3.12 permite agregar keys
   aditivas al `DevOpsSectionContext` (precedente: `selectedServer`, Plan 91 F6).

Los planes 93-96 (pendientes) y el 97 (implementado) agregan MÁS features encima de
estas mismas secciones: cada plan nuevo hereda hoy el transporte caro. Cerrar este gap
primero abarata todos los siguientes.

## 3. Principios y guardarraíles (no negociables, verificables)

1. **Flag default OFF + byte-idéntico con OFF.** Todo lo nuevo vive detrás de
   `STACKY_DEVOPS_BOOTSTRAP_ENABLED` (default OFF). Con OFF: los endpoints nuevos
   devuelven 404 (patrón `api/devops.py:47-48`), el frontend sigue el camino actual
   EXACTO (mismos requests, mismos payloads). Criterio binario por test + grep.
2. **Cero trabajo extra del operador.** Opt-in de 1 click en Configuración → Arnés
   (categoría DevOps), como toda la serie 87-97. Sin pasos manuales nuevos, sin
   migraciones, sin cambios de datos persistidos: el PATCH escribe en el MISMO
   `config.json` vía el MISMO `save_client_profile` (`services/client_profile.py:315`).
3. **Backward-compatible duro.** El PUT full existente NO cambia de contrato ni de
   mensajes de error (sus validaciones se EXTRAEN a funciones compartidas, no se
   reescriben). Cualquier consumidor actual del PUT (ClientProfileEditor, tests de
   los planes 87/88/89) sigue verde sin tocarse.
4. **Paridad de validación PUT/PATCH por construcción.** El PATCH no duplica
   validadores: usa las MISMAS funciones extraídas del PUT (F1). Un drift entre ambos
   es imposible sin romper un test de paridad nombrado.
5. **3 runtimes (Codex CLI, Claude Code CLI, GitHub Copilot Pro):** este plan es
   dashboard + API interna del panel; NINGÚN runner ni prompt de agente consume estos
   endpoints (los consumidores son componentes React). Impacto runtime: **NINGUNO**,
   declarado por fase (precedente: Plan 78, rediseño UI con impacto runtime nulo). El
   único punto de contacto es el agente DevOps del Plan 90, que conversa por
   `api/devops_agent.py` y NO lee client-profile por estos endpoints — sin cambios.
6. **Human-in-the-loop intacto.** Este plan NO agrega ni quita ninguna decisión: solo
   cambia el transporte de datos ya decididos por el operador. Ningún auto-guardado
   nuevo, ningún flujo autónomo.
7. **Mono-operador sin auth.** El lock de escritura es un `threading.Lock` de proceso
   (suficiente: un solo backend Flask, un solo operador). Nada de RBAC ni ETags con
   negociación multiusuario.
8. **Gotchas de flags (obligatorios):** la `FlagSpec` nueva NO lleva kwarg
   `default` (default OFF implícito; pasar `default=False` explícito rompe
   `test_default_known_only_for_curated` — Plan 63). La arista
   `STACKY_DEVOPS_BOOTSTRAP_ENABLED → STACKY_DEVOPS_PANEL_ENABLED` se agrega a
   `_REQUIRES_MAP_FROZEN` (R4, profundidad 1: PANEL no requiere nada, así que la
   cadena es legal). Todo archivo de test backend nuevo se registra en
   `HARNESS_TEST_FILES` de `run_harness_tests.sh` Y `.ps1` (ratchet Plan 49).
9. **No degradar.** Cero dependencias nuevas (npm/py). El shell `DevOpsPage.tsx` solo
   recibe cambios ADITIVOS (query nueva + key nueva en ctx), sin tocar el registro
   `DEVOPS_SECTIONS` ni el gate declarativo.

---

## F0 — Flag `STACKY_DEVOPS_BOOTSTRAP_ENABLED` (5 patas) + key aditiva en health

**Objetivo:** dar de alta la flag que protege TODO el plan, con default OFF, visible y
activable desde la UI del Arnés, y exponerla al frontend vía la key aditiva
`bootstrap_enabled` del health.
**Valor:** el guard existe antes que cualquier endpoint (los guards de F2/F3 compilan
contra una flag real); el operador puede activar/desactivar con 1 click.

**Archivos a editar (exactos):**

1. `Stacky Agents/backend/config.py` — inmediatamente después del bloque de
   `STACKY_DEVOPS_STACK_DETECT_ENABLED` (hoy `config.py:895-898`):

```python
# Plan 98 — Bootstrap unico del panel DevOps + PATCH por clave del client-profile.
# Default OFF.
STACKY_DEVOPS_BOOTSTRAP_ENABLED: bool = os.getenv(
    "STACKY_DEVOPS_BOOTSTRAP_ENABLED", "false"
).lower() in ("1", "true", "yes")
```

2. `Stacky Agents/backend/services/harness_flags.py`:
   - Agregar `"STACKY_DEVOPS_BOOTSTRAP_ENABLED",  # Plan 98 — bootstrap unico + PATCH por clave` como ÚLTIMA entrada de la tupla `_CATEGORY_KEYS["devops"]` (hoy líneas 177-184).
   - Agregar al `FLAG_REGISTRY`, inmediatamente después de la `FlagSpec` de
     `STACKY_DEVOPS_STACK_DETECT_ENABLED`:

```python
    # ── Plan 98 — Bootstrap unico del panel DevOps ──────────────────────────────
    FlagSpec(
        key="STACKY_DEVOPS_BOOTSTRAP_ENABLED",
        type="bool",
        label="Carga rapida del panel DevOps (Plan 98)",
        description=(
            "Plan 98 — El panel DevOps se hidrata con un solo request "
            "(GET /api/devops/bootstrap) y los guardados de pipelines/publicaciones/"
            "ambientes viajan como PATCH por clave (payload chico, merge en el "
            "backend). Con OFF todo funciona igual que antes (mas requests, "
            "payloads completos). No cambia ningun dato guardado."
        ),
        group="global",  # mismo group que STACKY_DEVOPS_PANEL_ENABLED (87 v2 F0)
        env_only=False,  # editable por UI (categoría 'devops')
        requires="STACKY_DEVOPS_PANEL_ENABLED",  # Plan 82 — declarativo, informa en UI
    ),
```

   **PROHIBIDO** pasar `default=False` (gotcha Plan 63) y **PROHIBIDO**
   `requires` apuntando a otra flag que no sea `STACKY_DEVOPS_PANEL_ENABLED` (R4).

3. `Stacky Agents/backend/services/harness_flags_help.py` — nueva entrada en el dict
   de ayudas, junto a las devops existentes (patrón `harness_flags_help.py:632-637`):

```python
    "STACKY_DEVOPS_BOOTSTRAP_ENABLED": PlainHelp(
        what="El panel DevOps carga todo de un solo viaje y guarda cada cambio mandando solo lo que cambio.",
        on_effect="Si la activás: el panel DevOps abre más rápido (un solo pedido al backend en vez de varios) y guardar un borrador/preset/configuración manda solo esa parte, no todo el perfil.",
        off_effect="Si la apagás: no cambia nada de lo guardado; el panel vuelve a cargar y guardar como antes (más pedidos y más datos por viaje).",
        example="Como pedir todo el supermercado en un solo delivery en vez de un viaje por producto — y devolver solo la botella vacía en vez de re-empacar toda la compra.",
    ),
```

4. `Stacky Agents/backend/harness_defaults.env` — agregar la línea
   `STACKY_DEVOPS_BOOTSTRAP_ENABLED=false` junto al bloque de flags DEVOPS.

5. `Stacky Agents/backend/api/devops.py` — en `devops_health_route`
   (`api/devops.py:26-40`), agregar la key aditiva (misma forma que
   `stack_detect_enabled`):

```python
        "bootstrap_enabled": bool(getattr(cfg, "STACKY_DEVOPS_BOOTSTRAP_ENABLED", False)),  # Plan 98
```

6. `Stacky Agents/backend/tests/test_harness_flags_requires.py` — agregar la arista
   al mapa congelado `_REQUIRES_MAP_FROZEN`:
   `"STACKY_DEVOPS_BOOTSTRAP_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",`.

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/backend/tests/test_plan98_bootstrap_flag.py`, 5 casos:

1. `test_flag_registered_bool` — existe `FlagSpec` con
   `key == "STACKY_DEVOPS_BOOTSTRAP_ENABLED"`, `type == "bool"`, `env_only is False`.
2. `test_flag_categorized_devops` — la key está en `_CATEGORY_KEYS["devops"]`.
3. `test_flag_requires_panel` — `spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"`.
4. `test_default_off_effective` — con env limpio (monkeypatch.delenv si existiera),
   recargar config ⇒ `config.STACKY_DEVOPS_BOOTSTRAP_ENABLED is False` (default
   EFECTIVO en `config.py`, no solo cosmético — gotcha
   "default runtime = config.py, no FlagSpec").
5. `test_health_exposes_bootstrap_enabled_false_by_default` — `GET /api/devops/health`
   responde 200 con `"bootstrap_enabled": False` (con la flag OFF).

**Comandos (venv real del repo — OJO: es `.venv`, no `venv`):**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan98_bootstrap_flag.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_requires.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q
```

**Criterio de aceptación (binario):** los 5 tests nuevos verdes + los 3 archivos de
meta-tests del arnés verdes (registro, categorización, requires, help).
**Flag:** `STACKY_DEVOPS_BOOTSTRAP_ENABLED`, default OFF.
**Impacto por runtime:** NINGUNO (flag de UI/backend del panel; ningún runner la lee).
Fallback: N/A.
**Trabajo del operador:** ninguno (opt-in default off, activable por UI).

---

## F1 — Extraer los validadores por-key del PUT a funciones compartidas (sin cambio de comportamiento)

**Objetivo:** mover los 4 bloques de validación devops que hoy viven inline en
`put_client_profile` (`api/client_profile.py:167-247`) a funciones puras reutilizables,
para que F2 (PATCH) valide EXACTAMENTE igual que el PUT sin duplicar código.
**Valor:** paridad PUT/PATCH por construcción; el PUT queda más corto sin cambiar ni
un mensaje de error.

**Archivo NUEVO:** `Stacky Agents/backend/services/client_profile_keys.py`

```python
"""services/client_profile_keys.py — Plan 98.

Allowlist de keys parcheables del client_profile + validadores por-key EXTRAIDOS
(movidos, no reescritos) de api/client_profile.py::put_client_profile. PUROS, sin I/O.
Los mensajes de error son BYTE-IDENTICOS a los que el PUT devolvia inline.
"""

PATCHABLE_PROFILE_KEYS: frozenset = frozenset({
    "devops_pipeline_drafts",       # Plan 87 F2
    "devops_publication_presets",   # Plan 88 F2
    "devops_publication_settings",  # Plan 88 F2
    "devops_environment_settings",  # Plan 89 F3
})


def validate_profile_key(key: str, value) -> str | None:
    """Primer mensaje de error (str) o None si el valor es valido para esa key.
    value=None es valido para toda key (semantica 'ausente = no-op' del PUT)."""
    if value is None:
        return None
    if key == "devops_pipeline_drafts":
        return _validate_pipeline_drafts(value)
    if key == "devops_publication_presets":
        return _validate_publication_presets(value)
    if key == "devops_publication_settings":
        return _validate_publication_settings(value)
    if key == "devops_environment_settings":
        return _validate_environment_settings(value)
    return f"key '{key}' no es parcheable."
```

Los cuerpos de `_validate_pipeline_drafts`, `_validate_publication_presets`,
`_validate_publication_settings` y `_validate_environment_settings` son el TRASLADO
LITERAL de los bloques del PUT (`api/client_profile.py:167-185`, `:187-212`,
`:213-224`, `:226-247` respectivamente), con una sola transformación mecánica: donde
el PUT hace `return jsonify({"ok": False, "error": "<MSG>"}), 400`, la función
devuelve `"<MSG>"` (el MISMO string, sin cambiar ni un carácter, incluidos los índices
`[{idx}]` interpolados). Los imports lazy de `environment_init`
(`validate_root`, `is_safe_segment`) se conservan tal cual dentro de la función. La
validación de `process_catalog` (`api/client_profile.py:141-165`) **NO se extrae** (su
error es estructurado `{"error": "invalid_process_kind", "value": ..., "allowed": ...,
"index": ...}`, no un string simple) y `process_catalog` **NO entra** en la allowlist
v1 — queda en el PUT, intacta.

**Archivo a editar:** `Stacky Agents/backend/api/client_profile.py` — en
`put_client_profile`, reemplazar los 4 bloques inline por:

```python
    from services.client_profile_keys import PATCHABLE_PROFILE_KEYS, validate_profile_key
    for _key in ("devops_pipeline_drafts", "devops_publication_presets",
                 "devops_publication_settings", "devops_environment_settings"):
        _err = validate_profile_key(_key, profile.get(_key))
        if _err:
            return jsonify({"ok": False, "error": _err}), 400
```

(el bloque de `process_catalog` de las líneas 141-165 queda ANTES, sin tocar; el orden
de chequeo por key se preserva: catalog → drafts → presets → settings → environment,
que es el orden actual del PUT).

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/backend/tests/test_plan98_profile_key_validators.py`, 8 casos:

1. `test_allowlist_frozen_exact` — `PATCHABLE_PROFILE_KEYS == frozenset({las 4 keys})`
   (congela la allowlist: agregar una key exige tocar este test a propósito).
2. `test_none_is_valid_for_every_key` — `validate_profile_key(k, None) is None` para
   las 4 keys.
3. `test_unknown_key_rejected` — `validate_profile_key("language", [])` devuelve
   mensaje no-None.
4. `test_drafts_invalid_cases` — no-lista → `"devops_pipeline_drafts debe ser una
   lista."`; 51 drafts → mensaje de máximo 50; draft sin `name` → mensaje con índice;
   nombre duplicado → mensaje de duplicado; `spec` no-dict → mensaje de objeto
   (mismos strings del PUT actual).
5. `test_presets_invalid_cases` — `mode` inválido, `groups` fuera de allowlist,
   `target` inválido, `process_names` ausente en `mode=selection` (mismos strings).
6. `test_settings_invalid_cases` — `step_templates` con key fuera de
   `{entry,processing,output,default}` o valor no-string.
7. `test_environment_invalid_cases` — `environment_root` relativo (reusa
   `validate_root`), `folder_layout` con key inválida, `per_process_subfolder`
   no-bool.
8. `test_put_uses_shared_validators_same_errors` — vía test client Flask: un PUT con
   `devops_pipeline_drafts` no-lista responde 400 con el MISMO
   `{"ok": False, "error": "devops_pipeline_drafts debe ser una lista."}` que antes
   del refactor (paridad de contrato del PUT).

**No-regresión obligatoria (el PUT es contrato de 3 planes):**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan98_profile_key_validators.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan87_devops_flag.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan88_publications_flag.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan89_environments_flag.py" -q
```

**Criterio de aceptación (binario):** 8 tests nuevos verdes + los 3 archivos de tests
de los planes 87/88/89 verdes SIN modificarlos (si alguno exige tocar sus asserts, el
refactor rompió el contrato del PUT y está mal).
**Flag:** ninguna (refactor puro sin cambio de comportamiento; no necesita gate).
**Impacto por runtime:** NINGUNO. Fallback: N/A.
**Trabajo del operador:** ninguno.

---

## F2 — `PATCH /api/projects/<name>/client-profile/keys/<key>` (merge server-side bajo lock)

**Objetivo:** escribir UNA key devops del profile con un request de payload chico; el
backend mergea sobre el estado persistido real y guarda vía `save_client_profile`.
**Valor:** elimina el riel GET→merge→PUT del cliente (2 requests full → 1 request
chico) y hace imposible pisar OTRAS keys del profile.

**Archivo a editar:** `Stacky Agents/backend/api/client_profile.py` — agregar (después
de `put_client_profile`):

```python
# ── PATCH /api/projects/<name>/client-profile/keys/<key> (Plan 98) ───────────
# Lock de proceso: serializa load→merge→save de PATCHes concurrentes (mono-operador,
# un solo proceso Flask — suficiente; NO hay lock hoy en services/client_profile.py,
# verificado por grep de threading/Lock = 0 matches).
import threading
_PROFILE_WRITE_LOCK = threading.Lock()


@bp.patch("/projects/<string:project_name>/client-profile/keys/<string:key>")
def patch_client_profile_key(project_name: str, key: str):
    import config as _config
    if not getattr(_config.config, "STACKY_DEVOPS_BOOTSTRAP_ENABLED", False):
        from flask import abort
        abort(404)  # guard per-request, patrón api/devops.py:47-48

    cfg = get_project_config(project_name)
    if not cfg:
        return jsonify({"ok": False, "error": f"Proyecto '{project_name}' no encontrado"}), 404

    from services.client_profile_keys import PATCHABLE_PROFILE_KEYS, validate_profile_key
    if key not in PATCHABLE_PROFILE_KEYS:
        return jsonify({"ok": False, "error": "key_not_patchable",
                        "allowed": sorted(PATCHABLE_PROFILE_KEYS)}), 400

    data = request.get_json(force=True, silent=True) or {}
    if not isinstance(data, dict) or "value" not in data:
        return jsonify({"ok": False, "error": "Body debe traer 'value'."}), 400
    value = data["value"]

    err = validate_profile_key(key, value)
    if err:
        return jsonify({"ok": False, "error": err}), 400

    with _PROFILE_WRITE_LOCK:
        base = load_client_profile(project_name) or {}
        if value is None:
            base.pop(key, None)          # PATCH value=null ⇒ borrar la key
        else:
            base[key] = value
        try:
            normalized = save_client_profile(project_name, base)
        except ClientProfileError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error en PATCH de client_profile.%s de %s", key, project_name)
            return jsonify({"ok": False, "error": str(exc)}), 500

    record_event(
        action="client_profile_key_patch",
        project=project_name,
        result="applied",
        actor=_actor(),
        schema_version=int(normalized.get("schema_version") or 1),
        detail={"key": key},
    )
    return jsonify({"ok": True, "key": key, "value": normalized.get(key)})
```

**Casos borde fijados por contrato:**
- Flag OFF ⇒ 404 (byte-idéntico: la ruta "no existe").
- Key fuera de allowlist ⇒ 400 `key_not_patchable` con `allowed` (nunca 500).
- Proyecto inexistente ⇒ 404 (mismo mensaje que GET/PUT).
- Body sin `"value"` ⇒ 400. `{"value": null}` ⇒ BORRA la key (explícito ≠ ausente).
- Profile inexistente (proyecto legacy sin `client_profile`) ⇒ `base = {}` y se crea
  el profile con esa única key (`save_client_profile` valida; las secciones
  requeridas son warnings, no errores — `services/client_profile.py:185-191`).
- Valor inválido ⇒ 400 con el MISMO string de error que daría el PUT (F1).
- El lock cubre load→merge→save COMPLETO: dos PATCHes concurrentes a keys distintas
  quedan serializados y ninguno pisa al otro.

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/backend/tests/test_plan98_profile_key_patch.py`, 9 casos (test client
Flask + proyecto fixture, mismo estilo que `test_plan88_publications_flag.py`):

1. `test_patch_404_when_flag_off` — flag OFF ⇒ 404.
2. `test_patch_404_unknown_project` — flag ON, proyecto inexistente ⇒ 404.
3. `test_patch_400_key_not_in_allowlist` — `PATCH .../keys/language` ⇒ 400 con
   `error == "key_not_patchable"` y `allowed` = las 4 keys ordenadas.
4. `test_patch_400_missing_value` — body `{}` ⇒ 400.
5. `test_patch_400_invalid_value_same_error_as_put` — `devops_pipeline_drafts` no-
   lista por PATCH y por PUT ⇒ mismo status y mismo `error` string (paridad F1).
6. `test_patch_preserves_other_keys` — sembrar profile con
   `devops_publication_presets` + `devops_pipeline_drafts`; PATCH solo drafts;
   releer profile ⇒ presets INTACTOS byte-idénticos y drafts actualizados.
7. `test_patch_creates_profile_when_absent` — proyecto sin `client_profile` ⇒ PATCH
   crea el profile con la key y responde `value` normalizado.
8. `test_patch_null_deletes_key` — sembrar la key, PATCH `{"value": null}` ⇒ la key
   desaparece del profile persistido y la respuesta trae `value: None`.
9. `test_patch_records_event` — `record_event` invocado con
   `action="client_profile_key_patch"` y `detail.key` correcto (monkeypatch del
   símbolo `record_event` EN `api.client_profile` — gotcha de mocks: parchear donde
   se consume).

**Comando:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan98_profile_key_patch.py" -q
```

**Criterio de aceptación (binario):** 9 tests verdes; `test_plan87/88/89_*.py` siguen
verdes (el PUT no cambió).
**Flag:** `STACKY_DEVOPS_BOOTSTRAP_ENABLED` (OFF ⇒ endpoint 404).
**Impacto por runtime:** NINGUNO (endpoint consumido solo por el frontend).
Fallback: con flag OFF el frontend usa el riel GET→merge→PUT actual (F5).
**Trabajo del operador:** ninguno.

---

## F3 — `GET /api/devops/bootstrap?project=X` (hidratación en un round-trip)

**Objetivo:** un endpoint agregador SOLO-LECTURA que devuelve en una sola respuesta el
health + las keys devops del profile + el catálogo + los servidores (si aplica).
**Valor:** abrir el panel pasa de 5 requests a 2 (health + bootstrap).

**Archivo a editar:** `Stacky Agents/backend/api/devops.py`

1. Extraer el payload del health a un helper para NO duplicarlo (paridad por
   construcción entre `/health` y `/bootstrap`):

```python
def _health_payload() -> dict:
    """Payload compartido por /health y /bootstrap (Plan 98). SIEMPRE calculable."""
    cfg = _config.config
    return {
        "flag_enabled": bool(getattr(cfg, "STACKY_DEVOPS_PANEL_ENABLED", False)),
        "generator_enabled": bool(getattr(cfg, "STACKY_PIPELINE_GENERATOR_ENABLED", False)),
        "trigger_enabled": bool(getattr(cfg, "STACKY_PIPELINE_TRIGGER_ENABLED", False)),
        "publications_enabled": bool(getattr(cfg, "STACKY_DEVOPS_PUBLICATIONS_ENABLED", False)),
        "environments_enabled": bool(getattr(cfg, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False)),
        "agent_enabled": bool(getattr(cfg, "STACKY_DEVOPS_AGENT_ENABLED", False)),
        "servers_enabled": bool(getattr(cfg, "STACKY_DEVOPS_SERVERS_ENABLED", False)),
        "rdp_available": (sys.platform == "win32") and server_registry.keyring_available(),
        "stack_detect_enabled": bool(getattr(cfg, "STACKY_DEVOPS_STACK_DETECT_ENABLED", False)),
        "bootstrap_enabled": bool(getattr(cfg, "STACKY_DEVOPS_BOOTSTRAP_ENABLED", False)),  # Plan 98
    }


@bp.get("/health")
def devops_health_route():
    """SIEMPRE 200 (la UI lo usa para decidir si muestra la tab)."""
    return jsonify(_health_payload())
```

2. Endpoint nuevo:

```python
@bp.get("/bootstrap")
def devops_bootstrap_route():
    """Hidratacion del panel DevOps en UN round-trip. SOLO-LECTURA. Plan 98."""
    if not getattr(_config.config, "STACKY_DEVOPS_BOOTSTRAP_ENABLED", False):
        abort(404)
    project = request.args.get("project")
    if not project:
        return jsonify({"error": "project es obligatorio"}), 400
    health = _health_payload()
    profile = load_client_profile(project) or {}

    def _lst(k):
        v = profile.get(k)
        return v if isinstance(v, list) else []

    def _dct(k):
        v = profile.get(k)
        return v if isinstance(v, dict) else None

    payload = {
        "health": health,
        "has_profile": bool(profile),
        "profile_keys": {
            "devops_pipeline_drafts": _lst("devops_pipeline_drafts"),
            "devops_publication_presets": _lst("devops_publication_presets"),
            "devops_publication_settings": _dct("devops_publication_settings") or {},
            # None (no {}) si ausente: EnvironmentsSection distingue "sin configurar"
            # (hasSavedSettings=false) de "configurado vacio" — EnvironmentsSection.tsx:88-95.
            "devops_environment_settings": _dct("devops_environment_settings"),
            "process_catalog": _lst("process_catalog"),
        },
        "servers": None,
    }
    if health["servers_enabled"]:
        payload["servers"] = {
            "servers": server_registry.list_servers(),
            "keyring_available": server_registry.keyring_available(),
        }
    return jsonify(payload)
```

**Casos borde fijados:** proyecto sin profile ⇒ 200 con listas vacías /
`devops_environment_settings: null` / `has_profile: false` (nunca 404: el panel debe
abrir igual). Keys corruptas por edición manual del JSON (no-lista/no-dict) ⇒
normalizadas a vacío/None (defensivo clase C5 del 88, mismo criterio que
`materialize_publication_route` — `api/devops.py:93-95`). `servers` solo si
`servers_enabled` (KPI-3 del Plan 91: con flag servers OFF no se toca
`server_registry`).

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/backend/tests/test_plan98_bootstrap_endpoint.py`, 7 casos:

1. `test_bootstrap_404_when_flag_off`.
2. `test_bootstrap_400_without_project`.
3. `test_bootstrap_shape_with_profile` — sembrar profile con las 5 keys ⇒ 200 y cada
   key llega con su valor exacto; `has_profile is True`.
4. `test_bootstrap_empty_profile_defaults` — proyecto sin profile ⇒ listas vacías,
   `devops_publication_settings == {}`, `devops_environment_settings is None`,
   `has_profile is False`.
5. `test_bootstrap_health_matches_health_endpoint` — el dict `health` del bootstrap es
   IGUAL (mismo set de keys y valores) al body de `GET /api/devops/health` en el mismo
   estado de flags (paridad por helper compartido).
6. `test_bootstrap_servers_only_when_enabled` — con `STACKY_DEVOPS_SERVERS_ENABLED`
   OFF ⇒ `servers is None`; con ON ⇒ dict con `servers` + `keyring_available`
   (monkeypatch de `server_registry.list_servers` EN `api.devops`).
7. `test_bootstrap_corrupt_keys_normalized` — sembrar
   `devops_pipeline_drafts: "basura"` (string) ⇒ 200 con lista vacía, sin 500.

**Comando:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan98_bootstrap_endpoint.py" -q
```

**Criterio de aceptación (binario):** 7 tests verdes + `GET /api/devops/health` sigue
respondiendo el MISMO shape que antes más `bootstrap_enabled` (cubierto por el test 5
y por los tests existentes de health de los planes 87-91, que deben seguir verdes).
**Flag:** `STACKY_DEVOPS_BOOTSTRAP_ENABLED` (OFF ⇒ 404).
**Impacto por runtime:** NINGUNO. Fallback: con flag OFF el frontend hidrata con los
GETs actuales (F4).
**Trabajo del operador:** ninguno.

---

## F4 — Frontend: query compartida de bootstrap + hidratación de las 3 secciones sin fetch propio

**Objetivo:** el shell (`DevOpsPage`) baja el bootstrap UNA vez con react-query y lo
pasa por `ctx` (key aditiva del contrato §3.12); Pipelines/Publicaciones/Ambientes se
hidratan de ahí y dejan de disparar su GET propio del profile — solo con la flag ON.
**Valor:** −3 requests full-profile al abrir el panel; caché única y coherente.

**Archivos a editar (exactos):**

1. `Stacky Agents/frontend/src/api/endpoints.ts` — dentro de `export const DevOps`
   (hoy `endpoints.ts:3072-3112`), agregar el tipo y el método:

```ts
export interface DevOpsBootstrapResponse {
  health: Record<string, boolean | undefined>;
  has_profile: boolean;
  profile_keys: {
    devops_pipeline_drafts: Array<{ name: string; spec: object; updated_at: string }>;
    devops_publication_presets: object[];
    devops_publication_settings: { step_templates?: Record<string, string> };
    devops_environment_settings: object | null;
    process_catalog: object[];
  };
  servers: { servers: ServerSummary[]; keyring_available: boolean } | null;
}
```

   y en el objeto `DevOps`:

```ts
  /** GET /api/devops/bootstrap — Plan 98. Hidratación del panel en 1 round-trip. */
  bootstrap: (project: string) =>
    api.get<DevOpsBootstrapResponse>(
      `/api/devops/bootstrap?project=${encodeURIComponent(project)}`,
    ),
```

2. `Stacky Agents/frontend/src/pages/DevOpsPage.tsx`:
   - `DevOpsHealth` suma la key explícita `bootstrap_enabled?: boolean;` (aditiva,
     como `servers_enabled`).
   - `DevOpsSectionContext` suma la key ADITIVA
     `bootstrap?: DevOpsBootstrapResponse | null;` (mismo precedente que
     `selectedServer`, Plan 91 F6 — `DevOpsPage.tsx:39`).
   - En el componente, después de `serversQuery`:

```ts
  // Plan 98 — bootstrap único (solo con la flag ON y proyecto activo).
  const activeProjectName = useWorkbench((s) => s.activeProject)?.name ?? '';
  const bootstrapQuery = useQuery({
    queryKey: ['devops-bootstrap', activeProjectName],
    queryFn: () => DevOps.bootstrap(activeProjectName),
    retry: false,
    enabled: healthQuery.data?.bootstrap_enabled === true && !!activeProjectName,
  });
```

   - En el `ctx`: `bootstrap: bootstrapQuery.data ?? null,`.
   - Import nuevo: `useWorkbench` desde `'../store/workbench'` (ya lo usan las
     secciones; el shell hoy no lo importa).
   - NADA más cambia en el shell: `DEVOPS_SECTIONS`, el gate declarativo y el selector
     de servidor quedan intactos.

3. Las 3 secciones agregan el early-path de hidratación (patrón idéntico en las 3):

   - `PipelineBuilderSection.tsx` — `loadDrafts` (`:108-119`) pasa a:

```ts
  const bootstrapOn = ctx.health.bootstrap_enabled === true;

  const loadDrafts = async () => {
    if (!activeProject) return;
    // Plan 98 — con bootstrap ON, hidratar desde ctx (0 requests propios).
    if (bootstrapOn) {
      if (ctx.bootstrap) {
        setDrafts(ctx.bootstrap.profile_keys.devops_pipeline_drafts as typeof drafts);
      }
      return; // aún cargando o ya hidratado: NUNCA fetch propio con la flag ON
    }
    /* ...camino actual INTACTO (api.get client-profile)... */
  };
```

     y el `useEffect` de montado (`:87-89`) suma `ctx.bootstrap` a las dependencias:
     `useEffect(() => { loadDrafts(); }, [ctx.bootstrap]);` — así, cuando la query del
     shell resuelve, la sección se hidrata sola sin request propio.

   - `PublicationsSection.tsx` — cambiar la firma a
     `= ({ ctx }) => {` (hoy descarta el prop: `PublicationsSection.tsx:55`), y en
     `loadProfile` (`:77-93`) el mismo early-path leyendo
     `devops_publication_presets`, `devops_publication_settings`, `process_catalog` y
     `devops_pipeline_drafts` de `ctx.bootstrap.profile_keys`; `useEffect` con deps
     `[activeProject, ctx.bootstrap]`.

   - `EnvironmentsSection.tsx` — en `loadProfile` (`:82-104`) el mismo early-path:
     `devops_environment_settings` (null ⇒ `setHasSavedSettings(false)` +
     `emptyEnvironmentSettings()`, no-null ⇒ setear y `setHasSavedSettings(true)`) y
     `devops_publication_presets` para el Paso 3; `useEffect` con deps
     `[activeProject, ctx.bootstrap]`.

**Caso borde fijado:** con `bootstrap_enabled === true` y la query aún en vuelo
(`ctx.bootstrap === null`), la sección NO hace fetch propio (evita el request
duplicado); se hidrata cuando la query resuelve vía el `useEffect`. Con flag OFF,
`bootstrapOn` es `false` y el camino actual corre byte-idéntico.

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/frontend/src/pages/__tests__/DevOpsBootstrap.test.ts` (TS-puro estilo
`ServersSection.test.ts:1-27` — import de módulos + grep de fuente con `fs`), 6 casos:

1. `shell define la query devops-bootstrap con enabled guard` — el fuente de
   `DevOpsPage.tsx` contiene `bootstrap_enabled === true` y `'devops-bootstrap'`.
2. `ctx expone bootstrap aditivo` — el fuente contiene `bootstrap: bootstrapQuery.data ?? null`.
3. `PipelineBuilderSection tiene early-path y no fetchea con flag ON` — su fuente
   contiene `ctx.bootstrap.profile_keys.devops_pipeline_drafts` y
   `bootstrap_enabled === true`.
4. `PublicationsSection consume ctx` — su fuente contiene `({ ctx })` y
   `ctx.bootstrap.profile_keys.devops_publication_presets`.
5. `EnvironmentsSection distingue settings null` — su fuente contiene
   `devops_environment_settings` leído de `ctx.bootstrap.profile_keys`.
6. `endpoints expone DevOps.bootstrap` — `import('../../api/endpoints')` y
   `typeof mod.DevOps.bootstrap === 'function'`.

**Comandos (SIEMPRE por archivo — nunca `npx vitest run` a secas; cwd
`Stacky Agents/frontend`):**

```
npx vitest run src/pages/__tests__/DevOpsBootstrap.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** 6 tests vitest verdes + `tsc --noEmit` 0 errores
+ los tests vitest existentes del panel (`DevOpsPage.test.ts`,
`ServersSection.test.ts`) verdes sin modificarlos.
**Flag:** `STACKY_DEVOPS_BOOTSTRAP_ENABLED` vía `health.bootstrap_enabled` (OFF ⇒
query `enabled: false`, secciones fetchean como hoy).
**Impacto por runtime:** NINGUNO (solo componentes React). Fallback: flag OFF =
comportamiento actual byte-idéntico.
**Trabajo del operador:** ninguno.

---

## F5 — Frontend: helper único de escritura por clave con fallback (PATCH ⇄ riel viejo)

**Objetivo:** un helper `saveProfileKey` reemplaza los 5 cuerpos GET→merge→PUT
dispersos; con flag ON hace 1 PATCH chico, con flag OFF ejecuta el riel actual.
**Valor:** −50% de requests y >90% menos bytes por guardado; un solo lugar donde vive
la lógica de escritura (hoy está copiada 5 veces).

**Archivo NUEVO:** `Stacky Agents/frontend/src/devops/profileKeys.ts`

```ts
/**
 * profileKeys.ts — Plan 98 F5.
 * Escritura por clave del client-profile con fallback al riel GET→merge→PUT.
 * ÚNICO punto de escritura de keys devops_* desde el panel DevOps.
 */
import { api } from '../api/client';
import { mergeKeysIntoProfile } from './presetsModel';

export type PatchableProfileKey =
  | 'devops_pipeline_drafts'
  | 'devops_publication_presets'
  | 'devops_publication_settings'
  | 'devops_environment_settings';

export async function saveProfileKey(
  project: string,
  key: PatchableProfileKey,
  value: unknown,
  bootstrapEnabled: boolean,
): Promise<void> {
  if (bootstrapEnabled) {
    // Plan 98 — 1 request, payload solo-key, merge server-side bajo lock.
    await api.patch(
      `/api/projects/${encodeURIComponent(project)}/client-profile/keys/${key}`,
      { value },
    );
    return;
  }
  // Fallback (flag OFF): riel GET→merge→PUT actual, byte-idéntico al preexistente.
  const json = await api.get<{ profile?: Record<string, unknown> }>(
    `/api/projects/${encodeURIComponent(project)}/client-profile`,
  );
  const base = json.profile ?? {};
  const merged = mergeKeysIntoProfile(base, { [key]: value });
  await api.put(`/api/projects/${encodeURIComponent(project)}/client-profile`, { profile: merged });
}
```

**Callers a migrar (lista EXACTA — cada uno reemplaza su cuerpo GET→merge→PUT por una
llamada a `saveProfileKey`, conservando su manejo de estado y errores actual):**

| Caller | Ubicación hoy | Key | Requests hoy → después |
|---|---|---|---|
| `saveDraft` | `PipelineBuilderSection.tsx:121-137` | `devops_pipeline_drafts` | 2 full → 1 chico |
| `savePresets` | `PublicationsSection.tsx:95-110` | `devops_publication_presets` | 2 full → 1 chico |
| `saveSettings` | `PublicationsSection.tsx:112-125` | `devops_publication_settings` | 2 full → 1 chico |
| `saveSettings` | `EnvironmentsSection.tsx:106-121` | `devops_environment_settings` | 2 full → 1 chico |
| `handleCreateTodoPreset` | `EnvironmentsSection.tsx:187-204` | `devops_publication_presets` | 2 full → 1 GET* + 1 chico |
| `handleSaveAsDraft` | `PublicationsSection.tsx:179-199` | `devops_pipeline_drafts` | 2 full → 1 GET* + 1 chico |

\* `handleSaveAsDraft` y `handleCreateTodoPreset` APPEND-ean sobre el valor persistido
(necesitan la base fresca de ESA key para no perder ítems agregados por otra vista y
para calcular `draftNameForPreset` sin colisión). Conservan su GET previo del profile
pero la ESCRITURA pasa a `saveProfileKey` (payload de subida chico y sin riesgo de
pisar OTRAS keys). Los otros 4 callers editan una copia local que ES la fuente de
edición ⇒ 1 solo request. En los 6, `bootstrapEnabled` se pasa como
`ctx.health.bootstrap_enabled === true`.

Ejemplo de migración (patrón para los 6 — `saveDraft` del builder):

```ts
  const saveDraft = async (newDrafts: typeof drafts) => {
    if (!activeProject) return;
    try {
      setActionError(null);
      // Plan 98 — escritura por clave (PATCH con flag ON; riel GET→merge→PUT con OFF).
      await saveProfileKey(activeProject, 'devops_pipeline_drafts', newDrafts,
        ctx.health.bootstrap_enabled === true);
      setDrafts(newDrafts);
      setLoadedSnapshot(spec);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error desconocido';
      setActionError(`No se pudieron guardar los borradores: ${msg}`);
      throw e;
    }
  };
```

(`mergeDraftsIntoProfile` de `specBuilder.ts` deja de usarse en el componente — se
conserva exportado en `specBuilder.ts` porque tiene tests propios del plan 87; NO se
borra en este plan.)

**Tests PRIMERO (TDD)** — archivo nuevo
`Stacky Agents/frontend/src/devops/profileKeys.test.ts`, 5 casos (unit con
`vi.mock('../api/client')`):

1. `con flag ON hace PATCH a la URL exacta con body {value}` — spy de `api.patch`
   recibe `/api/projects/p1/client-profile/keys/devops_pipeline_drafts` y
   `{ value: [...] }`; `api.get`/`api.put` NO llamados.
2. `con flag OFF ejecuta GET→merge→PUT` — `api.get` mock devuelve
   `{ profile: { otra_key: 1 } }`; `api.put` recibe profile con `otra_key: 1` intacta
   MÁS la key nueva (merge preserva).
3. `con flag OFF y profile ausente parte de {}` — `api.get` devuelve `{}` ⇒ PUT con
   `{ profile: { [key]: value } }`.
4. `propaga errores del PATCH` — `api.patch` rechaza ⇒ `saveProfileKey` rechaza (los
   callers muestran su error actual).
5. `encodeURIComponent en project` — project `mi proyecto` produce URL con
   `mi%20proyecto`.

Más 2 greps de integración agregados a `DevOpsBootstrap.test.ts` (F4):

7. `los 3 componentes importan saveProfileKey` — el fuente de cada sección contiene
   `from '../../devops/profileKeys'`.
8. `ningún componente devops re-implementa el PUT full` — el fuente de
   `PipelineBuilderSection.tsx`, `PublicationsSection.tsx` y
   `EnvironmentsSection.tsx` NO contiene `api.put(` (la única escritura vive en
   `profileKeys.ts`; la lectura `api.get` del fallback/append sí está permitida).

**Comandos:**

```
npx vitest run src/devops/profileKeys.test.ts
npx vitest run src/pages/__tests__/DevOpsBootstrap.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** 5 + 8 tests vitest verdes, `tsc --noEmit` 0
errores, y con flag OFF el flujo de guardado dispara EXACTAMENTE los mismos 2 requests
que hoy (verificable en Network y por el caso 2 del unit).
**Flag:** `STACKY_DEVOPS_BOOTSTRAP_ENABLED` vía `ctx.health.bootstrap_enabled`.
**Impacto por runtime:** NINGUNO. Fallback: flag OFF ⇒ riel GET→merge→PUT intacto
dentro del helper.
**Trabajo del operador:** ninguno.

---

## F6 — Cierre: ratchet, verificación manual y checklist binario

**Objetivo:** registrar los tests en el ratchet, correr la verificación integral y
dejar el checklist auditable.

**Archivos a editar:**
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` y
  `Stacky Agents/backend/scripts/run_harness_tests.sh` — agregar a
  `HARNESS_TEST_FILES` (patrón `run_harness_tests.ps1:127-129`):

```
  "tests/test_plan98_bootstrap_flag.py",
  "tests/test_plan98_profile_key_validators.py",
  "tests/test_plan98_profile_key_patch.py",
  "tests/test_plan98_bootstrap_endpoint.py",
```

**Verificación manual (HITL, 5 minutos, con la app corriendo):**
1. Flag OFF (default): abrir el panel DevOps con Network abierto ⇒ mismos requests que
   antes (3 GET client-profile al visitar las 3 secciones); guardar un preset ⇒
   GET + PUT. `GET /api/devops/bootstrap?project=X` a mano ⇒ 404.
2. Activar la flag en Configuración → Arnés (categoría DevOps) ⇒ recargar el panel ⇒
   1 solo `GET /api/devops/bootstrap` y CERO `GET client-profile` de las secciones;
   guardar un preset ⇒ 1 solo `PATCH .../keys/devops_publication_presets`.
3. Editar un draft en Pipelines y un preset en Publicaciones seguidos ⇒ releer el
   profile (`GET client-profile`) ⇒ ambas keys presentes (nadie pisó a nadie).

**Checklist binario (cada ítem pasa/falla):**
- [ ] Flag `STACKY_DEVOPS_BOOTSTRAP_ENABLED` default OFF; con OFF: bootstrap y PATCH
      responden 404, el frontend dispara los MISMOS requests que antes del plan
      (byte-idéntico), y los 4 archivos `test_plan98_*.py` + meta-tests del arnés
      están verdes.
- [ ] `FlagSpec` sin kwarg `default`; arista en `_REQUIRES_MAP_FROZEN`;
      `test_harness_flags.py`, `test_harness_flags_requires.py` y
      `test_harness_flags_help.py` verdes.
- [ ] PUT full: contrato intacto — `test_plan87_devops_flag.py`,
      `test_plan88_publications_flag.py`, `test_plan89_environments_flag.py` verdes
      SIN modificarlos.
- [ ] Paridad PUT/PATCH: mismos strings de error para los mismos payloads inválidos
      (`test_patch_400_invalid_value_same_error_as_put`).
- [ ] PATCH nunca pisa otras keys (`test_patch_preserves_other_keys`) y
      `{"value": null}` borra la key (`test_patch_null_deletes_key`).
- [ ] Bootstrap devuelve health idéntico a `/health`
      (`test_bootstrap_health_matches_health_endpoint`) y normaliza keys corruptas
      sin 500 (`test_bootstrap_corrupt_keys_normalized`).
- [ ] Con flag ON: 2 requests para hidratar el panel (health + bootstrap) y 1 request
      por guardado simple (verificación manual, pasos 2-3).
- [ ] `tsc --noEmit` 0 errores; vitest por archivo verdes
      (`DevOpsBootstrap.test.ts`, `profileKeys.test.ts`) + los existentes del panel
      sin modificar.
- [ ] Los 4 tests backend registrados en `run_harness_tests.sh` Y `.ps1`.
- [ ] `DEVOPS_SECTIONS`, el gate declarativo del shell y `DevOpsAgentSection` /
      `ServersSection` / `TriggerPipelineSection` sin cambios de contrato (los dos
      últimos no tocan client-profile; el agente queda fuera de scope).

**Trabajo del operador:** opt-in (default off) — activar 1 flag por UI si quiere la
carga rápida; nada más.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| PATCHes concurrentes a la MISMA key (dos tabs editando presets) siguen siendo last-write-wins | Igual que hoy (el PUT full también lo era para la key propia); alcance aceptado y documentado. El plan ELIMINA la clase peor (pisar OTRAS keys). Resolver conflictos de la misma key exigiría versionado/ETag: fuera de scope v1 (mono-operador). |
| El bootstrap queda stale si el operador edita el `process_catalog` en Configuración → Perfil del cliente y vuelve al panel | react-query refetchea por defecto al re-enfocar la ventana (`refetchOnWindowFocus`); además el gate del catálogo en Publicaciones ya muestra aviso si está vacío. Invalidaciones cross-página finas: fuera de scope v1. |
| Drift entre validadores del PUT y del PATCH con el tiempo | Imposible sin romper tests: ambos consumen `validate_profile_key` (F1) y `test_patch_400_invalid_value_same_error_as_put` fija la paridad. |
| El refactor F1 cambia sin querer un mensaje de error del PUT | Los strings se MUEVEN, no se reescriben; `test_put_uses_shared_validators_same_errors` + los tests de 87/88/89 sin modificar actúan de arnés. |
| Con flag ON y la query de bootstrap fallando (backend caído a medias), las secciones quedan sin datos | `retry: false` + el error queda visible en el shell (mismo patrón del health). La sección no rompe: estados iniciales vacíos, y el operador puede apagar la flag (kill-switch por UI). |
| `save_client_profile` normaliza el profile y el PATCH podría devolver un `value` distinto al enviado | Comportamiento CORRECTO y explícito: la respuesta trae `normalized.get(key)` (la verdad persistida), igual que el PUT devuelve `profile` normalizado. Los callers actuales ya setean su estado local con su copia; no dependen de la respuesta. |
| Secciones que NO entran al bootstrap (Agente DevOps: projects + conversations) mantienen sus requests | Declarado fuera de scope: son queries react-query propias con caché (`DevOpsAgentSection.tsx:40-56`) y dependen de otro dominio (conversaciones). Sumarlas al bootstrap acoplaría dominios sin necesidad. |
| El lock de proceso no cubre despliegues multi-proceso | Stacky es mono-operador con un solo backend Flask (sustrato sin auth); si algún día hay multi-proceso, el lock migra a lock de archivo en `save_client_profile` — fuera de scope v1. |

## 6. Fuera de scope (v1)

- PATCH para keys NO-devops (`process_catalog`, identidad, `language`, `build`…): la
  allowlist v1 es EXACTAMENTE las 4 keys devops. Ampliarla es 1 línea + tests en un
  plan futuro (el mecanismo queda listo).
- Versionado/ETag/optimistic-locking por key (conflictos de la MISMA key entre tabs).
- Migrar las secciones DevOps a react-query completo (mutations, invalidation
  fina) — v1 solo agrega la query de bootstrap en el shell y el helper de escritura.
- Sumar al bootstrap los datos del Agente DevOps (projects/conversations) o del
  preview YAML (ese es otro cuello, candidato a plan propio "Preview sin espera").
- Tocar los planes 93-96 (pendientes) o el 34 (client-profile semántico): cero
  intersección de archivos salvo `api/client_profile.py`, donde este plan solo
  EXTRAE validadores y AGREGA una ruta.
- SSE/WebSockets para push de cambios del profile.
- Cambios en `ClientProfileEditor.tsx` (sigue usando GET/PUT full: correcto para su
  caso — edita el perfil entero).

## 7. Glosario

- **client-profile**: sección `client_profile` del `config.json` de un proyecto;
  única fuente de verdad de drafts/presets/settings del panel DevOps
  (`services/client_profile.py:266,315`).
- **Riel GET→merge→PUT**: patrón preexistente (87 v3 C1/C2) donde el frontend baja el
  profile ENTERO, mergea su key y sube el profile ENTERO, para no pisar otras keys.
  Este plan lo reemplaza (flag ON) por PATCH server-side y lo conserva como fallback.
- **Key devops (`devops_*`)**: keys del profile propiedad del panel DevOps
  (`devops_pipeline_drafts`, `devops_publication_presets`,
  `devops_publication_settings`, `devops_environment_settings`) — contrato §3.12.
- **Contrato §3.12 (Plan 87 v3)**: registro declarativo `DEVOPS_SECTIONS` + shell
  agnóstico; extensiones = keys ADITIVAS en health y en `DevOpsSectionContext`.
- **Health aditivo**: `GET /api/devops/health` SIEMPRE-200 con un boolean por
  feature; el frontend gatea secciones y comportamientos con esas keys.
- **Flag 5 patas**: alta completa de una flag = `config.py` + `FlagSpec` en
  `FLAG_REGISTRY` + `_CATEGORY_KEYS` + `harness_flags_help.py` +
  `harness_defaults.env` (+ arista en `_REQUIRES_MAP_FROZEN` si tiene `requires`).
- **Ratchet (Plan 49)**: todo archivo de test backend nuevo se registra en
  `HARNESS_TEST_FILES` de `run_harness_tests.sh`/`.ps1`, o el meta-test falla.
- **Last-write-wins**: el último que escribe pisa lo anterior. Hoy aplica al profile
  ENTERO (entre keys); con este plan queda acotado a la misma key.
- **Bootstrap**: respuesta agregada de `GET /api/devops/bootstrap` que hidrata el
  panel en un round-trip (health + profile_keys + servers).

## 8. Orden de implementación

1. F0 — flag 5 patas + key `bootstrap_enabled` en health + arista R4 + tests.
2. F1 — `services/client_profile_keys.py` (extracción) + refactor del PUT + tests de
   paridad + no-regresión 87/88/89.
3. F2 — endpoint PATCH + lock + tests (mismo commit que F1 o inmediatamente después:
   depende de `validate_profile_key`).
4. F3 — helper `_health_payload()` + endpoint bootstrap + tests.
5. F4 — endpoints.ts + query en el shell + early-path de hidratación en las 3
   secciones + tests vitest + `tsc`.
6. F5 — `profileKeys.ts` + migración de los 6 callers + tests vitest + `tsc`.
7. F6 — ratchet (sh + ps1) + verificación manual HITL + checklist binario.

## 9. Definición de Hecho (DoD)

- F0: 5 tests verdes (`test_plan98_bootstrap_flag.py`) + 3 archivos de meta-tests del
  arnés verdes; flag visible en Configuración → Arnés, categoría DevOps, default OFF.
- F1: 8 tests verdes (`test_plan98_profile_key_validators.py`) + tests de 87/88/89
  verdes sin modificar.
- F2: 9 tests verdes (`test_plan98_profile_key_patch.py`).
- F3: 7 tests verdes (`test_plan98_bootstrap_endpoint.py`).
- F4: 6 tests vitest verdes (`DevOpsBootstrap.test.ts`) + `tsc --noEmit` 0 errores.
- F5: 5 tests vitest verdes (`profileKeys.test.ts`) + 2 greps agregados a
  `DevOpsBootstrap.test.ts` verdes + `tsc --noEmit` 0 errores.
- F6: 4 archivos registrados en ambos ratchets; verificación manual de los 3 pasos
  HITL documentada en el reporte de implementación (requests observados en Network).
- Global: con `STACKY_DEVOPS_BOOTSTRAP_ENABLED` OFF el sistema es byte-idéntico al
  estado previo (endpoints nuevos 404, mismos requests del frontend); con ON, el KPI
  de §1 se cumple: 2 requests para hidratar el panel y 1 request por guardado simple;
  ninguna key del profile puede ser pisada por la escritura de otra key.
- Impacto en los 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro):
  NINGUNO — ningún runner, prompt ni harness consume los endpoints tocados;
  verificable por grep de `client-profile` y `devops/bootstrap` fuera de
  `frontend/` + `api/` + `tests/`.
