# Plan 259 — Alta de proyecto GitLab de primera clase + guía de configuración verificable (botón INFO)

**Estado:** PROPUESTO v1
**Serie:** Paridad multi-proveedor (65 → 218 → 249 → **259**). Cierra el último tramo que quedó a mitad de camino: el **alta**.
**Fuente:** pedido del operador ("al crear un nuevo proyecto debe de darme la opción de GitLab y un botón de INFO que podamos abrir y nos dé info muy detallada de cómo configurarlo exactamente"), **verificado contra el árbol de trabajo** en la rama `feat/plan-217-migrador-mantis-gitlab`.

> **Hallazgo central de la verificación:** GitLab está implementado en el motor (7 módulos `services/gitlab_*.py`, fábrica en `tracker_provider.py:130-148`, tipo declarado en `frontend/src/types.ts:245`) y **está ofrecido en el modal de EDICIÓN** (`EditProjectModal.tsx:449-452`) — pero **no existe en el modal de ALTA** y **el backend no sabe crearlo**. Peor: apretar ese botón de GitLab en Edición y guardar **convierte el proyecto en Azure DevOps en silencio**. El pedido del operador no es una feature nueva: es cerrar un agujero que hoy corrompe datos.

---

## 1. Objetivo y KPI

Que crear un proyecto GitLab sea tan directo como crear uno de Azure DevOps, y que el operador **no tenga que adivinar ni buscar en ningún lado** cómo configurarlo: la propia pantalla se lo explica paso a paso y **verifica en vivo** cuál de los pasos falta.

| KPI | Hoy (medido en el árbol) | Meta |
|---|---|---|
| Trackers seleccionables al **crear** un proyecto | **3 de 4** (`NewProjectModal.tsx:373-393`: ADO, Jira, Mantis) | **4 de 4** |
| Proyectos GitLab creables vía `POST /api/init_project` | **0** — cae al `else # azure_devops` (`api/projects.py:360`) y responde `400 "organization requerida"` | **1 llamada, 200 OK** |
| `PATCH /api/projects/<n>` con `tracker_type="gitlab"` que **preserva** el tipo | **0 %** — reescribe `issue_tracker.type` a `azure_devops` (`api/projects.py:504-518`) | **100 %** |
| Campos GitLab devueltos por `GET /api/projects` | **0 de 4** (`_project_to_dict`, `api/projects.py:80-109`, no emite ninguno) | **4 de 4** |
| `_has_credentials` correcto para GitLab | **NO** — busca `mantis_auth.json` (`api/projects.py:69-77`) | **SÍ** (`gitlab_auth.json`) |
| Writer de credencial GitLab cifrada | **no existe** (`project_manager.py` tiene `write_ado_auth`/`write_jira_auth`/`write_mantis_auth`, no GitLab) | **existe, DPAPI, igual que los otros 3** |
| Pasos de configuración explicados dentro de la UI | **0** | **12 pasos** + **5 chequeos ejecutables** |
| Chequeos que el operador puede correr sin salir del modal | **0** | **5**, cada uno con el paso exacto que arregla el fallo |
| Proyecto GitLab recién creado que sincroniza al primer intento | **0 %** — `STACKY_GITLAB_ENABLED` nace en `false` (`config.py:1185`) y la fábrica tira `TrackerConfigError` | **100 %** (casilla "Activar el motor GitLab", tildada por default, visible y destildable) |

---

## 2. Evidencia real (anclaje anti-alucinación)

Todo lo que sigue fue leído del árbol, no inferido.

### E1 — El alta no ofrece GitLab; la edición sí (y miente)

`frontend/src/components/NewProjectModal.tsx:372-394` — la fila de trackers tiene **exactamente tres** botones:

```tsx
<div className={styles.trackerRow}>
  <button ... onClick={() => setTrackerType("azure_devops")}>🔷 Azure DevOps</button>
  <button ... onClick={() => setTrackerType("jira")}>🔵 Jira</button>
  <button ... onClick={() => setTrackerType("mantis")}>🟢 Mantis BT</button>
</div>
```

`frontend/src/components/EditProjectModal.tsx:449-452` — el de edición tiene el cuarto:

```tsx
<button ... onClick={() => patch("tracker_type", "gitlab" as TrackerType)}>🦊 GitLab</button>
```

y sus campos en `:695-746` (`gitlab_url`, `gitlab_project`, `gitlab_group`, `gitlab_auth_file`).

### E2 — El backend no tiene rama GitLab: degradación silenciosa a ADO

`backend/api/projects.py:290-383` (`init_project`) ramifica `if tracker_type == "jira" / elif "mantis" / else: # azure_devops`. **No hay rama `gitlab`.** Con `tracker_type="gitlab"` cae al `else`, exige `organization` y responde `400`.

`backend/api/projects.py:424-521` (`update_project`) tiene la misma estructura. Con `tracker_type="gitlab"` cae al `else` y llama `initialize_ado_project(...)`, que escribe `{"type": "azure_devops", ...}` en `config.json` (`project_manager.py:294-299`). **El botón GitLab de la pantalla de edición es una trampa: convierte el proyecto a ADO sin avisar.**

### E3 — Falta el escritor de credencial

`backend/project_manager.py:628-648` (`__all__`) exporta `write_ado_auth`, `write_jira_auth`, `write_mantis_auth` e `initialize_ado_project`, `initialize_jira_project`, `initialize_mantis_project`. **No hay ninguna función `*_gitlab_*`.**

### E4 — El lector de token NO descifra

`backend/services/gitlab_client.py:75-93`:

```python
data = json.loads(path.read_text(encoding="utf-8"))
tok = str(data.get("token") or data.get("private_token") or "").strip()
```

Lee el campo **crudo**. Los otros trackers guardan cifrado con DPAPI (`set_encrypted_secret`, `secrets_store.py:191-201`) y leen con `read_secret_from_file` (`:258-280`). Si el alta escribiera el token con el mecanismo de la casa, **GitLab enviaría el criptograma como `PRIVATE-TOKEN` y daría 401**. Esta incompatibilidad hay que cerrarla en el mismo plan o el alta nace rota.

### E5 — La variable de entorno gana sobre el archivo del proyecto

`backend/services/gitlab_client.py:62-64`:

```python
token = os.getenv("GITLAB_TOKEN") or ""
if not token:
    token = self._load_token_from_file(auth_path)
```

Si `GITLAB_TOKEN` está en el entorno, **todos** los proyectos GitLab usan ese token y el archivo por proyecto se ignora. Es una trampa real que la guía tiene que decir con todas las letras (paso `gl-10-env-precedencia`).

### E6 — El motor GitLab nace apagado

`backend/config.py:1185-1187`: `STACKY_GITLAB_ENABLED` default `"false"`. `backend/services/tracker_provider.py:133-136` lanza `TrackerConfigError("issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false")`. Mismo guard en `ci_provider.py:121`, `ci_variables.py:82`, `ci_preflight.py:39`, `ci_logs_provider.py:38`.
El comentario de `config.py:1191-1193` deja escrito el motivo: **excepción dura #3** (exige instancia GitLab + token, que no existen en una instalación limpia). Este plan **no cambia ese default**: lo enciende como parte de la acción explícita en la que el operador declara instancia y token.

### E7 — Lo que SÍ está resuelto (no reinventar)

- `project_context._auth_path_for` ya resuelve `auth/gitlab_auth.json` (`project_context.py:129-132`).
- `build_tracker_target` ya arma `project_path` / `base_url` / `group` / `auth_path` por proyecto (`project_context.py:232-273`).
- `GitLabTrackerProvider.__init__` ya acepta `base_url`, `group`, `auth_path` (`gitlab_provider.py:33-51`).
- `api/global_config.py:335-372` ya prueba conexión GitLab; **pero usa `GitLabClient`, que lee `GITLAB_TOKEN` del entorno primero (E5)** ⇒ no sirve para verificar lo que el operador acaba de tipear. Por eso F4 usa un camino HTTP propio y mínimo.
- Precedente exacto para el contenido de la guía: `backend/services/harness_flags_help.py` (módulo **puro**, dataclass congelada, `plain_help_for(key)` en `:1915-1925`, cobertura verificada por test centinela).

---

## 3. Principios y guardarraíles

1. **Paridad de los 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro).** Nada de este plan invoca un LLM. La guía es **dato estático** y la verificación es **HTTP determinista**. Por construcción, los 3 runtimes ven byte por byte lo mismo. Cada fase declara igual su impacto y su fallback.
2. **Cero trabajo extra para el operador.** Todo nace **ON**. La única casilla nueva viene **tildada** y su efecto está escrito al lado. No hay archivo nuevo que editar a mano, no hay variable de entorno obligatoria.
3. **Human-in-the-loop innegociable.** El plan **no** crea proyectos solo, **no** apaga ni prende nada sin un clic, y **no** manda el token a ningún lado que no sea la instancia que el operador escribió en ese mismo formulario. Todos los chequeos son `GET` de **solo lectura**.
4. **Mono-operador, sin auth real.** Ni roles ni permisos: se reusa el modelo actual.
5. **No degradar.** Backward-compatible: los proyectos ADO/Jira/Mantis existentes no cambian ni un byte de su `config.json`; el lector de token GitLab sigue aceptando el formato plano de hoy.
6. **Reusar.** `Dialog` canónico (plan 164), `Field/Input/Select/Checkbox` (plan 162), `apply_updates` de `harness_flags`, `secrets_store`, el patrón de `harness_flags_help.py`, la categoría de flags `paridad_proveedores` (plan 218).
7. **Sin RTL/jsdom.** No están instalados (gotcha de la casa): **toda** lógica de UI testeable vive en módulos puros `.ts` bajo `frontend/src/projects/`, y el `.tsx` solo pinta.

### Flags de este plan

| Flag | Tipo | Default | Categoría | Justificación del default |
|---|---|---|---|---|
| `STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED` | bool | **ON** | `paridad_proveedores` | Ninguna de las 4 excepciones aplica: no bypasea revisión (el operador aprieta "Crear"), no es destructiva (crea una carpeta nueva), no exige prerequisito no garantizado (con el flag ON y sin GitLab, el botón simplemente no se usa), no reduce seguridad (el token se guarda **cifrado**, hoy no se guarda de ninguna forma). |
| `STACKY_SETUP_GUIDE_ENABLED` | bool | **ON** | `paridad_proveedores` | Texto de solo lectura servido desde un módulo puro. Sin red, sin escritura. |
| `STACKY_SETUP_GUIDE_VERIFY_ENABLED` | bool | **ON** | `paridad_proveedores` | 5 `GET` de solo lectura contra la URL que el operador escribió, sin redirecciones y sin persistir nada. No es destructiva ni reduce seguridad. Queda como kill-switch por si el operador quiere el panel sin salida de red. |

`STACKY_GITLAB_ENABLED` **no cambia su default**: sigue OFF por excepción dura #3, como dice `config.py:1191-1193`.

---

## 4. Fases

> **Comando base backend** (desde `Stacky Agents/backend`, PowerShell):
> `.venv\Scripts\python.exe -m pytest tests/<archivo> -v`
> **Comando base frontend** (desde `Stacky Agents/frontend`):
> `npx vitest run src/__tests__/<archivo>`
> **Correr SIEMPRE por archivo** (gotcha de la casa: la corrida completa contamina cross-file, y `importlib.reload(config)` ensucia los tests de flag OFF).

---

### F0 — Registro puro de guías de configuración + flags

**Objetivo:** que el contenido de la guía exista como dato puro, testeable y sin IO, antes de que ninguna pantalla lo consuma.
**Valor:** el 100 % del texto que verá el operador queda bajo test; ningún runtime puede "redactarlo distinto".

