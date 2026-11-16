# Supabase

Local stack config, database migrations and generated types.

## Environments

| Environment | Project | Notes |
| --- | --- | --- |
| Local | Supabase CLI stack (`npx supabase start`) | No cloud keys. Used by tests. |
| Development | `sajao-dev`, Mumbai, project ref `lofesiqfpxoniwaipdaw` | Free plan. New tables are not auto-exposed; RLS is on by default. |
| Staging, production | Not created | Need founder approval before any paid project exists. |

The project ref is not a secret. The access token, database password and secret API keys are, and live only in secret managers and CI secrets.

## Migrations

Every database change is a new file in `migrations/`, backward compatible (expand, then contract).

```
npx supabase link --project-ref lofesiqfpxoniwaipdaw   # needs SUPABASE_ACCESS_TOKEN
npx supabase migration list --remote                    # compare local and remote
npx supabase db push                                    # apply new migrations
```

`db push` and `migration list` connect to Postgres directly, so they need a network that allows it. Where only HTTPS is available, apply a migration with `npx supabase db query --remote --yes -f <file>` and record its version in `supabase_migrations.schema_migrations`, which is the table `db push` reads, so both routes stay in step.

Applied to development: `20261115000000_idempotency_keys`.

## Types

```
pnpm db:types    # regenerates supabase/types/database.ts from sajao-dev
```

Only the `public` schema is generated. It is empty for now: the one table so far lives in the `private` schema, which is not exposed through the data API.

## Auth

The API verifies tokens against the project's public signing keys:

```
SAJAO_AUTH_JWKS_URL=https://<project ref>.supabase.co/auth/v1/.well-known/jwks.json
SAJAO_AUTH_ISSUER=https://<project ref>.supabase.co/auth/v1
```

Guest-first: anonymous sign-ins are on for the development project, limited to 30 per hour per IP address by the built-in rate limit. The local stack has them on too (`config.toml`). App attestation on guest sessions is required before the closed test.

The app uses `EXPO_PUBLIC_SUPABASE_URL` and `EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, set on the EAS environment. Only a publishable key may ship in the app; the app refuses to start with any other kind.
