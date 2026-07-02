# Plan 86 — Flags para mortales: ayuda en lenguaje llano, contraste ON/OFF y navegación por secciones

**Versión:** v2 (propuesto, 2026-07-02) — crítica adversarial v1→v2 aplicada (veredicto v1: RECHAZADO por C1)
**Estado:** PROPUESTO — no implementado
**Origen:** pedido textual del operador: *"Que cambie la forma de activar o desactivar flags: que sea mucho más estético y con mejores contrastes de colores alineados a la herramienta, que estén más sectorizados y, por sobre todo, que sean fáciles de entender sobre todo para personas que no entienden nada de IA (podrían tener cada uno un signito de exclamación que te dé una explicación de para qué sirve, con ejemplos claros para un mortal), y cualquier otra mejora que facilite el uso de esta configuración."*
**Dependencias:** ninguna dura. CONMUTATIVO con los planes propuestos 82 (requires/origen), 83 (bounds), 84 (restart_required) y 85 (reserved): este plan **NO agrega campos a `FlagSpec`** ni toca el hero — el contenido nuevo vive en un módulo aparte y la UI nueva ocupa espacio propio (ver sección 3.7). Complementa (no duplica) los rediseños ya implementados 62/63 (categorías colapsables + búsqueda) y 78 (hero + color/icono + Simple/Experto).

**Changelog v1 → v2 (crítica adversarial, todo verificado contra código):**
- **C1 (BLOQUEANTE, resuelto):** posición EXACTA del estado `showHelp` en `FlagRow` — debe declararse ANTES del early-return `if (isManagedAsPair) return null;` (HarnessFlagsPanel.tsx:71); después viola la regla de hooks de React, crashea el panel en runtime y `tsc` NO lo detecta (falso verde).
- **C2:** criterio F0 corregido — `test_no_runtime_imports_plain_help` PASA verde ya en F0 (módulo inexistente ⇒ 0 offenders); resultado esperado exacto: `6 failed, 1 passed`.
- **C3:** el centinela poda `.venv/__pycache__/node_modules/data/dist/build` (`backend\.venv` EXISTE; sin poda rglob lee miles de archivos del venv en cada corrida del ratchet).
- **C4:** conteo real: **158 flags** (104 bool / 25 int / 22 csv / 4 float / 2 str / 1 json), no ~139. Corregido en evidencia, riesgos, glosario y DoD.
- **C5:** eliminado el hedge vago de F2 — `read_current()` importa `config` LAZY (harness_flags.py:1934) y `test_harness_flags.py:523-529` ya lo llama sin mock: el test corre tal cual.
- **C6:** instrucción de `matches()` corregida — ya tiene cuerpo `{...}` con 3 `return` (tsx:246-254); se INSERTA antes del `return (` final, no se reescribe.
- **C9:** las flags pair (`*_PROJECTS`) no renderizan `FlagRow` propio (`isManagedAsPair`, tsx:70-71) → su ayuda llana era INALCANZABLE; F3 ahora agrega ⓘ + bloque también en el `pairRow`.
- **C7:** anclas actualizadas (`read_current()`:1932, dict :1952-1965). **C8:** `onToggle` libera `focusCat` al cerrar la sección a mano. **C10:** denylist con plural opcional (`s?`): "tokens" ya no se escapa. **C11:** removido `import pytest` muerto. **C12:** claim honesto — la denylist garantiza 0 apariciones de SUS términos, no "0 jerga" absoluta.
- **C13 [ADICIÓN ARQUITECTO]:** búsqueda insensible a acentos (deaccent NFD) — "notificacion" encuentra "notificación"; clave para el objetivo "mortales".

---

## 1. Objetivo e impacto

**Objetivo.** Que una persona SIN conocimiento de IA pueda abrir el panel del arnés y entender, flag por flag, **qué hace, qué pasa si la prende, qué pasa si la apaga y un ejemplo concreto** — vía un botón de ayuda (ⓘ) por flag con texto en lenguaje llano servido por la API (nunca hardcodeado en el frontend) — y que el estado ON/OFF de cada perilla sea inconfundible a simple vista (contraste accesible + etiqueta textual), con navegación rápida entre secciones.

**Evidencia del gap (verificada 2026-07-02):**
- `FlagSpec.description` (`Stacky Agents/backend/services/harness_flags.py:23`) es técnica y críptica para un no-experto: *"F1.1 — Si ON, outputs con errores duros degradan el run a needs_review."* (línea 219). Referencias a fases de planes ("F1.1"), jerga ("outputs", "run", "needs_review").
- El toggle ON usa `--color-primary` azul (`HarnessFlagsPanel.module.css:310-311`) — mismo color que botones/acentos del tema: ON no se distingue de "elemento acentuado". OFF es gris sin borde ni etiqueta. No hay texto "Activada/Desactivada"; el estado se comunica SOLO por color (falla de accesibilidad y de claridad para mortales).
- No existe ningún afordance de ayuda por flag: solo el `description` técnico inline (`HarnessFlagsPanel.tsx:169`).
- Con **158 flags** en 16 categorías (conteo verificado 2026-07-02 con el venv: 104 bool / 25 int / 22 csv / 4 float / 2 str / 1 json), ir de una sección a otra exige scroll ciego; no hay índice de navegación.
- La búsqueda (`HarnessFlagsPanel.tsx:246-254`) matchea solo `label/description/key` técnicos: un mortal que busca "costo" o "avisos" no encuentra nada si la description no usa esa palabra.

**KPI/impacto:**
- 100% de las flags del registry (158) con ayuda en lenguaje llano (cobertura garantizada por test centinela; 0 apariciones de los términos de la denylist de jerga — garantía mecánica sobre la denylist, que es finita: no es un detector semántico universal).
- Estado ON/OFF distinguible sin depender del color (etiqueta textual "Activada/Desactivada" + contraste AA + foco visible).
- Navegación a cualquier categoría en 1 click (chips índice).
- Búsqueda encuentra flags por palabras "de mortal" (busca también en la ayuda llana).
- Impacto en los 3 runtimes: **NULO**, probado por centinela mecánico (F0, `test_no_runtime_imports_plain_help`).

---

## 2. Por qué ahora / gap que cierra

