# Cache format — `.clasificacion_cache.json`

Archivo JSON que vive al lado del CSV de salida (mismo directorio raíz de la biblioteca de video). Contiene clasificaciones visuales previas para evitar re-procesar clips ya conocidos.

## Esquema

```json
{
  "<signature>": {
    "categoria": "Cóctel",
    "energia": "media",
    "confianza": 0.85,
    "tags": ["interior", "salon", "brindis"],
    "razonamiento": "Personas en mesas alzando copas. Iluminación cálida."
  },
  "<signature>": { ... }
}
```

## Cómo se calcula `signature`

```python
hashlib.sha1(f"{path.resolve()}|{size}|{int(mtime)}".encode()).hexdigest()
```

Cambia si:

- El clip se mueve o renombra (cambia el path)
- El clip se re-importa o reescribe (cambia size/mtime)

No cambia si:

- Solo se modifica el nombre de la carpeta padre (siempre que el path absoluto resuelto siga igual — verificar caso por caso)
- El clip se lee sin tocarlo

> **Trade-off conocido:** mover toda la biblioteca de carpeta invalida el cache completo. Si esto pasa con frecuencia, considerar cambiar a un signature basado en hash del primer/último MB del archivo (más caro pero estable bajo movimiento). Hoy no lo hacemos por simplicidad.

## Ciclo de vida

1. **Primera corrida:** cache no existe → todos los clips se procesan visualmente → cache se llena.
2. **Re-corrida sobre la misma carpeta:** todos los signatures ya están → 0 frames extraídos, 0 imágenes leídas, 0 latencia visual. CSV se regenera desde cache + metadata fresca.
3. **Carpeta con clips nuevos agregados:** solo los nuevos se procesan visualmente. Los viejos vienen del cache. Cache crece.
4. **Forzar reproceso:** `--no-cache` en el comando elimina el cache antes de empezar.

## Borrado manual

El usuario puede borrar el cache cuando quiera con:

```
rm /ruta/biblioteca/.clasificacion_cache.json
```

La próxima corrida re-procesará todo desde cero.

## Tamaño esperado

~300-500 bytes por clip cacheado. Para 1000 clips: ~400 KB. No requiere compresión.
