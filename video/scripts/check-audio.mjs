// Fails (non-zero exit) when the music track is missing or shorter than the video needs.
// Usage: node scripts/check-audio.mjs [--file PATH] [--min SECONDS]
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { ALL_FORMATS, FilePathSource, Input } from "mediabunny";

const videoDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
);
const file = args.file ?? join(videoDir, "public", "audio", "nepu-theme.m4a");
const min = Number(args.min ?? 45);

if (!existsSync(file)) {
  console.error(`audio file missing: ${file}`);
  process.exit(1);
}

const input = new Input({ source: new FilePathSource(file), formats: ALL_FORMATS });
const seconds = await input.computeDuration();
if (seconds < min) {
  console.error(`track is shorter than ${min} s (${seconds.toFixed(1)} s): ${file}`);
  process.exit(1);
}
console.log(`track ${seconds.toFixed(1)} s (minimum ${min} s): ${file}`);
