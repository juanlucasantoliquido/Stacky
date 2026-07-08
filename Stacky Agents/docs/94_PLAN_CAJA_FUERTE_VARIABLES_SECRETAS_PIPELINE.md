# Plan 94 — Caja fuerte de variables: secretos del pipeline fuera del YAML (ADO + GitLab)

**Estado:** IMPLEMENTADO (F0..F5) — 2026-07-07, commit `33aa5bcf` (reconciliado por
auditoría: 36 tests backend propios + 75 no-regresión + 30 vitest + tsc 0 errores, todos
verdes). F5 checklist completo salvo el ítem de verificación manual ÚNICA contra un ADO
real (C12, documentado como pendiente — no bloquea el cierre del plan).
**Versión:** v3 (v1 → v2 → v3)
**Fecha:** 2026-07-07
**Serie DevOps E2E:** plan 2 de 4 (93 preflight / 94 variables / 95 producción / 96 doctor).
**Requisito textual del operador (riel #1):** compatible con **Azure DevOps Y GitLab
desde el día 1**. Cada capacidad tiene pata en ambos trackers o degrada ámbar honesta.
**Dependencias:** plan 87 IMPLEMENTADO (`84a9ecb5`, panel host). Integraciones
ADITIVAS/OPCIONALES: plan 93 (el preflight consume `list_variables` si esta flag
está ON — ver 93 F3), plan 95 (la definición ADO que este plan necesita se crea con
"Llevar a producción"; sin ella, la pata ADO degrada honesta), plan 91 (bridge de
credenciales: SOLO nota de compatibilidad §6). Verificado en working tree 2026-07-05.

## Changelog v2 → v3 (2ª crítica adversarial C12..C16 + adición A3)

- **C12 (IMPORTANTE, resuelto en F2/F5):** riesgo de **wipe de secretos hermanos**
  en el PUT full-definition de ADO: el GET devuelve las variables `isSecret` con
  `value: null`; el PUT de v2 reenviaba el documento completo — si ADO interpreta
  ese `null` como "borrar el valor", CADA `set_variable` de OTRA key destruye los
  secretos preexistentes (el test anti-lost-update de v2 solo chequeaba que las
  KEYS siguieran; no protegía el contenido). v3: regla explícita "las entradas
  preexistentes viajan BYTE-IDÉNTICAS a como vinieron del GET (incluido
  `value:null` + `isSecret:true`), solo se muta/agrega LA key pedida" + test
  `test_f2_ado_set_preserves_secret_sibling` + ítem manual en F5 (la semántica del
  `null` en PUT es ambigüedad documentada de la API de ADO: se verifica UNA vez
  contra un ADO real antes de dar el plan por cerrado — honestidad, no fe).
- **C13 (IMPORTANTE, resuelto en F4):** "Mover a variable segura" en v2 sacaba la
  key del `spec` LOCAL, pero el YAML ya commiteado en HEAD sigue conteniendo el
  valor en texto plano hasta que el operador recommittee. A1 solo hablaba de la
  HISTORIA de git; faltaba el CTA sobre el PRESENTE. v3: el hint post-move agrega
  literal "recommitteá el pipeline (botón Commit) para sacar el valor del YAML
  actual del repo" + grep en el criterio binario de F4.
- **C14 (IMPORTANTE, resuelto en F3):** `_call_provider` de v2 mapeaba "cualquier
  otra excepción → 502": (a) `TrackerConfigError` de la fábrica
  (`ci_provider.py:113-133` — p. ej. `STACKY_GITLAB_ENABLED=false` o tracker sin
  provider) NO tiene `.status` y es un problema de CONFIG, no de gateway ⇒ 400
  `kind:"tracker_config"`; (b) una excepción inesperada (bug) a 502 con `str(e)`
  arriesga fuga del value en un mensaje no sanitizado ⇒ 500 con mensaje GENÉRICO
  fijo ("error interno de variables") sin `str(e)`, log solo de
  `type(e).__name__`. +2 tests (F3 pasa de 12 a 14).
- **C15 (MENOR, resuelto en F3):** `GET` sin `project` quedaba sin especificar:
  se fija literal — `get_variables_provider(None)` resuelve el proyecto ACTIVO vía
  `resolve_project_context` (mismo contrato que `get_ci_provider`).
- **C16 (MENOR, resuelto en F4):** el regex de `canBeMasked` (A2) incluía `_` y
  `-`, que NO están en las reglas documentadas de masking de GitLab (alfabeto
  Base64 + `@ : . ~`) ⇒ falso "sí se puede enmascarar". Regex corregido a
  `^[a-zA-Z0-9+/=@:.~]{8,}$` (el backend C8 sigue siendo la fuente de verdad).
- **[ADICIÓN ARQUITECTO] A3 (F2):** GitLab EXPANDE `$` dentro del value como
  referencia a otra variable salvo que la variable se cree con `raw: true` —
  una password con `$` (comunísimo) llega CORROMPIDA al job en silencio. v3: el
  adapter GitLab envía `"raw": True` cuando `secret=True` (GitLab ≥15.7; el
  reintento C8 conserva `raw` — solo `masked` conmuta) + test
  `test_f2_gitlab_secret_sends_raw_true`. Paridad: ADO no expande `$(VAR)` dentro
  de valores de variables, no necesita equivalente.
- **DoD recontado:** 35 tests backend (F0:5, F1:3, F2:13, F3:14) + 5 vitest.

## Changelog v1 → v2 (crítica adversarial C1..C11 + adiciones)

- **C1 (IMPORTANTE, resuelto en F0):** la flag declara `requires=` pero v1 omitía la
  6ª pata obligatoria: la arista en `_REQUIRES_MAP_FROZEN`
  (`tests/test_harness_flags_requires.py:120`; los 4 hermanos 88-91 la tienen en
  `:129-132`). Sin ella, `test_requires_map_is_frozen` queda ROJO en silencio
  (los tests nombrados del plan pasaban igual — falso verde por omisión).
- **C2 (IMPORTANTE, resuelto en F2):** el adapter GitLab de v1 decía "delegate
  `GitLabTrackerProvider` y su `_request`" — impreciso: `_request` vive en
  `gitlab_client.py:107` (se accede vía `provider._client`, `gitlab_provider.py:36,95`)
  y devuelve TUPLA `(body, status)`; además `GET /variables` es PAGINADO (trunca a 20)
  ⇒ `list_variables` DEBE usar `_request_paginated` (`gitlab_client.py:177`).
- **C3 (IMPORTANTE, resuelto en F2):** "si la key existe ⇒ PUT, sino POST" no decía
  CÓMO detectar existencia. Fijado: `GET /variables/:key`; `TrackerApiError.status
  == 404` ⇒ POST; 200 ⇒ PUT (atributo `status` verificado en
  `tracker_provider.py:48-52`).
- **C4 (IMPORTANTE, resuelto en F2):** el PUT full-definition de ADO exige el campo
  `revision` actual en el body; v1 no lo mencionaba (el tracker rechaza el update).
  Fijado: el body del PUT ES el JSON completo del GET, mutando SOLO `variables`.
- **C5 (IMPORTANTE, resuelto en §4/F2/F4):** contradicción de contrato: tras el
  fallback `masked:false`, en GitLab la variable es INDISTINGUIBLE de una normal en
  el próximo GET (`is_secret = masked or protected`, con `protected:false` fijo) ⇒
  el candado prometido desaparecía al refrescar. v2 documenta la limitación honesta
  y ajusta el copy de la UI (el badge "no enmascarable" es efímero, del alta).
- **C6 (IMPORTANTE, resuelto en F3):** HITL incompleto: `/delete` no declaraba
  `confirm ⇒ 400` ni tenía test; y el mapeo `VariablesUnavailableError ⇒ 409` /
  `⇒ 502` estaba especificado SOLO para el GET (en ADO sin definición, POST y
  delete levantan la misma excepción). v2: helper único de mapeo para TODAS las
  rutas + 2 tests nuevos (F3 pasa de 10 a 12 tests).
- **C7 (MENOR, resuelto en F1):** `CRED` matcheaba `CREDIT_LIMIT`/`ACCREDITED` ⇒
  token `CRED(?!IT)` + `CREDIT_LIMIT` agregado al fixture como `not_secret`.
- **C8 (MENOR, resuelto en F2):** el reintento de masking por "el mensaje menciona
  masking" era frágil (el texto del error de GitLab varía por versión). Regla
  determinista: POST/PUT con `masked:true` que devuelve status 400 ⇒ reintento
  ÚNICO con `masked:false`; si el reintento también falla ⇒ propagar sanitizado.
- **C9 (MENOR, resuelto en F1/F2):** `test_f1_pure_no_io` estaba redactado con
  puntos suspensivos y paréntesis divagante ⇒ greps literales; y la fábrica
  `get_variables_provider` DEBE usar lazy imports dentro de la función (espejo
  EXACTO de `get_ci_provider`, `ci_provider.py:113-129`, que ya es lazy).
- **C10 (MENOR, nota en F0):** drift PREEXISTENTE de `harness_defaults.env`
  (2026-07-05: centinelas de la serie 87-91 en rojo; generador real en
  `deployment/export_harness_defaults.py`). El implementador agrega SU línea y su
  test; NO "arregla" el drift ajeno en el mismo commit.
- **C11 (MENOR, resuelto en F2):** `definition["variables"]` puede faltar en el
  JSON de ADO ⇒ siempre `definition.get("variables") or {}`.
- **[ADICIÓN ARQUITECTO] A1 (F4):** aviso de rotación post-"Mover a variable
  segura": mover la key fuera del spec NO borra el secreto de la HISTORIA de git
  si el YAML ya fue commiteado — la UI lo dice en llano y sugiere rotar la
  credencial. Informativo, cero trabajo extra, paridad ADO+GitLab.
- **[ADICIÓN ARQUITECTO] A2 (F4):** `canBeMasked(value)` en `variablesModel.ts`
  (espejo puro de las reglas de masking de GitLab) ⇒ la UI avisa ANTES de guardar
  que el valor no va a poder enmascararse (solo tracker gitlab). El backend
  conserva el reintento C8 como fuente de verdad. +1 test vitest.
- **DoD recontado:** 31 tests backend (F0:5, F1:3, F2:11, F3:12) + 5 vitest.

| Pieza existente reusada | Evidencia (archivo:línea) |
|---|---|
| Blueprint del panel + health aditivo | `backend/api/devops.py:22,25-38` |
| Contrato §3.12: `DEVOPS_SECTIONS` declarativo + gate del shell | `frontend/src/pages/DevOpsPage.tsx:44-50,68` |
| `FlagGateBanner` | `frontend/src/components/devops/FlagGateBanner.tsx` |
| Builder 87: `spec.variables` editable (Pipeline properties) | `frontend/src/components/devops/BlockProperties.tsx`, `frontend/src/devops/specBuilder.ts` |
| Variables van HOY en texto plano al YAML commiteado | `backend/services/pipeline_renderers.py:47-49` (ado), `:148-149,163-164` (gitlab) |
| Cliente REST ADO con PAT | `backend/services/ado_client.py:257` (`_request`) |
| Cliente REST GitLab (C2) | `backend/services/gitlab_client.py:107` (`_request`, devuelve `(body, status)`), `:177` (`_request_paginated`); el provider lo expone vía `self._client` (`gitlab_provider.py:36,95`) |
| `TrackerApiError` con `.status` y `.kind` | `backend/services/tracker_provider.py:48-52` |
| Fábrica por tracker_type (patrón, lazy imports) | `backend/services/ci_provider.py:107-129` |
| Riel "secreto JAMÁS en JSON/logs/GET" (write-only + has_value) | plan 91 §3.1, `backend/services/server_registry.py`, `backend/api/devops_servers.py` |
| Guard anti-CSRF `request.is_json` en mutantes | plan 91 C5, `backend/api/devops_servers.py:19-25` (`_guard`) |
| Helper de definiciones ADO (compartido 93/95) | `backend/services/ado_pipeline_definitions.py` (lo crea el primero de 93/94/95 implementado; contenido EXACTO en 93 F2) |
| Patrón flag 5 patas + gotchas | `backend/config.py:857-859`, `harness_flags.py:177-183`, ratchet `run_harness_tests.ps1:103-125` |
| Mapa congelado de `requires` (C1) | `backend/tests/test_harness_flags_requires.py:120-148` |

---

## 1. Objetivo + KPI

Que el operador gestione **variables del pipeline por proyecto** desde una sección
nueva "Variables" del panel DevOps, marcando cada una como **secreta** (candado):

- Las **secretas** se crean EN EL TRACKER vía API — GitLab: project CI/CD variable
  con `masked`; ADO: variable de la pipeline definition con `isSecret:true` — y
  **JAMÁS tocan el YAML, el repo, el client_profile ni los logs** (riel §3.1 del 91).
- Las **normales** pueden seguir viviendo en `spec.variables` (comportamiento 87
  intacto) o crearse también en el tracker.
- En el builder del 87, una heurística detecta keys que "parecen secreto"
  (PASSWORD/TOKEN/etc.) en `spec.variables` y ofrece **"Mover a variable segura"**
  (1 click + confirmación): crea la variable en el tracker y la saca del spec.

**KPI (aspiracional; criterios binarios en F5):**
- 0 secretos commiteados al repo por el flujo DevOps (heurística + botón mover).
- Alta de una variable segura = 1 formulario + 1 confirmación, en ADO y en GitLab.
- El valor de un secreto es write-only: no aparece en NINGUNA respuesta GET ni log
  (test centinela, patrón KPI-2 del plan 91).

## 2. Por qué ahora / gap que cierra

Un pipeline real despliega contra servidores/servicios: necesita credenciales.
Hoy el único lugar para "variables" del flujo DevOps es `spec.variables`, que se
renderiza EN TEXTO PLANO dentro del YAML commiteado (`pipeline_renderers.py:47-49,
148-149`). El camino natural de un operador no-experto — poner la password ahí —
termina con el secreto versionado en el repo. Los trackers ya tienen el mecanismo
correcto (variables masked/secret inyectadas en runtime); solo falta el puente por
UI con el riel write-only que el plan 91 ya probó para el Credential Manager.

## 3. Principios y guardarraíles (NO negociables)

1. **PARIDAD ADO + GITLAB:** sub-puerto `CIVariablesProvider` con DOS adapters y
   fábrica por tracker_type. GitLab = project CI/CD variables API. ADO = variables
   de la pipeline definition (`isSecret`) — disponibles como `$(VAR)` en el YAML
   sin declararlas, igual que las de GitLab como `$VAR`. Si ADO no tiene definición
   aún ⇒ la sección degrada ámbar con CTA al plan 95 (nunca finge éxito).
2. **Secreto JAMÁS en disco/JSON/DB/logs/GET (riel 91 §3.1):** el valor entra SOLO
   por POST (write-only); GET devuelve `{key, is_secret, has_value}`; prohibido
   loggear el body de requests/responses de este plan; las excepciones HTTP que
   puedan contener el valor NUNCA propagan crudas (patrón 91 C1).
3. **HITL:** crear/actualizar/borrar una variable exige `confirm:true` en el body
   (server-side, en las TRES rutas mutantes — C6) + click explícito. Nada se
   sincroniza ni borra solo.
4. **Flag propia** `STACKY_DEVOPS_VARIABLES_ENABLED`: categoría `devops`,
   `env_only=False`, `requires="STACKY_DEVOPS_PANEL_ENABLED"`, SIN `default=`,
   CON `label`/`group`, `PlainHelp`, línea en `harness_defaults.env` + test,
   **Y la arista en `_REQUIRES_MAP_FROZEN` (C1 — 6ª pata, ver F0)**.
   Default OFF; byte-idéntico con OFF (endpoints 404, sección con `FlagGateBanner`
   del shell).
5. **No degradar:** `PipelineSpec`/renderers INTACTOS (cero campos nuevos, cero
   cambios de YAML); el flujo 87 sin la flag es byte-idéntico. `CI_PORT_METHODS`
   intacto (sub-puerto nuevo).
6. **Guard anti-CSRF (91 C5):** métodos mutantes exigen `request.is_json` ⇒ 400.
7. **3 runtimes:** UI + Flask; impacto NINGUNO (declarado por fase).
8. **Mono-operador sin auth; cero trabajo extra** (opt-in); **ratchet** en ambos
   scripts.
9. **NUNCA PUTear client_profile parcial:** este plan NO persiste nada en
   client_profile (la fuente de verdad de variables es EL TRACKER — cero estado
   duplicado en Stacky).

## 4. Modelo de datos (contrato)

No hay persistencia nueva en Stacky. Contratos del sub-puerto (F2):

```python
list_variables() -> list[dict]   # [{"key": str, "is_secret": bool, "has_value": True,
                                 #   "masked": bool|None}]  — NUNCA "value"
set_variable(key: str, value: str, secret: bool) -> dict   # {"key", "is_secret", "masked": bool|None}
delete_variable(key: str) -> bool                          # False si no existía
```

Reglas de key (PURAS, F1): `^[A-Za-z_][A-Za-z0-9_]*$`, 1..255 chars (constraint
GitLab; ADO lo tolera). Heurística `looks_secret(key)`: regex case-insensitive
`(PASSWORD|PASSWD|PWD|SECRET|TOKEN|APIKEY|API_KEY|PRIVATE|CRED(?!IT)|CONN(ECTION)?_?STR)`
(C7: `CRED(?!IT)` para no matchear `CREDIT_LIMIT`).

**Nota GitLab masked (C8, regla determinista):** GitLab rechaza `masked:true` si el
VALOR no cumple sus reglas (≥8 chars, una sola línea, charset restringido). El
adapter intenta `masked:true`; si el tracker devuelve **status 400** (sin
inspeccionar el texto del error — varía por versión de GitLab), reintenta UNA vez
con `masked:false`; si el reintento también falla, propaga sanitizado. Devuelve
`masked:false` — la UI muestra "guardada como secreta pero NO enmascarable en logs
de GitLab (el valor no cumple las reglas de masking)". Honestidad, no magia.

**Nota GitLab `raw` (A3):** sin `raw: true`, GitLab trata `$ALGO` dentro del VALUE
como referencia a otra variable y lo expande en el job — una password con `$`
llega corrompida sin error visible. El adapter envía `"raw": True` siempre que
`secret=True` (soportado desde GitLab 15.7, piso razonable; el reintento C8 NO
toca `raw` — la escalera determinista solo conmuta `masked`). Si un GitLab
prehistórico rechazara el atributo, el flujo C8 termina propagando sanitizado
(degradación honesta, nunca corrupción silenciosa).

**Limitación honesta GitLab (C5):** GitLab NO tiene bit "secreta" separado de
`masked`/`protected`. Con `protected:false` fijo (v1), una variable guardada con el
fallback `masked:false` es INDISTINGUIBLE de una normal en el próximo
`list_variables` ⇒ `is_secret` vuelve `False` y el candado NO aparece al refrescar.
El badge "no enmascarable" es EFÍMERO (vive en la respuesta del alta). La UI lo
dice en llano en ese momento (ver F4). En ADO no pasa: `isSecret` persiste.

## 5. Fases

> Comandos de test: backend `.venv/Scripts/python.exe -m pytest tests/<archivo> -q`
> desde `Stacky Agents/backend`; frontend `npx tsc --noEmit` + `npx vitest run
> <archivo>` (vitest ya instalado, correr por archivo).

### F0 — Flag `STACKY_DEVOPS_VARIABLES_ENABLED` (6 patas — C1)

Misma mecánica que 93 F0 / espejo de `test_plan91_servers_flag.py`, cambiando la
key. `FlagSpec` con `label="Variables del pipeline (Plan 94)"` y description en
llano: "Caja fuerte de variables: las secretas se guardan en el tracker (GitLab
masked / ADO isSecret), nunca en el YAML ni en archivos de Stacky. Default OFF:
/api/devops/variables da 404 y la sección no aparece."

