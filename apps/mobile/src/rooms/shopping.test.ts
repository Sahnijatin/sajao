import { SAMPLE_DESIGNS } from "./sample-designs";
import { itemFit, shoppingFor } from "./shopping";

const [, bestMatch] = SAMPLE_DESIGNS;

describe("shopping list for a look", () => {
  it("lists the design's own items, each with its price and buy link", () => {
    const shopping = shoppingFor(bestMatch);
    expect(shopping.lines.map((line) => line.id)).toEqual(bestMatch.items.map((item) => item.id));
    expect(shopping.lines[0]).toEqual({
      id: "sofa",
      title: "Oak frame three seater sofa",
      photo: "https://cdn.example.com/products/sofa-oak-3s/front.jpg",
      priceMinor: 4299900,
      url: "https://www.example.com/p/sofa-oak-3s",
      inStock: true,
      // The sample items carry no verdict of their own: nothing is promised.
      fit: "check",
      spareM: null,
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

  it("shows a product photo only when the catalog may show it", () => {
    const [sofa, ...rest] = bestMatch.items;
    const noRight = { ...sofa, product: { ...sofa.product, image_use_permitted: false } };
    const noPhoto = { ...sofa, product: { ...sofa.product, images: [] } };
    // The contract requires a permitted photo; data from outside may still lack one.
    const lineOf = (item: unknown) =>
      shoppingFor({ ...bestMatch, items: [item, ...rest] } as unknown as typeof bestMatch).lines[0];
    expect(lineOf(noRight)?.photo).toBeNull();
    expect(lineOf(noPhoto)?.photo).toBeNull();
  });
});

describe("per-item fit", () => {
  const [sofa, ...rest] = bestMatch.items;
  const withFit = (fit: unknown) =>
    ({ ...bestMatch, items: [{ ...sofa, fit }, ...rest] }) as unknown as typeof bestMatch;

  it("uses the item's own verdict when the design carries one", () => {
    const lines = shoppingFor(withFit({ status: "tight", clearance_m: 0.02 })).lines;
    expect(lines[0]).toMatchObject({ fit: "tight", spareM: 0.02 });
    // The other items carry none: nothing is promised for them.
    expect(lines[1]).toMatchObject({ fit: "check", spareM: null });
  });

  it("an item that does not fit says so even when the design as a whole passed", () => {
    expect(shoppingFor(withFit({ status: "does_not_fit" })).lines[0]?.fit).toBe("does_not_fit");
  });

  it("ignores a verdict it cannot read, and promises nothing without one", () => {
    for (const fit of [null, "fits", { status: "maybe" }, 3]) {
      expect(itemFit({ ...sofa, fit } as unknown as typeof sofa)).toBeNull();
      expect(shoppingFor(withFit(fit)).lines[0]?.fit).toBe("check");
    }
    expect(
      itemFit({ ...sofa, fit: { status: "fits", clearance_m: "wide" } } as unknown as typeof sofa),
    ).toEqual({
      status: "fits",
      spareM: null,
    });
  });
});

describe("fit, as the server checked it", () => {
  const [sofa, ...rest] = bestMatch.items;
  const fitted = {
    ...bestMatch,
    items: [{ ...sofa, fit: { status: "fits", clearance_m: 0.12 } }, ...rest],
  } as unknown as typeof bestMatch;

  it("says an item fits only when its fit was checked against measured sizes", () => {
    expect(shoppingFor(fitted, [`${bestMatch.id}:sofa`]).lines[0]?.fit).toBe("fits");
    // Not checked (an estimated room): nothing is promised.
    expect(shoppingFor(fitted, []).lines[0]?.fit).toBe("check");
    // A server that does not say keeps the item's own verdict.
    expect(shoppingFor(fitted).lines[0]?.fit).toBe("fits");
  });

  it("still says when an item does not fit", () => {
    const tooBig = {
      ...bestMatch,
      items: [{ ...sofa, fit: { status: "does_not_fit" } }, ...rest],
    } as unknown as typeof bestMatch;
    expect(shoppingFor(tooBig, []).lines[0]?.fit).toBe("does_not_fit");
  });
});
