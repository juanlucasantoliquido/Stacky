"""
diag_119_discovery.py — Phase 1: discover live FrmDetalleClie DOM
and check for abfCorredorPrincipal / abfRiesgoCliente fields.
ADO-119 | RF-006
"""
import asyncio, os, sys, json, re

BASE = os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")
USER = os.environ.get("AGENDA_WEB_USER", "PACIFICO")
PASS = os.environ.get("AGENDA_WEB_PASS", "PACIFICO")

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        # Login
        print(f"[1] Login as {USER} @ {BASE}")
        await page.goto(f"{BASE}FrmLogin.aspx", wait_until="load")
        await page.fill("#c_abfUsuario", USER)
        await page.fill("#c_abfContrasena", PASS)
        await page.locator("#c_btnOk").click(no_wait_after=True)
        try:
            await page.wait_for_url(
                lambda url: any(s in url for s in ["FrmAgenda", "FrmCambioPass"]),
                timeout=25000)
        except Exception as e:
            print(f"  [WARN] waitForURL: {e}")
        await page.wait_for_load_state("load", timeout=20000)
        print(f"  URL after login: {page.url}")

        # Navigate to FrmAgenda
        print("[2] Navigate to FrmAgenda")
        await page.goto(f"{BASE}FrmAgenda.aspx", wait_until="load")
        await page.wait_for_load_state("networkidle", timeout=15000)

        # Find first row in GridAgendaUsu
        rows = page.locator("#c_GridAgendaUsu tbody tr")
        row_count = await rows.count()
        print(f"  GridAgendaUsu rows: {row_count}")

        if row_count == 0:
            print("  [WARN] No rows in GridAgendaUsu - trying GridAgendaAut")
            rows = page.locator("#c_GridAgendaAut tbody tr")
            row_count = await rows.count()
            print(f"  GridAgendaAut rows: {row_count}")

        if row_count == 0:
            print("  [ERROR] No lotes found in agenda - BLOCKED")
            await browser.close()
            return

        # Click first row to navigate to FrmDetalleClie
        print(f"[3] Click first lote row")
        first_row = rows.first
        await first_row.click(no_wait_after=True)
        try:
            await page.wait_for_url(lambda url: "FrmDetalleClie" in url, timeout=20000)
        except Exception as e:
            print(f"  [WARN] waitForURL FrmDetalleClie: {e}")
            # Try direct navigation via session
            current_url = page.url
            print(f"  Current URL: {current_url}")
        await page.wait_for_load_state("load", timeout=20000)
        print(f"  URL: {page.url}")

        await page.screenshot(path="evidence/119/diag_01_detalleclie.png")
        print("  Screenshot: evidence/119/diag_01_detalleclie.png")

        # Check for new fields
        print("[4] Checking for new fields...")
        
        candidates = [
            "#c_abfCorredorPrincipal",
            "#c_abfRiesgoCliente",
            "input[id*='CorredorPrincipal']",
            "input[id*='RiesgoCliente']",
            "span[id*='CorredorPrincipal']",
            "span[id*='RiesgoCliente']",
            "*[id*='CorredorPrincipal']",
            "*[id*='RiesgoCliente']",
        ]
        for sel in candidates:
            try:
                cnt = await page.locator(sel).count()
                print(f"  {sel}: count={cnt}")
                if cnt > 0:
                    try:
                        visible = await page.locator(sel).first.is_visible()
                        text = await page.locator(sel).first.text_content()
                        print(f"    visible={visible}, text='{text}'")
                    except: pass
            except Exception as e:
                print(f"  {sel}: ERROR {e}")

        # Dump all AISBusinessField labels in top panel
        print("\n[5] All AISBusinessField labels in top section:")
        label_els = page.locator(".aisfieldbody label, .aisfield label")
        label_count = await label_els.count()
        for i in range(min(label_count, 30)):
            try:
                text = await label_els.nth(i).text_content()
                print(f"  [{i}] {text.strip()}")
            except: pass

        # Check Corredor/Riesgo by text
        print("\n[6] Searching by label text:")
        for text in ["Corredor Principal", "Riesgo de Cliente", "Corredor", "Riesgo"]:
            cnt = await page.get_by_text(text, exact=False).count()
            print(f"  '{text}': {cnt} elements")

        # Dump page HTML snippet of top panel
        print("\n[7] Top panel HTML snippet (first 2000 chars):")
        try:
            panel_html = await page.locator(".z-depth-1.section").first.inner_html()
            print(panel_html[:2000])
        except Exception as e:
            print(f"  ERROR: {e}")
            # Try alternate selectors
            try:
                panel_html = await page.locator(".row.z-depth-1").first.inner_html()
                print(panel_html[:2000])
            except: pass

        await browser.close()

asyncio.run(main())
