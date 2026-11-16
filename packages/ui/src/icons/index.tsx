// Small line icons drawn with Skia, so they look the same on both platforms
// and need no icon font or extra native package. Paths sit on a 24 by 24 grid.
import { Canvas, Group, Path, Skia } from "@shopify/react-native-skia";
import { useMemo } from "react";
import type { StyleProp, ViewStyle } from "react-native";

export const iconPaths = {
  close: { d: "M6 6 L18 18 M18 6 L6 18", filled: false },
  torch: {
    d: "M7 2 H17 V6 L14.5 10 V21 A1 1 0 0 1 13.5 22 H10.5 A1 1 0 0 1 9.5 21 V10 L7 6 Z M7 6 H17 M12 13 V15",
    filled: false,
  },
  torchOn: {
    d: "M7 2 H17 V6 L14.5 10 V21 A1 1 0 0 1 13.5 22 H10.5 A1 1 0 0 1 9.5 21 V10 L7 6 Z",
    filled: true,
  },
} as const;

export type IconName = keyof typeof iconPaths;

export interface IconProps {
  name: IconName;
  size?: number;
  color: string;
  style?: StyleProp<ViewStyle>;
}

export function Icon({ name, size = 22, color, style }: IconProps) {
  const { d, filled } = iconPaths[name];
  const path = useMemo(() => Skia.Path.MakeFromSVGString(d), [d]);
  return (
    <Canvas style={[{ width: size, height: size }, style]} pointerEvents="none">
      {path ? (
        <Group transform={[{ scale: size / 24 }]}>
          <Path
            path={path}
            color={color}
            style={filled ? "fill" : "stroke"}
            strokeWidth={2}
            strokeCap="round"
            strokeJoin="round"
          />
        </Group>
      ) : null}
    </Canvas>
  );
}
