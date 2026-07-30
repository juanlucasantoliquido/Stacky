"""tools/migrar_mantis_gitlab/mapping/date_map.py — normalización de fechas Mantis → ISO 8601.

## Por qué existe

Mantis entrega sus fechas **como texto ya formateado según el locale de la
instancia** — no como timestamps. Contra `soporte.ais-int.net` los formatos
observados en el HTML real son:

  * detalle de ticket (`td.bug-date-submitted`) → `dd/mm/yyyy HH:MM`  ej. `10/01/2026 09:15`
  * listado (`td.column-last-modified`)        → `dd/mm/yy`           ej. `10/01/26`
  * bugnotes (cabecera de la nota)             → `dd/mm/yyyy HH:MM`   ej. `13/01/2026 10:00`

La API de GitLab, en cambio, exige **ISO 8601** para los campos de fecha que sí
acepta (`created_at` en `POST /issues` y en `POST /issues/:iid/notes`,
`updated_at` en `PUT /issues/:iid`). Antes de este módulo el paquete no tenía
NINGUNA conversión de fechas (0 ocurrencias de `strptime`/`isoformat` en todo
`migrar_mantis_gitlab/`): las fechas viajaban como string crudo o se perdían.

## Regla de oro: día primero, y nunca adivinar

`10/01/2026` es **10 de enero** (formato es_ES/es_CL de MantisBT), no 1 de
octubre. Interpretarlo al revés desplaza fechas casi 9 meses sin que nada falle.
Por eso el parseo es **explícito y ordenado**, y ante un valor que no matchea
ningún formato conocido **devuelve `None`** en vez de arriesgar una fecha
inventada. El caller degrada a advertencia; jamás se manda a GitLab una fecha
que no se pudo verificar.

## Zona horaria

Mantis muestra la hora en el TZ de su instancia y **no lo declara en el HTML**.
Si se manda a GitLab un ISO sin offset, GitLab lo interpreta como **UTC**, lo que
introduce un corrimiento igual al offset real de la instancia (para Chile serían
3 o 4 horas según DST). Por eso:

  * `tz_offset` es un parámetro EXPLÍCITO (ej. `"-04:00"`), configurable en
    `origin.timezone_offset` del `migration_config.json`;
  * el default es `""` → se emite el ISO **sin** offset y el caller debe saber
    que GitLab lo tomará como UTC. Es un corrimiento de horas, nunca de días, y
    queda declarado en el reporte en vez de disimulado.

No se usa `dateutil` (no es dependencia del backend) ni se adivina el DST: el
offset es el que el operador declare.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

# Formatos aceptados, EN ORDEN. El primero que matchee gana.
# `%d/%m/...` (día primero) es deliberado — ver "Regla de oro" en el docstring.
_FORMATOS = (
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d-%m-%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)

# `dd/mm/yy` (año de 2 dígitos, el que usa el LISTADO de Mantis). Se trata
# aparte porque `%y` de strptime aplica la ventana 1969-2068, y acá conviene ser
# explícito: 00-68 → 20xx, 69-99 → 19xx. Un ticket de cobranzas de 1998 no
# existe, pero adivinar en silencio sí sería un problema.
_DDMMYY_RE = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2})(?:\s+(\d{1,2}):(\d{2}))?$")

# Ya viene en ISO 8601 (el adapter de API REST de Mantis devuelve así): se
# normaliza el sufijo pero no se re-interpreta.
_ISO_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?$"
)


def _normalizar_offset(tz_offset: str) -> str:
    """Valida y normaliza el offset a `''` | `'Z'` | `'-04:00'`.

    Se valida ACÁ ARRIBA y de una sola vez, NO dentro de los `try/except
    ValueError` del parseo de formatos: si se hace adentro, el `except` del loop
    se come el error del offset y una config con `tz_offset` inválido devuelve
    `None` (leído como "fecha ilegible") en vez de fallar ruidosamente. Fue un bug
    real de este módulo, atrapado por
    `test_mg_dates.py::test_tz_offset_invalido_falla_ruidoso`.
    """
    suf = (tz_offset or "").strip()
    if not suf:
        return ""
    if suf.upper() == "Z":
        return "Z"
    # Tolerar "-0400" y "-04:00"; GitLab acepta ambos, se normaliza al segundo.
    m = re.match(r"^([+-])(\d{2}):?(\d{2})$", suf)
    if not m:
        raise ValueError(
            f"tz_offset={tz_offset!r} inválido; se espera 'Z', '-04:00' o '-0400'."
        )
    return f"{m.group(1)}{m.group(2)}:{m.group(3)}"


def _iso(dt: datetime, tz_offset_normalizado: str) -> str:
    """`YYYY-MM-DDTHH:MM:SS` + el offset YA normalizado por `_normalizar_offset`."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + (tz_offset_normalizado or "")


