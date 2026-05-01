"""
prompt_enhancer.py — S-05, S-06, S-07: Mejoras Quirurgicas a los Prompts.

Complementa prompt_builder.py con:

  S-05: Inyeccion de BUG_LOCALIZATION.md en prompts PM y DEV
        Si existe BUG_LOCALIZATION.md en la carpeta del ticket, se inyecta
        como seccion de contexto adicional al inicio del prompt.

  S-06: Protocolo Fix Quirurgico en prompt DEV
        Instruye a DEV a declarar explicitamente el scope minimo:
        - Que archivos exactamente va a tocar
        - Que metodos va a modificar
        - Que NO va a tocar (para evitar side effects)

  S-07: Prompt PM: bajar ARQUITECTURA_SOLUCION a nivel de metodo
        Instruye a PM a identificar el metodo exacto a modificar,
        no solo el archivo. ARQUITECTURA_SOLUCION.md debe tener:
        - Archivo → Clase → Metodo exacto con numero de linea (si es posible)
        - Cambio especifico: agregar/modificar/mover

Uso:
    from prompt_enhancer import enhance_pm_prompt, enhance_dev_prompt
    enhanced_pm  = enhance_pm_prompt(base_pm_prompt, ticket_folder)
    enhanced_dev = enhance_dev_prompt(base_dev_prompt, ticket_folder)
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

# Maximo de caracteres a inyectar de BUG_LOCALIZATION.md
_BUG_LOC_MAX_CHARS = 3000


def enhance_pm_prompt(base_prompt: str, ticket_folder: str) -> str:
    """
    S-05 + S-07: Mejora el prompt PM con:
      - Contexto de bug localization pre-generado (S-05)
      - Instruccion de llevar ARQUITECTURA_SOLUCION al nivel de metodo (S-07)
    """
    enhancements = []

    # S-05: Inyectar BUG_LOCALIZATION.md si existe
    bug_loc_section = _inject_bug_localization(ticket_folder)
    if bug_loc_section:
        enhancements.append(bug_loc_section)

    # S-07: Instruccion de nivel-metodo para ARQUITECTURA_SOLUCION
    enhancements.append(_build_s07_instruction())

    if not enhancements:
        return base_prompt

    injection = "\n\n" + "\n\n".join(enhancements)
    return base_prompt + injection


def enhance_dev_prompt(base_prompt: str, ticket_folder: str) -> str:
    """
    S-05 + S-06: Mejora el prompt DEV con:
      - Contexto de bug localization pre-generado (S-05)
      - Protocolo de fix quirurgico (S-06)
    """
    enhancements = []

    # S-05: Inyectar BUG_LOCALIZATION.md si existe
    bug_loc_section = _inject_bug_localization(ticket_folder)
    if bug_loc_section:
        enhancements.append(bug_loc_section)

    # S-06: Protocolo de fix quirurgico
    enhancements.append(_build_s06_protocol())

    if not enhancements:
        return base_prompt

    injection = "\n\n" + "\n\n".join(enhancements)
    return base_prompt + injection


# ── Secciones de mejora ───────────────────────────────────────────────────────

def _inject_bug_localization(ticket_folder: str) -> str:
    """
    S-05: Lee BUG_LOCALIZATION.md y genera la seccion de inyeccion.
    Retorna '' si el archivo no existe.
    """
    bug_loc_path = Path(ticket_folder) / "BUG_LOCALIZATION.md"
    if not bug_loc_path.exists():
        return ""

    try:
        content = bug_loc_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

    if len(content) > _BUG_LOC_MAX_CHARS:
        content = content[:_BUG_LOC_MAX_CHARS] + "\n… [truncado — ver BUG_LOCALIZATION.md completo]"

    return f"""---

## Contexto Pre-Analizado por Stacky (Bug Localization)

> Este bloque fue generado automaticamente por analisis de stack trace,
> mensajes RIDIOMA y entry points. Usalo como punto de partida — valida
> contra el codigo real.

{content}

---"""


def _build_s06_protocol() -> str:
    """
    S-06: Protocolo de Fix Quirurgico para el prompt DEV.
    Instruye a DEV a declarar scope minimo antes de implementar.
    """
    return """---

## Protocolo de Fix Quirurgico — OBLIGATORIO

Antes de implementar, declara en DEV_COMPLETADO.md (o al inicio de tu trabajo):

### Scope del Fix
```
ARCHIVOS A MODIFICAR:
  - [ruta/archivo.cs] — razon: [por que este archivo]

METODOS A TOCAR:
  - [Clase.Metodo()] linea ~[N] — cambio: [descripcion exacta del cambio]

ARCHIVOS QUE NO VOY A TOCAR:
  - [listar otros archivos relacionados que se dejan sin cambios]

CAMBIO MINIMO:
  [descripcion en 1-2 lineas del cambio mas pequeño que resuelve el bug]
```

**Reglas del fix quirurgico:**
1. Modificar solo lo necesario para resolver el bug. Sin refactorizaciones adicionales.
2. Si el fix requiere tocar mas de 3 archivos, consultar con PM antes de proceder.
3. No cambiar firmas de metodos publicos sin listar TODOS los callers que se deben actualizar.
4. Cada cambio debe ser justificable directamente por el analisis PM.
5. Si hay duda entre dos enfoques, elegir el mas conservador (menor blast radius).

---"""


def _build_s07_instruction() -> str:
    """
    S-07: Instruccion para que PM lleve ARQUITECTURA_SOLUCION al nivel de metodo.
    """
    return """---

## Instruccion Adicional — ARQUITECTURA_SOLUCION.md a Nivel de Metodo

En ARQUITECTURA_SOLUCION.md, CADA cambio propuesto debe especificarse a nivel de metodo:

```markdown
## Cambios en [Archivo.cs]

**Clase:** `NombreClase`
**Metodo:** `NombreMetodo(TipoParam param)` — linea ~[N] (aproximada)
**Tipo de cambio:** [Agregar validacion / Modificar logica / Agregar llamada]
**Cambio especifico:**
  - Antes: [descripcion de lo que hace actualmente, si es relevante]
  - Despues: [lo que debe hacer post-fix]
  - Razon: [por que este cambio resuelve el bug]
```

**NO es suficiente decir:** "Modificar DAL_Pedidos.cs"
**SI es suficiente:** "En `DAL_Pedidos.GetPedidoDetalle()` (linea ~89): agregar validacion
  `if (result == null) return null;` antes de acceder a `result.ClienteId`"

Esta especificacion permite a DEV implementar sin ambiguedad y reduce el rework QA→DEV.

---"""
