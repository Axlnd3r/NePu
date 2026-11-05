import { Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { theme } from "../theme";

type Props = {
  text: string;
  /** Frame (inside the current Sequence) where the first word starts to enter. */
  startFrame?: number;
  /** Frames between consecutive words. */
  wordStagger?: number;
  /** Font size as a share of the composition width. */
  size?: number;
  maxWidth?: number | string;
  /** Words (trailing punctuation ignored) drawn in the accent colour with an underline that sweeps in. */
  highlight?: string[];
};

const SPRING = Easing.spring({ damping: 200 });
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// One idea per beat: the sentence appears word by word, each word rising out of a blur.
export const Narration: React.FC<Props> = ({ text, startFrame = 0, wordStagger = 4, size = 0.052, maxWidth = "86%", highlight = [] }) => {
  const frame = useCurrentFrame();
  const { width } = useVideoConfig();
  const words = text.split(" ");

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        columnGap: "0.28em",
        rowGap: "0.08em",
        maxWidth,
        fontFamily: theme.font,
        fontSize: Math.round(width * size),
        fontWeight: 500,
        letterSpacing: "-0.035em",
        lineHeight: 1.08,
        color: theme.ink,
      }}
    >
      {words.map((word, i) => {
        const at = startFrame + i * wordStagger;
        const hot = highlight.includes(word) || highlight.includes(word.replace(/[.,:;!?]+$/, ""));
        return (
          <span
            key={`${word}-${i}`}
            style={{
              display: "inline-block",
              opacity: interpolate(frame - at, [0, 16], [0, 1], { ...clamp, easing: SPRING }),
              translate: `0 ${interpolate(frame - at, [0, 16], [0.4, 0], { ...clamp, easing: SPRING })}em`,
              filter: `blur(${interpolate(frame - at, [0, 16], [6, 0], clamp)}px)`,
              color: hot ? theme.accent : theme.ink,
              backgroundImage: hot ? `linear-gradient(${theme.accent}, ${theme.accent})` : undefined,
              backgroundRepeat: "no-repeat",
              backgroundPosition: "0 100%",
              backgroundSize: `${interpolate(frame - at - 10, [0, 14], [0, 100], { ...clamp, easing: Easing.out(Easing.cubic) })}% 0.06em`,
            }}
          >
            {word}
          </span>
        );
      })}
    </div>
  );
};
