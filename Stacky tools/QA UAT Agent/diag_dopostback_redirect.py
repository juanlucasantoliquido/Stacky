"""
diag_dopostback_redirect.py — Verifica si __doPostBack con UniqueID correcto navega a FrmDetalleClie
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

GRID_OBL_UNIQUE_ID = "ctl00$c$GridObligaciones"   # confirmed from prev run

async def login_and_load_obligations(page):
    await page.goto(f"{BASE}FrmLogin.aspx", wait_until="load")
    await page.fill("#c_abfUsuario", USER)
    await page.fill("#c_abfContrasena", PASS)
    await page.locator("#c_btnOk").click(no_wait_after=True)
    try: await page.wait_for_url(lambda u: "FrmLogin" not in u, timeout=25000)
    except: pass
    await page.wait_for_load_state("load", timeout=20000)

    await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
    await page.fill("#c_abfApellido1", "MONTEZUMA")
    await page.locator("#c_btnOk").click(no_wait_after=True)
    await page.wait_for_load_state("load", timeout=20000)
    try: await page.locator("#c_GridPersonas tbody tr").first.wait_for(timeout=10000)
    except: pass

    icon = page.locator("#c_GridPersonas tbody tr:first-child td:first-child i")
    if await icon.count() > 0:
        await icon.click()
        await page.wait_for_timeout(3000)

    cnt = await page.locator("#c_GridObligaciones tbody tr").count()
    print(f"GridObligaciones rows: {cnt}")
    return cnt > 0

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # ── TEST 1: __doPostBack + wait_for_url (FrmDetalleClie) ──────────────
        print("=== TEST 1: __doPostBack + wait_for_url ===")
        page1 = await browser.new_page()
        ok = await login_and_load_obligations(page1)
        if ok:
            # Row 1 = MOR0026973 (highest debt 44161.92) = correct Corredor Principal
            print(f"  Calling __doPostBack('{GRID_OBL_UNIQUE_ID}', 'Select$1')")
            await page1.evaluate(f"__doPostBack('{GRID_OBL_UNIQUE_ID}', 'Select$1')")
            try:
                await page1.wait_for_url(lambda u: "FrmDetalleClie" in u, timeout=20000)
                print(f"  SUCCESS! URL: {page1.url}")
                await page1.wait_for_load_state("load", timeout=15000)
                await page1.screenshot(path=str(EVDIR / "test1_detalleclie.png"))
                print(f"  Screenshot saved")
                await browser.close()
                print("RESULT: __doPostBack + wait_for_url WORKS!")
                return
            except Exception as e:
                await page1.wait_for_timeout(2000)
                print(f"  URL after wait: {page1.url}")
                print(f"  Error: {e}")

        # ── TEST 2: __doPostBack row 0 + wait_for_url ─────────────────────────
        print("\n=== TEST 2: __doPostBack row 0 + wait_for_url ===")
        page2 = await browser.new_page()
        ok2 = await login_and_load_obligations(page2)
        if ok2:
            print(f"  Calling __doPostBack('{GRID_OBL_UNIQUE_ID}', 'Select$0')")
            await page2.evaluate(f"__doPostBack('{GRID_OBL_UNIQUE_ID}', 'Select$0')")
            try:
                await page2.wait_for_url(lambda u: "FrmDetalleClie" in u, timeout=20000)
                print(f"  SUCCESS! URL: {page2.url}")
                await page2.screenshot(path=str(EVDIR / "test2_detalleclie.png"))
                await browser.close()
                return
            except Exception as e:
                await page2.wait_for_timeout(2000)
                print(f"  URL: {page2.url}, Error: {e}")

        # ── TEST 3: Listen for ANY navigation after __doPostBack ───────────────
        print("\n=== TEST 3: Listen for navigation + long timeout ===")
        page3 = await browser.new_page()
        ok3 = await login_and_load_obligations(page3)
        if ok3:
            nav_url = []
            page3.on("framenavigated", lambda f: nav_url.append(f.url) if "FrmDetalleClie" in f.url else None)
            
            print(f"  Calling __doPostBack + waiting 15s for any navigation...")
            await page3.evaluate(f"__doPostBack('{GRID_OBL_UNIQUE_ID}', 'Select$1')")
            await page3.wait_for_timeout(15000)
            print(f"  Final URL: {page3.url}")
            print(f"  FrmDetalleClie navigations: {nav_url}")
            if "FrmDetalleClie" in page3.url:
                print("SUCCESS (via timeout)!")
                await page3.screenshot(path=str(EVDIR / "test3_detalleclie.png"))
                await browser.close()
                return
        
        # ── TEST 4: WebResource.axd first script (AIS framework JS) ────────────
        print("\n=== TEST 4: Fetch WebResource content ===")
        page4 = await browser.new_page()
        ok4 = await login_and_load_obligations(page4)
        if ok4:
            webresource_url = await page4.evaluate("""(function(){
                var scripts = document.querySelectorAll('script[src]');
                for (var i = 0; i < scripts.length; i++) {
                    if (scripts[i].src.indexOf('WebResource') !== -1) return scripts[i].src;
                }
                return null;
            })()""")
            print(f"  WebResource URL: {webresource_url}")
            if webresource_url:
                # Fetch the content
                js_content = await page4.evaluate(f"""
                    (async function() {{
                        var r = await fetch('{webresource_url}');
                        var t = await r.text();
                        // Look for clickable/gridIcon/Select handler
                        var idx = t.indexOf('clickable');
                        return idx >= 0 ? t.substring(Math.max(0,idx-100), Math.min(t.length, idx+500)) : 'not found';
                    }})()
                """)
                print(f"  WebResource 'clickable' context: {js_content[:500]}")

        await browser.close()
        print("\nAll tests done.")

asyncio.run(main())
