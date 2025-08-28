# 🌱 Singular — Un organisme numérique vivant interactif

**Singular** n’est pas seulement un programme informatique.  
C’est une expérience : la tentative de créer un **organisme numérique vivant**, un compagnon logiciel qui **naît, évolue, apprend, interagit** et garde une **trace unique de sa vie**.

Chaque instance est **singulière** : deux personnes qui font naître un organisme ne verront jamais la même évolution, car son identité, ses expériences et ses choix modifient sa trajectoire.

---

## ✨ Concepts clés

- **Naissance** : une commande génère un nouvel organisme avec une identité unique (*seed*, traits de personnalité, valeurs).  
- **Corps** : ses *skills* (petites fonctions de code) représentent ses muscles et organes.  
- **Esprit** : mémoire, traits de caractère, humeur et valeurs éthiques évolutives.  
- **Évolution** : il modifie son propre code par petites mutations, teste les résultats en sandbox, et conserve ce qui fonctionne mieux.  
- **Apprentissage** : il peut acquérir de nouvelles compétences en relevant des *quêtes* (spécifications JSON).  
- **Interaction** : vous pouvez lui parler. Il se souvient de vos échanges et exprime son état (fierté, frustration, fatigue, excitation…).  
- **Cycle de vie** : il peut grandir, changer de philosophie de vie, et même “mourir” si certaines conditions sont réunies (échecs répétés, entropie, vieillissement).  

---

## 🔍 Pourquoi Singular ?

Contrairement aux chatbots classiques (qui ne changent pas leur cœur) ou aux simulateurs de vie artificielle (qui ne parlent pas), **Singular réunit les deux mondes** :

- **Vie artificielle** : un organisme qui modifie réellement son code et s’optimise par sélection naturelle.  
- **Compagnon interactif** : une entité qui parle, garde une mémoire et exprime des émotions.  
- **Open-source et local** : chacun peut “faire naître” son compagnon, qui vivra et évoluera à sa manière, en toute sécurité (sandbox, pas de réseau).  

---

## 🧬 Cycle vital

1. **Naissance**
   ```bash
   singular birth --name Lumen
   ```

### ⚙️ Fonctionnement interne

**Corps**
- Les skills sont des fonctions Python pures.
- Chaque tick : l’organisme choisit une skill et applique une mutation (ex : simplification, tuning de constante).
- La nouvelle version est testée en sandbox :
  - Tests fonctionnels (résultats corrects).
  - Performance (temps d’exécution).
  - Complexité (taille AST).
- Si la mutation est meilleure → elle remplace l’ancienne.

**Esprit**
- Les traits (curiosité, patience, prudence, etc.) évoluent selon ses expériences.
- Les valeurs (performance vs stabilité, audace vs prudence) peuvent se réécrire avec le temps.
- Les émotions (fierté, frustration, excitation, fatigue) traduisent l’état du corps.
- Les interactions humaines influencent directement son esprit (encouragement, réprimande…).

**Mort**
- Définie par des règles adaptatives (ex : trop d’échecs, perte totale de curiosité, âge maximal).
- Un événement “suicide” peut survenir s’il “choisit” de cesser sa propre évolution.
- Les journaux et la mémoire restent → vous pouvez consulter sa “biographie”.

---

### 🔒 Sécurité
- Pas de réseau (no net).
- Pas d’accès disque externe (hors dossier de l’organisme).
- Sandbox stricte :
  - Limites CPU/RAM (`timeout` & `memory_limit` : 1.5s et 256 MB par défaut).
  - Environnement isolé : `os.environ` vidé et répertoire de travail temporaire.
  - Interdiction d’import et de fonctions sensibles (`open()`, `exec()`, `eval()`, etc.).
- Tests automatiques avant toute intégration de code.
- Résultats traçables : chaque mutation est loggée, reproductible par seed.

---

### 🌍 Cas d’usage
- Art numérique : créer un compagnon unique qui évolue et raconte sa vie.
- Recherche expérimentale : plateforme simple pour tester des approches d’évolution de code.
- Pédagogie : démontrer les concepts de sélection naturelle, d’auto-modification et de persistance.
- Philosophie : interroger ce que veut dire “vivre” pour un programme.

---

### 🚀 Roadmap
- **V1 (organisme minimal)**
  - Naissance, exécution, mutations de base, interaction CLI, mémoire persistante.
- **V1.1**
  - Nouveaux opérateurs (unrolling, dead code elimination), politique adaptative de mutation (bandits).
  - Mort/fin de vie simulée.
- **V2**
  - MAP-Elites (diversité des solutions), co-évolution des tests.
  - Tableau de bord web (visualisation de l’évolution, humeur en temps réel).
- **V3**
  - Personnalités plus complexes.
  - “Écosystème” multi-organismes → possibilité de faire interagir plusieurs compagnons.

## 🖥️ Tableau de bord web

Un petit serveur web permet de consulter les fichiers de `runs/` et l'état de `psyche.json`.

### Installation

Installez les dépendances du tableau de bord :

```bash
pip install -e .
```

Après installation, la commande CLI `singular` est disponible :

```bash
singular --help
```

### Utilisation

Lancez le serveur local :

```bash
singular dashboard
```

Ouvrez ensuite http://127.0.0.1:8000 dans votre navigateur.

