import { Card, Text } from "@sajao/ui";
import { useTranslation } from "react-i18next";
import { Screen } from "@/components/screen";

export function VastuScreen() {
  const { t } = useTranslation();
  return (
    <Screen title={t("vastu.title")}>
      <Card>
        <Text tone="secondary">{t("vastu.body")}</Text>
      </Card>
      {/* Every Vastu screen carries this label. */}
      <Text variant="caption" tone="tertiary">
        {t("vastu.label")}
      </Text>
    </Screen>
  );
}
