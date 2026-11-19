// A room on My home: its hero still, its name, when it was last updated and
// how many designs it has.
import { motion, Text, useTheme } from "@sajao/ui";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, View } from "react-native";
import Animated, { cubicBezier } from "react-native-reanimated";
import { designsLabel, type Room, updatedLabel } from "./rooms";
import { RoomStillView } from "./room-still";

export function roomName(
  room: Room,
  t: (key: string, values: Record<string, number>) => string,
): string {
  return room.name ?? t("rooms.defaultName", { number: room.number });
}

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);
const pressEasing = cubicBezier(...motion.press.bezier);

export function RoomCard({
  room,
  nowMs,
  onPress,
}: {
  room: Room;
  nowMs: number;
  /** Opens the room. */
  onPress: () => void;
}) {
  const { t } = useTranslation();
  const { tokens, tier, duration } = useTheme();
  const [pressed, setPressed] = useState(false);
  const { colors, spacing, radius } = tokens;
  const updated = updatedLabel(room.updatedAtMs, nowMs);
  const designs = designsLabel(room.designCount);
  const name = roomName(room, t);
  const meta = `${t(updated.key, updated.values ?? {})} · ${t(designs.key, designs.values ?? {})}`;
  return (
    <AnimatedPressable
      testID={`room-card-${room.id}`}
      accessibilityRole="button"
      accessibilityLabel={`${name}. ${meta}`}
      pressRetentionOffset={16}
      // Feedback on press-in, open on press-out.
      onPressIn={() => setPressed(true)}
      onPressOut={() => setPressed(false)}
      onPress={onPress}
      style={{
        backgroundColor: colors.surface,
        borderRadius: radius.card,
        borderCurve: "continuous",
        boxShadow: tokens.shadows[tier].card,
        transform: [{ scale: pressed ? motion.press.scale : 1 }],
        transitionProperty: "transform",
        transitionDuration: duration(motion.press.durationMs),
        transitionTimingFunction: pressEasing,
      }}
    >
      <RoomStillView
        still={room.still}
        // Your own room never shows a drawn stand-in.
        drawn={false}
        style={{
          aspectRatio: 16 / 10,
          borderTopLeftRadius: radius.card,
          borderTopRightRadius: radius.card,
          borderCurve: "continuous",
        }}
      />
      <View style={{ padding: spacing.gutter, gap: spacing.xs }}>
        <Text variant="heading" numberOfLines={1}>
          {name}
        </Text>
        <Text variant="meta" tone="secondary">
          {meta}
        </Text>
      </View>
    </AnimatedPressable>
  );
}
