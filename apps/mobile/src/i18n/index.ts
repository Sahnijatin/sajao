// Every user-facing string lives in the catalogs under ./locales, in
// English and Hindi. Screens read them with useTranslation().
import { getLocales } from "expo-localization";
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import hi from "./locales/hi.json";

export const LANGUAGES = ["en", "hi"] as const;
export type Language = (typeof LANGUAGES)[number];

/** The stored choice wins; otherwise Hindi devices get Hindi, everything else English. */
export function resolveLanguage(
  stored: Language | null,
  deviceLanguageCode: string | null | undefined = getLocales()[0]?.languageCode,
): Language {
  if (stored) return stored;
  return deviceLanguageCode === "hi" ? "hi" : "en";
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, hi: { translation: hi } },
  lng: resolveLanguage(null),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export default i18n;
