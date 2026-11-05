// "Obsidian and champagne", copied from site/app/globals.css so the video matches the dashboard.
export const theme = {
  bg: "#000000",
  card: "rgba(13, 12, 10, 0.72)",
  ink: "#fff7dd",
  ink2: "#cdc5ad",
  muted: "#9a958c",
  grid: "#1f1d19",
  ring: "rgba(255, 247, 221, 0.18)",
  accent: "#c8ad86",
  accentSoft: "#2e271c",
  accentLight: "#866a3f",
  accentDeep: "#f1e3c6",
  series2: "#b58a3a",
  series3: "#b374ad",
  neutral: "#66635f",
  critical: "#c96f5a",
  // Share of the composition width. Small text must stay legible at feed size.
  size: { caption: 0.016, source: 0.016 },
  font: '"Inter Variable", Inter, system-ui, -apple-system, "Segoe UI", sans-serif',
} as const;

// A theme colour (#rrggbb) at the given opacity, so components never type rgba() figures.
export const withAlpha = (hex: string, alpha: number): string => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
};
