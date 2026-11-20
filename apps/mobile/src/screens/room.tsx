// One room, in exactly three tabs. Room: the room as it is, in hero photos
// and measured dimensions (walls, openings, big items), with no 3D viewer. Designs: the three looks, with a Vastu view that
// switches on only when the scan has a compass reading. Shopping list: the
// chosen look's products, each with a price, a link and whether it fits.
// The look and its list are two views of one `Design` and cannot disagree.
import { Button, Card, Chip, Text, useTheme } from "@sajao/ui";
import type { Dimension } from "@sajao/schemas";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Image,
  Linking,
  Pressable,
  ScrollView,
  Switch,
  useWindowDimensions,
  View,
} from "react-native";
import { DesignPlanView } from "@/components/design-plan-view";
import { JobProgress } from "@/components/job-progress";
import type { RoomJobState } from "@/state/room-jobs";
import { Segmented } from "@/components/segmented";
import { twinViewerEnabled } from "@/features";
import { isApprox, leastCertain, wallName } from "@/rooms/measures";
import {
  compassCalibrated,
  contentForArea,
  designsOffered,
  hasAreas,
  redesignArea,
  type RoomContent,
  type RoomLook,
} from "@/rooms/room-content";
import { edgeKinds, fitClaimsAllowed } from "@/rooms/room-shape";
import { RoomStillView } from "@/rooms/room-still";
import { shoppingFor } from "@/rooms/shopping";
import { vastuEnabled } from "@/features";
import { useSettings } from "@/state/settings";
import { formatInr } from "@/utils/format-inr";
import { formatArea, formatLength, type LengthUnits } from "@/utils/format-length";

export const ROOM_TABS = ["room", "designs", "shopping"] as const;
export type RoomTab = (typeof ROOM_TABS)[number];

/** The side of a product photo on the shopping list. */
const PHOTO = 56;
/** The plan's box: a little wider than tall, like most rooms. */
const PLAN_ASPECT = 0.85;
/** Stills are portrait: three wide by four tall. */
const STILL_ASPECT = 3 / 4;

/**
 * The sample label: the same strip at the top of every tab, so nothing
 * below it can be read as your own room, looks or prices.
 */
function Sample({ text }: { text: string }) {
  const { tokens } = useTheme();
  const { colors, spacing, radius } = tokens;
  return (
    <View
      testID="sample-note"
      style={{
        padding: spacing.lg,
        borderRadius: radius.card,
        backgroundColor: colors.sand,
      }}
    >
      <Text variant="caption" tone="secondary">
        {text}
      </Text>
    </View>
  );
}

/** Where a value came from and how far off it may be, shown when its line is tapped. */
interface Provenance {
  text: string;
  /** The band is wide enough to say "approx." beside the value. */
  approx: boolean;
}

/**
 * One measured thing: what it is and its value, clean. A wide error band
 * adds a small "approx." beside the value. Tapping the line shows where the
 * value came from and its error band; tapping again hides it.
 */
