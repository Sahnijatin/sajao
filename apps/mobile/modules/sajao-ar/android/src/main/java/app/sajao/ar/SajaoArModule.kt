package app.sajao.ar

import com.google.ar.core.ArCoreApk
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import expo.modules.kotlin.records.Field
import expo.modules.kotlin.records.Record
import java.lang.ref.WeakReference

class ArLabelRecord : Record {
  @Field val id: String = ""
  @Field val text: String = ""
  @Field val x: Double = 0.0
  @Field val y: Double = 0.0
  @Field val z: Double = 0.0
}

class SajaoArModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("SajaoAr")

    Function("getCapabilities") {
      val context = appContext.reactContext
      val supported = try {
        context != null &&
          ArCoreApk.getInstance().checkAvailability(context) == ArCoreApk.Availability.SUPPORTED_INSTALLED
      } catch (_: Throwable) {
        false
      }
      mapOf(
        "platform" to "android",
        "arSupported" to supported,
        "lidar" to false,
        // Known once a session runs; the status event reports it.
        "depth" to false,
      )
    }

    OnActivityEntersBackground {
      liveViews.mapNotNull { it.get() }.forEach { it.hostPaused() }
    }

    OnActivityEntersForeground {
      liveViews.mapNotNull { it.get() }.forEach { it.hostResumed() }
    }

    View(SajaoArView::class) {
      Events("onArStatus", "onArPose", "onArDetections", "onArSurfaces")

      Prop("active") { view: SajaoArView, value: Boolean ->
        view.setActive(value)
      }
      Prop("torch") { view: SajaoArView, value: Boolean ->
        view.setTorch(value)
      }
      Prop("lite") { view: SajaoArView, value: Boolean ->
        view.lite = value
      }
      Prop("reducedMotion") { view: SajaoArView, value: Boolean ->
        view.reducedMotion = value
      }
      Prop("labels") { view: SajaoArView, value: List<ArLabelRecord> ->
        view.setLabels(value.map { ArLabel(it.id, it.text, it.x.toFloat(), it.y.toFloat(), it.z.toFloat()) })
      }
      OnViewDestroys { view: SajaoArView ->
        view.destroy()
      }
    }
  }

  companion object {
    internal val liveViews = mutableListOf<WeakReference<SajaoArView>>()
  }
}
