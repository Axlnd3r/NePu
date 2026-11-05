import { Composition } from "remotion";
import { Demo } from "./Demo";
import { FPS, TOTAL } from "./timeline";

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="Demo16x9" component={Demo} durationInFrames={TOTAL} fps={FPS} width={1920} height={1080} />
    <Composition id="Demo1x1" component={Demo} durationInFrames={TOTAL} fps={FPS} width={1080} height={1080} />
  </>
);
