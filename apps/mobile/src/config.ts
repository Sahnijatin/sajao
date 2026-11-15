// Per-environment configuration for the app. Values come from EXPO_PUBLIC_*
// variables set on the EAS environment (development, preview, production),
// never from the repository. These are public values: the project URL and
// the publishable key are meant to ship inside the app. Secret keys never
// belong here.

export type Environment = "development" | "preview" | "production";

export interface AppConfig {
  environment: Environment;
  /** Base URL of the Sajao API, or null until one is deployed for this environment. */
  apiUrl: string | null;
  supabase: { url: string; publishableKey: string } | null;
}

type Env = Record<string, string | undefined>;

const ENVIRONMENTS: readonly Environment[] = ["development", "preview", "production"];

function httpsUrl(name: string, value: string | undefined): string | null {
  if (!value) return null;
  if (
    !/^https:\/\/\S+$/.test(value) &&
    !/^http:\/\/(localhost|127\.0\.0\.1|10\.0\.2\.2)(:\d+)?/.test(value)
  ) {
    throw new Error(`${name} must be an https URL (http is allowed only for a local stack)`);
  }
  return value.replace(/\/+$/, "");
}

export function parseConfig(env: Env): AppConfig {
  const environment = (env.EXPO_PUBLIC_ENVIRONMENT ?? "development") as Environment;
  if (!ENVIRONMENTS.includes(environment)) {
    throw new Error(`EXPO_PUBLIC_ENVIRONMENT must be one of ${ENVIRONMENTS.join(", ")}`);
  }
  const url = httpsUrl("EXPO_PUBLIC_SUPABASE_URL", env.EXPO_PUBLIC_SUPABASE_URL);
  const key = env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if ((url === null) !== !key) {
    throw new Error(
      "EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY go together",
    );
  }
  // A secret or service key would give every phone full database access.
  if (key && !key.startsWith("sb_publishable_")) {
    throw new Error("EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY must be a publishable key");
  }
  return {
    environment,
    apiUrl: httpsUrl("EXPO_PUBLIC_API_URL", env.EXPO_PUBLIC_API_URL),
    supabase: url && key ? { url, publishableKey: key } : null,
  };
}

// Expo inlines EXPO_PUBLIC_* only when each is read by its full name.
export const config = parseConfig({
  EXPO_PUBLIC_ENVIRONMENT: process.env.EXPO_PUBLIC_ENVIRONMENT,
  EXPO_PUBLIC_API_URL: process.env.EXPO_PUBLIC_API_URL,
  EXPO_PUBLIC_SUPABASE_URL: process.env.EXPO_PUBLIC_SUPABASE_URL,
  EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
});
