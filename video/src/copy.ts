// Narration words and number formatting. No figure is written here: placeholders like {cents}
// are filled from data.ts, so every number on screen traces to a JSON field.
export type SceneId = "issuance" | "capture" | "coverage" | "hero" | "breakeven" | "proof" | "outro";

export const copy: Record<SceneId, string> = {
  issuance: "NEAR issues new tokens every day.",
  capture: "NEAR Intents fees buy some back.",
  coverage: "So: does capture outgrow issuance?",
  hero: "Today: {cents} cents back for every $1 issued.",
  breakeven: "Not yet. Capture needs {multiple}x today's volume.",
  proof: "Every input is hashed and committed on NEAR {network}.",
  outro: "Evidence, not conviction.",
};

export const formatCents = (cr: number): string => String(Math.round(cr * 100));
export const formatMultiple = (x: number): string => x.toFixed(1);
export const formatMillions = (usd: number): string => `$${(usd / 1e6).toFixed(1)}M`;
export const shortHash = (h: string): string => `${h.slice(0, 8)}…${h.slice(-6)}`;
export const formatCompact = (n: number): string =>
  n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : String(Math.round(n));
export const formatRatio = (r: number): string => r.toFixed(3);
export const formatPercent = (x: number, digits = 0): string => `${(x * 100).toFixed(digits)}%`;

type Cards = {
  distribution: { month: string; hhiChannel: number; top5ChannelShare: number };
  valuation: { horizonYears: number; inflation: number; basis: string; breakevenVolumeUsdPerDay: number };
  developer: { cohort: string; cohortSize: number; share1: number };
};
export type CardText = { title: string; value: string; caption: string };

// Words for the three small cards. Valuation shows only the reverse-valuation volume, never scenario odds.
export const cardTexts = (c: Cards): Record<keyof Cards, CardText> => ({
  distribution: {
    title: "Distribution Map",
    value: `HHI ${c.distribution.hhiChannel.toFixed(2)}`,
    caption: `Top 5 channels carry ${formatPercent(c.distribution.top5ChannelShare)} of 1Click volume (${c.distribution.month})`,
  },
  valuation: {
    title: "Valuation Lab",
    value: `${formatMillions(c.valuation.breakevenVolumeUsdPerDay)} per day`,
    caption: `Volume needed to cover issuance at ${formatPercent(c.valuation.inflation, 1)} inflation, ${c.valuation.basis} basis, ${c.valuation.horizonYears}-year horizon`,
  },
  developer: {
    title: "Developer indicator",
    value: `${formatPercent(c.developer.share1)} still used`,
    caption: `Of ${c.developer.cohortSize} new contracts deployed in ${c.developer.cohort}, called again the next month`,
  },
});

export const formatInt = (n: number): string => n.toLocaleString("en-US");
export const displayUrl = (url: string): string => url.replace(/^https?:\/\//, "").replace(/\/$/, "");

type ProofData = { network: string; contract: string; blockHeight: number; manifestSha256: string; otsStatus: string };

// Lines of the proof scene. The network is named on every line that shows the hash or the block, and the
// OpenTimestamps status is whatever data/proof.json says (never assumed).
export const proofLines = (p: ProofData): string[] => [
  "$ make proof",
  `manifest ${shortHash(p.manifestSha256)} committed on NEAR ${p.network}`,
  `contract ${p.contract} · block ${formatInt(p.blockHeight)} · NEAR ${p.network}`,
  `OpenTimestamps: ${p.otsStatus}`,
];

export const fillCopy = (text: string, vars: Record<string, string>): string =>
  text.replace(/\{(\w+)\}/g, (match, key: string) => vars[key] ?? match);

type SceneData = {
  windows: { mid: number; long: number };
  hero: { crUsd30: number; date: string };
  breakeven: { multiple: number; volumeUsdPerDay: number; vStarUsdPerDay: number; asOf: string };
  proof: ProofData;
  cards: Cards;
};

// Every string with a figure in it that the scenes render, so the audit can check each figure's source.
export const sceneTexts = (d: SceneData): string[] => [
  copy.issuance,
  copy.capture,
  copy.coverage,
  `coverage ratio, ${d.windows.mid}d`,
  `coverage ratio, ${d.windows.long}d`,
  fillCopy(copy.hero, { cents: formatCents(d.hero.crUsd30) }),
  `${formatCents(d.hero.crUsd30)}¢`,
  `${d.windows.mid} days to ${d.hero.date}`,
  fillCopy(copy.breakeven, { multiple: formatMultiple(d.breakeven.multiple) }),
  formatMillions(d.breakeven.volumeUsdPerDay),
  formatMillions(d.breakeven.vStarUsdPerDay),
  `as of ${d.breakeven.asOf}`,
  fillCopy(copy.proof, { network: d.proof.network }),
  ...proofLines(d.proof),
  copy.outro,
  ...Object.values(cardTexts(d.cards)).flatMap((card) => [card.title, card.value, card.caption]),
];
