"""Plan 265 F4.5 — Enmascarado de secretos ANTES de que un diff salga del
proceso (KPI-6). 8 casos del doc.
"""
from __future__ import annotations

import subprocess
import time

from services.console_secret_mask import mask_secrets


def test_1_password_kv_se_enmascara():
    text = 'PASSWORD=Sup3rS3cr3t!\nother=fine'
    masked, count = mask_secrets(text)
    assert "Sup3rS3cr3t!" not in masked
    assert count >= 1
    assert "MASKED" in masked.upper() or "***" in masked


def test_2_cadena_de_conexion_password_enmascarada_resto_legible():
    text = "Server=tcp:myserver.database.windows.net;Database=mydb;User ID=admin;Password=Sup3rS3cr3t!;"
    masked, count = mask_secrets(text)
    assert count >= 1
    assert "Sup3rS3cr3t!" not in masked
    assert "Server=tcp:myserver.database.windows.net" in masked
    assert "Database=mydb" in masked
    assert "User ID=admin" in masked


def test_3_pat_alta_entropia_con_prefijo_se_enmascara():
    text = "token de despliegue: ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    masked, count = mask_secrets(text)
    assert "ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8" not in masked
    assert count >= 1


def test_4_sin_secretos_texto_identico_contador_cero():
    text = (
        "def suma(a, b):\n"
        "    \"\"\"Devuelve la suma de dos numeros.\"\"\"\n"
        "    return a + b\n"
    )
    masked, count = mask_secrets(text)
    assert masked == text
    assert count == 0


def test_5_idempotencia():
    text = 'PASSWORD=Sup3rS3cr3t!\nSECRET=OtroValorLargoDeSecreto123'
    once, _ = mask_secrets(text)
    twice, _ = mask_secrets(once)
    assert twice == once


def test_6_entrada_vacia_none_safe():
    assert mask_secrets("") == ("", 0)
    assert mask_secrets(None) == (None, 0) or mask_secrets(None)[1] == 0


def test_7_orden_enmascara_antes_de_truncar():
    """repo_diff: aunque el diff completo supere 200 KB y se trunque, el
    secreto (ubicado bien adentro del contenido) no debe viajar, porque el
    enmascarado corre ANTES del truncado."""
    secret_value = "Sup3rS3cr3tQueNoDebeViajar!"
    # ~300 KB de relleno con el secreto insertado bien adentro (posicion ~KB 250).
    filler_before = "+linea de relleno sin nada raro\n" * 7500  # ~247 KB
    secret_line = f"+PASSWORD={secret_value}\n"
    filler_after = "+linea de relleno sin nada raro\n" * 2000
    fake_diff = filler_before + secret_line + filler_after

    import services.console_repo as console_repo

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=fake_diff, stderr="")

    orig_run = subprocess.run
    subprocess.run = _fake_run
    try:
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / ".git").mkdir()
            result = console_repo.repo_diff(ws, ws / "archivo.txt")
    finally:
        subprocess.run = orig_run

    assert secret_value not in result["diff"]
    assert result["truncated"] is True
    assert len(result["diff"].encode("utf-8")) <= 200 * 1024


def test_8_un_megabyte_en_menos_de_500ms():
    text = "linea sin nada raro\n" * 50_000  # ~1 MB
    start = time.perf_counter()
    mask_secrets(text)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 500
