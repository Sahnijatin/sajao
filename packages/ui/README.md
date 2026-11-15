# UI

The Sajao design system: LiveMap tokens, motion presets, the haptic map and core components. Every screen builds from this package. Source of truth: `docs/10-design-language-and-motion.md`.

## What is here

| Piece | File | Notes |
| --- | --- | --- |
| Tokens | `src/tokens.ts` | Colors, glass, radius, spacing, shadows, type. Light theme only; the dark slot is reserved in `themes`. |
| Motion presets | `src/motion.ts` | Transition ease, press feedback, selection spring, layout glide. |
| Haptic map | `src/haptics.ts` | One entry per moment in the design doc, with separate iOS and Android patterns. |
| Device tier | `src/deviceTier.ts` | `standard` or `low`; Android phones with up to 4 GB of RAM are low. |
| Theme | `src/theme.tsx` | `ThemeProvider` and `useTheme()`: tokens, tier, reduced motion and `duration()`. |
| Components | `src/components` | `Text`, `Button`, `Card`, `Chip`, `GlassSurface`, `Sheet`, `TextField`. |
| Gallery | `src/gallery/GalleryScreen.tsx` | Dev-only screen showing everything, with switches for the low tier and reduced motion. |

## Rules for screens

- Wrap the app in `ThemeProvider` once. Read values with `useTheme()`; do not hardcode colors, radii or durations.
- Run every duration through `duration()`. It returns 0 with reduced motion and a shorter value on the low tier.
- Haptics come only from `playHaptic(moment)`. They mark real milestones and are never the only feedback.
- Glass never animates its blur. Crossfade the whole surface instead.
- Components take their text as props. Strings live in the app's string catalogs.

## Fallbacks

| Effect | Standard | Low tier | Reduced motion |
| --- | --- | --- | --- |
| Glass | Live blur under a 62% white fill | Tinted fill, no blur | Same as tier |
| Shadows | Three stacked | One | Same as tier |
| Press and selection | Preset durations and spring | Durations cut by a third | Instant change |

On Android a live blur needs a `blurTarget`; without one `GlassSurface` shows the tinted fill.

## Provisional values

The design doc fixes colors, glass, radius, the transition ease and the selection spring. It does not give numbers for the spacing scale, the type scale, the shadow offsets, the glass border or the low-tier tint. Those are set here to sensible values and should be confirmed against the screen mockups. Blur saturation (180%) is recorded as a token but not applied, because the blur view has no saturation control.

## Hindi copy: needs native review

The Hindi strings in `apps/mobile/src/i18n/locales/hi.json` have not been read by a fluent speaker. They must be reviewed and corrected before the closed test. Components here take their text as props, so any new Hindi string added for a component goes through the same review.

## Tests

`pnpm --filter @sajao/ui test` checks the tokens and presets against the design doc, every haptic pattern on both platforms, the low-tier and reduced-motion fallbacks, and that the gallery renders.
