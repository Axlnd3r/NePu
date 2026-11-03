/** The NEAR "N" rebuilt from square tiles on a 9 x 9 grid: two uprights, the diagonal, and the
 * two short inner strokes of the official logo (rising from the left upright at the bottom,
 * falling from the right upright at the top). Pure SVG, so it renders without JavaScript or
 * image files; the metal look is a gold gradient plus a static noise filter.
 */
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
  /** Unique per page: the gradient and filter ids are derived from it. */
  id: string;
  className?: string;
  /** Flat champagne fill instead of gradient and texture (small sizes). */
  flat?: boolean;
  title?: string;
};

export function NearMark({ id, className = "", flat = false, title }: Props) {
  const gold = `${id}-gold`;
  const metal = `${id}-metal`;
  return (
    <svg
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      className={className}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      {!flat && (
        <defs>
          <linearGradient id={gold} x1="0" y1="0" x2={SIZE} y2={SIZE} gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#7a5f36" />
            <stop offset="0.22" stopColor="#c8ad86" />
            <stop offset="0.4" stopColor="#efdcb6" />
            <stop offset="0.58" stopColor="#a5875a" />
            <stop offset="0.78" stopColor="#d8c096" />
            <stop offset="1" stopColor="#6e5530" />
          </linearGradient>
          <filter id={metal} x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
            <feTurbulence type="fractalNoise" baseFrequency="0.006 0.05" numOctaves="4" seed="11" result="noise" />
            <feColorMatrix in="noise" type="saturate" values="0" result="grain" />
            <feBlend in="SourceGraphic" in2="grain" mode="overlay" result="textured" />
            <feComposite in="textured" in2="SourceGraphic" operator="in" />
          </filter>
        </defs>
      )}
      <g fill={flat ? "var(--accent)" : `url(#${gold})`} filter={flat ? undefined : `url(#${metal})`}>
        {CELLS.map(([r, c]) => (
          <rect key={`${r}-${c}`} x={c * STEP} y={r * STEP} width={TILE} height={TILE} rx={4} />
        ))}
      </g>
      {!flat && (
        <g fill="none" stroke="#fff7dd" strokeOpacity={0.22} strokeWidth={1}>
          {CELLS.map(([r, c]) => (
            <rect
              key={`${r}-${c}`}
              x={c * STEP + 0.5}
              y={r * STEP + 0.5}
              width={TILE - 1}
              height={TILE - 1}
              rx={3.5}
            />
          ))}
        </g>
      )}
    </svg>
  );
}
