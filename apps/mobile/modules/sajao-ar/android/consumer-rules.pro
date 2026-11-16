# Applied to any app that uses this module when its release build shrinks and
# renames code (R8). Without these the object detector fails to load with
# "RuntimeException: Field ..._ for ... not found. Known fields are [...]".

# MediaPipe Tasks: its native library finds Java classes, methods and fields
# by name, so none of them may be renamed or removed.
-keep class com.google.mediapipe.** { *; }
-keep interface com.google.mediapipe.** { *; }

# MediaPipe's options are protobuf-lite messages, which read their own fields
# by name at run time.
-keepclassmembers class * extends com.google.protobuf.GeneratedMessageLite {
  <fields>;
}

# Referenced by MediaPipe but not shipped in its Android library; never used at run time.
-dontwarn com.google.mediapipe.proto.CalculatorProfileProto$CalculatorProfile
-dontwarn com.google.mediapipe.proto.GraphTemplateProto$CalculatorGraphTemplate
-dontwarn javax.annotation.processing.**
-dontwarn javax.lang.model.**
-dontwarn com.google.auto.value.**
