# Processing script — extracción de metadata con ffprobe

Este es el script base que recorre la biblioteca y extrae metadata por clip usando `ffprobe`. Genera el primer pase de datos (sin clasificación visual). El visual se agrega después con `extract-frames.py` + Claude + `merge-classifications.py`.

> Si hay clasificación visual habilitada, **no escribir el CSV final desde aquí** — escribir un JSON intermedio y dejarlo para que `merge-classifications.py` lo combine con la salida de Claude.

**v0.4.1 — nuevo:** argumento `--brackets` permite override del schema horario del tipo. Útil cuando los horarios del evento real no coinciden con el default (ej. boda con ceremonia tardía 18:00-20:00 en vez del default 14:30-17:00).

---

## Script ffprobe-metadata.py

```python
#!/usr/bin/env python3
"""
Extrae metadata de cada clip de video con ffprobe y genera un JSON
intermedio que el resto del pipeline va a consumir.

Uso:
    python3 ffprobe-metadata.py \\
        --root /ruta/biblioteca-videos \\
        --tipo boda \\
        --timezone -3 \\
        --umbral 180 \\
        [--brackets "ceremonia=18:00-20:00,coctel=20:00-21:30,recepcion=21:30-"] \\
        --output /ruta/_metadata.json
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
]


def file_signature(path: Path) -> str:
    st = path.stat()
    raw = f"{path.resolve()}|{st.st_size}|{int(st.st_mtime)}"
    return hashlib.sha1(raw.encode()).hexdigest()


def parse_filename_datetime(name: str):
    for pattern, kind in FILENAME_PATTERNS:
        m = pattern.search(name)
        if m:
            y, mo, d, h, mi, s = (int(g) for g in m.groups())
            return dt.datetime(y, mo, d, h, mi, s), kind
    return None


def ffprobe(path: Path) -> dict:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, check=True,
        )
        return json.loads(r.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        return {"_error": str(e)}


def normalize_camera_name(folder: str) -> str:
    raw = folder.strip()
    low = raw.lower().replace("_", " ").replace("-", " ")
    rules = {
        "camara 1": "Cámara 1", "camara1": "Cámara 1", "cam 1": "Cámara 1",
        "camara 2": "Cámara 2", "camara2": "Cámara 2", "cam 2": "Cámara 2",
        "camara 3": "Cámara 3", "camara3": "Cámara 3", "cam 3": "Cámara 3",
        "drone": "Drone", "dji": "Drone", "mavic": "Drone",
        "go ultra": "Go Ultra", "goultra": "Go Ultra",
        "gopro": "GoPro", "go pro": "GoPro",
        "action": "Action Cam", "action cam": "Action Cam",
    }
    return rules.get(low, raw.title())


def extract_clip_metadata(path: Path, root: Path, tz_offset_hours: int) -> dict:
    rel = path.relative_to(root)
    folder = rel.parts[0] if len(rel.parts) > 1 else ""
    camera = normalize_camera_name(folder)
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
    if fname_parsed:
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
    """'14:30' → 14.5, '06:00' → 6.0"""
    h, m = s.split(":")
    return int(h) + int(m) / 60.0


def assign_momento_horario(meta: dict, schema: list) -> str:
    """schema: lista de (hora_ini_decimal, hora_fin_decimal, nombre)."""
    if not meta.get("hora_creacion"):
        return ""
    dt_obj = dt.datetime.fromisoformat(meta["hora_creacion"])
    h = dt_obj.hour + dt_obj.minute / 60.0
    for ini, fin, name in schema:
        if ini <= fin:
            if ini <= h < fin:
                return name
        else:  # cruza medianoche
            if h >= ini or h < fin:
                return name
    return ""


SCHEMAS_DEFAULT = {
    "boda": [(6.0, 14.5, "Preparativos"), (14.5, 17.0, "Ceremonia"),
             (17.0, 20.0, "Cóctel"), (20.0, 6.0, "Recepción")],
    "quinceanero": [(12.0, 18.0, "Preparativos"), (18.0, 19.5, "Entrada"),
                    (19.5, 21.0, "Vals"), (21.0, 6.0, "Fiesta")],
    "corporativo": [(6.0, 9.0, "Montaje"), (9.0, 10.0, "Apertura"),
                    (10.0, 17.0, "Talleres"), (17.0, 22.0, "Cierre")],
    "concierto": [(12.0, 18.0, "Soundcheck"), (18.0, 20.5, "Apertura"),
                  (20.5, 23.0, "Show"), (23.0, 4.0, "Cierre")],
}


def _normalize(s: str) -> str:
    """Normaliza para match: case + tildes."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def parse_brackets_override(s: str | None, default_schema: list) -> list:
    """
    Parsea --brackets "nombre=HH:MM-HH:MM,nombre=HH:MM-".
    "HH:MM-" significa "desde HH:MM hasta cierre del default".
    Conserva los nombres del default si solo se pisan algunos rangos.
    Match insensible a tildes y mayúsculas (coctel → Cóctel).
    """
    if not s:
        return default_schema
    overrides = {}
    for chunk in s.split(","):
        if "=" not in chunk:
            continue
        name, rng = chunk.split("=", 1)
        name = name.strip()
        rng = rng.strip()
        if "-" not in rng:
            continue
        ini_s, fin_s = rng.split("-", 1)
        ini_s = ini_s.strip()
        fin_s = fin_s.strip()
        ini = time_to_hour_decimal(ini_s) if ini_s else 0.0
        fin = time_to_hour_decimal(fin_s) if fin_s else 6.0
        canonical = _match_name(name, default_schema)
        overrides[_normalize(canonical)] = (ini, fin, canonical)

    new_schema = []
    used = set()
    for ini_d, fin_d, name_d in default_schema:
        key = _normalize(name_d)
        if key in overrides:
            new_schema.append(overrides[key])
            used.add(key)
        else:
            new_schema.append((ini_d, fin_d, name_d))
    for k, v in overrides.items():
        if k not in used:
            new_schema.append(v)
    return new_schema


def _match_name(input_name: str, default_schema: list) -> str:
    """Match insensible a tildes y mayúsculas. coctel → Cóctel."""
    low = _normalize(input_name)
    for _, _, n in default_schema:
        if _normalize(n) == low:
            return n
    return input_name


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--tipo", required=True,
                   choices=["boda", "quinceanero", "corporativo",
                            "concierto", "documental", "viaje"])
    p.add_argument("--timezone", type=int, default=-3)
    p.add_argument("--umbral", type=int, default=180)
    p.add_argument("--brackets", type=str, default=None,
                   help='Override del schema horario del evento. '
                        'Ej: "ceremonia=18:00-20:00,coctel=20:00-21:30"')
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    files = [
        f for f in args.root.rglob("*")
        if f.is_file() and f.suffix.lower() in VIDEO_EXTS
    ]
    print(f"[info] {len(files)} clips encontrados", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=8) as pool:
        metas = list(pool.map(
            lambda f: extract_clip_metadata(f, args.root, args.timezone),
            files,
        ))

    default_schema = SCHEMAS_DEFAULT.get(args.tipo, [])
    schema = parse_brackets_override(args.brackets, default_schema)
    if args.brackets:
        print(f"[info] brackets override aplicado: {schema}", file=sys.stderr)

    for m in metas:
        if "error" in m:
            m["momento_hora"] = "error_ffprobe"
            m["revisar_prioritario"] = "NO"
            continue
        m["momento_hora"] = assign_momento_horario(m, schema) or "Sin clasificar"
        m["revisar_prioritario"] = (
            "SI" if m.get("duracion_seg", 0) > args.umbral else "NO"
        )

    args.output.write_text(
        json.dumps(metas, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    errors = [m for m in metas if "error" in m]
    print(f"[ok] metadata escrita en {args.output}", file=sys.stderr)
    print(f"     {len(metas)} clips, {len(errors)} con error", file=sys.stderr)


if __name__ == "__main__":
    main()
```

