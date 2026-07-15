# Plan 139 — App Shell v2: sidebar agrupada, TopBar profesional e iconografía

**Estado:** PROPUESTO v1 (2026-07-15 — serie UI/UX 138-141)

**Autor:** StackyArchitectaUltraEficientCode (perfil normal)

**Depende de:** Plan 138 (Sistema de Diseño v2 — tokens + primitivas + ratchet). Este plan
CONSUME el contrato congelado en `138_..._TOKENS_SEMANTICOS_Y_PRIMITIVAS_UI.md § 10`
(tokens `--space-*`, `--text-*`, `--weight-*`, `--radius-*`, `--shadow-*`, `--duration-*`,
`--ease-*`, `--focus-ring`, `--status-*`; primitivas `IconButton`, `Tabs`, `StatusChip`,
`SectionHeader`, `Button`, `Card` en `frontend/src/components/ui/`). **PROHIBIDO redefinir
tokens o primitivas: solo se consumen por su nombre EXACTO.**

**Se implementa DESPUÉS de:** 138 (esta serie) y de la serie pendiente 132 → 134 → 135 → 136
(orden congelado por el plan 134 v2 §3.3). `App.tsx`, `TopBar.tsx` y su `.module.css` son
**zonas calientes** que 134/135/136 editan: por eso TODAS las anclas de este plan son por
**TEXTO normativo** (los `:NN` de línea son orientativos, snapshot 2026-07-15) y cada fase
lleva **pre-flight obligatorio** (`git status -- "<ruta>"` antes de tocar CADA archivo; si hay
WIP ajeno sin commitear → **STOP**, avisar al operador, no editar). Staging quirúrgico
siempre: `git add -- <paths>` explícitos, **NUNCA** `git add -A`.

---

## § 1. Objetivo y valor

Hoy la navegación global es una **fila plana de 14 pestañas con emojis**
(`frontend/src/App.tsx`, `<nav className={styles.nav}>` con 14 `.navTab`, patrón underline en
`App.module.css:7-39`). Cada plan agrega una pestaña (dbcompare fue la 14.ª, Plan 122) y el
costo de navegación crece linealmente (el propio Plan 129 §2 lo declaró como problema). La
fila ya no escala: no hay agrupamiento, la iconografía es emoji inconsistente, y a >12 tabs la
barra empieza a apretarse/wrapear.

Este plan crea un **App Shell v2** detrás de flag opt-in (default OFF):

1. **Sidebar (barra lateral) agrupada** por 5 grupos nombrados y congelados
   (Trabajo / Observabilidad / Conocimiento / Plataforma / Configuración).
2. **Iconografía `lucide-react`** (ya en `package.json ^0.453.0` — verificado, no se agrega
   dependencia): tabla exacta emoji → ícono por tab.
3. **TopBar profesional** re-estilada con los tokens del 138 (spacing/tipografía/sombra),
   gateada por la flag (con OFF, TopBar idéntica a hoy).
4. **Sidebar colapsable** con persistencia en `localStorage` y **responsive** (riel de iconos
   automático en pantallas angostas).

**CERO cambio de comportamiento:** los mismos 14 tabs, el mismo `type Tab`, el mismo
`TAB_PATHS`, la misma lógica de gating (`sections.*`, `*Enabled`), la misma navegación
(`selectTab`/`navigateTo`), el mismo mapeo path↔tab, el mismo montaje/desmontaje de páginas.
Solo cambia la **presentación del chrome de navegación**.

### KPI (verificables)

- **KPI-1 (byte-identidad):** con la flag OFF, el DOM renderizado del shell es idéntico al
  actual (misma `<nav>`, mismos 14 botones, misma TopBar). Verificación: smoke §11 caso OFF +
  criterio binario F3/F4.
- **KPI-2 (agrupamiento):** con la flag ON, los 14 tabs aparecen distribuidos en exactamente 5
  grupos, cada tab en exactamente 1 grupo (test puro `shellNav.test.ts`).
- **KPI-3 (iconografía real):** los 14 iconNames resuelven a un componente `lucide-react`
  existente (test puro `shellIcons.test.ts`).
- **KPI-4 (gating idéntico):** un tab oculto en v1 (por `sections.*` o `*Enabled`) también está
  oculto en el sidebar v2 (test puro `computeVisibleTabs` + smoke).
- **KPI-5 (deuda UI 0 en archivos nuevos):** los `.module.css` nuevos tienen **0** hex y los
  `.tsx` nuevos tienen **0** `style={{` (ratchet del 138 §10.3; `components/shell/**` parte de
  baseline 0).

---

## § 2. Flag (congelada — NO renombrar)

| Campo | Valor |
|---|---|
| Key | `STACKY_UI_SHELL_V2_ENABLED` |
| Tipo | `bool` |
| Default | **OFF** (opt-in del operador) |
| Categoría UI | `interfaz_ui` (categoría NUEVA de este plan) |
| `group` (FlagSpec) | `"global"` |
| `env_only` | `False` (atributo de `Config`, editable por UI) |
| Patrón | idéntico al Plan 119 (`STACKY_DEVOPS_UI_V2_ENABLED`): OFF ⇒ UI **byte-idéntica** a hoy |

**GOTCHA de la casa (declarado):** una `FlagSpec` con `default` ON **fuera** de
`_CURATED_DEFAULTS_ON` (`backend/tests/test_harness_flags.py:465`) rompe
`test_default_known_only_for_curated` (`:625`). Como esta flag es **default OFF**, NO se declara
`default` en la `FlagSpec` (cae al type-zero `False` vía `declared_default`) y **NO** se agrega a
`_CURATED_DEFAULTS_ON`. No hay riesgo, pero queda declarado para que el implementador no lo
promueva por costumbre.

### Mecanismo EXACTO de lectura de la flag por el frontend

El Plan 119 lee su flag de panel con `GET /api/devops/health → { flag_enabled }`
(`api/devops/health`, consumido en `App.tsx:95-98`). Ese endpoint es **feature-scoped** (DevOps).
Para un shell **global** el equivalente correcto es el **health global** que ya existe y ya se
consume en el chrome:

- **Endpoint reusado:** `GET /api/diag/health` — `backend/api/diag.py:286` `def health()`, retorno
  JSON en `diag.py:353-367`. Ya lo consume `TopBar` vía `Health.get()`
  (`frontend/src/api/endpoints.ts:2601-2603`, `TopBar.tsx:95-99`).
- **Campo NUEVO (ADITIVO):** se agrega `"shell_v2_enabled": bool(...)` al dict de retorno de
  `health()`, junto a `"local_llm_enabled"` (`diag.py:364`, mismo patrón `getattr(_config.config,
  ...)`). Aditivo puro: ningún consumidor existente se rompe.
- **Lectura en `App.tsx`:** un `fetch("/api/diag/health")` más en el `useEffect` de montaje,
  idéntico en forma a los 3 fetches de health que `App.tsx` ya hace (migrador/devops/dbcompare,
  `App.tsx:90-103`). Estado `shellV2Enabled` (default `false`; `.catch(() => false)`).

Evidencia de que `/api/diag/health` es el health global y ligero de reusar: `diag.py:36`
importa `get_app_version`; `diag.py:26` `import config as _config`; `diag.py:364` ya expone otra
flag (`LOCAL_LLM_ENABLED`) por el mismo patrón. **No se crea blueprint ni endpoint nuevo.**

---

## § 3. Contratos que este plan DEBE preservar (con evidencia)

Sección normativa. Cada ítem es un **contrato binario** que el implementador verifica.

### 3.1 Serie 132→134→135→136 aterriza ANTES (zonas calientes)
- **Evidencia:** orden congelado por Plan 134 v2 §3.3 (memoria del arquitecto). `App.tsx` y
  `TopBar.tsx` son editados por 134/135/136.
- **Contrato:** anclas por TEXTO normativo, no por línea; **pre-flight `git status -- "<ruta>"`
  antes de CADA archivo en CADA fase**; WIP ajeno sin commitear ⇒ STOP. Staging por paths
  explícitos.

### 3.2 Plan 134 (pendiente): badges de navegación
- **Qué aporta 134:** badge numérico en el botón de nav **Revisión**, badge "agente trabajando"
  con conteo en TopBar, y título de pestaña vivo (`document.title`).
