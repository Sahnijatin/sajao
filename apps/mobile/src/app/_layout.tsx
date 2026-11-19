import { Geist_400Regular } from "@expo-google-fonts/geist/400Regular";
import { Geist_500Medium } from "@expo-google-fonts/geist/500Medium";
import { Geist_600SemiBold } from "@expo-google-fonts/geist/600SemiBold";
import { InstrumentSerif_400Regular } from "@expo-google-fonts/instrument-serif/400Regular";
import { InstrumentSerif_400Regular_Italic } from "@expo-google-fonts/instrument-serif/400Regular_Italic";
import { colors, fontFamilies, ThemeProvider } from "@sajao/ui";
import { type FontSource, useFonts } from "expo-font";
import { Stack } from "expo-router/stack";
import { StatusBar } from "expo-status-bar";
import { useEffect, useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { AppState, Platform } from "react-native";
import { ErrorScreen } from "@/components/error-screen";
import { configResult } from "@/config";
import i18n, { resolveLanguage } from "@/i18n";
import { previewScreensEnabled } from "@/preview-screens";
import {
  clearFatalError,
  describeError,
  getFatalError,
  installGlobalErrorHandler,
  subscribeToFatalError,
} from "@/startup/crash-guard";
import { useSettings } from "@/state/settings";

// Render errors in any screen show the error screen instead of closing the app.
export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

installGlobalErrorHandler();

// Headlines use Instrument Serif on both platforms. Body text is the system
// font on iOS; Android bundles Geist, one file per weight. The family names
// are the ones the theme tokens expect.
const fonts: Record<string, FontSource> = {
  [fontFamilies.serif]: InstrumentSerif_400Regular,
  [fontFamilies.serifItalic]: InstrumentSerif_400Regular_Italic,
  ...(Platform.OS === "android"
    ? {
        [fontFamilies.regular]: Geist_400Regular,
        [fontFamilies.medium]: Geist_500Medium,
        [fontFamilies.semibold]: Geist_600SemiBold,
      }
    : {}),
};

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts(fonts);
  const { t } = useTranslation();
  const language = useSettings((state) => state.language);

  useEffect(() => {
    void i18n.changeLanguage(resolveLanguage(language));
  }, [language]);

  // A scan whose upload did not finish carries on by itself: when the app
  // opens and each time it comes back to the front. No tap needed.
  useEffect(() => {
    const resume = () =>
      void import("@/capture/package/start-upload")
        .then((uploads) => uploads.resumePendingUpload())
        .catch(() => undefined);
    resume();
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") resume();
    });
    return () => subscription.remove();
  }, []);

  const fatal = useSyncExternalStore(subscribeToFatalError, getFatalError, getFatalError);
  if (fatal) return <ErrorScreen error={fatal} onRetry={clearFatalError} />;
  // A bad configuration value is shown, never thrown.
  if (!configResult.ok) return <ErrorScreen error={describeError(configResult.error, "config")} />;

  // A font failure falls back to the system font rather than a blank app.
  if (!fontsLoaded && !fontError) return null;

  return (
    <ThemeProvider>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false }}>
        {/* Every route has a title: it is also the back button label on the next screen. */}
        <Stack.Screen name="(tabs)" options={{ title: t("nav.app") }} />
        {/* Add a room: one to three photos, the main way in. */}
        <Stack.Screen
          name="photos"
          options={{ title: t("nav.photos"), presentation: "fullScreenModal" }}
        />
        <Stack.Screen
          name="capture"
          options={{ title: t("nav.capture"), presentation: "fullScreenModal" }}
        />
        {/* After a scan: what we found, taste the first time, the stages, then the reveal. */}
        <Stack.Screen
          name="space"
          options={{ title: t("nav.space"), presentation: "fullScreenModal", animation: "fade" }}
        />
        <Stack.Screen
          name="consent"
          options={{ title: t("nav.consent"), gestureEnabled: false, animation: "fade" }}
        />
        <Stack.Screen
          name="budget"
          options={{ title: t("nav.budget"), presentation: "fullScreenModal", animation: "fade" }}
        />
        <Stack.Screen
          name="taste"
          options={{ title: t("nav.taste"), presentation: "fullScreenModal", animation: "fade" }}
        />
        <Stack.Screen
          name="generating"
          options={{
            title: t("nav.generating"),
            presentation: "fullScreenModal",
            animation: "fade",
            gestureEnabled: false,
          }}
        />
        <Stack.Screen
          name="reveal"
          options={{
            title: t("nav.reveal"),
            presentation: "fullScreenModal",
            animation: "fade",
            gestureEnabled: false,
          }}
        />
        {/* A scan of several areas: which one to redesign. */}
        <Stack.Screen
          name="areas"
          options={{
            headerShown: true,
            headerShadowVisible: false,
            headerBackButtonDisplayMode: "minimal",
            headerStyle: { backgroundColor: colors.canvas },
            headerTintColor: colors.ink,
            title: t("nav.areas"),
            animation: "fade",
          }}
        />
        {/* Add a room from photos or a video already on the phone. */}
        <Stack.Screen
          name="import"
          options={{
            headerShown: true,
            headerShadowVisible: false,
            headerBackButtonDisplayMode: "minimal",
            headerStyle: { backgroundColor: colors.canvas },
            headerTintColor: colors.ink,
            title: t("nav.import"),
          }}
        />
        {/* One room: a pushed screen with the platform's own header and back. */}
        <Stack.Screen
          name="room/[id]"
          options={{
            headerShown: true,
            headerShadowVisible: false,
            headerBackButtonDisplayMode: "minimal",
            headerStyle: { backgroundColor: colors.canvas },
            headerTintColor: colors.ink,
            title: t("nav.room"),
          }}
        />
        <Stack.Protected guard={previewScreensEnabled()}>
          <Stack.Screen name="gallery" options={{ headerShown: true, title: t("nav.gallery") }} />
          <Stack.Screen name="space-preview" options={{ title: t("nav.spacePreview") }} />
          <Stack.Screen name="taste-preview" options={{ title: t("nav.tastePreview") }} />
        </Stack.Protected>
      </Stack>
    </ThemeProvider>
  );
}
