import { ThemeProvider } from "@sajao/ui";
import { act, fireEvent, render, screen } from "@testing-library/react-native";
import type { Hint } from "@/capture/ar/guidance";
import { INITIAL_SCAN, type ScanState } from "@/capture/scan-session";
import "@/i18n";
import { CaptureScreen } from "@/screens/capture";

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
  hint: null as Hint,
  state: INITIAL_SCAN as ScanState,
  scanAnyway: jest.fn(),
};
jest.mock("@/capture/scan-session", () => ({
  ...jest.requireActual("@/capture/scan-session"),
  mappedShare: () => mockScan.share,
  canFinish: () => mockScan.ready,
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

const handlers = { onClose: jest.fn(), onDone: jest.fn(), onUsePhotos: jest.fn() };
const ui = () => (
  <ThemeProvider tier="standard" reducedMotion>
    <CaptureScreen {...handlers} />
  </ThemeProvider>
);

beforeEach(() => {
  jest.clearAllMocks();
  mockPreview = true;
  Object.assign(mockScan, { share: 0, ready: false, hint: null, state: INITIAL_SCAN });
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
    await fireEvent.press(screen.getByRole("button", { name: "Done" }));
    expect(mockHaptic).toHaveBeenCalledWith("roomVerified");
    expect(handlers.onDone).toHaveBeenCalledTimes(1);
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
    expect(screen.getByTestId("scan-mesh")).toBeTruthy();
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
