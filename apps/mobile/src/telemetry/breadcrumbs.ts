// A trail of what happened to uploads and room jobs, for working out what
// went wrong on a tester's phone. Every job state change and upload change
// leaves one breadcrumb. Kept in memory (the last few hundred), printed in
// development, and handed to crash reporting once it is installed: a crash
// report then carries the trail that led to it.

export interface Breadcrumb {
  atMs: number;
  /** "upload" or "job". */
  category: string;
  message: string;
  data?: Record<string, string | number | boolean | null>;
}

/** How many breadcrumbs are kept; older ones fall off. */
export const MAX_BREADCRUMBS = 300;

const trail: Breadcrumb[] = [];
type Sink = (crumb: Breadcrumb) => void;
let sink: Sink | null = null;

/** Leave a breadcrumb. Never throws. */
export function breadcrumb(
  category: string,
  message: string,
  data?: Breadcrumb["data"],
  atMs: number = Date.now(),
): void {
  const crumb: Breadcrumb = { atMs, category, message, ...(data ? { data } : {}) };
  trail.push(crumb);
  if (trail.length > MAX_BREADCRUMBS) trail.splice(0, trail.length - MAX_BREADCRUMBS);
  try {
    sink?.(crumb);
    if (__DEV__ && process.env.NODE_ENV !== "test") {
      console.info(`[${category}] ${message}`, data ?? "");
    }
  } catch {
    // Reporting must never break the app.
  }
}

/** The trail so far, oldest first. */
export function breadcrumbs(): readonly Breadcrumb[] {
  return trail;
}

/** Where breadcrumbs also go, such as crash reporting; null to stop. */
export function setBreadcrumbSink(next: Sink | null): void {
  sink = next;
}

/** For tests: start with an empty trail. */
export function clearBreadcrumbs(): void {
  trail.length = 0;
}
