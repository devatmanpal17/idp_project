/* Shared URL validation for saved connection settings and runtime requests. */
(() => {
  function connectionURL(value) {
    const url = new URL(String(value).trim());
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname ||
        url.username || url.password || url.search || url.hash) {
      throw new Error('Use an HTTP or HTTPS URL without credentials, a query, or a fragment.');
    }
    return url.href.replace(/\/$/, '');
  }
  function hostPasswordHeaders(base, saved) {
    if (!saved?.password) return {};
    const url = new URL(connectionURL(base));
    // Never forward a saved password when the destination changes.
    if (url.origin !== saved.origin) return {};
    if (url.protocol !== 'https:' && !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) {
      throw new Error('A hosted password requires HTTPS.');
    }
    if (!/^[\x20-\x7e]{16,72}$/.test(saved.password)) {
      throw new Error('Use the Render password: 16 to 72 printable ASCII characters.');
    }
    return { Authorization: `Basic ${btoa(`demo:${saved.password}`)}` };
  }
  globalThis.ChaiConnection = { connectionURL, hostPasswordHeaders };
  if (typeof module !== 'undefined') module.exports = globalThis.ChaiConnection;
})();
