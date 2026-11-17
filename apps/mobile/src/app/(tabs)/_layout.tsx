import { useTheme } from "@sajao/ui";
import { NativeTabs } from "expo-router/unstable-native-tabs";
import { useTranslation } from "react-i18next";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

// The platform's own tab bar: Material 3 on Android, the system bar on iOS.
// The Android icons (`md`) are drawn by the expo-symbols package, which must
// be installed: without it this layout throws on Android.
// Tabs are peers, so switching between them never slides.
export default function TabsLayout() {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  return (
    // The tab you are on takes the theme accent, icon and label alike.
    <NativeTabs tintColor={tokens.colors.accent}>
      <NativeTabs.Trigger name="index">
        <NativeTabs.Trigger.Icon sf="house.fill" md="home" />
        <NativeTabs.Trigger.Label>{t("tabs.home")}</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="profile">
        <NativeTabs.Trigger.Icon sf="person.fill" md="person" />
        <NativeTabs.Trigger.Label>{t("tabs.profile")}</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
