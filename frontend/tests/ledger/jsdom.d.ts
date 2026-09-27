// Minimal typing for the slice of the `jsdom` API that feature-ledger-page.test.ts
// uses. jsdom ships no .d.ts and @types/jsdom is not a devDependency; declaring
// only what is called keeps the typecheck honest without adding a package.
declare module "jsdom" {
  export class VirtualConsole {
    on(event: "jsdomError" | "error", listener: (e: unknown) => void): this;
  }
  export interface ConstructorOptions {
    runScripts?: "dangerously" | "outside-only";
    url?: string;
    virtualConsole?: VirtualConsole;
  }
  export class JSDOM {
    constructor(html?: string, options?: ConstructorOptions);
    readonly window: Window & typeof globalThis & { __xss?: unknown };
  }
}
