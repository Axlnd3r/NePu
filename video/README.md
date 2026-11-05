# NePu demo video

A 45-second Remotion video for X that tells the NePu story with on-screen text, the repo's real charts
and a music track whose beat drives the visuals. It lives apart from the Python and Next.js builds:
nothing here is part of `make all`, and the repo still builds offline without it.

## Where every number comes from
`scripts/build-data.mjs` reads `site/public/data/*.json` and `data/proof.json` and writes
`src/data.ts` plus `src/data.sources.json` (one JSON pointer per value). Scenes take figures only from
`data.ts` and words only from `src/copy.ts` (placeholders such as `{cents}`, no digits). Tests
(`npm test`) check that each value equals its source, that scene files contain no typed figures, and
that every number in the video's text traces to a sourced value.

Choices that follow from the data:
- Charts end on the latest day where all plotted fields exist (2026-10-31, because 2026-11-01 has no
  buyback or coverage value yet), over 90 days.
- The break-even scene uses one basis only: the "today" step of `summary.json` (levers), the same
  one the README quotes.
- The Valuation card shows only the reverse-valuation volume. Scenario probabilities from
  `valuation.json` are conditional model output, so they never enter `data.ts`.
- Distribution figures are shares of 1Click volume (the Explorer covers 1Click only).
- The proof is named with its network (testnet) and the OpenTimestamps status exactly as recorded.
- The issuance line is plotted raw. Its spikes (about 1.3x the median, every 2 to 5 days) are in the data; the cause was not investigated and nothing is smoothed.

## Rebuild
```bash
make build                 # from the repo root: refresh site/public/data/*.json
cd video && npm install
npm test                   # data checks, scene rules, audio check, number audit
npm run render:16x9        # out/nepu-demo-16x9.mp4 (1920x1080)
npm run render:1x1         # out/nepu-demo-1x1.mp4 (1080x1080)
npm run still              # out/cover.png (frame where the count-up has finished)
npm run dev                # Remotion Studio preview
```
`render:*` regenerate `src/data.ts` and check the music track first.

## Music
`public/audio/nepu-theme.m4a`: 48 s instrumental made with Higgsfield (`sonilo_music`, prompt:
"Calm minimal instrumental electronic track, soft pulsing bass and gentle plucked synth, clear steady
beat, restrained and confident, data-driven mood, no vocals", 3 credits). `npm run check:audio` fails if
it is missing or shorter than 45 s. The bass energy of the track (`pulseFromSpectrum`) brightens the card
borders and thickens the chart lines.

## Motion
- Behind every scene: a drifting hairline grid, a slow champagne glow and rising dust (`Backdrop`), a slow
  push-in per scene (`CameraPush`) and a music visualizer strip along the bottom (`Visualizer`, audio
  only, no figures). The glow, particles, card borders and chart lines follow the bass.
- Scene changes use `@remotion/transitions` (slide, wipe, iris and a zoom that dips through the
  background); every sequence but the last runs 15 frames longer, so scenes still start on the same
  frames and the total stays 1350.
- Narration words rise out of a blur; key words are drawn in the accent colour with an underline.
- Charts draw with a dot at the head and a ticker that shows the actual data point under it; the
  Capture chart shades the gap between issuance and buybacks, the Coverage chart draws an arrow to
  parity. The break-even marker's label is the multiple of today's volume at the marker's position, so
  it ends exactly on the narrated multiple. The proof lines type out with check marks; the NEAR mark
  assembles from scattered tiles.

## Layout
- `src/timeline.ts` scene frame ranges (30 fps, 1350 frames); `src/Demo.tsx` sequences them.
- `src/scenes/` one component per scene; `src/components/` shared pieces (narration, glass card, chart).
- `src/theme.ts` palette copied from `site/app/globals.css`.
