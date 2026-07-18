# Plan 190 — DevOps: equipaje portable — secciones export/import de servers y apps + re-credencialización HITL

- **Versión:** v2 (CRITICADO — APROBADO-CON-CAMBIOS; v1 → v2 aplicada)
- **Fecha:** 2026-07-18
- **Autor:** StackyArchitectaUltraEficientCode (pipeline proponer-plan-stacky → criticar-y-mejorar-plan)
- **Serie:** DevOps (91 registro de servidores + 120 Centro de Despliegues + transferencia de config existente)

## Changelog v1 → v2 (crítica C1..C5 + adición)

- **C1 (IMPORTANTE — bug fáctico):** el overwrite de la v1 ("delete_server por cada alias local y
  recrear") HABRÍA BORRADO los passwords del keyring: `delete_server`
  (`server_registry.py:149-161`) también ejecuta `keyring.delete_password`. v2: overwrite es
  DIFF-BASED — borra SOLO los aliases ausentes del bundle (ahí el borrado de credencial es la
  semántica correcta del 91); los aliases presentes se upsertean SIN tocar el keyring. Test nuevo
  `test_overwrite_conserva_password_de_alias_reimportado`.
- **C2 (IMPORTANTE):** las secciones devops son GLOBALES (stores en `data_dir`) → viven en el TOP
  LEVEL del bundle all-projects (como `uiPreferences`); `available_sections(scope)` con scope
  `"all"|"project"`; las rutas per-proyecto (:160/:189) NUNCA las exportan y las saltean con
  `skipped_sections` al importar. Tests nuevos en F0/F2.
- **C3 (IMPORTANTE):** el shape del reporte dry-run NO se inventa: instrucción ejecutable de leer
  cómo reporta el dry-run existente (grep) y EXTENDER esa misma estructura con la clave adicional
  `devops`.
- **C4 (MENOR):** el campo libre `notes` de servers se exporta con masking determinista de prefijos
  de token (misma lista del plan 188: `ghp_`, `github_pat_`, `glpat-`, `xoxb-`, `xoxp-`, `AKIA`,
  `eyJhbGciOi` → `<posible-secreto-omitido>`).
- **C5 (MENOR):** DoD aclarado: `config_transfer.py` no llama keyring DIRECTO; los borrados de
  aliases ausentes delegan en `server_registry.delete_server` (semántica 91 intacta).
- **[ADICIÓN ARQUITECTO]:** `credentials_manifest` dentro de la sección `devopsServers` (aliases
  que TENÍAN password al momento del export). Al importar, el checklist distingue
  `credentials_pending` (tenía y falta — prioridad alta) de `credentials_never_set` (nunca tuvo —
  informativo). Cero secretos: el manifest es una lista de aliases.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Stacky ya tiene un sistema completo de export/import de configuración
(`api/config_transfer.py` + `services/config_transfer.py`: bundles con `schemaVersion`, checksum
canónico, modos `dry-run`/`merge`/`overwrite`, ledger de eventos y política de secretos) — pero su
catálogo `ALL_SECTIONS` (`services/config_transfer.py:73-81`) **no incluye NADA de DevOps**: ni los
servidores del registro 91 ni las apps×targets del Centro de Despliegues 120. Hoy, mover Stacky de
máquina, restaurar un backup o clonar el setup implica recargar servidores y apps A MANO. Este plan
agrega dos secciones nuevas al MISMO mecanismo — `devopsServers` y `devopsApps` — con la garantía de
secretos intacta (los passwords viven SOLO en el keyring, `services/server_registry.py:4-8`, y JAMÁS
viajan), y cierra el ciclo con **re-credencialización HITL**: tras importar, la respuesta lista qué
servidores quedaron sin contraseña local (`credentials_pending`) y la UI muestra el checklist para
re-vincularlas donde siempre (sección Servidores). Backup y migración DevOps en 1 click, sin
transportar jamás un secreto.

**KPI / impacto esperado (binarios, verificados por tests):**

| KPI | Métrica | Criterio binario |
|-----|---------|------------------|
| KPI-1 | Cero secretos en el bundle | Con registro y apps sembrados (incluyendo password en keyring fake y claves `deploy_token` en un target), el JSON canónico del bundle NO contiene el valor sembrado ni claves con sufijo de `_SECRET_KEYS` en las secciones devops |
| KPI-2 | Round-trip fiel | export → borrar todo → import `overwrite` → `list_servers()` (campos públicos) y `list_apps()` (campos exportados) quedan `==` a lo exportado |
| KPI-3 | Dry-run inocuo | Modo `dry-run` con secciones devops: hash sha256 de `servers.json` y `apps.json` ANTES == DESPUÉS |
| KPI-4 | Backward compat | Un bundle viejo (sin secciones devops) importa EXACTAMENTE igual que hoy (mismos efectos y misma respuesta salvo campos nuevos ausentes) |
| KPI-5 | Re-credencialización correcta | Con manifest `["a"]` e importando `a` y `b` sin password local: `credentials_pending == ["a"]` (tenía y falta) y `credentials_never_set == ["b"]`; y un overwrite con `a` en el bundle CONSERVA su password del keyring |

**Ganancia robusta:** disaster recovery y migración de máquina dejan de ser un rearmado manual
propenso a error; el setup DevOps completo (menos secretos, por diseño) es un archivo versionado con
checksum.

**Onboarding casi nulo:** las secciones nuevas aparecen SOLAS en el catálogo de export selectivo que
la UI ya consume (`GET /config/sections`, `api/config_transfer.py:263`); el flujo de import es el
mismo de siempre + un checklist que se explica solo.

---

## 2. Por qué ahora / gap que cierra

Evidencia del estado actual (verificada en el repo):

- `services/config_transfer.py:73-81` — `ALL_SECTIONS = ("settings", "integrations", "workflows",
  "agentProfiles", "clientProfile", "uiPreferences", "secretsRef")`. **Cero DevOps.**
- `services/config_transfer.py:87-89` — `_SECRET_KEYS = {"pat", "token", "password", "secret",
  "auth_header", "api_key"}` (política de secretos ya existente, se REUSA).
- `api/config_transfer.py:71,98,263` — export/import multi-proyecto con modos
  `{"dry-run","merge","overwrite"}` (`_VALID_MODES` :51), eventos (`record_event`) y catálogo de
  secciones para la UI. **Toda la maquinaria lista.**
- `services/server_registry.py:4-8,71-74,168-171` — passwords EXCLUSIVAMENTE en keyring
  (`KEYRING_SERVICE = "stacky-devops"`); el JSON de servers tiene assert defensivo que PROHÍBE
  persistir `password`; `has_password(alias)` existe (:89 lo usa `list_servers`). **Exportar servers
  sin secretos es seguro POR CONSTRUCCIÓN.**
- `services/deploy_store.py:59-96` — `list_apps()`, `upsert_app(app)`, `delete_app` sobre
  `apps.json`. **Las apps×targets del Centro 120 son un JSON local importable.**
- `frontend/src/api/endpoints.ts` — único punto del frontend que llama `config/export|import`.
- Vecinos que NO se pisan: 186 (lint), 188 (evidencia de fallos), 189 (rollback readiness),
  178 (drift de BD), 163 (identidad de build de Stacky).

**Gap:** la única pieza del ecosistema DevOps que NO sobrevive a un cambio de máquina es su
configuración. Cerrarlo es agregar 2 secciones al mecanismo existente — reuso máximo, superficie
mínima.

---

## 3. Principios y guardarraíles (no negociables)

1. **3 runtimes con paridad total por construcción:** backend Python + UI React, cero LLM; idéntico
   en Codex CLI / Claude Code CLI / GitHub Copilot Pro o sin ninguno.
2. **Cero trabajo extra para el operador:** flag default **ON**; exportar/importar sigue siendo el
   mismo flujo; el checklist de re-credencialización es INFORMATIVO (la re-vinculación de passwords
   es inherentemente manual por diseño de seguridad del 91 — no es trabajo nuevo agregado por este
   plan, es el mismo alta de password de siempre, ahora guiada).
3. **Human-in-the-loop:** importar ya es una acción explícita del operador con modos y dry-run; este
   plan no agrega ninguna acción automática. Los secretos JAMÁS se automatizan.
4. **Mono-operador sin auth:** nada de roles.
5. **No degradar / backward-compatible:** `ALL_SECTIONS` (nombre y valor) NO se modifica — se agrega
   `DEVOPS_SECTIONS` y una función de composición; `CURRENT_SCHEMA_VERSION` queda en `1` (secciones
   ADITIVAS y opcionales); bundles viejos importan idéntico (KPI-4); con la flag OFF todo queda
   EXACTAMENTE como hoy.
6. **Reusar, no reinventar:** checksum/canonical/eventos/modos/scrub de `_SECRET_KEYS` existentes;
   `server_registry.upsert_server`/`validate_alias`/`validate_host`; `deploy_store.upsert_app`.
7. **Regla de oro de secretos:** las secciones devops NUNCA leen el keyring para exportar; el import
   NUNCA escribe el keyring. El único dato derivado es booleano (`has_password`) y local.

---

## 4. Fases

### F0 — Flag + composición dinámica del catálogo (sin tocar `ALL_SECTIONS`)

**Objetivo:** declarar la flag y hacer que el catálogo/validación usen una composición que la respeta.
**Valor:** wiring completo y retrocompatible; F1 solo agrega los handlers.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/harness_flags.py`
- EDITAR `Stacky Agents/backend/services/config_transfer.py`
- EDITAR `Stacky Agents/backend/tests/test_harness_flags_requires.py` (solo si se declara `requires`; esta flag NO declara — ver abajo)
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh`
- CREAR `Stacky Agents/backend/tests/test_plan190_transfer_flag.py`

**Cambios exactos:**

1. `harness_flags.py` — FlagSpec al final del bloque DEVOPS (~:2743):

```python
FlagSpec(
    key="STACKY_CONFIG_TRANSFER_DEVOPS_ENABLED",
    type="bool",
    label="Equipaje DevOps en export/import",
    description="Incluye servidores DevOps (sin contraseñas — quedan en el keyring) y "
                "apps del Centro de Despliegues en el export/import de configuración, "
                "con checklist de re-vinculación de credenciales al importar.",
    group="global",
    default=True,
    # SIN requires: la transferencia de config es global, no vive dentro del panel DevOps.
),
```

2. Agregar la key a `_CURATED_DEFAULTS_ON` (~:200-216, comentario
   `# Plan 190 — equipaje DevOps en export/import`). **Gotcha:** bool ON fuera de la lista rompe
   `test_default_known_only_for_curated`.

3. `services/config_transfer.py` — DEBAJO de `ALL_SECTIONS` (:81), SIN tocar su valor:

```python
# Plan 190 — secciones DevOps (aditivas, opcionales; schemaVersion sigue en 1).
DEVOPS_SECTIONS: tuple[str, ...] = ("devopsServers", "devopsApps")


def _devops_transfer_enabled() -> bool:
    from config import config as _cfg   # import intra-función (evita ciclos en startup)
    return bool(getattr(_cfg, "STACKY_CONFIG_TRANSFER_DEVOPS_ENABLED", False))


def available_sections(scope: str = "all") -> tuple[str, ...]:
    """Catálogo efectivo. C2: las secciones devops son GLOBALES (stores en data_dir) —
    solo existen en scope "all" (bundle all-projects, top-level como uiPreferences).
    scope "project" (rutas :160/:189) devuelve SIEMPRE ALL_SECTIONS sin devops."""
    if scope == "all" and _devops_transfer_enabled():
        return ALL_SECTIONS + DEVOPS_SECTIONS
    return ALL_SECTIONS
```

4. Redirigir los CONSUMIDORES del catálogo a `available_sections()`: correr
   `grep -n "ALL_SECTIONS" "Stacky Agents/backend/services/config_transfer.py"
   "Stacky Agents/backend/api/config_transfer.py"` y reemplazar SOLO los usos que (a) validan
   secciones pedidas, (b) componen el export default, (c) arman el catálogo de
   `GET /config/sections` (leer `api/config_transfer.py:263` y espejar cómo etiqueta las secciones
   existentes para agregar las 2 labels nuevas: "Servidores DevOps (sin contraseñas)" y
   "Apps de despliegue"). NO tocar usos en tests existentes ni la definición.

**Tests PRIMERO** — `tests/test_plan190_transfer_flag.py`:
- `test_flag_declarada_bool_default_on` — FlagSpec existe, `type=="bool"`, `default is True`,
  `requires is None`.
- `test_flag_en_curated_defaults_on`.
- `test_all_sections_intacta` — `ALL_SECTIONS == ("settings","integrations","workflows",
  "agentProfiles","clientProfile","uiPreferences","secretsRef")` (guardia anti-regresión).
- `test_available_sections_on` — con flag ON (monkeypatch) → termina en
  `("devopsServers","devopsApps")`.
- `test_available_sections_off` — flag OFF → `available_sections() == ALL_SECTIONS`.
- `test_project_scope_sin_devops` (C2) — `available_sections(scope="project") == ALL_SECTIONS` aun
  con flag ON.
- `test_catalogo_endpoint_refleja_flag` — `GET /api/config/sections` incluye/excluye las 2 nuevas
  según la flag (Flask test client).

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan190_transfer_flag.py -q`
(cwd = `Stacky Agents\backend`; SIEMPRE por archivo).

**Criterio binario:** los 7 tests pasan Y `test_harness_ratchet_meta.py` verde (test registrado en
`HARNESS_TEST_FILES`).

**Flag:** `STACKY_CONFIG_TRANSFER_DEVOPS_ENABLED` default **ON** (ninguna excepción dura: exportar
NUNCA incluye secretos; importar NUNCA toca el keyring; todo es local y explícito).

**Runtimes:** idéntico en los 3. Fallback: flag OFF → catálogo y comportamiento EXACTOS a hoy.

**Trabajo del operador:** ninguno.

---

### F1 — Handlers de las 2 secciones (export + import en 3 modos)

**Objetivo:** que `devopsServers`/`devopsApps` exporten e importen con el MISMO protocolo que las
secciones existentes.
**Valor:** el corazón del plan; backup/migración reales.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/config_transfer.py`
- CREAR `Stacky Agents/backend/tests/test_plan190_transfer_devops_sections.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` (registrar el test)

**Protocolo (instrucción ejecutable, NO inferir):** correr
`grep -n "\"settings\"" "Stacky Agents/backend/services/config_transfer.py"` y LEER cómo la sección
`settings` registra su par export/import (builder + applier + participación en `validate_import`).
Las 2 secciones nuevas se registran con EXACTAMENTE la misma estructura, en el MISMO lugar.

**Export (contenido EXACTO):**

```python
def _export_devops_servers() -> dict:
    """Campos públicos del registro 91 + has_password (booleano local). CERO keyring reads
    para valores; has_password ya lo expone list_servers (server_registry.py:89).
    C4: `notes` sale con masking de prefijos de token (lista del plan 188).
    [ADICIÓN ARQUITECTO]: credentials_manifest = aliases con password AL EXPORTAR."""
    from services import server_registry
    servers = server_registry.list_servers()   # ya viene SIN password y CON has_password
    for s in servers:
        s["notes"] = _mask_token_values(s.get("notes") or "")
    manifest = [s["alias"] for s in servers if s.get("has_password")]
    return {"servers": servers, "credentials_manifest": manifest}

def _export_devops_apps() -> dict:
    """Apps del Centro 120 con scrub defensivo de claves secretas en targets."""
    from services import deploy_store
    apps = deploy_store.list_apps()
    return {"apps": _scrub_secret_keys(apps)}   # reusar/extender el scrub de _SECRET_KEYS
```

`_scrub_secret_keys(obj)`: recursivo sobre dict/list; toda clave cuyo `lower()` esté en
`_SECRET_KEYS` O termine en `("_token","_pat","_password","_secret","_key","_apikey")` se reemplaza
por `"<omitido>"`. Si ya existe un scrub equivalente para `integrations`, EXTENDERLO en vez de
duplicar (grep `_SECRET_KEYS` y decidir por lectura).

`_mask_token_values(text)` (C4): reemplaza por `"<posible-secreto-omitido>"` toda substring que
empiece con un prefijo de `("ghp_", "github_pat_", "glpat-", "xoxb-", "xoxp-", "AKIA",
"eyJhbGciOi")` seguida de ≥8 chars `[A-Za-z0-9_./+-]`. Definirla EN `config_transfer.py` (el plan
188 define una igual pero aún no está implementado — no depender de él; si al implementar este plan
ya existiera en otro módulo compartido, importarla de ahí).

**Import (modos, semántica EXACTA — C1/C3):**
- `dry-run` (C3): NO muta. El SHAPE del reporte NO se inventa: correr
  `grep -n "dry" "Stacky Agents/backend/services/config_transfer.py"` y LEER cómo reportan las
  secciones existentes; EXTENDER esa misma estructura agregando la clave `devops` con conteos
  `{"servers": {"add": n, "update": m, "remove_overwrite": k}, "apps": {...}}` (add/update por
  `alias`/`id`; `remove_overwrite` = lo que un overwrite borraría).
- `merge`: por cada server del bundle → `server_registry.upsert_server(alias, host, domain,
  username, notes)` (los campos derivados `has_password`/`last_connected_at` NO se aplican); por
  cada app → `deploy_store.upsert_app(app_sin_campos_derivados)`. Lo local que no está en el bundle
  SE CONSERVA. El keyring NO se toca.
- `overwrite` (C1 — DIFF-BASED, NUNCA borrar-todo-y-recrear): (a) aliases/ids presentes en el
  bundle → upsert (keyring INTACTO: `upsert_server` no toca credenciales); (b) aliases/ids locales
  AUSENTES del bundle → `server_registry.delete_server(alias)` / `deploy_store.delete_app(id)` —
  y SÍ: `delete_server` borra también la credencial del keyring (:149-161), que es la semántica
  correcta del 91 para un server que deja de existir. PROHIBIDO llamar `delete_server` sobre un
  alias que está en el bundle (eso destruiría su password — era el bug C1 de la v1).
- Respuesta del import: agrega `"devops": {"credentials_pending": [...], "credentials_never_set":
  [...]}` calculados EN IMPORT TIME con `server_registry.has_password(alias)`:
  `credentials_pending` = sin password local ∧ alias ∈ `credentials_manifest` del bundle (tenía y
  falta — prioridad); `credentials_never_set` = sin password local ∧ alias ∉ manifest
  (informativo). Registrar `record_event` con los conteos (auditoría, patrón existente).
- Sección presente en el bundle pero flag OFF → NO se aplica; agregar
  `"skipped_sections": ["devopsServers", ...]` a la respuesta y registrar en `record_event`.
- Rutas per-proyecto (:160/:189) (C2): si el bundle trae secciones devops, se saltean SIEMPRE con
  `skipped_sections` (son globales; solo el import all-projects las aplica).

**Tests PRIMERO** — `tests/test_plan190_transfer_devops_sections.py` (fixtures: `tmp_path` +
monkeypatch de `runtime_paths.data_dir` — espejar el estilo de los tests EXISTENTES de
config_transfer: correr `ls tests/ | grep -i "config_transfer\|transfer"` y leer el que ya testee
export/import; keyring fake = monkeypatch de `server_registry.keyring` con dict en memoria):
- `test_kpi1_cero_secretos_en_bundle` — password seteado vía keyring fake + target con
  `deploy_token: "abc123def456"` → el JSON canónico del bundle no contiene `"abc123def456"` ni la
  clave sin scrub.
- `test_kpi2_round_trip_overwrite` — export → wipe stores → import overwrite → `list_servers()` y
  `list_apps()` `==` (en los campos exportados).
- `test_kpi3_dry_run_inocuo` — sha256 de `servers.json`/`apps.json` antes == después + conteos
  correctos `{"add": 2, "update": 0}`.
- `test_kpi5_manifest_divide_pending_y_never_set` — bundle con manifest `["a"]`, importar servers
  `a` y `b`, ninguno con password local → `credentials_pending == ["a"]` y
  `credentials_never_set == ["b"]`.
- `test_merge_conserva_lo_local` — server local extra NO desaparece en merge.
- `test_overwrite_borra_solo_ausentes` (C1) — server local `viejo` ausente del bundle desaparece
  (y su credencial del keyring fake también — semántica 91); los del bundle quedan.
- `test_overwrite_conserva_password_de_alias_reimportado` (C1 — el bug de la v1) — alias `a` local
  CON password en keyring fake, presente en el bundle → tras overwrite, el keyring fake TODAVÍA
  tiene la credencial de `a` y `has_password("a") is True`.
- `test_flag_off_skipped_sections` — bundle CON secciones devops + flag OFF → stores intactos +
  `skipped_sections` en la respuesta.
- `test_campos_derivados_no_se_aplican` — bundle con `has_password: true` y
  `last_connected_at` → tras import, esos valores NO se copiaron (has_password refleja el keyring
  local real).
- `test_notes_enmascaradas` (C4) — server con `notes` conteniendo `"glpat-" + "x"*12` (literal
  PARTIDO — gotcha push-protection) → en el bundle aparece `<posible-secreto-omitido>`.

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan190_transfer_devops_sections.py -q`

**Criterio binario:** los 11 tests pasan (KPI-1, KPI-2, KPI-3, KPI-5).

**Flag:** la de F0. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F2 — Compatibilidad congelada (bundles viejos y nuevos)

**Objetivo:** probar que nada de lo existente cambió y fijar el contrato de compatibilidad.
**Valor:** cero regresiones en la transferencia que ya funciona.

**Archivos:**
- CREAR `Stacky Agents/backend/tests/test_plan190_transfer_compat.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` (registrar el test)
- (código: CERO cambios nuevos — esta fase es solo verificación; si un test falla, el fix va en F0/F1)

**Contrato de compatibilidad (EXACTO, documentado en el propio test como docstring):**
- `CURRENT_SCHEMA_VERSION` sigue en `1` (las secciones son aditivas y opcionales).
- Bundle viejo (sin secciones devops) + flag ON → import idéntico a hoy; la respuesta NO incluye
  `devops` ni `skipped_sections`.
- Bundle nuevo + versión vieja de Stacky: fuera de nuestro control (la versión vieja no conoce las
  secciones); mitigación = export SELECTIVO (el operador puede excluirlas en la UI existente). Se
  DOCUMENTA, no se "arregla".
- `meta.sections` del bundle refleja SOLO las secciones efectivamente exportadas (comportamiento
  existente que las nuevas secciones heredan).
- El checksum sigue siendo el de `compute_checksum` (:126) sin cambios.

**Tests PRIMERO** — `tests/test_plan190_transfer_compat.py`:
- `test_kpi4_bundle_viejo_importa_identico` — construir un bundle SOLO con secciones viejas
  (usando `build_all_projects_export` con `sections=list(ALL_SECTIONS sin secretsRef)`), importarlo
  con flag ON → efectos idénticos a hoy y respuesta sin claves nuevas.
- `test_schema_version_sigue_en_1` — `CURRENT_SCHEMA_VERSION == 1` (guardia anti-bump accidental).
- `test_meta_sections_refleja_seleccion` — export con `sections=["devopsServers"]` → `meta.sections
  == ["devopsServers"]` y el bundle NO contiene `devopsApps`.
- `test_checksum_estable_con_devops` — export 2 veces con los mismos datos → mismo checksum.
- `test_per_project_saltea_devops` (C2) — import per-proyecto (:189) con bundle que trae
  `devopsServers` → stores globales intactos + `skipped_sections` en la respuesta.

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan190_transfer_compat.py -q`

**Criterio binario:** los 5 tests pasan (KPI-4).

**Flag:** la de F0. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F3 — UI: checklist de re-credencialización y secciones visibles

**Objetivo:** que el operador VEA las secciones nuevas al exportar y el checklist al importar.
**Valor:** cierre del ciclo; la migración se guía sola.

**Archivos:**
- CREAR `Stacky Agents/frontend/src/components/transferDevops.ts` (helpers puros)
- CREAR `Stacky Agents/frontend/src/components/transferDevops.test.ts`
- EDITAR el componente consumidor del import (localización EXACTA: correr
  `grep -rn "config/sections\|configExport\|configImport" "Stacky Agents/frontend/src" --include=*.tsx --include=*.ts`
  y editar el componente `.tsx` que renderiza el resultado del import; `endpoints.ts` es solo el
  cliente HTTP y probablemente no necesite cambios — verificar por lectura si ya pasa el JSON
  completo de respuesta).

**Comportamiento exacto:**
1. Export selectivo: NINGÚN cambio de código esperado — el catálogo `GET /config/sections` ya
   alimenta la UI; con F0 las 2 secciones aparecen con sus labels. Verificar visualmente en el
   smoke manual.
2. `transferDevops.ts` (puro):

```typescript
export interface DevopsImportResult {
  devops?: { credentials_pending?: string[]; credentials_never_set?: string[] };
  skipped_sections?: string[];
}
export function credentialsChecklist(res: DevopsImportResult | undefined): { pending: string[]; neverSet: string[] } {
  return {
    pending: res?.devops?.credentials_pending ?? [],
    neverSet: res?.devops?.credentials_never_set ?? [],
  };
}
export function skippedNote(res: DevopsImportResult | undefined): string | null {
  const s = res?.skipped_sections ?? [];
  if (!s.length) return null;
  return `Secciones omitidas: ${s.join(', ')}`;
}
```

3. En el componente del resultado del import: si `pending` no está vacío, render de la lista
   PRIORITARIA "Re-vinculá las contraseñas de estos servidores en DevOps → Servidores:" (un item
   por alias); si `neverSet` no está vacío, línea informativa "Sin contraseña configurada (igual
   que en el origen): …" (texto plano + clases del CSS module local; **gotcha ratchet:** cero
   `style={{}}`); si `skippedNote(...)` no es null, render de esa línea. Nada más.

