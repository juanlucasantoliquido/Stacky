"""tests/test_plan288_cuenta_local.py — Plan 288 F7.

El lector de la cuenta local de Claude Code, CON su filtro de admision.

LOS 13 CASOS USAN ARCHIVOS TEMPORALES PROPIOS (tmp_path + CLAUDE_CONFIG_DIR).
NINGUNO LEE EL DISCO REAL DEL OPERADOR. Es la diferencia entre una prueba y una
loteria: el contenido de ~/.claude.json cambia solo, y un test que lo lea pasa o
falla segun el dia.
"""
import json
from pathlib import Path

import pytest

from services import claude_account_models as cam
from services import model_catalog


@pytest.fixture(autouse=True)
def _reset_catalog_caches():
    model_catalog._cache.update(data=None, loaded_at=0.0, mtime=None)
    model_catalog._copilot_cache.update(models=None, loaded_at=0.0, error=None)
    yield
    model_catalog._cache.update(data=None, loaded_at=0.0, mtime=None)
    model_catalog._copilot_cache.update(models=None, loaded_at=0.0, error=None)


# ── Contenido REAL medido en el disco del operador el 2026-08-02 ─────────────
# Plan 288 §4.4(b). Es el fixture de la prueba de regresion del filtro: si el
# filtro se afloja, estos 7 descartes dejan de estar y el test lo grita.
STATS_REAL_2026_08_02 = {
    "modelUsage": {
        "claude-sonnet-4-6": {}, "claude-sonnet-5": {},
        "claude-haiku-4-5-20251001": {}, "claude-fable-5": {},
        "claude-opus-4-8": {}, "claude-opus-5": {},
        "glm-4.7": {}, "glm-5.2": {},
        "qwen2.5:3b": {}, "qwen2.5-coder:7b": {}, "qwen3-coder:30b-a3b-q4_K_M": {},
    },
    "dailyModelTokens": [
        {"date": "2026-07-28", "tokensByModel": {"claude-sonnet-5": 455132,
                                                 "claude-opus-5": 4321237}},
    ],
}
CONFIG_REAL_2026_08_02 = {
    "additionalModelOptionsCache": [
        {"value": "claude-fable-5[1m]", "label": "Fable",
         "description": "Fable 5 · Most capable for your hardest and longest-running tasks"},
    ],
    "modelAccessCache": [],
    "orgModelDefaultCache": None,
    "additionalModelCostsCache": {},
    "oauthAccount": {
        "billingType": "stripe_subscription",
        "organizationType": "claude_max",
        "organizationRateLimitTier": "default_claude_max_20x",
        "hasExtraUsageEnabled": False,
        "emailAddress": "no-se-debe-leer@ejemplo.com",
        "accountUuid": "no-se-debe-leer",
        "displayName": "no-se-debe-leer",
        "organizationName": "no-se-debe-leer",
        "organizationUuid": "no-se-debe-leer",
    },
}


def _sembrar(tmp_path: Path, monkeypatch, *, stats=None, cfg=None,
             stats_crudo=None, cfg_crudo=None) -> Path:
    """Deja una cuenta controlada en tmp_path y apunta CLAUDE_CONFIG_DIR ahi."""
    d = tmp_path / "claude_config"
    d.mkdir(parents=True, exist_ok=True)
    if stats_crudo is not None:
        (d / "stats-cache.json").write_text(stats_crudo, encoding="utf-8")
    elif stats is not None:
        (d / "stats-cache.json").write_text(json.dumps(stats), encoding="utf-8")
    if cfg_crudo is not None:
        (d / ".claude.json").write_text(cfg_crudo, encoding="utf-8")
    elif cfg is not None:
        (d / ".claude.json").write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(d))
    return d


