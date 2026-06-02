# Plan — Auto-llenado de rutas en el Client Profile (todo lleno por defecto, salvo BD)

> **Versión:** 1.0 — Propuesta
> **Fecha:** 2026-06-02
> **Autor:** Asistente Stacky
> **Estado:** PROPUESTA — pendiente de implementación
> **Alcance:** Que el editor del *Perfil del cliente* (Settings → Perfil del cliente) **arranque completamente lleno** con el layout estándar de `trunk/` (rutas idénticas en todos los proyectos), manteniendo todo **editable** y persistiendo una **copia por proyecto**. Único bloque excluido del auto-llenado: **`database`** (server/credencial siguen siendo manuales por proyecto).
> **Workstream padre:** continúa el [Plan 16 — Generalización de Agentes multi-cliente](./16_PLAN_GENERALIZACION_AGENTES_MULTI_CLIENTE.md).

---

## 0. Resumen ejecutivo (lectura de 2 minutos)

### El problema

Todos los proyectos de la org comparten **exactamente la misma estructura interna de repo**: el código vive dentro de `trunk/` con rutas idénticas (`trunk/OnLine`, `trunk/Batch`, `trunk/BD/...`, `trunk/lib`, `trunk/Tests`, `trunk/docs/agentic_manual/...`). Lo **único que cambia por proyecto** es dónde está clonado el repo en disco — el `workspace_root`.

Hoy el editor del client profile muestra esas rutas, pero con fricciones:

1. Si un perfil está **parcial** (campo ausente porque se editó a mano, se importó, o se creó con un template viejo), el formulario muestra ese campo **vacío** y la ruta estándar aparece solo como *placeholder gris* — el operador tiene que volver a tipearla aunque sea siempre la misma.
2. Un proyecto sin perfil persistido se marca como **"Usando defaults / sin configurar"** y el bloque de contexto que reciben los agentes lleva la nota *"perfil no configurado por el operador… confirmá rutas/estados"*, aun cuando las rutas son las de siempre.
3. No hay **ninguna validación** de que `workspace_root + ruta` exista realmente en disco → el error clásico de apuntar `workspace_root` a `.../trunk` (en vez de a la raíz del repo) produce rutas duplicadas `.../trunk/trunk/OnLine` que nadie detecta hasta que el agente falla.

### La meta

- **Todo lleno por defecto.** Al abrir el perfil de cualquier proyecto, todas las secciones (salvo `database`) arrancan **pobladas con el layout estándar** — no como placeholder, sino como valor real editable.
- **Auto-resuelto.** Las rutas se completan solas desde una única fuente canónica (el template default del tracker). El operador no las tipea: solo las ajusta si ese proyecto es la excepción.
- **Editable + copia por proyecto.** Cada proyecto guarda su propia copia (decisión del operador, ver §2). Editar un proyecto no afecta a los demás.
- **BD aparte.** El bloque `database` **no** se auto-llena: server, usuario y credencial los carga el operador a mano (la credencial sigue cifrada con DPAPI, fuera del perfil).
- **Guard de rutas.** Avisar (sin bloquear) cuando `workspace_root + ruta` no exista en disco, atrapando el problema de doble-`trunk` y los typos.

### Por qué es seguro

- No cambia el **schema** (`schema_version` sigue en 1) ni el contrato de los endpoints existentes — solo **agrega** un campo de respuesta y un helper.
- El auto-llenado es un **merge no destructivo**: lo que el operador ya guardó **siempre gana** sobre el default.
- `database` queda intacto, así que no hay riesgo de inyectar un server por defecto equivocado.

---

## 1. Estado actual (cómo funciona hoy)

### 1.1 Dónde viven los datos

