# Plan 154 — Arnés veraz: ratchet, fixtures y guard de red

> **Estado:** PROPUESTO v1 (2026-07-16) · **Autor:** StackyArchitectaUltraEficientCode
> **Origen:** debate adversarial 2026-07-16 con auditoría empírica del arnés y de los logs del deploy. Toda la evidencia archivo:línea de este doc fue **re-verificada contra el árbol el 2026-07-16**; los números de línea son referencia de ese día — **toda edición se ancla por TEXTO normativo citado, no por número de línea**.
> **Orden en el roadmap:** este plan se implementa **primero**, junto con el plan del ledger de publicación (son independientes entre sí; ninguno bloquea al otro). Es prerequisito moral del resto del roadmap: todo lo demás se construye sobre un arnés que dice la verdad.
> **Runtimes:** este plan es **infraestructura de tests backend**, 100% agnóstico del runtime de agentes (Codex CLI, Claude Code CLI, GitHub Copilot Pro). Ninguna fase toca el camino de ejecución de agentes; la paridad de los 3 runtimes es automática por vacuidad. Se declara igual por fase.
> **Flags nuevas:** **NINGUNA de operador.** Se introduce UNA env var interna **test-only sin UI** (`STACKY_TEST_ALLOW_WATCHER_SELF_POST`, F5.iii). Justificación de la excepción a la regla "toda config del operador va por UI": NO es config del operador — es infraestructura de tests, invisible en runtime normal, mismo estatus que `STACKY_TEST_MODE` (que tampoco está en `FLAG_REGISTRY` ni tiene panel). NO se toca `FLAG_REGISTRY`, NO se toca `_CURATED_DEFAULTS_ON`, NO hay panel nuevo.
> **Human-in-the-loop:** N/A — no hay acciones automáticas hacia afuera; al contrario, F5 **ELIMINA** egress no deseado (los tests hoy tocan la org ADO productiva).

---

## 1. Objetivo + KPI / impacto esperado

**Objetivo (1 párrafo):** el arnés de tests — la maquinaria cuya única función es decir la verdad — hoy miente en 4 modos a la vez: está **ROJO** (el meta-test del ratchet falla por 30 archivos sin clasificar), tiene un **falso VERDE** (un test de plan105 pasa por la razón equivocada sin ejercitar jamás el branch que dice probar), tiene **6 rojos que son bugs de fixture** (helpers de test que escriben un payload de 4 campos contra un contrato de 9), y mientras corre hace **egress de red REAL** a la org ADO productiva y al backend dev vivo. Este plan restaura la señal "arnés verde = verdad" y hace estructuralmente imposibles dos clases enteras de bug futuro: la clase "flag leída con `os.getenv` + default hardcodeado divergente de `config.py`" (3ra ocurrencia conocida) y la clase "test que sale a la red real".

