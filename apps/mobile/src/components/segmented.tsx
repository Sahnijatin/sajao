// A segmented control: a few peers, one chosen. The chosen segment lifts
// onto a surface with the segment shadow. Switching is instant, as tabs are
// peers and do not slide; a selection tick marks the change.
import { playHaptic, Text, touchTarget, useTheme } from "@sajao/ui";
import { Pressable, View } from "react-native";

export interface SegmentedProps<Key extends string> {
  segments: readonly { key: Key; label: string }[];
  selected: Key;
  onSelect: (key: Key) => void;
}

export function Segmented<Key extends string>({
  segments,
  selected,
  onSelect,
}: SegmentedProps<Key>) {
  const { tokens, tier } = useTheme();
  const { colors, spacing, radius } = tokens;
  return (
    <View
      accessibilityRole="tablist"
      style={{
        flexDirection: "row",
        padding: spacing.xs,
        gap: spacing.xs,
        borderRadius: radius.pill,
        backgroundColor: colors.sand,
      }}
    >
      {segments.map(({ key, label }) => {
        const on = key === selected;
        return (
          <Pressable
            key={key}
            accessibilityRole="tab"
            accessibilityLabel={label}
            accessibilityState={{ selected: on }}
            onPress={() => {
              if (on) return;
              void playHaptic("levelReached");
              onSelect(key);
            }}
            style={{
              flex: 1,
              minHeight: touchTarget - spacing.xs * 2,
              alignItems: "center",
              justifyContent: "center",
              paddingHorizontal: spacing.md,
              borderRadius: radius.pill,
              backgroundColor: on ? colors.surface : "transparent",
              boxShadow: on ? tokens.shadows[tier].segment : "none",
            }}
          >
            <Text variant="meta" tone={on ? "primary" : "secondary"} numberOfLines={1}>
              {label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}
