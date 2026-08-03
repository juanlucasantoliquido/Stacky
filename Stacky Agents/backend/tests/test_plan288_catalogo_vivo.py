"""tests/test_plan288_catalogo_vivo.py — Plan 288 F4 / F5 / F6 / F7.0 / F8 / F11.

Dos invariantes congelados:
  (a) el catalogo ofrece los modelos vigentes de la familia Claude 5;
  (b) TODO lo que el catalogo EFECTIVO ofrece, el camino de ejecucion lo respeta.

(b) es lo que impide que este plan se convierta en "aparece y miente": un id de
tier alto que llegue al catalogo sin estar en la lista de autorizados se ejecuta
como claude-sonnet-5 mientras la pantalla sigue mostrando el otro.

CATALOGO EFECTIVO = lo que devuelve load_model_catalog() DESPUES de fusionar la
sonda y la cuenta local (Plan 288 seccion 4.1). Ninguna prueba de este archivo
lee el disco real del operador: la cuenta se siembra en un tmp_path apuntado por
CLAUDE_CONFIG_DIR.
"""
import json
from pathlib import Path

import pytest

from harness import pricing
from services import llm_router, model_catalog
from services.claude_code_cli_runner import allow_opus_for_run


# ── Foto de F0.1 (medida 2026-08-02, ANTES de tocar nada) ────────────────────
# Es la pata de PRESENCIA de test_ausencia_y_presencia_...: ningun id de esta
# lista puede desaparecer del catalogo.
IDS_BASELINE_F0_1 = {
    "claude-sonnet-5",
    "claude-opus-4-8",
    "claude-haiku-4-5",
    "claude-sonnet-4-6",
}

# El modelo que esta cuenta YA ejecuto (4.321.237 unidades el 2026-07-28) y que
# el catalogo no ofrecia. Ver Plan 288 seccion 4.4(b).
ID_NUEVO = "claude-opus-5"

# Copia congelada de los bloques que este plan NO puede tocar (Plan 288 F11).
CODEX_CONGELADO = {
    "source": "static_config_file",
    "default_model": "",
    "default_effort": None,
    "models": [{"id": "", "label": "Automático (decide Codex CLI)", "recommended": True}],
    "efforts": [],
    "effort_support": {},
    "note": (
        "Codex CLI no soporta --effort como flag; el nivel se traduce internamente "
        "a presupuesto de turnos (ver codex_cli_runner.py:576-591)."
    ),
}
COPILOT_CONGELADO = {
    "source": "live_introspection",
    "default_model": None,
    "default_effort": None,
    "models": [],
    "efforts": [],
    "effort_support": {},
    "note": (
        "Poblado en runtime desde copilot_bridge.list_copilot_models() con caché TTL; "
        "ver campo 'error' de la respuesta del endpoint si la introspección falla."
    ),
}


@pytest.fixture(autouse=True)
def _reset_catalog_caches():
    """El repo tiene contaminacion de orden en los caches modulo-level."""
    model_catalog._cache.update(data=None, loaded_at=0.0, mtime=None)
    model_catalog._copilot_cache.update(models=None, loaded_at=0.0, error=None)
    yield
    model_catalog._cache.update(data=None, loaded_at=0.0, mtime=None)
    model_catalog._copilot_cache.update(models=None, loaded_at=0.0, error=None)


def _archivo() -> dict:
    """El catalogo tal cual esta en disco (sin sonda ni cuenta)."""
    return json.loads(model_catalog._catalog_path().read_text(encoding="utf-8"))


def _ids_del_archivo() -> list:
    return [m["id"] for m in _archivo()["runtimes"]["claude_code_cli"]["models"]]


def _ids_del_respaldo() -> list:
    bloque = model_catalog._EMERGENCY_FALLBACK["runtimes"]["claude_code_cli"]
    return [m["id"] for m in bloque["models"]]


def catalogo_efectivo(tmp_path: Path, monkeypatch, cuenta: dict | None = None) -> dict:
    """Arma el catalogo EFECTIVO de forma determinista.

    Siembra una cuenta controlada en un tmp_path y apunta CLAUDE_CONFIG_DIR ahi,
    para que el lector de Plan 288 F7 nunca toque el disco real del operador.
    """
    dir_cuenta = tmp_path / "claude_config"
    dir_cuenta.mkdir(parents=True, exist_ok=True)
    datos = cuenta or {}
    (dir_cuenta / ".claude.json").write_text(
        json.dumps(datos.get("config", {})), encoding="utf-8"
    )
    (dir_cuenta / "stats-cache.json").write_text(
        json.dumps(datos.get("stats", {})), encoding="utf-8"
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(dir_cuenta))
    return model_catalog.load_model_catalog(force_refresh=True)