- Los planes 62/63 dieron estructura (categorías, búsqueda, badge `def:`); el 78 dio identidad visual (hero, color/icono, Simple/Experto). Los propuestos 82/83/84/85 dan **honestidad de estado** (origen, rango, vigencia, cableado). Ninguno atacó la dimensión **comprensión**: todos muestran la `description` técnica tal cual. Este plan cierra esa 5ª dimensión: "¿QUÉ significa esta perilla para un humano normal?".
- El pedido es textual del operador (2026-07-02) — no es una hipótesis de valor.
- Costo acotado: un módulo declarativo de contenido + serialización aditiva + 3 mejoras de presentación. Cero cambio de comportamiento del sistema.

---

## 3. Principios y guardarraíles (no negociables)

1. **Cero trabajo extra al operador.** Todo aparece solo: el botón de ayuda, las etiquetas ON/OFF y los chips llegan con el deploy. Ninguna config nueva que setear.
2. **3 runtimes con paridad (Codex CLI, Claude Code CLI, GitHub Copilot Pro).** Este plan NO toca ningún runner ni camino de ejecución: los cambios viven en un módulo declarativo puro, el serializador del panel y React/CSS. Impacto por runtime: nulo e idéntico en los tres; no requiere fallback. Lo prueba el centinela `test_no_runtime_imports_plain_help` (F0).
3. **Human-in-the-loop.** Solo se agrega información y presentación; ninguna perilla cambia de comportamiento ni se deshabilita.
4. **Mono-operador, sin auth.** Sin cambios de superficie de seguridad.
5. **Backward-compatible.** El JSON del GET solo AGREGA la clave `plain_help` (los clientes viejos ignoran claves desconocidas); el campo TS es opcional (`plain_help?`) para tolerar backends viejos; si falta la ayuda de una flag, la UI muestra un **fallback honesto** ("Explicación simple pendiente" + description técnica), nunca texto inventado en el frontend.
6. **Sin flags nuevas.** Justificación explícita (regla "default OFF salvo justificación"): esto es contenido estático + presentación; el afordance de ayuda es opt-in por click del usuario; agregar una flag para mostrar ayuda sería fricción sin valor (mismo criterio que los planes 62/63/78, que tampoco usaron flag). Corolario: **cero riesgo con `_CURATED_DEFAULTS_ON`** — no se crea ninguna `FlagSpec`, no se pasa `default=` en ningún lado (`test_default_known_only_for_curated` intacto).
7. **Conmutatividad con 82/83/84/85 (regla de oro de este plan):**
   - **NO se agregan campos a `FlagSpec`** (82/83/84/85 ya agregan `requires`, `min_value/max_value`, `restart_required`, `reserved`): el contenido llano vive en `services/harness_flags_help.py` (módulo NUEVO) keyed por `spec.key`. En `harness_flags.py` este plan solo agrega 1 import + 1 línea en `read_current()`.
   - **NO se toca el hero** (`styles.hero`) — 82 F3/F4, 83 F3 y 84 F3 le agregan contadores/chips. Los chips de navegación de este plan van en un contenedor NUEVO propio (`styles.catNav`) debajo del toggle Simple/Experto.
   - En `FlagRow`, los badges de 82/83/84/85 se anclan junto a `defaultBadge` (línea ~166); el botón de ayuda de este plan se ancla junto a `flagName` (línea ~164) y el bloque de ayuda va DESPUÉS de `flagDesc` (línea ~169) — líneas distintas, sin solape semántico.
   - El orden de implementación entre 82/83/84/85/86 es libre: cualquier subset puede implementarse antes o después.
8. **Texto llano NUNCA hardcodeado en el frontend.** Toda la redacción vive en el backend declarativo y viaja por la API existente (`GET /api/harness-flags`). El frontend solo pinta.

---

## 4. Fases

### F0 — Tests centinela del módulo de ayuda (TDD: rojo primero)

**Objetivo (1 frase):** congelar por test el contrato del contenido llano (cobertura 100%, sin huérfanas, formato, sin jerga, pureza del módulo, impacto nulo en runtimes) ANTES de escribir el contenido.

**Archivo a crear:** `Stacky Agents/backend/tests/test_harness_flags_help.py`

**Contenido exacto (pseudocódigo estricto — copiar tal cual, completando solo imports triviales):**