- **Contrato del shell v2:**
  - El sidebar renderiza el **mismo badge** que la nav actual para cada tab, vía la prop
    `badges?: Partial<Record<ShellTab, ReactNode>>` de `AppSidebar` (ranura `.itemBadge`). El
    valor lo provee `App.tsx` desde **la misma fuente** que usa la nav v1.
  - El badge "agente trabajando" y el título vivo son de **TopBar** / `document.title`, que este
    plan **no toca funcionalmente** (F4 solo agrega una clase de estilo aditiva `.barV2`). Por lo
    tanto siguen renderizando igual con la flag ON u OFF.
  - **Integración con 134 (pre-flight explícito en F3):** como 134 aterriza ANTES, `App.tsx` ya
    tendrá el badge de Revisión en la `<nav>` v1. El implementador hace `grep -n "review"
    App.tsx` para localizar la expresión del badge y la **espeja** dentro del objeto `badges`
    que pasa a `<AppSidebar>`. Si 134 aún no aterrizó (no debería), pasa `badges={{}}`: el
    sidebar simplemente no muestra badge, igual que una nav v1 sin badge. **139 NO implementa
    lógica de badges**; solo la ranura.

### 3.3 Plan 135 F6 (pendiente): gating por health-check con retry
- **Qué aporta 135 F6:** los tabs Migrador/DevOps/Comparador BD se montan según health-check con
  reintento (`probeFlagHealth`).
- **Contrato:** el sidebar respeta el **mismo gating**: item oculto ⟺ tab oculto. Se implementa
  con la función pura `computeVisibleTabs(...)` que **consume los booleanos resultantes**
  (`migradorEnabled`, `devopsEnabled`, `dbCompareEnabled`, `sections.*`) — **desacoplada de CÓMO
  se obtienen** (fetch simple hoy, `probeFlagHealth` con 135). Si 135 cambia el mecanismo de
  fetch, los booleanos siguen existiendo en el estado de `App` y la visibilidad no cambia.
- **Evidencia del gating actual:** `App.tsx:141-149` (fallback a "team" cuando un tab opcional se
  oculta) y los condicionales de render `App.tsx:183-256`.

### 3.4 Plan 136 F7 (pendiente): sincronización tab↔URL (Ctrl+/)
- **Contrato:** el click en un item del sidebar llama a **`selectTab(tab)`** — exactamente el
  mismo handler que la nav v1 (`App.tsx:70-76`, hace `pushState` a `TAB_PATHS[next]`). El mapeo
  `path↔tab` (`TAB_PATHS`, `tabFromPath`, `App.tsx:33-54`) **no se toca**. El atajo Ctrl+/
  (`App.tsx:121,128-133`) queda intacto (vive en el handler `onKeyDown`, que este plan no edita).

### 3.5 Plan 129 (implementado): paleta Ctrl+K
- **Contrato:** los comandos `nav-*` de `CommandPalette` navegan vía `onNavigate(path) →
  navigateTo` (`App.tsx:78-84,274-278`; `CommandPalette.tsx:85-128`). El shell v2 **no toca**
  `CommandPalette` ni `navigateTo`. Los comandos funcionan idénticos con v1 y v2 (ambos terminan
  en el mismo `setTab` + `pushState`).

### 3.6 Plan 119 (implementado en rama, aún no en main): shell v2 INTERNO de DevOps
- **Evidencia:** `DevOpsPage.tsx:221-258` — barra de sub-tabs INTERNA de la página DevOps
  (`role="tablist"` con `DEVOPS_SECTIONS`). Es el chrome INTERNO de una página.
- **Contrato de convivencia:** el sidebar de este plan es el chrome **GLOBAL** (afuera de las
  páginas). No se pisan: el sidebar navega ENTRE páginas; las sub-tabs de DevOps navegan DENTRO
  de la página DevOps. Se reusa el **vocabulario visual** (tokens del 138; el patrón underline de
  v1 se reemplaza por resaltado de item en v2), no el código.

### 3.7 Montaje de páginas: CERO remount extra
- **Evidencia:** `App.tsx:259-272` monta 14 páginas con condicionales
  `{tab === "x" && <X/>}` (montaje/desmontaje por tab; NO keep-mounted).
- **Contrato binario:** este plan extrae ese bloque a un `const pages = (<>…</>)` **con los
  condicionales EXACTAMENTE iguales** y lo renderiza en ambas ramas (v1 y v2). Un fragment de
  React es transparente en el DOM ⇒ mismo árbol montado, mismo timing de montaje/desmontaje,
  **cero remounts extra**. La flag se lee una sola vez al montar; cambiarla exige recargar
  (no hay re-montaje en caliente por toggle).

---

## § 4. Restricciones no negociables

- **3 runtimes con paridad:** este plan es 100% frontend + 1 flag del arnés leída por un campo
  aditivo de un endpoint existente. Es **runtime-agnóstico**: no toca `claude_code_cli`,
  `codex` ni `github_copilot`. Se declara el impacto/fallback **por fase** (todas: impacto
  runtime = ninguno; fallback = flag OFF = UI actual).
- **Cero trabajo extra del operador:** flag opt-in default OFF; estrenarla = 1 click en
  `HarnessFlagsPanel` (Configuración → Arnés → categoría "Interfaz").
- **Human-in-the-loop; mono-operador sin auth:** no se agregan roles ni permisos.
- **No degradar** performance / seguridad / estabilidad / DX; **backward-compatible**.
- **PROHIBIDO agregar dependencias:** `package.json` **NO se toca** (verificar `git status --
  "Stacky Agents/frontend/package.json"` limpio al final). `lucide-react` ya está.
- **Ratchet de deuda UI (138 §10.3):** los archivos NUEVOS (`components/shell/**`) deben tener
  **0 hex** en `.module.css` y **0 `style={{`** en `.tsx`. Se consumen SOLO tokens/primitivas.
  Los archivos existentes que se editan (`App.module.css`, `TopBar.module.css`) **no aumentan**
  su conteo de hex (solo se AGREGAN reglas token-only).

---

## § 5. Inventario de archivos

### Nuevos (todos frontend, todos en `frontend/src/components/shell/`)
1. `shellNav.ts` — **PURO** (datos + funciones puras): grupos, meta por tab, `computeVisibleTabs`,
   `orderedVisibleGroups`, key/parse de colapso.
2. `shellIcons.ts` — mapa `ICON_BY_NAME` (nombre → componente `lucide-react`). Sin CSS, sin JSX.
3. `AppSidebar.tsx` — componente del sidebar (consume `shellNav`, `shellIcons`, primitiva
   `IconButton`, `AppSidebar.module.css`).
4. `AppSidebar.module.css` — estilos **token-only** (0 hex).
5. `__tests__/shellNav.test.ts` — vitest puro (sin RTL).
6. `__tests__/shellIcons.test.ts` — vitest puro (sin RTL).

### Nuevo (backend)
7. `backend/tests/test_plan139_shell_flag.py` — pytest del F0.

### Modificados
- `backend/config.py` — atributo `STACKY_UI_SHELL_V2_ENABLED`.
- `backend/services/harness_flags.py` — `FlagSpec` + `CategorySpec("interfaz_ui", …)` +
  entrada en `_CATEGORY_KEYS`.
- `backend/services/harness_flags_help.py` — entrada `PlainHelp`.
- `backend/api/diag.py` — campo aditivo `shell_v2_enabled` en `health()`.
- `frontend/src/api/endpoints.ts` — tipo de retorno de `Health.get` extendido (aditivo).
- `frontend/src/App.tsx` — lectura de flag, extracción de `pages`, render condicional
  sidebar↔nav, wiring de colapso/persistencia, prop `shellV2` a TopBar.
- `frontend/src/App.module.css` — clases `.shellLayout` / `.shellContent` (token-only).
- `frontend/src/components/TopBar.tsx` — prop `shellV2?: boolean` (aditiva) + clase condicional.
- `frontend/src/components/TopBar.module.css` — clase `.barV2` + subreglas (token-only).

---

## § 6. Decisiones congeladas (tablas normativas)

### 6.1 Agrupamiento de los 14 tabs (CONGELADO)

Orden de grupos (de arriba hacia abajo en el sidebar):

| # | Grupo (`id`) | Label | Tabs (en orden) |
|---|---|---|---|
| 1 | `trabajo` | Trabajo | `team`, `tickets`, `review`, `unblocker` |
| 2 | `observabilidad` | Observabilidad | `pm`, `logs`, `history`, `diagnostics` |
| 3 | `conocimiento` | Conocimiento | `docs`, `memory` |
| 4 | `plataforma` | Plataforma | `devops`, `migrador`, `dbcompare` |
| 5 | `configuracion` | Configuración | `settings` |