| Pieza | Archivo | Rol |
|-------|---------|-----|
| Template estándar por tracker | `backend/services/client_profile_defaults/{azure_devops,jira,mantis}.json` | Fuente canónica del layout (rutas `trunk/...` ya pobladas para ADO). |
| Servicio | `backend/services/client_profile.py` | `get_default_client_profile`, `validate_client_profile`, `load/save/clear`, `merge_with_defaults`, `_deep_merge`. |
| Endpoints | `backend/api/client_profile.py` | `GET/PUT/DELETE /api/projects/<name>/client-profile`, `GET /api/client-profile/default`, `POST/GET .../db-readonly-auth`. |
| Seed en creación | `backend/project_manager.py::initialize_project` (líneas ~161-169) | Todo proyecto nuevo arranca con `client_profile = get_default_client_profile(tracker)`. |
| Inyección a agentes | `backend/services/context_enrichment.py::_inject_client_profile_block` | Inyecta el bloque `client-profile`; si no hay perfil cae al default con nota *"sin configurar"*. |
| Editor UI | `frontend/src/components/ClientProfileEditor.tsx` | Formulario por secciones + toggle "Avanzado (JSON)". |

### 1.2 El dato decisivo: `workspace_root` es la **raíz del repo**, no `trunk`

Config real de `backend/projects/RSPACIFICO/config.json`:

```jsonc
"workspace_root": "C:/Desarrollo/GIT/RS/RSPACIFICO",          // raíz del repo (contiene trunk/)
"client_profile": {
  "code_layout": {
    "online_path": "trunk/OnLine",                            // → C:/.../RSPACIFICO/trunk/OnLine  ✅
    "batch_path":  "trunk/Batch",
    "db_scripts_path": "trunk/BD/1 - Inicializacion BD",
    "lib_path": "trunk/lib",
    "test_path": "trunk/Tests"
  },
  "docs_indexes": {
    "technical_master": "trunk/docs/agentic_manual/tecnica/00_INDICE_MAESTRO.md",
    ...
  }
}
```

Y el `Developer.agent.md` (líneas 40, 84-98) confirma cómo se consumen:

```
{workspace_root}/{client_profile.code_layout.online_path}/   → código UI/online
{workspace_root}/{client_profile.docs_indexes.technical_master}
```

> ⚠️ **Inconsistencia detectada:** el docstring de ejemplo en `project_manager.py` (líneas 12, 291, 338, 346) muestra `workspace_root: "C:/Repos/RSPacifico/trunk"` (apuntando **dentro** de trunk). Con ese valor + las rutas `trunk/...` del template, el agente armaría `.../trunk/trunk/OnLine` (doble trunk → ruta inexistente). La config real **no** tiene ese bug, pero el ejemplo induce al error. Se corrige en §5.

**Conclusión:** las rutas del perfil (`code_layout.*` + `docs_indexes.*`) son **constantes `trunk/...` en todos los proyectos**; la única variable por proyecto es `workspace_root`. Eso es justo lo que habilita auto-llenarlas.

### 1.3 El flujo de carga del editor (hoy)

`ClientProfileEditor.tsx` (líneas 377-385):

```ts
const initial = profileQuery.data.has_profile
  ? profileQuery.data.profile          // perfil guardado tal cual (puede estar parcial)
  : profileQuery.data.default_template; // sin perfil → template default
setBaseProfile((initial ?? {}) as ClientProfile);
```

- Los campos leen de `baseProfile` con `gs(path)`; el *placeholder* sale de `default_template` con `ph(path)`.
- **Gap:** si `baseProfile` (perfil guardado) tiene un campo ausente, `gs()` devuelve `""` → el input queda **vacío**, y la ruta estándar solo se ve como placeholder gris. No se materializa.

---

## 2. Decisiones tomadas (acordadas con el operador)

| # | Pregunta | Decisión |
|---|----------|----------|
| Q1 | ¿Cómo manejar las rutas estándar (idénticas en todos los proyectos)? | **Pre-llenar copia por proyecto.** Cada proyecto arranca con el layout estándar copiado en su `config.json`; es editable y la edición es local a ese proyecto. (Se descarta el "layout global compartido + overrides" por simplicidad y por mantener cada `config.json` autocontenido.) |
| Q2 | ¿Qué campos quedan "todo lleno" por defecto? | **Todo el formulario excepto la sección `database`.** Se pre-llenan `code_layout`, `language`, `build`, `conventions`, `docs_indexes`, `tracker_state_machine`, `terminology`, `extensions`. La sección `database` (server / usuario / credencial) **se mantiene manual** por proyecto. |