**KPIs binarios (comando exacto; pytest SIEMPRE desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend` con `.venv\Scripts\python.exe`, que es el venv real verificado en disco — `backend/venv` NO existe):**

- **KPI-1 — Ratchet verde:** `.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q` → exit 0 (incluye el test nuevo de F6).
- **KPI-2 — Output watcher 30/30:** `.venv\Scripts\python.exe -m pytest tests/test_output_watcher.py -q` → exit 0, **30 passed**; `grep -c "test_output_watcher" tests/harness_ratchet_allowlist.txt` → `0`; `grep -c "test_output_watcher" scripts/run_harness_tests.sh` → `1` y lo mismo en `scripts/run_harness_tests.ps1` → `1`.
- **KPI-3 — Plan105 13/13 honesto:** `.venv\Scripts\python.exe -m pytest tests/test_plan105_remote_console_api.py -q` → exit 0, **13 passed**, con la verificación por mutación de F3 documentada en el mensaje de commit/PR.
- **KPI-4 — Clase config-mal-leída cerrada:** `.venv\Scripts\python.exe -m pytest tests/test_flags_env_read_meta.py -q` → exit 0, y con entorno limpio (sin la env var seteada) `GET /api/executions/history` responde **200** en dev (test incluido en el mismo archivo).
- **KPI-5 — Cero egress desde pytest:** el guard de F5 está activo (test que lo prueba, verde) y una corrida del arnés por archivo no genera NINGUNA línea nueva en el access-log del backend dev vivo ni tráfico a `dev.azure.com` (verificación manual documentada del implementador).
- **KPI-6 — Grandfathered congelado:** editar `tests/harness_ratchet_allowlist.txt` agregando una entrada sin quitar otra hace fallar `test_harness_ratchet_meta.py` (test de F6, demostrado y revertido durante la implementación).
- **KPI-7 — Ratchet auto-registrado:** `grep -c "test_flags_env_read_meta.py" scripts/run_harness_tests.sh` → `1` e ídem en `scripts/run_harness_tests.ps1` → `1` (el meta-test nuevo también entra al arnés: el ratchet se audita a sí mismo).

**Impacto esperado:** la corrida completa del arnés pasa de roja-estructural a verde-veraz; 6 tests de intake pasan a validar el contrato real de 9 campos con aserciones sobre el artefacto (no solo status); 1 falso verde pasa a ejercitar el branch que dice probar; la página de historial de ejecuciones deja de estar muerta en deploys frescos; y queda **estructuralmente imposible** (a) reintroducir una lectura de flag divergente en `backend/api/` o `backend/services/`, (b) que un test futuro salga a la red real, (c) que la allowlist de deuda crezca en silencio.

---

## 2. Por qué ahora / gap que cierra (evidencia verificada 2026-07-16)

### 2.1 T1 — El meta-test del ratchet está ROJO HOY (30 archivos sin clasificar)

- `backend/tests/test_harness_ratchet_meta.py:43` — `test_ratchet_clasifica_todos_los_tests` exige que TODO `tests/test_*.py` esté en `HARNESS_TEST_FILES` (`backend/scripts/run_harness_tests.sh`) o en `tests/harness_ratchet_allowlist.txt`.
- Conteo en frío 2026-07-16 (replicando la lógica exacta del meta-test): **536** archivos `test_*.py` totales, **308** en `HARNESS_TEST_FILES`, **198** en la allowlist → **30 sin clasificar**. El meta-test SÍ está en el arnés (`run_harness_tests.sh:60`) → **la corrida completa del arnés está roja HOY**.
- Los 30 (lista exacta verificada; recontar en F0 porque otros planes corren en paralelo): `test_ado_client_stacky_name_resolution`, `test_documenter_autonomy`, `test_local_llm_model_fallback_and_ticket_insight`, `test_plan122_dbcompare_{api,engine,flags,registry,snapshot}`, `test_plan123_dbcompare_{api,diff,export,runs}`, `test_plan125_dbcompare_{bundle,emitters_oracle,emitters_sqlserver,flatten,preflight,scripts_api,sqlnames,toposort}`, `test_plan126_dbcompare_{data_api,data_diff,data_flags,data_scripts,sqlvalues}`, `test_plan139_shell_flag`, `test_plan98_bootstrap_{endpoint,flag}`, `test_plan98_profile_key_{patch,validators}`.

### 2.2 T3 — 6 rojos en `tests/test_output_watcher.py` que son bugs de FIXTURE, no de producto

- Los 6 rojos (defs verificadas): `test_mode_a_invokes_create_child_task_endpoint` (`:536`), `test_mode_a_auto_creates_without_running_execution` (`:575`), `test_mode_a_auto_corrects_human_ep_label_dir` (`:614`), `test_mode_a_terminal_4xx_is_quarantined_not_retried` (`:676`), `test_mode_a_transient_auto_create_error_is_not_cached` (`:719`), `test_mode_a_auto_creates_from_alt_base_when_canonical_missing` (`:753`).
- Causa raíz probada empíricamente (verificación diferencial: con el flag de intake OFF, pasan): el helper `_write_pending_task` (`tests/test_output_watcher.py:144-156`, ídem `_write_pending_task_alt` `:174-190`) escribe solo **4 campos** `{rf_id, title, status, generated_at}`. El gate de intake V1.3 (`services/output_watcher.py:1005`, flag `STACKY_ARTIFACT_INTAKE_ENABLED` con default efectivo `true` desde `84a9ecb5` 2026-07-04) valida con `artifact_intake._validate_schema` (`services/artifact_intake.py:183-194`), que vía `artifact_validator._required_fields()` (`services/artifact_validator.py:44-47`) exige los **9 campos** de `_PENDING_TASK_REQUIRED_FIELDS` (`api/tickets.py:48-52`): `generated_at, generated_by, epic_id, rf_id, title, description_html, plan_de_pruebas_path, parent_link_type, status`. Resultado: **cuarentena ANTES del POST** — el mock de `requests.post` nunca se invoca (`assert 0 == N`).
- Con `epic_id` presente e igual al ADO id del epic del test, la regla anti-ordinal también pasa: `_intake_valid_ado_ids` (`services/output_watcher.py:697`, llamado en `:1023`) incluye el epic fuente.
- **NO tocar código de producción del intake:** su comportamiento es by-design del plan de robustez de intake. El bug es del fixture.
- El archivo está en la allowlist (`tests/harness_ratchet_allowlist.txt:142`, motivo `pendiente-de-triage`) → **nada gatea estos rojos hoy**. Al quedar verde, se mueve a `HARNESS_TEST_FILES`.

### 2.3 T2 — Falso verde + rojo hermano en `tests/test_plan105_remote_console_api.py`

- El archivo SÍ está en el arnés (`run_harness_tests.sh:164`) → miembro **rojo HOY**. Tiene 13 tests.
- **El rojo** `test_f2_exec_write_requires_conversation_flag` (def `:125`): su fixture (`:140`) escribe `description='{...,"write_enabled":False}'` — `False` con mayúscula es **literal Python, JSON inválido**. La cadena de fallos: `_conv_meta` tolerante devuelve `{}` ante JSON inválido (`api/devops_remote_console.py:43-46`); el toggle de write-mode (`:366-368`) hace `meta = _conv_meta(ticket)` → `ticket.description = json.dumps(meta)`, **reescribiendo la description y PERDIENDO `server_alias`**; el gate de ejecución exige `meta.get("server_alias") == alias` (`:80`) → `mode` queda `read_only` para siempre. Probado empíricamente: con `json.dumps` el test pasa.
- **El falso verde** `test_f2_write_mode_wrong_alias_stays_read_only` (def `:172`, literal `True` en el fixture `:187`): pasa por la razón equivocada — el JSON inválido hace que `_conv_meta` devuelva `{}` y el modo quede `read_only` SIN ejercitar jamás el branch de mismatch de alias que el test dice probar.
- **Tercera ocurrencia detectada en la verificación de este plan (drift respecto del debate, que citaba 2):** `test_f2_write_mode_toggle_audited` (fixture `:359`, literal `False`). Hoy pasa igual porque solo aserta la entrada de auditoría, pero su conversación también tiene la description corrupta. Se corrige junto con las otras dos.

### 2.4 L4 — Clase "config-mal-leída" (3ra ocurrencia conocida)

- `backend/api/executions.py:291` — lee la env var `STACKY_EXECUTION_HISTORY_ENABLED` directo del entorno con **default hardcodeado `"false"`**, ignorando `backend/config.py:519-521` (default `"true"`) y la `FlagSpec` curada default ON (`services/harness_flags.py:1507-1518`, curada en `:244`).
- `backend/.env.example:191` documenta "default: false" (drift de doc).
- **Consecuencia:** `GET /api/executions/history` devuelve `404 feature_disabled` en cualquier entorno sin la env var explícita (deploy fresco) — **la página de historial está muerta** aunque la flag curada diga ON.
- Ocurrencias previas de la misma clase: plan 131 y plan 148 (gotcha `config` módulo vs `config.config` instancia en `api/tickets.py`). Tres ocurrencias = clase de bug, no accidente → merece meta-test (F4).

### 2.5 T4+L5 — Egress de red REAL desde pytest (a la org ADO productiva)

- Los logs auditados muestran GET/POST reales a `dev.azure.com` **org productiva Ubimia-STAB-SAAS** durante corridas de tests (`System.Rev` de un WI mock `123`, `POST $Feature`) más **80 POSTs al backend dev vivo**.
- Causa 1 verificada: `_startup_sync` (`backend/app.py:55`, invocado en `:404` dentro de `create_app`) **NO está gateado por `STACKY_TEST_MODE`**. Si hay proyecto activo configurado, cualquier test que llame `create_app()` dispara sync real contra ADO. El único gate de test-mode existente es el del daemon edit-learning (`app.py:501-504`) — el patrón exacto a calcar.
- Causa 2 verificada: el self-POST del watcher sale de `services/output_watcher.py:990` (`http://127.0.0.1:{port}/api/tickets/by-ado/{id}/create-child-task`). Es **loopback**, así que un guard "bloquear no-loopback" NO lo toca — pero si el backend dev está vivo en ese puerto (escenario real conocido: dos backends vivos en la misma máquina), el test **crea tasks reales en la DB viva**.
- La infraestructura de gating YA existe: `tests/conftest.py:11` setea `STACKY_TEST_MODE=1` para toda la suite. Falta **consumirla** en estos 2 puntos.

### 2.6 T4b — Deuda: 198 archivos grandfathered sin gate

- `tests/harness_ratchet_allowlist.txt` tiene **198** entradas, casi todas con motivo `pendiente-de-triage` — el 37% de la suite sin gate. Es la semilla del plan 49 F4 cuyo triage de seguimiento nunca se hizo. Este plan NO hace el triage (fuera de scope) pero **congela el contador** para que la deuda solo pueda BAJAR (F6).

### 2.7 Infra existente que se REUSA (leída, no supuesta)

| Símbolo | Archivo:línea (2026-07-16) | Rol en 154 |
|---|---|---|
| `test_ratchet_clasifica_todos_los_tests` + helpers `_ratchet_files`/`_allowlist`/`_all_test_files` | `backend/tests/test_harness_ratchet_meta.py:18-55` | F0 replica su lógica para la baseline; F6 agrega un test hermano en el MISMO archivo (ya registrado en el arnés → cero registro extra). |
| Gate test-mode del daemon edit-learning | `backend/app.py:501-504` (`_test_mode = os.environ.get("STACKY_TEST_MODE", ...)`) | Patrón EXACTO que F5.ii calca para `_startup_sync`. |
| `tests/conftest.py` | `backend/tests/conftest.py:11` (`os.environ.setdefault("STACKY_TEST_MODE", "1")`) | F5.i agrega ahí el fixture autouse del guard de sockets. |
| Check del flag auto-create del watcher | `services/output_watcher.py:981` (early-return si el flag es `"false"`) | Ancla de F5.iii: el gate test-only se inserta inmediatamente después, replicando la MISMA forma de retorno. |
| `_PENDING_TASK_REQUIRED_FIELDS` | `backend/api/tickets.py:48-52` | Contrato canónico de 9 campos que la factory de F2 satisface. |
| Valor canónico de `parent_link_type` | `backend/api/tickets.py:2981` (`payload.setdefault("parent_link_type", "System.LinkTypes.Hierarchy-Reverse")`) | Valor que usa la factory de F2. |
| Statuses permitidos | `services/artifact_validator.py:39` (`pending_manual_creation`, `pending`, `consumed`) | La factory usa `pending_manual_creation`. |
| `FLAG_REGISTRY` | `services/harness_flags.py` | F4 intersecta las ocurrencias grepeadas con las keys registradas (evita falsos positivos con env vars internas como `STACKY_TEST_MODE`). |
| `.env.example` | `backend/.env.example` (NO tiene generador; se copia en build, `deployment/build_release.ps1:572`; el generado es `harness_defaults.env`, otro archivo, PROHIBIDO tocarlo a mano) | F4 edita a mano la línea `:191` — es seguro. |

---

## 3. Principios y guardarraíles

1. **El arnés dice la verdad o no sirve.** Cero falsos verdes: cada fix de test debe demostrarse ejercitando el branch real (F3 lo prueba por mutación manual). Cero rojos huérfanos: todo test o está en el arnés o está en la allowlist con motivo explícito.
2. **Fixes test-only donde el bug es del test.** T3 y T2 se arreglan SIN tocar código de producción: el intake V1.3 y `_conv_meta` se comportan by-design. Los únicos toques a producción son L4 (`api/executions.py`, un bug real de lectura de flag) y F5.ii/F5.iii (gates de test-mode en 2 call-sites, no-op en runtime normal).
3. **Cero trabajo extra al operador.** Ninguna config nueva de operador; todo automático y backward-compatible. La env var de F5.iii es interna test-only sin UI (mismo estatus que `STACKY_TEST_MODE`). En runtime normal (sin `STACKY_TEST_MODE`) el comportamiento es byte-idéntico al actual.
4. **`STACKY_TEST_MODE` es la única llave de test.** No se inventa un segundo mecanismo de detección de pytest: los gates nuevos leen la misma env var que `tests/conftest.py:11` ya setea y que `app.py:501-504` ya consume.
5. **Los meta-tests se auditan a sí mismos.** Todo meta-test nuevo entra a `HARNESS_TEST_FILES` en `run_harness_tests.sh` **Y** `run_harness_tests.ps1` (los dos, siempre — gotcha recurrente).
6. **Ratchets sin slack.** F6 congela el contador de la allowlist en el valor exacto recontado en frío; quien limpia entradas DEBE bajar la constante en el mismo commit.
7. **No degradar nada.** Perf: los gates son 1 lectura de env var. Seguridad: F5 la MEJORA (cero riesgo de tocar la org ADO productiva o la DB viva desde tests). DX: la suite deja de depender de si el backend dev está corriendo.
8. **Mono-operador sin auth.** Nada de RBAC; no aplica a este plan (no hay endpoints nuevos).
9. **Anti-gamear gates.** La prosa de comentarios y docstrings en `backend/api/` y `backend/services/` NO debe contener el patrón literal que caza el grep de F4 (ver §9, gotcha con 6 recurrencias históricas). El gate siempre gana: se reescribe la prosa, jamás se relaja el gate.

---

## 4. Glosario (para un modelo menor que no conoce Stacky)

| Término | Definición |
|---|---|
| **ratchet** | Mecanismo "solo puede mejorar": un test que congela un contador o inventario de deuda y falla si la deuda crece. Bajar está permitido; subir rompe. |
| **HARNESS_TEST_FILES** | Lista explícita de archivos de test que la corrida oficial del arnés ejecuta, definida DOS veces: en `backend/scripts/run_harness_tests.sh` (formato: una línea `  tests/test_x.py` dentro del array) y en `backend/scripts/run_harness_tests.ps1` (formato: `  "tests/test_x.py",`). Todo registro va SIEMPRE en ambos. |
| **allowlist** | `backend/tests/harness_ratchet_allowlist.txt`: archivos de test EXCLUIDOS del arnés, uno por línea, con motivo tras `#`. Es la válvula de escape del ratchet del plan 49. |
| **grandfathered** | Entrada de la allowlist heredada con motivo genérico `pendiente-de-triage`: nadie evaluó si el archivo puede correr en el arnés. Hoy: 198. |
| **meta-test** | Test que verifica propiedades del PROPIO repo/arnés (no del producto): p. ej. "todo test está clasificado", "ningún archivo lee flags con default hardcodeado". |
| **mode_a** | Modo del `output_watcher` que detecta `pending-task.json` estables producidos por agentes y auto-crea las Tasks hijas vía POST al endpoint `create-child-task`. |
| **pending-task.json** | Artefacto que un agente deja en disco describiendo una Task a crear en el tracker. Contrato canónico: los 9 campos de `_PENDING_TASK_REQUIRED_FIELDS` (`api/tickets.py:48-52`). |
| **intake V1.3** | Gate de validación universal (flag `STACKY_ARTIFACT_INTAKE_ENABLED`, default ON) que todo artefacto file-based atraviesa ANTES de encolarse: reparación determinista + schema + regla anti-ordinal. Si falla → cuarentena con errores legibles. |
| **anti-ordinal** | Regla del intake que rechaza `epic_id` que parezcan ordinales inventados (1, 2, 3…) en vez de ADO ids reales; valida contra el set de ids conocidos del contexto (`_intake_valid_ado_ids`). |
| **cuarentena** | Marca persistente sobre un `pending-task.json` inválido para no reprocesarlo en cada scan; el artefacto NUNCA llega a ADO. |
| **factory (de payload)** | Función de test que construye un payload VÁLIDO y canónico con overrides opcionales, para que todos los tests compartan el mismo contrato en vez de duplicar dicts a mano. |
| **STACKY_TEST_MODE** | Env var interna (sin UI, no está en `FLAG_REGISTRY`) que `tests/conftest.py` setea a `"1"` para toda la suite. Señal única de "estamos bajo pytest". |
| **egress** | Tráfico de red saliente. En este plan: cualquier conexión de socket que un test abra hacia fuera de loopback (127.0.0.1/::1), o hacia un servicio real vivo en loopback. |
| **falso verde** | Test que pasa sin ejercitar el comportamiento que dice probar; peor que un rojo porque da confianza falsa. |
| **verificación por mutación** | Técnica manual: romper a propósito el branch de producción que el test dice cubrir; si el test NO falla, el test es falso verde. Se revierte la mutación tras verificar. |

---

## 5. Fases

> **Pre-flight OBLIGATORIO por fase que toque archivo caliente** (`backend/app.py`, `backend/api/executions.py`, `backend/services/output_watcher.py`, `backend/tests/conftest.py`, `backend/scripts/run_harness_tests.sh`, `backend/scripts/run_harness_tests.ps1`, `tests/harness_ratchet_allowlist.txt`): `git status -- "<ruta>"`. Si hay WIP ajeno, STOP y avisar al orquestador (sesiones paralelas en el mismo árbol son un escenario real conocido). Staging quirúrgico por path explícito. **El implementador NO commitea** (lo hace el orquestador).
>
> **Comandos:** pytest SIEMPRE por archivo desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend` con `.venv\Scripts\python.exe -m pytest tests/<archivo> -q` (equivalente POSIX: `cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/<archivo> -q`). NUNCA suite completa en un solo proceso: cross-file pollution conocida y documentada en este repo.
>
> **Orden de implementación REAL (no coincide con la numeración):** F0 → F1 → F3 → F4 → F5 → F2 → F6. Motivo duro: **F2 depende de F5.iii** — al volver válidos los payloads de los helpers, los tests de `test_output_watcher.py` que NO mockean `requests.post` dispararían el self-POST real del watcher contra el backend dev vivo (escenario real: dos backends vivos en la misma máquina). El gate de F5.iii debe existir ANTES de que F2 haga válidos esos payloads. F6 va último porque congela el contador DESPUÉS de que F2 saque `test_output_watcher.py` de la allowlist.

---

### F0 — Baseline documentada del ratchet (recontar en frío)

**Objetivo (1 frase):** dejar registrado el número EXACTO y la lista EXACTA de tests sin clasificar al momento de implementar, recontados en frío (otros planes corren en paralelo y la lista de §2.1 es la de HOY). **Valor:** la implementación arranca de una foto verificada, no de un dato heredado que pudo driftear.

**Archivos:** ninguno se modifica (fase de solo lectura).

**Procedimiento EXACTO:**

1. Desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`, ejecutar este snippet (replica la lógica EXACTA del meta-test, `tests/test_harness_ratchet_meta.py:18-55`):

```
.venv\Scripts\python.exe -c "import re, pathlib; B = pathlib.Path('.').resolve(); text = (B/'scripts/run_harness_tests.sh').read_text(encoding='utf-8'); ratchet = set(re.findall(r'^\s*(tests/[\w/]+\.py)\s*$', text, re.MULTILINE)); allow = {l.split('#',1)[0].strip() for l in (B/'tests/harness_ratchet_allowlist.txt').read_text(encoding='utf-8').splitlines() if l.split('#',1)[0].strip()}; todos = {p.relative_to(B).as_posix() for p in (B/'tests').rglob('test_*.py')}; sin = sorted(todos - ratchet - allow); print('total:', len(todos), 'ratchet:', len(ratchet), 'allow:', len(allow), 'sin_clasificar:', len(sin)); [print(' -', s) for s in sin]"
```

2. Copiar la salida completa (números + lista) en el resumen de implementación y en el mensaje de commit de F1.
3. Confirmar el rojo actual: `.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q` → debe FALLAR hoy con la lista de sin-clasificar en el mensaje. Si ya está verde (otro plan lo arregló en paralelo), STOP en F1 y reportar al orquestador; el resto de fases sigue igual.

**Criterio de aceptación BINARIO:** la salida del snippet (números exactos + lista) está pegada en el resumen/commit. Al 2026-07-16 la referencia es `total: 536, ratchet: 308, allow: 198, sin_clasificar: 30`.

**Flag:** N/A. **Runtimes:** N/A (solo lectura). **Trabajo del operador: ninguno.**

---

### F1 — Clasificar los 30 sin clasificar (arnés o allowlist con motivo)

**Objetivo (1 frase):** correr cada uno de los 30 archivos AISLADO con el venv real y clasificarlo: verde aislado → `HARNESS_TEST_FILES` (sh Y ps1); requiere entorno especial → allowlist con motivo ESPECÍFICO (jamás `pendiente-de-triage`). **Valor:** el meta-test del ratchet vuelve a verde y la corrida completa del arnés recupera sentido.

**Archivos:**
- MODIFICADO `backend/scripts/run_harness_tests.sh` (bloques nuevos comentados por plan de origen)
- MODIFICADO `backend/scripts/run_harness_tests.ps1` (los MISMOS bloques, sintaxis PowerShell)
- MODIFICADO `backend/tests/harness_ratchet_allowlist.txt` (solo si algún archivo requiere entorno especial)

**Procedimiento EXACTO:**

1. Por CADA archivo de la lista de F0, ejecutar aislado:

```
.venv\Scripts\python.exe -m pytest tests/<archivo> -q
```

2. Regla de decisión (sin excepciones):
   - **exit 0** → agregarlo a `HARNESS_TEST_FILES` en `run_harness_tests.sh` (una línea `  tests/<archivo>` dentro del array, en un bloque con comentario del plan de origen, mismo formato que los bloques vecinos, p. ej. `# — Plan 122 · Comparador BD núcleo —`) **Y** en `run_harness_tests.ps1` (línea `  "tests/<archivo>",` en el bloque equivalente).
   - **falla por dependencia externa** (servicio no disponible: Ollama/modelo local, red, binario ausente — leer el traceback, no adivinar) → allowlist con motivo específico, p. ej. `tests/test_local_llm_model_fallback_and_ticket_insight.py  # requiere Ollama local vivo`.
   - **falla por bug real** (assert de lógica, no de entorno) → NO esconderlo: reportar el archivo y el traceback al orquestador en el resumen. Si el fix es de test (fixture drift) y trivial (menos de ~10 líneas), arreglarlo en esta fase; si apunta a producción, va a la allowlist con motivo `ROJO conocido — <causa en 1 frase>; pendiente plan de limpieza` y queda EXPLÍCITO en el resumen final.
3. Agrupación esperada de los 30 por plan de origen (para los comentarios de bloque): plan 122 (5 archivos), plan 123 (4), plan 125 (8), plan 126 (5), plan 139 (1), plan 98 (4), sueltos (3: `test_ado_client_stacky_name_resolution`, `test_documenter_autonomy`, `test_local_llm_model_fallback_and_ticket_insight`).
4. Nota de contexto (no vinculante): los `test_planNNN_dbcompare_*` corrieron verdes por archivo durante la implementación de la serie 122-126; lo esperable es que la mayoría vaya al arnés.

**Criterio de aceptación BINARIO:** `.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q` → exit 0. Y `grep -c "pendiente-de-triage" tests/harness_ratchet_allowlist.txt` NO aumentó respecto de la baseline de F0.

**Flag:** N/A. **Runtimes:** N/A (registro de tests). **Trabajo del operador: ninguno.**

---

### F2 — Factory canónica de payload de intake + 6 mode_a verdes con aserciones reales

**Objetivo (1 frase):** crear `make_intake_payload()` con los 9 campos del contrato canónico, migrar los helpers de `test_output_watcher.py` a usarla, endurecer las aserciones de los 6 tests (artefacto completo, no solo status) y mover el archivo de la allowlist al arnés. **Valor:** los 6 rojos se vuelven verdes VERACES que validan el contrato real de intake de punta a punta.

**⚠️ DEPENDENCIA DURA: implementar DESPUÉS de F5** (ver orden en el preámbulo de §5). Sin el gate de F5.iii, los payloads válidos harían que los tests sin mock de `requests.post` posteen contra el backend dev vivo.

**Archivos:**
- NUEVO `backend/tests/intake_fixtures.py`
- MODIFICADO `backend/tests/test_output_watcher.py` (helpers + aserciones de los 6 tests + opt-in de F5.iii donde corresponda)
- MODIFICADO `backend/tests/harness_ratchet_allowlist.txt` (QUITAR la línea de `test_output_watcher.py`)
- MODIFICADO `backend/scripts/run_harness_tests.sh` y `backend/scripts/run_harness_tests.ps1` (AGREGAR `tests/test_output_watcher.py` en un bloque `# — Plan 154 · Arnés veraz —`)

**Contenido EXACTO de `backend/tests/intake_fixtures.py`:**

```python
"""Plan 154 F2 — Factory canónica de payloads pending-task para tests.

Única fuente de verdad de un payload VÁLIDO según el contrato de intake:
los 9 campos de _PENDING_TASK_REQUIRED_FIELDS (api/tickets.py). Cualquier
test que necesite un pending-task.json válido usa esta factory; los tests
que prueban payloads INVÁLIDOS los construyen a mano a propósito.
"""
from __future__ import annotations


def make_intake_payload(
    *,
    rf_id: str,
    epic_ado_id: int,
    title: str = "test",
    status: str = "pending_manual_creation",
    generated_at: str = "2026-05-16T00:00:00Z",
    **overrides,
) -> dict:
    """Payload pending-task válido con los 9 campos canónicos.

    epic_ado_id debe ser el ADO id REAL del epic del test (la regla
    anti-ordinal del intake lo valida contra _intake_valid_ado_ids).
    overrides pisa cualquier campo (incluso para romperlo a propósito).
    """
    payload = {
        "rf_id": rf_id,
        "title": title,
        "status": status,
        "generated_at": generated_at,
        "generated_by": "pytest-intake-fixture",
        "epic_id": int(epic_ado_id),
        "description_html": "<p>generado por tests (plan 154)</p>",
        "plan_de_pruebas_path": "outputs/plan_de_pruebas.md",
        "parent_link_type": "System.LinkTypes.Hierarchy-Reverse",
    }
    payload.update(overrides)
    return payload
```

(`System.LinkTypes.Hierarchy-Reverse` es el valor canónico que la producción defaultea en `api/tickets.py:2981`; `pending_manual_creation` es el status canónico de `artifact_validator.py:39`.)

**Migración de los helpers** (anclas de texto: `def _write_pending_task(` y `def _write_pending_task_alt(` en `tests/test_output_watcher.py`, hoy `:144` y `:174`): en AMBOS, reemplazar el dict literal de 4 campos dentro de `p.write_text(_json.dumps({...}), ...)` por:

```python
    from tests.intake_fixtures import make_intake_payload
    p.write_text(
        _json.dumps(make_intake_payload(rf_id=rf_id, epic_ado_id=epic_ado_id)),
        encoding="utf-8",
    )
```

(en `_write_pending_task_alt` conservar `title="test-alt"` y `generated_at="2026-06-01T00:00:00Z"` como overrides para no cambiar más que lo necesario). Si el import relativo `from tests.intake_fixtures` falla por sys.path, usar `from intake_fixtures import make_intake_payload` — `tests/conftest.py` ya inserta `backend/` en sys.path; verificar cuál resuelve y usar UNO consistentemente.

**Casos borde a respetar:**
- `test_mode_a_invalid_pending_task_is_terminal_skip` (`:649`) y cualquier otro test que escriba payloads inválidos A PROPÓSITO: **NO migrarlos a la factory** (o migrarlos usando `overrides` que borren campos explícitamente). Antes de tocar, grepear dentro del archivo qué tests escriben JSON a mano sin pasar por los helpers.
- Todos los tests del archivo que **monkeypatchean `requests.post`** (grep interno: `monkeypatch.setattr(_req` — hoy son los 6 rojos más `test_mode_a_does_not_create_child_tasks_when_flag_off` y `test_mode_a_invalid_pending_task_is_terminal_skip`) deben setear el opt-in de F5.iii: `monkeypatch.setenv("STACKY_TEST_ALLOW_WATCHER_SELF_POST", "1")`. Sin eso, el gate de F5.iii corta el auto-create antes del mock y los asserts de conteo vuelven a fallar (o peor: pasan por la razón equivocada en los tests de "0 llamadas").

**Aserciones endurecidas en los 6 tests** (el body del POST del watcher NO embebe el payload: lleva `pending_task_path`/`operator_reason`/`completion_source`, `services/output_watcher.py:1093-1100`; por eso el contrato se afirma sobre el ARTEFACTO en disco que el POST referencia — corrección de drift respecto del texto del debate, que asumía el payload dentro del body). En cada uno de los 6, además de los asserts existentes de conteo/URL, agregar:

```python
    import json as _json
    from api.tickets import _PENDING_TASK_REQUIRED_FIELDS
    on_disk = _json.loads(pt_path.read_text(encoding="utf-8"))
    assert _PENDING_TASK_REQUIRED_FIELDS <= set(on_disk.keys())
    assert on_disk["epic_id"] == <ado id del epic del test>   # p. ej. 40207
    assert on_disk["parent_link_type"] == "System.LinkTypes.Hierarchy-Reverse"
    assert call["body"]["pending_task_path"]  # el POST referencia el artefacto
```

(donde `pt_path` es el retorno de `_write_pending_task(...)`, que ya devuelve el Path; el intake puede reescribir el archivo al reparar — releerlo de disco DESPUÉS de `scan_once()` es correcto y deliberado).

**Movimiento de ratchet:** quitar la línea `tests/test_output_watcher.py  # pendiente-de-triage` de la allowlist (hoy `:142`) y agregar `tests/test_output_watcher.py` a `HARNESS_TEST_FILES` en sh Y ps1, bloque `# — Plan 154 · Arnés veraz —`.

**Criterio de aceptación BINARIO:** `.venv\Scripts\python.exe -m pytest tests/test_output_watcher.py -q` → exit 0 con **30 passed** (los 30 del archivo, no solo los 6); `grep -c "test_output_watcher" tests/harness_ratchet_allowlist.txt` → `0`; `grep -c "test_output_watcher" scripts/run_harness_tests.sh` → `1`; ídem `.ps1` → `1`; y `.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q` sigue exit 0.

**Flag:** N/A (fix de tests). **Runtimes:** N/A — el intake es camino compartido; ningún runtime se toca. **Trabajo del operador: ninguno.**

---

### F3 — Plan105: matar el falso verde y el rojo (JSON válido en fixtures + prueba de branch)

**Objetivo (1 frase):** reemplazar los 3 fixtures con literales Python (`False`/`True` en un string que debía ser JSON) por `json.dumps`, y DEMOSTRAR por mutación manual que el branch de mismatch de alias queda ejercitado. **Valor:** el archivo pasa de "1 rojo + 1 falso verde + 1 verde frágil" a 13/13 veraces.

**Archivos:**
- MODIFICADO `backend/tests/test_plan105_remote_console_api.py` (solo 3 líneas de fixture)

**Ediciones EXACTAS** (anclas de texto; el archivo ya usa el patrón correcto `description=json.dumps({...})` en `:261` y `:271` — calcarlo):

1. En `test_f2_exec_write_requires_conversation_flag` (fixture hoy `:140`):
   - ANTES: `description='{"kind":"remote_console","server_alias":"s1","write_enabled":False}',`
   - DESPUÉS: `description=json.dumps({"kind": "remote_console", "server_alias": "s1", "write_enabled": False}),`
2. En `test_f2_write_mode_wrong_alias_stays_read_only` (fixture hoy `:187`):
   - ANTES: `description='{"kind":"remote_console","server_alias":"A","write_enabled":True}',`
   - DESPUÉS: `description=json.dumps({"kind": "remote_console", "server_alias": "A", "write_enabled": True}),`
3. En `test_f2_write_mode_toggle_audited` (fixture hoy `:359` — tercera ocurrencia detectada al verificar este plan):
   - ANTES: `description='{"kind":"remote_console","server_alias":"s1","write_enabled":False}',`
   - DESPUÉS: `description=json.dumps({"kind": "remote_console", "server_alias": "s1", "write_enabled": False}),`

(Verificar que `import json` ya existe en el archivo — sí, lo usan `:261`/`:271`. NO tocar el fixture de `:318`, que usa `"write_enabled":false` en minúscula: ese string ES JSON válido.)

**Verificación por mutación (OBLIGATORIA, manual, documentada — NO es un test permanente):**

1. Correr el archivo → 13 passed.
2. Mutar `backend/api/devops_remote_console.py` — ancla de texto: `if meta.get("write_enabled") and meta.get("server_alias") == alias:` (hoy `:80`). Cambiar `== alias` por `!= alias` (mutación temporal).
3. Correr el archivo de nuevo → `test_f2_write_mode_wrong_alias_stays_read_only` DEBE FALLAR (si no falla, el fix no ejercitó el branch: investigar antes de seguir).
4. REVERTIR la mutación (`git checkout -- api/devops_remote_console.py` o edición inversa) y correr una vez más → 13 passed.
5. Documentar en el mensaje de commit/PR: "verificación por mutación ejecutada: invertir el chequeo de alias en devops_remote_console rompe test_f2_write_mode_wrong_alias_stays_read_only; revertida".

**Criterio de aceptación BINARIO:** `.venv\Scripts\python.exe -m pytest tests/test_plan105_remote_console_api.py -q` → exit 0, **13 passed**; la frase de verificación por mutación está en el commit/PR; `git diff` de producción limpio (la mutación fue revertida).

**Flag:** N/A. **Runtimes:** N/A. **Trabajo del operador: ninguno.**

---

### F4 — Meta-test de la clase "config-mal-leída" + fix de `api/executions.py`

**Objetivo (1 frase):** un meta-test que hace estructuralmente imposible leer una flag REGISTRADA con `os.getenv`+default hardcodeado en `backend/api/` o `backend/services/` (allowlist congelada de ocurrencias legacy que solo baja), más el fix de la 3ra ocurrencia conocida y el sync de `.env.example`. **Valor:** la página de historial revive en deploys frescos y la clase entera de bug (3 ocurrencias: planes 131, 148 y esta) queda extinta hacia adelante.

**Archivos:**
- NUEVO `backend/tests/test_flags_env_read_meta.py`
- NUEVO `backend/tests/flags_env_read_allowlist.txt`
- MODIFICADO `backend/api/executions.py` (el bloque de gate del endpoint history)
- MODIFICADO `backend/.env.example` (1 línea, hoy `:191`)
- MODIFICADO `backend/scripts/run_harness_tests.sh` y `.ps1` (registrar el meta-test nuevo, bloque `# — Plan 154 · Arnés veraz —`)

**Paso 1 — Fix de `backend/api/executions.py`** (ancla de texto: el docstring `Plan 39 A1 — Historial completo de ejecuciones` y el bloque de gate inmediato, hoy `:290-292`). Reemplazar las 3 líneas del gate (el `import os as _os`, la lectura de entorno con default y el `return jsonify(...) , 404`) por:

```python
    from config import config as _cfg
    if not getattr(_cfg, "STACKY_EXECUTION_HISTORY_ENABLED", True):
        return jsonify({"error": "feature_disabled", "feature": "STACKY_EXECUTION_HISTORY_ENABLED"}), 404
```

Gotcha duro (planes 131/148): la instancia de flags es `config.config` (por eso `from config import config as _cfg`), NUNCA el módulo `config` a secas — `getattr(<módulo>, FLAG)` devuelve siempre el default de clase y mata el branch OFF. Verificar que `_os` no quede huérfano en la función (si otras líneas lo usan, conservar el import).

**Paso 2 — Sync de `backend/.env.example`** (ancla de texto: la línea comentada de `STACKY_EXECUTION_HISTORY_ENABLED`, hoy `:191`): cambiar `=false` por `=true` y `default: false` por `default: true`, conservando el resto del formato de la línea. (`.env.example` NO tiene generador — se edita a mano sin riesgo; el archivo generado prohibido es `harness_defaults.env`, otro archivo.)

**Paso 3 — Meta-test.** Contenido EXACTO de `backend/tests/test_flags_env_read_meta.py`:

```python
"""Plan 154 F4 — Meta-test: flags registradas se leen desde config.config.

Clase de bug que extingue (3 ocurrencias conocidas: planes 131, 148 y
api/executions.py): leer una flag que YA existe en FLAG_REGISTRY tomando
el valor directo del entorno con un default local, que puede divergir del
default real de config.py y de la FlagSpec curada. Regla: en backend/api/
y backend/services/, toda flag registrada se lee desde la instancia
config.config. Las ocurrencias legacy viven en una allowlist congelada
(tests/flags_env_read_allowlist.txt) que SOLO puede bajar.
"""
import pathlib
import re

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_ALLOWLIST = _BACKEND / "tests" / "flags_env_read_allowlist.txt"
_SCAN_DIRS = ("api", "services")
_PATTERN = re.compile(
    r"""os\.(?:getenv|environ\.get)\(\s*['"](STACKY_[A-Z0-9_]+)['"]\s*,"""
)


def _registered_flags() -> set[str]:
    from services.harness_flags import FLAG_REGISTRY
    return {spec.key for spec in FLAG_REGISTRY}


def _allowlisted() -> set[str]:
    out = set()
    if _ALLOWLIST.exists():
        for line in _ALLOWLIST.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                out.add(line)
    return out


def _scan_occurrences() -> set[str]:
    registered = _registered_flags()
    found: set[str] = set()
    for d in _SCAN_DIRS:
        for py in sorted((_BACKEND / d).rglob("*.py")):
            rel = py.relative_to(_BACKEND).as_posix()
            for match in _PATTERN.finditer(py.read_text(encoding="utf-8")):
                flag = match.group(1)
                if flag in registered:
                    found.add(f"{rel}:{flag}")
            # nota: el regex tambien caza texto en comentarios/docstrings;
            # es deliberado (ver plan 154 §9: la prosa no debe contener el patron).
    return found


def test_flags_registradas_no_se_leen_del_entorno_con_default_local():
    found = _scan_occurrences()
    allow = _allowlisted()
    nuevas = sorted(found - allow)
    assert not nuevas, (
        "Lectura directa de entorno con default local para flags REGISTRADAS "
        "(leer desde config.config; ver plan 154 F4):\n  - " + "\n  - ".join(nuevas)
    )
    curadas_de_mas = sorted(allow - found)
    assert not curadas_de_mas, (
        "Entradas de flags_env_read_allowlist.txt que ya no existen en el "
        "codigo (sacarlas: la allowlist solo baja):\n  - " + "\n  - ".join(curadas_de_mas)
    )


def test_execution_history_default_on(monkeypatch):
    """Regresion del fix: sin la env var, /api/executions/history responde 200."""
    import os
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.delenv("STACKY_EXECUTION_HISTORY_ENABLED", raising=False)
    from app import create_app
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/executions/history")
    assert resp.status_code == 200, resp.get_data(as_text=True)
```

**Paso 4 — Generar la allowlist congelada.** Correr el meta-test UNA vez con `tests/flags_env_read_allowlist.txt` vacío; el mensaje de fallo lista todas las ocurrencias legacy `ruta:FLAG`. Copiarlas al archivo UNA por línea con motivo tras `#` (mínimo aceptable: `# legacy plan 154 F4 — pendiente migrar a config.config`). Ocurrencias esperables (verificadas hoy; el conteo real sale del scan): `services/output_watcher.py:STACKY_ARTIFACT_INTAKE_ENABLED` (gate `:1005` — código de intake INTOCABLE por este plan, va a la allowlist), `services/output_watcher.py:STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS` (`:981`, ídem), `services/output_watcher.py:STACKY_PENDING_TASK_STRICT_VALIDATION_ENABLED` (`:1067`), y las que el scan encuentre. **`api/executions.py` NO debe aparecer** (el Paso 1 la eliminó); si aparece, el Paso 1 quedó mal hecho.
- Nota de alcance: el scan cubre `backend/api/` y `backend/services/` (donde vive la clase de bug); `app.py` y `tests/` quedan fuera adrede (F5 usa `os.environ.get` con `STACKY_TEST_MODE`, que NO está en `FLAG_REGISTRY`, así que ni siquiera matchearía la intersección).

**Paso 5 — Registrar** `tests/test_flags_env_read_meta.py` en `run_harness_tests.sh` Y `.ps1`, bloque `# — Plan 154 · Arnés veraz —`.

**BACKLOG registrado (NO es fase; opcional, viaja gratis al tocar `api/executions.py`):** el plan del contrato de URL pidió que la respuesta de `GET /api/executions/history` incluya un campo `total` real (COUNT de la query filtrada ANTES de aplicar limit/offset) además de la página. Son ~4 líneas en el mismo endpoint. Si el implementador lo hace, debe agregar 1 test (`resp.get_json()["total"] >= len(resp.get_json()["items"])` con datos seeded) en el mismo archivo de meta-tests; si no lo hace, queda registrado acá como backlog explícito.

**Criterio de aceptación BINARIO:** `.venv\Scripts\python.exe -m pytest tests/test_flags_env_read_meta.py -q` → exit 0 (ambos tests); `grep -c "test_flags_env_read_meta.py" scripts/run_harness_tests.sh` → `1` e ídem `.ps1` → `1`; demostración manual: agregar temporalmente en cualquier archivo de `backend/api/` una lectura de entorno de una flag registrada con default local → el meta-test FALLA (revertir).

**Flag:** ninguna nueva (usa `STACKY_EXECUTION_HISTORY_ENABLED` existente, curada ON). **Runtimes:** N/A — endpoint de lectura compartido; los 3 runtimes ven el mismo backend. **Trabajo del operador: ninguno** (al contrario: la página de historial le empieza a funcionar sin tocar nada).

---

### F5 — Guard de red en 3 puntos bajo `STACKY_TEST_MODE`

**Objetivo (1 frase):** hacer estructuralmente imposible que pytest genere tráfico de red real: (i) fixture autouse que bloquea sockets no-loopback, (ii) `_startup_sync` gateado por test-mode, (iii) self-POST del watcher con opt-in explícito test-only. **Valor:** cero riesgo de tocar la org ADO productiva o la DB del backend dev vivo desde tests — hoy pasa (§2.5).

**Archivos:**
- MODIFICADO `backend/tests/conftest.py` (fixture autouse)
- MODIFICADO `backend/app.py` (helper `_is_test_mode()` + gate en la invocación de `_startup_sync` + reuso en el gate del daemon)
- MODIFICADO `backend/services/output_watcher.py` (gate test-only del auto-create, ~5 líneas)
- NUEVO test en `backend/tests/test_flags_env_read_meta.py`... **NO** — los tests del guard van en archivo propio: NUEVO `backend/tests/test_plan154_network_guard.py`
- MODIFICADO `backend/scripts/run_harness_tests.sh` y `.ps1` (registrar el test nuevo)

**(i) Fixture autouse en `tests/conftest.py`** — agregar al final del archivo (después del bloque module-level existente):

```python
import socket as _socket

import pytest


_REAL_CONNECT = _socket.socket.connect
_LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")


@pytest.fixture(autouse=True)
def _no_network_egress(monkeypatch):
    """Plan 154 F5.i — bajo STACKY_TEST_MODE, todo connect() saliente
    no-loopback falla con mensaje accionable. Un test que necesite red real
    no existe en este repo por diseño: mockear el cliente HTTP."""
    if os.environ.get("STACKY_TEST_MODE", "").strip().lower() not in ("1", "true", "yes"):
        yield
        return

    def _guarded_connect(self, address):
        host = None
        if isinstance(address, tuple) and address:
            host = address[0]
            if isinstance(host, bytes):
                host = host.decode("utf-8", "replace")
        if host in _LOOPBACK_HOSTS or self.family not in (_socket.AF_INET, _socket.AF_INET6):
            return _REAL_CONNECT(self, address)
        raise RuntimeError(
            f"[plan154 guard-red] egress de red bloqueado en tests: destino {address!r}. "
            "Mockea el cliente HTTP (requests/urllib) o usa loopback."
        )

    monkeypatch.setattr(_socket.socket, "connect", _guarded_connect)
    yield
```

Notas de diseño: se patchea `socket.socket.connect` (capa única por la que pasan `requests`, `urllib` y `socket.create_connection`); familias no-INET (p. ej. AF_UNIX) pasan de largo; loopback queda permitido — el caso "loopback pero servidor real vivo" lo cubre (iii). Limitación conocida y aceptada: UDP `sendto` sin `connect` no pasa por acá (no hay emisores UDP en este repo).

**(ii) Gate de `_startup_sync` en `backend/app.py`:**

1. Agregar helper module-level (cerca de `def _startup_sync`, hoy `:55`):

```python
def _is_test_mode() -> bool:
    """Plan 154 F5.ii — señal única de pytest (tests/conftest.py la setea)."""
    return os.environ.get("STACKY_TEST_MODE", "").strip().lower() in ("1", "true", "yes")
```

2. En la invocación (ancla de texto: la línea `_startup_sync(logger)` a continuación del comentario del preflight, hoy `:404`), reemplazar por:

```python
    if _is_test_mode():
        logger.info("startup_sync omitido (STACKY_TEST_MODE)")
    else:
        _startup_sync(logger)
```

3. En el gate del daemon edit-learning (ancla de texto: la línea `_test_mode = os.environ.get("STACKY_TEST_MODE", ...)`, hoy `:501`), reemplazar esa línea por `_test_mode = _is_test_mode()` (dedupe; el resto del bloque queda igual).
4. El gate va en el CALL-SITE a propósito: un test que quiera probar `_startup_sync` la sigue pudiendo llamar directo. Antes de editar, grepear `_startup_sync` en `backend/tests/` — si algún test asertara que corre durante `create_app()`, reportar al orquestador (a hoy no se conoce ninguno).

**(iii) Opt-in test-only del self-POST del watcher** — ancla de texto: el early-return del flag auto-create (`if os.getenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true").lower() == "false":`, hoy `services/output_watcher.py:981`). INMEDIATAMENTE después de ese bloque (replicando la MISMA forma de retorno que usa ese early-return — leerla en el archivo, no asumirla), insertar:

```python
    # Plan 154 F5.iii — bajo pytest, el self-POST real (127.0.0.1:{port}) puede
    # pegarle a un backend dev VIVO. Solo corre si el test opta explicitamente.
    _tm = os.getenv("STACKY_TEST_MODE", "").strip().lower() in ("1", "true", "yes")
    if _tm and os.getenv("STACKY_TEST_ALLOW_WATCHER_SELF_POST", "").strip().lower() not in ("1", "true", "yes"):
        logger.info("output_watcher mode_a: auto-create omitido (STACKY_TEST_MODE sin opt-in)")
        return  # misma forma de retorno que el early-return del flag OFF
```

`STACKY_TEST_ALLOW_WATCHER_SELF_POST` es env interna test-only: SIN UI, SIN `FLAG_REGISTRY`, SIN `_CURATED_DEFAULTS_ON`, SIN `.env.example` (mismo estatus que `STACKY_TEST_MODE`; no es config de operador — en runtime normal, sin `STACKY_TEST_MODE`, el gate es no-op y el comportamiento es byte-idéntico al actual). Los tests que asertan sobre el POST la setean con `monkeypatch.setenv` (lista exacta en F2).

**Tests (NUEVO `backend/tests/test_plan154_network_guard.py`):**

| Test | Qué afirma |
|---|---|
| `test_guard_bloquea_egress_no_loopback` | `socket.create_connection(("192.0.2.1", 80), timeout=1)` (TEST-NET-1, nunca ruteable) levanta `RuntimeError` con `"guard-red"` en el mensaje — NO `TimeoutError`. |
| `test_guard_permite_loopback` | Abrir un `socket.socket()` y conectar a un listener local efímero en `127.0.0.1` (crear listener con `socket.socket(); bind(("127.0.0.1", 0)); listen(1)`) NO levanta. |
| `test_startup_sync_gateado_en_test_mode` | `create_app()` con `STACKY_TEST_MODE=1` (ya seteado por conftest) NO invoca `_startup_sync`: `patch("app._startup_sync")` y asertar `not called` tras `create_app()`. |
| `test_watcher_self_post_requiere_opt_in` | Con un pending-task VÁLIDO (factory de F2 si ya existe; si F5 se implementa antes que F2 — orden real — construir el dict de 9 campos a mano en este test) y `requests.post` mockeado con contador, `scan_once()` SIN la env de opt-in → contador == 0; con `monkeypatch.setenv("STACKY_TEST_ALLOW_WATCHER_SELF_POST", "1")` → contador >= 1. |

Registrar el archivo en `run_harness_tests.sh` Y `.ps1`, bloque `# — Plan 154 · Arnés veraz —`.

**Criterio de aceptación BINARIO:** `.venv\Scripts\python.exe -m pytest tests/test_plan154_network_guard.py -q` → exit 0; verificación manual documentada del implementador (pegar en el resumen): anotar el tamaño/última línea del access-log del backend dev vivo, correr 3 archivos del arnés que hoy generan tráfico (p. ej. `tests/test_output_watcher.py`, `tests/test_diag_endpoint.py`, `tests/test_plan105_remote_console_api.py`), verificar que el access-log NO tiene líneas nuevas originadas por pytest y que no hubo requests a `dev.azure.com`.

**Flag:** solo la env interna test-only descrita (sin UI, justificada arriba). **Runtimes:** N/A — en runtime normal nada cambia (gates no-op sin `STACKY_TEST_MODE`); los 3 runtimes idénticos. **Trabajo del operador: ninguno.**

---

### F6 — Ratchet de grandfathered: el contador de la allowlist solo baja

**Objetivo (1 frase):** un test hermano en `test_harness_ratchet_meta.py` que congela el conteo de `harness_ratchet_allowlist.txt` en el valor recontado en frío tras F2 y solo permite BAJAR. **Valor:** la deuda de 198 archivos sin gate deja de poder crecer en silencio; el triage completo queda como deuda visible y acotada.

**Archivos:**
- MODIFICADO `backend/tests/test_harness_ratchet_meta.py` (1 constante + 1 test; el archivo YA está en el arnés, `run_harness_tests.sh:60` — cero registro extra)

**Contenido EXACTO a agregar** (después de `test_allowlist_no_se_solapa_con_ratchet`, hoy `:56`):

```python
# Plan 154 F6 — ratchet de deuda: la allowlist SOLO baja. Recontar en frío al
# implementar (tras F2 la referencia es 198 - 1 = 197) y actualizar la constante
# HACIA ABAJO en el mismo commit cada vez que se triagea una entrada.
_ALLOWLIST_MAX = 197  # valor EXACTO al día de implementación — recontar, no confiar


def test_allowlist_grandfathered_solo_baja():
    allow = _allowlist()
    assert len(allow) <= _ALLOWLIST_MAX, (
        f"La allowlist creció a {len(allow)} entradas (máximo congelado: "
        f"{_ALLOWLIST_MAX}). La deuda de tests sin gate SOLO puede bajar: "
        "triagear una entrada existente antes de (o en lugar de) agregar otra, "
        "o registrar el test nuevo directamente en HARNESS_TEST_FILES."
    )
```

**Procedimiento:** tras F2 (que quita `test_output_watcher.py` de la allowlist), recontar en frío con el snippet de F0 (campo `allow:`) y fijar `_ALLOWLIST_MAX` en ESE número exacto (la referencia al 2026-07-16 es 197; si F1 agregó entradas con motivo específico, el número real será mayor — usar el real, no el de referencia).

**Demostración obligatoria del KPI-6:** agregar temporalmente una línea `tests/test_fake_plan154_demo.py  # demo` a la allowlist → `pytest tests/test_harness_ratchet_meta.py -q` FALLA (por el test nuevo Y por `test_ratchet_no_referencia_archivos_inexistentes` si valida existencia — mejor aún) → revertir → verde. Documentar en el resumen.

**Criterio de aceptación BINARIO:** `.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q` → exit 0; la demostración de KPI-6 documentada.

**Flag:** N/A. **Runtimes:** N/A. **Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | El guard de sockets (F5.i) rompe tests que usan sockets loopback legítimos (listeners efímeros, Flask test server). | Loopback (`127.0.0.1`/`::1`/`localhost`) y familias no-INET quedan permitidos; el guard solo corta egress real. `test_guard_permite_loopback` lo prueba. Si un test legítimo falla igual, el mensaje `[plan154 guard-red]` dice exactamente qué destino se bloqueó. |
| R2 | Alguno de los 30 de F1 está rojo aislado por bug real y "clasificarlo" lo esconde. | Regla de decisión explícita en F1: bug real → reporte obligatorio al orquestador + motivo `ROJO conocido — <causa>` en la allowlist. Nada se esconde con `pendiente-de-triage` (F6 además congela el total). |
| R3 | F2 antes que F5 → tests sin mock postean contra el backend dev vivo (dos backends vivos es escenario real). | Orden de implementación DURO: F5 antes que F2 (preámbulo §5). El gate F5.iii corta el auto-create bajo pytest salvo opt-in. |
| R4 | El gate F5.iii rompe tests mode_a existentes que asertan conteo de POSTs (0 o N). | F2 enumera la regla exacta: todo test del archivo que monkeypatchea `requests.post` setea el opt-in. `test_watcher_self_post_requiere_opt_in` (F5) cubre ambos sentidos. |
| R5 | El regex de F4 caza falsos positivos (env vars internas tipo `STACKY_TEST_MODE`) o texto en comentarios. | Intersección con `FLAG_REGISTRY` (las internas no están registradas → no matchean). Comentarios: deliberado — la prosa no debe contener el patrón (§9); es la misma disciplina que el resto de los gates del repo. |
| R6 | Drift de números de línea entre este doc y el árbol al implementar (planes paralelos activos). | Toda edición se ancla por TEXTO normativo citado; F0 reconta en frío; si un ancla de texto no aparece con `grep`, STOP y reportar en vez de adivinar. |
| R7 | `test_execution_history_default_on` (F4) contaminado por orden de imports/config singleton. | El test usa `monkeypatch.delenv` + `DATABASE_URL` in-memory ANTES de importar `app`, y corre en archivo propio (pytest por archivo, disciplina del repo). |
| R8 | El gate de `_startup_sync` (F5.ii) oculta un test que dependía del sync en `create_app()`. | Paso explícito en F5.ii: grepear `_startup_sync` en `backend/tests/` antes de editar; el gate está en el call-site así que la función sigue testeable directo. |

---

## 7. Fuera de scope (explícito)

- **Triage completo de los ~198 grandfathered:** F6 solo CONGELA el contador. Evaluar archivo por archivo si puede entrar al arnés es un plan aparte (la deuda queda visible y acotada).
- **Tests flaky conocidos de heartbeat monitor** (`test_stale_recovery_guardian`, `test_cutover_p5`): ya allowlisteados con motivo, disco real + thread daemon vs sqlite; NO se persiguen acá.
- **Cualquier cambio al código de producción del intake** (`services/artifact_intake.py`, la lógica de validación/cuarentena de `services/output_watcher.py`): su comportamiento es by-design del plan de robustez de intake. Este plan solo INSERTA el gate test-only de F5.iii junto al early-return existente, sin tocar la validación.
- **Migrar las ocurrencias legacy de la allowlist de F4** (`STACKY_ARTIFACT_INTAKE_ENABLED`, etc.) a `config.config`: quedan congeladas con motivo; migrarlas es trabajo futuro que el propio meta-test forzará a limpiar (la allowlist solo baja).
- **El campo `total` del endpoint history:** registrado como BACKLOG en F4 (opcional, viaja gratis); no es criterio de aceptación de este plan.
- **Los 7 tests reales rojos revelados por el fix del daemon del plan 146** (6 mode_a + 1 plan105): NO — esos son EXACTAMENTE T3 y T2 de este plan, SÍ están en scope (F2 y F3). Se lista acá para evitar la confusión inversa.

---

## 8. Orden de implementación + Definition of Done global

**Orden (repetido del preámbulo de §5, es normativo):**

1. **F0** — baseline en frío (números + lista pegados).
2. **F1** — clasificar los 30 → ratchet verde.
3. **F3** — plan105 13/13 + verificación por mutación (independiente; temprana porque es el fix más barato del arnés rojo).
4. **F4** — meta-test config-mal-leída + fix executions + `.env.example`.
5. **F5** — guard de red (3 puntos) + sus tests.
6. **F2** — factory + 6 mode_a verdes + movimiento allowlist→arnés (REQUIERE F5.iii).
7. **F6** — congelar el contador de la allowlist (último: el número final depende de F1 y F2).

**DoD global (todo binario, todo con comando):**

- [ ] KPI-1: `pytest tests/test_harness_ratchet_meta.py -q` → exit 0.
- [ ] KPI-2: `pytest tests/test_output_watcher.py -q` → 30 passed; archivo fuera de la allowlist y dentro de sh+ps1.
- [ ] KPI-3: `pytest tests/test_plan105_remote_console_api.py -q` → 13 passed; mutación documentada.
- [ ] KPI-4: `pytest tests/test_flags_env_read_meta.py -q` → exit 0; history 200 sin env var.
- [ ] KPI-5: `pytest tests/test_plan154_network_guard.py -q` → exit 0; access-log limpio documentado.
- [ ] KPI-6: demo de allowlist+1 → rojo → revertido, documentada.
- [ ] KPI-7: los 2 archivos de test nuevos (`test_flags_env_read_meta.py`, `test_plan154_network_guard.py`) en `run_harness_tests.sh` Y `.ps1`.
- [ ] Cada archivo del arnés tocado por este plan corre verde AISLADO (pytest por archivo, nunca suite completa).
- [ ] `git status` final sin WIP ajeno arrastrado; staging por paths explícitos.
- [ ] Resumen final honesto: qué quedó verde, qué quedó en allowlist con motivo, y la lista de F1 con su clasificación.

---

## 9. Advertencias para el implementador (leer ANTES de escribir código)

1. **Gotcha comentario-choca-con-gate (6 recurrencias históricas: planes 134/135/136/138/146×2).** El meta-test de F4 greppea texto plano en `backend/api/` y `backend/services/`: NINGÚN comentario, docstring o string en esos directorios puede contener el patrón literal de lectura de entorno con default para una flag registrada (ni siquiera como ejemplo de "lo que NO hay que hacer"). Reescribí la prosa describiendo la regla sin reproducir el patrón — JAMÁS gamees el gate agregando la ocurrencia a la allowlist para "que pase": la allowlist es solo para código legacy preexistente. Lo mismo aplica a los greps de verificación de este plan: usá los comandos EXACTOS dados en cada fase, no variantes laxas que matcheen de más.
2. **pytest SIEMPRE por archivo.** Cross-file pollution conocida y documentada en este repo (backend y frontend). Un rojo en suite completa NO es evidencia; un rojo aislado SÍ.
3. **Los meta-tests nuevos también van al arnés (sh Y ps1).** El ratchet se audita a sí mismo; olvidar el `.ps1` es el error más repetido del repo.
4. **Venv real:** `backend\.venv\Scripts\python.exe` (py3.13, verificado en disco). `backend/venv` NO existe. No uses el Python global.
5. **`config.config`, no `config`.** En `backend/api/*` el nombre `config` suele ser el MÓDULO; la instancia de flags es `config.config`. `getattr` sobre el módulo devuelve el default de clase y mata el branch OFF (bit real de los planes 131 y 148). Patrón correcto: `from config import config as _cfg`.
6. **No confundas los dos archivos de entorno:** `backend/.env.example` se edita a mano (F4); `harness_defaults.env` es GENERADO por `deployment/export_harness_defaults.py` y está PROHIBIDO tocarlo a mano.
7. **Sesiones paralelas en el mismo árbol son reales.** Pre-flight `git status` por archivo caliente; staging quirúrgico por path explícito; NUNCA `git add .`, NUNCA amend/reset/rebase/checkout de rama compartida.
8. **Anclas por texto, no por línea.** Si el `grep` del ancla normativa no da EXACTAMENTE 1 hit en el archivo esperado, STOP y reportar drift — no adivines cuál de los hits es.
9. **El intake es intocable** (salvo la inserción del gate F5.iii junto al early-return existente). Si un test de F2 no pasa con el payload de 9 campos, el bug está en el test o en la factory — NO "arregles" `artifact_intake.py`.
