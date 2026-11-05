import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const videoDir = join(here, "..");
const repo = join(videoDir, "..");
const dataDir = join(repo, "site", "public", "data");
const script = join(videoDir, "scripts", "build-data.mjs");

const readJson = (p) => JSON.parse(readFileSync(p, "utf8"));
const summary = () => readJson(join(dataDir, "summary.json"));
const fileOf = (name) =>
  name === "proof.json" ? join(repo, "data", "proof.json") : join(dataDir, name);
const resolvePointer = (doc, pointer) =>
  pointer
    .split("/")
    .slice(1)
    .reduce((node, part) => node[part.replace(/~1/g, "/").replace(/~0/g, "~")], doc);

const loadData = async () => {
  const mod = await import(pathToFileURL(join(videoDir, "src", "data.ts")).href);
  return mod.videoData;
};
const loadCopy = () => import(pathToFileURL(join(videoDir, "src", "copy.ts")).href);

test("data.ts hero.cr30 equals summary.hero.cr_float_30", async () => {
  execFileSync("node", [script], { cwd: videoDir });
  const data = await loadData();
  assert.equal(data.hero.cr30, summary().hero.cr_float_30);
  assert.equal(data.hero.date, summary().hero.date);
  assert.equal(data.hero.crUsd30, summary().hero.cr_float_usd_30);
});

test("breakeven equals summary.levers.steps[0]", async () => {
  const data = await loadData();
  const { levers } = summary();
  assert.equal(data.breakeven.multiple, levers.steps[0].volume_multiple);
  assert.equal(data.breakeven.vStarUsdPerDay, levers.steps[0].v_star_usd_per_day);
  assert.equal(data.breakeven.volumeUsdPerDay, levers.volume_usd_per_day);
  assert.equal(data.breakeven.asOf, levers.as_of);
});

test("distribution card uses the last month with complete === true", async () => {
  const data = await loadData();
  const months = readJson(join(dataDir, "distribution.json")).periods.month;
  const last = months.filter((m) => m.complete === true).at(-1);
  assert.equal(data.cards.distribution.month, last.period);
  assert.equal(data.cards.distribution.hhiChannel, last.hhi_channel);
  assert.notEqual(data.cards.distribution.month, months.at(-1).period, "incomplete month must be skipped");
});

test("developer card uses the last complete cohort whose share_1 is observed", async () => {
  const data = await loadData();
  const cohorts = readJson(join(dataDir, "developer.json")).cohorts;
  const last = cohorts.filter((c) => c.complete === true && c.share_1 !== null).at(-1);
  assert.notEqual(last.cohort, cohorts.filter((c) => c.complete).at(-1).cohort, "newest complete cohort has no month +1 yet");
  assert.equal(data.cards.developer.cohort, last.cohort);
  assert.equal(data.cards.developer.cohortSize, last.cohort_size);
  assert.equal(data.cards.developer.share1, last.share_1);
});

test("valuation card is the 1-year buyback-basis reverse row", async () => {
  const data = await loadData();
  const row = readJson(join(dataDir, "valuation.json")).reverse.rows.find(
    (r) => r.horizon_years === 1 && r.inflation === 0.025 && r.basis === "buyback",
  );
  assert.equal(data.cards.valuation.breakevenVolumeUsdPerDay, row.breakeven_volume_usd_per_day);
  assert.equal(data.cards.valuation.basis, "buyback");
});

test("data.ts carries no scenario probabilities", () => {
  const text = readFileSync(join(videoDir, "src", "data.ts"), "utf8");
  assert.doesNotMatch(text, /p_cr_ge_1|scenarios|fan/);
});

test("proof block comes from data/proof.json", async () => {
  const data = await loadData();
  const proof = readJson(join(repo, "data", "proof.json"));
  assert.equal(data.proof.network, proof.near.network);
  assert.equal(data.proof.manifestSha256, proof.manifest_sha256);
  assert.equal(data.proof.otsStatus, proof.opentimestamps.status);
  assert.equal(data.proof.blockHeight, proof.near.block_height);
});

test("series cover 90 days and end on non-null values", async () => {
  const data = await loadData();
  for (const key of ["issuance", "buyback", "burn", "cr"]) {
    assert.equal(data[key].length, 90, key);
  }
  assert.ok(data.cr.every((p) => typeof p.cr30 === "number" && typeof p.cr90 === "number"));
});

test("build-data exits non-zero and names the pointer when a field is missing", () => {
  const tmp = mkdtempSync(join(tmpdir(), "nepu-video-"));
  try {
    cpSync(dataDir, tmp, { recursive: true });
    const broken = readJson(join(tmp, "summary.json"));
    delete broken.hero;
    writeFileSync(join(tmp, "summary.json"), JSON.stringify(broken)); // the copy only
    const run = spawnSync("node", [script, "--data", tmp, "--out", tmp], { encoding: "utf8" });
    assert.notEqual(run.status, 0);
    assert.match(run.stderr, /summary\.json#\/hero/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test("every data.sources.json entry resolves to its value in the named file", () => {
  const sources = readJson(join(videoDir, "src", "data.sources.json"));
  assert.ok(sources.length > 0);
  for (const s of sources) {
    const actual = resolvePointer(readJson(fileOf(s.file)), s.pointer);
    assert.equal(actual, s.value, `${s.key} -> ${s.file}#${s.pointer}`);
  }
});

test("copy.ts strings contain no digit except the literal $1", async () => {
  const { copy } = await loadCopy();
  for (const [id, text] of Object.entries(copy)) {
    assert.doesNotMatch(text.replaceAll("$1", ""), /\d/, id);
  }
});

test("formatters and shortHash", async () => {
  const { formatCents, formatMultiple, formatMillions, shortHash } = await loadCopy();
  assert.equal(formatCents(0.1202), "12");
  assert.equal(formatMultiple(7.5906), "7.6");
  assert.equal(formatMillions(130406943.67), "$130.4M");
  assert.equal(
    shortHash("48c59060cee309e2aafb62614dfb24454828bf5ae8f534bd52154165b5b8c096"),
    "48c59060…b8c096",
  );
});

test("window lengths come from coverage.json windows", async () => {
  const data = await loadData();
  const windows = readJson(join(dataDir, "coverage.json")).windows;
  assert.equal(data.windows.mid, windows[1]);
  assert.equal(data.windows.long, windows[2]);
});

test("build-data refuses to render 'Not yet.' when the break-even multiple is not above 1", () => {
  const tmp = mkdtempSync(join(tmpdir(), "nepu-video-"));
  try {
    cpSync(dataDir, tmp, { recursive: true });
    const doc = readJson(join(tmp, "summary.json"));
    doc.levers.steps[0].volume_multiple = 0.8;
    writeFileSync(join(tmp, "summary.json"), JSON.stringify(doc));
    const run = spawnSync("node", [script, "--data", tmp, "--out", tmp], { encoding: "utf8" });
    assert.notEqual(run.status, 0);
    assert.match(run.stderr, /Not yet/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});
