# Démo : une vie et sa mémoire après redémarrage

Cette démo exécute quatre commandes `singular` dans quatre processus séparés :
naissance, état, premier échange, second échange. Elle vérifie que la vie reste
active, que le premier message figure encore dans `mem/episodic.jsonl` et que son
extrait est retrouvé dans le contexte du second échange.

## Depuis le wheel installé

Installez le wheel v0.1.0 avec Python 3.11 ou plus récent, selon les
[instructions de la release](releases/v0.1.0.md). Depuis un clone du dépôt,
lancez ensuite :

```bash
DEMO_ROOT="$(mktemp -d)"
.venv/bin/python examples/demo_persistent_life.py \
  --root "$DEMO_ROOT" \
  --singular .venv/bin/singular
```

Le script refuse un root qui contient déjà un registre de vies. Il crée un nom
de vie unique et ne supprime pas les données à la fin : le JSON de sortie donne
les chemins de la vie et de son journal pour les inspecter. Le provider `dummy`
est sélectionné par défaut, sans service externe ni clé API.

Extrait du résultat vérifié :

```json
{
  "result": "passed",
  "first_message_persisted": true,
  "retrieved_excerpt": "Je prépare une scène lumineuse avec un phare bleu.",
  "real_llm_response": false,
  "provider": "dummy"
}
```

**Ce que cela prouve :** la persistance du registre, l'écriture des épisodes et
la récupération d'un souvenir dans le contexte d'une nouvelle conversation.
Le provider factice affiche un écho du contexte ; il ne comprend pas la question
et ne démontre pas une réponse intelligente ou une mémoire à long terme fiable.

## Avec un modèle réel, si vous en avez configuré un

Après avoir démarré Ollama et installé un modèle compatible selon le
[guide de configuration](../README.md#préparer-ollama-explicitement), créez un
**autre** root vide et ajoutez `--provider ollama`. Le script échoue si Singular
retombe sur `dummy` ; un résultat `real_llm_response: true` signifie qu'un
modèle réel a répondu, sans juger de la qualité ou de la véracité de sa réponse.
Le même principe s'applique au provider OpenAI déjà configuré, qui envoie les
prompts à son service externe. Les messages de cette démo sont synthétiques.

Le scénario du provider factice est également exécuté dans le job CI de
construction du wheel, hors de la racine du dépôt.