**Tests PRIMERO** — `transferDevops.test.ts` (vitest, sin @testing-library — gap conocido):
- `credentialsChecklist(undefined)` → `{pending: [], neverSet: []}`; con datos → separa bien.
- `skippedNote` — null sin skipped; texto correcto con 1 y con 2 secciones.

**Comando:** `npx vitest run src/components/transferDevops.test.ts`
(cwd = `Stacky Agents\frontend`; por archivo).

**Criterio binario:** los 2 tests pasan Y `npx tsc --noEmit` sin errores nuevos.

**Smoke manual (1 paso, opcional):** exportar con todo tildado → borrar un server → importar →
aparece el checklist con ese alias.

**Flag:** la de F0 (OFF → secciones ausentes del catálogo, import las saltea, UI sin cambios).
**Runtimes:** UI pura. **Trabajo del operador:** ninguno (re-vincular passwords ya era manual por
diseño del 91; ahora está guiado).

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Un secreto viaja en el bundle (peor caso) | Triple capa: server_registry JAMÁS persiste password (:71-74, assert), scrub `_SECRET_KEYS`+sufijos en apps, y KPI-1 escanea el JSON canónico con valores sembrados |
| El protocolo de handlers difiere de lo asumido | Instrucción ejecutable: grep `"settings"` y ESPEJAR la registración existente; F2 verifica que lo viejo no cambió |
| `available_sections()` rompe un consumidor no contemplado | F0 exige grep de TODOS los usos de `ALL_SECTIONS` y decidir por lectura; `test_all_sections_intacta` congela la tupla original |
| Import overwrite destruye passwords del keyring (bug C1 de la v1) | Overwrite DIFF-BASED: PROHIBIDO `delete_server` sobre aliases presentes en el bundle (delete_server borra keyring, :159-161); solo se borran los ausentes; `test_overwrite_conserva_password_de_alias_reimportado` lo congela |
| Bundle nuevo en Stacky viejo falla | Documentado en F2 (no controlable); mitigación = export selectivo existente |
| Sesión paralela toca config_transfer (serie 177-189 activa) | Cambios ADITIVOS (constantes + funciones nuevas + registración); tras merge `python -m compileall` + grep duplicado silencioso (gotcha conocido) |

