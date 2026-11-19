import { Button, Card, Chip, Sheet, Text, useTheme } from "@sajao/ui";
import { useRouter } from "expo-router";
import { type ReactNode, useState } from "react";
import type { DeleteResult } from "@/account/delete-account";
import { useTranslation } from "react-i18next";
import { View } from "react-native";
import { Screen } from "@/components/screen";
import { LANGUAGES, resolveLanguage } from "@/i18n";
import { previewScreensEnabled } from "@/preview-screens";
import { useSettings } from "@/state/settings";
import { useTaste } from "@/state/taste";
import { formatInr } from "@/utils/format-inr";
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

export function ProfileScreen({
  onDeleteAccount,
}: {
  /** Erases the account and everything kept for it; resolves with how it went. */
  onDeleteAccount: () => Promise<DeleteResult>;
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const { tokens } = useTheme();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [unreachable, setUnreachable] = useState(false);
  const confirmDelete = async () => {
    setDeleting(true);
    setUnreachable(false);
    const result = await onDeleteAccount();
    setDeleting(false);
    if (result === "deleted") {
      setConfirming(false);
      router.replace("/");
    } else {
      setUnreachable(true);
    }
  };
  const { language, units, setLanguage, setUnits } = useSettings();
  const activeLanguage = resolveLanguage(language);
  const taste = useTaste((state) => state.answers);

  return (
    <Screen title={t("profile.title")}>
      <Card>
        <Text variant="label">{t("profile.guestTitle")}</Text>
        <Text tone="secondary">{t("profile.guestBody")}</Text>
      </Card>

      {/* Taste and budget are asked once, before the first room's designs, and changed here. */}
      <Card style={{ gap: tokens.spacing.xl }}>
        <Text variant="label">{t("profile.tasteTitle")}</Text>
        {taste ? (
          <>
            <Text tone="secondary">
              {taste.traits.map((trait) => t(`taste.traits.${trait}`)).join(" · ")}
            </Text>
            <Text tone="secondary" selectable>
              {t("profile.tasteBudget", { amount: formatInr(taste.budget.limit.amount_minor) })}
            </Text>
          </>
        ) : (
          <Text tone="secondary">{t("profile.tasteNone")}</Text>
        )}
        <Button
          label={t(taste ? "profile.tasteChange" : "profile.tasteStart")}
          variant="outline"
          onPress={() => router.push("/taste")}
        />
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

      <Card style={{ gap: tokens.spacing.xl }}>
        <Text variant="label">{t("profile.account.title")}</Text>
        <Text tone="secondary">{t("profile.account.body")}</Text>
        <Button
          testID="delete-account"
          label={t("profile.account.delete")}
          variant="outline"
          onPress={() => setConfirming(true)}
        />
      </Card>

      <Sheet isPresented={confirming} onDismiss={() => !deleting && setConfirming(false)}>
        <View testID="delete-account-sheet" style={{ gap: tokens.spacing.xl }}>
          <Text variant="heading" accessibilityRole="header">
            {t("profile.account.confirmTitle")}
          </Text>
          <Text tone="secondary">{t("profile.account.confirmBody")}</Text>
          {unreachable ? (
            <Text testID="delete-account-unreachable" tone="secondary">
              {t("profile.account.unreachable")}
            </Text>
          ) : null}
          <Button
            label={t(deleting ? "profile.account.deleting" : "profile.account.confirm")}
            variant="ink"
            disabled={deleting}
            onPress={() => void confirmDelete()}
          />
          <Button
            label={t("profile.account.keep")}
            variant="ghost"
            disabled={deleting}
            onPress={() => setConfirming(false)}
          />
        </View>
      </Sheet>

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
