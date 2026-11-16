import type { ErrorBoundaryProps } from "expo-router";
import { useMemo } from "react";
import { reportError } from "@/startup/crash-guard";
import { ErrorScreen } from "./error-screen";

/**
 * Exported as `ErrorBoundary` from layout routes. A render error in any
 * screen below shows the error screen instead of closing the app.
 */
export function RouteErrorBoundary({ error, retry }: ErrorBoundaryProps) {
  const caught = useMemo(() => reportError(error, "render", true), [error]);
  return <ErrorScreen error={caught} onRetry={() => void retry()} />;
}
