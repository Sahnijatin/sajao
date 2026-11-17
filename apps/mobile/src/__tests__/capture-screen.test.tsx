import { ThemeProvider } from "@sajao/ui";
import { act, fireEvent, render, screen } from "@testing-library/react-native";
import type { Hint } from "@/capture/ar/guidance";
import { INITIAL_SCAN, type ScanState } from "@/capture/scan-session";
import "@/i18n";
import { CaptureScreen, RESCAN_NUDGE_MS } from "@/screens/capture";

jest.mock("expo-keep-awake", () => ({ useKeepAwake: jest.fn() }));
jest.mock("react-native-vision-camera", () => ({
  useCameraPermission: () => ({ hasPermission: true, canRequestPermission: false }),
}));
jest.mock("@/capture/scan-camera", () => ({ ScanCamera: () => null }));
// Skia ships ESM that Jest does not load; these tests need no drawing.
jest.mock("@sajao/ui/effects", () => {
  const { View } = jest.requireActual("react-native");
  return { MeshEffect: () => <View testID="scan-mesh" /> };
});
jest.mock("@sajao/ui/icons", () => ({ Icon: () => null }));
jest.mock("@/capture/mini-map", () => ({ MiniMap: () => null }));
jest.mock("@/capture/progress-ring", () => ({ ProgressRing: () => null }));
jest.mock("@/components/scan-ring", () => ({ ScanRing: () => null }));
jest.mock("@/capture/meter-map", () => {
  const { View } = jest.requireActual("react-native");
  return { MeterMap: () => <View testID="scan-meter-map" /> };
});
jest.mock(
  "react-native-safe-area-context",
  () => jest.requireActual("react-native-safe-area-context/jest/mock").default,
);

const mockHaptic = jest.fn();
jest.mock("@sajao/ui", () => ({
  ...jest.requireActual("@sajao/ui"),
  playHaptic: (moment: string) => mockHaptic(moment),
}));

let mockPreview = true;
jest.mock("@/preview-screens", () => ({ previewScreensEnabled: () => mockPreview }));

// The scan session is the capture module's; the screen only reads it.
const mockScan = {
  share: 0,
  ready: false,
  meter: false,
  stuck: false,
  hint: null as Hint,
  state: INITIAL_SCAN as ScanState,
  scanAnyway: jest.fn(),
};
jest.mock("@/capture/scan-session", () => ({
  ...jest.requireActual("@/capture/scan-session"),
  mappedShare: () => mockScan.share,
  canFinish: () => mockScan.ready,
  isMeter: () => mockScan.meter,
  canFinishEarly: () => mockScan.stuck,
}));
jest.mock("@/capture/use-scan-session", () => ({
  useScanSession: () => ({
    state: mockScan.state,
    debug: {
      cameraFps: 0,
      analysedFps: 0,
      featurePoints: 0,
      analysisMs: 0,
      waitingSeconds: 0,
      diagnostics: { dropped: 0, lastError: null },
      ar: null,
    },
    labels: { labels: [], rejected: 0 },
    hint: mockScan.hint,
    onFrame: jest.fn(),
    onExposure: jest.fn(),
    onDiagnostics: jest.fn(),
    onArStatus: jest.fn(),
    onArPose: jest.fn(),
    onArDetections: jest.fn(),
    onArSurfaces: jest.fn(),
    scanAnyway: mockScan.scanAnyway,
  }),
}));
jest.mock("@/capture/ar/labels", () => ({
  ...jest.requireActual("@/capture/ar/labels"),
  shownLabels: () => [],
}));

