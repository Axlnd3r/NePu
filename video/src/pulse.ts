// Beat strength 0..1 from an audio spectrum: the mean of the lowest quarter of the bins.
export const pulseFromSpectrum = (bins: number[]): number => {
  if (bins.length === 0) return 0;
  const low = bins.slice(0, Math.max(1, Math.ceil(bins.length / 4)));
  const mean = low.reduce((sum, v) => sum + v, 0) / low.length;
  return Math.min(1, Math.max(0, mean));
};

// Spectrum magnitudes to 0..1 on a decibel scale, so the highs are visible next to the bass.
const MIN_DB = -60;
const MAX_DB = -15;
export const scaleBins = (bins: number[]): number[] =>
  bins.map((v) => (v <= 0 ? 0 : Math.min(1, Math.max(0, (20 * Math.log10(v) - MIN_DB) / (MAX_DB - MIN_DB)))));