**Las 6 patas (C1 suma la 6ª):**
1. `config.py` (patrón exacto del archivo, junto a `STACKY_DEVOPS_PANEL_ENABLED`).
2. `harness_flags.py`: `_CATEGORY_KEYS["devops"]` + `FlagSpec` (SIN `default=`,
   `env_only=False`, `requires="STACKY_DEVOPS_PANEL_ENABLED"`, `group="global"`).
3. `harness_flags_help.py`: entrada `PlainHelp` en llano.
4. `harness_defaults.env`: línea `STACKY_DEVOPS_VARIABLES_ENABLED=false` (orden
   alfabético). **Nota C10:** hay drift PREEXISTENTE de este archivo (centinelas de
   la serie 87-91 en rojo al 2026-07-05, generador real en
   `deployment/export_harness_defaults.py`): agregar SOLO la línea propia; no
   arreglar el drift ajeno en este commit.
5. Tests del plan (abajo) + registro en ratchet.
6. **`tests/test_harness_flags_requires.py:120` — agregar la arista al mapa
   congelado, junto a las de la serie (`:129-132`):**
   ```python
   "STACKY_DEVOPS_VARIABLES_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 94
   ```

**Tests PRIMERO** — `tests/test_plan94_variables_flag.py`: los mismos 5 casos del
patrón (registry/categoría/default off/plain help/harness_defaults) + no-regresión
`test_harness_flags.py`, `test_flag_wiring.py` **y
`test_harness_flags_requires.py` (C1)** (misma nota del plan 85: F0+F3 en el mismo
commit si el wiring acusa).
**Ratchet:** registrar. **Criterio binario:** 5 propios + 3 archivos de
no-regresión verdes; default OFF.
**Flag:** `STACKY_DEVOPS_VARIABLES_ENABLED`. **Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F1 — Helpers PUROS (`validate_variable_key` / `looks_secret`)

