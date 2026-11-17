import { Button, Card, Chip, Text, useTheme } from "@sajao/ui";
import { useRouter } from "expo-router";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";
import { Screen } from "@/components/screen";
import { LANGUAGES, resolveLanguage } from "@/i18n";
import { previewScreensEnabled } from "@/preview-screens";
import { useSettings } from "@/state/settings";
import { formatLength } from "@/utils/format-length";

function Setting({ title, children }: { title: string; children: ReactNode }) {
  const { tokens } = useTheme();
  return (
    <Card style={{ gap: tokens.spacing.xl }}>
      <Text variant="label">{title}</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: tokens.spacing.md }}>
        {children}
      </View>
    </Card>
  );
}

export function ProfileScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const { language, units, setLanguage, setUnits } = useSettings();
  const activeLanguage = resolveLanguage(language);

  return (
    <Screen title={t("profile.title")}>
      <Card>
        <Text variant="label">{t("profile.guestTitle")}</Text>
        <Text tone="secondary">{t("profile.guestBody")}</Text>
      </Card>

      <Setting title={t("profile.language")}>
        {LANGUAGES.map((code) => (
          <Chip
            key={code}
            label={t(`languages.${code}`)}
            selected={activeLanguage === code}
            onPress={() => setLanguage(code)}
          />
        ))}
      </Setting>

      <Setting title={t("profile.units")}>
        <Chip
          label={t("profile.unitsFtIn")}
          selected={units === "ft_in"}
          onPress={() => setUnits("ft_in")}
        />
        <Chip
          label={t("profile.unitsCm")}
          selected={units === "cm"}
          onPress={() => setUnits("cm")}
        />
        <Text variant="caption" tone="tertiary">
          {t("profile.unitsExample", { length: formatLength(3.4, units, t) })}
        </Text>
      </Setting>

      {previewScreensEnabled() ? (
        <>
          <Button
            label={t("profile.gallery")}
            variant="outline"
            onPress={() => router.push("/gallery")}
          />
          <Button
            label={t("profile.spacePreview")}
            variant="outline"
            onPress={() => router.push("/space-preview")}
          />
          <Button
            label={t("profile.tastePreview")}
            variant="outline"
            onPress={() => router.push("/taste-preview")}
          />
        </>
      ) : null}
    </Screen>
  );
}
