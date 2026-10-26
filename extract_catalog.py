"""Extraction du catalogue des cartes SPAM (catalog.json) et de leurs miniatures (cards\\).

Depuis l'application : Reglages > "Preparer les cartes" (appelle extract()).
En ligne de commande :
    python extract_catalog.py                    catalogue seul
    python extract_catalog.py --images           catalogue + miniatures WebP dans cards\\
    python extract_catalog.py --game-dir "D:\\...\\SPAM"   dossier du jeu si non detecte
    python extract_catalog.py --keep-copies      garde les copies de travail (tmp-jeu\\)
    python extract_catalog.py --no-copy          reutilise les copies gardees

A relancer apres chaque mise a jour du jeu.

Securite : le dossier du jeu n'est que lu. Les copies de travail vont dans tmp-jeu\\
(dans le dossier des donnees du tracker) et sont supprimees a la fin, meme en cas
d'erreur. Aucune connexion reseau.

Le jeu est compile sans "typetrees" : UnityPy ne sait pas decoder les
ScriptableObjects du jeu tout seul. On lit donc les octets bruts de CardData en
suivant l'ordre des champs, deduit par analyse du fichier (version 1.26 du jeu).
Les textures (Texture2D) sont un type Unity standard que UnityPy decode directement.
"""

import csv
import gc
import io
import json
import re
import shutil
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

