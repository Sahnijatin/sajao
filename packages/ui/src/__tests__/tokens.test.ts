import { tierFor } from "../deviceTier";
import { motion, resolveDuration } from "../motion";
import {
  colors,
  controlHeight,
  fontFor,
  glass,
  radius,
  shadows,
  spacing,
  typography,
} from "../tokens";

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

  it("light and dark glass", () => {
    expect(glass.blurRadius).toBe(28);
    expect(glass.light).toMatchObject({ fill: "rgba(255, 255, 255, 0.62)", saturation: 1.8 });
    // Dark glass is for camera screens.
    expect(glass.dark).toMatchObject({
      fill: "rgba(20, 22, 26, 0.42)",
      border: "rgba(255, 255, 255, 0.18)",
      saturation: 1.6,
      text: "#ffffff",
    });
  });

  it("radius: panes, cards, sheets and pills", () => {
    expect(radius).toEqual({ pane: 20, card: 20, sheet: 30, pill: 999 });
  });

  it("shadows: three stacked on standard devices, one on the low tier", () => {
    expect(shadows.standard.card.split("),")).toHaveLength(3);
    expect(shadows.low.card.split("),")).toHaveLength(1);
    expect(shadows.standard.sheet).toBe("0 -16px 40px rgba(29, 29, 31, 0.12)");
    expect(shadows.standard.accentGlow).toBe("0 10px 24px rgba(10, 124, 255, 0.35)");
    expect(shadows.low.accentGlow).toBe("none");
  });
});

describe("values from the approved mockups", () => {
  it("spacing ladder", () => {
    expect(spacing).toEqual({
      xxs: 2,
      xs: 4,
      sm: 6,
      md: 8,
      lg: 10,
      xl: 12,
      xxl: 14,
      gutter: 16,
      sheetBottom: 26,
    });
  });

  it("control heights: 56 px pill buttons", () => {
    expect(controlHeight).toEqual({ button: 56, buttonSmall: 32, chip: 36 });
  });

  it("type scale: Instrument Serif headlines over a sans body", () => {
    expect(typography.display).toEqual({
      fontSize: 46,
      lineHeight: 46,
      face: "serif",
      letterSpacing: -0.8,
    });
    expect(typography.title).toEqual({ fontSize: 34, lineHeight: 36, face: "serif" });
    expect(typography.heading).toEqual({ fontSize: 26, lineHeight: 28, face: "serif" });
    expect(typography.body).toEqual({ fontSize: 16, lineHeight: 23, face: "regular" });
    expect(typography.label).toEqual({ fontSize: 14, lineHeight: 18, face: "semibold" });
    expect(typography.micro.fontSize).toBe(11);
    const serif = Object.entries(typography).filter(([, style]) => style.face === "serif");
    expect(serif.map(([name]) => name)).toEqual(["display", "title", "heading"]);
  });

  it("fonts: the serif is bundled on both platforms; body is system on iOS, Geist on Android", () => {
    for (const os of ["ios", "android"]) {
      expect(fontFor("serif", os)).toEqual({ fontFamily: "InstrumentSerif-Regular" });
      expect(fontFor("serifItalic", os)).toEqual({ fontFamily: "InstrumentSerif-Italic" });
    }
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
