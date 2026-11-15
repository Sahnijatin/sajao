import { Text } from "@sajao/ui";
import { useTranslation } from "react-i18next";
import { Screen } from "@/components/screen";

export function HomeScreen() {
  const { t } = useTranslation();
  return (
    <Screen title="Sajao">
      <Text variant="heading">{t("home.tagline")}</Text>
      <Text tone="secondary">{t("home.intro")}</Text>
    </Screen>
  );
}
