import { ThemeProvider } from "@sajao/ui";
import { act, fireEvent, render, screen } from "@testing-library/react-native";
import "@/i18n";
import type { TakenPhoto } from "@/photos/photo-session";
import type { SavedPhoto } from "@/photos/take-photo";
import { TakePhotosScreen } from "@/screens/take-photos";

let mockRotation = 0;
const mockTakePhoto = jest.fn(async () => "file:///raw.jpg");
jest.mock("@/photos/photo-camera", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  return {
    PhotoCamera: React.forwardRef(function MockCamera(
      { onRotation }: { onRotation: (degrees: number) => void },
      ref: React.Ref<{ takePhoto: () => Promise<string> }>,
    ) {
      React.useImperativeHandle(ref, () => ({ takePhoto: mockTakePhoto }));
      React.useEffect(() => onRotation(mockRotation), [onRotation]);
      return null;
    }),
  };
});
let mockPermission = true;
jest.mock("react-native-vision-camera", () => ({
  useCameraPermission: () => ({
    hasPermission: mockPermission,
    canRequestPermission: true,
    requestPermission: jest.fn(),
  }),
}));
jest.mock("expo-image-manipulator", () => ({}));
jest.mock(
  "react-native-safe-area-context",
  () => jest.requireActual("react-native-safe-area-context/jest/mock").default,
);
const mockHaptic = jest.fn();
jest.mock("@sajao/ui", () => ({
  ...jest.requireActual("@sajao/ui"),
  playHaptic: (...args: unknown[]) => mockHaptic(...args),
}));

const wide = (n: number): TakenPhoto => ({
  uri: `file:///p${n}.jpg`,
  widthPx: 1600,
  heightPx: 1200,
});

async function open(
  prepare: jest.Mock<Promise<SavedPhoto>, [string]> = jest.fn(async (_uri: string) => ({
    ok: true as const,
    photo: wide(1),
  })),
) {
  const handlers = { onDone: jest.fn(), onClose: jest.fn(), onUsePhotos: jest.fn() };
  await render(
    <ThemeProvider tier="low" reducedMotion>
      <TakePhotosScreen {...handlers} prepare={prepare} />
    </ThemeProvider>,
  );
  return { ...handlers, prepare };
}

beforeEach(() => {
  mockRotation = 90;
  mockPermission = true;
  mockTakePhoto.mockClear();
  mockHaptic.mockClear();
});

describe("Take photos", () => {
  it("opens on the note, with Use photos or a video beside it", async () => {
    const { onUsePhotos } = await open();
    expect(screen.getByTestId("photos-note")).toBeTruthy();
    expect(screen.getByText("Step back to a corner so the floor shows.")).toBeTruthy();
    expect(screen.getByText("Put away anything private.")).toBeTruthy();
    expect(screen.getByText("Keep people out of the picture.")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Use photos or a video" }));
    expect(onUsePhotos).toHaveBeenCalledTimes(1);
  });

  it("will not take a photo while the phone is upright", async () => {
    mockRotation = 0;
    await open();
    await fireEvent.press(screen.getByRole("button", { name: "Open the camera" }));
    expect(screen.getByTestId("photos-hint").props.children).toBe("Turn your phone sideways");
    await fireEvent.press(screen.getByTestId("photos-shutter"));
    expect(mockTakePhoto).not.toHaveBeenCalled();
  });

  it("takes a sideways photo, asks about it, and continues with it", async () => {
    const { onDone, prepare } = await open();
    await fireEvent.press(screen.getByRole("button", { name: "Open the camera" }));
    expect(screen.getByTestId("photos-hint").props.children).toBe(
      "Fit the room in, floor included",
    );
    expect(screen.getByText("Photo 1 of up to 3")).toBeTruthy();
    await act(async () => {
      fireEvent.press(screen.getByTestId("photos-shutter"));
    });
    expect(prepare).toHaveBeenCalledWith("file:///raw.jpg");
    expect(screen.getByText("Happy with the view and lighting?")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Continue" }));
    // Then every photo taken, each with its own Retake.
    expect(screen.getByRole("header", { name: "Your photo" })).toBeTruthy();
    expect(screen.getByTestId("photos-all-1")).toBeTruthy();
    expect(onDone).not.toHaveBeenCalled();
    await fireEvent.press(screen.getByRole("button", { name: "Use this photo" }));
    expect(onDone).toHaveBeenCalledWith([wide(1)]);
  });

  it("retake goes back to the camera and drops the photo", async () => {
    const { onDone } = await open();
    await fireEvent.press(screen.getByRole("button", { name: "Open the camera" }));
    await act(async () => {
      fireEvent.press(screen.getByTestId("photos-shutter"));
    });
    await fireEvent.press(screen.getByRole("button", { name: "Retake" }));
    expect(screen.getByTestId("photos-camera")).toBeTruthy();
    expect(screen.getByText("Photo 1 of up to 3")).toBeTruthy();
    expect(onDone).not.toHaveBeenCalled();
  });

  it("adds up to three views, shows them all, and retakes any one of them", async () => {
    let n = 0;
    const prepare = jest.fn(async (_uri: string): Promise<SavedPhoto> => ({
      ok: true,
      photo: wide(++n),
    }));
    const { onDone } = await open(prepare);
    await fireEvent.press(screen.getByRole("button", { name: "Open the camera" }));
    for (const next of [2, 3]) {
      await act(async () => {
        fireEvent.press(screen.getByTestId("photos-shutter"));
      });
      await fireEvent.press(screen.getByRole("button", { name: "Continue" }));
      await fireEvent.press(
        screen.getByRole("button", { name: `Add another view (${next} of 3)` }),
      );
    }
    await act(async () => {
      fireEvent.press(screen.getByTestId("photos-shutter"));
    });
    await fireEvent.press(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("header", { name: "Your 3 photos" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Add another view/ })).toBeNull();
    // Retake the second: the camera says which, and the new one takes its place.
    await fireEvent.press(screen.getByRole("button", { name: "Retake photo 2" }));
    expect(screen.getByText("Photo 2 of up to 3")).toBeTruthy();
    await act(async () => {
      fireEvent.press(screen.getByTestId("photos-shutter"));
    });
    await fireEvent.press(screen.getByRole("button", { name: "Continue" }));
    await fireEvent.press(screen.getByRole("button", { name: "Use these photos" }));
    expect(onDone).toHaveBeenCalledWith([wide(1), wide(4), wide(3)]);
  });

  it("says so when a photo came out upright", async () => {
    await open(
      jest.fn(async (_uri: string): Promise<SavedPhoto> => ({
        ok: false,
        problem: "notLandscape",
      })),
    );
    await fireEvent.press(screen.getByRole("button", { name: "Open the camera" }));
    await act(async () => {
      fireEvent.press(screen.getByTestId("photos-shutter"));
    });
    expect(screen.getByTestId("photos-hint").props.children).toBe(
      "That one came out upright. Hold your phone sideways and try again",
    );
  });

  it("asks for the camera, and offers photos already on the phone instead", async () => {
    mockPermission = false;
    const { onUsePhotos } = await open();
    await fireEvent.press(screen.getByRole("button", { name: "Open the camera" }));
    expect(screen.getByTestId("photos-permission")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Use photos or a video" }));
    expect(onUsePhotos).toHaveBeenCalledTimes(1);
  });
});
