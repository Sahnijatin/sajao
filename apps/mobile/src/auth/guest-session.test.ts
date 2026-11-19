import { shareInFlight } from "./guest-session";

describe("the guest session's token", () => {
  it("is asked for once however many requests want it at the same time", async () => {
    let signIns = 0;
    const token = shareInFlight(async () => {
      signIns += 1;
      // Signing in takes a moment; parallel requests arrive meanwhile.
      await new Promise((resolve) => setTimeout(resolve, 10));
      return `guest-${signIns}`;
    });
    const tokens = await Promise.all([token(), token(), token(), token()]);
    expect(signIns).toBe(1);
    expect(new Set(tokens)).toEqual(new Set(["guest-1"]));
    // Once settled, the next request asks again (and finds the saved session).
    expect(await token()).toBe("guest-2");
  });

  it("lets a request after a failure try again", async () => {
    let calls = 0;
    const token = shareInFlight(async () => {
      calls += 1;
      if (calls === 1) throw new Error("offline");
      return "guest";
    });
    await expect(Promise.all([token(), token()])).rejects.toThrow("offline");
    expect(calls).toBe(1);
    expect(await token()).toBe("guest");
  });
});
