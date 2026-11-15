import { parseConfig } from "./config";

const dev = {
  EXPO_PUBLIC_ENVIRONMENT: "development",
  EXPO_PUBLIC_SUPABASE_URL: "https://example.supabase.co/",
  EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_abc",
};

describe("app config", () => {
  it("works with nothing set: development, no backend", () => {
    expect(parseConfig({})).toEqual({ environment: "development", apiUrl: null, supabase: null });
  });

  it("reads the environment's public values", () => {
    expect(parseConfig({ ...dev, EXPO_PUBLIC_API_URL: "https://api.example.com/" })).toEqual({
      environment: "development",
      apiUrl: "https://api.example.com",
      supabase: { url: "https://example.supabase.co", publishableKey: "sb_publishable_abc" },
    });
  });

  it("refuses a secret or legacy key: only a publishable key may ship in the app", () => {
    for (const key of ["sb_secret_abc", "eyJhbGciOiJIUzI1NiJ9.service.role"]) {
      expect(() => parseConfig({ ...dev, EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: key })).toThrow(
        /publishable key/,
      );
    }
  });

  it("needs the URL and the key together", () => {
    expect(() => parseConfig({ EXPO_PUBLIC_SUPABASE_URL: dev.EXPO_PUBLIC_SUPABASE_URL })).toThrow(
      /go together/,
    );
  });

  it("allows plain http only for a local stack", () => {
    expect(parseConfig({ EXPO_PUBLIC_API_URL: "http://localhost:8000" }).apiUrl).toBe(
      "http://localhost:8000",
    );
    expect(() => parseConfig({ EXPO_PUBLIC_API_URL: "http://api.example.com" })).toThrow(/https/);
  });

  it("rejects an unknown environment", () => {
    expect(() => parseConfig({ EXPO_PUBLIC_ENVIRONMENT: "staging2" })).toThrow();
  });
});
