import { Geist_400Regular } from "@expo-google-fonts/geist/400Regular";
import { Geist_500Medium } from "@expo-google-fonts/geist/500Medium";
import { Geist_600SemiBold } from "@expo-google-fonts/geist/600SemiBold";
import { InstrumentSerif_400Regular } from "@expo-google-fonts/instrument-serif/400Regular";
import { InstrumentSerif_400Regular_Italic } from "@expo-google-fonts/instrument-serif/400Regular_Italic";
import { fontFamilies, ThemeProvider } from "@sajao/ui";
import { type FontSource, useFonts } from "expo-font";
import { Stack } from "expo-router/stack";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { Platform } from "react-native";
import i18n, { resolveLanguage } from "@/i18n";
import { useSettings } from "@/state/settings";

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
