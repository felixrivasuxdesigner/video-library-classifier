---
description: Clasifica una biblioteca de video por tipo de producción usando Google EmbeddingGemma 2 en local (visión + audio + sub-rangos) o fallback LLM por frames, generando CSV enriquecido e índice para Video Moment Finder
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion, TaskCreate, TaskUpdate, TaskList
argument-hint: '[tipo=boda|quinceanero|corporativo|concierto|documental|viaje] [carpeta=ruta] [timezone=-3] [umbral=180] [engine=gemma|triage|llm-frames] [no-cache]'
---

Activate the `classify-video-library` skill and begin the workflow immediately.

Parse arguments from $ARGUMENTS:

- `tipo=` → tipo de producción (skip preguntar 1a)
- `carpeta=` → ruta raíz de la biblioteca (skip 1b)
- `timezone=` → offset UTC (skip 1c)
- `engine=gemma|triage|llm-frames` → motor de clasificación:
  - `triage` (default): `gemma-classify.py` (`google/embeddinggemma-2` multimodal local) clasifica directo todos los clips claros y solo escala a revisión por LLM los clips con confianza `< 0.65` o prioritarios.
  - `gemma`: 100% local con `EmbeddingGemma 2` (0 tokens de LLM).
  - `llm-frames`: modo clásico (`extract-frames.py` + lectura de JPEGs con `Read`).
- `umbral=N` → segundos para marcar `revisar_prioritario=SI` (default: 180)
- `no-cache` → ignora cualquier cache previo y reprocesa todo

Si faltan argumentos críticos (`tipo`, `carpeta`), usar `AskUserQuestion`.

Después ejecutar el pipeline en orden:
1. **Metadata técnica**: `ffprobe-metadata.py` → `_metadata.json`
2. **Clasificación Multimodal Local (EmbeddingGemma 2)**:
   - Ejecutar `uv run skills/classify-video-library/references/gemma-classify.py --metadata _metadata.json --tipo <tipo> --output _visual_classifications.json --cache .clasificacion_cache.json --embeddings-cache .embeddings_cache.json --embed-mode <local|triage> --manifest-out _visual_manifest.json`
   - Si `engine=triage` y `_visual_manifest.json` tiene clips dudosos escalados, revisar únicamente esos keyframes con `Read` y actualizar sus entradas en `_visual_classifications.json`.
   - Si el entorno no puede ejecutar `EmbeddingGemma 2` o `engine=llm-frames`, caer a `extract-frames.py` + lectura por lotes.
3. **Fusión y Cache**: `merge-classifications.py` → CSV final + `.clasificacion_cache.json`
4. **Reporte al usuario**: mostrar distribución por momento, energía (1–5), sub-rangos intra-clip detectados y disponibilidad de `/buscar-momento`.
