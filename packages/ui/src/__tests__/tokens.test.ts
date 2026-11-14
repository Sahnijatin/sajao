import { tierFor } from "../deviceTier";
import { motion, resolveDuration } from "../motion";
import { colors, fontFor, glass, radius, shadows } from "../tokens";

const GB = 1024 ** 3;

describe("LiveMap tokens match the design doc", () => {
  it("colors", () => {
    expect(colors).toMatchObject({
      canvas: "#eef0f5",
      ink: "#1d1d1f",
      inkSecondary: "#55595f",
      inkTertiary: "#636873",
      accent: "#0a7cff",
      success: "#1fae55",
      danger: "#ff3b30",
      warning: "#ff8a00",
    });
  });

  it("glass, radius and shadows", () => {
    expect(glass).toMatchObject({ fill: "rgba(255, 255, 255, 0.62)", blurRadius: 28 });
    expect(radius).toMatchObject({ pane: 20, card: 14 });
    expect(shadows.standard.split("),")).toHaveLength(3);
    expect(shadows.low.split("),")).toHaveLength(1);
  });

  it("type: system font on iOS, bundled Geist on Android", () => {
    expect(fontFor("medium", "ios")).toEqual({ fontWeight: "500" });
    expect(fontFor("medium", "android")).toEqual({ fontFamily: "Geist-Medium" });
  });
});

describe("motion presets", () => {
  it("match the design doc", () => {
    expect(motion.ease).toEqual({ bezier: [0.32, 0.72, 0, 1], durationMs: 450 });
    expect(motion.selectionSpring).toMatchObject({ stiffness: 380, damping: 32 });
    expect(motion.layoutGlide).toEqual({ duration: 450, dampingRatio: 1 });
  });

  it("reduced motion turns every animation into an instant change", () => {
    for (const tier of ["standard", "low"] as const) {
      expect(resolveDuration(450, { reducedMotion: true, tier })).toBe(0);
    }
  });

  it("the low tier gets shorter animations, never none", () => {
    expect(resolveDuration(450, { reducedMotion: false, tier: "standard" })).toBe(450);
    expect(resolveDuration(450, { reducedMotion: false, tier: "low" })).toBe(300);
  });
});

describe("device tier", () => {
  it("treats budget Android phones (up to 4 GB) as low tier", () => {
    expect(tierFor("android", 3 * GB)).toBe("low");
    expect(tierFor("android", 4 * GB)).toBe("low");
    expect(tierFor("android", 8 * GB)).toBe("standard");
  });

  it("falls back to low when Android memory is unknown", () => {
    expect(tierFor("android", null)).toBe("low");
  });

  it("treats iPhones as standard", () => {
    expect(tierFor("ios", 3 * GB)).toBe("standard");
  });
});
