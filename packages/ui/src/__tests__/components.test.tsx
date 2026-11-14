import { fireEvent, render, screen } from "@testing-library/react-native";
import * as Haptics from "expo-haptics";
import type { ReactElement } from "react";
import { StyleSheet } from "react-native";
import GalleryScreen from "../gallery/GalleryScreen";
import {
  Button,
  Card,
  Chip,
  GlassSurface,
  motion,
  Text,
  ThemeProvider,
  type ThemeProviderProps,
  useTheme,
} from "../index";
import { glass, shadows } from "../tokens";

jest.mock("expo-haptics", () => ({
  ...jest.requireActual("expo-haptics"),
  impactAsync: jest.fn(() => Promise.resolve()),
  performAndroidHapticsAsync: jest.fn(() => Promise.resolve()),
}));

function renderIn(ui: ReactElement, theme: Omit<ThemeProviderProps, "children"> = {}) {
  return render(
    <ThemeProvider tier="standard" reducedMotion={false} {...theme}>
      {ui}
    </ThemeProvider>,
  );
}

const styleOf = (element: { props: { style?: unknown } }) =>
  StyleSheet.flatten(element.props.style as never) as Record<string, unknown>;

describe("Button", () => {
  it("presses, and plays its haptic only when one is given", async () => {
    const onPress = jest.fn();
    await renderIn(
      <>
        <Button label="Plain" onPress={onPress} />
        <Button label="Snap" haptic="furnitureSnap" />
      </>,
    );
    await fireEvent.press(screen.getByRole("button", { name: "Plain" }));
    expect(onPress).toHaveBeenCalledTimes(1);
    expect(Haptics.impactAsync).not.toHaveBeenCalled();
    expect(Haptics.performAndroidHapticsAsync).not.toHaveBeenCalled();

    await fireEvent.press(screen.getByRole("button", { name: "Snap" }));
    const played =
      jest.mocked(Haptics.impactAsync).mock.calls.length +
      jest.mocked(Haptics.performAndroidHapticsAsync).mock.calls.length;
    expect(played).toBe(1);
  });

  it("does not press when disabled", async () => {
    const onPress = jest.fn();
    await renderIn(<Button label="Off" disabled onPress={onPress} />);
    await fireEvent.press(screen.getByRole("button", { name: "Off" }));
    expect(onPress).not.toHaveBeenCalled();
  });
});

describe("ThemeProvider", () => {
  it("gives components shorter durations on the low tier and none with reduced motion", async () => {
    function Probe() {
      return <Text>{String(useTheme().duration(motion.press.durationMs))}</Text>;
    }
    const shown = async (theme: Omit<ThemeProviderProps, "children">, expected: string) => {
      const view = await renderIn(<Probe />, theme);
      expect(screen.getByText(expected)).toBeTruthy();
      await view.unmount();
    };
    await shown({}, "120");
    await shown({ tier: "low" }, "80");
    await shown({ reducedMotion: true }, "0");
  });
});

describe("Chip", () => {
  it("reports selection to assistive technology and presses", async () => {
    const onPress = jest.fn();
    await renderIn(<Chip label="Japandi" selected onPress={onPress} />);
    const chip = screen.getByRole("button", { name: "Japandi" });
    expect(chip.props.accessibilityState).toEqual({ selected: true });
    await fireEvent.press(chip);
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});

describe("low-tier fallbacks", () => {
  it("glass uses a live blur on standard devices", async () => {
    await renderIn(<GlassSurface testID="glass" />);
    expect(screen.queryByTestId("glass-blur")).not.toBeNull();
    expect(styleOf(screen.getByTestId("glass")).backgroundColor).toBe(glass.fill);
  });

  it("glass falls back to a tint, with no blur, on the low tier", async () => {
    await renderIn(<GlassSurface testID="glass" />, { tier: "low" });
    expect(screen.queryByTestId("glass-blur")).toBeNull();
    expect(styleOf(screen.getByTestId("glass")).backgroundColor).toBe(glass.fallbackFill);
  });

  it("cards drop to one shadow on the low tier", async () => {
    await renderIn(<Card testID="card" />, { tier: "low" });
    expect(styleOf(screen.getByTestId("card")).boxShadow).toBe(shadows.low);
  });
});

describe("gallery", () => {
  it("renders every section and switches to the low tier", async () => {
    await render(<GalleryScreen />);
    for (const title of ["Colors", "Type", "Buttons", "Chips", "Card", "Glass surface", "Input"]) {
      expect(screen.getAllByText(title).length).toBeGreaterThan(0);
    }
    await fireEvent.press(screen.getByRole("button", { name: "Low tier" }));
    expect(screen.getByText(/Tier: low/)).toBeTruthy();
    expect(screen.queryByTestId("glass-blur")).toBeNull();
  });
});
