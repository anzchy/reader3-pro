// 013 WI-11 A11.2 (ET-10), case C11.05: `debug.*` is gated on localStorage["reader3.debug"].
// Unset (or any value other than "1") means zero console output; "1" means exactly one
// console call per debug call, with the arguments passed through untouched.
import fc from "fast-check";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";

import { debug, DEBUG_STORAGE_KEY } from "@shared/debug";

const LEVELS = ["log", "verbose"] as const;
type Level = (typeof LEVELS)[number];
type ConsoleMethod = "log" | "info" | "debug" | "warn" | "error" | "trace";
const CONSOLE_METHODS: ConsoleMethod[] = ["log", "info", "debug", "warn", "error", "trace"];

let spies: Record<ConsoleMethod, MockInstance>;

function totalConsoleCalls(): number {
  return CONSOLE_METHODS.reduce((n, m) => n + spies[m].mock.calls.length, 0);
}

function allCalls(): unknown[][] {
  return CONSOLE_METHODS.flatMap((m) => spies[m].mock.calls as unknown[][]);
}

beforeEach(() => {
  localStorage.clear();
  spies = Object.fromEntries(
    CONSOLE_METHODS.map((m) => [m, vi.spyOn(console, m).mockImplementation(() => undefined)]),
  ) as unknown as Record<ConsoleMethod, MockInstance>;
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("debug gate (A11.2)", () => {
  it("uses the storage key reader3.debug", () => {
    expect(DEBUG_STORAGE_KEY).toBe("reader3.debug");
  });

  it.each(LEVELS)("debug.%s with the key unset produces no console output", (level) => {
    debug[level]("hello", 1, { a: 1 });
    expect(totalConsoleCalls()).toBe(0);
  });

  it.each(LEVELS)("debug.%s with the key set to 1 produces output", (level) => {
    localStorage.setItem(DEBUG_STORAGE_KEY, "1");
    debug[level]("hello");
    expect(totalConsoleCalls()).toBe(1);
  });

  it("never writes through console.log (the only sanctioned sinks are info and debug)", () => {
    localStorage.setItem(DEBUG_STORAGE_KEY, "1");
    debug.log("x");
    debug.verbose("y");
    expect(spies.log).not.toHaveBeenCalled();
  });

  it("reads the key on every call, not once at import", () => {
    debug.log("before");
    expect(totalConsoleCalls()).toBe(0);
    localStorage.setItem(DEBUG_STORAGE_KEY, "1");
    debug.log("during");
    expect(totalConsoleCalls()).toBe(1);
    localStorage.removeItem(DEBUG_STORAGE_KEY);
    debug.log("after");
    expect(totalConsoleCalls()).toBe(1);
  });

  it("stays silent when localStorage itself throws (sandboxed or storage-disabled contexts)", () => {
    localStorage.setItem(DEBUG_STORAGE_KEY, "1");
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    expect(() => debug.log("x")).not.toThrow();
    expect(totalConsoleCalls()).toBe(0);
    getItem.mockRestore();
  });

  it("holds for arbitrary argument lists and key values (C11.05)", () => {
    const keyValue = fc.option(fc.constantFrom("1", "0", "true", "", "yes", " 1", "1 "), { nil: null });
    fc.assert(
      fc.property(
        fc.array(fc.anything(), { maxLength: 6 }),
        keyValue,
        fc.constantFrom<Level>(...LEVELS),
        (args, key, level) => {
          vi.clearAllMocks();
          localStorage.clear();
          if (key !== null) localStorage.setItem(DEBUG_STORAGE_KEY, key);
          debug[level](...args);
          const expected = key === "1" ? 1 : 0;
          expect(totalConsoleCalls()).toBe(expected);
          if (expected === 1) {
            const [call] = allCalls();
            expect(call.length).toBe(args.length);
            call.forEach((arg, i) => expect(Object.is(arg, args[i])).toBe(true));
          }
        },
      ),
      { numRuns: 300 },
    );
  });
});
