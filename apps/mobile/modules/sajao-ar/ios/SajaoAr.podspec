Pod::Spec.new do |s|
  s.name           = 'SajaoAr'
  s.version        = '0.1.0'
  s.summary        = 'AR-anchored room scan: world tracking, scene mesh, live object labels'
  s.description    = 'ARKit world tracking with plane detection and, on LiDAR phones, the classified scene mesh, plus an on-device object detector with labels pinned in 3D.'
  s.license        = 'UNLICENSED'
  s.author         = 'Sajao'
  s.homepage       = 'https://sajao.app'
  s.platforms      = { :ios => '16.4' }
  s.source         = { git: '' }
  s.static_framework = true

  s.dependency 'ExpoModulesCore'
  # Apache 2.0. Pinned: the 0.10 Swift API is the one this module is written against.
  s.dependency 'MediaPipeTasksVision', '0.10.33'

  s.frameworks = 'ARKit', 'SceneKit', 'AVFoundation', 'CoreImage'
  s.source_files = '**/*.{h,m,swift}'
  # EfficientDet-Lite0 (COCO), Apache 2.0. Shared with the Android module.
  s.resource_bundles = { 'SajaoArAssets' => ['Assets/*.tflite'] }
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    # CocoaPods passes MediaPipe's copied static frameworks as header paths
    # only; Swift needs them as framework paths to import the modules.
    'FRAMEWORK_SEARCH_PATHS' => '$(inherited) "${PODS_XCFRAMEWORKS_BUILD_DIR}/MediaPipeTasksVision" "${PODS_XCFRAMEWORKS_BUILD_DIR}/MediaPipeTasksCommon"'
  }
end