**Archivos a CREAR:**
- `Stacky Agents/backend/services/setup_guides.py`
- `Stacky Agents/backend/tests/test_plan259_setup_guide_data.py`

**Archivos a EDITAR:**
- `Stacky Agents/backend/config.py`
- `Stacky Agents/backend/services/harness_flags.py`
- `Stacky Agents/backend/tests/test_harness_flags.py`

#### F0.a — `services/setup_guides.py` (NUEVO, PURO)

Sin `flask`, sin `config`, sin IO, sin red. Solo dataclasses + datos + 3 funciones de lookup. Mismo criterio que `harness_flags_help.py:1-11`.

```python
"""Plan 259 — Guías de configuración exactas por proveedor de tickets.

PURO: sin flask, sin config, sin IO, sin red. Datos + 3 funciones de lookup.
El contenido es el MISMO en Codex CLI, Claude Code CLI y GitHub Copilot Pro
porque no interviene ningún LLM: es una tabla.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuideStep:
    id: str          # kebab-case estable; los checks lo referencian
    title: str       # ≤ 90 chars
    detail: str      # texto llano, puede tener varias frases
    where: str       # "gitlab" | "stacky" | "windows"
    trap: str = ""   # "" o la trampa concreta a evitar


@dataclass(frozen=True)
class GuideCheck:
    id: str          # "chk-*"
    title: str
    fixes_step: str  # DEBE ser el .id de un GuideStep de la misma guía


@dataclass(frozen=True)
class SetupGuide:
    provider: str          # "gitlab"
    display_name: str      # "GitLab"
    summary: str           # 1 párrafo
    required_fields: tuple[str, ...]
    steps: tuple[GuideStep, ...]
    checks: tuple[GuideCheck, ...]


GITLAB_GUIDE = SetupGuide(
    provider="gitlab",
    display_name="GitLab",
    summary=(
        "Stacky se conecta a GitLab por su API v4 con un token personal. Necesitás tres "
        "datos: la URL base de tu GitLab, el path del proyecto y un token con permiso de "
        "API. El token se guarda cifrado en tu equipo y nunca sale de acá salvo hacia tu "
        "propia instancia de GitLab."
    ),
    required_fields=("gitlab_url", "gitlab_project", "gitlab_token"),
    steps=(
        GuideStep(
            id="gl-01-instancia",
            title="1. Identificá la URL base de tu GitLab",
            detail=(
                "Si usás GitLab en la nube es https://gitlab.com . Si tu empresa tiene el "
                "suyo, es la raíz del sitio, por ejemplo https://gitlab.miempresa.com . "
                "Va SIN barra al final y SIN /api/v4 : eso lo agrega Stacky. "
                "Para confirmar, abrí <URL>/api/v4/version en el navegador: si te devuelve "
                "un JSON o un 401, la URL está bien; si te devuelve 404, está mal."
            ),
            where="gitlab",
            trap="Pegar la URL del proyecto en vez de la del sitio. La URL base NO incluye el nombre del grupo ni del proyecto.",
        ),
        GuideStep(
            id="gl-02-token",
            title="2. Creá un Personal Access Token con permiso 'api'",
            detail=(
                "En GitLab (versiones 16.x y 17.x): hacé clic en tu foto arriba a la derecha "
                "→ 'Edit profile' → en el menú de la izquierda 'Access tokens' → 'Add new token'. "
                "Ponele de nombre 'stacky-agents'. Elegí una fecha de vencimiento (GitLab obliga "
                "a poner una). En la lista de permisos ('scopes') marcá 'api'. "
                "Con 'read_api' Stacky solo puede LEER: no podría comentar el ticket, cambiar la "
                "etiqueta ni cerrarlo. Apretá 'Create' y COPIÁ el token en ese momento: GitLab no "
                "te lo vuelve a mostrar nunca más."
            ),
            where="gitlab",
            trap="Cerrar la pantalla sin copiar el token. Si pasa, no se puede recuperar: hay que crear otro.",
        ),
        GuideStep(
            id="gl-03-rol",
            title="3. Verificá que tu usuario tenga rol suficiente en el proyecto",
            detail=(
                "En el proyecto de GitLab: menú 'Manage' → 'Members'. Buscá tu usuario. "
                "Con rol 'Reporter' Stacky puede leer los tickets. Para comentar, cambiar "
                "etiquetas y cerrar, necesitás 'Developer' o superior. "
                "El token nunca te da más permisos de los que ya tenés vos."
            ),
            where="gitlab",
        ),
        GuideStep(
            id="gl-04-project-path",
            title="4. Anotá el path del proyecto",
            detail=(
                "Es lo que viene después del dominio en la URL del proyecto, sin https:// y "
                "sin la parte /-/algo. Ejemplo: si la URL es "
                "https://gitlab.com/acme/backend/api entonces el path es acme/backend/api . "
                "También se acepta el número de ID del proyecto, que figura en "
                "'Settings' → 'General', arriba de todo, como 'Project ID'. "
                "Las barras las codifica Stacky solo."
            ),
            where="gitlab",
            trap="Escribir solo el último tramo ('api'). Hay que poner el path completo con los grupos y subgrupos.",
        ),
        GuideStep(
            id="gl-05-issues",
            title="5. Confirmá que el proyecto tenga los Issues habilitados",
            detail=(
                "En el proyecto: 'Settings' → 'General' → 'Visibility, project features, "
                "permissions' → la perilla 'Issues' tiene que estar encendida. "
                "Si está apagada, GitLab responde 404 cuando Stacky pide la lista de tickets, "
                "aunque la URL y el token estén perfectos."
            ),
            where="gitlab",
        ),
        GuideStep(
            id="gl-06-grupo",
            title="6. (Opcional) Grupo, solo si vas a usar épicas nativas",
            detail=(
                "El campo 'Grupo' es únicamente para las épicas nativas de GitLab, que son una "
                "función de los planes Premium y Ultimate. Es el path del grupo raíz, por "
                "ejemplo 'acme'. Si lo dejás vacío, Stacky trabaja con issues comunes, que "
                "funcionan en todos los planes incluido el gratuito."
            ),
            where="gitlab",
        ),
        GuideStep(
            id="gl-07-stacky-alta",
            title="7. Cargá los datos en Stacky",
            detail=(
                "En Stacky: 'Nuevo Proyecto' → elegí el botón '🦊 GitLab' → completá "
                "Nombre interno, Workspace root, URL base (paso 1), Path del proyecto (paso 4) "
                "y pegá el Token (paso 2). El Grupo (paso 6) es opcional."
            ),
            where="stacky",
        ),
        GuideStep(
            id="gl-08-motor",
            title="8. Dejá tildada la casilla 'Activar el motor GitLab'",
            detail=(
                "Viene tildada. Enciende la perilla STACKY_GITLAB_ENABLED, que es el interruptor "
                "general del soporte GitLab y de fábrica viene apagada. Si la destildás, el "
                "proyecto se crea igual pero cada sincronización va a fallar con el mensaje "
                "'issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false'. "
                "La podés prender o apagar después desde el panel de Configuración del arnés, "
                "categoría 'Paridad de proveedores'."
            ),
            where="stacky",
        ),
        GuideStep(
            id="gl-09-donde-queda",
            title="9. Dónde queda guardado el token",
            detail=(
                "En backend/projects/<NOMBRE>/auth/gitlab_auth.json , cifrado con DPAPI de "
                "Windows y atado a tu usuario de Windows. Ni Stacky ni nadie puede leerlo desde "
                "otro usuario o desde otra máquina. Si copiás la carpeta a otra PC, hay que "
                "volver a pegar el token."
            ),
            where="windows",
        ),
        GuideStep(
            id="gl-10-env-precedencia",
            title="10. Cuidado con la variable de entorno GITLAB_TOKEN",
            detail=(
                "Si en tu equipo existe la variable de entorno GITLAB_TOKEN, esa GANA sobre el "
                "token guardado por proyecto. Con dos proyectos GitLab distintos, los dos "
                "terminarían usando el mismo token y uno de los dos va a fallar. "
                "Recomendación: no definas GITLAB_TOKEN en el entorno y dejá que cada proyecto "
                "use el suyo."
            ),
            where="windows",
            trap="Un token viejo en el entorno hace fallar un token nuevo y correcto cargado por pantalla.",
        ),
        GuideStep(
            id="gl-11-ssl",
            title="11. Redes de empresa con certificado propio",
            detail=(
                "Si tu GitLab usa un certificado emitido por la autoridad certificante de la "
                "empresa, importá esa autoridad al almacén de certificados de Windows "
                "('Entidades de certificación raíz de confianza'). "
                "Stacky no ofrece 'desactivar la verificación SSL' para GitLab a propósito: "
                "sería mandar tu token por un canal que no se puede verificar."
            ),
            where="windows",
        ),
        GuideStep(
            id="gl-12-verificar",
            title="12. Verificá antes de crear",
            detail=(
                "Apretá 'Verificar ahora' en este mismo panel. Corre 5 controles de solo lectura "
                "contra tu GitLab y te dice exactamente cuál falla y qué paso de esta guía lo "
                "arregla. No crea ni modifica nada en GitLab."
            ),
            where="stacky",
        ),
    ),
    checks=(
        GuideCheck(id="chk-flag",      title="El motor GitLab está encendido",              fixes_step="gl-08-motor"),
        GuideCheck(id="chk-instancia", title="La URL responde y es un GitLab",              fixes_step="gl-01-instancia"),
        GuideCheck(id="chk-token",     title="El token es válido",                          fixes_step="gl-02-token"),
        GuideCheck(id="chk-scope",     title="El token tiene el permiso 'api'",              fixes_step="gl-02-token"),
        GuideCheck(id="chk-proyecto",  title="El proyecto existe y tiene Issues habilitado", fixes_step="gl-04-project-path"),
    ),
)


SETUP_GUIDES: dict[str, SetupGuide] = {"gitlab": GITLAB_GUIDE}


def guide_exists(provider: str) -> bool:
    return (provider or "").strip().lower() in SETUP_GUIDES


def guide_for(provider: str) -> SetupGuide | None:
    return SETUP_GUIDES.get((provider or "").strip().lower())


def guide_as_dict(provider: str) -> dict | None:
    """Serializa la guía para la API. None si el proveedor no tiene guía."""
    g = guide_for(provider)
    if g is None:
        return None
    return {
        "provider": g.provider,
        "display_name": g.display_name,
        "summary": g.summary,
        "required_fields": list(g.required_fields),
        "steps": [
            {"id": s.id, "title": s.title, "detail": s.detail, "where": s.where, "trap": s.trap}
            for s in g.steps
        ],
        "checks": [
            {"id": c.id, "title": c.title, "fixes_step": c.fixes_step} for c in g.checks
        ],
    }


__all__ = ["GuideStep", "GuideCheck", "SetupGuide", "SETUP_GUIDES",
           "GITLAB_GUIDE", "guide_exists", "guide_for", "guide_as_dict"]
```

#### F0.b — Flags

`config.py`, **inmediatamente después** del bloque del plan 218 (después de la línea `STACKY_CAPABILITY_DEGRADATION_ENABLED`, hoy `config.py:1203-1205`):

```python
    # ── Plan 259 — Alta de proyecto GitLab + guía de configuración ────────────
    # Las 3 nacen ON: ninguna dispara las 4 excepciones duras. El alta guarda el
    # token CIFRADO (hoy no se guarda de ninguna forma), la guía es texto de solo
    # lectura y la verificación son 5 GET sin redirecciones contra la instancia
    # que el propio operador tipeó. El kill-switch del eje GitLab sigue siendo
    # STACKY_GITLAB_ENABLED, que NO cambia su default (OFF, excepción dura #3).
    STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED: bool = os.getenv(
        "STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    STACKY_SETUP_GUIDE_ENABLED: bool = os.getenv(
        "STACKY_SETUP_GUIDE_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    STACKY_SETUP_GUIDE_VERIFY_ENABLED: bool = os.getenv(
        "STACKY_SETUP_GUIDE_VERIFY_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
```

