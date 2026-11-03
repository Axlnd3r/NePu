// QA for the static dashboard: open every page of site/out on desktop and phone widths, fail on
// console errors, failed requests or horizontal overflow, check the break-even meter against the
// data, and save full-page screenshots to qa/screenshots/. Run: make qa (after make site).
import { createReadStream, existsSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
// Set QA_BASE_PATH (e.g. /NePu---NEAR-Pulse-) to test a build made with SITE_BASE_PATH.
const basePath = process.env.QA_BASE_PATH ?? "";
const out = join(root, "site", "out");
const shots = join(root, "qa", "screenshots");
const require = createRequire(join(root, "site", "package.json"));
const { chromium } = require("playwright");

const PAGES = [
  ["overview", "/"],
  ["token", "/token/"],
  ["intents", "/intents/"],
  ["valuation", "/valuation/"],
  ["developer", "/developer/"],
  ["methodology", "/methodology/"],
];
const VIEWPORTS = {
  desktop: { width: 1280, height: 900 },
  mobile: { width: 390, height: 844 },
};
const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".txt": "text/plain",
  ".ico": "image/x-icon",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

function serve() {
  const server = createServer((req, res) => {
    let path = decodeURIComponent(new URL(req.url, "http://x").pathname);
    if (basePath) {
      if (!path.startsWith(basePath)) return res.writeHead(404).end("outside base path");
      path = path.slice(basePath.length) || "/";
    }
    let file = join(out, path);
    if (!file.startsWith(out)) return res.writeHead(403).end();
    if (existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
    if (!existsSync(file)) return res.writeHead(404).end("not found");
    res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
    createReadStream(file).pipe(res);
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok(server)));
}

function launch() {
  const channel = process.env.QA_BROWSER_CHANNEL ?? "chrome";
  return chromium.launch({ channel }).catch(() => chromium.launch({ channel: "msedge" }));
}

const failures = [];
const fail = (msg) => {
  failures.push(msg);
  console.error(`FAIL ${msg}`);
};

if (!existsSync(join(out, "index.html"))) {
  console.error("site/out is missing: run `make site` first");
  process.exit(1);
}
mkdirSync(shots, { recursive: true });
const summary = JSON.parse(readFileSync(join(root, "site", "public", "data", "summary.json"), "utf8"));
const valuation = JSON.parse(readFileSync(join(root, "site", "public", "data", "valuation.json"), "utf8"));

const server = await serve();
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await launch();

for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
  for (const scheme of vpName === "desktop" ? ["light", "dark"] : ["light"]) {
    const context = await browser.newContext({ viewport, colorScheme: scheme });
    for (const [name, path] of PAGES) {
      const page = await context.newPage();
      const tag = `${name} ${vpName} ${scheme}`;
      page.on("console", (m) => m.type() === "error" && fail(`${tag}: console error: ${m.text()}`));
      page.on("pageerror", (e) => fail(`${tag}: page error: ${e.message}`));
      // Prefetches cancelled because the test closes the page are not errors.
      page.on("requestfailed", (r) => {
        const why = r.failure()?.errorText ?? "";
        if (!why.includes("ERR_ABORTED")) fail(`${tag}: request failed (${why}): ${r.url()}`);
      });
      page.on("response", (r) => r.status() >= 400 && fail(`${tag}: HTTP ${r.status()} ${r.url()}`));

      await page.goto(base + basePath + path, { waitUntil: "networkidle" });
      await page.waitForTimeout(300); // charts measure their container after hydration

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      if (overflow > 1) fail(`${tag}: page is ${overflow}px wider than the viewport`);

      if (name === "overview" && vpName === "desktop" && scheme === "light") {
        const meter = page.getByTestId("vstar");
        const read = async () => Number(await meter.getAttribute("data-value"));
        const expectBuyback = summary.levers.steps[0].v_star_usd_per_day;
        const revenueRow = valuation.reverse.rows.find(
          (r) => r.horizon_years === 1 && r.inflation === 0.025 && r.basis === "revenue",
        );
        const got = await read();
        if (Math.abs(got / expectBuyback - 1) > 1e-9)
          fail(`meter default ${got} != summary V* ${expectBuyback}`);
        await page.getByRole("button", { name: "All revenue" }).click();
        const gotRevenue = await read();
        if (Math.abs(gotRevenue / revenueRow.breakeven_volume_usd_per_day - 1) > 1e-9)
          fail(`meter revenue basis ${gotRevenue} != ${revenueRow.breakeven_volume_usd_per_day}`);
        await page.getByRole("button", { name: "Buyback wallet" }).click();
        console.log(`ok   meter matches the data (${got.toFixed(0)} and ${gotRevenue.toFixed(0)})`);
      }

      const suffix = scheme === "dark" ? `${vpName}-dark` : vpName;
      await page.screenshot({ path: join(shots, `${name}-${suffix}.png`), fullPage: true });
      console.log(`ok   ${tag}`);
      await page.close();
    }
    await context.close();
  }
}

await browser.close();
server.close();
if (failures.length) {
  console.error(`\n${failures.length} problem(s)`);
  process.exit(1);
}
console.log(`\nall pages clean; screenshots in qa/screenshots/`);
