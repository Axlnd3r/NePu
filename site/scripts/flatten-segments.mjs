// Work around a Windows-only bug in `next build` with output: "export" (Next.js 16.4.3).
//
// The exporter names each prefetch segment file `__next<segmentPath with "/" -> ".">.txt`, but it
// builds segmentPath with path.relative(), which uses "\" on Windows. The "\" survives the
// replacement and path.join() turns it into a folder: out/token/__next.token/__PAGE__.txt instead
// of out/token/__next.token.__PAGE__.txt, which is what the client router requests
// (next/dist/export/index.js collectSegmentPaths; client/components/segment-cache/cache.js).
// This moves every file under a `__next.*` folder to the flat name. On Linux and macOS there are
// no such folders and nothing happens.
import { readdirSync, renameSync, rmSync, statSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const out = join(dirname(fileURLToPath(import.meta.url)), "..", "out");

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}

function walk(dir) {
  let moved = 0;
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (!statSync(path).isDirectory()) continue;
    if (name.startsWith("__next.")) {
      for (const file of files(path)) {
        const flat = [name, ...relative(path, file).split(sep)].join(".");
        renameSync(file, join(dir, flat));
        moved += 1;
      }
      rmSync(path, { recursive: true });
    } else if (name !== "_next") {
      moved += walk(path);
    }
  }
  return moved;
}

const moved = walk(out);
console.log(`flatten-segments: ${moved} segment file(s) renamed`);
