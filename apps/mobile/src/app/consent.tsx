import { useRouter } from "expo-router";
import { configResult } from "@/config";
import { ConsentScreen } from "@/screens/consent";
import { useConsent } from "@/state/consent";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

/** Consent at first use. Agreeing goes on to My home. */
export default function ConsentRoute() {
  const router = useRouter();
  const legal = configResult.ok ? configResult.config.legal : null;
  return (
    <ConsentScreen
      legal={legal}
      onAccept={() => {
        useConsent.getState().accept();
        router.replace("/");
      }}
    />
  );
}
