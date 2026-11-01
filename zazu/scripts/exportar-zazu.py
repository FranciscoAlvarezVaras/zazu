#!/usr/bin/env python3
"""Vuelca a el Cerebro (Obsidian) todo lo de Zazu, en notas legibles. Solo lee ~/.hermes; solo escribe en DESTINO y en el bloque «Zazu hoy» del Diario.
- Conversaciones (WhatsApp, HolaZazu, terminal): una nota por conversación, en 50 Zazu/Conversaciones/AAAA-MM/ (tipo conversacion).
- Informes de rutinas (cron): el resultado final de cada ejecución, en 50 Zazu/Informes/AAAA-MM/ (tipo informe-zazu).
  Si Hermes no entregó la respuesta de la rutina por ser un silencio ([SILENT], NO_REPLY…: la misma regla que
  gateway.response_filters.is_autonomous_silence_response), no hay nota.
- rutinas.md: las rutinas activas, con horario y último resultado (tipo zazu).
- memoria.md: copia de lo que Zazu sabe de Fran (USER.md) y de sus lecciones (MEMORY.md) (tipo zazu).
- 20 Diario/AAAA-MM-DD.md: bloque «## Zazu hoy» (entre <!-- zazu-hoy:inicio --> y <!-- zazu-hoy:fin -->) con enlaces
  a lo de ese día. Solo los últimos 14 días; solo se reemplaza el bloque (el resto de la nota es de Fran y de guardar-propuestas.py).
  Si las marcas están rotas (un inicio sin fin, marcas repetidas), no toca la nota y lo avisa por pantalla.
- Si una conversación se borra en Hermes (o se oculta), se borra su copia y su línea de «Zazu hoy».
Lo lanza zazu-exportar.timer cada 15 min; solo reescribe las notas que han cambiado. Sin IA.
Privacidad (privacidad.py): se tachan claves, PIN, códigos, tarjetas, cuentas, documentos, tokens y teléfonos, también en
títulos y en memoria.md. De los mensajes de Fran no se copian los datos de correo/agenda/WhatsApp que mete el sistema, la
descripción automática de las imágenes, el mensaje citado al responder (también la transcripción de una nota de voz
citada), el contenido de los documentos de texto y de los adjuntos «@file:» ni el contexto de otros canales;
tampoco los resúmenes de compactación. Si Zazu lee las notificaciones del móvil en una conversación (movil.py marca cada
línea con «[notificación del móvil]», también si una rutina la filtra con grep), lo que dice desde ahí hasta el final no
se copia; tampoco cuando lo leído vuelve por otra conversación (contexto de otro canal, session_search) o por el prompt
de una rutina. El contexto de otro canal Hermes lo guarda en messages.api_content (lo que se manda al modelo): se mira
también ahí, solo para detectarlo; api_content nunca se copia.
Si cambian los filtros (privacidad.py), los valores de ~/.hermes/.env o este script, se rehacen todas las notas solas."""
import hashlib, json, re, sqlite3, sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import privacidad   # los filtros de privacidad viven solo ahí
from privacidad import DE_OTRA, HABLA_DE_NOTIFICACIONES, LEE_NOTIFICACIONES, sin_datos_ajenos, tachar

HOME = Path("/home/server")
BD = HOME / ".hermes/state.db"
# (prefijo de la clave en ESTADO, base de datos): el chat de Fran en la app va por el perfil «tecnico» desde 2026-10-11
BDS = (("", BD), ("tecnico:", HOME / ".hermes/profiles/tecnico/state.db"))
SALIDAS = HOME / ".hermes/cron/output"   # informes de las rutinas SIN IA («Tu día», «Tu semana»…): no crean conversación
TRABAJOS = HOME / ".hermes/cron/jobs.json"
DESTINO = HOME / "Cerebro/50 Zazu"
DIARIO = HOME / "Cerebro/20 Diario"
ESTADO = HOME / ".local/state/exportar-zazu.json"
VERSION = 4   # súbela si cambia el formato: se rehacen todas las notas
# Huella de los filtros: privacidad.py, este script y los valores del .env. Si cambia algo (p. ej. Fran guarda en .env una
# clave que pegó en el chat), cambia la firma de todas las conversaciones y se rehacen con lo nuevo tachado. Solo se guarda
# este resumen (12 cifras hex de un SHA-256), nunca los valores.
HUELLA = hashlib.sha256(b"\0".join([Path(privacidad.__file__).read_bytes(), Path(__file__).read_bytes(),
                                    *(v.encode() for v in privacidad.LARGOS + privacidad.CORTOS)])).hexdigest()[:12]
