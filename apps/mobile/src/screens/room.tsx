// One room, in exactly three tabs. Room: the room as it is, in its hero
// views, with its size. Designs: the three looks, with a Vastu view that
// switches on only when the scan has a compass reading. Shopping list: the
// chosen look's products, each with a price, a link and whether it fits.
// The look and its list are two views of one `Design` and cannot disagree.
import { Button, Card, Chip, Text, useTheme } from "@sajao/ui";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Linking, ScrollView, Switch, useWindowDimensions, View } from "react-native";
import { Segmented } from "@/components/segmented";
import { compassCalibrated, type RoomContent, type RoomLook } from "@/rooms/room-content";
import { RoomStillView } from "@/rooms/room-still";
import { shoppingFor } from "@/rooms/shopping";
import { useSettings } from "@/state/settings";
import { formatInr } from "@/utils/format-inr";
import { formatLength, type LengthUnits } from "@/utils/format-length";

export const ROOM_TABS = ["room", "designs", "shopping"] as const;
export type RoomTab = (typeof ROOM_TABS)[number];

/** Stills are portrait: three wide by four tall. */
const STILL_ASPECT = 3 / 4;

function Sample({ text }: { text: string }) {
  return (
    <Text variant="caption" tone="tertiary">
      {text}
    </Text>
  );
}

/** The room as it is: hero views to swipe through, its size, and the plan to come. */
function RoomTabBody({ content, units }: { content: RoomContent; units: LengthUnits }) {
  const { t } = useTranslation();
  const { tokens, tier } = useTheme();
  const { spacing, radius } = tokens;
  const { width } = useWindowDimensions();
  const cardWidth = Math.round((width - spacing.gutter * 2) * 0.86);
  const size = content.dimensions;
  return (
    <>
      {/* Hero views only: fixed viewpoints to swipe between, no free movement. */}
      <ScrollView
        horizontal
        testID="room-hero-views"
        showsHorizontalScrollIndicator={false}
        decelerationRate="fast"
        snapToInterval={cardWidth + spacing.xl}
        style={{ marginHorizontal: -spacing.gutter }}
        contentContainerStyle={{ paddingHorizontal: spacing.gutter, gap: spacing.xl }}
      >
        {content.heroViews.map((view, index) => (
          <RoomStillView
            key={view.id}
            still={view.still}
            label={t("reveal.view", { number: index + 1, total: content.heroViews.length })}
            style={{
              width: cardWidth,
              aspectRatio: STILL_ASPECT,
              borderRadius: radius.card,
              borderCurve: "continuous",
              boxShadow: tokens.shadows[tier].card,
            }}
          />
        ))}
      </ScrollView>

      <Card style={{ gap: spacing.xs }}>
        <Text variant="captionStrong" tone="tertiary">
          {t("room.size.title")}
        </Text>
        {size ? (
          <>
            <Text variant="figure" selectable>
              {t("room.size.floor", {
                long: formatLength(size.long.value_m, units, t),
                short: formatLength(size.short.value_m, units, t),
              })}
            </Text>
            <Text tone="secondary" selectable>
              {t("room.size.ceiling", { height: formatLength(size.ceiling.value_m, units, t) })}
            </Text>
            {/* Every size says where it came from and how far off it may be. */}
            <Text variant="caption" tone="tertiary">
              {t(`room.size.source.${size.long.source}`, {
                band: formatLength(
                  Math.max(size.long.error_band_m, size.short.error_band_m),
                  units,
                  t,
                ),
              })}
            </Text>
          </>
        ) : (
          <Text tone="secondary">{t("room.size.none")}</Text>
        )}
      </Card>

      {/* The furnished floor plan goes here when it is built. */}
      <Card testID="room-plan-slot" style={{ gap: spacing.xs }}>
        <Text variant="captionStrong" tone="tertiary">
          {t("room.plan.title")}
        </Text>
        <Text tone="secondary">{t("room.plan.body")}</Text>
      </Card>

      {content.sample ? <Sample text={t("room.sample")} /> : null}
    </>
  );
}

function LookPicker({
  looks,
  selected,
  onSelect,
}: {
  looks: readonly RoomLook[];
  selected: number;
  onSelect: (index: number) => void;
}) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: tokens.spacing.md }}>
      {looks.map((look, index) => (
        <Chip
          key={look.design.id}
          label={t(`design.slot.${look.design.slot}`)}
          selected={index === selected}
          haptic="swapLands"
          onPress={() => onSelect(index)}
        />
      ))}
    </View>
  );
}

