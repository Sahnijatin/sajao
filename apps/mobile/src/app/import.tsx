import { useRouter } from "expo-router";
import { afterAdding, flowRoute } from "@/rooms/flow";
import { ImportMediaScreen } from "@/screens/import-media";
import { useTaste } from "@/state/taste";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

/** Add a room from photos or a video already on the phone. */
export default function ImportRoute() {
  const router = useRouter();
  return (
    <ImportMediaScreen
      onTakePhotos={() => router.replace("/photos")}
      // The new room is on My home and uploading: the questions, then its stages.
      onImported={(room) =>
        router.replace(
          flowRoute(afterAdding({ hasTaste: useTaste.getState().answers !== null }), room),
        )
      }
    />
  );
}