```python
"""Plan 86 — Centinelas del contenido de ayuda en lenguaje llano.

Contrato: services/harness_flags_help.py es un módulo PURO (sin flask/config/IO)
con PLAIN_HELP cubriendo el 100% de FLAG_REGISTRY, sin keys huérfanas, con
formato fijo (on/off empiezan con "Si "), sin jerga de IA (denylist congelada)
y que NINGÚN módulo de runtime importa.
"""
import re
from pathlib import Path

from services.harness_flags import FLAG_REGISTRY

BACKEND_ROOT = Path(__file__).resolve().parent.parent  # .../backend

# Denylist CONGELADA de jerga prohibida en la ayuda llana (case-insensitive,
# por palabra completa). Cambiarla es decisión consciente con code review.
JARGON_DENYLIST = (
    "MCP", "TF-IDF", "LLM", "stdin", "stdout", "endpoint", "frontmatter",
    "prompt", "token", "regex", "backend", "frontend", "gate", "hook", "runtime",
)
# Prohibido citar keys tipo SCREAMING_SNAKE y referencias a fases de planes ("F1.1").
_KEY_RE = re.compile(r"\b[A-Z]+_[A-Z0-9_]+\b")
_PHASE_RE = re.compile(r"\bF\d")

REGISTRY_KEYS = {spec.key for spec in FLAG_REGISTRY}


def _all_fields(entry) -> list[str]:
    return [entry.what, entry.on_effect, entry.off_effect, entry.example]


def test_plain_help_covers_all_registry_keys():
    from services.harness_flags_help import PLAIN_HELP
    missing = sorted(REGISTRY_KEYS - set(PLAIN_HELP))
    assert missing == [], f"Flags sin ayuda llana: {missing}"


def test_plain_help_has_no_orphan_keys():
    from services.harness_flags_help import PLAIN_HELP
    orphans = sorted(set(PLAIN_HELP) - REGISTRY_KEYS)
    assert orphans == [], f"Ayuda para flags inexistentes: {orphans}"


def test_plain_help_fields_non_empty_and_bounded():
    from services.harness_flags_help import PLAIN_HELP
    for key, entry in PLAIN_HELP.items():
        assert len(entry.what.strip()) >= 10, f"{key}: what demasiado corto"
        assert len(entry.what) <= 200, f"{key}: what > 200 chars"
        assert len(entry.on_effect) <= 240, f"{key}: on_effect > 240 chars"
        assert len(entry.off_effect) <= 240, f"{key}: off_effect > 240 chars"
        assert len(entry.example) <= 300, f"{key}: example > 300 chars"
        for field in _all_fields(entry):
            assert field.strip(), f"{key}: campo vacío"


def test_plain_help_on_off_start_with_si():
    from services.harness_flags_help import PLAIN_HELP
    for key, entry in PLAIN_HELP.items():
        assert entry.on_effect.startswith("Si "), f"{key}: on_effect no empieza con 'Si '"
        assert entry.off_effect.startswith("Si "), f"{key}: off_effect no empieza con 'Si '"


def test_plain_help_avoids_jargon_denylist():
    from services.harness_flags_help import PLAIN_HELP
    violations = []
    for key, entry in PLAIN_HELP.items():
        for field in _all_fields(entry):
            for term in JARGON_DENYLIST:
                # v2/C10 — plural opcional: "token" y "tokens" caen igual.
                if re.search(rf"\b{re.escape(term)}s?\b", field, re.IGNORECASE):
                    violations.append(f"{key}: '{term}'")
            if _KEY_RE.search(field):
                violations.append(f"{key}: cita una key SCREAMING_SNAKE")
            if _PHASE_RE.search(field):
                violations.append(f"{key}: referencia a fase de plan (F<n>)")
    assert violations == [], f"Jerga prohibida en ayuda llana: {violations}"


def test_plain_help_module_is_pure():
    src = (BACKEND_ROOT / "services" / "harness_flags_help.py").read_text(encoding="utf-8")
    for forbidden in ("import flask", "from flask", "from config", "import os", "import requests"):
        assert forbidden not in src, f"harness_flags_help.py no debe contener '{forbidden}'"


# v2/C3 — poda de directorios que NO son código de la app (backend\.venv EXISTE:
# sin poda, rglob leería miles de archivos del venv en cada corrida del ratchet).
_EXCLUDED_DIRS = {".venv", "venv", "__pycache__", "node_modules", "data", "dist", "build"}


def test_no_runtime_imports_plain_help():
    """Centinela de impacto NULO en los 3 runtimes: solo el registry (y este
    módulo/los tests) pueden referirse a harness_flags_help."""
    allowed = {"services/harness_flags.py", "services/harness_flags_help.py"}
    offenders = []
    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        if _EXCLUDED_DIRS & set(path.parts):
            continue
        rel = path.relative_to(BACKEND_ROOT).as_posix()
        if rel.startswith("tests/") or rel in allowed:
            continue
        if "harness_flags_help" in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(rel)
    assert offenders == [], f"Módulos fuera del registry que tocan la ayuda llana: {offenders}"
```

**Comando (desde `Stacky Agents/backend`, con el venv del repo):**
```
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -q
```

**Criterio de aceptación binario F0 (v2/C2 — exacto por test):** los 5 tests que importan `PLAIN_HELP` fallan con `ModuleNotFoundError` (`services.harness_flags_help` no existe); `test_plain_help_module_is_pure` falla con `FileNotFoundError` (lee el archivo directo); `test_no_runtime_imports_plain_help` **PASA verde ya en F0** (módulo inexistente ⇒ nadie lo referencia ⇒ 0 offenders — verde trivial ESPERADO, no es señal de error). Resultado esperado exacto: `6 failed, 1 passed`. Cualquier otro resultado = investigar antes de seguir.

**Flag protectora:** no aplica (test puro). **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F1 — Módulo `harness_flags_help.py`: ayuda llana para el 100% de las flags

**Objetivo:** crear el módulo declarativo PURO con la ayuda en lenguaje llano de TODAS las keys de `FLAG_REGISTRY`, dejando F0 en verde.

**Archivo a crear:** `Stacky Agents/backend/services/harness_flags_help.py`

**Estructura exacta:**

```python
"""Plan 86 — Ayuda en lenguaje llano ("para mortales") por flag del arnés.

Reglas de diseño:
- PURO: sin flask, sin config, sin IO. Solo datos + 1 función de lookup.
- Keyed por FlagSpec.key. Cobertura 100% del FLAG_REGISTRY (test centinela).
- SEPARADO de harness_flags.py a propósito: los planes 82/83/84/85 editan las
  specs; este archivo solo contiene contenido → conmutatividad.
- Redacción: prohibida la jerga de la denylist de tests/test_harness_flags_help.py.
  on_effect/off_effect son frases COMPLETAS que empiezan con "Si " (el panel
  las pinta tal cual, sin lógica de redacción en el frontend).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlainHelp:
    what: str        # qué hace, en 1 frase sin jerga (≤200 chars)
    on_effect: str   # "Si la activás: ..." / "Si subís el número: ..." (≤240)
    off_effect: str  # "Si la apagás: ..." / "Si lo dejás vacío: ..." (≤240)
    example: str     # ejemplo concreto para un no-experto (≤300)


PLAIN_HELP: dict[str, PlainHelp] = {
    # ... una entrada por CADA key de FLAG_REGISTRY (ver plantillas y ejemplos oro abajo) ...
}


def plain_help_for(key: str) -> dict | None:
    """Devuelve la ayuda llana serializable de una key, o None si no existe."""
    entry = PLAIN_HELP.get(key)
    if entry is None:
        return None
    return {
        "what": entry.what,
        "on_effect": entry.on_effect,
        "off_effect": entry.off_effect,
        "example": entry.example,
    }
```

**Procedimiento de poblado (determinista, para modelo menor):**
1. Recorrer `_CATEGORY_KEYS` de `services/harness_flags.py` (línea 91) categoría por categoría, en el orden del archivo; escribir la entrada de cada key en ese mismo orden (así el diff es revisable y ninguna key se salta). Son **158 entradas** en total (v2/C4: 104 bool / 25 int / 22 csv / 4 float / 2 str / 1 json — verificado con el venv). Las keys que no estén en `_CATEGORY_KEYS` no existen (el test de Plan 63 lo garantiza); la cobertura la verifica `test_plain_help_covers_all_registry_keys`.
2. Para redactar cada entrada, leer `label` + `description` de la spec correspondiente y aplicar la plantilla por tipo (tabla siguiente). Está PROHIBIDO inventar comportamiento que la description no respalde; si la description es ambigua, describir el efecto en términos del resultado visible para el operador ("el trabajo queda marcado para revisar", "aparece un aviso", "se gasta menos").
3. Verificar cada lote de categoría corriendo el comando de F0 (los tests de formato/jerga acusan la key exacta que viola).