Cobertura: 4 + 4 + 2 + 3 + 1 = **14**, cada tab en exactamente 1 grupo. Racional:
- **Trabajo** = flujo diario del operador (equipo, tickets, aprobar en Revisión, desatascar).
- **Observabilidad** = tableros y diagnóstico (PM, logs, historial, diagnóstico).
- **Conocimiento** = documentación y memoria.
- **Plataforma** = infraestructura/CI/BD (DevOps, migrador ADO→GitLab, comparador de BD).
- **Configuración** = ajustes (siempre al fondo).

### 6.2 Iconografía emoji → `lucide-react` (CONGELADO; los 14 verificados existentes)

| tab | label v2 | emoji actual | icono `lucide-react` (`iconName`) |
|---|---|---|---|
| `team` | Mi Equipo | ⚡ | `Zap` |
| `tickets` | Tickets ADO | 📋 | `ClipboardList` |
| `review` | Revisión | 🧭 | `Inbox` |
| `unblocker` | Desatascador | 🧹 | `Wrench` |
| `pm` | PM | 📊 | `LayoutDashboard` |
| `logs` | System Logs | 🔍 | `ScrollText` |
| `history` | Historial | 📋 | `History` |
| `diagnostics` | Diagnóstico | 🩺 | `Stethoscope` |
| `docs` | Docs | 📄 | `FileText` |
| `memory` | Memoria | (sin emoji) | `Brain` |
| `devops` | DevOps | (sin emoji) | `Server` |
| `migrador` | Migrador | (sin emoji) | `ArrowRightLeft` |
| `dbcompare` | Comparador BD | (sin emoji) | `Database` |
| `settings` | Configuración | ⚙️ | `Settings` |

Toggle de colapso: `PanelLeftClose` (expandido → plegar) / `PanelLeftOpen` (plegado → expandir).
Todos verificados presentes en `lucide-react ^0.453.0` (probe empírico 2026-07-15).

Los **labels v2 conservan el texto actual** (sin el emoji), para que el operador reconozca cada
opción 1:1 con la nav de hoy.

### 6.3 Persistencia del colapso (CONGELADO)

- Clave `localStorage`: **`stacky.ui.shell.collapsed`** (convención `stacky.ui.*`, coherente con
  `stacky.ui.theme` del 138 §10.1 y `stacky.devops.selectedServer` de `DevOpsPage.tsx:175`).
- Valores: string `"true"` / `"false"`. `parseCollapsed(raw)` = `raw === "true"`
  (null/ausente ⇒ `false`, sidebar expandido por defecto).

---

## § 7. Fase F0 — Flag del arnés + lectura global (backend, TDD)

**Objetivo (1 frase):** registrar `STACKY_UI_SHELL_V2_ENABLED` (default OFF) en el arnés y
exponerla, aditivamente, por `GET /api/diag/health`, para que el frontend pueda leerla.

**Valor:** habilita el opt-in por UI (HarnessFlagsPanel) y da al frontend un único booleano para
decidir shell v1 vs v2, sin tocar ningún runtime.

### F0 · Pre-flight (obligatorio)
```
git status -- "Stacky Agents/backend/config.py" \
              "Stacky Agents/backend/services/harness_flags.py" \
              "Stacky Agents/backend/services/harness_flags_help.py" \
              "Stacky Agents/backend/api/diag.py"
```
Si alguno tiene cambios sin commitear ajenos a este plan → STOP.

### F0 · Test primero
Crear `backend/tests/test_plan139_shell_flag.py`:

```python
"""Plan 139 F0 — flag del shell v2 + lectura por /api/diag/health."""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import importlib

import pytest


def test_flag_registered_and_categorized():
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS, categorize
    keys = {s.key for s in FLAG_REGISTRY}
    assert "STACKY_UI_SHELL_V2_ENABLED" in keys
    assert "STACKY_UI_SHELL_V2_ENABLED" in _CATEGORY_KEYS["interfaz_ui"]
    assert categorize("STACKY_UI_SHELL_V2_ENABLED") == "interfaz_ui"


def test_flag_default_off_and_not_curated():
    from services.harness_flags import FLAG_REGISTRY, declared_default, default_is_known
    spec = next(s for s in FLAG_REGISTRY if s.key == "STACKY_UI_SHELL_V2_ENABLED")
    assert declared_default(spec) is False          # type-zero (sin default explícito)
    assert default_is_known(spec) is False           # NO curada


def test_plain_help_present():
    from services.harness_flags_help import PLAIN_HELP
    assert "STACKY_UI_SHELL_V2_ENABLED" in PLAIN_HELP


def test_config_default_off():
    import config
    importlib.reload(config)
    assert config.config.STACKY_UI_SHELL_V2_ENABLED is False


@pytest.fixture
def client():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_diag_health_exposes_shell_flag_default_off(client):
    r = client.get("/api/diag/health")
    assert r.status_code == 200
    assert r.get_json()["shell_v2_enabled"] is False


def test_diag_health_reflects_flag_on(client, monkeypatch):
    import config
    monkeypatch.setattr(config.config, "STACKY_UI_SHELL_V2_ENABLED", True, raising=False)
    r = client.get("/api/diag/health")
    assert r.get_json()["shell_v2_enabled"] is True
```

Correr (debe fallar por los símbolos aún inexistentes):
```
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./.venv/Scripts/python.exe -m pytest tests/test_plan139_shell_flag.py -q
```
(En PowerShell: `& .\.venv\Scripts\python.exe -m pytest tests/test_plan139_shell_flag.py -q`.)

### F0 · Implementación

**(a) `backend/config.py`** — agregar el atributo (mismo patrón exacto que
`STACKY_DB_COMPARE_ENABLED`, `config.py:103-105`). Ubicarlo cerca del bloque de flags UI/globales:

```python
    # ── Plan 139 — App Shell v2 (sidebar agrupada + TopBar + iconografía) ──────
    # Default OFF: opt-in del operador vía UI (categoría "interfaz_ui").
    # Con OFF la interfaz es byte-idéntica a la actual.
    STACKY_UI_SHELL_V2_ENABLED: bool = os.getenv(
        "STACKY_UI_SHELL_V2_ENABLED", "false"
    ).strip().lower() == "true"
```

**(b) `backend/services/harness_flags.py`** — tres ediciones:

(b1) En `FLAG_CATEGORIES` (tupla, `harness_flags.py:53-112`), agregar la categoría NUEVA
(antes de `CategorySpec("otros", …)`):
```python
    CategorySpec("interfaz_ui", "Interfaz",
        "Aspecto y disposición de la aplicación: estilo de navegación (fila de pestañas o barra lateral agrupada) y presentación general.",
        tier="simple", intent="Elegir el estilo de navegación y la presentación de la app"),
```

(b2) En `_CATEGORY_KEYS` (dict, `harness_flags.py:114-291`), agregar la entrada NUEVA
(antes de `"otros"`):
```python
    "interfaz_ui": (
        "STACKY_UI_SHELL_V2_ENABLED",  # Plan 139 — shell v2 (sidebar agrupada + TopBar + iconografía)
    ),
```

(b3) En `FLAG_REGISTRY` (lista de `FlagSpec`), agregar la spec (junto a las demás flags
`group="global"`, p.ej. cerca de `STACKY_DB_COMPARE_ENABLED`, `harness_flags.py:2733-2738`).
**Sin `default`** (⇒ OFF) y **sin `env_only`** (⇒ editable por UI):
```python
    FlagSpec(
        key="STACKY_UI_SHELL_V2_ENABLED",
        type="bool",
        label="Shell v2: navegación lateral agrupada",
        description=(
            "Plan 139 — Reemplaza la fila de pestañas superior por una barra lateral "
            "agrupada por temas (Trabajo, Observabilidad, Conocimiento, Plataforma, "
            "Configuración) con iconografía y una barra superior renovada. Default OFF: "
            "con OFF la interfaz es idéntica a la actual. Solo cambia la presentación; "
            "mismas pantallas y misma navegación."
        ),
        group="global",
    ),
```

