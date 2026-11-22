import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// An unclosed /* comment silently swallows the rules after it (it broke the example questions once).
describe("styles.css", () => {
  const css = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

  it("closes every comment", () => {
    let open = 0;
    for (let i = 0; i < css.length - 1; i++) {
      if (css.startsWith("/*", i)) {
        expect(open, `nested or unclosed comment near offset ${i}`).toBe(0);
        open = 1;
        i++;
      } else if (css.startsWith("*/", i)) {
        expect(open, `stray */ near offset ${i}`).toBe(1);
        open = 0;
        i++;
      }
    }
    expect(open, "a comment is never closed").toBe(0);
  });

  it("balances braces once comments are removed", () => {
    const code = css.replace(/\/\*[\s\S]*?\*\//g, "");
    expect(code.split("{").length).toBe(code.split("}").length);
  });
});