> Nota sobre "todo lleno": el auto-llenado solo materializa los campos que el **template trae con valor**. Los campos que en el template están vacíos porque son intrínsecamente por-proyecto (`build.online_solutions`, `terminology.product_name`/`client_label`) seguirán vacíos — no hay un default universal sensato para ellos y el placeholder ya guía al operador.

---

## 3. Diseño de la solución

### 3.1 Núcleo: helper `complete_client_profile(...)`

Un único punto de verdad para "completar un perfil con el layout estándar, salvo BD". Se apoya en el `_deep_merge` que ya existe.

```python
# backend/services/client_profile.py

PREFILL_SKIP_SECTIONS: frozenset[str] = frozenset({"database"})

def complete_client_profile(
    profile: dict | None,
    tracker_type: str | None = None,
    skip_sections: frozenset[str] = PREFILL_SKIP_SECTIONS,
) -> dict:
    """Devuelve el perfil con TODAS las secciones pobladas desde el template
    default del tracker, EXCEPTO las de `skip_sections` (por defecto `database`).

    - Merge no destructivo: lo que ya trae `profile` gana sobre el default.
    - Las secciones en `skip_sections` se devuelven tal cual vienen en `profile`
      (no se les inyecta el default): así `database` nunca recibe un server por
      defecto equivocado.
    - Idempotente: completar dos veces da el mismo resultado.
    """
    default = get_default_client_profile(tracker_type)
    base = {k: v for k, v in (default or {}).items() if k not in skip_sections}
    completed = _deep_merge(base, profile or {})
    completed["schema_version"] = SCHEMA_VERSION
    return completed
```

> Diferencia con el `merge_with_defaults` existente: ese mergea **todas** las secciones (incluida `database`). `complete_client_profile` respeta `skip_sections`. Se mantienen ambos: `merge_with_defaults` para la inyección de contexto completa (si se decide), `complete_client_profile` para el editor.

### 3.2 Endpoint GET: devolver el perfil ya completado

`api/client_profile.py::get_client_profile` agrega un campo `prefilled_profile` que el formulario usa como estado inicial (sin tocar `profile` crudo ni `default_template`, que se siguen devolviendo):

```python
return jsonify({
    "ok": True,
    "project": project_name,
    "tracker_type": tracker_type,
    "has_profile": has_profile,
    "profile": profile,                                  # crudo (lo que está en disco)
    "default_template": get_default_client_profile(tracker_type),
    "prefilled_profile": complete_client_profile(profile, tracker_type),  # ← NUEVO: todo lleno salvo BD
    "path_check": _check_paths(project_name, profile, cfg),  # ← NUEVO §5 (warnings, no bloquea)
    "validation": validation_dict,
})
```

### 3.3 Frontend: arrancar desde `prefilled_profile`

`ClientProfileEditor.tsx`, en el `useEffect` de carga:

```ts
useEffect(() => {
  if (!profileQuery.data) return;
  // Arranca SIEMPRE completo (salvo BD). Si el backend no manda prefilled
  // (versión vieja), cae al comportamiento previo.
  const initial =
    profileQuery.data.prefilled_profile ??
    (profileQuery.data.has_profile
      ? profileQuery.data.profile
      : profileQuery.data.default_template);
  setBaseProfile((initial ?? {}) as ClientProfile);
  setWarnings(profileQuery.data.validation?.warnings ?? []);
  setAdvancedJson(null);
}, [profileQuery.data]);
```

Efecto: cada campo no-BD muestra su **valor real editable** (no placeholder). La sección `database` queda como hoy (vacía → placeholder), porque `prefilled_profile` no inyecta defaults de BD.

Ajustes UI adicionales:

