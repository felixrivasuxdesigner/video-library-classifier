# Visual Classification Prompt — Literal Instructions for Claude

This is the contract Claude follows when consuming `_visual_manifest.json`.

---

## Classification Procedure (Wedding v2)

### 1. Energy Scale (Rhythm Detection)
Evaluate movement and emotional intensity in frames (1-5):
- **1 (Atmospheric)**: Static shots of objects, flowers, rings, architecture.
- **2 (Intimate)**: Couple whispering, intertwined hands, subtle tears, quiet prep.
- **3 (Social)**: People talking, seated toasts, guests walking.
- **4 (Celebration)**: Loud laughter, couple dancing, effusive hugs, church exit.
- **5 (Ecstasy)**: Full dancefloor, jumping, confetti, sparklers, unbridled action.

### 2. Narrative Value (Archetypes)
Identify the clip's function in the story:
- **Foundation**: Visible speeches, vow reading, interviews.
- **Candid**: Spontaneous genuine reactions (not posed).
- **Epic**: Visually stunning shots (drones, wide angle, epic movements).
- **Filler**: B-roll (people eating, walking without narrative purpose).

---

## Strict JSON Schema

```json
{
  "signature": "<copy>",
  "archivo": "<copy>",
  "categoria": "<Prep|Ceremony|Cocktail|Reception|Details|Drone|Unclassified>",
  "energia": 1|2|3|4|5,
  "valor_narrativo": "<Foundation|Candid|Epic|Filler>",
  "confianza": 0.0-1.0,
  "tags": ["lowercase", "singular", "max 8"],
  "razonamiento": "<one short sentence>"
}
```

---

## Golden Rules
- **Energy 5** must be reserved for max-action moments (party).
- **Narrative Value "Candid"** is priority for the Highlight.
- If you see a **Drone** with a clearly aerial shot, use `categoria: "Drone"` and put the real moment in `tags`.
- If the clip is a short insert of an object, use `categoria: "Details"`.
