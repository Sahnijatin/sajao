// The camera's frame callback is created inside a component, so it is
// captured from a render with the camera library stubbed out, then checked
// like the other camera thread worklets.
import { render } from "@testing-library/react-native";
import { isWorklet, unsafeReferences } from "@/test-utils/isolated-worklet";
import { ScanCamera } from "./scan-camera";

const mockCaptured: { onFrame?: unknown } = {};

jest.mock("react-native-vision-camera", () => ({
  Camera: () => null,
  useCameraDevice: () => null,
  useFrameOutput: (options: { onFrame: unknown }) => {
    mockCaptured.onFrame = options.onFrame;
    return {};
  },
}));

describe("the camera's frame callback", () => {
  it("is a worklet that reads only captured values and runtime built-ins", async () => {
    await render(<ScanCamera active torch={false} onAnalysed={() => {}} />);
    expect(isWorklet(mockCaptured.onFrame)).toBe(true);
    expect(unsafeReferences(mockCaptured.onFrame)).toEqual([]);
  });
});
