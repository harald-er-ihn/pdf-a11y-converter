# Mathematische Grundlagen des Spatial Matchings

Um Kollisionen von Bounding Boxes sicher aufzulösen, nutzt der SpatialMatcher eine gewichtete Funktion aus Geometrie und semantischer Textähnlichkeit.

## Intersection over Union (IoU)

Die geometrische Überschneidung wird wie folgt definiert:

$$ IoU(A, B) = \frac{Area(A \cap B)}{Area(A \cup B)} $$

## Gewichtete Matching-Funktion

Die finale Gewichtung kombiniert den IoU mit der Levenshtein-Distanz $L(t_1, t_2)$ der erkannten Texte:

$$ Score(E_1, E_2) = \alpha \cdot IoU(E_1, E_2) + \beta \cdot \left( 1 - \frac{L(t_1, t_2)}{\max(|t_1|, |t_2|)} \right) $$

Dabei sind $\alpha = 0.4$ und $\beta = 0.6$ experimentell ermittelte Konstanten für optimale Fallback-Toleranz.
