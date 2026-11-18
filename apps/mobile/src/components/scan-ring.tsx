// The scan's one progress ring: a thin arc that fills from the top as the
// room is covered and turns to the success colour when Done is ready. No
// number: the arc is the reading. Drawn once per change, so it costs nothing
// between changes and is the same with reduced motion and on low-tier phones.
import { Canvas, Circle, Path, Skia } from "@shopify/react-native-skia";
import { useTheme } from "@sajao/ui";
import { useMemo } from "react";
import { ringSweepDegrees } from "@/capture/ring-geometry";

export const SCAN_RING_STROKE = 3;

export function ScanRing({
  progress,
  ready,
  size,
}: {
  /** 0 to 1. */
  progress: number;
  ready: boolean;
  size: number;
}) {
  const { tokens } = useTheme();
  const centre = size / 2;
  const radius = (size - SCAN_RING_STROKE) / 2;
  const sweep = ringSweepDegrees(progress);
  const arc = useMemo(() => {
    const oval = Skia.XYWHRect(centre - radius, centre - radius, radius * 2, radius * 2);
    return Skia.PathBuilder.Make().arcToOval(oval, -90, sweep, true).detach();
  }, [centre, radius, sweep]);
  return (
    <Canvas style={{ position: "absolute", width: size, height: size }} pointerEvents="none">
      <Circle
        cx={centre}
        cy={centre}
        r={radius}
        color={tokens.glass.dark.border}
        style="stroke"
        strokeWidth={SCAN_RING_STROKE}
      />
      {sweep > 0 ? (
        <Path
          path={arc}
          color={ready ? tokens.colors.success : tokens.glass.dark.text}
          style="stroke"
          strokeWidth={SCAN_RING_STROKE}
          strokeCap="round"
        />
      ) : null}
    </Canvas>
  );
}
