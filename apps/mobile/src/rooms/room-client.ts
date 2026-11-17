// The room API over the network, with the guest session's token. Null when
// this build has no server configured: the app then has no real rooms.
import { createApiClient } from "@sajao/api-client";
import { uuidV4 } from "@/capture/package/upload-capture";
import { configResult } from "@/config";
import type { RoomApi, RoomJob } from "./room-api";

export function roomApi(): RoomApi | null {
  const config = configResult.ok ? configResult.config : null;
  if (!config?.apiUrl || !config.supabase) return null;
  const supabase = config.supabase;
  const client = createApiClient({ baseUrl: config.apiUrl, newIdempotencyKey: uuidV4 });
  client.use({
    async onRequest({ request }) {
      // Loaded on first use, so screens that never reach the server do not load the auth library.
      const { guestAccessToken } = await import("@/auth/guest-session");
      request.headers.set("Authorization", `Bearer ${await guestAccessToken(supabase)}`);
      return request;
    },
  });
  const ok = <T>(result: { data?: T; response: Response }, what: string): T => {
    if (!result.response.ok || result.data === undefined) {
      throw new Error(`${what} failed with ${result.response.status}`);
    }
    return result.data;
  };
  return {
    async createRoom(captureId): Promise<RoomJob> {
      return ok(
        await client.POST("/v1/rooms", {
          body: { capture_id: captureId },
          // The capture id makes a repeat of this call the same request.
          headers: { "Idempotency-Key": `room-${captureId}` },
        }),
        "Creating the room",
      );
    },
    async getRoom(roomId): Promise<RoomJob> {
      return ok(
        await client.GET("/v1/rooms/{room_id}", { params: { path: { room_id: roomId } } }),
        "Reading the room",
      );
    },
    async getTwin(roomId): Promise<unknown> {
      return ok(
        await client.GET("/v1/rooms/{room_id}/twin", { params: { path: { room_id: roomId } } }),
        "Reading the room's twin",
      );
    },
  };
}
