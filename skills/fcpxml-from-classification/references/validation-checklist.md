# Validation checklist antes de entregar el FCPXML

Correr siempre este chequeo con ElementTree antes de entregar el archivo al usuario. Si falla alguno, FCP no va a aplicar los keywords y el trabajo queda mal hecho.

## Script de validación

```python
import xml.etree.ElementTree as ET

def validate_fcpxml(path):
    tree = ET.parse(path)
    root = tree.getroot()

    # 1. Versión
    version = root.get("version")
    assert version == "1.13", f"version debe ser 1.13, es {version}"

    # 2. Un asset-clip por asset
    assets = list(root.iter("asset"))
    clips = list(root.iter("asset-clip"))
    assert len(clips) == len(assets), (
        f"mismatch: {len(assets)} assets vs {len(clips)} asset-clips"
    )

    # 3. Keywords con start + duration (el bug histórico)
    keywords = list(root.iter("keyword"))
    sin_rango = [
        k for k in keywords
        if not k.get("start") or not k.get("duration")
    ]
    assert not sin_rango, (
        f"{len(sin_rango)} keywords sin start/duration — FCP los ignoraría"
    )

    # 4. Cada asset-clip tiene al menos 1 keyword
    clips_sin_kw = [c for c in clips if not list(c.iter("keyword"))]
    if clips_sin_kw:
        print(f"[warn] {len(clips_sin_kw)} asset-clips sin keywords")

    # 5. Cada asset referenciado por un asset-clip existe
    asset_ids = {a.get("id") for a in assets}
    for clip in clips:
        ref = clip.get("ref")
        assert ref in asset_ids, f"clip ref={ref} no apunta a asset válido"

    # 6. <media-rep> con src file:// válido
    for asset in assets:
        mr = asset.find("media-rep")
        assert mr is not None, f"asset {asset.get('id')} sin media-rep"
        src = mr.get("src")
        assert src and src.startswith("file://"), (
            f"media-rep src inválido: {src}"
        )

    # 7. hasAudio="0" no debe tener audioRole en asset-clip
    no_audio_assets = {
        a.get("id") for a in assets if a.get("hasAudio") == "0"
    }
    for clip in clips:
        if clip.get("ref") in no_audio_assets:
            assert not clip.get("audioRole"), (
                f"clip {clip.get('name')} sin audio no debe tener audioRole"
            )

    print(f"✓ FCPXML 1.13 válido")
    print(f"  {len(assets)} assets, {len(clips)} clips, {len(keywords)} keywords")
    print(f"  {len(no_audio_assets)} assets sin audio")
```

## Report v0.4 después de validar

```
✓ FCPXML generado: matrimonio-21-02-2026.fcpxml
  Total clips:     257
  Total keywords:  1240 (todos con rango válido)

  Keyword Collections:
    Momentos:
      Preparativos:        21 clips
      Ceremonia:           42 clips
      Cóctel:              39 clips
      Recepción:          155 clips
    Cámaras:
      Cámara 1:            75 clips
      Cámara 2:           150 clips
      Drone:               28 clips
      Go Ultra:             4 clips
    Energía:
      ⚡ alta:              98 clips
      ⚡ media:            122 clips
      ⚡ baja:              37 clips
    Tags (visual):
      # vals:              12 clips
      # brindis:           18 clips
      # atardecer:          9 clips
      # ramo:               4 clips
      ...
    ★ Prioritario:         16 clips

  Proyectos creados:
    Película · 30 min
    Highlight · 5 min
    RRSS · 1 min

Listo para File → Import → XML en Final Cut Pro.
```

## Anti-patrones a vigilar

- `<keyword value="X"/>` sin atributos → keyword fantasma, FCP lo ignora
- `<format>` faltante o mal referenciado → FCP rechaza el import entero
- UIDs generados con `uuid4()` → crea duplicados si se reimporta
- `audioRate="48000"` (debe ser `48k`) → FCP puede rechazar
- `duration="240240/1s"` (denominador incorrecto) → clips de horas de duración
- `hasAudio="1"` en asset sin pista de audio → FCP muestra warnings
- `file://` omitido en src → import falla
- Barras `\` en paths → debe ser `/` en URIs
- En modo `--keywords full`, asset-clip sin keyword de energía cuando el CSV sí trae el campo → bug de filtrado, revisar
