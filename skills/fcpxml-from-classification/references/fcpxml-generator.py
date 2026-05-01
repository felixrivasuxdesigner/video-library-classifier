#!/usr/bin/env python3
"""
Generador FCPXML 1.13 desde CSV de clasificación (formato del skill
video-library-classifier 0.6+).

v0.6: Energía ahora es escala 1-5 con nombres descriptivos:
  1=Atmosférico, 2=Íntimo, 3=Social, 4=Celebración, 5=Éxtasis.
  Agrega dimensión Valor Narrativo (Foundation, Candid, Epic, Filler).
  Mantiene backwards compatibility con CSVs v0.3 (alta/media/baja) y
  v0.4 (mismas columnas pero energia como string).

Uso:
    python3 fcpxml-generator.py \\
        --csv /ruta/clasificacion.csv \\
        --videos-root /ruta/carpeta-videos \\
        --library-path /Users/<user>/Movies/<evento>.fcpbundle \\
        --event-name "Matrimonio 21-02-2026" \\
        --output /ruta/salida.fcpxml \\
        [--keywords full|basic]   (default: full)

Defaults wedding (tres proyectos): Película · 30 min | Highlight · 5 min
| RRSS · 1 min. Personalizable vía --projects.

Invariantes críticos (lee references/fcpxml-spec-notes.md):
- FCPXML version="1.13"
- <keyword> SIEMPRE con start + duration (sin eso, FCP ignora el keyword)
- UIDs estables vía uuid5(NAMESPACE_URL, archivo) → idempotente
- Clips sin audio (drones) → hasAudio="0" y sin audioRole
"""
from __future__ import annotations
import argparse
import csv
import json
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from xml.sax.saxutils import escape

# -- Defaults configurables ---------------------------------------------------

DEFAULT_PROJECTS_WEDDING = [
    ("Feature Film · 30 min", 1800),
    ("Highlight · 5 min", 300),
    ("Social Teaser · 1 min", 60),
]

DEFAULT_FOLDER_BY_CAMERA = {
    "Camera 1": "camara1",
    "Camera 2": "camara2",
    "Camera 3": "camara3",
    "Drone": "drone",
    "Go Ultra": "goUltra",
    "GoPro": "gopro",
    "Action Cam": "action",
}

PRIO_KW = "★ Priority"
ENERGIA_PREFIX = "⚡ "       # "⚡ Atmospheric", "⚡ Celebration"
NARRATIVO_PREFIX = "◆ "     # "◆ Foundation", "◆ Candid"
TAG_PREFIX = "# "           # "# toast", "# sunset"

# -- Energy scale v0.6 (1-5 descriptive) -------------------------------------

ENERGIA_NAMES = {
    1: "Atmospheric",
    2: "Intimate",
    3: "Social",
    4: "Celebration",
    5: "Ecstasy",
}

# Backwards compat: CSVs v0.3-0.4 use strings "alta/media/baja"
ENERGIA_LEGACY_MAP = {
    "baja": 1,       # Atmospheric
    "media": 3,      # Social
    "alta": 5,       # Ecstasy
}

# -- Narrative Value v0.6 (archetypes) ---------------------------------------

VALOR_NARRATIVO_VALID = {"Foundation", "Candid", "Epic", "Filler"}

# -- Tags --------------------------------------------------------------------

# Generic tags that don't deserve a Keyword Collection in FCP
# (they clutter the sidebar). Still saved as clip-level keywords.
TAGS_BLOCKLIST = {
    "interior", "exterior", "day", "night",
    "discard", "no_frames",
}

# Tags that DO deserve a Keyword Collection. If not in allowlist,
# they're emitted as clip keyword but no collection is created
# (unless --tags-as-collections all).
TAGS_ALLOWLIST_DEFAULT = {
    # People/subjects
    "bride", "groom", "parents", "photographer", "kids",
    # Iconic objects
    "rings", "dress", "bouquet", "cake", "altar",
    # Spaces
    "church", "venue", "dancefloor", "table", "beach",
    # Actions
    "first_dance", "speech", "toast", "dance", "entrance",
    # Time of day
    "sunset", "sunrise",
    # Shot types
    "aerial", "drone",
}


# -- ffprobe -----------------------------------------------------------------


