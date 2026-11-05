import { useVideoConfig } from "remotion";
import { theme } from "../theme";

// Music visualizer strip along the bottom edge: the track's spectrum, mirrored around the centre.
// Audio only, no data: the bars carry no figures.
export const Visualizer: React.FC<{ bins: number[] }> = ({ bins }) => {
  const { width, height } = useVideoConfig();
  const bars = [...[...bins].reverse(), ...bins];
  return (
    <div
      style={{
        position: "absolute",
        left: Math.round(width * 0.06),
        right: Math.round(width * 0.06),
        bottom: Math.round(height * 0.012),
        height: Math.round(height * 0.065),
        display: "flex",
        alignItems: "flex-end",
        gap: 3,
      }}
    >
      {bars.map((v, i) => (
        <div
          key={i}
          style={{ flex: 1, height: `${Math.max(0.04, v ** 2.2) * 100}%`, background: theme.accent, borderRadius: 2, opacity: 0.18 + 0.55 * v ** 2 }}
        />
      ))}
    </div>
  );
};
