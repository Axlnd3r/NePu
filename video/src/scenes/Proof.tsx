import { AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { GlassCard } from "../components/GlassCard";
import { Narration } from "../components/Narration";
import { NearMark } from "../components/NearMark";
import { copy, fillCopy, proofLines } from "../copy";
import { typed } from "../count";
import { theme } from "../theme";
import { videoData } from "../data";

const FIRST_LINE = 16;
const LINE_STAGGER = 36;
const CHARS_PER_FRAME = 1.8;
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// A terminal: every line types out in turn, results get a check mark, the cursor blinks on the last line.
export const Proof: React.FC<{ pulse?: number }> = ({ pulse = 0 }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const pad = Math.round(width * 0.06);
  const lines = proofLines(videoData.proof);
  const text = fillCopy(copy.proof, { network: videoData.proof.network });
  const font = Math.round(width * 0.0185);
  const blinkOn = Math.floor(frame / 8) % 2 === 0;

  return (
    <AbsoluteFill style={{ padding: pad, justifyContent: "center", gap: Math.round(height * 0.04) }}>
      <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
        <NearMark size={Math.round(width * 0.05)} startFrame={0} />
        <Narration text={text} highlight={["committed"]} maxWidth="82%" size={0.044} />
      </div>
      <GlassCard pulse={pulse} style={{ fontFamily: "Consolas, 'Courier New', monospace", fontSize: font, lineHeight: 1.7, padding: 36 }}>
        {lines.map((line, i) => {
          const start = FIRST_LINE + i * LINE_STAGGER;
          const doneAt = start + Math.ceil(line.length / CHARS_PER_FRAME);
          const typing = frame >= start && frame < doneAt;
          const lastAndDone = i === lines.length - 1 && frame >= doneAt;
          return (
            <div
              key={line}
              style={{ display: "flex", gap: 14, alignItems: "baseline", minHeight: "1.7em", color: i === 0 ? theme.accent : theme.ink, whiteSpace: "pre-wrap", wordBreak: "break-all" }}
            >
              <span>
                {typed(line, frame, start, CHARS_PER_FRAME)}
                {(typing || (lastAndDone && blinkOn)) && <span style={{ color: theme.accent }}>▍</span>}
              </span>
              {i > 0 && (
                <span
                  style={{
                    color: theme.accent,
                    opacity: interpolate(frame - doneAt, [0, 6], [0, 1], clamp),
                    scale: interpolate(frame - doneAt, [0, 6, 12], [1.8, 0.9, 1], { ...clamp, easing: Easing.out(Easing.cubic) }),
                  }}
                >
                  ✓
                </span>
              )}
            </div>
          );
        })}
      </GlassCard>
      <div style={{ fontFamily: theme.font, fontSize: Math.round(width * theme.size.source), color: theme.muted, letterSpacing: "0.04em" }}>
        Source: data/proof.json · run {videoData.proof.runId}
      </div>
    </AbsoluteFill>
  );
};
