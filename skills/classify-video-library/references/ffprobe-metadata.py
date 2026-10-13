#!/usr/bin/env python3
"""
Extrae metadata de cada clip de video con ffprobe y genera un JSON
intermedio (`_metadata.json`) que el resto del pipeline consume.

Soporta tanto librerías organizadas en subcarpetas por cámara (`camara1/`,
`drone/`, etc.) como carpetas planas (archivos directo en la raíz).
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mxf"}

FILENAME_PATTERNS = [
    (re.compile(r"DJI_(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})_"), "local"),
    (re.compile(r"VID_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})"), "local"),
    (re.compile(r"VID-(\d{4})(\d{2})(\d{2})-WA"), "date_only"),
]


def file_signature(path: Path) -> str:
    st = path.stat()
    raw = f"{path.resolve()}|{st.st_size}|{int(st.st_mtime)}"
    return hashlib.sha1(raw.encode()).hexdigest()


def parse_filename_datetime(name: str):
    for pattern, kind in FILENAME_PATTERNS:
        m = pattern.search(name)
        if m:
            groups = [int(g) for g in m.groups()]
            if kind == "date_only":
                y, mo, d = groups
                return dt.datetime(y, mo, d, 12, 0, 0), kind
            y, mo, d, h, mi, s = groups
            return dt.datetime(y, mo, d, h, mi, s), kind
    return None


def ffprobe(path: Path) -> dict:
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error", "-print_format", "json",
                "-show_format", "-show_streams", str(path),
            ],
            capture_output=True, text=True, check=True,
        )
        return json.loads(r.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        return {"_error": str(e)}


def normalize_camera_name(folder: str, filename: str = "") -> str:
    raw = folder.strip()
    if not raw:
        if "-WA" in filename.upper():
            return "WhatsApp"
        if filename.upper().startswith("DJI_"):
            return "Drone"
        return "Camera 1"
    low = raw.lower().replace("_", " ").replace("-", " ")
    rules = {
        "camara 1": "Camera 1", "camara1": "Camera 1", "cam 1": "Camera 1",
        "camara 2": "Camera 2", "camara2": "Camera 2", "cam 2": "Camera 2",
        "camara 3": "Camera 3", "camara3": "Camera 3", "cam 3": "Camera 3",
        "drone": "Drone", "dji": "Drone", "mavic": "Drone",
        "go ultra": "Go Ultra", "goultra": "Go Ultra",
        "gopro": "GoPro", "go pro": "GoPro",
        "action": "Action Cam", "action cam": "Action Cam",
    }
    return rules.get(low, raw.title())


def extract_clip_metadata(path: Path, root: Path, tz_offset_hours: int) -> dict:
    rel = path.relative_to(root)
    folder = rel.parts[0] if len(rel.parts) > 1 else ""
    camera = normalize_camera_name(folder, path.name)
    sig = file_signature(path)
    probe = ffprobe(path)
    if "_error" in probe:
        return {
            "archivo": path.name, "camara": camera,
            "ruta_relativa": str(rel), "signature": sig,
            "error": probe["_error"],
        }
    fmt = probe.get("format", {})
    streams = probe.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duracion_seg = round(float(fmt.get("duration", 0.0)), 1)

    creation_dt = None
    fname_parsed = parse_filename_datetime(path.name)
    if fname_parsed and fname_parsed[1] == "local":
        creation_dt, _kind = fname_parsed
    else:
        ct = fmt.get("tags", {}).get("creation_time")
        if ct:
            try:
                base = dt.datetime.fromisoformat(ct.replace("Z", "+00:00"))
                creation_dt = base + dt.timedelta(hours=tz_offset_hours)
                creation_dt = creation_dt.replace(tzinfo=None)
            except ValueError:
                creation_dt = None
        if creation_dt is None and fname_parsed:
            creation_dt, _kind = fname_parsed

    return {
        "archivo": path.name, "camara": camera,
        "ruta_relativa": str(rel), "ruta_absoluta": str(path),
        "signature": sig, "duracion_seg": duracion_seg,
        "hora_creacion": creation_dt.isoformat() if creation_dt else "",
        "fecha": creation_dt.date().isoformat() if creation_dt else "",
        "resolucion": f"{video.get('width', 0)}x{video.get('height', 0)}",
        "codec": video.get("codec_name", ""),
        "has_audio": audio is not None,
    }


def time_to_hour_decimal(s: str) -> float:
    h, m = s.split(":")
    return int(h) + int(m) / 60.0


def assign_momento_horario(meta: dict, schema: list) -> str:
    if not meta.get("hora_creacion"):
        return ""
    dt_obj = dt.datetime.fromisoformat(meta["hora_creacion"])
    h = dt_obj.hour + dt_obj.minute / 60.0
    for ini, fin, name in schema:
        if ini <= fin:
            if ini <= h < fin:
                return name
        else:
            if h >= ini or h < fin:
                return name
    return ""


SCHEMAS_DEFAULT = {
    "boda": [(6.0, 14.5, "Prep"), (14.5, 17.0, "Ceremony"),
             (17.0, 20.0, "Cocktail"), (20.0, 6.0, "Reception")],
    "quinceanero": [(12.0, 18.0, "Prep"), (18.0, 19.5, "Entrance"),
                    (19.5, 21.0, "Waltz"), (21.0, 6.0, "Party")],
    "corporativo": [(6.0, 16.5, "Setup"), (16.5, 17.2, "Opening"),
                    (17.2, 18.0, "Sessions"), (18.0, 23.0, "Closing")],
    "social": [(6.0, 16.9, "Arrival"), (16.9, 17.3, "Opening"),
               (17.3, 18.0, "Celebration"), (18.0, 23.5, "Closing")],
    "concierto": [(12.0, 18.0, "Soundcheck"), (18.0, 20.5, "Opening"),
                  (20.5, 23.0, "Show"), (23.0, 4.0, "Closing")],
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--tipo", required=True,
                   choices=["boda", "quinceanero", "corporativo", "social",
                            "concierto", "documental", "viaje"])
    p.add_argument("--timezone", type=int, default=-3)
    p.add_argument("--umbral", type=int, default=180)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    files = sorted([
        f for f in args.root.rglob("*")
        if f.is_file() and f.suffix.lower() in VIDEO_EXTS and not f.name.startswith("._")
    ])
    print(f"[info] {len(files)} clips encontrados en {args.root}", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=8) as pool:
        metas = list(pool.map(
            lambda f: extract_clip_metadata(f, args.root, args.timezone),
            files,
        ))

    schema = SCHEMAS_DEFAULT.get(args.tipo, [])
    for m in metas:
        if "error" in m:
            m["momento_hora"] = "error_ffprobe"
            m["revisar_prioritario"] = "NO"
            continue
        m["momento_hora"] = assign_momento_horario(m, schema) or "Unclassified"
        m["revisar_prioritario"] = (
            "SI" if m.get("duracion_seg", 0) > args.umbral else "NO"
        )

    args.output.write_text(
        json.dumps(metas, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    errors = [m for m in metas if "error" in m]
    print(f"[ok] metadata escrita en {args.output} ({len(metas)} clips, {len(errors)} errores)", file=sys.stderr)


if __name__ == "__main__":
    main()
