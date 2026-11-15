import type { BottomSheetProps } from "@expo/ui";

/** Android: the Material sheet keeps its own corner shape. */
export function sheetModifiers(_cornerRadius: number): NonNullable<BottomSheetProps["modifiers"]> {
  return [];
}
