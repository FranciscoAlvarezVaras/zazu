#!/usr/bin/env python3
"""Respaldo automático de los documentos de WhatsApp del móvil de Fran → ~/Documentos/WhatsApp (sin fotos ni vídeos).
Lo lanza respaldo-whatsapp.timer cada 3 h. Copia por KDE Connect (movil.py montar). Solo AÑADE: nunca borra aquí
lo que se borre en el móvil, nunca escribe en el móvil y nunca pisa un archivo que ya exista.
Estado (para la página de estado del Cerebro): ~/.local/state/respaldo-whatsapp.json"""
import json, shutil, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import movil  # noqa: E402

ORIGEN = movil.ENLACE / "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Documents"
DESTINO = Path.home() / "Documentos/WhatsApp"
CARPETAS = {"": "Recibidos", "Sent": "Enviados", "Private": "Privados"}
FUERA = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".bmp",                 # fotos
         ".mp4", ".mov", ".3gp", ".mkv", ".avi", ".webm", ".m4v"}                           # vídeos
ESTADO = Path.home() / ".local/state/respaldo-whatsapp.json"


def guardar_estado(**cambios):
    try:
        e = json.loads(ESTADO.read_text())
    except Exception:
        e = {}
    e.update(cambios)
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(e, ensure_ascii=False, indent=1))


def main():
    if not movil.conectado():
        guardar_estado(ultimo_intento=time.time(), resultado="móvil no accesible")
        print("Móvil no accesible: lo intento en la próxima pasada.")
        return 0
    if movil.montar() != 0:
        guardar_estado(ultimo_intento=time.time(), resultado="no se pudieron montar los archivos del móvil")
        return 1
    raiz = ORIGEN.resolve()
    if not str(raiz).startswith(movil.MONTAJE) or not raiz.is_dir():
        guardar_estado(ultimo_intento=time.time(), resultado="no encuentro la carpeta WhatsApp Documents")
        print(f"No encuentro la carpeta de documentos de WhatsApp en el móvil ({ORIGEN}).")
        return 1
    for resto in DESTINO.rglob(".*.copiando"):          # copias a medias de una pasada interrumpida
        resto.unlink(missing_ok=True)
    nuevos, saltados, errores = [], 0, 0
    for sub, nombre in CARPETAS.items():
        src_dir, dst_dir = raiz / sub, DESTINO / nombre
        if not src_dir.is_dir():
            continue
        for f in src_dir.iterdir():                     # WhatsApp guarda los documentos sin subcarpetas
            try:
                if f.is_symlink() or not f.is_file() or f.name.startswith(".") or f.stat().st_size == 0:
                    continue
                if f.suffix.lower() in FUERA:
                    saltados += 1
                    continue
                dst = dst_dir / f.name
                if dst.exists():
                    continue
                dst_dir.mkdir(parents=True, exist_ok=True)
                tmp = dst.with_name(f".{dst.name}.copiando")
                shutil.copy2(f, tmp)                        # copia completa a un temporal y luego se renombra
                tmp.rename(dst)
                nuevos.append(f"{nombre}/{f.name}")
            except OSError as e:
                errores += 1
                print(f"No pude copiar {f.name}: {e.strerror}")
    total = sum(1 for p in DESTINO.rglob("*") if p.is_file() and not p.name.startswith("."))
    fin = {"ultimo_intento": time.time(), "resultado": "ok" if not errores else f"{errores} errores", "total": total, "nuevos_ultima_vez": len(nuevos)}
    if not errores:
        fin["ultimo_ok"] = time.time()
    guardar_estado(**fin)
    print(f"Respaldo de WhatsApp: {len(nuevos)} nuevos · {total} en total en ~/Documentos/WhatsApp · {saltados} fotos/vídeos ignorados" + (f" · {errores} errores" if errores else ""))
    for n in nuevos[:20]:
        print(f"  + {n}")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
