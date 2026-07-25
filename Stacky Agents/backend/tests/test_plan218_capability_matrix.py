"""tests/test_plan218_capability_matrix.py -- Plan 218 F2.

Registro de capacidades por proveedor + matriz de paridad GENERADA (nunca a mano).
Los tests son los que impiden que la matriz se pudra, en los DOS sentidos:
  * declarar `full` sin cumplirlo  -> lo caza F3 (contrato conductual)
  * dejar `absent` algo ya implementado -> lo caza `test_matriz_no_miente_estructuralmente`
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.provider_capabilities import (  # noqa: E402
    CAPABILITY_KEYS,
    CAPABILITY_MATRIX,
    CAPABILITY_STATUSES,
    _CAPABILITY_TO_PORT_METHOD,
    capability_loss,
    capability_status,
    render_markdown_matrix,
    supports,
)

_DOC = _BACKEND.parent / "docs" / "_roadmap" / "PARIDAD_ADO_GITLAB.md"
_EVIDENCE_RE = re.compile(r"^[\w/\.]+\.py:\d+$")

# SHA-256 de "\n".join(CAPABILITY_KEYS) CONGELADO por el Plan 218 §3.1.
# Agregar claves es aditivo y actualiza este hash a propósito; RENOMBRAR una clave
# rompe a los consumidores (matriz, catálogo de la serie, overrides por proyecto).
_KEYS_SHA = "10c58a01edf6e475d313adadbd8fe99fcddf05b9b6d44976a3dfbc0b20d453a8"


def test_toda_clave_declarada_en_ambos_proveedores():
    assert set(CAPABILITY_MATRIX["azure_devops"]) == set(CAPABILITY_KEYS)
    assert set(CAPABILITY_MATRIX["gitlab"]) == set(CAPABILITY_KEYS)


def test_status_pertenece_al_vocabulario():
    for provider, caps in CAPABILITY_MATRIX.items():
        for key, entry in caps.items():
            assert entry["status"] in CAPABILITY_STATUSES, f"{provider}/{key}"


def test_partial_exige_loss_no_vacio():
    for provider, caps in CAPABILITY_MATRIX.items():
        for key, entry in caps.items():
            if entry["status"] == "partial":
                assert len(entry.get("loss", "")) >= 10, (
                    f"{provider}/{key}: `partial` SIN pérdida declarada. Una capacidad "
                    "parcial sin pérdida es una promesa a medias."
                )


def test_full_y_partial_exigen_evidencia():
    for provider, caps in CAPABILITY_MATRIX.items():
        for key, entry in caps.items():
            if entry["status"] in ("full", "partial"):
                assert _EVIDENCE_RE.match(entry.get("evidence", "")), (
                    f"{provider}/{key}: evidencia inválida {entry.get('evidence')!r} "
                    "(se espera 'ruta/archivo.py:linea')"
                )


def test_supports_es_consistente():
    for provider, caps in CAPABILITY_MATRIX.items():
        for key, entry in caps.items():
            esperado = entry["status"] in ("full", "partial")
            assert supports(provider, key) is esperado, f"{provider}/{key}"
            assert capability_status(provider, key) == entry["status"]
            if entry["status"] != "partial":
                assert capability_loss(provider, key) == ""


def test_render_es_determinista():
    assert render_markdown_matrix() == render_markdown_matrix()


def test_doc_de_paridad_esta_sincronizado():
    """El documento de paridad es GENERADO. Si diverge, este test lo delata.

    C16: comparación NORMALIZADA a \\n — en Windows `core.autocrlf` puede reescribir
    el archivo al checkout y una comparación byte-a-byte cruda sería intermitente.
    """
    assert _DOC.exists(), f"falta el documento generado: {_DOC}"
    en_disco = _DOC.read_text(encoding="utf-8").replace("\r\n", "\n")
    generado = render_markdown_matrix().replace("\r\n", "\n")
    assert en_disco == generado, (
        "docs/_roadmap/PARIDAD_ADO_GITLAB.md quedó desincronizado de "
        "render_markdown_matrix(). Regeneralo (nunca lo edites a mano)."
    )


def test_claves_congeladas_no_se_renombran():
    sha = hashlib.sha256("\n".join(CAPABILITY_KEYS).encode("utf-8")).hexdigest()
    assert sha == _KEYS_SHA, (
        f"CAPABILITY_KEYS cambió (sha {sha}). Agregar claves es ADITIVO y actualiza "
        "este hash; renombrar NO está permitido (§3.1 congela el contrato)."
    )


def test_matriz_no_miente_estructuralmente():
    """[ADICIÓN ARQUITECTO 2a] Detector de mentiras en el eje ESTRUCTURAL.

    Para cada capacidad `tracker.*` mapeada a un método del puerto:
      * `full`/`partial` ⇒ el método EXISTE y es callable en ese adaptador.
      * `absent`        ⇒ `supports()` es False (la vía consultiva, la que usa el código).
    Cierra el lazo en el sentido contrario al de F3: caza la capacidad ya implementada
    que la matriz sigue declarando ausente (y que por eso la UI oculta).
    """
    from services.ado_provider import AdoTrackerProvider
    from services.gitlab_provider import GitLabTrackerProvider
    from services.tracker_provider import PORT_METHODS

    for metodo in _CAPABILITY_TO_PORT_METHOD.values():
        assert metodo in PORT_METHODS, f"{metodo} no está en PORT_METHODS"

    adaptadores = {"azure_devops": AdoTrackerProvider, "gitlab": GitLabTrackerProvider}
    for provider, cls in adaptadores.items():
        for key, metodo in _CAPABILITY_TO_PORT_METHOD.items():
            status = capability_status(provider, key)
            if status in ("full", "partial"):
                assert callable(getattr(cls, metodo, None)), (
                    f"{provider}/{key} declarado {status} pero {cls.__name__}.{metodo} "
                    "no existe o no es callable"
                )
            elif status == "absent":
                assert supports(provider, key) is False, f"{provider}/{key}"


def test_capability_unavailable_existe_y_es_subclase():
    from services.tracker_provider import CapabilityUnavailable, TrackerError

    assert issubclass(CapabilityUnavailable, TrackerError)
    exc = CapabilityUnavailable(
        "tracker.sync.full", "gitlab", reason="todavía no implementado", workaround="usá ADO",
    )
    payload = exc.to_payload()
    assert set(payload) == {"available", "capability", "provider", "reason", "workaround"}
    assert payload["available"] is False
    assert payload["capability"] == "tracker.sync.full"
    assert payload["provider"] == "gitlab"
