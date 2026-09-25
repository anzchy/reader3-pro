// 013 final review L2 (RV-4): a library search hit opens /read/<book>/<chapter> with both path
// segments percent-encoded. A book folder is a filesystem name; a space or a '#' in it must not
// end the path (or start a fragment) in the URL the hit navigates to.
import { describe, expect, it } from "vitest";

import { searchHitHref } from "../../src/library/search";

describe("searchHitHref", () => {
  it("encodes a book id with a space and a '#' (keyword hit keeps q and occurrence)", () => {
    const href = searchHitHref("my book#1_data", { chapter_order: 3, occurrence_index: 2 }, "a b", false);
    expect(href).toBe("/read/my%20book%231_data/3?q=a%20b&occurrence=2");
  });

  it("encodes the chapter segment too (String, then encodeURIComponent)", () => {
    const href = searchHitHref("plain_data", { chapter_order: "1/2#x", occurrence_index: 0 }, "q", false);
    expect(href).toBe("/read/plain_data/1%2F2%23x?q=q&occurrence=0");
  });

  it("a semantic hit in semantic mode opens the chapter without q / occurrence", () => {
    const href = searchHitHref("my book#1_data", { chapter_order: 3, mode: "semantic" }, "a b", true);
    expect(href).toBe("/read/my%20book%231_data/3");
  });

  it("a keyword hit while the panel is in semantic mode still carries q / occurrence", () => {
    const href = searchHitHref("b", { chapter_order: 0, occurrence_index: 1, mode: "keyword" }, "z", true);
    expect(href).toBe("/read/b/0?q=z&occurrence=1");
  });
});

// 013 final review RV-13: a hit without a usable occurrence_index must not write
// `occurrence=NaN` into the URL. The reader (static/search.js) reads a missing `occurrence` as
// null, which the highlight API treats as "no occurrence selected"; omitting the param says that
// explicitly instead of relying on NaN surviving JSON.stringify as null.
describe("searchHitHref without a usable occurrence_index", () => {
  it("omits occurrence when occurrence_index is missing", () => {
    const href = searchHitHref("b", { chapter_order: 2 }, "z", false);
    expect(href).toBe("/read/b/2?q=z");
    expect(href).not.toContain("NaN");
  });

  it("omits occurrence when occurrence_index is a non-numeric string", () => {
    const href = searchHitHref("b", { chapter_order: 2, occurrence_index: "abc" }, "z", false);
    expect(href).toBe("/read/b/2?q=z");
  });

  it("omits occurrence when occurrence_index is an empty string (Number('') would be 0)", () => {
    const href = searchHitHref("b", { chapter_order: 2, occurrence_index: "" }, "z", false);
    expect(href).toBe("/read/b/2?q=z");
  });

  it("still carries a numeric-string occurrence_index", () => {
    const href = searchHitHref("b", { chapter_order: 2, occurrence_index: "4" }, "z", false);
    expect(href).toBe("/read/b/2?q=z&occurrence=4");
  });
});
