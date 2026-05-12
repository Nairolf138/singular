# Diagnostic gouvernance et circuit breaker

Le dashboard expose les paramètres actifs de gouvernance pour aider à comprendre pourquoi une mutation est ralentie, bloquée ou mise en quarantaine. Ces valeurs proviennent de `policy.yaml` et doivent être lues comme des garde-fous, pas comme des objectifs à atteindre.

## Pourquoi le breaker s’ouvre

Le circuit breaker s’ouvre quand trop de violations ou d’échecs de gouvernance sont observés dans une fenêtre courte. Les paramètres concernés sont :

- `autonomy.circuit_breaker_threshold` : nombre de violations nécessaires pour ouvrir le breaker ;
- `autonomy.circuit_breaker_window_seconds` : durée de la fenêtre d’observation ;
- `autonomy.circuit_breaker_cooldown_seconds` : délai pendant lequel le système reste en refroidissement après ouverture ;
- `autonomy.safe_mode` : mode prudent qui force davantage de contrôles ;
- `autonomy.mutation_quota_per_window` : limite de mutations permises par fenêtre.

Une ouverture du breaker signifie généralement qu’une skill tente une action interdite, écrit hors des chemins autorisés, dépasse un quota, échoue de façon répétée ou produit des mutations trop risquées.

## Comment corriger une skill

1. Identifier la skill fautive dans le diagnostic cockpit (`Dernière skill fautive`) et dans les derniers événements de run.
2. Reproduire le scénario avec une mutation minimale ou un run ciblé.
3. Vérifier que la skill respecte les chemins autorisés par `permissions.modifiable_paths` et n’écrit pas dans `permissions.forbidden_paths`.
4. Réduire la portée de la mutation : une seule responsabilité, entrées validées, sorties bornées, pas d’effet de bord implicite.
5. Ajouter ou ajuster les tests qui couvrent l’échec observé.
6. Relancer après correction et surveiller que les violations ne réapparaissent pas pendant la fenêtre du breaker.

## Ajuster les seuils dans `policy.yaml` si nécessaire

Si les diagnostics montrent que les échecs sont maîtrisés et que le breaker est trop sensible pour une charge légitime, ajuster prudemment les clés de la section `autonomy` :

```yaml
autonomy:
  circuit_breaker_threshold: 3
  circuit_breaker_window_seconds: 180.0
  circuit_breaker_cooldown_seconds: 300.0
  safe_mode: false
  mutation_quota_per_window: 25
```

Recommandations :

- augmenter un seul paramètre à la fois ;
- documenter la raison du changement ;
- préférer un petit incrément plutôt qu’un grand saut ;
- revenir au seuil précédent si les violations augmentent ;
- garder `safe_mode` activable rapidement pendant une investigation.

## Pourquoi augmenter les seuils ne doit pas être la première solution

Augmenter les seuils masque souvent le symptôme au lieu de corriger la cause. Si une skill viole la sandbox, écrit dans une zone interdite ou génère des mutations instables, un seuil plus haut lui laisse simplement plus de temps pour produire des dégâts avant l’arrêt automatique.

La bonne séquence est donc : diagnostiquer l’événement, corriger la skill, renforcer les tests, puis seulement ajuster les seuils si le comportement corrigé reste légitime mais trop fréquemment interrompu.
