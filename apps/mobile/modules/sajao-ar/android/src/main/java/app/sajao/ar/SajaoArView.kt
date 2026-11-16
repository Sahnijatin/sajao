package app.sajao.ar

import android.content.Context
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import android.opengl.Matrix
import android.os.SystemClock
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.widget.FrameLayout
import android.widget.TextView
import com.google.ar.core.Config
import com.google.ar.core.Coordinates2d
import com.google.ar.core.Frame
import com.google.ar.core.Plane
import com.google.ar.core.Session
import com.google.ar.core.TrackingFailureReason
import com.google.ar.core.TrackingState
import expo.modules.kotlin.AppContext
import expo.modules.kotlin.viewevent.EventDispatcher
import expo.modules.kotlin.views.ExpoView
import java.lang.ref.WeakReference
import java.nio.FloatBuffer
import java.util.concurrent.atomic.AtomicReference
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10
import kotlin.math.asin
import kotlin.math.atan2

data class ArLabel(val id: String, val text: String, val x: Float, val y: Float, val z: Float)

/**
 * The live AR scan on Android. ARCore world tracking renders the camera and a
 * mapping overlay anchored to the room: detected planes drawn as glowing
 * meshes plus world-anchored feature points, with depth used for hit tests
 * where the phone supports it. An on-device detector names objects; their
 * positions are hit-tested into the scene and sent to JavaScript, which
 * decides the labels and sends them back to be pinned here. Nothing drawn
 * here sets a dimension.
 */
