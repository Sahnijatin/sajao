import { type RoomContent, sampleContent } from "./room-content";
import { SAMPLE_DESIGNS, totalOf } from "./sample-designs";

describe("sample designs", () => {
  it("are one per slot, in reveal order", () => {
    expect(SAMPLE_DESIGNS.map((design) => design.slot)).toEqual([
      "best_value",
      "best_match",
      "bold",
    ]);
    expect(new Set(SAMPLE_DESIGNS.map((design) => design.id)).size).toBe(3);
  });

  it("each total is the sum of that design's own items, in paise", () => {
    for (const design of SAMPLE_DESIGNS) {
      const sum = design.items.reduce((total, item) => total + item.product.price.amount_minor, 0);
      expect(design.total_cost).toEqual({ currency: "INR", amount_minor: sum });
      expect(totalOf(design.items)).toEqual(design.total_cost);
    }
    expect(SAMPLE_DESIGNS.map((design) => design.total_cost.amount_minor)).toEqual([
      3349700, 6049600, 7949500,
    ]);
  });

  it("every item is a product with a price, a link and a size, placed by the solver or a person", () => {
    for (const item of SAMPLE_DESIGNS.flatMap((design) => design.items)) {
      expect(item.product.price.amount_minor).toBeGreaterThan(0);
      expect(item.product.routes[0]?.url).toMatch(/^https:\/\//);
      expect(item.product.routes[0]?.price).toEqual(item.product.price);
      expect(item.product.dimensions.width.value_m).toBeGreaterThan(0);
      expect(["solver", "user"]).toContain(item.placed_by);
    }
  });

  it("item ids are unique within a design", () => {
    for (const design of SAMPLE_DESIGNS) {
      const ids = design.items.map((item) => item.id);
      expect(new Set(ids).size).toBe(ids.length);
    }
  });
});

describe("room content", () => {
  it("is marked as a sample, with three hero views and three looks", () => {
    const content = sampleContent() as RoomContent;
    expect(content.sample).toBe(true);
    expect(content.heroViews).toHaveLength(3);
    expect(content.looks.map((look) => look.design)).toEqual([...SAMPLE_DESIGNS]);
  });
});
