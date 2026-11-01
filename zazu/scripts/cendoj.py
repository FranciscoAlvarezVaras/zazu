#!/home/server/.hermes/venvs/cendoj/bin/python
"""Busca jurisprudencia en CENDOJ (CGPJ) con Chrome real. Uso puntual de Fran:
cendoj.py "texto" [--n 5] [--db TS|AN|TSJ|AP]  -> título, ECLI, resumen. Sin descargas masivas (aviso legal CGPJ)."""
import argparse, re, sys
from playwright.sync_api import sync_playwright
ap = argparse.ArgumentParser(); ap.add_argument("q"); ap.add_argument("--n", type=int, default=5)
ap.add_argument("--db", default="")
a = ap.parse_args(); n = min(a.n, 10)
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page()
    pg.goto("https://www.poderjudicial.es/search/indexAN.jsp", wait_until="networkidle", timeout=60000)
    pg.locator("#modalAvisoLegal button").first.click(); pg.wait_for_timeout(800)
    if a.db:
        pg.evaluate("v=>document.getElementById('frmBusquedajurisprudencia_databasematch').value=v", a.db)
    pg.fill("#frmBusquedajurisprudencia_TEXT", a.q)
    pg.click("#srcjur_search"); pg.wait_for_timeout(8000)
    t = pg.inner_text("body"); b.close()
m = re.search(r"([\d\.]+) resultados", t); print("Resultados:", m.group(1) if m else "?")
L = [l.strip() for l in t.split("\n")]
items = []
for k, l in enumerate(L):
    if "ROJ:" in l and k + 2 < len(L) and L[k+1].startswith("ECLI:"):
        items.append((l, L[k+1], L[k+2].replace("Resumen Automático:", "").strip()))
for h, e, r in items[:n]:
    print(f"- {h}\n  {e.split('  N')[0]}\n  {r[:300]}")
if not items: print("No he podido leer resultados (¿cambió la web?)")