// The AR view and the recorder are the capture module's too. `mockAr` turns
// the AR scan on, so a finished scan produces a capture to hand on.
let mockAr = true;
// The props the screen gives the AR view, so a test can send its events.
const mockArProps: { current: Record<string, unknown> } = { current: {} };
const mockRecorder = {
  onKeyframe: jest.fn(),
  onSensor: jest.fn(),
  onDetections: jest.fn(),
  discardKeyframes: jest.fn(async () => {}),
  setReviewOpen: jest.fn(),
};
const mockFinish = jest.fn(async () => ({ captureId: "capture-1", state: {}, files: [] }));
jest.mock("../../modules/sajao-ar", () => {
  const { View } = jest.requireActual("react-native");
  return {
    getArCapabilities: () => ({
      platform: "ios",
      arSupported: mockAr,
      lidar: false,
      depth: false,
    }),
    getArView: () =>
      mockAr
        ? (props: Record<string, unknown>) => {
            mockArProps.current = props;
            return <View testID="ar-view" />;
          }
        : null,
  };
});
jest.mock("@/capture/package/use-capture-recorder", () => ({
  useCaptureRecorder: () => ({
    viewRef: { current: { discardKeyframes: mockRecorder.discardKeyframes } },
    captureId: "capture-1",
    onKeyframe: mockRecorder.onKeyframe,
    onSensor: mockRecorder.onSensor,
    onDetections: mockRecorder.onDetections,
    finish: mockFinish,
    setReviewOpen: mockRecorder.setReviewOpen,
    capturePaused: false,
  }),
}));

const handlers = {
  onClose: jest.fn(),
  onDone: jest.fn(),
  onUsePhotos: jest.fn(),
  onCaptured: jest.fn(),
};
const ui = () => (
  <ThemeProvider tier="standard" reducedMotion>
    <CaptureScreen {...handlers} />
  </ThemeProvider>
);

beforeEach(() => {
  jest.clearAllMocks();
  mockPreview = true;
  mockAr = true;
  Object.assign(mockScan, {
    share: 0,
    ready: false,
    meter: false,
    stuck: false,
    hint: null,
    state: INITIAL_SCAN,
  });
});

const tripleTap = async () => {
  const camera = screen.getByTestId("scan-camera-area");
  await fireEvent.press(camera);
  await fireEvent.press(camera);
  await fireEvent.press(camera);
};

