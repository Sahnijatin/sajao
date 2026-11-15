import { resolveLanguage } from "@/i18n";
import en from "@/i18n/locales/en.json";
import hi from "@/i18n/locales/hi.json";

type Catalog = { [key: string]: string | Catalog };

function flatten(catalog: Catalog, prefix = ""): Record<string, string> {
  return Object.entries(catalog).reduce<Record<string, string>>((all, [key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof value === "string"
      ? { ...all, [path]: value }
      : { ...all, ...flatten(value, path) };
  }, {});
}

const english = flatten(en);
const hindi = flatten(hi);
const placeholders = (text: string) => (text.match(/{{\w+}}/g) ?? []).sort();

describe("string catalogs", () => {
  it("English and Hindi have exactly the same keys", () => {
    expect(Object.keys(hindi).sort()).toEqual(Object.keys(english).sort());
  });

  it("no string is empty, and placeholders match across languages", () => {
    for (const key of Object.keys(english)) {
      expect(english[key]?.trim()).not.toBe("");
      expect(hindi[key]?.trim()).not.toBe("");
      expect(placeholders(hindi[key] ?? "")).toEqual(placeholders(english[key] ?? ""));
    }
  });

  it("Hindi strings are translated, apart from language names", () => {
    const same = Object.keys(english).filter(
      (key) => !key.startsWith("languages.") && english[key] === hindi[key],
    );
    expect(same).toEqual([]);
  });

  it("has no paywall, lock or upgrade wording", () => {
    const banned = /\b(upgrade|premium|subscribe|subscription|unlock|paywall|pro plan|paid)\b/i;
    const hits = Object.entries(english).filter(([, text]) => banned.test(text));
    expect(hits).toEqual([]);
  });

  it("follows repository writing rules", () => {
    for (const text of [...Object.values(english), ...Object.values(hindi)]) {
      expect(text).not.toMatch(/—/);
      expect(text).not.toMatch(/\b(he|she|his|her|hers)\b/i);
    }
  });

  it("carries the required Vastu label", () => {
    expect(english["vastu.label"]).toBe(
      "Vastu guidance, as close as possible. For a full consultation, speak to an expert.",
    );
  });
});

describe("language choice", () => {
  it("uses the stored choice first", () => {
    expect(resolveLanguage("hi", "en")).toBe("hi");
    expect(resolveLanguage("en", "hi")).toBe("en");
  });

  it("follows a Hindi device, and falls back to English otherwise", () => {
    expect(resolveLanguage(null, "hi")).toBe("hi");
    expect(resolveLanguage(null, "ta")).toBe("en");
    expect(resolveLanguage(null, null)).toBe("en");
  });
});
