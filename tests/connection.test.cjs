const { test } = require('node:test');
const assert = require('node:assert/strict');
const { connectionURL, hostPasswordHeaders } = require('../extension/connection.js');

test('connection URLs are normalized and unsafe/malformed settings rejected', () => {
  assert.equal(connectionURL(' http://localhost:8000/ '), 'http://localhost:8000');
  assert.equal(connectionURL('https://example.test/backend/'), 'https://example.test/backend');
  for (const url of ['javascript:alert(1)', 'file:///tmp', 'http://', 'https://user:password@example.test',
    'http://localhost:8000?secret=value', 'https://example.test/#fragment']) {
    assert.throws(() => connectionURL(url));
  }
});

test('hosted passwords are sent only to the saved secure origin; localhost stays optional', () => {
  const password = 'test-password-only-123';
  const saved = {origin: 'https://demo.example.test', password};
  assert.deepEqual(hostPasswordHeaders('http://localhost:8000', null), {});
  assert.deepEqual(hostPasswordHeaders('https://other.example.test', saved), {});
  assert.equal(hostPasswordHeaders(saved.origin, saved).Authorization,
    'Basic ' + Buffer.from('demo:' + password).toString('base64'));
  assert.throws(() => hostPasswordHeaders('http://demo.example.test',
    {...saved, origin:'http://demo.example.test'}), /HTTPS/);
  assert.throws(() => hostPasswordHeaders(saved.origin, {...saved,password:'short'}), /16 to 72/);
  assert.throws(() => hostPasswordHeaders(saved.origin, {...saved,password:'x'.repeat(73)}));
  assert.throws(() => hostPasswordHeaders(saved.origin, {...saved,password:password+'\n'}));
});
