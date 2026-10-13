#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "sentence-transformers>=3.3.0",
#   "transformers>=4.48.0",
#   "torch>=2.4.0",
#   "numpy>=1.26.0",
# ]
# ///
"""
Video Moment Finder (`moment-finder.py`) — Búsqueda semántica de momentos en
lenguaje natural con Google EmbeddingGemma 2 (`google/embeddinggemma-2`).

Inspirado en "Video Moment Finder" de Google AI Edge Gallery:
- Busca en milisegundos sobre el índice `.embeddings_cache.json` generado por
  `gemma-classify.py` sin tener que re-procesar los videos.
- Devuelve los clips exactos con su rango de tiempo (`start_sec` + `duration_sec`).
- Puede inyectar los resultados directamente en `clasificacion.csv` (columna
  `sub_ranges`) con el prefijo `🔍 <consulta>` para que `fcpxml-generator.py`
  cree una Keyword Collection de ese momento exacto en Final Cut Pro.

Uso:
    uv run moment-finder.py \\
        --query "novio llorando en el altar" \\
        --embeddings /ruta/.embeddings_cache.json \\
        [--top-k 10] [--min-score 0.25] \\
        [--inject-csv /ruta/clasificacion.csv] \\
        [--label "🔍 novio llorando"]
"""
from __future__ import annotations
import argparse
import csv
import importlib
import json
import sys
from pathlib import Path
from typing import Any

# Import shared helpers from gemma-classify.py in the same folder
sys.path.insert(0, str(Path(__file__).resolve().parent))
_gemma = importlib.import_module("gemma-classify")
cosine_sim = _gemma.cosine_sim
truncate_and_normalize = _gemma.truncate_and_normalize
load_embeddings_cache = _gemma.load_embeddings_cache
GemmaMultimodalEmbedder = _gemma.GemmaMultimodalEmbedder


def format_mmss(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds - (m * 60)
    return f"{m:02d}:{s:04.1f}"


def search_moments(
    query_vec: list[float],
    cache_path: Path,
    top_k: int = 10,
    min_score: float = 0.25,
) -> list[dict[str, Any]]:
    """
    Searches all indexed video/audio windows in `cache_path` against `query_vec`
    using cosine similarity. Returns the top-K matching windows sorted by score.
    """
    windows = load_embeddings_cache(cache_path)
    if not windows:
        return []

    scored: list[dict[str, Any]] = []
    for w in windows:
        emb = w.get("embedding", [])
        if not emb:
            continue
        score = cosine_sim(query_vec, emb)
        if score >= min_score:
            st = float(w.get("start_sec", 0.0))
            dur = float(w.get("duration_sec", 0.0))
            scored.append({
                "signature": w.get("signature", ""),
                "archivo": w.get("archivo", ""),
                "camara": w.get("camara", ""),
                "start_sec": round(st, 2),
                "duration_sec": round(dur, 2),
                "timecode": f"{format_mmss(st)} - {format_mmss(st + dur)}",
                "score": round(score, 4),
            })

    scored.sort(key=lambda item: -item["score"])
    return scored[:top_k]


def inject_matches_into_csv(
    csv_path: Path,
    matches: list[dict[str, Any]],
    keyword_label: str,
) -> int:
    """
    Injects matched sub-clip ranges into the `sub_ranges` column of `csv_path`
    under `keyword_label` (e.g., '🔍 novio llorando') so `fcpxml-generator.py`
    turns them into frame-accurate Keyword Collection ranges in Final Cut Pro.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV no encontrado: {csv_path}")

    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if "sub_ranges" not in fieldnames:
        # Insert sub_ranges right after tags if present, else at the end
        if "tags" in fieldnames:
            idx = fieldnames.index("tags") + 1
            fieldnames.insert(idx, "sub_ranges")
        else:
            fieldnames.append("sub_ranges")

    matches_by_file: dict[str, list[dict[str, Any]]] = {}
    for m in matches:
        matches_by_file.setdefault(m["archivo"], []).append(m)

    injected_count = 0
    for row in rows:
        arch = row.get("archivo", "").strip()
        raw_sr = row.get("sub_ranges", "").strip()
        try:
            sr_list = json.loads(raw_sr) if raw_sr else []
            if not isinstance(sr_list, list):
                sr_list = []
        except json.JSONDecodeError:
            sr_list = []

        if arch in matches_by_file:
            for m in matches_by_file[arch]:
                entry = {
                    "start_sec": m["start_sec"],
                    "duration_sec": m["duration_sec"],
                    "keyword": keyword_label,
                }
                if entry not in sr_list:
                    sr_list.append(entry)
                    injected_count += 1

        row["sub_ranges"] = json.dumps(sr_list, ensure_ascii=False)

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return injected_count


def main() -> None:
    p = argparse.ArgumentParser(
        description="Video Moment Finder — Búsqueda en lenguaje natural con EmbeddingGemma 2"
    )
    p.add_argument("--query", required=True, help="Descripción en lenguaje natural del momento a buscar")
    p.add_argument("--embeddings", type=Path, required=True, help="Ruta a .embeddings_cache.json")
    p.add_argument("--top-k", type=int, default=10, help="Cantidad máxima de momentos a devolver")
    p.add_argument("--min-score", type=float, default=0.22, help="Similitud coseno mínima (default: 0.22)")
    p.add_argument("--inject-csv", type=Path, default=None, help="CSV donde inyectar los sub-rangos encontrados")
    p.add_argument("--label", type=str, default=None, help="Nombre del Keyword en FCP (default: '🔍 <query>')")
    p.add_argument("--json", action="store_true", help="Imprimir salida en formato JSON")
    args = p.parse_args()

    windows = load_embeddings_cache(args.embeddings)
    if not windows:
        print(f"[error] No se encontraron embeddings en {args.embeddings}", file=sys.stderr)
        sys.exit(1)

    mrl_dim = len(windows[0].get("embedding", [])) or 256
    embedder = GemmaMultimodalEmbedder()
    raw_q = embedder.encode_text([args.query], prompt_name="SearchQuery")
    q_vec = truncate_and_normalize(raw_q, mrl_dim=mrl_dim)[0]

    matches = search_moments(
        query_vec=q_vec,
        cache_path=args.embeddings,
        top_k=args.top_k,
        min_score=args.min_score,
    )

    if args.inject_csv and matches:
        label = args.label or f"🔍 {args.query.strip()}"
        n_inj = inject_matches_into_csv(args.inject_csv, matches, label)
        print(
            f"[ok] {n_inj} sub-rangos inyectados en {args.inject_csv} bajo el keyword '{label}'",
            file=sys.stderr,
        )

    if args.json:
        print(json.dumps(matches, ensure_ascii=False, indent=2))
        return

    print(f"\n🔍 Video Moment Finder — Consulta: \"{args.query}\"")
    print(f"   Momentos encontrados: {len(matches)}\n")
    for idx, m in enumerate(matches, 1):
        print(
            f"  {idx:2d}. [{m['score']:.3f}] {m['archivo']} ({m['camara']}) "
            f"→ {m['timecode']} (start={m['start_sec']}s, dur={m['duration_sec']}s)"
        )


if __name__ == "__main__":
    main()
