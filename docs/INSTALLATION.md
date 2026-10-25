# Guide d'installation (pas à pas)

*[English version](INSTALLATION.en.md)*

Ce guide part de zéro. Compte 5 minutes, plus quelques minutes pour préparer les cartes.

Il te faut : Windows 10 ou 11, le jeu **SPAM** installé avec Steam, et environ 2,5 Go d'espace
libre (seulement pendant la préparation des cartes).

## 1. Télécharger

1. Ouvre la page des versions : <https://github.com/Valaraukar56/Spam-Tracker/releases/latest>.
2. Dans la dernière version, sous **Assets**, télécharge :
   - `SPAM-Tracker.exe` (l'application) ;
   - `SHA256SUMS.txt` (l'empreinte qui permet de vérifier le fichier).

## 2. Ranger l'application dans son propre dossier

SPAM Tracker enregistre ses données **à côté de l'exe**. Ne le laisse donc pas dans
"Téléchargements" :

1. Crée un dossier, par exemple `Documents\SPAM Tracker`.
2. Déplace `SPAM-Tracker.exe` dedans.

## 3. Vérifier le fichier (SHA-256)

Cette étape garantit que le fichier est exactement celui publié, sans modification.

1. Ouvre le dossier `SPAM Tracker`, clique dans la barre d'adresse, tape `powershell`, puis Entrée.
2. Dans la fenêtre bleue, colle cette commande et appuie sur Entrée :

   ```powershell
   (Get-FileHash .\SPAM-Tracker.exe -Algorithm SHA256).Hash
   ```

3. Ouvre `SHA256SUMS.txt` avec le Bloc-notes. Les deux suites de chiffres et de lettres doivent
   être **identiques** (majuscules et minuscules ne comptent pas).
   Si elles diffèrent, **ne lance pas le fichier** : supprime-le et retélécharge-le.

## 4. Premier lancement et avertissement SmartScreen

Double-clique sur `SPAM-Tracker.exe`. Windows peut afficher un écran bleu
**"Windows a protégé votre ordinateur"**.

1. Clique sur **"Informations complémentaires"**.
2. Vérifie que l'application indiquée est bien `SPAM-Tracker.exe`.
3. Clique sur **"Exécuter quand même"**.

**Pourquoi cet avertissement ?** L'exe n'est pas signé avec un certificat de développeur, qui est
payant. SmartScreen avertit pour tout programme récent et peu téléchargé, même sans danger.
La vérification SHA-256 de l'étape 3, ou la compilation depuis le code source (voir le README),
permet de s'assurer du contenu.

Au premier lancement, la fenêtre de SPAM Tracker s'ouvre. Si tu as déjà joué, tes derniers matchs
apparaissent tout de suite (le jeu en garde 10).

## 5. Préparer les cartes

Sans cette étape, les cartes s'affichent par leur identifiant, sans nom ni illustration.

1. Clique sur **Réglages**, dans la barre de gauche.
2. Dans **Dossier du jeu**, vérifie que le jeu est **"Détecté"**. Sinon :
   - dans Steam, fais un clic droit sur SPAM > **Gérer** > **Parcourir les fichiers locaux** ;
   - copie le chemin du dossier qui s'ouvre (celui qui contient `SPAM.exe`) ;
   - colle-le dans le champ, puis clique sur **Enregistrer** (ou utilise **Parcourir**).
3. Clique sur **Préparer les cartes**, puis attends la fin de la barre de progression (quelques
   minutes).

L'application lit les fichiers du jeu sans les modifier, en fait une copie temporaire, extrait les
noms et des miniatures, puis supprime la copie.
**Refais cette étape après chaque mise à jour du jeu** : un bandeau te le rappellera.

## 6. Utilisation au quotidien

- **Laisse SPAM Tracker tourner pendant que tu joues.** Chaque match apparaît quelques secondes
  après sa fin.
- Fermer la fenêtre (la croix) **ne quitte pas** l'application : elle se range dans la zone de
  notification, près de l'horloge. Clique sur son icône pour la rouvrir.
- Pour quitter vraiment : clic droit sur l'icône > **Quitter**.

## 7. Lancer au démarrage de Windows (recommandé)

Le jeu ne garde que tes 10 derniers matchs. Pour ne rien perdre, l'application doit tourner quand
tu joues :

1. **Réglages** > active **Lancer au démarrage de Windows**.
2. SPAM Tracker démarrera alors discrètement dans la zone de notification à chaque ouverture de
   session.

Si tu déplaces l'exe dans un autre dossier, désactive puis réactive cette option.

## 8. Où sont mes données ?

Tout est dans le dossier de l'application (`Documents\SPAM Tracker` dans l'exemple) :

| Élément | Contenu |
|---|---|
| `spam.db` | ton historique de matchs (le plus précieux) |
| `catalog.json`, `cards\` | les cartes préparées (régénérables à tout moment) |
| `settings.json` | tes réglages (dossier du jeu) |
| `tracker.log` | le journal, utile en cas de problème |
| `webview-cache\` | les fichiers internes de la fenêtre |

**Réglages > Dossier des données > Ouvrir** ouvre ce dossier.
Ces fichiers sont personnels : ne les publie pas (voir SECURITY.md).

## 9. Sauvegarder ses matchs

1. Quitte l'application (clic droit sur l'icône > **Quitter**).
2. Copie `spam.db` ailleurs : clé USB, cloud, autre disque.
3. Pour restaurer, remets ce fichier à côté de `SPAM-Tracker.exe`, puis relance l'application.

## 10. Mettre à jour SPAM Tracker

Quitte l'application, remplace `SPAM-Tracker.exe` par la nouvelle version **dans le même dossier**
(vérifie son SHA-256), puis relance-la. Tes données sont conservées.

## 11. Désinstaller

1. **Réglages** > désactive **Lancer au démarrage de Windows** (si tu l'avais activé).
2. Clic droit sur l'icône > **Quitter**.
3. Supprime le dossier de l'application.

C'est tout. SPAM Tracker n'a pas d'installateur et n'écrit rien ailleurs, à part l'entrée de
démarrage automatique si tu l'avais activée. Le jeu n'est jamais modifié.
