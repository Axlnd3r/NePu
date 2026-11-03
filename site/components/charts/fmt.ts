// Formatters usable inside client charts (functions cannot be passed from server components).
export type Fmt = "ratio" | "pct" | "usd" | "near" | "bps" | "count";

export function formatValue(v: number, fmt: Fmt, axis = false): string {
  const abs = Math.abs(v);
  switch (fmt) {
    case "ratio":
      if (axis && abs >= 1000)
        return new Intl.NumberFormat("en-US", { notation: "compact" }).format(v);
      return axis ? String(Number(v.toPrecision(2))) : v.toFixed(3);
    case "pct":
      return `${(v * 100).toFixed(axis ? 0 : 1)}%`;
    case "bps":
      return `${(v * 10_000).toFixed(axis ? 1 : 2)} bp`;
    case "usd":
      if (abs >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
      if (abs >= 1e9) return `$${(v / 1e9).toFixed(axis ? 1 : 2)}B`;
      if (abs >= 1e6) return `$${(v / 1e6).toFixed(axis ? 0 : 1)}M`;
      if (abs >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
      return `$${v.toFixed(0)}`;
    case "near":
      if (abs >= 1e6) return `${(v / 1e6).toFixed(axis ? 1 : 2)}M`;
      if (abs >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
      return v.toFixed(0);
    case "count":
      return new Intl.NumberFormat("en-US").format(Math.round(v));
  }
}
