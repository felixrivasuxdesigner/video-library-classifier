#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "sentence-transformers[image,audio,video]>=3.3.0",
#   "transformers>=4.48.0",
#   "torch>=2.4.0",
#   "numpy>=1.26.0",
#   "pillow>=10.0.0",
# ]
# ///
"""
Local Multimodal Video Library Classifier powered by Google EmbeddingGemma 2
(`google/embeddinggemma-2`).

Replaces manual frame-by-frame LLM reading with local zero-shot multimodal
(Vision + Audio + Text) classification and semantic indexing.

Optimized for Intel Core i9 Macs (8 cores / 16 threads, AVX2) & Apple Silicon:
1. Offloads 4K video decoding to `ffmpeg` in parallel (extracts 384x384 frames
   + 16kHz mono WAV audio chunks).
2. Skips the 300M audio encoder automatically on silent/Drone clips (~40% speedup).
3. Uses Matryoshka Representation Learning (MRL) to truncate 768d vectors to
   256d L2-normalized vectors for fast cosine similarity & compact caching.
4. Detects intra-clip sub-ranges (`sub_ranges`) on clips >= 30s for frame-accurate
   FCPXML `<keyword start="..." duration="..."/>` tagging.

Usage:
    uv run gemma-classify.py \\
        --metadata /path/_metadata.json \\
        --tipo boda \\
        --output /path/_visual_classifications.json \\
        --cache /path/.clasificacion_cache.json \\
        --embeddings-cache /path/.embeddings_cache.json \\
        [--embed-mode local|triage|assist] \\
        [--triage-threshold 0.65] \\
        [--mrl-dim 256]
"""
from __future__ import annotations
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# Hardware thread tuning for Intel Core i9 (8 physical cores)
os.environ.setdefault("OMP_NUM_THREADS", "8")
os.environ.setdefault("MKL_NUM_THREADS", "8")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "8")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


# ---------------------------------------------------------------------------
# Vector Math Helpers (Pure Python + optional NumPy acceleration)
# ---------------------------------------------------------------------------

def truncate_and_normalize(
    vectors: list[list[float]] | Any,
    mrl_dim: int = 256,
) -> list[list[float]]:
    """
    Applies Matryoshka Representation Learning (MRL) truncation to `mrl_dim`
    dimensions followed by L2 normalization. Returns a list of float lists
    rounded to 6 decimals (compatible with both stdlib JSON and NumPy).
    """
    if hasattr(vectors, "tolist"):
        vectors = vectors.tolist()

    out: list[list[float]] = []
    for vec in vectors:
        sliced = [float(x) for x in vec[:mrl_dim]]
        norm = math.sqrt(sum(x * x for x in sliced))
        if norm > 1e-12:
            sliced = [round(x / norm, 6) for x in sliced]
        else:
            sliced = [0.0 for _ in sliced]
        out.append(sliced)
    return out


def cosine_sim(v1: list[float], v2: list[float]) -> float:
    """Dot product of two L2-normalized vectors."""
    n = min(len(v1), len(v2))
    return sum(v1[i] * v2[i] for i in range(n))


def average_vectors(vecs: list[list[float]]) -> list[float]:
    """Computes the L2-normalized mean of multiple vectors."""
    if not vecs:
        return []
    dim = len(vecs[0])
    mean = [0.0] * dim
    for v in vecs:
        for i in range(dim):
            mean[i] += v[i]
    norm = math.sqrt(sum(x * x for x in mean))
    if norm > 1e-12:
        return [round(x / norm, 6) for x in mean]
    return mean


# ---------------------------------------------------------------------------
# Production Type Taxonomies & Semantic Anchors
# ---------------------------------------------------------------------------

