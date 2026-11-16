import { useTheme } from "@sajao/ui";
import { Canvas, Group, Line, Path, RoundedRect, Skia, vec } from "@shopify/react-native-skia";
import { useMemo } from "react";
import type { PlanDrawing } from "./space-profile";

/** The floor plan of a space, top down: outline, doors, windows and existing items. */
export function PlanView({
  drawing,
  width,
  height,
}: {
  drawing: PlanDrawing;
  width: number;
  height: number;
}) {
  const { colors } = useTheme().tokens;
  const outline = useMemo(() => {
    const builder = Skia.PathBuilder.Make();
    drawing.outline.forEach((point, index) =>
      index === 0 ? builder.moveTo(point.x, point.y) : builder.lineTo(point.x, point.y),
    );
    return builder.close().detach();
  }, [drawing.outline]);

  return (
    <Canvas testID="space-plan" style={{ width, height }}>
      <Path path={outline} color={colors.accentTint} />
      <Path
        path={outline}
        color={colors.accent}
        style="stroke"
        strokeWidth={2.5}
        strokeJoin="round"
      />
      {drawing.items.map((item) => (
        <Group
          key={item.id}
          origin={vec(item.x, item.y)}
          transform={[{ rotate: (-item.rotationDeg * Math.PI) / 180 }]}
          opacity={item.action === "remove" ? 0.35 : 1}
        >
          <RoundedRect
            x={item.x - item.width / 2}
            y={item.y - item.depth / 2}
            width={item.width}
            height={item.depth}
            r={6}
            color={item.action === "keep" ? colors.success : colors.inkTertiary}
            opacity={0.35}
          />
        </Group>
      ))}
      {drawing.openings.map((opening) => (
        <Line
          key={opening.id}
          p1={vec(opening.from.x, opening.from.y)}
          p2={vec(opening.to.x, opening.to.y)}
          color={opening.kind === "window" ? "#8fc7ff" : colors.surface}
          strokeWidth={6}
          strokeCap="round"
        />
      ))}
    </Canvas>
  );
}