def _ids_efectivos(catalogo: dict) -> list:
    bloque = (catalogo.get("runtimes") or {}).get("claude_code_cli") or {}
    return [m.get("id") for m in (bloque.get("models") or [])]


# ── F4 / F5 — paridad del catalogo ───────────────────────────────────────────

def test_paridad_el_catalogo_ofrece_los_modelos_vigentes_de_claude_5():
    """El bloque claude_code_cli ofrece claude-opus-5 ADEMAS de los 4 que tenia."""
    ids = _ids_del_archivo()
    assert ID_NUEVO in ids, (
        f"{ID_NUEVO} no esta en el catalogo. Esta cuenta ya lo ejecuto "
        f"(Plan 288 seccion 4.4(b)) y el selector no lo ofrece. Ids: {ids}"
    )
    # Dos patas: los 4 de siempre siguen ahi.
    assert IDS_BASELINE_F0_1.issubset(set(ids))


def test_paridad_el_respaldo_de_emergencia_no_ofrece_menos_que_el_archivo():
    """El respaldo NUNCA puede ofrecer menos que el archivo (model_catalog.py:28-30)."""
    del_archivo = set(_ids_del_archivo())
    del_respaldo = set(_ids_del_respaldo())
    faltantes = del_archivo - del_respaldo
    assert not faltantes, (
        f"El respaldo de emergencia ofrece MENOS que el archivo: falta {sorted(faltantes)}. "
        "Si el JSON no se puede leer, el operador veria una lista mutilada."
    )


# ── F4 / F6 — el invariante central: lo ofrecido se ejecuta ───────────────────

def test_ejecutable_todo_modelo_del_catalogo_efectivo_sobrevive_la_eleccion_explicita(
    tmp_path, monkeypatch
):
    """Para CADA id del catalogo EFECTIVO: o el runner lo autoriza, o el clamp no lo toca.

    Si falla, el catalogo ofrece algo que el runner degrada en silencio: la
    pantalla muestra un modelo y se ejecuta otro.
    """
    catalogo = catalogo_efectivo(tmp_path, monkeypatch)
    ids = _ids_efectivos(catalogo)
    assert ids, "el catalogo efectivo quedo vacio: el test no probaria nada"

    degradados = [
        mid
        for mid in ids
        if mid
        and not (
            allow_opus_for_run(mid, "developer") is True
            or llm_router.clamp_model(mid) == mid
        )
    ]
    assert not degradados, (
        f"El catalogo EFECTIVO ofrece {degradados}, que el camino de eleccion "
        f"explicita degrada en silencio a {llm_router.CLAUDE_CAP_MODEL}. "
        "O se agregan a _OPUS_ALLOWLIST, o no se ofrecen."
    )


def test_ejecutable_el_ruteo_automatico_sigue_capado_en_sonnet():
    """CONTRA-PRUEBA, misma corrida: F6 no puede aflojar el cap automatico."""
    # Sin allow_opus, opus-5 sigue capado.
    assert llm_router.clamp_model(ID_NUEVO) == llm_router.CLAUDE_CAP_MODEL
    # Y fable sigue capado INCLUSO con allow_opus=True: su politica no se toca.
    assert (
        llm_router.clamp_model("claude-fable-5", allow_opus=True)
        == llm_router.CLAUDE_CAP_MODEL
    )
    # El agente de DevOps nunca escala de tier, aunque el id este autorizado.
    assert allow_opus_for_run(ID_NUEVO, "devops") is False


def test_ausencia_y_presencia_ningun_modelo_desaparecio():
    """DOS PATAS: nada de la foto de F0.1 se fue, y no entraron ids muertos."""
    ids = set(_ids_del_archivo())
    # PRESENCIA — la regla del repo es UNION, nunca resta.
    assert IDS_BASELINE_F0_1.issubset(ids), (
        f"desaparecieron {sorted(IDS_BASELINE_F0_1 - ids)}"
    )
    # AUSENCIA — ids muertos que no pueden volver.
    for muerto in ("claude-opus-4-7", "claude-3-"):
        assert not any(muerto in mid for mid in ids), f"id muerto en el catalogo: {muerto}"