**Objetivo:** validación y heurística deterministas, compartidas backend/frontend
por paridad de datos.

**Archivo NUEVO:** `Stacky Agents/backend/services/ci_variables.py` (el Protocol
va en F2; acá nacen los helpers puros del mismo módulo):
```python
"""ci_variables.py — Plan 94. Sub-puerto de variables CI + helpers PUROS.
Los helpers no hacen I/O. El VALOR de un secreto jamás se loggea ni retorna."""
import re

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECRET_HINT_RE = re.compile(
    r"(PASSWORD|PASSWD|PWD|SECRET|TOKEN|APIKEY|API_KEY|PRIVATE|CRED(?!IT)|CONN(ECTION)?_?STR)",
    re.IGNORECASE,
)

def validate_variable_key(key: str) -> str | None:
    """None si OK; mensaje en llano si no (vacía, regex, >255)."""

def looks_secret(key: str) -> bool:
    """True si el NOMBRE sugiere secreto (heurística, solo por key, nunca por valor)."""
```

**Archivo NUEVO (fixture compartido py↔ts, patrón 88):**
`Stacky Agents/backend/tests/fixtures/plan94_secret_hints.json` — contenido literal:
```json
{
  "secret": ["DB_PASSWORD", "password", "GITLAB_TOKEN", "ApiKey", "MY_API_KEY",
              "SSH_PRIVATE_KEY", "CONN_STR", "ConnectionString", "SVC_CRED"],
  "not_secret": ["DEPLOY_PATH", "ENVIRONMENT", "TIMEOUT_SECONDS", "TARGET_HOST",
                 "KEYBOARD_LAYOUT", "MONKEY", "CREDIT_LIMIT"]
}
```
(Notas: `KEYBOARD`/`MONKEY` NO deben matchear — el regex exige los tokens listados,
no la substring `KEY` suelta: por eso `APIKEY|API_KEY` y no `KEY`. `CREDIT_LIMIT`
NO debe matchear — C7: `CRED(?!IT)`.)

