# Mobile app

The Sajao app: Expo with Expo Router, two native tabs, English and Hindi, and a units setting. It opens on My home as a guest; there is no sign-in gate and no paywall, lock or upgrade prompt anywhere.

## Layout

| Path | What lives there |
| --- | --- |
| `src/app` | Routes only. `(tabs)` holds Home (My home) and Profile; `gallery` is the dev-only component gallery. |
| `src/screens` | Screen bodies the route files render. |
| `src/components` | Shared building blocks for screens. Design system components come from `@sajao/ui`. |
| `src/capture` | Scan logic, all unit-tested: frame statistics, feature points, triangulation, mesh tracking, guardrails and the scan session. `scan-camera.tsx` is the only file that touches the camera library. |
| `src/rooms` | Rooms on My home: the room model, card labels, the room card and the room still (a real image, or a drawn stand-in until one exists). Also what a room holds after the pipeline (`room-content.ts`: hero views and three looks, each a view of one `Design`), the generation stages, the sample content that stands in for both, the shopping list as a view of a `Design` (`shopping.ts`), the room's measured walls, openings and big items read from its `SpaceTwin` (`measures.ts`), and the geometry of the 2D plan drawn from a `Design` and the room's shell (`design-plan.ts`). |
| `src/space` | Space Profile card logic: what was found, user edits, tape re-fit, plan geometry. |
| `src/taste` | Taste onboarding: adaptive swipes, the card deck and the onboarding flow. |
| `src/i18n` | String catalogs (`locales/en.json`, `locales/hi.json`) and language choice. |
| `src/state` | On-device settings (language, units) and the rooms on My home, saved across launches. |
| `src/uploads` | Photo resizing and resumable uploads through signed URLs. |
| `src/utils` | Length and INR formatting. |

## Real rooms

With `EXPO_PUBLIC_API_URL` set, a confirmed scan becomes a room on the server: `src/rooms/room-source.ts` waits for the upload, creates the room, follows its job stage by stage and reads its `SpaceTwin`. `room-api.ts` holds the pure mapping (stages done, failure reasons, twin to room content) and `room-client.ts` the typed network client. Designs and photos are not read yet.

## Samples

Stand-in content (the sample room, designs, space profile, and the drawn stills) shows only where `samplesAllowed()` in `src/rooms/samples.ts` says so: development and preview builds. A store or closed-test build shows none of it; where real data is missing a screen is skipped or says the room is being prepared.

## Flags

`src/features.ts` holds features that are built towards but switched off. `EXPO_PUBLIC_TWIN_VIEWER=1` on an EAS environment shows the place kept for the 3D view on the Room tab; without it the tab is hero photos and measurements only.

## Rules for screens

- Every user-facing string goes in both catalogs. A test fails if the keys or placeholders differ, or if a Hindi string is left in English.
- Lengths are metres in data and are shown through `formatLength` in the user's units: feet and inches by default, centimetres as the alternative in settings. Prices are paise in data and are shown through `formatInr`.
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

## Builds

The app is linked to the EAS project `@sahniijatinn/sajao`. `eas.json` has three profiles:

| Profile | What it is | App name and id |
| --- | --- | --- |
| `development` | Development client, internal distribution | Sajao (Dev), `app.sajao.dev` |
| `preview` | Release build for testers, internal distribution | Sajao (Preview), `app.sajao.preview` |
| `production` | Store build | Sajao, `app.sajao` |

```
eas build --platform android --profile development
eas build --platform ios --profile development      # needs an Apple Developer account and a registered iPhone
pnpm --filter @sajao/mobile start                    # then open the development build and connect
```

Each EAS environment (development, preview, production) holds that environment's `EXPO_PUBLIC_*` values. Nothing secret goes in `EXPO_PUBLIC_*` values: they ship inside the app.

## Updates without a rebuild

Preview and production builds check for a JavaScript update when they start. Each build listens on the channel named after its profile.

```
eas update --channel preview --environment preview --message "<what changed>"
```

An update reaches a build only when the app version matches, and it can only change JavaScript, styling and bundled assets. Adding or changing a native package needs a new build, and the app version in `app.json` must be raised with it so older builds do not receive JavaScript they cannot run. On the phone, close the app fully and open it up to twice: the first launch downloads the update, the next one runs it.
