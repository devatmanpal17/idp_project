/**
 * Cognivue — Domain Helper Functions
 */

export function masteryBand(score: number) {
  if (score >= 75) return { label: "Strong", tone: "positive" as const };
  if (score >= 50) return { label: "Developing", tone: "primary" as const };
  return { label: "At risk", tone: "warn" as const };
}

export function relativeTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diff / 60000);
  if (Math.abs(mins) < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (Math.abs(hours) < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

/** Ebbinghaus-style retention decay: stronger mastery decays slower. */
export function retentionCurve(mastery: number, days: number, reviews: number[] = []) {
  const points: { day: number; retention: number }[] = [];
  let strength = 1 + mastery / 40;
  let lastReview = 0;
  for (let d = 0; d <= days; d++) {
    if (reviews.includes(d)) {
      strength += 1.4;
      lastReview = d;
    }
    const elapsed = d - lastReview;
    const retention = 100 * Math.exp(-elapsed / (strength * 2.2));
    points.push({ day: d, retention: Math.round(retention * 10) / 10 });
  }
  return points;
}