def test_precio_declarado_para_todo_modelo_ofrecido():
    """Sin entrada de precio, el centro de costos atribuye la tarifa por defecto."""
    sin_precio = []
    for mid in _ids_del_archivo():
        if not any(mid.startswith(pref) for pref in pricing.DEFAULT_PRICES):
            sin_precio.append(mid)
    assert not sin_precio, (
        f"Sin entrada de precio (match por PREFIJO) para {sin_precio}. "
        "Ojo: 'claude-opus-5' NO empieza con 'claude-opus-4'."
    )


# ── F7.0 — el respaldo de emergencia deja de contaminarse ────────────────────

def test_el_respaldo_de_emergencia_no_se_contamina(tmp_path, monkeypatch):
    """load_model_catalog asignaba la REFERENCIA de la constante de modulo, y
    _merge_probe/_merge_cuenta le hacian append: quedaba mutada para siempre.
    """
    antes = len(_ids_del_respaldo())

    # Archivo ilegible -> se cae al respaldo de emergencia, dos veces.
    monkeypatch.setattr(
        model_catalog, "_catalog_path", lambda: tmp_path / "no_existe.json"
    )
    dir_cuenta = tmp_path / "claude_config"
    dir_cuenta.mkdir(parents=True, exist_ok=True)
    (dir_cuenta / "stats-cache.json").write_text(
        json.dumps({"modelUsage": {"claude-sonnet-5": {}, "claude-opus-5": {}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(dir_cuenta))

    primera = model_catalog.load_model_catalog(force_refresh=True)
    segunda = model_catalog.load_model_catalog(force_refresh=True)

    # DOS PATAS: la respuesta SI trajo los modelos (si no, el test pasaria vacio)...
    assert primera["fallback_used"] is True
    assert len(_ids_efectivos(segunda)) >= antes
    assert "claude-sonnet-5" in _ids_efectivos(segunda)
    # ...y la constante de modulo quedo intacta.
    assert len(_ids_del_respaldo()) == antes, (
        f"_EMERGENCY_FALLBACK quedo contaminado: {antes} -> {len(_ids_del_respaldo())}"
    )


# ── F4 / F11 — los otros dos motores no cambian ──────────────────────────────

def test_los_otros_dos_motores_no_cambian():
    """Este plan toca SOLO el bloque claude_code_cli."""
    runtimes = _archivo()["runtimes"]
    assert runtimes["codex_cli"] == CODEX_CONGELADO
    assert runtimes["github_copilot"] == COPILOT_CONGELADO


# ── F4 / F5 / F6 — gate de alcance: fable queda afuera ───────────────────────

def test_fable_sigue_fuera_del_catalogo_y_de_la_allowlist():
    """DOS PATAS: fable AUSENTE en los 3 lugares, opus-5 PRESENTE en los 3.

    La pata de ausencia congela una decision de costo tomada y testeada por los
    planes 43 y 212 (Plan 288 seccion 8.9). La de presencia prueba que el test
    mira los lugares correctos y no pasa por vacio.
    """
    ids_archivo = set(_ids_del_archivo())
    ids_respaldo = set(_ids_del_respaldo())

    # AUSENCIA — fable fuera de los tres lugares.
    assert "claude-fable-5" not in ids_archivo
    assert "claude-fable-5" not in ids_respaldo
    assert "claude-fable-5" not in llm_router._OPUS_ALLOWLIST

    # PRESENCIA — opus-5 dentro de los tres lugares.
    assert ID_NUEVO in ids_archivo
    assert ID_NUEVO in ids_respaldo
    assert ID_NUEVO in llm_router._OPUS_ALLOWLIST


# ── F8 — la respuesta publica de donde salio cada modelo ─────────────────────

def _cliente(monkeypatch):
    """App de pruebas minima para pegarle a la ruta del catalogo."""
    import app as _app

    aplicacion = _app.create_app()
    aplicacion.config.update(TESTING=True)
    return aplicacion.test_client()


def _respuesta_catalogo(tmp_path, monkeypatch, cuenta=None) -> dict:
    catalogo_efectivo(tmp_path, monkeypatch, cuenta)   # siembra CLAUDE_CONFIG_DIR
    cli = _cliente(monkeypatch)
    return cli.get("/api/agents/model-catalog?refresh=true").get_json()


def test_respuesta_conserva_probe_y_cuenta_despues_del_enriquecido_de_capacidades(
    tmp_path, monkeypatch
):
    """El bloque del 264 RECONSTRUYE cada runtime: las claves nuevas tienen que sobrevivir."""
    datos = _respuesta_catalogo(tmp_path, monkeypatch, {
        "stats": {"modelUsage": {"claude-opus-5": {}}}, "config": {},
    })
    bloque = datos["runtimes"]["claude_code_cli"]

    # DOS PATAS: las claves nuevas del 288 estan...
    assert "cuenta" in bloque
    assert "motivo" in bloque["cuenta"]
    assert "omitidos" in bloque["cuenta"]
    # ...y la clave que puso el 264 NO desaparecio.
    assert "effort_mode" in bloque


def test_respuesta_trae_fallback_used_y_error(tmp_path, monkeypatch):
    """Con el archivo ilegible, el operador tiene con que enterarse."""
    monkeypatch.setattr(
        model_catalog, "_catalog_path", lambda: tmp_path / "no_existe.json"
    )
    datos = _respuesta_catalogo(tmp_path, monkeypatch)

    assert datos["fallback_used"] is True
    assert datos.get("error"), "el motivo del respaldo no viaja en la respuesta"


def test_los_modelos_del_catalogo_efectivo_llegan_a_la_respuesta(tmp_path, monkeypatch):
    """La capa del 264 no anula lo que agrego la cuenta."""
    datos = _respuesta_catalogo(tmp_path, monkeypatch, {
        "stats": {"modelUsage": {"claude-sonnet-4-5-sembrado": {}}}, "config": {},
    })
    bloque = datos["runtimes"]["claude_code_cli"]
    ids = [m["id"] for m in bloque["models"]]

    assert "claude-sonnet-4-5-sembrado" in ids, (
        "el id que agrego la cuenta se perdio en el enriquecido del plan 264"
    )
    assert "claude-sonnet-4-5-sembrado" in bloque["cuenta"]["agregados"]


# ── F11 — gate de paridad de motores ─────────────────────────────────────────

def test_paridad_codex_y_copilot_no_cambian_con_la_cuenta_encendida(tmp_path, monkeypatch):
    """DOS PATAS: los otros dos motores identicos, Y el de Claude SI cambio.

    Sin la contra-pata, la primera mitad pasaria por accidente si el lector no
    estuviera cableado: un gate que no puede fallar es un adorno.
    """
    import config as _config

    semilla = {"stats": {"modelUsage": {"claude-opus-5": {}}}, "config": {}}

    monkeypatch.setattr(_config.config, "STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED", True)
    encendido = catalogo_efectivo(tmp_path / "on", monkeypatch, semilla)["runtimes"]
    encendido = json.loads(json.dumps(encendido))

    monkeypatch.setattr(_config.config, "STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED", False)
    apagado = catalogo_efectivo(tmp_path / "off", monkeypatch, semilla)["runtimes"]
    apagado = json.loads(json.dumps(apagado))

    # PATA 1 — los otros dos motores, clave por clave.
    for motor in ("codex_cli", "github_copilot"):
        assert encendido[motor] == apagado[motor], f"{motor} cambio con la flag"
        assert "cuenta" not in encendido[motor], f"{motor} no puede tener la clave cuenta"
        assert "cuenta" not in apagado[motor]

    # PATA 2 (CONTRA-PRUEBA) — el de Claude SI tiene que cambiar.
    assert encendido["claude_code_cli"] != apagado["claude_code_cli"], (
        "el bloque claude_code_cli quedo igual con la flag encendida y apagada: "
        "el lector de cuenta NO esta cableado y la pata 1 pasa por accidente"
    )
    assert encendido["claude_code_cli"]["cuenta"]["disponible"] is True
    assert apagado["claude_code_cli"]["cuenta"]["motivo"] == "flag_apagada"


def test_ningun_simbolo_nuevo_nombra_un_motor():
    """Los simbolos nuevos no bifurcan por motor (salvo la excepcion declarada)."""
    raiz = Path(model_catalog.__file__).resolve().parents[1]
    frontend = raiz.parent / "frontend" / "src" / "services"
    objetivos = [
        raiz / "services" / "claude_account_models.py",
        frontend / "modelCatalogOrigin.ts",
        frontend / "modelCatalogRefresh.ts",
    ]
    for ruta in objetivos:
        if not ruta.exists():
            continue
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
            if "// paridad-ok" in linea:
                continue          # excepcion declarada: regla 7 de F9 (copilot)
            bajo = linea.lower()
            assert "codex" not in bajo, f"{ruta.name}:{n} nombra codex"
            assert "copilot" not in bajo, f"{ruta.name}:{n} nombra copilot"
