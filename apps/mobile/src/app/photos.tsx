import { useRouter } from "expo-router";
import { useCallback } from "react";
import type { TakenPhoto } from "@/photos/photo-session";
import { afterAdding, flowRoute } from "@/rooms/flow";
import { startPhotoRoom } from "@/rooms/media-import";
import { TakePhotosScreen } from "@/screens/take-photos";
import { useTaste } from "@/state/taste";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

/** Add a room: take one to three photos of it. */
export default function PhotosRoute() {
  const router = useRouter();
  const onDone = useCallback(
    (photos: TakenPhoto[]) => {
      // The photos become a room on My home and start uploading; the
      // questions are asked meanwhile, then the stages.
      const room = startPhotoRoom(photos);
      const step = afterAdding({ hasTaste: useTaste.getState().answers !== null });
      router.replace(flowRoute(step, room));
    },
    [router],
  );
  return (
    <TakePhotosScreen
      onDone={onDone}
      onClose={() => router.back()}
      onUsePhotos={() => router.replace("/import")}
    />
  );
}
