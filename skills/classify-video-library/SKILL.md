---
name: classify-video-library
description: Clasificación profesional de video con IA (Energía 1-5 descriptiva, Valor Narrativo y FCPXML v1.13).
version: 0.6.1
---

# Video Library Classifier — Skill v0.6.1

## Flujo de Trabajo (Workflow)

1. **Extracción de Metadata**: `ffprobe-metadata.py` (Technical probe).
2. **Extracción de Frames**: `extract-frames.py` (2-3 frames por clip).
3. **Clasificación Visual Inteligente**:
   - **Regla de Oro**: "Visual mata Hora". El contenido del frame siempre tiene prioridad.
   - **Escala de Energía (1-5)**: 1:Atmosférico, 2:Íntimo, 3:Social, 4:Celebración, 5:Éxtasis.
   - **Valor Narrativo**: Foundation (Discursos), Candid (Emoción real), Epic (Drones/Impacto), Filler (Recurso).
4. **Merge de Datos**: `merge-classifications.py` (ahora incluye `valor_narrativo` en CSV).
5. **Generación de FCPXML**: `generate-fcpxml.py` (Versión 1.13).
   - Crea 3 proyectos: Película (30m), Highlight (5m), RRSS (1m).
   - Keyword Collections en 6 dimensiones: Momento, Cámara, Energía, Narrativo, Tags, Prioridad.

## Convenciones de Desarrollo
- Idioma: Español Latino Neutro para interacciones.
- Formato: FCPXML 1.13 estricto (uso de media-rep, keywords con start+duration).
- Matemática: Frames redondeados * 1001 / 24000s para 23.98 fps.
- Energía en CSV: integer 1-5 (no string).
