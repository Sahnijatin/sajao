// The shopping list for one look. It is a view of the `Design`: the same
// items the look shows, each with its price and where to buy it, and the
// design's own total. Pure. Nothing here sets a price.
import type { Design } from "@sajao/schemas";

export interface ShoppingLine {
  id: string;
  title: string;
  priceMinor: number;
  /** Where to buy it; null when the product has no buy route. */
  url: string | null;
  inStock: boolean;
  /** fits: the design passed the verifier. check: it did not, so nothing is promised. */
  fit: "fits" | "check";
}

export interface Shopping {
  lines: ShoppingLine[];
  /** The design's total, in paise. */
  totalMinor: number;
  /**
   * The lines add up to the design's total. When they do not, the list and
   * the look would disagree, so the total is not shown.
   */
  consistent: boolean;
}

export function shoppingFor(design: Design): Shopping {
  const fit = design.check_report.passed ? "fits" : "check";
  const lines = design.items.map((item) => ({
    id: item.id,
    title: item.product.title,
    priceMinor: item.product.price.amount_minor,
    url: item.product.routes.find((route) => route.kind === "buy")?.url ?? null,
    inStock: item.product.in_stock,
    fit,
  })) satisfies ShoppingLine[];
  const sum = lines.reduce((total, line) => total + line.priceMinor, 0);
  return {
    lines,
    totalMinor: design.total_cost.amount_minor,
    consistent: sum === design.total_cost.amount_minor,
  };
}
