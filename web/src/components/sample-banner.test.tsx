import { render, screen } from "@testing-library/react";
import { SampleBanner } from "./sample-banner";

test("states that all data is sample data", () => {
  render(<SampleBanner />);
  expect(screen.getByRole("note")).toHaveTextContent(
    "SAMPLE DATA, NOT REAL CLIENT OR COMPANY DATA",
  );
});
