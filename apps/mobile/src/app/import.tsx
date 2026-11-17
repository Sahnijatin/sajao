import { useRouter } from "expo-router";
import { ImportMediaScreen } from "@/screens/import-media";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

/** Add a room from photos or a video already on the phone. */
export default function ImportRoute() {
  const router = useRouter();
  return (
    <ImportMediaScreen
      onScan={() => router.replace("/capture")}
      // The new room is on My home; its stages show how it is getting on.
      onImported={(room) => router.replace({ pathname: "/generating", params: { room } })}
    />
  );
}
