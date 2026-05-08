"""
diag_frmbusqueda_2step.py — Diagnóstico del flujo de 2 pasos en FrmBusqueda
GridPersonas → GridObligaciones → FrmDetalleClie
"""
import asyncio, os, pathlib, sys
sys.stdout.reconfigure(encoding='utf-8')

_env_path = pathlib.Path(__file__).parent / "../../.secrets/agenda_web.env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

BASE = os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/").rstrip("/") + "/"
USER = os.environ.get("AGENDA_WEB_USER", "PABLO")
PASS = os.environ.get("AGENDA_WEB_PASS", "PABLO")
EVDIR = pathlib.Path(__file__).parent / "evidence" / "119"
EVDIR.mkdir(parents=True, exist_ok=True)

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Login
        await page.goto(f"{BASE}FrmLogin.aspx", wait_until="load")
        await page.fill("#c_abfUsuario", USER)
        await page.fill("#c_abfContrasena", PASS)
        await page.locator("#c_btnOk").click(no_wait_after=True)
        try: await page.wait_for_url(lambda u: "FrmLogin" not in u, timeout=25000)
        except: pass
        await page.wait_for_load_state("load", timeout=20000)
        print(f"Login → {page.url}")

        # FrmBusqueda search
        await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
        await page.fill("#c_abfApellido1", "MONTEZUMA")
        await page.locator("#c_btnOk").click(no_wait_after=True)
        await page.wait_for_load_state("load", timeout=20000)
        try: await page.locator("#c_GridPersonas tbody tr").first.wait_for(timeout=10000)
        except: pass

        print(f"After search. URL: {page.url}")
        cnt = await page.locator("#c_GridPersonas tbody tr").count()
        print(f"GridPersonas rows: {cnt}")

        # STEP 1: Click the icon in GridPersonas (should load GridObligaciones)
        print("\n--- STEP 1: Click GridPersonas icon ---")
        icon = page.locator("#c_GridPersonas tbody tr:first-child td:first-child i")
        if await icon.count() > 0:
            await icon.click()
            # Wait for UpdatePanel update
            await page.wait_for_timeout(3000)
            print(f"URL after GridPersonas icon click: {page.url}")

            # Check GridObligaciones
            obl_html = await page.locator("#c_GridObligaciones").inner_html() if await page.locator("#c_GridObligaciones").count() > 0 else "not found"
            print(f"GridObligaciones HTML (truncated): {obl_html[:500]}")

            obl_rows = await page.locator("#c_GridObligaciones tbody tr").count()
            print(f"GridObligaciones rows: {obl_rows}")
        else:
            print("Icon not found!")

        # Take screenshot after step 1
        await page.screenshot(path=str(EVDIR / "diag_step1.png"))

        # STEP 2: Click GridObligaciones row (should navigate to FrmDetalleClie)
        print("\n--- STEP 2: Click GridObligaciones row ---")
        obl_cnt = await page.locator("#c_GridObligaciones tbody tr").count()
        print(f"GridObligaciones rows before click: {obl_cnt}")

        if obl_cnt > 0:
            # Check what the rows look like
            for i in range(min(obl_cnt, 2)):
                row = page.locator("#c_GridObligaciones tbody tr").nth(i)
                row_html = await row.evaluate("el => el.outerHTML")
                print(f"OblRow[{i}] HTML: {row_html[:300]}")

            # Try clicking the icon in first row
            obl_icon = page.locator("#c_GridObligaciones tbody tr:first-child td:first-child i")
            obl_td = page.locator("#c_GridObligaciones tbody tr:first-child td:first-child")
            obl_row = page.locator("#c_GridObligaciones tbody tr:first-child")

            if await obl_icon.count() > 0:
                print("Clicking GridObligaciones icon...")
                await obl_icon.click()
            else:
                print("No icon — clicking row...")
                await obl_row.click()

            try:
                await page.wait_for_url(lambda u: "FrmDetalleClie" in u, timeout=15000)
                print(f"SUCCESS! URL: {page.url}")
            except Exception as e:
                await page.wait_for_timeout(3000)
                print(f"Timeout. URL: {page.url}")

        await page.screenshot(path=str(EVDIR / "diag_step2.png"))
        print(f"Screenshots: diag_step1.png, diag_step2.png")
        await browser.close()

asyncio.run(main())
