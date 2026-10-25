# Construit dist\SPAM-Tracker.exe et dist\SHA256SUMS.txt
#
# Prerequis (une seule fois), depuis ce dossier :
#   py -3.13 -m venv .venv
#   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Puis :
#   powershell -ExecutionPolicy Bypass -File build.ps1
#
# L'exe embarque l'interface (ui.html) et l'extracteur de cartes (UnityPy).
# Aucune donnee personnelle ni aucun fichier du jeu n'est embarque.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Environnement .venv absent : voir les prerequis en haut de ce fichier." }

# Icone de l'exe, generee avec la meme fonction que l'icone de la zone de notification
& $py -c "import app; app.tray_image(256).save('icon.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if ($LASTEXITCODE) { throw "Generation de l'icone impossible" }

& $py -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name SPAM-Tracker --icon icon.ico `
    --add-data "ui.html;." `
    --hidden-import extract_catalog `
    --collect-data UnityPy --collect-data archspec `
    --collect-submodules etcpak --collect-binaries etcpak `
    --collect-submodules astc_encoder --collect-binaries astc_encoder `
    --collect-submodules texture2ddecoder `
    --collect-binaries fmod_toolkit --collect-submodules pyfmodex `
    --exclude-module tkinter `
    app.py
if ($LASTEXITCODE) { throw "PyInstaller a echoue" }

# Empreinte SHA-256, au format de sha256sum (verifiable avec Get-FileHash ou certutil)
$exe = "dist\SPAM-Tracker.exe"
$hash = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
"$hash *SPAM-Tracker.exe" | Set-Content -Encoding ascii "dist\SHA256SUMS.txt"

Get-Item $exe | Select-Object Name, @{n = "Taille (Mo)"; e = { [math]::Round($_.Length / 1MB, 1) } }
Write-Host "SHA-256 : $hash"
