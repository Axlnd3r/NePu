import { Audio } from "@remotion/media";
import { linearTiming, TransitionPresentation, TransitionSeries } from "@remotion/transitions";
import { iris } from "@remotion/transitions/iris";
import { slide } from "@remotion/transitions/slide";
import { wipe } from "@remotion/transitions/wipe";
import { AbsoluteFill, interpolate, staticFile, useVideoConfig } from "remotion";
import { TRACK, useSpectrum } from "./components/AudioPulse";
import { Backdrop } from "./components/Backdrop";
import { CameraPush } from "./components/CameraPush";
import { Visualizer } from "./components/Visualizer";
import { zoom } from "./components/Zoom";
import { BreakEven } from "./scenes/BreakEven";
import { Capture } from "./scenes/Capture";
import { Coverage } from "./scenes/Coverage";
import { Hero } from "./scenes/Hero";
import { Issuance } from "./scenes/Issuance";
import { Outro } from "./scenes/Outro";
import { Proof } from "./scenes/Proof";
import { SCENES, SceneKey, sequenceFrames, TOTAL, TRANSITION_FRAMES, TRANSITIONS, TransitionKind } from "./timeline";

const SCENE_COMPONENTS: Record<SceneKey, React.FC<{ pulse?: number }>> = {
  issuance: Issuance,
  capture: Capture,
  coverage: Coverage,
  hero: Hero,
  breakeven: BreakEven,
  proof: Proof,
  outro: Outro,
};

const AUDIO_FADE = 45;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const presentationFor = (kind: TransitionKind, width: number, height: number): TransitionPresentation<any> => {
  switch (kind) {
    case "slide-right":
      return slide({ direction: "from-right" });
    case "slide-up":
      return slide({ direction: "from-bottom" });
    case "wipe":
      return wipe({ direction: "from-left" });
    case "iris":
      return iris({ width, height });
    case "zoom":
      return zoom();
  }
};

export const Demo: React.FC = () => {
  const { width, height } = useVideoConfig();
  const { bins, pulse } = useSpectrum();
  return (
    <AbsoluteFill>
      <Backdrop pulse={pulse} />
      <TransitionSeries>
        {SCENES.flatMap((scene, i) => {
          const Scene = SCENE_COMPONENTS[scene.id];
          const items = [
            <TransitionSeries.Sequence key={scene.id} name={scene.id} durationInFrames={sequenceFrames(i)}>
              <CameraPush frames={sequenceFrames(i)}>
                <Scene pulse={pulse} />
              </CameraPush>
            </TransitionSeries.Sequence>,
          ];
          if (i < TRANSITIONS.length) {
            items.push(
              <TransitionSeries.Transition
                key={`to-${SCENES[i + 1].id}`}
                presentation={presentationFor(TRANSITIONS[i], width, height)}
                timing={linearTiming({ durationInFrames: TRANSITION_FRAMES })}
              />,
            );
          }
          return items;
        })}
      </TransitionSeries>
      <Visualizer bins={bins} />
      <Audio
        src={staticFile(TRACK)}
        volume={(f) => interpolate(f, [TOTAL - AUDIO_FADE, TOTAL], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}
      />
    </AbsoluteFill>
  );
};
