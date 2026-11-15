// Typed client for the Sajao API. Paths, parameters and responses come from
// the OpenAPI document the API exports, so a contract change that breaks the
// app fails typecheck instead of failing on a phone.
import createClient, { type Client, type Middleware } from "openapi-fetch";
import type { paths } from "./generated/v1";

export type { components, paths } from "./generated/v1";

const WRITE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export interface ApiClientOptions {
  baseUrl: string;
  /** Sent as X-App-Version so the API can ask old apps to update. */
  appVersion?: string;
  /** Makes a new idempotency key. Defaults to a random UUID. */
  newIdempotencyKey?: () => string;
  fetch?: typeof globalThis.fetch;
}

export type ApiClient = Client<paths>;

export function createApiClient({
  baseUrl,
  appVersion,
  newIdempotencyKey = () => globalThis.crypto.randomUUID(),
  fetch,
}: ApiClientOptions): ApiClient {
  const client = createClient<paths>({ baseUrl, ...(fetch ? { fetch } : {}) });

  const headers: Middleware = {
    onRequest({ request }) {
      if (appVersion) request.headers.set("X-App-Version", appVersion);
      // Every write carries a key. To retry a write safely, pass the same
      // Idempotency-Key header again; a key set by the caller is never replaced.
      if (WRITE_METHODS.has(request.method) && !request.headers.has("Idempotency-Key")) {
        request.headers.set("Idempotency-Key", newIdempotencyKey());
      }
      return request;
    },
  };
  client.use(headers);
  return client;
}
