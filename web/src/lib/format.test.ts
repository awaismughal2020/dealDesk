import {
  formatGBP,
  formatHours,
  formatNumber,
  humanise,
  ratioToPercent,
  utilisationBand,
} from "./format";

describe("money and number formatting works on strings, never floats", () => {
  test.each([
    ["137830.00", "£137,830.00"],
    ["0.5", "£0.50"],
    ["-2631.54", "-£2,631.54"],
    ["1000000", "£1,000,000.00"],
  ])("formatGBP(%s)", (input, expected) => {
    expect(formatGBP(input)).toBe(expected);
  });

  test("precision beyond float range is preserved", () => {
    expect(formatGBP("90071992547409931.17")).toBe("£90,071,992,547,409,931.17");
  });

  test.each([
    ["0.3376", "33.76%"],
    ["0.25", "25%"],
    ["1.2500", "125%"],
    ["0", "0%"],
    ["-0.0123", "-1.23%"],
  ])("ratioToPercent(%s)", (input, expected) => {
    expect(ratioToPercent(input)).toBe(expected);
  });

  test("hours, numbers, missing values and labels", () => {
    expect(formatHours("1320.50")).toBe("1,320.5 h");
    expect(formatHours("12.00")).toBe("12 h");
    expect(formatNumber("1995.00")).toBe("1,995");
    expect(formatGBP(null)).toBe("—");
    expect(ratioToPercent(undefined)).toBe("—");
    expect(humanise("draft_proposal")).toBe("Draft proposal");
  });

  test.each([
    ["0.3000", "low"],
    ["0.5", "medium"],
    ["0.9", "high"],
    ["1.0000", "high"],
    ["1.2222", "over"],
  ])("utilisationBand(%s)", (input, band) => {
    expect(utilisationBand(input)).toBe(band);
  });
});
