#!/usr/bin/env python3
"""Pide una tarea de ARCHIVOS al móvil de Fran a través de la app de Zazu y (si se quiere) espera la respuesta. Solo biblioteca estándar.

CADA ORDEN LA APRUEBA FRAN EN EL MÓVIL ANTES DE QUE SE HAGA: la app enseña «Zazu quiere: … — <motivo>» con Permitir / Rechazar
y no hace nada sin que él pulse Permitir. Sin respuesta en 15 minutos, la petición caduca. No hay comandos libres ni shell:
solo los tipos de abajo, y las rutas siempre bajo /storage/emulated/0 (vale escribir /sdcard/… o Download/…).
Nunca se borra nada para siempre: «papelera» mueve a /sdcard/.ZazuPapelera/<fecha>/.

    movil-app.py listar /sdcard/Download --motivo "Fran pidió ver Descargas" --esperar 300
    movil-app.py tamanos /sdcard --motivo "Fran quiere saber qué ocupa más" --esperar 300
    movil-app.py duplicados /sdcard/DCIM --motivo "buscar fotos repetidas" --esperar 600
    movil-app.py info /sdcard/Download/factura.pdf --motivo "comprobar que está"
    movil-app.py crear_carpeta /sdcard/Documents/Facturas --motivo "ordenar facturas"
    movil-app.py mover /sdcard/Download/factura.pdf /sdcard/Documents/Facturas --motivo "ordenar facturas"
    movil-app.py papelera /sdcard/Download/viejo.apk --motivo "limpiar Descargas"
    movil-app.py subir /sdcard/Documents/Facturas --motivo "copia en casa"     (llega a ~/Documentos/Movil-S25/Documents/Facturas)
    movil-app.py estado <id>                                                  (cómo va una petición)

Salida: la petición en JSON. Código: 0 hecha (o creada sin --esperar), 1 rechazada/error/caducada o petición no válida
(uso, ruta no permitida, cola ilegible: sin JSON y con el motivo en stderr), 2 aún pendiente al acabar la espera.
"""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pagina-web"))
import movil  # noqa: E402   la misma cola que lee el Hub (~/.local/state/zazu-movil/peticiones.jsonl)

POSICIONALES = {"listar": ["ruta"], "tamanos": ["ruta"], "tamaños": ["ruta"], "duplicados": ["ruta"], "info": ["ruta"], "crear_carpeta": ["ruta"],
                "papelera": ["ruta"], "subir": ["ruta"], "mover": ["origen", "destino"]}


class _Argumentos(argparse.ArgumentParser):
    def error(self, message):
        # argparse sale con 2 en cualquier error, y el 2 es «aún pendiente»: Zazu podía creer que una petición rechazada
        # por la ruta estaba esperando en el móvil. Los errores salen con 1.
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(1)


def main():
    ap = _Argumentos(description="Pide una tarea de archivos al móvil de Fran (él la aprueba en el móvil).")
    ap.add_argument("tipo", choices=sorted(POSICIONALES) + ["estado"])
    ap.add_argument("valores", nargs="*")
    ap.add_argument("--motivo", help="por qué lo pide Zazu (Fran lo ve en el móvil)")
    ap.add_argument("--esperar", type=int, default=0, help="segundos a esperar la respuesta (máx. 900)")
    a = ap.parse_args()
    if a.tipo == "estado":
        p = movil.peticion(a.valores[0] if a.valores else "")
        print(json.dumps(p, ensure_ascii=False, indent=1))
        return 0 if p else 1
    nombres = POSICIONALES[a.tipo]
    if len(a.valores) != len(nombres):
        ap.error(f"{a.tipo} necesita: {' '.join(nombres)}")
    try:
        p = movil.crear_peticion(a.tipo, dict(zip(nombres, a.valores)), a.motivo)
    except ValueError as e:
        ap.error(str(e))
    fin = time.time() + min(max(a.esperar, 0), 900)
    while time.time() < fin and p["estado"] in ("pendiente", "aprobada"):
        time.sleep(3)
        p = movil.peticion(p["id"]) or p
    print(json.dumps(p, ensure_ascii=False, indent=1))
    if p["estado"] in ("pendiente", "aprobada"):
        return 2 if a.esperar else 0
    return 0 if p["estado"] == "hecha" else 1


if __name__ == "__main__":
    sys.exit(main())
