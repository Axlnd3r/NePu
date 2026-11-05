import { test } from "node:test";
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const { typed } = await import(pathToFileURL(join(here, "..", "src", "count.ts")).href);
const { scaleBins } = await import(pathToFileURL(join(here, "..", "src", "pulse.ts")).href);

test("typed text grows from empty to the full line", () => {
  assert.equal(typed("$ make proof", 0, 5, 1), "");
  assert.equal(typed("$ make proof", 8, 5, 1), "$ m");
  assert.equal(typed("$ make proof", 999, 5, 1), "$ make proof");
});

test("spectrum bins are log-scaled into 0..1", () => {
  const out = scaleBins([0, 1e-6, 0.001, 0.03, 1]);
  assert.ok(out.every((v) => v >= 0 && v <= 1), out.join());
  assert.equal(out[0], 0);
  assert.equal(out[4], 1);
  for (let i = 1; i < out.length; i += 1) assert.ok(out[i] >= out[i - 1]);
});
