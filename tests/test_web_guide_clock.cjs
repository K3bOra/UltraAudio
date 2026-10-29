const fs = require('fs'), vm = require('vm'), assert = require('assert');
for (const tree of ['ipk-source', 'deb-source']) {
  const html = fs.readFileSync(__dirname + '/../' + tree + '/data/usr/lib/enigma2/python/Plugins/Extensions/UltraAudio/web/index.html', 'utf8');
  const code = html.slice(html.indexOf('function guideNow()'), html.indexOf('function streamRow('));
  const context = {S: {library: {now: 1000}}, Date: {now: () => 864000000}};
  vm.createContext(context); vm.runInContext(code, context);
  const station = {guide: {title: 'Current program', start: 900, end: 1100}};
  for (const browserTime of [0, 1000000000, -1000000000]) {
    context.Date.now = () => browserTime;
    assert.strictEqual(context.guideNow(), 1000);
    assert.strictEqual(context.guideEvent(station, context.guideNow()), station.guide);
  }
  context.S.library.now = 1100;
  assert.strictEqual(context.guideEvent(station, context.guideNow()), null);
  context.S.library.now = 899;
  assert.strictEqual(context.guideEvent(station, context.guideNow()), null);
  delete context.S.library.now;
  assert.strictEqual(context.guideEvent(station, context.guideNow()), station.guide);
  assert.strictEqual(context.guideEvent({guide: null}, 1000), null);
  assert(!html.includes('Date.now() / 1000'));
  console.log('PASS ' + tree + ': guide ignores browser clock offsets, honors receiver intervals, handles old snapshots');
}
