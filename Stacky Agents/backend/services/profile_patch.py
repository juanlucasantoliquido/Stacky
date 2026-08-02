"""Plan 296 F4 - El diff del perfil: se ve ANTES de aplicarse.

PURO: sin flask, sin red, sin escritura. `aplicar_sobre` devuelve una COPIA y
nunca muta la base.

P5 - el copiloto SIEMPRE produce un diff que enumera cada cambio con path,
antes, despues, motivo y sensible. Aplicar exige un `confirm_token` derivado del
diff: si el diff cambio, el token no valida y no se escribe nada.

P6 - el copiloto NO toca credenciales. Este es el PRIMER candado (el segundo es
`validate_client_profile`, que usa `_contains_secret_keys` recursivo).
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass

from services.client_profile import _SECRET_KEYS, _deep_merge
from services.profile_completeness import SECCIONES_SENSIBLES

PATCH_VERSION = "1"

#: Las 9 secciones que `validate_client_profile` tipa a dict
#: (client_profile.py:306-316). Una propuesta que ponga otra cosa ahi se RECHAZA
#: antes de armar el cambio.
SECCIONES_TIPADAS_DICT: tuple[str, ...] = (
    "code_layout", "language", "database", "build", "conventions",
    "docs_indexes", "terminology", "extensions", "tracker_state_machine",
)

_AUSENTE = object()


@dataclass(frozen=True)
class CambioPropuesto:
    path: tuple[str, ...]     # ("code_layout", "roots")
    antes: object
    despues: object
    motivo: str               # una frase, en castellano
    sensible: bool            # path[0] in SECCIONES_SENSIBLES

    def to_dict(self) -> dict:
        return {
            "path": list(self.path),
            "path_texto": ".".join(self.path),
            "antes": None if self.antes is _AUSENTE else self.antes,
            "existia": self.antes is not _AUSENTE,
            "despues": self.despues,
            "motivo": self.motivo,
            "sensible": self.sensible,
        }


@dataclass(frozen=True)
class ProfilePatch:
    proyecto: str
    cambios: tuple[CambioPropuesto, ...]
    rechazos: tuple[str, ...]      # propuestas descartadas, con su motivo
    confirm_token: str             # sha256 del patch canonico
    version: str = PATCH_VERSION


def _valor_canonico(valor: object) -> str:
    """Representacion estable entre procesos (json ordenado, sin sorpresas de
    `repr` ni de hash aleatorio)."""
    try:
        return json.dumps(valor, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return str(valor)


def confirm_token_for(cambios) -> str:
    """sha256 de la lista ORDENADA de (path_texto, valor_canonico). Determinista
    y estable entre procesos: no depende del orden de las keys de la propuesta."""
    canonico = sorted(
        (".".join(c.path), _valor_canonico(c.despues)) for c in (cambios or ())
    )
    crudo = json.dumps(canonico, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:32]


def _leer(base: dict, path: tuple[str, ...]):
    nodo = base
    for parte in path:
        if not isinstance(nodo, dict) or parte not in nodo:
            return _AUSENTE
        nodo = nodo[parte]
    return nodo


def _hojas(nodo, prefijo: tuple[str, ...]):
    """Recorre la propuesta y devuelve (path, valor) por cada HOJA. Un dict
    vacio cuenta como hoja (es un valor propuesto, no un contenedor)."""
    if isinstance(nodo, dict) and nodo:
        for clave, valor in nodo.items():
            yield from _hojas(valor, prefijo + (str(clave),))
    else:
        yield prefijo, nodo


def build_profile_patch(*, proyecto: str, base: dict, propuesta: dict) -> ProfilePatch:
    """Arma el diff. NUNCA lanza, NUNCA escribe. Reglas, en orden:

    1. Rechazo de secretos (P6).
    2. Rechazo de no-dict en una de las 9 secciones tipadas.
    3. Sin cambio real, sin entrada (es lo que hace que "no repetir preguntas"
       tambien signifique "no proponer lo ya escrito").
    4. sensible = path[0] in SECCIONES_SENSIBLES.
    """
    base = base if isinstance(base, dict) else {}
    propuesta = propuesta if isinstance(propuesta, dict) else {}

    cambios: list[CambioPropuesto] = []
    rechazos: list[str] = []

    for seccion, valor in propuesta.items():
        seccion = str(seccion)

        # Regla 2 - no-dict en seccion tipada.
        if seccion in SECCIONES_TIPADAS_DICT and not isinstance(valor, dict):
            rechazos.append(
                f"No propongo '{seccion}': esa sección tiene que ser un objeto y "
                f"recibí {type(valor).__name__}."
            )
            continue

        for path, despues in _hojas(valor, (seccion,)):
            # Regla 1 - secretos, antes de cualquier otra cosa.
            if path and str(path[-1]).lower() in _SECRET_KEYS:
                rechazos.append(
                    f"No propongo '{'.'.join(path)}': el perfil nunca guarda credenciales."
                )
                continue

            antes = _leer(base, path)
            # Regla 3 - sin cambio real, sin entrada.
            if antes is not _AUSENTE and antes == despues:
                continue

            sensible = path[0] in SECCIONES_SENSIBLES
            if antes is _AUSENTE:
                motivo = (
                    f"'{'.'.join(path)}' todavía no estaba configurado y el agente lo "
                    f"necesita para trabajar sobre este proyecto."
                )
            else:
                motivo = (
                    f"'{'.'.join(path)}' cambia de lo que hay hoy a lo que respondiste "
                    f"en la conversación."
                )
            cambios.append(CambioPropuesto(
                path=path, antes=antes, despues=despues, motivo=motivo, sensible=sensible
            ))

    cambios_ordenados = tuple(sorted(cambios, key=lambda c: ".".join(c.path)))
    return ProfilePatch(
        proyecto=proyecto,
        cambios=cambios_ordenados,
        rechazos=tuple(rechazos),
        confirm_token=confirm_token_for(cambios_ordenados),
    )


def patch_to_dict(p: ProfilePatch) -> dict:
    return {
        "proyecto": p.proyecto,
        "cambios": [c.to_dict() for c in p.cambios],
        "rechazos": list(p.rechazos),
        "confirm_token": p.confirm_token,
        "version": p.version,
        "sensibles": sorted({c.path[0] for c in p.cambios if c.sensible}),
    }


def patch_from_dict(d: dict | None) -> ProfilePatch:
    """Reconstruye un patch recibido por HTTP. NUNCA lanza. El `confirm_token`
    NO se toma del cuerpo: F5 lo RECALCULA desde los cambios (paso 5)."""
    d = d if isinstance(d, dict) else {}
    cambios: list[CambioPropuesto] = []
    for crudo in (d.get("cambios") or []):
        if not isinstance(crudo, dict):
            continue
        path = tuple(str(x) for x in (crudo.get("path") or ()))
        if not path:
            continue
        existia = bool(crudo.get("existia"))
        cambios.append(CambioPropuesto(
            path=path,
            antes=crudo.get("antes") if existia else _AUSENTE,
            despues=crudo.get("despues"),
            motivo=str(crudo.get("motivo") or ""),
            sensible=path[0] in SECCIONES_SENSIBLES,
        ))
    ordenados = tuple(sorted(cambios, key=lambda c: ".".join(c.path)))
    return ProfilePatch(
        proyecto=str(d.get("proyecto") or ""),
        cambios=ordenados,
        rechazos=tuple(str(x) for x in (d.get("rechazos") or [])),
        confirm_token=confirm_token_for(ordenados),
        version=str(d.get("version") or PATCH_VERSION),
    )


def _anidar(cambios) -> dict:
    salida: dict = {}
    for c in cambios or ():
        nodo = salida
        for parte in c.path[:-1]:
            siguiente = nodo.get(parte)
            if not isinstance(siguiente, dict):
                siguiente = {}
                nodo[parte] = siguiente
            nodo = siguiente
        nodo[c.path[-1]] = copy.deepcopy(c.despues)
    return salida


def aplicar_sobre(base: dict, p: ProfilePatch) -> dict:
    """PURO: devuelve una copia con el patch aplicado. NO escribe, NO muta base."""
    base = base if isinstance(base, dict) else {}
    return _deep_merge(copy.deepcopy(base), _anidar(p.cambios))
