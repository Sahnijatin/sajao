import { Card, Text } from "@sajao/ui";
import { useTranslation } from "react-i18next";
import { Screen } from "@/components/screen";

export function RoomsScreen() {
  const { t } = useTranslation();
  return (
    <Screen title={t("rooms.title")}>
      <Card>
        <Text variant="label">{t("rooms.emptyTitle")}</Text>
        <Text tone="secondary">{t("rooms.emptyBody")}</Text>
      </Card>
    </Screen>
  );
}
