"""tests/test_plan294_project_probe.py — Plan 294 F5.

`probe_project` COMPONE lo que ya existe (deteccion de stack, contexto de
proyecto, inventario del plan 246 con la ficha del 294 F2, nombres de variables)
y devuelve en UNA llamada todo lo que el paso 1 muestra.

READ-ONLY ABSOLUTO y NUNCA LANZA: cada bloque va en su propio try/except y su
fallo agrega una entrada a `sources` con `available: False` y `reason` no vacio.
Que falle uno no puede vaciar los otros.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_BACKEND = pathlib.Path(__file__).resolve().parents[1]

_TRECE_CLAVES = (
    "ok", "project", "provider", "repository", "default_branch", "stack",
    "framework", "package_manager", "build_command", "test_command",
    "variables", "inventory", "sources",
)

_YAML_OK = "steps:\n  - script: echo hola\n"


def _inventario(n: int) -> dict:
    from services.pipeline_inventory import make_entry

    return {
        "ok": True,
        "pipelines": [
            make_entry(
                provider="azure_devops",
                name=f"pipeline-{i}",
                yaml_path=f"pipelines/p{i}.yml",
                default_branch="main",
                definition_id=str(i),
                category="registrada+en_repo",
            )
            for i in range(n)
        ],
        "sources": [],
        "counts": {},
    }


def test_el_shape_trae_las_trece_claves(monkeypatch):
    import services.pipeline_project_probe as probe

    monkeypatch.setattr(probe, "_build_inventory", lambda *a, **k: _inventario(0))
    out = probe.probe_project("RecoveryStrategy")
    assert out["ok"] is True
    assert set(out) == set(_TRECE_CLAVES), sorted(set(out) ^ set(_TRECE_CLAVES))


def test_si_el_inventario_revienta_el_resto_sobrevive_y_se_ve(monkeypatch):
    """Degradacion VISIBLE: no basta con no romper, hay que decir que falto."""
    import services.pipeline_project_probe as probe

    def _explota(*a, **k):
        raise RuntimeError("el proveedor no responde")

    monkeypatch.setattr(probe, "_build_inventory", _explota)
    out = probe.probe_project("RecoveryStrategy")

    assert out["ok"] is True
    assert out["inventory"].get("pipelines") == []
    caidas = [s for s in out["sources"] if s.get("available") is False]
    assert caidas, "no se declaro ninguna fuente caida"
    assert all(s.get("reason", "").strip() for s in caidas)


def test_sin_stack_no_se_inventa_ningun_comando(monkeypatch):
    import services.pipeline_project_probe as probe

    monkeypatch.setattr(probe, "_build_inventory", lambda *a, **k: _inventario(0))
    monkeypatch.setattr(probe, "_detect_stack", lambda root: None)
    out = probe.probe_project("RecoveryStrategy")

    assert out["stack"] == ""
    assert out["build_command"] == ""
    assert out["test_command"] == ""


def test_r3_las_variables_son_nombres_nunca_valores(monkeypatch):
    import services.pipeline_project_probe as probe

    monkeypatch.setattr(probe, "_build_inventory", lambda *a, **k: _inventario(0))
    monkeypatch.setattr(
        probe, "_variable_names",
        lambda project: ["NUGET_FEED", "SIGNING_KEY"],
    )
    out = probe.probe_project("RecoveryStrategy")

    assert out["variables"] == ["NUGET_FEED", "SIGNING_KEY"]
    for nombre in out["variables"]:
        assert "=" not in nombre and ":" not in nombre


def test_el_tope_limita_la_lectura_de_disco_no_la_ficha(monkeypatch):
    """C8 — TODAS las entradas pasan por describe_pipeline; el tope limita
    cuantas LEEN el archivo del disco, que es lo caro. Sin el mock de la lectura
    las 40 darian 'sin_datos' y el caso no probaria el tope."""
    import services.pipeline_project_probe as probe

    monkeypatch.setattr(probe, "_build_inventory", lambda *a, **k: _inventario(40))
    monkeypatch.setattr(
        probe, "_get_pipeline_yaml", lambda key: (_YAML_OK, "pipelines/p.yml")
    )

    entradas = probe.probe_project("RecoveryStrategy")["inventory"]["pipelines"]
    assert len(entradas) == 40
    assert all("purpose_source" in e for e in entradas)
    assert sum(1 for e in entradas if e["purpose_source"] == "plantilla") == 25
    assert sum(1 for e in entradas if e["purpose_source"] == "sin_datos") == 15
    assert probe._MAX_DESCRIBED == 25


def test_probe_project_no_escribe(monkeypatch):
    import builtins

    import services.pipeline_project_probe as probe

    real_open = builtins.open

    def _solo_lectura(archivo, modo="r", *a, **k):
        if "w" in str(modo) or "a" in str(modo) or "+" in str(modo):
            raise AssertionError(f"probe_project intento escribir en {archivo!r}")
        return real_open(archivo, modo, *a, **k)

    monkeypatch.setattr(builtins, "open", _solo_lectura)
    monkeypatch.setattr(probe, "_build_inventory", lambda *a, **k: _inventario(1))

    out = probe.probe_project("RecoveryStrategy")
    assert out["ok"] is True


def test_kpi4_el_modulo_no_llama_a_ningun_modelo():
    """C19 — verificacion ESTRUCTURAL y determinista, no un mock de un cliente
    sin nombrar. Si alguien cablea un modelo aca, este caso lo dice por nombre."""
    fuente = (_BACKEND / "services" / "pipeline_project_probe.py").read_text(
        encoding="utf-8"
    )
    for prohibida in (
        "llm", "anthropic", "openai", "copilot_bridge", "model_router",
        "requests", "urllib", "httpx",
    ):
        assert prohibida not in fuente, (
            f"pipeline_project_probe.py menciona {prohibida!r}: el paso 1 no gasta"
        )


def test_un_proyecto_inexistente_no_lanza():
    from services.pipeline_project_probe import probe_project

    out = probe_project("proyecto-que-no-existe-294")
    assert out["ok"] is True
    assert isinstance(out["sources"], list)


def test_c11_sin_workspace_activo_no_revienta_por_tipos(monkeypatch):
    """MITAD DE CONTRASTE del bug de tipos: detect_stack toma `str` y
    _active_workspace_root devuelve `Path | None`. Si alguien escribe
    `detect_stack(_active_workspace_root())` a secas, con workspace ausente pasa
    None y revienta. Este caso se pone rojo."""
    import services.pipeline_project_probe as probe

    monkeypatch.setattr(probe, "_build_inventory", lambda *a, **k: _inventario(0))
    monkeypatch.setattr(
        "runtime_paths._active_workspace_root", lambda: None, raising=True
    )

    out = probe.probe_project("RecoveryStrategy")
    assert out["stack"] == ""
    assert out["build_command"] == ""