**(c) `backend/services/harness_flags_help.py`** — agregar al dict `PLAIN_HELP` (respetando la
denylist de jerga de `tests/test_harness_flags_help.py:17-20` y el formato `on/off` empieza con
`"Si "`):
```python
    "STACKY_UI_SHELL_V2_ENABLED": PlainHelp(
        what="Muestra la navegación de la app como un menú lateral agrupado por temas, en vez de la fila de solapas de arriba.",
        on_effect="Si la activás: la navegación pasa a una barra lateral con secciones que podés plegar; son las mismas pantallas, ordenadas por tema.",
        off_effect="Si la apagás: la app usa la fila de solapas clásica de arriba, exactamente como venía.",
        example="Como pasar de una fila de solapas apretadas a un menú lateral tipo panel de control, con las opciones ordenadas por tema.",
    ),
```
Chequeo manual antes de correr: ninguna de las 4 frases contiene términos de la denylist
(`MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token(s), regex, backend,
frontend, gate, hook, runtime`), ni `SCREAMING_SNAKE`, ni `F<n>`. Largos: `what` ≤200,
`on_effect`/`off_effect` ≤240, `example` ≤300.

**(d) `backend/api/diag.py`** — en el `return jsonify({...})` de `health()` (`diag.py:353-367`),
agregar el campo aditivo justo después de `"local_llm_enabled": ...` (`diag.py:364`):
```python
        "shell_v2_enabled": bool(getattr(_config.config, "STACKY_UI_SHELL_V2_ENABLED", False)),  # Plan 139
```
(`_config` ya está importado, `diag.py:26`.)

### F0 · Validación
```
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./.venv/Scripts/python.exe -m pytest tests/test_plan139_shell_flag.py -q
./.venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q
./.venv/Scripts/python.exe -m pytest tests/test_harness_flags_help.py -q
```

### F0 · Criterio de aceptación BINARIO
- `pytest tests/test_plan139_shell_flag.py` → **todos verdes**.
- `pytest tests/test_harness_flags.py` → verde (incluye `test_default_known_only_for_curated`,
  `test_every_registry_flag_is_categorized`, `test_list_categories_ids_unique_and_include_otros`,
  `test_every_category_has_tier_and_intent`, `test_at_least_one_simple_and_one_advanced_category`).
- `pytest tests/test_harness_flags_help.py` → verde (cobertura 100% + denylist).

### F0 · Flag / runtime / operador
- **Flag:** crea `STACKY_UI_SHELL_V2_ENABLED` (OFF). Nada la consume aún.
- **Impacto runtime (3):** ninguno; campo pasivo. **Fallback:** con OFF, `shell_v2_enabled=false`.
- **Trabajo del operador:** ninguno (aparece la categoría "Interfaz" en el Arnés, sin acción
  requerida).

### F0 · Staging
```
git add -- "Stacky Agents/backend/config.py" \
           "Stacky Agents/backend/services/harness_flags.py" \
           "Stacky Agents/backend/services/harness_flags_help.py" \
           "Stacky Agents/backend/api/diag.py" \
           "Stacky Agents/backend/tests/test_plan139_shell_flag.py"
```

**Nota de despliegue (no bloqueante):** el generador `deployment/export_harness_defaults.py`
lee del `.env` del deploy, no de `config.py`; **NO regenerar** `harness_defaults.env` en este
plan (ver gotcha "drift harness_defaults.env"). La flag nace OFF; no requiere semilla.

---

## § 8. Fase F1 — Modelo de navegación puro (frontend, TDD)

**Objetivo:** definir, como datos puros y testeables, el agrupamiento, la meta por tab (label +
iconName), la visibilidad (gating) y la persistencia de colapso — sin React, sin CSS.

**Valor:** aísla toda la lógica del shell v2 en un módulo puro (cubierto por vitest sin RTL),
que el componente solo pinta. Cumple KPI-2 y KPI-4.

### F1 · Pre-flight
`git status -- "Stacky Agents/frontend/src/components/shell/"` (carpeta nueva; debe estar
ausente/limpia).

### F1 · Test primero
Crear `frontend/src/components/shell/__tests__/shellNav.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import {
  SHELL_NAV_GROUPS,
  TAB_META,
  computeVisibleTabs,
  orderedVisibleGroups,
  parseCollapsed,
  SIDEBAR_COLLAPSED_KEY,
} from "../shellNav";

const ALL_TABS = [
  "team", "tickets", "review", "unblocker", "pm", "logs", "settings",
  "docs", "memory", "diagnostics", "history", "migrador", "devops", "dbcompare",
] as const;

describe("shellNav — modelo de navegación", () => {
  it("TAB_META cubre exactamente los 14 tabs", () => {
    expect(Object.keys(TAB_META).sort()).toEqual([...ALL_TABS].sort());
  });

  it("cada tab aparece en exactamente un grupo (cobertura 14, sin duplicados)", () => {
    const flat = SHELL_NAV_GROUPS.flatMap((g) => g.tabs);
    expect(flat.slice().sort()).toEqual([...ALL_TABS].sort());
    expect(new Set(flat).size).toBe(flat.length);
  });

  it("orden de grupos congelado", () => {
    expect(SHELL_NAV_GROUPS.map((g) => g.id)).toEqual([
      "trabajo", "observabilidad", "conocimiento", "plataforma", "configuracion",
    ]);
  });

  it("todo tab tiene label no vacío e iconName", () => {
    for (const t of ALL_TABS) {
      expect(TAB_META[t].label.trim().length).toBeGreaterThan(0);
      expect(TAB_META[t].iconName.trim().length).toBeGreaterThan(0);
    }
  });

  it("computeVisibleTabs: los 7 base siempre visibles", () => {
    const v = computeVisibleTabs({
      sections: { pm: false, logs: false, docs: false, memory: false },
      migradorEnabled: false, devopsEnabled: false, dbCompareEnabled: false,
    });
    expect([...v].sort()).toEqual(
      ["diagnostics", "history", "review", "settings", "team", "tickets", "unblocker"].sort(),
    );
  });

  it("computeVisibleTabs: opcionales aparecen solo con su gate", () => {
    const v = computeVisibleTabs({
      sections: { pm: true, logs: true, docs: true, memory: true },
      migradorEnabled: true, devopsEnabled: true, dbCompareEnabled: true,
    });
    expect([...v].sort()).toEqual([...ALL_TABS].sort());
  });

  it("orderedVisibleGroups oculta grupos vacíos y filtra tabs ocultos", () => {
    const v = computeVisibleTabs({
      sections: { pm: false, logs: false, docs: false, memory: false },
      migradorEnabled: false, devopsEnabled: false, dbCompareEnabled: false,
    });
    const groups = orderedVisibleGroups(v);
    // conocimiento (docs/memory) y plataforma (devops/migrador/dbcompare) quedan vacíos
    expect(groups.map((g) => g.id)).toEqual(["trabajo", "observabilidad", "configuracion"]);
    const obs = groups.find((g) => g.id === "observabilidad")!;
    expect(obs.tabs.slice().sort()).toEqual(["diagnostics", "history"]);
  });

  it("parseCollapsed y clave de persistencia", () => {
    expect(SIDEBAR_COLLAPSED_KEY).toBe("stacky.ui.shell.collapsed");
    expect(parseCollapsed("true")).toBe(true);
    expect(parseCollapsed("false")).toBe(false);
    expect(parseCollapsed(null)).toBe(false);
    expect(parseCollapsed("garbage")).toBe(false);
  });
});
```

Correr (debe fallar: módulo inexistente):
```
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/components/shell/__tests__/shellNav.test.ts
```

### F1 · Implementación
Crear `frontend/src/components/shell/shellNav.ts`:

