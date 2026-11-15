import { formatInr } from "./format-inr";

describe("INR formatting", () => {
  it.each([
    [0, "₹0"],
    [99900, "₹999"],
    [100000, "₹1,000"],
    [4299900, "₹42,999"],
    [15000000, "₹1,50,000"],
    [1234567800, "₹1,23,45,678"],
  ])("%d paise is %s", (paise, shown) => {
    expect(formatInr(paise)).toBe(shown);
  });

  it("shows paise only when there are any", () => {
    expect(formatInr(4299950)).toBe("₹42,999.50");
    expect(formatInr(5)).toBe("₹0.05");
  });

  it("rejects amounts that are not whole paise", () => {
    expect(() => formatInr(10.5)).toThrow(RangeError);
    expect(() => formatInr(-1)).toThrow(RangeError);
  });
});
