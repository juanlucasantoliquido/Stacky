"""
diag_full_nav.py — Captura TODAS las navegaciones y respuestas tras __doPostBack
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
        browser = await p.chromium.launch(headless=False)  # headful for visibility
        page = await browser.new_page()

        # Capture all responses
        all_responses = []
        async def on_response(response):
            try:
                ct = response.headers.get("content-type", "")
                all_responses.append({
                    "url": response.url,
                    "method": response.request.method,
                    "status": response.status,
                    "is_redirect": response.status in (301, 302, 303, 307, 308),
                    "content_type": ct[:60],
                })
            except:
                pass
        page.on("response", on_response)

        # Capture all navigations
        all_navs = []
        def on_framenavigated(frame):
            if frame == page.main_frame:
                all_navs.append(frame.url)
        page.on("framenavigated", on_framenavigated)

        # Handle dialogs (capture message, dismiss)
        dialogs = []
        async def on_dialog(dialog):
            dialogs.append({"type": dialog.type, "message": dialog.message[:200]})
            await dialog.dismiss()
        page.on("dialog", on_dialog)

        # Login
        print("=== LOGIN ===")
        await page.goto(f"{BASE}FrmLogin.aspx", wait_until="load")
        await page.fill("#c_abfUsuario", USER)
        await page.fill("#c_abfContrasena", PASS)
        await page.locator("#c_btnOk").click(no_wait_after=True)
        try: await page.wait_for_url(lambda u: "FrmLogin" not in u, timeout=25000)
        except: pass
        await page.wait_for_load_state("load", timeout=20000)
        print(f"After login: {page.url}")

        # Navigate to FrmBusqueda
        print("\n=== FRMBUSQUEDA ===")
        all_responses.clear()
        await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
        await page.fill("#c_abfApellido1", "MONTEZUMA")
        
        # Click btnOk
        print("Clicking btnOk...")
        all_responses.clear()
        await page.locator("#c_btnOk").click(no_wait_after=True)
        await page.wait_for_load_state("load", timeout=20000)
        await page.wait_for_timeout(2000)
        print(f"After btnOk: {page.url}")
        
        cnt = await page.locator("#c_GridPersonas tbody tr").count()
        print(f"GridPersonas rows: {cnt}")

        # Click GridPersonas icon
        print("\nClicking GridPersonas icon...")
        all_responses.clear()
        icon = page.locator("#c_GridPersonas tbody tr:first-child td:first-child i")
        if await icon.count() > 0:
            await icon.click()
            await page.wait_for_timeout(3000)
        
        cnt2 = await page.locator("#c_GridObligaciones tbody tr").count()
        print(f"GridObligaciones rows: {cnt2}")

        if cnt2 == 0:
            print("ERROR: no obligations loaded")
            await browser.close()
            return

        # Get UniqueID
        uid = await page.evaluate("""(function(){
            var go = document.getElementById('c_GridObligaciones');
            return go ? ($(go).data('uniqueId') || go.getAttribute('data-unique-id')) : null;
        })()""")
        print(f"GridObligaciones UID: {uid}")

        # Print current state
        state = await page.evaluate("""(function(){
            var f = document.querySelector('form');
            return {
                isAsync: typeof Sys !== 'undefined' && Sys.WebForms && 
                          Sys.WebForms.PageRequestManager.getInstance()._processingRequest,
                eventtarget: f['__EVENTTARGET'] ? f['__EVENTTARGET'].value : 'N/A',
                viewstateLen: f['__VIEWSTATE'] ? f['__VIEWSTATE'].value.length : 0
            };
        })()""")
        print(f"Pre-doPostBack state: {state}")

        # Now trigger GridObligaciones postback and monitor EVERYTHING
        print(f"\n=== __doPostBack({uid}, 'Select$1') ===")
        all_responses.clear()
        all_navs.clear()
        dialogs.clear()
        
        # Start navigation expectation BEFORE calling __doPostBack
        try:
            async with page.expect_navigation(timeout=20000) as nav_info:
                await page.evaluate(f"window.__doPostBack('{uid}', 'Select$1')")
            nav = await nav_info.value
            print(f"Navigation detected! URL: {page.url}")
            await page.wait_for_load_state("load", timeout=15000)
            print(f"After load: {page.url}")
            await page.screenshot(path=str(EVDIR / "after_dopostback.png"))
            print(f"Screenshot saved")
        except Exception as e:
            print(f"No navigation within 20s: {e}")
            print(f"Current URL: {page.url}")
            await page.screenshot(path=str(EVDIR / "after_dopostback_timeout.png"))

        print(f"\nAll navigations captured: {all_navs}")
        print(f"All dialogs: {dialogs}")
        print(f"\nAll responses ({len(all_responses)} total):")
        for r in all_responses[-20:]:  # last 20
            print(f"  [{r['method']} {r['status']}] {r['url'][:80]}")

        # If we're at FrmDetalleClie, verify ADO-119 fields
        if "FrmDetalleClie" in page.url:
            print("\n=== FrmDetalleClie LOADED - checking ADO-119 fields ===")
            corredor_val = await page.evaluate("""(function(){
                var el = document.querySelector("[id*='abfCorredorPrincipal']");
                return el ? {found:true, value: el.value, visible: el.offsetParent !== null} : {found:false};
            })()""")
            riesgo_val = await page.evaluate("""(function(){
                var el = document.querySelector("[id*='abfRiesgoCliente']");
                return el ? {found:true, value: el.value, visible: el.offsetParent !== null} : {found:false};
            })()""")
            print(f"abfCorredorPrincipal: {corredor_val}")
            print(f"abfRiesgoCliente: {riesgo_val}")
        
        await page.wait_for_timeout(3000)
        await browser.close()

asyncio.run(main())