**Tests PRIMERO** — `tests/test_plan94_variables_pure.py`:
- `test_f1_key_valid_and_invalid` (ok: `DEPLOY_PATH`, `_x`; error: vacía, `9X`,
  `con espacios`, `a-b`, 256 chars).
- `test_f1_secret_hints_shared_fixture` (parametrizado con el JSON: los `secret`
  dan True, los `not_secret` dan False — 16 casos).
- `test_f1_pure_no_io` (C9, literal): leer el FUENTE de
  `services/ci_variables.py` como texto y assert que NO contiene ninguno de:
  `"import flask"`, `"from flask"`, `"import requests"`, `"from requests"`.
  (Los adapters de F2 viven en archivos propios y la fábrica usa lazy imports —
  ver F2 — así este grep se mantiene verde para siempre.)

**Ratchet:** registrar. **Criterio binario:** 3 tests (1 parametrizado ×16) verdes.
**Flag:** ninguna (puro). **Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F2 — Sub-puerto `CIVariablesProvider` + adapters GitLab y ADO

**Objetivo:** las 3 operaciones (list/set/delete) con paridad real y write-only.

**Archivo a editar:** `Stacky Agents/backend/services/ci_variables.py` — agregar:
```python
from typing import Optional, Protocol, runtime_checkable

class VariablesUnavailableError(Exception):
    """El tracker no puede alojar variables todavía (ADO sin definición) → 409."""

@runtime_checkable
class CIVariablesProvider(Protocol):
    name: str
    def list_variables(self) -> list[dict]: ...
    def set_variable(self, key: str, value: str, secret: bool) -> dict: ...
    def delete_variable(self, key: str) -> bool: ...

VARIABLES_PORT_METHODS = ("list_variables", "set_variable", "delete_variable")

def get_variables_provider(project: Optional[str] = None) -> CIVariablesProvider:
    """Fábrica espejo EXACTO de get_ci_provider (ci_provider.py:107-129):
    resolve_project_context por tracker_type; TODOS los imports (project_context,
    config, adapters) son LAZY, DENTRO de la función (C9 — mantiene verde el grep
    de test_f1_pure_no_io). gitlab -> GitLabVariablesProvider;
    azure_devops -> AdoVariablesProvider; otro -> TrackerConfigError."""
```

