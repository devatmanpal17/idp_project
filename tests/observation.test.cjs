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

test('frame observation follows the playback clock when submitted timestamps jump ahead', () => {
  const previousDocument = globalThis.document;
  globalThis.document = { hidden: false, addEventListener() {}, removeEventListener() {} };
  let callback;
  const video = { currentTime: 0, paused: false, seeking: false, ended: false, readyState: 4, playbackRate: 1,
    addEventListener() {}, removeEventListener() {}, cancelVideoFrameCallback() {},
    requestVideoFrameCallback(next) { callback = next; return 1; } };
  try {
    const observation = attach(video);
    callback(1000, { mediaTime: 0, presentedFrames: 1, expectedDisplayTime: 1100 });
    video.currentTime = .1;
    callback(1100, { mediaTime: .1, presentedFrames: 2, expectedDisplayTime: 1200 });
    video.currentTime = .2;
    callback(1200, { mediaTime: .4, presentedFrames: 3, expectedDisplayTime: 1300 });
    assert.deepEqual(observation.tracker.intervals, [[0, 200]]);
    assert.equal(observation.tracker.covers(300, 400), false, 'Future submitted frame did not unlock future captions');
    video.currentTime = .3;
    callback(1300, { mediaTime: .5, presentedFrames: 3 });
    assert.deepEqual(observation.tracker.intervals, [[0, 200]], 'Repeated frame is not playback evidence');
    video.currentTime = .4;
    callback(1400, { mediaTime: .6, presentedFrames: 4 });
    video.currentTime = .5;
    callback(1500, { mediaTime: .7, presentedFrames: 5 });
    assert.deepEqual(observation.tracker.intervals, [[0, 200], [400, 500]]);
    video.currentTime = 5;
    callback(1600, { mediaTime: 5, presentedFrames: 6 });
    assert.equal(observation.tracker.covers(500, 5000), false, 'Unannounced jump remains blocked');
    observation.detach();
  } finally {
    globalThis.document = previousDocument;
  }
});

test('rendered-frame playback rejects hidden, stalled and seeking spans', () => {
  const previousDocument = globalThis.document;
  globalThis.document = { hidden: false, addEventListener() {}, removeEventListener() {} };
  let callback;
  const video = { currentTime: 0, paused: false, seeking: false, ended: false, readyState: 4, playbackRate: 1,
    addEventListener() {}, removeEventListener() {}, cancelVideoFrameCallback() {},
    requestVideoFrameCallback(next) { callback = next; return 1; } };
  try {
    const observation = attach(video);
    let frame = 0;
    const sample = (media, wall) => {
      video.currentTime = media;
      callback(wall, { presentedFrames: ++frame, mediaTime: media + .2 });
    };
    sample(0, 0); sample(.1, 100);
    document.hidden = true; sample(.2, 200);
    document.hidden = false; sample(.3, 300); sample(.4, 400);
    sample(1.9, 1900); sample(2, 2000);
    video.seeking = true; sample(8, 2100);
    video.seeking = false; sample(8.1, 2200); sample(8.2, 2300);
    assert.deepEqual(observation.tracker.intervals, [[0, 100], [300, 400], [1900, 2000], [8100, 8200]]);
    observation.detach();
  } finally {
    globalThis.document = previousDocument;
  }
});
