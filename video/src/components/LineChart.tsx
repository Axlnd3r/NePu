import { useId } from "react";
import { Easing, interpolate, useCurrentFrame } from "remotion";
import { theme, withAlpha } from "../theme";

export type Point = { date: string; value: number };

type Props = {
  series: Point[][];
  colors: string[];
  names: string[];
  width: number;
  height: number;
  /** Frame where the lines start to draw, and how many frames the draw takes. */
  startFrame?: number;
  revealFrames?: number;
  /** Beat strength 0..1; thickens the lines slightly. */
  pulse?: number;
  /** Top of the y axis; defaults to the series maximum plus headroom. The axis always starts at zero. */
  yMax?: number;
  /** Dashed reference line with a words-only label. */
  refLine?: { value: number; label: string };
  /** Shade the area between two series (indexes) and name it. */
  gap?: { upper: number; lower: number; label: string };
  /** After the draw, an arrow from the first series' last point up to refLine, with this label. */
  refGap?: string;
  formatValue: (v: number) => string;
};

const LABEL_W = 230;
const LABEL_GAP = 64;
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const LineChart: React.FC<Props> = ({
  series, colors, names, width, height, startFrame = 0, revealFrames = 90, pulse = 0, yMax, refLine, gap, refGap, formatValue,
}) => {
  const frame = useCurrentFrame();
  const clipId = `clip${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const t = interpolate(frame - startFrame, [0, revealFrames], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const gridT = interpolate(frame - startFrame + 18, [0, 18], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
  const labelOpacity = interpolate(t, [0.85, 1], [0, 1], clamp);
  const tickerOpacity = interpolate(t, [0, 0.04, 0.88, 1], [0, 1, 1, 0], clamp);

  const top = 14;
  const bottom = 44;
  const plotW = width - LABEL_W;
  const plotH = height - top - bottom;
  const top_ = yMax ?? Math.max(...series.flat().map((p) => p.value)) * 1.08;
  const n = series[0].length;
  const x = (i: number) => (i / (n - 1)) * plotW;
  const y = (v: number) => top + plotH - (v / top_) * plotH;
  const path = (s: Point[]) => s.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)} ${y(p.value).toFixed(1)}`).join(" ");

  // Head of the draw: the dot follows the line exactly; the ticker shows the actual data point under it.
  const fi = t * (n - 1);
  const i0 = Math.floor(fi);
  const i1 = Math.min(n - 1, i0 + 1);
  const headY = (s: Point[]) => y(s[i0].value + (s[i1].value - s[i0].value) * (fi - i0));

  // End-of-line labels, pushed apart so close values stay readable.
  const ends = series.map((s, k) => ({ k, y: y(s.at(-1)!.value) })).sort((a, b) => a.y - b.y);
  ends.forEach((e, i) => { if (i > 0 && e.y - ends[i - 1].y < LABEL_GAP) e.y = ends[i - 1].y + LABEL_GAP; });
  const labelY = new Map(ends.map((e) => [e.k, e.y]));

  const arrowT = interpolate(frame - startFrame - revealFrames - 8, [0, 24], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
  const arrowX = plotW - 70;
  const arrowFrom = y(series[0].at(-1)!.value) - 10;
  const arrowTo = refLine ? y(refLine.value) + 12 : arrowFrom;
  const arrowY = arrowFrom + (arrowTo - arrowFrom) * arrowT;

  return (
    <svg width={width} height={height} style={{ fontFamily: theme.font, overflow: "visible" }}>
      <defs>
        <clipPath id={clipId}>
          <rect x={-10} y={-10} width={plotW * t + 10} height={height + 20} />
        </clipPath>
      </defs>
      {[0, 0.5, 1].map((f) => (
        <line key={f} x1={0} x2={plotW * gridT} y1={top + plotH * f} y2={top + plotH * f} stroke={theme.grid} strokeWidth={1} />
      ))}
      {refLine && (
        <g opacity={gridT}>
          <line x1={0} x2={plotW * gridT} y1={y(refLine.value)} y2={y(refLine.value)} stroke={theme.accent} strokeWidth={1.5} strokeDasharray="10 8" />
          <text x={plotW - 8} y={y(refLine.value) - 12} textAnchor="end" fill={theme.accent} fontSize={26}>{refLine.label}</text>
        </g>
      )}
      <g clipPath={`url(#${clipId})`}>
        {gap && (
          <path
            d={`${path(series[gap.upper])} ${[...series[gap.lower]].reverse().map((p, j) => `L${x(n - 1 - j).toFixed(1)} ${y(p.value).toFixed(1)}`).join(" ")} Z`}
            fill={withAlpha(theme.critical, 0.14)}
          />
        )}
        {series.map((s, k) => (
          <path key={names[k]} d={path(s)} fill="none" stroke={colors[k]} strokeWidth={4 + 2.5 * pulse} strokeLinecap="round" strokeLinejoin="round" />
        ))}
      </g>
      {gap && (
        <text x={plotW * 0.5} y={(y(series[gap.upper][Math.floor(n / 2)].value) + y(series[gap.lower][Math.floor(n / 2)].value)) / 2} textAnchor="middle" fill={theme.critical} fontSize={30} fontWeight={600} opacity={labelOpacity}>
          {gap.label}
        </text>
      )}
      {series.map((s, k) => (
        <g key={`head-${names[k]}`} opacity={tickerOpacity}>
          <circle cx={plotW * t} cy={headY(s)} r={16 + 8 * pulse} fill={colors[k]} opacity={0.18} />
          <circle cx={plotW * t} cy={headY(s)} r={7} fill={colors[k]} />
        </g>
      ))}
      <text x={plotW * t + 18} y={headY(series[0]) - 18} fill={colors[0]} fontSize={28} fontWeight={600} opacity={tickerOpacity}>
        {formatValue(series[0][Math.round(fi)].value)}
      </text>
      {series.map((s, k) => (
        <g key={names[k]} opacity={labelOpacity}>
          <circle cx={plotW} cy={y(s.at(-1)!.value)} r={6} fill={colors[k]} />
          <text x={plotW + 18} y={labelY.get(k)! - 6} fill={colors[k]} fontSize={28} fontWeight={600}>{formatValue(s.at(-1)!.value)}</text>
          <text x={plotW + 18} y={labelY.get(k)! + 22} fill={theme.muted} fontSize={22}>{names[k]}</text>
        </g>
      ))}
      {refLine && refGap && arrowT > 0 && (
        <g>
          <line x1={arrowX} x2={arrowX} y1={arrowFrom} y2={arrowY} stroke={theme.critical} strokeWidth={3} />
          <polygon points={`${arrowX - 10},${arrowY + 14} ${arrowX + 10},${arrowY + 14} ${arrowX},${arrowY}`} fill={theme.critical} opacity={arrowT} />
          <text x={arrowX - 18} y={(arrowFrom + arrowTo) / 2} textAnchor="end" fill={theme.critical} fontSize={28} fontWeight={600} opacity={arrowT}>{refGap}</text>
        </g>
      )}
      <text x={0} y={height - 8} fill={theme.muted} fontSize={22} opacity={gridT}>{series[0][0].date}</text>
      <text x={plotW} y={height - 8} textAnchor="end" fill={theme.muted} fontSize={22} opacity={gridT}>{series[0].at(-1)!.date}</text>
    </svg>
  );
};
