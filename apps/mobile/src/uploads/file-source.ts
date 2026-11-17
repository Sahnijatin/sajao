// A local file as an upload source: its size, and any range of its bytes
// read from disk on demand, so a large scan video is never held in memory.
import { File, Paths } from "expo-file-system";
import {
  type MediaKind,
  PartUrlExpiredError,
  type PutFile,
  type UploadSource,
} from "./resumable-upload";

export function fileSource(uri: string, kind: MediaKind, contentType: string): UploadSource {
  const file = new File(uri);
  if (!file.exists) throw new Error("The file to upload is missing");
  return {
    kind,
    contentType,
    sizeBytes: file.size,
    uri,
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

/**
 * PUT a whole file to its signed URL through the phone's transfer service.
 * On iOS that is a background session: the transfer carries on after the app
 * is suspended, and its result is delivered when the app runs again.
 */
export const putFile: PutFile = async (url, uri) => {
  const result = await new File(uri).upload(url, { httpMethod: "PUT", sessionType: "background" });
  if (result.status === 403) throw new PartUrlExpiredError();
  const etag = Object.entries(result.headers).find(([name]) => name.toLowerCase() === "etag")?.[1];
  if (result.status < 200 || result.status >= 300 || !etag) {
    throw new Error(`File upload failed with ${result.status}`);
  }
  return etag;
};
