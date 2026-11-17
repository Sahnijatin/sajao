import { Button, Text } from "@sajao/ui";
import { useRouter } from "expo-router";
import { useTranslation } from "react-i18next";
import { Screen } from "@/components/screen";
import { UploadStatus } from "@/components/upload-status";

export function HomeScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  return (
    <Screen title="Sajao">
      <Text variant="display">{t("home.headline")}</Text>
      <Text tone="secondary">{t("home.intro")}</Text>
      <Button label={t("home.start")} onPress={() => router.push("/capture")} />
      <UploadStatus />
      <Text variant="caption" tone="tertiary">
        {t("home.worksWith")}
      </Text>
    </Screen>
  );
}
