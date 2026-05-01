---
description: Generates a valid FCPXML 1.13 for Final Cut Pro from a video classification CSV (with Keyword Collections across 6 dimensions — moment, camera, energy, narrative, tags, priority)
allowed-tools: Read, Write, Bash, Glob, AskUserQuestion
argument-hint: '[csv=path] [videos-root=path] [event="name"] [library=path] [keywords=full|basic]'
---

Activate the `fcpxml-from-classification` skill and begin the FCPXML generation workflow.

Parse any arguments provided in $ARGUMENTS:
- `csv=` → path to classification CSV (video-library-classifier 0.6+ format)
- `videos-root=` → root folder containing camera subfolders
- `event=` → FCP event name (e.g. "Wedding 15-02-2026")
- `library=` → path to .fcpbundle (default: ~/Movies/<event>.fcpbundle)
- `keywords=full|basic` → `full` (default) creates Keyword Collections for moment, camera, energy (1-5 descriptive), narrative value, tags, and priority. `basic` = moment+camera+priority only (v0.3 compat)

If arguments are missing, follow the skill's Step 1 to gather them via AskUserQuestion.

Then execute Steps 2 and 3 of the skill in full, including running the validator before delivering the file.
