import { previewScreensEnabled } from "./preview-screens";

describe("gallery and screen previews", () => {
  it("show in development", () => {
    expect(previewScreensEnabled(true, undefined)).toBe(true);
  });

  it("show in preview builds for testers", () => {
    expect(previewScreensEnabled(false, "preview")).toBe(true);
  });

  it("never show in the store build", () => {
    expect(previewScreensEnabled(false, "production")).toBe(false);
    expect(previewScreensEnabled(false, undefined)).toBe(false);
  });
});