**Plantilla por tipo de flag:**

| type | on_effect empieza con | off_effect empieza con |
|---|---|---|
| bool | "Si la activás: ..." | "Si la apagás: ..." |
| int / float | "Si subís el número: ..." (o "Si le ponés un valor: ...") | "Si lo bajás: ..." — salvo que la `description` de la spec documente que 0/vacío desactiva la función: en ese caso usar "Si lo dejás en cero: ..." |
| csv | "Si escribís nombres de proyectos separados por coma: ..." | "Si lo dejás vacío: ..." (normalmente "vale para todos los proyectos") |
| str | "Si escribís un valor: ..." | "Si lo dejás vacío: ..." |
| json | "Si escribís una configuración: ..." | "Si lo dejás vacío: ..." |

**Ejemplos ORO (copiar textual — son las 10 primeras entradas de referencia; cubren los 5 tipos):**

```python
    "CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED": PlainHelp(
        what="Un control de calidad automático que revisa el trabajo del agente antes de darlo por bueno.",
        on_effect="Si la activás: cuando el resultado tiene errores graves, el trabajo queda marcado 'para revisar' en vez de figurar como terminado.",
        off_effect="Si la apagás: el trabajo se da por terminado aunque tenga errores graves, y los descubrís vos después.",
        example="Es como la inspección final de una fábrica: si la pieza sale fallada, no se despacha al cliente.",
    ),
    "STACKY_DESKTOP_NOTIFY_ENABLED": PlainHelp(
        what="Avisos emergentes en tu computadora cuando un agente termina o necesita tu atención.",
        on_effect="Si la activás: te salta una notificación en la pantalla al terminar un trabajo, sin tener que mirar la aplicación.",
        off_effect="Si la apagás: no hay avisos; te enterás solo cuando entrás a mirar la aplicación.",
        example="Como el timbre del microondas: podés irte a hacer otra cosa y te avisa cuando está listo.",
    ),
    "STACKY_MAX_CONCURRENT_RUNS": PlainHelp(
        what="Cuántos agentes pueden estar trabajando al mismo tiempo como máximo.",
        on_effect="Si subís el número: más trabajos corren en paralelo, pero la máquina y el gasto suben.",
        off_effect="Si lo bajás: los trabajos hacen fila y salen de a menos, con la máquina más tranquila y gasto más previsible.",
        example="Como las cajas abiertas de un supermercado: más cajas = menos fila, pero más cajeros que pagar.",
    ),
    "STACKY_RUNAWAY_MAX_COST_USD": PlainHelp(
        what="Freno de emergencia por costo: cuánto puede gastar un trabajo antes de que se lo frene.",
        on_effect="Si le ponés un valor: un trabajo que se desboca y gasta de más se corta y queda marcado para que lo revises.",
        off_effect="Si lo dejás en cero: no hay tope, y un trabajo descontrolado puede gastar sin límite.",
        example="Como el límite de la tarjeta de crédito: si algo intenta gastar de más, la operación se bloquea.",
    ),
    "CLAUDE_CODE_CLI_MCP_PROJECTS": PlainHelp(
        what="En qué proyectos vale la conexión de herramientas extra del agente de Claude.",
        on_effect="Si escribís nombres de proyectos separados por coma: la función se usa solo en esos proyectos.",
        off_effect="Si lo dejás vacío: la función vale para todos los proyectos.",
        example="Como una llave que abre solo las oficinas que vos elijas; sin lista, abre todas.",
    ),
    "STACKY_MEMORY_CAPS_JSON": PlainHelp(
        what="Límites de cuánta memoria acumulada se le muestra al agente en cada trabajo.",
        on_effect="Si escribís una configuración: acotás cuántos recuerdos de cada tipo recibe el agente, para que no se distraiga ni encarezca.",
        off_effect="Si lo dejás vacío: se usan los límites estándar del sistema.",
        example="Como decirle a un asesor 'traeme máximo 3 antecedentes por tema', en vez de que llegue con la biblioteca entera.",
    ),
    "STACKY_EPIC_FROM_BRIEF_ENABLED": PlainHelp(
        what="Permite generar una épica (ficha grande de trabajo) a partir de un texto breve que escribís.",
        on_effect="Si la activás: escribís una idea en pocas líneas y el sistema arma la épica completa y la publica en tu tablero.",
        off_effect="Si la apagás: la opción de crear épicas desde un texto breve desaparece; las épicas se crean a mano.",
        example="Le dictás 'quiero un proceso nocturno que cargue archivos de clientes' y aparece la ficha completa en Azure DevOps.",
    ),
    "STACKY_PUSH_REJECTIONS_ENABLED": PlainHelp(
        what="Hace que el sistema aprenda de los trabajos que rechazaste, para no repetir el mismo error.",
        on_effect="Si la activás: cada rechazo tuyo se convierte en una lección que los agentes reciben en los próximos trabajos.",
        off_effect="Si la apagás: los rechazos no dejan enseñanza; el mismo error puede repetirse.",
        example="Como un empleado que anota 'al jefe no le gusta X' después de cada devolución, y no tropieza dos veces.",
    ),
    "STACKY_ORPHAN_REAPER_ENABLED": PlainHelp(
        what="Limpieza automática de procesos que quedaron colgados sin que nadie los use.",
        on_effect="Si la activás: cada tanto se buscan y cierran procesos abandonados, liberando memoria de la máquina.",
        off_effect="Si la apagás: los procesos colgados quedan vivos hasta que alguien los cierre a mano.",
        example="Como apagar las luces de las oficinas vacías cada una hora.",
    ),
    "STACKY_RAG_CATALOG_ENABLED": PlainHelp(
        what="Cuando el catálogo de procesos es largo, le muestra al agente solo las partes que se parecen a tu pedido.",
        on_effect="Si la activás: el agente recibe solo los procesos del catálogo relacionados con lo que pediste — menos ruido y menos gasto.",
        off_effect="Si la apagás: el agente recibe el catálogo completo, aunque la mayoría no tenga que ver con tu pedido.",
        example="En vez de darle la guía telefónica entera, le das la página donde está el apellido que busca.",
    ),
```

**Criterio de aceptación binario F1:**
```
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -q
```
→ los 7 tests de F0 en verde (cobertura 100%, sin huérfanas, formato, sin jerga, módulo puro, ningún runtime lo importa).

