"""SPAM Tracker : application Windows (fenetre + zone de notification).

Lance dans un seul processus :
    - le tracker (tracker.watch) dans un thread
    - un serveur web local sur 127.0.0.1:8765 (jamais accessible depuis le reseau)
    - une fenetre native pywebview qui affiche ui.html
    - une icone dans la zone de notification (Ouvrir / Quitter)

Options :
    --tray   demarre reduit dans la zone de notification (utilise au demarrage de Windows)
    --quit   demande a l'instance en cours de se fermer

Securite : lecture seule sur les fichiers du jeu, aucune connexion sortante,
ni ticket ni AccountId dans l'interface ou les logs.
"""

import ctypes
import http.client
import json
import os
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import tracker

APP_NAME = "SPAM-Tracker"
HOST, PORT = "127.0.0.1", 8765
URL = f"http://{HOST}:{PORT}/"
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
# En-tete obligatoire sur les POST : une page web externe ne peut pas l'envoyer sans
# requete CORS prealable, que ce serveur ne valide jamais.
CSRF_HEADER = "X-SPAM-Tracker"

APP_VERSION = "1.0.0"
DATA_DIR = tracker.BASE_DIR                                  # a cote de l'exe
RES_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))  # ui.html embarque
LOG_PATH = DATA_DIR / "tracker.log"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


# ---------------------------------------------------------------- "Preparer les cartes"

class PrepareJob:
    """Extraction du catalogue et des miniatures en arriere-plan, une seule a la fois."""

    def __init__(self):
        self.lock = threading.Lock()
        self.state = {"state": "idle", "progress": 0.0, "message": "", "error": None, "report": None}

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def _set(self, **kw):
        with self.lock:
            self.state.update(kw)

    def start(self):
        with self.lock:
            if self.state["state"] == "running":
                return False, "La preparation des cartes est deja en cours."
        gd, _ = tracker.game_dir()
        if not gd:
            return False, "Jeu SPAM introuvable : indique son dossier dans les Reglages."
        self._set(state="running", progress=0.0, message="Demarrage...", error=None, report=None)
        threading.Thread(target=self._run, args=(gd,), name="prepare-cards", daemon=True).start()
        return True, None

    def _run(self, gd):
        import gc
        try:
            import extract_catalog
            print(f"Preparation des cartes depuis {gd}")
            report = extract_catalog.extract(
                gd, DATA_DIR, images=True,
                progress=lambda f, m: self._set(progress=round(min(max(f, 0), 1), 3), message=m),
                log=print, game_version=tracker.current_game_version())
            tracker.load_catalog()
            msg = f"{report.get('cards', 0)} cartes et {report.get('images', 0)} illustrations pretes."
            if not report.get("images_ok", True):
                msg += " Certaines illustrations n'ont pas pu etre extraites (cartes de remplacement affichees)."
            self._set(state="done", progress=1.0, message=msg, report={k: report.get(k) for k in
                      ("cards", "images", "images_ok", "partial", "warnings")})
            print(msg)
        except Exception as e:
            known = type(e).__name__ == "ExtractError"
            text = str(e) if known else (f"Erreur inattendue ({type(e).__name__}). "
                                         "Les details sont dans tracker.log, dans le dossier des donnees.")
            if not known:
                import traceback
                traceback.print_exc()
            print(f"[!] Preparation des cartes : {text}")
            self._set(state="error", error=text, message="Echec")
        finally:
            gc.collect()


PREP = PrepareJob()


# ---------------------------------------------------------------- journal

class LogWriter:
    """Remplace stdout/stderr : chaque ligne part dans tracker.log avec l'heure."""

    def __init__(self, path):
        self.f = open(path, "a", encoding="utf-8", buffering=1)
        self.lock = threading.Lock()
        self.buf = ""

    def write(self, s):
        with self.lock:
            self.buf += s
            while "\n" in self.buf:
                line, self.buf = self.buf.split("\n", 1)
                if line.strip():
                    self.f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {line}\n")
        return len(s)

    def flush(self):
        self.f.flush()


def setup_log():
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 1_000_000:
            LOG_PATH.replace(LOG_PATH.with_suffix(".old.log"))
        sys.stdout = sys.stderr = LogWriter(LOG_PATH)
    except OSError:
        pass  # sans journal, l'app fonctionne quand meme


