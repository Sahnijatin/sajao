import { act, renderHook } from "@testing-library/react-native";
import type { ArKeyframeEvent, SajaoArViewRef } from "../../../modules/sajao-ar";
import { useCaptureStore } from "@/state/capture";
import { useCaptureRecorder } from "./use-capture-recorder";

const keyframe = (uri: string, yaw: number, sharpness: number): ArKeyframeEvent => ({
  uri,
  sharpness,
  yaw,
  pitch: 0,
  depth: true,
  pose: { position: { x_m: 0, y_m: 1.4, z_m: 0 }, rotation: [0, 0, 0, 1] },
  intrinsics: { fx: 1400, fy: 1400, cx: 960, cy: 720, width_px: 1920, height_px: 1440 },
});

function nativeView() {
  return {
    discardKeyframes: jest.fn(async () => undefined),
    finishCapture: jest.fn(async () => ({
      planes: "file:///planes.json",
      sceneMesh: null,
      depth: "file:///depth.sjdepth",
      video: "file:///scan.mp4" as string | null,
    })),
  } satisfies SajaoArViewRef;
}

let clock = 1_000_000;
beforeEach(() => {
  // Keyframes are ordered by capture time: give each its own millisecond.
  jest.spyOn(Date, "now").mockImplementation(() => (clock += 100));
});
afterEach(() => jest.restoreAllMocks());

describe("capture recorder hook", () => {
  it("deletes candidates the recorder drops and finishes with keyframes in package order", async () => {
    const { result } = await renderHook(() =>
      useCaptureRecorder({ tracking: "arcore", lidar: false, depth: false }),
    );
    const view = nativeView();
    result.current.viewRef.current = view;

    await act(async () => {
      result.current.onKeyframe(keyframe("file:///a.jpg", 10, 100));
      result.current.onKeyframe(keyframe("file:///b.jpg", 100, 100));
      // Sharper, same direction as a: a is dropped.
      result.current.onKeyframe(keyframe("file:///c.jpg", 12, 200));
      // Blurrier, same direction as b: c itself is dropped.
      result.current.onKeyframe(keyframe("file:///d.jpg", 101, 50));
    });
    expect(view.discardKeyframes.mock.calls).toEqual([[["file:///a.jpg"]], [["file:///d.jpg"]]]);

    let local;
    await act(async () => {
      local = await result.current.finish();
    });
    expect(view.finishCapture).toHaveBeenCalledWith(["file:///b.jpg", "file:///c.jpg"]);
    expect(local).toMatchObject({
      captureId: result.current.captureId,
      state: { ar: { tracking: "arcore", depth: true } },
      files: {
        keyframes: [
          { id: "k1", uri: "file:///b.jpg" },
          { id: "k2", uri: "file:///c.jpg" },
        ],
        depth: "file:///depth.sjdepth",
        planes: "file:///planes.json",
        video: "file:///scan.mp4",
      },
    });
    expect(useCaptureStore.getState().last).toBe(local);
  });

  it("still makes a local capture when the native view fails to finish", async () => {
    const { result } = await renderHook(() =>
      useCaptureRecorder({ tracking: "arkit", lidar: true, depth: false }),
    );
    const view = nativeView();
    view.finishCapture.mockRejectedValueOnce(new Error("gone"));
    result.current.viewRef.current = view;
    await act(async () => result.current.onKeyframe(keyframe("file:///a.jpg", 10, 100)));
    let local;
    await act(async () => {
      local = await result.current.finish();
    });
    expect(local).toMatchObject({ state: { ar: { depth: false } }, files: { depth: null } });
  });
});
