import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "src");
const readme = readFileSync(join(here, "..", "..", "README.md"), "utf8");
const load = (f) => import(pathToFileURL(join(src, f)).href);

const { videoData } = await load("data.ts");
const { proofLines, shortHash, formatInt, displayUrl, copy } = await load("copy.ts");

const proof = { ...videoData.proof };

test("scene files exist", () => {
  for (const f of ["scenes/Proof.tsx", "scenes/Outro.tsx"]) assert.ok(existsSync(join(src, f)), f);
});

test("proof text takes the OpenTimestamps status from the data, for pending and confirmed", () => {
  const pending = proofLines({ ...proof, otsStatus: "pending" }).join("\n");
  const confirmed = proofLines({ ...proof, otsStatus: "confirmed" }).join("\n");
  assert.match(pending, /OpenTimestamps: pending/);
  assert.match(confirmed, /OpenTimestamps: confirmed/);
  assert.doesNotMatch(confirmed, /pending/);
});

test("every proof line that shows the hash or the block names the network", () => {
  const lines = proofLines(proof);
  const shown = lines.filter((l) => l.includes(shortHash(proof.manifestSha256)) || l.includes(formatInt(proof.blockHeight)));
  assert.ok(shown.length >= 1);
  for (const l of shown) assert.ok(l.includes(proof.network), l);
});

test("the first proof line is the command that commits, the last is the OpenTimestamps status", () => {
  const lines = proofLines(proof);
  assert.equal(lines[0], "$ make proof");
  assert.match(lines.at(-1), /^OpenTimestamps: /);
});

test("proof narration says committed, not proven, and names the network from the data", () => {
  assert.ok(copy.proof.includes("{network}"));
  assert.doesNotMatch(copy.proof, /proven/i);
  assert.match(copy.proof, /committed on NEAR/);
});

test("formatInt and displayUrl", () => {
  assert.equal(formatInt(276017917), "276,017,917");
  assert.equal(displayUrl("https://example.io/NePu/"), "example.io/NePu");
});

test("links come from the README", () => {
  const dashboard = readme.match(/\*\*Live dashboard:\*\*\s+(https:\/\/\S+)/)[1];
  const repo = readme.match(/https:\/\/github\.com\/[\w-]+\/[\w-]+/)[0];
  assert.equal(videoData.links.dashboard, dashboard);
  assert.equal(videoData.links.repo, repo);
});