**Archivo NUEVO:** `Stacky Agents/backend/services/gitlab_variables.py` (C2/C3/C8)
- `class GitLabVariablesProvider` (`name="gitlab"`). Constructor
  `(project: str | None)`: instancia
  `GitLabTrackerProvider(project_name=project)` (`gitlab_provider.py:28`) y guarda
  `self._client = provider._client` (`gitlab_provider.py:36` — es un
  `GitLabClient`). ⚠️ C2: `_request` vive en `gitlab_client.py:107` y devuelve
  TUPLA `(body, status)`; `_request_paginated` (`gitlab_client.py:177`) devuelve
  la lista completa ya unida. El path del proyecto se resuelve con
  `self._client._project_path()` (patrón `gitlab_provider.py:104`).
  - `list_variables`: **`self._client._request_paginated("GET",
    f"/projects/{proj}/variables")`** (C2: el GET simple pagina de a 20 y
    truncaría) → `[{key, is_secret: bool(v.get("masked") or v.get("protected")),
    has_value: True, masked: v.get("masked")}]` — el campo `value` de la respuesta
    del tracker se DESCARTA antes de retornar (assert en test). Ver §4 C5: una
    secreta guardada con fallback `masked:false` lista como `is_secret:false`
    (limitación del tracker, cubierta por test).
  - `set_variable` (C3, detección de existencia LITERAL):
    1. `try: self._client._request("GET", f"/projects/{proj}/variables/{key}")`
       ⇒ 200 = existe ⇒ verbo `PUT /projects/{proj}/variables/{key}`.
    2. `except TrackerApiError as e:` si `e.status == 404` ⇒ no existe ⇒ verbo
       `POST /projects/{proj}/variables`; cualquier otro status ⇒ propagar
       sanitizado (regla de abajo).
    3. Body `{ "key": key, "value": value, "masked": secret, "protected": False }`
       — **y si `secret` es True, además `"raw": True` (A3: evita que GitLab
       expanda `$` dentro del value; el reintento del paso 4 conserva `raw`)**.
    4. **Reintento masking (C8, determinista):** si el POST/PUT con `masked:true`
       levanta `TrackerApiError` con `e.status == 400` ⇒ reintento ÚNICO con
       `masked:false` (mismo verbo); si el reintento también falla ⇒ propagar
       sanitizado. Retorno `{"key", "is_secret": secret, "masked": <lo enviado>}`.
    5. **Sanitización (91 C1):** toda excepción propagada se relanza como
       `TrackerApiError(e.status, <mensaje del tracker SOLAMENTE>, kind=e.kind)`
       — JAMÁS interpolar el body del request (contiene el value).
  - `delete_variable`: `DELETE /projects/{proj}/variables/{key}`;
    `TrackerApiError` con `e.status == 404` ⇒ `False`; éxito ⇒ `True`.

**Archivo NUEVO:** `Stacky Agents/backend/services/ado_variables.py` (C4/C11)
- `class AdoVariablesProvider` (`name="azure_devops"`; usa `AdoClient._request`
  (`ado_client.py:257`) + `find_yaml_definition` de
  `services/ado_pipeline_definitions.py` — si ese módulo no existe aún (93/95 sin
  implementar), CREARLO con el contenido EXACTO del 93 F2):
  - Constructor resuelve `self._definition = find_yaml_definition(project)`;
    si None, TODAS las operaciones levantan
    `VariablesUnavailableError("ADO sin pipeline definition para "
    "azure-pipelines.yml — creala con 'Llevar a producción' (plan 95) o en la web "
    "de ADO")` (la captura F3 → 409).
  - `list_variables`: `GET {base_proj}/_apis/build/definitions/{id}?api-version=7.1`
    → `definition.get("variables") or {}` (C11: el campo puede faltar) →
    `[{key, is_secret: bool(v.get("isSecret")), has_value: True, masked: None}]`
    (los valores de los secretos YA vienen null de ADO; los no-secretos se
    descartan igual — write-only uniforme).
  - `set_variable` (C4): GET del detalle → el body del PUT ES el JSON COMPLETO
    devuelto por el GET, mutando SOLO
    `variables[key] = {"value": value, "isSecret": secret, "allowOverride": False}`
    — **el campo `revision` del GET viaja TAL CUAL en el PUT** (ADO lo exige;
    sin él rechaza el update). **Regla C12 (anti-wipe de secretos hermanos):
    TODA entrada preexistente de `variables` distinta de `key` viaja
    BYTE-IDÉNTICA a como vino del GET — incluidas las `isSecret:true` cuyo
    `value` el GET devuelve `null` (NO rellenar, NO borrar, NO normalizar ese
    `null`). Prohibido reconstruir el dict: mutar el JSON del GET in place.**
    `PUT .../definitions/{id}?api-version=7.1`.
    Si el tracker rechaza por revision desactualizada (status 409/400) ⇒ propagar
    sanitizado (sin el value). Retorno `{"key", "is_secret": secret, "masked": None}`.
  - `delete_variable`: GET → si la key no está en `get("variables") or {}` ⇒
    False; sino `del` + PUT (mismo riel C4) ⇒ True.

**Tests PRIMERO** — `tests/test_plan94_variables_providers.py` (mocks del
`_request`/`_request_paginated` correspondiente en su módulo de ORIGEN
(`services.gitlab_client.GitLabClient` / `services.ado_client.AdoClient`);
NUNCA red):
- `test_f2_factory_by_tracker_type` (patrón 93 F2).
- `test_f2_gitlab_list_never_returns_value` (fixture PAGINADA con
  `value:"S3cr3t!"` ⇒ el retorno NO contiene la key `value` ni el literal —
  centinela §3.1; incluye una variable `masked:false, protected:false` y assert
  `is_secret is False` — caso C5).
- `test_f2_gitlab_set_post_then_put` (GET por key ⇒ 404 ⇒ POST; GET ⇒ 200 ⇒ PUT — C3).
- `test_f2_gitlab_masked_rejected_fallback` (400 en el primer intento con
  `masked:true` ⇒ reintento con `masked:false` y retorno `masked False`; segundo
  400 ⇒ excepción sanitizada — C8; **assert adicional: AMBOS intentos llevan
  `raw: True` — A3**).
- `test_f2_gitlab_secret_sends_raw_true` (A3: `set_variable(k, "pa$$word", True)`
  ⇒ el body capturado tiene `raw is True`; con `secret=False` ⇒ `raw` ausente).
- `test_f2_gitlab_delete_404_false`.
- `test_f2_ado_no_definition_raises_unavailable` (find ⇒ None ⇒
  `VariablesUnavailableError` con "plan 95" en el mensaje).
- `test_f2_ado_list_maps_is_secret` (incluye definición SIN campo `variables` ⇒
  lista vacía, no crash — C11).
- `test_f2_ado_set_merges_full_definition` (el PUT lleva el documento completo con
  la variable nueva Y las preexistentes intactas — anti-lost-update — **y el campo
  `revision` idéntico al del GET** — C4).
- `test_f2_ado_set_preserves_secret_sibling` (C12: el GET del fixture trae una
  variable hermana `{"OTRA_SECRETA": {"value": None, "isSecret": True}}`;
  tras `set_variable("NUEVA", "v", False)`, el body del PUT contiene
  `OTRA_SECRETA` EXACTAMENTE como vino — `value` sigue `None`, `isSecret` sigue
  `True`, sin claves agregadas ni quitadas).
