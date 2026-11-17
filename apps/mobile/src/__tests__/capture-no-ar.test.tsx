import { ThemeProvider } from "@sajao/ui";
import { fireEvent, render } from "@testing-library/react-native";
import { CaptureScreen } from "@/screens/capture";

jest.mock("../../modules/sajao-ar", () => ({
  // A phone without ARCore: the module is there, AR is not supported.
  getArCapabilities: () => ({
    platform: "android",
    arSupported: false,
    lidar: false,
    depth: false,
  }),
  getArView: () => null,
}));
jest.mock("expo-keep-awake", () => ({ useKeepAwake: jest.fn() }));
jest.mock("react-native-vision-camera", () => ({
  useCameraPermission: () => ({
    hasPermission: false,
    canRequestPermission: true,
    requestPermission: jest.fn(),
  }),
}));
jest.mock("@/capture/scan-camera", () => ({ ScanCamera: () => null }));
jest.mock("@sajao/ui/effects", () => ({ MeshEffect: () => null }));
jest.mock("@sajao/ui/icons", () => ({ Icon: () => null }));
jest.mock("@/capture/mini-map", () => ({ MiniMap: () => null }));
jest.mock("@/capture/progress-ring", () => ({ ProgressRing: () => null }));
jest.mock("@/capture/meter-map", () => ({ MeterMap: () => null }));
jest.mock("@/components/scan-ring", () => ({ ScanRing: () => null }));
jest.mock(
  "react-native-safe-area-context",
  () => jest.requireActual("react-native-safe-area-context/jest/mock").default,
);
jest.mock("expo-sensors", () => ({
  DeviceMotion: { setUpdateInterval: jest.fn(), addListener: () => ({ remove: jest.fn() }) },
}));

async function open(onUsePhotos = jest.fn(), onClose = jest.fn()) {
  return render(
    <ThemeProvider tier="low" reducedMotion>
      <CaptureScreen onClose={onClose} onDone={jest.fn()} onUsePhotos={onUsePhotos} />
    </ThemeProvider>,
  );
}

describe("a phone without AR", () => {
  it("sees a friendly note and goes to photos, never the scan or a permission request", async () => {
    const onUsePhotos = jest.fn();
    const screen = await open(onUsePhotos);
    expect(screen.getByTestId("no-ar-notice")).toBeTruthy();
    expect(screen.getByText("capture.noAr.title")).toBeTruthy();
    expect(screen.queryByTestId("scan-camera-area")).toBeNull();
    expect(screen.queryByText("capture.permissionAllow")).toBeNull();
    fireEvent.press(screen.getByText("capture.usePhotos"));
    expect(onUsePhotos).toHaveBeenCalledTimes(1);
  });

  it("can be closed", async () => {
    const onClose = jest.fn();
    const screen = await open(jest.fn(), onClose);
    fireEvent.press(screen.getByText("capture.close"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
