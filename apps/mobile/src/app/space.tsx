import type { SpaceProfile } from "@sajao/schemas";
import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { afterSpace } from "@/rooms/flow";
import { roomSpaceProfile } from "@/rooms/room-space";
import { SpaceProfileScreen } from "@/screens/space-profile";
import { useTaste } from "@/state/taste";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

/** After "Looks good": what we found in this room, to confirm before the designs. */
export default function SpaceRoute() {
  const router = useRouter();
  const { room } = useLocalSearchParams<{ room?: string }>();
  const [profile, setProfile] = useState<SpaceProfile | null>(() =>
    room ? roomSpaceProfile(room) : null,
  );
  if (!room) return <Redirect href="/" />;
  const step = afterSpace({ hasTaste: useTaste.getState().answers !== null });
  const href = { pathname: step === "taste" ? "/taste" : "/generating", params: { room } } as const;
  const next = () => router.replace(href);
  // Nothing to confirm yet: carry on rather than stop on an empty screen.
  if (!profile) return <Redirect href={href} />;
  return <SpaceProfileScreen profile={profile} onChange={setProfile} onShowIdeas={next} />;
}
