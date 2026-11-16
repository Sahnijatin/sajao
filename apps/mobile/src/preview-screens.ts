// The component gallery and the screen previews are tools for building and
// reviewing the app. They show in development and in preview builds for
// testers, and never in the store build.
export function previewScreensEnabled(
  isDev: boolean = __DEV__,
  environment: string | undefined = process.env.EXPO_PUBLIC_ENVIRONMENT,
): boolean {
  return isDev || environment === "preview";
}