function Measure({
  title,
  value,
  provenance,
}: {
  title: string;
  value: string;
  provenance: Provenance;
}) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const [open, setOpen] = useState(false);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${title}, ${provenance.approx ? `${t("room.approx")} ` : ""}${value}`}
      accessibilityHint={t("room.measureHint")}
      accessibilityState={{ expanded: open }}
      hitSlop={tokens.spacing.sm}
      onPress={() => setOpen((shown) => !shown)}
      style={{ gap: tokens.spacing.xxs }}
    >
      <View
        style={{
          flexDirection: "row",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: tokens.spacing.xl,
        }}
      >
        <Text style={{ flexShrink: 1 }}>{title}</Text>
        <View style={{ flexDirection: "row", alignItems: "baseline", gap: tokens.spacing.sm }}>
          {provenance.approx ? (
            <Text variant="caption" tone="tertiary">
              {t("room.approx")}
            </Text>
          ) : null}
          <Text variant="bodyStrong" style={{ fontVariant: ["tabular-nums"] }}>
            {value}
          </Text>
        </View>
      </View>
      {open ? (
        <Text variant="caption" tone="tertiary" testID="measure-provenance">
          {provenance.text}
        </Text>
      ) : null}
    </Pressable>
  );
}

/**
 * The room as it is, without a 3D viewer: hero photos to swipe through, then
 * what was measured: the floor and ceiling, each wall, doors and windows, and
 * the big things in the room. A place is kept for the 3D view behind its
 * flag, and for the furnished plan.
 */
function RoomTabBody({
  content,
  units,
  show3d,
  look,
  onMeasure,
}: {
  content: RoomContent;
  units: LengthUnits;
  show3d: boolean;
  /** "Measure to confirm", for a room whose sizes are estimates. */
  onMeasure?: () => void;
  /** The look whose furniture the plan shows; none draws the room alone. */
  look: RoomLook | undefined;
}) {
  const { t } = useTranslation();
  const { tokens, tier } = useTheme();
  const { spacing, radius } = tokens;
  const { width } = useWindowDimensions();
  const cardWidth = Math.round((width - spacing.gutter * 2) * 0.86);
  // The plan fills its card: the screen less the page and card padding.
  const planWidth = width - spacing.gutter * 4;
  const measures = content.measures;
  // A real room shows only views with a picture: never a blank card.
  const [missing, setMissing] = useState<string[]>([]);
  const heroViews = content.heroViews.filter(
    (view) => !missing.includes(view.id) && (content.sample || view.still.kind === "image"),
  );
  // A piece tapped on the plan; a different look starts with none.
  const [picked, setPicked] = useState<{ slot: string; id: string } | null>(null);
  const selectedId = look && picked?.slot === look.design.slot ? picked.id : null;
  const selectedItem = look?.design.items.find((item) => item.id === selectedId) ?? null;
  // Gaps to the walls are fit claims: measured rooms only.
  const gaps = fitClaimsAllowed(content.confidence);
  // The source and error band of a value. Several dimensions of one thing
  // (a door's width and height) share a line: the least certain one speaks.
  const sourceOf = (...dimensions: [Dimension, ...Dimension[]]): Provenance => {
    const widest = leastCertain(...dimensions);
    return {
      text: t(`room.size.source.${widest.source}`, {
        band: formatLength(widest.error_band_m, units, t),
      }),
      approx: isApprox(widest),
    };
  };
  return (
    <>
      {content.sample ? <Sample text={t("room.sample")} /> : null}
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
        {heroViews.map((view, index) => (
          <RoomStillView
            key={view.id}
            testID={`room-hero-${view.id}`}
            still={view.still}
            label={t("reveal.view", { number: index + 1, total: heroViews.length })}
            drawn={content.sample}
            // A photo the phone no longer has drops out rather than leave a blank card.
            onMissing={() => setMissing((gone) => [...gone, view.id])}
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

      {/* How far to trust the numbers below, in plain words. */}
      {content.confidence ? (
        <Card testID="room-confidence" style={{ gap: spacing.md }}>
          <Text variant="bodyStrong">{t(`room.confidence.${content.confidence}.title`)}</Text>
          <Text tone="secondary">{t(`room.confidence.${content.confidence}.body`)}</Text>
          {content.confidence === "estimated" && onMeasure ? (
            <Button
              label={t("room.confidence.measure")}
              variant="outline"
              size="small"
              onPress={onMeasure}
            />
          ) : null}
        </Card>
      ) : null}

      {measures ? (
        <>
          <Card style={{ gap: spacing.xs }}>
            <Text variant="captionStrong" tone="tertiary">
              {t("room.size.title")}
            </Text>
            <Text variant="figure" selectable>
              {t("room.size.area", { area: formatArea(measures.areaM2, units, t) })}
            </Text>
            <Measure
              title={t("room.size.ceilingTitle")}
              value={formatLength(measures.ceiling.value_m, units, t)}
              provenance={sourceOf(measures.ceiling)}
            />
          </Card>

          <Card testID="room-walls" style={{ gap: spacing.xl }}>
            <Text variant="captionStrong" tone="tertiary">
              {t("room.walls.title")}
            </Text>
            {measures.walls.map((wall) => (
              <Measure
                key={wall.id}
                title={t("room.walls.wall", { name: wallName(wall.number) })}
                value={formatLength(wall.length.value_m, units, t)}
                provenance={sourceOf(wall.length)}
              />
            ))}
          </Card>

          {measures.openings.length > 0 ? (
            <Card testID="room-openings" style={{ gap: spacing.xl }}>
              <Text variant="captionStrong" tone="tertiary">
                {t("room.openings.title")}
              </Text>
              {measures.openings.map((opening) => (
                <Measure
                  key={opening.id}
                  title={
                    opening.wallNumber === null
                      ? t(`room.openings.${opening.kind}`)
                      : t(`room.openings.${opening.kind}OnWall`, {
                          name: wallName(opening.wallNumber),
                        })
                  }
                  value={t("room.openings.size", {
                    width: formatLength(opening.width.value_m, units, t),
                    height: formatLength(opening.height.value_m, units, t),
                  })}
                  provenance={sourceOf(opening.width, opening.height)}
                />
              ))}
            </Card>
          ) : null}

          {measures.bigItems.length > 0 ? (
            <Card testID="room-items" style={{ gap: spacing.xl }}>
              <Text variant="captionStrong" tone="tertiary">
                {t("room.items.title")}
              </Text>
              {measures.bigItems.map((item) => (
                <Measure
                  key={item.id}
                  title={item.label}
                  value={t("room.items.size", {
                    width: formatLength(item.width.value_m, units, t),
                    depth: formatLength(item.depth.value_m, units, t),
                    height: formatLength(item.height.value_m, units, t),
                  })}
                  provenance={sourceOf(item.width, item.depth, item.height)}
                />
              ))}
            </Card>
          ) : null}
        </>
      ) : (
        <Card style={{ gap: spacing.xs }}>
          <Text variant="captionStrong" tone="tertiary">
            {t("room.size.title")}
          </Text>
          <Text tone="secondary">{t("room.size.none")}</Text>
        </Card>
      )}

      {/* A place for the 3D view. The app may launch without it, so it shows only with its flag. */}
      {show3d ? (
        <Card testID="room-3d-slot" style={{ gap: spacing.xs }}>
          <Text variant="captionStrong" tone="tertiary">
            {t("room.view3d.title")}
          </Text>
          <Text tone="secondary">{t("room.view3d.body")}</Text>
        </Card>
      ) : null}

      {/* The plan: the room to scale with the chosen look's furniture in place. */}
      {content.shell ? (
        <Card testID="room-plan-slot" style={{ gap: spacing.md }}>
          <Text variant="captionStrong" tone="tertiary">
            {look
              ? t("room.plan.titleFor", { look: t(`design.slot.${look.design.slot}`) })
              : t("room.plan.title")}
          </Text>
          <View style={{ alignItems: "center" }}>
            <DesignPlanView
              design={look?.design ?? null}
              shell={content.shell}
              units={units}
              width={planWidth}
              height={Math.round(planWidth * PLAN_ASPECT)}
              selectedId={selectedId}
              gaps={gaps}
              onSelect={
                look ? (id) => setPicked(id ? { slot: look.design.slot, id } : null) : undefined
              }
            />
          </View>
          {selectedItem ? (
            <View testID="room-plan-selected" style={{ gap: spacing.xxs }}>
              <Text variant="bodyStrong">{selectedItem.product.title}</Text>
              <Text variant="meta" tone="secondary" style={{ fontVariant: ["tabular-nums"] }}>
                {t("room.plan.size", {
                  width: formatLength(selectedItem.product.dimensions.width.value_m, units, t),
                  depth: formatLength(selectedItem.product.dimensions.depth.value_m, units, t),
                  height: formatLength(selectedItem.product.dimensions.height.value_m, units, t),
                })}
              </Text>
              {gaps ? null : (
                <Text variant="caption" tone="tertiary">
                  {t("room.plan.gapsMeasured")}
                </Text>
              )}
            </View>
          ) : look ? (
            <Text variant="caption" tone="tertiary">
              {t("room.plan.tapPiece")}
            </Text>
          ) : null}
          {content.shell.walls.some((wall) => wall.length.source !== "measured") ? (
            <Text variant="caption" tone="tertiary">
              {t("room.plan.softEdge")}
            </Text>
          ) : null}
          {edgeKinds(content.shell).includes("open") ? (
            <Text testID="room-plan-open" variant="caption" tone="tertiary">
              {t("room.plan.openEdge")}
            </Text>
          ) : null}
        </Card>
      ) : null}
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
  showVastu,
}: {
  content: RoomContent;
  look: RoomLook;
  picker: React.ReactNode;
  showVastu: boolean;
}) {
  const { t } = useTranslation();
  const { tokens, tier } = useTheme();
  const { colors, spacing, radius } = tokens;
  const calibrated = compassCalibrated(content);
  const [vastu, setVastu] = useState(false);
  const { design } = look;
  return (
    <>
      {content.sample ? <Sample text={t("reveal.sample")} /> : null}
      {picker}
      <View>
        <RoomStillView
          still={look.still}
          label={
            look.stillIsToday
              ? `${t(`design.slot.${design.slot}`)}. ${t("reveal.today")}`
              : t(`design.slot.${design.slot}`)
          }
          // A real room never shows a drawn stand-in.
          drawn={content.sample}
          style={{
            aspectRatio: STILL_ASPECT,
            borderRadius: radius.card,
            borderCurve: "continuous",
            boxShadow: tokens.shadows[tier].card,
          }}
        />
        {look.stillIsToday ? (
          <View
            testID="design-today"
            style={{
              position: "absolute",
              top: spacing.lg,
              left: spacing.lg,
              paddingHorizontal: spacing.md,
              paddingVertical: spacing.xs,
              borderRadius: radius.pill,
              backgroundColor: colors.surface,
            }}
          >
            <Text variant="caption">{t("reveal.today")}</Text>
          </View>
        ) : null}
      </View>
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
        {/* A photo room whose only fit was to keep the seating says so first. */}
        {design.layout_rung === "refresh" ? (
          <Text testID="design-refresh">{t("designs.refresh")}</Text>
        ) : null}
        {design.explanations.map((line) => (
          <Text key={line}>{line}</Text>
        ))}
        <Text variant="meta" tone="secondary">
          {fitClaimsAllowed(content.confidence)
            ? t(design.check_report.passed ? "designs.fits" : "designs.check")
            : t("reveal.estimated")}
        </Text>
      </Card>

      {/* The Vastu view, behind its build setting (off). */}
      {showVastu ? (
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
      ) : null}
    </>
  );
}

function ShoppingTabBody({
  content,
  look,
  picker,
  units,
}: {
  content: RoomContent;
  look: RoomLook;
  picker: React.ReactNode;
  units: LengthUnits;
}) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const { colors, spacing } = tokens;
  const shopping = shoppingFor(look.design, content.fitChecked);
  // "This fits" is only said of a room that was taped or measured by the scan.
  const fitClaims = fitClaimsAllowed(content.confidence);
  return (
    <>
      {content.sample ? <Sample text={t("shopping.sample")} /> : null}
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
            {/* The product's own photo. Sample products have none to show. */}
            <View
              style={{
                width: PHOTO,
                height: PHOTO,
                borderRadius: spacing.xl,
                borderCurve: "continuous",
                overflow: "hidden",
                backgroundColor: colors.sand,
              }}
            >
              {line.photo && !content.sample ? (
                <Image
                  testID={`shopping-photo-${line.id}`}
                  source={{ uri: line.photo }}
                  accessibilityIgnoresInvertColors
                  resizeMode="cover"
                  style={{ flex: 1 }}
                />
              ) : null}
            </View>
            <View style={{ flex: 1, gap: spacing.xxs }}>
              <Text variant="bodyStrong">{line.title}</Text>
              <Text variant="meta" tone="secondary" selectable>
                {formatInr(line.priceMinor)}
              </Text>
              <Text variant="caption" tone="tertiary">
                {!line.inStock
                  ? t("shopping.outOfStock")
                  : !fitClaims
                    ? t("shopping.fit.confirm")
                    : line.fit === "fits" && line.spareM !== null
                      ? t("shopping.fit.fitsWith", { spare: formatLength(line.spareM, units, t) })
                      : t(`shopping.fit.${line.fit}`)}
              </Text>
            </View>
            {line.url ? (
              <Button
                label={t("shopping.buy")}
                variant="tint"
                size="small"
                accessibilityLabel={t("shopping.buyItem", { item: line.title })}
                // Sample products have example links; real ones open at the retailer.
                disabled={
                  content.sample || !line.inStock || (fitClaims && line.fit === "does_not_fit")
                }
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
    </>
  );
}

/** A room whose photos, measurements and designs are not ready yet. */
export function RoomWaiting({
  job,
  onRetry,
  onAddPhoto,
}: {
  /** The room's job, when this phone is following it. */
  job?: RoomJobState;
  onRetry?: () => void;
  onAddPhoto?: () => void;
} = {}) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const { colors, spacing } = tokens;
  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.canvas }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={{ padding: spacing.gutter, gap: spacing.xl }}
    >
      <Text variant="title" accessibilityRole="header">
        {t("room.waiting.title")}
      </Text>
      <Text tone="secondary">{t("room.waiting.body")}</Text>
      {job ? <JobProgress job={job} onRetry={onRetry} onAddPhoto={onAddPhoto} /> : null}
    </ScrollView>
  );
}

export function RoomScreen({
  content,
  show3d = twinViewerEnabled(),
  redesignAreaId = null,
  onChooseArea,
  onMeasure,
  remeasuring = false,
  job,
  onRetry,
  onAddPhoto,
  showVastu = vastuEnabled(),
}: {
  /** The room needs another photo: opens the camera for this same room. */
  onAddPhoto?: () => void;
  /** The Vastu view on Designs, behind its build setting (off). */
  showVastu?: boolean;
  content: RoomContent;
  /** The room's job while its designs are being made, or why it stopped. */
  job?: RoomJobState;
  /** Try the room's job again after it stopped. */
  onRetry?: () => void;
  /**
   * A new scan is measuring the room again: what shows is still the old
   * content, based on estimated sizes, until the new designs arrive.
   */
  remeasuring?: boolean;
  /** Show the place kept for the 3D view. Off unless its flag is on. */
  show3d?: boolean;
  /** For a scan of several areas: the one chosen to redesign. */
  redesignAreaId?: string | null;
  /** Opens the choice of which area to redesign. */
  onChooseArea?: () => void;
  /** Opens "Measure this room for exact fit", for a room whose sizes are estimates. */
  onMeasure?: () => void;
}) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const { colors, spacing } = tokens;
  const units = useSettings((state) => state.units);
  const [tab, setTab] = useState<RoomTab>("room");
  // A scan of several areas: every area has its Room tab; one has designs.
  const areas = hasAreas(content) ? content.areas : [];
  const redesigned = redesignArea(content, redesignAreaId);
  const [viewedId, setViewedId] = useState(redesigned?.id ?? areas[0]?.id ?? null);
  const viewed = areas.find((area) => area.id === viewedId) ?? areas[0];
  const roomView = viewed ? contentForArea(content, viewed, viewed.id === redesigned?.id) : content;
  const designView = redesigned ? contentForArea(content, redesigned, true) : content;
  const areaName = (area: (typeof areas)[number]) =>
    t(`space.typeNames.${area.spaceType ?? "other"}`, {
      defaultValue: t("areas.unnamed", { number: areas.indexOf(area) + 1 }),
    });
  // Until an area is chosen there is nothing to design.
  const awaitingChoice = areas.length > 0 && !redesigned;
  // The chosen look is shared by Designs and Shopping list. Best match first.
  const [chosen, setChosen] = useState(Math.min(1, content.looks.length - 1));
  const offered = designsOffered(designView.spaceType);
  const look = offered && !awaitingChoice ? designView.looks[chosen] : undefined;
  const picker = <LookPicker looks={designView.looks} selected={chosen} onSelect={setChosen} />;

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
      {remeasuring ? (
        <View testID="remeasuring-note">
          <Sample text={t("room.remeasuring")} />
        </View>
      ) : null}
      <Segmented
        segments={ROOM_TABS.map((key) => ({ key, label: t(`room.tabs.${key}`) }))}
        selected={tab}
        onSelect={setTab}
      />
      {tab === "room" && areas.length > 0 ? (
        <View
          testID="room-areas"
          style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}
        >
          {areas.map((area) => (
            <Chip
              key={area.id}
              label={areaName(area)}
              selected={area.id === viewed?.id}
              haptic="swapLands"
              onPress={() => setViewedId(area.id)}
            />
          ))}
        </View>
      ) : null}
      {tab === "room" ? (
        <RoomTabBody
          content={roomView}
          units={units}
          show3d={show3d}
          // The plan shows furniture only in the area being redesigned.
          look={!viewed || viewed.id === redesigned?.id ? look : undefined}
          onMeasure={onMeasure}
        />
      ) : null}
      {tab !== "room" && awaitingChoice ? (
        <Card testID="areas-choose" style={{ gap: spacing.lg }}>
          <Text tone="secondary">{t("areas.chooseFirst", { count: areas.length })}</Text>
          {onChooseArea ? <Button label={t("areas.chooseOne")} onPress={onChooseArea} /> : null}
        </Card>
      ) : null}
      {tab !== "room" && redesigned ? (
        <View
          testID="areas-chosen"
          style={{ flexDirection: "row", alignItems: "center", gap: spacing.lg }}
        >
          <Text tone="secondary" style={{ flex: 1 }}>
            {t("areas.designsFor", { area: areaName(redesigned) })}
          </Text>
          {onChooseArea ? (
            <Button label={t("areas.change")} variant="ghost" size="small" onPress={onChooseArea} />
          ) : null}
        </View>
      ) : null}
      {tab !== "room" && !awaitingChoice && !offered ? (
        // Any space can be scanned; designs are made for living rooms and bedrooms for now.
        <Card testID="designs-coming">
          <Text tone="secondary">{t("designs.comingForSpace")}</Text>
        </Card>
      ) : null}
      {tab === "designs" && look ? (
        <DesignsTabBody content={designView} look={look} picker={picker} showVastu={showVastu} />
      ) : null}
      {tab === "shopping" && look ? (
        <ShoppingTabBody content={designView} look={look} picker={picker} units={units} />
      ) : null}
      {tab !== "room" && !awaitingChoice && offered && !look ? (
        // No designs yet: how the job is getting on, or why it stopped. Never a stand-in.
        job && job.stage !== "done" ? (
          <JobProgress job={job} onRetry={onRetry} onAddPhoto={onAddPhoto} />
        ) : (
          <Text tone="secondary">{t("rooms.designs.none")}</Text>
        )
      ) : null}
    </ScrollView>
  );
}
