"""
diag_scriptmanager_registration.py — Verifica qué controles están registrados como async postback triggers
y prueba la alternativa: postback directo via form submit
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
    await page.wait_for_timeout(1000)
    try: await page.locator("#c_GridPersonas tbody tr").first.wait_for(timeout=10000)
    except: pass
    await page.wait_for_timeout(500)

    icon = page.locator("#c_GridPersonas tbody tr:first-child td:first-child i")
    if await icon.count() > 0:
        await icon.click()
        await page.wait_for_timeout(3000)
    cnt = await page.locator("#c_GridObligaciones tbody tr").count()
    return cnt > 0

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Handle dialogs
        dialogs = []
        async def on_dialog(dialog):
            dialogs.append({"type": dialog.type, "msg": dialog.message[:300]})
            await dialog.dismiss()
        page.on("dialog", on_dialog)

        ok = await login_and_load_obligations(page)
        print(f"Obligations loaded: {ok}")

        # === TEST 1: Check ScriptManager registration ===
        print("\n=== ScriptManager Registration ===")
        sm_info = await page.evaluate("""(function(){
            if (typeof Sys === 'undefined') return {error: 'Sys not defined'};
            var prm = Sys.WebForms.PageRequestManager.getInstance();
            if (!prm) return {error: 'PRM not available'};
            // Check registered async controls
            var asyncTriggers = prm._asyncPostBackControlIDs || [];
            var postbackTriggers = prm._postBackControlIDs || [];
            var panels = prm._updatePanelIDs || [];
            return {
                asyncTriggers: asyncTriggers.join ? asyncTriggers.join(',') : JSON.stringify(asyncTriggers),
                postbackTriggers: postbackTriggers.join ? postbackTriggers.join(',') : JSON.stringify(postbackTriggers),
                panels: panels.join ? panels.join(',') : JSON.stringify(panels),
                isInAsyncPostBack: prm.get_isInAsyncPostBack(),
                clientID_GridObligaciones: document.getElementById('c_GridObligaciones') ? 'FOUND' : 'NOT FOUND',
            };
        })()""")
        print(f"ScriptManager info: {sm_info}")

        # === TEST 2: Manually set form fields and submit (full postback) ===
        print("\n=== TEST 2: Full postback via form.submit() ===")
        ok2 = await login_and_load_obligations(page)
        print(f"Obligations loaded (test 2): {ok2}")
        
        if ok2:
            all_navs = []
            page.on("framenavigated", lambda f: all_navs.append(f.url) if f == page.main_frame else None)
            
            # Directly set form fields and submit like a full postback
            await page.evaluate("""(function(){
                var f = document.querySelector('form');
                // Set EVENTTARGET to GridObligaciones UniqueID 
                f['__EVENTTARGET'].value = 'ctl00$c$GridObligaciones';
                f['__EVENTARGUMENT'].value = 'Select$1';
                // DISABLE the ScriptManager interception by directly calling HTMLFormElement.prototype.submit
                HTMLFormElement.prototype.submit.call(f);
            })()""")
            
            try:
                await page.wait_for_url(lambda u: "FrmDetalleClie" in u or "frmLogin" in u.lower(), timeout=15000)
                print(f"Navigation to: {page.url}")
                await page.wait_for_load_state("load", timeout=15000)
                print(f"After load: {page.url}")
                await page.screenshot(path=str(EVDIR / "test2_full_postback.png"))
                print(f"Screenshot saved: test2_full_postback.png")
            except Exception as e:
                print(f"Timeout/error: {e}")
                print(f"Current URL: {page.url}")
                print(f"All navs: {all_navs}")
                await page.screenshot(path=str(EVDIR / "test2_full_postback_timeout.png"))
            
            print(f"Dialogs: {dialogs}")

        await browser.close()

asyncio.run(main())