- **Badge de estado:** hoy "Configurado" vs "Usando defaults". Agregar un estado intermedio claro: si `!has_profile` pero el formulario ya está pre-llenado, mostrar *"Pre-llenado con layout estándar (guardá para fijarlo)"* en vez de *"Usando defaults"*. Una vez guardado → "Configurado".
- **Nota en la sección "Estructura de código":** *"Rutas estándar de `trunk/` — iguales en todos los proyectos. Editá solo si este repo difiere."*
- **Resolución de rutas (§5):** debajo de cada ruta (o como bloque al pie de la sección) mostrar el resultado del `path_check`: `✓ trunk/OnLine → C:/…/RSPACIFICO/trunk/OnLine` o `⚠️ no existe en disco`.

### 3.4 Seed en creación (sin cambios funcionales, intención explícita)

`project_manager.py::initialize_project` ya siembra `get_default_client_profile(tracker)`. Como el default ya trae el layout `trunk/...`, los proyectos nuevos arrancan llenos. Se mantiene; solo se documenta que el seed = layout estándar. (Opcional: usar `complete_client_profile(None, tracker)` para dejar la intención explícita; el resultado es equivalente.)

### 3.5 Inyección de contexto a agentes (opcional, recomendado)

`context_enrichment.py::_inject_client_profile_block`: hoy inyecta el perfil crudo (o el default si no hay). Para que los agentes reciban siempre las rutas completas aunque el perfil guardado esté parcial, envolver el perfil con `complete_client_profile(profile, tracker)` antes de serializar. La nota *"sin configurar"* se mantiene solo cuando **no** hay perfil persistido. Mantiene la feature flag `STACKY_INJECT_CLIENT_PROFILE`.

---

## 4. Cambios archivo por archivo

| Archivo | Cambio | Tipo |
|---------|--------|------|
| `backend/services/client_profile.py` | + `PREFILL_SKIP_SECTIONS`, + `complete_client_profile(...)`, + export en `__all__`. | Backend (núcleo) |
| `backend/services/client_profile.py` | + `resolve_layout_paths(profile, workspace_root)` y/o `validate_paths_against_workspace(...)` → warnings (§5). | Backend (núcleo) |
| `backend/api/client_profile.py` | GET: agregar `prefilled_profile` y `path_check` a la respuesta. Sin romper campos existentes. | Backend (API) |
| `backend/project_manager.py` | Corregir docstring/ejemplos de `workspace_root` (raíz del repo, no `.../trunk`). Opcional: seed vía `complete_client_profile`. | Backend |
| `frontend/src/api/endpoints.ts` | Tipar `prefilled_profile?: ClientProfile` y `path_check?: {...}` en la respuesta de `ClientProfileApi.get`. | Frontend (tipos) |
| `frontend/src/components/ClientProfileEditor.tsx` | Arrancar `baseProfile` desde `prefilled_profile`; badge intermedio; nota en sección de rutas; render del `path_check`. | Frontend (UI) |
| `frontend/src/components/ClientProfileEditor.module.css` | Estilos para el badge intermedio y las líneas de resolución de ruta (✓/⚠️). | Frontend (estilos) |
| `backend/services/context_enrichment.py` | (Opcional) envolver con `complete_client_profile` antes de inyectar. | Backend |
| `backend/tests/test_client_profile.py` | Tests de `complete_client_profile` + resolución de rutas. | Tests |
| `backend/tests/test_client_profile_endpoints.py` | Test: GET devuelve `prefilled_profile` (no-BD lleno, BD vacío) y `path_check`. | Tests |

---

## 5. Validación de rutas (`workspace_root` + trunk) — el guard de correctitud

Esto materializa la parte de "que lo **resuelva** automáticamente": no solo prellenar, sino **verificar** que la ruta resuelve a algo real.