```ts
// Plan 139 — modelo de navegación del App Shell v2 (PURO: sin React, sin CSS).

// Debe coincidir 1:1 con `type Tab` de App.tsx. Si App.tsx agrega/quita un tab,
// actualizar aquí (el test shellNav.test.ts detecta el drift de cobertura).
export type ShellTab =
  | "team" | "tickets" | "review" | "unblocker" | "pm" | "logs"
  | "settings" | "docs" | "memory" | "diagnostics" | "history"
  | "migrador" | "devops" | "dbcompare";

export interface ShellTabMeta {
  label: string;
  iconName: string; // clave de ICON_BY_NAME (ver shellIcons.ts)
}

export const TAB_META: Record<ShellTab, ShellTabMeta> = {
  team:        { label: "Mi Equipo",     iconName: "Zap" },
  tickets:     { label: "Tickets ADO",   iconName: "ClipboardList" },
  review:      { label: "Revisión",      iconName: "Inbox" },
  unblocker:   { label: "Desatascador",  iconName: "Wrench" },
  pm:          { label: "PM",            iconName: "LayoutDashboard" },
  logs:        { label: "System Logs",   iconName: "ScrollText" },
  history:     { label: "Historial",     iconName: "History" },
  diagnostics: { label: "Diagnóstico",   iconName: "Stethoscope" },
  docs:        { label: "Docs",          iconName: "FileText" },
  memory:      { label: "Memoria",       iconName: "Brain" },
  devops:      { label: "DevOps",        iconName: "Server" },
  migrador:    { label: "Migrador",      iconName: "ArrowRightLeft" },
  dbcompare:   { label: "Comparador BD", iconName: "Database" },
  settings:    { label: "Configuración", iconName: "Settings" },
};

export interface ShellNavGroup {
  id: string;
  label: string;
  tabs: ShellTab[];
}

export const SHELL_NAV_GROUPS: ShellNavGroup[] = [
  { id: "trabajo",        label: "Trabajo",        tabs: ["team", "tickets", "review", "unblocker"] },
  { id: "observabilidad", label: "Observabilidad", tabs: ["pm", "logs", "history", "diagnostics"] },
  { id: "conocimiento",   label: "Conocimiento",   tabs: ["docs", "memory"] },
  { id: "plataforma",     label: "Plataforma",     tabs: ["devops", "migrador", "dbcompare"] },
  { id: "configuracion",  label: "Configuración",  tabs: ["settings"] },
];

export interface VisibilityInput {
  sections: { pm: boolean; logs: boolean; docs: boolean; memory: boolean };
  migradorEnabled: boolean;
  devopsEnabled: boolean;
  dbCompareEnabled: boolean;
}

// Tabs SIEMPRE visibles (espejo del render actual de App.tsx: no dependen de gate).
const ALWAYS_VISIBLE: ReadonlyArray<ShellTab> = [
  "team", "tickets", "review", "unblocker", "settings", "diagnostics", "history",
];

export function computeVisibleTabs(input: VisibilityInput): Set<ShellTab> {
  const v = new Set<ShellTab>(ALWAYS_VISIBLE);
  if (input.sections.pm) v.add("pm");
  if (input.sections.logs) v.add("logs");
  if (input.sections.docs) v.add("docs");
  if (input.sections.memory) v.add("memory");
  if (input.migradorEnabled) v.add("migrador");
  if (input.devopsEnabled) v.add("devops");
  if (input.dbCompareEnabled) v.add("dbcompare");
  return v;
}

export function orderedVisibleGroups(visible: ReadonlySet<ShellTab>): ShellNavGroup[] {
  return SHELL_NAV_GROUPS
    .map((g) => ({ ...g, tabs: g.tabs.filter((t) => visible.has(t)) }))
    .filter((g) => g.tabs.length > 0);
}

export const SIDEBAR_COLLAPSED_KEY = "stacky.ui.shell.collapsed";

export function parseCollapsed(raw: string | null): boolean {
  return raw === "true";
}
```

### F1 · Validación
```
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/components/shell/__tests__/shellNav.test.ts
npx tsc --noEmit
```

### F1 · Criterio BINARIO
- `vitest run …/shellNav.test.ts` → **todos verdes**.
- `npx tsc --noEmit` → **0 errores**.

### F1 · Flag / runtime / operador
- **Flag:** ninguna (módulo puro sin consumidores aún). **Runtime (3):** ninguno.
  **Operador:** ninguno.

### F1 · Staging
```
git add -- "Stacky Agents/frontend/src/components/shell/shellNav.ts" \
           "Stacky Agents/frontend/src/components/shell/__tests__/shellNav.test.ts"
```

---

## § 9. Fase F2 — Iconos + componente `AppSidebar` (frontend, TDD parcial)

**Objetivo:** mapear iconNames a componentes `lucide-react` (testeable) y construir el
componente `AppSidebar` que pinta el modelo puro, con colapso CSS-driven y responsive.

**Valor:** el sidebar renderizable. Cumple KPI-3 y KPI-5.

### F2 · Pre-flight
`git status -- "Stacky Agents/frontend/src/components/shell/"`.
Además, confirmar que las primitivas del 138 existen (dependencia de serie):
`git status` no debe faltar `frontend/src/components/ui/IconButton.tsx` ni
`frontend/src/components/ui/index.ts` (creados por el Plan 138 §10.2). Si faltan → 138 no
aterrizó → STOP (este plan requiere 138 implementado).

### F2 · Test primero (iconos)
Crear `frontend/src/components/shell/__tests__/shellIcons.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { ICON_BY_NAME } from "../shellIcons";
import { TAB_META } from "../shellNav";

describe("shellIcons — cobertura de iconografía", () => {
  it("todo iconName de TAB_META existe en ICON_BY_NAME", () => {
    for (const t of Object.keys(TAB_META) as (keyof typeof TAB_META)[]) {
      const name = TAB_META[t].iconName;
      expect(ICON_BY_NAME[name], `falta icono para ${name}`).toBeTruthy();
    }
  });

  it("cada entrada de ICON_BY_NAME es un componente (objeto o función)", () => {
    for (const name of Object.keys(ICON_BY_NAME)) {
      expect(["object", "function"]).toContain(typeof ICON_BY_NAME[name]);
    }
  });
});
```

Correr (debe fallar: `shellIcons` inexistente):
```
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/components/shell/__tests__/shellIcons.test.ts
```

### F2 · Implementación

**(a) `frontend/src/components/shell/shellIcons.ts`** (solo `lucide-react`, sin CSS/JSX — para
que el test lo importe sin tocar el DOM):
```ts
import type { LucideIcon } from "lucide-react";
import {
  Zap, ClipboardList, Inbox, Wrench, LayoutDashboard, ScrollText,
  History, Stethoscope, FileText, Brain, Server, ArrowRightLeft,
  Database, Settings,
} from "lucide-react";

export const ICON_BY_NAME: Record<string, LucideIcon> = {
  Zap, ClipboardList, Inbox, Wrench, LayoutDashboard, ScrollText,
  History, Stethoscope, FileText, Brain, Server, ArrowRightLeft,
  Database, Settings,
};
```

**(b) `frontend/src/components/shell/AppSidebar.tsx`** (consume `IconButton` del 138; **sin
`style={{`** — todo por CSS module):
```tsx
import type { ReactNode } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { IconButton } from "../ui";
import { ICON_BY_NAME } from "./shellIcons";
import {
  TAB_META, orderedVisibleGroups, type ShellTab,
} from "./shellNav";
import styles from "./AppSidebar.module.css";

export interface AppSidebarProps {
  activeTab: ShellTab;
  onSelect: (tab: ShellTab) => void;
  visibleTabs: ReadonlySet<ShellTab>;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  badges?: Partial<Record<ShellTab, ReactNode>>;
}

export default function AppSidebar({
  activeTab, onSelect, visibleTabs, collapsed, onToggleCollapsed, badges,
}: AppSidebarProps) {
  const groups = orderedVisibleGroups(visibleTabs);
  return (
    <aside
      className={`${styles.sidebar} ${collapsed ? styles.collapsed : ""}`}
      aria-label="Navegación principal"
    >
      <nav className={styles.groups}>
        {groups.map((g) => (
          <div key={g.id} className={styles.group}>
            <div className={styles.groupLabel}>{g.label}</div>
            {g.tabs.map((t) => {
              const meta = TAB_META[t];
              const Icon = ICON_BY_NAME[meta.iconName];
              const isActive = activeTab === t;
              const badge = badges?.[t];
              return (
                <button
                  key={t}
                  type="button"
                  className={`${styles.item} ${isActive ? styles.active : ""}`}
                  aria-current={isActive ? "page" : undefined}
                  title={meta.label}
                  onClick={() => onSelect(t)}
                >
                  <span className={styles.itemIcon} aria-hidden="true">
                    {Icon ? <Icon size={18} strokeWidth={2} /> : null}
                  </span>
                  <span className={styles.itemLabel}>{meta.label}</span>
                  {badge != null && <span className={styles.itemBadge}>{badge}</span>}
                </button>
              );
            })}
          </div>
        ))}
      </nav>
      <div className={styles.footer}>
        <IconButton
          label={collapsed ? "Expandir menú" : "Plegar menú"}
          icon={collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          size="sm"
          onClick={onToggleCollapsed}
        />
      </div>
    </aside>
  );
}
```
Notas de contrato:
- **Colapso CSS-driven:** los labels/groupLabels/badges SIEMPRE están en el DOM; el estado
  `collapsed` (y el media query) los ocultan por CSS. Así el responsive es puro CSS (sin lógica
  JS de ancho de ventana).