DIAS_DIARIO = 14
CANAL = {"whatsapp": "WhatsApp", "hub": "HolaZazu", "api_server": "HolaZazu", "cli": "Terminal", "tui": "Terminal", "oneshot": "Terminal", "cron": "Rutina"}
OCULTO = {"hidden", "internal_notification", "session_meta", "model_switch", "steer", "process_complete", "failed_turn"}
ZAZU = "50 Zazu/Zazu"   # la nota central de la carpeta (destino de «Volver a Zazu»)
AVISO_MOVIL = "[aquí Zazu leyó las notificaciones del móvil: lo que dijo desde entonces en esta conversación no se copia al Cerebro]"
COMPACTACION = re.compile(r"\s*\[(?:CONTEXT COMPACTION|PRIOR CONTEXT)")   # resumen que Hermes hace al compactar: es un duplicado


def _regla_silencio():
    """Cuándo Hermes NO entrega la respuesta de una rutina: gateway.response_filters.is_autonomous_silence_response (la
    misma que usa el scheduler). Se carga del propio Hermes para que las dos reglas no se separen; si no se puede, una
    copia exacta: [SILENT], SILENT, NO_REPLY o NO REPLY (y sus formas en chino) como respuesta entera o como su primera o
    última línea (sin contar mayúsculas ni signos sueltos alrededor), o una respuesta que empieza por «[SILENT]»."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "hermes_response_filters", HOME / ".hermes/hermes-agent/gateway/response_filters.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m.is_autonomous_silence_response
    except Exception:
        import unicodedata
        marcas = {"[SILENT]", "SILENT", "NO_REPLY", "NO REPLY", "[静默]", "静默", "[沉默]", "沉默"}
        signo = lambda c: c not in "[]" and unicodedata.category(c).startswith("P")

        def exacta(s):
            s = s.strip()
            if not 0 < len(s) <= 64:
                return False
            a, b = 0, len(s)
            while a < b and signo(s[a]):
                a += 1
            while b > a and signo(s[b - 1]):
                b -= 1
            return any(" ".join(f.upper().split()) in marcas for f in (s, s[a:b].strip()))

        def silencio(r):
            s = r.strip() if isinstance(r, str) else ""
            if not s:
                return False
            lineas = [l for l in s.splitlines() if l.strip()]
            return s.upper().startswith(tuple(sorted(m for m in marcas if m.startswith("[")))) \
                or any(exacta(c) for c in (s, lineas[0], lineas[-1]))
        return silencio


SILENCIO = _regla_silencio()


def nombre_archivo(s, n=70):
    s = re.sub(r'[\\/:*?"<>|#^\[\]\x00-\x1f]', " ", s or "sin título")
    return re.sub(r"\s+", " ", s).strip()[:n].rstrip(" .") or "sin título"


def hora(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M") if ts else ""


def texto(content):
    """El contenido puede ser texto o una lista de bloques (multimodal)."""
    if not content:
        return ""
    try:
        bloques = json.loads(content) if content.lstrip().startswith("[") else None
    except ValueError:
        bloques = None
    if isinstance(bloques, list):
        partes = []
        for b in bloques:
            if isinstance(b, dict) and b.get("type") == "text":
                partes.append(b.get("text", ""))
            elif isinstance(b, dict):
                partes.append(f"[{b.get('type', 'adjunto')}]")
        return "\n".join(partes)
    return content


def escribir(ruta, contenido):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists() and ruta.read_text(encoding="utf-8") == contenido:
        return False
    tmp = ruta.with_name(f".{ruta.name}.tmp")
    tmp.write_text(contenido, encoding="utf-8")
    tmp.replace(ruta)
    return True


def borrar(e):
    """Borra la copia de una conversación (solo si está dentro de DESTINO). Devuelve los días en que salía en el Diario."""
    ruta = Path(e.get("ruta", ""))
    if ruta.suffix == ".md" and ruta.is_relative_to(DESTINO):
        ruta.unlink(missing_ok=True)
    return set(e.get("dias", {}))


def columnas(db):
    return {c[1] for c in db.execute("PRAGMA table_info(messages)")}


def lee(rol, contenido, llamadas):
    """¿Esta fila lee las notificaciones del móvil? (la llamada a la herramienta, su salida, o el prompt de una rutina
    cuyo script las mete dentro)."""
    return bool(llamadas and LEE_NOTIFICACIONES.search(llamadas)
                or rol in ("tool", "user") and contenido and LEE_NOTIFICACIONES.search(contenido))


def plano(s):
    return re.sub(r"\s+", " ", s or "").strip()


def lecturas(db):
    """Las conversaciones en las que Zazu leyó las notificaciones y el principio de cada cosa que dijo después (lo que no
    se copia), para reconocerlo si vuelve por otra conversación: el contexto de otro canal o un resultado de session_search."""
    api = "api_content" in columnas(db)   # (api_content: solo para detectar; nunca se copia)
    con = {sid for sid, rol, c, ll, a in db.execute(
        f"SELECT session_id, role, content, tool_calls, {'api_content' if api else 'NULL'} FROM messages "
        "WHERE content LIKE '%otifica%' OR tool_calls LIKE '%otifica%'" + (" OR api_content LIKE '%otifica%'" if api else ""))
        if lee(rol, c, ll) or lee(rol, a, None)}
    dichos = set()
    for sid in con:
        leido = False
        for rol, c, ll, a in db.execute(f"SELECT role, content, tool_calls, {'api_content' if api else 'NULL'} FROM messages "
                                        "WHERE session_id=? ORDER BY id", (sid,)):
            if leido and rol == "assistant" and len(plano(texto(c))) >= 30:
                dichos.add(plano(texto(c))[:600])   # fran-hub guarda los 500 primeros caracteres de cada respuesta
            leido = leido or lee(rol, c, ll) or lee(rol, a, None)
    return con, dichos


def de_otra(contenido, con, dichos):
    """¿Trae este texto (contexto de otro canal, session_search) lo que Zazu contó de las notificaciones en otra conversación?"""
    m = DE_OTRA.search(contenido or "")
    if not m:
        return False
    parte = contenido[m.start():] if m.group(0).startswith("Contexto") else contenido   # del mensaje de Fran, solo el bloque
    junto = plano(parte)
    # fran-hub recorta el bloque por delante (body[-2000:]): de la entrada más antigua puede quedar solo el final. Se mira
    # también si el final de cada línea («… | Hermes: <respuesta>», sin el «…» del recorte a 500) sale en algo que Zazu dijo.
    colas = {c[-40:] for l in parte.splitlines() if len(c := plano(l.split("| Hermes: ")[-1]).rstrip("…").strip()) >= 25}
    return bool(HABLA_DE_NOTIFICACIONES.search(parte) or any(s in parte for s in con) or any(d[:40] in junto for d in dichos)
                or any(c in d for c in colas for d in dichos))


def mensajes(db, sid, rutina, otras=(set(), set())):
    """Las líneas de la nota: (ts, texto), y (frase, ajeno): la primera frase útil de Fran y, si a uno de sus primeros
    mensajes se le quitó algo que mete el sistema (de ahí pudo sacar Hermes el título), cómo llamarlo si Fran no escribió nada."""
    hay = columnas(db)
    resumen = "_compressed_summary" if "_compressed_summary" in hay else "0"
    api = "api_content" if "api_content" in hay else "NULL"   # lo que se mandó al modelo (con el contexto de otro canal): solo para detectar
    filas = db.execute(f"SELECT role, content, timestamp, display_kind, tool_calls, {resumen}, {api} FROM messages "
                       "WHERE session_id=? ORDER BY id", (sid,)).fetchall()
    lineas, vistos, de_fran, ajeno, ultima = [], set(), [], "", ""
    movil = avisado = False   # Zazu ha leído las notificaciones del móvil en esta conversación (o le han llegado de otra)
    for rol, contenido, ts, tipo, llamadas, compactado, api_c in filas:
        t = texto(contenido)
        lectura = lee(rol, contenido, llamadas) or lee(rol, api_c, None) or bool(
            rol in ("tool", "user") and (de_otra(t, *otras) or api_c and de_otra(texto(api_c), *otras))   # lo que Zazu contó de las notificaciones en otra conversación
            or llamadas and "session_search" in llamadas and HABLA_DE_NOTIFICACIONES.search(llamadas))   # o lo busca
        visible = (rol in ("user", "assistant") and tipo not in OCULTO and not compactado
                   and not COMPACTACION.match(t) and (rol, ts, contenido) not in vistos)   # (las compactaciones duplican filas)
        vistos.add((rol, ts, contenido))
        if visible:
            cruda = t
            if rol == "user":
                limpio = sin_datos_ajenos(t)
                if limpio != t and len(de_fran) < 3 and not ajeno:   # Hermes titula con alguno de los 3 primeros mensajes
                    ajeno = next(iter(re.findall(r"\[([^\]\n:]+)", limpio)), "") or "sin título"
                t = limpio
            t = tachar(t).strip()
            t = re.sub(r"\[\[(?:audio_as_voice|as_document|as_image)\]\]\s*", "", t).strip()   # etiquetas internas de Hermes, no son enlaces
            if rol == "user":
                de_fran.append(t)
            if t and rol == "assistant":
                ultima = cruda   # tal cual la dio el modelo: es lo que mira Hermes para no entregarla
            if t and rol == "assistant" and movil:
                t, avisado = ("" if avisado else AVISO_MOVIL), True   # un solo aviso, y nada más de Zazu hasta el final
            if t and not (rutina and rol == "user"):   # en una rutina, el «mensaje de Fran» es el prompt técnico: no aporta
                lineas.append((ts, f"**{'Fran' if rol == 'user' else 'Zazu'}** · {hora(ts)}\n{t}\n"))
        movil = movil or lectura   # lo que diga Zazu a partir de aquí no se copia
    frase = next((l.strip() for m in de_fran[:3] for l in m.splitlines() if l.strip() and not l.lstrip().startswith("[")), "")
    if rutina and SILENCIO(ultima):
        lineas = []   # Hermes no la entregó (no tenía nada que contar): sin nota, y si había copia, se borra
    return (lineas[-1:] if rutina else lineas), (frase, ajeno[:1].upper() + ajeno[1:])   # de una rutina interesa el informe final


def conversaciones(bds, estado):
    """Devuelve (notas escritas, notas borradas, días del Diario que hay que revisar por las borradas)."""
    hechas, vivas = 0, set()
    for prefijo, db in bds:
        h, v = _conversaciones(db, prefijo, estado)
        hechas, vivas = hechas + h, vivas | v
    h, v = informes_script(estado)
    hechas, vivas = hechas + h, vivas | v
    revisar = set()
    muertas = [sid for sid in estado if sid not in vivas]   # borradas u ocultadas en Hermes, o ya sin nada que copiar
    for sid in muertas:
        revisar |= borrar(estado.pop(sid))
    return hechas, len(muertas), revisar


def _conversaciones(db, prefijo, estado):
    hechas, vivas = 0, set()
    otras = lecturas(db)
    filas = db.execute("SELECT id, source, title, started_at, last_activity_at, message_count, tool_names FROM sessions "
                       "WHERE coalesce(hidden,0)=0 ORDER BY started_at").fetchall()
    for sid_bd, fuente, titulo, inicio, ultima, num, herramientas in filas:
        sid = prefijo + sid_bd
        firma = f"{num}|{ultima}|{VERSION}|{HUELLA}"
        previo = estado.get(sid, {})
        if previo.get("firma") == firma and "dias" in previo and Path(previo["ruta"]).exists():
            vivas.add(sid)
            continue
        dia = datetime.fromtimestamp(inicio)
        rutina = fuente == "cron"
        lineas, (frase, ajeno) = mensajes(db, sid_bd, rutina, otras)
        if not lineas:
            continue   # sin nada que copiar: si había copia, se borra abajo
        vivas.add(sid)
        titulo = tachar(titulo or "")
        if not rutina and ajeno or titulo.startswith("[") and frase:   # (el de una rutina lo pone Hermes: su nombre y la fecha)
            # Hermes saca el título de los primeros mensajes, con lo que el sistema mete dentro (datos, mensaje citado,
            # documento, imagen…): mejor lo que pidió Fran; si no escribió nada, lo que mandó («Documento de texto»).
            titulo = frase or ajeno
        carpeta = DESTINO / ("Informes" if rutina else "Conversaciones") / dia.strftime("%Y-%m")
        ocupadas = {v["ruta"]: k for k, v in estado.items() if k != sid}   # dos conversaciones en el mismo minuto y con el mismo título
        base, n = f"{dia:%Y-%m-%d %H.%M} · {nombre_archivo(titulo)}", 2
        ruta = carpeta / f"{base}.md"
        while str(ruta) in ocupadas:
            ruta, n = carpeta / f"{base} ({n}).md", n + 1
        viejo = previo.get("ruta")
        if viejo and viejo != str(ruta):
            borrar(previo)   # cambió el título: se renombra la nota
        tipo_nota = "informe-zazu" if rutina else "conversacion"
        canal = CANAL.get(fuente, fuente)
        cuerpo = (f"---\ntipo: {tipo_nota}\ncanal: {canal}\n"
                  f"fecha: {dia:%Y-%m-%d}\nhora: \"{dia:%H:%M}\"\nmensajes: {len(lineas)}\nsesion: \"{sid}\"\ntags: [zazu, {tipo_nota}]\n---\n"
                  f"Volver a [[{ZAZU}|Zazu]] · Copia automática de la conversación (no se edita aquí).\n\n"
                  f"# {nombre_archivo(titulo, 120)}\n_{canal} · {dia:%Y-%m-%d %H:%M}"
                  + (f" · herramientas: {', '.join(json.loads(herramientas))}" if herramientas and herramientas.startswith("[") and json.loads(herramientas) else "")
                  + "_\n\n" + "\n".join(l for _, l in lineas))
        if escribir(ruta, cuerpo):
            hechas += 1
        dias = {}   # día → hora del primer mensaje copiado ese día (una conversación de WhatsApp puede durar varios días)
        for ts, _ in lineas:
            if ts:
                dias.setdefault(f"{datetime.fromtimestamp(ts):%Y-%m-%d}", hora(ts))
        estado[sid] = {"firma": firma, "ruta": str(ruta), "canal": canal, "titulo": nombre_archivo(titulo, 120),
                       "enlace": str(ruta.relative_to(DESTINO.parent).with_suffix("")), "dias": dias}
    return hechas, vivas


def informes_script(estado):
    """Cada informe de una rutina SIN IA de los últimos 60 días → 50 Zazu/Informes, igual que los de las rutinas con IA."""
    hechas, vivas = 0, set()
    try:
        trabajos = [j for j in json.loads(TRABAJOS.read_text()).get("jobs", []) if j.get("no_agent") and re.fullmatch(r"[0-9a-f]{6,32}", j.get("id", ""))]
    except (OSError, ValueError):
        return 0, vivas
    desde = f"{datetime.now() - timedelta(days=60):%Y-%m-%d}"
    for j in trabajos:
        for f in sorted((SALIDAS / j["id"]).glob("????-??-??_??-??-??.md")):
            if f.name[:10] < desde:
                continue
            t = f.read_text(encoding="utf-8", errors="replace")
            if not re.search(r"^\*\*Mode:\*\*\s*no_agent", t, re.M):
                continue
            m = re.search(r"^---\s*$(.*)", t, re.S | re.M)
            cuerpo = tachar((m.group(1) if m else "").strip())
            if not cuerpo or "[SILENT]" in cuerpo:
                continue
            sid = f"script:{j['id']}:{f.stem}"
            vivas.add(sid)
            dia = datetime.strptime(f.stem, "%Y-%m-%d_%H-%M-%S")
            titulo = nombre_archivo(tachar(j.get("name") or "Rutina"), 120)
            ruta = DESTINO / "Informes" / dia.strftime("%Y-%m") / f"{dia:%Y-%m-%d %H.%M} · {nombre_archivo(titulo)}.md"
            previo = estado.get(sid, {})
            firma = f"{f.stat().st_size}|{VERSION}|{HUELLA}"
            if previo.get("firma") == firma and Path(previo.get("ruta", "")).exists():
                continue
            nota = (f"---\ntipo: informe-zazu\ncanal: Rutina\nfecha: {dia:%Y-%m-%d}\nhora: \"{dia:%H:%M}\"\ntags: [zazu, informe-zazu]\n---\n"
                    f"Volver a [[{ZAZU}|Zazu]] · Copia automática del informe (no se edita aquí).\n\n# {titulo}\n_Rutina sin IA · {dia:%Y-%m-%d %H:%M}_\n\n{cuerpo}\n")
            if escribir(ruta, nota):
                hechas += 1
            estado[sid] = {"firma": firma, "ruta": str(ruta), "canal": "Rutina", "titulo": titulo,
                           "enlace": str(ruta.relative_to(DESTINO.parent).with_suffix("")), "dias": {f"{dia:%Y-%m-%d}": f"{dia:%H:%M}"}}
    return hechas, vivas


INICIO_HOY, FIN_HOY = "<!-- zazu-hoy:inicio -->", "<!-- zazu-hoy:fin -->"
BLOQUE_HOY = re.compile(re.escape(INICIO_HOY) + r"(?:(?!" + re.escape(INICIO_HOY) + r").)*?" + re.escape(FIN_HOY), re.S)
QUITAR_HOY = re.compile(r"\n*" + BLOQUE_HOY.pattern + r"\n*", re.S)


def diario(estado, revisar=()):
    """En la nota de cada día con actividad (últimos 14 días, y los días de las conversaciones borradas), reemplaza solo
    el bloque «Zazu hoy»; si ese día ya no queda nada, quita el bloque. Si la nota no existe, la crea.
    Solo toca una nota con una pareja completa de marcas, o sin ninguna; si no, avisa y la deja como está."""
    desde = f"{datetime.now() - timedelta(days=DIAS_DIARIO - 1):%Y-%m-%d}"
    por_dia = {}
    for e in estado.values():
        for dia, hh in e.get("dias", {}).items():
            if dia >= desde or dia in revisar:
                por_dia.setdefault(dia, []).append((hh, e["canal"], e["enlace"], e["titulo"]))
    con_bloque = {p.stem for p in DIARIO.glob("????-??-??.md")
                  if (p.stem >= desde or p.stem in revisar) and INICIO_HOY in p.read_text(encoding="utf-8")}
    hechas = 0
    for dia in sorted(set(por_dia) | con_bloque):
        cosas = por_dia.get(dia, [])
        nota = DIARIO / f"{dia}.md"
        if not cosas and not nota.exists():
            continue
        previo = (nota.read_text(encoding="utf-8") if nota.exists()
                  else f"---\ntipo: diario\nfecha: {dia}\ntags: [diario]\n---\nVolver al [[Inicio]]\n\n## Mis notas\n")
        ni, nf = previo.count(INICIO_HOY), previo.count(FIN_HOY)
        if (ni, nf) == (0, 0):
            if not cosas:
                continue
            nuevo = previo.rstrip("\n") + "\n\n" + bloque_hoy(cosas) + "\n"
        elif (ni, nf) == (1, 1) and BLOQUE_HOY.search(previo):
            nuevo = (BLOQUE_HOY.sub(lambda m: bloque_hoy(cosas), previo, count=1) if cosas
                     else QUITAR_HOY.sub(lambda m: "\n\n" if m.end() < len(previo) else "\n", previo, count=1))
        else:
            print(f"AVISO: «{nota.relative_to(DIARIO.parent)}» tiene las marcas de «Zazu hoy» rotas ({ni} de inicio y {nf} de fin): "
                  f"no la toco. Deja una sola pareja {INICIO_HOY} … {FIN_HOY}, o borra las dos, y se rehará sola.")
            continue
        if escribir(nota, nuevo):
            hechas += 1
    return hechas


def bloque_hoy(cosas):
    return (f"{INICIO_HOY}\n## Zazu hoy\n_Lo apunta Zazu solo (cada 15 min): lo que hizo por ti este día. "
            f"No escribas dentro de este bloque; el resto de la nota es tuyo._\n"
            + "\n".join(f"- {hh} · {canal} · [[{enlace}|{titulo}]]" for hh, canal, enlace, titulo in sorted(cosas))
            + f"\n\n{FIN_HOY}")


def rutinas():
    try:
        jobs = json.loads((HOME / ".hermes/cron/jobs.json").read_text()).get("jobs", [])
    except (OSError, ValueError):
        return False
    filas = []
    for j in jobs:
        ok = {"ok": "✅", "error": "🔴"}.get(j.get("last_status"), "·")
        prox = j.get("next_run_at") or j.get("next_run") or ""
        filas.append(tachar(f"| {ok} | {j.get('name')} | `{j.get('schedule_display') or j.get('schedule')}` | {'sí' if j.get('enabled') else 'no'} | {str(prox)[:16]} |"))
    cuerpo = (f"---\ntipo: zazu\ntags: [zazu]\n---\nVolver a [[{ZAZU}|Zazu]] · Se reescribe sola cada 15 min desde `~/Hermes/cron/jobs.json`.\n\n"
              f"# Rutinas de Zazu\nPara crear, cambiar o pausar una, pídeselo a Zazu («crea una rutina que…», «pausa el vigía de empleo»). Sus informes están en [[{ZAZU}#Informes|Informes]].\n\n"
              "| | Rutina | Cuándo | Activa | Próxima |\n|---|---|---|---|---|\n" + "\n".join(filas) + "\n")
    return escribir(DESTINO / "rutinas.md", cuerpo)


def memoria():
    partes = []
    for nombre, titulo in (("USER.md", "Lo que Zazu sabe de ti"), ("MEMORY.md", "Lecciones y contexto de Zazu")):
        try:
            t = (HOME / ".hermes/memories" / nombre).read_text()
        except OSError:
            continue
        t = re.sub(r"(?m)^#", "##", t.replace("§", "").strip())   # baja un nivel los títulos
        partes.append(f"# {titulo}\n_Origen: `~/Hermes/memories/{nombre}`_\n\n{tachar(t)}\n")
    cuerpo = (f"---\ntipo: zazu\ntags: [zazu]\n---\nVolver a [[{ZAZU}|Zazu]] · **Copia automática** (cada 15 min). Para cambiar algo, díselo a Zazu "
              "(«recuerda que…», «olvida que…»); si lo editas aquí, se pisa.\n\n" + "\n".join(partes))
    return escribir(DESTINO / "memoria.md", cuerpo)


def main():
    try:
        estado = json.loads(ESTADO.read_text())
    except (OSError, ValueError):
        estado = {}
    bds = [(prefijo, sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, timeout=30)) for prefijo, ruta in BDS if ruta.exists()]
    n, b, revisar = conversaciones(bds, estado)
    r = rutinas()
    m = memoria()
    d = diario(estado, revisar)
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(estado))
    print(f"Zazu → Cerebro: {n} notas de conversación/informe actualizadas · {b} borradas · rutinas {'actualizadas' if r else 'igual'} · "
          f"memoria {'actualizada' if m else 'igual'} · {d} días del Diario con «Zazu hoy» actualizado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
