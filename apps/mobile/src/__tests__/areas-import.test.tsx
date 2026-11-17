import AsyncStorage from "@react-native-async-storage/async-storage";
import { ThemeProvider } from "@sajao/ui";
import { act, fireEvent, render, screen } from "@testing-library/react-native";
import "@/i18n";
import type { RoomArea } from "@/rooms/room-content";
import { AreasScreen } from "@/screens/areas";
import { ImportMediaScreen } from "@/screens/import-media";
import { useSettings } from "@/state/settings";

const mockHaptic = jest.fn();
jest.mock("@sajao/ui", () => ({
  ...jest.requireActual("@sajao/ui"),
  playHaptic: (moment: string) => mockHaptic(moment),
}));

const wrap = (ui: React.ReactElement) =>
  render(
    <ThemeProvider tier="standard" reducedMotion>
      {ui}
    </ThemeProvider>,
  );

const area = (id: string, spaceType: RoomArea["spaceType"]): RoomArea => ({
  id,
  spaceType,
  photo: { kind: "image", uri: `https://example.com/${id}.jpg` },
  heroViews: [],
  measures: null,
  shell: null,
  confidence: "measured",
});

beforeEach(async () => {
  mockHaptic.mockClear();
  await AsyncStorage.clear();
  await act(async () => {
    useSettings.setState({ language: null, units: "cm" });
  });
});

describe("which area to redesign", () => {
  const areas = [area("kitchen", "other"), area("living", "living_room"), area("bed", "bedroom")];

  it("shows each area and starts on the first one that can be designed", async () => {
    const onChoose = jest.fn();
    await wrap(<AreasScreen areas={areas} onChoose={onChoose} />);
    expect(screen.getByText("Your scan covers 3 areas. Pick the one to redesign.")).toBeTruthy();
    const radios = screen.getAllByRole("radio");
    expect(radios.map((radio) => radio.props.accessibilityState.selected)).toEqual([
      false,
      true,
      false,
    ]);
    await fireEvent.press(screen.getByRole("button", { name: "Redesign this one" }));
    expect(onChoose).toHaveBeenCalledWith("living");
  });

  it("lets you pick another, and not a kind of space with no designs yet", async () => {
    const onChoose = jest.fn();
    await wrap(<AreasScreen areas={areas} onChoose={onChoose} />);
    expect(screen.getByText("Designs for this kind of space are coming")).toBeTruthy();
    await fireEvent.press(screen.getByTestId("area-kitchen"));
    await fireEvent.press(screen.getByTestId("area-bed"));
    await fireEvent.press(screen.getByRole("button", { name: "Redesign this one" }));
    expect(onChoose).toHaveBeenCalledWith("bed");
    expect(mockHaptic).toHaveBeenCalledWith("roomVerified");
  });

  it("opens on the earlier choice when changing it", async () => {
    await wrap(<AreasScreen areas={areas} chosenId="bed" onChoose={jest.fn()} />);
    expect(screen.getByTestId("area-bed").props.accessibilityState.selected).toBe(true);
  });
});

describe("use photos or a video", () => {
  it("says sizes from pictures are estimates, before anything is chosen", async () => {
    await wrap(<ImportMediaScreen onImported={jest.fn()} onScan={jest.fn()} />);
    expect(screen.getByText(/^Sizes from photos are estimates\./)).toBeTruthy();
    expect(screen.queryByTestId("import-problem")).toBeNull();
  });

  it("goes on to the new room once the pictures are chosen", async () => {
    const onImported = jest.fn();
    await wrap(
      <ImportMediaScreen
        onImported={onImported}
        onScan={jest.fn()}
        importMedia={async () => ({ status: "imported", roomId: "room-9" })}
      />,
    );
    await fireEvent.press(screen.getByRole("button", { name: "Choose photos or a video" }));
    expect(onImported).toHaveBeenCalledWith("room-9");
    expect(mockHaptic).toHaveBeenCalledWith("roomVerified");
  });

  it("stays put when the picker is closed", async () => {
    const onImported = jest.fn();
    await wrap(
      <ImportMediaScreen
        onImported={onImported}
        onScan={jest.fn()}
        importMedia={async () => ({ status: "cancelled" })}
      />,
    );
    await fireEvent.press(screen.getByRole("button", { name: "Choose photos or a video" }));
    expect(onImported).not.toHaveBeenCalled();
    expect(screen.queryByTestId("import-problem")).toBeNull();
  });

  it("says why the pictures cannot be used, and offers the scan", async () => {
    const onScan = jest.fn();
    await wrap(
      <ImportMediaScreen
        onImported={jest.fn()}
        onScan={onScan}
        importMedia={async () => ({ status: "problem", problem: "photosAndVideo" })}
      />,
    );
    await fireEvent.press(screen.getByRole("button", { name: "Choose photos or a video" }));
    expect(screen.getByText("Please choose photos or one video, not both.")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Scan the room instead" }));
    expect(onScan).toHaveBeenCalledTimes(1);
  });
});
