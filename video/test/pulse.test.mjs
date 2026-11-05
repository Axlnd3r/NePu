import { test } from "node:test";
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const { pulseFromSpectrum } = await import(pathToFileURL(join(here, "..", "src", "pulse.ts")).href);

test("empty spectrum gives no pulse", () => {
  assert.equal(pulseFromSpectrum([]), 0);
});

test("energy in the low quarter of the bins is the pulse", () => {
  assert.equal(pulseFromSpectrum([1, 1, 0, 0, 0, 0, 0, 0]), 1);
});

test("energy only in the upper bins gives no pulse", () => {
  assert.equal(pulseFromSpectrum([0, 0, 1, 1, 1, 1, 1, 1]), 0);
});

test("pulse is clamped to 1", () => {
  assert.equal(pulseFromSpectrum([2, 2, 2, 2]), 1);
});
