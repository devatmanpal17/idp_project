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
  globalThis.ChaiConnection = { connectionURL };
  if (typeof module !== 'undefined') module.exports = globalThis.ChaiConnection;
})();
