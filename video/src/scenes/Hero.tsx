import { AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { GlassCard } from "../components/GlassCard";
import { MiniCard } from "../components/MiniCard";
import { Narration } from "../components/Narration";
import { copy, cardTexts, fillCopy, formatCents } from "../copy";
import { countUp } from "../count";
import { theme, withAlpha } from "../theme";
import { videoData } from "../data";
import { CARD_APPEAR } from "../timeline";

const COUNT_START = 36;
const COUNT_FRAMES = 90;
const COUNT_END = COUNT_START + COUNT_FRAMES;
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Hero: React.FC<{ pulse?: number }> = ({ pulse = 0 }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const pad = Math.round(width * 0.06);
  const cents = formatCents(videoData.hero.crUsd30);
  const shown = countUp(Number(cents), frame, COUNT_START, COUNT_FRAMES);
  const text = fillCopy(copy.hero, { cents });

  return (
    <AbsoluteFill style={{ padding: pad, justifyContent: "center", gap: Math.round(height * 0.03) }}>
      <Narration text={text} highlight={[cents]} maxWidth="88%" />
      <GlassCard
        pulse={pulse}
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24, padding: 36, position: "relative", overflow: "hidden" }}
      >
        {/* A light sweep across the card once the count lands. */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: `linear-gradient(110deg, transparent 35%, ${withAlpha(theme.accentDeep, 0.16)} 50%, transparent 65%)`,
            translate: `${interpolate(frame, [COUNT_END, COUNT_END + 50], [-110, 110], clamp)}% 0`,
          }}
        />
        <div>
          <div
            style={{
              fontSize: Math.round(width * 0.17),
              fontWeight: 600,
              letterSpacing: "-0.05em",
              lineHeight: 1,
              color: theme.accentDeep,
              fontVariantNumeric: "tabular-nums",
              transformOrigin: "left bottom",
              scale: interpolate(frame, [COUNT_END, COUNT_END + 8, COUNT_END + 22], [1, 1.08, 1], clamp),
              textShadow: `0 0 ${interpolate(frame, [COUNT_END, COUNT_END + 10, COUNT_END + 40], [0, 40, 12], clamp)}px ${withAlpha(theme.accent, 0.6)}`,
            }}
          >
            {shown}¢
          </div>
          <div
            style={{
              fontSize: Math.round(width * 0.02),
              color: theme.ink2,
              marginTop: 12,
              opacity: interpolate(frame, [COUNT_START + 20, COUNT_START + 40], [0, 1], clamp),
              translate: `0 ${interpolate(frame, [COUNT_START + 20, COUNT_START + 40], [12, 0], { ...clamp, easing: Easing.out(Easing.cubic) })}px`,
            }}
          >
            per dollar of new NEAR issued, as buybacks or gas burn
          </div>
        </div>
        <MiniCard {...cardTexts(videoData.cards).developer} appearAt={CARD_APPEAR.developer} pulse={pulse} />
      </GlassCard>
      <div style={{ fontFamily: theme.font, fontSize: Math.round(width * theme.size.source), color: theme.muted, letterSpacing: "0.04em" }}>
        Source: summary.json · {videoData.windows.mid} days to {videoData.hero.date}
      </div>
    </AbsoluteFill>
  );
};
