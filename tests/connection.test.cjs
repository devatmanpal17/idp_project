const { test } = require('node:test');
const assert = require('node:assert/strict');
const { connectionURL } = require('../extension/connection.js');

test('connection URLs are normalized and unsafe/malformed settings rejected', () => {
  assert.equal(connectionURL(' http://localhost:8000/ '), 'http://localhost:8000');
  assert.equal(connectionURL('https://example.test/backend/'), 'https://example.test/backend');
  for (const url of ['javascript:alert(1)', 'file:///tmp', 'http://', 'https://user:password@example.test',
    'http://localhost:8000?secret=value', 'https://example.test/#fragment']) {
    assert.throws(() => connectionURL(url));
  }
});
