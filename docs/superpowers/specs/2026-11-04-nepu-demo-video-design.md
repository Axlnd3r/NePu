# NePu demo video for X: design

Date: 2026-11-04. Status: draft for review.

## Goal
A ~45 s video for X that shows what NePu is for: it answers the falsifiable question "can NEAR
Intents value capture outgrow token issuance?" with real charts from the repo, honestly ("Not yet").
Audience: crypto/NEAR readers on X and the NEAR HACKATHON 2026 judges (track Investment Thesis).

## Constraints
- Hard rule 1: every number on screen comes from `site/public/data/*.json` or `data/proof.json`,
  read by a generator script. No number is typed by hand.
- Hard rule 7: no price predictions or targets. Hard rule 8: all text in English.
- The proof is always shown with its network name (testnet) and the OpenTimestamps status as
  recorded in `data/proof.json` (currently "pending"; never claim a Bitcoin confirmation that is
  not in the file).
- The video must read without sound (most X autoplay is muted): the narration is on-screen text.
- Higgsfield is used for the music track and, only if needed, text-free atmosphere plates. No text
  or numbers inside AI-generated images. Credit cost is shown (`higgsfield generate cost`) before
  anything is generated.
- Nothing in `video/` is part of `make all`; the repo still builds offline from a clean clone.

## Look and feel
- Narration: one large sentence per beat, words entering in turn (reference: Pinterest pin
  "Control your emotions", one idea per beat).
- Cards: translucent glass cards on a dark background (reference: anico.studio "Stats & Data
  Animation"), in the dashboard's dark champagne palette and with the pixel NEAR mark, so the
  video and the site look like one product.
- Music-visual: one instrumental track (~45 s, no vocals). Remotion reads its spectrum
  (`@remotion/media-utils`) and drives subtle line/particle/card-edge pulses.

## Scenes
Values are read at build time; the figures in the last column are the current snapshot values and
are listed here only to show what each scene will display.

| Time | Narration text | Data shown | Source field |
|---|---|---|---|
| 0-5 s | NEAR issues new tokens every day. | Daily gross issuance, last 90 d | `coverage.series[].issuance_gross_near` |
| 5-10 s | NEAR Intents fees buy some back. | Buyback and burn lines catching up | `series[].buyback_near`, `burnt_near` |
| 10-18 s | So: does capture outgrow issuance? | CR 30d and 90d line | `series[].cr_float_30`, `cr_float_90` |
| 18-26 s | Today: 12 cents back for every $1 issued. | Count-up of CR_float 30d (to 2026-10-31) | `summary.hero` |
| 26-33 s | Not yet. Capture needs 7.6x today's volume. | Break-even meter, $130.4M vs $989.9M per day | `summary.levers.steps[0]` |
| 33-40 s | Every input is hashed and committed on NEAR testnet. | `make proof`, manifest SHA-256, contract and block | `data/proof.json` |
| 40-45 s | Evidence, not conviction. | Logo, dashboard URL, repo URL | README |

Cards for Distribution Map, Valuation Lab and the developer indicator appear briefly between the
data scenes (not as scenes of their own), taking their numbers from `distribution.json`,
`valuation.json` and `developer.json`.

Basis rule: scene 5 uses one basis only, the "today" step of `summary.levers` (the same one the
README quotes). It must not mix it with `coverage.v_star` (a different tau basis) in the same frame;
if both ever appear, each carries its label.

## Architecture
- `video/` is a standalone Remotion project (own `package.json`, not part of `site/` or `src/`).
- `video/scripts/build-data.mjs` reads the JSON files and writes `video/src/data.ts`. Components
  import from it and never contain figures. The script fails if a required field is missing.
- `video/src/` holds one component per scene plus shared `Narration`, `GlassCard`, `AudioPulse`.
- `video/public/audio/` holds the Higgsfield track; `video/public/ai/` any atmosphere plates.
- Outputs in `video/out/` (gitignored): `nepu-demo-16x9.mp4`, `nepu-demo-1x1.mp4`, a cover PNG.

## Verification
- Number audit: a script extracts every number rendered in the final frames' source (the data.ts
  values) and checks each one maps to a JSON field; the build fails otherwise. The `verify-numbers`
  skill is run on the final text.
- Render both formats, then inspect still frames at each scene boundary (no text clipped at 1:1,
  nothing unreadable at X's typical feed size).
- Re-run `make build` before generating `data.ts` so the video reflects the current snapshot.

## Open items (decided during implementation, not blocking this spec)
- Whether Higgsfield is signed in and the credit balance (`higgsfield account`).
- Exact track prompt (mood: calm, minimal, data-driven) after seeing the cost.
- Whether to commit `video/` to this repo or keep it local; default is to commit source, not outputs.
