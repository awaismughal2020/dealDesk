/**
 * Display formatting for decimal strings computed by the server. These functions only move
 * characters around; they never convert money to floating point or do arithmetic on it.
 */

function splitDecimal(value: string): { sign: string; whole: string; fraction: string } {
  const trimmed = value.trim();
  const sign = trimmed.startsWith("-") ? "-" : "";
  const unsigned = trimmed.replace(/^[-+]/, "");
  const [whole = "0", fraction = ""] = unsigned.split(".");
  return { sign, whole: whole.replace(/^0+(?=\d)/, ""), fraction };
}

function groupThousands(whole: string): string {
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** "137830.00" -> "£137,830.00" */
export function formatGBP(value: string | null | undefined): string {
  if (value == null || value === "") return "—";
  const { sign, whole, fraction } = splitDecimal(value);
  return `${sign}£${groupThousands(whole)}.${fraction.padEnd(2, "0").slice(0, 2)}`;
}

/** "1320.50" -> "1,320.5 h"; trailing zeros dropped. */
export function formatHours(value: string | null | undefined): string {
  if (value == null || value === "") return "—";
  const { sign, whole, fraction } = splitDecimal(value);
  const shortFraction = fraction.replace(/0+$/, "");
  return `${sign}${groupThousands(whole)}${shortFraction ? `.${shortFraction}` : ""} h`;
}

/** A ratio string to a percentage by moving the decimal point: "0.3376" -> "33.76%". */
export function ratioToPercent(value: string | null | undefined): string {
  if (value == null || value === "") return "—";
  const { sign, whole, fraction } = splitDecimal(value);
  const digits = `${whole}${fraction.padEnd(2, "0")}`;
  const integerPart = digits.slice(0, whole.length + 2).replace(/^0+(?=\d)/, "");
  const rest = digits.slice(whole.length + 2).replace(/0+$/, "");
  return `${sign}${integerPart}${rest ? `.${rest}` : ""}%`;
}

/** Plain number grouping for integers and decimals given as strings: "1995.00" -> "1,995". */
export function formatNumber(value: string | null | undefined): string {
  if (value == null || value === "") return "—";
  const { sign, whole, fraction } = splitDecimal(value);
  const shortFraction = fraction.replace(/0+$/, "");
  return `${sign}${groupThousands(whole)}${shortFraction ? `.${shortFraction}` : ""}`;
}

const DATE = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const DATE_TIME = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDate(value: string): string {
  return DATE.format(new Date(value));
}

export function formatDateTime(value: string): string {
  return DATE_TIME.format(new Date(value));
}

/** Humanise an identifier: "draft_proposal" -> "Draft proposal". */
export function humanise(value: string): string {
  const spaced = value.replace(/_/g, " ").toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Server-computed utilisation (1.0 = 100%) to a heat band, by string comparison only. */
export function utilisationBand(value: string): "low" | "medium" | "high" | "over" {
  const { whole, fraction } = splitDecimal(value);
  const hundredths = Number.parseInt(`${whole}${fraction.padEnd(2, "0").slice(0, 2)}`, 10);
  if (hundredths > 100) return "over";
  if (hundredths >= 85) return "high";
  if (hundredths >= 50) return "medium";
  return "low";
}
