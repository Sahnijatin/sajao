// The real upload calls, typed from the API's OpenAPI document.
import type { ApiClient } from "@sajao/api-client";
import {
  FileTooLargeError,
  PartUrlExpiredError,
  type PutPart,
  UploadGoneError,
  type UploadsApi,
} from "./resumable-upload";

class UploadApiError extends Error {}

export function uploadsApi(client: ApiClient): UploadsApi {
  return {
    async create(body) {
      const { data, response } = await client.POST("/v1/uploads", { body });
      if (response.status === 413) throw new FileTooLargeError();
      if (!data) throw new UploadApiError("Could not start the upload");
      return data;
    },
    async resume(body) {
      const { data, response } = await client.POST("/v1/uploads/resume", { body });
      if (response.status === 404) throw new UploadGoneError();
      if (!data) throw new UploadApiError("Could not resume the upload");
      return data;
    },
    async complete(body) {
      const { data, response } = await client.POST("/v1/uploads/complete", { body });
      if (response.status === 404) throw new UploadGoneError();
      if (!data) throw new UploadApiError("Could not finish the upload");
      return data;
    },
  };
}

/** PUT one part to its signed URL. The ETag in the response proves it arrived. */
export const putPart: PutPart = async (url, body) => {
  const response = await fetch(url, { method: "PUT", body });
  if (response.status === 403) throw new PartUrlExpiredError();
  const etag = response.headers.get("etag");
  if (!response.ok || !etag) throw new Error(`Part upload failed with ${response.status}`);
  return etag;
};
