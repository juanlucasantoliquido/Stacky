"""
Login OAuth de GitHub Copilot vía device flow.

Genera un token con scopes Copilot (formato `ghu_...`) y lo guarda en
`backend/.copilot_token`. Usa el client_id público del plugin Copilot Vim,
el mismo que usan la mayoría de las integraciones third-party.

Uso:
    cd "Tools/Stacky Agents/backend"
    .venv\\Scripts\\python.exe scripts/copilot_login.py

Te va a mostrar un código corto y una URL. Abrís la URL en el browser
(donde estás logueado a GitHub con tu cuenta de Copilot Pro), pegás el
código, autorizás, y el script termina escribiendo el token al disco.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Truststore para que la SSL funcione detrás de Zscaler / proxies corporativos.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import requests


CLIENT_ID = "Iv1.b507a08c87ecfe98"  # GitHub Copilot Vim plugin (público)
DEVICE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
TOKEN_FILE = Path(__file__).resolve().parent.parent / ".copilot_token"

EDITOR_HEADERS = {
    "Editor-Version": "vscode/1.95.0",
    "Editor-Plugin-Version": "copilot-chat/0.20.0",
    "User-Agent": "GitHubCopilotChat/0.20.0",
}


def request_device_code() -> dict:
    resp = requests.post(
        DEVICE_URL,
        headers={"Accept": "application/json", **EDITOR_HEADERS},
        data={"client_id": CLIENT_ID, "scope": "read:user"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def poll_for_token(device_code: str, interval: int, expires_in: int) -> str:
    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        resp = requests.post(
            TOKEN_URL,
            headers={"Accept": "application/json", **EDITOR_HEADERS},
            data={
                "client_id": CLIENT_ID,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=15,
        )
        data = resp.json()
        if "access_token" in data:
            return data["access_token"]
        err = data.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        raise RuntimeError(f"OAuth device flow falló: {data}")
    raise TimeoutError("Device flow expirado sin autorizar.")


def main() -> int:
    print(">>> Solicitando device code a GitHub...")
    info = request_device_code()
    user_code = info["user_code"]
    verify_url = info.get("verification_uri") or info.get("verification_uri_complete")
    interval = int(info.get("interval", 5))
    expires_in = int(info.get("expires_in", 900))

    print()
    print("=" * 60)
    print(f"  Abrí esta URL en el browser:  {verify_url}")
    print(f"  Y pegá este código:           {user_code}")
    print("=" * 60)
    print()
    print("Esperando autorización... (Ctrl+C para cancelar)")

    try:
        token = poll_for_token(info["device_code"], interval, expires_in)
    except KeyboardInterrupt:
        print("\nCancelado.")
        return 1

    TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
    print()
    print(f"OK — token guardado en {TOKEN_FILE}")
    print("Ya podés arrancar el backend; el ModelPicker va a listar tus modelos reales.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
