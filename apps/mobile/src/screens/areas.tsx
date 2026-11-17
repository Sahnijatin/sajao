// A scan that went through more than one area: a photo of each, and one
// question, which to redesign. The others keep their photos and
// measurements on the Room tab. Designs are made for living rooms and
// bedrooms for now, so an area of another kind cannot be picked.
import { Button, Card, motion, playHaptic, Text, useTheme } from "@sajao/ui";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, ScrollView, View } from "react-native";
import Animated, { Easing, FadeIn } from "react-native-reanimated";
import { designsOffered, type RoomArea } from "@/rooms/room-content";
import { RoomStillView } from "@/rooms/room-still";
import { useSettings } from "@/state/settings";
import { formatArea } from "@/utils/format-length";

/** Each card follows the one above by this much as the list appears. */
const STAGGER_MS = 60;
/** Photos are landscape here: four wide by three tall. */
const PHOTO_ASPECT = 4 / 3;

export function AreasScreen({
  areas,
  chosenId = null,
  onChoose,
}: {
  areas: readonly RoomArea[];
  /** The area chosen before, when changing the choice. */
  chosenId?: string | null;
  onChoose: (areaId: string) => void;
}) {
  const { t } = useTranslation();
  const { tokens, duration } = useTheme();
  const { colors, spacing, radius } = tokens;
  const units = useSettings((state) => state.units);
  const firstOffered = areas.find((area) => designsOffered(area.spaceType))?.id ?? null;
  const [selected, setSelected] = useState<string | null>(chosenId ?? firstOffered);
  const fade = duration(motion.ease.durationMs);
  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.canvas }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={{
        padding: spacing.gutter,
        paddingBottom: spacing.sheetBottom * 2,
        gap: spacing.sheetBottom,
      }}
    >
      <View style={{ gap: spacing.md }}>
        <Text variant="title" accessibilityRole="header">
          {t("areas.title")}
        </Text>
        <Text tone="secondary">{t("areas.body", { count: areas.length })}</Text>
      </View>
      {areas.map((area, index) => {
        const offered = designsOffered(area.spaceType);
        const on = selected === area.id;
        const name = t(`space.typeNames.${area.spaceType ?? "other"}`, {
          defaultValue: t("areas.unnamed", { number: index + 1 }),
        });
        return (
          <Animated.View
            key={area.id}
            entering={
              fade > 0
                ? FadeIn.duration(fade)
                    .delay(index * STAGGER_MS)
                    .easing(Easing.bezier(...motion.ease.bezier))
                : undefined
            }
          >
            <Pressable
              testID={`area-${area.id}`}
              accessibilityRole="radio"
              accessibilityLabel={name}
              accessibilityState={{ selected: on, disabled: !offered }}
              disabled={!offered}
              onPress={() => {
                void playHaptic("levelReached");
                setSelected(area.id);
              }}
            >
              <Card
                style={{
                  padding: 0,
                  overflow: "hidden",
                  borderWidth: 2,
                  borderColor: on ? colors.accent : "transparent",
                  opacity: offered ? 1 : 0.6,
                }}
              >
                {area.photo ? (
                  <RoomStillView still={area.photo} style={{ aspectRatio: PHOTO_ASPECT }} />
                ) : (
                  <View
                    style={{
                      aspectRatio: PHOTO_ASPECT,
                      backgroundColor: colors.sand,
                      borderTopLeftRadius: radius.card,
                      borderTopRightRadius: radius.card,
                    }}
                  />
                )}
                <View style={{ padding: spacing.gutter, gap: spacing.xxs }}>
                  <Text variant="heading">{name}</Text>
                  {area.measures ? (
                    <Text variant="meta" tone="secondary">
                      {t("room.size.area", {
                        area: formatArea(area.measures.areaM2, units, t),
                      })}
                    </Text>
                  ) : null}
                  {offered ? null : (
                    <Text variant="caption" tone="tertiary">
                      {t("areas.notYet")}
                    </Text>
                  )}
                </View>
              </Card>
            </Pressable>
          </Animated.View>
        );
      })}
      <Text variant="caption" tone="tertiary">
        {t("areas.others")}
      </Text>
      <Button
        label={t("areas.choose")}
        disabled={selected === null}
        onPress={() => {
          if (selected === null) return;
          void playHaptic("roomVerified");
          onChoose(selected);
        }}
      />
    </ScrollView>
  );
}
