# Production Types — Moment Schemas & Visual Vocabularies

This file defines two things per production type:

1. **Temporal schema**: time brackets → event moment. Used by the hour-based heuristic classification (fallback).
2. **Closed visual vocabulary**: list of categories Claude can assign after viewing frames. Prevents the model from inventing new categories on each run.

When the script or skill applies the schema, read the section matching the production type selected by the user.

---

## Wedding

### Time brackets (local timezone)

| Local time  | Moment    |
| ----------- | --------- |
| 06:00–14:30 | Prep      |
| 14:30–17:00 | Ceremony  |
| 17:00–20:00 | Cocktail  |
| 20:00–06:00 | Reception |

### Energy Scale (1-5)

1. **Atmospheric**: Detail shots, decor, architecture, empty landscapes.
2. **Intimate**: Glances, hands, quiet preparation, private moments.
3. **Social**: Guests chatting, polite greetings, walking.
4. **Celebration**: Ceremony exit, first dance, strong hugs, toasts.
5. **Ecstasy**: Intense party, jumping, screaming, confetti, sparklers, max action.

### Narrative Value (Archetypes)

- **Foundation**: Speeches, vows, interviews (clips with essential audio).
- **Candid**: Spontaneous reactions, laughter, tears.
- **Epic**: High visual impact shots (drone, complex camera movements).
- **Filler**: Necessary b-roll without emotional weight.

### Closed visual vocabulary
Main category (`categoria` in CSV):
`Prep`, `Ceremony`, `Cocktail`, `Reception`, `Details`, `Drone`, `Unclassified`.


### Suggested free tags (not mandatory, not exhaustive)

`bride`, `groom`, `parents`, `rings`, `dress`, `altar`, `church`, `venue`, `dancefloor`, `table`, `cake`, `bouquet`, `entrance`, `first_dance`, `speech`, `sunset`, `night`, `day`, `interior`, `exterior`, `photographer`, `kids`.

Claude can add others if the scene warrants it. Keep tags lowercase and singular.

---

## Quinceañera / XV

### Time brackets

| Local time  | Moment   |
| ----------- | -------- |
| 12:00–18:00 | Prep     |
| 18:00–19:30 | Entrance |
| 19:30–21:00 | Waltz    |
| 21:00–06:00 | Party    |

### Closed visual vocabulary

```
Prep
Entrance
Waltz
Party
Details
Drone
Unclassified
```

### Energy

```
5 (Ecstasy)     → waltz with standing crowd, dancing, MCs on dancefloor
3 (Social)      → solemn entrance, toasts, dinner
1 (Atmospheric) → prep, static decor
```

---

## Corporate Event

### Time brackets

| Local time  | Moment   |
| ----------- | -------- |
| 06:00–09:00 | Setup    |
| 09:00–10:00 | Opening  |
| 10:00–17:00 | Sessions |
| 17:00–22:00 | Closing  |

### Closed visual vocabulary

```
Setup
Opening
Keynote
Sessions
Networking
Closing
Details
Drone
Unclassified
```

### Energy

```
5 (Ecstasy)     → audience applauding, active networking, heated panel
3 (Social)      → presenter on stage, attentive audience, workshop
1 (Atmospheric) → empty room, technical setup, branding details
```

---

## Concert / Live Show

### Time brackets

| Local time  | Moment     |
| ----------- | ---------- |
| 12:00–18:00 | Soundcheck |
| 18:00–20:30 | Opening    |
| 20:30–23:00 | Show       |
| 23:00–04:00 | Closing    |

### Closed visual vocabulary

```
Soundcheck
Opening
Show
Closing
Backstage
Audience
Drone
Unclassified
```

### Energy

```
5 (Ecstasy)     → lit stage, crowd jumping, band playing intensely
3 (Social)      → between songs, band talking to crowd, calm audience
1 (Atmospheric) → empty soundcheck, setup, empty post-show
```

---

## Documentary (multi-day)

No time brackets. Classification is by **date** (`Day 1`, `Day 2`, etc.) plus context-dependent visual vocabulary.

### Closed visual vocabulary (generic)

```
Interview
B-roll
Location
Character
Action
Detail
Drone
Unclassified
```

### Energy

```
5 (Ecstasy)     → action, movement, crowds
3 (Social)      → active interview, observation
1 (Atmospheric) → landscape, detail, empty location
```

---

## Travel

Same as documentary, but classifies by **destination** (`Santiago`, `Valparaíso`, etc.) instead of days. User defines destinations at classification start.

### Closed visual vocabulary

```
Arrival
Exploration
Food
Location
Characters
Detail
Drone
Unclassified
```

### Energy

```
5 (Ecstasy)     → travel movement, crowds, market
3 (Social)      → walking exploration, food at table
1 (Atmospheric) → static landscape, detail, hotel
```

---

## Global Rules for Claude Classification

1. **`categoria` must belong to the closed vocabulary of the production type.** If the scene doesn't fit any, return `Unclassified` — never invent a new category.
2. **`energia`** is always an integer 1-5. Use the full scale; don't cluster everything at 3.
3. **`valor_narrativo`** is always one of: `Foundation`, `Candid`, `Epic`, `Filler`.
4. **`confianza`** is a float between 0.0 and 1.0. If the image is ambiguous, dark, out of focus, or shows a transition, lower confidence.
5. **`tags`** is an array of short strings (1-2 words) in lowercase and singular. Min 0, max 8 per clip. Free tags but coherent with the visible scene.
6. **`Drone`** overrides any temporal category when the shot is clearly aerial. Set `categoria: "Drone"` and add the temporal category as a tag (e.g. `tags: ["aerial", "ceremony", "exterior"]`).
7. **`Details`** overrides the temporal category when it's a short static insert (rings, decor, hanging dress, plated food).
8. If the clip seems like a recording error (camera pointing at floor, no subject, completely black), return `categoria: "Unclassified"`, `confianza: 0.1`, `tags: ["discard"]`.
