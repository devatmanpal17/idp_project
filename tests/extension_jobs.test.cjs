const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { randomUUID } = require('node:crypto');

// Execute the actual content script with browser services stubbed and UI startup
// replaced by an export. The async capture and job functions remain unchanged.
const source = fs.readFileSync(require.resolve('../extension/content.js'), 'utf8')
  .replace(/  buildOverlay\(\);\s+beginCapture\(\);\s*\}\)\(\);\s*$/,
    '  globalThis.testAPI = {state, runAI, syncMedia, ensureObservation};\n})();');

function browser(handler, storage = {}, url = 'https://example.test/lesson') {
  const video = { paused: true, readyState: 4, currentTime: 10, duration: 12 };
  const context = vm.createContext({
    URL, crypto: { randomUUID }, setTimeout: fn => fn(), clearTimeout: () => {},
    ChaiObservation: { attach: () => ({ detach() {}, evidence: 'rendered-frame', tracker: { intervals: [] } }) },
    location: { href: url, hostname: new URL(url).hostname },
    document: {
      hidden: false, title: 'Test lesson', getElementById: () => null,
      querySelector: selector => selector === '#movie_player video.html5-main-video' ? video : null,
    },
    chrome: {
      runtime: {
        onMessage: { addListener() {} },
        sendMessage(message, callback) {
          Promise.resolve().then(() => handler(message)).then(
            data => callback({ ok: true, data }),
            error => callback({ ok: false, error: error.message }),
          );
        },
      },
      storage: { local: {
        async get(key) { return { [key]: storage[key] }; },
        async set(value) { Object.assign(storage, value); },
        async remove(key) { delete storage[key]; },
      } },
    },
  });
  vm.runInContext(source, context);
  const api = context.testAPI;
  assert.ok(api, 'test must load actual content functions');
  api.state.trackedVideo = video;
  api.state.observation = { detach() {}, evidence: 'rendered-frame', tracker: { intervals: [[0, 10000]] } };
  api.state.mediaCaptions = [{ start_ms: 0, end_ms: 1000, text: 'Observed lesson.' }];
  api.state.mediaSignature = JSON.stringify(api.state.mediaCaptions);
  api.state.documentId = 'original-document';
  return api;
}

test('retry after a lost start response reuses the persisted request ID', async () => {
  const storage = {};
  let requestID;
  const first = browser(({ type, payload }) => {
    assert.equal(type, 'JOB_START');
    requestID = payload.request_id;
    throw new Error('worker connection lost after server accepted request');
  }, storage);
  await assert.rejects(first.runAI('ask', { question: 'Explain gravity' }), /connection lost/);
  const reloaded = browser(({ type, payload }) => {
    if (type === 'JOB_START') {
      assert.equal(payload.request_id, requestID);
      return { job_id: requestID };
    }
    return { status: 'succeeded', result: { answer: 'Recovered answer' } };
  }, storage);
  assert.equal((await reloaded.runAI('ask', { question: 'Explain gravity' })).answer, 'Recovered answer');
  assert.equal(Object.keys(storage).length, 0);
});

test('navigation during observation upload prevents speculation on the new document', async () => {
  const calls = [];
  let api;
  api = browser(({ type }) => {
    calls.push(type);
    if (type === 'OBSERVE') {
      api.state.pageKey = 'https://example.test/new-lesson';
      api.state.documentId = 'new-document';
    }
    return {};
  });
  await api.syncMedia();
  assert.deepEqual(calls, ['OBSERVE']);
});

test('interactive capture drains observed batches before generation', async () => {
  let batches = 0;
  const calls = [];
  const api = browser(({ type, payload }) => {
    calls.push(type);
    if (type === 'SPECULATE') {
      assert.equal(payload.observed_only, true);
      return ++batches <= 2 ? { job_id: `batch-${batches}` } : { job_id: null, pending_chunks: 0 };
    }
    if (type === 'JOB_STATUS') return { status: 'succeeded' };
    return {};
  });
  await api.syncMedia(true);
  assert.deepEqual(calls, ['OBSERVE', 'SPECULATE', 'JOB_STATUS', 'SPECULATE', 'JOB_STATUS', 'SPECULATE']);
});

test('reusing a video element for a different source clears its captions and observation proof', () => {
  const api = browser(() => ({}));
  const video = api.state.trackedVideo;
  api.ensureObservation(video);
  assert.equal(api.state.documentId, 'original-document');
  video.currentSrc = 'https://example.test/different-video.mp4';
  api.ensureObservation(video);
  assert.equal(api.state.documentId, null);
  assert.equal(api.state.mediaCaptions.length, 0);
  assert.equal(api.state.observation.tracker.intervals.length, 0);
});

test('YouTube full captions seal through the durable job before intervals upload', async () => {
  const calls = [];
  const api = browser(({type, payload}) => {
    calls.push([type, payload]);
    if (type === 'LEARNER_KEY') return 'learner-uuid';
    if (type === 'JOB_START') return {job_id: payload.request_id};
    if (type === 'JOB_STATUS') return {status: 'succeeded',
      result: {sealed_added: 1, last_batch_seq: 40, revision: 'a'.repeat(64)}};
    return {accepted: 1};
  }, {}, 'https://www.youtube.com/watch?v=video123');
  api.state.scopedEnabled = true;
  api.state.mediaSignature = '';
  api.state.observation.tracker.pending = [{start: 0, end: 1, wall_ms: 1000, rate: 1}];
  await api.syncMedia();
  const started = calls.find(([type]) => type === 'JOB_START')[1];
  assert.equal(started.operation, 'seal');
  assert.equal(started.payload.video_key, 'youtube:video123');
  assert.equal(started.payload.cues.length, api.state.mediaCaptions.length);
  const interval = calls.find(([type]) => type === 'F1_INTERVALS')[1];
  assert.ok(interval.batch_seq > 40);
  assert.equal(interval.revision, 'a'.repeat(64));
  assert.ok(calls.findIndex(([type]) => type === 'JOB_STATUS') <
    calls.findIndex(([type]) => type === 'F1_INTERVALS'));
});
