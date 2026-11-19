import { File } from "expo-file-system";
import { accountDeps } from "@/account/account-client";
import { deleteAccount } from "@/account/delete-account";
import { ProfileScreen } from "@/screens/profile";

/** Removes a file this phone kept; a file already gone is fine. */
function removeFile(uri: string): void {
  const file = new File(uri);
  if (file.exists) file.delete();
}

export default function ProfileRoute() {
  return <ProfileScreen onDeleteAccount={() => deleteAccount(accountDeps(removeFile))} />;
}
