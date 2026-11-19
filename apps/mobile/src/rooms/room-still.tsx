// One still of a room. A real image when there is one (a hero view from the
// twin, a render); otherwise a quiet drawn stand-in in the theme's warm
// neutrals. The stand-in is a placeholder, not a picture of anyone's room:
// real photos replace it through the same `still` value with no code change.
import { useTheme } from "@sajao/ui";
import { Image, type StyleProp, View, type ViewStyle } from "react-native";
import type { RoomStill } from "./rooms";
import { samplesAllowed } from "./samples";

export interface RoomStillViewProps {
  still: RoomStill;
  /** Read by screen readers; omit when the still is decoration beside a title. */
  label?: string;
  style?: StyleProp<ViewStyle>;
  testID?: string;
  /** The picture could not be loaded, such as a photo the phone has since cleared. */
  onMissing?: () => void;
  /**
   * Draw a stand-in room where there is no picture yet, in builds that allow
   * samples. Off for a person's own room: its tile stays plain until a real
   * picture exists.
   */
  drawn?: boolean;
}

/** A bare room (before) or the same room furnished (after), drawn from theme colours. */
function DrawnRoom({ look, view = 0 }: { look: "before" | "after"; view?: 0 | 1 | 2 }) {
  const { tokens } = useTheme();
  const { colors, spacing } = tokens;
  const after = look === "after";
  const soft = { borderRadius: spacing.md, borderCurve: "continuous" } as const;
  return (
    <View
      style={{
        flex: 1,
        backgroundColor: after ? colors.daylight : colors.sand,
        // The same room from the other side, or from closer in.
        transform: view === 1 ? [{ scaleX: -1 }] : view === 2 ? [{ scale: 1.3 }] : [],
      }}
    >
      {/* Window, with daylight. */}
      <View
        style={{
          position: "absolute",
          left: "10%",
          top: "12%",
          width: "26%",
          height: "38%",
          backgroundColor: colors.surface,
          opacity: after ? 0.95 : 0.6,
          ...soft,
        }}
      />
      {/* Floor. */}
      <View
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: "30%",
          backgroundColor: colors.wood,
          opacity: after ? 0.55 : 0.3,
        }}
      />
      {after ? (
        <>
          {/* Rug. */}
          <View
            style={{
              position: "absolute",
              left: "22%",
              right: "14%",
              bottom: "6%",
              height: "13%",
              backgroundColor: colors.sand,
              ...soft,
            }}
          />
          {/* Lamp glow and lamp. */}
          <View
            style={{
              position: "absolute",
              right: "9%",
              top: "20%",
              width: "22%",
              aspectRatio: 1,
              borderRadius: tokens.radius.pill,
              backgroundColor: colors.surface,
              opacity: 0.8,
            }}
          />
          <View
            style={{
              position: "absolute",
              right: "19%",
              top: "30%",
              width: "1.5%",
              bottom: "24%",
              backgroundColor: colors.wood,
            }}
          />
        </>
      ) : null}
      {/* Sofa: plain before, upholstered with a cushion after. */}
      <View
        style={{
          position: "absolute",
          left: "30%",
          width: "44%",
          bottom: "20%",
          height: "22%",
          backgroundColor: after ? colors.accent : colors.inkTertiary,
          opacity: after ? 0.9 : 0.28,
          ...soft,
        }}
      />
      {after ? (
        <>
          <View
            style={{
              position: "absolute",
              left: "34%",
              width: "12%",
              bottom: "27%",
              height: "11%",
              backgroundColor: colors.daylight,
              ...soft,
            }}
          />
          {/* Side table. */}
          <View
            style={{
              position: "absolute",
              left: "12%",
              width: "13%",
              bottom: "18%",
              height: "13%",
              backgroundColor: colors.wood,
              ...soft,
            }}
          />
        </>
      ) : null}
    </View>
  );
}

export function RoomStillView({
  still,
  label,
  style,
  testID,
  drawn = true,
  onMissing,
}: RoomStillViewProps) {
  const { tokens } = useTheme();
  return (
    <View
      testID={testID}
      accessible={label !== undefined}
      accessibilityRole={label === undefined ? undefined : "image"}
      accessibilityLabel={label}
      style={[{ overflow: "hidden", backgroundColor: tokens.colors.sand }, style]}
    >
      {
        still.kind === "image" ? (
          <Image
            source={{ uri: still.uri }}
            resizeMode="cover"
            style={{ flex: 1 }}
            onError={onMissing}
          />
        ) : drawn && samplesAllowed() ? (
          <DrawnRoom look={still.look} view={still.view} />
        ) : null /* A store build never shows a drawn room: the tile stays plain until the photo exists. */
      }
    </View>
  );
}
