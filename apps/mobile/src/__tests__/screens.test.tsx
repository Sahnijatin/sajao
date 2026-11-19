import AsyncStorage from "@react-native-async-storage/async-storage";
import { ThemeProvider } from "@sajao/ui";
import { act, fireEvent, render, screen } from "@testing-library/react-native";
import type { ReactElement } from "react";
import i18n from "@/i18n";
import { HomeScreen } from "@/screens/home";
import { ProfileScreen } from "@/screens/profile";
import { useCaptureStore } from "@/state/capture";
import { useRooms } from "@/state/rooms";
import { useSettings } from "@/state/settings";
import { useTaste } from "@/state/taste";

const mockPush = jest.fn();
const mockReplace = jest.fn();
const mockDelete = jest.fn<Promise<"deleted" | "unreachable">, []>(async () => "deleted");
jest.mock("expo-router", () => {
  const { useEffect } = jest.requireActual<typeof import("react")>("react");
  return {
    useRouter: () => ({ push: mockPush, replace: mockReplace }),
    // A screen under test is always the focused one.
    useFocusEffect: (effect: () => void) => useEffect(effect, [effect]),
  };
});
let mockPreview = true;
jest.mock("@/preview-screens", () => ({ previewScreensEnabled: () => mockPreview }));
const mockHaptic = jest.fn();
jest.mock("@sajao/ui", () => ({
  ...jest.requireActual("@sajao/ui"),
  playHaptic: (moment: string) => mockHaptic(moment),
}));
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
  mockHaptic.mockClear();
  mockPreview = true;
  await AsyncStorage.clear();
  await act(async () => {
    useRooms.setState({ rooms: [] });
    useTaste.setState({ answers: null });
    useCaptureStore.setState({ upload: { state: "idle", finished: 0, total: 0 } });
    useSettings.setState({ language: null, units: "cm" });
    await i18n.changeLanguage("en");
  });
});

describe("My home", () => {
  it("before the first room: one before and after, one line, and the two ways in", async () => {
    await show(<HomeScreen />);
    expect(screen.getByLabelText("A room before and after a redesign")).toBeTruthy();
    expect(screen.getByText("See your room redone with furniture you can buy.")).toBeTruthy();
    expect(screen.getAllByRole("button")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Add a room" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Use photos or a video" })).toBeTruthy();
    expect(screen.queryByText(/sign in/i)).toBeNull();
    expect(screen.queryByText(/living room|bedroom/i)).toBeNull();
    expect(screen.queryByText(/scan/i)).toBeNull();
  });

  it("a store build shows the line and the button without the drawn stand-in", async () => {
    mockPreview = false;
    await show(<HomeScreen />);
    expect(screen.queryByLabelText("A room before and after a redesign")).toBeNull();
    expect(screen.getByText("See your room redone with furniture you can buy.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add a room" })).toBeTruthy();
    // Photos are the main way in, so every build offers both.
    expect(screen.getByRole("button", { name: "Use photos or a video" })).toBeTruthy();
  });

  it("Use photos or a video opens the import screen", async () => {
    await show(<HomeScreen />);
    await fireEvent.press(screen.getByRole("button", { name: "Use photos or a video" }));
    expect(mockPush).toHaveBeenCalledWith("/import");
  });

  it("Add a room opens Take photos, never the scan", async () => {
    await show(<HomeScreen />);
    await fireEvent.press(screen.getByRole("button", { name: "Add a room" }));
    expect(mockPush).toHaveBeenCalledTimes(1);
    expect(mockPush).toHaveBeenCalledWith("/photos");
  });

  it("lists rooms newest first, each with its name, last update and designs", async () => {
    const day = 24 * 60 * 60 * 1000;
    const now = Date.now();
    useRooms.setState({
      rooms: [
        {
          id: "one",
          name: null,
          number: 1,
          updatedAtMs: now - 5 * day,
          designCount: 3,
          still: { kind: "placeholder", look: "after" },
          captureId: "one",
        },
        {
          id: "two",
          name: "Bedroom by the balcony",
          number: 2,
          updatedAtMs: now,
          designCount: 0,
          still: { kind: "placeholder", look: "before" },
          captureId: "two",
        },
      ],
    });
    await show(<HomeScreen />);
    expect(screen.getByRole("header", { name: "My home" })).toBeTruthy();
    const cards = screen.getAllByTestId(/^room-card-/);
    expect(cards.map((card) => card.props.accessibilityLabel)).toEqual([
      "Bedroom by the balcony. Updated today · No designs yet",
      "Room 1. Updated 5 days ago · 3 designs",
    ]);
    expect(screen.queryByLabelText("A room before and after a redesign")).toBeNull();
    await fireEvent.press(screen.getByRole("button", { name: "Add a room" }));
    expect(mockPush).toHaveBeenCalledWith("/photos");
    // A card opens its room.
    await fireEvent.press(screen.getByTestId("room-card-one"));
    expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/room/[id]", params: { id: "one" } });
  });

  it("ticks softly when a new room lands, and not on first sight of the list", async () => {
    await show(<HomeScreen />);
    expect(mockHaptic).not.toHaveBeenCalled();
    await act(async () => {
      useRooms.getState().addRoomForCapture("capture-1");
    });
    expect(screen.getByText("Room 1")).toBeTruthy();
    expect(mockHaptic).toHaveBeenCalledWith("roomAdded");
    expect(mockHaptic).toHaveBeenCalledTimes(1);
  });

  it("keeps one room for a scan that is added twice, and remembers rooms on the phone", async () => {
    await act(async () => {
      useRooms.getState().addRoomForCapture("capture-1");
      useRooms.getState().addRoomForCapture("capture-1");
    });
    expect(useRooms.getState().rooms).toHaveLength(1);
    const stored = JSON.parse((await AsyncStorage.getItem("sajao.rooms")) ?? "{}");
    expect(stored.state.rooms).toHaveLength(1);
  });

  it("still shows the state of the last upload", async () => {
    useCaptureStore.setState({ upload: { state: "failed", finished: 0, total: 0 } });
    await show(<HomeScreen />);
    expect(screen.getByText("Upload paused. Nothing is lost")).toBeTruthy();
  });

  it("renders in Hindi", async () => {
    await act(async () => {
      await i18n.changeLanguage("hi");
    });
    await show(<HomeScreen />);
    expect(screen.getByRole("button", { name: "कमरा जोड़ें" })).toBeTruthy();
  });
});

