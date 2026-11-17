// Shown instead of the scan on a phone that cannot measure a room: no
// ARCore or ARKit, or an AR session that will not start. A scan there could
// never become measurements, so the person is told plainly and kindly, and
// sent to photos, where the redesign and the shopping list still work. Never
// an error screen.
import { Button, motion, playHaptic, resolveDuration, Text, useTheme } from "@sajao/ui";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";
import Animated, { Easing, FadeIn } from "react-native-reanimated";

export interface NoArNoticeProps {
  onUsePhotos: () => void;
  onClose: () => void;
}

export function NoArNotice({ onUsePhotos, onClose }: NoArNoticeProps) {
  const { t } = useTranslation();
  const { tokens, tier, reducedMotion } = useTheme();
  const { spacing } = tokens;

  // One gentle tick as the notice appears: something changed, nothing broke.
  useEffect(() => {
    void playHaptic("levelReached");
  }, []);

  const duration = resolveDuration(motion.ease.durationMs, { reducedMotion, tier });
  return (
    <View
      testID="no-ar-notice"
      style={{
        flex: 1,
        justifyContent: "center",
        padding: spacing.gutter,
        backgroundColor: tokens.colors.canvas,
      }}
    >
      <Animated.View
        entering={FadeIn.duration(duration).easing(Easing.bezier(...motion.ease.bezier))}
        style={{ gap: spacing.gutter }}
      >
        <Text variant="title" accessibilityRole="header">
          {t("capture.noAr.title")}
        </Text>
        <Text tone="secondary">{t("capture.noAr.body")}</Text>
        <Button label={t("capture.usePhotos")} onPress={onUsePhotos} />
        <Button label={t("capture.close")} variant="ghost" size="small" onPress={onClose} />
      </Animated.View>
    </View>
  );
}
