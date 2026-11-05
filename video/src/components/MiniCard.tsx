import { Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { CardText } from "../copy";
import { theme } from "../theme";
import { GlassCard } from "./GlassCard";

type Props = CardText & {
  /** Frame (inside the Sequence) where the card fades in. */
  appearAt: number;
  pulse?: number;
  style?: React.CSSProperties;
};

// Small glass card for a module that is not a scene of its own (Distribution, Valuation, Developer).
export const MiniCard: React.FC<Props> = ({ title, value, caption, appearAt, pulse = 0, style }) => {
  const frame = useCurrentFrame();
  const { width } = useVideoConfig();
  const t = interpolate(frame - appearAt, [0, 14], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  return (
    <GlassCard pulse={pulse} style={{ opacity: t, transform: `translateY(${(1 - t) * 24}px)`, width: Math.round(width * 0.34), padding: 22, ...style }}>
      <div style={{ fontSize: Math.round(width * 0.0135), letterSpacing: "0.14em", textTransform: "uppercase", color: theme.accent }}>{title}</div>
      <div style={{ fontSize: Math.round(width * 0.03), fontWeight: 600, margin: "8px 0", color: theme.ink }}>{value}</div>
      <div style={{ fontSize: Math.round(width * theme.size.caption), lineHeight: 1.35, color: theme.ink2 }}>{caption}</div>
    </GlassCard>
  );
};
