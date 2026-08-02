"""Plan 296 F2 - Completitud del client_profile y banco de preguntas.

PURO: sin flask, sin red, sin escritura, sin modelo. El motor conversacional es
DETERMINISTA (P3): el banco de preguntas y la deteccion de faltantes salen del
schema del perfil y de fuentes que ya existen. Por eso los 3 runtimes obtienen
EXACTAMENTE el mismo resultado.

C1 - `procesos_detectados` es un PARAMETRO, no una llamada. La deteccion de
procesos vive en una RUTA FLASK (autodetect_process_catalog) y este modulo no
puede importar la capa web. El endpoint de F3 arma la tupla desde las mismas dos
fuentes de services/ que usa esa ruta y se la pasa. Con la tupla vacia la
pregunta degrada a texto libre: VISIBLE, nunca muda. Misma disciplina que ya se
aplicaba a `estados_validos`.

QUE PERFIL SE MIDE: la presencia de secciones, la validacion y las
inconsistencias se calculan sobre el perfil REALMENTE GUARDADO
(`load_client_profile`), no sobre el efectivo. `load_effective_client_profile`
cae al template del tracker cuando no hay perfil (client_profile.py:388-402), y
ese template TRAE las tres secciones requeridas pobladas: medir sobre el
efectivo diria "0 faltantes" para un proyecto sin configurar y volveria
insatisfacibles los criterios K3/K4 del plan. El efectivo igual viaja en el
estado, bajo la clave `perfil`, porque es lo que el copiloto muestra como "ya
deducido".
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from services.client_profile import (
    _OPTIONAL_SECTIONS,
    _REQUIRED_SECTIONS,
    get_project_tracker_type,
    has_client_profile,
    load_client_profile,
    load_effective_client_profile,
    validate_client_profile,
)

#: Espejo de client_profile._REQUIRED_SECTIONS (:48-52).
SECCIONES_REQUERIDAS: tuple[str, ...] = tuple(_REQUIRED_SECTIONS)

#: Espejo de client_profile._OPTIONAL_SECTIONS (:54-61).
SECCIONES_OPCIONALES: tuple[str, ...] = tuple(_OPTIONAL_SECTIONS)

#: Secciones cuyo cambio exige confirmacion explicita por seccion (F4/F5).
SECCIONES_SENSIBLES: tuple[str, ...] = ("tracker_state_machine", "state_flow", "database")

#: Catalogo de procesos: NO es una de las 9 secciones tipadas del perfil, es una
#: lista. Se pregunta igual porque es lo que alimenta el grounding.
SECCION_PROCESOS = "process_catalog"

#: Sufijo EXACTO del warning que emite client_profile.py:304. Es el unico
#: indicador que discrimina, porque validate_client_profile({}).ok ya es True.
_SUFIJO_AUSENTE = " ausente — el agente preguntará al operador."
_PREFIJO_PERFIL = "client_profile."


@dataclass(frozen=True)
class Pregunta:
    id: str                          # "code_layout.roots"
    seccion: str                     # "code_layout"
    texto: str                       # castellano, sin jerga
    tipo: str                        # "texto" | "lista" | "eleccion" | "si_no"
    opciones: tuple[str, ...] = ()   # solo para tipo "eleccion"
    obligatoria: bool = True
    motivo: str = ""                 # por que se pregunta, en una frase

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "seccion": self.seccion,
            "texto": self.texto,
            "tipo": self.tipo,
            "opciones": list(self.opciones),
            "obligatoria": self.obligatoria,
            "motivo": self.motivo,
        }


@dataclass(frozen=True)
class _Molde:
    """Molde declarativo de una pregunta. `tipo` puede degradar a texto libre."""
    id: str
    seccion: str
    texto: str
    tipo: str
    motivo: str
    obligatoria: bool = True
    fuente_opciones: str = ""  # "estados_validos" | "procesos_detectados" | ""
    extra: tuple[str, ...] = field(default=())


_MOLDES: tuple[_Molde, ...] = (
    # ── Requeridas, en el orden de SECCIONES_REQUERIDAS ──────────────────────
    _Molde(
        id="code_layout.roots",
        seccion="code_layout",
        texto="¿En qué carpetas del repositorio vive el código de este proyecto?",
        tipo="lista",
        motivo=("El agente necesita saber dónde mirar antes de proponer un cambio; "
                "sin esto lee de más y acierta de menos."),
    ),
    _Molde(
        id="language.primary",
        seccion="language",
        texto="¿En qué lenguaje está escrito principalmente este proyecto?",
        tipo="texto",
        motivo="Define el estilo, las convenciones y las herramientas que el agente asume.",
    ),
    _Molde(
        id="tracker_state_machine.functional.input_states",
        seccion="tracker_state_machine",
        texto=("¿Desde qué estado del tablero tiene que tomar un ticket el agente "
               "funcional?"),
        tipo="eleccion",
        fuente_opciones="estados_validos",
        motivo=("Es lo que decide qué tickets levanta cada agente y a qué estado los "
                "deja. Sin esto, el ruteo queda a mano."),
    ),
    # ── Opcionales, en el orden de SECCIONES_OPCIONALES ──────────────────────
    _Molde(
        id="database.engine",
        seccion="database",
        texto="¿Qué motor de base de datos usa este proyecto?",
        tipo="texto",
        obligatoria=False,
        motivo="Cambia el dialecto de SQL que el agente escribe y valida.",
    ),
    _Molde(
        id="build.command",
        seccion="build",
        texto="¿Con qué comando se compila o se construye este proyecto?",
        tipo="texto",
        obligatoria=False,
        motivo="Permite que el agente verifique su propio cambio antes de entregarlo.",
    ),
    _Molde(
        id="conventions.branch_naming",
        seccion="conventions",
        texto="¿Cómo se nombran las ramas y los mensajes de cambio en tu equipo?",
        tipo="texto",
        obligatoria=False,
        motivo="Evita que el agente proponga nombres que tu equipo después tiene que corregir.",
    ),
    _Molde(
        id="docs_indexes.roots",
        seccion="docs_indexes",
        texto="¿Dónde está la documentación de este proyecto?",
        tipo="lista",
        obligatoria=False,
        motivo="Es de dónde salen las citas cuando el agente explica una decisión.",
    ),
    _Molde(
        id="terminology.glossary",
        seccion="terminology",
        texto="¿Qué términos propios de este cliente conviene que el agente no traduzca?",
        tipo="lista",
        obligatoria=False,
        motivo="Evita que el agente renombre conceptos que tu equipo ya tiene nombrados.",
    ),
    _Molde(
        id="extensions.notes",
        seccion="extensions",
        texto="¿Hay algo particular de este proyecto que el agente deba tener siempre presente?",
        tipo="texto",
        obligatoria=False,
        motivo="Es el lugar para lo que no entra en ninguna de las otras secciones.",
    ),
    _Molde(
        id="process_catalog.names",
        seccion=SECCION_PROCESOS,
        texto="¿Cuáles son los procesos de negocio de este cliente?",
        tipo="eleccion",
        fuente_opciones="procesos_detectados",
        obligatoria=False,
        motivo=("Es lo que le permite al agente hablar en los nombres de tu negocio y no "
                "en los del código."),
    ),
)


# ── Estado del perfil ────────────────────────────────────────────────────────

def _seccion_presente(perfil: dict, seccion: str) -> bool:
    """Presente = esta, es dict y NO esta vacia. Un `{}` cuenta como AUSENTE:
    es el caso real de un perfil recien sembrado y es lo que hace honesto a K4."""
    valor = perfil.get(seccion)
    return isinstance(valor, dict) and bool(valor)


def _procesos_presentes(perfil: dict) -> bool:
    valor = perfil.get(SECCION_PROCESOS)
    return isinstance(valor, (list, tuple)) and bool(valor)


def _seccion_de_mensaje(mensaje: str) -> str:
    """Regla determinista, cubre las CUATRO formas reales (C13). Nunca pierde
    un mensaje: lo que no encaja cae en "general"."""
    primer_token = (mensaje or "").strip().split(" ", 1)[0]
    if primer_token.startswith(_PREFIJO_PERFIL):
        resto = primer_token[len(_PREFIJO_PERFIL):]
        candidata = resto.split(".", 1)[0]
        if candidata:
            return candidata
        return "general"
    componente = primer_token.split(".", 1)[0]
    if componente in SECCIONES_REQUERIDAS + SECCIONES_OPCIONALES + ("state_flow",):
        return componente
    return "general"


def _inconsistencias(validacion: dict) -> list[dict]:
    salida: list[dict] = []
    for nivel, mensajes in (
        ("error", validacion.get("errors") or []),
        ("warning", validacion.get("warnings") or []),
    ):
        for mensaje in mensajes:
            seccion = _seccion_de_mensaje(mensaje)
            sensible = ("no debe contener secretos" in mensaje) or (
                seccion in SECCIONES_SENSIBLES
            )
            salida.append({
                "seccion": seccion,
                "detalle": mensaje,
                "origen": "validacion",
                "nivel": nivel,
                "sensible": sensible,
            })
    return salida


def _warnings_de_seccion_ausente(validacion: dict) -> list[str]:
    """C12 - extrae las secciones nombradas por los warnings de la forma EXACTA
    `client_profile.<seccion> ausente — el agente preguntará al operador.`"""
    secciones: list[str] = []
    for w in validacion.get("warnings") or []:
        if w.startswith(_PREFIJO_PERFIL) and w.endswith(_SUFIJO_AUSENTE):
            seccion = w[len(_PREFIJO_PERFIL):-len(_SUFIJO_AUSENTE)].strip()
            if seccion:
                secciones.append(seccion)
    return secciones


def estado_perfil(project_name: str) -> dict:
    """Foto determinista del perfil de un proyecto. NUNCA lanza."""
    guardado = load_client_profile(project_name) or {}
    validacion = validate_client_profile(guardado).to_dict()

    presentes = [s for s in SECCIONES_REQUERIDAS + SECCIONES_OPCIONALES
                 if _seccion_presente(guardado, s)]
    if _procesos_presentes(guardado):
        presentes.append(SECCION_PROCESOS)

    return {
        "proyecto": project_name,
        "tracker_type": get_project_tracker_type(project_name),
        "tiene_perfil": has_client_profile(project_name),
        "perfil": load_effective_client_profile(project_name),
        "perfil_guardado": guardado,
        "secciones_presentes": presentes,
        "secciones_faltantes_requeridas": [
            s for s in SECCIONES_REQUERIDAS if not _seccion_presente(guardado, s)
        ],
        "secciones_faltantes_opcionales": [
            s for s in SECCIONES_OPCIONALES if not _seccion_presente(guardado, s)
        ],
        "validacion": validacion,
        "warnings_de_seccion_ausente": _warnings_de_seccion_ausente(validacion),
        "inconsistencias": _inconsistencias(validacion),
    }


# ── Banco de preguntas ───────────────────────────────────────────────────────

def preguntas_pendientes(
    estado: dict,
    *,
    estados_validos: tuple[str, ...] = (),
    tipos_work_item: tuple[str, ...] = (),
    procesos_detectados: tuple[str, ...] = (),
) -> list[Pregunta]:
    """Preguntas que faltan. EXCLUYE toda seccion ya presente (corazon de K4).

    Los tres parametros de contexto los provee el endpoint de F3: este modulo no
    puede importar la capa web. Con cualquiera de ellos vacio la pregunta
    correspondiente degrada a texto libre -- VISIBLE, nunca muda.
    """
    presentes = set(estado.get("secciones_presentes") or [])
    fuentes = {
        "estados_validos": tuple(estados_validos or ()),
        "procesos_detectados": tuple(procesos_detectados or ()),
    }

    salida: list[Pregunta] = []
    for molde in _MOLDES:
        if molde.seccion in presentes:
            continue
        opciones: tuple[str, ...] = ()
        tipo = molde.tipo
        if molde.fuente_opciones:
            opciones = fuentes.get(molde.fuente_opciones, ())
            if not opciones:
                tipo = "texto"  # degradacion VISIBLE
        motivo = molde.motivo
        if molde.seccion == "tracker_state_machine" and tipos_work_item:
            motivo = (
                f"{motivo} Tipos de ticket detectados en este proyecto: "
                f"{', '.join(tipos_work_item)}."
            )
        salida.append(Pregunta(
            id=molde.id,
            seccion=molde.seccion,
            texto=molde.texto,
            tipo=tipo,
            opciones=opciones,
            obligatoria=molde.obligatoria,
            motivo=motivo,
        ))

    # Obligatorias primero, respetando el orden de SECCIONES_REQUERIDAS (que es
    # el orden en que estan declarados los moldes). `sorted` es estable.
    return sorted(salida, key=lambda p: 0 if p.obligatoria else 1)


def proxima_pregunta(
    estado: dict, ya_respondidas: tuple[str, ...] = (), **kw
) -> Pregunta | None:
    """La siguiente pregunta, o None si no falta ninguna. NUNCA lanza."""
    respondidas = set(ya_respondidas or ())
    for pregunta in preguntas_pendientes(estado, **kw):
        if pregunta.id not in respondidas:
            return pregunta
    return None


# ── Completitud ──────────────────────────────────────────────────────────────

def completitud(estado: dict) -> dict:
    """Porcentaje sobre las REQUERIDAS unicamente, y el veredicto de si el perfil
    ya sirve. `listo_para_usar` incluye el AND con los warnings de seccion
    ausente (C12): sin ese tercer termino el indicador no discrimina, porque
    `validate_client_profile({}).ok` ya es True hoy."""
    presentes = set(estado.get("secciones_presentes") or [])
    requeridas_ok = sum(1 for s in SECCIONES_REQUERIDAS if s in presentes)
    opcionales_ok = sum(1 for s in SECCIONES_OPCIONALES if s in presentes)
    total_req = len(SECCIONES_REQUERIDAS)

    porcentaje = 0
    if total_req:
        porcentaje = int(math.floor(requeridas_ok / total_req * 100))

    validacion_ok = bool((estado.get("validacion") or {}).get("ok") is True)
    sin_warnings_ausente = not (estado.get("warnings_de_seccion_ausente") or [])

    return {
        "requeridas_ok": requeridas_ok,
        "requeridas_total": total_req,
        "opcionales_ok": opcionales_ok,
        "opcionales_total": len(SECCIONES_OPCIONALES),
        "porcentaje": porcentaje,
        "listo_para_usar": (
            requeridas_ok == total_req and validacion_ok and sin_warnings_ausente
        ),
    }
