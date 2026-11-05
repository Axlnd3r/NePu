import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "src");
const readme = readFileSync(join(here, "..", "..", "README.md"), "utf8");
const results = readme.split("<!-- results:start -->")[1].split("<!-- results:end -->")[0];
const load = (f) => import(pathToFileURL(join(src, f)).href);

const { videoData } = await load("data.ts");
const copyMod = await load("copy.ts");
const { copy, formatCents, formatMultiple, formatMillions, formatPercent, cardTexts } = copyMod;

test("scene and card files exist and Coverage carries the Distribution card", () => {
  for (const f of ["scenes/Hero.tsx", "scenes/BreakEven.tsx", "components/MiniCard.tsx", "count.ts"]) {
    assert.ok(existsSync(join(src, f)), f);
  }
  assert.match(readFileSync(join(src, "scenes", "Coverage.tsx"), "utf8"), /MiniCard/);
});

test("count-up starts at 0, ends at the target, never decreases", async () => {
  const { countUp } = await load("count.ts");
  assert.equal(countUp(12, 0, 30, 90), 0);
  assert.equal(countUp(12, 999, 30, 90), 12);
  let prev = 0;
  for (let f = 0; f <= 200; f += 1) {
    const v = countUp(12, f, 30, 90);
    assert.ok(v >= prev, `frame ${f}`);
    prev = v;
  }
});

test("the hero count-up ends on the cents the README results block states", async () => {
  const { countUp } = await load("count.ts");
  const end = countUp(Number(formatCents(videoData.hero.crUsd30)), 999, 30, 90);
  assert.match(results, new RegExp(`\\*\\*${end} cents\\*\\*`));
});

test("break-even figures match the README results block", () => {
  const { multiple, volumeUsdPerDay, vStarUsdPerDay } = videoData.breakeven;
  assert.ok(results.includes(`${formatMultiple(multiple)}x`));
  assert.ok(results.includes(formatMillions(volumeUsdPerDay)));
  assert.ok(results.includes(formatMillions(vStarUsdPerDay)));
});

test("cents are on the USD basis, the one summary.json's own sentence uses", () => {
  const sentence = JSON.parse(readFileSync(join(here, "..", "..", "site", "public", "data", "summary.json"), "utf8")).hero.sentence;
  assert.ok(sentence.includes(`${formatCents(videoData.hero.crUsd30)} cents`), sentence);
});

test("break-even narration says Not yet before any figure, and the multiple is a level, not an increase", () => {
  assert.ok(copy.breakeven.startsWith("Not yet."));
  assert.doesNotMatch(copy.breakeven, /more volume/);
  assert.match(copy.breakeven, /today's volume/);
});

test("formatPercent", () => {
  assert.equal(formatPercent(0.025, 1), "2.5%");
  assert.equal(formatPercent(0.3126), "31%");
});

test("cards: valuation names its basis and never reads as a forecast", () => {
  const t = cardTexts(videoData.cards);
  assert.ok(t.valuation.caption.includes(videoData.cards.valuation.basis));
  assert.ok(t.valuation.value.includes(formatMillions(videoData.cards.valuation.breakevenVolumeUsdPerDay)));
  for (const card of Object.values(t)) {
    assert.doesNotMatch(`${card.title} ${card.value} ${card.caption}`, /probab|forecast|predict|target|moon/i);
  }
});

test("cards: distribution and developer figures come from the data", () => {
  const t = cardTexts(videoData.cards);
  assert.ok(t.distribution.caption.includes(formatPercent(videoData.cards.distribution.top5ChannelShare)));
  assert.ok(t.distribution.caption.includes(videoData.cards.distribution.month));
  assert.ok(t.developer.value.includes(formatPercent(videoData.cards.developer.share1)));
  assert.ok(t.developer.caption.includes(videoData.cards.developer.cohort));
});

test("the break-even marker label ends on the multiple the narration states", () => {
  const { volumeUsdPerDay, vStarUsdPerDay, multiple } = videoData.breakeven;
  const share = volumeUsdPerDay / vStarUsdPerDay;
  assert.equal(formatMultiple(1 / share), formatMultiple(multiple));
});