def _bloque_claude(catalogo: dict) -> dict:
    return (catalogo.get("runtimes") or {}).get("claude_code_cli") or {}


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_cuenta_flag_apagada_no_abre_archivos(tmp_path, monkeypatch):
    """Flag apagada: motivo flag_apagada y CERO lecturas de disco."""
    _sembrar(tmp_path, monkeypatch, stats=STATS_REAL_2026_08_02, cfg=CONFIG_REAL_2026_08_02)
    monkeypatch.setattr(cam._cfg, "STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED", False, raising=False)

    llamadas = []
    real = Path.read_text
    monkeypatch.setattr(
        Path, "read_text",
        lambda self, *a, **k: (llamadas.append(str(self)), real(self, *a, **k))[1],
    )

    lectura = cam.leer_cuenta_claude()
    assert lectura.disponible is False
    assert lectura.motivo == "flag_apagada"
    assert lectura.usados == () and lectura.ofrecidos == ()
    assert llamadas == [], f"con la flag apagada no se abre NINGUN archivo, y se abrieron {llamadas}"


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_cuenta_sin_archivos_no_lanza(tmp_path, monkeypatch):
    d = tmp_path / "claude_config"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(d))

    lectura = cam.leer_cuenta_claude()
    assert lectura.disponible is False
    assert lectura.motivo == "sin_archivos"
    assert lectura.usados == () and lectura.ofrecidos == () and lectura.omitidos == ()


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_cuenta_json_roto_conserva_lo_otro(tmp_path, monkeypatch):
    """El config esta roto pero el de estadisticas se leyo: lo suyo SE CONSERVA."""
    _sembrar(tmp_path, monkeypatch,
             stats=STATS_REAL_2026_08_02, cfg_crudo="{ esto no es json ")

    lectura = cam.leer_cuenta_claude()
    assert lectura.motivo == "json_ilegible"
    # DOS PATAS: se conserva lo del archivo sano...
    assert "claude-opus-5" in lectura.usados
    assert "claude-sonnet-5" in lectura.usados
    # ...y se perdio lo del roto (la suscripcion vivia ahi).
    assert lectura.suscripcion == ""


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_cuenta_usados_normaliza_y_dedup(tmp_path, monkeypatch):
    """El sufijo de fecha se saca y el id no se repite."""
    _sembrar(tmp_path, monkeypatch, stats={
        "modelUsage": {"claude-haiku-4-5-20251001": {}, "claude-haiku-4-5": {},
                       "claude-sonnet-5": {}},
        "dailyModelTokens": [{"date": "x", "tokensByModel": {"claude-sonnet-5": 1}}],
    }, cfg={})

    lectura = cam.leer_cuenta_claude()
    assert lectura.usados == ("claude-haiku-4-5", "claude-sonnet-5")
    assert cam.normalizar_id_modelo("claude-haiku-4-5-20251001") == "claude-haiku-4-5"
    assert cam.normalizar_id_modelo("claude-fable-5[1m]") == "claude-fable-5"
    assert cam.normalizar_id_modelo("claude-opus-5") == "claude-opus-5"
    assert cam.normalizar_id_modelo("qwen2.5-coder:7b") == "qwen2.5-coder:7b"


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_cuenta_ofrecidos_tolera_formas(tmp_path, monkeypatch):
    """additionalModelOptionsCache: lista vacia, de strings y de objetos."""
    _sembrar(tmp_path, monkeypatch, stats={}, cfg={
        "additionalModelOptionsCache": ["claude-opus-5", {"value": "claude-sonnet-5"},
                                        {"id": "claude-haiku-4-5"}, 42, None],
        "modelAccessCache": [],
    })
    lectura = cam.leer_cuenta_claude()
    assert lectura.ofrecidos == ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5")
    assert lectura.usados == ()


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_cuenta_etiqueta_no_se_inventa(tmp_path, monkeypatch):
    """Sin `label` no entra al diccionario de etiquetas."""
    _sembrar(tmp_path, monkeypatch, stats={}, cfg={
        "additionalModelOptionsCache": [
            {"value": "claude-opus-5", "label": "Opus cinco"},
            {"value": "claude-sonnet-5"},
        ],
    })
    lectura = cam.leer_cuenta_claude()
    assert lectura.etiquetas == {"claude-opus-5": "Opus cinco"}
    assert "claude-sonnet-5" in lectura.ofrecidos  # entro, pero sin etiqueta


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_cuenta_no_lee_datos_personales(tmp_path, monkeypatch):
    """Solo organizationType y organizationRateLimitTier salen de oauthAccount."""
    _sembrar(tmp_path, monkeypatch,
             stats=STATS_REAL_2026_08_02, cfg=CONFIG_REAL_2026_08_02)
    lectura = cam.leer_cuenta_claude()

    assert lectura.suscripcion == "claude_max"
    assert lectura.nivel_de_limite == "default_claude_max_20x"
    # Ningun campo del dataclass contiene el centinela de dato personal.
    serializado = json.dumps({
        "s": lectura.suscripcion, "n": lectura.nivel_de_limite,
        "u": list(lectura.usados), "o": list(lectura.ofrecidos),
        "e": lectura.etiquetas, "om": [list(x) for x in lectura.omitidos],
        "c": list(lectura.crudos),
    })
    assert "no-se-debe-leer" not in serializado


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_cuenta_no_cachea_por_su_cuenta(tmp_path, monkeypatch):
    """Un cambio en el archivo se ve en la lectura siguiente: el lector no cachea."""
    d = _sembrar(tmp_path, monkeypatch, stats={"modelUsage": {"claude-sonnet-5": {}}}, cfg={})
    primera = cam.leer_cuenta_claude()
    assert primera.usados == ("claude-sonnet-5",)

    (d / "stats-cache.json").write_text(
        json.dumps({"modelUsage": {"claude-sonnet-5": {}, "claude-opus-5": {}}}),
        encoding="utf-8",
    )
    segunda = cam.leer_cuenta_claude()
    assert segunda.usados == ("claude-sonnet-5", "claude-opus-5")


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_cuenta_no_duplica_ids_del_catalogo(tmp_path, monkeypatch):
    """Un id que el catalogo YA tiene no se agrega dos veces ni cuenta como omitido."""
    _sembrar(tmp_path, monkeypatch,
             stats={"modelUsage": {"claude-sonnet-5": {}, "claude-opus-5": {}}}, cfg={})
    catalogo = model_catalog.load_model_catalog(force_refresh=True)
    cli = _bloque_claude(catalogo)

    ids = [m["id"] for m in cli["models"]]
    assert ids.count("claude-sonnet-5") == 1
    assert ids.count("claude-opus-5") == 1
    # Ya estaban en el archivo, asi que la cuenta no agrego nada nuevo...
    assert cli["cuenta"]["agregados"] == []
    # ...y NO se reportan como omitidos (la condicion (c) no es un descarte).
    assert cli["cuenta"]["omitidos"] == []


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_cuenta_nunca_resta(tmp_path, monkeypatch):
    """Un id del catalogo que la cuenta no registra SE CONSERVA."""
    _sembrar(tmp_path, monkeypatch, stats={"modelUsage": {"claude-opus-5": {}}}, cfg={})
    catalogo = model_catalog.load_model_catalog(force_refresh=True)
    ids = {m["id"] for m in _bloque_claude(catalogo)["models"]}

    for previo in ("claude-sonnet-5", "claude-opus-4-8", "claude-haiku-4-5", "claude-sonnet-4-6"):
        assert previo in ids, f"la cuenta RESTO {previo} del catalogo"


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_cuenta_omitidos_filtro_literal_del_disco_real_2026_08_02(tmp_path, monkeypatch):
    """PRUEBA DE REGRESION LITERAL — el caso que habria hundido a la v1.

    Sin filtro, el selector de Claude Code mostraria SEIS ids que no puede
    ejecutar. Con filtro, los descarta Y explica por que.
    """
    _sembrar(tmp_path, monkeypatch,
             stats=STATS_REAL_2026_08_02, cfg=CONFIG_REAL_2026_08_02)
    lectura = cam.leer_cuenta_claude()

    assert lectura.disponible is True
    assert lectura.motivo == "ok"
    assert lectura.usados == ("claude-sonnet-4-6", "claude-sonnet-5", "claude-haiku-4-5",
                              "claude-opus-4-8", "claude-opus-5")
    assert lectura.ofrecidos == ()
    assert dict(lectura.omitidos) == {
        "claude-fable-5":                "bloqueado_por_politica_de_costo",
        "claude-fable-5[1m]":            "bloqueado_por_politica_de_costo",
        "glm-4.7":                       "otro_proveedor",
        "glm-5.2":                       "otro_proveedor",
        "qwen2.5:3b":                    "otro_proveedor",
        "qwen2.5-coder:7b":              "otro_proveedor",
        "qwen3-coder:30b-a3b-q4_K_M":    "otro_proveedor",
    }


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_cuenta_viva_con_la_sonda_apagada(tmp_path, monkeypatch):
    """La flag nueva NO depende de STACKY_MODEL_PROBE_ENABLED (cierra C4)."""
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_MODEL_PROBE_ENABLED", False, raising=False)
    _sembrar(tmp_path, monkeypatch, stats={"modelUsage": {"claude-opus-5": {}}}, cfg={})

    catalogo = model_catalog.load_model_catalog(force_refresh=True)
    cli = _bloque_claude(catalogo)

    # DOS PATAS: la cuenta vive...
    assert cli["cuenta"]["disponible"] is True
    # ...y la sonda de verdad estaba apagada (no dejo su clave).
    assert "probe" not in cli


# ── 13 ───────────────────────────────────────────────────────────────────────
def test_cuenta_cableada_bajo_modo_de_prueba(tmp_path, monkeypatch):
    """El lector NO tiene la guarda de STACKY_TEST_MODE de _merge_probe (cierra C3)."""
    monkeypatch.setenv("STACKY_TEST_MODE", "1")
    _sembrar(tmp_path, monkeypatch,
             stats={"modelUsage": {"claude-opus-5": {}, "claude-sonnet-4-5-sembrado": {}}},
             cfg={"additionalModelOptionsCache": [{"value": "claude-sonnet-4-5-sembrado",
                                                   "label": "Sembrado"}]})
    catalogo = model_catalog.load_model_catalog(force_refresh=True)
    cli = _bloque_claude(catalogo)

    # DOS PATAS: la clave existe bajo modo de prueba...
    assert "cuenta" in cli
    # ...y trae el id sembrado en el tmp_path, no una lista vacia.
    assert "claude-sonnet-4-5-sembrado" in cli["cuenta"]["agregados"]
