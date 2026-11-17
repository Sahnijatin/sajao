// A room on My home: its hero still, its name, when it was last updated and
// how many designs it has.
import { Text, useTheme } from "@sajao/ui";
import { useTranslation } from "react-i18next";
import { View } from "react-native";
import { designsLabel, type Room, updatedLabel } from "./rooms";
import { RoomStillView } from "./room-still";

export function roomName(
  room: Room,
  t: (key: string, values: Record<string, number>) => string,
): string {
  return room.name ?? t("rooms.defaultName", { number: room.number });
}

export function RoomCard({ room, nowMs }: { room: Room; nowMs: number }) {
  const { t } = useTranslation();
  const { tokens, tier } = useTheme();
  const { colors, spacing, radius } = tokens;
  const updated = updatedLabel(room.updatedAtMs, nowMs);
  const designs = designsLabel(room.designCount);
  const name = roomName(room, t);
  const meta = `${t(updated.key, updated.values ?? {})} · ${t(designs.key, designs.values ?? {})}`;
  return (
    <View
      testID={`room-card-${room.id}`}
      accessible
      accessibilityLabel={`${name}. ${meta}`}
      style={{
        backgroundColor: colors.surface,
        borderRadius: radius.card,
        borderCurve: "continuous",
        boxShadow: tokens.shadows[tier].card,
      }}
    >
      <RoomStillView
        still={room.still}
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
    </View>
  );
}