- `IconButton` viene de `../ui` (barrel `components/ui/index.ts`, 138 §10.2); `label` es
  OBLIGATORIO (aria-label + title) — cumplido.
- `ShellTab` y `Tab` (App) son uniones idénticas ⇒ mutuamente asignables (tsc ok).

**(c) `frontend/src/components/shell/AppSidebar.module.css`** (TOKEN-ONLY, **0 hex**):
```css
.sidebar {
  display: flex;
  flex-direction: column;
  width: 232px;
  flex-shrink: 0;
  background: var(--bg-panel);
  border-right: var(--border-width) solid var(--border);
  padding: var(--space-5) var(--space-3);
  gap: var(--space-5);
  overflow-y: auto;
  transition: width var(--duration-base) var(--ease-in-out);
}

.groups {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  flex: 1 1 auto;
}

.group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.groupLabel {
  font-size: var(--text-2xs);
  font-weight: var(--weight-semibold);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted);
  padding: 0 var(--space-3) var(--space-1);
}

.item {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  width: 100%;
  padding: var(--space-3);
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-muted);
  font-size: var(--text-sm);
  font-weight: var(--weight-medium);
  text-align: left;
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-standard),
    color var(--duration-fast) var(--ease-standard);
}

.item:hover {
  background: var(--status-neutral-bg);
  color: var(--text-primary);
}

.item.active {
  background: var(--status-info-bg);
  color: var(--accent);
  font-weight: var(--weight-semibold);
}

.item:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.itemIcon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

.itemLabel {
  flex: 1 1 auto;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.itemBadge {
  flex-shrink: 0;
  font-size: var(--text-2xs);
  font-weight: var(--weight-bold);
  color: var(--status-info-text);
}

.footer {
  display: flex;
  justify-content: flex-end;
  padding-top: var(--space-3);
  border-top: var(--border-width) solid var(--border);
}

/* ── Colapsado (estado explícito del operador) ── */
.collapsed {
  width: 60px;
  padding: var(--space-5) var(--space-2);
}
.collapsed .itemLabel,
.collapsed .groupLabel,
.collapsed .itemBadge {
  display: none;
}
.collapsed .item {
  justify-content: center;
  padding: var(--space-3) 0;
}
.collapsed .footer {
  justify-content: center;
}

/* ── Responsive: riel de iconos automático en pantallas angostas ── */
@media (max-width: 820px) {
  .sidebar {
    width: 60px;
    padding: var(--space-5) var(--space-2);
  }
  .itemLabel,
  .groupLabel,
  .itemBadge {
    display: none;
  }
  .item {
    justify-content: center;
    padding: var(--space-3) 0;
  }
  .footer {
    justify-content: center;
  }
}
```

### F2 · Validación
```
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx vitest run src/components/shell/__tests__/shellIcons.test.ts
npx tsc --noEmit
```
Chequeo de ratchet (anticipado; el ratchet lo corre el CI del 138):
```
grep -cE '#[0-9a-fA-F]{3,8}\b' "src/components/shell/AppSidebar.module.css"   # debe imprimir 0
grep -cF 'style={{' "src/components/shell/AppSidebar.tsx"                      # debe imprimir 0
```

### F2 · Criterio BINARIO
- `vitest run …/shellIcons.test.ts` → verde.
- `npx tsc --noEmit` → 0 errores.
- Los dos `grep -c` → **0** y **0**.

### F2 · Flag / runtime / operador
- **Flag:** ninguna (componente aún no montado). **Runtime (3):** ninguno. **Operador:** ninguno.

### F2 · Staging
```
git add -- "Stacky Agents/frontend/src/components/shell/shellIcons.ts" \
           "Stacky Agents/frontend/src/components/shell/AppSidebar.tsx" \
           "Stacky Agents/frontend/src/components/shell/AppSidebar.module.css" \
           "Stacky Agents/frontend/src/components/shell/__tests__/shellIcons.test.ts"
```

---

## § 10. Fase F3 — Integración en `App.tsx` (flag OFF byte-idéntico)

**Objetivo:** leer la flag y renderizar sidebar v2 cuando ON / `<nav>` v1 cuando OFF, sin cambiar
el montaje de páginas ni la navegación.

**Valor:** cierra el circuito. Cumple KPI-1 (OFF byte-idéntico) y contrato §3.7 (cero remount).

### F3 · Pre-flight (CRÍTICO — zona caliente)
```
git status -- "Stacky Agents/frontend/src/App.tsx" \
              "Stacky Agents/frontend/src/App.module.css" \
              "Stacky Agents/frontend/src/api/endpoints.ts"
```
Si hay WIP ajeno (134/135/136) sin commitear → STOP. Además, **grep de integración 134**:
```
grep -n "review" "Stacky Agents/frontend/src/App.tsx"
```
Localizar si el botón de nav `review` renderiza un badge (lo agrega el Plan 134). Anotar la
expresión exacta para espejarla en `badges` (ver paso (e)).

### F3 · Implementación (diff ilustrativo con casos borde)

**(a) Imports nuevos en `App.tsx`** (junto a los imports de componentes):
```tsx
import AppSidebar from "./components/shell/AppSidebar";
import {
  computeVisibleTabs, parseCollapsed, SIDEBAR_COLLAPSED_KEY,
} from "./components/shell/shellNav";
```

**(b) `endpoints.ts` (aditivo, opcional pero recomendado):** extender el tipo de retorno de
`Health.get` (`endpoints.ts:2601-2603`) para que el campo sea conocido por TS:
```tsx
export const Health = {
  get: (): Promise<{ version?: string; ok?: boolean; healthy?: boolean; shell_v2_enabled?: boolean }> =>
    api.get<{ version?: string; ok?: boolean; healthy?: boolean; shell_v2_enabled?: boolean }>("/api/diag/health"),
};
```

**(c) Estado nuevo en `App()`** (junto a `dbCompareEnabled`, `App.tsx:66`):
```tsx
const [shellV2Enabled, setShellV2Enabled] = useState(false);
const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(
  () => parseCollapsed(localStorage.getItem(SIDEBAR_COLLAPSED_KEY)),
);
const toggleSidebar = () => {
  setSidebarCollapsed((c) => {
    const next = !c;
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? "true" : "false");
    return next;
  });
};
```

**(d) Lectura de la flag** en el `useEffect` de montaje (`App.tsx:86-104`), agregar un fetch más
(mismo patrón que los 3 existentes):
```tsx
fetch("/api/diag/health")
  .then((r) => r.json())
  .then((d: { shell_v2_enabled?: boolean }) => setShellV2Enabled(d.shell_v2_enabled === true))
  .catch(() => setShellV2Enabled(false));
```

**(e) Cálculo de visibles + badges** (antes del `return`, después de los `useEffect`):
```tsx
const visibleTabs = computeVisibleTabs({
  sections: {
    pm: !!sections.pm, logs: !!sections.logs,
    docs: !!sections.docs, memory: !!sections.memory,
  },
  migradorEnabled, devopsEnabled, dbCompareEnabled,
});

// [Contrato §3.2 — Plan 134] Espejar el/los badge(s) de la nav v1 aquí.
// Si el pre-flight encontró un badge en el botón "review", copiar esa MISMA
// expresión como `review: <expr>`. Si 134 no aterrizó, dejar el objeto vacío.
const shellBadges: Partial<Record<Tab, React.ReactNode>> = {
  // review: <expresión de badge del Plan 134>,
};
```

**(f) Extraer el bloque de páginas** — CUT de `App.tsx:259-272` a un `const` (condicionales
EXACTAMENTE iguales), declarado antes del `return`:
```tsx
const pages = (
  <>
    {tab === "team"        && <TeamScreen />}
    {tab === "tickets"     && <TicketBoard />}
    {tab === "review"      && <ReviewInboxPage />}
    {tab === "unblocker"   && <UnblockerPage />}
    {tab === "pm"          && sections.pm     && <PMCommandCenter />}
    {tab === "logs"        && sections.logs   && <SystemLogsPage />}
    {tab === "settings"    && <SettingsPage />}
    {tab === "docs"        && sections.docs   && <DocsPage />}
    {tab === "memory"      && sections.memory && <MemoryPage />}
    {tab === "diagnostics" && <DiagnosticsPage />}
    {tab === "history"     && <ExecutionHistoryPage />}
    {tab === "migrador"    && migradorEnabled && <MigratorPage />}   {/* Plan 74 */}
    {tab === "devops"      && devopsEnabled   && <DevOpsPage />}      {/* Plan 87 */}
    {tab === "dbcompare"   && dbCompareEnabled && <DbComparePage />}  {/* Plan 122 */}
  </>
);
```

