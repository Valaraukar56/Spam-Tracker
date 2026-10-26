"""Tracker de matchs pour SPAM (Ticroco).

Usage :
    python tracker.py          surveille les matchs et les enregistre dans spam.db
    python tracker.py stats    affiche les statistiques
    python tracker.py decks    statistiques par deck et cartes adverses

Les noms de cartes viennent de catalog.json (bouton "Preparer les cartes" ou
python extract_catalog.py --images).

Securite :
    - lecture seule sur les fichiers du jeu (on lit seulement index.json)
    - ni l'AccountId ni le ticket ne sont stockes ; les replays .srpl ne sont pas copies
    - le champ Loading.ticket n'est jamais lu ni stocke
    - aucune connexion reseau

Variables d'environnement (optionnelles, surtout pour les tests) :
    SPAM_DATA_DIR     dossier des donnees du tracker (defaut : a cote de l'exe ou du script)
    SPAM_REPLAYS_DIR  dossier replays du jeu (defaut : detecte dans AppData\\LocalLow)
"""

import json
import os
import re
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


def local_low_dir():
    """Dossier AppData\\LocalLow de l'utilisateur courant, demande a Windows."""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD),
                        ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]

        # FOLDERID_LocalAppDataLow = {A520A1A4-1780-4FF6-BD18-167343C5AF16}
        fid = GUID(0xA520A1A4, 0x1780, 0x4FF6,
                   (ctypes.c_ubyte * 8)(0xBD, 0x18, 0x16, 0x73, 0x43, 0xC5, 0xAF, 0x16))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(out)) == 0:
            path = out.value
            ctypes.windll.ole32.CoTaskMemFree(out)
            return Path(path)
    except (AttributeError, OSError):
        pass
    return Path(os.environ.get("LOCALAPPDATA", "")).parent / "LocalLow"


# Dossier ou le jeu ecrit ses replays : replays\<serveur>\<accountId>\index.json.
# SPAM_REPLAYS_DIR permet de pointer vers une copie pour les tests.
REPLAYS_DIR = Path(os.environ.get("SPAM_REPLAYS_DIR") or local_low_dir() / "Ticroco" / "Spam" / "replays")

# Fichiers du tracker, a cote du script (ou a cote de l'exe, jamais dans le dossier temporaire PyInstaller)
if os.environ.get("SPAM_DATA_DIR"):
    BASE_DIR = Path(os.environ["SPAM_DATA_DIR"]).resolve()
elif getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
BASE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = BASE_DIR / "spam.db"
CATALOG_PATH = BASE_DIR / "catalog.json"
SETTINGS_PATH = BASE_DIR / "settings.json"

# Version du jeu pour laquelle le decodage du catalogue a ete verifie (AppVersion des replays)
TESTED_GAME_VERSION = "1.26"
SPAM_APP_ID = "2902720"   # AppID Steam de SPAM


# ---------------------------------------------------------------- reglages locaux (settings.json)

def load_settings():
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(**changes):
    data = load_settings() | changes
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(SETTINGS_PATH)
    return data


# ---------------------------------------------------------------- dossier d'installation du jeu