`services/harness_flags.py` — agregar las 3 keys a `_CATEGORY_KEYS["paridad_proveedores"]` (hoy `harness_flags.py:478-484`, después de `STACKY_GITLAB_SEMANTIC_RULES_ENABLED`):

```python
        "STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED",  # Plan 259 F1/F2/F5 — alta de proyecto GitLab
        "STACKY_SETUP_GUIDE_ENABLED",                # Plan 259 F4/F6 — botón INFO + guía
        "STACKY_SETUP_GUIDE_VERIFY_ENABLED",         # Plan 259 F4/F6 — "Verificar ahora"
```

y 3 `FlagSpec` al final de `FLAG_REGISTRY`, con `group="global"`, `env_only=False`, `default=True` y el comentario `# Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).`:

| key | label | description |
|---|---|---|
| `STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED` | `Crear proyectos GitLab desde la pantalla de alta` | `Plan 259 — Agrega GitLab a los sistemas de tickets elegibles al crear un proyecto y habilita la rama GitLab del alta en el backend. Si la apagás, el botón no aparece y el backend rechaza tracker_type=gitlab con un mensaje explícito en vez de convertir el proyecto a Azure DevOps.` |
| `STACKY_SETUP_GUIDE_ENABLED` | `Botón INFO con la guía de configuración paso a paso` | `Plan 259 — Muestra un botón INFO junto al sistema de tickets elegido que abre la guía exacta de configuración (12 pasos para GitLab). Texto de solo lectura, sin red.` |
| `STACKY_SETUP_GUIDE_VERIFY_ENABLED` | `Botón "Verificar ahora" dentro de la guía` | `Plan 259 — Corre 5 controles de solo lectura contra la instancia que escribiste en el formulario y marca cuál falla. No escribe nada, ni en GitLab ni en disco.` |

`tests/test_harness_flags.py` — agregar las 3 keys a `_CURATED_DEFAULTS_ON` (hoy `:467`), encabezadas por el bloque de comentario del plan 259 igual que hacen los planes 254-258.

#### Tests (PRIMERO)

`backend/tests/test_plan259_setup_guide_data.py`:

| Test | Qué asegura |
|---|---|
| `test_modulo_es_puro` | Leer el fuente de `services/setup_guides.py` y afirmar que **no** contiene `import flask`, `import config`, `import requests`, `open(`, `Path(`. |
| `test_gitlab_tiene_los_12_pasos` | `len(GITLAB_GUIDE.steps) == 12` y los `id` son exactamente los 12 `gl-*` listados, en orden. |
| `test_ids_de_paso_unicos` | No hay `id` repetido en `steps` ni en `checks`, para **toda** guía de `SETUP_GUIDES`. |
| `test_cada_check_apunta_a_un_paso_existente` | Para toda guía y todo `check`: `check.fixes_step in {s.id for s in guide.steps}`. **Este es el invariante que hace útil la verificación.** |
| `test_campos_no_vacios` | Para toda guía: `summary`, y por paso `title`/`detail`/`where` no vacíos; `where in {"gitlab","stacky","windows"}`. |
| `test_titulos_acotados` | `len(step.title) <= 90` para todo paso. |
| `test_sin_jerga_sin_explicar` | Denylist: si `detail` contiene `PAT`, `scope`, `namespace`, `endpoint`, `payload` sin una explicación en la misma frase, falla. Implementado como: cada término de la denylist debe aparecer acompañado de su glosa entre paréntesis o comillas simples en el mismo `detail`; se permite `'api'` y `'read_api'` entrecomillados porque son literales que el operador tiene que tipear. |
| `test_guide_as_dict_serializa_y_es_json` | `json.dumps(guide_as_dict("gitlab"))` no lanza; el dict tiene 6 claves; `len(d["steps"]) == 12`; `len(d["checks"]) == 5`. |
| `test_guide_as_dict_desconocido_es_none` | `guide_as_dict("azure_devops") is None` y `guide_exists("azure_devops") is False`. |
| `test_menciona_los_anclajes_operativos` | El texto concatenado de los 12 pasos menciona literalmente `STACKY_GITLAB_ENABLED`, `GITLAB_TOKEN`, `gitlab_auth.json`, `/api/v4/version` y `'api'`. Blinda que la guía no pierda los datos duros. |

**Comando:**
```
.venv\Scripts\python.exe -m pytest tests/test_plan259_setup_guide_data.py -v
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -v
```

**Criterio de aceptación BINARIO:** los dos comandos en verde y
```
.venv\Scripts\python.exe -c "from services.setup_guides import guide_as_dict; d=guide_as_dict('gitlab'); print(len(d['steps']), len(d['checks']))"
```
imprime exactamente `12 5`.

**Flag:** `STACKY_SETUP_GUIDE_ENABLED` (default **ON**). El módulo de datos en sí no se gatea (es inerte sin consumidor).
**Impacto por runtime:** ninguno — módulo puro sin LLM. **Fallback Codex / Claude Code / Copilot:** idéntico, el dato es el mismo.
**Trabajo del operador:** ninguno.

---

### F1 — `initialize_gitlab_project` + `write_gitlab_auth`

**Objetivo:** que `project_manager.py` sepa crear un proyecto GitLab y guardar su token cifrado, igual que los otros 3 trackers.
**Valor:** el `config.json` GitLab queda con la **forma exacta** que ya consumen `project_context._auth_path_for` y `build_tracker_target` (E7) — sin tocarlos.

**Archivo a EDITAR:** `Stacky Agents/backend/project_manager.py`
**Archivo a CREAR:** `Stacky Agents/backend/tests/test_plan259_project_manager_gitlab.py`

Agregar al final del archivo, **antes** de `__all__`:

```python
# ── GitLab ────────────────────────────────────────────────────────────────────

def initialize_gitlab_project(
    name: str,
    url: str,
    project_path: str,
    workspace_root: str,
    display_name: str = "",
    group: str = "",
    auth_file: str = "auth/gitlab_auth.json",
    docs_paths: dict | None = None,
    agents_dir: str | None = None,
) -> dict:
    """Helper de alto nivel para dar de alta un proyecto GitLab (Plan 259 F1).

    `project_path` es 'grupo/subgrupo/proyecto' o el ID numérico. Se guarda en
    `issue_tracker.project` y `issue_tracker.base_url`, que son las claves que ya
    leen project_context._tracker_project_for (:98) y _base_url_for (:107-110).
    """
    tracker: dict = {
        "type":      "gitlab",
        "base_url":  url.rstrip("/"),
        "project":   project_path.strip(),
        "auth_file": auth_file,
    }
    if group:
        tracker["group"] = group.strip()

    return initialize_project(
        name=name,
        display_name=display_name or name,
        workspace_root=workspace_root,
        issue_tracker=tracker,
        docs_paths=docs_paths,
        agents_dir=agents_dir,
    )


def write_gitlab_auth(name: str, url: str, token: str, project_path: str = "") -> Path:
    """Escribe backend/projects/{NAME}/auth/gitlab_auth.json con el token cifrado.

    El campo se llama `token` y el formato queda declarado en `token_format`
    (DPAPI), igual que Jira y Mantis. El lector se adapta en F3.
    """
    auth_dir = PROJECTS_DIR / name.upper() / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    auth_file = auth_dir / "gitlab_auth.json"
    payload: dict = {"url": url.rstrip("/")}
    if project_path:
        payload["project"] = project_path.strip()
    set_encrypted_secret(payload, "token", token, format_field="token_format")
    write_json_file(auth_file, payload)
    return auth_file
```

y sumar `"initialize_gitlab_project"` y `"write_gitlab_auth"` a `__all__` (hoy `project_manager.py:628-648`).

> **Nota de diseño, no ambigua:** `base_url` (no `url`) porque es la clave que lee `_base_url_for` (`project_context.py:110`), y `project` (no `project_path`) porque es la que lee `_tracker_project_for` (`project_context.py:98`). Usar otros nombres dejaría el proyecto creado pero **inalcanzable**.

#### Tests (PRIMERO) — `test_plan259_project_manager_gitlab.py`

Usar `monkeypatch.setattr(project_manager, "PROJECTS_DIR", tmp_path)` para no tocar el perfil real (gotcha del plan 216).

| Test | Qué asegura |
|---|---|
| `test_crea_config_con_forma_canonica` | `issue_tracker == {"type":"gitlab","base_url":"https://gitlab.com","project":"acme/api","auth_file":"auth/gitlab_auth.json"}`. |
| `test_group_opcional_ausente_si_vacio` | Sin `group`, la clave **no está** en el dict (no `""`). |
| `test_group_presente_si_se_pasa` | Con `group="acme"`, `issue_tracker["group"] == "acme"`. |
| `test_url_sin_barra_final` | `url="https://gitlab.com/"` → `base_url == "https://gitlab.com"`. |
| `test_client_profile_sembrado` | `"client_profile" in cfg` (lo hace `initialize_project:165-169` con `get_default_client_profile("gitlab")`). **Si `get_default_client_profile` no conociera "gitlab", este test lo destapa acá y no en producción.** |
| `test_token_no_queda_en_claro` | Tras `write_gitlab_auth(..., token="glpat-SECRETO")`, el texto del archivo **no** contiene `glpat-SECRETO` y `payload["token_format"]` está seteado. |
| `test_token_se_puede_releer` | `read_secret_from_file(path, "token", format_field="token_format").value == "glpat-SECRETO"`. |
| `test_idempotente_preserva_extras` | Un `config.json` previo con `pinned_agents` conserva esa clave tras re-inicializar. |
| `test_auth_path_resuelve_a_gitlab_auth` | `project_context._auth_path_for(cfg)` termina en `auth/gitlab_auth.json`. |
| `test_build_tracker_target_lee_lo_escrito` | Con el proyecto creado y activo, `build_tracker_target(name)` devuelve `project_path=="acme/api"` y `base_url=="https://gitlab.com"`. **Cierra el lazo escritura↔lectura.** |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan259_project_manager_gitlab.py -v`
Si aparece `SQLITE_LOCKED`, correr el archivo 8-12 veces seguidas (gotcha shared-cache de la casa) y estabilizar con `run_with_retry` alrededor de la unidad de trabajo.

**Criterio de aceptación BINARIO:** los 10 tests en verde y
```
.venv\Scripts\python.exe -c "import project_manager as p; print('initialize_gitlab_project' in p.__all__, 'write_gitlab_auth' in p.__all__)"
```
imprime `True True`.

**Flag:** `STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED` (default **ON**). Las funciones son aditivas y no tienen call site hasta F2, así que no llevan guard interno: el guard vive en el endpoint.
**Impacto por runtime:** ninguno. **Fallback:** idéntico en los 3.
**Trabajo del operador:** ninguno.

---

### F2 — Cablear `api/projects.py`: rama GitLab en alta, edición, credenciales y listado

**Objetivo:** que la API cree, actualice y devuelva proyectos GitLab, y que **deje de convertirlos a Azure DevOps en silencio**.
**Valor:** cierra un bug de corrupción de datos vivo hoy (E2).

**Archivo a EDITAR:** `Stacky Agents/backend/api/projects.py`
**Archivo a CREAR:** `Stacky Agents/backend/tests/test_plan259_api_projects_gitlab.py`

**Cambio 1 — import** (`api/projects.py:39-59`): agregar `initialize_gitlab_project` y `write_gitlab_auth` a la lista importada de `project_manager`.

**Cambio 2 — `_has_credentials` (`:69-77`)**, que hoy manda GitLab al archivo de Mantis:

```python
def _has_credentials(name: str, tracker_type: str) -> bool:
    """Indica si el proyecto tiene archivo de credenciales almacenado."""
    if tracker_type == "azure_devops":
        auth_filename = "ado_auth.json"
    elif tracker_type == "jira":
        auth_filename = "jira_auth.json"
    elif tracker_type == "gitlab":            # Plan 259 F2 — antes caía en mantis_auth.json
        auth_filename = "gitlab_auth.json"
    else:  # mantis
        auth_filename = "mantis_auth.json"
    return (PROJECTS_DIR / name / "auth" / auth_filename).exists()
