// Deterministic, framework-free coordinate math for the chart components in
// this directory. Kept as plain functions (no DOM, no React) so the scaling
// logic itself - not just its rendering - can be reasoned about and verified
// independently of any component.

export interface Scale {
  (value: number): number;
  domain: [number, number];
  range: [number, number];
}

/**
 * Maps a numeric domain onto a pixel range. A degenerate domain (min === max,
 * e.g. a single data point or an all-zero series) would otherwise divide by
 * zero; it instead maps every value to the midpoint of the range rather than
 * producing NaN/Infinity coordinates that would silently break the SVG path.
 */
export function linearScale(domain: [number, number], range: [number, number]): Scale {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0;
  const scale = ((value: number) => {
    if (span === 0) return (r0 + r1) / 2;
    return r0 + ((value - d0) / span) * (r1 - r0);
  }) as Scale;
  scale.domain = domain;
  scale.range = range;
  return scale;
}

/** Expands a [min, max] domain by a small margin so extreme points don't sit
 * flush against the chart edge. No-ops on a degenerate (min === max) domain -
 * that case is handled by linearScale's midpoint fallback instead. */
export function padDomain([min, max]: [number, number], fraction = 0.08): [number, number] {
  if (min === max) return [min, max];
  const pad = (max - min) * fraction;
  return [min - pad, max + pad];
}

/** A handful of human-friendly tick values spanning [min, max], inclusive of
 * the endpoints. Falls back to just the endpoints when the domain is
 * degenerate or count < 2. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max || count < 2) return [min, max];
  const step = (max - min) / (count - 1);
  return Array.from({ length: count }, (_, i) => min + step * i);
}

/** Given the pixel x-position of a pointer over a chart of `width` px
 * representing `length` evenly-spaced samples, returns the nearest sample
 * index (clamped to a valid index). Shared by every chart's hover handler so
 * "nearest point" behaves identically across chart types. */
export function nearestIndex(pointerX: number, width: number, length: number): number {
  if (length <= 1) return 0;
  const ratio = Math.min(1, Math.max(0, pointerX / width));
  return Math.round(ratio * (length - 1));
}
