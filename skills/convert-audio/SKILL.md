---
name: convert-audio
description: >
  This skill converts audio files to AIFF format for professional editing workflows
  (Final Cut Pro, Logic Pro, DaVinci Resolve, Pro Tools). Handles FLAC, M4A, MP3,
  WAV, AAC, OGG, and OPUS input formats. Use when the user asks to "convert audio
  to AIFF", "prepare music for FCP", "convert FLAC to AIFF", "convert M4A to AIFF",
  "batch convert music files", or "prepare audio for editing". Also triggers on:
  "convertir audio", "pasar a AIFF", "convertir música", "preparar pistas para edición".
version: 0.4.0
---

# Audio Converter — Skill

## Overview

Converts audio files from any common format (FLAC, M4A, MP3, WAV, AAC, OGG) to AIFF
(PCM 16-bit, 44.1 kHz), the lossless format preferred by Final Cut Pro, Logic Pro,
and other professional NLE/DAW tools. Uses `ffmpeg` for all conversions.

Originals are **never deleted** unless the user explicitly requests it.

---

## Step 1 — Identify the audio folder

If the user provided a path, use it. Otherwise:
- Check if the current workspace has an `Audios/` or `Music/` subfolder
- List contents and propose it as default

Ask only if genuinely ambiguous:
> _"¿En qué carpeta están los archivos de audio? Por ejemplo: `/Users/you/Project/Audios/Music`"_

---

## Step 2 — Scan for convertible files

Run a scan for supported input formats:

```bash
find "[AUDIO_FOLDER]" -maxdepth 2 \
  -iname "*.flac" -o -iname "*.m4a" -o -iname "*.mp3" \
  -o -iname "*.wav" -o -iname "*.aac" -o -iname "*.ogg" -o -iname "*.opus" \
  | sort
```

**Skip files that already have a matching `.aiff` sibling** (same base name) — they were
already converted. Report how many were skipped.

Report the scan results before converting:
```
Archivos encontrados para convertir:
  FLAC: X archivos
  M4A:  X archivos
  Ya convertidos (se omitirán): X archivos
  ─────────────────────────────
  Total a convertir: X archivos
```

If nothing to convert, tell the user and stop.

---

## Step 3 — Convert

Use ffmpeg with these parameters (lossless PCM, compatible con FCP):

```bash
ffmpeg -i "[INPUT]" -c:a pcm_s16be -ar 44100 "[OUTPUT_BASENAME].aiff" -y -loglevel error
```

**Output naming rule:** Same base filename as input, same folder, `.aiff` extension.

Process all files in a single loop. Show a progress line per file:
```
Convirtiendo: [filename] → ✓
```

If ffmpeg fails on a specific file, log the error and continue with the rest.

---

## Step 4 — Report results

```
✓ Conversión completada
  Convertidos: X archivos
  Omitidos (ya existían): X archivos
  Errores: X archivos  ← list them if > 0

  Archivos AIFF generados:
    [nombre.aiff] — [tamaño MB]
    ...
```

---

## Step 5 — FCP import recommendation

> **Para Final Cut Pro:**
> - Importa los AIFF en un **Evento separado** (ej: "🎵 Music") dentro de la librería del proyecto
> - Al importar, selecciona **"Leave files in place"** para no duplicar almacenamiento
> - Asigna el rol de audio **Music** a cada clip — facilita el mix y exportación con stems

---

## Important behaviors

- **Never delete originals** unless the user explicitly says so
- **Incremental:** Always check for existing `.aiff` before converting
- **Formats supported:** `.flac`, `.m4a`, `.mp3`, `.wav`, `.aac`, `.ogg`, `.opus`
- **Output always:** `.aiff` — PCM 16-bit signed big-endian, 44.1 kHz
- **ffmpeg required:** Verify with `ffmpeg -version` before starting
- **WAV files from Logic Pro / DAW:** No es necesario convertirlos — WAV es PCM nativo, compatible directo con FCP
