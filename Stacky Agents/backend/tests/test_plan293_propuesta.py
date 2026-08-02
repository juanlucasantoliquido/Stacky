"""Plan 293 F11 — La propuesta de cambio, el unico paso REST del tablero."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from services import change_proposal as cp


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    ).stdout or ""


@pytest.fixture(autouse=True)
def _envio_encendido(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "STACKY_WORKBENCH_PUSH_ENABLED", True, raising=False)


class _ProveedorDoble:
    def __init__(self):
        self.llamadas: list[tuple] = []

    def create_merge_request(self, source, target, title, description):
        self.llamadas.append((source, target, title, description))
        return {"web_url": "https://servidor/propuesta/1", "id": 1}


@pytest.fixture()
def proveedor(monkeypatch):
    doble = _ProveedorDoble()
    monkeypatch.setattr(
        "services.merge_request_provider.get_merge_request_provider",
        lambda project=None: doble,
    )
    return doble


# ── build_description ───────────────────────────────────────────────────────
def test_01_orden_de_secciones_estable():
    d = cp.build_description(
        resumen="arregle el total", archivos=["a.py"], pruebas="lo abri y anda",
        evidencias=["![captura](u)"], sospechas=[{"archivo": "a.py", "tipo": "clave privada"}],
    )
    orden = [d.index(s) for s in ("## Que cambie", "## Archivos incluidos", "## Que probe",
                                  "## Evidencia adjunta", "## Revisar antes de integrar")]
    assert orden == sorted(orden), f"las secciones salieron desordenadas: {orden}"


def test_02_sin_evidencia_la_seccion_no_aparece():
    d = cp.build_description(resumen="x", archivos=["a.py"])
    assert "## Evidencia adjunta" not in d
    assert "## Que probe" not in d


def test_03_con_sospechas_el_aviso_aparece_SIEMPRE():
    d = cp.build_description(
        resumen="x", archivos=["a.py"],
        sospechas=[{"archivo": "cfg.py", "tipo": "credencial de GitLab"}],
    )
    assert "## Revisar antes de integrar" in d
    assert "cfg.py" in d and "credencial de GitLab" in d


def test_04_sin_archivos_es_error():
    with pytest.raises(ValueError):
        cp.build_description(resumen="x", archivos=[])


def test_05_un_titulo_con_almohadilla_no_rompe_la_estructura():
    d = cp.build_description(resumen="## no soy una seccion", archivos=["a.py"])
    assert d.count("## Que cambie") == 1
    assert d.index("## Que cambie") < d.index("## Archivos incluidos")


def test_06_muchos_archivos_se_acotan_y_se_dice_cuantos_faltan():
    d = cp.build_description(resumen="x", archivos=[f"f{i}.py" for i in range(70)])
    assert "y 10 mas" in d


# ── Deteccion de secretos ───────────────────────────────────────────────────
def test_07_detecta_los_seis_patrones_de_alta_confianza():
    textos = {
        "a": "AKIA" + "A" * 16,
        "b": "ghp_" + "a" * 36,
        "c": "glpat-" + "a" * 20,
        "d": "xoxb-1234567890",
        "e": "Authorization: Bearer " + "a" * 25,
        "f": "-----BEGIN RSA PRIVATE KEY-----",
    }
    hallazgos = cp.buscar_sospechas(textos)
    assert {h["archivo"] for h in hallazgos} == set(textos)


def test_08_no_marca_codigo_legitimo():
    """Se avisa de MENOS a proposito: un detector agresivo destruye codigo real."""
    assert cp.buscar_sospechas({"a": 'password = cfg.get("db_password")'}) == []


def test_09_nunca_devuelve_el_secreto():
    h = cp.buscar_sospechas({"a": "ghp_" + "z" * 36})
    assert "ghp_" not in repr(h)


# ── Rama destino ────────────────────────────────────────────────────────────
@pytest.fixture()
def clon(tmp_path: Path) -> Path:
    remoto = tmp_path / "remoto.git"
    remoto.mkdir()
    _git(remoto, "init", "--bare", "-b", "principal")
    c = tmp_path / "clon"
    c.mkdir()
    _git(c, "init", "-b", "principal")
    _git(c, "config", "user.email", "p@l")
    _git(c, "config", "user.name", "P")
    _git(c, "remote", "add", "origin", str(remoto))
    (c / "a.txt").write_text("x\n", encoding="utf-8")
    _git(c, "add", "a.txt")
    _git(c, "commit", "-m", "i")
    _git(c, "push", "origin", "principal")
    _git(c, "fetch", "origin")
    return c


def test_10_rama_destino_NO_se_supone_main(clon):
    """MEDIDO: la rama principal de este remoto se llama "principal", no "main".

    Un plan que hubiera devuelto "main" por defecto habria hecho fallar el REST
    con un error del proveedor que no dice nada util. Se resuelve preguntandole
    al repositorio, y el resultado es el nombre REAL.
    """
    _git(clon, "switch", "-c", "mi-trabajo")
    assert cp.resolver_rama_destino(clon) == "principal"


def test_10b_sin_origin_head_ni_candidatas_devuelve_None(tmp_path):
    """Sin remoto no se inventa una rama: se dice que no se sabe."""
    solo = tmp_path / "solo"
    solo.mkdir()
    _git(solo, "init", "-b", "loquesea")
    _git(solo, "config", "user.email", "p@l")
    _git(solo, "config", "user.name", "P")
    (solo / "a.txt").write_text("x\n", encoding="utf-8")
    _git(solo, "add", "a.txt")
    _git(solo, "commit", "-m", "i")
    assert cp.resolver_rama_destino(solo) is None


def test_11_rama_destino_lee_origin_head_si_existe(clon):
    _git(clon, "remote", "set-head", "origin", "principal")
    assert cp.resolver_rama_destino(clon) == "principal"


# ── abrir_propuesta ─────────────────────────────────────────────────────────
def test_12_propuesta_feliz_usa_los_CUATRO_parametros(clon, proveedor):
    _git(clon, "remote", "set-head", "origin", "principal")
    _git(clon, "switch", "-c", "mi-trabajo")
    res = cp.abrir_propuesta(
        raiz=clon, rama_origen="mi-trabajo", titulo="Arreglo el total",
        resumen="cambie el calculo", archivos=["a.txt"], pruebas="lo abri",
    )
    assert res["ok"] is True, res
    assert res["url"].startswith("https://")
    assert len(proveedor.llamadas) == 1
    source, target, title, description = proveedor.llamadas[0]
    assert (source, target, title) == ("mi-trabajo", "principal", "Arreglo el total")
    # TODO lo del formulario vive DENTRO de description: es el unico campo libre.
    assert "## Que cambie" in description and "## Que probe" in description


def test_13_flag_apagada_no_llama_al_proveedor(clon, proveedor, monkeypatch):
    from config import config
    monkeypatch.setattr(config, "STACKY_WORKBENCH_PUSH_ENABLED", False, raising=False)
    res = cp.abrir_propuesta(
        raiz=clon, rama_origen="x", titulo="t", resumen="r", archivos=["a.txt"],
    )
    assert res["codigo"] == "push_apagado"
    assert proveedor.llamadas == []


def test_14_proponer_sobre_la_misma_rama_se_rechaza(clon, proveedor):
    _git(clon, "remote", "set-head", "origin", "principal")
    res = cp.abrir_propuesta(
        raiz=clon, rama_origen="principal", titulo="t", resumen="r", archivos=["a.txt"],
    )
    assert res["codigo"] == "misma_rama"
    assert proveedor.llamadas == []


def test_15_sin_rama_destino_no_inventa(clon, proveedor, monkeypatch):
    monkeypatch.setattr(cp, "resolver_rama_destino", lambda raiz: None)
    res = cp.abrir_propuesta(
        raiz=clon, rama_origen="x", titulo="t", resumen="r", archivos=["a.txt"],
    )
    assert res["codigo"] == "sin_rama_destino"
    assert proveedor.llamadas == []


def test_16_tracker_sin_propuestas_da_error_claro(clon, monkeypatch):
    _git(clon, "remote", "set-head", "origin", "principal")
    _git(clon, "switch", "-c", "otra")

    def _explota(project=None):
        raise RuntimeError("no hay proveedor")

    monkeypatch.setattr(
        "services.merge_request_provider.get_merge_request_provider", _explota,
    )
    res = cp.abrir_propuesta(
        raiz=clon, rama_origen="otra", titulo="t", resumen="r", archivos=["a.txt"],
    )
    assert res["codigo"] == "tracker_sin_propuestas"


# ── CASOS NEGATIVOS: lo que este modulo NO puede hacer ──────────────────────
def test_17_NUNCA_llama_a_link_attachment():
    """`link_attachment` de GitLab lee la descripcion del issue y si el GET falla
    asume "", PISANDO la descripcion entera. Es perdida de datos."""
    fuente = Path(cp.__file__).read_text(encoding="utf-8")
    codigo = "\n".join(
        l for l in fuente.splitlines() if not l.strip().startswith("#")
    )
    # Aparece SOLO en el docstring de advertencia, nunca como llamada.
    assert "link_attachment(" not in codigo
    assert ".link_attachment" not in codigo


def test_18_NO_importa_redact_secrets_de_pr_review_sanitize():
    """`redact_secrets` es camino de LECTURA (hacia el modelo) y destruye codigo
    legitimo. Usarlo sobre lo que se publica arruinaria el contenido."""
    fuente = Path(cp.__file__).read_text(encoding="utf-8")
    assert "pr_review_sanitize" not in fuente
    assert "redact_secrets" not in fuente


def test_19_una_sola_llamada_REST_por_propuesta(clon, proveedor):
    """Crear primero y "completar" despues es el camino que puede pisar
    contenido. La descripcion va armada en el mismo llamado."""
    _git(clon, "remote", "set-head", "origin", "principal")
    _git(clon, "switch", "-c", "otra")
    cp.abrir_propuesta(
        raiz=clon, rama_origen="otra", titulo="t", resumen="r", archivos=["a.txt"],
    )
    assert len(proveedor.llamadas) == 1
