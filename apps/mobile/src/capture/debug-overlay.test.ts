import { scanDebugLines } from "./debug-overlay";
import { INITIAL_SCAN } from "./scan-session";
import type { ArDebug, ScanDebug } from "./use-scan-session";

const AR: ArDebug = {
  tracking: "normal",
  lidar: false,
  planes: 0,
  meshTriangles: 0,
  mappedPoints: 0,
  detector: false,
  labels: 0,
  featurePoints: 0,
  detectionsFound: 0,
  detectionsPlaced: 0,
  placedBy: "",
  detectorStatus: "",
  cameraImage: "",
  session: "",
  planeStates: "",
  surfaceHits: "",
  errors: "",
  lastError: "",
  video: "",
  detectorError: "",
  labelsRejected: 0,
};

const DEBUG: ScanDebug = {
  cameraFps: 30,
  analysedFps: 8,
  featurePoints: 0,
  analysisMs: 0,
  waitingSeconds: 0,
  diagnostics: { dropped: 0, lastError: null },
  ar: AR,
};

const line = (lines: [string, string][], key: string) => lines.find(([k]) => k === key)?.[1];

describe("scan debug overlay", () => {
  it("shows the detector's whole error text, not a shortened one", () => {
    const error =
      "error: RuntimeException: Field baseOptions_ for a.b.C not found. Known fields are " +
      "[a, b, c, d, e, f, g, h, i, j, k, l, m, n, o, p, q, r, s, t, u, v, w, x, y, z] | at a.b.c:12";
    const lines = scanDebugLines({ ...DEBUG, ar: { ...AR, detectorStatus: error } }, INITIAL_SCAN);
    expect(line(lines, "detectorStatus")).toBe(error);
  });

  it("shows the session configuration and every plane state", () => {
    const lines = scanDebugLines(
      {
        ...DEBUG,
        ar: {
          ...AR,
          session: "planes HORIZONTAL_AND_VERTICAL, depth RAW_DEPTH_ONLY",
          planeStates: "tracking 0 paused 0 stopped 0 merged 0 of 0",
        },
      },
      INITIAL_SCAN,
    );
    expect(line(lines, "session")).toBe("planes HORIZONTAL_AND_VERTICAL, depth RAW_DEPTH_ONLY");
    expect(line(lines, "planeStates")).toBe("tracking 0 paused 0 stopped 0 merged 0 of 0");
  });

  it("shows why AR could not start only when it could not", () => {
    expect(line(scanDebugLines(DEBUG, INITIAL_SCAN), "arStart")).toBeUndefined();
    const lines = scanDebugLines(DEBUG, INITIAL_SCAN, "UnavailableArcoreNotInstalledException");
    expect(line(lines, "arStart")).toBe("UnavailableArcoreNotInstalledException");
  });
});