```python
# backend/services/client_profile.py
from pathlib import Path

_LAYOUT_PATH_KEYS = (
    ("code_layout", "online_path"),
    ("code_layout", "batch_path"),
    ("code_layout", "db_scripts_path"),
    ("code_layout", "lib_path"),
    ("code_layout", "test_path"),
    ("docs_indexes", "technical_master"),
    ("docs_indexes", "functional_online"),
    ("docs_indexes", "functional_batch"),
)

def resolve_layout_paths(profile: dict, workspace_root: str) -> list[dict]:
    """Para cada ruta del layout, devuelve {section, key, rel, abs, exists}.
    No lanza; rutas vacías se omiten. `exists` permite que la UI avise."""
    out: list[dict] = []
    root = Path(workspace_root) if workspace_root else None
    for section, key in _LAYOUT_PATH_KEYS:
        rel = ((profile.get(section) or {}).get(key) or "").strip()
        if not rel:
            continue
        abs_path = (root / rel) if root else None
        out.append({
            "section": section, "key": key, "rel": rel,
            "abs": str(abs_path).replace("\\", "/") if abs_path else "",
            "exists": bool(abs_path and abs_path.exists()),
        })
    return out
```

El endpoint expone esto como `path_check`; la UI lo pinta. Casos que atrapa:

- **Doble trunk:** `workspace_root = .../trunk` + `online_path = trunk/OnLine` → `.../trunk/trunk/OnLine` no existe → ⚠️. La UI puede sugerir: *"¿`workspace_root` apunta dentro de `trunk`? Debería ser la raíz del repo."*
- **Typos** en rutas editadas a mano.
- **Repo no clonado** todavía en esa máquina.

> Es **solo warning**: nunca bloquea el guardado (el repo puede no estar clonado en la máquina que edita la config). Encaja con el patrón "validación tolerante" que ya usa `validate_client_profile`.

Además: corregir los ejemplos de `workspace_root` en `project_manager.py` para que muestren la **raíz del repo** (`C:/Repos/RSPacifico`, no `C:/Repos/RSPacifico/trunk`) y agregar un comentario de una línea explicando que las rutas del `code_layout` cuelgan de ahí.

---

## 6. Migración de proyectos existentes

Los proyectos ya creados pueden tener perfiles **parciales**. Dos caminos, no excluyentes:

1. **Auto-completado perezoso (incluido en el diseño):** al abrir el editor, `prefilled_profile` ya muestra todo lleno; al primer **Guardar**, la copia completa (salvo BD) queda persistida. Cero trabajo extra de migración para el operador que toque cada proyecto.
2. **Normalización batch (opcional):** un comando `backend/tools/normalize_client_profiles.py` (o función one-shot) que recorra `projects/*/config.json`, aplique `complete_client_profile` (preservando BD y lo ya configurado) y reescriba. Idempotente. Útil si se quiere dejar todos los proyectos consistentes sin abrir uno por uno.

> Recomendación: implementar (1) sí o sí; (2) como conveniencia. RSPACIFICO ya tiene el perfil completo, así que (2) es de bajo impacto inmediato pero conviene para futuros proyectos importados.

---

## 7. Tests

### Backend (`pytest`)

`test_client_profile.py` — nuevos:
- `complete_client_profile` rellena `code_layout`/`docs_indexes`/`build`/`conventions`/`language`/`tracker_state_machine` desde el default.
- **No** toca `database`: si `profile` no trae `database`, el resultado no tiene `database` poblado con el default (queda como vino).
- Lo que trae el perfil **gana** sobre el default (override de una ruta no se pisa).
- Idempotencia: `complete(complete(p)) == complete(p)`.
- `resolve_layout_paths`: marca `exists=False` para rutas inexistentes; omite rutas vacías; arma bien el absoluto con separadores `/`.

`test_client_profile_endpoints.py` — nuevos:
- GET devuelve `prefilled_profile` con secciones no-BD pobladas y `database` vacío/ausente.
- GET devuelve `path_check` con la forma esperada cuando el proyecto tiene `workspace_root`.
- Regresión: `profile`, `default_template`, `has_profile`, `validation` siguen presentes e intactos.

