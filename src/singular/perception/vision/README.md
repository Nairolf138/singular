# Vision perception

Pipeline vision compacte qui:

- capture caméra (`CameraCapture`) via OpenCV,
- capture écran (`ScreenCapture`) ou fenêtre active (`ActiveWindowCapture`),
- applique un prétraitement (`FramePreprocessor`: ROI + resize),
- applique une stratégie de sampling (`FrameSamplingStrategy`, défaut `1.5 FPS`),
- extrait des événements (`OcrTextExtractor`, `KeyObjectExtractor`, `UIStateChangeExtractor`),
- émet des `PerceptEvent(event_type="vision")` compacts sans persistance d'images brutes.

## Exemple rapide

```python
from perception.vision import VisionPerceptionPipeline

pipeline = VisionPerceptionPipeline(source="window")
percepts = pipeline.collect()
```

Le payload inclut des métadonnées compactes (`frame_fingerprint`, snippets OCR,
objets clés, indicateur de changement d'état UI), pas les buffers image complets.
