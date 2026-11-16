// The launch swipe deck: three cards per style profile, described from
// docs/14-style-profiles.md. Placeholder content: the real deck uses rooms
// and products from the curated catalog, with images, once it exists.
import type { Attributes, Style, SwipeCard, Trait } from "./adaptive-swipes";

const appeal = (
  main: Style,
  strong: Partial<Record<Style, number>> = {},
): Record<Style, number> => ({
  modern_indian: 0.2,
  warm_luxe: 0.2,
  japandi: 0.2,
  warm_maximalist: 0.2,
  eclectic_retro: 0.2,
  minimal_wabi_sabi: 0.2,
  ...strong,
  [main]: 0.9,
});

const attributes = (
  warmth: number,
  saturation: number,
  boldness: number,
  clutter: number,
  formality: number,
  timeless: number,
): Attributes => ({
  palette_warmth: warmth,
  saturation,
  boldness,
  clutter_tolerance: clutter,
  formality,
  trend_vs_timeless: timeless,
});

const card = (
  id: string,
  main: Style,
  near: Partial<Record<Style, number>>,
  traits: Trait[],
  attrs: Attributes,
): SwipeCard => ({ id, appeal: appeal(main, near), traits, attributes: attrs });

export const DECK: readonly SwipeCard[] = [
  card(
    "modern-indian-jhoola",
    "modern_indian",
    { warm_luxe: 0.45, warm_maximalist: 0.4 },
    ["warm_tones", "natural_wood", "brass", "handmade"],
    attributes(0.8, 0.55, 0.55, 0.5, 0.6, 0.7),
  ),
  card(
    "modern-indian-arch",
    "modern_indian",
    { minimal_wabi_sabi: 0.45 },
    ["warm_tones", "handmade", "soft_neutrals"],
    attributes(0.7, 0.4, 0.4, 0.35, 0.55, 0.75),
  ),
  card(
    "modern-indian-teal",
    "modern_indian",
    { eclectic_retro: 0.45, warm_maximalist: 0.45 },
    ["bold_colour", "natural_wood", "brass"],
    attributes(0.6, 0.7, 0.7, 0.5, 0.55, 0.6),
  ),
  card(
    "warm-luxe-media-wall",
    "warm_luxe",
    { modern_indian: 0.4 },
    ["soft_neutrals", "warm_tones", "layered"],
    attributes(0.7, 0.3, 0.45, 0.4, 0.8, 0.6),
  ),
  card(
    "warm-luxe-boucle",
    "warm_luxe",
    { japandi: 0.45, minimal_wabi_sabi: 0.4 },
    ["soft_neutrals", "low_clutter"],
    attributes(0.65, 0.2, 0.3, 0.25, 0.75, 0.65),
  ),
  card(
    "warm-luxe-chandelier",
    "warm_luxe",
    { warm_maximalist: 0.4 },
    ["brass", "layered", "warm_tones"],
    attributes(0.75, 0.4, 0.65, 0.5, 0.9, 0.5),
  ),
  card(
    "japandi-low-sofa",
    "japandi",
    { minimal_wabi_sabi: 0.6, warm_luxe: 0.35 },
    ["natural_wood", "low_clutter", "soft_neutrals"],
    attributes(0.55, 0.2, 0.25, 0.15, 0.5, 0.8),
  ),
  card(
    "japandi-lantern",
    "japandi",
    { minimal_wabi_sabi: 0.55 },
    ["natural_wood", "low_clutter", "handmade"],
    attributes(0.6, 0.25, 0.3, 0.2, 0.45, 0.8),
  ),
  card(
    "japandi-accent",
    "japandi",
    { eclectic_retro: 0.4 },
    ["natural_wood", "bold_colour", "low_clutter"],
    attributes(0.5, 0.5, 0.5, 0.2, 0.45, 0.65),
  ),
  card(
    "maximalist-gallery",
    "warm_maximalist",
    { eclectic_retro: 0.6 },
    ["bold_colour", "pattern", "layered", "vintage"],
    attributes(0.85, 0.85, 0.9, 0.9, 0.35, 0.4),
  ),
  card(
    "maximalist-checker",
    "warm_maximalist",
    { eclectic_retro: 0.55 },
    ["pattern", "bold_colour", "warm_tones"],
    attributes(0.8, 0.8, 0.85, 0.8, 0.3, 0.35),
  ),
  card(
    "maximalist-plants",
    "warm_maximalist",
    { modern_indian: 0.45 },
    ["plants", "layered", "warm_tones", "vintage"],
    attributes(0.75, 0.65, 0.7, 0.85, 0.3, 0.5),
  ),
  card(
    "retro-colour-block",
    "eclectic_retro",
    { warm_maximalist: 0.55 },
    ["bold_colour", "pattern"],
    attributes(0.65, 0.9, 0.9, 0.6, 0.3, 0.25),
  ),
  card(
    "retro-teak",
    "eclectic_retro",
    { modern_indian: 0.4, japandi: 0.35 },
    ["natural_wood", "vintage", "warm_tones"],
    attributes(0.7, 0.55, 0.55, 0.5, 0.4, 0.5),
  ),
  card(
    "retro-mushroom-lamp",
    "eclectic_retro",
    { warm_maximalist: 0.5 },
    ["bold_colour", "vintage", "pattern"],
    attributes(0.7, 0.75, 0.75, 0.6, 0.3, 0.3),
  ),
  card(
    "wabi-sabi-plaster",
    "minimal_wabi_sabi",
    { japandi: 0.6 },
    ["soft_neutrals", "handmade", "low_clutter"],
    attributes(0.55, 0.1, 0.2, 0.1, 0.45, 0.9),
  ),
  card(
    "wabi-sabi-linen",
    "minimal_wabi_sabi",
    { japandi: 0.55, warm_luxe: 0.35 },
    ["soft_neutrals", "natural_wood", "low_clutter"],
    attributes(0.6, 0.15, 0.2, 0.15, 0.5, 0.9),
  ),
  card(
    "wabi-sabi-blue",
    "minimal_wabi_sabi",
    { modern_indian: 0.35 },
    ["cool_tones", "handmade", "vintage"],
    attributes(0.35, 0.35, 0.4, 0.25, 0.5, 0.85),
  ),
];
