# Diagrammes PFE DataWatch

Ces sources produisent les figures du rapport PFE. Elles sont volontairement simplifiées pour rester lisibles sur une page A4 et correspondent aux modèles et flux actuellement présents dans le dépôt. Le diagramme de séquence final utilise `sequence-uml.svg`; les autres figures restent régénérables depuis Graphviz.

```bash
for file in docs/diagrams/pfe/*.dot; do dot -Tpng -Gdpi=180 "$file" -o "${file%.dot}.png"; done
```

Les fichiers `*-doc.png` sont les versions optimisées pour Google Docs. Les SVG conservent une source vectorielle éditable.
