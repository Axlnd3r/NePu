import { staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { useWindowedAudioData, visualizeAudio } from "@remotion/media-utils";
import { pulseFromSpectrum, scaleBins } from "../pulse";

export const TRACK = "audio/nepu-theme.m4a";
const SAMPLES = 64;
// Bass bins of a normalised track sit well below 1; this brings a typical beat into 0..1.
const GAIN = 2.5;
// The upper half of the spectrum is nearly empty for this track, so the visualizer shows the lower half.
const SHOWN_BINS = 32;

// Spectrum (log-scaled, 0..1) and beat strength at the current frame of the composition. Call it at the
// composition root (the global frame) and pass the values down.
export const useSpectrum = (): { bins: number[]; pulse: number } => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { audioData, dataOffsetInSeconds } = useWindowedAudioData({ src: staticFile(TRACK), frame, fps, windowInSeconds: 30 });
  if (!audioData) return { bins: new Array(SHOWN_BINS).fill(0), pulse: 0 };
  const raw = visualizeAudio({ fps, frame, audioData, numberOfSamples: SAMPLES, optimizeFor: "speed", dataOffsetInSeconds });
  return { bins: scaleBins(raw).slice(0, SHOWN_BINS), pulse: Math.min(1, pulseFromSpectrum(raw) * GAIN) };
};
