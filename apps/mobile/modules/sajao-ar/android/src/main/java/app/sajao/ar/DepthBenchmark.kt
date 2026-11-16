package app.sajao.ar

import android.content.Context
import android.os.Build
import android.os.PowerManager
import android.os.SystemClock
import android.util.Log
import org.tensorflow.lite.Interpreter
import org.tensorflow.lite.gpu.CompatibilityList
import org.tensorflow.lite.gpu.GpuDelegate
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.random.Random

/**
 * Measures on-device depth speed before anything is built on it (decision:
 * reverse "surface effect without a depth model", pending this number).
 * Runs Depth Anything V2 Small (Apache 2.0), converted to LiteRT at small
 * fixed inputs, on the CPU (XNNPACK, 4 threads) and on the GPU delegate,
 * and reports milliseconds per frame. Measurement only: no output is used.
 */
object DepthBenchmark {
  /** Bundled models: input width by height, portrait, multiples of the model's 14 px patch. */
  val MODELS = listOf("depth_anything_v2_small_196x252.tflite", "depth_anything_v2_small_266x350.tflite")

  private const val WARMUP = 3

  fun run(context: Context, runs: Int): Map<String, Any> {
    val result = LinkedHashMap<String, Any>()
    result["device"] = "${Build.MANUFACTURER} ${Build.MODEL}"
    result["soc"] = if (Build.VERSION.SDK_INT >= 31) "${Build.SOC_MANUFACTURER} ${Build.SOC_MODEL}" else "unknown"
    result["thermalBefore"] = thermal(context)
    val models = ArrayList<Map<String, Any>>()
    for (name in MODELS) {
      val model = try {
        load(context, name)
      } catch (error: Throwable) {
        models.add(mapOf("model" to name, "error" to "not bundled: ${error.message}"))
        continue
      }
      val entry = LinkedHashMap<String, Any>()
      entry["model"] = name
      entry["cpu"] = time(model, runs, gpu = false)
      entry["gpu"] = time(model, runs, gpu = true)
      models.add(entry)
      Log.i(Detector.TAG, "depth benchmark $entry")
    }
    result["models"] = models
    result["thermalAfter"] = thermal(context)
    return result
  }

  private fun load(context: Context, name: String): ByteBuffer {
    val bytes = context.assets.open(name).use { it.readBytes() }
    return ByteBuffer.allocateDirect(bytes.size).order(ByteOrder.nativeOrder()).apply {
      put(bytes)
      rewind()
    }
  }

  /** Median and 90th percentile milliseconds per frame, or why the backend could not run. */
  private fun time(model: ByteBuffer, runs: Int, gpu: Boolean): String {
    var delegate: GpuDelegate? = null
    return try {
      val options = Interpreter.Options()
      if (gpu) {
        val compatibility = CompatibilityList()
        if (!compatibility.isDelegateSupportedOnThisDevice) return "GPU delegate not supported on this phone"
        delegate = GpuDelegate(compatibility.bestOptionsForThisDevice)
        options.addDelegate(delegate)
      } else {
        options.setNumThreads(4)
      }
      model.rewind()
      Interpreter(model, options).use { interpreter ->
        val input = interpreter.getInputTensor(0)
        val output = interpreter.getOutputTensor(0)
        val inBuffer = ByteBuffer.allocateDirect(input.numBytes()).order(ByteOrder.nativeOrder())
        val random = Random(7)
        while (inBuffer.remaining() >= 4) inBuffer.putFloat(random.nextFloat())
        val outBuffer = ByteBuffer.allocateDirect(output.numBytes()).order(ByteOrder.nativeOrder())
        val times = ArrayList<Double>()
        repeat(WARMUP + runs) { index ->
          inBuffer.rewind()
          outBuffer.rewind()
          val started = SystemClock.elapsedRealtimeNanos()
          interpreter.run(inBuffer, outBuffer)
          val ms = (SystemClock.elapsedRealtimeNanos() - started) / 1e6
          if (index >= WARMUP) times.add(ms)
        }
        times.sort()
        val median = times[times.size / 2]
        val p90 = times[(times.size * 9) / 10]
        "median %.0f ms, p90 %.0f ms (%.1f a second), input %s".format(
          median, p90, 1000 / median, input.shape().joinToString("x"),
        )
      }
    } catch (error: Throwable) {
      "error: ${error.javaClass.simpleName}: ${error.message ?: ""}".take(160)
    } finally {
      delegate?.close()
    }
  }

  private fun thermal(context: Context): String {
    if (Build.VERSION.SDK_INT < 29) return "unknown"
    val power = context.getSystemService(Context.POWER_SERVICE) as? PowerManager ?: return "unknown"
    return when (power.currentThermalStatus) {
      PowerManager.THERMAL_STATUS_NONE -> "none"
      PowerManager.THERMAL_STATUS_LIGHT -> "light"
      PowerManager.THERMAL_STATUS_MODERATE -> "moderate"
      PowerManager.THERMAL_STATUS_SEVERE -> "severe"
      else -> "critical"
    }
  }
}
