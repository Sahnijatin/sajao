# UI

The Sajao design system: LiveMap tokens, motion presets, the haptic map and core components. Every screen builds from this package. Source of truth: `docs/10-design-language-and-motion.md`.

## What is here

| Piece | File | Notes |
| --- | --- | --- |
| Tokens | `src/tokens.ts` | Colors, light and dark glass, radius, spacing, control heights, shadows, type. Light theme only; the dark slot is reserved in `themes`. |
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
| Glass | Live blur under a light or dark fill | Tinted fill, no blur | Same as tier |
| Shadows | Three stacked; glow under the accent button | One; no glow | Same as tier |
| Press and selection | Preset durations and spring | Durations cut by a third | Instant change |

On Android a live blur needs a `blurTarget`; without one `GlassSurface` shows the tinted fill.

## Values from the approved mockups

Spacing, type and shadows come from the approved key-screen mockups.

| Token | Values |
| --- | --- |
| Spacing | 2, 4, 6, 8, 10, 12, 14; 16 for screen and card padding; 26 under sheets |
| Type | Instrument Serif headlines: display 46, title 34, heading 26. Sans body: 16, 14, 13, 12, 11; totals 24 semibold |
| Buttons | 56 px pills; 32 px small pills. Variants: `primary`, `ink`, `outline`, `tint`, `ghost` |
| Sheets | 30 px top corners, white, with an upward shadow |
| Shadows | Card (three stacked), sheet, accent glow, segment; each with a low-tier version |
| Glass | `light` over the canvas and photos; `dark` (`tone="dark"`) on camera screens |

## Fonts

The app loads these at startup under exactly these family names (`fontFamilies` in `src/tokens.ts`):

| Family name | Font | Platforms |
| --- | --- | --- |
| `InstrumentSerif-Regular`, `InstrumentSerif-Italic` | Instrument Serif (SIL Open Font License) | iOS and Android |
| `Geist-Regular`, `Geist-Medium`, `Geist-SemiBold` | Geist (SIL Open Font License) | Android only; iOS uses the system font |

Instrument Serif has Latin letters only. Hindi headlines fall back to the system Devanagari font, so they need a look on a device.

## Still open

- **Card radius.** The design doc says 14 px cards and 20 px panes, which is what the tokens hold. The mockups draw cards at 18 to 24 px. Not changed here; it needs a decision.
- **Sheet corners on Android.** iOS gets the 30 px radius. The Android sheet keeps its Material shape, because the native sheet does not take a radius.
- **Low-tier dark glass tint** (78% opacity) is not on the mockups; it was chosen so white text stays legible without a blur.
- Blur saturation (180% light, 160% dark) is recorded as a token but not applied, because the blur view has no saturation control.

## Tests

`pnpm --filter @sajao/ui test` checks the tokens and presets against the design doc, every haptic pattern on both platforms, the low-tier and reduced-motion fallbacks, and that the gallery renders.
