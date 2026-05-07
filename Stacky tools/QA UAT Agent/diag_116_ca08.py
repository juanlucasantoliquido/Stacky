"""
diag_116_ca08.py — Verifica visibilidad del counter "Promesas a Vencer en 7 días"
para usuario PACIFICO (debe verse) y SANCHEZRO (CA-08: NO debe verse).
"""
import asyncio
import os
import sys
from playwright.async_api import async_playwright

BASE = os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")

async def check_user(user: str, pwd: str) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(f"{BASE}FrmLogin.aspx", wait_until="load")
            await page.fill("#c_abfUsuario", user)
            await page.fill("#c_abfContrasena", pwd)
            await page.locator("#c_btnOk").click(no_wait_after=True)
            try:
                await page.wait_for_url(
                    lambda url: any(s in url for s in ["FrmAgenda", "FrmAgendaJudicial", "FrmCambioPass"]),
                    timeout=25000
                )
            except Exception as e:
                print(f"  [WARN] waitForURL timeout for {user}: {e}", file=sys.stderr)
            await page.wait_for_load_state("load", timeout=20000)

            final_url = page.url
            # Get barraResumen inner HTML (if present)
            barra_count = await page.locator(".barraResumen").count()
            barra_html = ""
            if barra_count:
                barra_html = await page.locator(".barraResumen").first.inner_html()

            # Check for the counter text
            counter_count = await page.get_by_text("Promesas a Vencer", exact=False).count()
            counter_count2 = await page.locator("text=/Promesas.*Vencer.*7/i").count()

            await page.screenshot(path=f"evidence/116/diag_ca08_{user}.png")
            return {
                "user": user,
                "url": final_url,
                "barraResumen_found": barra_count > 0,
                "counter_visible": counter_count > 0 or counter_count2 > 0,
                "barra_html_snippet": barra_html[:500] if barra_html else "(none)",
            }
        finally:
            await browser.close()


async def main():
    print("=== DIAG CA-08: Visibilidad contador Promesas a Vencer 7 días ===\n")

    pacifico = await check_user("PACIFICO", "PACIFICO")
    print(f"[PACIFICO] URL={pacifico['url']}")
    print(f"  barraResumen_found: {pacifico['barraResumen_found']}")
    print(f"  counter_visible:    {pacifico['counter_visible']}")
    print(f"  barra_html_snippet:\n    {pacifico['barra_html_snippet'][:300]}\n")

    sanchezro = await check_user("SANCHEZRO", "SANCHEZRO")
    print(f"[SANCHEZRO] URL={sanchezro['url']}")
    print(f"  barraResumen_found: {sanchezro['barraResumen_found']}")
    print(f"  counter_visible:    {sanchezro['counter_visible']}")
    print(f"  barra_html_snippet:\n    {sanchezro['barra_html_snippet'][:300]}\n")

    # Verdict
    ca08_ok = pacifico['counter_visible'] and not sanchezro['counter_visible']
    print(f"=== CA-08 VERDICT ===")
    print(f"PACIFICO sees counter:   {'PASS' if pacifico['counter_visible'] else 'FAIL'} (esperado: YES)")
    print(f"SANCHEZRO sees counter:  {'PASS' if not sanchezro['counter_visible'] else 'FAIL_CA08'} (esperado: NO)")
    print(f"CA-08 OVERALL:           {'PASS' if ca08_ok else '*** FAIL — counter visible para no-Pacifico ***'}")


asyncio.run(main())
