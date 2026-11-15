// The haptic map, from docs/10-design-language-and-motion.md. Small rewards
// at real milestones only. Android motors vary widely, so patterns stay
// simple there. Both platforms respect the system haptics setting.
import * as Haptics from "expo-haptics";
import { Platform } from "react-native";

export type HapticMoment =
  | "cornerCaptured"
  | "levelReached"
  | "roomVerified"
  | "furnitureSnap"
  | "collision"
  | "swapLands"
  | "priceTick"
  | "designReveal";

type IosStep =
  | { kind: "impact"; style: Haptics.ImpactFeedbackStyle }
  | { kind: "selection" }
  | { kind: "notification"; type: Haptics.NotificationFeedbackType };

interface HapticPattern {
  /** One or more steps; more than one plays as a cascade. */
  ios: readonly IosStep[];
  /** null means no haptic on Android for this moment. */
  android: Haptics.AndroidHaptics | null;
}

const { ImpactFeedbackStyle: Impact, NotificationFeedbackType: Notify, AndroidHaptics } = Haptics;
const shortTick = AndroidHaptics.Clock_Tick;

export const hapticMap: Record<HapticMoment, HapticPattern> = {
  cornerCaptured: { ios: [{ kind: "impact", style: Impact.Light }], android: shortTick },
  levelReached: { ios: [{ kind: "selection" }], android: shortTick },
  roomVerified: {
    ios: [{ kind: "notification", type: Notify.Success }],
    android: AndroidHaptics.Confirm, // double tick
  },
  furnitureSnap: { ios: [{ kind: "impact", style: Impact.Medium }], android: shortTick },
  collision: {
    ios: [{ kind: "impact", style: Impact.Rigid }],
    android: AndroidHaptics.Long_Press, // single strong tick
  },
  swapLands: { ios: [{ kind: "impact", style: Impact.Soft }], android: shortTick },
  priceTick: { ios: [{ kind: "impact", style: Impact.Soft }], android: null },
  designReveal: {
    // Light cascade as items land.
    ios: [
      { kind: "impact", style: Impact.Light },
      { kind: "impact", style: Impact.Light },
      { kind: "impact", style: Impact.Light },
    ],
    android: shortTick,
  },
};

const CASCADE_GAP_MS = 90;

function playIosStep(step: IosStep) {
  switch (step.kind) {
    case "impact":
      return Haptics.impactAsync(step.style);
    case "selection":
      return Haptics.selectionAsync();
    case "notification":
      return Haptics.notificationAsync(step.type);
  }
}

/**
 * Play the haptic for a moment. Fire it in the same frame as the visual it
 * confirms. Haptics are never the only feedback, so failures are ignored.
 */
export async function playHaptic(moment: HapticMoment, os: string = Platform.OS): Promise<void> {
  const pattern = hapticMap[moment];
  try {
    if (os === "android") {
      if (pattern.android !== null) await Haptics.performAndroidHapticsAsync(pattern.android);
      return;
    }
    if (os !== "ios") return;
    for (const [index, step] of pattern.ios.entries()) {
      if (index > 0) await new Promise((resolve) => setTimeout(resolve, CASCADE_GAP_MS));
      await playIosStep(step);
    }
  } catch {
    // No motor, or haptics switched off: the visual stands alone.
  }
}
