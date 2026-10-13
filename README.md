# Video Library Classifier (v0.7.0)

A Claude Code / Cowork and Gemini / Antigravity plugin for videographers who need to organize large libraries of footage before editing in Final Cut Pro.

## What's New in v0.7.0 — Google EmbeddingGemma 2 & Video Moment Finder

- **Local Multimodal Classification (`gemma-classify.py`)** — Powered by `google/embeddinggemma-2` (Vision + Audio + Text in a unified vector space). Classifies clips locally with near-zero LLM token cost while listening to the actual audio track (accurately distinguishing spoken vows/speeches `◆ Foundation` from ambient B-roll `◆ Filler`).
- **Intel Core i9 & Apple Silicon Optimized** — Offloads 4K video decoding to parallel `ffmpeg` (`384x384` snapshots + `16kHz` mono WAV snippets), skips the audio encoder on silent/Drone clips (~40% faster), and stores compact **Matryoshka 256d** vectors in `.embeddings_cache.json`.
- **Video Moment Finder (`/buscar-momento`)** — Search for specific moments across your entire video library using natural language (e.g., `"novio llorando en el altar"`, `"brindis con copas arriba"`) in `<100ms` and inject exact sub-clip ranges (`start` + `duration`) straight into Final Cut Pro as `🔍 <query>` Keyword Collections.
- **Intra-Clip Sub-Ranges in FCPXML 1.13** — Clips longer than 30 seconds automatically receive frame-accurate sub-clip `<keyword start="..." duration="..."/>` ranges when the action or audio shifts.

## Commands

| Command             | Description                                                                 |
| ------------------- | --------------------------------------------------------------------------- |
| `/clasificar-video` | Classify a video library using EmbeddingGemma 2 (with optional LLM triage)  |
| `/buscar-momento`   | Search for exact moments in natural language & inject sub-ranges into FCP   |
| `/generar-fcpxml`   | Generate FCPXML 1.13 from a classification CSV                              |
| `/convertir-audio`  | Batch convert FLAC, M4A, MP3, WAV audio files to lossless AIFF              |

## Energy Scale (1–5)

| Level | Name        | Description                                         |
| ----- | ----------- | --------------------------------------------------- |
| 1     | Atmospheric | Static shots — objects, architecture, details       |
| 2     | Intimate    | Quiet moments — hands, whispers, subtle emotion     |
| 3     | Social      | People interacting — conversations, walking, toasts |
| 4     | Celebration | High energy — dancing, laughing, exits              |
| 5     | Ecstasy     | Peak action — dancefloor, confetti, sparklers       |

## Narrative Value Archetypes

| Value      | Use in edit                                       |
| ---------- | ------------------------------------------------- |
| Foundation | Speeches, vows, interviews — story backbone       |
| Candid     | Spontaneous reactions — highlight gold            |
| Epic       | Visually stunning — drones, wide angles, movement |
| Filler     | B-roll without narrative weight                   |

## Requirements

- **ffmpeg/ffprobe** installed and in PATH
- **uv** (recommended) or Python 3.10+ for running `gemma-classify.py` and `moment-finder.py` (dependencies are declared inline via PEP 723)
- A folder of video files (MP4, MOV, MXF, etc.)

## Production types supported

Wedding, Quinceañera, Corporate Event, Concert, Documentary, Travel — with moment brackets and multimodal semantic vocabularies configurable per type.

## Author

**Félix Rivas** — [shapecreativestudio.com](https://shapecreativestudio.com)

## License

MIT