```

**Cambio 3 — `_project_to_dict` (`:80-109`)**: agregar los 4 campos que `EditProjectModal.tsx:41-44` ya lee y que hoy llegan siempre vacíos, con el mismo patrón condicional que usan `jira_url`/`mantis_url`:

```python
        # GitLab fields (Plan 259 F2)
        "gitlab_url":        tracker.get("base_url", "") if t_type == "gitlab" else "",
        "gitlab_project":    tracker.get("project", "")  if t_type == "gitlab" else "",
        "gitlab_group":      tracker.get("group", "")    if t_type == "gitlab" else "",
        "gitlab_auth_file":  tracker.get("auth_file", "") if t_type == "gitlab" else "",
```

**Cambio 4 — helper de guard, nuevo, después de `_has_credentials`:**

```python
def _gitlab_onboarding_enabled() -> bool:
    """Plan 259 F2 — la flag vive en la INSTANCIA (config.config), no en el módulo.
    Mismo idioma que tracker_provider.py:133 y ci_provider.py:121."""
    try:
        import config as _config
        return bool(getattr(_config.config, "STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED", False))
    except Exception:
        return False
```

**Cambio 5 — rama GitLab en `init_project`**, insertada **antes** del `else: # azure_devops` (`:360`):

```python
        elif tracker_type == "gitlab":
            if not _gitlab_onboarding_enabled():
                return jsonify({"ok": False, "error":
                    "El alta de proyectos GitLab está apagada "
                    "(STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED=false)."}), 400
            gitlab_url     = (data.get("gitlab_url") or "").strip()
            gitlab_project = (data.get("gitlab_project") or "").strip()
            gitlab_group   = (data.get("gitlab_group") or "").strip()
            gitlab_token   = (data.get("gitlab_token") or "").strip()
            enable_engine  = bool(data.get("gitlab_enable_engine", True))

            if not gitlab_url:
                return jsonify({"ok": False, "error": "gitlab_url requerida"}), 400
            if not gitlab_project:
                return jsonify({"ok": False, "error": "gitlab_project requerido"}), 400

            cfg = initialize_gitlab_project(
                name=name,
                display_name=display_name or name,
                workspace_root=workspace_root,
                url=gitlab_url,
                project_path=gitlab_project,
                group=gitlab_group,
                auth_file="auth/gitlab_auth.json",
                docs_paths=docs_paths,
                agents_dir=agents_dir,
            )
            if gitlab_token:
                write_gitlab_auth(name=name, url=gitlab_url,
                                  token=gitlab_token, project_path=gitlab_project)
            if enable_engine:
                engine_result = _enable_gitlab_engine()   # F7
```

**Cambio 6 — misma rama en `update_project`**, antes del `else` (`:504`), con `_resolve_text_field` para PATCH parcial:

```python
        elif tracker_type == "gitlab":
            if not _gitlab_onboarding_enabled():
                return jsonify({"ok": False, "error":
                    "La edición de proyectos GitLab está apagada "
                    "(STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED=false)."}), 400
            tracker        = cfg.get("issue_tracker") or {}
            gitlab_url     = _resolve_text_field(data, "gitlab_url",     tracker.get("base_url", ""))
            gitlab_project = _resolve_text_field(data, "gitlab_project", tracker.get("project", ""))
            gitlab_group   = _resolve_text_field(data, "gitlab_group",   tracker.get("group", ""))
            gitlab_token   = (data.get("gitlab_token") or "").strip()
            new_cfg = initialize_gitlab_project(
                name=project_name,
                display_name=(data.get("display_name") or cfg.get("display_name", project_name)).strip(),
                workspace_root=workspace_root,
                url=gitlab_url,
                project_path=gitlab_project,
                group=gitlab_group,
                auth_file="auth/gitlab_auth.json",
                docs_paths=docs_paths,
                agents_dir=agents_dir,
            )
            if gitlab_token:
                write_gitlab_auth(name=project_name, url=gitlab_url,
                                  token=gitlab_token, project_path=gitlab_project)
```

**Cambio 7 — `get_project_credentials` (`:543-...`)**: agregar al `result` la clave `"gitlab_token_saved": (PROJECTS_DIR / project_name / "auth" / "gitlab_auth.json").exists()`. Nunca devolver el token.

**Cambio 8 — docstring del módulo (`:11-27`)**: agregar el bloque de campos GitLab, para que el contrato quede escrito donde ya están los otros 3.

#### Tests (PRIMERO) — `test_plan259_api_projects_gitlab.py`

Cliente Flask de test + `monkeypatch` de `PROJECTS_DIR` a `tmp_path` en `project_manager` **y** en `api.projects` (importa el símbolo por valor).

| Test | Qué asegura |
|---|---|
| `test_init_gitlab_devuelve_200` | `POST /api/init_project` con `tracker_type="gitlab"` → 200 y `project["tracker_type"] == "gitlab"`. |
| `test_init_gitlab_escribe_type_gitlab` | El `config.json` en disco tiene `issue_tracker.type == "gitlab"`. **Anti-regresión del bug E2.** |
| `test_init_gitlab_sin_url_400` | Falta `gitlab_url` → 400 con `"gitlab_url requerida"`. |
| `test_init_gitlab_sin_project_400` | Falta `gitlab_project` → 400 con `"gitlab_project requerido"`. |
| `test_init_gitlab_no_exige_organization` | El body **no** manda `organization` y responde 200 (hoy responde 400). |
| `test_patch_a_gitlab_no_degrada_a_ado` | Proyecto ADO existente + `PATCH {"tracker_type":"gitlab","gitlab_url":...,"gitlab_project":...}` → `config.json` queda con `type=="gitlab"`. **Este test falla contra el árbol actual: es la prueba del bug.** |
| `test_patch_parcial_preserva_url` | `PATCH {"display_name":"X"}` sobre un proyecto GitLab conserva `base_url` y `project`. |
| `test_listado_expone_campos_gitlab` | `GET /api/projects` → el proyecto trae `gitlab_url`, `gitlab_project`, `gitlab_group`, `gitlab_auth_file` con los valores escritos. |
| `test_listado_no_filtra_gitlab_en_proyecto_ado` | Un proyecto ADO trae los 4 campos GitLab en `""`. |
| `test_has_credentials_gitlab` | Con `auth/gitlab_auth.json` presente → `has_credentials is True`; sin él → `False`. |
| `test_token_nunca_en_la_respuesta` | El token enviado en el body **no** aparece en `json.dumps(response.get_json())` de init, patch, listado ni `/credentials`. |
| `test_flag_off_rechaza_explicito` | Con `monkeypatch.setattr(config.config, "STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED", False)`: 400 con el mensaje que nombra la flag, y **el `config.json` NO se creó**. Nunca degradación silenciosa. |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan259_api_projects_gitlab.py -v`

**Criterio de aceptación BINARIO:** 12 tests en verde, y esta verificación de no-regresión de los otros trackers, también en verde:
```
.venv\Scripts\python.exe -m pytest tests/test_plan208_profile_schema.py -v
```

**Flag:** `STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED` (default **ON**). Con la flag OFF el endpoint **rechaza explícito**; jamás vuelve a caer al `else` de ADO.
**Impacto por runtime:** ninguno. **Fallback:** idéntico en los 3.
**Trabajo del operador:** ninguno.

---

### F3 — Que GitLab pueda leer el token cifrado (sin romper el formato plano actual)

**Objetivo:** que `GitLabClient` descifre el token que F1 escribe, y siga leyendo los archivos en texto plano que existan hoy.
**Valor:** sin esto, F1+F2 crean un proyecto que da **401 en la primera llamada** — un falso verde de manual.

**Archivo a EDITAR:** `Stacky Agents/backend/services/gitlab_client.py`
**Archivo a CREAR:** `Stacky Agents/backend/tests/test_plan259_gitlab_token_dpapi.py`

Reemplazar `_load_token_from_file` (`gitlab_client.py:75-93`) por:

```python
    def _load_token_from_file(self, auth_path: Optional[str]) -> str:
        """Busca el token en auth/gitlab_auth.json bajo auth_path.

        Plan 259 F3: usa read_secret_from_file, que descifra DPAPI cuando el
        archivo declara token_format y devuelve el valor tal cual cuando está en
        texto plano. Backward-compatible con los archivos que existan hoy.
        """
        from services.secrets_store import read_secret_from_file  # import local: evita ciclo

        candidates: list[Path] = []
        if auth_path:
            candidates.append(Path(auth_path) / "auth" / "gitlab_auth.json")
            candidates.append(Path(auth_path))
        candidates.append(Path("auth") / "gitlab_auth.json")

        for path in candidates:
            if not path.exists():
                continue
            for field, fmt in (("token", "token_format"), ("private_token", "private_token_format")):
                try:
                    tok = (read_secret_from_file(path, field, format_field=fmt).value or "").strip()
                except Exception:
                    tok = ""
                if tok:
                    return tok
        return ""
```

> **No se toca** la precedencia `env > archivo` de `:62-64`: cambiarla rompería instalaciones que hoy dependen de `GITLAB_TOKEN`. La trampa queda **documentada** en el paso `gl-10-env-precedencia` y **detectada** por el chequeo `chk-token` de F4, que no usa esa precedencia.

#### Tests (PRIMERO) — `test_plan259_gitlab_token_dpapi.py`

| Test | Qué asegura |
|---|---|
| `test_lee_token_cifrado_dpapi` | Escribir con `write_gitlab_auth(token="glpat-XYZ")` y construir `GitLabClient(auth_path=<dir_proyecto>)` → `client._token == "glpat-XYZ"`. |
| `test_lee_token_plano_legacy` | `{"token": "glpat-PLANO"}` sin `token_format` → `client._token == "glpat-PLANO"`. **Backward-compat.** |
| `test_lee_private_token_legacy` | `{"private_token": "glpat-VIEJO"}` → se lee igual. |
| `test_archivo_corrupto_no_lanza` | JSON inválido → `_load_token_from_file` devuelve `""` y el constructor tira `TrackerConfigError` (no `JSONDecodeError`). |
| `test_env_sigue_ganando` | Con `GITLAB_TOKEN=env-token` en el entorno y un archivo cifrado distinto → `client._token == "env-token"`. **Congela la precedencia documentada.** |
| `test_sin_token_error_claro` | Sin env y sin archivo → `TrackerConfigError` con el mensaje actual, byte por byte. |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan259_gitlab_token_dpapi.py -v`

**Criterio de aceptación BINARIO:** 6 tests en verde **y** los tests GitLab preexistentes sin tocar:
```
.venv\Scripts\python.exe -m pytest tests/test_plan218_gitlab_reachable.py -v
.venv\Scripts\python.exe -m pytest tests/test_plan70_smoke_gitlab.py -v
```

**Flag:** ninguna nueva. Es una corrección de compatibilidad interna del lector, no una funcionalidad conmutable; ponerla detrás de un flag dejaría un camino en el que F1 escribe cifrado y el cliente lee criptograma.
**Impacto por runtime:** ninguno. **Fallback:** si DPAPI no está disponible (no-Windows), `read_secret_from_file` devuelve el valor tal cual y el archivo plano sigue funcionando, exactamente como hoy.
**Trabajo del operador:** ninguno.

