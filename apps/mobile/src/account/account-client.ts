// The account calls over the network, with the guest session's token. Null
// when this build has no server: the account then lives on this phone only.
import { createApiClient } from "@sajao/api-client";
import { uuidV4 } from "@/capture/package/upload-capture";
import { configResult } from "@/config";
import type { DeleteDeps } from "./delete-account";

export function accountDeps(removeFile: DeleteDeps["removeFile"]): DeleteDeps {
  const config = configResult.ok ? configResult.config : null;
  const supabase = config?.supabase;
  if (!config?.apiUrl || !supabase) {
    return { eraseOnServer: null, signOut: async () => {}, removeFile };
  }
  const client = createApiClient({ baseUrl: config.apiUrl, newIdempotencyKey: uuidV4 });
  return {
    async eraseOnServer() {
      const { guestAccessToken } = await import("@/auth/guest-session");
      const token = await guestAccessToken(supabase);
      const { response } = await client.DELETE("/v1/me", {
        headers: { Authorization: `Bearer ${token}`, "Idempotency-Key": uuidV4() },
      });
      if (!response.ok) throw new Error(`Deleting the account failed with ${response.status}`);
    },
    async signOut() {
      const { signOutHere } = await import("@/auth/guest-session");
      await signOutHere(supabase);
    },
    removeFile,
  };
}
