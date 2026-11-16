// A local file as an upload source: its size, and any range of its bytes
// read from disk on demand, so a large scan video is never held in memory.
import { File, Paths } from "expo-file-system";
import type { MediaKind, UploadSource } from "./resumable-upload";

export function fileSource(uri: string, kind: MediaKind, contentType: string): UploadSource {
  const file = new File(uri);
  if (!file.exists) throw new Error("The file to upload is missing");
  return {
    kind,
    contentType,
    sizeBytes: file.size,
    async slice(start, end) {
      const handle = file.open();
      try {
        handle.offset = start;
        const bytes = await handle.readBytes(end - start);
        return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
      } finally {
        handle.close();
      }
    },
  };
}

/** Write text to a file in the cache folder and return its uri. */
export function writeCacheText(name: string, text: string): string {
  const file = new File(Paths.cache, name);
  if (file.exists) file.delete();
  file.create();
  file.write(text);
  return file.uri;
}