TAXONOMY_BY_TYPE: dict[str, dict[str, Any]] = {
    "boda": {
        "moments": {
            "Prep": "Wedding preparation, bride getting ready, makeup, hair styling, putting on wedding dress or groom suit in a room",
            "Ceremony": "Wedding ceremony at church or altar, bride and groom exchanging vows and rings, priest officiating, guests seated in pews",
            "Cocktail": "Outdoor or indoor cocktail hour, guests mingling, holding drinks, chatting casually, daytime or golden hour social gathering",
            "Reception": "Wedding reception dinner and party at night, banquet tables, first dance, dancefloor with lights, guests dancing and celebrating",
            "Details": "Close-up static detail shot of wedding rings, flower bouquet, hanging dress, cake, table decor, architecture, no people moving",
            "Drone": "Aerial drone view from high above, landscape, roof of venue, church exterior from the sky, wide bird-eye perspective",
        },
        "tags": {
            "bride": "Bride in white wedding dress, veil, bridal portrait",
            "groom": "Groom in suit or tuxedo, boutonnière",
            "parents": "Older parents of the bride or groom hugging, emotional family moment",
            "rings": "Close up of wedding rings, exchanging rings on fingers",
            "dress": "Wedding dress hanging or bride wearing white gown",
            "altar": "Ceremony altar, church sanctuary, wedding arch with flowers",
            "church": "Inside or outside a church, cathedral, religious ceremony",
            "venue": "Event venue, banquet hall, decorated garden tent",
            "dancefloor": "Crowded dancefloor with party lights, people dancing",
            "table": "Banquet dinner table with glasses, plates, centerpieces",
            "cake": "Wedding cake, cutting the cake",
            "bouquet": "Bridal flower bouquet, throwing the bouquet",
            "entrance": "Grand entrance of the bride or couple walking down the aisle or into reception",
            "first_dance": "Bride and groom slow dancing together in the center of the room",
            "speech": "Person speaking into a microphone giving a speech or reading vows",
            "toast": "Raising champagne glasses for a wedding toast, clinking glasses, brindis",
            "sunset": "Golden hour warm sunset light outdoors, orange sky",
            "kids": "Children or flower girls running, playing, or walking at the wedding",
        },
    },
    "quinceanero": {
        "moments": {
            "Prep": "Quinceanera preparation, makeup, tiara, putting on formal ballgown dress",
            "Entrance": "Formal entrance of the quinceanera and family walking into the hall",
            "Waltz": "Choreographed waltz dance in the center of the ballroom with father or court of honor",
            "Party": "High energy party on dancefloor with DJ lights, crowd dancing, cotillon",
            "Details": "Static close-up of dress details, tiara, cake, decorations, rings",
            "Drone": "Aerial drone shot from above of venue or exterior landscape",
        },
        "tags": {
            "dress": "Quinceanera ballgown dress",
            "dance": "Choreographed dance or party dancing",
            "speech": "Family member speaking into microphone giving a speech",
            "toast": "Raising glasses for a toast",
            "cake": "Birthday quinceanera cake",
            "parents": "Parents hugging the quinceanera",
            "dancefloor": "Crowded dancefloor with colorful party lights",
        },
    },
    "corporativo": {
        "moments": {
            "Setup": "Empty conference room, technical audio visual setup, banners and stage preparation",
            "Opening": "Attendees arriving at registration desk, welcome coffee, people entering auditorium",
            "Keynote": "Main speaker on stage presenting with large presentation screen and microphone",
            "Sessions": "Breakout workshop session, panel discussion, audience listening and taking notes",
            "Networking": "Professionals talking in groups with badges, coffee break, cocktails and conversation",
            "Closing": "Closing applause, group photo on stage, farewell drinks",
            "Details": "Close-up of company branding, logos, lanyards, stage details, food platters",
            "Drone": "Aerial drone shot of corporate building, convention center, city skyline",
        },
        "tags": {
            "speech": "Speaker presenting with microphone on stage or podium",
            "venue": "Conference hall, auditorium, modern office",
            "table": "Meeting table or catering table",
            "toast": "Corporate networking toast with drinks",
        },
    },
    "concierto": {
        "moments": {
            "Soundcheck": "Musicians on stage during daytime or empty venue testing instruments and soundcheck",
            "Opening": "Crowd entering the venue, warm-up act, stage lights dimming",
            "Show": "Main live concert performance, band playing under bright stage lights, energetic singing",
            "Closing": "Band taking a final bow on stage, confetti, crowd cheering at the end of the concert",
            "Backstage": "Behind the scenes backstage, artists preparing before going on stage",
            "Audience": "Crowd of fans singing along, clapping, hands in the air, audience reaction",
            "Drone": "Aerial drone shot over concert stage, stadium, or festival crowd",
        },
        "tags": {
            "dance": "Crowd jumping and dancing to live music",
            "speech": "Singer talking to the audience between songs into the microphone",
            "venue": "Concert stage, arena, festival grounds",
        },
    },
    "documental": {
        "moments": {
            "Interview": "Talking head interview, person speaking directly to camera or off-camera interviewer with clear voice audio",
            "B-roll": "Observational footage of daily activities, hands working, candid contextual visuals",
            "Location": "Wide establishing shot of environment, street, building, natural landscape",
            "Character": "Portrait or tracking shot following the main subject in action",
            "Action": "Dynamic sequence of events, physical movement, work or conflict happening",
            "Detail": "Close-up macro shot of objects, textures, tools, documents",
            "Drone": "High aerial drone shot over landscape, city, or territory",
        },
        "tags": {
            "speech": "Spoken interview voice, monologue, dialogue",
            "sunset": "Golden hour sunset lighting over location",
            "aerial": "Aerial perspective from drone",
        },
    },
    "viaje": {
        "moments": {
            "Arrival": "Airport, train station, car journey, arriving at destination or hotel",
            "Exploration": "Walking through streets, markets, trails, exploring a new place",
            "Food": "Local gastronomy, restaurant table, street food, cooking and eating",
            "Location": "Iconic landmark, scenic landscape, beach, mountains, architecture",
            "Characters": "Travel companions, locals, portraits and interactions",
            "Detail": "Close-up of local crafts, signs, textures, coffee cup, small details",
            "Drone": "Sweeping aerial drone view of coastline, mountains, or city",
        },
        "tags": {
            "beach": "Ocean coast, waves, sandy beach",
            "sunset": "Sunset or sunrise over travel landscape",
            "aerial": "Aerial drone view",
            "table": "Food and drinks on a restaurant table",
        },
    },
}
# Alias wedding -> boda
TAXONOMY_BY_TYPE["wedding"] = TAXONOMY_BY_TYPE["boda"]

