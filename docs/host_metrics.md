# Host metrics payload (`collect_host_metrics`)

Le module `src/singular/sensors/host.py` expose une API unique: `collect_host_metrics()`.

Le payload est **normalisé**: toutes les clés ci-dessous sont toujours présentes.

| Clé | Type | Unité | Plage attendue | Description |
|---|---|---|---|---|
| `cpu_percent` | `float` | `%` | `0.0` à `100.0` | Utilisation CPU globale de l'hôte. |
| `cpu_load_1m` | `float \| None` | load average (sans unité) | `>= 0.0` ou `None` | Charge CPU sur 1 minute (`None` si indisponible). |
| `ram_used_percent` | `float` | `%` | `0.0` à `100.0` | Pourcentage de RAM utilisée. |
| `ram_available_mb` | `float` | MB | `>= 0.0` | RAM disponible en mégaoctets. |
| `disk_used_percent` | `float` | `%` | `0.0` à `100.0` | Pourcentage d'occupation disque sur le volume courant. |
| `disk_free_gb` | `float` | GB | `>= 0.0` | Espace disque libre en gigaoctets. |
| `host_temperature_c` | `float \| None` | °C | `>= 0.0` ou `None` | Température moyenne hôte via capteurs matériels, sinon `None`. |
| `process_cpu_percent` | `float` | `%` | `0.0` à `100.0` | Utilisation CPU du process Singular courant. |
| `process_rss_mb` | `float` | MB | `>= 0.0` | RSS mémoire du process Singular courant. |

## Robustesse et fallback

- Chemin prioritaire: `psutil` si installé.
- Fallback stdlib (sans crash): `os`, `resource`, `shutil`, `time`.
- En cas d'indisponibilité d'une métrique, la fonction renvoie une valeur par défaut sûre (`0.0`) ou `None` pour les champs explicitement optionnels (`cpu_load_1m`, `host_temperature_c`).