- `test_f2_ado_delete_absent_false`.
- `test_f2_port_structural_conformance` (patrón `test_plan73_repo_writer.py:34-44`).
- `test_f2_no_value_in_exceptions`: forzar excepción del `_request` durante
  `set_variable("K","S3cr3t!XYZ",True)` en AMBOS adapters ⇒ el `str()` de la
  excepción propagada NO contiene `S3cr3t!XYZ` (patrón 91 C1).

**Ratchet:** registrar. **Criterio binario:** 13 tests verdes; grep en los 2
adapters: cero `logger`/`print` que referencien `value`; grep en
`ci_variables.py`: los imports de la fábrica están DENTRO de la función (C9).
**Flag:** ninguna (sin consumidores hasta F3). **Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F3 — Endpoints `/api/devops/variables` (write-only, HITL)

**Objetivo:** exponer el CRUD con guard de flag, is_json, confirm y mapeo de
errores UNIFORME (C6).

**Archivo NUEVO:** `Stacky Agents/backend/api/devops_variables.py` (blueprint
propio, patrón `api/devops_servers.py`; prefix SIN `/api`):
```python
bp = Blueprint("devops_variables", __name__, url_prefix="/devops/variables")

def _guard():
    if not getattr(_config.config, "STACKY_DEVOPS_VARIABLES_ENABLED", False):
        abort(404)
    if request.method in ("POST", "PUT", "DELETE") and not request.is_json:
        abort(400, description="Content-Type application/json requerido")  # 91 C5

def _call_provider(fn):
    """C6/C14 — mapeo ÚNICO para TODAS las rutas: ejecuta fn() y traduce EN ESTE ORDEN:
    VariablesUnavailableError -> (409, {"error": str(e), "kind": "variables_unavailable"})
    TrackerConfigError        -> (400, {"error": str(e), "kind": "tracker_config"})
                                 # C14a: la fábrica la levanta sin .status (config, no gateway)
    TrackerApiError           -> (502, {"error": str(e)})   # ya viene sanitizada de F2
    Exception (cualquier otra)-> (500, {"error": "error interno de variables"})
                                 # C14b: mensaje GENÉRICO FIJO — PROHIBIDO str(e)
                                 # (podría contener el value); loggear SOLO
                                 # type(e).__name__, jamás el repr/str.
    éxito                     -> el retorno de fn."""
```
Rutas (todas llaman `_guard()` y envuelven el provider con `_call_provider`;
el project SIEMPRE en query/body; **C15: si `project` viene vacío/ausente,
`get_variables_provider(None)` resuelve el proyecto ACTIVO vía
`resolve_project_context` — mismo contrato que `get_ci_provider`**):
- `GET ""?project=` → `{variables: [...], provider: "gitlab"|"azure_devops"}`.
- `POST ""` body `{project, key, value, secret, confirm:true}` →
  `validate_variable_key` (400 si error); `confirm is not True` ⇒ 400 (HITL);
  `set_variable` ⇒ 201 con el retorno del provider (SIN value). PROHIBIDO loggear
  el body en cualquier rama.
- `POST "/delete"` body `{project, key, confirm:true}` → **`confirm is not True`
  ⇒ 400 (HITL — C6, igual que el alta)**; `delete_variable`; 404 si no existía;
  200 `{"ok": true}`. (POST y no DELETE para llevar body JSON con confirm de
  forma uniforme — mismo criterio que `/test` del 91.)

**Registro:** `api/__init__.py` junto a los blueprints devops existentes (import +
`api_bp.register_blueprint(devops_variables_bp)`).
**Health:** en `devops_health_route` (`api/devops.py:29-38`) agregar
`"variables_enabled": bool(getattr(cfg, "STACKY_DEVOPS_VARIABLES_ENABLED", False)),`.

**Tests PRIMERO** — `tests/test_plan94_variables_endpoints.py` (fixtures flag
on/off; provider mockeado con `unittest.mock.patch(
"api.devops_variables.get_variables_provider", ...)` — import lazy en el módulo):
- `test_f3_flag_off_all_routes_404`.
- `test_f3_non_json_post_400` (91 C5).
- `test_f3_post_without_confirm_400` (HITL server-side).
- `test_f3_delete_without_confirm_400` (HITL server-side — C6, NUEVO).
- `test_f3_post_invalid_key_400`.
- `test_f3_post_happy_201_no_value_in_response` (texto crudo sin el value).
- `test_f3_get_lists_without_values`.
- `test_f3_ado_unavailable_409_kind` (GET: provider lanza `VariablesUnavailableError`).
- `test_f3_post_unavailable_409` (POST: la MISMA excepción mapea igual — C6, NUEVO).
- `test_f3_delete_absent_404`.
- `test_f3_tracker_config_400_kind` (C14a: el provider-factory mockeado lanza
  `TrackerConfigError("issue_tracker.type=gitlab pero ...")` ⇒ 400 con
  `kind == "tracker_config"` y el mensaje visible).
- `test_f3_unexpected_error_500_generic` (C14b: el provider lanza
  `RuntimeError("boom S3cr3t!XYZ")` ⇒ 500, body == mensaje genérico fijo, y el
  texto crudo de la respuesta NO contiene `S3cr3t!XYZ`).
- `test_f3_health_has_variables_enabled`.
- `test_f3_route_registered` (centinela url_map).

**Ratchet:** registrar. **Criterio binario:** 14 tests verdes; grep en
`api/devops_variables.py`: cero `logger`/`print` con `value`.
**Flag:** `STACKY_DEVOPS_VARIABLES_ENABLED` (guard per-request).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F4 — Frontend: sección "Variables" + "Mover a variable segura" en el builder

**Objetivo:** el candado visible y el puente 1-click desde el builder del 87.

**Archivo NUEVO:** `Stacky Agents/frontend/src/devops/variablesModel.ts` (puro):
- `looksSecret(key: string): boolean` y `validateVariableKey(key): string | null`
  — ESPEJO de F1 (incluida la regla `CRED(?!IT)` — C7); el test de paridad lee el
  MISMO fixture `backend/tests/fixtures/plan94_secret_hints.json` (patrón 88:
  paridad por datos).
- `splitSpecVariables(spec): {secretLooking: string[], plain: string[]}` (inmutable).
- **[ADICIÓN ARQUITECTO] A2** — `canBeMasked(value: string): boolean` — espejo
  PURO de las reglas de masking de GitLab: una sola línea (sin `\n`/`\r`),
  longitud ≥ 8, y todos los chars en el alfabeto Base64 más `@ : . ~` (regex
  literal `^[a-zA-Z0-9+\/=@:.~]{8,}$` — **C16: SIN `_` ni `-`, que GitLab NO
  acepta para masking; incluirlos daba falso "sí se puede"**). El value NUNCA se
  persiste: la función se evalúa on-change sobre el input y se descarta. El
  backend (reintento C8) sigue siendo la fuente de verdad.

