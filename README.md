# Video Library Classifier

A Claude Code / Cowork plugin for videographers who need to organize large libraries of footage before editing in Final Cut Pro.

## What it does

1. **Classifies video clips** — Combines ffprobe metadata (resolution, codec, duration, creation time) with visual classification via Claude (keyframe analysis) to categorize each clip by moment, energy, narrative value, and custom tags.

2. **Generates FCPXML** — Produces a valid FCPXML 1.13 file ready to import into Final Cut Pro 11/12, with Keyword Collections organized across 6 dimensions: moment, camera, energy (1–5 descriptive scale), narrative value, tags, and priority.

3. **Converts audio** — Batch converts FLAC, M4A, MP3, WAV to AIFF for professional editing workflows.

## Commands

| Command | Description |
|---------|-------------|
| `/clasificar-video` | Classify a video library from a folder of clips |
| `/generar-fcpxml` | Generate FCPXML from a classification CSV |
| `/convertir-audio` | Convert audio files to AIFF |

## Energy Scale (1–5)

| Level | Name | Description |
|-------|------|-------------|
| 1 | Atmospheric | Static shots — objects, architecture, details |
| 2 | Intimate | Quiet moments — hands, whispers, subtle emotion |
| 3 | Social | People interacting — conversations, walking, toasts |
| 4 | Celebration | High energy — dancing, laughing, exits |
| 5 | Ecstasy | Peak action — dancefloor, confetti, sparklers |

## Narrative Value Archetypes

| Value | Use in edit |
|-------|-------------|
| Foundation | Speeches, vows, interviews — story backbone |
| Candid | Spontaneous reactions — highlight gold |
| Epic | Visually stunning — drones, wide angles, movement |
| Filler | B-roll without narrative weight |

## Requirements

- **ffmpeg/ffprobe** installed and in PATH
- A folder of video files (MP4, MOV, MXF, etc.)
- Claude with multimodal capabilities (for visual classification)

## Production types supported

Wedding, Quinceañera, Corporate Event, Concert, Documentary, Travel — with moment brackets configurable per type.

## Installation

Drag the `.plugin` file into Claude, or install from the community directory:

```
/plugin install video-library-classifier
```

## Author

**Shape Creative Studio** — [shapecreative.co](https://shapecreative.co)

## License

MIT
