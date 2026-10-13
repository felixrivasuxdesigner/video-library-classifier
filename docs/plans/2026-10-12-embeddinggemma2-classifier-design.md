# Video Library Classifier v0.7.0 — EmbeddingGemma 2 Local Multimodal Engine & Video Moment Finder

**Date:** 2026-10-12  
**Author:** Félix Rivas (Shape Creative Studio)  
**Status:** Validated & Approved

---

## 1. Motivation & Paradigm Shift

In versions `v0.4.0` through `v0.6.1`, `video-library-classifier` relied on extracting static JPEG frames via `extract-frames.py` and asking the conversational LLM (Claude/Gemini) to read hundreds of images sequentially. This caused three bottlenecks:
1. **High token/context cost & latency** when reading 300–1,000+ frames in batches.
2. **Zero audio awareness** — unable to distinguish spoken vows/speeches (`◆ Foundation`) or applause/cheering (`⚡ Ecstasy`) from silent B-roll (`◆ Filler`).
3. **Whole-clip keyword limitation** — long clips (>30s) could only receive whole-clip keywords (`start="0s"`), missing exact intra-clip moments.

By integrating **`google/embeddinggemma-2`** (740M parameters total: 270M Text + 170M Vision + 300M Audio in a unified 768d vector space with Matryoshka Representation Learning), the plugin shifts to **local multimodal zero-shot classification and semantic moment retrieval**.

---

## 2. Target Hardware Optimization (Intel Core i9 Mac)

Designed to run smoothly on **Intel Core i9-9880H (8 cores / 16 threads, AVX2, 16GB RAM, AMD Radeon Pro 5500M 4GB)**:
- **FFmpeg Preprocessing Offload:** Instead of decoding heavy 4K HEVC/H.264 streams inside Python, `ffmpeg` extracts lightweight `384x384` frame snapshots and `16kHz` mono `.wav` audio snippets in parallel (`ThreadPoolExecutor`).
- **Modular Encoder Activation:** Clips without audio (`has_audio: false` or Drone clips) bypass the 300M audio encoder, saving ~40% compute time.
- **CPU / Dynamic INT8 & Matryoshka 256d:** Configures PyTorch/ONNX threads (`torch.set_num_threads(8)`) and truncates output embeddings to **256 dimensions (`float16`)** with L2 normalization for ultra-fast cosine similarity and compact disk storage (`.embeddings_cache.npz`).

---

## 3. Architecture & Data Flow (v0.7.0)

```
[Video Folder]
      │
      ▼
1. ffprobe-metadata.py ──→ _metadata.json
      │
      ▼
2. gemma-classify.py (EmbeddingGemma 2 Local Multimodal Engine)
   ├── Encodes production-type taxonomy anchors (Moments, Energy 1-5, Narrative Value, Tags)
   ├── Extracts lightweight visual windows + 16kHz audio via ffmpeg
   ├── Computes multimodal embeddings (vision + audio fusion)
   ├── Detects intra-clip sub-ranges (`sub_ranges`) on clips > 30s
   ├── Persists `.embeddings_cache.npz` + `.embeddings_index.json` (Matryoshka 256d)
   ├── Emits `_visual_classifications.json`
   └── Optional `--embed-mode=triage`: exports `_visual_manifest.json` ONLY for low-confidence (<0.65) clips
      │
      ▼
3. merge-classifications.py
   ├── Merges metadata + visual classifications + `sub_ranges`
   └── Produces `[Folder]_clasificacion.csv` + `.clasificacion_cache.json`
      │
      ▼
4. fcpxml-generator.py (FCPXML 1.13)
   ├── Emits 6-dimension Keyword Collections
   └── Injects sub-clip `<keyword start="..." duration="..."/>` ranges for long clips & semantic moments
      │
      ▼
5. moment-finder.py (/buscar-momento)
   ├── Natural language query → EmbeddingGemma 2 SearchQuery vector (256d)
   ├── Cosine similarity search against `.embeddings_cache.npz` in <100ms
   └── Outputs matching clips with exact timestamps (`start` / `duration`) and optional FCPXML injection
```

---

## 4. Components Specification

### 4.1 `skills/classify-video-library/references/gemma-classify.py`
- **Inputs:** `--metadata`, `--tipo` (`boda`, `quinceanero`, `corporativo`, `concierto`, `documental`, `viaje`), `--cache`, `--output` (`_visual_classifications.json`), `--embeddings-out` (`.embeddings_cache.npz`), `--embed-mode` (`local|triage|assist`).
- **Multimodal Taxonomy Anchors:** Built from `production-types.md`, with descriptive English/Spanish prompts for:
  - **Moments** per production type (`Prep`, `Ceremony`, `Cocktail`, `Reception`, `Details`, `Drone`, etc.)
  - **Energy (1–5):** `1` Atmospheric through `5` Ecstasy (combining visual motion cues + acoustic intensity)
  - **Narrative Value:** `Foundation` (weighted heavily by spoken-voice audio similarity), `Candid`, `Epic`, `Filler`
  - **Tags:** Curated vocabulary per production type
- **Intra-Clip Windowing (>30s):** Samples temporal windows (every 10–15s) to detect shifts in Moment, Energy, or high-confidence Tags, emitting `sub_ranges: [{"start_sec": ..., "duration_sec": ..., "keyword": ...}]`.

### 4.2 `skills/classify-video-library/references/moment-finder.py` & `commands/buscar-momento.md`
- **Inputs:** `--query "novio llorando en el altar"`, `--embeddings .embeddings_cache.npz`, `--top-k 10`, `--min-score 0.25`, optional `--fcpxml-out` or `--inject-csv`.
- **Behavior:** Encodes natural language query with `EmbeddingGemma 2`, ranks all clip/window embeddings by cosine similarity, returns exact `archivo`, `camara`, `start_sec`, `duration_sec`, `score`, and can export or append a `# 🔍 <query>` Keyword Collection for Final Cut Pro.

### 4.3 Updates to `merge-classifications.py` & `fcpxml-generator.py`
- `merge-classifications.py`: Preserves `sub_ranges` (serialized as JSON string in CSV column `sub_ranges` and stored natively in `.clasificacion_cache.json`) and fixes the energy distribution summary report to support `1..5` integers alongside legacy strings.
- `fcpxml-generator.py`: Reads `sub_ranges` (if present in CSV or cache) and emits sub-clip `<keyword start="{ticks}/30000s" duration="{ticks}/30000s" value="..."/>` elements quantized to frame boundaries, while maintaining 100% backwards compatibility with `v0.3–v0.6.1` CSVs.
