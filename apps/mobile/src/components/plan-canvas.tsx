// The drawn part of the room plan: the floor outline with its soft error-band
// edge, walls solid and open sides dashed, doors and windows, the design's items to scale, and the clearance
// lines. Skia only; the numbers on the plan are text laid over it.
import { useTheme } from "@sajao/ui";
import { Canvas, DashPathEffect, Line, Path, Skia, vec } from "@shopify/react-native-skia";
import { useMemo } from "react";
import type { DesignPlan, Px } from "@/rooms/design-plan";

function closedPath(points: readonly Px[]) {
  const builder = Skia.PathBuilder.Make();
  points.forEach((point, index) =>
    index === 0 ? builder.moveTo(point.x, point.y) : builder.lineTo(point.x, point.y),
  );
  return builder.close().detach();
}

export function PlanCanvas({
  plan,
  width,
  height,
}: {
  plan: DesignPlan;
  width: number;
  height: number;
}) {
  const { colors } = useTheme().tokens;
  const outline = useMemo(() => closedPath(plan.outline), [plan.outline]);
  const items = useMemo(() => plan.items.map((item) => closedPath(item.corners)), [plan.items]);
  return (
    <Canvas style={{ width, height }} pointerEvents="none">
      {/* Walls not tape-measured: a soft band as wide as their error band, both ways. */}
      {plan.haloPx > 0 ? (
        <Path
          path={outline}
          color={colors.sand}
          style="stroke"
          strokeWidth={plan.haloPx * 2}
          strokeJoin="round"
        />
      ) : null}
      <Path path={outline} color={colors.surface} />
      {/* Walls are solid. An open side, where the room runs on with no wall, is a light dashed line. */}
      {plan.edges.map((edge, index) =>
        edge.kind === "wall" ? (
          <Line
            key={`edge-${index}`}
            p1={vec(edge.from.x, edge.from.y)}
            p2={vec(edge.to.x, edge.to.y)}
            color={colors.ink}
            strokeWidth={2.5}
            strokeCap="round"
          />
        ) : (
          <Line
            key={`edge-${index}`}
            p1={vec(edge.from.x, edge.from.y)}
            p2={vec(edge.to.x, edge.to.y)}
            color={colors.inkTertiary}
            strokeWidth={1.5}
          >
            <DashPathEffect intervals={[6, 6]} />
          </Line>
        ),
      )}
      {plan.openings.map((opening) => (
        <Line
          key={opening.id}
          p1={vec(opening.from.x, opening.from.y)}
          p2={vec(opening.to.x, opening.to.y)}
          color={opening.kind === "window" ? colors.daylight : colors.surface}
          strokeWidth={5}
          strokeCap="round"
        />
      ))}
      {items.map((path, index) => {
        const id = plan.items[index]?.id;
        // The selected piece stands out; the rest stay as they are.
        const chosen = id !== undefined && id === plan.selected?.id;
        return (
          <Path
            key={id}
            path={path}
            color={chosen ? colors.accent : colors.wood}
            opacity={chosen ? 0.75 : 0.45}
          />
        );
      })}
      {items.map((path, index) => (
        <Path
          key={`${plan.items[index]?.id}-edge`}
          path={path}
          color={colors.wood}
          style="stroke"
          strokeWidth={1.5}
          strokeJoin="round"
        />
      ))}
      {plan.clearances.map((gap) => (
        <Line
          key={gap.itemId}
          p1={vec(gap.from.x, gap.from.y)}
          p2={vec(gap.to.x, gap.to.y)}
          color={colors.success}
          strokeWidth={1.5}
        />
      ))}
    </Canvas>
  );
}
