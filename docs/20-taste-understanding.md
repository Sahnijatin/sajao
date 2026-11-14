# Taste understanding

Taste is a learned profile, not a dropdown. Age and life stage give a starting guess; your own choices quickly override it.

## Inputs, in order

1. **Light context (two taps).** Age band, who lives here (alone, couple, family with kids, parents, pets), owned or rented. The age band is a weak prior only (for example, younger users leaning toward expressive, trend-led looks and older users toward subtle, durable ones). It is never shown back as a label.
2. **Adaptive swipes (8 to 12 cards).** Each next card is the one that best separates your remaining likely styles, so 10 swipes learn more than 30 random ones. Cards are real rooms and real products from our catalog.
3. **Optional references.** Instagram or Pinterest screenshots, a saved reel, a photo of a room you love.
4. **Budget and must-haves.** Slider plus "strict" or "can stretch 10%"; items to include; loved and banned colours.
5. **Behaviour (ongoing).** Swaps, saves, buy taps and skipped designs keep updating the profile.

## Representation

One vector in an open image-text embedding space, plus readable attributes: palette warmth, saturation, boldness, material preferences, clutter tolerance, formality, trend versus timeless. The vector ranks products and renders; the attributes drive the AI designer's brief and the plain-language profile you can edit.

## Mapping to style profiles

Your vector is described as a blend of the six launch [style profiles](14-style-profiles.md) (for example 60% Japandi, 30% Warm Luxe), which keeps designs coherent instead of random.

## Guardrails

- No stereotyping in copy.
- Age never filters products; it only seeds the first guess.
- You can view, correct and reset your taste profile at any time.
