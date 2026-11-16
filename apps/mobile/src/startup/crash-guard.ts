// Startup must fail safe. A missing config value, a missing native module or
// any other uncaught error shows an error screen instead of closing the app.
//
// Everything caught here also goes to the crash reporter, once one is set.

export interface CaughtError {
  message: string;
  /** Where it was caught: "render", "global" or "config". */
  source: string;
  stack?: string;
}

type Reporter = (error: unknown, context: { source: string; fatal: boolean }) => void;
type Listener = () => void;

let reporter: Reporter = () => {};
let fatal: CaughtError | null = null;
const listeners = new Set<Listener>();

/** Plug in the crash reporter (Sentry, once its key exists). */
export function setErrorReporter(next: Reporter): void {
  reporter = next;
}

export function describeError(error: unknown, source: string): CaughtError {
  if (error instanceof Error) {
    return {
      message: error.message || error.name,
      source,
      ...(error.stack ? { stack: error.stack } : {}),
    };
  }
  return { message: typeof error === "string" ? error : "Unknown error", source };
}

export function reportError(error: unknown, source: string, isFatal = false): CaughtError {
  const caught = describeError(error, source);
  try {
    reporter(error, { source, fatal: isFatal });
  } catch {
    // A broken reporter must never turn a handled error into a crash.
  }
  return caught;
}

export function getFatalError(): CaughtError | null {
  return fatal;
}

export function subscribeToFatalError(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function clearFatalError(): void {
  fatal = null;
  for (const listener of listeners) listener();
}

interface ErrorUtilsLike {
  getGlobalHandler(): (error: unknown, isFatal?: boolean) => void;
  setGlobalHandler(handler: (error: unknown, isFatal?: boolean) => void): void;
}

/**
 * Catch errors thrown outside React rendering (event handlers, timers,
 * promises that reach the top). In a release build the default handler
 * closes the app; this one keeps it open and shows the error screen. In
 * development the usual red error screen still appears.
 */
export function installGlobalErrorHandler(
  errorUtils: ErrorUtilsLike | undefined = (globalThis as { ErrorUtils?: ErrorUtilsLike })
    .ErrorUtils,
  isDev: boolean = __DEV__,
): void {
  if (!errorUtils) return;
  const previous = errorUtils.getGlobalHandler();
  errorUtils.setGlobalHandler((error, isFatal) => {
    const caught = reportError(error, "global", !!isFatal);
    if (isDev) {
      previous(error, isFatal);
      return;
    }
    if (isFatal) {
      fatal = caught;
      for (const listener of listeners) listener();
    }
  });
}
