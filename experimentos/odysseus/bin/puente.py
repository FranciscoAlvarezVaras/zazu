#!/usr/bin/python3
"""Puente mínimo TCP <-> socket Unix para dejar a Odysseus SIN red y aun así hablar con servicios concretos.
Uso:  puente.py 'ESCUCHA>DESTINO' ['ESCUCHA>DESTINO' ...]      con  tcp:PUERTO  (siempre 127.0.0.1)  o  unix:RUTA
Ejemplos (los usa arrancar.sh / dentro.sh):
  unix:run/p11434.sock>tcp:11434   en el PC: lo que llegue al socket se reenvía a Ollama (127.0.0.1:11434)
  tcp:11434>unix:run/p11434.sock   en la jaula: Odysseus cree que Ollama está en su 127.0.0.1:11434
  tcp:7011>unix:run/in7011.sock    en el PC: tu navegador entra por 127.0.0.1:7011
  unix:run/in7011.sock>tcp:7011    en la jaula: llega a Odysseus
Solo pasan los puertos que se listan; todo lo demás (internet, WhatsApp, Hermes, la app…) queda sin camino."""
import asyncio, os, sys

async def pipe(r, w):
    try:
        while (d := await r.read(65536)):
            w.write(d); await w.drain()
    except Exception:
        pass
    finally:
        try: w.close()
        except Exception: pass

def destino(spec):
    tipo, _, valor = spec.partition(":")
    if tipo == "tcp":
        return lambda: asyncio.open_connection("127.0.0.1", int(valor))
    return lambda: asyncio.open_unix_connection(valor)

async def main():
    servidores = []
    for par in sys.argv[1:]:
        esc, _, dst = par.partition(">")
        abrir = destino(dst)
        async def h(cr, cw, abrir=abrir):
            try:
                ur, uw = await abrir()
            except Exception:
                cw.close(); return
            await asyncio.gather(pipe(cr, uw), pipe(ur, cw))
        tipo, _, valor = esc.partition(":")
        if tipo == "tcp":
            servidores.append(await asyncio.start_server(h, host="127.0.0.1", port=int(valor)))
        else:
            if os.path.exists(valor): os.unlink(valor)
            servidores.append(await asyncio.start_unix_server(h, path=valor))
            os.chmod(valor, 0o600)
    await asyncio.gather(*(s.serve_forever() for s in servidores))

asyncio.run(main())
