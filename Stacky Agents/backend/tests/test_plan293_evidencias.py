"""Plan 293 F11b — Evidencias de prueba.

AISLAMIENTO OBLIGATORIO: este es el UNICO archivo de test del plan que escribe en
disco. `runtime_paths.data_dir()` NO esta aislado por el conftest, asi que sin el
monkeypatch de abajo correr este archivo dejaria archivos REALES en la carpeta
del operador.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import runtime_paths
from services import work_evidence as we

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 40
GIF = b"GIF89a" + b"\x00" * 40
PDF = b"%PDF-1.7" + b"\x00" * 40
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 40


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path / "datos")
    return tmp_path


@pytest.fixture()
def sesion() -> str:
    return we.nueva_sesion()


# ── Deteccion por CONTENIDO, no por extension ───────────────────────────────
@pytest.mark.parametrize("contenido,esperado", [
    (PNG, "image/png"), (JPG, "image/jpeg"), (GIF, "image/gif"),
    (PDF, "application/pdf"), (WEBP, "image/webp"),
    (b"BM" + b"\x00" * 40, "image/bmp"),
])
def test_01_detecta_por_firma_real(contenido, esperado):
    assert we.detectar_tipo(contenido)[0] == esperado


def test_02_un_ejecutable_disfrazado_de_png_se_RECHAZA(sesion):
    """La extension la elige quien sube el archivo. Manda el contenido."""
    res = we.guardar(sesion, [("captura.png", b"MZ\x90\x00" + b"\x00" * 100)])
    assert res["archivos"] == []
    assert res["rechazados"] == [{"nombre": "captura.png", "motivo": "formato_no_permitido"}]


def test_03_un_texto_plano_tambien_se_rechaza(sesion):
    res = we.guardar(sesion, [("nota.png", b"hola, soy texto")])
    assert res["rechazados"][0]["motivo"] == "formato_no_permitido"


# ── Guardar y listar ────────────────────────────────────────────────────────
def test_04_guarda_y_lista(sesion):
    res = we.guardar(sesion, [("captura 1.png", PNG), ("informe.pdf", PDF)])
    assert res["ok"] is True and len(res["archivos"]) == 2
    listado = we.listar(sesion)
    assert [e["nombre"] for e in listado] == ["captura 1.png", "informe.pdf"]
    assert [e["tipo"] for e in listado] == ["image/png", "application/pdf"]


def test_05_el_nombre_del_disco_NO_es_el_de_entrada(sesion):
    """Anti path-traversal por construccion: el nombre en disco se DERIVA, no se
    copia de lo que llega de afuera."""
    we.guardar(sesion, [("../../fuera.png", PNG)])
    guardados = [e["guardado"] for e in we.listar(sesion)]
    assert guardados == ["00.png"]
    assert ".." not in guardados[0]


def test_06_el_nombre_visible_queda_saneado(sesion):
    we.guardar(sesion, [("../../etc/passwd.png", PNG)])
    assert we.listar(sesion)[0]["nombre"] == "passwd.png"


def test_07_las_evidencias_NO_viven_en_el_repo_del_operador(sesion, _aislar):
    we.guardar(sesion, [("a.png", PNG)])
    assert we.raiz().is_relative_to(_aislar / "datos")


def test_08_listar_no_devuelve_rutas_absolutas(sesion):
    we.guardar(sesion, [("a.png", PNG)])
    texto = repr(we.listar(sesion))
    assert ":\\" not in texto and "/home" not in texto and "datos" not in texto


# ── Topes ───────────────────────────────────────────────────────────────────
def test_09_archivo_muy_grande(sesion, monkeypatch):
    monkeypatch.setattr(we, "MAX_BYTES_POR_ARCHIVO", 100)
    res = we.guardar(sesion, [("grande.png", PNG + b"\x00" * 500)])
    assert res["rechazados"][0]["motivo"] == "archivo_muy_grande"
    assert we.listar(sesion) == []


def test_10_demasiados_archivos(sesion, monkeypatch):
    monkeypatch.setattr(we, "MAX_ARCHIVOS", 2)
    res = we.guardar(sesion, [("a.png", PNG), ("b.png", PNG), ("c.png", PNG)])
    assert len(res["archivos"]) == 2
    assert res["rechazados"][0]["motivo"] == "demasiados_archivos"


def test_11_tope_total(sesion, monkeypatch):
    monkeypatch.setattr(we, "MAX_BYTES_TOTAL", 100)
    res = we.guardar(sesion, [("a.png", PNG), ("b.png", PNG + b"\x00" * 200)])
    assert res["rechazados"][-1]["motivo"] == "total_muy_grande"


def test_12_una_captura_mala_no_voltea_las_buenas(sesion):
    res = we.guardar(sesion, [("ok.png", PNG), ("mala.png", b"MZ" + b"\x00" * 50), ("ok2.pdf", PDF)])
    assert len(res["archivos"]) == 2
    assert len(res["rechazados"]) == 1


# ── Previsualizacion ────────────────────────────────────────────────────────
def test_13_ruta_de_sirve_la_vista_previa(sesion):
    we.guardar(sesion, [("a.png", PNG)])
    ruta = we.ruta_de(sesion, "00.png")
    assert ruta is not None and ruta.read_bytes() == PNG


def test_14_ruta_de_rechaza_lo_que_no_esta_en_el_meta(sesion):
    we.guardar(sesion, [("a.png", PNG)])
    for intento in ("../../../etc/passwd", "meta.json", "99.png", "..\\..\\x"):
        assert we.ruta_de(sesion, intento) is None, intento


def test_15_sesion_invalida_no_toca_el_disco(_aislar):
    for mala in ("../otro", "x", "", "a" * 200, "con/barra"):
        assert we.guardar(mala, [("a.png", PNG)])["ok"] is False or we.listar(mala) == []
    assert not (_aislar / "datos" / "work_evidence").exists()


# ── Subida al proveedor ─────────────────────────────────────────────────────
class _GitLabDoble:
    name = "gitlab"

    def __init__(self):
        self.subidos: list[str] = []

    def upload_attachment(self, file_path, file_name):
        self.subidos.append(file_name)
        return {"markdown": f"![{file_name}](/uploads/x/{file_name})", "url": "/uploads/x"}


class _AdoDoble:
    name = "azure_devops"

    def upload_attachment(self, file_path, file_name):
        # ADO SI sabe subir, pero devuelve un adjunto de WORK ITEM, que no se
        # muestra embebido dentro de una propuesta de cambio.
        return {"id": "abc", "url": "https://ado/_apis/wit/attachments/abc"}


def test_16_gitlab_devuelve_markdown_embebible(sesion, monkeypatch):
    doble = _GitLabDoble()
    monkeypatch.setattr("services.tracker_provider.get_tracker_provider", lambda project=None: doble)
    we.guardar(sesion, [("captura.png", PNG)])
    res = we.subir_al_proveedor(sesion)
    assert res["ok"] is True and res["degradado"] is None
    assert res["markdown"] == ["![captura.png](/uploads/x/captura.png)"]
    assert doble.subidos == ["captura.png"]


def test_17_ado_DECLARA_la_degradacion_en_vez_de_fallar(sesion, monkeypatch):
    monkeypatch.setattr("services.tracker_provider.get_tracker_provider", lambda project=None: _AdoDoble())
    we.guardar(sesion, [("captura.png", PNG)])
    res = we.subir_al_proveedor(sesion)
    assert res["ok"] is True
    assert res["markdown"] == []
    deg = res["degradado"]
    assert deg is not None
    # Las CINCO claves congeladas del contrato con el renderizador del frontend.
    assert set(deg) == {"capability", "reason", "provider", "site", "at"}
    assert deg["capability"] == "git.evidence.embed"


def test_18_una_subida_que_falla_no_voltea_la_propuesta(sesion, monkeypatch):
    class _Roto(_GitLabDoble):
        def upload_attachment(self, file_path, file_name):
            raise RuntimeError("cayo la red")

    monkeypatch.setattr("services.tracker_provider.get_tracker_provider", lambda project=None: _Roto())
    we.guardar(sesion, [("a.png", PNG)])
    res = we.subir_al_proveedor(sesion)
    assert res["ok"] is True
    assert res["fallidos"][0]["motivo"] == "no_se_pudo_subir"


def test_19_sin_evidencias_no_llama_al_proveedor(sesion, monkeypatch):
    llamado = []
    monkeypatch.setattr(
        "services.tracker_provider.get_tracker_provider",
        lambda project=None: llamado.append(1),
    )
    res = we.subir_al_proveedor(sesion)
    assert res["markdown"] == [] and llamado == []


# ── CASO NEGATIVO: el que protege la descripcion del issue ──────────────────
def test_20_NUNCA_se_llama_a_link_attachment():
    """`link_attachment` de GitLab lee la descripcion del issue y si el GET
    previo falla asume "", PISANDOLA ENTERA. El markdown de este modulo se
    embebe en la descripcion que se manda AL CREAR la propuesta, en un unico
    llamado, justamente para no pasar por ahi."""
    fuente = Path(we.__file__).read_text(encoding="utf-8")
    codigo = "\n".join(
        l for l in fuente.splitlines()
        if not l.strip().startswith("#") and not l.strip().startswith('"')
    )
    assert "link_attachment(" not in codigo
    assert ".link_attachment" not in codigo


def test_21_el_markdown_entra_en_la_descripcion_de_la_propuesta(sesion, monkeypatch):
    """El camino completo: subir -> markdown -> descripcion, sin tocar el issue."""
    from services import change_proposal as cp

    monkeypatch.setattr("services.tracker_provider.get_tracker_provider", lambda project=None: _GitLabDoble())
    we.guardar(sesion, [("captura.png", PNG)])
    subida = we.subir_al_proveedor(sesion)

    descripcion = cp.build_description(
        resumen="arregle el total", archivos=["a.py"],
        pruebas="lo probe a mano", evidencias=subida["markdown"],
    )
    assert "## Evidencia adjunta" in descripcion
    assert "![captura.png](/uploads/x/captura.png)" in descripcion
