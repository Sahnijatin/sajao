import type { BottomSheetProps } from "@expo/ui";
import { presentationCornerRadius } from "@expo/ui/swift-ui/modifiers";

/** iOS: set the sheet's corner radius. This import is iOS-only, hence the split file. */
export function sheetModifiers(cornerRadius: number): NonNullable<BottomSheetProps["modifiers"]> {
  return [presentationCornerRadius(cornerRadius)];
}
