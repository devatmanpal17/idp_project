const { test } = require('node:test');
const assert = require('node:assert/strict');
const { ObservationTracker } = require('../extension/observation.js');
test('seek gap, rewind, replay, rate change and hidden playback', () => {
  const t = new ObservationTracker();
  t.sample(0, 0); t.sample(100, 100); t.sample(200, 200);
  t.breakTraversal(); t.sample(500, 300); t.sample(600, 400);
  assert.deepEqual(t.intervals, [[0, 200], [500, 600]]);
  t.breakTraversal(); t.sample(100, 500); t.sample(200, 600); t.sample(300, 700);
  t.breakTraversal(); t.sample(300, 800, 2); t.sample(500, 900, 2);
  assert.deepEqual(t.intervals, [[0, 600]]);
  t.sample(700, 1000, 2, false); t.sample(900, 1100, 2, false);
  assert.equal(t.watermark, 600);
});
test('unannounced jumps and long callback gaps fail closed', () => {
  const t = new ObservationTracker();
  t.sample(0, 0); t.sample(5000, 100); t.sample(8000, 3100);
  assert.deepEqual(t.intervals, []);
});
