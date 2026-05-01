---
description: Clasifica una biblioteca de video por tipo de producción (con clasificación visual opcional usando Claude + ffmpeg) y genera un CSV enriquecido por momentos del evento
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion, TaskCreate, TaskUpdate, TaskList
argument-hint: '[tipo=boda|quinceanero|corporativo|concierto|documental|viaje] [carpeta=ruta] [timezone=-3] [umbral=180] [visual=on|off] [frames=3] [no-cache]'
---

Activate the `classify-video-library` skill and begin the workflow immediately.

Parse arguments from $ARGUMENTS:

- `tipo=` → tipo de producción (skip preguntar 1a)
- `carpeta=` → ruta raíz de la biblioteca (skip 1b)
- `timezone=` → offset UTC (skip 1c)
- `visual=on|off` → habilita/deshabilita clasificación visual con Claude (default: on)
- `frames=N` → cantidad por defecto de frames a extraer por clip (default: 3, máx 4)
- `umbral=N` → segundos para marcar `revisar_prioritario=SI` (default: 180)
- `no-cache` → ignora cualquier cache previo y reprocesa todo
- `keep-frames` → no borra los JPEGs temporales al final (debug)

Si faltan argumentos críticos, usar AskUserQuestion para los que falten siguiendo el Step 1 del skill. NO preguntar argumentos opcionales (visual, frames, umbral) salvo que el usuario los mencione o la situación lo justifique.

Después ejecutar Steps 2 a 9 del skill en orden:
- Step 4: ffprobe-metadata.py → `_metadata.json`
- Step 5: extract-frames.py → `_frames/` + `_visual_manifest.json` (skip si visual=off)
- Step 6: tú (Claude) lees los frames en lotes y escribís `_visual_classifications.json` (skip si visual=off)
- Step 7: merge-classifications.py → CSV final + cache + cleanup
- Step 8: reporte al usuario

Recordá: la clasificación visual la hacés vos (Claude) leyendo los frames con la herramienta `Read` (multimodal). NO llamar a la API de Anthropic — el modelo es el de la sesión Cowork actual.
