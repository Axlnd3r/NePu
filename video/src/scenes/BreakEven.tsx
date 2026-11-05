import { AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { GlassCard } from "../components/GlassCard";
import { MiniCard } from "../components/MiniCard";
import { Narration } from "../components/Narration";
import { copy, cardTexts, fillCopy, formatMillions, formatMultiple } from "../copy";
import { theme, withAlpha } from "../theme";
import { videoData } from "../data";
import { CARD_APPEAR } from "../timeline";

const BAR_START = 30;
const MARK_START = BAR_START + 55;
const MARK_FRAMES = 50;
const SPRING = Easing.spring({ damping: 200 });
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

const Bar: React.FC<{ label: string; value: string; share: number; color: string; width: number; children?: React.ReactNode }> = ({
  label, value, share, color, width, children,
}) => (
  <div style={{ fontFamily: theme.font }}>
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: Math.round(width * 0.018), color: theme.ink2, marginBottom: 10 }}>
      <span>{label}</span>
      <span style={{ color, fontWeight: 600 }}>{value}</span>
    </div>
    <div style={{ position: "relative", height: 26, background: theme.grid, borderRadius: 13 }}>
      <div style={{ height: "100%", width: `${share * 100}%`, background: color, borderRadius: 13 }} />
      {children}
    </div>
  </div>
);

export const BreakEven: React.FC<{ pulse?: number }> = ({ pulse = 0 }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const pad = Math.round(width * 0.06);
  const { multiple, volumeUsdPerDay, vStarUsdPerDay, asOf } = videoData.breakeven;
  const share = volumeUsdPerDay / vStarUsdPerDay;
  const grow1 = interpolate(frame - BAR_START, [0, 40], [0, 1], { ...clamp, easing: SPRING });
  const grow2 = interpolate(frame - BAR_START - 12, [0, 40], [0, 1], { ...clamp, easing: SPRING });
  // A marker travels from today's volume to the volume needed; its label is the multiple of today's volume
  // at the marker's position, so it ends exactly on the multiple (vStar / volume).
  const m = interpolate(frame - MARK_START, [0, MARK_FRAMES], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const markerAt = share + (1 - share) * m;
  const markerOpacity = interpolate(frame - MARK_START, [0, 8], [0, 1], clamp);
  const text = fillCopy(copy.breakeven, { multiple: formatMultiple(multiple) });

  return (
    <AbsoluteFill style={{ padding: pad, justifyContent: "center", gap: Math.round(height * 0.028) }}>
      <Narration text={text} highlight={["Not", "yet.", `${formatMultiple(multiple)}x`]} maxWidth="88%" />
      <GlassCard pulse={pulse} style={{ display: "flex", flexDirection: "column", gap: 36, padding: 36 }}>
        <Bar label="Average Intents volume per day" value={formatMillions(volumeUsdPerDay)} share={share * grow1} color={theme.accent} width={width} />
        <Bar label="Needed for capture to cover issuance" value={formatMillions(vStarUsdPerDay)} share={grow2} color={theme.critical} width={width}>
          <div
            style={{
              position: "absolute",
              left: `${markerAt * 100}%`,
              top: -10,
              width: 4,
              height: 46,
              background: theme.ink,
              borderRadius: 2,
              opacity: markerOpacity,
              boxShadow: `0 0 ${12 + 18 * pulse}px ${withAlpha(theme.ink, 0.7)}`,
            }}
          />
          <div
            style={{
              position: "absolute",
              left: `${markerAt * 100}%`,
              top: 44,
              // Centred under the marker, sliding to right-aligned near the end so it stays inside the card.
              translate: `${interpolate(markerAt, [0.8, 1], [-50, -100], clamp)}% 0`,
              fontSize: Math.round(width * 0.03),
              fontWeight: 700,
              color: theme.ink,
              fontVariantNumeric: "tabular-nums",
              opacity: markerOpacity,
            }}
          >
            {formatMultiple(markerAt / share)}x
          </div>
        </Bar>
        <div style={{ height: Math.round(width * 0.022) }} />
      </GlassCard>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 24 }}>
        <div style={{ flex: 1, fontFamily: theme.font, fontSize: Math.round(width * theme.size.source), color: theme.muted, letterSpacing: "0.04em" }}>
          Source: summary.json · at today's take rate and inflation, as of {asOf}
        </div>
        <MiniCard {...cardTexts(videoData.cards).valuation} appearAt={CARD_APPEAR.valuation} pulse={pulse} />
      </div>
    </AbsoluteFill>
  );
};
