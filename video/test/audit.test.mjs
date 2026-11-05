import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const videoDir = join(here, "..");
const load = (f) => import(pathToFileURL(join(videoDir, "src", f)).href);

const { videoData } = await load("data.ts");
const c = await load("copy.ts");
const sources = JSON.parse(readFileSync(join(videoDir, "src", "data.sources.json"), "utf8"));

// Identifiers and names, not figures: removed before tokenising.
const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const IDENTIFIERS = [/\$1(?!\d)/g, /1Click/g, /Top 5/g, new RegExp(escape(c.shortHash(videoData.proof.manifestSha256)), "g")];

// Every way the video renders a sourced number or date.
// Only the values a scene can show: everything except the plotted days, of which only the last one is
// labelled. Formats are the ones copy.ts uses, so a typed figure has little chance of matching by luck.
const shown = sources.filter(({ key }) => !/\[\d+\]/.test(key) || /\[89\]/.test(key));

// How each sourced number is allowed to appear on screen, by key. An unknown key may only appear as itself.
const FORMATS = [
  [/^hero\.crUsd30$/, (v) => [(v * 100).toFixed(0)]],
  [/^cr\[\d+\]\.cr(30|90)$/, (v) => [v.toFixed(3)]],
  [/^(issuance|buyback|burn)\[\d+\]$/, (v) => [c.formatCompact(v).replace(/[kM]$/, "")]],
  [/^breakeven\.(volumeUsdPerDay|vStarUsdPerDay)$/, (v) => [(v / 1e6).toFixed(1)]],
  [/^breakeven\.multiple$/, (v) => [v.toFixed(1)]],
  [/^proof\.blockHeight$/, (v) => [c.formatInt(v)]],
  [/^cards\.distribution\.hhiChannel$/, (v) => [v.toFixed(2)]],
  [/^cards\.distribution\.top5ChannelShare$/, (v) => [(v * 100).toFixed(0)]],
  [/^cards\.valuation\.inflation$/, (v) => [(v * 100).toFixed(1)]],
  [/^cards\.valuation\.breakevenVolumeUsdPerDay$/, (v) => [(v / 1e6).toFixed(1)]],
  [/^cards\.developer\.share1$/, (v) => [(v * 100).toFixed(0)]],
];
const renderings = new Set();
for (const { key, value: v } of shown) {
  if (typeof v === "string") {
    v.split(/\D+/).filter(Boolean).forEach((t) => renderings.add(t));
  } else {
    renderings.add(String(v));
    for (const [pattern, fn] of FORMATS) if (pattern.test(key)) fn(v).forEach((t) => renderings.add(t));
  }
}

// Numeric tokens of a text that no sourced value renders to.
const unsourced = (texts) =>
  texts.flatMap((raw) => {
    const text = IDENTIFIERS.reduce((t, id) => t.replace(id, " "), raw);
    return (text.match(/\d[\d,.]*/g) ?? []).map((t) => t.replace(/[,.]+$/, "")).filter((t) => !renderings.has(t));
  });

test("every number in the video's text traces to a sourced value", () => {
  const texts = c.sceneTexts(videoData);
  assert.ok(texts.length >= 15);
  assert.deepEqual(unsourced(texts), []);
});

test("the audit rejects figures nobody sourced", () => {
  assert.deepEqual(unsourced(["13 cents back", "at 1.5% inflation", "7.5x today's volume", "block 123,456"]), ["13", "1.5", "7.5", "123,456"]);
});

test("npm run data is idempotent for unchanged JSON", () => {
  const tmp = mkdtempSync(join(tmpdir(), "nepu-audit-"));
  try {
    execFileSync("node", [join(videoDir, "scripts", "build-data.mjs"), "--out", tmp], { cwd: videoDir });
    for (const f of ["data.ts", "data.sources.json"]) {
      assert.equal(readFileSync(join(tmp, f), "utf8"), readFileSync(join(videoDir, "src", f), "utf8"), f);
    }
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test("no placeholder is left unfilled in the video's text", () => {
  for (const raw of c.sceneTexts(videoData)) assert.doesNotMatch(raw, /[{}]/, raw);
});
