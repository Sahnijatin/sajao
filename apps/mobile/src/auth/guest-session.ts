// The app is guest-first: there is no sign-in gate. The first call that
// needs the server creates a guest session with the auth service and keeps
// it on the phone; later calls reuse and refresh it. A guest has a real user
// id, so their captures stay theirs if they sign in properly later.
import AsyncStorage from "@react-native-async-storage/async-storage";
import type { SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;

async function authClient(config: {
  url: string;
  publishableKey: string;
}): Promise<SupabaseClient> {
  // Loaded on first use, so screens that never reach the server do not load the auth library.
  const { createClient } = await import("@supabase/supabase-js");
  client ??= createClient(config.url, config.publishableKey, {
    auth: {
      storage: AsyncStorage,
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: false,
    },
  });
  return client;
}

/** Forget the session on this phone, after the account was erased. */
export async function signOutHere(config: { url: string; publishableKey: string }): Promise<void> {
  await (await authClient(config)).auth.signOut({ scope: "local" });
}

/** A valid access token for the API, signing in as a guest when there is no session yet. */
export async function guestAccessToken(config: {
  url: string;
  publishableKey: string;
}): Promise<string> {
  const auth = (await authClient(config)).auth;
  const existing = await auth.getSession();
  if (existing.data.session) return existing.data.session.access_token;
  const created = await auth.signInAnonymously();
  const token = created.data.session?.access_token;
  if (created.error || !token) throw new Error("Could not start a guest session");
  return token;
}
