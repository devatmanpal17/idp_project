/* Pure interval tracker plus HTMLVideoElement adapter. No timestamp watermark proof. */
(() => {
  class ObservationTracker {
    constructor() { this.intervals = []; this.pending = []; this.previous = null; }
    breakTraversal() { this.previous = null; }
    sample(mediaMs, wallMs, rate = 1, eligible = true) {
      if (![mediaMs, wallMs, rate].every(Number.isFinite) || rate <= 0 || !eligible) {
        this.breakTraversal(); return;
      }
      const last = this.previous;
      this.previous = { mediaMs, wallMs, rate };
      if (!last) return;
      const elapsed = wallMs - last.wallMs, delta = mediaMs - last.mediaMs;
      // Bound callback stalls to 1s and media movement to elapsed time plus 1 frame
      // (50ms permits <=20fps material). Never merge a positive seek gap.
      if (elapsed <= 0 || elapsed > 1000 || delta <= 0 || last.rate !== rate ||
          delta > elapsed * rate + 50) return;
      this.add(Math.ceil(last.mediaMs), Math.floor(mediaMs));
      this.pending.push({start: last.mediaMs / 1000, end: mediaMs / 1000,
        wall_ms: elapsed, rate});
    }
    add(start, end) {
      if (end <= start) return;
      const merged = [];
      for (const pair of [...this.intervals, [start, end]].sort((a, b) => a[0] - b[0])) {
        const tail = merged.at(-1);
        if (tail && pair[0] <= tail[1]) tail[1] = Math.max(tail[1], pair[1]);
        else merged.push([...pair]);
      }
      this.intervals = merged;
    }
    covers(start, end) { return this.intervals.some(([a, b]) => a <= start && b >= end); }
    get watermark() { return this.intervals[0]?.[0] === 0 ? this.intervals[0][1] : 0; }
  }

  function attach(video, { visible = () => !document.hidden, allowed = () => true } = {}) {
    const tracker = new ObservationTracker();
    let frameId, stopped = false;
    const reset = () => tracker.breakTraversal();
    const events = ['play', 'pause', 'seeking', 'seeked', 'ratechange', 'waiting', 'stalled', 'ended'];
    events.forEach(event => video.addEventListener(event, reset));
    document.addEventListener('visibilitychange', reset);
    const eligible = () => !video.paused && !video.seeking && !video.ended &&
      video.readyState >= 2 && visible() && allowed();
    const frame = (now, metadata) => {
      tracker.sample(metadata.mediaTime * 1000, now, video.playbackRate, eligible());
      if (!stopped) frameId = video.requestVideoFrameCallback(frame);
    };
    // Fallback requires decoded-frame counter advancement as well as playback events.
    let frames = video.getVideoPlaybackQuality?.().totalVideoFrames;
    const fallback = () => {
      const next = video.getVideoPlaybackQuality?.().totalVideoFrames;
      tracker.sample(video.currentTime * 1000, performance.now(), video.playbackRate,
        eligible() && Number.isFinite(next) && next > frames);
      frames = next;
    };
    if (video.requestVideoFrameCallback) frameId = video.requestVideoFrameCallback(frame);
    else video.addEventListener('timeupdate', fallback);
    return { tracker, evidence: video.requestVideoFrameCallback ? 'rendered-frame' : 'decoded-frame',
      detach() {
        stopped = true;
        if (frameId !== undefined) video.cancelVideoFrameCallback?.(frameId);
        events.forEach(event => video.removeEventListener(event, reset));
        video.removeEventListener('timeupdate', fallback);
        document.removeEventListener('visibilitychange', reset);
      } };
  }
  globalThis.ChaiObservation = { ObservationTracker, attach };
  if (typeof module !== 'undefined') module.exports = globalThis.ChaiObservation;
})();