### Frontend (verificación manual / UI)
- Proyecto nuevo: el formulario abre con rutas y demás campos no-BD llenos; BD vacía.
- Editar una ruta → guardar → recargar: la edición persiste (copia por proyecto).
- Perfil parcial (borrar un campo en "Avanzado JSON" y volver a Formulario) → el campo se re-llena desde el estándar.
- `path_check`: con `workspace_root` correcto muestra ✓; forzando `.../trunk` muestra ⚠️ doble-trunk.

---

## 8. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Auto-llenar pisa una personalización del operador. | Merge **no destructivo**: el perfil guardado siempre gana. Solo se rellenan campos **ausentes**. |
| Inyectar un server de BD por defecto equivocado. | `database` está **excluido** del auto-llenado (decisión Q2). |
| `path_check` da falsos ⚠️ porque el repo no está clonado en la máquina de configuración. | Es **warning informativo**, nunca bloquea guardar. Texto claro: *"no encontrado en esta máquina"*. |
| Romper el contrato del endpoint GET. | Solo se **agregan** campos (`prefilled_profile`, `path_check`); los existentes no cambian. Frontend cae al comportamiento previo si faltan. |
| Confusión `workspace_root` = repo root vs trunk. | Se corrigen ejemplos en `project_manager.py` y el `path_check` detecta el doble-trunk activamente. |
| El template estándar cambia y los proyectos viejos quedan desfasados (porque es copia por proyecto). | Aceptado por decisión Q1. La normalización batch (§6.2) permite re-sincronizar cuando haga falta. |

---

## 9. Checklist de implementación (orden sugerido)

- [ ] **B1.** `client_profile.py`: `PREFILL_SKIP_SECTIONS` + `complete_client_profile` + export. Tests.
- [ ] **B2.** `client_profile.py`: `resolve_layout_paths` (+ helper `_check_paths` del endpoint). Tests.
- [ ] **B3.** `api/client_profile.py`: GET devuelve `prefilled_profile` + `path_check`. Tests de endpoint.
- [ ] **B4.** `project_manager.py`: corregir ejemplos de `workspace_root`; (opcional) seed vía `complete_client_profile`.
- [ ] **F1.** `endpoints.ts`: tipar `prefilled_profile` y `path_check`.
- [ ] **F2.** `ClientProfileEditor.tsx`: estado inicial desde `prefilled_profile`; badge intermedio; nota de rutas estándar; render de `path_check`.
- [ ] **F3.** `ClientProfileEditor.module.css`: estilos badge + líneas ✓/⚠️.
- [ ] **B5.** (Opcional) `context_enrichment.py`: envolver con `complete_client_profile`.
- [ ] **M1.** (Opcional) `tools/normalize_client_profiles.py` — normalización batch idempotente.
- [ ] **V.** Correr `pytest backend/tests/test_client_profile*.py` + verificación manual UI (§7).

---

## 10. Fuera de alcance (explícito)

- **Layout global compartido entre proyectos** (descartado en Q1 a favor de copia por proyecto).
- **Auto-llenado de `database`** / autodescubrimiento de server (excluido en Q2).
- **Auto-detección/edición de `workspace_root`** (solo se valida y se avisa; no se reescribe automáticamente).
- **Cambios de schema** (`schema_version` permanece en 1).
- Cualquier cambio a los `.agent.md` más allá de corregir documentación de rutas si hiciera falta.

---

### Apéndice A — Mapa de "qué se llena" vs "qué queda manual"

| Sección | Auto-llenado | Notas |
|---------|:---:|-------|
| `code_layout` (rutas + extensiones + capas) | ✅ | Layout `trunk/...` estándar. |
| `language` | ✅ | `primary`, `comment_traceability`, `ticket_token_pattern`, `languages_in_ridioma`. |
| `build` | ✅ (lo constante) | `tool`, `msbuild_path`, `configuration`, `batch_proj_glob`. `online_solutions` queda vacío (por-proyecto). |
| `conventions` | ✅ | `ridioma_helper`, `ridioma_message_const`, `string_sanitizer`, `error_helpers`. |
| `docs_indexes` | ✅ | Rutas `trunk/docs/agentic_manual/...`. |
| `tracker_state_machine` | ✅ | Estados functional/technical/developer del tracker. |
| `terminology` | ✅ (lo constante) | `product_name`/`client_label` quedan vacíos (por-proyecto). |
| `extensions` | ✅ | `{}` por defecto; preservado tal cual si el operador lo usa. |
| **`database`** | ❌ **manual** | `server`, `readonly_user_hint`, etc. + credencial DPAPI aparte. |