**(g) Render condicional** — reemplazar, dentro del `return`, el bloque `<nav>…</nav>` +
las 14 líneas de páginas por:
```tsx
<TopBar onGoToTeam={() => selectTab("team")} shellV2={shellV2Enabled} />
<HealthBanner />

{shellV2Enabled ? (
  <div className={styles.shellLayout}>
    <AppSidebar
      activeTab={tab}
      onSelect={selectTab}
      visibleTabs={visibleTabs}
      collapsed={sidebarCollapsed}
      onToggleCollapsed={toggleSidebar}
      badges={shellBadges}
    />
    <main className={styles.shellContent}>{pages}</main>
  </div>
) : (
  <>
    <nav className={styles.nav}>
      {/* ⚠️ DEJAR VERBATIM los 14 botones actuales (App.tsx:158-257).
          NO tocar este bloque: garantiza la byte-identidad con la flag OFF. */}
    </nav>
    {pages}
  </>
)}
```
**Casos borde:**
- Flag OFF: `styles.appRoot` sin clase extra; se renderiza `<nav>` (verbatim) + `{pages}`
  (fragment transparente) ⇒ DOM idéntico a hoy. TopBar recibe `shellV2={false}` ⇒ sin `.barV2`
  (F4) ⇒ TopBar idéntica.
- Flag ON pero `visibleTabs` sin opcionales: `orderedVisibleGroups` oculta grupos vacíos; el
  sidebar nunca queda con un grupo vacío ni con un item de un tab oculto.
- `tab` activo se oculta (p.ej. `sections.pm` pasa a false): el efecto de fallback
  (`App.tsx:141-149`) sigue vigente (no se toca) y lleva a "team"; el sidebar deja de mostrar ese
  item. Sin pantalla en blanco.

**(h) `App.module.css`** — AGREGAR (token-only, **0 hex**; NO tocar `.nav`/`.navTab`):
```css
.shellLayout {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
}

.shellContent {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
}
```

### F3 · Validación
```
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx tsc --noEmit
npx vitest run src/components/shell/__tests__/shellNav.test.ts src/components/shell/__tests__/shellIcons.test.ts
grep -cE '#[0-9a-fA-F]{3,8}\b' "src/App.module.css"   # NO debe aumentar vs baseline (sigue 2)
grep -cF 'style={{' "src/App.tsx"                      # NO debe aumentar vs baseline
```
Más el **smoke manual §12 caso OFF y caso ON** (obligatorio: no hay RTL/jsdom para probar el
render — ver gotcha "RTL/jsdom estructural").

### F3 · Criterio BINARIO
- `npx tsc --noEmit` → 0 errores.
- Los dos vitest puros → verdes.
- `grep -c` de hex en `App.module.css` → **igual** al baseline (no aumenta; sigue 2).
- Smoke §12 caso OFF: la UI es indistinguible de la actual (misma fila de tabs, misma TopBar).
- Smoke §12 caso ON: aparece el sidebar agrupado, navegación funciona, Ctrl+K y Ctrl+/ funcionan.

### F3 · Flag / runtime / operador
- **Flag:** `STACKY_UI_SHELL_V2_ENABLED` ahora tiene consumidor (frontend). **Runtime (3):**
  ninguno (solo cambia el chrome). **Fallback:** OFF ⇒ UI actual. **Operador:** ninguno hasta
  que decida activarla.

### F3 · Staging
```
git add -- "Stacky Agents/frontend/src/App.tsx" \
           "Stacky Agents/frontend/src/App.module.css" \
           "Stacky Agents/frontend/src/api/endpoints.ts"
```

---

## § 11. Fase F4 — TopBar profesional (gateada por flag, token-based)

**Objetivo:** al activar el shell v2, re-estilar la TopBar con los tokens del 138
(spacing/tipografía/sombra), sin alterar su funcionalidad y sin romper la byte-identidad OFF.

**Valor:** coherencia visual del chrome v2 con el sistema de diseño; "TopBar profesional".

### F4 · Pre-flight (zona caliente)
```
git status -- "Stacky Agents/frontend/src/components/TopBar.tsx" \
              "Stacky Agents/frontend/src/components/TopBar.module.css"
```
WIP ajeno → STOP.

### F4 · Implementación

**(a) `TopBar.tsx`** — prop aditiva (backward-compat; default falsy):
```tsx
interface TopBarProps {
  onGoToTeam?: () => void;
  shellV2?: boolean;   // Plan 139 — aplica el re-estilo v2 (aditivo)
}

export default function TopBar({ onGoToTeam, shellV2 }: TopBarProps) {
  // ...
  return (
    <header className={`${styles.bar} ${shellV2 ? styles.barV2 : ""}`}>
      {/* ...contenido idéntico... */}
    </header>
  );
}
```
No se toca ninguna otra parte del componente (el badge "Agente trabajando…" de 134, el selector
de proyecto, la versión, etc. quedan igual). Con `shellV2` falsy ⇒ sin `.barV2` ⇒ idéntico.

**(b) `TopBar.module.css`** — AGREGAR al final (token-only, **0 hex nuevos**; NO tocar reglas
existentes):
```css
/* Plan 139 — re-estilo profesional del shell v2 (aditivo; solo con flag ON). */
.barV2 {
  box-shadow: var(--shadow-1);
  border-bottom-color: var(--border);
}
.barV2 .main {
  gap: var(--space-7);
  padding: var(--space-4) var(--space-6);
}
.barV2 .brand {
  gap: var(--space-4);
  font-size: var(--text-md);
  font-weight: var(--weight-semibold);
}
.barV2 .actions {
  gap: var(--space-5);
}
.barV2 .version {
  font-size: var(--text-xs);
}
```

### F4 · Validación
```
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"
npx tsc --noEmit
grep -cE '#[0-9a-fA-F]{3,8}\b' "src/components/TopBar.module.css"   # NO aumenta vs baseline
```
+ smoke §12 (comparar TopBar OFF vs ON).

### F4 · Criterio BINARIO
- `npx tsc --noEmit` → 0 errores.
- `grep -c` hex de `TopBar.module.css` → **igual** al baseline (no aumenta).
- Smoke: con OFF la TopBar es idéntica a hoy; con ON tiene spacing/tipografía/sombra del 138 y
  **toda** la funcionalidad intacta (selector de proyecto, badge de ejecución, versión).

### F4 · Flag / runtime / operador
- **Flag:** el re-estilo se activa solo con `shellV2` (⇐ `STACKY_UI_SHELL_V2_ENABLED`).
  **Runtime (3):** ninguno. **Fallback:** OFF ⇒ TopBar actual. **Operador:** ninguno.

### F4 · Staging
```
git add -- "Stacky Agents/frontend/src/components/TopBar.tsx" \
           "Stacky Agents/frontend/src/components/TopBar.module.css"
```

---

## § 12. Smoke manual final (obligatorio — no hay RTL/jsdom)

Levantar el frontend contra un backend local. Ejecutar **ambos** casos.

### Preparación
1. Backend arriba. Confirmar el health:
   `curl -s http://localhost:<puerto>/api/diag/health` → el JSON incluye `"shell_v2_enabled"`.
   **Esperado:** `false` (flag OFF por default).

### Caso OFF (byte-identidad — KPI-1)
2. Abrir la app en el navegador. **Esperado:** fila de 14 pestañas arriba, con emojis, patrón
   underline; TopBar como hoy.
3. Navegar por varias pestañas (Mi Equipo, Tickets, Revisión, Diagnóstico). **Esperado:** cada
   una monta su página igual que hoy; la URL cambia (`/tickets`, `/review`, …).
4. Ctrl+K → escribir "Diagn" → Enter. **Esperado:** navega a Diagnóstico (paleta intacta).
5. Ctrl+/ → **Esperado:** alterna entre Mi Equipo y Tickets (atajo intacto).
6. Lanzar un run (si hay proyecto). **Esperado:** el badge "Agente trabajando…" aparece en la
   TopBar (contrato 134 intacto).

