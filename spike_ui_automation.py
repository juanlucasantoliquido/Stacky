"""
spike_ui_automation.py — Test de UI automation sobre VS Code + Copilot Chat

Ejecutar con VS Code abierto y Copilot Chat visible.

Uso:
    cd tools/mantis_scraper
    python spike_ui_automation.py

Valida:
    1. pywinauto puede encontrar la ventana de VS Code
    2. pyautogui puede abrir Copilot Chat (Ctrl+Alt+I)
    3. pyperclip puede pegar texto con caracteres especiales (tildes, ñ)

NO presionar Enter durante el test — es solo una prueba de escritura en el input.
"""

import sys
import time

TEXTO_CON_TILDES = "Probando: Santolíquido, ñoño, ¿funciona? — test 123"


def main():
    # ── 1. Verificar dependencias ─────────────────────────────────────────────
    try:
        import pyperclip
        import pyautogui
        import pywinauto
        print("[OK] Dependencias importadas correctamente")
    except ImportError as e:
        print(f"[ERROR] Dependencia faltante: {e}")
        print("       Ejecutar: pip install pywinauto pyautogui pyperclip")
        sys.exit(1)

    # ── 2. Buscar ventana VS Code ─────────────────────────────────────────────
    print("\nBuscando ventana VS Code...")
    desktop = pywinauto.Desktop(backend="uia")

    vscode_windows = [
        w for w in desktop.windows()
        if "Visual Studio Code" in (w.window_text() or "")
    ]

    if not vscode_windows:
        # Fallback: buscar por título parcial
        try:
            app = pywinauto.Application(backend="uia").connect(title_re=".*Code.*")
            vscode_windows = [app.top_window()]
            print("[WARN] Usando fallback regex para encontrar VS Code")
        except Exception:
            pass

    if not vscode_windows:
        print("[ERROR] No se encontró VS Code abierto.")
        print("       Asegurate de que VS Code esté abierto antes de ejecutar este script.")
        sys.exit(1)

    win = vscode_windows[0]
    print(f"[OK] Encontrado: {win.window_text()!r}")

    # ── 3. Enfocar ventana ────────────────────────────────────────────────────
    try:
        win.set_focus()
        time.sleep(0.8)
        print("[OK] VS Code enfocado")
    except Exception as e:
        print(f"[ERROR] No se pudo enfocar VS Code: {e}")
        sys.exit(1)

    # ── 4. Abrir Copilot Chat ─────────────────────────────────────────────────
    print("\nAbriendo Copilot Chat (Ctrl+Alt+I)...")
    pyautogui.hotkey('ctrl', 'alt', 'i')
    time.sleep(2.0)
    print("[OK] Shortcut enviado — verificar manualmente que el chat se abrió")

    # ── 5. Pegar texto con tildes via clipboard ───────────────────────────────
    print(f"\nPegando texto de prueba: {TEXTO_CON_TILDES!r}")
    pyperclip.copy(TEXTO_CON_TILDES)
    time.sleep(0.2)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.5)

    # ── 6. Resultado ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("[TEST COMPLETO]")
    print("=" * 60)
    print("Verificar MANUALMENTE que:")
    print("  1. El panel de Copilot Chat está abierto")
    print(f"  2. El texto '{TEXTO_CON_TILDES}' aparece en el input")
    print("  3. Los caracteres ó, í, ñ, ¿, — se ven correctamente")
    print("")
    print("NO presionar Enter — borrar el texto de prueba después de verificar.")
    print("=" * 60)

    # ── 7. Limpiar clipboard ──────────────────────────────────────────────────
    pyperclip.copy("")


if __name__ == "__main__":
    main()
