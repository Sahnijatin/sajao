// "Use photos or a video": make a room from what is already on the phone.
// The screen says plainly what this gives (a redesign and a shopping list)
// and what it cannot (sizes you can rely on without measuring), then opens
// the phone's own picker. What is chosen uploads like a scan.
import { Button, Card, playHaptic, Text, useTheme } from "@sajao/ui";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ScrollView, View } from "react-native";
import { importFromGallery, type ImportResult } from "@/rooms/media-import";

export function ImportMediaScreen({
  onImported,
  onScan,
  importMedia = importFromGallery,
}: {
  /** The pictures are a room on My home and their upload has started. */
  onImported: (roomId: string) => void;
  /** "Scan the room instead". */
  onScan: () => void;
  importMedia?: () => Promise<ImportResult>;
}) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const { colors, spacing } = tokens;
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const choose = async () => {
    setBusy(true);
    const result = await importMedia();
    setBusy(false);
    if (result.status === "imported") {
      void playHaptic("roomVerified");
      onImported(result.roomId);
    } else if (result.status === "problem") {
      setProblem(result.problem);
    }
  };

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
        <Text>{t("import.tipCount")}</Text>
        {/* Honest about the level: sizes from pictures are estimates until measured. */}
        <Text tone="secondary">{t("import.estimated")}</Text>
      </Card>

      {problem ? (
        <Text testID="import-problem" tone="secondary" accessibilityRole="alert">
          {t(`import.problems.${problem}`)}
        </Text>
      ) : null}

      <View style={{ gap: spacing.lg }}>
        <Button label={t("import.choose")} disabled={busy} onPress={() => void choose()} />
        <Button label={t("import.scanInstead")} variant="ghost" size="small" onPress={onScan} />
      </View>
    </ScrollView>
  );
}