ENERGY_ANCHOR_TEXTS: dict[int, str] = {
    1: "1 Atmospheric: completely static shot of inanimate objects, flowers, rings, empty architecture, silent ambient room, calm and still",
    2: "2 Intimate: quiet emotional moment, gentle whispers, holding hands, subtle tears, soft slow preparation, tender closeness",
    3: "3 Social: moderate energy, guests chatting politely, walking at normal pace, seated conversation, casual gathering",
    4: "4 Celebration: high energy celebration, loud laughter, couple first dance, enthusiastic applause, big hugs, cheering ceremony exit, brindis",
    5: "5 Ecstasy: maximum party action, crowded dancefloor jumping, screaming, loud music, confetti, sparklers, wild unbridled euphoria",
}

NARRATIVE_ANCHOR_TEXTS: dict[str, str] = {
    "Foundation": "Foundation narrative backbone: person speaking clearly into a microphone, reading wedding vows, formal speech, toast monologue, interview with clear spoken voice",
    "Candid": "Candid emotional reaction: spontaneous genuine laughter, crying tears of joy, surprised face, unposed emotional hug, tearful reaction",
    "Epic": "Epic cinematic visual impact: sweeping aerial drone shot, dramatic wide angle composition, sunset silhouette, grand camera movement",
    "Filler": "Filler B-roll background: people walking by, guests eating at tables, general crowd background without specific main action",
}


def build_taxonomy_anchors(
    tipo: str,
    embedder: Any,
    mrl_dim: int = 256,
) -> dict[str, Any]:
    """
    Pre-computes MRL-truncated L2-normalized anchor vectors for Moments,
    Energy (1-5), Narrative Value, and Tags in a single batched pass.
    """
    tax = TAXONOMY_BY_TYPE.get(tipo.lower(), TAXONOMY_BY_TYPE["boda"])

    moment_names = list(tax["moments"].keys())
    moment_prompts = [tax["moments"][k] for k in moment_names]

    energy_levels = [1, 2, 3, 4, 5]
    energy_prompts = [ENERGY_ANCHOR_TEXTS[k] for k in energy_levels]

    narrative_names = list(NARRATIVE_ANCHOR_TEXTS.keys())
    narrative_prompts = [NARRATIVE_ANCHOR_TEXTS[k] for k in narrative_names]

    tag_names = list(tax["tags"].keys())
    tag_prompts = [tax["tags"][k] for k in tag_names]

    all_prompts = moment_prompts + energy_prompts + narrative_prompts + tag_prompts
    all_vecs = truncate_and_normalize(
        embedder.encode_text(all_prompts, prompt_name="Classification"),
        mrl_dim=mrl_dim,
    )

    i0 = len(moment_prompts)
    i1 = i0 + len(energy_prompts)
    i2 = i1 + len(narrative_prompts)

    moment_vecs = all_vecs[:i0]
    energy_vecs = all_vecs[i0:i1]
    narrative_vecs = all_vecs[i1:i2]
    tag_vecs = all_vecs[i2:]

    return {
        "moments": dict(zip(moment_names, moment_vecs)),
        "energy": dict(zip(energy_levels, energy_vecs)),
        "narrative": dict(zip(narrative_names, narrative_vecs)),
        "tags": dict(zip(tag_names, tag_vecs)),
    }


# ---------------------------------------------------------------------------
# EmbeddingGemma 2 Runtime Wrapper
# ---------------------------------------------------------------------------

