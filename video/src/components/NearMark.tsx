import { Easing, interpolate, random, useCurrentFrame } from "remotion";

// The NEAR "N" from square tiles on a 9 x 9 grid, as in site/components/NearMark.tsx.
const GRID = 9;
const TILE = 40;
const GAP = 6;
const STEP = TILE + GAP;
const SIZE = GRID * STEP - GAP;

const CELLS: [number, number][] = [
  ...Array.from({ length: GRID }, (_, r) => [r, 0] as [number, number]),
  ...Array.from({ length: GRID }, (_, r) => [r, GRID - 1] as [number, number]),
  ...Array.from({ length: GRID - 2 }, (_, i) => [i + 1, i + 1] as [number, number]),
  [7, 1],
  [6, 2],
  [1, 7],
  [2, 6],
];

type Props = {
  size: number;
  /** Frame (inside the Sequence) where the tiles start to move into place; omit for a static mark. */
  startFrame?: number;
  /** Tiles fly in from scattered positions instead of dropping in. */
  assemble?: boolean;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const NearMark: React.FC<Props> = ({ size, startFrame, assemble = false }) => {
  const frame = useCurrentFrame();
  return (
    <svg width={size} height={size} viewBox={`0 0 ${SIZE} ${SIZE}`} style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="near-gold" x1="0" y1="0" x2={SIZE} y2={SIZE} gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#7a5f36" />
          <stop offset="0.22" stopColor="#c8ad86" />
          <stop offset="0.4" stopColor="#efdcb6" />
          <stop offset="0.58" stopColor="#a5875a" />
          <stop offset="0.78" stopColor="#d8c096" />
          <stop offset="1" stopColor="#6e5530" />
        </linearGradient>
      </defs>
      {CELLS.map(([r, c], i) => {
        const t =
          startFrame === undefined
            ? 1
            : interpolate(frame - startFrame - i * (assemble ? 0.9 : 0.6), [0, assemble ? 26 : 10], [0, 1], {
                ...clamp,
                easing: assemble ? Easing.spring({ damping: 14 }) : Easing.out(Easing.cubic),
              });
        const dx = assemble ? (random(`tile-x-${i}`) * 2 - 1) * SIZE * 1.4 : 0;
        const dy = assemble ? (random(`tile-y-${i}`) * 2 - 1) * SIZE * 1.4 : 24;
        const spin = assemble ? (random(`tile-r-${i}`) * 2 - 1) * 180 : 0;
        const cx = c * STEP + TILE / 2;
        const cy = r * STEP + TILE / 2;
        return (
          <rect
            key={`${r}-${c}`}
            x={c * STEP + (1 - t) * dx}
            y={r * STEP + (1 - t) * dy}
            width={TILE}
            height={TILE}
            rx={4}
            fill="url(#near-gold)"
            opacity={Math.min(1, t * 1.4)}
            transform={`rotate(${(1 - t) * spin} ${cx + (1 - t) * dx} ${cy + (1 - t) * dy})`}
          />
        );
      })}
    </svg>
  );
};
