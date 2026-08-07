# Bridge ROS2 (optionnel)

Le bridge est **désactivé par défaut** : sa présence ne signifie ni que ROS2, ni
que les interfaces listées, ni qu'un robot sont disponibles. Installez une
distribution ROS2 compatible, sourcez son environnement et installez Singular
avec les extras nécessaires :

```bash
source /opt/ros/$ROS_DISTRO/setup.bash
python -m pip install -e '.[ros2,yaml]'
```

Copiez `configs/ros2_bridge.example.yaml`, remplacez les topics et types par
ceux réellement exposés puis construisez les ports :

```python
from singular.embodiment import build_bridge_ports
from singular.core.agent_runtime import AgentRuntime

ports = build_bridge_ports("configs/my_ros2_bridge.yaml")
runtime = AgentRuntime(perception=ports.perception, mind=my_mind, action=ports.action)
try:
    runtime.step()
finally:
    ports.perception.close()
    ports.action.close()
```

`qos` accepte `depth`, `reliability`, `durability` et `history`. Les délais sont
en secondes. `reconnect` recrée une souscription après une erreur de spin. Les
transformations ne font pas d'`eval` : `fields` associe un champ de destination
à un chemin dans le payload et `constants` ajoute des valeurs littérales.

Une publication peut utiliser un topic d'acquittement dont le message contient
`command_id`. Services et actions attendent leur réponse/résultat réel. Chaque
adaptateur retourne le même `command_id` et place la réponse structurée dans
`Acknowledgement.actual`. L'arrêt d'urgence est verrouillé pour toute la durée
de vie des ports. Il faut recréer le bridge (ou réinitialiser explicitement son
signal après une procédure opérateur) avant de reprendre.

Le manifeste Compose sous `deploy/ros2/` n'est qu'un exemple. Il suppose une
image construite par l'opérateur avec ROS2 et les paquets d'interfaces requis ;
il ne revendique aucun accès matériel et ne monte aucun périphérique par défaut.
