// The state of the last scan's upload, shown on the home screen: uploading
// with a count, uploaded, paused with a retry, or saved on the phone when
// this build has no server. Nothing shows before the first scan.
import { Button, Card, Text } from "@sajao/ui";
import { useTranslation } from "react-i18next";
import { startCaptureUpload } from "@/capture/package/start-upload";
import { type UploadStatus, useCaptureStore } from "@/state/capture";

/** The message key and its values for an upload state; null when there is nothing to show. */
export function uploadMessage(
  upload: UploadStatus,
): { key: string; values?: Record<string, number> } | null {
  switch (upload.state) {
    case "idle":
      return null;
    case "waiting":
      return { key: "home.upload.waiting" };
    case "uploading":
      return upload.total > 0
        ? {
            key: "home.upload.uploading",
            values: { finished: upload.finished, total: upload.total },
          }
        : { key: "home.upload.starting" };
    case "done":
      return { key: upload.videoSkipped ? "home.upload.doneNoVideo" : "home.upload.done" };
    case "failed":
      return { key: "home.upload.failed" };
  }
}

export function UploadStatus() {
  const { t } = useTranslation();
  const upload = useCaptureStore((store) => store.upload);
  const last = useCaptureStore((store) => store.last);
  const device = useCaptureStore((store) => store.device);
  const message = uploadMessage(upload);
  if (!message) return null;
  return (
    <Card testID="upload-status" accessibilityRole="summary">
      <Text variant="bodySmall">{t(message.key, message.values ?? {})}</Text>
      {upload.state === "failed" && last && device ? (
        <Button
          label={t("home.upload.retry")}
          variant="outline"
          size="small"
          // Resumes: finished files are skipped.
          onPress={() => void startCaptureUpload(last, device)}
        />
      ) : null}
    </Card>
  );
}