class GemmaMultimodalEmbedder:
    """
    Runs `EmbeddingGemma 2` locally.
    Primary backend on macOS (especially Intel Core i9 x86_64):
      `gemma-onnx-worker.mjs` using `onnx-community/embeddinggemma-2-ONNX` (Q4)
      via native C++ `onnxruntime-node` (AVX2 / CoreML).
    Fallback backend:
      `sentence-transformers` (`google/embeddinggemma-2`).
    """
    TASK_PREFIXES = {
        "Classification": "task: classification | query: ",
        "SearchQuery": "task: search result | query: ",
        "Document": "title: none | text: ",
    }

    def __init__(
        self,
        model_id: str = "google/embeddinggemma-2",
        device: str | None = None,
        quantize_int8: bool = False,
        backend: str = "auto",
    ):
        self.model_id = model_id
        self.worker_mjs = Path(__file__).resolve().parent / "gemma-onnx-worker.mjs"
        node_modules = Path(__file__).resolve().parent / "node_modules"

        if backend == "auto":
            if self.worker_mjs.exists() and node_modules.exists():
                self.backend = "onnx-node"
            else:
                self.backend = "torch"
        else:
            self.backend = backend

        if self.backend == "onnx-node":
            print(
                f"[gemma] Motor activo: ONNX Runtime Q4 nativo ({self.worker_mjs.name})",
                file=sys.stderr,
            )
            self.model = None
            return

        import torch
        from sentence_transformers import SentenceTransformer

        torch.set_num_threads(min(8, os.cpu_count() or 4))
        if device is None:
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
            elif torch.cuda.is_available():
                device = "cuda"
            else:
                device = "cpu"

        self.device = device
        print(
            f"[gemma] Cargando {model_id} en dispositivo '{device}' "
            f"(threads={torch.get_num_threads()})...",
            file=sys.stderr,
        )
        self.model = SentenceTransformer(model_id, device=device)

        if quantize_int8 and device == "cpu":
            try:
                self.model = torch.ao.quantization.quantize_dynamic(
                    self.model, {torch.nn.Linear}, dtype=torch.qint8
                )
                print("[gemma] Cuantización dinámica INT8 activada en CPU", file=sys.stderr)
            except Exception as exc:
                print(f"[warn] No se pudo aplicar INT8 dinámico: {exc}", file=sys.stderr)

    def _run_onnx_worker(
        self,
        texts: list[str] | None = None,
        windows: list[dict[str, Any]] | None = None,
        text_only: bool = False,
    ) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="gemma_ipc_") as tmpdir:
            req_path = Path(tmpdir) / "req.json"
            res_path = Path(tmpdir) / "res.json"
            req_path.write_text(
                json.dumps({"texts": texts or [], "windows": windows or []}),
                encoding="utf-8",
            )
            cmd = [
                "node",
                str(self.worker_mjs),
                "--input", str(req_path),
                "--output", str(res_path),
            ]
            if text_only and not windows:
                cmd.append("--text-only")
            subprocess.run(cmd, check=True)
            return json.loads(res_path.read_text(encoding="utf-8"))

    def encode_text(
        self, texts: list[str], prompt_name: str = "Classification"
    ) -> list[list[float]]:
        prefix = self.TASK_PREFIXES.get(prompt_name, "")
        prefixed = [
            t if t.startswith("task: ") or t.startswith("title: ") else f"{prefix}{t}"
            for t in texts
        ]
        if self.backend == "onnx-node":
            res = self._run_onnx_worker(texts=prefixed, text_only=True)
            return res.get("text_embeddings", [])

        try:
            vecs = self.model.encode(
                texts,
                prompt_name=prompt_name,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except TypeError:
            vecs = self.model.encode(
                prefixed,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        return vecs.tolist()

    def encode_windows_batch(
        self, windows_req: list[dict[str, Any]]
    ) -> dict[str, list[float]]:
        """
        Encodes a batch of `{id, frame_path, audio_path}` items in a single pass.
        """
        if not windows_req:
            return {}
        if self.backend == "onnx-node":
            res = self._run_onnx_worker(windows=windows_req, text_only=False)
            return res.get("window_embeddings", {})

        out: dict[str, list[float]] = {}
        for w in windows_req:
            out[w["id"]] = self.encode_window(
                Path(w["frame_path"]) if w.get("frame_path") else None,
                Path(w["audio_path"]) if w.get("audio_path") else None,
            )
        return out

    def encode_window(
        self,
        frame_path: Path | None,
        audio_path: Path | None,
        hint: str = "",
    ) -> list[float]:
        if self.backend == "onnx-node":
            res = self.encode_windows_batch([{
                "id": "single",
                "frame_path": str(frame_path) if frame_path else None,
                "audio_path": str(audio_path) if audio_path else None,
            }])
            return res.get("single", [0.0] * 768)

        inputs: list[Any] = []
        if frame_path and frame_path.exists():
            inputs.append({"image": str(frame_path)})
        if audio_path and audio_path.exists():
            inputs.append({"audio": str(audio_path)})

        if not inputs:
            if hint:
                return self.encode_text([hint])[0]
            return [0.0] * 768

        try:
            vecs = self.model.encode(
                inputs,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            v_list = vecs.tolist()
            if len(v_list) == 2:
                dim = len(v_list[0])
                fused = [0.65 * v_list[0][i] + 0.35 * v_list[1][i] for i in range(dim)]
                return fused
            return v_list[0]
        except Exception as exc:
            if len(inputs) > 1 and frame_path and frame_path.exists():
                vecs = self.model.encode(
                    [{"image": str(frame_path)}],
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )
                return vecs.tolist()[0]
            raise RuntimeError(f"Error codificando ventana multimodal: {exc}") from exc


# ---------------------------------------------------------------------------
# FFmpeg Window Extraction (384x384 Frame + 16kHz Mono Audio)
# ---------------------------------------------------------------------------

def compute_window_schedule(
    duration: float,
    subrange_min_duration: float = 30.0,
    window_sec: float = 12.0,
) -> list[tuple[float, float]]:
    """
    Returns a list of (start_sec, duration_sec) windows for a clip.
    - Short clips (<5s): 1 window covering the whole clip
    - Medium clips (5..30s): 2 windows
    - Long clips (>= subrange_min_duration): sliding windows of ~window_sec
      (capped at 12 windows max so a 10-minute clip doesn't stall the CPU).
    """
    if duration <= 0:
        return [(0.0, 1.0)]
    if duration < 5.0:
        return [(0.0, round(duration, 2))]
    if duration < subrange_min_duration:
        half = round(duration / 2.0, 2)
        return [(0.0, half), (half, round(duration - half, 2))]

    num_windows = min(12, max(3, int(math.ceil(duration / window_sec))))
    step = duration / num_windows
    schedule: list[tuple[float, float]] = []
    for i in range(num_windows):
        st = round(i * step, 2)
        dur = round(min(step, duration - st), 2)
        if dur > 0.2:
            schedule.append((st, dur))
    return schedule


def extract_window_media(
    video_path: Path,
    start_sec: float,
    duration_sec: float,
    out_dir: Path,
    prefix: str,
    extract_audio: bool = True,
    frame_size: int = 384,
) -> tuple[Path | None, Path | None]:
    """
    Uses ffmpeg to extract 1 representative 384x384 frame at the midpoint of the
    window, plus a 16kHz mono WAV snippet (capped at 6 seconds for speed).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    mid_ts = start_sec + (duration_sec * 0.5)
    frame_out = out_dir / f"{prefix}.jpg"
    audio_out = out_dir / f"{prefix}.wav" if extract_audio else None

    cmd_frame = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{mid_ts:.3f}",
        "-i", str(video_path),
        "-frames:v", "1",
        "-vf", f"scale={frame_size}:{frame_size}:force_original_aspect_ratio=decrease,"
               f"pad={frame_size}:{frame_size}:(ow-iw)/2:(oh-ih)/2:black",
        "-q:v", "4",
        str(frame_out),
    ]
    frame_ok = False
    try:
        subprocess.run(cmd_frame, check=True, capture_output=True)
        frame_ok = frame_out.exists() and frame_out.stat().st_size > 0
    except subprocess.CalledProcessError:
        frame_ok = False

    audio_ok = False
    if extract_audio and audio_out is not None:
        audio_dur = min(duration_sec, 6.0)
        cmd_audio = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{start_sec:.3f}",
            "-t", f"{audio_dur:.3f}",
            "-i", str(video_path),
            "-vn", "-ac", "1", "-ar", "16000",
            "-f", "wav",
            str(audio_out),
        ]
        try:
            subprocess.run(cmd_audio, check=True, capture_output=True)
            audio_ok = audio_out.exists() and audio_out.stat().st_size > 100
        except subprocess.CalledProcessError:
            audio_ok = False

    return (frame_out if frame_ok else None, audio_out if audio_ok else None)


# ---------------------------------------------------------------------------
# Classification & Intra-Clip Sub-Range Logic
# ---------------------------------------------------------------------------

def score_single_vector(
    vec: list[float],
    anchors: dict[str, Any],
    is_drone_camera: bool = False,
) -> dict[str, Any]:
    """
    Scores a single 256d multimodal vector against all 4 taxonomy dimensions:
    Moments, Energy (1-5), Narrative Value, and Tags.
    """
    # 1. Moment
    moment_scores = {
        m: cosine_sim(vec, m_vec) for m, m_vec in anchors["moments"].items()
    }
    sorted_moments = sorted(moment_scores.items(), key=lambda kv: -kv[1])
    best_moment, best_score = sorted_moments[0]
    second_score = sorted_moments[1][1] if len(sorted_moments) > 1 else 0.0

    # Golden Rule: Drone camera override
    if is_drone_camera and "Drone" in anchors["moments"]:
        best_moment = "Drone"

    # Confidence mapped from cosine similarity & top-2 margin
    margin = max(0.0, best_score - second_score)
    confianza = min(0.99, max(0.15, round(0.55 + (best_score * 0.35) + (margin * 0.6), 2)))

    # 2. Energy (1-5)
    energy_scores = {
        lvl: cosine_sim(vec, e_vec) for lvl, e_vec in anchors["energy"].items()
    }
    best_energy = max(energy_scores.items(), key=lambda kv: kv[1])[0]

    # 3. Narrative Value
    narrative_scores = {
        nv: cosine_sim(vec, n_vec) for nv, n_vec in anchors["narrative"].items()
    }
    best_narrative = max(narrative_scores.items(), key=lambda kv: kv[1])[0]
    if best_moment == "Drone":
        best_narrative = "Epic"

    # 4. Tags (top tags above threshold, max 8)
    tag_scores = [
        (t, cosine_sim(vec, t_vec)) for t, t_vec in anchors["tags"].items()
    ]
    tag_scores.sort(key=lambda kv: -kv[1])
    best_tag_score = tag_scores[0][1] if tag_scores else 0.0
    tag_cutoff = max(0.18, best_tag_score * 0.70)
    selected_tags = [t for t, sc in tag_scores if sc >= tag_cutoff][:6]

    if is_drone_camera and "aerial" not in selected_tags:
        selected_tags.insert(0, "aerial")

    # Dominant sub-range highlight keyword for this window
    top_tag = selected_tags[0] if selected_tags else None
    if best_narrative in ("Foundation", "Candid") and narrative_scores[best_narrative] >= best_score:
        dominant_kw = f"◆ {best_narrative}"
    elif top_tag and tag_scores and tag_scores[0][1] >= 0.25:
        dominant_kw = f"# {top_tag}"
    else:
        dominant_kw = best_moment

    return {
        "categoria": best_moment,
        "energia": int(best_energy),
        "valor_narrativo": best_narrative,
        "confianza": confianza,
        "tags": selected_tags[:8],
        "dominant_kw": dominant_kw,
        "raw_score": best_score,
    }


def merge_contiguous_subranges(raw_ranges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Merges adjacent temporal windows that share the same `keyword`.
    """
    if not raw_ranges:
        return []
    merged: list[dict[str, Any]] = [dict(raw_ranges[0])]
    for curr in raw_ranges[1:]:
        prev = merged[-1]
        prev_end = round(prev["start_sec"] + prev["duration_sec"], 2)
        if (
            curr["keyword"] == prev["keyword"]
            and abs(curr["start_sec"] - prev_end) <= 0.5
        ):
            prev["duration_sec"] = round(prev["duration_sec"] + curr["duration_sec"], 2)
        else:
            merged.append(dict(curr))
    return merged


def classify_clip_from_windows(
    clip_meta: dict[str, Any],
    windows: list[dict[str, Any]],
    anchors: dict[str, Any],
    subrange_min_duration: float = 30.0,
) -> dict[str, Any]:
    """
    Aggregates window embeddings for a clip, computes clip-level classification,
    selects the highest-salience keyframe, and extracts intra-clip `sub_ranges`
    when the clip duration >= `subrange_min_duration`.
    """
    is_drone = clip_meta.get("camara", "").strip().lower() == "drone"
    duration = float(clip_meta.get("duracion_seg", 0.0))

    if not windows:
        return {
            "signature": clip_meta["signature"],
            "archivo": clip_meta["archivo"],
            "categoria": "Unclassified",
            "energia": 3,
            "valor_narrativo": "Filler",
            "confianza": 0.1,
            "tags": ["discard"],
            "sub_ranges": [],
            "best_frame": None,
            "razonamiento": "Sin ventanas válidas para analizar.",
        }

    window_vecs = [w["embedding"] for w in windows]
    clip_vec = average_vectors(window_vecs)
    clip_eval = score_single_vector(clip_vec, anchors, is_drone_camera=is_drone)

    # Evaluate each window individually for best keyframe selection and sub-ranges
    win_evals = []
    for w in windows:
        we = score_single_vector(w["embedding"], anchors, is_drone_camera=is_drone)
        win_evals.append((w, we))

    # Union high-confidence tags from individual windows into clip tags
    all_tags = list(clip_eval["tags"])
    for _, we in win_evals:
        for t in we["tags"][:2]:
            if t not in all_tags and len(all_tags) < 8:
                all_tags.append(t)

    # Best semantic keyframe = window with highest raw semantic score
    best_win, _ = max(win_evals, key=lambda item: item[1]["raw_score"])
    best_frame = best_win.get("frame_path")

    # Build intra-clip sub_ranges if clip >= subrange_min_duration and has >= 2 windows
    sub_ranges: list[dict[str, Any]] = []
    if duration >= subrange_min_duration and len(win_evals) >= 2:
        raw_sub: list[dict[str, Any]] = []
        for w, we in win_evals:
            raw_sub.append({
                "start_sec": float(w["start_sec"]),
                "duration_sec": float(w["duration_sec"]),
                "keyword": we["dominant_kw"],
            })
        merged_sub = merge_contiguous_subranges(raw_sub)
        # Only emit sub_ranges if there are distinct segments or specific highlights
        if len(merged_sub) > 1 or (merged_sub and merged_sub[0]["keyword"].startswith(("#", "◆"))):
            sub_ranges = merged_sub

    audio_note = "con análisis de audio+visión" if clip_meta.get("has_audio", True) and not is_drone else "visión (sin audio)"
    razonamiento = (
        f"EmbeddingGemma 2 ({audio_note}): {clip_eval['categoria']} · "
        f"E{clip_eval['energia']} · {clip_eval['valor_narrativo']}"
    )

    return {
        "signature": clip_meta["signature"],
        "archivo": clip_meta["archivo"],
        "categoria": clip_eval["categoria"],
        "energia": clip_eval["energia"],
        "valor_narrativo": clip_eval["valor_narrativo"],
        "confianza": clip_eval["confianza"],
        "tags": all_tags,
        "sub_ranges": sub_ranges,
        "best_frame": best_frame,
        "clip_embedding": clip_vec,
        "razonamiento": razonamiento,
    }


# ---------------------------------------------------------------------------
# Embeddings Cache Persistence (.embeddings_cache.json)
# ---------------------------------------------------------------------------

def load_embeddings_cache(path: Path) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("windows", []) if isinstance(data, dict) else data
    except (json.JSONDecodeError, OSError):
        return []


def save_embeddings_cache(path: Path, window_entries: list[dict[str, Any]]) -> None:
    payload = {
        "model": "google/embeddinggemma-2",
        "mrl_dim": len(window_entries[0]["embedding"]) if window_entries else 256,
        "count": len(window_entries),
        "windows": window_entries,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main CLI Pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description="Clasificador multimodal local con Google EmbeddingGemma 2"
    )
    p.add_argument("--metadata", type=Path, required=True, help="Ruta a _metadata.json")
    p.add_argument(
        "--tipo",
        default="boda",
        choices=["boda", "wedding", "quinceanero", "corporativo", "concierto", "documental", "viaje"],
    )
    p.add_argument("--output", type=Path, required=True, help="Ruta a _visual_classifications.json")
    p.add_argument("--cache", type=Path, default=None, help="Ruta a .clasificacion_cache.json")
    p.add_argument(
        "--embeddings-cache",
        type=Path,
        default=None,
        help="Ruta para guardar vectores 256d (default: .embeddings_cache.json junto a output)",
    )
    p.add_argument(
        "--embed-mode",
        choices=["local", "triage", "assist"],
        default="triage",
        help="local=100%% EmbeddingGemma 2; triage=escala dudosos (<umbral) al LLM; assist=pasa mejores keyframes al LLM",
    )
    p.add_argument("--triage-threshold", type=float, default=0.65)
    p.add_argument("--manifest-out", type=Path, default=None, help="Ruta opcional para _visual_manifest.json (clips escalados al LLM)")
    p.add_argument("--frames-dir", type=Path, default=None, help="Directorio temporal para snapshots")
    p.add_argument("--mrl-dim", type=int, default=256, choices=[128, 256, 512, 768])
    p.add_argument("--subrange-min-duration", type=float, default=30.0)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--quantize-int8", action="store_true", help="Activa cuantización dinámica INT8 en CPU Intel")
    args = p.parse_args()

    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    cls_cache: dict[str, Any] = {}
    if args.cache and args.cache.exists():
        try:
            cls_cache = json.loads(args.cache.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cls_cache = {}

    emb_cache_path = args.embeddings_cache or (args.output.parent / ".embeddings_cache.json")
    existing_emb_windows = load_embeddings_cache(emb_cache_path)
    emb_by_sig: dict[str, list[dict[str, Any]]] = {}
    for w in existing_emb_windows:
        emb_by_sig.setdefault(w["signature"], []).append(w)

    to_process = [
        m for m in metadata
        if "error" not in m and m.get("signature") not in cls_cache
    ]
    print(
        f"[gemma] {len(metadata)} clips totales · "
        f"{len(metadata) - len(to_process)} en cache · "
        f"{len(to_process)} a clasificar con EmbeddingGemma 2",
        file=sys.stderr,
    )

    if not to_process:
        args.output.write_text("[]", encoding="utf-8")
        print("[ok] Todos los clips ya estaban en cache.", file=sys.stderr)
        return

    embedder = GemmaMultimodalEmbedder(quantize_int8=args.quantize_int8)
    anchors = build_taxonomy_anchors(args.tipo, embedder, mrl_dim=args.mrl_dim)

    temp_root = args.frames_dir or Path(tempfile.mkdtemp(prefix="gemma_media_"))
    temp_root.mkdir(parents=True, exist_ok=True)

    # Step 1: Parallel FFmpeg extraction of lightweight 384x384 frames + 16kHz audio
    print(f"[gemma] Extrayendo snapshots ligeros (384x384 + audio 16kHz) con {args.workers} hilos...", file=sys.stderr)

    def _prep_clip(clip: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        sig = clip["signature"]
        vpath = Path(clip["ruta_absoluta"])
        if not vpath.exists():
            return clip, []
        dur = float(clip.get("duracion_seg", 0.0))
        is_drone = clip.get("camara", "").strip().lower() == "drone"
        use_audio = bool(clip.get("has_audio", True)) and not is_drone
        sched = compute_window_schedule(dur, args.subrange_min_duration)
        w_list = []
        for idx, (st, wdur) in enumerate(sched):
            f_out, a_out = extract_window_media(
                vpath, st, wdur, temp_root, f"{sig[:12]}_{idx:02d}", extract_audio=use_audio
            )
            if f_out is not None:
                w_list.append({
                    "start_sec": st,
                    "duration_sec": wdur,
                    "frame_path": str(f_out),
                    "audio_path": str(a_out) if a_out else None,
                })
        return clip, w_list

    prepared: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(_prep_clip, c) for c in to_process]
        for fut in as_completed(futs):
            prepared.append(fut.result())

    # Step 2: Multimodal Embedding & Classification (Single Batch Pass)
    batch_reqs: list[dict[str, Any]] = []
    for clip, w_list in prepared:
        sig = clip["signature"]
        for w_idx, w in enumerate(w_list):
            w_id = f"{sig}_{w_idx}"
            w["id"] = w_id
            batch_reqs.append({
                "id": w_id,
                "frame_path": w.get("frame_path"),
                "audio_path": w.get("audio_path"),
            })

    batch_embeddings = embedder.encode_windows_batch(batch_reqs)

    classifications: list[dict[str, Any]] = []
    triage_manifest: list[dict[str, Any]] = []

    for idx, (clip, w_list) in enumerate(prepared, 1):
        sig = clip["signature"]
        encoded_windows: list[dict[str, Any]] = []
        for w in w_list:
            raw_vec = batch_embeddings.get(w["id"], [0.0] * 768)
            vec256 = truncate_and_normalize([raw_vec], mrl_dim=args.mrl_dim)[0]
            encoded_windows.append({
                "signature": sig,
                "archivo": clip["archivo"],
                "camara": clip.get("camara", ""),
                "start_sec": w["start_sec"],
                "duration_sec": w["duration_sec"],
                "embedding": vec256,
                "frame_path": w["frame_path"],
            })

        if encoded_windows:
            emb_by_sig[sig] = [
                {
                    "signature": ew["signature"],
                    "archivo": ew["archivo"],
                    "camara": ew["camara"],
                    "start_sec": ew["start_sec"],
                    "duration_sec": ew["duration_sec"],
                    "embedding": ew["embedding"],
                }
                for ew in encoded_windows
            ]

        res = classify_clip_from_windows(
            clip_meta=clip,
            windows=encoded_windows,
            anchors=anchors,
            subrange_min_duration=args.subrange_min_duration,
        )

        classifications.append({
            "signature": res["signature"],
            "archivo": res["archivo"],
            "categoria": res["categoria"],
            "energia": res["energia"],
            "valor_narrativo": res["valor_narrativo"],
            "confianza": res["confianza"],
            "tags": res["tags"],
            "sub_ranges": res["sub_ranges"],
            "razonamiento": res["razonamiento"],
        })

        needs_llm = (
            args.embed_mode == "assist"
            or (
                args.embed_mode == "triage"
                and (
                    res["confianza"] < args.triage_threshold
                    or clip.get("revisar_prioritario") == "SI"
                )
            )
        )
        if needs_llm and res.get("best_frame"):
            triage_manifest.append({
                "signature": sig,
                "archivo": clip["archivo"],
                "camara": clip.get("camara", ""),
                "duracion_seg": clip.get("duracion_seg", 0.0),
                "momento_hora": clip.get("momento_hora", ""),
                "gemma_hypothesis": {
                    "categoria": res["categoria"],
                    "energia": res["energia"],
                    "valor_narrativo": res["valor_narrativo"],
                    "confianza": res["confianza"],
                    "tags": res["tags"],
                },
                "frames": [
                    {
                        "ts": encoded_windows[0]["start_sec"],
                        "path": res["best_frame"],
                        "path_host": res["best_frame"],
                    }
                ],
            })

        if idx % 20 == 0 or idx == len(prepared):
            print(f"[gemma] {idx}/{len(prepared)} clips clasificados", file=sys.stderr)

    # Save outputs
    args.output.write_text(
        json.dumps(classifications, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[ok] Clasificaciones escritas en {args.output}", file=sys.stderr)

    all_cached_windows = [w for w_group in emb_by_sig.values() for w in w_group]
    if all_cached_windows:
        save_embeddings_cache(emb_cache_path, all_cached_windows)
        print(
            f"[ok] Índice vectorial Matryoshka ({args.mrl_dim}d) guardado en {emb_cache_path} "
            f"({len(all_cached_windows)} ventanas)",
            file=sys.stderr,
        )

    if args.manifest_out:
        args.manifest_out.write_text(
            json.dumps(triage_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            f"[gemma] Auto-Triage ({args.embed_mode}): {len(triage_manifest)}/{len(classifications)} "
            f"clips escalados a revisión LLM en {args.manifest_out}",
            file=sys.stderr,
        )

    # Clean up temporary frames if not needed for triage
    if not args.frames_dir and not triage_manifest and temp_root.exists():
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    main()
