// Scene frame ranges at 30 fps (45 s). Each scene starts where the previous one ends.
export const FPS = 30;
export const SCENE_FRAMES = [
  ["issuance", 150],
  ["capture", 150],
  ["coverage", 240],
  ["hero", 240],
  ["breakeven", 210],
  ["proof", 210],
  ["outro", 150],
] as const;

export type SceneKey = (typeof SCENE_FRAMES)[number][0];

export const SCENES = SCENE_FRAMES.map(([id, frames], i) => ({
  id,
  frames,
  from: SCENE_FRAMES.slice(0, i).reduce((sum, [, f]) => sum + f, 0),
}));

export const TOTAL = SCENES.reduce((sum, s) => sum + s.frames, 0);
// Frames (inside their scene) where the three small cards appear, and the least time one may stay on screen.
export const CARD_APPEAR = { distribution: 150, developer: 140, valuation: 120 } as const;
export const MIN_CARD_DWELL = 90;
// The hero count-up has finished and the developer card has not appeared yet: used for the cover.
export const COVER_FRAME = SCENES[3].from + 130;

// Scene changes: each sequence but the last runs TRANSITION_FRAMES longer, overlapping the next scene's
// first frames, so every scene still starts at `from` and the total stays TOTAL.
export const TRANSITION_FRAMES = 15;
export const TRANSITIONS = ["slide-right", "wipe", "zoom", "slide-up", "iris", "zoom"] as const;
export type TransitionKind = (typeof TRANSITIONS)[number];
export const sequenceFrames = (i: number): number => SCENES[i].frames + (i < SCENES.length - 1 ? TRANSITION_FRAMES : 0);
