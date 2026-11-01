#!/usr/bin/env python3
"""App de Android 2.5 con casa falsa (tests/fakehome.sh): avisos nativos (la cola de avisos de cada móvil) y «Conectar con Google»
desde la app (billete de un solo uso → Custom Tab → permisos en espera → la app los confirma con su sesión). Nada real: Google no
se toca (el intercambio del código no se prueba) y gog es tests/fakegog.py.

    cd pagina-web && python3 -m unittest tests.test_app_nativa -v
"""
import base64, hashlib, hmac, json, os, subprocess, sys, time, unittest, urllib.error, urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_api as T   # noqa: E402  (como módulo: así sus clases no se vuelven a ejecutar aquí)

REPO = T.REPO


def galleta(fh, email):
    """Sesión firmada como la del Hub (la clave de prueba de la casa falsa)."""
    cfg = json.loads((fh / ".config/hermes-hub/auth.json").read_text())
    body = f"{int(time.time()) + 3600}.{base64.urlsafe_b64encode(email.encode()).decode().rstrip('=')}.abcdef"
    return f"{body}.{hmac.new(bytes.fromhex(cfg['session_key']), body.encode(), hashlib.sha256).hexdigest()}"


class AvisosApp(T.Base):
    """Cada push que sale (vigilante.push) queda también en la cola de los móviles con la app de quien lo recibe."""

    def setUp(self):
        (self.fh / ".config/hermes-hub/movil.json").unlink(missing_ok=True)
        (self.fh / ".local/state/zazu-movil/avisos.json").unlink(missing_ok=True)
        os.environ["HOME"] = str(self.fh)
        sys.path.insert(0, str(REPO))
        import movil   # noqa: E402
        movil.TOKENS = self.fh / ".config/hermes-hub/movil.json"            # los mismos archivos que usa el Hub de pruebas
        movil.AVISOS = self.fh / ".local/state/zazu-movil/avisos.json"
        self.movil = movil

    def token(self):
        st, d = self.post("/api/movil/token", {"nombre": "S25"})   # en pruebas, 127.0.0.1 es Fran (HUB_DEV)
        self.assertEqual(st, 200, d)
        return d["token"]

    def con_token(self, metodo, ruta, tok, cuerpo=None):
        r = urllib.request.Request(f"http://127.0.0.1:{self.hub_port}{ruta}", method=metodo, headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                                   data=json.dumps(cuerpo).encode() if cuerpo is not None else None)
        try:
            with urllib.request.urlopen(r, timeout=20) as f:
                return f.status, json.loads(f.read())
        except urllib.error.HTTPError as e:
            raw = e.read()
            e.close()
            return e.code, json.loads(raw or b"null")

    def push(self, **datos):
        r = subprocess.run([sys.executable, str(REPO / "vigilante.py"), "--push-json"], input=json.dumps(datos), capture_output=True, text=True,
                           cwd=str(REPO), env=self.entorno(0, "http://127.0.0.1:1"), timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_el_push_llega_a_la_app_y_se_confirma(self):
        tok = self.token()
        self.assertEqual(self.push(titulo="⏰ Recordatorio", cuerpo="Llamar al dentista", tag="rec-1", url="/?tab=inicio"), "1 notificaciones enviadas")
        st, d = self.con_token("GET", "/api/movil/avisos", tok)
        self.assertEqual(st, 200)
        [a] = d["avisos"]
        self.assertEqual({k: a[k] for k in ("title", "body", "url", "tag")},
                         {"title": "⏰ Recordatorio", "body": "Llamar al dentista", "url": "/?tab=inicio", "tag": "rec-1"})
        self.assertRegex(a["id"], r"^[0-9a-f]{12}$")
        self.assertEqual(a["x"] - a["t"], 86400)                                  # caduca en un día, como el web push
        self.push(titulo="⏰ Recordatorio", cuerpo="Llamar al dentista (otra vez)", tag="rec-1")
        [b] = self.con_token("GET", "/api/movil/avisos", tok)[1]["avisos"]        # mismo tag: sustituye, no se duplica
        self.assertEqual((b["body"], b["id"] != a["id"]), ("Llamar al dentista (otra vez)", True))
        self.push(titulo="Rutina", cuerpo="Informe", tag="rut-1", para="invitada@example.com")
        self.assertEqual(len(self.con_token("GET", "/api/movil/avisos", tok)[1]["avisos"]), 1)   # lo de una invitada no le llega a Fran
        self.assertEqual(self.con_token("POST", "/api/movil/avisos/confirmar", tok, {"ids": [b["id"], "otro"]}), (200, {"quitados": 1}))
        self.assertEqual(self.con_token("GET", "/api/movil/avisos", tok), (200, {"avisos": []}))
        f = self.fh / ".local/state/zazu-movil/avisos.json"
        self.assertEqual(f.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(tok, f.read_text())                                     # por móvil, con el sha256 del token

    def test_solo_con_el_token_del_movil(self):
        self.token()
        self.assertEqual(self.pedir("GET", "/api/movil/avisos")[0], 403)         # con sesión, no: la cola es de cada móvil
        self.assertEqual(self.post("/api/movil/avisos/confirmar", {"ids": []})[0], 403)
        self.assertEqual(self.con_token("GET", "/api/movil/avisos", "zm_falso")[0], 401)
        tok = self.token()
        self.assertEqual(self.con_token("POST", "/api/movil/avisos/confirmar", tok, {"ids": ["x"] * 101})[0], 400)

    def test_tope_caducidad_limpieza_y_un_movil_por_cola(self):
        m = self.movil
        tok, otro = self.token(), self.token()
        for i in range(40):
            self.assertEqual(m.encolar_aviso({"title": f"t{i}", "body": "b", "url": "/?tab=inicio", "tag": f"tag-{i}"}), 2)
        self.assertEqual([a["title"] for a in m.avisos_de(tok)], [f"t{i}" for i in range(10, 40)])   # tope: los 30 más nuevos
        m.confirmar_avisos(tok, [a["id"] for a in m.avisos_de(tok)])
        self.assertEqual((len(m.avisos_de(tok)), len(m.avisos_de(otro))), (0, 30))   # confirmar en un móvil no quita los del otro
        a = m.encolar_aviso({"title": "malo", "url": "//otra-web.example/x", "tag": "x", "aprob": "no-vale"})
        [x] = [y for y in m.avisos_de(tok) if y["tag"] == "x"]
        self.assertEqual((a, x["url"], "aprob" in x), (2, "/?tab=inicio", False))   # solo enlaces de Zazu; aprob con formato malo, fuera
        m.encolar_aviso({"title": "permiso", "url": "/?tab=chat", "tag": "aprob-1", "aprob": "0123456789ab"})
        self.assertEqual([y["aprob"] for y in m.avisos_de(tok) if y["tag"] == "aprob-1"], ["0123456789ab"])
        d = json.loads(m.AVISOS.read_text())
        for v in d.values():
            for y in v:
                y["x"] = int(time.time()) - 1
        m.AVISOS.write_text(json.dumps(d))
        self.assertEqual(m.avisos_de(tok), [])                                    # caducados
        self.assertEqual(m.encolar_aviso({"title": "n"}, para="invitada@example.com", invitadas={"invitada@example.com"}), 0)
        self.assertEqual(m.encolar_aviso({"title": "n"}, invitadas={"dev"}), 0)   # para=None solo va a móviles que no son de una invitada
        m.encolar_aviso({"title": "n", "tag": "n"})
        (self.fh / ".config/hermes-hub/movil.json").write_text(json.dumps({"tokens": {}}))   # Fran quitó los móviles
        m.encolar_aviso({"title": "m"})
        self.assertEqual(json.loads(m.AVISOS.read_text()), {})                   # su cola se va con ellos


class GoogleDesdeApp(T.Base):
    """«Conectar con Google» desde la app: billete de un solo uso atado al email de la sesión, state con a=1 y los permisos solo
    se guardan cuando la app vuelve con la sesión de ESE email. Un segundo Hub abre el puerto público (el de Cloudflare)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.entorno(T.puerto_libre(), f"http://127.0.0.1:{cls.gw_port}")
        cls.pub_port = T.puerto_libre()
        env["HUB_PUBLIC_PORT"] = str(cls.pub_port)
        cls.lanzar([sys.executable, str(REPO / "server.py")], "hub-pub.log", env)
        T.esperar_puerto(cls.pub_port)
        os.environ["HOME"] = str(cls.fh)
        sys.path.insert(0, str(REPO))
        import server   # noqa: E402
        cls.server = server
        cls.ip_n = 0

    def setUp(self):
        self.server.G_APP = self.fh / ".config/hermes-hub/google-app.json"   # el mismo archivo que usa el Hub de pruebas
        self.cliente = self.fh / ".config/hermes-hub/google-web.json"
        self.cliente.write_text(json.dumps({"web": {"client_id": "cid", "client_secret": "cs", "redirect_uris": ["https://holazazu.app/oauth/google/callback"]}}))
        (self.fh / "gog-import.log").unlink(missing_ok=True)

    def tearDown(self):
        self.cliente.unlink(missing_ok=True)

    def http(self, metodo, ruta, cabeceras=None, puerto=None, cuerpo=None):
        import http.client
        type(self).ip_n += 1
        c = http.client.HTTPConnection("127.0.0.1", puerto or self.pub_port, timeout=20)
        c.request(metodo, ruta, body=cuerpo, headers={"CF-Connecting-IP": f"198.51.100.{self.ip_n}", **(cabeceras or {})})
        r = c.getresponse()
        datos = r.read()
        c.close()
        return r.status, dict(r.getheaders()), datos

    def billete(self, **kw):
        st, d = self.post("/api/google/enlace-app", kw.pop("cuerpo", {}), **kw)
        self.assertEqual(st, 200, d)
        return d["url"]

    def importados(self):
        p = self.fh / "gog-import.log"
        return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []

    def test_billete_de_un_solo_uso_y_sin_galleta(self):
        url = self.billete(cuerpo={"email": "fran.otra@example.com"})
        q = parse_qs(urlparse(url).query)
        self.assertEqual((urlparse(url).path, q["mode"], q["email"]), ("/oauth/google/start", ["connect"], ["fran.otra@example.com"]))
        self.assertRegex(q["t"][0], r"^[A-Za-z0-9_-]{43}$")
        self.assertNotIn(q["t"][0], (self.fh / ".config/hermes-hub/google-app.json").read_text())   # en disco, solo el hash
        st, h, _ = self.http("GET", url)                                          # la Custom Tab: sin galleta de sesión
        self.assertEqual(st, 302)
        g = urlparse(h["Location"])
        self.assertEqual(g.netloc, "accounts.google.com")
        p = parse_qs(g.query)
        self.assertIn("https://www.googleapis.com/auth/gmail.modify", p["scope"][0])   # los permisos de Fran
        self.assertEqual(p["login_hint"], ["fran.otra@example.com"])
        cuerpo = p["state"][0].split(".")[0]
        d = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))
        self.assertEqual((d["m"], d["w"], d["a"], d["g"]), ("connect", "dev", 1, False))
        self.assertIn("g_st=", h.get("Set-Cookie", ""))
        for otra in (url, url.replace(q["t"][0], "A" * 43)):                      # reutilizado o inventado: vuelve a la app con el aviso
            st, h, _ = self.http("GET", otra)
            self.assertEqual((st, h["Location"]), (302, "https://holazazu.app/app/entrar?e=caducado"))
        st, h, _ = self.http("GET", "/oauth/google/start?mode=connect")
        self.assertEqual(h["Location"], "/login")                                 # sin billete ni sesión, como siempre
        # la vuelta con error de Google en una conexión de la app también vuelve a la app
        st, h, _ = self.http("GET", "/oauth/google/callback?error=access_denied&state=" + p["state"][0])
        self.assertEqual(h["Location"], "https://holazazu.app/app/entrar?e=google_no")

    def test_billete_pide_sesion_x_hub_y_cliente(self):
        r = urllib.request.Request(f"http://127.0.0.1:{self.hub_port}/api/google/enlace-app", method="POST", data=b"{}")
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(r, timeout=20)                                 # sin X-Hub (otra web): fuera
        self.assertEqual(e.exception.code, 403)
        e.exception.close()
        st, _, _ = self.http("POST", "/api/google/enlace-app", {"X-Hub": "1", "Content-Type": "application/json"}, cuerpo=b"{}")
        self.assertEqual(st, 403)                                                 # por internet y sin sesión: fuera
        self.cliente.unlink()
        self.assertEqual(self.post("/api/google/enlace-app", {})[0], 404)        # sin cliente OAuth, no hay nada que abrir

    def test_invitada_con_sus_permisos(self):
        cookie = galleta(self.fh, "invitada@example.com")
        url = self.billete(cookie=cookie)
        st, h, _ = self.http("GET", url)
        p = parse_qs(urlparse(h["Location"]).query)
        self.assertIn("https://www.googleapis.com/auth/gmail.readonly", p["scope"][0])
        self.assertNotIn("gmail.modify", p["scope"][0])                           # los de invitada, nunca los de Fran
        cuerpo = p["state"][0].split(".")[0]
        d = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))
        self.assertEqual((d["w"], d["g"], d["a"]), ("invitada@example.com", True, 1))

    def test_una_invitada_no_echa_el_billete_de_fran(self):
        url_fran = self.billete()
        cookie = galleta(self.fh, "invitada@example.com")
        for _ in range(55):   # más que el tope global de 50: solo se quedan sus 3 más nuevos
            self.billete(cookie=cookie)
        st, h, _ = self.http("GET", url_fran)
        self.assertEqual(st, 302)
        self.assertEqual(urlparse(h["Location"]).netloc, "accounts.google.com")   # el de Fran sigue valiendo
        vivos = json.loads((self.fh / ".config/hermes-hub/google-app.json").read_text())
        self.assertLessEqual(sum(1 for v in vivos.values() if v.get("w") == "invitada@example.com"), 3)

    def test_la_app_confirma_con_la_sesion_del_mismo_email(self):
        s = self.server
        scope = "openid email https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/tasks"
        # Fran (dev en pruebas): se guarda en SU gog
        g = s.g_app_nuevo("g", "dev", 120, email="fran.otra@example.com", rt="1//rt-falso", scope=scope)
        self.assertEqual(self.http("GET", f"/app/google?g={g}", puerto=self.hub_port)[1]["Location"], "/?tab=cuentas&ok=google")
        [i] = self.importados()
        self.assertEqual((i["email"], i["refresh_token"], i["services"], i["home"]), ("fran.otra@example.com", "1//rt-falso", ["calendar", "tasks"], ""))
        self.assertEqual(self.http("GET", f"/app/google?g={g}", puerto=self.hub_port)[1]["Location"], "/?tab=cuentas&e=caducado")   # una sola vez
        # el código de otra persona no se guarda en tu cuenta (y queda gastado)
        ajeno = s.g_app_nuevo("g", "invitada@example.com", 120, email="otra@example.com", rt="1//x", scope=scope)
        self.assertEqual(self.http("GET", f"/app/google?g={ajeno}", puerto=self.hub_port)[1]["Location"], "/?tab=cuentas&e=caducado")
        cookie = {"Cookie": "hub_s=" + galleta(self.fh, "invitada@example.com")}
        self.assertEqual(self.http("GET", f"/app/google?g={ajeno}", cookie)[1]["Location"], "/?e=caducado")
        self.assertEqual(len(self.importados()), 1)
        # la invitada: en SU carpeta de gog
        suyo = s.g_app_nuevo("g", "invitada@example.com", 120, email="invi.google@example.com", rt="1//inv", scope=scope)
        self.assertEqual(self.http("GET", f"/app/google?g={suyo}", cookie)[1]["Location"], "/?ok=google")
        i = self.importados()[-1]
        self.assertEqual((i["email"], i["home"].endswith("/invitadas/zitest")), ("invi.google@example.com", True))
        # caducado, un billete usado como código y sin sesión
        viejo = s.g_app_nuevo("g", "dev", -1, email="a@example.com", rt="r", scope=scope)
        billete = s.g_app_nuevo("t", "dev", 120)
        for c in (viejo, billete, "corto"):
            self.assertEqual(self.http("GET", f"/app/google?g={c}", puerto=self.hub_port)[1]["Location"], "/?tab=cuentas&e=caducado")
        self.assertEqual(self.http("GET", f"/app/google?g={s.g_app_nuevo('g', 'dev', 120, email='a@example.com', rt='r', scope=scope)}")[1]["Location"], "/login")
        self.assertEqual(len(self.importados()), 2)
        # e=<motivo>: lista cerrada
        self.assertEqual(self.http("GET", "/app/google?e=nivel", cookie)[1]["Location"], "/?e=nivel")
        self.assertEqual(self.http("GET", "/app/google?e=%3Cscript%3E", puerto=self.hub_port)[1]["Location"], "/?tab=cuentas&e=google")

    def test_en_chrome_abre_la_app_sin_canjear(self):
        g = self.server.g_app_nuevo("g", "dev", 120, email="a@example.com", rt="r", scope="openid")
        st, h, b = self.http("GET", f"/app/entrar?g={g}")
        self.assertEqual((st, h.get("Cache-Control")), (200, "no-store"))
        self.assertIn(f"intent://entrar?g={g}#Intent;scheme=zazu;package=app.holazazu.zazu;end".encode(), b)
        self.assertIn("terminar de conectar Google".encode(), b)
        self.assertIn(b"intent://entrar?e=nivel#", self.http("GET", "/app/entrar?e=nivel")[2])
        self.assertNotIn(b"intent://", self.http("GET", "/app/entrar?e=%22%3E%3Cscript%3E")[2])
        self.assertEqual(self.http("GET", f"/app/google?g={g}", puerto=self.hub_port)[1]["Location"], "/?tab=cuentas&ok=google")   # sigue sin usar


    def test_purgar_quita_los_permisos_caducados(self):
        s = self.server
        viejo = s.g_app_nuevo("g", "dev", -1, email="a@example.com", rt="1//caducado", scope="openid")
        vivo = s.g_app_nuevo("g", "dev", 120, email="b@example.com", rt="1//vivo", scope="openid")
        s.g_app_purgar()   # sin que nadie más conecte: el refresh_token caducado no se queda en disco
        texto = s.G_APP.read_text()
        self.assertNotIn("1//caducado", texto)
        self.assertIn("1//vivo", texto)
        self.assertIsNone(s.g_app_canjear(viejo, "g"))
        self.assertIsNotNone(s.g_app_canjear(vivo, "g"))


if __name__ == "__main__":
    unittest.main()