class SajaoArView(context: Context, appContext: AppContext) :
  ExpoView(context, appContext), GLSurfaceView.Renderer {

  private val onArStatus by EventDispatcher()
  private val onArPose by EventDispatcher()
  private val onArDetections by EventDispatcher()

  var lite = false
  var reducedMotion = false

  private val container = FrameLayout(context)
  private val surface = GLSurfaceView(context)
  private val labelLayer = FrameLayout(context)
  private val labelViews = HashMap<String, TextView>()
  @Volatile private var labels: List<ArLabel> = emptyList()

  private var session: Session? = null
  private var depthSupported = false
  private var wantsActive = false
  private var running = false
  private var hostInForeground = true
  @Volatile private var torchOn = false
  @Volatile private var torchDirty = false
  @Volatile private var displayDirty = true
  private var viewWidth = 0
  private var viewHeight = 0

  private val background = CameraBackground()
  private val shapes = WorldShapes()
  private val detector by lazy { Detector(context) }

  private val view = FloatArray(16)
  private val projection = FloatArray(16)
  private val viewProjection = FloatArray(16)

  // Feature points kept in world space, keyed by ARCore's id.
  private val pointCloud = LinkedHashMap<Int, FloatArray>()
  private var pointBuffer: FloatBuffer = Gl.floats(3)
  private var pointCount = 0
  private val maxPoints = 5000

  // When each plane last grew, for the brief brighten.
  private val planeArea = HashMap<Plane, Float>()
  // The last world outline of every plane seen, kept while ARCore stops tracking it.
  private val planeOutlines = LinkedHashMap<Plane, PlaneOutline>()
  private val planeGrewAt = HashMap<Plane, Long>()

  private var lastPoseAt = 0L
  private var lastStatusAt = 0L
  private var lastPointsAt = 0L
  // Paces AR frames to the detector: a steady 8 a second while it keeps up.
  private val pacer = FramePacer()
  private var lastCameraTimestamp = 0L
  @Volatile private var detectionsDone = 0
  // Detections the detector returned, and how many of them were placed in
  // the room: tells "detector sees nothing" apart from "nothing to hit".
  private var detectionsFound = 0
  private var detectionsPlaced = 0
  @Volatile private var lastDetectionMs = 0.0
  // Detections waiting for the next drawn frame to be hit-tested. Calling
  // session.update() anywhere but onDrawFrame takes a camera frame away from
  // the renderer, so results wait here instead.
  private val pendingDetections = AtomicReference<List<UprightDetection>?>(null)
  private var brightness = 128.0
  private var pixelIntensity = 1.0
  private var featureCount = 0
  private var trackingName = "initializing"
  private var planeCount = 0

  init {
    container.layoutParams = LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT)
    addView(container)
    surface.preserveEGLContextOnPause = true
    surface.setEGLContextClientVersion(2)
    surface.setEGLConfigChooser(8, 8, 8, 8, 16, 0)
    surface.setRenderer(this)
    surface.renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
    container.addView(surface, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
    container.addView(labelLayer, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
    SajaoArModule.liveViews.add(WeakReference(this))
  }

  override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
    super.onLayout(changed, l, t, r, b)
    container.layout(0, 0, r - l, b - t)
    container.measure(
      MeasureSpec.makeMeasureSpec(r - l, MeasureSpec.EXACTLY),
      MeasureSpec.makeMeasureSpec(b - t, MeasureSpec.EXACTLY),
    )
    container.layout(0, 0, r - l, b - t)
  }

  // region Props and lifecycle

  fun setActive(active: Boolean) {
    wantsActive = active
    if (active) resume() else pause()
  }

  fun setTorch(on: Boolean) {
    torchOn = on
    torchDirty = true
  }

  fun setLabels(next: List<ArLabel>) {
    labels = next
    val ids = next.map { it.id }.toSet()
    labelViews.keys.filter { it !in ids }.forEach { id ->
      labelViews.remove(id)?.let { labelLayer.removeView(it) }
    }
    for (label in next) {
      val existing = labelViews[label.id]
      if (existing != null) {
        if (existing.text != label.text) existing.text = label.text
      } else {
        val chip = glassLabel(label.text)
        chip.alpha = 0f
        labelLayer.addView(chip, FrameLayout.LayoutParams(FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT))
        labelViews[label.id] = chip
      }
    }
  }

  fun hostPaused() {
    hostInForeground = false
    pause()
  }

  fun hostResumed() {
    hostInForeground = true
    if (wantsActive) resume()
  }

  fun destroy() {
    pause()
    session?.close()
    session = null
    detector.close()
  }

  override fun onDetachedFromWindow() {
    pause()
    super.onDetachedFromWindow()
  }

  override fun onAttachedToWindow() {
    super.onAttachedToWindow()
    if (wantsActive) resume()
  }

  private fun resume() {
    if (running || !hostInForeground || !isAttachedToWindow) return
    try {
      val current = session ?: Session(context).also { created ->
        val config = Config(created)
        config.planeFindingMode = Config.PlaneFindingMode.HORIZONTAL_AND_VERTICAL
        config.lightEstimationMode = Config.LightEstimationMode.AMBIENT_INTENSITY
        config.updateMode = Config.UpdateMode.LATEST_CAMERA_IMAGE
        config.focusMode = Config.FocusMode.AUTO
        depthSupported = created.isDepthModeSupported(Config.DepthMode.AUTOMATIC)
        if (depthSupported) config.depthMode = Config.DepthMode.AUTOMATIC
        created.configure(config)
        session = created
      }
      current.resume()
      surface.onResume()
      running = true
      displayDirty = true
      torchDirty = true
    } catch (error: Throwable) {
      running = false
      emitStatus(mapOf("tracking" to "notAvailable", "error" to (error.message ?: "AR could not start")))
    }
  }

  private fun pause() {
    if (!running) return
    running = false
    surface.onPause()
    try {
      session?.pause()
    } catch (_: Throwable) {
    }
  }

  // endregion

  // region GL thread

  override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
    GLES20.glClearColor(0f, 0f, 0f, 1f)
    background.create()
    shapes.create()
    session?.setCameraTextureName(background.textureId)
  }

  override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
    GLES20.glViewport(0, 0, width, height)
    viewWidth = width
    viewHeight = height
    displayDirty = true
  }

  override fun onDrawFrame(gl: GL10?) {
    GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT or GLES20.GL_DEPTH_BUFFER_BIT)
    val session = session ?: return
    if (!running) return
    try {
      session.setCameraTextureName(background.textureId)
      if (displayDirty && viewWidth > 0) {
        session.setDisplayGeometry(display?.rotation ?: 0, viewWidth, viewHeight)
        displayDirty = false
      }
      if (torchDirty) {
        torchDirty = false
        applyTorch(session)
      }
      val frame = session.update()
      background.draw(frame)
      val camera = frame.camera
      trackingName = when (camera.trackingState) {
        TrackingState.TRACKING -> "normal"
        TrackingState.PAUSED ->
          if (camera.trackingFailureReason == TrackingFailureReason.NONE) "initializing" else "limited"
        else -> "notAvailable"
      }
      frame.lightEstimate?.let { estimate ->
        if (estimate.state == com.google.ar.core.LightEstimate.State.VALID) {
          pixelIntensity = estimate.pixelIntensity.toDouble()
        }
      }
      val now = SystemClock.uptimeMillis()
      if (camera.trackingState == TrackingState.TRACKING) {
        camera.getViewMatrix(view, 0)
        camera.getProjectionMatrix(projection, 0, 0.05f, 50f)
        Matrix.multiplyMM(viewProjection, 0, projection, 0, view, 0)
        if (now - lastPointsAt > 200) {
          lastPointsAt = now
          accumulatePoints(frame)
        }
        drawPlanes(session, now)
        drawPoints()
        projectLabels()
      }
      if (now - lastPoseAt > 100) {
        lastPoseAt = now
        sendPose(frame)
      }
      if (now - lastStatusAt > 250) {
        lastStatusAt = now
        sendStatus(session)
      }
      pendingDetections.getAndSet(null)?.let { found ->
        if (camera.trackingState == TrackingState.TRACKING) hitTestDetections(frame, found)
      }
      // The detector is fed from ARCore's own camera images: ARCore owns the
      // camera during the scan. Only a new image counts; update() can return
      // the same one again when the screen draws faster than the camera.
      val cameraTimestamp = frame.timestamp
      if (cameraTimestamp != lastCameraTimestamp && detector.isAvailable) {
        lastCameraTimestamp = cameraTimestamp
        if (pacer.shouldSubmit(cameraTimestamp / 1e9, detector.isBusy) &&
          camera.trackingState == TrackingState.TRACKING
        ) {
          runDetector(frame)
        }
      }
    } catch (_: Throwable) {
      // A dropped frame is fine; the next one tries again.
    }
  }

  private fun applyTorch(session: Session) {
    try {
      val config = session.config
      config.flashMode = if (torchOn) Config.FlashMode.TORCH else Config.FlashMode.OFF
      session.configure(config)
    } catch (_: Throwable) {
      // Not every phone allows the torch during AR.
    }
  }

  private fun accumulatePoints(frame: Frame) {
    frame.acquirePointCloud().use { cloud ->
      val ids = cloud.ids
      val points = cloud.points
      featureCount = ids.remaining()
      for (i in 0 until ids.remaining()) {
        if (pointCloud.size >= maxPoints) break
        val confidence = points.get(i * 4 + 3)
        if (confidence < 0.3f) continue
        pointCloud[ids.get(i)] = floatArrayOf(points.get(i * 4), points.get(i * 4 + 1), points.get(i * 4 + 2))
      }
    }
    if (pointBuffer.capacity() < pointCloud.size * 3) pointBuffer = Gl.floats(maxPoints * 3)
    pointBuffer.position(0)
    for (p in pointCloud.values) pointBuffer.put(p)
    pointBuffer.position(0)
    pointCount = pointCloud.size
  }

  private fun drawPoints() {
    if (pointCount == 0) return
    shapes.draw(viewProjection, pointBuffer, pointCount, GLES20.GL_POINTS, Palette.glow, true, pointSize = 9f)
    shapes.draw(viewProjection, pointBuffer, pointCount, GLES20.GL_POINTS, Palette.dot, true, pointSize = 4f)
  }

  private fun drawPlanes(session: Session, now: Long) {
    // Refresh the outline of every plane ARCore is tracking. A plane that
    // ARCore stops tracking keeps its last outline, so mapped surfaces stay
    // on screen for the whole scan; a plane merged into another is dropped,
    // because the plane it merged into now covers it.
    for (plane in session.getAllTrackables(Plane::class.java)) {
      if (plane.subsumedBy != null) {
        planeOutlines.remove(plane)
        continue
      }
      if (plane.trackingState != TrackingState.TRACKING) continue
      outlineOf(plane)?.let { planeOutlines[plane] = it }
    }
    for ((plane, outline) in planeOutlines) {
      drawOutline(plane, outline, now)
    }
    planeCount = planeOutlines.size
  }

  /** A plane's polygon in world space, or null while it has fewer than three corners. */
  private fun outlineOf(plane: Plane): PlaneOutline? {
    val polygon = plane.polygon ?: return null
    val corners = polygon.remaining() / 2
    if (corners < 3) return null
    val pose = plane.centerPose
    val world = FloatArray(corners * 3)
    val local = FloatArray(3)
    for (i in 0 until corners) {
      local[0] = polygon.get(i * 2)
      local[1] = 0f
      local[2] = polygon.get(i * 2 + 1)
      val out = pose.transformPoint(local)
      world[i * 3] = out[0]
      world[i * 3 + 1] = out[1]
      world[i * 3 + 2] = out[2]
    }
    return PlaneOutline(world, pose.translation, plane.type == Plane.Type.VERTICAL, plane.extentX * plane.extentZ)
  }

  private fun drawOutline(plane: Plane, outline: PlaneOutline, now: Long) {
    val world = outline.world
    val corners = world.size / 3
    val centre = outline.centre

    // Brighten briefly when the plane grows: the leading edge of mapping.
    val area = outline.area
    val previous = planeArea[plane] ?: 0f
    if (area > previous * 1.05f) {
      planeArea[plane] = area
      planeGrewAt[plane] = now
    }
    val since = (now - (planeGrewAt[plane] ?: 0L)).toFloat()
    val boost = if (reducedMotion) 1f else 1f + 1.2f * (1f - since / 800f).coerceIn(0f, 1f)

    // Faces: a fan from the centre. Edges: the outline plus spokes, so the
    // plane reads as a mesh.
    val triangles = Gl.floats(corners * 9)
    val lines = Gl.floats(corners * 12)
    for (i in 0 until corners) {
      val j = (i + 1) % corners
      triangles.put(centre[0]).put(centre[1]).put(centre[2])
      triangles.put(world[i * 3]).put(world[i * 3 + 1]).put(world[i * 3 + 2])
      triangles.put(world[j * 3]).put(world[j * 3 + 1]).put(world[j * 3 + 2])
      lines.put(world[i * 3]).put(world[i * 3 + 1]).put(world[i * 3 + 2])
      lines.put(world[j * 3]).put(world[j * 3 + 1]).put(world[j * 3 + 2])
      lines.put(centre[0]).put(centre[1]).put(centre[2])
      lines.put(world[i * 3]).put(world[i * 3 + 1]).put(world[i * 3 + 2])
    }
    val vertical = outline.vertical
    val fill = if (vertical) Palette.wallFill else Palette.floorFill
    if (!lite) {
      shapes.draw(viewProjection, triangles, corners * 3, GLES20.GL_TRIANGLES, fill, false)
      shapes.draw(viewProjection, lines, corners * 4, GLES20.GL_LINES, scaled(Palette.glow, boost), true, lineWidth = 6f)
    }
    shapes.draw(viewProjection, lines, corners * 4, GLES20.GL_LINES, scaled(Palette.edge, boost), true, lineWidth = 2f)
  }

  private fun scaled(color: FloatArray, boost: Float) =
    floatArrayOf(color[0], color[1], color[2], (color[3] * boost).coerceAtMost(1f))

  private fun projectLabels() {
    val current = labels
    if (current.isEmpty() || viewWidth == 0) return
    val positions = ArrayList<Triple<String, Float, Float>>(current.size)
    val visible = HashSet<String>()
    val clip = FloatArray(4)
    for (label in current) {
      Matrix.multiplyMV(clip, 0, viewProjection, 0, floatArrayOf(label.x, label.y, label.z, 1f), 0)
      if (clip[3] <= 0f) continue
      val x = (clip[0] / clip[3] * 0.5f + 0.5f) * viewWidth
      val y = (1f - (clip[1] / clip[3] * 0.5f + 0.5f)) * viewHeight
      if (x < -60 || x > viewWidth + 60 || y < -60 || y > viewHeight + 60) continue
      positions.add(Triple(label.id, x, y))
      visible.add(label.id)
    }
    post {
      for ((id, chip) in labelViews) {
        val target = if (id in visible) 1f else 0f
        chip.alpha += (target - chip.alpha) * if (reducedMotion) 1f else 0.25f
      }
      for ((id, x, y) in positions) {
        val chip = labelViews[id] ?: continue
        chip.translationX = x - chip.width / 2f
        chip.translationY = y - chip.height - dp(8f)
      }
    }
  }

  private fun sendPose(frame: Frame) {
    val pose = frame.camera.displayOrientedPose
    val z = pose.zAxis
    // The camera looks down its -Z axis; +Y is up (gravity aligned).
    val fx = -z[0]
    val fy = -z[1]
    val fz = -z[2]
    val yaw = Math.toDegrees(atan2(-fx, -fz).toDouble())
    val pitch = Math.toDegrees(asin(fy.coerceIn(-1f, 1f).toDouble()))
    val t = pose.translation
    val payload = mapOf(
      "yaw" to yaw,
      "pitch" to pitch,
      "x" to t[0].toDouble(),
      "y" to t[1].toDouble(),
      "z" to t[2].toDouble(),
      "tracking" to trackingName,
    )
    post { onArPose(payload) }
  }

  private fun sendStatus(session: Session) {
    emitStatus(
      mapOf(
        "tracking" to trackingName,
        "lidar" to false,
        "depth" to depthSupported,
        "planes" to planeCount,
        "meshTriangles" to 0,
        "featurePoints" to featureCount,
        "mappedPoints" to pointCloud.size,
        "brightness" to brightness,
        "ambientIntensity" to pixelIntensity * 1000,
        "detector" to detector.isAvailable,
        "labels" to labels.size,
        "frames" to pacer.frames,
        "detectorRuns" to detectionsDone,
        "detectorSkipped" to pacer.skippedBusy,
        "detectorMs" to lastDetectionMs,
        "detectionsFound" to detectionsFound,
        "detectionsPlaced" to detectionsPlaced,
        "detectorError" to (detector.loadError ?: ""),
      ),
    )
  }

  private fun emitStatus(payload: Map<String, Any>) {
    post { onArStatus(payload) }
  }

  private fun runDetector(frame: Frame) {
    val copy = try {
      frame.acquireCameraImage().use { YuvCopy.from(it) }
    } catch (_: Throwable) {
      return
    }
    brightness = copy.meanBrightness()
    detector.detect(copy) { found, milliseconds ->
      detectionsDone += 1
      lastDetectionMs = milliseconds
      pendingDetections.set(found)
    }
  }

  /** Runs inside onDrawFrame with the frame it just drew. */
  private fun hitTestDetections(frame: Frame, found: List<UprightDetection>) {
    if (!running) return
    val payload = ArrayList<Map<String, Any>>(found.size)
    for (detection in found) {
      // Upright image point back to the sensor image (turned 90 degrees
      // clockwise), then to view pixels.
      val sensor = floatArrayOf(detection.centreY, 1f - detection.centreX)
      val viewPoint = FloatArray(2)
      frame.transformCoordinates2d(Coordinates2d.IMAGE_NORMALIZED, sensor, Coordinates2d.VIEW, viewPoint)
      val entry = HashMap<String, Any>()
      entry["detectorClass"] = detection.detectorClass
      entry["score"] = detection.score.toDouble()
      val hit = try {
        frame.hitTest(viewPoint[0], viewPoint[1]).firstOrNull()
      } catch (_: Throwable) {
        null
      }
      detectionsFound += 1
      if (hit != null) {
        detectionsPlaced += 1
        val t = hit.hitPose.translation
        entry["world"] = mapOf("x" to t[0].toDouble(), "y" to t[1].toDouble(), "z" to t[2].toDouble())
      }
      payload.add(entry)
    }
    post { onArDetections(mapOf("detections" to payload)) }
  }

  // endregion

  private fun dp(value: Float) =
    TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value, resources.displayMetrics)

  private fun glassLabel(text: String): TextView {
    val chip = TextView(context)
    chip.text = text
    chip.setTextColor(Color.WHITE)
    chip.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
    chip.typeface = android.graphics.Typeface.DEFAULT_BOLD
    chip.gravity = Gravity.CENTER_VERTICAL
    val padH = dp(12f).toInt()
    val padV = dp(5f).toInt()
    chip.setPadding(padH, padV, padH, padV)
    chip.background = GradientDrawable().apply {
      cornerRadius = dp(14f)
      setColor(Color.argb(150, 20, 24, 32))
      setStroke(dp(0.75f).toInt().coerceAtLeast(1), Color.argb(90, 255, 255, 255))
    }
    chip.importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
    return chip
  }
}

/** A plane's polygon in world space as last tracked, with what drawing it needs. */
class PlaneOutline(val world: FloatArray, val centre: FloatArray, val vertical: Boolean, val area: Float)
