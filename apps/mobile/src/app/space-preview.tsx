// Dev-only preview of the Space Profile card on sample data. The real route
// arrives when a scan produces a profile; the root layout guards this one.
import type { SpaceProfile } from "@sajao/schemas";
import { useRouter } from "expo-router";
import { useState } from "react";
import { SpaceProfileScreen } from "@/screens/space-profile";
import { setRedo } from "@/space/space-profile";
import sample from "../../../../packages/schemas/fixtures/v1/valid/space-profile.json";

export default function SpacePreviewRoute() {
  const router = useRouter();
  const [profile, setProfile] = useState(sample as unknown as SpaceProfile);
  return (
    <SpaceProfileScreen
      profile={profile}
      onChange={setProfile}
      onShowIdeas={() => router.back()}
      // Drawing around a part is not built yet: the preview picks one corner.
      onChoosePart={() =>
        setProfile((current) =>
          setRedo(current, {
            scope: "part",
            polygon: [
              { x_m: 0, y_m: 0 },
              { x_m: 2, y_m: 0 },
              { x_m: 0, y_m: 2 },
            ],
          }),
        )
      }
    />
  );
}