def mantis_date_to_iso(raw: object, tz_offset: str = "") -> Optional[str]:
    """Convierte una fecha de Mantis (texto) a ISO 8601, o `None` si no se puede.

    `None` NO es un error del caller: significa "Mantis no dio la fecha, o la dio
    en un formato que no reconozco". El caller debe degradarlo a advertencia y
    **no** mandar nada a GitLab, nunca sustituirla por `now()`.
    """
    # Primero el offset: un offset inválido es un error de CONFIG y tiene que
    # explotar siempre, no degradar a `None` (que el caller leería como "Mantis
    # no dio la fecha").
    offset = _normalizar_offset(tz_offset)

    if raw is None:
        return None
    texto = str(raw).strip()
    if not texto:
        return None

    m = _ISO_RE.match(texto)
    if m:
        anio, mes, dia, hh, mm = (int(m.group(i)) for i in range(1, 6))
        ss = int(m.group(6) or 0)
        try:
            dt = datetime(anio, mes, dia, hh, mm, ss)
        except ValueError:
            return None
        # Si el propio valor ya trae offset, se respeta el suyo (es más fiel que
        # el declarado por config: viene del origen).
        propio = m.group(7)
        if propio:
            return _iso(dt, _normalizar_offset(propio))
        return _iso(dt, offset)

    m = _DDMMYY_RE.match(texto)
    if m:
        dia, mes, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        anio = 2000 + yy if yy <= 68 else 1900 + yy
        hh = int(m.group(4) or 0)
        mm = int(m.group(5) or 0)
        try:
            dt = datetime(anio, mes, dia, hh, mm)
        except ValueError:
            return None
        return _iso(dt, offset)

    for fmt in _FORMATOS:
        try:
            dt = datetime.strptime(texto, fmt)
        except ValueError:
            continue
        return _iso(dt, offset)

    return None


def extraer_fechas_issue(issue: dict, tz_offset: str = "") -> dict:
    """`{created_at_iso, updated_at_iso, created_at_raw, updated_at_raw}`.

    Acepta las claves de AMBOS adapters, que no coinciden entre sí:
      * scraping → `date_submitted` / `last_modified`
      * API REST → `created_at` / `updated_at` (ya en ISO)
    Devolver el `*_raw` además del ISO es a propósito: el texto original de
    Mantis se preserva en el bloque de metadata de la descripción, así que el
    dato humano sobrevive incluso si la conversión a ISO falló.
    """
    creado_raw = issue.get("date_submitted") or issue.get("created_at") or ""
    mod_raw = (
        issue.get("last_modified")
        or issue.get("last_updated")
        or issue.get("updated_at")
        or ""
    )
    return {
        "created_at_raw": str(creado_raw).strip(),
        "updated_at_raw": str(mod_raw).strip(),
        "created_at_iso": mantis_date_to_iso(creado_raw, tz_offset),
        "updated_at_iso": mantis_date_to_iso(mod_raw, tz_offset),
    }


def extraer_fecha_nota(comment: dict, tz_offset: str = "") -> Optional[str]:
    """ISO de la fecha de una bugnote, o `None`.

    Acepta `date` (scraping) y `created_at` (API REST) — las dos claves que los
    adapters producen para lo mismo.
    """
    return mantis_date_to_iso(
        comment.get("date") or comment.get("created_at") or "", tz_offset
    )


__all__ = [
    "extraer_fecha_nota",
    "extraer_fechas_issue",
    "mantis_date_to_iso",
]
