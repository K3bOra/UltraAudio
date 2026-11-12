#!/usr/bin/env node
// Renders the README artwork from tools/page/templates into assets/, and frames screenshots.
//
//   node tools/page/build.js              all artwork (hero, headings, buttons, panels)
//   node tools/page/build.js art hero     only outputs whose name contains "hero"
//   node tools/page/build.js shots        screenshots/ua-tv-*.jpg -> screenshots/framed/ua-tv-*.jpg
//
// The original screenshots are never changed; framed copies go to screenshots/framed/.
// Needs Playwright with Chromium (npm i playwright && npx playwright install chromium).
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const HERE = __dirname;
const REPO = path.resolve(HERE, '..', '..');
const ASSETS = path.join(REPO, 'screenshots', 'page');
const SHOTS = path.join(REPO, 'screenshots');

const HEADINGS = [
  ['overview', 'تعرّف على الترا أوديو', 'Meet Ultra Audio'],
  ['whats-new', 'الجديد', "What's new"],
  ['tour', 'جولة داخل البلجن', 'A tour of the plugin'],
  ['features', 'المميزات', 'Features'],
  ['compatibility', 'التوافق والمتطلبات', 'Compatibility'],
  ['install', 'التثبيت', 'Installation'],
  ['faq', 'أسئلة شائعة', 'Questions & troubleshooting'],
  ['family', 'عيلة Ultra', 'The Ultra family'],
  ['resources', 'التحديثات والروابط', 'Updates & resources'],
  ['mobile', 'تحكم من الموبايل', 'One experience, two screens'],
  ['sync', 'كل تفصيلة في توقيتها', 'Find your perfect timing'],
  ['themes', 'أربع ثيمات', 'Four themes'],
];
const ART = [
  ['hero.html', 'ultraaudio-hero.jpg'],
  ['button.html', 'button-install.png', { ar: 'ثبّت الترا أوديو', en: 'Install Ultra Audio' }],
  ['button.html', 'button-releases.png', { ar: 'الإصدارات الرسمية', en: 'Official releases' }],
  ['features.html', 'features.jpg'],
  ['steps.html', 'install-steps.jpg'],
  ['family.html', 'family-quran.png', { p: 'quran' }],
  ['family.html', 'family-stalker.png', { p: 'stalker' }],
  ['family.html', 'family-audio.png', { p: 'audio' }],
  ['colophon.html', 'colophon.jpg'],
  ...HEADINGS.map(([slug, ar, en]) => ['heading.html', 'heading-' + slug + '.png', { ar, en }]),
];

function sizeOf(html) {
  const m = html.match(/<meta name="size" content="(\d+)x(\d+)">/);
  if (!m) throw new Error('template without <meta name="size">');
  return [+m[1], +m[2]];
}

async function render(page, template, out, query = {}) {
  const file = path.join(HERE, 'templates', template);
  const [w, h] = sizeOf(fs.readFileSync(file, 'utf8'));
  await page.setViewportSize({ width: w, height: h });
  const qs = new URLSearchParams(query).toString();
  await page.goto('file://' + file + (qs ? '?' + qs : ''));
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => [...document.images].every((i) => i.complete));
  await page.waitForTimeout(150);
  const jpeg = out.endsWith('.jpg');
  await page.screenshot({ path: out, type: jpeg ? 'jpeg' : 'png', quality: jpeg ? 90 : undefined, omitBackground: !jpeg });
  console.log('  ' + path.relative(REPO, out));
}

(async () => {
  const mode = process.argv[2] || 'art';
  const browser = await chromium.launch();
  fs.mkdirSync(ASSETS, { recursive: true });
  if (mode === 'art') {
    const page = await browser.newPage({ deviceScaleFactor: 2 });
    for (const [template, out, query] of ART.filter((a) => !process.argv[3] || a[1].includes(process.argv[3])))
      await render(page, template, path.join(ASSETS, out), query);
  } else if (mode === 'shots') {
    const page = await browser.newPage({ deviceScaleFactor: 1 });
    const framed = path.join(SHOTS, 'framed');
    fs.mkdirSync(framed, { recursive: true });
    fs.mkdirSync(ASSETS, { recursive: true });
    for (const name of fs.readdirSync(SHOTS).filter((n) => /^ua-tv-.+\.jpg$/.test(n)).sort())
      await render(page, 'shot.html', path.join(framed, name), { src: 'file://' + path.join(SHOTS, name) });
  }
  await browser.close();
})();
