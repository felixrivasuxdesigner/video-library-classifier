#!/usr/bin/env python3
"""
Test suite for Video Library Classifier v0.7.0:
- gemma-classify.py (Multimodal taxonomy classification, Matryoshka 256d truncation,
  sub-range detection on long clips, smart keyframe selection, and auto-triage)
- moment-finder.py (Natural language semantic moment search & CSV/FCPXML injection)
- merge-classifications.py (Preserving sub_ranges & v0.7 energy 1-5 report)
- fcpxml-generator.py (Emitting sub-clip <keyword start="..." duration="..."/> ranges
  and 🔍 Moment Finder collections in valid FCPXML 1.13)
"""
from __future__ import annotations
import csv
import json
import math
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLASSIFY_REFS = REPO_ROOT / "skills" / "classify-video-library" / "references"
FCPXML_REFS = REPO_ROOT / "skills" / "fcpxml-from-classification" / "references"

sys.path.insert(0, str(CLASSIFY_REFS))
sys.path.insert(0, str(FCPXML_REFS))


class DummyEmbedder:
    """
    Deterministic mock embedder that simulates google/embeddinggemma-2
    768-dimensional output space so tests run fast and offline without downloading
    500MB weights.
    """
    def __init__(self, dim: int = 768):
        self.dim = dim

    def _keyword_vec(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        t = text.lower()
        if any(w in t for w in ("ceremony", "altar", "vow", "church", "ceremonia")):
            vec[0] = 1.0
        if any(w in t for w in ("reception", "party", "dancefloor", "ecstasy", "5", "fiesta")):
            vec[1] = 1.0
        if any(w in t for w in ("speech", "toast", "foundation", "microphone", "spoken", "vows", "brindis")):
            vec[2] = 1.0
        if any(w in t for w in ("drone", "aerial", "epic", "wide")):
            vec[3] = 1.0
        if any(w in t for w in ("prep", "dress", "intimate", "2")):
            vec[4] = 1.0
        if any(w in t for w in ("candid", "tear", "crying", "llorando", "laugh", "reaction")):
            vec[5] = 1.0
        if any(w in t for w in ("details", "rings", "atmospheric", "1", "static")):
            vec[6] = 1.0
        if any(w in t for w in ("celebration", "4", "first_dance", "hug")):
            vec[7] = 1.0
        for i, ch in enumerate(t.encode("utf-8")[:64]):
            vec[10 + (i % 50)] += (ch % 7) * 0.01
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def encode_text(self, texts: list[str], prompt_name: str = "Classification") -> list[list[float]]:
        return [self._keyword_vec(t) for t in texts]

    def encode_window(
        self,
        frame_path: Path | None,
        audio_path: Path | None,
        hint: str = "",
    ) -> list[float]:
        return self._keyword_vec(hint)


class TestPipelineV07(unittest.TestCase):

    def test_01_matryoshka_truncation_and_l2_norm(self):
        import importlib
        gemma = importlib.import_module("gemma-classify")

        raw = [[float((i + j) % 13) - 6.0 for j in range(768)] for i in range(4)]
        trunc = gemma.truncate_and_normalize(raw, mrl_dim=256)
        self.assertEqual(len(trunc), 4)
        self.assertEqual(len(trunc[0]), 256)
        for row in trunc:
            norm = math.sqrt(sum(x * x for x in row))
            self.assertAlmostEqual(norm, 1.0, places=3)

    def test_02_subrange_detection_and_merging_on_long_clip(self):
        import importlib
        gemma = importlib.import_module("gemma-classify")
        embedder = DummyEmbedder()

        anchors = gemma.build_taxonomy_anchors("boda", embedder, mrl_dim=256)

        # Simulate a 60-second clip with 6 windows of 10s each:
        # 0-20s: speech/toast, 20-40s: candid crying reaction, 40-60s: party celebration
        window_semantic_hints = [
            (0.0, 10.0, "speech toast foundation microphone"),
            (10.0, 10.0, "speech toast foundation microphone"),
            (20.0, 10.0, "candid tear crying reaction"),
            (30.0, 10.0, "candid tear crying reaction"),
            (40.0, 10.0, "reception party dancefloor ecstasy"),
            (50.0, 10.0, "reception party dancefloor ecstasy"),
        ]
        window_entries = []
        for start_s, dur_s, hint in window_semantic_hints:
            vec768 = embedder.encode_window(None, None, hint=hint)
            vec256 = gemma.truncate_and_normalize([vec768], mrl_dim=256)[0]
            window_entries.append({
                "start_sec": start_s,
                "duration_sec": dur_s,
                "embedding": vec256,
                "frame_path": f"/tmp/frame_{int(start_s)}.jpg",
            })

        result = gemma.classify_clip_from_windows(
            clip_meta={
                "signature": "sig_long_001",
                "archivo": "C001_LONG.MP4",
                "camara": "Camera 1",
                "duracion_seg": 60.0,
                "has_audio": True,
            },
            windows=window_entries,
            anchors=anchors,
            subrange_min_duration=30.0,
        )

        self.assertIn("sub_ranges", result)
        self.assertGreaterEqual(len(result["sub_ranges"]), 2)
        first_sr = result["sub_ranges"][0]
        self.assertEqual(first_sr["start_sec"], 0.0)
        self.assertEqual(first_sr["duration_sec"], 20.0)

    def test_03_moment_finder_semantic_search_and_csv_injection(self):
        import importlib
        gemma = importlib.import_module("gemma-classify")
        finder = importlib.import_module("moment-finder")
        embedder = DummyEmbedder()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            cache_path = tmp / ".embeddings_cache.json"
            csv_path = tmp / "clasificacion.csv"

            hints = [
                ("sig1", "C001.MP4", "Camera 1", 0.0, 12.0, "prep dress intimate"),
                ("sig2", "C002.MP4", "Camera 2", 15.0, 10.0, "ceremony altar candid tear crying llorando"),
                ("sig2", "C002.MP4", "Camera 2", 25.0, 15.0, "reception party dancefloor ecstasy"),
            ]
            entries = []
            for sig, arch, cam, st, dur, h in hints:
                v768 = embedder.encode_window(None, None, hint=h)
                v256 = gemma.truncate_and_normalize([v768], mrl_dim=256)[0]
                entries.append({
                    "signature": sig,
                    "archivo": arch,
                    "camara": cam,
                    "start_sec": st,
                    "duration_sec": dur,
                    "embedding": v256,
                })

            gemma.save_embeddings_cache(cache_path, entries)

            q_vec768 = embedder.encode_text(["novio llorando en el altar"], prompt_name="SearchQuery")
            q_vec256 = gemma.truncate_and_normalize(q_vec768, mrl_dim=256)[0]

            matches = finder.search_moments(
                query_vec=q_vec256,
                cache_path=cache_path,
                top_k=2,
                min_score=0.2,
            )
            self.assertGreaterEqual(len(matches), 1)
            self.assertEqual(matches[0]["archivo"], "C002.MP4")
            self.assertEqual(matches[0]["start_sec"], 15.0)
            self.assertEqual(matches[0]["duration_sec"], 10.0)

            with csv_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=[
                    "archivo", "camara", "duracion_seg", "hora_creacion",
                    "momento", "momento_hora", "categoria_visual", "energia",
                    "valor_narrativo", "confianza", "tags", "sub_ranges",
                    "resolucion", "codec", "revisar_prioritario"
                ])
                w.writeheader()
                w.writerow({
                    "archivo": "C002.MP4",
                    "camara": "Camera 2",
                    "duracion_seg": "40.0",
                    "hora_creacion": "2026-02-21T16:00:00",
                    "momento": "Ceremony",
                    "momento_hora": "Ceremony",
                    "categoria_visual": "Ceremony",
                    "energia": "2",
                    "valor_narrativo": "Candid",
                    "confianza": "0.88",
                    "tags": "bride, altar",
                    "sub_ranges": "[]",
                    "resolucion": "3840x2160",
                    "codec": "hevc",
                    "revisar_prioritario": "NO",
                })

            finder.inject_matches_into_csv(
                csv_path=csv_path,
                matches=matches[:1],
                keyword_label="🔍 novio llorando",
            )

            with csv_path.open(encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            sub_ranges = json.loads(rows[0]["sub_ranges"])
            self.assertEqual(len(sub_ranges), 1)
            self.assertEqual(sub_ranges[0]["keyword"], "🔍 novio llorando")
            self.assertEqual(sub_ranges[0]["start_sec"], 15.0)

    def test_04_merge_and_fcpxml_subclip_keyword_ranges(self):
        import importlib
        merge_mod = importlib.import_module("merge-classifications")
        fcpxml_mod = importlib.import_module("fcpxml-generator")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            meta_json = tmp / "_metadata.json"
            vis_json = tmp / "_visual_classifications.json"
            csv_out = tmp / "clasificacion.csv"
            fcpxml_out = tmp / "evento.fcpxml"

            meta_data = [{
                "archivo": "C002.MP4",
                "camara": "Camera 1",
                "ruta_relativa": "camara1/C002.MP4",
                "ruta_absoluta": str(tmp / "camara1" / "C002.MP4"),
                "signature": "sig_c002",
                "duracion_seg": 60.0,
                "hora_creacion": "2026-02-21T19:00:00",
                "momento_hora": "Cocktail",
                "resolucion": "3840x2160",
                "codec": "hevc",
                "revisar_prioritario": "NO",
            }]
            vis_data = [{
                "signature": "sig_c002",
                "archivo": "C002.MP4",
                "categoria": "Reception",
                "energia": 4,
                "valor_narrativo": "Foundation",
                "confianza": 0.91,
                "tags": ["toast", "speech"],
                "sub_ranges": [
                    {"start_sec": 10.0, "duration_sec": 15.0, "keyword": "# toast"},
                    {"start_sec": 35.0, "duration_sec": 20.0, "keyword": "🔍 brindis emotivo"},
                ],
                "razonamiento": "Toast speech followed by cheering",
            }]
            meta_json.write_text(json.dumps(meta_data), encoding="utf-8")
            vis_json.write_text(json.dumps(vis_data), encoding="utf-8")

            row = merge_mod.merge_one(meta_data[0], vis_data[0], None)
            self.assertIn("sub_ranges", row)
            merge_mod.write_csv([row], csv_out)

            rows = fcpxml_mod.load_rows(csv_out)
            metas = {
                "C002.MP4": {
                    "width": 3840,
                    "height": 2160,
                    "frame_duration": "1001/24000s",
                    "duration": "1801800/30000s",
                    "has_video": True,
                    "has_audio": True,
                    "audio_channels": 2,
                    "audio_rate": 48000,
                }
            }
            collections = fcpxml_mod.collect_keyword_collections(
                rows=rows,
                keywords_mode="full",
                tags_allowlist=fcpxml_mod.TAGS_ALLOWLIST_DEFAULT,
                include_priority_keyword=True,
            )
            self.assertIn("🔍 brindis emotivo", collections)

            xml_str = fcpxml_mod.build_fcpxml(
                rows=rows,
                metas=metas,
                videos_root_mac_uri="file:///Users/felix/Movies/Boda",
                folder_map=fcpxml_mod.DEFAULT_FOLDER_BY_CAMERA,
                library_location="file:///Users/felix/Movies/Boda.fcpbundle/",
                event_name="Boda Test",
                projects=fcpxml_mod.DEFAULT_PROJECTS_WEDDING,
                include_priority_keyword=True,
                keywords_mode="full",
                tags_allowlist=fcpxml_mod.TAGS_ALLOWLIST_DEFAULT,
                keyword_collections_order=collections,
            )
            fcpxml_out.write_text(xml_str, encoding="utf-8")
            fcpxml_mod.validate_fcpxml(fcpxml_out)

            tree = ET.parse(fcpxml_out)
            root = tree.getroot()
            kws = list(root.iter("keyword"))
            search_kws = [k for k in kws if k.get("value") == "🔍 brindis emotivo"]
            self.assertEqual(len(search_kws), 1)
            self.assertNotEqual(search_kws[0].get("start"), "0s")


if __name__ == "__main__":
    unittest.main()
