# HBntory---Inventory

# HBntory — Authentification et autorisation du Backoffice

**Fichiers concernés** : `backoffice/app.py`, `backoffice/decorators.py`, `backoffice/init_db.py`, `backoffice/models.py`

---

## 1. Stratégie d'authentification retenue : session

### Décision

L'authentification du Backoffice repose sur des **sessions côté serveur** (`flask.session`), et non sur des jetons de type JWT.

### Justification

Le Backoffice a été conçu en **rendu côté serveur (SSR)** : chaque interaction de l'utilisateur provoque le chargement d'une page HTML complète générée par le serveur, sans code JavaScript client chargé d'appeler une API.

Dans ce contexte :

- Avec une **session**, le cookie d'identification est renvoyé **automatiquement par le navigateur** à chaque requête. Aucun code supplémentaire n'est nécessaire côté client pour maintenir l'authentification d'une page à l'autre.
- Avec un **jeton (JWT)**, il faudrait au contraire écrire du JavaScript pour stocker le jeton (typiquement dans `localStorage`) puis l'ajouter manuellement dans les en-têtes `Authorization` de chaque requête. Ce mécanisme est pertinent pour une application monopage (SPA) ou une application mobile consommant une API REST, mais il ajouterait ici une couche de complexité sans bénéfice, puisqu'aucun client JavaScript autonome n'existe dans notre Backoffice.

### Bénéfice et compromis

| | |
|---|---|
| **Bénéfice** | Gestion automatique par le navigateur, aucun code client à écrire, intégration native avec Flask. |
| **Compromis** | Le mécanisme est lié au navigateur : il ne conviendrait pas tel quel à un client mobile ou à une API consommée par un service tiers. Ce n'est pas une limite pour ce projet, le Backoffice étant exclusivement une application web interne. |

### Sécurité du cookie de session

Flask signe cryptographiquement le contenu du cookie de session à l'aide d'une **clé secrète** (`app.secret_key`). Cette signature garantit qu'un utilisateur ne peut pas modifier le contenu de son propre cookie — par exemple remplacer son `user_id` par celui d'un autre compte — sans que Flask ne détecte l'altération et rejette le cookie.

Cette clé est chargée depuis une variable d'environnement et **jamais écrite en dur dans le code source** :

```python
load_dotenv()
app.secret_key = os.getenv("SECRET_KEY_FLASK")
```

Le fichier `.env` qui contient sa valeur réelle est exclu du dépôt via `.gitignore`. Un fichier `.env.example` versionné documente les variables attendues sans révéler leurs valeurs.

---

## 2. Stockage sécurisé des mots de passe

### Mécanisme utilisé : bcrypt

La bibliothèque **bcrypt** a été retenue pour le hachage des mots de passe.

### Comment les mots de passe sont hachés

À la création d'un compte (script `init_db.py`, et prochainement lors de la création d'utilisateurs par l'administrateur) :

```python
password = os.getenv("ADMIN_PASSWORD")
hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
hash = hash.decode('utf-8')
```

Étapes :

1. `password.encode('utf-8')` convertit la chaîne de caractères en octets, format attendu par bcrypt.
2. `bcrypt.gensalt()` génère un **sel** (*salt*) aléatoire, différent à chaque appel.
3. `bcrypt.hashpw(...)` combine le mot de passe et le sel pour produire l'empreinte. Le sel est intégré au résultat final, ce qui permet de le retrouver lors de la vérification.
4. `.decode('utf-8')` reconvertit le résultat (des octets) en chaîne de caractères, afin de rester cohérent avec le type de la colonne `password_hash` déclarée en `String(255)`. Sans cette conversion, le type stocké serait `bytes` : SQLite l'accepte silencieusement, mais un moteur plus strict comme PostgreSQL — utilisé en déploiement — le refuserait ou provoquerait des comportements inattendus.

À aucun moment le mot de passe en clair n'est écrit en base ni conservé après l'opération.

### Comment la vérification fonctionne

Un hachage est une opération **à sens unique** : il est impossible de retrouver le mot de passe d'origine à partir de son empreinte. La vérification ne consiste donc pas à « déchiffrer » l'empreinte, mais à **recalculer** une empreinte à partir du mot de passe saisi et à la comparer :

```python
if user and user.is_active and bcrypt.checkpw(
        password.encode('utf-8'),
        user.password_hash.encode('utf-8')):
    flask_session['user_id'] = user.id
```

`bcrypt.checkpw()` extrait le sel contenu dans l'empreinte stockée, recalcule le hachage du mot de passe soumis avec ce même sel, et compare les deux résultats. Il retourne `True` uniquement si les empreintes correspondent.

### Pourquoi un hachage généraliste comme SHA-256 seul est insuffisant

SHA-256 est un algorithme de hachage **généraliste**, conçu à l'origine pour vérifier l'intégrité de fichiers ou de messages. Il n'est pas adapté au stockage de mots de passe, pour trois raisons :

1. **Il est délibérément rapide.** C'est une qualité pour vérifier l'intégrité d'un fichier, mais un défaut majeur ici : un attaquant ayant dérobé la base peut tester des milliards de combinaisons par seconde sur du matériel grand public. bcrypt est au contraire volontairement **lent** et son coût est paramétrable, ce qui rend une attaque par force brute des ordres de grandeur plus coûteuse.
2. **Il ne sale pas les empreintes.** Sans sel, deux utilisateurs ayant choisi le même mot de passe obtiennent exactement la même empreinte, ce qui est immédiatement exploitable. Cela ouvre également la voie aux *rainbow tables*, ces tables précalculées associant des empreintes connues à leurs mots de passe d'origine. bcrypt génère un sel aléatoire unique pour chaque hachage : deux comptes partageant le même mot de passe produisent des empreintes différentes, et aucune table précalculée n'est réutilisable.
3. **Son coût n'est pas ajustable.** Le matériel devient plus rapide chaque année ; un algorithme à coût fixe se dévalue mécaniquement avec le temps. bcrypt permet d'augmenter son facteur de coût pour rester aligné sur l'état de l'art sans changer d'algorithme.

