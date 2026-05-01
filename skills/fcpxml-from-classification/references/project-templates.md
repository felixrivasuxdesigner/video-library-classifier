# FCP Project Templates by Production Type

When generating the FCPXML, include empty projects (sequences) that reflect typical deliverables for the production type. This gives the editor a base structure without creating it manually.

## Wedding

**Default:**

| Project name | Sequence duration | Purpose |
|---|---|---|
| Feature Film · 30 min | 1800s | Long deliverable, full memory |
| Highlight · 5 min | 300s | Emotional summary for sharing |
| Social Teaser · 1 min | 60s | Vertical or square reel for Instagram |

**Avoid** names like "Compilation", "Long Summary" — they sound academic, not wedding.

**Acceptable alternatives** if the user wants variety:

- Wedding Film · 30 min
- The Film · 30 min
- Long Form · 30 min
- Full Story · 30 min

## Quinceañera / XV

| Name | Duration |
|---|---|
| Feature Film · 20 min | 1200s |
| Highlight · 3 min | 180s |
| Social Teaser · 1 min | 60s |

## Corporate Event

| Name | Duration |
|---|---|
| Corporate Video · 5 min | 300s |
| After Movie · 2 min | 120s |
| Testimonials · variable | 600s |
| Social Teaser · 30 sec | 30s |

## Concert / Live Show

| Name | Duration |
|---|---|
| Full Concert · ~90 min | 5400s |
| Show Highlight · 3 min | 180s |
| Multicam Master | variable |

## Documentary (multi-day)

One project per day/destination:

| Name | Duration |
|---|---|
| Day 1 · [location] | variable |
| Day 2 · [location] | variable |
| Final Cut · 20 min | 1200s |

## Travel

| Name | Duration |
|---|---|
| Long Form · 5 min | 300s |
| Vertical Reel · 30 sec | 30s |

## Reference sequence format

All sequences by default:

```xml
<sequence duration="{DURATION}" format="r1" tcStart="0s" tcFormat="NDF"
          audioLayout="stereo" audioRate="48k">
  <spine/>
</sequence>
```

For vertical social (9:16), add an additional format:

```xml
<format id="r-vertical" name="FFVideoFormat1080x1920p2997"
        frameDuration="1001/30000s" fieldOrder="progressive"
        width="1080" height="1920" colorSpace="1-1-1 (Rec. 709)"/>
```
