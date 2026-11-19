import { useCaptureStore } from "@/state/capture";
import {
  breadcrumb,
  breadcrumbs,
  clearBreadcrumbs,
  MAX_BREADCRUMBS,
  setBreadcrumbSink,
} from "./breadcrumbs";

beforeEach(() => clearBreadcrumbs());

describe("breadcrumbs", () => {
  it("keeps the trail in order, up to a limit, and hands each to the sink", () => {
    const sunk: string[] = [];
    setBreadcrumbSink((crumb) => sunk.push(crumb.message));
    for (let i = 0; i < MAX_BREADCRUMBS + 5; i += 1) breadcrumb("job", `step ${i}`, undefined, i);
    expect(breadcrumbs()).toHaveLength(MAX_BREADCRUMBS);
    expect(breadcrumbs()[0]?.message).toBe("step 5");
    expect(sunk).toHaveLength(MAX_BREADCRUMBS + 5);
    setBreadcrumbSink(null);
  });

  it("never throws when the sink does", () => {
    setBreadcrumbSink(() => {
      throw new Error("offline");
    });
    expect(() => breadcrumb("job", "x")).not.toThrow();
    setBreadcrumbSink(null);
  });

  it("records each change of a capture's upload, with its error", () => {
    useCaptureStore.getState().queueUpload("c1");
    useCaptureStore
      .getState()
      .setUpload({ state: "uploading", finished: 0, total: 2, captureId: "c1" });
    useCaptureStore
      .getState()
      .setUpload({ state: "failed", finished: 0, total: 0, captureId: "c1", error: "timeout" });
    expect(breadcrumbs().map((crumb) => crumb.message)).toEqual(["queued", "uploading", "failed"]);
    expect(breadcrumbs().at(-1)?.data).toMatchObject({ captureId: "c1", error: "timeout" });
  });
});