function DesignsTabBody({
  content,
  look,
  picker,
}: {
  content: RoomContent;
  look: RoomLook;
  picker: React.ReactNode;
}) {
  const { t } = useTranslation();
  const { tokens, tier } = useTheme();
  const { colors, spacing, radius } = tokens;
  const calibrated = compassCalibrated(content);
  const [vastu, setVastu] = useState(false);
  const { design } = look;
  return (
    <>
      {picker}
      <RoomStillView
        still={look.still}
        label={t(`design.slot.${design.slot}`)}
        style={{
          aspectRatio: STILL_ASPECT,
          borderRadius: radius.card,
          borderCurve: "continuous",
          boxShadow: tokens.shadows[tier].card,
        }}
      />
      <View style={{ gap: spacing.xs }}>
        <Text variant="heading">{t(`design.slot.${design.slot}`)}</Text>
        <Text variant="meta" tone="secondary" selectable>
          {t("design.total", { amount: formatInr(design.total_cost.amount_minor) })}
        </Text>
      </View>
      <Card style={{ gap: spacing.md }}>
        <Text variant="captionStrong" tone="tertiary">
          {t("designs.why")}
        </Text>
        {design.explanations.map((line) => (
          <Text key={line}>{line}</Text>
        ))}
        <Text variant="meta" tone="secondary">
          {t(design.check_report.passed ? "designs.fits" : "designs.check")}
        </Text>
      </Card>

      <Card style={{ gap: spacing.md }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xl }}>
          <View style={{ flex: 1, gap: spacing.xxs }}>
            <Text variant="label">{t("designs.vastu")}</Text>
            {calibrated ? null : (
              <Text variant="caption" tone="tertiary">
                {t("designs.vastuNeedsCompass")}
              </Text>
            )}
          </View>
          <Switch
            testID="vastu-toggle"
            accessibilityLabel={t("designs.vastu")}
            value={calibrated && vastu}
            disabled={!calibrated}
            onValueChange={setVastu}
            trackColor={{ false: colors.sand, true: colors.accent }}
            thumbColor={colors.surface}
          />
        </View>
        {calibrated && vastu ? (
          <>
            <Text tone="secondary">{t("designs.vastuPoints")}</Text>
            {/* Every Vastu view carries this label. */}
            <Text variant="caption" tone="tertiary">
              {t("vastu.label")}
            </Text>
          </>
        ) : null}
      </Card>

      {content.sample ? <Sample text={t("reveal.sample")} /> : null}
    </>
  );
}

function ShoppingTabBody({
  content,
  look,
  picker,
}: {
  content: RoomContent;
  look: RoomLook;
  picker: React.ReactNode;
}) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const { colors, spacing } = tokens;
  const shopping = shoppingFor(look.design);
  return (
    <>
      {picker}
      <Card style={{ padding: 0 }}>
        {shopping.lines.map((line, index) => (
          <View
            key={line.id}
            testID={`shopping-line-${line.id}`}
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: spacing.xl,
              padding: spacing.gutter,
              borderTopWidth: index === 0 ? 0 : 1,
              borderTopColor: colors.hairline,
            }}
          >
            <View style={{ flex: 1, gap: spacing.xxs }}>
              <Text variant="bodyStrong">{line.title}</Text>
              <Text variant="meta" tone="secondary" selectable>
                {formatInr(line.priceMinor)}
              </Text>
              <Text variant="caption" tone="tertiary">
                {line.inStock ? t(`shopping.fit.${line.fit}`) : t("shopping.outOfStock")}
              </Text>
            </View>
            {line.url ? (
              <Button
                label={t("shopping.buy")}
                variant="tint"
                size="small"
                accessibilityLabel={t("shopping.buyItem", { item: line.title })}
                // Sample products have example links; real ones open at the retailer.
                disabled={content.sample || !line.inStock}
                onPress={() => void Linking.openURL(line.url as string)}
              />
            ) : null}
          </View>
        ))}
      </Card>

      <View
        style={{
          flexDirection: "row",
          justifyContent: "space-between",
          alignItems: "baseline",
          paddingHorizontal: spacing.gutter,
        }}
      >
        <Text variant="label">{t("shopping.total")}</Text>
        {shopping.consistent ? (
          <Text variant="figure" selectable testID="shopping-total">
            {formatInr(shopping.totalMinor)}
          </Text>
        ) : (
          // The list and the look must never disagree: no total beats a wrong one.
          <Text tone="secondary">{t("shopping.checking")}</Text>
        )}
      </View>

      {content.sample ? <Sample text={t("shopping.sample")} /> : null}
    </>
  );
}

export function RoomScreen({ content }: { content: RoomContent }) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const { colors, spacing } = tokens;
  const units = useSettings((state) => state.units);
  const [tab, setTab] = useState<RoomTab>("room");
  // The chosen look is shared by Designs and Shopping list. Best match first.
  const [chosen, setChosen] = useState(Math.min(1, content.looks.length - 1));
  const look = content.looks[chosen];
  const picker = <LookPicker looks={content.looks} selected={chosen} onSelect={setChosen} />;

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
      <Segmented
        segments={ROOM_TABS.map((key) => ({ key, label: t(`room.tabs.${key}`) }))}
        selected={tab}
        onSelect={setTab}
      />
      {tab === "room" ? <RoomTabBody content={content} units={units} /> : null}
      {tab === "designs" && look ? (
        <DesignsTabBody content={content} look={look} picker={picker} />
      ) : null}
      {tab === "shopping" && look ? (
        <ShoppingTabBody content={content} look={look} picker={picker} />
      ) : null}
      {tab !== "room" && !look ? <Text tone="secondary">{t("rooms.designs.none")}</Text> : null}
    </ScrollView>
  );
}
