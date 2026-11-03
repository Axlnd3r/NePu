// Number formatting. Every value passed here comes from site/public/data/*.json.

export function usd(value: number, digits = 1): string {
  const abs = Math.abs(value);
  if (abs >= 1e12) return `$${(value / 1e12).toFixed(digits)}T`;
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(digits)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(digits)}M`;
  if (abs >= 1e3) return `$${(value / 1e3).toFixed(digits)}K`;
  return `$${value.toFixed(2)}`;
}

export function near(value: number, digits = 0): string {
  const abs = Math.abs(value);
  if (abs >= 1e6) return `${(value / 1e6).toFixed(digits === 0 ? 2 : digits)}M NEAR`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(digits === 0 ? 1 : digits)}K NEAR`;
  return `${value.toFixed(digits)} NEAR`;
}

export function pct(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function ratio(value: number, digits = 3): string {
  return value.toFixed(digits);
}

export function times(value: number, digits = 2): string {
  return `${value.toFixed(digits)}x`;
}

export function compact(value: number): string {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(
    value,
  );
}