---

### F4 — Endpoints: servir la guía y verificar en vivo

**Objetivo:** exponer la guía de F0 y 5 chequeos de solo lectura que le digan al operador **cuál** de los 12 pasos le falta.
**Valor:** convierte "info detallada" en "info detallada **verificada**". Es la diferencia entre un manual y un diagnóstico.

**Archivos a CREAR:**
- `Stacky Agents/backend/api/setup_guide.py`
- `Stacky Agents/backend/services/gitlab_setup_check.py`
- `Stacky Agents/backend/tests/test_plan259_setup_guide_api.py`

**Archivo a EDITAR:** `Stacky Agents/backend/api/__init__.py` (registrar el blueprint junto a los demás, patrón de `:37` y `:111`).

#### F4.a — `services/gitlab_setup_check.py`

Camino HTTP **propio y mínimo**, deliberadamente separado de `GitLabClient` por tres razones concretas: (1) `GitLabClient` lee `GITLAB_TOKEN` del entorno y **taparía** el token tipeado (E5) → falso verde; (2) lanza `TrackerConfigError` en `__init__` si no hay token, y acá "no hay token" es un **resultado**, no una excepción; (3) acá hace falta `allow_redirects=False`, que el cliente general no impone.

```python
"""Plan 259 F4 — 5 chequeos de SOLO LECTURA de una configuración GitLab.

NUNCA escribe: ni en GitLab, ni en disco, ni en os.environ.
NUNCA loguea el token ni lo devuelve.
allow_redirects=False: un 30x podría reenviar el header PRIVATE-TOKEN a otro host.
"""
from __future__ import annotations

import urllib.parse
import requests

_TIMEOUT_S = 8
_OK, _FAIL, _UNKNOWN = "ok", "fail", "unknown"


def _res(check_id, status, message, detail=""):
    return {"id": check_id, "status": status, "message": message, "detail": detail}


def _get(base: str, path: str, token: str | None):
    headers = {"Accept": "application/json"}
    if token:
        headers["PRIVATE-TOKEN"] = token
    return requests.get(f"{base}/api/v4{path}", headers=headers,
                        timeout=_TIMEOUT_S, allow_redirects=False)


def run_gitlab_checks(base_url: str, project_path: str, token: str,
                      engine_enabled: bool) -> list[dict]:
    out: list[dict] = []

    # chk-flag — local, sin red
    out.append(_res("chk-flag", _OK if engine_enabled else _FAIL,
                    "El motor GitLab está encendido." if engine_enabled
                    else "El motor GitLab está apagado: la sincronización va a fallar."))

    base = (base_url or "").rstrip("/")
    if not base.startswith(("http://", "https://")):
        out.append(_res("chk-instancia", _FAIL,
                        "La URL tiene que empezar con http:// o https://."))
        for cid in ("chk-token", "chk-scope", "chk-proyecto"):
            out.append(_res(cid, _UNKNOWN, "No se pudo probar: falta una URL válida."))
        return out

    # chk-instancia — sin token
    try:
        r = _get(base, "/version", None)
        if r.status_code in (200, 401):
            out.append(_res("chk-instancia", _OK, "La URL responde y es un GitLab."))
        elif r.status_code in (301, 302, 307, 308):
            out.append(_res("chk-instancia", _FAIL,
                            "La URL redirige a otro lado. Usá la dirección final.",
                            f"HTTP {r.status_code}"))
            for cid in ("chk-token", "chk-scope", "chk-proyecto"):
                out.append(_res(cid, _UNKNOWN, "No se pudo probar: la URL redirige."))
            return out
        else:
            out.append(_res("chk-instancia", _FAIL,
                            "La dirección responde pero no parece un GitLab.",
                            f"HTTP {r.status_code}"))
    except requests.RequestException as exc:
        out.append(_res("chk-instancia", _FAIL,
                        "No se pudo llegar a esa dirección.", type(exc).__name__))
        for cid in ("chk-token", "chk-scope", "chk-proyecto"):
            out.append(_res(cid, _UNKNOWN, "No se pudo probar: la dirección no responde."))
        return out

    if not token:
        for cid, msg in (("chk-token",    "Falta pegar el token."),
                         ("chk-scope",    "No se pudo probar: falta el token."),
                         ("chk-proyecto", "No se pudo probar: falta el token.")):
            out.append(_res(cid, _FAIL if cid == "chk-token" else _UNKNOWN, msg))
        return out

    # chk-token
    try:
        r = _get(base, "/user", token)
        if r.status_code == 200:
            out.append(_res("chk-token", _OK,
                            f"Token válido (usuario: {r.json().get('username', '?')})."))
        elif r.status_code in (401, 403):
            out.append(_res("chk-token", _FAIL,
                            "El token no sirve: está mal copiado, venció o fue revocado."))
        else:
            out.append(_res("chk-token", _UNKNOWN,
                            "Respuesta inesperada al validar el token.", f"HTTP {r.status_code}"))
    except requests.RequestException as exc:
        out.append(_res("chk-token", _UNKNOWN, "No se pudo validar el token.", type(exc).__name__))

    # chk-scope — GitLab 15.x+; 404 en tokens de proyecto o versiones viejas ⇒ unknown, no rojo
    try:
        r = _get(base, "/personal_access_tokens/self", token)
        if r.status_code == 200:
            scopes = r.json().get("scopes") or []
            if "api" in scopes:
                out.append(_res("chk-scope", _OK, "El token tiene el permiso 'api'."))
            elif "read_api" in scopes:
                out.append(_res("chk-scope", _FAIL,
                                "El token solo puede LEER ('read_api'). Stacky no va a poder "
                                "comentar ni cerrar tickets.", f"permisos: {', '.join(scopes)}"))
            else:
                out.append(_res("chk-scope", _FAIL,
                                "Al token le falta el permiso 'api'.",
                                f"permisos: {', '.join(scopes) or 'ninguno'}"))
        else:
            out.append(_res("chk-scope", _UNKNOWN,
                            "Tu GitLab no informa los permisos del token. "
                            "Revisá a mano que tenga 'api'.", f"HTTP {r.status_code}"))
    except requests.RequestException as exc:
        out.append(_res("chk-scope", _UNKNOWN,
                        "No se pudieron consultar los permisos.", type(exc).__name__))

    # chk-proyecto
    pp = (project_path or "").strip()
    if not pp:
        out.append(_res("chk-proyecto", _FAIL, "Falta el path del proyecto."))
        return out
    enc = urllib.parse.quote(pp, safe="") if not pp.isdigit() else pp
    try:
        r = _get(base, f"/projects/{enc}", token)
        if r.status_code == 200:
            body = r.json()
            if body.get("issues_enabled") is False:
                out.append(_res("chk-proyecto", _FAIL,
                                "El proyecto existe pero tiene los Issues deshabilitados.",
                                body.get("name_with_namespace", "")))
            else:
                out.append(_res("chk-proyecto", _OK,
                                f"Proyecto encontrado: {body.get('name_with_namespace', pp)}."))
        elif r.status_code == 404:
            out.append(_res("chk-proyecto", _FAIL,
                            "No existe un proyecto con ese path, o tu usuario no tiene acceso."))
        else:
            out.append(_res("chk-proyecto", _UNKNOWN,
                            "Respuesta inesperada al buscar el proyecto.", f"HTTP {r.status_code}"))
    except requests.RequestException as exc:
        out.append(_res("chk-proyecto", _UNKNOWN,
                        "No se pudo buscar el proyecto.", type(exc).__name__))
    return out


__all__ = ["run_gitlab_checks"]
```

#### F4.b — `api/setup_guide.py`

```python
GET  /api/setup-guide/<provider>          → { ok, guide }        (404 si no hay guía)
POST /api/setup-guide/gitlab/verify       → { ok, checks: [...] }
```

- El `GET` responde `{"ok": False, "error": "guía deshabilitada"}`, **403**, si `config.config.STACKY_SETUP_GUIDE_ENABLED` es `False`.
- El `POST` responde **403** si `STACKY_SETUP_GUIDE_VERIFY_ENABLED` es `False`.
- Body del `POST`: `{"gitlab_url": str, "gitlab_project": str, "gitlab_token": str}`. `engine_enabled` **no** viene del cliente: lo lee el servidor de `config.config.STACKY_GITLAB_ENABLED` (que el cliente mienta no puede pintar un verde falso).
- El handler envuelve todo en `try/except Exception` y **nunca** loguea el body. La línea de log es exactamente:
  `logger.info("setup-guide verify gitlab: %s", {c["id"]: c["status"] for c in checks})`.

#### Tests (PRIMERO) — `test_plan259_setup_guide_api.py`

`monkeypatch.setattr(services.gitlab_setup_check, "requests", FakeRequests)` — **cero red real** (guard de red del plan 154).

| Test | Qué asegura |
|---|---|
| `test_get_guia_gitlab_200` | 200, `guide["provider"]=="gitlab"`, 12 pasos, 5 chequeos. |
| `test_get_guia_desconocida_404` | `GET /api/setup-guide/azure_devops` → 404. |
| `test_get_flag_off_403` | `STACKY_SETUP_GUIDE_ENABLED=False` → 403. |
| `test_verify_flag_off_403` | `STACKY_SETUP_GUIDE_VERIFY_ENABLED=False` → 403 **y `FakeRequests.get` con 0 llamadas**. |
| `test_verify_todo_ok` | Fake que responde 200 a `/version`, `/user`, `/personal_access_tokens/self` (con `scopes:["api"]`) y `/projects/...` (con `issues_enabled:True`) → los 5 chequeos en `ok`. |
| `test_verify_devuelve_siempre_5_chequeos` | En **todos** los escenarios (sin URL, URL caída, sin token, 404 de proyecto) hay exactamente 5 resultados y los `id` son los 5 de la guía. **Invariante que la UI necesita para pintar la lista.** |
| `test_verify_url_invalida` | `gitlab_url="gitlab.com"` (sin esquema) → `chk-instancia` en `fail`, los 3 siguientes en `unknown`, **0 llamadas HTTP**. |
| `test_verify_redirect_no_reenvia_token` | Fake que devuelve 302 en `/version` → `chk-instancia` en `fail` y **`FakeRequests.get` fue llamado exactamente 1 vez**, sin `PRIVATE-TOKEN` en esa llamada. **Anti-fuga de credencial.** |
| `test_verify_token_401` | `/user` → 401 ⇒ `chk-token` en `fail`. |
| `test_verify_scope_read_api` | `scopes:["read_api"]` ⇒ `chk-scope` en `fail` con el texto de solo lectura. |
| `test_verify_scope_404_es_unknown` | `/personal_access_tokens/self` → 404 ⇒ `chk-scope` en `unknown`, **no** `fail`. |
| `test_verify_issues_deshabilitado` | `issues_enabled:False` ⇒ `chk-proyecto` en `fail`. |
| `test_verify_project_path_numerico_no_se_encodea` | `gitlab_project="4711"` ⇒ la URL pedida termina en `/projects/4711`. |
| `test_verify_project_path_con_barras_se_encodea` | `"acme/backend/api"` ⇒ `/projects/acme%2Fbackend%2Fapi`. |
| `test_verify_nunca_devuelve_el_token` | El token del body no aparece en `json.dumps(response.get_json())`. |
| `test_verify_timeout_y_sin_redirects` | Toda llamada del fake recibió `timeout=8` y `allow_redirects=False`. |
| `test_engine_enabled_lo_pone_el_servidor` | Body con `{"engine_enabled": true}` mentiroso y `config.config.STACKY_GITLAB_ENABLED=False` ⇒ `chk-flag` en `fail`. |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan259_setup_guide_api.py -v`

**Criterio de aceptación BINARIO:** 17 tests en verde y
```
.venv\Scripts\python.exe -c "from app import create_app; a=create_app(); print(sorted(str(r) for r in a.url_map.iter_rules() if 'setup-guide' in str(r)))"
```
imprime las 2 rutas.

**Flag:** `STACKY_SETUP_GUIDE_ENABLED` y `STACKY_SETUP_GUIDE_VERIFY_ENABLED`, ambas default **ON**.
**Impacto por runtime:** ninguno (HTTP determinista, sin LLM). **Fallback:** si el endpoint responde 403/500, F6 pinta la copia embebida de la guía y oculta el botón "Verificar ahora".
**Trabajo del operador:** ninguno.

---

### F5 — UI: el botón GitLab en el alta (lógica en módulo puro)

**Objetivo:** que "Nuevo Proyecto" ofrezca **🦊 GitLab** con sus campos y su validación.
**Valor:** el pedido literal del operador, parte 1.

**Archivos a CREAR:**
- `Stacky Agents/frontend/src/projects/newProjectGitlabModel.ts` (PURO)
- `Stacky Agents/frontend/src/__tests__/plan259GitlabOnboarding.test.ts`

**Archivos a EDITAR:**
- `Stacky Agents/frontend/src/types.ts`
- `Stacky Agents/frontend/src/api/endpoints.ts`
- `Stacky Agents/frontend/src/components/NewProjectModal.tsx`

#### F5.a — `types.ts`

En `InitProjectPayload` (`:296-329`), el bloque GitLab ya existe (`:324-328`). Agregar **solo** las 2 claves que faltan:

```ts
  gitlab_token?: string;
  gitlab_enable_engine?: boolean;
