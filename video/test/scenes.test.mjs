import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "src");
const read = (rel) => readFileSync(join(src, rel), "utf8");

// Scene files may only reach figures through data/copy/theme/components/pulse (rule 1).
const ALLOWED_IMPORT = /^(remotion|react|\.\.\/(data|copy|theme|pulse|count|timeline)|\.\.\/components\/[A-Za-z]+|\.\/[A-Za-z]+)$/;
const sceneFiles = () => (existsSync(join(src, "scenes")) ? readdirSync(join(src, "scenes")).filter((f) => f.endsWith(".tsx")) : []);
const mustExist = ["Issuance.tsx", "Capture.tsx", "Coverage.tsx"];

test("scenes 1-3 exist", () => {
  for (const f of mustExist) assert.ok(existsSync(join(src, "scenes", f)), f);
});

test("scene files import only from the allowed modules", () => {
  for (const f of sceneFiles()) {
    for (const m of read(`scenes/${f}`).matchAll(/from\s+"([^"]+)"/g)) {
      assert.match(m[1], ALLOWED_IMPORT, `${f} imports ${m[1]}`);
    }
  }
});

test("scene and component files have no digits in JSX text or Narration text props", () => {
  const files = [...sceneFiles().map((f) => `scenes/${f}`), ...readdirSync(join(src, "components")).map((f) => `components/${f}`)];
  for (const rel of files.filter((f) => f.endsWith(".tsx"))) {
    const text = read(rel);
    // A JSX tag's ">" has no space or "=" before it and its text has no ; = ( ) or braces, which skips
    // arrow functions, comparisons and generics.
    for (const m of text.matchAll(/(?<![\s=])>([^<>{}();=]*\d[^<>{}();=]*)</g)) assert.fail(`${rel}: digit in JSX text "${m[1].trim()}"`);
    for (const m of text.matchAll(/\btext="([^"]*\d[^"]*)"/g)) assert.fail(`${rel}: digit in text prop "${m[1]}"`);
  }
});

test("formatCompact and formatRatio label chart values", async () => {
  const { formatCompact, formatRatio } = await import(pathToFileURL(join(src, "copy.ts")).href);
  assert.equal(formatCompact(88123), "88.1k");
  assert.equal(formatCompact(1234567), "1.2M");
  assert.equal(formatCompact(950), "950");
  assert.equal(formatCompact(7969), "8.0k");
  assert.equal(formatRatio(0.1202), "0.120");
});

test("scene files do not type window lengths (they come from data.windows)", () => {
  for (const f of sceneFiles()) {
    assert.doesNotMatch(read(`scenes/${f}`), /\b\d+\s*(d|days)\b/, f);
  }
});

// A figure typed into a literal: a digit next to a word, in a string, a template, or a JSX text run.
// CSS values (units, functions, hex colours) are skipped.
const CSS = /[\d.]+(?:px|em|rem|vw|vh|ms|s|deg)\b|translateY|translate|rgba|rgb|drop-shadow|solid|blur|tabular-nums/g;
// Percentages are CSS only inside a gradient or a bare value ("100%"); in prose ("2.5% inflation") they are figures.
const CSS_PERCENT = /[\d.]+%/g;
const isCssText = (text) => /gradient\(/.test(text) || /^[\s\d.%-]*$/.test(text);
const typedFigures = (source) => {
  const hits = [];
  const literals = [...source.matchAll(/"([^"\n]*)"|`([^`\n]*)`/g)].map((m) => m[1] ?? m[2]);
  // After a tag's ">" (no space or "=" before it, so not a comparison or arrow) or after a "}".
  // A run stays on one line, so a multi-line style object after "}" is not mistaken for text.
  const jsxRuns = [...source.matchAll(/(?<=(?<![\s=])>|\})([^<>{}();=\n]*\d[^<>{}();=\n]*)(?=[<{])/g)].map((m) => m[1]);
  for (const text of [...literals, ...jsxRuns]) {
    const noVars = text.replace(/\$\{[^}]*\}/g, "");
    const bare = (isCssText(noVars) ? noVars.replace(CSS_PERCENT, "") : noVars).replace(CSS, "").replace(/#[0-9a-fA-F]{3,8}/g, "");
    // Phrases only: a single token (a file name, an id, a colour) is not narration.
    if (/\d/.test(bare) && /[A-Za-z]{3,}/.test(bare) && /\s/.test(bare.trim())) hits.push(text.trim());
  }
  return hits;
};

test("the typed-figure check catches what the older checks missed", () => {
  assert.equal(typedFigures('<Card label="at 2.5% inflation" />').length, 1);
  assert.equal(typedFigures('names={["gross 2026 issuance"]}').length, 1);
  assert.equal(typedFigures("<div>Source · 30 days to {x}</div>").length, 1);
  assert.equal(typedFigures('style={{ border: "1px solid red", transform: `translateY(${y}px)` }}').length, 0);
});

test("scene and component files type no figure inside a literal", () => {
  const files = [...sceneFiles().map((f) => `scenes/${f}`), ...readdirSync(join(src, "components")).map((f) => `components/${f}`)];
  for (const rel of files.filter((f) => f.endsWith(".tsx"))) assert.deepEqual(typedFigures(read(rel)), [], rel);
});

test("chart end labels fit the label column at 1:1", () => {
  for (const f of sceneFiles()) {
    const m = read(`scenes/${f}`).match(/names=\{\[([^\]]*)\]\}/);
    if (!m) continue;
    for (const s of [...m[1].matchAll(/"([^"]*)"|`([^`]*)`/g)].map((x) => (x[1] ?? x[2]).replace(/\$\{[^}]*\}/g, "30"))) {
      assert.ok(s.length <= 20, `${f}: "${s}" is ${s.length} chars`);
    }
  }
});

test("text sizes and card dwell are readable at feed size", async () => {
  const { theme } = await import(pathToFileURL(join(src, "theme.ts")).href);
  const { SCENES, CARD_APPEAR, MIN_CARD_DWELL } = await import(pathToFileURL(join(src, "timeline.ts")).href);
  assert.ok(theme.size.caption >= 0.015 && theme.size.source >= 0.015, "small text too small");
  const frames = Object.fromEntries(SCENES.map((s) => [s.id, s.frames]));
  const sceneOf = { distribution: "coverage", developer: "hero", valuation: "breakeven" };
  for (const [card, at] of Object.entries(CARD_APPEAR)) {
    assert.ok(frames[sceneOf[card]] - at >= MIN_CARD_DWELL, `${card} card is on screen ${frames[sceneOf[card]] - at} frames`);
  }
});