describe("the calm scan screen", () => {
  it("shows the camera with one instruction and one ring, and nothing else", async () => {
    await render(ui());
    expect(screen.getByText("Move slowly around the room")).toBeTruthy();
    expect(screen.getAllByTestId("scan-instruction")).toHaveLength(1);
    expect(screen.getByRole("progressbar", { name: "Scanning your room" })).toBeTruthy();
    // Diagnostics and the old panel are gone by default.
    expect(screen.queryByTestId("scan-debug-layer")).toBeNull();
    expect(screen.queryByTestId("scan-mesh")).toBeNull();
    expect(screen.queryByTestId("scan-mapped")).toBeNull();
    expect(screen.queryByText(/mapped|Light good|Steady|Level/)).toBeNull();
    expect(screen.queryByText("Use photos")).toBeNull();
    expect(screen.queryByText("Done")).toBeNull();
    expect(screen.queryByRole("button", { name: "Torch" })).toBeNull();
    // Only the way out is a button until Done is ready.
    expect(screen.getAllByRole("button").map((b) => b.props.accessibilityLabel)).toEqual(["Close"]);
  });

  it("moves from the room to the corners, then offers Done", async () => {
    const view = await render(ui());
    mockScan.share = 0.6;
    await view.rerender(ui());
    expect(screen.getByText("Get the corners")).toBeTruthy();
    mockScan.share = 0.8;
    mockScan.ready = true;
    await view.rerender(ui());
    expect(screen.getByText("Looking good. Keep going, or tap Done")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Done" })).toBeTruthy();
  });

  it("does not finish before there is enough", async () => {
    mockScan.share = 0.4;
    await render(ui());
    await fireEvent.press(screen.getByTestId("scan-done"));
    expect(handlers.onDone).not.toHaveBeenCalled();
  });

  it("shows a nudge from the scan in place of the steady instruction", async () => {
    mockScan.hint = { id: "walkAround", kind: "sofa" };
    await render(ui());
    expect(screen.getByText("Walk around the sofa")).toBeTruthy();
    expect(screen.queryByText("Move slowly around the room")).toBeNull();
    expect(screen.queryByRole("button", { name: "Keep going" })).toBeNull();
  });

  it("when it is too dark: says so, offers the torch and a way to keep going", async () => {
    mockScan.state = {
      ...INITIAL_SCAN,
      pause: { ...INITIAL_SCAN.pause, paused: true, reason: "light" },
    };
    await render(ui());
    expect(screen.getByText("It's a bit dark. Switch on a light")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Keep going" }));
    expect(mockScan.scanAnyway).toHaveBeenCalledTimes(1);
    await fireEvent.press(screen.getByRole("button", { name: "Use the torch" }));
    // The torch is on: its switch shows, and the offer goes away.
    expect(screen.getByRole("button", { name: "Torch" }).props.accessibilityState).toEqual({
      selected: true,
    });
    expect(screen.queryByRole("button", { name: "Use the torch" })).toBeNull();
  });

  it("ticks once for each tenth of coverage, and once when Done is ready", async () => {
    const view = await render(ui());
    for (const share of [0.05, 0.12, 0.18, 0.31, 0.31]) {
      mockScan.share = share;
      await view.rerender(ui());
    }
    expect(mockHaptic.mock.calls.filter(([m]) => m === "cornerCaptured")).toHaveLength(2);
    expect(mockHaptic).not.toHaveBeenCalledWith("levelReached");
    mockScan.ready = true;
    await view.rerender(ui());
    await view.rerender(ui());
    expect(mockHaptic.mock.calls.filter(([m]) => m === "levelReached")).toHaveLength(1);
  });
});

describe("the debug flag", () => {
  it("three taps bring back the chips, the map and the mesh in a preview build", async () => {
    await render(ui());
    await act(tripleTap);
    expect(screen.getByTestId("scan-debug-layer")).toBeTruthy();
    expect(mockArProps.current.overlay).toBe(true);
    expect(screen.getByText("0% mapped")).toBeTruthy();
    expect(screen.getByText("Light good")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Torch" })).toBeTruthy();
    // The scan itself stays as it was.
    expect(screen.getByText("Move slowly around the room")).toBeTruthy();
  });

  it("cannot be switched on in the store build", async () => {
    mockPreview = false;
    await render(ui());
    await act(tripleTap);
    expect(screen.queryByTestId("scan-debug-layer")).toBeNull();
    expect(screen.queryByTestId("scan-mesh")).toBeNull();
  });
});

describe("review before upload", () => {
  const openReview = async (share = 0.8) => {
    mockScan.share = share;
    mockScan.ready = true;
    const view = await render(ui());
    await fireEvent.press(screen.getByRole("button", { name: "Done" }));
    return view;
  };

  it("Done opens the review; nothing is finished or handed on yet", async () => {
    await openReview();
    expect(screen.getByTestId("scan-review")).toBeTruthy();
    expect(screen.getByRole("header", { name: "We got your room" })).toBeTruthy();
    expect(screen.getByText("80% of your room is in")).toBeTruthy();
    expect(screen.getByText("Nothing. Every side is in.")).toBeTruthy();
    expect(screen.getByText("We'll measure it from your scan")).toBeTruthy();
    // The scan's own controls step aside while the review is open.
    expect(screen.queryByTestId("scan-instruction")).toBeNull();
    expect(screen.queryByTestId("scan-done")).toBeNull();
    expect(mockFinish).not.toHaveBeenCalled();
    expect(handlers.onCaptured).not.toHaveBeenCalled();
    expect(handlers.onDone).not.toHaveBeenCalled();
    expect(mockHaptic).not.toHaveBeenCalledWith("roomVerified");
  });

  it("Looks good finishes the scan and hands the capture on, once", async () => {
    await openReview();
    await fireEvent.press(screen.getByRole("button", { name: "Looks good" }));
    expect(mockHaptic).toHaveBeenCalledWith("roomVerified");
    expect(mockFinish).toHaveBeenCalledTimes(1);
    expect(handlers.onCaptured).toHaveBeenCalledTimes(1);
    expect(handlers.onCaptured).toHaveBeenCalledWith(
      expect.objectContaining({ captureId: "capture-1" }),
      { platform: "ios", tier: "standard", has_ar: true },
    );
    expect(handlers.onDone).toHaveBeenCalledTimes(1);
    // Both buttons are off while it finishes, so a second tap does nothing.
    expect(
      screen.getByRole("button", { name: "Looks good" }).props.accessibilityState.disabled,
    ).toBe(true);
  });

  it("keeps what the camera sees during the review out of the package", async () => {
    const send = (event: string, nativeEvent: object) =>
      act(async () => {
        (mockArProps.current[event] as (e: { nativeEvent: object }) => void)({ nativeEvent });
      });
    const keyframe = (uri: string) => send("onArKeyframe", { uri, sharpness: 1, depth: false });
    const pose = () => send("onArPose", { x: 0, y: 0, z: 0, yaw: 0, pitch: 0, tracking: "normal" });
    const detections = () =>
      send("onArDetections", { detections: [{ detectorClass: "couch", score: 0.9 }] });

    mockScan.share = 0.8;
    mockScan.ready = true;
    await render(ui());
    // During the scan everything is recorded.
    await keyframe("file:///k1.jpg");
    await pose();
    await detections();
    expect(mockRecorder.onKeyframe).toHaveBeenCalledTimes(1);
    expect(mockRecorder.onSensor).toHaveBeenCalledTimes(1);
    expect(mockRecorder.onDetections).toHaveBeenCalledTimes(1);

    // With the review open, frames are deleted and nothing is recorded.
    await fireEvent.press(screen.getByRole("button", { name: "Done" }));
    await keyframe("file:///k2.jpg");
    await pose();
    await detections();
    expect(mockRecorder.onKeyframe).toHaveBeenCalledTimes(1);
    expect(mockRecorder.onSensor).toHaveBeenCalledTimes(1);
    expect(mockRecorder.onDetections).toHaveBeenCalledTimes(1);
    expect(mockRecorder.discardKeyframes).toHaveBeenCalledWith(["file:///k2.jpg"]);
    // The recorder is told, so it pauses the native view and notes the window.
    expect(mockRecorder.setReviewOpen.mock.calls).toEqual([[true]]);

    // Back in the scan, recording carries on.
    await fireEvent.press(screen.getByRole("button", { name: "Scan a bit more" }));
    await keyframe("file:///k3.jpg");
    expect(mockRecorder.setReviewOpen.mock.calls).toEqual([[true], [false]]);
    expect(mockRecorder.onKeyframe).toHaveBeenCalledTimes(2);
    expect(mockRecorder.discardKeyframes).toHaveBeenCalledTimes(1);
  });

  it("calls out what is missing and a rough size, in the chosen units", async () => {
    const wall = (normalYaw: number, offset: number, covered: boolean) => ({
      normalYaw,
      offset,
      minAlong: 0,
      maxAlong: 5,
      cells: covered
        ? Object.fromEntries(
            Array.from({ length: 24 }, (_, i) => [`${i % 6},${Math.floor(i / 6)}`, 5]),
          )
        : {},
    });
    mockScan.state = {
      ...INITIAL_SCAN,
      surfacesSeen: true,
      surfaces: {
        ...INITIAL_SCAN.surfaces,
        walls: [
          wall(0, -2.06, true),
          wall(180, -2.06, true),
          wall(90, -1.2, false),
          wall(270, -2.18, false),
        ],
      },
    };
    await openReview(0.72);
    expect(screen.getByRole("header", { name: "Nearly there" })).toBeTruthy();
    expect(screen.getByText("One or more walls")).toBeTruthy();
    expect(screen.getByText("The floor")).toBeTruthy();
    // Feet and inches unless centimetres are chosen in settings.
    expect(screen.getByText("About 13 ft 5 in by 11 ft 2 in")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Rescan this part" })).toBeTruthy();
  });

  it("Rescan this part returns to the same scan and points at the missing part", async () => {
    jest.useFakeTimers();
    try {
      mockScan.state = { ...INITIAL_SCAN, surfacesSeen: true };
      await openReview(0.72);
      await fireEvent.press(screen.getByRole("button", { name: "Rescan this part" }));
      expect(screen.queryByTestId("scan-review")).toBeNull();
      expect(screen.getByText("Show the walls you missed")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Done" })).toBeTruthy();
      expect(handlers.onDone).not.toHaveBeenCalled();
      // The pointer goes away by itself and the usual instruction returns.
      await act(async () => {
        jest.advanceTimersByTime(RESCAN_NUDGE_MS + 1);
      });
      expect(screen.queryByText("Show the walls you missed")).toBeNull();
      expect(screen.getByText("Looking good. Keep going, or tap Done")).toBeTruthy();
    } finally {
      jest.useRealTimers();
    }
  });

  it("shows the mesh for a moment on the review, and not during the scan", async () => {
    mockScan.share = 0.8;
    mockScan.ready = true;
    await render(ui());
    expect(mockArProps.current.overlay).toBe(false);
    await fireEvent.press(screen.getByRole("button", { name: "Done" }));
    expect(mockArProps.current.overlay).toBe(true);
    await fireEvent.press(screen.getByRole("button", { name: "Scan a bit more" }));
    expect(mockArProps.current.overlay).toBe(false);
  });

  it("Finish anyway opens the review, which names what the meter still wanted", async () => {
    mockScan.meter = true;
    mockScan.stuck = true;
    mockScan.share = 0.5;
    await render(ui());
    await fireEvent.press(screen.getByRole("button", { name: "Finish anyway" }));
    expect(screen.getByRole("header", { name: "Nearly there" })).toBeTruthy();
    // A scan that has barely started is missing the walk and the turn in the middle.
    expect(screen.getByText("The far side of the room")).toBeTruthy();
    expect(screen.getByText("The middle of the room")).toBeTruthy();
    expect(mockFinish).not.toHaveBeenCalled();
    expect(handlers.onDone).not.toHaveBeenCalled();
  });
});
describe("the coverage meter in the calm scan", () => {
  it("says the meter's next step as the one instruction, with no map", async () => {
    mockScan.meter = true;
    mockScan.hint = { id: "standMiddle" };
    await render(ui());
    expect(screen.getByText("Now stand in the middle and turn slowly")).toBeTruthy();
    expect(screen.getAllByTestId("scan-instruction")).toHaveLength(1);
    expect(screen.queryByTestId("scan-meter-map")).toBeNull();
  });

  it("shows the map only for the step that needs a place to point at", async () => {
    mockScan.meter = true;
    mockScan.hint = { id: "oneMoreSpot" };
    await render(ui());
    expect(screen.getByText("One more spot, over there")).toBeTruthy();
    expect(screen.getByTestId("scan-meter-map")).toBeTruthy();
  });

  it("leaves the ticks to the meter, which is felt sector by sector", async () => {
    mockScan.meter = true;
    const view = await render(ui());
    for (const share of [0.12, 0.31, 0.55]) {
      mockScan.share = share;
      await view.rerender(ui());
    }
    expect(mockHaptic).not.toHaveBeenCalledWith("cornerCaptured");
  });

  it("offers Finish anyway only when coverage has stopped moving, and not once Done is ready", async () => {
    const view = await render(ui());
    expect(screen.queryByRole("button", { name: "Finish anyway" })).toBeNull();
    mockScan.stuck = true;
    await view.rerender(ui());
    expect(screen.getByRole("button", { name: "Finish anyway" })).toBeTruthy();
    mockScan.ready = true;
    await view.rerender(ui());
    expect(screen.queryByRole("button", { name: "Finish anyway" })).toBeNull();
  });
});

describe("a phone that cannot run AR", () => {
  it("gets the friendly note and photos, not a scan", async () => {
    mockAr = false;
    await render(ui());
    expect(screen.getByText("This phone can't measure a room by scanning")).toBeTruthy();
    expect(screen.queryByTestId("scan-instruction")).toBeNull();
    expect(screen.queryByTestId("scan-done")).toBeNull();
  });
});
