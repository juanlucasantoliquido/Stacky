"""
diag_ais_grid_mechanism.py — Descubre el UniqueID del grid y el mecanismo correcto de __doPostBack
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
        try: await page.locator("#c_GridPersonas tbody tr").first.wait_for(timeout=10000)
        except: pass

        # Get data-unique-id of GridPersonas table
        gp_attrs = await page.evaluate("""(function(){
            var t = document.getElementById('c_GridPersonas');
            if (!t) return 'not found';
            return {uniqueId: t.getAttribute('data-unique-id'), className: t.className};
        })()""")
        print(f"GridPersonas attributes: {gp_attrs}")

        # Click GridPersonas icon to load GridObligaciones
        icon = page.locator("#c_GridPersonas tbody tr:first-child td:first-child i")
        if await icon.count() > 0:
            await icon.click()
            await page.wait_for_timeout(3000)

        # Get data-unique-id of GridObligaciones table
        go_attrs = await page.evaluate("""(function(){
            var t = document.getElementById('c_GridObligaciones');
            if (!t) return 'not found';
            return {uniqueId: t.getAttribute('data-unique-id'), className: t.className};
        })()""")
        print(f"GridObligaciones attributes: {go_attrs}")

        # Try __doPostBack with correct UniqueID format
        unique_id = None
        if isinstance(go_attrs, dict):
            unique_id = go_attrs.get('uniqueId')
        print(f"GridObligaciones UniqueID: {unique_id}")

        # Look for all script content that mentions 'clickable' or 'data-unique-id'
        scripts_info = await page.evaluate("""(function(){
            var scripts = document.querySelectorAll('script');
            var content = '';
            for (var i = 0; i < scripts.length; i++) {
                var s = scripts[i].textContent;
                if (s.indexOf('clickable') !== -1 || s.indexOf('unique-id') !== -1 || s.indexOf('UniqueID') !== -1) {
                    content += '--- script ' + i + ' ---\\n' + s.substring(0, 500) + '\\n';
                }
            }
            return content.substring(0, 3000) || 'no scripts found';
        })()""")
        print(f"Scripts with 'clickable'/'unique-id':\n{scripts_info[:1500]}")

        # Check JS source files loaded
        all_scripts = await page.evaluate("""(function(){
            var scripts = document.querySelectorAll('script[src]');
            var srcs = [];
            for (var i = 0; i < scripts.length; i++) {
                srcs.push(scripts[i].src);
            }
            return srcs;
        })()""")
        print(f"\nLoaded JS files: {all_scripts}")

        # Try __doPostBack with UniqueID
        if unique_id:
            print(f"\n--- Trying __doPostBack('{unique_id}', 'Select$1') (row 1 = MOR0026973 highest debt) ---")
            try:
                await page.evaluate(f"__doPostBack('{unique_id}', 'Select$1')")
                await page.wait_for_load_state("load", timeout=10000)
                print(f"URL: {page.url}")
                if "FrmDetalleClie" in page.url:
                    print("SUCCESS!")
                    await browser.close()
                    return
            except Exception as e:
                print(f"Error: {e}")

            print(f"\n--- Trying __doPostBack('{unique_id}', 'Select$0') (row 0 = MOR0024967) ---")
            # Need to reload GridObligaciones first
            await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
            await page.fill("#c_abfApellido1", "MONTEZUMA")
            await page.locator("#c_btnOk").click(no_wait_after=True)
            await page.wait_for_load_state("load", timeout=20000)
            try: await page.locator("#c_GridPersonas tbody tr").first.wait_for(timeout=10000)
            except: pass
            icon2 = page.locator("#c_GridPersonas tbody tr:first-child td:first-child i")
            if await icon2.count() > 0:
                await icon2.click()
                await page.wait_for_timeout(3000)
            try:
                await page.evaluate(f"__doPostBack('{unique_id}', 'Select$0')")
                await page.wait_for_load_state("load", timeout=10000)
                print(f"URL: {page.url}")
                if "FrmDetalleClie" in page.url:
                    print("SUCCESS!")
                    await browser.close()
                    return
            except Exception as e:
                print(f"Error: {e}")

        # Capture network requests to see what happens on row click
        print("\n--- Capturing network on row click ---")
        await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
        await page.fill("#c_abfApellido1", "MONTEZUMA")
        await page.locator("#c_btnOk").click(no_wait_after=True)
        await page.wait_for_load_state("load", timeout=20000)
        try: await page.locator("#c_GridPersonas tbody tr").first.wait_for(timeout=10000)
        except: pass
        icon3 = page.locator("#c_GridPersonas tbody tr:first-child td:first-child i")
        if await icon3.count() > 0:
            await icon3.click()
            await page.wait_for_timeout(3000)

        responses = []
        page.on("response", lambda r: responses.append((r.url, r.status)))
        obl_row = page.locator("#c_GridObligaciones tbody tr:first-child")
        if await obl_row.count() > 0:
            await obl_row.click()
            await page.wait_for_timeout(4000)
            print(f"URL after row click: {page.url}")
            print(f"Captured responses: {[(url[-60:], status) for url, status in responses[-5:]]}")

        await page.screenshot(path=str(EVDIR / "diag_ais_mechanism.png"))
        await browser.close()
        print("\nDone. Check evidence/119/diag_ais_mechanism.png")

asyncio.run(main())