---

## 11. Hallazgo en implementación — causa raíz real (2026-06-02)

> **Estado:** IMPLEMENTADO. El plan §3 (núcleo + endpoint + UI) ya estaba aplicado en el commit previo, pero **seguían apareciendo las advertencias** y el Developer arrancaba con `client-profile no inyectado`. La causa real **no estaba contemplada en el plan** y vivía en el **empaquetado del release**, no en la lógica del perfil.

### 11.1 Causa raíz #1 — los templates JSON no se empaquetaban en el build congelado

El backend se distribuye **congelado con PyInstaller** (`deployment/build_release.ps1`, `--onedir`). El comando usaba `--collect-submodules services`, que empaqueta los módulos `.py` del paquete **pero no los archivos de datos** `services/client_profile_defaults/*.json`. En el deploy:

- `get_default_client_profile()` no encontraba ningún JSON → devolvía `{"schema_version": 1}` **vacío**.
- El editor mostraba un "template default" vacío; **guardarlo persistía `{"schema_version": 1}`** → el validador avisaba `code_layout / language / tracker_state_machine ausente` (síntoma 1).
- `initialize_project` sembraba a los proyectos nuevos con ese template vacío → p. ej. `projects/RSSICREA/config.json` quedó con `client_profile = {"schema_version": 1}`.

> Desde el código fuente (`python app.py`) **nunca se reproducía**, porque ahí los JSON sí están en disco. El bug era exclusivo del `.exe` congelado.

**Fix:**
- Nuevo módulo `services/client_profile_default_templates.py` con los 3 templates embebidos como dicts Python. PyInstaller **sí** los empaqueta (import estático), así que el default nunca queda vacío.
- `_read_default_template` ahora resuelve: (1) JSON en disco si existe (dev/overrides) → (2) fallback embebido. Nunca devuelve vacío.
- `build_release.ps1`: se agregó `--collect-data services` (defensa en profundidad: empaqueta también los JSON en disco).
- Test de drift `test_embedded_templates_match_json` + simulación frozen `test_default_template_works_without_json_files`.

### 11.2 Causa raíz #2 — la inyección no completaba perfiles parciales/vacíos (§3.5 nunca implementado)

`context_enrichment._inject_client_profile_block` inyectaba el perfil **crudo** y solo caía al default cuando el perfil era `None`. Un perfil vacío como el de RSSICREA (`{"schema_version": 1}`, que **es** un dict) se inyectaba tal cual, sin layout → el Developer no veía rutas y narraba `client-profile no inyectado — operando con fallbacks` (síntoma 2). El §3.5/B5 del plan ("envolver con el default antes de inyectar") **no se había implementado**.

**Fix:** la inyección ahora completa **siempre** con `merge_with_defaults(profile, tracker)` (incluye `database` —que el agente necesita—, a diferencia de `complete_client_profile` del editor). Un perfil vacío se trata como "sin configurar" (conserva la nota) pero igual recibe el layout estándar completo. Tests: `test_completes_partial_profile_with_standard_layout`, `test_empty_profile_treated_as_unconfigured`.

### 11.3 Para que el fix llegue al deploy

El backend congelado **debe reconstruirse** (`deployment/build_release.ps1`) para tomar el código nuevo. Tras reconstruir: proyectos nuevos se siembran completos; proyectos ya creados con perfil vacío (RSSICREA) se auto-completan al inyectar y muestran el formulario lleno (basta volver a **Guardar** para fijarlo). Alternativa sin rebuild: pegar el perfil completo en *Avanzado (JSON)* y Guardar.
