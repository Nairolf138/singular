# Grammaire des parcours CLI de recette

Les parcours fonctionnels visibles suivent tous la forme `singular [options globales]
<groupe> <action> [arguments]`. Les syntaxes prises en charge sont :

```text
singular [--life VIE] skills list [--life VIE]
singular [--life VIE] quest create SPEC [--life VIE]
singular [--life VIE] quest list [--life VIE]
singular [--life VIE] social interact CIBLE ÉVÉNEMENT [--life VIE]
singular [--life VIE] self-narrative summarize [--long] [--life VIE]
singular [--life VIE] cognition self-observe [--life VIE]
```

`--life` placé sur l'action est prioritaire sur `--life` placé avant le groupe. La
résolution est unique : une vie inconnue produit `Vie introuvable: <nom>` et aucune
commande n'est exécutée. Par exemple, les deux commandes suivantes ciblent Ada :

```console
singular --root ~/.singular --life ada skills list
singular --root ~/.singular skills list --life ada
```

## Migration de l'ancienne quête

`singular quest SPEC` reste temporairement accepté et délègue exactement à
`singular quest create SPEC`, avec un avertissement de migration sur stderr. Les
formes d'inspection deviennent `singular quest create --example` et
`singular quest create --schema`.

