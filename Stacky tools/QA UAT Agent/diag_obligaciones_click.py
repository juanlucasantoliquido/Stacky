"""
diag_obligaciones_click.py — Explora el mecanismo de click en GridObligaciones
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

async def navigate_to_obligations(page):
    """Login + search MONTEZUMA + click GridPersonas → returns True if GridObligaciones has rows"""
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

    # Click GridPersonas icon
    icon = page.locator("#c_GridPersonas tbody tr:first-child td:first-child i")
    if await icon.count() > 0:
        await icon.click()
        await page.wait_for_timeout(3000)
    
    obl_cnt = await page.locator("#c_GridObligaciones tbody tr").count()
    print(f"GridObligaciones rows: {obl_cnt}")
    return obl_cnt > 0

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # Check full GridObligaciones HTML after loading
        print("=== INSPECT GridObligaciones HTML ===")
        page = await browser.new_page()
        ok = await navigate_to_obligations(page)
        if ok:
            full_html = await page.locator("#c_GridObligaciones").inner_html()
            print(f"Full GridObligaciones HTML:\n{full_html[:1000]}")
            
            # Check event listeners on rows
            has_jquery = await page.evaluate("typeof jQuery !== 'undefined'")
            if has_jquery:
                row_events = await page.evaluate("(function(){ var r=document.querySelector('#c_GridObligaciones tbody tr'); if(!r) return 'no row'; var e=jQuery._data(r,'events'); return e?Object.keys(e).join(','):'no events'; })()")
                print(f"OblRow jQuery events: {row_events}")

            # Check if __doPostBack exists
            has_postback = await page.evaluate("typeof __doPostBack !== 'undefined'")
            print(f"__doPostBack defined: {has_postback}")

            # Strategy A: __doPostBack with GridObligaciones$ctl02
            print("\n--- Strategy A: __doPostBack GridObligaciones$ctl02 Select ---")
            try:
                await page.evaluate("__doPostBack('c_GridObligaciones$ctl02', 'Select')")
                await page.wait_for_load_state("load", timeout=10000)
                print(f"URL: {page.url}")
                if "FrmDetalleClie" in page.url:
                    print("SUCCESS A!")
                    await browser.close()
                    return
            except Exception as e:
                print(f"Error: {e}")

        # Strategy B: Direct form submit simulation
        print("\n--- Strategy B: Form submit with __EVENTTARGET ---")
        page2 = await browser.new_page()
        ok2 = await navigate_to_obligations(page2)
        if ok2:
            # Get __VIEWSTATE and other hidden fields
            vs = await page2.evaluate("(function(){ var e=document.getElementById('__VIEWSTATE'); return e?e.value.substring(0,50):'no viewstate'; })()")
            print(f"__VIEWSTATE (first 50): {vs}")
            
            et = await page2.evaluate("(function(){ var e=document.getElementById('__EVENTTARGET'); return e?e.value:'no eventtarget'; })()")
            print(f"__EVENTTARGET: {et}")
            
            # Try setting __EVENTTARGET and submitting
            try:
                await page2.evaluate("""(function() {
                    document.getElementById('__EVENTTARGET').value = 'c_GridObligaciones';
                    document.getElementById('__EVENTARGUMENT').value = 'Select$0';
                    document.forms[0].submit();
                })()""")
                await page2.wait_for_load_state("load", timeout=10000)
                print(f"URL after form submit: {page2.url}")
                if "FrmDetalleClie" in page2.url:
                    print("SUCCESS B!")
                    await browser.close()
                    return
            except Exception as e:
                print(f"Error B: {e}")

        # Strategy C: Check rendered JS for row click
        print("\n--- Strategy C: Inspect JS source for AISGridView click ---")
        page3 = await browser.new_page()
        ok3 = await navigate_to_obligations(page3)
        if ok3:
            # Get all script content to find row click handler
            scripts = await page3.evaluate("(function(){ var scripts=document.querySelectorAll('script'); var content=''; for(var i=0;i<scripts.length;i++){var s=scripts[i].textContent; if(s.indexOf('GridObligaciones')!==-1){content+=s.substring(0,500)+'\\n---\\n';}} return content.substring(0,2000); })()")
            print(f"Scripts mentioning GridObligaciones:\n{scripts[:1000] if scripts else 'none'}")
            
            # Try double-click
            print("\nTrying double-click on GridObligaciones row...")
            obl_row = page3.locator("#c_GridObligaciones tbody tr:first-child")
            await obl_row.dblclick()
            await page3.wait_for_timeout(3000)
            print(f"URL after dblclick: {page3.url}")

        await browser.close()

asyncio.run(main())
