#!/usr/bin/env node
/**
 * Capture marketing screenshots of the rendered sample itineraries.
 *
 * Produces, per trip, into docs/img/:
 *   <name>-og.png      1200x630 social/OG card (hero crop)
 *   <name>-wide.png    1200-wide desktop showcase (hero + reservation countdown)
 *   <name>-mobile.png  390-wide mobile full page
 *   <name>-<section>.png  element shots: countdown, days, budget, evplan, crossborder
 *
 * The Leaflet map needs network access to OpenStreetMap tiles; run this on a
 * machine with internet so the route map renders in the screenshots. In a
 * sandbox without tile access the map degrades to an offline notice.
 *
 * Usage:  node scripts/capture_demo.js
 * Requires Playwright + a Chromium build. Set CHROMIUM_PATH to override the
 * browser binary (defaults to Playwright's bundled Chromium).
 */
const path = require("path");
const fs = require("fs");

let chromium;
try {
  ({ chromium } = require("playwright"));
} catch (e) {
  try {
    ({ chromium } = require("/opt/node22/lib/node_modules/playwright"));
  } catch (e2) {
    console.error("Playwright not found. Install with: npm i -D playwright");
    process.exit(1);
  }
}

const ROOT = path.resolve(__dirname, "..");
const outDir = path.join(ROOT, "docs", "img");
fs.mkdirSync(outDir, { recursive: true });

const TRIPS = [
  { file: "assets/preview.html", name: "southwest" },
  { file: "assets/preview-tahoe.html", name: "tahoe" },
  { file: "assets/preview-pnw.html", name: "pnw" },
];

const SECTIONS = ["countdown", "days", "budget", "evplan", "crossborder", "routes"];

async function settle(page) {
  await page.goto("file://" + path.resolve(ROOT, page._roadtripUrl), {
    waitUntil: "networkidle",
  }).catch(() => {});
  await page.waitForTimeout(2500); // let Leaflet tiles settle when online
}

(async () => {
  const launchOpts = {};
  if (process.env.CHROMIUM_PATH) launchOpts.executablePath = process.env.CHROMIUM_PATH;
  const browser = await chromium.launch(launchOpts);

  for (const t of TRIPS) {
    // Desktop
    const pg = await browser.newPage({
      viewport: { width: 1200, height: 900 },
      deviceScaleFactor: 2,
    });
    pg._roadtripUrl = t.file;
    await settle(pg);
    await pg.screenshot({
      path: path.join(outDir, `${t.name}-og.png`),
      clip: { x: 0, y: 0, width: 1200, height: 630 },
    });
    await pg.screenshot({
      path: path.join(outDir, `${t.name}-wide.png`),
      clip: { x: 0, y: 0, width: 1200, height: 860 },
    });
    for (const sec of SECTIONS) {
      const el = await pg.$(`#${sec}`);
      if (!el) continue;
      const box = await el.boundingBox();
      if (!box || box.height < 20) continue; // empty/unused section
      await el.screenshot({ path: path.join(outDir, `${t.name}-${sec}.png`) }).catch(() => {});
    }
    await pg.close();

    // Mobile
    const mp = await browser.newPage({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 2,
      isMobile: true,
    });
    mp._roadtripUrl = t.file;
    await settle(mp);
    await mp.screenshot({ path: path.join(outDir, `${t.name}-mobile.png`) });
    await mp.close();

    console.log("captured", t.name);
  }

  await browser.close();
})();
