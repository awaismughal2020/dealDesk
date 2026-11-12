// Fails if src/lib/api/schema.d.ts is not exactly what openapi.json generates (CI guard).
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const dir = mkdtempSync(join(tmpdir(), "client-"));
const generated = join(dir, "schema.d.ts");
try {
  execFileSync("npx", ["openapi-typescript", "openapi.json", "-o", generated], { stdio: "ignore" });
  execFileSync("npx", ["prettier", "--config", ".prettierrc.json", "--write", generated], {
    stdio: "ignore",
  });
  const committed = readFileSync("src/lib/api/schema.d.ts", "utf8");
  if (readFileSync(generated, "utf8") !== committed) {
    console.error(
      "The generated API client is stale. Run `make gen-client` and commit the result.",
    );
    process.exit(1);
  }
  process.stdout.write("API client is up to date with openapi.json\n");
} finally {
  rmSync(dir, { recursive: true, force: true });
}