def message_box(text, error=False):
    flags = 0x10 if error else 0x30  # MB_ICONERROR / MB_ICONWARNING
    ctypes.windll.user32.MessageBoxW(None, text, "SPAM Tracker", flags)


# ---------------------------------------------------------------- instance unique

_mutex = None


def acquire_single_instance():
    """Mutex Windows nomme : False si une autre instance tourne deja."""
    global _mutex
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _mutex = kernel32.CreateMutexW(None, False, f"Local\\{APP_NAME}-single-instance")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def ask_running_instance(path):
    """Envoie un ordre (/api/show ou /api/quit) a l'instance deja lancee, en local."""
    try:
        conn = http.client.HTTPConnection(HOST, PORT, timeout=3)
        conn.request("POST", path, body="{}", headers={CSRF_HEADER: "1", "Content-Type": "application/json"})
        return conn.getresponse().status == 200
    except OSError:
        return False


# ---------------------------------------------------------------- demarrage avec Windows

def autostart_available():
    return bool(getattr(sys, "frozen", False))


def autostart_command():
    return f'"{Path(sys.executable).resolve()}" --tray'


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, APP_NAME)[0] == autostart_command()
    except OSError:
        return False


def set_autostart(enabled):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------- WebView2

def webview2_installed():
    """WebView2 Runtime present ? (cles de registre documentees par Microsoft)."""
    import winreg
    guid = r"{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    places = [
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"),
        (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{guid}"),
    ]
    for root, key in places:
        try:
            with winreg.OpenKey(root, key) as k:
                version = winreg.QueryValueEx(k, "pv")[0]
                if version and version != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


# ---------------------------------------------------------------- barre de titre sombre (DWM)

# COLORREF = 0x00BBGGRR. Fond de l'interface #0a0c11, texte #ece6d6 (variables --ink et --paper de ui.html)
CAPTION_COLOR = 0x00110C0A
CAPTION_TEXT_COLOR = 0x00D6E6EC
DWMWA_USE_IMMERSIVE_DARK_MODE = 20         # Windows 10 20H1+ et Windows 11
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19     # Windows 10 1809 a 1909
DWMWA_CAPTION_COLOR = 35                   # Windows 11 uniquement
DWMWA_TEXT_COLOR = 36                      # Windows 11 uniquement


def find_own_window(title="SPAM Tracker"):
    """Handle de la fenetre principale de CE processus (sans passer par WinForms)."""
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    pid, found = os.getpid(), []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value == title:
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def style_title_bar():
    """Barre de titre native mais sombre. Toute erreur est ignoree : la barre normale reste."""
    try:
        from ctypes import wintypes
        hwnd = find_own_window()
        if not hwnd:
            return
        dwm = ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long  # HRESULT, 0 = succes

        def set_attr(attr, value):
            v = wintypes.DWORD(value)
            return dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v)) == 0

        if not set_attr(DWMWA_USE_IMMERSIVE_DARK_MODE, 1):
            set_attr(DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, 1)
        # Windows 10 refuse ces deux attributs (E_INVALIDARG) : sans consequence, le mode sombre suffit
        set_attr(DWMWA_CAPTION_COLOR, CAPTION_COLOR)
        set_attr(DWMWA_TEXT_COLOR, CAPTION_TEXT_COLOR)
        # redessine le cadre tout de suite (sinon Windows 10 attend le prochain changement de focus)
        SWP = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # NOSIZE NOMOVE NOZORDER NOACTIVATE FRAMECHANGED
        ctypes.windll.user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP)
    except Exception:
        pass


# ---------------------------------------------------------------- application

class App:
    def __init__(self):
        self.stop = threading.Event()
        self.window = None
        self.icon = None
        self.server = None
        self.mode = "webview"
        self.quitting = False

    def show(self):
        if self.window is not None:
            self.window.show()
            self.window.restore()
            style_title_bar()  # reappliquee a chaque reaffichage depuis la zone de notification
        else:
            webbrowser.open(URL)

    def quit(self):
        if self.quitting:
            return
        self.quitting = True
        print("Fermeture demandee.")
        self.stop.set()
        if self.icon is not None:
            self.icon.stop()
        if self.server is not None:
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        if self.window is not None:
            self.window.destroy()


