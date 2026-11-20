import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useMemo } from "react";
import type { TakenPhoto } from "@/photos/photo-session";
import { afterAdding, flowRoute } from "@/rooms/flow";
import { addPhotosToRoom, startPhotoRoom, takenPhotosOf } from "@/rooms/media-import";
import { useRoomJobs } from "@/state/room-jobs";
import { TakePhotosScreen } from "@/screens/take-photos";
import { useTaste } from "@/state/taste";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

/**
 * Add a room: take one to three photos of it. With a room: add a photo to
 * that room (it keeps the photos it has), which measures it again.
 */
export default function PhotosRoute() {
  const router = useRouter();
  const { room: existing } = useLocalSearchParams<{ room?: string }>();
  const initialPhotos = useMemo(() => (existing ? takenPhotosOf(existing) : []), [existing]);
  const onDone = useCallback(
    (photos: TakenPhoto[]) => {
      if (existing) {
        // The same room: its budget is known, so straight on to the stages.
        addPhotosToRoom(existing, photos);
        useRoomJobs.getState().clearJob(existing);
        router.replace({ pathname: "/generating", params: { room: existing } });
        return;
      }
      // The photos become a room on My home and start uploading; the
      // questions are asked meanwhile, then the stages.
      const room = startPhotoRoom(photos);
      const step = afterAdding({ hasTaste: useTaste.getState().answers !== null });
      router.replace(flowRoute(step, room));
    },
    [router, existing],
  );
  return (
    <TakePhotosScreen
      onDone={onDone}
      onClose={() => router.back()}
      // Adding to a room is photos taken here; a gallery pick makes a new room.
      onUsePhotos={existing ? () => router.back() : () => router.replace("/import")}
      initialPhotos={initialPhotos}
    />
  );
}
