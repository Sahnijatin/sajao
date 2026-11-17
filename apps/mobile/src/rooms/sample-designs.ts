// Sample designs, in the shape the design engine will send: three `Design`
// objects, one per slot. They stand in until real designs arrive, and are
// always shown labelled as samples. Products and prices here are examples.
// Each total is added up by code from the same items, as the contract
// requires; nothing is typed in by hand.
import type { Design, Product } from "@sajao/schemas";
import fixture from "../../../../packages/schemas/fixtures/v1/valid/design.json";

type Item = Design["items"][number];

const base = fixture as unknown as Design;
const [oakSofa, paperLamp] = base.items as [Item, Item];

/** A sample product in the same shape as the catalog's. */
function product(
  number: number,
  title: string,
  group: Product["group"],
  category: string,
  rupees: number,
  size: [number, number, number],
): Product {
  const price = { currency: "INR" as const, amount_minor: rupees * 100 };
  const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const dimension = (value_m: number) => ({
    value_m,
    source: "measured" as const,
    error_band_m: 0.01,
  });
  return {
    ...paperLamp.product,
    id: `00000000-0000-4000-8000-0000000001${String(number).padStart(2, "0")}`,
    sku: slug.toUpperCase(),
    title,
    group,
    category,
    dimensions: {
      width: dimension(size[0]),
      depth: dimension(size[1]),
      height: dimension(size[2]),
    },
    price,
    images: [`https://cdn.example.com/products/${slug}/front.jpg`],
    routes: [
      { kind: "buy", retailer: "flipkart", url: `https://www.example.com/p/${slug}`, price },
    ],
  };
}

const item = (id: string, value: Product, x_m: number, y_m: number, rotation_deg = 0): Item => ({
  id,
  product: value,
  position: { x_m, y_m },
  rotation_deg,
  placed_by: "solver",
});

const linenSofa = item(
  "sofa",
  product(1, "Linen two seater sofa", "furniture", "sofa", 24999, [1.6, 0.8, 0.8]),
  2.1,
  2.85,
  180,
);
const juteRug = item(
  "rug",
  product(2, "Handwoven jute rug", "decor", "rug", 4999, [1.8, 1.2, 0.01]),
  2.1,
  1.9,
);
const caneTable = item(
  "table",
  product(3, "Cane and teak coffee table", "furniture", "coffee_table", 8999, [0.9, 0.5, 0.4]),
  2.1,
  1.9,
);
const rustChair = item(
  "chair",
  product(4, "Rust velvet armchair", "furniture", "armchair", 15999, [0.75, 0.8, 0.85]),
  0.9,
  1.6,
  90,
);
const brassLamp = item(
  "pendant",
  product(5, "Brass dome pendant lamp", "lighting", "pendant_lamp", 6499, [0.4, 0.4, 0.3]),
  2.1,
  1.9,
);

/** The sum of the item prices: the only way a total is ever made. */
export function totalOf(items: readonly Item[]): Design["total_cost"] {
  return {
    currency: "INR",
    amount_minor: items.reduce((sum, each) => sum + each.product.price.amount_minor, 0),
  };
}

function design(number: number, slot: Design["slot"], items: Design["items"], why: string): Design {
  return {
    ...base,
    id: `00000000-0000-4000-8000-0000000002${String(number).padStart(2, "0")}`,
    slot,
    items,
    total_cost: totalOf(items),
    relaxations: [],
    explanations: [why],
  };
}

export const SAMPLE_DESIGNS: readonly [Design, Design, Design] = [
  design(
    1,
    "best_value",
    [linenSofa, paperLamp, juteRug],
    "A lighter sofa leaves the walkway wide and the budget free.",
  ),
  design(
    2,
    "best_match",
    [oakSofa, paperLamp, caneTable, juteRug],
    "The sofa faces the window and keeps 0.82 m clear to the door.",
  ),
  design(
    3,
    "bold",
    [oakSofa, rustChair, caneTable, brassLamp, juteRug],
    "A rust armchair by the window gives the room one strong note.",
  ),
];
