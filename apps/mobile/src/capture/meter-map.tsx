// The coverage meter's map: the floor walked so far, the parts of the loop
// still missing, where to stand for the next sweep, and the phone. Drawn
// once per change; nothing animates, so reduced motion needs no special case.
import { Canvas, Circle, Rect } from "@shopify/react-native-skia";
import { colors } from "@sajao/ui";
import { useMemo } from "react";
import type { Point2 } from "./ar/guidance";
import type { MeterState } from "./coverage-meter";
import { meterMapLayout } from "./meter-map-layout";

export interface MeterMapProps {
  meter: MeterState;
  position: Point2 | null;
  yaw: number;
  size?: number;
}

export function MeterMap({ meter, position, yaw, size = 72 }: MeterMapProps) {
  const layout = useMemo(
    () => meterMapLayout(meter, size, position ? { position, yaw } : null),
    [meter, size, position, yaw],
  );
  const nose = layout.phone
    ? {
        x: layout.phone.x + 7 * Math.sin((layout.phone.headingDeg * Math.PI) / 180),
        y: layout.phone.y - 7 * Math.cos((layout.phone.headingDeg * Math.PI) / 180),
      }
    : null;
  return (
    <Canvas testID="scan-meter-map" style={{ width: size, height: size }} pointerEvents="none">
      <Rect x={0} y={0} width={size} height={size} color="rgba(0, 0, 0, 0.45)" />
      {layout.cells.map((cell) => (
        <Rect
          key={`${cell.x}:${cell.y}`}
          x={cell.x}
          y={cell.y}
          width={cell.size}
          height={cell.size}
          color={colors.accent}
          opacity={0.7}
        />
      ))}
      {layout.missing.map((gap) => (
        <Circle
          key={`${gap.x}:${gap.y}`}
          cx={gap.x}
          cy={gap.y}
          r={2.5}
          color="rgba(255, 255, 255, 0.55)"
          style="stroke"
          strokeWidth={1}
        />
      ))}
      {layout.sweeps.map((sweep) => (
        <Circle
          key={`${sweep.x}:${sweep.y}`}
          cx={sweep.x}
          cy={sweep.y}
          r={4}
          color={colors.success}
        />
      ))}
      {layout.next ? (
        <Circle
          cx={layout.next.x}
          cy={layout.next.y}
          r={5}
          color="#ffffff"
          style="stroke"
          strokeWidth={1.5}
        />
      ) : null}
      {layout.phone && nose ? (
        <>
          <Circle cx={nose.x} cy={nose.y} r={1.5} color="#ffffff" />
          <Circle cx={layout.phone.x} cy={layout.phone.y} r={3} color="#ffffff" />
        </>
      ) : null}
    </Canvas>
  );
}