**Flag protectora:** no aplica (datos declarativos que nadie lee todavía). **Impacto por runtime:** ninguno (el módulo no es importado por nadie en esta fase). **Trabajo del operador:** ninguno.

---

### F2 — Exponer `plain_help` en la API (`read_current()`)

**Objetivo:** que `GET /api/harness-flags` incluya la ayuda llana por flag, sin tocar el endpoint.

**Test PRIMERO — agregar a `Stacky Agents/backend/tests/test_harness_flags_help.py`:**

```python
def test_read_current_exposes_plain_help():
    from services.harness_flags import read_current
    flags = {f["key"]: f for f in read_current()}
    ph = flags["CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED"]["plain_help"]
    assert ph is not None
    assert set(ph) == {"what", "on_effect", "off_effect", "example"}
    assert ph["on_effect"].startswith("Si ")
    # Toda flag expone la clave (aunque una futura sin entrada daría None):
    assert all("plain_help" in f for f in flags.values())
```
(Verificado v2/C5: `read_current()` importa `config` LAZY dentro de la función — `services/harness_flags.py:1934` — y `tests/test_harness_flags.py:523-529` ya lo llama tal cual, sin mock ni fixture: este test corre igual, a pelo.)

**Archivo a editar:** `Stacky Agents/backend/services/harness_flags.py`
1. Import al tope del módulo (junto a los imports existentes): `from services.harness_flags_help import plain_help_for`
2. En `read_current()` (línea 1932), dentro del dict de `result.append({...})` (líneas 1952-1965), agregar UNA línea inmediatamente después de `"active": is_active(spec, value),`:
   ```python
            "plain_help": plain_help_for(spec.key),
   ```
   (Aditiva y en línea propia — no colisiona con las líneas que agregan 82/83/84/85 al mismo dict.)

**Criterio binario F2:**
```
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py tests/test_harness_flags.py -q
```
→ test nuevo verde Y `test_harness_flags.py` completo sigue verde (categorización, curated defaults y serializador intactos).

**Flag protectora:** no aplica (clave aditiva en JSON; clientes existentes la ignoran). **Impacto por runtime:** ninguno (`read_current()` solo lo consume el panel vía `api/harness_flags.py`; el centinela de F0 sigue verde porque `services/harness_flags.py` está en `allowed`). **Trabajo del operador:** ninguno.

---

### F3 — UI: botón de ayuda (ⓘ) por flag + bloque expandible + búsqueda que entiende a mortales

**Objetivo:** el "signito" que pidió el operador: un botón por flag que despliega la ayuda llana, con fallback honesto, y búsqueda que también matchea ese texto.

**Archivos a editar:**

1. `Stacky Agents/frontend/src/api/endpoints.ts` — en `interface HarnessFlagView` (línea 652), agregar tras `active: boolean;`:
   ```typescript
     plain_help?: {              // Plan 86 — ayuda en lenguaje llano (null/ausente = sin ayuda aún)
       what: string;
       on_effect: string;
       off_effect: string;
       example: string;
     } | null;
   ```
   (Opcional `?` para tolerar backends viejos — backward compatible.)

2. `Stacky Agents/frontend/src/components/HarnessFlagsPanel.tsx`:
   - Import: `import { Info } from "lucide-react";` (icono existente en lucide-react@0.453; NO usar `HelpCircle`, ya reservado como fallback de categoría en `harnessVisuals.ts:59`).
   - En `FlagRow`, agregar los estados locales `const [showHelp, setShowHelp] = useState(false);` y `const [showPairHelp, setShowPairHelp] = useState(false);` (v2/C9) INMEDIATAMENTE DESPUÉS del `useEffect` de `localPair` (línea 67) y **ANTES** del early-return `if (isManagedAsPair) return null;` (línea 71). **(v2/C1 — BLOQUEANTE corregido):** si un hook se declara después de ese `return null;` condicional se viola la regla de hooks de React → el panel entero crashea en runtime y `npx tsc --noEmit` NO lo detecta (falso verde). La posición es OBLIGATORIA, no estilística.
   - En el JSX de `flagMeta` (línea ~163), inmediatamente DESPUÉS de `<span className={styles.flagName}>` y ANTES del badge `def:`, agregar:
     ```tsx
     <button
       type="button"
       className={styles.helpBtn}
       aria-expanded={showHelp}
       aria-label={`Explicación simple de ${flag.label}`}
       title="¿Para qué sirve esto?"
       onClick={() => setShowHelp((v) => !v)}
     >
       <Info size={14} aria-hidden="true" />
     </button>
     ```
   - Inmediatamente DESPUÉS de `<p className={styles.flagDesc}>` (línea ~169), agregar:
     ```tsx
     {showHelp && (
       <div className={styles.plainHelp}>
         {flag.plain_help ? (
           <>
             <p className={styles.plainWhat}>{flag.plain_help.what}</p>
             <ul className={styles.plainList}>
               <li>{flag.plain_help.on_effect}</li>
               <li>{flag.plain_help.off_effect}</li>
             </ul>
             <p className={styles.plainExample}>Ejemplo: {flag.plain_help.example}</p>
           </>
         ) : (
           <p className={styles.plainPending}>
             Explicación simple pendiente para esta opción. Descripción técnica: {flag.description}
           </p>
         )}
       </div>
     )}
     ```
     (Fallback HONESTO: nunca se inventa texto en el frontend.)
   - **(v2/C9) Ayuda para la flag pair.** Las flags `*_PROJECTS` gestionadas como par NO renderizan `FlagRow` propio (`isManagedAsPair` → `return null`, líneas 70-71): sin este paso su ayuda llana sería INALCANZABLE (incluida la key oro `CLAUDE_CODE_CLI_MCP_PROJECTS`). En el bloque `pairRow` (líneas 174-187), inmediatamente DESPUÉS de `<span className={styles.pairLabel}>{pairFlag.label}</span>`, agregar el mismo botón (usando `showPairHelp`/`setShowPairHelp` y `aria-label={`Explicación simple de ${pairFlag.label}`}`), y DESPUÉS del `<input ...>` del par, agregar el mismo bloque `{showPairHelp && (...)}` leyendo `pairFlag.plain_help` (mismo fallback honesto con `pairFlag.description`).
   - Búsqueda (v2/C6 corregido + **[ADICIÓN ARQUITECTO v2/C13]** insensible a acentos). `matches()` (líneas 246-254) **YA tiene cuerpo `{ ... }`** con dos early-returns (`onlyActive`, `!qLower`) y un `return (...)` final — NO reescribirla; solo insertar/reemplazar. Pasos exactos:
     1. Junto a `const qLower = q.trim().toLowerCase();` (línea 245), agregar:
        ```tsx
        // Plan 86 — búsqueda "de mortal": sin acentos ("notificacion" encuentra "notificación").
        const deaccent = (s: string) => s.normalize("NFD").replace(/[\\u0300-\\u036f]/g, "");
        const qPlain = deaccent(qLower);
        ```
     2. Dentro de `matches()`, INMEDIATAMENTE ANTES del `return (` final (línea 249), insertar:
        ```tsx
        const ph = f.plain_help;
        if (ph) {
          const plainBlob = deaccent(`${ph.what} ${ph.on_effect} ${ph.off_effect} ${ph.example}`.toLowerCase());
          if (plainBlob.includes(qPlain)) return true;
        }
        ```
     3. Reemplazar el `return (...)` final por (mismas 3 condiciones, ahora sin acentos en label/description; las keys son ASCII y siguen con `qLower`):
        ```tsx
        return (
          deaccent(f.label.toLowerCase()).includes(qPlain) ||
          deaccent(f.description.toLowerCase()).includes(qPlain) ||
          f.key.toLowerCase().includes(qLower)
        );
        ```

