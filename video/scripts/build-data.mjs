// Reads the built dashboard JSON and data/proof.json and writes src/data.ts plus
// src/data.sources.json (one JSON pointer per value). Every figure in the video comes from here.
// Usage: node scripts/build-data.mjs [--data DIR] [--proof FILE] [--out DIR]
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const videoDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const repo = join(videoDir, "..");

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
);
const dataDir = args.data ?? join(repo, "site", "public", "data");
const proofFile = args.proof ?? join(repo, "data", "proof.json");
const outDir = args.out ?? join(videoDir, "src");
const readmeFile = args.readme ?? join(repo, "README.md");
const WINDOW_DAYS = 90;

const docs = {};
const load = (name) => {
  if (!docs[name]) {
    const path = name === "proof.json" ? proofFile : join(dataDir, name);
    docs[name] = JSON.parse(readFileSync(path, "utf8"));
  }
  return docs[name];
};

const sources = [];
const esc = (part) => String(part).replace(/~/g, "~0").replace(/\//g, "~1");

// Walks the pointer; fails naming the first missing or null step.
const need = (file, pointer) => {
  let node = load(file);
  let walked = "";
  for (const part of pointer.split("/").slice(1)) {
    walked += `/${part}`;
    if (node == null || node[part] == null) throw new Error(`missing field ${file}#${walked}`);
    node = node[part];
  }
  return node;
};

// Reads a value and records where it came from.
const pick = (key, file, pointer) => {
  const value = need(file, pointer);
  sources.push({ key, file, pointer, value });
  return value;
};

const series = (key, file, rows, field) => rows.map(({ index, date }, j) => ({
  date,
  value: pick(`${key}[${j}]`, file, `/series/${index}/${field}`),
}));

try {
  // One shared window: the latest date where every plotted field exists, then 90 rows back.
  const rows = need("coverage.json", "/series");
  const fields = ["issuance_gross_near", "buyback_near", "burnt_near", "cr_float_30", "cr_float_90"];
  let end = rows.length - 1;
  while (end >= 0 && fields.some((f) => rows[end][f] == null)) end -= 1;
  if (end < WINDOW_DAYS - 1) throw new Error("missing field coverage.json#/series (fewer than 90 complete days)");
  const window = rows.slice(end - WINDOW_DAYS + 1, end + 1).map((r, j) => ({ index: end - WINDOW_DAYS + 1 + j, date: r.date }));

  const crSeries = window.map(({ index, date }, j) => ({
    date,
    cr30: pick(`cr[${j}].cr30`, "coverage.json", `/series/${index}/cr_float_30`),
    cr90: pick(`cr[${j}].cr90`, "coverage.json", `/series/${index}/cr_float_90`),
  }));

  const step = "/levers/steps/0";
  const months = need("distribution.json", "/periods/month");
  const dMonth = months.findLastIndex((m) => m.complete === true);
  const cohorts = need("developer.json", "/cohorts");
  const cohort = cohorts.findLastIndex((c) => c.complete === true && c.share_1 != null);
  const vRows = need("valuation.json", "/reverse/rows");
  const vRow = vRows.findLastIndex((r) => r.horizon_years === 1 && r.inflation === 0.025 && r.basis === "buyback");
  if (dMonth < 0) throw new Error("missing field distribution.json#/periods/month (no complete month)");
  if (cohort < 0) throw new Error("missing field developer.json#/cohorts (no complete cohort with share_1)");
  if (vRow < 0) throw new Error("missing field valuation.json#/reverse/rows (1-year buyback row)");
  const multiple = need("summary.json", "/levers/steps/0/volume_multiple");
  if (multiple <= 1) throw new Error(`break-even multiple ${multiple} is not above 1: the "Not yet." narration no longer applies; change copy.breakeven before rendering`);

  const readme = readFileSync(readmeFile, "utf8");
  const dashboard = readme.match(/\*\*Live dashboard:\*\*\s+(https:\/\/\S+)/)?.[1];
  const repoUrl = readme.match(/https:\/\/github\.com\/[\w-]+\/[\w-]+/)?.[0];
  if (!dashboard) throw new Error("missing field README.md#live-dashboard");
  if (!repoUrl) throw new Error("missing field README.md#repository-url");

  const videoData = {
    issuance: series("issuance", "coverage.json", window, "issuance_gross_near"),
    buyback: series("buyback", "coverage.json", window, "buyback_near"),
    burn: series("burn", "coverage.json", window, "burnt_near"),
    cr: crSeries,
    hero: {
      date: pick("hero.date", "summary.json", "/hero/date"),
      cr30: pick("hero.cr30", "summary.json", "/hero/cr_float_30"),
      // "cents per dollar" is the USD basis, the one summary.json's own sentence uses
      crUsd30: pick("hero.crUsd30", "summary.json", "/hero/cr_float_usd_30"),
    },
    breakeven: {
      asOf: pick("breakeven.asOf", "summary.json", "/levers/as_of"),
      volumeUsdPerDay: pick("breakeven.volumeUsdPerDay", "summary.json", "/levers/volume_usd_per_day"),
      vStarUsdPerDay: pick("breakeven.vStarUsdPerDay", "summary.json", `${step}/v_star_usd_per_day`),
      multiple: pick("breakeven.multiple", "summary.json", `${step}/volume_multiple`),
    },
    proof: {
      network: pick("proof.network", "proof.json", "/near/network"),
      contract: pick("proof.contract", "proof.json", "/near/contract"),
      txHash: pick("proof.txHash", "proof.json", "/near/tx_hash"),
      blockHeight: pick("proof.blockHeight", "proof.json", "/near/block_height"),
      manifestSha256: pick("proof.manifestSha256", "proof.json", "/manifest_sha256"),
      otsStatus: pick("proof.otsStatus", "proof.json", "/opentimestamps/status"),
      runId: pick("proof.runId", "proof.json", "/run_id"),
    },
    links: { dashboard, repo: repoUrl },
    windows: {
      mid: pick("windows.mid", "coverage.json", "/windows/1"),
      long: pick("windows.long", "coverage.json", "/windows/2"),
    },
    cards: {
      distribution: {
        month: pick("cards.distribution.month", "distribution.json", `/periods/month/${dMonth}/period`),
        hhiChannel: pick("cards.distribution.hhiChannel", "distribution.json", `/periods/month/${dMonth}/hhi_channel`),
        top5ChannelShare: pick("cards.distribution.top5ChannelShare", "distribution.json", `/periods/month/${dMonth}/top5_channel_share`),
      },
      valuation: {
        horizonYears: pick("cards.valuation.horizonYears", "valuation.json", `/reverse/rows/${vRow}/horizon_years`),
        inflation: pick("cards.valuation.inflation", "valuation.json", `/reverse/rows/${vRow}/inflation`),
        basis: pick("cards.valuation.basis", "valuation.json", `/reverse/rows/${vRow}/basis`),
        breakevenVolumeUsdPerDay: pick("cards.valuation.breakevenVolumeUsdPerDay", "valuation.json", `/reverse/rows/${vRow}/breakeven_volume_usd_per_day`),
      },
      developer: {
        cohort: pick("cards.developer.cohort", "developer.json", `/cohorts/${cohort}/cohort`),
        cohortSize: pick("cards.developer.cohortSize", "developer.json", `/cohorts/${cohort}/cohort_size`),
        share1: pick("cards.developer.share1", "developer.json", `/cohorts/${cohort}/share_1`),
      },
    },
  };

  mkdirSync(outDir, { recursive: true });
  writeFileSync(
    join(outDir, "data.ts"),
    `// Generated by scripts/build-data.mjs from site/public/data and data/proof.json. Do not edit.\nexport const videoData = ${JSON.stringify(videoData, null, 2)};\nexport type VideoData = typeof videoData;\n`,
  );
  writeFileSync(join(outDir, "data.sources.json"), `${JSON.stringify(sources, null, 1)}\n`);
  console.log(`wrote data.ts and data.sources.json (${sources.length} sourced values, window to ${window.at(-1).date})`);
} catch (err) {
  console.error(err.message);
  process.exit(1);
}
