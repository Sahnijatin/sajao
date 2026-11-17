// The simple scan's progress: one clean ring that fills as the camera turns
// and moves, with the share in the middle. It turns to the success colour
// once Done is ready. Drawn once per change, so it needs no animation and
// behaves the same with reduced motion and on low-tier phones.
import { Canvas, Circle, Path, Skia } from "@shopify/react-native-skia";
import { Text, useTheme } from "@sajao/ui";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";
import { ringHalves, ringSweepDegrees } from "./ring-geometry";

export interface ProgressRingProps {
  /** 0 to 1. */
  progress: number;
  /** Done is on. */
  ready: boolean;
  /**
   * The coverage meter's two parts, 0 to 1 each: the loop fills the first
   * half of the ring, the sweeps the second. Without it the ring is one arc.
   */
  parts?: { loop: number; sweeps: number };
  size?: number;
}

const STROKE = 5;

export function ProgressRing({ progress, ready, parts, size = 64 }: ProgressRingProps) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const centre = size / 2;
  const radius = (size - STROKE) / 2 - 1;
  const sweep = ringSweepDegrees(progress);
  const percent = Math.round(Math.min(1, Math.max(0, progress)) * 100);
  const loop = parts?.loop;
  const sweeps = parts?.sweeps;
  const arc = useMemo(() => {
    const oval = Skia.XYWHRect(centre - radius, centre - radius, radius * 2, radius * 2);
    const builder = Skia.PathBuilder.Make();
    if (loop !== undefined && sweeps !== undefined) {
      // Two halves with a small gap between: the loop, then the sweeps.
      for (const half of ringHalves(loop, sweeps)) {
        if (half.sweep > 0) builder.arcToOval(oval, half.start, half.sweep, true);
      }
      return builder.detach();
    }
    // From the top, clockwise.
    return builder.arcToOval(oval, -90, sweep, true).detach();
  }, [centre, radius, sweep, loop, sweeps]);

  return (
    <View
      testID="scan-progress-ring"
      accessible
      accessibilityRole="progressbar"
      accessibilityLabel={t("capture.mapped", { percent })}
      accessibilityValue={{ min: 0, max: 100, now: percent }}
      style={{ width: size, height: size, alignItems: "center", justifyContent: "center" }}
    >
      <Canvas style={{ position: "absolute", width: size, height: size }} pointerEvents="none">
        <Circle cx={centre} cy={centre} r={radius + STROKE / 2} color="rgba(0, 0, 0, 0.45)" />
        <Circle
          cx={centre}
          cy={centre}
          r={radius}
          color="rgba(255, 255, 255, 0.25)"
          style="stroke"
          strokeWidth={STROKE}
        />
        {sweep > 0 || parts ? (
          <Path
            path={arc}
            color={ready ? tokens.colors.success : tokens.colors.accent}
            style="stroke"
            strokeWidth={STROKE}
            strokeCap="round"
          />
        ) : null}
      </Canvas>
      <Text variant="captionStrong" tone="onDark">
        {`${percent}%`}
      </Text>
    </View>
  );
}
