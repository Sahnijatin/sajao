// Stand-in content exists so the flow can be built and reviewed before the
// room and design API serves real data. It may show in development and in
// preview builds only. A store or closed-test build never shows a sample:
// where real data is missing it shows nothing, or says it is on its way.
import { previewScreensEnabled } from "@/preview-screens";

export function samplesAllowed(): boolean {
  return previewScreensEnabled();
}
