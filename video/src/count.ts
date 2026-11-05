// Integer count-up from 0 to target, easing out, between startFrame and startFrame + duration.
export const countUp = (target: number, frame: number, startFrame: number, duration: number): number => {
  const p = Math.min(1, Math.max(0, (frame - startFrame) / duration));
  return Math.round(target * (1 - (1 - p) ** 3));
};

// The part of a line a typewriter has printed by this frame.
export const typed = (text: string, frame: number, startFrame: number, charsPerFrame: number): string =>
  text.slice(0, Math.max(0, Math.floor((frame - startFrame) * charsPerFrame)));
