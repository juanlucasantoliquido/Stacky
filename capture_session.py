"""
capture_session.py
Uso único: abre el browser con UI visible, permite hacer login SSO
en MantisBT, y guarda el estado de sesión en auth/auth.json.

Ejecutar:
    cd tools/mantis_scraper
    pip install playwright
    playwright install chromium
    python capture_session.py
"""

import json
import os
from playwright.sync_api import sync_playwright

AUTH_PATH = "auth/auth.json"
MANTIS_URL = "https://soporte.ais-int.net/mantis/view_all_bug_page.php"


def capture_session():
    os.makedirs("auth", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # HEADED para login manual
        context = browser.new_context()
        page = context.new_page()

        page.goto(MANTIS_URL)

        print("=" * 50)
        print("Completá el login en el browser.")
        print("Cuando veas la tabla de tickets, presioná ENTER aquí.")
        print("=" * 50)
        input()

        context.storage_state(path=AUTH_PATH)
        print(f"Sesión guardada en: {AUTH_PATH}")

        browser.close()


if __name__ == "__main__":
    capture_session()
