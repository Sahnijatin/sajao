import { useRouter } from "expo-router";
import { useCallback } from "react";
import type { TakenPhoto } from "@/photos/photo-session";
import { afterReview } from "@/rooms/flow";
import { startPhotoRoom } from "@/rooms/media-import";
import { roomSpaceProfile } from "@/rooms/room-space";
import { TakePhotosScreen } from "@/screens/take-photos";
import { useTaste } from "@/state/taste";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

const ROUTES = {
  space: "/space",
  taste: "/taste",
  budget: "/budget",
  generating: "/generating",
} as const;

/** Add a room: take one to three photos of it. */
export default function PhotosRoute() {
  const router = useRouter();
  const onDone = useCallback(
    (photos: TakenPhoto[]) => {
      // The photos become a room on My home and start uploading; then on to
      // what we found, taste the first time, and the stages.
      const room = startPhotoRoom(photos);
      const step = afterReview({
        hasSpaceProfile: roomSpaceProfile(room) !== null,
        hasTaste: useTaste.getState().answers !== null,
      });
      router.replace({ pathname: ROUTES[step], params: { room } });
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
