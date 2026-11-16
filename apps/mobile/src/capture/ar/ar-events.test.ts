import { arFrameEvent, arPoseEvent, IOS_LOW_LIGHT_LUMENS, trackingOf } from "./ar-events";

const status = { tracking: "normal", brightness: 120, ambientIntensity: 900, featurePoints: 55 };

describe("AR events", () => {
  it("reads low light from the iOS light estimate only", () => {
    const dim = { ...status, ambientIntensity: IOS_LOW_LIGHT_LUMENS - 1 };
    expect(arFrameEvent(dim, "ios", 1).lowLight).toBe(true);
    expect(arFrameEvent(status, "ios", 1).lowLight).toBe(false);
    expect(arFrameEvent(dim, "android", 1).lowLight).toBe(false);
  });

  it("passes brightness and feature points through, and survives bad numbers", () => {
    expect(arFrameEvent(status, "ios", 5)).toMatchObject({
      brightness: 120,
      featureCount: 55,
      atMs: 5,
    });
    expect(arFrameEvent({ ...status, brightness: Number.NaN }, "ios", 5).brightness).toBe(128);
  });

  it("maps tracking names and treats unknown ones as no AR", () => {
    expect(trackingOf("limited")).toBe("limited");
    expect(trackingOf("weird")).toBe("none");
    expect(arPoseEvent({ yaw: 10, pitch: -5, tracking: "normal" }, 7)).toEqual({
      type: "arPose",
      yaw: 10,
      pitch: -5,
      tracking: "normal",
      atMs: 7,
    });
  });
});
