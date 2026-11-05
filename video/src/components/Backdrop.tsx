import { AbsoluteFill, random, useCurrentFrame, useVideoConfig } from "remotion";
import { theme, withAlpha } from "../theme";

const PARTICLES = 46;

// Living background behind every scene: a drifting hairline grid, a slow-moving champagne glow that
// brightens on the beat, and dust particles rising through the frame.
export const Backdrop: React.FC<{ pulse: number }> = ({ pulse }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const cell = Math.round(width / 14);
  const drift = (frame * 0.35) % cell;
  const grid = withAlpha(theme.accent, 0.07);

  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      <AbsoluteFill
        style={{
          backgroundImage: `linear-gradient(${grid} 1px, transparent 1px), linear-gradient(90deg, ${grid} 1px, transparent 1px)`,
          backgroundSize: `${cell}px ${cell}px`,
          backgroundPosition: `${drift}px ${drift}px`,
          maskImage: "radial-gradient(ellipse at center, black 35%, transparent 80%)",
        }}
      />
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at ${50 + 24 * Math.cos(frame / 90)}% ${40 + 16 * Math.sin(frame / 110)}%, ${withAlpha(theme.accent, 0.08 + 0.14 * pulse)}, transparent 55%)`,
        }}
      />
      <svg width={width} height={height} style={{ position: "absolute", inset: 0 }}>
        {Array.from({ length: PARTICLES }, (_, i) => {
          const speed = 0.4 + random(`ps-${i}`) * 1.2;
          const y = (((random(`py-${i}`) * height - frame * speed) % height) + height) % height;
          const x = random(`px-${i}`) * width + Math.sin((frame + i * 40) / 60) * 12;
          return (
            <circle
              key={i}
              cx={x}
              cy={y}
              r={1 + random(`pr-${i}`) * 2.2}
              fill={theme.accentDeep}
              opacity={Math.min(0.9, 0.12 + random(`po-${i}`) * 0.3 + 0.35 * pulse)}
            />
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};
