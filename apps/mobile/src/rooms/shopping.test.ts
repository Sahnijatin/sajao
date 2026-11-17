import { SAMPLE_DESIGNS } from "./sample-designs";
import { shoppingFor } from "./shopping";

const [, bestMatch] = SAMPLE_DESIGNS;

describe("shopping list for a look", () => {
  it("lists the design's own items, each with its price and buy link", () => {
    const shopping = shoppingFor(bestMatch);
    expect(shopping.lines.map((line) => line.id)).toEqual(bestMatch.items.map((item) => item.id));
    expect(shopping.lines[0]).toEqual({
      id: "sofa",
      title: "Oak frame three seater sofa",
      priceMinor: 4299900,
      url: "https://www.example.com/p/sofa-oak-3s",
      inStock: true,
      fit: "fits",
    });
  });

  it("the total is the design's, and the lines add up to it", () => {
    for (const design of SAMPLE_DESIGNS) {
      const shopping = shoppingFor(design);
      expect(shopping.totalMinor).toBe(design.total_cost.amount_minor);
      expect(shopping.consistent).toBe(true);
    }
  });

  it("flags a design whose total disagrees with its items", () => {
    const broken = { ...bestMatch, total_cost: { currency: "INR" as const, amount_minor: 1 } };
    expect(shoppingFor(broken).consistent).toBe(false);
  });

  it("promises no fit when the design did not pass the verifier", () => {
    const failed = { ...bestMatch, check_report: { ...bestMatch.check_report, passed: false } };
    expect(shoppingFor(failed).lines.every((line) => line.fit === "check")).toBe(true);
  });

  it("uses the buy route, never the rent one, and copes with none", () => {
    const [sofa, ...rest] = bestMatch.items;
    const rentOnly = {
      ...sofa,
      product: {
        ...sofa.product,
        routes: sofa.product.routes.filter((route) => route.kind === "rent"),
      },
    };
    const design = { ...bestMatch, items: [rentOnly, ...rest] } as typeof bestMatch;
    expect(shoppingFor(design).lines[0]?.url).toBeNull();
  });
});
