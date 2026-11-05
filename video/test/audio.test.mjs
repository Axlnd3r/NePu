import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const videoDir = join(here, "..");
const script = join(videoDir, "scripts", "check-audio.mjs");
const track = join(videoDir, "public", "audio", "nepu-theme.m4a");

const run = (...args) => spawnSync("node", [script, ...args], { cwd: videoDir, encoding: "utf8" });

test("check-audio fails with a message when the file is missing", () => {
  const r = run("--file", join(videoDir, "public", "audio", "does-not-exist.mp3"));
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /missing/i);
});

test("check-audio fails when the track is shorter than the minimum", () => {
  assert.ok(existsSync(track), "track must exist for this check");
  const r = run("--file", track, "--min", "9999");
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /shorter/i);
});

test("the shipped track is at least 45 seconds", () => {
  assert.ok(existsSync(track));
  assert.ok(statSync(track).size > 100_000, "file looks too small to be a 45 s track");
  const r = run();
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /\d+(\.\d+)? s/);
});
