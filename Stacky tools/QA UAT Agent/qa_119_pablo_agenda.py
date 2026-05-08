"""
qa_119_pablo_agenda.py — Login PABLO, inspect FrmAgenda rows, click first, check ADO-119 fields.
"""
import asyncio, os, sys, pathlib, json, datetime

BASE = os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")
USER = "PABLO"; PASS = "PABLO"
EVDIR = pathlib.Path("evidence/119"); EVDIR.mkdir(parents=True, exist_ok=True)
sys.stdout.reconfigure(encoding='utf-8')

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx  = await browser.new_context()
        page = await ctx.new_page()

        # Login
        await page.goto(f"{BASE}FrmLogin.aspx", wait_until="load")
        await page.fill("#c_abfUsuario", USER)
        await page.fill("#c_abfContrasena", PASS)
        await page.locator("#c_btnOk").click(no_wait_after=True)
        try: await page.wait_for_url(lambda u: "FrmLogin" not in u, timeout=25000)
        except: pass
        await page.wait_for_load_state("load", timeout=20000)
        print(f"[1] URL: {page.url}")

        await page.goto(f"{BASE}FrmAgenda.aspx", wait_until="load")
        await page.wait_for_load_state("networkidle", timeout=15000)
        await page.screenshot(path=str(EVDIR / "pablo_agenda.png"))

        # Find ALL table rows
        all_rows = page.locator("table tbody tr")
        total = await all_rows.count()
        print(f"[2] Total tbody rows on FrmAgenda: {total}")

        target = None
        for i in range(min(total, 10)):
            row = all_rows.nth(i)
            vis = await row.is_visible()
            text = (await row.text_content() or "").strip()[:80]
            onclick = await row.get_attribute("onclick") or ""
            print(f"  row[{i}] vis={vis} onclick={onclick[:60]} text={text[:60]}")
            if vis and (onclick or text) and not target:
                # Try clicking this row
                print(f"  → Clicking row[{i}]")
                async with ctx.expect_page(timeout=5000) as popup_info:
                    await row.click(no_wait_after=True)
                try:
                    popup = await popup_info.value
                    await popup.wait_for_load_state("load", timeout=15000)
                    print(f"    Popup: {popup.url}")
                    if "FrmDetalleClie" in popup.url:
                        target = popup
                        break
                except Exception:
                    await page.wait_for_load_state("load", timeout=5000)
                    print(f"    Same page: {page.url}")
                    if "FrmDetalleClie" in page.url:
                        target = page
                        break

        if not target:
            print("[3] No navigation via rows — trying onclick extraction")
            for i in range(min(total, 10)):
                row = all_rows.nth(i)
                onclick = await row.get_attribute("onclick") or ""
                if "FrmDetalleClie" in onclick or "DetalleClie" in onclick:
                    print(f"  Found onclick with FrmDetalleClie: {onclick[:200]}")
                    # Navigate directly
                    import re
                    m = re.search(r"location[^'\"]*['\"]([^'\"]+FrmDetalleClie[^'\"]*)['\"]", onclick)
                    if m:
                        url = BASE.rstrip("/") + "/" + m.group(1).lstrip("/")
                        print(f"  Nav to: {url}")
                        await page.goto(url, wait_until="load")
                        await page.wait_for_load_state("load", timeout=15000)
                        if "FrmDetalleClie" in page.url:
                            target = page
                            break

        if not target:
            print("[4] Listing page source for any FrmDetalleClie links...")
            content = await page.content()
            import re
            links = re.findall(r"FrmDetalleClie[^\"'<> ]{0,100}", content)
            for lnk in links[:5]:
                print(f"  Link: {lnk}")
            await page.screenshot(path=str(EVDIR / "pablo_agenda_debug.png"), full_page=True)
            print("  Screenshot saved: pablo_agenda_debug.png")
            await browser.close()
            return

        # Field check
        print(f"\n[FIELDS] On {target.url}")
        await target.screenshot(path=str(EVDIR / "ca_05_08_09.png"))
        results = {}
        for fname in ["abfCorredorPrincipal", "abfRiesgoCliente"]:
            for sel in [f"#c_{fname}", f"*[id*='{fname}']"]:
                try:
                    n = await target.locator(sel).count()
                    if n > 0:
                        el = target.locator(sel).first
                        vis = await el.is_visible()
                        ro  = await el.get_attribute("readonly") or await el.get_attribute("disabled")
                        try: val = await el.input_value()
                        except: val = (await el.text_content() or "").strip()
                        results[fname] = {"found": True, "visible": vis, "value": val.strip(), "readonly": ro is not None}
                        print(f"  {fname}: vis={vis} val='{val.strip()}' ro={ro is not None}")
                        break
                except: pass
            if fname not in results:
                results[fname] = {"found": False}
                print(f"  {fname}: NOT FOUND")

        # Labels
        rel = []
        for i in range(await target.locator("label").count()):
            try:
                t = await target.locator("label").nth(i).text_content()
                if t and any(w in t.lower() for w in ["corredor", "riesgo"]):
                    rel.append(t.strip())
            except: pass
        print(f"  Labels: {rel}")

        # Verdicts
        ca = {}
        corredor = results.get("abfCorredorPrincipal", {})
        riesgo   = results.get("abfRiesgoCliente",   {})
        for caId, fd, nm in [("CA-05", corredor,"abfCorredorPrincipal"),("CA-08",riesgo,"abfRiesgoCliente")]:
            if fd.get("found") and fd.get("visible"):
                ca[caId] = f"PASS — visible, val='{fd['value']}'"
            elif fd.get("found"):
                ca[caId] = f"FAIL — en DOM pero NO visible"
            else:
                ca[caId] = f"FAIL — NO en DOM"
        ca["CA-09"] = ("PASS — readonly" if corredor.get("readonly") and riesgo.get("readonly") and corredor.get("found") and riesgo.get("found") else "BLOCKED/FAIL")
        for x in ["CA-01","CA-02","CA-03","CA-04","CA-06","CA-07","CA-11","CA-12"]:
            ca[x] = "BLOCKED — requiere datos post-batch"

        print("\n" + "="*50)
        for c in ["CA-01","CA-02","CA-03","CA-04","CA-05","CA-06","CA-07","CA-08","CA-09","CA-11","CA-12"]:
            v = ca[c]; icon = "✅" if v.startswith("PASS") else ("❌" if v.startswith("FAIL") else "⏸")
            print(f"  {icon} {c}: {v}")

        (EVDIR / "qa_119_results.json").write_text(
            json.dumps({"ticket":"ADO-119","ts":datetime.datetime.now().isoformat(),"results":ca,"fields":results,"labels":rel}, ensure_ascii=False, indent=2), encoding="utf-8")
        await browser.close()

asyncio.run(main())
