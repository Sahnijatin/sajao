import * as Haptics from "expo-haptics";
import { type HapticMoment, hapticMap, playHaptic } from "../haptics";

jest.mock("expo-haptics", () => ({
  ...jest.requireActual("expo-haptics"),
  impactAsync: jest.fn(() => Promise.resolve()),
  selectionAsync: jest.fn(() => Promise.resolve()),
  notificationAsync: jest.fn(() => Promise.resolve()),
  performAndroidHapticsAsync: jest.fn(() => Promise.resolve()),
}));

const { ImpactFeedbackStyle: Impact, NotificationFeedbackType: Notify, AndroidHaptics } = Haptics;

beforeEach(() => jest.clearAllMocks());

describe("haptic map", () => {
  it("covers every moment in the design doc", () => {
    expect(Object.keys(hapticMap).sort()).toEqual(
      [
        "collision",
        "cornerCaptured",
        "designReveal",
        "furnitureSnap",
        "levelReached",
        "priceTick",
        "roomVerified",
        "swapLands",
      ].sort(),
    );
  });

  it.each<[HapticMoment, unknown, unknown]>([
    ["cornerCaptured", Haptics.impactAsync, Impact.Light],
    ["roomVerified", Haptics.notificationAsync, Notify.Success],
    ["furnitureSnap", Haptics.impactAsync, Impact.Medium],
    ["collision", Haptics.impactAsync, Impact.Rigid],
    ["swapLands", Haptics.impactAsync, Impact.Soft],
    ["priceTick", Haptics.impactAsync, Impact.Soft],
  ])("iOS %s", async (moment, call, argument) => {
    await playHaptic(moment, "ios");
    expect(call).toHaveBeenCalledTimes(1);
    expect(call).toHaveBeenCalledWith(argument);
    expect(Haptics.performAndroidHapticsAsync).not.toHaveBeenCalled();
  });

  it("iOS level reached is a selection tick", async () => {
    await playHaptic("levelReached", "ios");
    expect(Haptics.selectionAsync).toHaveBeenCalledTimes(1);
  });

  it("iOS design reveal is a light cascade", async () => {
    await playHaptic("designReveal", "ios");
    expect(Haptics.impactAsync).toHaveBeenCalledTimes(3);
    expect(Haptics.impactAsync).toHaveBeenCalledWith(Impact.Light);
  });

  it.each<[HapticMoment, Haptics.AndroidHaptics]>([
    ["cornerCaptured", AndroidHaptics.Clock_Tick],
    ["levelReached", AndroidHaptics.Clock_Tick],
    ["roomVerified", AndroidHaptics.Confirm],
    ["furnitureSnap", AndroidHaptics.Clock_Tick],
    ["collision", AndroidHaptics.Long_Press],
    ["swapLands", AndroidHaptics.Clock_Tick],
    ["designReveal", AndroidHaptics.Clock_Tick],
  ])("Android %s is one simple pattern", async (moment, pattern) => {
    await playHaptic(moment, "android");
    expect(Haptics.performAndroidHapticsAsync).toHaveBeenCalledTimes(1);
    expect(Haptics.performAndroidHapticsAsync).toHaveBeenCalledWith(pattern);
    expect(Haptics.impactAsync).not.toHaveBeenCalled();
  });

  it("Android price ticks are silent", async () => {
    await playHaptic("priceTick", "android");
    expect(Haptics.performAndroidHapticsAsync).not.toHaveBeenCalled();
  });

  it("never throws when the device cannot play a haptic", async () => {
    jest.mocked(Haptics.impactAsync).mockRejectedValueOnce(new Error("no motor"));
    await expect(playHaptic("collision", "ios")).resolves.toBeUndefined();
  });

  it("does nothing on web", async () => {
    await playHaptic("collision", "web");
    expect(Haptics.impactAsync).not.toHaveBeenCalled();
  });
});
