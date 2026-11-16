// The screen shown when something breaks at startup or while rendering.
// It uses nothing but plain views and text, because the theme, the fonts or
// the string catalogs may be the very thing that failed.
import { Pressable, Text, View } from "react-native";
import i18n from "@/i18n";
import { previewScreensEnabled } from "@/preview-screens";
import type { CaughtError } from "@/startup/crash-guard";

const FALLBACK = {
  title: "Something went wrong",
  body: "Sajao hit a problem and could not show this screen. Nothing you saved is lost.",
  retry: "Try again",
};

function text(key: keyof typeof FALLBACK): string {
  try {
    const value = i18n.t(`error.${key}`);
    return typeof value === "string" && value && value !== `error.${key}` ? value : FALLBACK[key];
  } catch {
    return FALLBACK[key];
  }
}

export function ErrorScreen({ error, onRetry }: { error: CaughtError; onRetry?: () => void }) {
  return (
    <View
      accessibilityRole="alert"
      style={{
        flex: 1,
        justifyContent: "center",
        gap: 16,
        padding: 24,
        backgroundColor: "#eef0f5",
      }}
    >
      <Text style={{ fontSize: 26, lineHeight: 30, color: "#1d1d1f" }}>{text("title")}</Text>
      <Text style={{ fontSize: 16, lineHeight: 23, color: "#55595f" }}>{text("body")}</Text>
      {/* Testers see the cause; store users never see technical text. */}
      {previewScreensEnabled() ? (
        <Text selectable style={{ fontSize: 12, lineHeight: 16, color: "#636873" }}>
          {`${error.source}: ${error.message}`}
        </Text>
      ) : null}
      {onRetry ? (
        <Pressable
          accessibilityRole="button"
          onPress={onRetry}
          style={{
            height: 56,
            borderRadius: 999,
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: "#0a7cff",
          }}
        >
          <Text style={{ fontSize: 16, fontWeight: "600", color: "#ffffff" }}>{text("retry")}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}
