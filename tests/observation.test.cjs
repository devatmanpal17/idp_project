const { test } = require('node:test');
const assert = require('node:assert/strict');
const { ObservationTracker, attach } = require('../extension/observation.js');
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

test('fractional frame boundaries do not invent holes in continuous playback', () => {
  const tracker = new ObservationTracker();
  tracker.sample(100.001, 0);
  tracker.sample(200.001, 100);
  tracker.sample(300.001, 200);
  assert.deepEqual(tracker.intervals, [[101, 300]]);
  tracker.breakTraversal();
  tracker.sample(500.001, 300);
  tracker.sample(600.001, 400);
  assert.deepEqual(tracker.intervals, [[101, 300], [501, 600]]);
});

test('frame observation uses display timestamps despite callback and submission jitter', () => {
  const previousDocument = globalThis.document;
  globalThis.document = { hidden: false, addEventListener() {}, removeEventListener() {} };
  let callback;
  const video = { paused: false, seeking: false, ended: false, readyState: 4, playbackRate: 1,
    addEventListener() {}, removeEventListener() {}, cancelVideoFrameCallback() {},
    requestVideoFrameCallback(next) { callback = next; return 1; } };
  try {
    const observation = attach(video);
    callback(1000, { mediaTime: 0, presentationTime: 0, expectedDisplayTime: 0 });
    callback(1100, { mediaTime: .1, presentationTime: 100, expectedDisplayTime: 100 });
    callback(1105, { mediaTime: .2, presentationTime: 105, expectedDisplayTime: 200 });
    assert.deepEqual(observation.tracker.intervals, [[0, 200]]);
    observation.detach();
  } finally {
    globalThis.document = previousDocument;
  }
});
