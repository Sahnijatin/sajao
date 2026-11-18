// Features that are built towards but not switched on. Each is off unless
// its EXPO_PUBLIC_* value on the EAS environment says otherwise.

/**
 * The 3D view of a room. The app may launch without it: the Room tab is
 * built on hero photos and measured dimensions, and only keeps a place for
 * the 3D view, shown when this is on.
 */
export function twinViewerEnabled(
  value: string | undefined = process.env.EXPO_PUBLIC_TWIN_VIEWER,
): boolean {
  return value === "1";
}
