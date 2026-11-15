import {
  BlurMask,
  Canvas,
  Group,
  LinearGradient,
  Path,
  Points,
  Rect,
  Skia,
  vec,
} from "@shopify/react-native-skia";
import { useMemo } from "react";
import type { StyleProp, ViewStyle } from "react-native";
import { useTheme } from "../theme";
import { effectLevel, scanMesh, scanMeshLayers } from "./presets";

export interface MeshPoint {
  x: number;
  y: number;
}

export interface MeshEffectProps {
  /** Mesh vertices in canvas pixels. */
  points: readonly MeshPoint[];
  /** Triangles as index triples into `points`. */
  triangles: readonly (readonly [number, number, number])[];
  /** x of the sweep's leading edge in pixels; omit to hide the sweep. */
  sweepX?: number;
  width: number;
  height: number;
  style?: StyleProp<ViewStyle>;
}

const SWEEP_WIDTH = 90;

/**
 * The live scan mesh: glowing edges over what the camera has mapped, with a
 * white sweep at the frontier. Low-tier phones get dots and edges only.
 * The mesh is feedback: nothing it draws is stored or used for dimensions.
 */
export function MeshEffect({ points, triangles, sweepX, width, height, style }: MeshEffectProps) {
  const layers = scanMeshLayers(effectLevel(useTheme()));
  const lite = !layers.glow;

  const { edges, faces } = useMemo(() => {
    const edgePath = Skia.PathBuilder.Make();
    const facePath = Skia.PathBuilder.Make();
    const drawn = new Set<string>();
    for (const [a, b, c] of triangles) {
      const corners = [points[a], points[b], points[c]];
      const [p, q, r] = corners;
      if (!p || !q || !r) continue;
      facePath.moveTo(p.x, p.y).lineTo(q.x, q.y).lineTo(r.x, r.y).close();
      for (const [i, j] of [
        [a, b],
        [b, c],
        [c, a],
      ] as const) {
        const key = i < j ? `${i}-${j}` : `${j}-${i}`;
        if (drawn.has(key)) continue;
        drawn.add(key);
        const from = points[i];
        const to = points[j];
        if (from && to) edgePath.moveTo(from.x, from.y).lineTo(to.x, to.y);
      }
    }
    return { edges: edgePath.detach(), faces: facePath.detach() };
  }, [points, triangles]);

  const dots = useMemo(() => points.map((point) => vec(point.x, point.y)), [points]);

  return (
    <Canvas testID="scan-mesh" style={[{ width, height }, style]} pointerEvents="none">
      {layers.faces ? (
        <Path path={faces} color={scanMesh.face.color} opacity={scanMesh.face.opacity} />
      ) : null}
      <Group>
        <Path
          path={edges}
          style="stroke"
          color={scanMesh.edge.color}
          strokeWidth={lite ? scanMesh.lite.edgeWidth : scanMesh.edge.width}
          opacity={lite ? scanMesh.lite.edgeOpacity : scanMesh.edge.opacity}
        >
          {layers.glow ? <BlurMask blur={scanMesh.glowBlurRadius} style="solid" /> : null}
        </Path>
        <Points
          points={dots}
          mode="points"
          color={scanMesh.point.color}
          opacity={scanMesh.point.opacity}
          strokeCap="round"
          strokeWidth={2 * (lite ? scanMesh.lite.pointRadius : scanMesh.point.radius)}
        />
      </Group>
      {layers.sweep && sweepX !== undefined ? (
        <Rect x={sweepX - SWEEP_WIDTH} y={0} width={SWEEP_WIDTH} height={height}>
          <LinearGradient
            start={vec(sweepX - SWEEP_WIDTH, 0)}
            end={vec(sweepX, 0)}
            colors={[scanMesh.sweep.from, scanMesh.sweep.mid, scanMesh.sweep.to]}
            positions={[0, 0.85, 1]}
          />
        </Rect>
      ) : null}
    </Canvas>
  );
}
