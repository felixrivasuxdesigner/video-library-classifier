---
name: fcpxml-from-classification
description: >
  Genera un FCPXML listo para importar en Final Cut Pro 11/12.x a partir
  de un CSV de clasificación de video (formato video-library-classifier
  0.6+). Crea evento, Keyword Collections pobladas con rango válido
  en seis dimensiones: momento, cámara, energía (1-5 descriptiva),
  valor narrativo, tags y prioridad. Proyectos vacíos con nomenclatura
  estándar de wedding/evento. Dispara cuando el usuario pide: "generar
  FCPXML", "crear proyecto Final Cut desde CSV", "armar librería FCP
  con keywords", "importar clasificación a Final Cut", "hacer el fcpxml
  del matrimonio", "pasar de CSV a FCP", o trabaja con un CSV generado
  por video-library-classifier y quiere dar el siguiente paso hacia FCP.
version: 2.0.0
---

# FCPXML from Classification — Skill

## Overview

Toma un CSV de clasificación (formato del skill `video-library-classifier` 0.6+) y genera un **FCPXML 1.13** válido que al importar en Final Cut Pro:

1. Crea la librería (si no existe) y el evento.
2. Importa los clips apuntando a sus rutas reales.
3. Declara y **puebla** Keyword Collections en seis dimensiones:
   - **Moment** (Prep, Ceremony, Cocktail, Reception…)
   - **Camera** (Camera 1, Camera 2, Drone, Go Ultra…)
   - **Energy** — descriptive 1-5 scale:
     - `⚡ Atmospheric` (1) — detail shots, decor, empty landscapes
     - `⚡ Intimate` (2) — glances, hands, quiet preparation
     - `⚡ Social` (3) — guests chatting, greetings
     - `⚡ Celebration` (4) — first dance, hugs, toasts
     - `⚡ Ecstasy` (5) — intense party, jumping, confetti
   - **Narrative Value** — clip's function in the story:
     - `◆ Foundation` — speeches, vows (essential audio)
     - `◆ Candid` — spontaneous reactions
     - `◆ Epic` — high visual impact (drones, wide angle)
     - `◆ Filler` — b-roll without narrative weight
   - **Tags** (`# toast`, `# sunset`, `# first_dance`…) — filtered by allowlist
   - **Priority** (`★ Priority`)
4. Crea proyectos vacíos con la nomenclatura wedding estándar.

> 📌 **Bug histórico a evitar** (lee `references/fcpxml-spec-notes.md`):
> en FCPXML 1.10+, el `<keyword>` dentro de `<asset-clip>` requiere
> `start` y `duration`. Sin ellos, FCP parsea el XML sin error pero **no
> aplica los keywords** — las Keyword Collections quedan vacías.

> 📌 **Compat v0.3-0.4:** si el CSV tiene energía como string
> (`alta`/`media`/`baja`), se mapea automáticamente a la escala 1-5:
> baja→1 (Atmosférico), media→3 (Social), alta→5 (Éxtasis).
> Si no tiene columnas `energia`/`tags`/`valor_narrativo`, degrada a
> Keyword Collections básicas (momento+cámara+prioridad).

---

## Step 1 — Gather parameters

Si no están dados, preguntar con AskUserQuestion:

**1a. CSV de clasificación** — ruta al CSV generado por `video-library-classifier`. Columnas v0.6 esperadas:

```
archivo, camara, duracion_seg, hora_creacion, momento, momento_hora,
categoria_visual, energia, valor_narrativo, confianza, tags,
resolucion, codec, revisar_prioritario
```

- `energia`: integer 1-5 (v0.6+) o string "alta"/"media"/"baja" (v0.3-0.4)
- `valor_narrativo`: "Foundation"/"Candid"/"Epic"/"Filler" (v0.6+, puede faltar)

CSVs v0.3-0.4 (sin `valor_narrativo` o con energía como string) también funcionan — se mapean o ignoran las faltantes.

**1b. Carpeta raíz de los videos** — donde viven las subcarpetas `camara1/`, `camara2/`, `drone/`, etc.

**1c. Nombre del evento FCP** — default: nombre del matrimonio/evento.

**1d. Ruta de la librería FCP** — default: `/Users/<user>/Movies/<nombre-evento>.fcpbundle`.