3. `Stacky Agents/frontend/src/components/HarnessFlagsPanel.module.css` — agregar clases:
   ```css
   .helpBtn {
     display: inline-flex;
     align-items: center;
     padding: 2px;
     margin-left: 4px;
     border: none;
     border-radius: 50%;
     background: transparent;
     color: var(--color-primary, #2563eb);
     cursor: pointer;
   }
   .helpBtn:hover { background: var(--color-primary-light, #dce8ff); }
   .helpBtn:focus-visible { outline: 2px solid var(--color-primary, #2563eb); outline-offset: 2px; }
   .plainHelp {
     margin: 6px 0 4px;
     padding: 8px 10px;
     border-left: 3px solid var(--color-primary, #2563eb);
     border-radius: 4px;
     background: var(--color-primary-light-subtle, #f0f6ff);
     font-size: 0.85rem;
     color: var(--color-text, #222);
   }
   .plainWhat { margin: 0 0 4px; font-weight: 600; }
   .plainList { margin: 0 0 4px; padding-left: 18px; }
   .plainExample { margin: 0; font-style: italic; color: var(--color-text-secondary, #555); }
   .plainPending { margin: 0; color: var(--color-text-secondary, #777); }
   ```

4. `Stacky Agents/frontend/src/components/__tests__/HarnessFlagsPanel.test.tsx` — SI vitest está operativo en el entorno, agregar 2 casos: (a) click en el botón de ayuda de un flag con `plain_help` muestra `what`; (b) flag sin `plain_help` muestra el texto "Explicación simple pendiente". SI vitest no corre (limitación conocida del repo), el criterio de F3 es solo el typecheck.

**Criterio binario F3 (desde `Stacky Agents/frontend`):**
```
npx tsc --noEmit
```
→ exit code 0.

**Flag protectora:** no aplica — data-driven: sin `plain_help` en los datos, el bloque muestra el fallback y nada más cambia. **Impacto por runtime:** ninguno (solo panel). **Trabajo del operador:** ninguno.

---

### F4 — UI: contraste ON/OFF inconfundible (color + etiqueta textual + foco visible)

**Objetivo:** que el estado de cada perilla se entienda de un vistazo y sin depender del color, alineado a los tokens del tema.

**Archivos a editar:**

1. `Stacky Agents/frontend/src/components/HarnessFlagsPanel.tsx` — en `FlagRow`, dentro de la rama `flag.type === "bool"` del `control()` (línea ~76), envolver el toggle con una etiqueta de estado textual. Reemplazar el `return` de esa rama por:
   ```tsx
   return (
     <div className={styles.boolControl}>
       <label className={styles.toggle}>
         <input
           type="checkbox"
           checked={Boolean(flag.value)}
           disabled={saving}
           onChange={(e) => onUpdate(flag.key, e.target.checked)}
         />
         <span className={styles.toggleSlider} />
       </label>
       <span
         className={`${styles.stateLabel} ${Boolean(flag.value) ? styles.stateOn : styles.stateOff}`}
       >
         {Boolean(flag.value) ? "Activada" : "Desactivada"}
       </span>
     </div>
   );
   ```
   (El `<input type="checkbox">` sigue siendo el control accesible; la etiqueta es refuerzo visual.)

2. `Stacky Agents/frontend/src/components/HarnessFlagsPanel.module.css`:
   - Cambiar el color ON del slider (línea ~310) de primary a success, para que "encendida" no se confunda con el azul de acento del tema:
     ```css
     .toggle input:checked + .toggleSlider {
       background: var(--color-success, #15803d);
     }
     ```
   - Reforzar el OFF (línea ~301, regla `.toggleSlider`): agregar `border: 1px solid var(--color-border-strong, #9ca3af);` y `box-sizing: border-box;` para que la perilla apagada no se pierda contra el fondo.
   - Foco visible por teclado (regla nueva):
     ```css
     .toggle input:focus-visible + .toggleSlider {
       outline: 2px solid var(--color-primary, #2563eb);
       outline-offset: 2px;
     }
     ```
   - Clases nuevas:
     ```css
     .boolControl { display: flex; align-items: center; gap: 8px; }
     .stateLabel { font-size: 0.75rem; font-weight: 600; min-width: 82px; }
     .stateOn  { color: var(--color-success, #15803d); }
     .stateOff { color: var(--color-text-secondary, #6b7280); }
     ```
   - Micro-mejora de claridad (1 atributo): en el JSX del badge `def:` (`HarnessFlagsPanel.tsx` línea ~166) agregar `title="Valor de fábrica"` al `<span className={styles.defaultBadge}>`.

**Nota de contraste (criterio de elección de colores):** `#15803d` sobre fondo claro y como fondo del slider con perilla blanca cumple contraste AA (≥3:1 para componentes UI); los fallbacks elegidos son los que ya usa la familia de tokens del tema (`--color-success`, `--color-border-strong`) — NO se agregan variables globales nuevas; si el token no existe, aplica el fallback local.

