const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { randomUUID } = require('node:crypto');

function worker(storage, request, settings) {
  const context = vm.createContext({
    importScripts() {}, crypto: { randomUUID }, AbortSignal,
    ChaiConnection: require('../extension/connection.js'),
    fetch: async (url, init) => ({ok: true, json: async () => request(init.body ? JSON.parse(init.body) : null, init, url)}),
    chrome: {
      runtime: {onInstalled: {addListener() {}}, onMessage: {addListener() {}}},
      storage: {
        sync: {get: async defaults => ({...defaults, ...settings})},
        local: {
          get: async key => ({[key]: storage[key]}),
          set: async values => Object.assign(storage, values),
        },
      },
    },
  });
  const source = fs.readFileSync(require.resolve('../extension/background.js'), 'utf8');
  vm.runInContext(source + '\nglobalThis.testHandlers = handlers;', context);
  return context.testHandlers;
}

test('one learner key survives concurrent tabs and worker restart', async () => {
  const storage = {};
  const first = worker(storage, () => ({}));
  const keys = await Promise.all(Array.from({length: 10}, () => first.LEARNER_KEY()));
  assert.equal(new Set(keys).size, 1);
  const restarted = worker(storage, () => ({}));
  assert.equal(await restarted.LEARNER_KEY(), keys[0]);
});

test('actual worker adds the hosted password from local storage only for its saved origin', async () => {
  const password = 'disposable-test-password';
  const storage = {hostPassword: {origin:'https://demo.test', password}};
  const settings = {apiBaseUrl:'https://demo.test'};
  const first = worker(storage, (body, init, url) => {
    assert.equal(url, 'https://demo.test/api/health');
    assert.equal(init.headers.Authorization, 'Basic '+Buffer.from('demo:'+password).toString('base64'));
    assert.equal(body, null);
    return {status:'ready'};
  }, settings);
  assert.equal((await first.HEALTH()).status, 'ready');
  const moved = worker(storage, (_body, init) => {
    assert.equal(init.headers.Authorization, undefined);
    return {};
  }, {apiBaseUrl:'http://localhost:8000'});
  await moved.HEALTH();
});

test('interval sequence increases across tabs, lost replies, and worker restart', async () => {
  const storage = {}, sequences = [];
  const request = payload => {
    sequences.push(payload.batch_seq);
    if (sequences.length === 1) throw new Error('lost reply');
    return {accepted: 1};
  };
  const payload = {learner_key: 'learner', video_key: 'youtube:test', batch_seq: 1, intervals: []};
  const first = worker(storage, request);
  await assert.rejects(first.F1_INTERVALS(payload), /lost reply/);
  await Promise.all([first.F1_INTERVALS(payload), first.F1_INTERVALS(payload)]);
  await worker(storage, request).F1_INTERVALS(payload);
  assert.ok(sequences.every((value, index) => index === 0 || value > sequences[index - 1]));
});
