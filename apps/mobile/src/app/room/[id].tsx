import { Redirect, Stack, useLocalSearchParams, useRouter } from "expo-router";
import { useTranslation } from "react-i18next";
import { roomName } from "@/rooms/room-card";
import { useEffect } from "react";
import { designsOffered, useRoomContent } from "@/rooms/room-content";
import { loadRoomContent, retryRoomJob, startRoomJob } from "@/rooms/room-source";
import { useRoomData } from "@/state/room-data";
import { useRoomJobs } from "@/state/room-jobs";
import { getArCapabilities } from "../../../modules/sajao-ar";
import { RoomScreen, RoomWaiting } from "@/screens/room";
import { useRooms, useRoomsLoaded } from "@/state/rooms";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

export default function RoomRoute() {
  const { t } = useTranslation();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const loaded = useRoomsLoaded();
  const room = useRooms((state) => state.rooms.find((each) => each.id === id));
  const content = useRoomContent(id);
  const job = useRoomJobs((state) => state.jobs[id]);
  // A real room's content is read when the room is opened; a room with
  // nothing yet has its job followed here, so its stages show.
  useEffect(() => {
    void loadRoomContent(id).then(() => {
      const now = useRoomData.getState().content[id];
      const designsMissing = now && now.looks.length === 0 && designsOffered(now.spaceType);
      const known = useRoomJobs.getState().jobs[id];
      if ((!now || designsMissing) && !known) startRoomJob(id);
    });
  }, [id]);
  const retry = () => void retryRoomJob(id);
  const addPhoto = () => router.push({ pathname: "/photos", params: { room: id } });
  if (!loaded) return null;
  // A link to a room that is not on this phone goes to My home.
  if (!room) return <Redirect href="/" />;
  return (
    <>
      <Stack.Screen options={{ title: roomName(room, t) }} />
      {content ? (
        <RoomScreen
          content={content}
          redesignAreaId={room.redesignAreaId ?? null}
          remeasuring={Boolean(room.remeasure)}
          job={job}
          onRetry={retry}
          onAddPhoto={addPhoto}
          onChooseArea={() => router.push({ pathname: "/areas", params: { room: id } })}
          // "Measure this room for exact fit": the AR scan, on a phone that can run it.
          // The two-tape-value step joins it once the API takes tape values for a room.
          onMeasure={
            getArCapabilities().arSupported && !room.remeasure
              ? () => router.push({ pathname: "/capture", params: { room: id } })
              : undefined
          }
        />
      ) : (
        <RoomWaiting job={job} onRetry={retry} onAddPhoto={addPhoto} />
      )}
    </>
  );
}