APP = App()


class Handler(BaseHTTPRequestHandler):
    server_version = "SPAMTracker"

    def log_message(self, *args):
        pass  # pas de journal HTTP

    def _send(self, status, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        # les miniatures changent rarement : petit cache ; le reste jamais
        self.send_header("Cache-Control", "max-age=600" if ctype == "image/webp" else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; style-src 'unsafe-inline'; "
                         "script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        # protege contre le "DNS rebinding" : seul l'hote local est accepte
        if self.headers.get("Host") not in ALLOWED_HOSTS:
            self._send(403, {"error": "hote refuse"})
            return False
        return True

    def do_GET(self):
        if not self._host_ok():
            return
        if self.path in ("/", "/index.html"):
            self._send(200, (RES_DIR / "ui.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/dashboard":
            try:
                data = tracker.dashboard_data()
            except Exception as e:  # la base peut etre verrouillee un instant
                print(f"[!] Erreur dashboard : {type(e).__name__}: {e}")
                self._send(500, {"error": "donnees indisponibles"})
                return
            data["app"] = {"mode": APP.mode, "data_dir": str(DATA_DIR), "version": APP_VERSION,
                           "autostart": autostart_enabled(), "autostart_available": autostart_available(),
                           "can_browse": APP.window is not None}
            data["prepare"] = PREP.snapshot()
            self._send(200, data)
        elif self.path == "/api/prepare-status":
            self._send(200, PREP.snapshot())
        elif self.path.startswith("/cards/"):
            # /cards/<uuid>.webp uniquement : le nom est valide avant de toucher au disque
            name = self.path[len("/cards/"):]
            uid = name[:-5] if name.endswith(".webp") else ""
            path = tracker.CARDS_DIR / f"{uid}.webp"
            if not tracker.UUID_RE.match(uid) or not path.is_file():
                self._send(404, {"error": "image absente"})
                return
            self._send(200, path.read_bytes(), "image/webp")
        else:
            self._send(404, {"error": "introuvable"})

    def do_POST(self):
        if not self._host_ok():
            return
        if self.headers.get(CSRF_HEADER) != "1":
            self._send(403, {"error": "requete refusee"})
            return
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 10_000)
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            body = {}

        if self.path == "/api/show":
            self._send(200, {"ok": True})
            APP.show()
        elif self.path == "/api/quit":
            self._send(200, {"ok": True})
            threading.Thread(target=APP.quit, daemon=True).start()
        elif self.path == "/api/open-folder":
            os.startfile(DATA_DIR)
            self._send(200, {"ok": True})
        elif self.path == "/api/autostart":
            if not autostart_available():
                self._send(400, {"error": "Disponible uniquement depuis SPAM-Tracker.exe"})
                return
            try:
                set_autostart(bool(body.get("enabled")))
            except OSError as e:
                self._send(500, {"error": f"Registre inaccessible : {e.strerror}"})
                return
            print(f"Demarrage avec Windows : {'active' if autostart_enabled() else 'desactive'}")
            self._send(200, {"ok": True, "autostart": autostart_enabled()})
        elif self.path == "/api/prepare-cards":
            ok, message = PREP.start()
            self._send(200 if ok else 409, {"ok": ok, "error": None if ok else message})
        elif self.path == "/api/game-dir":
            # dossier du jeu saisi par l'utilisateur (ou vide pour revenir a la detection automatique)
            raw = str(body.get("path") or "").strip()
            if not raw:
                tracker.save_settings(game_dir=None)
                self._send(200, {"ok": True, "game": tracker.game_status()})
                return
            gd = tracker.normalize_game_dir(raw)
            if not gd:
                self._send(400, {"error": "Ce dossier ne contient pas SPAM (SPAM_Data\\resources.assets introuvable). "
                                          "Choisis le dossier ou se trouve SPAM.exe."})
                return
            tracker.save_settings(game_dir=str(gd))
            self._send(200, {"ok": True, "game": tracker.game_status()})
        elif self.path == "/api/choose-game-dir":
            # selecteur de dossier natif (fenetre WebView2 uniquement)
            if APP.window is None:
                self._send(400, {"error": "Selecteur indisponible en mode navigateur : colle le chemin du dossier."})
                return
            try:
                import webview
                picked = APP.window.create_file_dialog(webview.FileDialog.FOLDER)
            except Exception as e:
                self._send(500, {"error": f"Selecteur indisponible ({type(e).__name__})"})
                return
            self._send(200, {"path": picked[0] if picked else None})
        else:
            self._send(404, {"error": "introuvable"})


def tray_image(size=64):
    """Icone generee avec Pillow (pas de fichier image a fournir)."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, size - 3, size - 3), radius=size // 5, fill=(22, 25, 32, 255),
                        outline=(124, 156, 255, 255), width=max(2, size // 20))
    try:
        font = ImageFont.truetype("segoeuib.ttf", int(size * 0.62))
    except OSError:
        font = ImageFont.load_default()
    d.text((size / 2, size / 2), "S", font=font, fill=(124, 156, 255, 255), anchor="mm")
    return img


def start_tray():
    import pystray
    menu = pystray.Menu(
        pystray.MenuItem("Ouvrir", lambda: APP.show(), default=True),
        pystray.MenuItem("Quitter", lambda: APP.quit()),
    )
    APP.icon = pystray.Icon(APP_NAME, tray_image(), "SPAM Tracker", menu)
    APP.icon.run_detached()


def main():
    args = set(sys.argv[1:])
    setup_log()

    if not acquire_single_instance():
        # deja lance : on montre la fenetre existante (ou on la ferme) puis on sort
        ask_running_instance("/api/quit" if "--quit" in args else "/api/show")
        return
    if "--quit" in args:
        return

    print(f"Demarrage de SPAM Tracker, donnees dans {DATA_DIR}")
    tracker.load_catalog()

    try:
        APP.server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as e:
        message_box(f"Impossible d'ouvrir le port local {PORT} ({e.strerror}).\n"
                    "Une autre application l'utilise peut-etre.", error=True)
        return
    APP.server.daemon_threads = True
    threading.Thread(target=APP.server.serve_forever, name="http", daemon=True).start()
    threading.Thread(target=tracker.watch, args=(APP.stop,), name="tracker", daemon=True).start()
    start_tray()

    # SPAM_FORCE_BROWSER=1 simule l'absence de WebView2 (pour tester le mode navigateur)
    use_webview = webview2_installed() and not os.environ.get("SPAM_FORCE_BROWSER")
    if use_webview:
        try:
            import webview
            # SPAM_START_TAB=decks|opponents|settings ouvre directement un onglet (captures d'ecran)
            start = URL + (f"#{os.environ['SPAM_START_TAB']}" if os.environ.get("SPAM_START_TAB") else "")
            APP.window = webview.create_window("SPAM Tracker", start, width=1180, height=780,
                                               min_size=(820, 560), background_color="#0e1015",
                                               hidden="--tray" in args)

            def on_closing():
                if APP.quitting:
                    return True
                # fermer = reduire dans la zone de notification ; hide() hors du thread de l'evenement
                threading.Timer(0.05, APP.window.hide).start()
                return False

            APP.window.events.closing += on_closing
            APP.window.events.shown += style_title_bar   # premiere apparition de la fenetre
            # profil WebView2 dans le dossier de l'app (et non un dossier temporaire au nom aleatoire)
            webview.start(gui="edgechromium", private_mode=True, storage_path=str(DATA_DIR / "webview-cache"))
        except Exception as e:
            print(f"[!] Fenetre WebView2 impossible ({type(e).__name__}: {e}), passage au navigateur.")
            APP.window = None
            use_webview = False

    if not use_webview and not APP.quitting:
        APP.mode = "browser"
        print("WebView2 absent : tableau de bord ouvert dans le navigateur.")
        message_box("Microsoft Edge WebView2 Runtime est absent ou ne fonctionne pas.\n\n"
                    "Le tableau de bord va s'ouvrir dans ton navigateur. Le tracker continue "
                    "de tourner dans la zone de notification (clic droit, Quitter pour l'arreter).\n\n"
                    "Pour avoir la fenetre native, installe WebView2 Runtime depuis le site de Microsoft.")
        if "--tray" not in args:
            webbrowser.open(URL)
        APP.stop.wait()

    APP.quit()
    print("SPAM Tracker arrete.")


if __name__ == "__main__":
    main()
