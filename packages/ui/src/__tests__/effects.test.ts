import {
  blobAt,
  canvasBlobs,
  effectLevel,
  glow,
  isAnimated,
  paintSweepAt,
  paintSweepDurationMs,
  perspectiveGrid,
  scanMesh,
  scanMeshLayers,
} from "../effects/presets";

describe("effect level", () => {
  it("is full on standard phones, lite on the low tier, still with reduced motion", () => {
    expect(effectLevel({ tier: "standard", reducedMotion: false })).toBe("full");
    expect(effectLevel({ tier: "low", reducedMotion: false })).toBe("lite");
    expect(effectLevel({ tier: "standard", reducedMotion: true })).toBe("still");
    // The low tier wins: it is already the lighter, motionless version.
    expect(effectLevel({ tier: "low", reducedMotion: true })).toBe("lite");
  });

  it("only the full level moves on its own", () => {
    expect(["full", "lite", "still"].map((level) => isAnimated(level as never))).toEqual([
      true,
      false,
      false,
    ]);
  });
});

describe("scan mesh preset", () => {
  it("matches the mockup", () => {
    expect(scanMesh.edge).toEqual({ color: "#8ff0ff", width: 0.9, opacity: 0.55 });
    expect(scanMesh.point).toMatchObject({ color: "#e9fdff", opacity: 0.9, radius: 1.6 });
    expect(scanMesh.face.color).toBe("#5ee0ff");
    expect(scanMesh.glowBlurRadius).toBe(2.2);
    expect(glow.blurRadius).toBe(2.2);
  });

  it("draws the full mesh on standard phones", () => {
    expect(scanMeshLayers("full")).toEqual({
      faces: true,
      glow: true,
      sweep: true,
      edges: true,
      points: true,
    });
  });

  it("draws dots and edges only on low-tier phones", () => {
    expect(scanMeshLayers("lite")).toEqual({
      faces: false,
      glow: false,
      sweep: false,
      edges: true,
      points: true,
    });
  });

  it("keeps the look but drops the moving sweep with reduced motion", () => {
    expect(scanMeshLayers("still")).toMatchObject({ faces: true, glow: true, sweep: false });
  });
});

describe("canvas colour blobs", () => {
  const size = { width: 390, height: 844 };

  it("are terracotta, amber and wood: warm light on an ivory wall", () => {
    expect(canvasBlobs.map((blob) => blob.color)).toEqual([
      "rgba(173, 79, 39, 0.12)",
      "rgba(232, 178, 96, 0.20)",
      "rgba(176, 137, 104, 0.14)",
    ]);
  });

  it("drift in a closed loop: the end of the loop is its start", () => {
    for (const blob of canvasBlobs) {
      const start = blobAt(blob, 0, size);
      const end = blobAt(blob, 1, size);
      expect(end.cx).toBeCloseTo(start.cx, 6);
      expect(end.cy).toBeCloseTo(start.cy, 6);
    }
  });

  it("never drift further than their drift distance from rest", () => {
    for (const blob of canvasBlobs) {
      for (let step = 0; step <= 20; step += 1) {
        const at = blobAt(blob, step / 20, size);
        const distance = Math.hypot(at.cx - blob.x * size.width, at.cy - blob.y * size.height);
        expect(distance).toBeLessThanOrEqual(blob.drift * size.width + 1e-6);
      }
    }
  });

  it("do not move in step with each other", () => {
    expect(new Set(canvasBlobs.map((blob) => blob.phase)).size).toBe(canvasBlobs.length);
  });
});

describe("perspective grid", () => {
  const grid = perspectiveGrid({ width: 390, height: 844, horizonY: 520, columns: 8, rows: 5 });
  const fan = grid.slice(0, 9);
  const cross = grid.slice(9);

  it("has one line per column edge and one per row", () => {
    expect(fan).toHaveLength(9);
    expect(cross).toHaveLength(5);
  });

  it("fans out: lines are closer together at the horizon than at the near edge", () => {
    const farSpan = fan[8]!.x1 - fan[0]!.x1;
    const nearSpan = fan[8]!.x2 - fan[0]!.x2;
    expect(nearSpan).toBeGreaterThan(farSpan);
    expect(fan.every((line) => line.y1 === 520 && line.y2 === 844)).toBe(true);
  });

  it("bunches cross lines toward the horizon", () => {
    const ys = cross.map((line) => line.y1);
    const gaps = ys.slice(1).map((y, index) => y - ys[index]!);
    expect(gaps).toEqual([...gaps].sort((a, b) => a - b));
    expect(ys.at(-1)).toBe(844);
  });
});

describe("paint sweep", () => {
  const wall = { x: 40, width: 300 };

  it("covers the wall from left to right", () => {
    expect(paintSweepAt(0, wall)).toEqual({ x: 40, width: 0, edgeX: 40 });
    expect(paintSweepAt(0.5, wall)).toEqual({ x: 40, width: 150, edgeX: 190 });
    expect(paintSweepAt(1, wall)).toEqual({ x: 40, width: 300, edgeX: 340 });
  });

  it("never paints outside the wall", () => {
    expect(paintSweepAt(-1, wall).width).toBe(0);
    expect(paintSweepAt(3, wall).width).toBe(300);
  });

  it("is an instant change on the low tier and with reduced motion", () => {
    expect(paintSweepDurationMs("full")).toBe(600);
    expect(paintSweepDurationMs("lite")).toBe(0);
    expect(paintSweepDurationMs("still")).toBe(0);
  });
});