```

#### F5.b — `newProjectGitlabModel.ts` (PURO — sin React, sin fetch)

```ts
/** Plan 259 F5 — lógica pura del alta GitLab. Sin React y sin red:
 *  RTL/jsdom no están instalados en este repo, así que TODO lo testeable vive acá. */

export interface GitlabFormValues {
  gitlab_url?: string;
  gitlab_project?: string;
  gitlab_token?: string;
  gitlab_group?: string;
  gitlab_enable_engine?: boolean;
}

/** Errores por campo del bloque GitLab. {} = válido. */
export function validateGitlabFields(f: GitlabFormValues): Record<string, string> {
  const errs: Record<string, string> = {};
  const url = (f.gitlab_url ?? "").trim();
  const proj = (f.gitlab_project ?? "").trim();
  if (!url) errs.gitlab_url = "Ingresá la URL base de GitLab (ej: https://gitlab.com)";
  else if (!/^https?:\/\//i.test(url)) errs.gitlab_url = "La URL tiene que empezar con http:// o https://";
  else if (/\/api\/v4\/?$/i.test(url)) errs.gitlab_url = "Quitá el /api/v4 del final: lo agrega Stacky";
  if (!proj) errs.gitlab_project = "Ingresá el path del proyecto (ej: grupo/proyecto)";
  else if (/^https?:\/\//i.test(proj)) errs.gitlab_project = "Poné solo el path, sin https:// ni el dominio";
  if (!(f.gitlab_token ?? "").trim()) errs.gitlab_token = "Pegá el token de acceso de GitLab";
  return errs;
}

/** Quita la barra final y un /api/v4 pegado; no toca nada más. */
export function normalizeGitlabUrl(raw: string): string {
  return (raw ?? "").trim().replace(/\/+$/, "").replace(/\/api\/v4$/i, "");
}

/** 'https://gitlab.com/acme/api/-/issues' → 'acme/api'. Un path ya limpio queda igual. */
export function normalizeGitlabProjectPath(raw: string): string {
  let v = (raw ?? "").trim();
  v = v.replace(/^https?:\/\/[^/]+\//i, "");
  v = v.split("/-/")[0];
  return v.replace(/^\/+/, "").replace(/\/+$/, "");
}

/** Default del motor: tildado salvo que el operador lo haya destildado. */
export function engineCheckboxDefault(current: boolean | undefined): boolean {
  return current === undefined ? true : current;
}

/** Orden DOM del bloque GitLab, para el foco-al-primer-error (patrón NP_FIELD_DOM_ORDER). */
export const GITLAB_FIELD_DOM_ORDER = ["gitlab_url", "gitlab_project", "gitlab_token"] as const;
```

#### F5.c — `NewProjectModal.tsx`

1. `EMPTY` (`:13-38`): agregar `gitlab_url: ""`, `gitlab_project: ""`, `gitlab_group: ""`, `gitlab_token: ""`, `gitlab_enable_engine: true`.
2. Cuarto botón en `trackerRow` (`:372-394`), después de Mantis:
   ```tsx
   <button type="button"
     className={`${styles.trackerBtn} ${isGitlab ? styles.trackerBtnActive : ""}`}
     onClick={() => setTrackerType("gitlab")}>🦊 GitLab</button>
   ```
   Renderizado solo si `flags.STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED !== false`, leído de `/api/diag/health` (las flags de UI viven ahí, gotcha de la casa). Si la lectura falla, se **muestra** (fail-open hacia la funcionalidad; el backend igual valida).
3. `const isGitlab = form.tracker_type === "gitlab";` junto a `:248-250`.
4. Bloque `{isGitlab && (...)}` con `Field` + `Input`, ids `np-gitlab_url`, `np-gitlab_project`, `np-gitlab_token`, `np-gitlab_group`:
   - URL base — placeholder `Ej: https://gitlab.com`
   - Path del proyecto — placeholder `Ej: grupo/subgrupo/proyecto`
   - Token de acceso — `type="password"`, placeholder `Pegá el token con permiso 'api'`
   - `<details>` "🔍 Opciones avanzadas GitLab" → Grupo (para épicas nativas)
   - `Checkbox` `label="Activar el motor GitLab (necesario para que sincronice)"`, `checked={form.gitlab_enable_engine !== false}`
   - `<p className={styles.note}>` con: `Las credenciales se guardan cifradas en backend/projects/{nombre}/auth/gitlab_auth.json`
5. `validate` (`:199-220`): `if (f.tracker_type === "gitlab") return { ...errs, ...validateGitlabFields(f) };` **antes** del `else` de Mantis — hoy ese `else` es el catch-all y aplicaría reglas de Mantis a GitLab.
6. `NP_FIELD_DOM_ORDER` (`:223`): insertar `"gitlab_url","gitlab_project","gitlab_token"` después de `"mantis_token"`.
7. `buildPayload` (`:79-85`): si es GitLab, normalizar con `normalizeGitlabUrl` / `normalizeGitlabProjectPath` antes de enviar.
8. **Cero `style={{}}`**: todo por clases de `NewProjectModal.module.css` (ratchet `uiDebtRatchet`).

#### Tests (PRIMERO) — `plan259GitlabOnboarding.test.ts`

| Test | Qué asegura |
|---|---|
| `valida url vacia` | `validateGitlabFields({})` trae `gitlab_url`, `gitlab_project`, `gitlab_token`. |
| `valida url sin esquema` | `"gitlab.com"` ⇒ error de esquema. |
| `rechaza /api/v4 al final` | `"https://gitlab.com/api/v4"` ⇒ error con el texto de quitar `/api/v4`. |
| `acepta config completa` | URL + path + token ⇒ `{}`. |
| `rechaza url completa como path` | `gitlab_project="https://gitlab.com/acme/api"` ⇒ error. |
| `normaliza barra final` | `normalizeGitlabUrl("https://gitlab.com/")` ⇒ `"https://gitlab.com"`. |
| `normaliza /api/v4` | `"https://gl.io/api/v4"` ⇒ `"https://gl.io"`. |
| `normaliza path desde url completa` | `"https://gitlab.com/acme/backend/api/-/issues"` ⇒ `"acme/backend/api"`. |
| `path limpio no se toca` | `"acme/api"` ⇒ `"acme/api"`. |
| `path numerico no se toca` | `"4711"` ⇒ `"4711"`. |
| `motor tildado por default` | `engineCheckboxDefault(undefined) === true`; `engineCheckboxDefault(false) === false`. |
| `orden dom cubre los 3 obligatorios` | `GITLAB_FIELD_DOM_ORDER` tiene exactamente las 3 keys que `validateGitlabFields({})` reporta. **Sin esto, el foco-al-primer-error apunta a un campo inexistente.** |

**Comando (desde `Stacky Agents/frontend`):** `npx vitest run src/__tests__/plan259GitlabOnboarding.test.ts`

**Criterio de aceptación BINARIO:** 12 tests en verde,
```
npx tsc --noEmit
```
con **0 errores**, y
```
npx vitest run src/__tests__/uiDebtRatchet.test.ts
```
en verde sin regenerar la línea base (implica **cero** `style={{}}` nuevo).

**Flag:** `STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED` (default **ON**).
**Impacto por runtime:** ninguno — es la UI del backend, común a los 3. **Fallback:** si `/api/diag/health` no responde, el botón se muestra igual y el backend valida.
**Trabajo del operador:** ninguno.

---

### F6 — UI: el botón INFO y el panel de la guía

**Objetivo:** un botón **ℹ️ INFO** junto al selector de tracker que abre la guía completa, con "Verificar ahora".
**Valor:** el pedido literal del operador, parte 2.

**Archivos a CREAR:**
- `Stacky Agents/frontend/src/projects/setupGuideModel.ts` (PURO)
- `Stacky Agents/frontend/src/components/SetupGuideDialog.tsx`
- `Stacky Agents/frontend/src/components/SetupGuideDialog.module.css`
- `Stacky Agents/frontend/src/__tests__/plan259SetupGuideModel.test.ts`

**Archivos a EDITAR:** `endpoints.ts`, `NewProjectModal.tsx`, `types.ts`.

#### F6.a — `endpoints.ts`

```ts
export const SetupGuide = {
  get: (provider: string) =>
    rawGet<{ ok: boolean; guide?: SetupGuideDoc; error?: string }>(`/api/setup-guide/${provider}`),
  verifyGitlab: (payload: { gitlab_url: string; gitlab_project: string; gitlab_token: string }) =>
    rawPost<{ ok: boolean; checks?: GuideCheckResult[]; error?: string }>(
      "/api/setup-guide/gitlab/verify", payload),
};
```

> **`rawGet`/`rawPost`, no `api.get`/`api.post`**: el wrapper `api.*` **lanza** en cualquier respuesta no-2xx (gotcha de la casa), y acá un `403` (flag apagada) y un `404` (sin guía) son respuestas normales que hay que pintar, no excepciones.

#### F6.b — `setupGuideModel.ts` (PURO)

```ts
export type CheckStatus = "ok" | "fail" | "unknown";
export interface GuideCheckResult { id: string; status: CheckStatus; message: string; detail?: string }
export interface GuideStepDoc { id: string; title: string; detail: string; where: string; trap?: string }
export interface GuideCheckDoc { id: string; title: string; fixes_step: string }
export interface SetupGuideDoc {
  provider: string; display_name: string; summary: string;
  required_fields: string[]; steps: GuideStepDoc[]; checks: GuideCheckDoc[];
}

/** Resumen para el encabezado del panel. */
export function summarizeChecks(rs: GuideCheckResult[]): { ok: number; fail: number; unknown: number; verdict: CheckStatus } {
  const ok = rs.filter(r => r.status === "ok").length;
  const fail = rs.filter(r => r.status === "fail").length;
  const unknown = rs.filter(r => r.status === "unknown").length;
  return { ok, fail, unknown, verdict: fail > 0 ? "fail" : unknown > 0 ? "unknown" : "ok" };
}

/** Ids de paso a resaltar: los que arreglan los chequeos en 'fail'. */
export function stepsToHighlight(guide: SetupGuideDoc | null, rs: GuideCheckResult[]): string[] {
  if (!guide) return [];
  const failed = new Set(rs.filter(r => r.status === "fail").map(r => r.id));
  return guide.checks.filter(c => failed.has(c.id)).map(c => c.fixes_step);
}

/** El botón "Verificar ahora" se habilita solo con URL y path cargados. */
export function canVerify(v: { gitlab_url?: string; gitlab_project?: string }): boolean {
  return Boolean((v.gitlab_url ?? "").trim()) && Boolean((v.gitlab_project ?? "").trim());
}

/** Copia embebida mínima si el endpoint no responde. NUNCA deja al operador sin nada. */
export const GITLAB_FALLBACK_GUIDE: SetupGuideDoc = { /* provider gitlab, summary + 3 pasos:
   gl-01-instancia, gl-02-token, gl-04-project-path, checks: [] */ };

/** true si la guía viene del servidor; false si es la copia embebida. */
export function isServerGuide(g: SetupGuideDoc | null): boolean {
  return Boolean(g) && g !== GITLAB_FALLBACK_GUIDE;
}
```

#### F6.c — `SetupGuideDialog.tsx`

- Usa `Dialog` canónico con `size="lg"`, `title={`Cómo configurar ${guide.display_name}`}`. **No** reimplementa portal, focus-trap ni Escape.
- Estructura: resumen → lista numerada de pasos (badge `where`: `GitLab` / `Stacky` / `Windows`; la `trap` en una tira `⚠️`) → bloque "Verificar ahora".
- Un paso resaltado por `stepsToHighlight` lleva la clase `stepHighlight` y un `aria-current="step"`.
- Botón "Verificar ahora" `disabled={!canVerify(values)}`; mientras corre, `aria-busy`.
- Resultados: una fila por chequeo con `✅ / ❌ / ❔`, el `message` y, si es `fail`, `→ ver paso N`.
- **Fallback:** si `SetupGuide.get` responde no-2xx o tira, se pinta `GITLAB_FALLBACK_GUIDE` con una tira `Mostrando la guía básica embebida: no se pudo leer la guía del servidor.` y el bloque de verificación oculto.
- **Cero `style={{}}`** (ratchet `uiDebtRatchet` es `forcedZero` para archivos nuevos).
- El token **no** se guarda en estado del diálogo: se pasa como argumento a `verifyGitlab` y se descarta.

#### F6.d — El botón INFO en `NewProjectModal.tsx`

En la fila del selector, después de los 4 botones:

```tsx
{guideAvailable && (
  <button type="button" className={styles.btnInfo} onClick={() => setGuideOpen(true)}
          title="Cómo configurar este sistema de tickets" aria-label="Información de configuración">
    ℹ️ INFO
  </button>
)}
```

`guideAvailable` = `form.tracker_type === "gitlab" && flags.STACKY_SETUP_GUIDE_ENABLED !== false`. En este plan **solo GitLab tiene guía**; el botón no aparece para los otros 3 (honesto: nada de un INFO que abre un panel vacío).

#### Tests (PRIMERO) — `plan259SetupGuideModel.test.ts`

| Test | Qué asegura |
|---|---|
| `resumen todo ok` | 5 `ok` ⇒ `{ok:5,fail:0,unknown:0,verdict:"ok"}`. |
| `un fail manda` | 4 `ok` + 1 `fail` ⇒ `verdict:"fail"`. |
| `unknown sin fail` | 4 `ok` + 1 `unknown` ⇒ `verdict:"unknown"`. |
| `lista vacia` | `[]` ⇒ `verdict:"ok"` y los 3 contadores en 0. |
| `resalta el paso del check fallado` | `chk-token` en `fail` ⇒ `["gl-02-token"]`. |
| `resalta varios sin repetir orden` | 2 fails ⇒ los 2 `fixes_step`, en el orden de `guide.checks`. |
| `no resalta si no hay guia` | `stepsToHighlight(null, [...]) === []`. |
| `no resalta los ok` | Todos `ok` ⇒ `[]`. |
| `canVerify exige url y path` | 4 combinaciones cubiertas. |
| `fallback tiene contenido` | `GITLAB_FALLBACK_GUIDE.steps.length >= 3` y todos con `title` y `detail` no vacíos. |
| `isServerGuide distingue` | `isServerGuide(GITLAB_FALLBACK_GUIDE) === false`; con un doc del servidor, `true`; con `null`, `false`. |

**Comando:** `npx vitest run src/__tests__/plan259SetupGuideModel.test.ts`

**Criterio de aceptación BINARIO:** 11 tests en verde, `npx tsc --noEmit` en 0 errores, y `npx vitest run src/__tests__/uiDebtRatchet.test.ts` en verde **sin regenerar la línea base**.

**Flag:** `STACKY_SETUP_GUIDE_ENABLED` (panel) y `STACKY_SETUP_GUIDE_VERIFY_ENABLED` (botón verificar), ambas **ON**.
**Impacto por runtime:** ninguno. **Fallback:** guía embebida si el servidor no responde; el botón de verificar se oculta si su flag está OFF.
**Trabajo del operador:** ninguno (el INFO es opcional; si no lo abre, el alta funciona igual).

---

### F7 — Encender el motor GitLab en el mismo acto de creación (HITL, visible, reversible)

**Objetivo:** que el proyecto recién creado **sincronice al primer intento**, sin mandar al operador a otra pantalla.
**Valor:** sin esta fase el KPI "sincroniza al primer intento" queda en 0 %: `STACKY_GITLAB_ENABLED` nace en `false` (E6).

**Archivo a EDITAR:** `Stacky Agents/backend/api/projects.py`
**Archivo a CREAR:** `Stacky Agents/backend/tests/test_plan259_enable_engine.py`

```python
def _enable_gitlab_engine() -> dict:
    """Plan 259 F7 — enciende STACKY_GITLAB_ENABLED reusando el camino canónico
    de la casa (harness_flags.apply_updates: .env + os.environ + hot-apply).

    Se dispara SOLO desde init_project con tracker_type="gitlab" y la casilla
    `gitlab_enable_engine` tildada — es decir, tras un clic explícito del operador
    en "Crear e inicializar". NO hay ningún camino automático que llegue acá.
    Best-effort: si falla, el proyecto igual se crea y se informa en la respuesta.
    """
    try:
        import config as _config
        if bool(getattr(_config.config, "STACKY_GITLAB_ENABLED", False)):
            return {"changed": False, "already_on": True}
        from services.harness_flags import apply_updates
        apply_updates({"STACKY_GITLAB_ENABLED": "true"})
        logger.info("Plan 259 F7: STACKY_GITLAB_ENABLED encendido al crear un proyecto GitLab")
        return {"changed": True, "already_on": False}
    except Exception as exc:
        logger.warning("Plan 259 F7: no se pudo encender STACKY_GITLAB_ENABLED: %s", exc)
        return {"changed": False, "already_on": False, "error": str(exc)}
```

La respuesta de `init_project` para GitLab suma `"gitlab_engine": engine_result`, y F5 lo pinta como
`✅ Motor GitLab activado.` / `ℹ️ El motor GitLab ya estaba activado.` / `⚠️ El proyecto se creó, pero no se pudo activar el motor GitLab. Actívalo en Configuración → Paridad de proveedores.`

> **Por qué esto NO viola las reglas.** No es autonomía proactiva: el disparo exige (a) elegir GitLab, (b) dejar tildada una casilla que dice qué hace, (c) apretar "Crear e inicializar". No es destructivo ni irreversible: `apply_updates` es el mismo camino que ya usa el panel de flags, y la perilla se apaga desde ahí. No reduce la seguridad: `STACKY_GITLAB_ENABLED` no abre nada por sí sola — sin un proyecto de tipo `gitlab` la rama ni se evalúa (`tracker_provider.py:130`). Y **no cambia ningún default**: `config.py:1185` sigue diciendo `"false"`.

#### Tests (PRIMERO) — `test_plan259_enable_engine.py`

| Test | Qué asegura |
|---|---|
| `test_enciende_si_estaba_apagado` | Con `STACKY_GITLAB_ENABLED=False` y `apply_updates` espiado: se llama **una** vez con `{"STACKY_GITLAB_ENABLED":"true"}`; devuelve `changed=True`. |
| `test_no_toca_si_ya_estaba_on` | Con `True`: `apply_updates` **0 llamadas**, `already_on=True`. |
| `test_falla_no_rompe_el_alta` | `apply_updates` lanza ⇒ `POST /api/init_project` responde **200**, el `config.json` existe y `gitlab_engine.error` está poblado. |
| `test_checkbox_destildada_no_enciende` | Body con `gitlab_enable_engine: false` ⇒ `apply_updates` **0 llamadas** y proyecto creado igual. |
| `test_no_se_dispara_en_otros_trackers` | Alta ADO / Jira / Mantis ⇒ `apply_updates` **0 llamadas**. |
| `test_no_se_dispara_en_patch` | `PATCH` a un proyecto GitLab ⇒ `apply_updates` **0 llamadas**. Encender es del alta, no de la edición. |

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan259_enable_engine.py -v`

**Criterio de aceptación BINARIO:** 6 tests en verde y
```
.venv\Scripts\python.exe -c "import re,pathlib; s=pathlib.Path('config.py').read_text(encoding='utf-8'); print(bool(re.search(r'STACKY_GITLAB_ENABLED\", \"false\"', s)))"
```
imprime `True` — **el default no se movió.**

**Flag:** `STACKY_PROJECT_GITLAB_ONBOARDING_ENABLED` (default **ON**) — es la misma que gatea toda la rama de alta GitLab.
**Impacto por runtime:** ninguno. **Fallback:** si `apply_updates` falla, el proyecto queda creado y el mensaje dice exactamente dónde prender la perilla a mano.
**Trabajo del operador:** ninguno (casilla tildada por default, destildable).

---

### F8 — Cierre: registro en el arnés, huella de regresión y documentación

**Objetivo:** que los 6 archivos de test nuevos queden bajo el ratchet del arnés y que el bug de degradación silenciosa quede huellado.
**Valor:** sin esto, la cobertura del arnés se encoge en silencio y `test_ratchet_clasifica_todos_los_tests` (`tests/test_harness_ratchet_meta.py:43-53`) queda **ROJO**.

**Archivos a EDITAR:**
- `Stacky Agents/backend/scripts/run_harness_tests.sh` — agregar al array `HARNESS_TEST_FILES` (`:20`), una línea por archivo, con la forma exacta `tests/test_planNNN_*.py` que exige el regex `^\s*(tests/[\w/]+\.py)\s*$` (`test_harness_ratchet_meta.py:21`):
  ```
  tests/test_plan259_setup_guide_data.py
  tests/test_plan259_project_manager_gitlab.py
  tests/test_plan259_api_projects_gitlab.py
  tests/test_plan259_gitlab_token_dpapi.py
  tests/test_plan259_setup_guide_api.py
  tests/test_plan259_enable_engine.py
  ```
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` — el equivalente Windows, misma lista.
- `Stacky Agents/docs/sistema/error_fingerprints.json` — entrada nueva:
  - `id`: `plan259-gitlab-tracker-downgrade`
  - `pattern`: `issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false`
  - `meaning`: `El proyecto está configurado como GitLab pero el motor GitLab está apagado.`
  - `fix`: `Configuración → Paridad de proveedores → activar "STACKY_GITLAB_ENABLED", o recrear el proyecto dejando tildada la casilla del motor.`
- `Stacky Agents/backend/api/projects.py` — docstring del módulo con el bloque de campos GitLab (Cambio 8 de F2).

**Prohibido:** agregar cualquiera de los 6 a `tests/harness_ratchet_allowlist.txt`. Son tests nuevos que pasan aislados; la allowlist solo puede **bajar** (`_ALLOWLIST_MAX`, `test_harness_ratchet_meta.py:66-70`).

**Tests:**
```
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -v
```

**Criterio de aceptación BINARIO:** los 3 tests del meta-ratchet en verde y
```
.venv\Scripts\python.exe -c "import json,pathlib; d=json.loads(pathlib.Path('../docs/sistema/error_fingerprints.json').read_text(encoding='utf-8')); print(any('plan259' in json.dumps(x) for x in (d if isinstance(d,list) else d.get('fingerprints',[]))))"
```
imprime `True`.

**Flag:** ninguna (infraestructura de tests y documentación).
**Impacto por runtime:** ninguno. **Fallback:** N/A.
**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación (concreta, en este plan) |
|---|---|---|---|
| R1 | F1 escribe el token cifrado y `GitLabClient` sigue leyéndolo crudo ⇒ **401 con todo "bien configurado"**. | **Alta** si F3 no se hace | F3 es **obligatoria** y va antes de habilitar la UI; `test_lee_token_cifrado_dpapi` cierra el lazo escritura↔lectura. |
| R2 | El chequeo `chk-token` da verde con un `GITLAB_TOKEN` viejo del entorno, tapando el token recién tipeado (E5). | Media | `gitlab_setup_check` **no** usa `GitLabClient` ni lee `os.environ`: manda el header con el token del body y nada más. Cubierto por `test_engine_enabled_lo_pone_el_servidor` y el diseño de `_get`. |
| R3 | Una URL maliciosa/mal tipeada redirige y `requests` reenvía `PRIVATE-TOKEN` a otro host. | Baja, impacto alto | `allow_redirects=False` en toda llamada; un 30x en `/version` **corta** la verificación antes de mandar el token. `test_verify_redirect_no_reenvia_token` lo blinda. |
| R4 | Los tests de F4 salen a internet de verdad y quedan flaky / violan el guard de red del plan 154. | Media | `monkeypatch` del símbolo `requests` **dentro** de `services.gitlab_setup_check`. `test_verify_url_invalida` afirma **0 llamadas**. |
| R5 | `get_default_client_profile("gitlab")` no tiene template y `initialize_project:165-169` explota al crear. | Media | `test_client_profile_sembrado` (F1) lo detecta en la primera corrida; si falta, se agrega el template GitLab en `services/client_profile.py` copiando el de ADO, dentro de F1. |
| R6 | Editar `NewProjectModal.tsx` choca con la sesión paralela viva (memoria: `TicketBoard.tsx`/`UnblockerPage.tsx` bloqueados). | Media | `NewProjectModal.tsx` **no** está en la lista de bloqueados. Aun así: `git worktree list` **antes** de tocar, y commit con `git commit -- "<ruta>"` explícito, sin `add -A`, sin `reset`, sin `amend`. |
| R7 | Las 3 flags nuevas rompen `test_default_known_only_for_curated` por olvidar `_CURATED_DEFAULTS_ON`. | Media | Está explícito en F0.b y verificado por el comando de aceptación de F0 (`test_harness_flags.py`). |
| R8 | El texto de menús de GitLab ("Edit profile" → "Access tokens") cambia en una versión futura. | Media | Los pasos declaran su alcance ("versiones 16.x y 17.x") y **cada uno tiene un chequeo que verifica el resultado**, no el camino: aunque el menú se mueva, `chk-token` sigue diciendo si el token sirve. |
| R9 | `apply_updates` de F7 escribe el `.env` y pisa algo. | Baja | Es el mismo camino que ya usa el panel de flags (`api/harness_flags.py:130`); `_write_env` (`global_config.py:131-156`) solo reescribe la clave pedida y preserva el resto. Envuelto en `try/except`: nunca rompe el alta. |
| R10 | Los tests que tocan la DB fallan con `SQLITE_LOCKED` bajo pytest. | Alta (gotcha conocido) | Correr cada archivo 8-12 veces y envolver la unidad de trabajo en `run_with_retry`. Declarado en F1. |

---

## 6. Fuera de scope

- Guías de configuración para Azure DevOps, Jira y Mantis. La infraestructura queda lista (`SETUP_GUIDES` es un dict, `guide_exists` decide si se pinta el botón), pero **este plan solo escribe la de GitLab**, que es lo pedido. El botón INFO no aparece para los otros 3.
- Descubrir proyectos GitLab por API para ofrecer un desplegable (lo análogo a "Cargar proyectos de Mantis").
- Épicas nativas de GitLab (`STACKY_GITLAB_EPICS_NATIVE`): el campo Grupo se carga y se guarda, pero encender esa funcionalidad es otro plan.
- Cambiar el default de `STACKY_GITLAB_ENABLED` en `config.py`. Sigue OFF por excepción dura #3.
- Migrar tickets de otro tracker a GitLab (eso es el plan 74 / el migrador Mantis→GitLab del plan 217).
- Soporte de GitLab en el asistente DevOps de pipelines (planes 246-252 ya cubren ese eje).
- Deshabilitar la verificación SSL para GitLab: decisión explícita de **no** ofrecerlo (paso `gl-11-ssl`).

---

## 7. Glosario

| Término | Qué es en este plan |
|---|---|
| **Tracker** | Sistema de tickets del que Stacky lee y en el que escribe: Azure DevOps, Jira, Mantis o GitLab. |
| **`issue_tracker`** | Bloque dentro de `backend/projects/<NOMBRE>/config.json` que describe el tracker del proyecto. Su clave `type` decide todo el ruteo. |
| **Project path (GitLab)** | `grupo/subgrupo/proyecto`. Es lo que va después del dominio en la URL. También se acepta el ID numérico. Stacky codifica las barras como `%2F` (`gitlab_client.py:98-105`). |
| **PAT / Personal Access Token** | Token personal de GitLab. En la guía se lo llama siempre "token de acceso" para no usar la sigla. |
| **Scope `api`** | Permiso del token que habilita leer **y** escribir por la API. `read_api` solo lee. |
| **DPAPI** | Cifrado de Windows atado al usuario que lo hizo. Es como Stacky guarda todas las credenciales. No es portable a otro usuario ni a otra máquina. |
| **Flag del arnés** | Perilla de configuración editable desde Configuración → Arnés en la UI, persistida en el `.env`. Registrada en `FLAG_REGISTRY` (`services/harness_flags.py`). |
| **Excepción dura** | Una de las 4 razones tasadas por las que una flag puede nacer OFF: (1) bypasea revisión humana, (2) es destructiva/irreversible, (3) exige un prerequisito no garantizado, (4) reduce la seguridad. |
| **Ratchet del arnés** | Guardia que exige que todo `tests/test_*.py` nuevo figure en `HARNESS_TEST_FILES` o en la allowlist. Lo verifica `tests/test_harness_ratchet_meta.py`. |
| **Módulo puro** | `.py`/`.ts` sin IO, sin red, sin framework: solo datos y funciones. Es lo único testeable en este repo del lado del frontend, porque RTL/jsdom no están instalados. |
| **`config.config`** | La **instancia** de `Config`. Leer la flag del **módulo** `config` devuelve siempre el default y mata el camino OFF (gotcha de la casa, `tracker_provider.py:131-133`). |
| **Degradación silenciosa** | Que el sistema haga algo distinto de lo pedido sin avisar. Es lo que hace hoy `update_project` con GitLab (E2) y lo que este plan elimina. |

---

## 8. Orden de implementación

1. **F0** — `services/setup_guides.py` + las 3 flags (`config.py`, `harness_flags.py`, `_CURATED_DEFAULTS_ON`) + su test.
2. **F1** — `initialize_gitlab_project` + `write_gitlab_auth` en `project_manager.py` + su test. *(Si `test_client_profile_sembrado` falla, agregar el template GitLab en `services/client_profile.py` acá, ver R5.)*
3. **F3** — lector DPAPI en `gitlab_client.py` + su test. **Va antes que F2**: sin esto, todo lo que F2 cree nace con 401.
4. **F2** — cableado de `api/projects.py` (init, patch, `_has_credentials`, `_project_to_dict`, credentials, docstring) + su test.
5. **F7** — `_enable_gitlab_engine` + su test. *(Depende de F2: se llama desde la rama GitLab de `init_project`.)*
6. **F4** — `services/gitlab_setup_check.py` + `api/setup_guide.py` + registro del blueprint + su test.
7. **F5** — `newProjectGitlabModel.ts` + `types.ts` + `NewProjectModal.tsx` + su test vitest.
8. **F6** — `setupGuideModel.ts` + `SetupGuideDialog.tsx` + `.module.css` + `endpoints.ts` + botón INFO + su test vitest.
9. **F8** — `run_harness_tests.sh` / `.ps1` + `error_fingerprints.json` + meta-ratchet.

---

## 9. Definición de Hecho (DoD)

El plan está hecho cuando **todo** lo siguiente es cierto y verificado corriendo:

- [ ] Los **6 archivos de test backend** en verde, corridos **de a uno**:
  ```
  .venv\Scripts\python.exe -m pytest tests/test_plan259_setup_guide_data.py -v
  .venv\Scripts\python.exe -m pytest tests/test_plan259_project_manager_gitlab.py -v
  .venv\Scripts\python.exe -m pytest tests/test_plan259_gitlab_token_dpapi.py -v
  .venv\Scripts\python.exe -m pytest tests/test_plan259_api_projects_gitlab.py -v
  .venv\Scripts\python.exe -m pytest tests/test_plan259_enable_engine.py -v
  .venv\Scripts\python.exe -m pytest tests/test_plan259_setup_guide_api.py -v
  ```
- [ ] Los **2 archivos de test frontend** en verde:
  ```
  npx vitest run src/__tests__/plan259GitlabOnboarding.test.ts
  npx vitest run src/__tests__/plan259SetupGuideModel.test.ts
  ```
- [ ] **Sin regresiones** en los guardianes que este plan toca:
  ```
  .venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -v
  .venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -v
  .venv\Scripts\python.exe -m pytest tests/test_plan218_gitlab_reachable.py -v
  .venv\Scripts\python.exe -m pytest tests/test_plan70_smoke_gitlab.py -v
  npx vitest run src/__tests__/uiDebtRatchet.test.ts
  ```
- [ ] `npx tsc --noEmit` con **0 errores**.
- [ ] `.venv\Scripts\python.exe -m compileall -q backend` sin errores.
- [ ] `config.py` sigue teniendo `STACKY_GITLAB_ENABLED` con default `"false"` (comando de F7).
- [ ] **Smoke manual (HITL, lo corre el operador):** abrir "Nuevo Proyecto" → aparece **🦊 GitLab** → aparece **ℹ️ INFO** → el panel abre con **12 pasos** → "Verificar ahora" con datos falsos marca en rojo el chequeo correcto y señala el paso que lo arregla → con datos reales, los 5 en verde → "Crear e inicializar" → el proyecto aparece en la lista con tipo **GitLab** y `has_credentials` en true → el `config.json` en disco dice `"type": "gitlab"`.
- [ ] Ningún archivo bajo `frontend/src/components/` nuevo tiene `style={{`.
- [ ] El token no aparece en ningún log ni en ninguna respuesta HTTP (verificado por `test_token_nunca_en_la_respuesta` y `test_verify_nunca_devuelve_el_token`).
- [ ] Commit con `git commit -- "<rutas explícitas>"`. **Sin `git add -A`, sin `reset`, sin `amend`, sin `--no-verify`.** `git push` **solo** si el operador lo pide.
