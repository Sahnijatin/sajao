import ARKit
import ExpoModulesCore

struct ArLabelRecord: Record {
  @Field var id: String = ""
  @Field var text: String = ""
  @Field var x: Double = 0
  @Field var y: Double = 0
  @Field var z: Double = 0
}

public final class SajaoArModule: Module {
  public func definition() -> ModuleDefinition {
    Name("SajaoAr")

    Function("getCapabilities") { () -> [String: Any] in
      return [
        "platform": "ios",
        "arSupported": ARWorldTrackingConfiguration.isSupported,
        "lidar": ARWorldTrackingConfiguration.supportsSceneReconstruction(.meshWithClassification),
        "depth": ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth),
      ]
    }

    View(SajaoArView.self) {
      Events("onArStatus", "onArPose", "onArDetections", "onArSurfaces", "onArKeyframe")

      Prop("captureId") { (view: SajaoArView, value: String) in
        view.setCaptureId(value)
      }

      AsyncFunction("discardKeyframes") { (view: SajaoArView, uris: [String]) in
        view.discardKeyframes(uris)
      }

      AsyncFunction("finishCapture") { (view: SajaoArView, chosen: [String], promise: Promise) in
        view.finishCapture(chosen) { result in
          promise.resolve(result.mapValues { $0 ?? NSNull() })
        }
      }.runOnQueue(.main)

      Prop("active") { (view: SajaoArView, value: Bool) in
        view.setActive(value)
      }
      Prop("torch") { (view: SajaoArView, value: Bool) in
        view.setTorch(value)
      }
      Prop("lite") { (view: SajaoArView, value: Bool) in
        view.lite = value
      }
      Prop("reducedMotion") { (view: SajaoArView, value: Bool) in
        view.reducedMotion = value
      }
      Prop("labels") { (view: SajaoArView, value: [ArLabelRecord]) in
        view.setLabels(value.map { ArLabel(id: $0.id, text: $0.text, x: $0.x, y: $0.y, z: $0.z) })
      }
    }
  }
}