**Archivo NUEVO:** `Stacky Agents/frontend/src/components/devops/VariablesSection.tsx`
- Props `{ ctx: DevOpsSectionContext }`. El gate de SU flag NO vive acá (lo
  renderiza el shell — entrada declarativa abajo).
- Lista (useQuery `["devops-variables", project]` → `DevOpsVariables.list`):
  fila = key + candado 🔒 si `is_secret` + badge "no enmascarable" si
  `masked === false` en la RESPUESTA DEL ALTA (efímero — C5: al refrescar,
  GitLab no distingue una secreta no enmascarable de una normal; el copy del badge
  lo dice: "GitLab no va a poder enmascarar este valor en los logs; al refrescar
  esta variable se lista sin candado — limitación del tracker"); botón Borrar
  (confirm → `POST /delete` con `confirm:true`).
- Form alta: key (validación local en vivo), value (`type="password"` si el
  checkbox "secreta" está tildado), checkbox "Es secreta 🔒" (pre-tildado si
  `looksSecret(key)`), **aviso A2 si el tracker es gitlab, "secreta" está tildado
  y `!canBeMasked(value)`: "este valor no va a poder enmascararse en los logs de
  GitLab (reglas de masking)" — informativo, NO bloquea (HITL: decide el
  operador)**, botón Guardar con `window.confirm` ⇒
  `DevOpsVariables.create({..., confirm:true})`. Value NUNCA se guarda en estado
  tras el submit (se limpia el input).
- Estado 409 `variables_unavailable` (ADO sin definición) ⇒ banner ámbar con el
  mensaje literal del backend + hint "Llevá el pipeline a producción (plan 95)".
- Errores async siempre visibles (patrón C16 87). Prohibido `console.*` único.

**Archivos a editar:**
- `frontend/src/api/endpoints.ts` — namespace nuevo `DevOpsVariables`
  (junto a `DevOps`, `endpoints.ts:3072`): `list(project)`,
  `create(body)` → POST, `remove(project, key)` → POST `/delete` (con
  `confirm:true` en el body).
- `frontend/src/pages/DevOpsPage.tsx` — UNA entrada declarativa en
  `DEVOPS_SECTIONS` (`:68`), shape EXACTO del contrato:
  ```ts
  {
    id: 'variables',
    label: 'Variables',
    icon: '🔒',
    healthKey: 'variables_enabled',
    gateFlagKey: 'STACKY_DEVOPS_VARIABLES_ENABLED',
    gateMessage: 'La sección Variables necesita la flag STACKY_DEVOPS_VARIABLES_ENABLED (Configuración → Arnés, categoría DevOps).',
    render: (ctx) => <VariablesSection ctx={ctx} />,
  },
  ```
  PROHIBIDO tocar el shell fuera del array (§3.12).
- `frontend/src/components/devops/PipelineBuilderSection.tsx` — si
  `ctx.health.variables_enabled === true` y `splitSpecVariables(spec).secretLooking`
  no vacío ⇒ warning ámbar "Estas variables parecen secretos y van a quedar EN EL
  YAML del repo: <keys>" + botón **"Mover a variable segura"** por key: modal con
  el value pre-cargado desde `spec.variables[key]` (`type="password"`, editable) →
  confirm → `DevOpsVariables.create` → al 201, quitar la key de `spec.variables`
  vía helper puro `removeSpecVariable(spec, key)` (agregar a `specBuilder.ts`,
  inmutable) → hint "Movida al tracker: usala igual, $VAR (GitLab) o $(VAR) (ADO)".
  **C13 — el mismo hint agrega, literal: "recommitteá el pipeline (botón Commit)
  para sacar el valor del YAML actual del repo" — mover la key del spec solo
  cambia el estado local; el YAML en HEAD sigue teniendo el secreto en texto
  plano hasta el próximo commit (modal del 87).**
  **[ADICIÓN ARQUITECTO] A1 — aviso de rotación (mismo bloque del hint, literal):**
  "Ojo: si este YAML ya se commiteó al repo, el valor sigue viviendo en la
  historia de git — rotá la credencial en el destino y actualizá la variable
  segura." (Mover la key del spec NO reescribe la historia; Stacky lo dice en
  llano en vez de fingir que el secreto nunca se filtró. Aplica igual a ADO y
  GitLab; informativo, cero trabajo extra, el operador decide.)
  Si `variables_enabled !== true` el warning muestra `FlagGateBanner` inline.

**Tests** — `frontend/src/devops/variablesModel.test.ts` (vitest TS puro):
- `looksSecret_shared_fixture_parity` (lee el JSON del backend, mismos 16 casos).
- `validate_key_mirror` (mismos casos que F1).
- `splitSpecVariables_detects` / `removeSpecVariable_immutable`.
- `canBeMasked_rules` (A2: corto ⇒ false; con `\n` ⇒ false; con espacio ⇒ false;
  `Abcd1234~` ⇒ true).
Componentes: gate `tsc`.

**Criterio binario:** vitest verde (5 tests, 1 parametrizado); `tsc` 0 errores;
la entrada del registro declara `healthKey/gateFlagKey/gateMessage` y
`VariablesSection.tsx` NO contiene el literal de su flag (gate del shell — grep);
`PipelineBuilderSection.tsx` contiene los literales "Mover a variable segura",
"historia de git" (A1 — grep) Y "recommitteá el pipeline" (C13 — grep).
**Flag:** `variables_enabled` (gate declarativo del shell + inline en builder).
**Runtimes:** sin impacto. **Trabajo del operador:** opt-in (flag por UI); cargar
variables ES la feature.

### F5 — Cierre: no-regresión + checklist binario

