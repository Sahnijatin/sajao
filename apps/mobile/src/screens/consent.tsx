// Consent at first use: what happens to your photos, in plain words, with
// the privacy policy and terms one tap away. Shown once, before anything
// else; asked again only when the wording changes.
import { Button, Card, motion, Text, useTheme } from "@sajao/ui";
import { useTranslation } from "react-i18next";
import { Linking, ScrollView, View } from "react-native";
import Animated, { Easing, FadeIn } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

const POINTS = ["photos", "people", "delete"] as const;

export function ConsentScreen({
  legal,
  onAccept,
}: {
  /** Where the privacy policy and terms are hosted; null while they are not. */
  legal: { privacyUrl: string; termsUrl: string } | null;
  onAccept: () => void;
}) {
  const { t } = useTranslation();
  const { tokens, duration } = useTheme();
  const { spacing } = tokens;
  const insets = useSafeAreaInsets();
  const fade = duration(motion.ease.durationMs);
  const entering =
    fade > 0 ? FadeIn.duration(fade).easing(Easing.bezier(...motion.ease.bezier)) : undefined;
  return (
    <ScrollView
      testID="consent"
      style={{ backgroundColor: tokens.colors.canvas }}
      contentContainerStyle={{
        flexGrow: 1,
        paddingTop: insets.top + spacing.sheetBottom,
        paddingBottom: insets.bottom + spacing.sheetBottom,
        paddingHorizontal: spacing.gutter,
        gap: spacing.sheetBottom,
      }}
    >
      <Animated.View entering={entering} style={{ gap: spacing.gutter }}>
        <Text variant="title" accessibilityRole="header">
          {t("consent.title")}
        </Text>
        <Card style={{ gap: spacing.xl }}>
          {POINTS.map((point) => (
            <Text key={point} tone="secondary">
              {t(`consent.points.${point}`)}
            </Text>
          ))}
        </Card>
        {legal ? (
          <View style={{ gap: spacing.md }}>
            <Text variant="caption" tone="tertiary">
              {t("consent.agree")}
            </Text>
            <View style={{ flexDirection: "row", gap: spacing.md }}>
              <Button
                label={t("consent.privacy")}
                variant="ghost"
                size="small"
                onPress={() => void Linking.openURL(legal.privacyUrl)}
              />
              <Button
                label={t("consent.terms")}
                variant="ghost"
                size="small"
                onPress={() => void Linking.openURL(legal.termsUrl)}
              />
            </View>
          </View>
        ) : null}
      </Animated.View>
      <View style={{ flex: 1 }} />
      <Button label={t("consent.continue")} onPress={onAccept} />
    </ScrollView>
  );
}
