// Screenshots of dashboard sections for README.md, taken from the built site (site/out).
// Run: node qa/readme-shots.mjs (after make site). Writes docs/media/readme/*.png.
import { createReadStream, existsSync, mkdirSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const out = join(root, "site", "out");
const dest = join(root, "docs", "media", "readme");
const require = createRequire(join(root, "site", "package.json"));
const { chromium } = require("playwright");
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".txt": "text/plain" };

const SHOTS = [
  ["hero", "/", "main > div > section:first-of-type"],
  ["how-it-works", "/", "section[aria-labelledby=what]"],
  ["path-to-yes", "/", "#path"],
  ["definitions", "/", "#definitions"],
  ["levers", "/", "#levers"],
  ["proof", "/methodology/", "#proof"],
];

const server = createServer((req, res) => {
  let file = join(out, decodeURIComponent(new URL(req.url, "http://x").pathname));
  if (!file.startsWith(out)) return res.writeHead(403).end();
  if (existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
  if (!existsSync(file)) return res.writeHead(404).end();
  res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
  createReadStream(file).pipe(res);
});
await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
const base = `http://127.0.0.1:${server.address().port}`;
mkdirSync(dest, { recursive: true });

const browser = await chromium
  .launch({ channel: "chrome" })
  .catch(() => chromium.launch({ channel: "msedge" }));
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 });
for (const [name, path, selector] of SHOTS) {
  await page.goto(base + path, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);
  if (name === "proof") {
    await page.waitForFunction(
      () => !document.querySelector('[data-testid="proof-verdict"]')?.textContent?.includes("Checking"),
      null,
      { timeout: 30000 },
    );
  }
  const target = name === "proof" ? page.locator(selector).locator("xpath=..") : page.locator(selector);
  await target.first().screenshot({ path: join(dest, `${name}.png`) });
  console.log(`wrote docs/media/readme/${name}.png`);
}
await browser.close();
server.close();
