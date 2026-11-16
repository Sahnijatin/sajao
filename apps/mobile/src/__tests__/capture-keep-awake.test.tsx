import { ThemeProvider } from "@sajao/ui";
import { render } from "@testing-library/react-native";
import { useKeepAwake } from "expo-keep-awake";
import { CaptureScreen, SCAN_KEEP_AWAKE_TAG } from "@/screens/capture";

jest.mock("expo-keep-awake", () => ({ useKeepAwake: jest.fn() }));
jest.mock("react-native-vision-camera", () => ({
  useCameraPermission: () => ({
    hasPermission: false,
    canRequestPermission: true,
    requestPermission: jest.fn(),
  }),
}));
jest.mock("@/capture/scan-camera", () => ({ ScanCamera: () => null }));
// Skia ships ESM that Jest does not load; this test needs no drawing.
jest.mock("@sajao/ui/effects", () => ({ MeshEffect: () => null }));
jest.mock("@sajao/ui/icons", () => ({ Icon: () => null }));
jest.mock("@/capture/mini-map", () => ({ MiniMap: () => null }));
jest.mock(
  "react-native-safe-area-context",
  () => jest.requireActual("react-native-safe-area-context/jest/mock").default,
);
jest.mock("expo-sensors", () => ({
  DeviceMotion: { setUpdateInterval: jest.fn(), addListener: () => ({ remove: jest.fn() }) },
}));

describe("scan screen", () => {
  it("keeps the screen awake while it is open", async () => {
    await render(
      <ThemeProvider tier="standard" reducedMotion>
        <CaptureScreen onClose={jest.fn()} onDone={jest.fn()} onUsePhotos={jest.fn()} />
      </ThemeProvider>,
    );
    expect(useKeepAwake).toHaveBeenCalledWith(SCAN_KEEP_AWAKE_TAG);
  });
});
