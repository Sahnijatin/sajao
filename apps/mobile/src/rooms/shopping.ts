// The shopping list for one look. It is a view of the `Design`: the same
// items the look shows, each with its price and where to buy it, and the
// design's own total. Pure. Nothing here sets a price.
import type { Design } from "@sajao/schemas";

/** How an item fits where it stands, as the verifier found it. */
export type ItemFit = "fits" | "tight" | "does_not_fit";

/**
 * The verifier's verdict for one item, when the design carries it. The field
 * is being added to the Design contract (scope change 21); until a design
 * has it this returns null and the line falls back to the design's verdict.
 */
export function itemFit(item: Design["items"][number]): {
  status: ItemFit;
  /** Space left after the error band is taken as margin, in metres, when given. */
  spareM: number | null;
} | null {
  const fit = (item as { fit?: unknown }).fit;
  if (typeof fit !== "object" || fit === null) return null;
  const { status, clearance_m: spare } = fit as { status?: unknown; clearance_m?: unknown };
  if (status !== "fits" && status !== "tight" && status !== "does_not_fit") return null;
  return { status, spareM: typeof spare === "number" && Number.isFinite(spare) ? spare : null };
}

export interface ShoppingLine {
  id: string;
  title: string;
  /** The product's own photo, when the catalog may show it; null otherwise. */
  photo: string | null;
  priceMinor: number;
  /** Where to buy it; null when the product has no buy route. */
  url: string | null;
  inStock: boolean;
  /**
   * The item's own verdict from the verifier. Without one nothing is
   * promised: "check". The design passing as a whole does not say this item
   * fits.
   */
  fit: ItemFit | "check";
  /** Space to spare for this item, in metres, when the verifier gave it. */
  spareM: number | null;
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

export function shoppingFor(design: Design, fitChecked?: readonly string[] | null): Shopping {
  const lines = design.items.map((item) => {
    const own = itemFit(item);
    return {
      id: item.id,
      title: item.product.title,
      photo:
        item.product.image_use_permitted && item.product.images[0] ? item.product.images[0] : null,
      priceMinor: item.product.price.amount_minor,
      url: item.product.routes.find((route) => route.kind === "buy")?.url ?? null,
      inStock: item.product.in_stock,
      // A verdict counts only for an item whose fit the server checked, when it says.
      fit:
        own &&
        (own.status === "does_not_fit" ||
          !fitChecked ||
          fitChecked.includes(`${design.id}:${item.id}`))
          ? own.status
          : "check",
      spareM: own?.spareM ?? null,
    };
  }) satisfies ShoppingLine[];
  const sum = lines.reduce((total, line) => total + line.priceMinor, 0);
  return {
    lines,
    totalMinor: design.total_cost.amount_minor,
    consistent: sum === design.total_cost.amount_minor,
  };
}
