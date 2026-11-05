import { theme } from "../theme";

type Props = {
  /** Beat strength 0..1 from the music; brightens the hairline border. */
  pulse?: number;
  style?: React.CSSProperties;
  children?: React.ReactNode;
};

// Translucent card with a 1px hairline, 4px radius, as on the dashboard.
export const GlassCard: React.FC<Props> = ({ pulse = 0, style, children }) => (
  <div
    style={{
      background: theme.card,
      backdropFilter: "blur(14px)",
      border: `1px solid rgba(200, 173, 134, ${0.18 + 0.5 * pulse})`,
      borderRadius: 4,
      boxShadow: `0 0 ${24 * pulse}px rgba(200, 173, 134, ${0.25 * pulse})`,
      padding: 28,
      color: theme.ink,
      fontFamily: theme.font,
      ...style,
    }}
  >
    {children}
  </div>
);
