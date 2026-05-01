# FCPXML — notas del DTD y bugs históricos

## Versión a usar

| Final Cut Pro | FCPXML version |
|---|---|
| 10.6.6 | 1.11 |
| 11.0 | 1.12 |
| 11.1+ | 1.13 |
| 12.x | 1.13 (y lee 1.14+ si existe) |

**Default: `1.13`.** Es compatible hacia atrás con FCP 11.1 y nativo en
FCP 12.x. No uses 1.10 o 1.11 a menos que el usuario corra una versión
antigua de FCP — en ese caso degrada.

## El bug del `<keyword>` sin rango

Apple declara en el DTD de FCPXML 1.10+:

```dtd
<!ATTLIST keyword  start     %time;  #IMPLIED>
<!ATTLIST keyword  duration  %time;  #REQUIRED>
<!ATTLIST keyword  value     CDATA   #REQUIRED>
<!ATTLIST keyword  note      CDATA   #IMPLIED>
```

`duration` es **REQUIRED**. Si el `<keyword>` va dentro de un
`<asset-clip>` o `<clip>` y NO tiene `start` + `duration`, FCP:

1. Parsea el XML sin mostrar error.
2. Importa los clips correctamente.
3. **No aplica los keywords a ningún rango.**
4. Las `<keyword-collection>` declaradas a nivel de evento quedan
   visibles en el sidebar pero vacías.

### Forma correcta

```xml
<asset-clip ref="a1" name="C4355.MP4" start="0s"
            duration="240240/30000s" format="r1" audioRole="dialogue">
  <keyword start="0s" duration="240240/30000s" value="Reception"/>
  <keyword start="0s" duration="240240/30000s" value="Camera 1"/>
  <keyword start="0s" duration="240240/30000s" value="⚡ Celebration"/>
  <keyword start="0s" duration="240240/30000s" value="◆ Candid"/>
  <keyword start="0s" duration="240240/30000s" value="# toast"/>
</asset-clip>
```

El `start` y `duration` del keyword deben cubrir el rango del clip
donde aplican.

## Formato de tiempos

Todos los tiempos en FCPXML son fracciones racionales de segundo:

```
"1001/30000s"      → 33.367 ms (1 frame a 29.97)
"240240/30000s"    → 8.008s (240 frames a 29.97)
"300s"             → 5 min
```

**Normalizar al denominador 30000** cuando trabajes con 29.97 fps.

## Audio opcional (drones)

La mayoría de MP4 de DJI no tiene pista de audio. Declarar `hasAudio="0"` y omitir `audioSources`/`audioChannels`/`audioRate`. En el `<asset-clip>` correspondiente, **no incluir** `audioRole="dialogue"`.

## Color space

Para clips Rec. 709 SDR (típico Sony Alpha, DJI estándar, GoPro flat):

```xml
colorSpace="1-1-1 (Rec. 709)"
```

## UIDs estables entre corridas

Usar `uuid.uuid5(uuid.NAMESPACE_URL, archivo_name)` para que el UID sea determinista. Esto permite reimportar el mismo FCPXML y que FCP detecte los assets como existentes (merge, no duplica).

**No usar `uuid4()`** — cada corrida genera UIDs distintos y FCP duplica los clips.

## Conventions v0.6 — Unicode prefixes and dimensions

FCP sidebar groups Keyword Collections by Unicode prefix for instant recognition:

- **Energy** (descriptive 1-5 scale):
  - `⚡ Atmospheric` (1) — detail shots, decor, empty landscapes
  - `⚡ Intimate` (2) — glances, hands, quiet preparation
  - `⚡ Social` (3) — guests chatting, greetings
  - `⚡ Celebration` (4) — first dance, hugs, toasts
  - `⚡ Ecstasy` (5) — intense party, jumping, confetti

- **Narrative Value** (clip's editing function):
  - `◆ Foundation` — speeches, vows, interviews (essential audio)
  - `◆ Candid` — genuine spontaneous reactions
  - `◆ Epic` — high visual impact (drones, wide angle)
  - `◆ Filler` — b-roll without narrative weight

- **Tags**: `# toast`, `# sunset`, `# first_dance`
- **Priority**: `★ Priority`

### Collection order in sidebar

Declaration order in the FCPXML determines sidebar order:
Moments → Cameras → ⚡ Energy → ◆ Narrative → # Tags → ★ Priority

### Backwards compatibility (CSVs v0.3-0.4)

If the CSV has `energia` as string (`alta`/`media`/`baja`), it maps:
- `baja` → 1 (Atmospheric)
- `media` → 3 (Social)
- `alta` → 5 (Ecstasy)

If `valor_narrativo` column doesn't exist, that Keyword Collection dimension is simply skipped.

## Estructura mínima válida

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.13">
  <resources>
    <format id="r1" .../>
    <asset id="a1" ...>
      <media-rep kind="original-media" src="file:///..."/>
    </asset>
  </resources>
  <library location="file:///.../.fcpbundle/">
    <event name="...">
      <keyword-collection name="..."/>
      <asset-clip ref="a1" ...>
        <keyword start="..." duration="..." value="..."/>
      </asset-clip>
      <project name="...">
        <sequence duration="..." format="r1" tcStart="0s" tcFormat="NDF"
                  audioLayout="stereo" audioRate="48k">
          <spine/>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
```

El orden importa: `<resources>` antes de `<library>`, y dentro de `<event>` las `<keyword-collection>` antes de los `<asset-clip>`.
