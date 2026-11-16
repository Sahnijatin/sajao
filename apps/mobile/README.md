# Mobile app

The Sajao app shell: Expo with Expo Router, four native tabs, English and Hindi, and a units setting. It opens straight into the app as a guest; there is no sign-in gate and no paywall, lock or upgrade prompt anywhere.

## Layout

| Path | What lives there |
| --- | --- |
| `src/app` | Routes only. `(tabs)` holds Home, My rooms, Vastu and Profile; `gallery` is the dev-only component gallery. |
| `src/screens` | Screen bodies the route files render. |
| `src/components` | Shared building blocks for screens. Design system components come from `@sajao/ui`. |
| `src/capture` | Scan logic, all unit-tested: frame statistics, feature points, triangulation, mesh tracking, guardrails and the scan session. `scan-camera.tsx` is the only file that touches the camera library. |
| `src/i18n` | String catalogs (`locales/en.json`, `locales/hi.json`) and language choice. |
| `src/state` | On-device settings (language, units), saved across launches. |
| `src/uploads` | Photo resizing and resumable uploads through signed URLs. |
| `src/utils` | Length and INR formatting. |

## Rules for screens

- Every user-facing string goes in both catalogs. A test fails if the keys or placeholders differ, or if a Hindi string is left in English.
- Lengths are metres in data and are shown through `formatLength` in the user's units. Prices are paise in data and are shown through `formatInr`.
- Colors, spacing, motion and haptics come from `@sajao/ui`.

## Hindi copy: needs native review

`src/i18n/locales/hi.json` has not been read by a fluent Hindi speaker yet. It must be reviewed before the closed test; the review is tracked in Notion.

## Running it

```
pnpm --filter @sajao/mobile start      # development server
pnpm --filter @sajao/mobile test       # unit and screen tests
pnpm --filter @sajao/mobile typecheck
```

The app uses native tabs and native sheets, so it needs a development build on a device or simulator rather than a browser.