## 6. Fuera de scope (explícito)

- Transportar secretos cifrados (export de credenciales, aún cifradas) — contradice el diseño 91.
- Export/import del LEDGER de deploys (historial es local por naturaleza; solo viaja la config).
- Presets de pipeline (97) y variables CI (94): viven en el tracker/código, no en stores locales.
- Sincronización automática entre máquinas (autonomía proactiva — prohibida).
- Migración de `schemaVersion` a 2 (innecesaria: secciones aditivas opcionales).

## 7. Glosario (para modelos menores)

- **Bundle:** JSON de export con `meta` (schemaVersion, checksum, sections) + secciones.
- **Secciones:** unidades exportables del catálogo (`ALL_SECTIONS` :73); este plan agrega
  `devopsServers` y `devopsApps` vía `DEVOPS_SECTIONS` + `available_sections()`.
- **Modos de import:** `dry-run` (solo reporta), `merge` (upsert conservando lo local),
  `overwrite` (reemplaza la sección completa) — `_VALID_MODES` (`api/config_transfer.py:51`).
- **Registro 91:** servidores DevOps `{alias, host, domain, username, notes}`; password SOLO en
  keyring (`KEYRING_SERVICE="stacky-devops"`); `has_password` es derivado local.
- **Centro 120:** apps×targets de despliegue en `apps.json` (`deploy_store.list_apps`/`upsert_app`).
- **Re-credencialización:** volver a cargar el password de un server importado, en la sección
  Servidores de siempre; el import solo AVISA cuáles faltan (`credentials_pending`).
