"""
diag_frmbusqueda.py — Inspecciona el HTML de GridPersonas post-búsqueda en FrmBusqueda.aspx
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

        # FrmBusqueda
        await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
        await page.fill("#c_abfApellido1", "MONTEZUMA")
        await page.locator("#c_btnOk").click(no_wait_after=True)
        await page.wait_for_load_state("load", timeout=20000)
        try:
            await page.locator("#c_GridPersonas tbody tr").first.wait_for(timeout=12000)
        except:
            pass

        # Dump GridPersonas HTML
        try:
            html = await page.locator("#c_GridPersonas").inner_html()
            print(f"\n=== GridPersonas HTML ===\n{html[:3000]}\n===")
        except Exception as e:
            print(f"GridPersonas not found: {e}")
            # Try alternatives
            for sel in ["table.grid", ".grid", "[id*='GridPersonas']", "table"]:
                cnt = await page.locator(sel).count()
                if cnt > 0:
                    html = await page.locator(sel).first.inner_html()
                    print(f"\n=== {sel} HTML ===\n{html[:2000]}\n===")
                    break

        # Count rows
        cnt = await page.locator("#c_GridPersonas tbody tr").count()
        print(f"\nRows found: {cnt}")

        # Inspect each row
        rows = page.locator("#c_GridPersonas tbody tr")
        for i in range(min(cnt, 3)):
            row = rows.nth(i)
            text = (await row.text_content() or "").strip()
            onclick = await row.get_attribute("onclick") or ""
            # Find clickable elements inside row
            links = row.locator("a, input[type=button], button, input[type=submit]")
            link_cnt = await links.count()
            print(f"\nRow[{i}]:")
            print(f"  text: {text[:80]}")
            print(f"  onclick: {onclick[:100]}")
            print(f"  clickable elements: {link_cnt}")
            for j in range(link_cnt):
                lnk = links.nth(j)
                lnk_html = await lnk.evaluate("el => el.outerHTML")
                print(f"  link[{j}]: {lnk_html[:200]}")

        await page.screenshot(path=str(EVDIR / "diag_busqueda.png"))
        print(f"\nScreenshot: {EVDIR}/diag_busqueda.png")
        await browser.close()

asyncio.run(main())
