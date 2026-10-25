# Installation guide (step by step)

*[Version française](INSTALLATION.md)*

This guide starts from scratch. Allow 5 minutes, plus a few minutes to prepare the cards.
The app interface is in French: the French labels are given in quotes.

You need: Windows 10 or 11, **SPAM** installed through Steam, and about 2.5 GB of free space (only
while preparing the cards).

## 1. Download

1. Open the releases page: <https://github.com/Valaraukar56/Spam-Tracker/releases/latest>.
2. In the latest release, under **Assets**, download:
   - `SPAM-Tracker.exe` (the app);
   - `SHA256SUMS.txt` (the checksum used to verify the file).

## 2. Give the app its own folder

SPAM Tracker stores its data **next to the exe**, so don't leave it in "Downloads":

1. Create a folder, for example `Documents\SPAM Tracker`.
2. Move `SPAM-Tracker.exe` into it.

## 3. Verify the file (SHA-256)

This proves the file is exactly the published one, unmodified.

1. Open the `SPAM Tracker` folder, click the address bar, type `powershell` and press Enter.
2. Paste this command and press Enter:

   ```powershell
   (Get-FileHash .\SPAM-Tracker.exe -Algorithm SHA256).Hash
   ```

3. Open `SHA256SUMS.txt` in Notepad. Both strings must be **identical** (case does not matter).
   If they differ, **do not run the file**: delete it and download it again.

## 4. First launch and the SmartScreen warning

Double-click `SPAM-Tracker.exe`. Windows may show a blue **"Windows protected your PC"** screen.

1. Click **"More info"**.
2. Check that the app name is `SPAM-Tracker.exe`.
3. Click **"Run anyway"**.

**Why this warning?** The exe is not signed with a (paid) code signing certificate, and SmartScreen
warns about any new, rarely downloaded program, even a safe one. The SHA-256 check above, or
building from source (see the README), lets you verify what you run.

On first launch the SPAM Tracker window opens. If you already played, your latest matches appear
right away (the game keeps 10).

## 5. Prepare the cards

Without this step, cards are shown by their identifier, without name or artwork.

1. Click **"Réglages"** (Settings) in the left bar.
2. In **"Dossier du jeu"** (game folder), check that the game is **"Détecté"** (detected). If not:
   - in Steam, right click SPAM > **Manage** > **Browse local files**;
   - copy the path of the folder that opens (the one containing `SPAM.exe`);
   - paste it in the field, then click **"Enregistrer"** (Save), or use **"Parcourir"** (Browse).
3. Click **"Préparer les cartes"** (Prepare cards) and wait for the progress bar to finish (a few
   minutes).

The app reads the game files without modifying them, makes a temporary copy, extracts names and
thumbnails, then deletes the copy. **Do it again after each game update**: a banner reminds you.

## 6. Everyday use

- **Keep SPAM Tracker running while you play.** Each match appears a few seconds after it ends.
- Closing the window **does not quit** the app: it moves to the notification area (near the clock).
  Click its icon to reopen it.
- To really quit: right click the icon > **"Quitter"** (Quit).

## 7. Start with Windows (recommended)

The game only keeps your last 10 matches, so the app should be running whenever you play:

1. **"Réglages"** > enable **"Lancer au démarrage de Windows"**.
2. SPAM Tracker will then start quietly in the notification area at each sign-in.

If you move the exe to another folder, turn this option off and on again.

## 8. Where is my data?

Everything is in the app folder (`Documents\SPAM Tracker` in this example):

| Item | Content |
|---|---|
| `spam.db` | your match history (the most valuable file) |
| `catalog.json`, `cards\` | prepared cards (can be regenerated anytime) |
| `settings.json` | your settings (game folder) |
| `tracker.log` | log file, useful for troubleshooting |
| `webview-cache\` | internal files of the window |

**"Réglages" > "Dossier des données" > "Ouvrir"** opens this folder. These files are personal: never
publish them (see SECURITY.md).

## 9. Back up your matches

1. Quit the app (right click the icon > **"Quitter"**).
2. Copy `spam.db` somewhere else (USB drive, cloud, another disk).
3. To restore it, put the file back next to `SPAM-Tracker.exe` and start the app.

## 10. Update SPAM Tracker

Quit the app, replace `SPAM-Tracker.exe` with the new version **in the same folder** (check its
SHA-256), then start it. Your data is kept.

## 11. Uninstall

1. **"Réglages"** > turn off **"Lancer au démarrage de Windows"** (if you enabled it).
2. Right click the icon > **"Quitter"**.
3. Delete the app folder.

That's all: SPAM Tracker has no installer and writes nothing elsewhere, except the startup entry if
you enabled it. The game is never modified.
