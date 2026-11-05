import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";

// Slow push-in over the whole scene, so no frame is ever completely still.
export const CameraPush: React.FC<{ frames: number; children: React.ReactNode }> = ({ frames, children }) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill
      style={{
        scale: interpolate(frame, [0, frames], [1, 1.045], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.quad) }),
      }}
    >
      {children}
    </AbsoluteFill>
  );
};
