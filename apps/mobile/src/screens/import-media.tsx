// "Use photos or a video": make a room from what is already on the phone.
// The screen says plainly what this gives (a redesign and a shopping list)
// and what it cannot (measurements you can rely on without checking), then
// opens the phone's own picker.
import { Button, Card, playHaptic, Text, useTheme } from "@sajao/ui";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Image, ScrollView, View } from "react-native";
import { mediaImporter, type PickedMedia, pickMedia, type PickResult } from "@/rooms/media-import";

/** The side of a chosen photo's thumbnail. */
const THUMB = 72;

export function ImportMediaScreen({
  onImported,
  onScan,
  pick = pickMedia,
}: {
  /** The media has been handed over and a room made for it. */
  onImported: (roomId: string) => void;
  /** "Scan instead". */
  onScan: () => void;
  pick?: () => Promise<PickResult>;
}) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const { colors, spacing } = tokens;
  const [media, setMedia] = useState<PickedMedia[]>([]);
  const [problem, setProblem] = useState<"denied" | "unavailable" | "failed" | null>(null);
  const [busy, setBusy] = useState(false);
  const importer = mediaImporter();

  const choose = async () => {
    setBusy(true);
    const result = await pick();
    setBusy(false);
    if (result.status === "picked") {
      void playHaptic("cornerCaptured");
      setMedia(result.media);
      setProblem(null);
    } else if (result.status !== "cancelled") {
      setProblem(result.status);
    }
  };
  const send = async () => {
    if (!importer) return;
    setBusy(true);
    try {
      const { roomId } = await importer(media);
      void playHaptic("roomVerified");
      onImported(roomId);
    } catch {
      setProblem("failed");
      setBusy(false);
    }
  };
  const photos = media.filter((each) => each.kind === "photo").length;
  const videos = media.length - photos;

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
          {t("import.title")}
        </Text>
        <Text tone="secondary">{t("import.body")}</Text>
      </View>
      <Card style={{ gap: spacing.md }}>
        <Text variant="captionStrong" tone="tertiary">
          {t("import.tipsTitle")}
        </Text>
        <Text>{t("import.tipWalls")}</Text>
        <Text>{t("import.tipLight")}</Text>
        {/* Honest about the level: sizes from photos are estimates until measured. */}
        <Text tone="secondary">{t("import.estimated")}</Text>
      </Card>

      {media.length > 0 ? (
        <Card testID="import-chosen" style={{ gap: spacing.lg }}>
          <Text variant="bodyStrong">{t("import.chosen", { photos, videos })}</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <View style={{ flexDirection: "row", gap: spacing.md }}>
              {media.map((each) => (
                <Image
                  key={each.uri}
                  source={{ uri: each.uri }}
                  accessibilityIgnoresInvertColors
                  style={{
                    width: THUMB,
                    height: THUMB,
                    borderRadius: spacing.lg,
                    backgroundColor: colors.sand,
                  }}
                />
              ))}
            </View>
          </ScrollView>
          {importer ? null : <Text tone="secondary">{t("import.notYet")}</Text>}
        </Card>
      ) : null}

      {problem ? (
        <Text testID="import-problem" tone="secondary" accessibilityRole="alert">
          {t(`import.problem.${problem}`)}
        </Text>
      ) : null}

      <View style={{ gap: spacing.lg }}>
        {media.length > 0 && importer ? (
          <Button label={t("import.use")} disabled={busy} onPress={() => void send()} />
        ) : null}
        <Button
          label={media.length > 0 ? t("import.chooseAgain") : t("import.choose")}
          variant={media.length > 0 ? "outline" : "primary"}
          disabled={busy}
          onPress={() => void choose()}
        />
        <Button label={t("import.scanInstead")} variant="ghost" size="small" onPress={onScan} />
      </View>
    </ScrollView>
  );
}
