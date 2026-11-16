// Per-variant app identity on top of app.json. Each variant has its own
// name and application id, so a development build installs beside a preview
// or store build instead of replacing it.
import type { ConfigContext, ExpoConfig } from "expo/config";

type Variant = "development" | "preview" | "production";

// Android processor types to compile for. Compiling the native libraries is
// the slowest part of a build, so development and preview builds target
// 64-bit ARM only, which is what current phones use. The store build also
// covers 32-bit ARM phones. Emulator types (x86) are never built.
const VARIANTS: Record<
  Variant,
  { name: string; id: string; iosId?: string; androidArchs: string[] }
> = {
  development: { name: "Sajao (Dev)", id: "app.sajao.dev", androidArchs: ["arm64-v8a"] },
  preview: {
    name: "Sajao (Preview)",
    id: "app.sajao.preview",
    // Temporary: Apple has a signing profile only for the development id so
    // far. Until one exists for app.sajao.preview, the iOS preview build uses
    // the development id and so replaces the development build on a phone.
    iosId: "app.sajao.dev",
    androidArchs: ["arm64-v8a"],
  },
  // Confirmed by the founder. A store listing can never change its application id.
  production: { name: "Sajao", id: "app.sajao", androidArchs: ["arm64-v8a", "armeabi-v7a"] },
};

export default ({ config }: ConfigContext): ExpoConfig => {
  const requested = process.env.APP_VARIANT ?? "development";
  if (!(requested in VARIANTS)) throw new Error(`Unknown APP_VARIANT: ${requested}`);
  const variant = VARIANTS[requested as Variant];
  return {
    ...config,
    name: variant.name,
    slug: config.slug ?? "sajao",
    ios: { ...config.ios, bundleIdentifier: variant.iosId ?? variant.id },
    android: { ...config.android, package: variant.id },
    plugins: [
      ...(config.plugins ?? []),
      ["expo-build-properties", { android: { buildArchs: variant.androidArchs } }],
      "./plugins/with-mediapipe-ios",
    ],
  };
};
