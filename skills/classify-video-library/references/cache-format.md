# Cache Formats — `.clasificacion_cache.json` & `.embeddings_cache.json` (v0.7.0)

Ambos archivos viven al lado del CSV de salida (mismo directorio raíz de la biblioteca de video). Evitan re-procesar clips ya conocidos y habilitan búsquedas instantáneas con **Video Moment Finder** (`moment-finder.py`).

---

## 1. `.clasificacion_cache.json`

Contiene las clasificaciones multimodales finales por clip (incluyendo `sub_ranges` detectados en clips largos).

```json
{
  "<signature>": {
    "categoria": "Reception",
    "energia": 4,
    "valor_narrativo": "Foundation",
    "confianza": 0.91,
    "tags": ["toast", "speech", "bride"],
    "sub_ranges": [
      {"start_sec": 12.0, "duration_sec": 18.0, "keyword": "# toast"}
    ],
    "razonamiento": "EmbeddingGemma 2 (con análisis de audio+visión): Reception · E4 · Foundation"
  }
}
```

---

## 2. `.embeddings_cache.json` (Nuevo en v0.7.0)

Almacena los vectores multimodales truncados con **Matryoshka Representation Learning (MRL 256d)** y normalizados L2 por ventana temporal de cada clip.

```json
{
  "model": "google/embeddinggemma-2",
  "mrl_dim": 256,
  "count": 420,
  "windows": [
    {
      "signature": "a1b2c3d4...",
      "archivo": "C002.MP4",
      "camara": "Camera 2",
      "start_sec": 15.0,
      "duration_sec": 10.0,
      "embedding": [0.0412, -0.0891, ...]
    }
  ]
}
```

### Cómo se calcula `signature`

```python
hashlib.sha1(f"{path.resolve()}|{size}|{int(mtime)}".encode()).hexdigest()
```

### Ciclo de vida

1. **Primera corrida:** ambos caches se crean desde cero.
2. **Re-corrida o clips nuevos:** `gemma-classify.py` salta cualquier `signature` que ya esté en `.clasificacion_cache.json` y conserva sus vectores en `.embeddings_cache.json`.
3. **Consultas `/buscar-momento`:** `moment-finder.py` lee `.embeddings_cache.json` en `<100ms` sin tocar los archivos de video ni invocar `ffmpeg`.