**Criterio binario F4 (desde `Stacky Agents/frontend`):**
```
npx tsc --noEmit
```
→ exit code 0. Verificación visual (no bloqueante): toggle ON verde con etiqueta "Activada"; OFF gris con borde y etiqueta "Desactivada"; Tab muestra anillo de foco.

**Flag protectora:** no aplica (presentación pura). **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F5 — UI: chips índice de categorías (navegación en 1 click) + encabezado de sección tintado

**Objetivo:** sectorización perceptible: un índice visual con el color/icono de cada categoría que lleva a su sección, y encabezados que "pertenecen" visualmente a su color.

**Archivo a editar:** `Stacky Agents/frontend/src/components/HarnessFlagsPanel.tsx`

1. Estado nuevo en `HarnessFlagsPanel` (junto a `const [onlyActive, ...]`, línea ~202):
   ```tsx
   const [focusCat, setFocusCat] = useState<string | null>(null);
   ```
2. En `renderSection` (línea ~316):
   - Agregar `id={`harness-cat-${cat.id}`}` al `<details>`.
   - Cambiar el `open` (línea 326) a: `open={!!qLower || onlyActive || sectionActive || focusCat === cat.id}`.
   - (v2/C8) Agregar al mismo `<details>` un `onToggle` que libere el foco cuando el usuario cierra la sección a mano (evita que quede "pegada" abierta por `focusCat`):
     ```tsx
     onToggle={(e) => {
       if (!e.currentTarget.open && focusCat === cat.id) setFocusCat(null);
     }}
     ```
   - Al `<summary className={styles.sectionSummary}>` agregarle tinte del color de la categoría (inline, porque el color es dinámico):
     ```tsx
     style={{ background: `color-mix(in srgb, ${color} 8%, transparent)` }}
     ```
3. Contenedor de chips — insertar DESPUÉS del bloque del toggle Simple/Experto (línea ~447) y ANTES de las secciones. Las secciones listadas son las visibles según el modo (en modo simple, las categorías del catch-all "Todo lo demás" NO tienen chip — mantiene el modo simple simple):
   ```tsx
   {(() => {
     const navSections = mode === "experto" ? orderedSections : simpleSections;
     if (navSections.length < 2) return null;
     return (
       <nav aria-label="Ir a categoría" className={styles.catNav}>
         {navSections.map(({ cat, catFlags }) => {
           const { color, icon: CatIcon } = visualFor(cat.id);
           return (
             <button
               key={cat.id}
               type="button"
               className={styles.catChip}
               style={{ borderColor: color, color }}
               onClick={() => {
                 setFocusCat(cat.id);
                 requestAnimationFrame(() => {
                   document
                     .getElementById(`harness-cat-${cat.id}`)
                     ?.scrollIntoView({ behavior: "smooth", block: "start" });
                 });
               }}
             >
               <CatIcon size={13} aria-hidden="true" />
               {cat.label}
               <span className={styles.catChipCount}>{catFlags.length}</span>
             </button>
           );
         })}
       </nav>
     );
   })()}
   ```
4. `HarnessFlagsPanel.module.css` — clases nuevas:
   ```css
   .catNav {
     display: flex;
     flex-wrap: wrap;
     gap: 6px;
     margin: 8px 0 12px;
   }
   .catChip {
     display: inline-flex;
     align-items: center;
     gap: 5px;
     padding: 3px 10px;
     border: 1px solid;
     border-radius: 14px;
     background: var(--color-surface, #fff);
     font-size: 0.75rem;
     cursor: pointer;
   }
   .catChip:hover { filter: brightness(0.92); }
   .catChip:focus-visible { outline: 2px solid var(--color-primary, #2563eb); outline-offset: 2px; }
   .catChipCount {
     font-size: 0.7rem;
     opacity: 0.75;
   }
   ```

**Regla de NO colisión:** este contenedor `styles.catNav` es NUEVO y vive fuera de `styles.hero`; los planes 82/83/84 agregan sus chips/contadores DENTRO del hero. Cero solape.

**Criterio binario F5 (desde `Stacky Agents/frontend`):**
```
npx tsc --noEmit
```
→ exit code 0. Verificación visual (no bloqueante): click en un chip abre y scrollea a la sección; los chips reflejan el modo Simple/Experto.

**Flag protectora:** no aplica. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F6 — Ratchet + verificación integral

**Objetivo:** registrar el test nuevo en el gate del arnés (regla Plan 49 F4) y cerrar con verificación completa.

