import { BlurView, type BlurViewProps } from "expo-blur";
import { Platform, StyleSheet, View, type ViewProps } from "react-native";
import { useTheme } from "../theme";

export interface GlassSurfaceProps extends ViewProps {
  /**
   * Android only: the BlurTargetView this surface blurs. Without it Android
   * shows the tinted fallback, which is also what the low tier always shows.
   */
  blurTarget?: BlurViewProps["blurTarget"];
}

// expo-blur intensity runs 0 to 100; this maps the 28 px LiveMap radius.
const BLUR_INTENSITY = 56;

/**
 * Frosted glass for camera overlays, sheets and floating toolbars. Standard
 * devices get a live blur; the low tier gets a tinted surface. The blur is
 * static: never animate its intensity, crossfade the whole surface instead.
 */
export function GlassSurface({ blurTarget, style, children, ...rest }: GlassSurfaceProps) {
  const { tokens, tier } = useTheme();
  const { glass, radius } = tokens;
  const canBlur = tier === "standard" && (Platform.OS !== "android" || blurTarget != null);

  return (
    <View
      style={[
        {
          borderRadius: radius.pane,
          borderWidth: StyleSheet.hairlineWidth,
          borderColor: glass.border,
          overflow: "hidden",
          backgroundColor: canBlur ? glass.fill : glass.fallbackFill,
        },
        style,
      ]}
      {...rest}
    >
      {canBlur ? (
        <BlurView
          testID="glass-blur"
          tint="light"
          intensity={BLUR_INTENSITY}
          blurMethod="dimezisBlurViewSdk31Plus"
          {...(blurTarget ? { blurTarget } : {})}
          style={StyleSheet.absoluteFill}
        />
      ) : null}
      {children}
    </View>
  );
}