Des alternatives comme **Argon2** ou **PBKDF2** répondent au même besoin et auraient également été acceptables. bcrypt a été retenu pour sa maturité, sa large adoption et la simplicité de son API en Python.

---

## 3. Protection des routes contre l'accès anonyme

L'accès aux pages du Backoffice est réservé aux utilisateurs authentifiés. La vérification est centralisée dans un **décorateur** réutilisable, `backoffice/decorators.py` :

```python
from flask import session as flask_session
from functools import wraps
from flask import url_for, redirect

def login_required(fonction):
    @wraps(fonction)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in flask_session:
            return redirect(url_for("login"))
        return fonction(*args, **kwargs)
    return decorated_function
```

Application sur une route :

```python
@app.route("/stock")
@login_required
def stock_page():
    ...
```

**Fonctionnement :** si aucun `user_id` n'est présent en session, la fonction de vue **n'est jamais exécutée** et l'utilisateur est redirigé vers la page de connexion (réponse HTTP 302). La protection est donc appliquée côté serveur, avant tout traitement, et non par simple masquage d'un lien dans l'interface.

**Rôle de `@wraps` :** un décorateur remplace la fonction d'origine par la fonction interne `decorated_function`. Sans `@wraps`, toutes les vues décorées porteraient le même nom interne (`decorated_function`), et Flask — qui identifie ses routes par le nom de la fonction — refuserait d'enregistrer la seconde route décorée. `@wraps(fonction)` recopie le nom et la documentation de la fonction d'origine sur le wrapper, ce qui préserve l'unicité des points d'entrée.

**Choix d'implémentation :** placer cette logique dans un décorateur plutôt que de la répéter au début de chaque vue évite la duplication de code et, surtout, le risque d'oubli sur une route ajoutée ultérieurement. Le décorateur est isolé dans son propre module (`decorators.py`) et importe la session directement depuis Flask, afin d'éviter un import circulaire avec `app.py`.

---

## 4. Rejet des utilisateurs supprimés

La suppression d'un compte est **logique** et non physique : l'administrateur passe la colonne `is_active` à `False`, sans supprimer l'enregistrement.

La condition d'authentification vérifie explicitement ce statut :

```python
if user and user.is_active and bcrypt.checkpw(...):
```

Un compte désactivé ne peut donc plus ouvrir de session, même si le mot de passe saisi est correct. Les enregistrements de stock ne sont en aucun cas affectés : la table `stock` référence des succursales, jamais des utilisateurs.

**Note sur les messages d'erreur :** un identifiant inexistant, un mot de passe incorrect et un compte désactivé produisent tous le même message générique (« Invalid username or password »). Ce choix est délibéré : distinguer ces cas révélerait à un attaquant quels identifiants existent réellement dans le système.

---

## 5. Autorisation basée sur les rôles

### Règles à appliquer

| Rôle | Autorisé | Interdit |
|---|---|---|
| `admin` | Gérer les utilisateurs (lister, créer, modifier, soft-delete, changer mot de passe et succursale) | Toute opération sur le stock |
| `common_user` | Gérer le stock **de sa seule succursale assignée** (ajouter, retirer, consulter, lister) | Gérer les utilisateurs ; opérer sur une autre succursale |

### Principe d'implémentation retenu

L'autorisation est appliquée **dans la logique backend**, jamais uniquement par le masquage d'éléments dans l'interface. Masquer un bouton n'empêche en rien un utilisateur d'appeler directement l'URL correspondante : le contrôle doit donc être effectué côté serveur, à chaque requête.

L'approche suit le même patron que `@login_required` : des décorateurs dédiés vérifient le rôle de l'utilisateur en session avant d'exécuter la vue, et refusent l'accès sinon.

Pour la restriction à la succursale, le principe est de ne **jamais faire confiance à l'identifiant de succursale transmis par le client**. La succursale sur laquelle porte une opération de stock est systématiquement relue depuis la base, à partir du `user_id` en session (`user.branch_id`), et non depuis un champ de formulaire ou un paramètre d'URL — qu'un utilisateur pourrait modifier pour cibler une autre succursale.

### État d'avancement

Cette section décrit la stratégie décidée. L'implémentation des décorateurs de rôle et des contrôles de succursale est **en cours** (phase suivante du développement) et cette documentation sera complétée avec le code correspondant une fois celui-ci écrit et testé.

---

## 6. Récapitulatif des mesures de sécurité en place

| Mesure | Statut |
|---|---|
| Mots de passe hachés avec bcrypt (jamais en clair) | Implémenté et testé |
| Sel aléatoire unique par mot de passe | Fourni automatiquement par `bcrypt.gensalt()` |
| Vérification sans déchiffrement (`checkpw`) | Implémenté et testé |
| Rejet des comptes désactivés à la connexion | Implémenté et testé |
| Messages d'erreur non discriminants à la connexion | Implémenté |
| Session signée par une clé secrète | Implémenté |
| Secrets hors du code source (`.env` + `.gitignore`) | Implémenté |
| Routes protégées contre l'accès anonyme (`@login_required`) | Implémenté et testé |
| Autorisation par rôle appliquée côté backend | En cours |
| Restriction d'un utilisateur standard à sa succursale | En cours |

**Hors périmètre :** conformément au cahier des charges, SSL/TLS n'est pas mis en place pour ce projet. En conditions réelles, il serait indispensable : sans chiffrement du transport, les identifiants et le cookie de session circulent en clair sur le réseau.