**Archivos a editar:**
- `Stacky Agents/backend/scripts/run_harness_tests.sh` — agregar `tests/test_harness_flags_help.py` a `HARNESS_TEST_FILES`, en orden alfabético relativo a los vecinos.
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` — ídem en la lista equivalente.

**Criterio binario F6:**
1. Desde `Stacky Agents/backend`:
   ```
   .venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py tests/test_harness_flags.py -q
   ```
   → todo verde (incluye el meta-test del ratchet si vive en `test_harness_flags.py`; si el meta-test del Plan 49 F4 vive en otro archivo, correrlo también por nombre).
2. Desde `Stacky Agents/frontend`:
   ```
   npx tsc --noEmit
   ```
   → exit code 0.
3. `git diff --stat` limitado a: `services/harness_flags_help.py` (nuevo), `services/harness_flags.py` (2 líneas), `tests/test_harness_flags_help.py` (nuevo), `frontend/src/api/endpoints.ts`, `frontend/src/components/HarnessFlagsPanel.tsx`, `frontend/src/components/HarnessFlagsPanel.module.css`, opcional `__tests__/HarnessFlagsPanel.test.tsx`, y los 2 scripts de ratchet. **Ningún archivo de runners/runtime tocado.**

**Flag protectora:** no aplica. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Redactar 158 entradas llanas es laborioso y un modelo menor puede alucinar comportamiento | Procedimiento determinista (recorrer `_CATEGORY_KEYS` en orden), prohibición explícita de inventar más allá de la `description`, plantillas por tipo, 10 ejemplos oro textuales, y tests que acusan la key exacta (formato/jerga/longitud). El texto es DATO: corregirlo después es editar 1 string. |
| La denylist de jerga rompe una redacción legítima (p.ej. "Azure DevOps") | La denylist es corta y congelada; nombres de productos (Azure DevOps, GitLab, Claude, Codex, Copilot) NO están prohibidos. Ampliarla/reducirla exige editar el test a propósito (patrón Plan 61/63). |
| Colisión con 82/83/84/85 en `harness_flags.py` / `FlagRow` / hero | Diseño conmutativo (sección 3.7): módulo aparte, 1 línea aditiva en `read_current()`, UI en espacio propio (botón junto a `flagName`, bloque bajo `flagDesc`, `catNav` fuera del hero). Quien implemente segundo solo edita líneas distintas. |
| Cambiar el ON del toggle de azul a verde confunde a quien ya se acostumbró | El verde + etiqueta "Activada" es estrictamente más informativo; `activeRow` ya tinta la fila igual que antes. Reversible en 1 línea de CSS. |
| `color-mix` / `:focus-visible` en navegadores viejos | Ambos ya se usan o se proponen en el repo (plan 85 F3 usa `color-mix`); la app corre en navegadores modernos del operador. Si `color-mix` no aplica, el summary queda sin tinte (degradación cosmética, no funcional). |
| El bloque de ayuda abierto empuja el layout | Es colapsable por flag (estado local, cerrado por default); no hay estado global ni persistencia. |
| Suite completa del backend contaminada (~40F/449E conocidos) | Validar por archivo (`test_harness_flags_help.py` + `test_harness_flags.py`), patrón estándar del repo. |
| vitest no operativo para los tests de UI | Igual que planes 78/85: criterio binario = `npx tsc --noEmit`; los casos vitest quedan escritos como opcionales. |

## 6. Fuera de scope

- Agregar campos a `FlagSpec` o tocar specs individuales del registry (eso es territorio de 82/83/84/85).
- Tocar el hero (`styles.hero`), sus contadores o los botones de perfil (82/83/84 ya lo intervienen).
- Traducir/renombrar `label`/`description` técnicos existentes (siguen siendo la fuente para expertos).
- Tooltips flotantes con librerías nuevas (cero dependencias nuevas; el bloque es expandible inline).
- Editor de la ayuda llana desde la UI (el contenido es código declarativo versionado; editarlo es un PR de 1 string).
- Reordenar o fusionar categorías (`FLAG_CATEGORIES` intacta; la sectorización se mejora con navegación y tinte, no reestructurando).
- Cualquier cambio en runners, `api/harness_flags.py`, perfiles o caminos de ejecución de los 3 runtimes.

## 7. Glosario

- **FLAG_REGISTRY / FlagSpec:** catálogo declarativo de 158 flags del arnés (`backend/services/harness_flags.py:214`; conteo verificado 2026-07-02); fuente única que la UI renderiza dinámicamente (Planes 33/62/63).
- **Ayuda llana / `PlainHelp`:** texto por flag SIN jerga de IA, con formato fijo (`what`, `on_effect`, `off_effect`, `example`), pensado para un operador no técnico (este plan).
- **HarnessFlagsPanel:** panel React (`frontend/src/components/HarnessFlagsPanel.tsx`) que renderiza el registry por categorías (Planes 62/63/78).
- **harnessVisuals.ts:** mapa slug de categoría → color+icono (Plan 78); este plan lo REUSA (`visualFor`) para chips y tintes, no lo modifica.
- **Hero:** cabecera del panel con perfil y contadores (Plan 78 F3); intocable en este plan (lo intervienen 82/83/84).
- **Centinela:** test que congela una invariante estructural y rompe CI a propósito si se viola (patrón Planes 49/61/63).
- **Ratchet / HARNESS_TEST_FILES:** listas en `backend/scripts/run_harness_tests.{sh,ps1}` donde debe registrarse todo test nuevo del backend (meta-test del Plan 49 F4).
- **`_CURATED_DEFAULTS_ON`:** lista congelada de 12 keys (Plan 63) fuera de la cual está prohibido declarar `default=` en una FlagSpec; este plan no crea specs → sin riesgo.
- **Modo Simple/Experto:** toggle del Plan 78 que muestra solo categorías `tier="simple"` o todas; los chips de F5 lo respetan.

## 8. Orden de implementación

1. F0 — escribir `tests/test_harness_flags_help.py`; verificar que falla por módulo inexistente.
2. F1 — crear `services/harness_flags_help.py` y poblar el 100% de las entradas por categoría; F0 verde.
3. F2 — test del serializador; import + 1 línea en `read_current()`; verde.
4. F3 — tipo TS + botón ⓘ + bloque expandible + fallback + búsqueda extendida; `npx tsc --noEmit` exit 0.
5. F4 — contraste ON/OFF (CSS + etiqueta textual + foco visible); tsc exit 0.
6. F5 — chips índice + tinte de encabezados; tsc exit 0.
7. F6 — ratchet sh+ps1 + verificación integral (tests por archivo + tsc + diff limitado).

## 9. Definición de Hecho (DoD)

- [ ] `tests/test_harness_flags_help.py` existe con los 8 tests nombrados (7 de F0 + 1 de F2) y pasa con el venv del repo.
- [ ] `services/harness_flags_help.py` cubre el 100% de `FLAG_REGISTRY` (158 keys), sin huérfanas, formato y denylist verdes; módulo puro.
- [ ] `GET /api/harness-flags` expone `plain_help` por flag (clave presente en todas; objeto o `null`).
- [ ] Cada flag del panel tiene botón ⓘ que despliega la ayuda llana — INCLUIDAS las flags pair `*_PROJECTS` dentro del `pairRow` (v2/C9); flags sin ayuda muestran el fallback honesto "Explicación simple pendiente".
- [ ] La búsqueda matchea también el texto de la ayuda llana y es insensible a acentos (deaccent NFD) [ADICIÓN ARQUITECTO v2/C13].
- [ ] Toggle ON verde (token success) + OFF con borde, etiqueta textual "Activada/Desactivada", foco visible por teclado.
- [ ] Chips índice de categorías con color+icono (reusando `visualFor`) que abren y scrollean a su sección; encabezados de sección tintados con el color de su categoría.
- [ ] `test_no_runtime_imports_plain_help` verde (impacto NULO en los 3 runtimes, probado mecánicamente).
- [ ] `test_harness_flags.py` completo sigue verde (categorización y `test_default_known_only_for_curated` intactos; no se creó ninguna FlagSpec).
- [ ] Test nuevo registrado en `run_harness_tests.sh` y `.ps1`; `npx tsc --noEmit` exit 0.
- [ ] Diff limitado a los archivos listados en F6.3; ningún runner/runtime tocado; ninguna flag nueva; hero intacto.
- [ ] Trabajo del operador: ninguno.
