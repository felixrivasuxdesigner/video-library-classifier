---
name: classify-video-library
description: Clasificación profesional de video con IA multimodal local (EmbeddingGemma 2 Visión + Audio, Energía 1-5 descriptiva, Valor Narrativo, Sub-Rangos FCPXML v1.13 y Video Moment Finder).
version: 0.7.0
---

# Video Library Classifier — Skill v0.7.0 (EmbeddingGemma 2 Multimodal)

## Flujo de Trabajo (Workflow)

1. **Extracción de Metadata**: `ffprobe-metadata.py` (Technical probe: resolución, codec, duración, `has_audio`, brackets horarios).
2. **Clasificación Multimodal Local (`gemma-classify.py` — Google EmbeddingGemma 2)**:
   - **Visión + Audio en un mismo espacio vectorial (768d → Matryoshka 256d)**:
     - Evalúa snapshots ligeros (`384x384`) + audio real (`16kHz` mono) contra las anclas semánticas del tipo de producción (`production-types.md`).
     - Optimizado para Mac Intel Core i9 (`8 hilos`, bypass automático del encoder de audio en clips de Drone o sin audio).
   - **Auto-Triage (`--embed-mode=triage|local|assist`)**:
     - Resuelve en local los clips con confianza `>= 0.65` (0 costo de tokens).
     - En modo `triage`, exporta a `_visual_manifest.json` únicamente el mejor keyframe semántico de los clips dudosos para desempate por el LLM.
   - **Detección de Sub-Rangos Intra-Clip (`sub_ranges`)**:
     - En clips largos (`>= 30s`), divide por ventanas temporales y detecta momentos internos (`start_sec`, `duration_sec`, `keyword`) para etiquetado parcial en Final Cut Pro.
   - **Índice Vectorial Local (`.embeddings_cache.json`)**:
     - Guarda los vectores `256d` por ventana para búsquedas instantáneas con `moment-finder.py` (`/buscar-momento`).
3. **Búsqueda Semántica de Momentos (`moment-finder.py` — Opcional / Bajo Demanda)**:
   - Permite buscar cualquier momento en lenguaje natural (ej. `"novio llorando en el altar"`, `"brindis con copas arriba"`) e inyectar los rangos exactos en el CSV bajo `🔍 <consulta>`.
4. **Merge de Datos**: `merge-classifications.py` (combina metadata + clasificación + `sub_ranges` en CSV y actualiza `.clasificacion_cache.json`).
5. **Generación de FCPXML**: `fcpxml-generator.py` / `generate-fcpxml.py` (Versión 1.13).
   - Crea 3 proyectos: Película (30m), Highlight (5m), RRSS (1m).
   - Keyword Collections en 6+ dimensiones: Momento, Cámara, Energía (`⚡`), Valor Narrativo (`◆`), Tags (`#`), Búsquedas (`🔍`) y Prioridad (`★`).
   - Aplica `<keyword start="..." duration="..."/>` tanto a nivel de clip completo como a nivel de **sub-clip** (`sub_ranges`).

## Convenciones de Desarrollo
- Idioma: Español Latino Neutro para interacciones.
- Regla de Oro: *"Visual + Audio mata Hora"* — la evidencia multimodal siempre tiene prioridad sobre el bracket horario.
- Formato: FCPXML 1.13 estricto (uso de `media-rep`, `<keyword>` siempre con `start` y `duration` alineados a frame boundary).
- Ejecución de scripts con dependencias ML: `uv run skills/classify-video-library/references/gemma-classify.py ...` (usa metadatos inline PEP 723).
