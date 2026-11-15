// Prices are INR in paise (see Money in @sajao/schemas). Shown with Indian
// digit grouping: 1,50,000 rather than 150,000.
function groupIndian(rupees: number): string {
  const digits = String(rupees);
  if (digits.length <= 3) return digits;
  const lastThree = digits.slice(-3);
  const rest = digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return `${rest},${lastThree}`;
}

export function formatInr(amountMinor: number): string {
  if (!Number.isInteger(amountMinor) || amountMinor < 0) {
    throw new RangeError("amountMinor must be a non-negative integer number of paise");
  }
  const rupees = Math.floor(amountMinor / 100);
  const paise = amountMinor % 100;
  const fraction = paise === 0 ? "" : `.${String(paise).padStart(2, "0")}`;
  return `₹${groupIndian(rupees)}${fraction}`;
}
