// Device tier, detected once at launch. The low tier gets lighter effects
// (tinted glass instead of live blur, one shadow, shorter animations),
// never broken ones.
import * as Device from "expo-device";
import { Platform } from "react-native";

export type DeviceTier = "standard" | "low";

/** Budget Android phones in the device matrix have 3 to 4 GB of RAM. */
const LOW_TIER_MAX_MEMORY_BYTES = 4 * 1024 ** 3;

export function tierFor(os: string, totalMemoryBytes: number | null): DeviceTier {
  if (os !== "android") return "standard";
  // Unknown memory on Android is treated as low: lighter is always safe.
  if (totalMemoryBytes === null) return "low";
  return totalMemoryBytes <= LOW_TIER_MAX_MEMORY_BYTES ? "low" : "standard";
}

export function detectDeviceTier(): DeviceTier {
  return tierFor(Platform.OS, Device.totalMemory);
}
