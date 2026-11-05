import { AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { Narration } from "../components/Narration";
import { NearMark } from "../components/NearMark";
import { copy, displayUrl } from "../copy";
import { typed } from "../count";
import { theme, withAlpha } from "../theme";
import { videoData } from "../data";

const LINKS_START = 48;
const CHARS_PER_FRAME = 1.2;
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Outro: React.FC<{ pulse?: number }> = ({ pulse = 0 }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const pad = Math.round(width * 0.06);
  const dashboard = displayUrl(videoData.links.dashboard);
  const repo = displayUrl(videoData.links.repo);
  const repoStart = LINKS_START + Math.ceil(dashboard.length / CHARS_PER_FRAME) + 4;

  return (
    <AbsoluteFill style={{ padding: pad, justifyContent: "center", alignItems: "flex-start", gap: Math.round(height * 0.05) }}>
      <div style={{ filter: `drop-shadow(0 0 ${12 + 34 * pulse}px ${withAlpha(theme.accent, 0.35 + 0.4 * pulse)})` }}>
        <NearMark size={Math.round(width * 0.12)} startFrame={0} assemble />
      </div>
      <Narration text={copy.outro} startFrame={22} size={0.06} highlight={["Evidence"]} />
      <div
        style={{
          fontFamily: theme.font,
          fontSize: Math.round(width * 0.02),
          lineHeight: 1.6,
          color: theme.ink2,
          opacity: interpolate(frame - LINKS_START + 6, [0, 10], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) }),
        }}
      >
        <div style={{ color: theme.accent, letterSpacing: "0.14em", textTransform: "uppercase", fontSize: Math.round(width * 0.012) }}>NEAR Capture Ledger</div>
        <div>{typed(dashboard, frame, LINKS_START, CHARS_PER_FRAME)}</div>
        <div>{typed(repo, frame, repoStart, CHARS_PER_FRAME)}</div>
      </div>
    </AbsoluteFill>
  );
};
