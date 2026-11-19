import type { Design } from "@sajao/schemas";
import { validate } from "@sajao/schemas/validate";
import designFixture from "../../../../packages/schemas/fixtures/v1/valid/design.json";
import type { TasteAnswers } from "@/taste/taste-session";
import { type DesignIds, designsRequest, isDesign, readDesigns } from "./designs-api";

const IDS: DesignIds = {
  requestId: "00000000-0000-4000-8000-0000000000a1",
  briefId: "00000000-0000-4000-8000-0000000000a2",
  spaceProfileId: "00000000-0000-4000-8000-0000000000a3",
  tasteProfileId: "00000000-0000-4000-8000-0000000000a4",
  createdAt: "2026-01-05T10:00:00.000Z",
};

const answers = {
  budget: { limit: { currency: "INR", amount_minor: 15_000_000 }, flexibility: "stretch_10" },
  must_haves: ["sofa"],
  consider_vastu: true,
} as unknown as TasteAnswers;

const design = designFixture as unknown as Design;
const slots = (["best_value", "best_match", "bold"] as const).map((slot) => ({
  ...design,
  id: `d-${slot}`,
  slot,
}));
const job = (status: string, designs: unknown[] | null = null) => ({
  id: "j",
  status,
  stages: [],
  designs,
});

describe("the design request", () => {
  it("is a valid Brief from the budget, must-haves and Vastu given on this phone", () => {
    const request = designsRequest(answers, IDS);
    expect(request.id).toBe(IDS.requestId);
    expect(validate("Brief", request.brief).ok).toBe(true);
    expect(request.brief).toMatchObject({
      id: IDS.briefId,
      created_at: IDS.createdAt,
      intent: "full_makeover",
      budget: answers.budget,
      must_haves: ["sofa"],
      keep_item_ids: [],
      consider_vastu: true,
    });
    // Asking again sends the same request.
    expect(designsRequest(answers, IDS)).toEqual(request);
  });

  it("uses the room's own budget when it has one", () => {
    const budget = {
      limit: { currency: "INR", amount_minor: 5_000_000 },
      flexibility: "strict",
    } as const;
    const request = designsRequest(answers, IDS, budget);
    expect(request.brief.budget).toEqual(budget);
    expect(validate("Brief", request.brief).ok).toBe(true);
  });
});

describe("designs from the server", () => {
  it("accept a design with the parts the app reads", () => {
    expect(isDesign(design)).toBe(true);
  });

  it("refuse anything else", () => {
    const item = design.items[0];
    for (const bad of [
      null,
      "design",
      { ...design, slot: "cheapest" },
      { ...design, items: [] },
      { ...design, total_cost: { amount_minor: "lots" } },
      { ...design, check_report: undefined },
      { ...design, items: [{ ...item, product: { ...item?.product, price: null } }] },
      { ...design, items: [{ ...item, position: { x_m: 1 } }] },
    ]) {
      expect(isDesign(bad)).toBe(false);
    }
  });

  it("are ready only as one checked design per slot, in slot order", () => {
    expect(readDesigns(job("working"))).toEqual({ state: "working" });
    const ready = readDesigns(job("ready", [slots[2], slots[0], slots[1]]));
    expect(ready.state).toBe("ready");
    if (ready.state === "ready") {
      expect(ready.designs.map((each) => each.slot)).toEqual(["best_value", "best_match", "bold"]);
    }
    expect(readDesigns(job("ready", [slots[0], slots[0], slots[1]]))).toEqual({
      state: "failed",
      reason: "bad_designs",
    });
    expect(readDesigns(job("ready", null)).state).toBe("failed");
    expect(
      readDesigns({
        ...job("working"),
        stages: [{ stage: "design", status: "failed", detail: "x" }],
      }),
    ).toEqual({ state: "failed", reason: "x" });
    expect(readDesigns(job("failed"))).toEqual({ state: "failed", reason: "unknown" });
  });
});
