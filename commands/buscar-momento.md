---
description: Busca momentos específicos dentro de una biblioteca de video usando lenguaje natural con Google EmbeddingGemma 2 (Video Moment Finder) e inyecta los rangos encontrados en el CSV / FCPXML para Final Cut Pro
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion
argument-hint: '[query="novio llorando en el altar"] [carpeta=ruta] [top-k=10] [inject-csv=si|no]'
---

Activate the `classify-video-library` skill in **Video Moment Finder** mode.

Parse arguments from $ARGUMENTS:

- `query=` → descripción en lenguaje natural del momento a buscar (ej. `"novio llorando"`, `"brindis con copas arriba"`, `"fuegos artificiales en la pista"`)
- `carpeta=` → ruta raíz de la biblioteca donde vive `.embeddings_cache.json`
- `top-k=N` → cantidad de resultados a mostrar (default: 10)
- `min-score=F` → similitud coseno mínima (default: 0.22)
- `inject-csv=si|no` → si es `si`, inyecta automáticamente los rangos (`start_sec` + `duration_sec`) en el CSV de clasificación bajo el keyword `🔍 <query>` para llevarlos a Final Cut Pro

Pasos de ejecución:
1. Si falta `query` o `carpeta`, preguntar al usuario con `AskUserQuestion`.
2. Verificar que exista `<carpeta>/.embeddings_cache.json`. Si no existe, indicar que primero debe correrse `/clasificar-video` con `engine=gemma` (o ejecutarlo automáticamente).
3. Ejecutar `uv run skills/classify-video-library/references/moment-finder.py --query "<query>" --embeddings "<carpeta>/.embeddings_cache.json" --top-k <top-k>`.
4. Si el usuario pidió `inject-csv=si` (o confirma querer verlos como Keyword Collection en Final Cut Pro), pasar `--inject-csv "<carpeta>/<evento>_clasificacion.csv"` y regenerar el `.fcpxml` con `fcpxml-generator.py`.
