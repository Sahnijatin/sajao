// Per-variant app identity on top of app.json. Each variant has its own
// name and application id, so a development build installs beside a preview
// or store build instead of replacing it.
import type { ConfigContext, ExpoConfig } from "expo/config";

type Variant = "development" | "preview" | "production";

const VARIANTS: Record<Variant, { name: string; id: string }> = {
  development: { name: "Sajao (Dev)", id: "app.sajao.dev" },
  preview: { name: "Sajao (Preview)", id: "app.sajao.preview" },
  // Working identifier: confirm it before the first store build, because a
  // store listing can never change its application id.
  production: { name: "Sajao", id: "app.sajao" },
};

export default ({ config }: ConfigContext): ExpoConfig => {
  const requested = process.env.APP_VARIANT ?? "development";
  if (!(requested in VARIANTS)) throw new Error(`Unknown APP_VARIANT: ${requested}`);
  const variant = VARIANTS[requested as Variant];
  return {
    ...config,
    name: variant.name,
    slug: config.slug ?? "sajao",
    ios: { ...config.ios, bundleIdentifier: variant.id },
    android: { ...config.android, package: variant.id },
  };
};