**Comandos:**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_plan94_variables_flag.py tests/test_plan94_variables_pure.py tests/test_plan94_variables_providers.py tests/test_plan94_variables_endpoints.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan87_devops_endpoints.py tests/test_harness_flags.py tests/test_flag_wiring.py tests/test_harness_flags_requires.py -q
cd "../frontend"
npx vitest run src/devops/variablesModel.test.ts
npx vitest run src/devops/specBuilder.test.ts
npx tsc --noEmit
```

**Checklist binario:**
- [ ] Flag OFF ⇒ endpoints 404, sección con FlagGateBanner del shell, builder sin
      warning nuevo, byte-idéntico.
- [ ] PARIDAD: proyecto GitLab crea variable masked por API; proyecto ADO con
      definición crea variable `isSecret` en la definition; ADO sin definición ⇒
      409 honesto con CTA (nunca falso éxito) — en GET, POST y delete (C6).
- [ ] El VALUE de un secreto no aparece en: respuesta de POST, respuesta de GET,
      texto de excepciones, logs (tests centinela verdes).
- [ ] `spec.variables` con key `DB_PASSWORD` ⇒ warning + "Mover a variable segura"
      la crea en el tracker, la saca del YAML y muestra el aviso de rotación (A1).
- [ ] GitLab masking rechazado ⇒ variable creada sin masked + badge honesto
      (efímero, con el copy C5).
- [ ] Crear Y borrar exigen confirm server-side (400 sin él — C6).
- [ ] `test_requires_map_is_frozen` verde con la arista nueva (C1).
- [ ] Secreta GitLab se crea con `raw:true` (A3 — test del body) ⇒ un value con
      `$` NO se expande en el job.
- [ ] `set_variable` ADO NO altera las variables hermanas `isSecret` que vienen
      con `value:null` del GET (C12 — test del body del PUT) + **verificación
      manual ÚNICA contra un ADO real: crear secreta A, luego setear variable B,
      confirmar en la web de ADO que A conserva su valor** (ambigüedad
      documentada de la API; una sola vez, antes de dar el plan por cerrado).
- [ ] `TrackerConfigError` ⇒ 400 `tracker_config`; excepción inesperada ⇒ 500
      genérico sin `str(e)` (C14).
- [ ] `PipelineSpec`/renderers/`test_f1_spec_shape_frozen` intactos.
- [ ] Tests registrados en ambos scripts de ratchet.

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Secreto fugado en excepción/log del tracker | Sanitización de excepciones (test `test_f2_no_value_in_exceptions`, patrón 91 C1) + grep centinela sin logger/print de value |
| ADO exige PUT full-definition ⇒ lost-update de variables ajenas o rechazo por `revision` | GET→merge→PUT con el JSON completo del GET (incluido `revision` — C4) + `test_f2_ado_set_merges_full_definition` |
| PUT ADO con `value:null` de secretos hermanos podría BORRARLOS (semántica ambigua de la API) | C12: entradas preexistentes viajan byte-idénticas (mutar el JSON del GET in place) + `test_f2_ado_set_preserves_secret_sibling` + verificación manual única en F5 |
| GitLab expande `$` dentro del value ⇒ password corrompida en silencio | A3: `raw:true` en secretas + `test_f2_gitlab_secret_sends_raw_true` |
| YAML en HEAD conserva el secreto tras "Mover a variable segura" | C13: CTA literal "recommitteá el pipeline (botón Commit)" en el hint post-move + grep |
| GitLab rechaza masked por reglas de valor | Aviso pre-guardado `canBeMasked` (A2) + reintento determinista `masked:false` (C8) + badge honesto en UI |
| Secreta no enmascarable pierde el candado al refrescar (GitLab sin bit "secreta") | Limitación documentada (§4 C5) + copy explícito en el badge + caso en test de list |
| GitLab pagina `GET /variables` de a 20 ⇒ listado truncado | `_request_paginated` obligatorio (C2) + fixture paginada en el test de list |
| ADO sin pipeline definition | `VariablesUnavailableError` ⇒ 409 con CTA al plan 95 en TODAS las rutas (C6); la sección degrada ámbar |
| Secreto ya commiteado antes del move (historia de git) | Aviso de rotación A1 en llano tras "Mover a variable segura" — nunca fingir que el move limpia la historia |
| Falsos positivos de la heurística (KEYBOARD, CREDIT_LIMIT) | Regex por tokens (APIKEY/API_KEY, no KEY suelta; `CRED(?!IT)` — C7) + fixture compartido congelado |
| Doble fuente de verdad Stacky↔tracker | El tracker ES la única fuente; Stacky no persiste nada de este plan |
| PAT sin scope (GitLab api / ADO Build RW) | TrackerApiError ⇒ 502 con mensaje visible; scopes documentados en PlainHelp |
| Bridge plan 91 (passwords de servidores → variables) | FUERA de scope v1; §3.10 del 91 sigue siendo el punto de consumo futuro (nota de compat, cero dependencia) |

## 7. Fuera de scope (v1)

- Bridge automático plan 91 → variables (nota de compatibilidad; requiere decisión
  de seguridad propia: copiar un password del Credential Manager al tracker es un
  movimiento de frontera de confianza que merece su propio plan/crítica).
- Variable groups ADO multi-pipeline (v1 usa variables de LA definition del YAML
  del panel; grupos compartidos quedan para cuando haya >1 definition).
- Scheduled rotation / expiración de secretos.
- Environments/protected branches scoping (protected:false fijo en v1).
- `environment_scope` GitLab (v1 asume el scope default `*`; una colisión de
  scopes múltiples propaga el error del tracker sanitizado como 502).

## 8. Glosario

- **Variable masked (GitLab)**: variable CI/CD cuyo valor se oculta en los logs
  del job; exige reglas de formato del valor.
- **Variable isSecret (ADO)**: variable de la pipeline definition cifrada por ADO;
  se referencia `$(KEY)` en el YAML sin declararla.
- **Write-only**: el valor entra por POST y nunca vuelve a salir por la API.
- **Pipeline definition (ADO)**: registro del pipeline en ADO que apunta al YAML;
  prerequisito de la pata ADO (la crea el plan 95). Su `revision` es un contador
  de versión que TODO PUT debe devolver tal cual vino del GET (C4).
- **VariablesUnavailableError**: excepción del sub-puerto cuando el tracker no
  puede alojar variables todavía (ADO sin definición) → 409 `variables_unavailable`
  en TODAS las rutas (C6).

## 9. Orden de implementación

1. F0 — flag (6 patas, C1 incluida).
2. F1 — helpers puros + fixture compartido de hints.
3. F2 — sub-puerto + adapters gitlab/ado (+ `ado_pipeline_definitions` si no existe).
4. F3 — blueprint endpoints + health key.
5. F4 — `variablesModel.ts` + `VariablesSection` + entrada declarativa + puente
   "Mover a variable segura" (con aviso de rotación A1) en el builder.
6. F5 — cierre.

## 10. Definición de Hecho (DoD)

- 35 tests backend nombrados (F0:5, F1:3, F2:13, F3:14) verdes por archivo con el
  venv + los 3 archivos de no-regresión de flags (incluido
  `test_harness_flags_requires.py` — C1).
- Vitest F4 verde (5 tests); `tsc` 0 errores; paridad heurística py↔ts por fixture
  compartido.
- Paridad ADO+GitLab por tests de ambos adapters; degradación ADO-sin-definición
  honesta (409 + CTA) en las TRES operaciones.
- Ningún secreto en respuestas/logs/excepciones (centinelas verdes).
- Flag OFF ⇒ byte-idéntico; shell (`DevOpsPage.tsx`) tocado SOLO en el array
  `DEVOPS_SECTIONS`; checklist F5 completo.
