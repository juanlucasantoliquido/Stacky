"""Plan 288 F7 — Que modelos tiene ESTA cuenta de Claude Code, leido del disco.

CUATRO REGLAS DURAS:
1. **Nunca invoca un modelo ni sale a la red.** Lee dos archivos de texto locales.
2. **Nunca resta.** Lo leido se SUMA al catalogo; nunca quita un id que ya estaba.
3. **Nunca propaga una excepcion.** Sin archivos, con permisos denegados o con un
   JSON roto, devuelve `disponible=False` con el motivo y el catalogo queda igual.
4. **Nunca admite un id que Stacky no pueda ejecutar.** El archivo de estadisticas
   del programa registra TODO lo que la sesion uso, incluidos modelos de otros
   proveedores y modelos locales. Sin filtro, el selector de Claude Code mostraria
   ids que ese programa no puede correr. Ver `_admisible` y el Plan 288 §4.4(b-bis).

POR QUE ESTA FUENTE Y NO OTRA (medido el 2026-08-02, ver Plan 288 §4.4):
  - El programa instalado (2.1.220) NO tiene subcomando de listado: los 3
    candidatos de model_probe.py dan `unknown option`. Por eso el `reason`
    `no_candidate_worked` de la sonda es el valor ESPERADO en el programa 2.x,
    no una averia.
  - La ruta de listado del proveedor refleja una clave de interfaz, no una
    suscripcion; aca el motor corre con la sesion del programa
    (`oauthAccount.billingType == "stripe_subscription"`).
  - Estos dos archivos SI existen y SI traen el dato.

LO QUE ESTO NO ES: no es una consulta a la suscripcion. Es lo que esta instalacion
registro sobre esta cuenta, filtrado a lo ejecutable. Ver Plan 288 §4.4(c).
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
import re
from pathlib import Path

from config import config as _cfg

logger = logging.getLogger("stacky.services.claude_account_models")

__all__ = [
    "LecturaCuenta", "leer_cuenta_claude", "normalizar_id_modelo",
    "ruta_config_claude", "ruta_stats_claude",
]

# El programa respeta CLAUDE_CONFIG_DIR para mover ~/.claude a otro lado.
_ENV_DIR = "CLAUDE_CONFIG_DIR"
# Sufijo de fecha que el programa agrega a algunos ids: claude-haiku-4-5-20251001
_SUFIJO_FECHA = re.compile(r"-\d{8}$")
# Variante de ventana de contexto: claude-fable-5[1m]
_SUFIJO_VARIANTE = re.compile(r"\[[^\]]+\]$")
# Regla 5.a del filtro de admision.
_PREFIJO_ADMISIBLE = "claude-"


@dataclass(frozen=True)
class LecturaCuenta:
    disponible: bool
    motivo: str                 # ok | flag_apagada | sin_archivos | json_ilegible
    suscripcion: str            # p. ej. "claude_max"; "" si no se pudo leer
    nivel_de_limite: str        # p. ej. "default_claude_max_20x"; "" si no se pudo leer
    usados: tuple[str, ...]     # ids NORMALIZADOS y ADMISIBLES que esta cuenta ejecuto
    ofrecidos: tuple[str, ...]  # ids NORMALIZADOS y ADMISIBLES que el programa ofrece de mas
    etiquetas: dict             # id_normalizado -> rotulo que el propio programa le pone
    omitidos: tuple             # ((id_crudo, motivo), ...) — TODO lo que el filtro descarto
    crudos: tuple[str, ...]     # ids tal cual venian, solo para diagnostico


def _dir_configurado() -> Path | None:
    crudo = (os.environ.get(_ENV_DIR) or "").strip()
    return Path(crudo) if crudo else None


def _modo_prueba() -> bool:
    return os.environ.get("STACKY_TEST_MODE", "").strip().lower() in ("1", "true", "yes")


def ruta_config_claude() -> Path:
    """~/.claude.json, o el equivalente si CLAUDE_CONFIG_DIR esta definido."""
    base = _dir_configurado()
    if base is not None:
        return base / ".claude.json"
    return Path.home() / ".claude.json"


def ruta_stats_claude() -> Path:
    """~/.claude/stats-cache.json, o el equivalente bajo CLAUDE_CONFIG_DIR."""
    base = _dir_configurado()
    if base is not None:
        return base / "stats-cache.json"
    return Path.home() / ".claude" / "stats-cache.json"


def normalizar_id_modelo(crudo: str) -> str:
    """Saca el sufijo de fecha y el de variante. NO toca nada mas.

    'claude-haiku-4-5-20251001' -> 'claude-haiku-4-5'
    'claude-fable-5[1m]'        -> 'claude-fable-5'
    'claude-opus-5'             -> 'claude-opus-5'
    'qwen2.5-coder:7b'          -> 'qwen2.5-coder:7b'   (no se toca; el filtro lo rechaza)
    """
    val = (crudo or "").strip()
    # La variante va primero: un id puede traer fecha Y variante.
    val = _SUFIJO_VARIANTE.sub("", val)
    val = _SUFIJO_FECHA.sub("", val)
    return val


def _admisible(id_normalizado: str) -> tuple[bool, str]:
    """Filtro de admision. Devuelve (entra, motivo_si_no_entra).

    Condiciones (a) y (b) del Plan 288 §6.F7 regla 5. La (c) — "no esta ya en el
    catalogo" — la aplica `_merge_cuenta`, que es quien conoce el catalogo, y por
    definicion NO cuenta como omitido.
    """
    # (a) tiene que ser un modelo de Claude Code.
    if not id_normalizado.startswith(_PREFIJO_ADMISIBLE):
        return False, "otro_proveedor"
    # (b) Stacky tiene que poder ejecutarlo de verdad: o el clamp no lo toca, o
    #     esta explicitamente autorizado para eleccion puntual del operador.
    #     Import perezoso: este modulo no depende de nada de Stacky salvo config.
    from services import llm_router

    if not (
        llm_router.clamp_model(id_normalizado) == id_normalizado
        or llm_router.is_opus_allowlisted(id_normalizado)
    ):
        return False, "bloqueado_por_politica_de_costo"
    return True, ""


def _leer_json(ruta: Path) -> tuple[dict | None, bool]:
    """Devuelve (datos, hubo_error_de_formato). Nunca lanza.

    (None, False) = el archivo no existe.
    (None, True)  = existe pero no se pudo interpretar (o no se pudo abrir).
    """
    try:
        if not ruta.exists():
            return None, False
    except OSError:
        return None, True
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — JSON roto, permisos, encoding
        logger.debug("claude_account_models: no se pudo leer %s", ruta, exc_info=True)
        return None, True
    return (datos if isinstance(datos, dict) else {}), False


def _ids_de_opciones(valor) -> list:
    """Ids de additionalModelOptionsCache / modelAccessCache.

    Tolera lista vacia, lista de strings y lista de objetos con `id` o `value`.
    """
    salida: list = []
    if not isinstance(valor, list):
        return salida
    for item in valor:
        if isinstance(item, str):
            if item.strip():
                salida.append(item.strip())
        elif isinstance(item, dict):
            crudo = item.get("value") or item.get("id")
            if isinstance(crudo, str) and crudo.strip():
                salida.append(crudo.strip())
    return salida


def leer_cuenta_claude() -> LecturaCuenta:
    """Lee del disco local que modelos tiene esta cuenta. Nunca lanza."""
    vacia = {
        "suscripcion": "", "nivel_de_limite": "", "usados": (), "ofrecidos": (),
        "etiquetas": {}, "omitidos": (), "crudos": (),
    }

    # Regla 1 — flag apagada: NO se abre ningun archivo.
    if not getattr(_cfg, "STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED", True):
        return LecturaCuenta(disponible=False, motivo="flag_apagada", **vacia)

    # Bajo modo de prueba este lector SOLO mira un directorio EXPLICITO. Sin esa
    # barrera, cualquier prueba del repositorio que refresque el catalogo leeria
    # el ~/.claude.json real de quien la corre: no es determinista (el archivo
    # cambia solo) y ademas mete datos de una cuenta real en una corrida ajena.
    # Rompio de hecho a tests/test_plan159_model_catalog_loader.py::
    # test_cache_reused_within_ttl, que cuenta lecturas de disco.
    #
    # OJO — NO es la guarda de `_merge_probe` (Plan 288 C3): `_merge_cuenta` SI
    # corre bajo modo de prueba y publica `cuenta` igual. Lo unico que exige es
    # que la prueba diga DE DONDE leer, que es justamente lo que el plan manda
    # (tmp_path + CLAUDE_CONFIG_DIR). Lo verifica el caso
    # `cuenta_cableada_bajo_modo_de_prueba`.
    if _modo_prueba() and _dir_configurado() is None:
        return LecturaCuenta(disponible=False, motivo="sin_archivos", **vacia)

    try:
        stats, stats_roto = _leer_json(ruta_stats_claude())
        cfg_json, cfg_roto = _leer_json(ruta_config_claude())

        # Regla 2 — ninguno de los dos existe.
        if stats is None and cfg_json is None:
            motivo = "json_ilegible" if (stats_roto or cfg_roto) else "sin_archivos"
            return LecturaCuenta(disponible=False, motivo=motivo, **vacia)

        # ── Regla 4 — ids crudos, sin repetir, en orden de aparicion ──────────
        crudos_usados: list = []
        crudos_ofrecidos: list = []
        etiquetas: dict = {}

        if stats:
            uso = stats.get("modelUsage")
            if isinstance(uso, dict):
                crudos_usados.extend(k for k in uso if isinstance(k, str) and k.strip())
            diario = stats.get("dailyModelTokens")
            if isinstance(diario, list):
                for dia in diario:
                    por_modelo = (dia or {}).get("tokensByModel") if isinstance(dia, dict) else None
                    if isinstance(por_modelo, dict):
                        crudos_usados.extend(
                            k for k in por_modelo if isinstance(k, str) and k.strip()
                        )

        suscripcion = ""
        nivel_de_limite = ""
        if cfg_json:
            extra = cfg_json.get("additionalModelOptionsCache")
            crudos_ofrecidos.extend(_ids_de_opciones(extra))
            crudos_ofrecidos.extend(_ids_de_opciones(cfg_json.get("modelAccessCache")))
            # Regla 7 — la etiqueta no se inventa.
            if isinstance(extra, list):
                for item in extra:
                    if not isinstance(item, dict):
                        continue
                    crudo = item.get("value") or item.get("id")
                    rotulo = item.get("label")
                    if isinstance(crudo, str) and isinstance(rotulo, str) and rotulo.strip():
                        etiquetas[normalizar_id_modelo(crudo)] = rotulo
            # Regla 8 — SOLO estos dos campos. Nada de emailAddress, accountUuid,
            # displayName, organizationName ni organizationUuid.
            cuenta = cfg_json.get("oauthAccount")
            if isinstance(cuenta, dict):
                suscripcion = str(cuenta.get("organizationType") or "")
                nivel_de_limite = str(cuenta.get("organizationRateLimitTier") or "")

        # ── Regla 5 — filtro de admision ─────────────────────────────────────
        usados: list = []
        ofrecidos: list = []
        omitidos: list = []
        vistos_crudos: set = set()
        vistos_norm: set = set()

        for crudo, destino in (
            *((c, usados) for c in crudos_usados),
            *((c, ofrecidos) for c in crudos_ofrecidos),
        ):
            if crudo in vistos_crudos:
                continue
            vistos_crudos.add(crudo)
            norm = normalizar_id_modelo(crudo)
            entra, motivo_no = _admisible(norm)
            if not entra:
                omitidos.append((crudo, motivo_no))
                continue
            if norm in vistos_norm:
                continue
            vistos_norm.add(norm)
            destino.append(norm)

        # Las etiquetas solo valen para lo que efectivamente entro.
        etiquetas = {k: v for k, v in etiquetas.items() if k in vistos_norm}

        motivo = "json_ilegible" if (stats_roto or cfg_roto) else "ok"
        return LecturaCuenta(
            disponible=True,
            motivo=motivo,
            suscripcion=suscripcion,
            nivel_de_limite=nivel_de_limite,
            usados=tuple(usados),
            ofrecidos=tuple(ofrecidos),
            etiquetas=etiquetas,
            omitidos=tuple(omitidos),
            crudos=tuple(vistos_crudos_en_orden(crudos_usados, crudos_ofrecidos)),
        )
    except Exception:  # noqa: BLE001 — Regla 3: nunca propaga
        logger.debug("claude_account_models: lectura fallo (no critico)", exc_info=True)
        return LecturaCuenta(disponible=False, motivo="json_ilegible", **vacia)


def vistos_crudos_en_orden(usados: list, ofrecidos: list) -> list:
    """Ids crudos sin repetir, conservando el orden de aparicion (diagnostico)."""
    salida: list = []
    vistos: set = set()
    for crudo in (*usados, *ofrecidos):
        if crudo not in vistos:
            vistos.add(crudo)
            salida.append(crudo)
    return salida
