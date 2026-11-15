import AsyncStorage from "@react-native-async-storage/async-storage";
import { ThemeProvider } from "@sajao/ui";
import { act, fireEvent, render, screen } from "@testing-library/react-native";
import type { ReactElement } from "react";
import i18n from "@/i18n";
import { HomeScreen } from "@/screens/home";
import { ProfileScreen } from "@/screens/profile";
import { RoomsScreen } from "@/screens/rooms";
import { VastuScreen } from "@/screens/vastu";
import { useSettings } from "@/state/settings";

const mockPush = jest.fn();
jest.mock("expo-router", () => ({ useRouter: () => ({ push: mockPush }) }));
jest.mock(
  "react-native-safe-area-context",
  () => jest.requireActual("react-native-safe-area-context/jest/mock").default,
);

const show = (ui: ReactElement) =>
  render(
    <ThemeProvider tier="standard" reducedMotion>
      {ui}
    </ThemeProvider>,
  );

beforeEach(async () => {
  mockPush.mockClear();
  await AsyncStorage.clear();
  await act(async () => {
    useSettings.setState({ language: null, units: "cm" });
    await i18n.changeLanguage("en");
  });
});

describe("tab screens", () => {
  it("Home shows the tagline with no sign-in gate", async () => {
    await show(<HomeScreen />);
    expect(screen.getByText("Scan your room. See it redone. Buy what fits.")).toBeTruthy();
    expect(screen.queryByText(/sign in/i)).toBeNull();
  });

  it("My rooms shows an empty state", async () => {
    await show(<RoomsScreen />);
    expect(screen.getByText("No rooms yet")).toBeTruthy();
  });

  it("Vastu carries the guidance label", async () => {
    await show(<VastuScreen />);
    expect(screen.getByText(/^Vastu guidance, as close as possible\./)).toBeTruthy();
  });

  it("render in Hindi", async () => {
    await act(async () => {
      await i18n.changeLanguage("hi");
    });
    await show(<RoomsScreen />);
    expect(screen.getByText("मेरे कमरे")).toBeTruthy();
  });
});

describe("Profile", () => {
  it("is usable as a guest", async () => {
    await show(<ProfileScreen />);
    expect(screen.getByText("You are browsing as a guest")).toBeTruthy();
  });

  it("switches units between centimetres and feet and inches, and remembers", async () => {
    await show(<ProfileScreen />);
    expect(screen.getByText("A 3.4 m wall shows as 340 cm")).toBeTruthy();

    await fireEvent.press(screen.getByRole("button", { name: "Feet and inches" }));
    expect(screen.getByText("A 3.4 m wall shows as 11 ft 2 in")).toBeTruthy();
    expect(useSettings.getState().units).toBe("ft_in");
    const stored = JSON.parse((await AsyncStorage.getItem("sajao.settings")) ?? "{}");
    expect(stored.state).toEqual({ language: null, units: "ft_in" });
  });

  it("stores the chosen language", async () => {
    await show(<ProfileScreen />);
    await fireEvent.press(screen.getByRole("button", { name: "हिन्दी" }));
    expect(useSettings.getState().language).toBe("hi");
  });

  it("links to the component gallery in development", async () => {
    await show(<ProfileScreen />);
    await fireEvent.press(screen.getByRole("button", { name: "Component gallery" }));
    expect(mockPush).toHaveBeenCalledWith("/gallery");
  });
});