describe("Profile", () => {
  it("is usable as a guest", async () => {
    await show(<ProfileScreen onDeleteAccount={mockDelete} />);
    expect(screen.getByText("You are browsing as a guest")).toBeTruthy();
  });

  it("offers taste and budget before they are set, and shows them with Change after", async () => {
    const view = await show(<ProfileScreen onDeleteAccount={mockDelete} />);
    await fireEvent.press(screen.getByRole("button", { name: "Set my taste" }));
    expect(mockPush).toHaveBeenLastCalledWith("/taste");
    await act(async () => {
      useTaste.getState().setAnswers({
        context: { age_band: "25_34", household: ["couple"], tenure: "owned" },
        swipes: [],
        attributes: {
          palette_warmth: 0.7,
          saturation: 0.4,
          boldness: 0.4,
          clutter_tolerance: 0.3,
          formality: 0.5,
          trend_vs_timeless: 0.6,
        },
        style_blend: [{ style: "japandi", weight: 1 }],
        traits: ["warm_tones", "natural_wood"],
        budget: { limit: { currency: "INR", amount_minor: 15000000 }, flexibility: "strict" },
        must_haves: [],
        consider_vastu: false,
      });
    });
    await view.rerender(
      <ThemeProvider tier="standard" reducedMotion>
        <ProfileScreen onDeleteAccount={mockDelete} />
      </ThemeProvider>,
    );
    expect(screen.getByText("Warm tones · Natural wood")).toBeTruthy();
    expect(screen.getByText("Budget ₹1,50,000")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Change" }));
    expect(mockPush).toHaveBeenLastCalledWith("/taste");
    // The answers are kept on the phone for the next room.
    const stored = JSON.parse((await AsyncStorage.getItem("sajao.taste")) ?? "{}");
    expect(stored.state.answers.budget.limit.amount_minor).toBe(15000000);
  });

  it("switches units between centimetres and feet and inches, and remembers", async () => {
    await show(<ProfileScreen onDeleteAccount={mockDelete} />);
    expect(screen.getByText("A 3.4 m wall shows as 340 cm")).toBeTruthy();

    await fireEvent.press(screen.getByRole("button", { name: "Feet and inches" }));
    expect(screen.getByText("A 3.4 m wall shows as 11 ft 2 in")).toBeTruthy();
    expect(useSettings.getState().units).toBe("ft_in");
    const stored = JSON.parse((await AsyncStorage.getItem("sajao.settings")) ?? "{}");
    expect(stored.state).toEqual({ language: null, units: "ft_in" });
  });

  it("stores the chosen language", async () => {
    await show(<ProfileScreen onDeleteAccount={mockDelete} />);
    await fireEvent.press(screen.getByRole("button", { name: "हिन्दी" }));
    expect(useSettings.getState().language).toBe("hi");
  });

  it("deletes the account and everything kept for it, after asking, then goes to My home", async () => {
    mockDelete.mockClear();
    mockReplace.mockClear();
    await show(<ProfileScreen onDeleteAccount={mockDelete} />);
    await fireEvent.press(screen.getByRole("button", { name: "Delete my account and data" }));
    expect(screen.getByText("Delete your account and data?")).toBeTruthy();
    expect(mockDelete).not.toHaveBeenCalled();
    await fireEvent.press(screen.getByRole("button", { name: "Delete everything" }));
    expect(mockDelete).toHaveBeenCalledTimes(1);
    expect(mockReplace).toHaveBeenCalledWith("/");
  });

  it("says nothing was deleted when Sajao cannot be reached, and stays put", async () => {
    mockDelete.mockClear();
    mockReplace.mockClear();
    mockDelete.mockResolvedValueOnce("unreachable");
    await show(<ProfileScreen onDeleteAccount={mockDelete} />);
    await fireEvent.press(screen.getByRole("button", { name: "Delete my account and data" }));
    await fireEvent.press(screen.getByRole("button", { name: "Delete everything" }));
    expect(screen.getByTestId("delete-account-unreachable")).toBeTruthy();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("links to the component gallery in development", async () => {
    await show(<ProfileScreen onDeleteAccount={mockDelete} />);
    await fireEvent.press(screen.getByRole("button", { name: "Component gallery" }));
    expect(mockPush).toHaveBeenCalledWith("/gallery");
  });
});