### Activación
7. Ir a Configuración → Arnés → categoría **Interfaz** → activar
   `STACKY_UI_SHELL_V2_ENABLED` (1 click). Recargar la página (F5).
   Alternativa sin UI: setear `STACKY_UI_SHELL_V2_ENABLED=true` en el `.env` del deploy y
   reiniciar backend.
8. `curl -s .../api/diag/health` → **Esperado:** `"shell_v2_enabled": true`.

### Caso ON (shell v2 — KPI-2/3/4/5)
9. Recargar. **Esperado:** desaparece la fila superior de tabs; aparece un **sidebar a la
   izquierda** con 5 grupos en orden: Trabajo, Observabilidad, Conocimiento, Plataforma,
   Configuración, cada uno con sus items e **iconos lucide** (no emojis). TopBar re-estilada
   (spacing/sombra del 138).
10. Verificar el agrupamiento: Trabajo = Mi Equipo/Tickets ADO/Revisión/Desatascador;
    Configuración = Configuración (al fondo). **Esperado:** coincide con §6.1.
11. Click en cada item. **Esperado:** navega a la misma página que en v1; la URL cambia igual;
    el item activo queda resaltado (`aria-current="page"`).
12. Ctrl+K y Ctrl+/ de nuevo. **Esperado:** funcionan idénticos (contratos §3.4/§3.5).
13. Plegar el sidebar con el botón inferior (icono panel). **Esperado:** queda un **riel de
    iconos** (labels ocultos, tooltips por `title`). Recargar. **Esperado:** sigue plegado
    (persistencia `stacky.ui.shell.collapsed`).
14. Achicar la ventana < 820px de ancho. **Esperado:** el sidebar pasa a riel de iconos
    automáticamente (responsive), sin romper el layout ni scroll horizontal del body.
15. Gating: si DevOps/Migrador/Comparador BD están OFF, **Esperado:** el grupo Plataforma no los
    muestra (o desaparece si queda vacío). Si PM/logs/docs/memory están ocultos por `sections.*`,
    **Esperado:** no aparecen en sus grupos (contrato §3.3).
16. Volver a apagar la flag y recargar. **Esperado:** vuelve exactamente a la fila de tabs de
    hoy (reversibilidad total).

---

## § 13. Orden de implementación (numerado)

1. **F0** — flag backend + campo aditivo en `/api/diag/health` (tests backend verdes).
2. **F1** — `shellNav.ts` + test puro (vitest + tsc verdes).
3. **F2** — `shellIcons.ts` + `AppSidebar.tsx` + `.module.css` + test de iconos (verde, 0 hex).
4. **F3** — integración en `App.tsx` (+ `App.module.css`, `endpoints.ts`); smoke OFF + ON.
5. **F4** — TopBar profesional gateada; smoke comparativo TopBar.
6. Smoke manual §12 completo (OFF y ON).

Cada fase: pre-flight → test-first (donde aplica) → implementar → validar → criterio binario →
staging quirúrgico. **No** avanzar a la siguiente fase con la anterior en rojo.

---

## § 14. Definition of Done (global)

- [ ] `pytest tests/test_plan139_shell_flag.py` verde; `tests/test_harness_flags.py` y
      `tests/test_harness_flags_help.py` verdes (sin regresión).
- [ ] `vitest run` de `shellNav.test.ts` y `shellIcons.test.ts` verdes.
- [ ] `npx tsc --noEmit` → 0 errores.
- [ ] `git status -- "Stacky Agents/frontend/package.json"` **limpio** (cero dependencias nuevas).
- [ ] `grep -cE '#[0-9a-fA-F]{3,8}\b'` = **0** en `AppSidebar.module.css`; sin aumento en
      `App.module.css` y `TopBar.module.css` vs su baseline.
- [ ] `grep -cF 'style={{'` = **0** en `AppSidebar.tsx`; sin aumento en `App.tsx`.
- [ ] Smoke §12: caso OFF byte-idéntico; caso ON con sidebar agrupado, iconos, colapso
      persistente, responsive y gating correcto; reversibilidad total.
- [ ] `git status` no muestra archivos fuera de los listados en §5.
- [ ] Contratos §3.2–§3.7 verificados (badges espejados, gating, URL, paleta, DevOps interno,
      cero remount).

---

## § 15. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | 134/135/136 aún no aterrizaron y sus ediciones colisionan con `App.tsx`/`TopBar.tsx`. | Pre-flight por archivo en cada fase; anclas por texto; STOP ante WIP ajeno; staging quirúrgico. |
| R2 | La byte-identidad OFF se rompe por un cambio inadvertido en `<nav>`/TopBar. | La `<nav>` v1 se deja VERBATIM; TopBar v2 es una clase aditiva gateada; smoke §12 caso OFF obligatorio. |
| R3 | `ShellTab` y `Tab` (App) divergen al agregarse un tab futuro. | `shellNav.test.ts` falla si `TAB_META`/grupos no cubren los 14; comentario de sincronización en ambos archivos. |
| R4 | Alguna página asumía ser hija directa de `.appRoot` (flex column) y se ve distinta dentro de `.shellContent`. | `.shellContent` replica `display:flex; flex-direction:column; overflow:auto`; smoke §12 recorre las páginas con flag ON. |
| R5 | Ratchet del 138 marca deuda por hex/inline en archivos nuevos. | Archivos shell 100% token-only / CSS module; `grep -c` = 0 en el criterio de F2/F3/F4. |
| R6 | Badge de Revisión (134) no se refleja en el sidebar. | Contrato §3.2 + pre-flight grep en F3 para espejar la expresión; ranura `.itemBadge` lista. |
| R7 | Doble fetch a `/api/diag/health` (TopBar + App) agrega latencia. | Es un GET liviano ya usado; 1 request extra en montaje, sin impacto perceptible; se puede memoizar en una serie futura (fuera de scope). |
| R8 | El icono elegido no representa bien al tab (p.ej. `Inbox` para Revisión). | Tabla §6.2 congelada y revisable; cambiar un `iconName` es 1 línea en `TAB_META` (más su icono en `shellIcons.ts`), cubierto por el test de cobertura. |

---

## § 16. Fuera de scope (explícito)

- **NO** se cambia `type Tab`, `TAB_PATHS`, `tabFromPath`, `selectTab`, `navigateTo` ni el
  montaje de páginas.
- **NO** se implementa la lógica de badges (es del Plan 134); solo la ranura del sidebar.
- **NO** se toca `CommandPalette` (Plan 129) ni el atajo Ctrl+/ (Plan 136).
- **NO** se toca el shell INTERNO de DevOps (Plan 119).
- **NO** se agrega selector de tema (es del Plan 141) ni se migran los tokens legacy.
- **NO** se agregan dependencias ni se toca `package.json`.
- **NO** se migran a token los hex preexistentes de `App.module.css`/`TopBar.module.css` que sean
  compartidos v1+v2 (romperían la byte-identidad OFF).
- **NO** se regenera `harness_defaults.env`.

---

## § 17. Glosario

- **Shell / chrome:** el marco de navegación global de la app (barra superior + navegación),
  distinto del contenido de cada página.
- **Sidebar:** barra lateral de navegación (v2), reemplaza la fila de pestañas (v1).
- **Tab (`ShellTab`):** una de las 14 secciones navegables (team, tickets, …). 1:1 con `type Tab`
  de `App.tsx`.
- **Grupo:** conjunto nombrado de tabs en el sidebar (Trabajo / Observabilidad / Conocimiento /
  Plataforma / Configuración).
- **Gating / visibilidad:** reglas que ocultan tabs opcionales (`sections.*` para pm/logs/docs/
  memory; `*Enabled` para migrador/devops/dbcompare).
- **Byte-idéntico (OFF):** con la flag apagada, el DOM y el estilo renderizados son iguales a la
  versión actual.
- **Ratchet (138 §10.3):** test que impide que aumente la deuda de estilo (hex en `.module.css`,
  `style={{` en `.tsx`); `components/**/ui` y `components/shell/**` deben mantenerse en 0.
- **Primitiva:** componente base del sistema de diseño 138 (`IconButton`, `Tabs`, …), consumido
  por su firma exacta.

---

**Fin del Plan 139 (v1 PROPUESTO).** Próximo paso sugerido: `criticar-y-mejorar-plan 139`.
