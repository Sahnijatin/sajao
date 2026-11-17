import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { designsOffered, hasAreas, roomContent } from "@/rooms/room-content";
import { AreasScreen } from "@/screens/areas";
import { useRooms } from "@/state/rooms";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

/** After the room is measured, for a scan of several areas: which one to redesign. */
export default function AreasRoute() {
  const router = useRouter();
  const { room, next } = useLocalSearchParams<{ room?: string; next?: "reveal" | "room" }>();
  if (!room) return <Redirect href="/" />;
  const toRoom = { pathname: "/room/[id]", params: { id: room } } as const;
  const content = roomContent(room);
  // Nothing to choose between: the room screen takes it from here.
  if (!content || !hasAreas(content)) return <Redirect href={toRoom} />;
  const chosenId = useRooms.getState().rooms.find((each) => each.id === room)?.redesignAreaId;
  return (
    <AreasScreen
      areas={content.areas}
      chosenId={chosenId ?? null}
      onChoose={(areaId) => {
        useRooms.getState().setRedesignArea(room, areaId);
        const area = content.areas.find((each) => each.id === areaId);
        // The reveal is for an area with designs to show; otherwise straight to the room.
        const reveal = next === "reveal" && area && designsOffered(area.spaceType);
        router.replace(reveal ? { pathname: "/reveal", params: { room } } : toRoom);
      }}
    />
  );
}
