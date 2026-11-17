import { validate } from "@sajao/schemas/validate";
import { SAMPLE_DESIGNS } from "./sample-designs";

describe("sample designs against the contract", () => {
  it.each(SAMPLE_DESIGNS.map((design) => [design.slot, design] as const))(
    "%s is a valid Design",
    (_slot, design) => {
      const result = validate("Design", design);
      expect(result.ok ? [] : result.errors).toEqual([]);
    },
  );
});