def ffprobe(path: Path) -> dict:
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error", "-print_format", "json",
                "-show_streams", str(path),
            ],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(r.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        return {"error": str(e)}

    video = next(
        (s for s in data["streams"] if s.get("codec_type") == "video"), None
    )
    audio = next(
        (s for s in data["streams"] if s.get("codec_type") == "audio"), None
    )
    if video is None:
        return {"error": "no video stream"}

    tb = video.get("time_base", "1/30000")
    tb_num, tb_den = map(int, tb.split("/"))
    dur_ts = int(video.get("duration_ts", 0))
    duration_num = dur_ts * tb_num
    duration_den = tb_den
    if duration_den != 30000:
        duration_num = duration_num * 30000 // duration_den
        duration_den = 30000
    duration = f"{duration_num}/{duration_den}s"

    r_frame_rate = video.get("r_frame_rate", "30000/1001")
    fr_num, fr_den = map(int, r_frame_rate.split("/"))
    frame_duration = f"{fr_den}/{fr_num}s"

    return {
        "width": video.get("width", 3840),
        "height": video.get("height", 2160),
        "frame_duration": frame_duration,
        "duration": duration,
        "has_video": True,
        "has_audio": audio is not None,
        "audio_channels": int(audio["channels"]) if audio else 0,
        "audio_rate": int(audio["sample_rate"]) if audio else 0,
    }


def probe_all(
    rows: list[dict], videos_root: Path, folder_map: dict[str, str]
) -> dict[str, dict]:
    def _probe(row):
        archivo = row["archivo"].strip()
        camara = row["camara"].strip()
        folder = folder_map.get(camara, camara.lower().replace(" ", ""))
        path = videos_root / folder / archivo
        meta = ffprobe(path)
        meta["archivo"] = archivo
        meta["folder"] = folder
        meta["path"] = path
        return archivo, meta

    out: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for archivo, meta in pool.map(_probe, rows):
            out[archivo] = meta
    return out


# -- helpers de tags, energía y valor narrativo ------------------------------


def parse_energia(raw: str) -> int | None:
    """
    Parsea el campo energia del CSV.
    - v0.6+: integer 1-5 → devuelve directo
    - v0.3-0.4: string "alta"/"media"/"baja" → mapea a escala 1-5
    - vacío o inválido → None
    """
    if not raw:
        return None
    raw = raw.strip()
    # Intentar como integer (v0.6+)
    try:
        val = int(raw)
        if 1 <= val <= 5:
            return val
        return None
    except ValueError:
        pass
    # Intentar como string legacy (v0.3-0.4)
    return ENERGIA_LEGACY_MAP.get(raw.lower())


def energia_keyword(nivel: int) -> str:
    """Convierte nivel 1-5 a keyword con prefijo: '⚡ Atmosférico'."""
    name = ENERGIA_NAMES.get(nivel, f"Nivel {nivel}")
    return ENERGIA_PREFIX + name


def parse_valor_narrativo(raw: str) -> str | None:
    """Parsea valor_narrativo del CSV. Devuelve None si no existe o es inválido."""
    if not raw:
        return None
    val = raw.strip()
    # Normalizar primera mayúscula
    val_title = val.capitalize()
    if val_title in VALOR_NARRATIVO_VALID:
        return val_title
    return None


def narrativo_keyword(valor: str) -> str:
    """Convierte valor narrativo a keyword con prefijo: '◆ Foundation'."""
    return NARRATIVO_PREFIX + valor


def parse_tags(raw: str) -> list[str]:
    """CSV column `tags` viene como 'a, b, c' o vacío. Devuelve lista limpia."""
    if not raw:
        return []
    return [t.strip().lower() for t in raw.split(",") if t.strip()]


def filter_tags_for_collections(
    tags: list[str], allowlist: set[str] | None,
) -> list[str]:
    """Filtra tags que ameritan Keyword Collection."""
    out = []
    for t in tags:
        if t in TAGS_BLOCKLIST:
            continue
        if allowlist is None or t in allowlist:
            out.append(t)
    return out


# -- XML builders ------------------------------------------------------------


def frame_rate_label(frame_duration: str) -> str:
    num, den = frame_duration.replace("s", "").split("/")
    fps = round(int(den) / int(num), 2)
    return {
        23.98: "2398", 24.0: "24", 25.0: "25", 29.97: "2997",
        30.0: "30", 50.0: "50", 59.94: "5994", 60.0: "60",
    }.get(fps, str(int(round(fps))))


def unique_formats(metas: dict[str, dict]) -> dict[tuple, str]:
    formats = {}
    idx = 0
    for m in metas.values():
        if "error" in m:
            continue
        key = (m["width"], m["height"], m["frame_duration"])
        if key not in formats:
            idx += 1
            formats[key] = f"r{idx}"
    return formats


def load_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def build_fcpxml(
    rows: list[dict],
    metas: dict[str, dict],
    videos_root_mac_uri: str,
    folder_map: dict[str, str],
    library_location: str,
    event_name: str,
    projects: list[tuple[str, int]],
    include_priority_keyword: bool,
    keywords_mode: str,                    # "full" | "basic"
    tags_allowlist: set[str] | None,
    keyword_collections_order: list[str],
) -> str:
    formats = unique_formats(metas)
    out: list[str] = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append("<!DOCTYPE fcpxml>")
    out.append('<fcpxml version="1.13">')
    out.append("  <resources>")

    for (w, h, fd), fid in formats.items():
        fps = frame_rate_label(fd)
        out.append(
            f'    <format id="{fid}" name="FFVideoFormat{h}p{fps}" '
            f'frameDuration="{fd}" fieldOrder="progressive" width="{w}" '
            f'height="{h}" colorSpace="1-1-1 (Rec. 709)"/>'
        )

    asset_ids: dict[str, str] = {}
    idx = 0
    for row in rows:
        archivo = row["archivo"].strip()
        m = metas.get(archivo)
        if m is None or "error" in m:
            print(f"[warn] skip: {archivo}", file=sys.stderr)
            continue
        idx += 1
        aid = f"a{idx}"
        asset_ids[archivo] = aid
        fid = formats[(m["width"], m["height"], m["frame_duration"])]
        asset_uid = uuid.uuid5(uuid.NAMESPACE_URL, archivo).hex.upper()
        camara = row["camara"].strip()
        folder = folder_map.get(camara, camara.lower().replace(" ", ""))
        src = f"{videos_root_mac_uri}/{folder}/{archivo}"
        has_audio = "1" if m["has_audio"] else "0"
        audio_attrs = ""
        if m["has_audio"]:
            audio_attrs = (
                f' audioSources="1" audioChannels="{m["audio_channels"]}" '
                f'audioRate="{m["audio_rate"]//1000}k"'
            )
        out.append(
            f'    <asset id="{aid}" name="{escape(archivo)}" uid="{asset_uid}" '
            f'start="0s" duration="{m["duration"]}" hasVideo="1" '
            f'format="{fid}" videoSources="1" hasAudio="{has_audio}"{audio_attrs}>'
        )
        out.append(
            f'      <media-rep kind="original-media" src="{escape(src)}"/>'
        )
        out.append("    </asset>")
    out.append("  </resources>")

    out.append(f'  <library location="{library_location}">')
    out.append(f'    <event name="{escape(event_name)}">')
    # Dedup estable: si una collection aparece varias veces (ej. "Drone"
    # como momento + como cámara), emitir una sola declaración.
    seen_kc: set[str] = set()
    for kw in keyword_collections_order:
        if kw in seen_kc:
            continue
        seen_kc.add(kw)
        out.append(f'      <keyword-collection name="{escape(kw)}"/>')

    for row in rows:
        archivo = row["archivo"].strip()
        if archivo not in asset_ids:
            continue
        aid = asset_ids[archivo]
        m = metas[archivo]
        duration = m["duration"]
        fid = formats[(m["width"], m["height"], m["frame_duration"])]
        momento = row["momento"].strip()
        camara = row["camara"].strip()
        prio = row.get("revisar_prioritario", "").strip().upper() == "SI"

        # Campos v0.6 (opcionales — ignorar si no existen)
        energia_raw = row.get("energia", "").strip()
        energia_nivel = parse_energia(energia_raw)
        valor_narrativo = parse_valor_narrativo(
            row.get("valor_narrativo", "").strip()
        )
        tags_raw = row.get("tags", "").strip()
        tags = parse_tags(tags_raw)
        emit_tags = filter_tags_for_collections(tags, tags_allowlist) \
            if keywords_mode == "full" else []

        audio_role = ' audioRole="dialogue"' if m["has_audio"] else ""
        out.append(
            f'      <asset-clip ref="{aid}" name="{escape(archivo)}" '
            f'start="0s" duration="{duration}" format="{fid}"{audio_role}>'
        )
        # 🔑 start + duration son REQUIRED por el DTD.
        # Construir lista de keywords del clip evitando duplicados (ej.
        # cuando momento == camara para clips de Drone).
        clip_kws: list[str] = [momento, camara]
        if prio and include_priority_keyword:
            clip_kws.append(PRIO_KW)
        if keywords_mode == "full" and energia_nivel is not None:
            clip_kws.append(energia_keyword(energia_nivel))
        if keywords_mode == "full" and valor_narrativo:
            clip_kws.append(narrativo_keyword(valor_narrativo))
        if keywords_mode == "full":
            clip_kws.extend(TAG_PREFIX + t for t in emit_tags)

        seen: set[str] = set()
        for kw in clip_kws:
            if not kw or kw in seen:
                continue
            seen.add(kw)
            out.append(
                f'        <keyword start="0s" duration="{duration}" '
                f'value="{escape(kw)}"/>'
            )
        out.append("      </asset-clip>")

    main_fid = "r1"
    for pname, pdur in projects:
        out.append(f'      <project name="{escape(pname)}">')
        out.append(
            f'        <sequence duration="{pdur}s" format="{main_fid}" '
            f'tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">'
        )
        out.append("          <spine/>")
        out.append("        </sequence>")
        out.append("      </project>")

    out.append("    </event>")
    out.append("  </library>")
    out.append("</fcpxml>")
    return "\n".join(out) + "\n"


def validate_fcpxml(path: Path) -> None:
    import xml.etree.ElementTree as ET

    tree = ET.parse(path)
    root = tree.getroot()
    assert root.get("version") == "1.13", "version debe ser 1.13"
    clips = list(root.iter("asset-clip"))
    kws = list(root.iter("keyword"))
    sin_rango = [k for k in kws if not k.get("start") or not k.get("duration")]
    assert (
        not sin_rango
    ), f"{len(sin_rango)} keywords sin start/duration — FCP los ignoraría"
    print(
        f"[validate] ✓ version 1.13 · {len(clips)} clips · {len(kws)} keywords "
        f"(todos con rango)"
    )


def parse_projects_arg(s: str | None) -> list[tuple[str, int]]:
    if not s:
        return DEFAULT_PROJECTS_WEDDING
    out = []
    for chunk in s.split(","):
        name, dur = chunk.rsplit(":", 1)
        out.append((name.strip(), int(dur.strip())))
    return out


def parse_folder_map_arg(s: str | None) -> dict[str, str]:
    if not s:
        return DEFAULT_FOLDER_BY_CAMERA
    out = {}
    for chunk in s.split(","):
        k, v = chunk.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def parse_tags_allowlist_arg(s: str | None) -> set[str] | None:
    if not s:
        return TAGS_ALLOWLIST_DEFAULT
    if s.strip().lower() == "all":
        return None  # None = no filtra, todos pasan (excepto blocklist)
    return {t.strip().lower() for t in s.split(",") if t.strip()}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--videos-root", type=Path, required=True)
    p.add_argument(
        "--videos-root-mac",
        help="Ruta en el Mac del usuario (para el file:// src). Si no se da, usa --videos-root.",
    )
    p.add_argument("--library-path", required=True, help="Ruta absoluta al .fcpbundle")
    p.add_argument("--event-name", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--projects",
        help='Lista "Nombre:seg,Nombre:seg". Default: plantilla wedding.',
    )
    p.add_argument(
        "--camera-folder-map",
        help='Mapeo cámara→carpeta "Cámara 1=cam1,Drone=drone"',
    )
    p.add_argument(
        "--no-priority-keyword", action="store_true",
        help="No aplicar el keyword ★ Prioritario",
    )
    p.add_argument(
        "--keywords", choices=["full", "basic"], default="full",
        help="full = momento+cámara+energía+narrativo+tags+prioridad (v0.6). "
             "basic = momento+cámara+prioridad (compat v0.3).",
    )
    p.add_argument(
        "--tags-allowlist",
        help='Lista de tags que crean Keyword Collection. "all" = todos. '
             "Default = allowlist hardcodeado (novia, anillos, atardecer, etc).",
    )
    args = p.parse_args()

    rows = load_rows(args.csv)
    folder_map = parse_folder_map_arg(args.camera_folder_map)
    tags_allowlist = parse_tags_allowlist_arg(args.tags_allowlist)
    print(f"[info] CSV: {len(rows)} filas")
    has_v06_cols = any(row.get("valor_narrativo") for row in rows)
    has_v04_cols = any(row.get("energia") or row.get("tags") for row in rows)
    if args.keywords == "full" and not has_v04_cols:
        print(
            "[warn] --keywords=full pero el CSV no tiene columnas "
            "energia/tags. Cayendo a comportamiento básico para esos campos.",
            file=sys.stderr,
        )
    if has_v06_cols:
        print("[info] CSV v0.6 detectado (valor_narrativo presente)")
    elif has_v04_cols:
        print("[info] CSV v0.4 detectado (energia como string legacy)")

    print("[info] sondeando con ffprobe...")
    metas = probe_all(rows, args.videos_root, folder_map)
    errors = {k: v for k, v in metas.items() if "error" in v}
    if errors:
        print(f"[warn] {len(errors)} archivos con error", file=sys.stderr)

    projects = parse_projects_arg(args.projects)
    mac_root = args.videos_root_mac or f"file://{args.videos_root}"
    if not mac_root.startswith("file://"):
        mac_root = f"file://{mac_root}"
    library_loc = args.library_path
    if not library_loc.startswith("file://"):
        library_loc = f"file://{library_loc}"
    if not library_loc.endswith("/"):
        library_loc += "/"

    # Keyword collections: orden definido y predecible
    momentos_unicos = sorted({row["momento"].strip() for row in rows
                              if row["momento"].strip()})
    camaras_unicas = sorted({row["camara"].strip() for row in rows})
    collections = list(momentos_unicos) + list(camaras_unicas)

    if args.keywords == "full":
        # Energía (1-5 descriptiva, con backwards compat)
        energia_niveles: set[int] = set()
        for row in rows:
            nivel = parse_energia(row.get("energia", ""))
            if nivel is not None:
                energia_niveles.add(nivel)
        collections += [energia_keyword(n) for n in sorted(energia_niveles)]

        # Valor Narrativo (v0.6+)
        narrativos_unicos: set[str] = set()
        for row in rows:
            vn = parse_valor_narrativo(row.get("valor_narrativo", ""))
            if vn:
                narrativos_unicos.add(vn)
        # Orden fijo: Foundation → Candid → Epic → Filler
        narrativo_order = ["Foundation", "Candid", "Epic", "Filler"]
        collections += [
            narrativo_keyword(v) for v in narrativo_order
            if v in narrativos_unicos
        ]

        # Tags (solo los que pasen el filtro)
        all_tags: set[str] = set()
        for row in rows:
            for t in parse_tags(row.get("tags", "")):
                all_tags.add(t)
        emit_tag_collections = filter_tags_for_collections(
            sorted(all_tags), tags_allowlist
        )
        collections += [TAG_PREFIX + t for t in emit_tag_collections]

    if not args.no_priority_keyword and any(
        row.get("revisar_prioritario", "").strip().upper() == "SI" for row in rows
    ):
        collections.append(PRIO_KW)

    xml = build_fcpxml(
        rows=rows,
        metas=metas,
        videos_root_mac_uri=mac_root,
        folder_map=folder_map,
        library_location=library_loc,
        event_name=args.event_name,
        projects=projects,
        include_priority_keyword=not args.no_priority_keyword,
        keywords_mode=args.keywords,
        tags_allowlist=tags_allowlist,
        keyword_collections_order=collections,
    )
    args.output.write_text(xml, encoding="utf-8")
    print(f"[ok] escrito: {args.output}")
    validate_fcpxml(args.output)
    print(
        f"[info] Keyword Collections totales: {len(collections)} "
        f"(modo={args.keywords})"
    )


if __name__ == "__main__":
    main()
