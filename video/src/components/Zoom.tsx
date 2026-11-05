import { AbsoluteFill } from "remotion";
import type { TransitionPresentation, TransitionPresentationComponentProps } from "@remotion/transitions";

// Scene change that pushes through the cut: the old scene shrinks and fades, the new one settles in from larger.
const ZoomPresentation: React.FC<TransitionPresentationComponentProps<Record<string, never>>> = ({
  children,
  presentationDirection,
  presentationProgress: p,
}) => {
  const entering = presentationDirection === "entering";
  return (
    <AbsoluteFill
      style={{
        // Out first, then in: the old scene is gone by the midpoint, so the two never overlap.
        opacity: entering ? Math.max(0, p * 2 - 1) : Math.max(0, 1 - p * 2),
        scale: entering ? 1.12 - 0.12 * p : 1 - 0.06 * p,
        filter: `blur(${(entering ? 1 - p : p) * 6}px)`,
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

export const zoom = (): TransitionPresentation<Record<string, never>> => ({ component: ZoomPresentation, props: {} });
