// DegradeBanner base component (plan WI-1, implementation half, hosted in 013 WI-11;
// design spec §5.4). The four banner-shaped degradation states render through this.
// DEG-S5 is ConflictDialog (WI-6), not a variant here.
//
//   * tone follows the state: warn = S1 / S2 / S4, danger = S3.
//   * dismissible follows the tone: warn may be dismissed, danger never. The danger variants'
//     props type has no `dismissible: true`, and it is refused at runtime too.
//   * role="status" + aria-live="polite" on the banner itself; nothing inside re-announces.
//   * the icon is rendered by the component from the tone; callers cannot pass or hide it.
//   * body and actions are slots (nodes), not label strings; at least one action is required.
//   * dismissal removes the banner from the DOM and writes sessionStorage
//     ["reader3.degrade.<state>"]: one key per state, not per page (spec §5.4). A state
//     dismissed in this session stays absent on every later mount in the session.
//   * testids are per state (WI-1 "涉及 testid"); the -dismiss ids come from the WI-2/3/5 lists.
import "./degrade-banner.css";
export type WarnVariant = "rd-s1" | "lib-s2" | "lib-s4";
export type DangerVariant = "lib-s3" | "rd-s3";
export type DegradeVariant = WarnVariant | DangerVariant;
export type DegradeTone = "warn" | "danger";

export interface DegradeBannerSpec {
  rootTestId: string;
  dismissTestId: string | null;
  tone: DegradeTone;
  stateId: "s1" | "s2" | "s3" | "s4";
}

interface CommonOptions {
  /** The children slot: title, copy and whatever the state needs. */
  body: Node | Node[];
  /** The actions slot: at least one `.r3-btn`. */
  actions: HTMLElement[];
}

export type DegradeBannerOptions =
  | (CommonOptions & { variant: WarnVariant; dismissible?: boolean })
  | (CommonOptions & { variant: DangerVariant; dismissible?: false });

// Static testid table: the naming lint shape-checks every value in a `*TESTID*` const table.
const DEGRADE_TESTID = {
  rdS1: "rd-degrade-s1",
  rdS1Dismiss: "rd-degrade-s1-dismiss",
  libS2: "lib-degrade-s2",
  libS2Dismiss: "lib-degrade-s2-dismiss",
  libS3: "lib-degrade-s3",
  rdS3: "rd-degrade-s3",
  libS4: "lib-degrade-s4",
  libS4Dismiss: "lib-degrade-s4-dismiss",
};

const SPECS: Record<DegradeVariant, DegradeBannerSpec> = {
  "rd-s1": { rootTestId: DEGRADE_TESTID.rdS1, dismissTestId: DEGRADE_TESTID.rdS1Dismiss, tone: "warn", stateId: "s1" },
  "lib-s2": { rootTestId: DEGRADE_TESTID.libS2, dismissTestId: DEGRADE_TESTID.libS2Dismiss, tone: "warn", stateId: "s2" },
  "lib-s3": { rootTestId: DEGRADE_TESTID.libS3, dismissTestId: null, tone: "danger", stateId: "s3" },
  "rd-s3": { rootTestId: DEGRADE_TESTID.rdS3, dismissTestId: null, tone: "danger", stateId: "s3" },
  "lib-s4": { rootTestId: DEGRADE_TESTID.libS4, dismissTestId: DEGRADE_TESTID.libS4Dismiss, tone: "warn", stateId: "s4" },
};

export const DEGRADE_VARIANTS = Object.keys(SPECS) as readonly DegradeVariant[];

// Tone glyphs. Decorative (aria-hidden): the text carries the meaning.
const ICONS: Record<DegradeTone, string> = { warn: "⚠", danger: "⛔" };

export function degradeBannerSpec(variant: DegradeVariant): DegradeBannerSpec {
  return SPECS[variant];
}

function storageKey(spec: DegradeBannerSpec): string {
  return `reader3.degrade.${spec.stateId}`;
}

function isDismissed(spec: DegradeBannerSpec): boolean {
  try {
    return sessionStorage.getItem(storageKey(spec)) !== null;
  } catch {
    return false;
  }
}

function part(className: string): HTMLDivElement {
  const el = document.createElement("div");
  el.className = className;
  return el;
}

/**
 * Render the banner into `parent`. Returns the banner root, or null when this state was
 * dismissed earlier in the session (nothing is rendered then).
 */
export function mountDegradeBanner(parent: HTMLElement, options: DegradeBannerOptions): HTMLElement | null {
  const spec = SPECS[options.variant];
  const dismissible = options.dismissible === true;
  if (dismissible && spec.tone !== "warn") {
    throw new Error(`${options.variant} is a danger banner and cannot be dismissible`);
  }
  if (options.actions.length === 0) {
    throw new Error(`${options.variant} needs at least one action`);
  }
  if (isDismissed(spec)) return null;

  const root = document.createElement("section");
  root.className = `r3-degrade-banner r3-degrade-banner--${spec.tone}`;
  root.dataset.testid = spec.rootTestId;
  root.setAttribute("role", "status");
  root.setAttribute("aria-live", "polite");

  const icon = part("r3-degrade-banner__icon");
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = ICONS[spec.tone];

  const body = part("r3-degrade-banner__body");
  body.append(...(Array.isArray(options.body) ? options.body : [options.body]));

  const actions = part("r3-degrade-banner__actions");
  actions.append(...options.actions);

  root.append(icon, body, actions);

  if (dismissible && spec.dismissTestId) {
    const close = document.createElement("button");
    close.type = "button";
    close.className = "r3-degrade-banner__dismiss";
    close.dataset.testid = spec.dismissTestId;
    close.setAttribute("aria-label", "关闭");
    close.textContent = "×";
    close.addEventListener("click", () => {
      try {
        sessionStorage.setItem(storageKey(spec), "1");
      } catch {
        // Storage unavailable: the banner still closes for this page view.
      }
      root.remove();
    });
    root.append(close);
  }

  parent.append(root);
  return root;
}
