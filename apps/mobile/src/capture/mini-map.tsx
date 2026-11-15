// The mini-map: a top-down view of the circle around the person scanning.
// Mapped directions are filled; the way the phone points is always up, so
// the map turns as you pan, like a compass.
import { Canvas, Circle, Path, Skia } from "@shopify/react-native-skia";
import { colors } from "@sajao/ui";
import { useMemo } from "react";
import { SECTOR_DEGREES, screenAngle } from "./coverage";
import { wrapDegrees } from "./pose";

export interface MiniMapProps {
  mapped: readonly boolean[];
  /** Where the phone points now, degrees; positive is turned left. */
  yaw: number;
  size?: number;
}

export function MiniMap({ mapped, yaw, size = 64 }: MiniMapProps) {
  const centre = size / 2;
  const radius = size / 2 - 2;
  const oval = useMemo(
    () => Skia.XYWHRect(centre - radius, centre - radius, radius * 2, radius * 2),
    [centre, radius],
  );

  const wedges = useMemo(() => {
    const builder = Skia.PathBuilder.Make();
    mapped.forEach((isMapped, sector) => {
      if (!isMapped) return;
      const from = wrapDegrees(sector * SECTOR_DEGREES - yaw);
      // The sector spans `from` to `from + SECTOR_DEGREES` to the left.
      builder
        .moveTo(centre, centre)
        .arcToOval(oval, screenAngle(from + SECTOR_DEGREES), SECTOR_DEGREES, false)
        .close();
    });
    return builder.detach();
  }, [mapped, yaw, centre, oval]);

  // A narrow wedge for where the camera looks now.
  const view = useMemo(
    () =>
      Skia.PathBuilder.Make()
        .moveTo(centre, centre)
        .arcToOval(oval, screenAngle(15), 30, false)
        .close()
        .detach(),
    [centre, oval],
  );

  return (
    <Canvas testID="scan-mini-map" style={{ width: size, height: size }} pointerEvents="none">
      <Circle cx={centre} cy={centre} r={radius} color="rgba(0, 0, 0, 0.45)" />
      <Path path={wedges} color={colors.accent} opacity={0.85} />
      <Path path={view} color="rgba(255, 255, 255, 0.35)" />
      <Circle
        cx={centre}
        cy={centre}
        r={radius}
        color="rgba(255, 255, 255, 0.6)"
        style="stroke"
        strokeWidth={1}
      />
      <Circle cx={centre} cy={centre} r={3} color="#ffffff" />
    </Canvas>
  );
}
