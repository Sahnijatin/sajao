import { ThemeProvider } from "@sajao/ui";
import { act, renderHook } from "@testing-library/react-native";
import type { ReactNode } from "react";
import { useScanSession } from "./use-scan-session";

jest.mock("expo-sensors", () => ({
  DeviceMotion: { setUpdateInterval: jest.fn(), addListener: () => ({ remove: jest.fn() }) },
}));

const wrapper = ({ children }: { children: ReactNode }) => (
  <ThemeProvider tier="standard" reducedMotion>
    {children}
  </ThemeProvider>
);

const status = (frames: number, detectorRuns: number) => ({
  tracking: "normal" as const,
  lidar: false,
  planes: 2,
  meshTriangles: 0,
  featurePoints: 140,
  mappedPoints: 900,
  brightness: 120,
  ambientIntensity: 900,
  detector: true,
  labels: 1,
  frames,
  detectorRuns,
  detectorSkipped: 0,
  detectorMs: 38,
});

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

describe("scan debug numbers during the AR scan", () => {
  // The founder's overlay showed camera 0 fps, analysed 0 fps and "waiting
  // for frames" for the whole AR scan: it counted the 2D camera, which never
  // runs while ARKit or ARCore owns the camera.
  it("reports AR camera frames and a steady detector rate, not waiting", async () => {
    const { result } = await renderHook(() => useScanSession(true), { wrapper });
    // Four seconds: the AR view reports 60 camera frames and 8 detector runs a second.
    for (let second = 1; second <= 4; second += 1) {
      await act(async () => {
        result.current.onArStatus(status(second * 60, second * 8));
        jest.advanceTimersByTime(1000);
      });
    }
    const { debug } = result.current;
    expect(debug.cameraFps).toBe(60);
    expect(debug.analysedFps).toBeGreaterThanOrEqual(5);
    expect(debug.analysedFps).toBeLessThanOrEqual(10);
    expect(debug.analysisMs).toBe(38);
    expect(debug.waitingSeconds).toBe(0);
    expect(debug.ar?.tracking).toBe("normal");
  });

  it("says it is waiting when the AR view sends no frames", async () => {
    const { result } = await renderHook(() => useScanSession(true), { wrapper });
    await act(async () => {
      result.current.onArStatus(status(0, 0));
      jest.advanceTimersByTime(3000);
    });
    expect(result.current.debug.cameraFps).toBe(0);
    expect(result.current.debug.waitingSeconds).toBeGreaterThan(0);
  });
});