def _steam_roots():
    """Dossiers d'installation de Steam connus du registre (utilisateur et machine)."""
    roots = []
    try:
        import winreg
    except ImportError:
        return roots
    keys = [(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")]
    for root, key, value in keys:
        try:
            with winreg.OpenKey(root, key) as k:
                p = Path(winreg.QueryValueEx(k, value)[0])
                if p not in roots:
                    roots.append(p)
        except OSError:
            continue
    return roots


def _uninstall_location():
    """Dossier donne par l'entree de desinstallation "Steam App 2902720", si elle existe."""
    try:
        import winreg
    except ImportError:
        return None
    for view in (0, getattr(winreg, "KEY_WOW64_32KEY", 0), getattr(winreg, "KEY_WOW64_64KEY", 0)):
        try:
            key = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App {SPAM_APP_ID}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key, 0, winreg.KEY_READ | view) as k:
                return Path(winreg.QueryValueEx(k, "InstallLocation")[0])
        except OSError:
            continue
    return None


def is_game_dir(path):
    """Un dossier d'installation de SPAM valide contient SPAM_Data\\resources.assets."""
    try:
        return path is not None and (Path(path) / "SPAM_Data" / "resources.assets").is_file()
    except OSError:
        return False


def normalize_game_dir(path):
    """Accepte le dossier du jeu, son SPAM_Data ou le SPAM.exe ; renvoie le dossier du jeu ou None."""
    if not path:
        return None
    p = Path(str(path).strip().strip('"'))
    for candidate in (p, p.parent, p.parent.parent):
        if is_game_dir(candidate):
            return candidate
    return None


def detect_game_dir():
    """Cherche SPAM (AppID 2902720) dans toutes les bibliotheques Steam, sur tous les disques."""
    libraries = []
    for steam in _steam_roots():
        libraries.append(steam)
        try:
            vdf = (steam / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # chaque bibliotheque : "path" "X:\\..." puis la liste "apps" de ses jeux installes
        for block in re.split(r'\n\s*"\d+"\s*\n', vdf):
            m = re.search(r'"path"\s+"([^"]+)"', block)
            if not m:
                continue
            lib = Path(m.group(1).replace("\\\\", "\\"))
            if f'"{SPAM_APP_ID}"' in block:
                libraries.insert(0, lib)      # bibliotheque qui declare SPAM : en premier
            elif lib not in libraries:
                libraries.append(lib)
    for lib in libraries:
        manifest = lib / "steamapps" / f"appmanifest_{SPAM_APP_ID}.acf"
        installdir = "SPAM"
        try:
            m = re.search(r'"installdir"\s+"([^"]+)"', manifest.read_text(encoding="utf-8", errors="replace"))
            if m:
                installdir = m.group(1)
        except OSError:
            pass
        candidate = lib / "steamapps" / "common" / installdir
        if is_game_dir(candidate):
            return candidate
    loc = _uninstall_location()
    return loc if is_game_dir(loc) else None


def game_dir():
    """(dossier du jeu, origine) : choix de l'utilisateur s'il est valide, sinon detection."""
    chosen = load_settings().get("game_dir")
    if chosen and is_game_dir(chosen):
        return Path(chosen), "choisi"
    found = detect_game_dir()
    return (found, "detecte") if found else (None, "introuvable")

POLL_SECONDS = 2
# GameUid attendu, ex. "match-4306984" (on refuse tout le reste pour construire un chemin sans risque)
GAME_UID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


# ---------------------------------------------------------------- rangs et modes (donnees du jeu)
#
# Source : Assembly-CSharp.dll (Spam.Data.RankData, TcgEngine.GameMode) et resources.assets
# (7 RankData, traductions Rank.*), version 1.26 du jeu.
# - "stars" = etoiles du mode Classe. Rang = premier palier dont etoiles <= seuil, Legende au-dela.
# - Dans chaque rang il y a 15 etoiles a remplir (RankData.FilledStars) ; Legende n'a pas de suite :
#   le jeu y affiche la position au classement a la place.
# - "rank" (Loading.me/opponent) = position au classement general (tri par etoiles), PAS un palier.
RANK_INTERP_VERSION = 1
RANKS = [  # (seuil d'etoiles inclus, identifiant du jeu, nom affiche en francais)
    (0, "unranked", "Sans rang"),
    (15, "bronze", "Bronze"),
    (30, "silver", "Argent"),
    (45, "gold", "Or"),
    (60, "crystal", "Cristal"),
    (75, "celeste", "Céleste"),
    (90, "legend", "Légende"),
]
RANK_NAMES = {rid: name for _, rid, name in RANKS}
STARS_PER_TIER = 15
GAME_MODES = {0: "Normal", 10: "Classé", 15: "Debug", 20: "Tutoriel", 25: "Premières parties",
              30: "Entraînement", 40: "Amis", 50: "Duel en équipe", 60: "Tournoi", 70: "Battleground"}


def rank_from_stars(stars):
    """(identifiant, nom, etoiles remplies dans le rang 0-15) d'apres les etoiles, comme le jeu."""
    if stars is None:
        return None, None, None
    for threshold, rid, name in RANKS:
        if stars <= threshold:
            break
    else:
        threshold, rid, name = RANKS[-1]
    if rid == "legend":
        filled = STARS_PER_TIER   # dernier rang : jauge pleine, le jeu montre la position au classement
    else:
        filled = (stars - 1) % STARS_PER_TIER + 1 if stars > 0 else 0
    return rid, name, filled


def interpretation(game_mode, my_stars, opp_stars):
    """Colonnes interpretees, stockees a cote des valeurs brutes."""
    my = rank_from_stars(my_stars)
    op = rank_from_stars(opp_stars)
    return {
        "mode_name": GAME_MODES.get(game_mode, f"Mode {game_mode}") if game_mode is not None else None,
        "my_tier": my[0], "my_tier_stars": my[2],
        "opponent_tier": op[0], "opponent_tier_stars": op[2],
        "interp_version": RANK_INTERP_VERSION,
    }


INTERP_COLUMNS = {"mode_name": "TEXT", "my_tier": "TEXT", "my_tier_stars": "INTEGER",
                  "opponent_tier": "TEXT", "opponent_tier_stars": "INTEGER", "interp_version": "INTEGER"}
# colonnes brutes ajoutees apres la premiere version (vides pour les anciens matchs)
EXTRA_RAW_COLUMNS = {"app_version": "TEXT"}


def migrate(db):
    """Ajoute les colonnes d'interpretation et (re)calcule celles qui sont absentes ou anciennes.

    Les valeurs brutes du jeu (my_rank, my_stars, opponent_rank, opponent_stars, game_mode)
    ne sont jamais modifiees : my_rank / opponent_rank = position au classement.
    """
    cols = {r[1] for r in db.execute("PRAGMA table_info(matches)")}
    all_columns = INTERP_COLUMNS | EXTRA_RAW_COLUMNS
    missing = [c for c in all_columns if c not in cols]
    if missing and db.execute("SELECT COUNT(*) FROM matches").fetchone()[0]:
        backup = DB_PATH.with_name(f"spam.avant-migration.{datetime.now():%Y%m%d-%H%M%S}.db")
        try:
            db.commit()
            with sqlite3.connect(backup) as b:
                db.backup(b)          # copie coherente avant de toucher au schema
            print(f"Sauvegarde de la base avant migration : {backup.name}")
        except sqlite3.Error as e:
            print(f"[!] Sauvegarde impossible ({e}) : migration annulee")
            return
    for c in missing:
        db.execute(f"ALTER TABLE matches ADD COLUMN {c} {all_columns[c]}")
    todo = db.execute("""SELECT game_uid, game_mode, my_stars, opponent_stars FROM matches
                         WHERE interp_version IS NULL OR interp_version < ?""", (RANK_INTERP_VERSION,)).fetchall()
    for uid, mode, ms, os_ in todo:
        vals = interpretation(mode, ms, os_)
        sets = ", ".join(f"{k} = :{k}" for k in vals)
        db.execute(f"UPDATE matches SET {sets} WHERE game_uid = :uid", {**vals, "uid": uid})
    if todo:
        print(f"Interpretation des rangs mise a jour pour {len(todo)} match(s).")
    db.commit()


# ---------------------------------------------------------------- base SQLite

def open_db():
    """Ouvre (et cree si besoin) la base spam.db."""
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            game_uid        TEXT PRIMARY KEY,
            account_id      TEXT,
            start_utc       TEXT,
            end_utc         TEXT,
            duration_s      INTEGER,
            game_mode       INTEGER,
            level           TEXT,
            seat            INTEGER,
            opponent_id     TEXT,
            opponent_name   TEXT,
            opponent_is_ai  INTEGER,
            opponent_rank   INTEGER,   -- brut "rank" du jeu = position au classement (pas un palier)
            opponent_stars  INTEGER,   -- brut "stars" = etoiles du mode Classe
            my_rank         INTEGER,   -- idem pour moi
            my_stars        INTEGER,
            result          TEXT,      -- 'victoire', 'defaite' ou 'egalite'
            turns           INTEGER,
            my_deck         TEXT,      -- liste JSON de 4 UUID
            opponent_deck   TEXT,      -- liste JSON de 4 UUID
            imported_at     TEXT
        )
    """)
    db.commit()
    migrate(db)
    return db


def known_uids(db):
    return {row[0] for row in db.execute("SELECT game_uid FROM matches")}


def to_row(m):
    """Transforme une entree d'index.json en ligne SQL.

    On ne recopie que les champs utiles : Loading.ticket n'est jamais touche.
    """
    loading = m.get("Loading") or {}
    opp = loading.get("opponent") or {}
    me = loading.get("me") or {}

    if m.get("IsDraw"):
        result = "egalite"
    elif m.get("WinnerId") and m.get("WinnerId") == m.get("AccountId"):
        result = "victoire"
    else:
        result = "defaite"

    return {
        "game_uid": m["GameUid"],
        "account_id": None,   # jamais stocke : il ne sert qu'a calculer le resultat ci-dessus
        "start_utc": m.get("StartUtc"),
        "end_utc": m.get("EndUtc"),
        "duration_s": round((m.get("DurationMs") or 0) / 1000),
        "game_mode": m.get("GameMode"),
        "app_version": m.get("AppVersion"),
        "level": m.get("Level"),
        "seat": m.get("Seat"),
        "opponent_id": m.get("OpponentId"),
        "opponent_name": m.get("OpponentName") or opp.get("username"),
        "opponent_is_ai": 1 if m.get("OpponentIsAi") else 0,
        "opponent_rank": opp.get("rank"),
        "opponent_stars": opp.get("stars"),
        "my_rank": me.get("rank"),
        "my_stars": me.get("stars"),
        "result": result,
        "turns": m.get("TurnCount"),
        "my_deck": json.dumps(m.get("MyCards") or []),
        "opponent_deck": json.dumps(m.get("OpponentCards") or []),
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **interpretation(m.get("GameMode"), me.get("stars"), opp.get("stars")),
    }


def insert_match(db, row):
    cols = ", ".join(row)
    marks = ", ".join(":" + k for k in row)
    db.execute(f"INSERT OR IGNORE INTO matches ({cols}) VALUES ({marks})", row)
    db.commit()


# ---------------------------------------------------------------- fichiers du jeu

def find_index():
    """Trouve index.json (serveur et <accountId> detectes, le plus recent si plusieurs)."""
    found = list(REPLAYS_DIR.glob("*/*/index.json")) + list(REPLAYS_DIR.glob("*/index.json"))
    if not found:
        return None
    return max(found, key=lambda p: p.stat().st_mtime)


def read_index(path):
    """Lit index.json. Renvoie None si le fichier est illisible ou en cours d'ecriture."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("[!] index.json introuvable, nouvel essai plus tard.")
        return None
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        print(f"[!] index.json illisible ({type(e).__name__}), nouvel essai plus tard.")
        return None
    if not isinstance(data, list):
        print("[!] index.json n'a pas le format attendu (tableau), nouvel essai plus tard.")
        return None
    return data


# Les replays .srpl du jeu ne sont PAS copies : leur en-tete contient l'AccountId du joueur
# et le ticket de connexion du match. Le resume de chaque match est conserve dans spam.db.


# ---------------------------------------------------------------- catalogue des cartes

CATALOG = {}          # uuid -> nom, rempli par load_catalog()
CARDS = {}            # uuid -> fiche complete (element, rarete, PV...)
CATALOG_LOADED = False
CATALOG_INFO = {"error": None, "generated_utc": None, "mtime": None, "game_version": None}


def load_catalog():
    """Charge catalog.json s'il existe. Sans catalogue, on affiche les UUID."""
    global CATALOG, CARDS, CATALOG_LOADED
    try:
        mtime = CATALOG_PATH.stat().st_mtime
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        CARDS = dict(data["cards"])
        CATALOG = {uid: c["name"] for uid, c in CARDS.items()}
        CATALOG_LOADED = True
        CATALOG_INFO.update(error=None, generated_utc=data.get("generated_utc"), mtime=mtime,
                            game_version=data.get("game_version"))
    except FileNotFoundError:
        CATALOG_LOADED = False
        CATALOG_INFO.update(error="absent", mtime=None)
        print("(catalog.json absent : UUID affiches. Reglages > Preparer les cartes, ou 'python extract_catalog.py --images')")
    except (json.JSONDecodeError, KeyError, TypeError, OSError):
        CATALOG_LOADED = False
        CATALOG_INFO.update(error="illisible", mtime=None)
        print("[!] catalog.json illisible : UUID affiches. Reglages > Preparer les cartes pour le regenerer")


def reload_catalog_if_changed():
    """Recharge catalog.json s'il a ete regenere pendant que l'app tourne."""
    try:
        mtime = CATALOG_PATH.stat().st_mtime
    except OSError:
        mtime = None
    if mtime != CATALOG_INFO["mtime"] or (mtime is None and CATALOG_INFO["error"] != "absent"):
        load_catalog()


def card_name(uid):
    return CATALOG.get(uid, uid)


def unknown_cards(uids):
    """Cartes absentes du catalogue (vide si pas de catalogue du tout)."""
    if not CATALOG_LOADED:
        return []
    return [u for u in uids if u not in CATALOG]


def warn_unknown(uids):
    missing = sorted(set(unknown_cards(uids)))
    if missing:
        print(f"[!] {len(missing)} carte(s) absente(s) du catalogue, catalogue a regenerer "
              f"(Reglages > Preparer les cartes) : {', '.join(missing)}")


def deck_label(deck_json):
    return ", ".join(sorted(card_name(u) for u in json.loads(deck_json)))


# ---------------------------------------------------------------- affichage

LABELS = {"victoire": "Victoire", "defaite": "Defaite", "egalite": "Egalite"}


def format_duration(seconds):
    return f"{seconds} s" if seconds < 60 else f"{round(seconds / 60)} min"


def match_line(row):
    ia = " [IA]" if row["opponent_is_ai"] else ""
    return (f"{LABELS[row['result']]} vs {row['opponent_name']}{ia} "
            f"({row['turns']} tours, {format_duration(row['duration_s'])})")


# ---------------------------------------------------------------- synchronisation

def sync(db, index_path):
    """Insere les matchs absents de la base. Renvoie les lignes ajoutees (plus ancien d'abord)."""
    data = read_index(index_path)
    if data is None:
        return None
    known = known_uids(db)
    added = []
    for m in data:
        uid = m.get("GameUid") if isinstance(m, dict) else None
        if not isinstance(uid, str) or not GAME_UID_RE.match(uid):
            continue
        if uid in known:
            continue
        try:
            row = to_row(m)
        except (KeyError, TypeError, ValueError) as e:
            print(f"[!] entree {uid} ignoree ({type(e).__name__})")
            continue
        insert_match(db, row)
        known.add(uid)
        added.append(row)
    added.sort(key=lambda r: r["start_utc"] or "")
    return added


def watch(stop=None):
    """Boucle de surveillance. `stop` (threading.Event) permet de l'arreter depuis l'app."""
    stop = stop or threading.Event()
    db = open_db()
    print(f"Base : {DB_PATH}")
    print("Surveillance de index.json (Ctrl+C pour quitter)")

    index_path = None
    last_mtime = None
    first_sync = True
    session = {"victoire": 0, "defaite": 0, "egalite": 0}

    while not stop.is_set():
        try:
            reload_catalog_if_changed()
            # Recherche du fichier (le dossier peut ne pas exister encore)
            if index_path is None or not index_path.exists():
                index_path = find_index()
                last_mtime = None
                if index_path is None:
                    print("[!] Aucun index.json trouve, nouvel essai dans quelques secondes.")
                    stop.wait(10)
                    continue

            mtime = index_path.stat().st_mtime
            if mtime != last_mtime:
                if last_mtime is not None:
                    stop.wait(1)  # laisse le jeu finir d'ecrire
                added = sync(db, index_path)
                if added is None:
                    stop.wait(POLL_SECONDS)
                    continue  # on garde l'ancien mtime pour reessayer
                last_mtime = mtime

                if first_sync:
                    # Import initial : resume, sans compter dans la session
                    print(f"Import initial : {len(added)} nouveau(x) match(s), "
                          f"{len(known_uids(db))} en base au total.")
                    warn_unknown(u for row in added
                                 for col in ("my_deck", "opponent_deck")
                                 for u in json.loads(row[col]))
                    first_sync = False
                else:
                    for row in added:
                        session[row["result"]] += 1
                        s = f"{session['victoire']}V {session['defaite']}D"
                        if session["egalite"]:
                            s += f" {session['egalite']}N"
                        print(f"{match_line(row)} | Session : {s}")
                        print(f"    Moi : {deck_label(row['my_deck'])}")
                        print(f"    Adv : {deck_label(row['opponent_deck'])}")
                        warn_unknown(json.loads(row["my_deck"]) + json.loads(row["opponent_deck"]))

            stop.wait(POLL_SECONDS)
        except KeyboardInterrupt:
            print("\nArret du tracker.")
            break
        except OSError as e:
            print(f"[!] Erreur de lecture ({e.strerror}), nouvel essai.")
            index_path = None
            stop.wait(POLL_SECONDS)
        except sqlite3.Error as e:
            print(f"[!] Erreur de base de donnees ({e}), nouvel essai.")
            stop.wait(POLL_SECONDS)
    db.close()
    print("Tracker arrete.")


# ---------------------------------------------------------------- statistiques

def stats():
    if not DB_PATH.exists():
        print("Aucune base pour l'instant : lance d'abord 'python tracker.py'.")
        return
    db = open_db()
    rows = db.execute("SELECT result FROM matches ORDER BY start_utc DESC").fetchall()
    total = len(rows)
    if total == 0:
        print("Aucun match en base.")
        return

    wins = sum(1 for (r,) in rows if r == "victoire")
    losses = sum(1 for (r,) in rows if r == "defaite")
    draws = total - wins - losses

    # Serie en cours : nombre de resultats identiques depuis le dernier match
    current = rows[0][0]
    streak = 0
    for (r,) in rows:
        if r != current:
            break
        streak += 1

    print(f"Parties        : {total} ({wins}V {losses}D {draws}N)")
    print(f"Taux victoire  : {100 * wins / total:.1f} %")
    print(f"Serie en cours : {streak} {LABELS[current].lower()}(s)")
    print("Adversaires les plus rencontres :")
    top = db.execute("""
        SELECT opponent_name, COUNT(*) AS n,
               SUM(result = 'victoire'), SUM(result = 'defaite')
        FROM matches GROUP BY opponent_id ORDER BY n DESC, MAX(start_utc) DESC LIMIT 5
    """).fetchall()
    for name, n, w, l in top:
        print(f"  {name:<20} {n} partie(s)  ({w}V {l}D)")

    last = db.execute("SELECT my_deck FROM matches ORDER BY start_utc DESC LIMIT 1").fetchone()
    print(f"Dernier deck joue : {deck_label(last[0])}")
    warn_unknown(u for (d,) in db.execute("SELECT my_deck || opponent_deck FROM matches")
                 for u in re.findall(r"[0-9a-f-]{36}", d))
    db.close()


def deck_stats():
    """Decks les plus joues, et cartes adverses presentes dans mes defaites."""
    if not DB_PATH.exists():
        print("Aucune base pour l'instant : lance d'abord 'python tracker.py'.")
        return
    db = open_db()
    rows = db.execute("SELECT my_deck, opponent_deck, result FROM matches").fetchall()
    if not rows:
        print("Aucun match en base.")
        return

    # Un deck = l'ensemble de ses 4 cartes (l'ordre ne compte pas)
    decks = {}
    opp_cards = {}   # uuid -> [parties contre, defaites]
    for my_deck, opp_deck, result in rows:
        key = tuple(sorted(json.loads(my_deck)))
        d = decks.setdefault(key, {"victoire": 0, "defaite": 0, "egalite": 0})
        d[result] += 1
        for u in set(json.loads(opp_deck)):
            c = opp_cards.setdefault(u, [0, 0])
            c[0] += 1
            c[1] += result == "defaite"

    print("Mes decks les plus joues :")
    ranked = sorted(decks.items(), key=lambda kv: -sum(kv[1].values()))
    for key, d in ranked[:10]:
        n = sum(d.values())
        names = ", ".join(sorted(card_name(u) for u in key))
        print(f"  {n:>3} partie(s)  {d['victoire']}V {d['defaite']}D  "
              f"{100 * d['victoire'] / n:5.1f} %  | {names}")

    print("Cartes adverses qui me battent le plus souvent :")
    beaters = [(u, n, l) for u, (n, l) in opp_cards.items() if l > 0]
    beaters.sort(key=lambda t: (-t[2], -t[2] / t[1]))
    if not beaters:
        print("  aucune defaite pour l'instant")
    for u, n, l in beaters[:10]:
        print(f"  {l} defaite(s) sur {n} rencontre(s) ({100 * l / n:.0f} %)  {card_name(u)}")

    warn_unknown([u for key in decks for u in key] + list(opp_cards))
    db.close()


# ---------------------------------------------------------------- donnees pour l'interface

def game_resources_file():
    """resources.assets du jeu installe (lecture seule), ou None."""
    gd, _ = game_dir()
    return gd / "SPAM_Data" / "resources.assets" if gd else None


def current_game_version():
    """AppVersion du dernier match ecrit par le jeu (index.json), sinon du dernier match en base."""
    path = find_index()
    if path:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            versions = [(m.get("StartUtc") or "", m.get("AppVersion")) for m in data
                        if isinstance(m, dict) and m.get("AppVersion")]
            if versions:
                return max(versions)[1]
        except (OSError, json.JSONDecodeError):
            pass
    try:
        db = open_db()
        row = db.execute("SELECT app_version FROM matches WHERE app_version IS NOT NULL "
                         "ORDER BY start_utc DESC LIMIT 1").fetchone()
        db.close()
        return row[0] if row else None
    except sqlite3.Error:
        return None


def game_status():
    """Dossier du jeu et versions : testee, actuelle, celle du catalogue, avec un avertissement eventuel."""
    gd, origin = game_dir()
    current = current_game_version()
    warning = None
    if current and current != TESTED_GAME_VERSION:
        warning = (f"Le jeu est en version {current}, l'extraction des cartes a ete verifiee pour la "
                   f"version {TESTED_GAME_VERSION}. Les noms ou images peuvent etre incomplets.")
    return {"dir": str(gd) if gd else None, "origin": origin, "tested": TESTED_GAME_VERSION,
            "current": current, "catalog": CATALOG_INFO.get("game_version"), "warning": warning}


def catalog_status(seen_uids):
    """Etat du catalogue : ok, absent, illisible ou perime (avec la raison)."""
    reload_catalog_if_changed()
    if not CATALOG_LOADED:
        return {"state": CATALOG_INFO["error"] or "absent", "count": 0,
                "generated_utc": None, "unknown": [], "reason": None}
    unknown = sorted(set(unknown_cards(seen_uids)))
    reason = None
    if unknown:
        reason = f"{len(unknown)} carte(s) jouee(s) absente(s) du catalogue"
    else:
        current = current_game_version()
        if current and CATALOG_INFO.get("game_version") and current != CATALOG_INFO["game_version"]:
            reason = f"le jeu est passe de la version {CATALOG_INFO['game_version']} a {current}"
        else:
            game_file = game_resources_file()
            if game_file and CATALOG_INFO["mtime"] and game_file.stat().st_mtime > CATALOG_INFO["mtime"]:
                reason = "le jeu a ete mis a jour apres la generation du catalogue"
    return {"state": "perime" if reason else "ok", "count": len(CATALOG),
            "generated_utc": CATALOG_INFO["generated_utc"], "unknown": unknown, "reason": reason}


CARDS_DIR = BASE_DIR / "cards"   # miniatures <uuid>.webp (python extract_catalog.py --images)
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def card_info(uid):
    c = CARDS.get(uid) or {}
    elements = c.get("elements") or []
    has_image = bool(UUID_RE.match(uid)) and (CARDS_DIR / f"{uid}.webp").exists()
    return {"uuid": uid, "name": c.get("name"), "element": elements[0] if elements else None,
            "rarity": c.get("rarity"), "hp": c.get("hp"), "image": has_image}


def dashboard_data(recent_limit=5000):   # tout l'historique (onglet Historique), avec une limite de securite
    """Toutes les donnees affichees par l'interface (jamais d'AccountId ni de ticket)."""
    reload_catalog_if_changed()
    db = open_db()
    try:
        rows = db.execute("""
            SELECT start_utc, duration_s, opponent_id, opponent_name, opponent_is_ai,
                   opponent_rank, opponent_stars, my_rank, my_stars, result, turns,
                   my_deck, opponent_deck, game_mode, mode_name,
                   my_tier, my_tier_stars, opponent_tier, opponent_tier_stars
            FROM matches ORDER BY start_utc DESC
        """).fetchall()
    finally:
        db.close()

    def standing(stars, placement, tier, tier_stars):
        """Rang interprete + valeurs brutes. 'placement' = champ brut 'rank' du jeu."""
        return {"stars": stars, "placement": placement, "tier": tier,
                "tier_name": RANK_NAMES.get(tier), "tier_stars": tier_stars}

    matches = []
    for r in rows:
        matches.append({
            "start_utc": r[0], "duration_s": r[1], "opp_key": r[2] or r[3], "opponent": r[3],
            "is_ai": bool(r[4]), "result": r[9], "turns": r[10],
            "mode": r[13], "mode_name": r[14] or GAME_MODES.get(r[13], "?"),
            "me": standing(r[8], r[7], r[15], r[16]),
            "opp": standing(r[6], r[5], r[17], r[18]),
            "my_deck": json.loads(r[11] or "[]"), "opp_deck": json.loads(r[12] or "[]"),
        })

    def tally():
        return {"games": 0, "victoire": 0, "defaite": 0, "egalite": 0}

    def record(ms):
        t = tally()
        for m in ms:
            t["games"] += 1
            t[m["result"]] += 1
        return t

    def rate(t):
        return round(100 * t["victoire"] / t["games"], 1) if t["games"] else 0

    # Les parties contre l'IA sont mises a part : elles ne comptent pas dans les statistiques
    humans = [m for m in matches if not m["is_ai"]]
    bots = [m for m in matches if m["is_ai"]]

    h = record(humans)
    streak = {"n": 0, "result": None}
    if humans:
        streak["result"] = humans[0]["result"]
        for m in humans:
            if m["result"] != streak["result"]:
                break
            streak["n"] += 1

    decks, my_cards, opp_cards = {}, {}, {}
    for m in humans:
        key = tuple(sorted(m["my_deck"]))
        for bucket in (decks.setdefault(key, tally()),
                       *(my_cards.setdefault(u, tally()) for u in set(m["my_deck"])),
                       *(opp_cards.setdefault(u, tally()) for u in set(m["opp_deck"]))):
            bucket["games"] += 1
            bucket[m["result"]] += 1

    def opponents_of(ms):
        out = {}
        for m in ms:   # du plus recent au plus ancien : le premier vu donne le dernier etat connu
            o = out.setdefault(m["opp_key"], {**tally(), "name": m["opponent"], "is_ai": m["is_ai"],
                                              "last": m["opp"], "last_seen": m["start_utc"]})
            o["games"] += 1
            o[m["result"]] += 1
        return sorted((o | {"winrate": rate(o)} for o in out.values()), key=lambda o: -o["games"])

    by_mode = {}
    for m in humans:
        by_mode.setdefault(m["mode_name"], tally())
        by_mode[m["mode_name"]]["games"] += 1
        by_mode[m["mode_name"]][m["result"]] += 1

    human_opponents, bot_opponents = opponents_of(humans), opponents_of(bots)  # avant de retirer opp_key
    seen = {u for m in matches for u in m["my_deck"] + m["opp_deck"]}
    for m in matches:
        del m["opp_key"]
        m["my_deck"] = [card_info(u) for u in m["my_deck"]]
        m["opp_deck"] = [card_info(u) for u in m["opp_deck"]]

    return {
        "summary": {
            "total": h["games"], "wins": h["victoire"], "losses": h["defaite"], "draws": h["egalite"],
            "winrate": rate(h), "streak": streak,
            "by_mode": [{"mode": k, **v, "winrate": rate(v)} for k, v in by_mode.items()],
            "ranked_games": sum(1 for m in humans if m["mode"] == 10),
            "bots": record(bots) | {"winrate": rate(record(bots))},
            # mon dernier etat connu (rang calcule depuis les etoiles + position au classement)
            "me": matches[0]["me"] if matches else None,
        },
        "recent": matches[:recent_limit],
        # evolution de mes etoiles et de ma position au classement (au debut de chaque match)
        "progress": [{"t": m["start_utc"], "placement": m["me"]["placement"], "stars": m["me"]["stars"],
                      "tier": m["me"]["tier"], "tier_name": m["me"]["tier_name"], "mode_name": m["mode_name"],
                      "result": m["result"], "opponent": m["opponent"], "is_ai": m["is_ai"]}
                     for m in reversed(matches)][-300:],
        "decks": sorted(({"cards": [card_info(u) for u in k], **t, "winrate": rate(t)}
                         for k, t in decks.items()), key=lambda d: (-d["games"], -d["winrate"])),
        "my_cards": sorted(({"card": card_info(u), **t, "winrate": rate(t)} for u, t in my_cards.items()),
                           key=lambda c: (-c["victoire"], -c["winrate"])),
        "beaters": sorted(({"card": card_info(u), "faced": t["games"], "losses": t["defaite"],
                            "loss_rate": round(100 * t["defaite"] / t["games"], 1)}
                           for u, t in opp_cards.items() if t["defaite"]),
                          key=lambda c: (-c["losses"], -c["loss_rate"])),
        "opponents": human_opponents,
        "bot_opponents": bot_opponents,
        "catalog": catalog_status(seen),
        "game": game_status(),
        "index_found": find_index() is not None,
        # miniatures : presentes dans cards\ et cartes du catalogue qui n'en ont pas
        "images_total": len(list(CARDS_DIR.glob("*.webp"))) if CARDS_DIR.is_dir() else 0,
        "images_missing": sum(1 for u in CARDS if not (CARDS_DIR / f"{u}.webp").exists()),
    }


if __name__ == "__main__":
    # La console Windows ne gere pas toujours les pseudos non latins
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except AttributeError:
        pass

    load_catalog()
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "stats":
        stats()
    elif command == "decks":
        deck_stats()
    else:
        watch()
