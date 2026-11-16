// The payoff after a scan. First the room itself, in its hero views; then
// the three looks, each with its name and what everything in it costs. The
// stills swipe sideways. Each look is a view of one `Design`: its total is
// read from that design and never worked out here.
import { Button, motion, playHaptic, Text, useTheme } from "@sajao/ui";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ScrollView, useWindowDimensions, View } from "react-native";
import Animated, { Easing, FadeIn } from "react-native-reanimated";
import { SafeAreaView } from "react-native-safe-area-context";
import type { RoomContent } from "@/rooms/room-content";
import type { RoomStill } from "@/rooms/rooms";
import { RoomStillView } from "@/rooms/room-still";
import { formatInr } from "@/utils/format-inr";

/** Each card follows the one before it by this much as the looks land. */
const CASCADE_MS = 90;
/** Stills are portrait: three wide by four tall. */
const STILL_ASPECT = 3 / 4;

export interface RevealProps {
  content: RoomContent;
  /** On to the room itself. */
  onOpenRoom: () => void;
}

export function RevealScreen({ content, onOpenRoom }: RevealProps) {
  const { t } = useTranslation();
  const { tokens, tier, duration } = useTheme();
  const { colors, spacing, radius } = tokens;
  const { width } = useWindowDimensions();
  const [phase, setPhase] = useState<"room" | "looks">("room");
  // The next card peeks in from the right, so it is clear there is more.
  const cardWidth = Math.round((width - spacing.gutter * 2) * 0.86);

  const fade = duration(motion.ease.durationMs);
  const entering = (index: number) =>
    fade > 0
      ? FadeIn.duration(fade)
          .delay(index * CASCADE_MS)
          .easing(Easing.bezier(...motion.ease.bezier))
      : undefined;

  const card = (
    key: string,
    index: number,
    still: RoomStill,
    label: string,
    below?: React.ReactNode,
  ) => (
    <Animated.View
      key={key}
      testID={`reveal-card-${key}`}
      entering={entering(index)}
      style={{
        width: cardWidth,
        backgroundColor: colors.surface,
        borderRadius: radius.card,
        borderCurve: "continuous",
        boxShadow: tokens.shadows[tier].card,
      }}
    >
      <RoomStillView
        still={still}
        label={label}
        style={{
          aspectRatio: STILL_ASPECT,
          borderTopLeftRadius: radius.card,
          borderTopRightRadius: radius.card,
          borderBottomLeftRadius: below ? 0 : radius.card,
          borderBottomRightRadius: below ? 0 : radius.card,
          borderCurve: "continuous",
        }}
      />
      {below}
    </Animated.View>
  );

  const showLooks = () => {
    // The looks land with a light cascade under the fingers.
    void playHaptic("designReveal");
    setPhase("looks");
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.canvas }}>
      <ScrollView
        contentContainerStyle={{
          flexGrow: 1,
          paddingVertical: spacing.sheetBottom,
          gap: spacing.sheetBottom,
        }}
      >
        <Animated.View
          key={`title-${phase}`}
          entering={entering(0)}
          style={{ paddingHorizontal: spacing.gutter }}
        >
          <Text variant="title" accessibilityRole="header">
            {t(phase === "room" ? "reveal.roomTitle" : "reveal.looksTitle")}
          </Text>
        </Animated.View>

        <ScrollView
          key={phase}
          testID={`reveal-${phase}`}
          horizontal
          showsHorizontalScrollIndicator={false}
          decelerationRate="fast"
          snapToInterval={cardWidth + spacing.xl}
          contentContainerStyle={{
            paddingHorizontal: spacing.gutter,
            // Room for the card shadow.
            paddingBottom: spacing.sheetBottom,
            gap: spacing.xl,
          }}
        >
          {phase === "room"
            ? content.heroViews.map((view, index) =>
                card(
                  view.id,
                  index,
                  view.still,
                  t("reveal.view", { number: index + 1, total: content.heroViews.length }),
                ),
              )
            : content.looks.map((look, index) =>
                card(
                  look.design.slot,
                  index,
                  look.still,
                  t(`design.slot.${look.design.slot}`),
                  <View style={{ padding: spacing.gutter, gap: spacing.xs }}>
                    <Text variant="heading">{t(`design.slot.${look.design.slot}`)}</Text>
                    <Text variant="meta" tone="secondary" selectable>
                      {t("design.total", {
                        amount: formatInr(look.design.total_cost.amount_minor),
                      })}
                    </Text>
                  </View>,
                ),
              )}
        </ScrollView>

        <View style={{ flex: 1 }} />
        <View style={{ paddingHorizontal: spacing.gutter, gap: spacing.xl }}>
          {content.sample && phase === "looks" ? (
            <Text variant="caption" tone="tertiary">
              {t("reveal.sample")}
            </Text>
          ) : null}
          {phase === "room" ? (
            <Button label={t("reveal.roomCta")} onPress={showLooks} />
          ) : (
            <Button label={t("reveal.looksCta")} onPress={onOpenRoom} />
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
