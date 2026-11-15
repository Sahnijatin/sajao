import { describe, expect, it } from "vitest";
import { createApiClient } from "./index";

function recordingFetch(body: unknown = { status: "ok", version: "0.0.0", environment: "dev" }) {
  const requests: Request[] = [];
  const fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    requests.push(new Request(input, init));
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  return { requests, fetch };
}

describe("api client", () => {
  it("calls versioned paths and returns typed data", async () => {
    const { requests, fetch } = recordingFetch();
    const api = createApiClient({ baseUrl: "https://api.example.com", fetch });

    const { data, error } = await api.GET("/v1/health");

    expect(error).toBeUndefined();
    expect(data?.status).toBe("ok");
    expect(requests[0]?.url).toBe("https://api.example.com/v1/health");
  });

  it("sends the app version when given one", async () => {
    const { requests, fetch } = recordingFetch();
    await createApiClient({ baseUrl: "https://a.example", appVersion: "1.4.0", fetch }).GET(
      "/v1/health",
    );
    expect(requests[0]?.headers.get("X-App-Version")).toBe("1.4.0");
  });

  it("does not add an idempotency key to reads", async () => {
    const { requests, fetch } = recordingFetch();
    await createApiClient({ baseUrl: "https://a.example", fetch }).GET("/v1/health");
    expect(requests[0]?.headers.has("Idempotency-Key")).toBe(false);
  });

  it("adds a fresh idempotency key to each write, and keeps one the caller set", async () => {
    const { requests, fetch } = recordingFetch();
    let next = 0;
    const api = createApiClient({
      baseUrl: "https://a.example",
      newIdempotencyKey: () => `key-${++next}`,
      fetch,
    });
    // No write endpoints exist yet, so reach below the typed surface.
    const post = api.POST as unknown as (path: string, init?: object) => Promise<unknown>;

    await post("/v1/future-write");
    await post("/v1/future-write");
    await post("/v1/future-write", { headers: { "Idempotency-Key": "retry-me" } });

    expect(requests.map((request) => request.headers.get("Idempotency-Key"))).toEqual([
      "key-1",
      "key-2",
      "retry-me",
    ]);
  });
});
