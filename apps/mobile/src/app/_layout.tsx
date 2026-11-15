import { Geist_400Regular } from "@expo-google-fonts/geist/400Regular";
import { Geist_500Medium } from "@expo-google-fonts/geist/500Medium";
import { Geist_600SemiBold } from "@expo-google-fonts/geist/600SemiBold";
import { ThemeProvider } from "@sajao/ui";
import { type FontSource, useFonts } from "expo-font";
import { Stack } from "expo-router/stack";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { Platform } from "react-native";
import i18n, { resolveLanguage } from "@/i18n";
import { useSettings } from "@/state/settings";

// iOS uses the system font. Android bundles Geist, one file per weight,
// under the family names the theme tokens expect.
const fonts: Record<string, FontSource> =
  Platform.OS === "android"
    ? {
        "Geist-Regular": Geist_400Regular,
        "Geist-Medium": Geist_500Medium,
        "Geist-SemiBold": Geist_600SemiBold,
      }
    : {};

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts(fonts);
  const language = useSettings((state) => state.language);

  useEffect(() => {
    void i18n.changeLanguage(resolveLanguage(language));
  }, [language]);

  // A font failure falls back to the system font rather than a blank app.
  if (!fontsLoaded && !fontError) return null;

  return (
    <ThemeProvider>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Protected guard={__DEV__}>
          <Stack.Screen name="gallery" options={{ headerShown: true, title: "Gallery" }} />
        </Stack.Protected>
      </Stack>
    </ThemeProvider>
  );
}
