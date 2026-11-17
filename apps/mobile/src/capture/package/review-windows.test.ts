import { addNativeKeyframe } from "./native-capture";
import {
  buildPackage,
  inReview,
  MAX_REVIEW_WINDOWS,
  record,
  reviewWindowsOf,
  startRecording,
} from "./recorder";

const AR = { tracking: "arcore", lidar: false, depth: false } as const;

const keyframe = (uri: string, yaw: number) => ({
  uri,
  sharpness: 30,
  yaw,
  pitch: 0,
  depth: false,
  tracking: true,
  pose: {
    position: { x_m: 0, y_m: 1.4, z_m: 0 },
    rotation: [0, 0, 0, 1] as [number, number, number, number],
  },
  intrinsics: { fx: 1400, fy: 1400, cx: 960, cy: 540, width_px: 1920, height_px: 1080 },
});

describe("review windows", () => {
  it("records when the review opened and closed, from the start of the capture", () => {
    let state = startRecording(1_000, AR);
    state = record(state, { type: "review", open: true, atMs: 42_200 });
    expect(inReview(state)).toBe(true);
    state = record(state, { type: "review", open: false, atMs: 53_900 });
    expect(inReview(state)).toBe(false);
    expect(reviewWindowsOf(state)).toEqual([{ start_ms: 41_200, end_ms: 52_900 }]);
  });

  it("keeps nothing seen while the review is open", () => {
    let state = startRecording(0, AR);
    state = addNativeKeyframe(state, keyframe("file:///kf-1.jpg", 0), 500).state;
    state = record(state, { type: "review", open: true, atMs: 10_000 });

    const during = addNativeKeyframe(state, keyframe("file:///kf-2.jpg", 90), 12_000);
    expect(during.state).toBe(state);
    // The file is deleted at once: the phone was pointing at the floor.
    expect(during.discard).toEqual(["file:///kf-2.jpg"]);
    const logged = record(state, {
      type: "sensor",
      atMs: 12_100,
      reading: { source: "imu", gyro_alpha: 1 },
    });
    expect(logged.sensorLog).toHaveLength(0);
    const seen = record(state, {
      type: "detections",
      atMs: 12_200,
      detections: [{ detectorClass: "couch", score: 0.9, world: null }],
    });
    expect(seen.detections).toHaveLength(0);

    state = record(state, { type: "review", open: false, atMs: 20_000 });
    const after = addNativeKeyframe(state, keyframe("file:///kf-3.jpg", 90), 21_000);
    expect(after.state.keyframes.size).toBe(2);
  });

  it("puts the windows and the video's start into the package", () => {
    let state = startRecording(0, AR);
    state = record(state, { type: "videoStart", atMs: 640 });
    state = record(state, { type: "videoStart", atMs: 9_000 }); // only the first counts
    state = addNativeKeyframe(state, keyframe("file:///kf-1.jpg", 0), 500).state;
    state = record(state, { type: "review", open: true, atMs: 41_200 });
    state = record(state, { type: "review", open: false, atMs: 52_900 });

    const built = buildPackage(state, {
      keyframes: { k1: "user/k1.jpg" },
      sensorLog: "user/log.jsonl",
      video: "user/scan.mp4",
    });
    expect(built.video_start_ms).toBe(640);
    expect(built.review_windows).toEqual([{ start_ms: 41_200, end_ms: 52_900 }]);

    const noVideo = buildPackage(state, {
      keyframes: { k1: "user/k1.jpg" },
      sensorLog: "user/log.jsonl",
    });
    expect(noVideo.video_start_ms).toBeUndefined();
    expect(noVideo.review_windows).toHaveLength(1);
  });

  it("a scan with no review has no windows in its package", () => {
    let state = startRecording(0, AR);
    state = addNativeKeyframe(state, keyframe("file:///kf-1.jpg", 0), 500).state;
    const built = buildPackage(state, { keyframes: { k1: "k" }, sensorLog: "s" });
    expect(built.review_windows).toBeUndefined();
  });

  it("a review still open at the end runs to the end of the capture", () => {
    let state = startRecording(0, AR);
    state = record(state, { type: "review", open: true, atMs: 30_000 });
    expect(reviewWindowsOf(state, 36_500)).toEqual([{ start_ms: 30_000, end_ms: 36_500 }]);
  });

  it("opening twice or closing when not open changes nothing, and windows are capped", () => {
    let state = startRecording(0, AR);
    expect(record(state, { type: "review", open: false, atMs: 5 })).toBe(state);
    state = record(state, { type: "review", open: true, atMs: 100 });
    expect(record(state, { type: "review", open: true, atMs: 200 })).toBe(state);
    state = record(state, { type: "review", open: false, atMs: 300 });
    for (let i = 0; i < MAX_REVIEW_WINDOWS + 5; i += 1) {
      state = record(state, { type: "review", open: true, atMs: 1000 + i * 10 });
      state = record(state, { type: "review", open: false, atMs: 1005 + i * 10 });
    }
    expect(reviewWindowsOf(state)).toHaveLength(MAX_REVIEW_WINDOWS);
  });
});