---

## Output esperado

JSON intermedio con esta estructura por clip (igual que v0.4.0, no cambia el schema):

```json
{
  "archivo": "C4355.MP4",
  "camara": "Cámara 1",
  "ruta_relativa": "camara1/C4355.MP4",
  "ruta_absoluta": "/Users/felix/Movies/Boda/camara1/C4355.MP4",
  "signature": "a1b2c3d4...",
  "duracion_seg": 8.0,
  "hora_creacion": "2026-02-21T19:32:14",
  "fecha": "2026-02-21",
  "resolucion": "3840x2160",
  "codec": "hevc",
  "has_audio": true,
  "momento_hora": "Cóctel",
  "revisar_prioritario": "NO"
}
```

## Brackets — guía rápida

**Default boda (sin `--brackets`):**

| Hora        | Momento      |
| ----------- | ------------ |
| 06:00–14:30 | Preparativos |
| 14:30–17:00 | Ceremonia    |
| 17:00–20:00 | Cóctel       |
| 20:00–06:00 | Recepción    |

**Ejemplo override para boda con ceremonia tardía** (caso real Daniel-HFoto 21-feb 2026):

```bash
--brackets "ceremonia=18:00-20:00,coctel=20:00-21:30,recepcion=21:30-"
```

Resultado:

| Hora        | Momento                                                 |
| ----------- | ------------------------------------------------------- |
| 06:00–14:30 | Preparativos (default conservado)                       |
| 14:30–18:00 | Preparativos (default conservado, extiende hasta 18:00) |
| 18:00–20:00 | Ceremonia (override)                                    |
| 20:00–21:30 | Cóctel (override)                                       |
| 21:30–06:00 | Recepción (override)                                    |

> Ojo: el parser respeta los nombres del default. Si pisas solo `ceremonia` y `coctel`, el bracket de `Preparativos` y `Recepción` quedan en sus posiciones del default — pero los huecos entre ellos pueden quedar `Sin clasificar`. Si quieres control fino, pisa los 4 brackets explícitamente.