**1e. Plantilla de proyectos** — ver `references/project-templates.md`. Default wedding:
- Película · 30 min
- Highlight · 5 min
- RRSS · 1 min

**1f. Modo de keywords** — `full` (default v0.4) o `basic` (compat v0.3). Solo preguntar si el usuario quiere comparar comportamiento entre versiones.

**1g. Allowlist de tags** — solo preguntar si el usuario menciona querer ver MÁS tags como Collections (default es una allowlist curada que evita ensuciar el sidebar de FCP con tags genéricos).

---

## Step 2 — Ejecutar el generador

Usar `references/fcpxml-generator.py` con los parámetros recolectados. El script:

1. Lee el CSV, detecta versión (v0.3, v0.4, v0.6+).
2. Corre `ffprobe` en paralelo (8 workers) para duración exacta, framerate, has_audio.
3. Agrupa formats únicos.
4. Genera UIDs estables con `uuid5(NAMESPACE_URL, archivo)`.
5. Parsea energía: integer 1-5 directo, o mapea legacy (baja→1, media→3, alta→5).
6. Parsea valor narrativo: Foundation/Candid/Epic/Filler (ignora si no existe).
7. Construye Keyword Collections en orden: momentos → cámaras → energías → narrativo → tags → prioridad.
8. Emite los `<keyword>` por clip con `start` y `duration` válidos.
9. Valida el output con ElementTree (ver `references/validation-checklist.md`).

**Validar después de generar:**
- `fcpxml version="1.13"`
- Todos los `<keyword>` tienen `start` y `duration`
- Duraciones normalizadas a `/30000s` cuando aplica
- Clips de drone con `hasAudio="0"` y sin `audioRole`
- `colorSpace="1-1-1 (Rec. 709)"` en formats

---

## Step 3 — Instrucciones al usuario para importar

```
Import en FCP 12.x:

1. Cerrar cualquier instancia abierta de Final Cut Pro.
2. Si existe librería previa con el mismo nombre, hacer backup
   (duplicar el .fcpbundle en Finder).
3. Abrir Final Cut Pro.
4. File → Import → XML…
5. Seleccionar el archivo .fcpxml generado.
6. En el diálogo: "Create New Library" si no existe, o seleccionar
   la existente para merge.
7. Esperar el import (~1-3 min para 250+ clips).
8. Verify Keyword Collections in sidebar:
   - Moments section (Prep, Cocktail, Reception…)
   - Cameras section
   - ⚡ Energy (Atmospheric, Intimate, Social, Celebration, Ecstasy)
   - ◆ Narrative Value (Foundation, Candid, Epic, Filler)
   - # Tags (toast, sunset, first_dance…)
   - ★ Priority
9. Transcode → Create Proxy Media cuando termine.
```

Para comparar versiones: el cliente puede importar un FCPXML v0.4 (3 niveles de energía, sin narrativo) y uno v0.6 (5 niveles + valor narrativo) y ver la diferencia en granularidad de filtrado en el sidebar.

---

## Important behaviors

- **Nunca inventar UIDs aleatorios cada corrida** — usar `uuid5` con el nombre del archivo.
- **Nunca omitir `start`/`duration`** en `<keyword>`.
- **Hacer ffprobe, no confiar en CSV para duraciones** — el CSV redondea a 1 decimal.
- **Validar con ElementTree** antes de entregar.
- **Tags allowlist por defecto**: filtra tags genéricos (`interior`, `exterior`, `dia`, `noche`) que ensucian FCP. El usuario puede pasar `--tags-allowlist all` si quiere ver TODOS los tags como Collections.
- **Unicode prefixes for visual grouping in FCP sidebar**:
  - Energy: `⚡ Atmospheric`, `⚡ Intimate`, `⚡ Social`, `⚡ Celebration`, `⚡ Ecstasy`
  - Narrative: `◆ Foundation`, `◆ Candid`, `◆ Epic`, `◆ Filler`
  - Tags: `# toast`, `# sunset`…
  - Priority: `★ Priority`
- **Backwards compat v0.3-0.4**: script detects energy format (integer vs string) and maps automatically. If `valor_narrativo` column doesn't exist, that dimension is simply skipped.
- **Collection order in sidebar**: Moments → Cameras → ⚡ Energy → ◆ Narrative → # Tags → ★ Priority.
