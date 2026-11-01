#!/usr/bin/env python3
"""Ajuste fino POR API (OpenAI) del modelo que decide si una oferta de empleo te interesa.
Usa los mismos ejemplos que entrenar_ofertas.py (lo que guardas y descartas: tabla feedback del almacén) y sube SOLO
la oferta (pública) y tu sí/no; nunca conversaciones ni WhatsApp.

  afinar_ofertas.py                 → prepara datos/afinar-ofertas.jsonl en local y dice cuántos ejemplos hay (no sube nada)
  afinar_ofertas.py --subir         → sube el fichero a OpenAI y lanza el entrenamiento (necesita --minimo ejemplos; cuesta dinero)
  afinar_ofertas.py --estado        → cómo va el último entrenamiento y, si acabó, el nombre de tu modelo
La clave sale de OPENAI_API_KEY en ~/.hermes/.env (nunca se imprime). El último trabajo se apunta en ~/.config/zazu-afinar.json."""
import argparse
import json
import os
import sqlite3
import sys
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import almacen

AQUI = Path(__file__).resolve().parent
SALIDA = AQUI / "datos/afinar-ofertas.jsonl"
ESTADO = Path.home() / ".config/zazu-afinar.json"
OFERTAS = Path.home() / ".local/state/empleo-buscador/ofertas.db"
API = "https://api.openai.com/v1"
SISTEMA = ("Eres el filtro de ofertas de empleo de Fran. Lee la oferta y contesta solo «si» si le interesaría "
           "o «no» si no. Fran busca puestos junior de datos/desarrollo y marketing digital, en España o en remoto.")


def clave():
    for linea in (Path.home() / ".hermes/.env").read_text().splitlines():
        if linea.startswith("OPENAI_API_KEY="):
            return linea.split("=", 1)[1].strip().strip('"\'')
    sys.exit("No hay OPENAI_API_KEY en ~/.hermes/.env")


def ejemplos():
    """→ lista de (texto de la oferta, 'si'|'no'); la última opinión tuya sobre cada oferta manda."""
    with almacen.conectar() as c:
        ops = {}
        for r in c.execute("SELECT objeto, valor FROM feedback WHERE objeto LIKE 'oferta:%' ORDER BY id"):
            ops[r["objeto"].split(":", 1)[1]] = "si" if r["valor"] == "si" else "no"
    if not ops:
        return []
    o = sqlite3.connect(f"file:{OFERTAS}?mode=ro", uri=True)
    o.row_factory = sqlite3.Row
    out = []
    for id_, v in ops.items():
        r = o.execute("SELECT titulo, empresa, lugar, pais, remoto, pista, descripcion FROM ofertas WHERE id = ?", (id_,)).fetchone()
        if r:
            texto = f"{r['titulo']} · {r['empresa']} · {r['lugar'] or ''} {r['pais'] or ''} · remoto={r['remoto']} · pista={r['pista']}\n{(r['descripcion'] or '')[:1500]}"
            out.append((texto, v))
    return out


def pedir(metodo, ruta, datos=None, tipo="application/json"):
    req = urllib.request.Request(API + ruta, data=datos, method=metodo, headers={"Authorization": f"Bearer {clave()}", "Content-Type": tipo})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subir", action="store_true")
    ap.add_argument("--estado", action="store_true")
    ap.add_argument("--minimo", type=int, default=50)
    ap.add_argument("--modelo", default=os.environ.get("AFINAR_MODELO", "gpt-4.1-mini-2025-04-14"))
    a = ap.parse_args()

    if a.estado:
        e = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
        if not e.get("trabajo"):
            return print("Aún no se ha lanzado ningún entrenamiento.")
        j = pedir("GET", f"/fine_tuning/jobs/{e['trabajo']}")
        e.update(estado=j.get("status"), modelo_final=j.get("fine_tuned_model"))
        ESTADO.write_text(json.dumps(e, indent=1))
        return print(f"Entrenamiento {j.get('status')}." + (f" Tu modelo: {j['fine_tuned_model']}" if j.get("fine_tuned_model") else ""))

    ej = ejemplos()
    si = sum(v == "si" for _, v in ej)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with SALIDA.open("w") as f:
        for texto, v in ej:
            f.write(json.dumps({"messages": [{"role": "system", "content": SISTEMA}, {"role": "user", "content": texto}, {"role": "assistant", "content": v}]}, ensure_ascii=False) + "\n")
    print(f"{len(ej)} ejemplos ({si} sí, {len(ej) - si} no) en {SALIDA}")
    if not a.subir:
        return
    if len(ej) < a.minimo or not si or si == len(ej):
        sys.exit(f"Pocos ejemplos para entrenar (hacen falta {a.minimo}, con síes y noes). Marca más ofertas en Empleo.")
    limite = "----zazu" + uuid.uuid4().hex
    cuerpo = (f"--{limite}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nfine-tune\r\n"
              f"--{limite}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{SALIDA.name}\"\r\nContent-Type: application/jsonl\r\n\r\n").encode() \
        + SALIDA.read_bytes() + f"\r\n--{limite}--\r\n".encode()
    fich = pedir("POST", "/files", cuerpo, f"multipart/form-data; boundary={limite}")
    j = pedir("POST", "/fine_tuning/jobs", json.dumps({"training_file": fich["id"], "model": a.modelo, "suffix": "zazu-ofertas"}).encode())
    ESTADO.write_text(json.dumps({"trabajo": j["id"], "modelo_base": a.modelo, "ejemplos": len(ej)}, indent=1))
    os.chmod(ESTADO, 0o600)
    print(f"Entrenamiento lanzado ({j['id']}, base {a.modelo}). Mira cómo va con: afinar_ofertas.py --estado")


if __name__ == "__main__":
    main()
