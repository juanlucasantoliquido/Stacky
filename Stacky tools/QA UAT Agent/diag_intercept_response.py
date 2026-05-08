"""
diag_intercept_response.py — Intercepta el POST del postback y captura la respuesta del servidor
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
    try: await page.locator("#c_GridPersonas tbody tr").first.wait_for(timeout=10000)
    except: pass
    await page.wait_for_timeout(500)

    icon = page.locator("#c_GridPersonas tbody tr:first-child td:first-child i")
    if await icon.count() > 0:
        await icon.click()
        await page.wait_for_timeout(3000)
    
    cnt = await page.locator("#c_GridObligaciones tbody tr").count()
    print(f"GridObligaciones rows: {cnt}")
    
    # Get current page state for analysis
    state = await page.evaluate("""(function(){
        var f = document.forms[0] || document.querySelector('form');
        if (!f) return {error: 'no form'};
        var vst = f['__VIEWSTATE'] ? f['__VIEWSTATE'].value.substring(0,50) : 'N/A';
        var evt = f['__EVENTTARGET'] ? f['__EVENTTARGET'].value : '';
        var go = document.getElementById('c_GridObligaciones');
        var rows = go ? go.querySelectorAll('tbody tr').length : 0;
        // Get data-unique-id via jQuery
        var uid = go ? ($(go).data('uniqueId') || go.getAttribute('data-unique-id')) : 'N/A';
        return {viewstateStart: vst, eventtarget: evt, obligRows: rows, uid: uid};
    })()""")
    print(f"  Page state: {state}")
    return cnt > 0

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Capture all POST responses to FrmBusqueda
        captured_responses = []
        
        async def capture_response(response):
            if "FrmBusqueda" in response.url and response.request.method == "POST":
                try:
                    body = await response.text()
                    captured_responses.append({
                        "status": response.status,
                        "url": response.url,
                        "body_len": len(body),
                        "body_preview": body[:2000],  # first 2000 chars
                        "has_redirect": "pageRedirect" in body,
                        "has_error": "AsyncPostBackError" in body or "error" in body.lower()[:500],
                    })
                except Exception as ex:
                    captured_responses.append({"error": str(ex)})
        
        page.on("response", capture_response)
        
        ok = await login_and_load_obligations(page)
        
        if not ok:
            print("ERROR: No obligations loaded")
            await browser.close()
            return
        
        print(f"\nCaptured {len(captured_responses)} POST responses so far:")
        for i, r in enumerate(captured_responses):
            print(f"  [{i}] status={r.get('status')} len={r.get('body_len')} redirect={r.get('has_redirect')} error={r.get('has_error')}")
            if r.get('has_redirect'):
                # Find the redirect URL
                body = r['body_preview']
                idx = body.find('pageRedirect')
                print(f"    REDIRECT FOUND: {body[idx:idx+200]}")
        
        # Clear previous captures and try the GridObligaciones postback
        captured_responses.clear()
        
        print(f"\n--- Triggering GridObligaciones postback ---")
        uid_val = await page.evaluate("""(function(){
            var go = document.getElementById('c_GridObligaciones');
            return go ? ($(go).data('uniqueId') || go.getAttribute('data-unique-id')) : null;
        })()""")
        print(f"GridObligaciones data-unique-id (jQuery): {uid_val}")
        
        # Call __doPostBack the EXACT same way the AIS JS does
        await page.evaluate(f"window.__doPostBack('{uid_val}', 'Select$1')")
        
        # Wait for response
        await page.wait_for_timeout(10000)
        
        print(f"\nCaptured {len(captured_responses)} POST responses after __doPostBack:")
        for i, r in enumerate(captured_responses):
            print(f"  [{i}] status={r.get('status')} len={r.get('body_len')} redirect={r.get('has_redirect')} error={r.get('has_error')}")
            body = r.get('body_preview', '')
            if r.get('has_redirect'):
                idx = body.find('pageRedirect')
                print(f"    REDIRECT: {body[idx:idx+300]}")
            elif r.get('has_error'):
                print(f"    ERROR BODY: {body[:500]}")
            else:
                print(f"    BODY (first 300): {body[:300]}")
        
        print(f"\nFinal URL: {page.url}")
        
        if not captured_responses:
            print("NO POST REQUESTS CAPTURED — __doPostBack did not send a request!")
            # Maybe it was filtered, let's check ALL responses
            print("All page URLs after __doPostBack (checking via evaluate):")
            result = await page.evaluate("""(function(){
                return {
                    url: window.location.href,
                    prm_exists: typeof Sys !== 'undefined' && typeof Sys.WebForms !== 'undefined',
                    prm_request: typeof Sys !== 'undefined' && Sys.WebForms && Sys.WebForms.PageRequestManager ? 
                        Sys.WebForms.PageRequestManager.getInstance()._request : 'N/A'
                };
            })()""")
            print(f"  {result}")
        
        await browser.close()

asyncio.run(main())