# resources.assets contient les donnees, globalgamemanagers.assets les noms de classes (MonoScript)
ASSET_FILES = ["resources.assets", "globalgamemanagers.assets"]
RESS_FILE = "resources.assets.resS"          # pixels des textures (~2,4 Go), seulement pour les images
THUMB_W, THUMB_H = 200, 285                   # ratio des illustrations du jeu (516 x 736)
FREE_SPACE_MARGIN = 300 * 1024 * 1024         # marge disque en plus des copies
TESTED_GAME_VERSION = "1.26"

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
ILLUSTRATION_RE = re.compile(rb"Sprites/Card/Illustration/[A-Za-z0-9_]+")
TALENT_ID_RE = re.compile(rb"\$\x00\x00\x00([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


class ExtractError(Exception):
    """Erreur avec un message comprehensible par l'utilisateur."""


class Reader:
    """Lecture sequentielle d'un objet Unity serialise (little endian, alignement 4)."""

    def __init__(self, raw):
        self.b = raw
        self.i = 0

    def int(self):
        v = struct.unpack_from("<i", self.b, self.i)[0]
        self.i += 4
        return v

    def string(self):
        n = self.int()
        if n < 0 or self.i + n > len(self.b):
            raise ValueError("chaine invalide")
        s = self.b[self.i:self.i + n].decode("utf-8")
        self.i = (self.i + n + 3) & ~3
        return s

    def pptr(self):
        """Reference vers un autre objet : (fileID int32, pathID int64)."""
        file_id = self.int()
        path_id = struct.unpack_from("<q", self.b, self.i)[0]
        self.i += 8
        return path_id if file_id == 0 else None

    def pptr_list(self):
        n = self.int()
        if not 0 <= n <= 100:
            raise ValueError("liste invalide")
        return [self.pptr() for _ in range(n)]

    def skip(self, n):
        self.i += n


def read_name(raw):
    """m_Name d'un MonoBehaviour (apres GameObject, Enabled, Script)."""
    r = Reader(raw)
    r.skip(28)
    return r.string()


def read_tag(raw):
    """ElementData / RarityData : m_Name puis un identifiant court ("fire", "rarity-epic")."""
    r = Reader(raw)
    r.skip(28)
    r.string()
    r.skip(4)
    return r.string()


def read_card(raw):
    """Decode un CardData. Renvoie un dict, ou None si la structure ne colle pas."""
    r = Reader(raw)
    r.skip(28)                 # m_GameObject, m_Enabled, m_Script
    name = r.string()          # m_Name = nom affiche (en francais)
    r.string()                 # champ texte vide
    uid = r.string()           # identifiant de la carte
    if not UUID_RE.match(uid):
        return None
    number = r.int()           # numero de la carte (collection)
    r.skip(20)                 # champs non identifies
    illustration = r.string()  # chemin de l'illustration (Sprites/Card/Illustration/...)
    r.skip(16)                 # couleur (4 floats)
    slug = r.string()          # identifiant texte de la carte
    r.pptr()                   # artiste
    elements = r.pptr_list()   # elements de la carte
    rarity = r.pptr()          # rarete
    hp = r.int()               # points de vie
    stat2 = r.int()            # second entier non identifie
    abilities = r.pptr_list()  # attaques / capacites
    statuses = r.pptr_list()   # statuts passifs
    talents = r.pptr_list()    # talents disponibles
    return {
        "uuid": uid, "name": name, "slug": slug, "number": number, "illustration": illustration,
        "_elements": elements, "_rarity": rarity, "hp": hp, "_stat2": stat2,
        "_abilities": abilities, "_statuses": statuses, "_talents": talents,
    }


def load_translations(env):
    """Cherche la table CSV de traduction (cles du type Talent.Name.X) et renvoie {cle: texte FR}."""
    for obj in env.objects:
        if obj.type.name != "TextAsset":
            continue
        try:
            text = obj.read().m_Script
        except Exception:
            continue
        if isinstance(text, bytes):
            text = text.decode("utf-8", "replace")
        if "Talent.Name." not in text:
            continue
        rows = csv.reader(io.StringIO(text))
        header = next(rows, [])
        # colonne francaise si l'en-tete l'indique, sinon la premiere langue
        col = 1
        for i, h in enumerate(header):
            if h.strip().lower() in ("fr", "french", "francais", "français"):
                col = i
        return {row[0]: row[col] for row in rows if len(row) > col}
    return {}


# ---------------------------------------------------------------- copies de travail

def copy_with_progress(src, dst, on_bytes):
    """Copie par blocs (lecture seule sur la source) en signalant les octets copies."""
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        while True:
            chunk = fin.read(16 * 1024 * 1024)
            if not chunk:
                break
            fout.write(chunk)
            on_bytes(len(chunk))


def close_handles_in(folder):
    """UnityPy garde ses propres flux ouverts sur les copies : on ferme ceux du dossier donne."""
    folder = Path(folder).resolve()
    gc.collect()
    for o in gc.get_objects():
        if isinstance(o, (io.BufferedReader, io.FileIO)) and not o.closed:
            try:
                if Path(str(getattr(o, "name", ""))).resolve().parent == folder:
                    o.close()
            except (OSError, ValueError):
                pass


def delete_copies(tmp_dir, log):
    """Supprime tmp-jeu\\ et son contenu (jamais les fichiers du jeu)."""
    if not tmp_dir.is_dir():
        return
    close_handles_in(tmp_dir)
    for f in tmp_dir.iterdir():
        try:
            f.unlink()
        except OSError as e:
            log(f"[!] Copie {f.name} non supprimee ({e.strerror}) : a effacer a la main dans {tmp_dir}")
    try:
        tmp_dir.rmdir()
        log("Copies temporaires supprimees.")
    except OSError:
        pass


# ---------------------------------------------------------------- miniatures

def extract_images(env, cards, cards_dir, progress, log):
    """Cree cards\\<uuid>.webp (200 x 285) pour chaque carte, a partir de son illustration.

    La carte est reliee a sa texture par le chemin Sprites/Card/Illustration/<nom> lu dans
    son CardData. Les originaux ne sont jamais modifies : on enregistre une miniature a part.
    Renvoie un rapport ; met a jour card["image"].
    """
    from PIL import Image, ImageOps

    textures = {}
    for obj in env.objects:
        if obj.type.name == "Texture2D" and obj.assets_file.name == "resources.assets":
            name = obj.peek_name()
            if name and name.startswith("illustration_"):
                textures[name] = obj
    log(f"Illustrations trouvees dans le jeu : {len(textures)}")

    cards_dir.mkdir(exist_ok=True)
    thumbs, failures, no_image = {}, {}, []
    total = max(1, len(cards))
    for n, c in enumerate(cards.values(), 1):
        key = Path(c["illustration"]).name if c.get("illustration") else None
        c["image"] = False
        if key not in textures:
            no_image.append(c["name"])
        else:
            if key not in thumbs and key not in failures:
                try:
                    img = textures[key].read().image.convert("RGBA")
                    # meme cadre pour toutes : recadrage centre minimal puis reduction
                    thumbs[key] = ImageOps.fit(img, (THUMB_W, THUMB_H), Image.LANCZOS)
                except Exception as e:
                    failures[key] = f"{type(e).__name__}: {e}"
            if key in thumbs:
                thumbs[key].save(cards_dir / f"{c['uuid']}.webp", "WEBP", quality=82, method=6)
                c["image"] = True
        progress(n / total, f"Illustrations : {n} / {total}")

    for f in cards_dir.glob("*.webp"):          # miniatures de cartes disparues
        if f.stem not in cards:
            f.unlink()

    used = {Path(c["illustration"]).name for c in cards.values()
            if c.get("illustration") and Path(c["illustration"]).name in textures}
    bad = []
    for c in cards.values():
        if c["image"]:
            try:
                with Image.open(cards_dir / f"{c['uuid']}.webp") as im:
                    if im.size != (THUMB_W, THUMB_H):
                        bad.append(c["uuid"])
            except OSError:
                bad.append(c["uuid"])
    for key, err in sorted(failures.items()):
        log(f"  [!] {key} : {err}")
    return {
        "images": sum(1 for c in cards.values() if c["image"]),
        "images_ok": not failures and not bad and len(thumbs) == len(used),
        "no_image": sorted(no_image),
        "unused_images": sorted(set(textures) - used),
        "failures": len(failures),
    }


# ---------------------------------------------------------------- extraction complete

def extract(game_dir, out_dir, images=True, progress=None, log=print,
            keep_copies=False, reuse_copies=False, game_version=None):
    """Extrait catalog.json (et cards\\ si images) depuis le jeu installe dans game_dir.

    progress(fraction 0-1, message) est appele regulierement. Leve ExtractError avec un
    message lisible en cas de probleme. Les copies de travail sont toujours supprimees
    (sauf keep_copies). Renvoie un rapport (dict).
    """
    progress = progress or (lambda f, m: None)
    out_dir = Path(out_dir)
    game_data = Path(game_dir) / "SPAM_Data"
    tmp_dir = out_dir / "tmp-jeu"
    names = ASSET_FILES + ([RESS_FILE] if images else [])

    try:
        import UnityPy
    except ImportError:
        raise ExtractError("Le module UnityPy est absent : impossible de lire les fichiers du jeu. "
                           "Utilise SPAM-Tracker.exe, ou installe-le (pip install -r requirements.txt).")

    if not reuse_copies:
        missing = [n for n in names if not (game_data / n).is_file()]
        if missing:
            raise ExtractError(f"Fichiers du jeu introuvables dans {game_data} : {', '.join(missing)}. "
                               "Verifie le dossier du jeu dans les Reglages.")
        needed = sum((game_data / n).stat().st_size for n in names)
        out_dir.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(out_dir).free
        if free < needed + FREE_SPACE_MARGIN:
            raise ExtractError(
                f"Pas assez de place sur le disque des donnees ({free / 1e9:.1f} Go libres, il faut environ "
                f"{(needed + FREE_SPACE_MARGIN) / 1e9:.1f} Go le temps de l'extraction). Libere de la place, "
                "ou deplace le dossier de SPAM Tracker sur un autre disque.")

    report = {}
    try:
        # 1. Copies de travail (0 a 35 %)
        if not reuse_copies:
            tmp_dir.mkdir(parents=True, exist_ok=True)
            done = [0]

            def on_bytes(n):
                done[0] += n
                progress(0.35 * done[0] / needed, f"Copie des fichiers du jeu : {done[0] / 1e9:.1f} / {needed / 1e9:.1f} Go")

            for n in names:
                copy_with_progress(game_data / n, tmp_dir / n, on_bytes)
            log(f"Copies de travail faites dans {tmp_dir}")
        for n in names:
            if not (tmp_dir / n).is_file():
                raise ExtractError(f"Copie de travail absente : {n}. Relance sans --no-copy.")

        # 2. Lecture des donnees (35 a 50 %)
        progress(0.36, "Lecture des donnees du jeu...")
        env = UnityPy.load(*(str(tmp_dir / n) for n in ASSET_FILES))
        by_class = {}
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour" or obj.assets_file.name != "resources.assets":
                continue
            try:
                cls = obj.read(check_read=False).m_Script.read().m_ClassName
            except Exception:
                continue
            if cls in ("CardData", "TalentData", "ElementData", "RarityData", "AbilityData"):
                by_class.setdefault(cls, {})[obj.path_id] = obj.get_raw_data()
        if not by_class.get("CardData"):
            raise ExtractError("Aucune carte trouvee dans les fichiers du jeu : son format a probablement change "
                               f"(extraction verifiee pour la version {TESTED_GAME_VERSION}).")
        tr = load_translations(env)
        progress(0.5, "Decodage des cartes...")

        # 3. Tables de correspondance pathID -> libelle, puis les cartes (50 a 55 %)
        def safe(fn, raw, default=None):
            try:
                return fn(raw)
            except (ValueError, struct.error, UnicodeDecodeError):
                return default

        elements = {pid: safe(read_tag, raw) for pid, raw in by_class.get("ElementData", {}).items()}
        rarities = {pid: safe(read_tag, raw, "").replace("rarity-", "") or None
                    for pid, raw in by_class.get("RarityData", {}).items()}
        abilities = {pid: safe(read_name, raw) for pid, raw in by_class.get("AbilityData", {}).items()}
        talents, talents_by_id = {}, {}
        for pid, raw in by_class.get("TalentData", {}).items():
            key = safe(read_name, raw)
            if key:
                talents[pid] = tr.get(f"Talent.Name.{key}", key)
                # identifiant du talent (premier UUID apres le nom) : celui cite dans les replays
                m = TALENT_ID_RE.search(raw, 28)
                if m:
                    talents_by_id[m.group(1).decode()] = talents[pid]

        cards, partial = {}, 0
        for raw in by_class["CardData"].values():
            try:
                c = read_card(raw)
            except (ValueError, struct.error, UnicodeDecodeError):
                c = None
            if c is None:
                # repli : au minimum le nom et l'UUID s'ils se trouvent en tete
                try:
                    r = Reader(raw)
                    r.skip(28)
                    name = r.string()
                    r.string()
                    uid = r.string()
                    if UUID_RE.match(uid):
                        m = ILLUSTRATION_RE.search(raw)
                        cards[uid] = {"uuid": uid, "name": name,
                                      "illustration": m.group(0).decode() if m else None}
                        partial += 1
                except (ValueError, struct.error, UnicodeDecodeError):
                    pass
                continue
            cards[c["uuid"]] = {
                "uuid": c["uuid"], "name": c["name"], "number": c["number"], "illustration": c["illustration"],
                "elements": [elements.get(p) for p in c["_elements"] if elements.get(p)],
                "rarity": rarities.get(c["_rarity"]), "hp": c["hp"],
                "abilities": [abilities[p] for p in c["_abilities"] if abilities.get(p)],
                "talents": [talents[p] for p in c["_talents"] if talents.get(p)],
            }
        if not cards:
            raise ExtractError("Les cartes du jeu n'ont pas pu etre decodees : son format a probablement change "
                               f"(extraction verifiee pour la version {TESTED_GAME_VERSION}).")
        report.update(cards=len(cards), partial=partial)
        progress(0.55, f"{len(cards)} cartes decodees")

        # 4. Miniatures (55 a 95 %)
        cards_dir = out_dir / "cards"
        if images:
            report.update(extract_images(env, cards, cards_dir,
                                         lambda f, m: progress(0.55 + 0.40 * f, m), log))
        else:
            for c in cards.values():
                c["image"] = (cards_dir / f"{c['uuid']}.webp").exists()

        # 5. Ecriture (atomique) du catalogue
        progress(0.96, "Ecriture du catalogue...")
        out = {
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "resources.assets",
            "game_version": game_version,
            "tested_with": TESTED_GAME_VERSION,
            "count": len(cards),
            "cards": dict(sorted(cards.items(), key=lambda kv: kv[1]["name"].lower())),
            "talents": talents_by_id,   # uuid du talent -> nom francais
        }
        catalog = out_dir / "catalog.json"
        tmp = catalog.with_suffix(".tmp")
        tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(catalog)
        log(f"{len(cards)} cartes ecrites dans catalog.json ({partial} avec nom et UUID seulement), "
            f"{len(talents)} talents, {len(elements)} elements, {len(rarities)} raretes.")
        if partial:
            report.setdefault("warnings", []).append(
                f"{partial} carte(s) decodee(s) partiellement (nom seulement) : le format du jeu a peut-etre change.")
        del env, by_class
    except MemoryError:
        raise ExtractError("Memoire insuffisante pendant l'extraction. Ferme d'autres applications et reessaie.")
    except OSError as e:
        raise ExtractError(f"Erreur d'acces aux fichiers : {e.strerror or e} ({getattr(e, 'filename', '')}).")
    finally:
        if not keep_copies:
            progress(0.98, "Suppression des fichiers temporaires...")
            delete_copies(tmp_dir, log)
    progress(1.0, "Termine")
    return report


# ---------------------------------------------------------------- ligne de commande

def main():
    args = sys.argv[1:]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import tracker   # dossier des donnees, detection du jeu, version du jeu

    gd = None
    if "--game-dir" in args:
        i = args.index("--game-dir")
        gd = tracker.normalize_game_dir(args[i + 1] if i + 1 < len(args) else "")
        if not gd:
            sys.exit("Ce dossier ne contient pas SPAM (SPAM_Data\\resources.assets introuvable).")
    else:
        gd, _ = tracker.game_dir()
    if not gd and "--no-copy" not in args:
        sys.exit("Jeu SPAM introuvable. Indique son dossier : python extract_catalog.py --game-dir \"<dossier>\"")

    last = [-1]

    def progress(f, msg):
        pct = int(f * 100)
        if pct >= last[0] + 5 or f >= 1:
            last[0] = pct
            print(f"[{pct:3d} %] {msg}")

    try:
        report = extract(gd or Path("."), tracker.BASE_DIR, images="--images" in args, progress=progress,
                         keep_copies="--keep-copies" in args, reuse_copies="--no-copy" in args,
                         game_version=tracker.current_game_version())
    except ExtractError as e:
        sys.exit(f"[!] {e}")
    print(json.dumps({k: v for k, v in report.items() if k not in ("no_image", "unused_images")},
                     ensure_ascii=False))
    if report.get("no_image"):
        print(f"Cartes sans image : {', '.join(report['no_image'])}")
    if report.get("unused_images"):
        print(f"Images qu'aucune carte n'utilise : {', '.join(report['unused_images'])}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
