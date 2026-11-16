import { Canvas, Circle, Fill, RadialGradient, vec } from "@shopify/react-native-skia";
import { useEffect } from "react";
import { type LayoutChangeEvent, StyleSheet } from "react-native";
import {
  cancelAnimation,
  Easing,
  type SharedValue,
  useDerivedValue,
  useSharedValue,
  withRepeat,
  withTiming,
} from "react-native-reanimated";
import { useTheme } from "../theme";
import { type Blob, BLOB_PERIOD_MS, blobAt, canvasBlobs, effectLevel, isAnimated } from "./presets";

interface Size {
  width: number;
  height: number;
}

function DriftingBlob({
  blob,
  t,
  size,
}: {
  blob: Blob;
  t: SharedValue<number>;
  size: SharedValue<Size>;
}) {
  const center = useDerivedValue(() => {
    const at = blobAt(blob, t.get(), size.get());
    return vec(at.cx, at.cy);
  });
  const radius = useDerivedValue(() => blobAt(blob, 0, size.get()).r);
  return (
    <Circle c={center} r={radius}>
      <RadialGradient
        c={center}
        r={radius}
        colors={[blob.color, "transparent"]}
        positions={[0, 0.7]}
      />
    </Circle>
  );
}

/**
 * The canvas background: slow drifting colour blobs behind home, brief and
 * list screens. The blobs stand still on the low tier and with reduced motion.
 */
export function CanvasBlobs() {
  const theme = useTheme();
  const animated = isAnimated(effectLevel(theme));
  const t = useSharedValue(0);
  const size = useSharedValue<Size>({ width: 0, height: 0 });

  useEffect(() => {
    if (!animated) {
      t.set(0);
      return;
    }
    t.set(withRepeat(withTiming(1, { duration: BLOB_PERIOD_MS, easing: Easing.linear }), -1));
    return () => cancelAnimation(t);
  }, [animated, t]);

  const onLayout = (event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    size.set({ width, height });
  };

  return (
    <Canvas testID="canvas-blobs" style={StyleSheet.absoluteFill} onLayout={onLayout}>
      <Fill color={theme.tokens.colors.canvas} />
      {canvasBlobs.map((blob) => (
        <DriftingBlob key={blob.color} blob={blob} t={t} size={size} />
      ))}
    </Canvas>
  );
}
