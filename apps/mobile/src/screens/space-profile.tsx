import type { SpaceProfile } from "@sajao/schemas";
import { Button, Card, Chip, playHaptic, Sheet, Text, TextField, useTheme } from "@sajao/ui";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, ScrollView, useWindowDimensions, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { PlanView } from "@/space/plan-view";
import {
  applyTapeToCeiling,
  applyTapeToWall,
  cycleItemAction,
  describeSpace,
  planDrawing,
  setSpaceType,
  SPACE_TYPES,
} from "@/space/space-profile";
import { useSettings } from "@/state/settings";
import { formatArea, formatLength } from "@/utils/format-length";

export interface SpaceProfileScreenProps {
  profile: SpaceProfile;
  onChange: (profile: SpaceProfile) => void;
  onShowIdeas: () => void;
}

const PLAN_HEIGHT = 300;

function Badge({ label, tone }: { label: string; tone: "warning" | "success" }) {
  const { tokens } = useTheme();
  const color = tone === "warning" ? tokens.colors.warning : tokens.colors.success;
  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: tokens.spacing.sm,
        height: 26,
        paddingHorizontal: tokens.spacing.lg,
        borderRadius: tokens.radius.pill,
        backgroundColor: tone === "warning" ? "rgba(255, 138, 0, 0.12)" : "rgba(31, 174, 85, 0.12)",
      }}
    >
      <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: color }} />
      <Text variant="captionStrong">{label}</Text>
    </View>
  );
}

/**
 * The Space Profile card: what the scan found, with every number labelled
 * estimated or verified. The user confirms and corrects; nothing is drawn
 * from scratch.
 */
export function SpaceProfileScreen({ profile, onChange, onShowIdeas }: SpaceProfileScreenProps) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const { spacing } = tokens;
  const insets = useSafeAreaInsets();
  const window = useWindowDimensions();
  const units = useSettings((state) => state.units);
  const [changing, setChanging] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [target, setTarget] = useState<string>("ceiling");
  const [entered, setEntered] = useState("");

  const found = describeSpace(profile);
  const drawing = useMemo(
    () => planDrawing(profile, { width: window.width, height: PLAN_HEIGHT, padding: 28 }),
    [profile, window.width],
  );
  const typeLabel = t(`space.types.${found.spaceType}`);
  const summary = [
    t("space.about", { area: formatArea(found.areaM2, units, t) }),
    t("space.windows", { count: found.windows }),
    t("space.doors", { count: found.doors }),
    found.light ? t(`space.light.${found.light}`) : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const measured = Number(entered.replace(",", "."));
  const applyTape = () => {
    if (!(measured > 0)) return;
    onChange(
      target === "ceiling"
        ? applyTapeToCeiling(profile, measured)
        : applyTapeToWall(profile, target, measured),
    );
    // The value snaps in: one tick, in the same moment the numbers change.
    void playHaptic("cornerCaptured");
    setEntered("");
    setVerifying(false);
  };

  return (
    <View style={{ flex: 1, backgroundColor: tokens.colors.canvas }}>
      <ScrollView
        contentContainerStyle={{
          paddingTop: insets.top,
          paddingBottom: insets.bottom + spacing.sheetBottom,
          gap: spacing.gutter,
        }}
      >
        <PlanView drawing={drawing} width={window.width} height={PLAN_HEIGHT} />

        <View style={{ paddingHorizontal: spacing.gutter, gap: spacing.gutter }}>
          <View style={{ gap: spacing.sm }}>
            <View
              style={{
                flexDirection: "row",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <Text variant="captionStrong" tone="secondary">
                {t("space.found").toUpperCase()}
              </Text>
              {found.badge.kind === "verified" ? (
                <Badge tone="success" label={t("space.verified")} />
              ) : (
                <Badge
                  tone="warning"
                  label={t("space.estimated", {
                    band: formatLength(found.badge.errorBandM, units, t),
                  })}
                />
              )}
            </View>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.lg }}>
              <Text variant="title" accessibilityRole="header" style={{ flexShrink: 1 }}>
                {found.extent === "part" ? t("space.partOf", { space: typeLabel }) : typeLabel}
              </Text>
              <Button
                label={t("space.change")}
                variant="tint"
                size="small"
                onPress={() => setChanging(true)}
              />
            </View>
            <Text variant="bodySmall" tone="secondary">
              {summary}
            </Text>
          </View>

          {profile.existing_items.length > 0 ? (
            <View style={{ gap: spacing.md }}>
              <Text variant="label">{t("space.itemsTitle")}</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                <View style={{ flexDirection: "row", gap: spacing.lg }}>
                  {profile.existing_items.map((item) => (
                    <Pressable
                      key={item.id}
                      accessibilityRole="button"
                      accessibilityLabel={`${item.label}: ${t(`space.actions.${item.action}`)}`}
                      onPress={() => onChange(cycleItemAction(profile, item.id))}
                    >
                      <Card style={{ width: 120, gap: spacing.md, padding: spacing.lg }}>
                        <Text variant="meta">{item.label}</Text>
                        <Text
                          variant="captionStrong"
                          tone={item.action === "replace" ? "accent" : "secondary"}
                        >
                          {t(`space.actions.${item.action}`)}
                        </Text>
                      </Card>
                    </Pressable>
                  ))}
                </View>
              </ScrollView>
            </View>
          ) : null}

          <View style={{ flexDirection: "row", gap: spacing.lg }}>
            <Button
              label={t("space.verify")}
              variant="outline"
              onPress={() => setVerifying(true)}
            />
            <Button label={t("space.showIdeas")} style={{ flex: 1 }} onPress={onShowIdeas} />
          </View>
        </View>
      </ScrollView>

      <Sheet isPresented={changing} onDismiss={() => setChanging(false)}>
        <View style={{ gap: spacing.xxl }}>
          <Text variant="heading">{t("space.changeTitle")}</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
            {SPACE_TYPES.map((type) => (
              <Chip
                key={type}
                label={t(`space.typeNames.${type}`)}
                selected={profile.space_type === type}
                onPress={() => {
                  onChange(setSpaceType(profile, type));
                  setChanging(false);
                }}
              />
            ))}
          </View>
        </View>
      </Sheet>

      <Sheet isPresented={verifying} onDismiss={() => setVerifying(false)}>
        <View style={{ gap: spacing.xxl }}>
          <Text variant="heading">{t("space.verifyTitle")}</Text>
          <Text variant="bodySmall" tone="secondary">
            {t("space.verifyBody")}
          </Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
            {profile.walls.map((wall, index) => (
              <Chip
                key={wall.id}
                label={t("space.wall", { number: index + 1 })}
                selected={target === wall.id}
                onPress={() => setTarget(wall.id)}
              />
            ))}
            <Chip
              label={t("space.ceiling")}
              selected={target === "ceiling"}
              onPress={() => setTarget("ceiling")}
            />
          </View>
          <TextField
            label={t("space.valueLabel")}
            keyboardType="decimal-pad"
            value={entered}
            onChangeText={setEntered}
          />
          <Button label={t("space.apply")} disabled={!(measured > 0)} onPress={applyTape} />
        </View>
      </Sheet>
    </View>
  );
}