- **`_CURATED_DEFAULTS_ON` / HARNESS_TEST_FILES / ratchet UI:** convenciones de flags ON curadas,
  registro de tests del arnés y prohibición de estilos inline (ver planes 186-189).

## 8. Orden de implementación

1. F0 — flag + `DEVOPS_SECTIONS` + `available_sections()` + catálogo + 6 tests.
2. F1 — handlers export/import 3 modos + `credentials_pending` + 8 tests.
3. F2 — compat congelada + 4 tests.
4. F3 — helpers UI + checklist + 2 tests + `tsc`.

Cada fase se commitea sola con sus tests verdes ANTES de la siguiente (TDD estricto, cero falsos
verdes).

## 9. Definición de Hecho (DoD) global

- [ ] Los 4 archivos de test (`test_plan190_transfer_flag.py`,
      `test_plan190_transfer_devops_sections.py`, `test_plan190_transfer_compat.py`,
      `transferDevops.test.ts`) pasan POR ARCHIVO con el intérprete correcto.
- [ ] `test_harness_ratchet_meta.py` y `test_default_known_only_for_curated` siguen verdes; los
      tests de config_transfer EXISTENTES siguen verdes (correr el archivo que ya exista, localizado
      en F1).
- [ ] KPI-1..KPI-5 verificados por los tests nombrados.
- [ ] `npx tsc --noEmit` sin errores nuevos; `python -m compileall backend` limpio.
- [ ] Flag `STACKY_CONFIG_TRANSFER_DEVOPS_ENABLED` visible/toggleable en la UI de flags, default ON.
- [ ] Con la flag OFF: catálogo, export, import y UI EXACTOS a hoy.
- [ ] `ALL_SECTIONS` y `CURRENT_SCHEMA_VERSION` intactos (tests guardia).
- [ ] `config_transfer.py` NO llama keyring DIRECTO (grep del diff: cero `keyring.` en ese
      archivo); el único camino que toca credenciales es `server_registry.delete_server` para
      aliases AUSENTES del bundle en overwrite (semántica 91, C1/C5), verificado por
      `test_overwrite_conserva_password_de_alias_reimportado` + `test_overwrite_borra_solo_ausentes`.
