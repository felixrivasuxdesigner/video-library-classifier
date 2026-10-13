# GEMINI.md - Video Library Classifier Plugin (v0.7.0)

## Project Overview

This repository is the **Single Source of Truth (SSOT)** for the **Video Library Classifier** plugin (`v0.7.0`), compatible with both Claude Code / Cowork (`.claude-plugin`) and Gemini / Antigravity (`skills/`).

It automates the multimodal classification (**Google EmbeddingGemma 2**: Vision + Audio + Text), natural-language moment retrieval (**Video Moment Finder**), audio preparation, and Final Cut Pro organization of professional video libraries (MP4, MOV, MXF) for events such as weddings, quinceañeras, corporate events, concerts, documentaries, and travel productions.

---

## Modular Architecture

```
video-library-classifier/
├── .claude-plugin/
│   └── plugin.json                        # Plugin manifest (v0.7.0)
├── commands/                              # Slash commands
│   ├── clasificar-video.md                # /clasificar-video (EmbeddingGemma 2 + Auto-Triage)
│   ├── buscar-momento.md                  # /buscar-momento (Video Moment Finder)
│   ├── generar-fcpxml.md                  # /generar-fcpxml
│   └── convertir-audio.md                 # /convertir-audio
├── docs/plans/
│   └── 2026-10-12-embeddinggemma2-classifier-design.md
├── tests/
│   └── test_pipeline_v07.py               # Automated test suite
└── skills/                                # Modular skills (symlinked to ~/.gemini/config/skills/)
    ├── classify-video-library/            # Stage 1: Metadata + EmbeddingGemma 2 Multimodal -> CSV
    │   ├── SKILL.md
    │   └── references/
    │       ├── cache-format.md
    │       ├── extract-frames.py          # Legacy / fallback frame extractor
    │       ├── gemma-classify.py          # Local Multimodal Engine (EmbeddingGemma 2)
    │       ├── moment-finder.py           # Natural Language Video Moment Finder
    │       ├── generate-fcpxml.py
    │       ├── merge-classifications.py
    │       ├── processing-script.md
    │       ├── production-types.md
    │       └── visual-classification-prompt.md
    ├── fcpxml-from-classification/        # Stage 2: CSV -> FCPXML 1.13 (6+ dimensions & Sub-Ranges)
    │   ├── SKILL.md
    │   └── references/
    │       ├── fcpxml-generator.py
    │       ├── fcpxml-spec-notes.md
    │       ├── project-templates.md
    │       └── validation-checklist.md
    └── convert-audio/                     # Stage 3: Batch Audio -> Lossless AIFF (PCM 16-bit 44.1kHz)
        └── SKILL.md
```

---

## Data Flow & Pipeline (v0.7.0)

```
[Video Folder]
      │
      ▼
ffprobe-metadata.py ──→ _metadata.json (Technical details + temporal brackets)
                            │
                            ▼
              gemma-classify.py (EmbeddingGemma 2 Local Engine)
              ├── Extracts lightweight 384x384 frames + 16kHz audio via ffmpeg
              ├── Computes 256d Matryoshka vectors (Vision + Audio)
              ├── Saves .embeddings_cache.json ──→ moment-finder.py (/buscar-momento)
              ├── Detects intra-clip sub_ranges on clips >= 30s
              └── Auto-Triage: resolves clear clips locally, escalates <0.65 to LLM
                            │
                            ▼
              merge-classifications.py
                            │
                            ▼
        [Folder]_clasificacion.csv + .clasificacion_cache.json
                            │
                            ▼
              fcpxml-generator.py (FCPXML 1.13)
                            │
                            ▼
         [Event].fcpxml (6+ Keyword Dimensions + Sub-Clip Ranges + Projects)
```

---

## Taxonomy & Dimensions (v0.7.0)

1. **Moment:** Configurable by production type (e.g., Prep, Ceremony, Cocktail, Reception, Details, Drone).
2. **Camera:** Camera 1, Camera 2, Drone, Go Ultra, etc.
3. **Energy Scale (1–5 Descriptive):**
   - `1` — `⚡ Atmospheric` (Static shots, details, architecture)
   - `2` — `⚡ Intimate` (Quiet moments, glances, subtle emotion)
   - `3` — `⚡ Social` (Conversations, greetings, walking)
   - `4` — `⚡ Celebration` (First dance, hugs, toasts, high energy)
   - `5` — `⚡ Ecstasy` (Peak party action, dancefloor, confetti)
4. **Narrative Value Archetypes:**
   - `◆ Foundation` — Speeches, vows, interviews (story backbone — boosted by spoken-voice audio analysis)
   - `◆ Candid` — Spontaneous reactions (highlight gold)
   - `◆ Epic` — High visual impact (drones, wide angles, movement)
   - `◆ Filler` — B-roll without narrative weight
5. **Tags:** Filtered via curated allowlist (`# toast`, `# sunset`, `# first_dance`, etc.), including intra-clip `sub_ranges`.
6. **Semantic Search Moments:** `🔍 <query>` (injected by `/buscar-momento` with exact `start` and `duration`).
7. **Priority:** `★ Priority` (`revisar_prioritario == SI`).

---

## Development Conventions

- **User Interaction Language:** Español (Latino Neutro).
- **Code & Technical Docs:** English / Spanish per skill spec.
- **Golden Rule of Classification:** *"Visual + Audio mata Hora"* — multimodal evidence always overrides timestamp heuristics.
- **FCPXML Invariants:**
  - Always include `start` and `duration` on `<keyword>` elements inside `<asset-clip>` (both whole-clip and sub-clip ranges).
  - Use deterministic `uuid5(NAMESPACE_URL, archivo)` for asset UIDs.
  - Set `hasAudio="0"` and omit `audioRole` on silent/drone clips.
  - Validate output with `ElementTree` before delivery.
- **Incremental Updates:** Leverage `.clasificacion_cache.json` and `.embeddings_cache.json` to avoid re-processing unchanged clips.
