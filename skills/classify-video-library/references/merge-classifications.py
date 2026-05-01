#!/usr/bin/env python3
"""
Mergea metadata ffprobe + clasificación visual de Claude + clasificación
temporal en el CSV final. Actualiza el cache de clasificaciones para
runs futuros y limpia los frames temporales del disco.

v0.4.1 — alertas nuevas:
  - override visual >40% → bracket horario probablemente mal calibrado
  - clips con hora_creacion sospechosa (luz "dia" pero hora de noche
    según bracket, o viceversa)
  - clips con tag "descarte" → sugerir revisión manual

Política de fusión:
- categoria visual con confianza >= 0.6 → fuente de verdad para `momento`
- Si confianza < 0.6 → fallback a `momento_hora`
- Si el clip viene del cache → usar el cacheado
- `momento_hora` queda SIEMPRE en su columna para auditoría

Uso:
    python3 merge-classifications.py \\
        --metadata /ruta/_metadata.json \\
        --visual /ruta/_visual_classifications.json \\
        --cache /ruta/.clasificacion_cache.json \\
        --frames-dir /ruta/_frames \\
        --output /ruta/clasificacion.csv \\
        [--keep-frames] [--alert-threshold 0.4]
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

CSV_COLUMNS = [
    "archivo", "camara", "duracion_seg", "hora_creacion",
    "momento", "momento_hora", "categoria_visual", "energia",
    "valor_narrativo", "confianza", "tags", "resolucion", "codec",
    "revisar_prioritario",
]

CONFIDENCE_THRESHOLD = 0.6

# Tags suggesting daylight → if time bracket says "night", flag
TAGS_LUZ_DIA = {"day", "sunset", "sunrise", "exterior"}
TAGS_LUZ_NOCHE = {"night", "party", "club", "lights"}


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[warn] no pude leer {path}: {e}", file=sys.stderr)
        return default


def merge_one(meta: dict, visual: dict | None, cache_entry: dict | None) -> dict:
    source = visual or cache_entry

    if source:
        categoria_visual = source.get("categoria", "")
        energia = source.get("energia", "")
        valor_narrativo = source.get("valor_narrativo", "")
        confianza = float(source.get("confianza", 0.0))
        tags = source.get("tags", []) or []
    else:
        categoria_visual = ""
        energia = ""
        valor_narrativo = ""
        confianza = 0.0
        tags = []

    momento_hora = meta.get("momento_hora", "")
    if "error" in meta:
        momento_final = "error_ffprobe"
    elif categoria_visual and confianza >= CONFIDENCE_THRESHOLD:
        momento_final = categoria_visual
    elif momento_hora:
        momento_final = momento_hora
    else:
        momento_final = "Sin clasificar"

    return {
        "archivo": meta["archivo"],
        "camara": meta.get("camara", ""),
        "duracion_seg": meta.get("duracion_seg", ""),
        "hora_creacion": meta.get("hora_creacion", ""),
        "momento": momento_final,
        "momento_hora": momento_hora,
        "categoria_visual": categoria_visual,
        "energia": energia,
        "valor_narrativo": valor_narrativo,
        "confianza": f"{confianza:.2f}" if source else "",
        "tags": ", ".join(tags),
        "resolucion": meta.get("resolucion", ""),
        "codec": meta.get("codec", ""),
        "revisar_prioritario": meta.get("revisar_prioritario", "NO"),
    }


def write_csv(rows: list[dict], path: Path) -> None:
    rows.sort(key=lambda r: (r["camara"], r["hora_creacion"] or ""))
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def update_cache(cache: dict, visual_classifications: list) -> dict:
    for v in visual_classifications:
        sig = v.get("signature")
        if sig:
            cache[sig] = {
                "categoria": v.get("categoria", ""),
                "energia": v.get("energia", ""),
                "valor_narrativo": v.get("valor_narrativo", ""),
                "confianza": v.get("confianza", 0.0),
                "tags": v.get("tags", []),
                "razonamiento": v.get("razonamiento", ""),
            }
    return cache


def detect_suspicious_creation_time(rows: list[dict]) -> list[dict]:
    """
    Detecta clips donde el bracket horario sugiere noche pero los tags
    visuales sugieren día (o viceversa). Indica creation_time poco
    confiable (típico Sony Alpha cuando se reescribe el archivo).
    """
    suspects = []
    for r in rows:
        if not r.get("hora_creacion") or not r.get("tags"):
            continue
        tags = {t.strip() for t in r["tags"].split(",") if t.strip()}
        try:
            h = dt.datetime.fromisoformat(r["hora_creacion"]).hour
        except ValueError:
            continue
        is_night_by_hour = h >= 21 or h < 6
        is_day_by_hour = 7 <= h < 19
        has_dia_tags = bool(tags & TAGS_LUZ_DIA)
        has_noche_tags = bool(tags & TAGS_LUZ_NOCHE)
        if is_night_by_hour and has_dia_tags and not has_noche_tags:
            suspects.append({
                **r,
                "_motivo_sospecha": (
                    f"hora={h:02d}:00 (noche) pero tags visuales sugieren dia"
                ),
            })
        elif is_day_by_hour and has_noche_tags and not has_dia_tags:
            suspects.append({
                **r,
                "_motivo_sospecha": (
                    f"hora={h:02d}:00 (dia) pero tags visuales sugieren noche"
                ),
            })
    return suspects


def report(rows: list[dict], alert_threshold: float = 0.4) -> None:
    total = len(rows)
    sin_hora = sum(1 for r in rows if not r["hora_creacion"])
    prio = sum(1 for r in rows if r["revisar_prioritario"] == "SI")
    visual = sum(1 for r in rows if r["categoria_visual"])
    sin_clasif = sum(1 for r in rows if r["momento"] == "Sin clasificar")
    descartes = sum(1 for r in rows if "descarte" in r.get("tags", ""))

    # Override visual = momento != momento_hora cuando hay visual
    overrides = sum(
        1 for r in rows
        if r["categoria_visual"] and r["momento_hora"]
        and r["momento"] != r["momento_hora"]
    )
    base = sum(1 for r in rows if r["categoria_visual"] and r["momento_hora"])
    override_pct = overrides / base if base else 0

    dist = {}
    for r in rows:
        dist[r["momento"]] = dist.get(r["momento"], 0) + 1

    energia_dist = {}
    for r in rows:
        if r["energia"]:
            energia_dist[r["energia"]] = energia_dist.get(r["energia"], 0) + 1

    print()
    print(f"✓ CSV generado")
    print(f"  Total clips: {total}")
    print(f"  Con clasificación visual: {visual}")
    print(f"  Sin metadata de hora: {sin_hora}")
    print(f"  Sin clasificar: {sin_clasif}")
    print(f"  Clips prioritarios: {prio}")
    print()
    print("  Distribución por momento (visual + horario fusionados):")
    for k, v in sorted(dist.items(), key=lambda kv: -kv[1]):
        print(f"    {k}: {v}")
    if energia_dist:
        print()
        print("  Distribución por energía:")
        for k in ("alta", "media", "baja"):
            if k in energia_dist:
                print(f"    {k}: {energia_dist[k]}")

    # ===== Alertas v0.4.1 =====
    print()
    print("  --- Alertas ---")
    if base:
        line = (
            f"  Override visual: {override_pct*100:.0f}% "
            f"({overrides}/{base} clips visual ≠ horario)"
        )
        if override_pct >= alert_threshold:
            print(f"  ⚠ {line}")
            print(
                f"    → tu bracket horario probablemente está mal calibrado "
                f"para este evento."
            )
            print(
                f"    → re-correr con --brackets ajustado mejoraría la "
                f"señal del CSV."
            )
        else:
            print(line)
    if descartes:
        print(f"  ⚠ Clips con tag 'descarte': {descartes}")
        print(f"    → sugerir revisión manual antes de importar a FCP")
    suspects = detect_suspicious_creation_time(rows)
    if suspects:
        print(f"  ⚠ Clips con hora_creacion sospechosa: {len(suspects)}")
        print(f"    (luz visual no concuerda con bracket horario)")
        for s in suspects[:5]:
            print(f"      {s['archivo']} ({s['camara']}) — {s['_motivo_sospecha']}")
        if len(suspects) > 5:
            print(f"      ... y {len(suspects)-5} más")
        print(
            f"    → posible {chr(96)}creation_time{chr(96)} engañoso "
            f"(Sony Alpha tras copia/proceso). Validar visualmente."
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--metadata", type=Path, required=True)
    p.add_argument("--visual", type=Path, default=None)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--frames-dir", type=Path, default=None)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--keep-frames", action="store_true")
    p.add_argument("--alert-threshold", type=float, default=0.4,
                   help="Umbral de override visual para alerta (default 0.4)")
    args = p.parse_args()

    metadata = load_json(args.metadata, [])
    visual_list = load_json(args.visual, []) if args.visual else []
    cache = load_json(args.cache, {})

    visual_by_sig = {v["signature"]: v for v in visual_list if "signature" in v}

    rows = []
    for m in metadata:
        sig = m.get("signature")
        v = visual_by_sig.get(sig)
        cached = cache.get(sig) if sig else None
        rows.append(merge_one(m, v, cached))

    write_csv(rows, args.output)
    print(f"[ok] CSV escrito en {args.output}", file=sys.stderr)

    cache = update_cache(cache, visual_list)
    args.cache.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[ok] cache actualizado: {len(cache)} clips", file=sys.stderr)

    if args.frames_dir and args.frames_dir.exists() and not args.keep_frames:
        shutil.rmtree(args.frames_dir)
        print(f"[ok] frames temp eliminados de {args.frames_dir}", file=sys.stderr)

    report(rows, args.alert_threshold)


if __name__ == "__main__":
    main()