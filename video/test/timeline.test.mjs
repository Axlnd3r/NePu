import { test } from "node:test";
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const { FPS, TOTAL, SCENES } = await import(pathToFileURL(join(here, "..", "src", "timeline.ts")).href);

test("scene ranges are those of the spec and contiguous", () => {
  assert.equal(FPS, 30);
  assert.equal(TOTAL, 1350);
  assert.deepEqual(
    SCENES.map((s) => [s.id, s.from, s.from + s.frames]),
    [
      ["issuance", 0, 150],
      ["capture", 150, 300],
      ["coverage", 300, 540],
      ["hero", 540, 780],
      ["breakeven", 780, 990],
      ["proof", 990, 1200],
      ["outro", 1200, 1350],
    ],
  );
});

test("the cover frame is after the count-up and before the Developer card, and package.json uses it", async () => {
  const { COVER_FRAME, SCENES, CARD_APPEAR } = await import(pathToFileURL(join(here, "..", "src", "timeline.ts")).href);
  const hero = SCENES.find((s) => s.id === "hero");
  assert.ok(COVER_FRAME >= hero.from + 126, "count-up (36 + 90 frames) has finished");
  assert.ok(COVER_FRAME < hero.from + CARD_APPEAR.developer, "Developer card has not appeared");
  const pkg = JSON.parse((await import("node:fs")).readFileSync(join(here, "..", "package.json"), "utf8"));
  assert.ok(pkg.scripts.still.includes(`--frame=${COVER_FRAME}`), pkg.scripts.still);
});

test("transitions overlap scenes without changing where each scene starts or the 1350-frame total", async () => {
  const { SCENES, TOTAL, TRANSITION_FRAMES, TRANSITIONS, sequenceFrames } = await import(pathToFileURL(join(here, "..", "src", "timeline.ts")).href);
  assert.equal(TRANSITIONS.length, SCENES.length - 1);
  assert.ok(TRANSITIONS.every((t) => ["slide-right", "slide-up", "wipe", "iris", "zoom"].includes(t)), TRANSITIONS.join());
  const seq = SCENES.map((_, i) => sequenceFrames(i));
  assert.equal(seq.reduce((a, b) => a + b, 0) - TRANSITIONS.length * TRANSITION_FRAMES, TOTAL);
  // TransitionSeries starts sequence i at the sum of earlier sequences minus the earlier transitions
  SCENES.forEach((s, i) => {
    const start = seq.slice(0, i).reduce((a, b) => a + b, 0) - i * TRANSITION_FRAMES;
    assert.equal(start, s.from, s.id);
  });
});
