#!/usr/bin/env python3
"""
Extrae frames keyframes de cada clip a baja resolución (640x360 JPEG q=4)
para que Claude (modelo cargado en la sesión Cowork) los lea y clasifique
visualmente.

v0.4.1 — fix crítico: el manifest emite DOS paths por frame:
  - "path": ruta tal como existe en disco (donde corre este script)
  - "path_host": ruta como la verá la herramienta `Read` del modelo
Si --host-root coincide con el root real de filesystem, ambos son iguales.
Si el script corre en un VM/sandbox y los frames quedan en /sessions/...
pero el modelo lee desde el host (/Users/.../Movies/...), el manifest debe
exponer la ruta del host. Este es el bug que rompió la clasificación
visual en v0.4.0 cuando el modelo era invocado desde Cowork.

Diseño:
- Frames adaptativos según duración:
    * <5s   → 1 frame al medio (50%)
    * 5-30s → 2 frames (25%, 75%)
    * >30s  → 3 frames (15%, 50%, 85%)
    * >60s  → 4 frames (10%, 40%, 60%, 90%) — opcional con --frames 4
- Frames temporales en --frames-dir, borrados después por
  merge-classifications.py.
- Cache: signature (sha1 path+size+mtime) en cache JSON evita reproceso.

Uso:
    python3 extract-frames.py \\
        --metadata /ruta/_metadata.json \\
        --frames-dir /ruta/_frames \\
        --output /ruta/_visual_manifest.json \\
        --cache /ruta/.clasificacion_cache.json \\
        [--host-root /Users/usuario/Movies/Boda] \\
        [--vm-root /sessions/.../mnt/Boda] \\
        [--frames-default 3] [--max-frames 4] [--quality 4] \\
        [--width 640] [--height 360]
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def adaptive_frame_count(duration: float, default: int, cap: int) -> int:
    if duration <= 0:
        return 1
    if duration < 5:
        return 1
    if duration < 30:
        return min(2, cap)
    if duration < 60:
        return min(default, cap)
    return min(cap, max(default, 4))


def frame_timestamps(duration: float, n: int) -> list[float]:
    """Distribuye n frames evitando los bordes del clip."""
    if n == 1:
        return [duration * 0.5]
    if n == 2:
        return [duration * 0.25, duration * 0.75]
    if n == 3:
        return [duration * 0.15, duration * 0.50, duration * 0.85]
    if n == 4:
        return [duration * 0.10, duration * 0.40, duration * 0.60, duration * 0.90]
    step = (duration * 0.9) / (n - 1)
    start = duration * 0.05
    return [start + i * step for i in range(n)]


def extract_one_frame(
    video_path: Path, ts_seconds: float, out_path: Path,
    width: int, height: int, quality: int,
) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{ts_seconds:.3f}",
        "-i", str(video_path),
        "-frames:v", "1",
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
               f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
        "-q:v", str(quality),
        str(out_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return out_path.exists() and out_path.stat().st_size > 0
    except subprocess.CalledProcessError:
        return False


def vm_to_host(path_str: str, vm_root: str | None, host_root: str | None) -> str:
    """Convierte un path del VM/sandbox al equivalente en el host del usuario."""
    if not vm_root or not host_root:
        return path_str
    if path_str.startswith(vm_root):
        return host_root + path_str[len(vm_root):]
    return path_str


def auto_detect_vm_root(path: Path) -> str | None:
    """
    Si el path absoluto comienza con /sessions/<algo>/mnt/<nombre>/...
    devuelve "/sessions/<algo>/mnt/<nombre>" como vm_root candidato.
    En cualquier otro caso devuelve None.
    """
    parts = path.resolve().parts
    if len(parts) >= 5 and parts[1] == "sessions" and parts[3] == "mnt":
        return "/" + "/".join(parts[1:5])
    return None


def extract_clip_frames(
    clip_meta: dict, frames_dir: Path,
    default_frames: int, max_frames: int,
    width: int, height: int, quality: int,
    vm_root: str | None, host_root: str | None,
) -> dict:
    if "error" in clip_meta:
        return {
            "signature": clip_meta["signature"],
            "archivo": clip_meta["archivo"],
            "frames": [],
            "skipped_reason": "ffprobe_error",
        }

    duration = float(clip_meta.get("duracion_seg", 0))
    video_path = Path(clip_meta["ruta_absoluta"])
    if not video_path.exists():
        return {
            "signature": clip_meta["signature"],
            "archivo": clip_meta["archivo"],
            "frames": [],
            "skipped_reason": "file_missing",
        }

    n = adaptive_frame_count(duration, default_frames, max_frames)
    timestamps = frame_timestamps(duration, n)

    sig_short = clip_meta["signature"][:12]
    frame_entries = []
    for idx, ts in enumerate(timestamps):
        out = frames_dir / f"{sig_short}_{idx:02d}.jpg"
        ok = extract_one_frame(
            video_path, ts, out, width, height, quality,
        )
        if ok:
            path_str = str(out)
            entry = {
                "ts": round(ts, 2),
                "path": path_str,
                "path_host": vm_to_host(path_str, vm_root, host_root),
            }
            frame_entries.append(entry)

    return {
        "signature": clip_meta["signature"],
        "archivo": clip_meta["archivo"],
        "camara": clip_meta.get("camara", ""),
        "duracion_seg": duration,
        "momento_hora": clip_meta.get("momento_hora", ""),
        "frames": frame_entries,
    }


def load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--metadata", type=Path, required=True,
                   help="JSON producido por ffprobe-metadata.py")
    p.add_argument("--frames-dir", type=Path, required=True,
                   help="Directorio temp donde escribir los JPEGs")
    p.add_argument("--output", type=Path, required=True,
                   help="Manifest JSON con paths de frames a clasificar")
    p.add_argument("--cache", type=Path, default=None,
                   help="Cache JSON de clasificaciones previas")
    p.add_argument("--host-root", type=str, default=None,
                   help="Path del Mac/host del usuario equivalente a --vm-root. "
                        "Ej: /Users/felix/Movies/Boda. El modelo Claude usará "
                        "este prefix para leer los frames con Read.")
    p.add_argument("--vm-root", type=str, default=None,
                   help="Path del sandbox/VM. Default: auto-detect desde el "
                        "primer clip si comienza con /sessions/*/mnt/*.")
    p.add_argument("--frames-default", type=int, default=3)
    p.add_argument("--max-frames", type=int, default=4)
    p.add_argument("--quality", type=int, default=4,
                   help="ffmpeg -q:v 2-5; menor = mejor calidad")
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=360)
    p.add_argument("--workers", type=int, default=4,
                   help="Concurrencia ffmpeg (cuidado con I/O)")
    args = p.parse_args()

    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    cache = load_cache(args.cache) if args.cache else {}

    # Resolver vm_root: explícito > auto-detect
    vm_root = args.vm_root
    if not vm_root and metadata:
        first_path = Path(metadata[0].get("ruta_absoluta", "/"))
        vm_root = auto_detect_vm_root(first_path)
        if vm_root:
            print(f"[info] vm_root auto-detectado: {vm_root}", file=sys.stderr)

    if vm_root and not args.host_root:
        print(
            "[warn] vm_root detectado/dado pero NO --host-root. "
            "El manifest usará el mismo path para vm y host. Si el modelo "
            "lee desde el Mac del usuario, va a fallar con 'VM path' error. "
            "Pasá --host-root /Users/<usuario>/Movies/<carpeta>",
            file=sys.stderr,
        )

    # Limpiar y crear frames_dir
    if args.frames_dir.exists():
        shutil.rmtree(args.frames_dir)
    args.frames_dir.mkdir(parents=True, exist_ok=True)

    to_process = [m for m in metadata if m["signature"] not in cache]
    skipped_cached = len(metadata) - len(to_process)
    print(
        f"[info] {len(metadata)} clips totales · "
        f"{skipped_cached} en cache · {len(to_process)} a procesar",
        file=sys.stderr,
    )

    manifest = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                extract_clip_frames, m, args.frames_dir,
                args.frames_default, args.max_frames,
                args.width, args.height, args.quality,
                vm_root, args.host_root,
            ): m for m in to_process
        }
        done = 0
        for fut in as_completed(futures):
            entry = fut.result()
            manifest.append(entry)
            done += 1
            if done % 25 == 0 or done == len(to_process):
                print(
                    f"[progress] {done}/{len(to_process)} clips procesados",
                    file=sys.stderr,
                )

    total_bytes = sum(
        Path(f["path"]).stat().st_size
        for entry in manifest for f in entry["frames"]
        if Path(f["path"]).exists()
    )
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"[ok] manifest visual: {args.output}",
        file=sys.stderr,
    )
    print(
        f"     {sum(len(e['frames']) for e in manifest)} frames generados, "
        f"{total_bytes / 1024 / 1024:.1f} MB en disco temp",
        file=sys.stderr,
    )
    if vm_root and args.host_root:
        print(
            f"     vm_root={vm_root}  →  host_root={args.host_root}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()