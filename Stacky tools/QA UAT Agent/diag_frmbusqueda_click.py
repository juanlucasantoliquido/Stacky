"""
diag_frmbusqueda_click.py — Encuentra la estrategia correcta de click para GridPersonas
"""
import asyncio, os, pathlib, sys, json
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

        await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
        await page.fill("#c_abfApellido1", "MONTEZUMA")
        await page.locator("#c_btnOk").click(no_wait_after=True)
        await page.wait_for_load_state("load", timeout=20000)
        try:
            await page.locator("#c_GridPersonas tbody tr").first.wait_for(timeout=10000)
        except:
            pass

        # Inspect JavaScript presence
        has_jquery = await page.evaluate("typeof jQuery !== 'undefined'")
        print(f"jQuery: {has_jquery}")

        # Get event listeners on row via CDP
        row_html = await page.locator("#c_GridPersonas tbody tr:first-child").evaluate("el => el.outerHTML")
        print(f"Row HTML (truncated): {row_html[:500]}")

        # Check jQuery events on row
        if has_jquery:
            row_events = await page.evaluate("(function(){ var row = document.querySelector('#c_GridPersonas tbody tr'); if (!row) return 'no row'; var events = jQuery._data(row, 'events'); return events ? Object.keys(events).join(',') : 'no events'; })()")
            print(f"Row jQuery events: {row_events}")

            icon_events = await page.evaluate("(function(){ var icon = document.querySelector('#c_GridPersonas tbody tr td i'); if (!icon) return 'no icon'; var events = jQuery._data(icon, 'events'); return events ? Object.keys(events).join(',') : 'no events'; })()")
            print(f"Icon jQuery events: {icon_events}")

            td_events = await page.evaluate("(function(){ var td = document.querySelector('#c_GridPersonas tbody tr td:first-child'); if (!td) return 'no td'; var events = jQuery._data(td, 'events'); return events ? Object.keys(events).join(',') : 'no events'; })()")
            print(f"TD jQuery events: {td_events}")

        # Strategy 1: click the <i> icon
        print("\n--- Strategy 1: click <i> icon ---")
        icon_locator = page.locator("#c_GridPersonas tbody tr:first-child td:first-child i")
        if await icon_locator.count() > 0:
            await icon_locator.click()
            await page.wait_for_timeout(3000)
            print(f"URL after icon click: {page.url}")
            if "FrmDetalleClie" in page.url:
                print("SUCCESS via icon click!")
                await browser.close()
                return

        # Strategy 2: click the first <td>
        print("--- Strategy 2: click first <td> ---")
        # Re-search (navigate back)
        await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
        await page.fill("#c_abfApellido1", "MONTEZUMA")
        await page.locator("#c_btnOk").click(no_wait_after=True)
        await page.wait_for_load_state("load", timeout=20000)
        try: await page.locator("#c_GridPersonas tbody tr").first.wait_for(timeout=10000)
        except: pass
        td = page.locator("#c_GridPersonas tbody tr:first-child td:first-child")
        if await td.count() > 0:
            await td.click()
            await page.wait_for_timeout(3000)
            print(f"URL after td click: {page.url}")
            if "FrmDetalleClie" in page.url:
                print("SUCCESS via td click!")
                await browser.close()
                return

        # Strategy 3: click entire row without no_wait_after
        print("--- Strategy 3: click row (no_wait_after=False) ---")
        await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
        await page.fill("#c_abfApellido1", "MONTEZUMA")
        await page.locator("#c_btnOk").click(no_wait_after=True)
        await page.wait_for_load_state("load", timeout=20000)
        try: await page.locator("#c_GridPersonas tbody tr").first.wait_for(timeout=10000)
        except: pass
        row = page.locator("#c_GridPersonas tbody tr:first-child")
        if await row.count() > 0:
            await row.click()  # no no_wait_after
            await page.wait_for_timeout(5000)
            print(f"URL after row click (no wait): {page.url}")
            if "FrmDetalleClie" in page.url:
                print("SUCCESS via row click (no wait)!")
                await browser.close()
                return

        # Strategy 4: try __doPostBack directly
        print("--- Strategy 4: __doPostBack ---")
        await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
        await page.fill("#c_abfApellido1", "MONTEZUMA")
        await page.locator("#c_btnOk").click(no_wait_after=True)
        await page.wait_for_load_state("load", timeout=20000)
        try: await page.locator("#c_GridPersonas tbody tr").first.wait_for(timeout=10000)
        except: pass

        # Find postback target from ViewState or __EVENTTARGET patterns
        grid_id = await page.evaluate("document.querySelector('#c_GridPersonas') ? document.querySelector('#c_GridPersonas').id : 'notfound'")
        print(f"Grid ID: {grid_id}")
        # Try __doPostBack with Select command
        try:
            await page.evaluate("__doPostBack('c_GridPersonas$ctl02', 'Select')")
            await page.wait_for_load_state("load", timeout=10000)
            print(f"URL after __doPostBack: {page.url}")
            if "FrmDetalleClie" in page.url:
                print("SUCCESS via __doPostBack!")
                await browser.close()
                return
        except Exception as e:
            print(f"__doPostBack error: {e}")

        # Strategy 5: Use FrmDetalleClie direct URL with session set via FrmBusqueda server click
        print("--- Strategy 5: Simulate click via form submit ---")
        # The AIS grid might work by submitting the form with __EVENTTARGET
        event_target_val = None
        try:
            et = await page.evaluate("document.getElementById('__EVENTTARGET') ? document.getElementById('__EVENTTARGET').value : 'not found'")
            print(f"__EVENTTARGET: {et}")
        except: pass

        # Try using the second data column (text cell) which might be a hyperlink
        await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
        await page.fill("#c_abfApellido1", "MONTEZUMA")
        await page.locator("#c_btnOk").click(no_wait_after=True)
        await page.wait_for_load_state("load", timeout=20000)
        try: await page.locator("#c_GridPersonas tbody tr").first.wait_for(timeout=10000)
        except: pass

        # Try each TD
        for td_idx in range(4):
            td_n = page.locator(f"#c_GridPersonas tbody tr:first-child td").nth(td_idx)
            if await td_n.count() > 0:
                td_html = await td_n.evaluate("el => el.outerHTML")
                print(f"TD[{td_idx}]: {td_html[:200]}")

        await page.screenshot(path=str(EVDIR / "diag_click_strategies.png"))
        print(f"\nAll strategies FAILED. Check screenshot.")
        await browser.close()

asyncio.run(main())
