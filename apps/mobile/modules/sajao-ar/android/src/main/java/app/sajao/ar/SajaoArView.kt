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
import com.google.ar.core.CameraConfig
import com.google.ar.core.CameraConfigFilter
import com.google.ar.core.Config
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
import java.util.EnumSet
import java.util.concurrent.Executors
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
  private val onArSurfaces by EventDispatcher()
  private val onArKeyframe by EventDispatcher()
  // Records the capture package's native files while a capture id is set.
  private var recorder: CaptureRecorder? = null
  private var captureId = ""

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
  // The surface effect: tracked points joined to their nearest neighbours.
  // Rebuilt less often than points arrive; only the newest points are joined.
  private var linkBuffer: FloatBuffer = Gl.floats(3)
  private var linkVertexCount = 0
  private var lastLinksAt = 0L
  private val maxLinkedPoints = 2500
  private val linkExecutor = Executors.newSingleThreadExecutor()
  @Volatile private var linksBusy = false
  // Finished link vertices waiting for the GL thread to upload them.
  private val pendingLinks = AtomicReference<FloatArray?>(null)

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
  private val pendingDetections = AtomicReference<PendingDetections?>(null)
  // Height of the lowest upward-facing plane: the floor.
  private var floorY: Float? = null
  // Sharpness of the latest camera image copied for the detector.
  @Volatile private var latestSharpness = 0.0
  private var lastSurfacesAt = 0L
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

  /** Start recording a capture package into its own folder; an empty id records nothing. */
  fun setCaptureId(id: String) {
    if (id == captureId) return
    captureId = id
    recorder?.close()
    recorder = if (id.isEmpty()) {
      null
    } else {
      CaptureRecorder(CaptureRecorder.folder(context.cacheDir, id)) { payload -> post { onArKeyframe(payload) } }
    }
  }

  /** Delete keyframe candidates the app's recorder dropped. */
  fun discardKeyframes(uris: List<String>) {
    recorder?.discard(uris)
  }

  /**
   * End the capture: planes snapshot on the GL thread, then the recorder
   * writes planes and depth for the chosen keyframes and resolves with the
   * files' uris.
   */
  fun finishCapture(chosen: List<String>, done: (Map<String, Any?>) -> Unit) {
    val current = recorder ?: return done(mapOf("planes" to null, "depth" to null, "sceneMesh" to null))
    val session = session
    if (session == null || !running) {
      current.finish(org.json.JSONArray(), chosen, done)
      return
    }
    surface.queueEvent {
      val planes = try {
        current.snapshotPlanes(session)
      } catch (_: Throwable) {
        org.json.JSONArray()
      }
      current.finish(planes, chosen, done)
    }
  }

  fun destroy() {
    pause()
    recorder?.close()
    session?.close()
    session = null
    detector.close()
    linkExecutor.shutdown()
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
        // Keyframes are saved from ARCore's CPU image, 640 by 480 by
        // default: ask for the largest one up to 1920 wide at 30 fps.
        try {
          val filter = CameraConfigFilter(created).setTargetFps(EnumSet.of(CameraConfig.TargetFps.TARGET_FPS_30))
          created.getSupportedCameraConfigs(filter)
            .filter { it.imageSize.width <= 1920 }
            .maxByOrNull { it.imageSize.width * it.imageSize.height }
            ?.let { created.cameraConfig = it }
        } catch (_: Throwable) {
          // The default camera configuration still works.
        }
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
        if (now - lastSurfacesAt > 250) {
          lastSurfacesAt = now
          sendSurfaces(frame)
        }
      }
      if (now - lastPoseAt > 100) {
        lastPoseAt = now
        sendPose(frame)
      }
      if (now - lastStatusAt > 250) {
        lastStatusAt = now
        sendStatus(session)
      }
      pendingDetections.getAndSet(null)?.let { pending ->
        if (camera.trackingState == TrackingState.TRACKING) hitTestDetections(frame, pending)
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
        val confidence = points.get(i * 4 + 3)
        if (confidence < 0.3f) continue
        // Full: drop the oldest point, so newly mapped areas keep appearing.
        if (pointCloud.size >= maxPoints && !pointCloud.containsKey(ids.get(i))) {
          pointCloud.remove(pointCloud.keys.first())
        }
        pointCloud[ids.get(i)] = floatArrayOf(points.get(i * 4), points.get(i * 4 + 1), points.get(i * 4 + 2))
      }
    }
    if (pointBuffer.capacity() < pointCloud.size * 3) pointBuffer = Gl.floats(maxPoints * 3)
    pointBuffer.position(0)
    for (p in pointCloud.values) pointBuffer.put(p)
    pointBuffer.position(0)
    pointCount = pointCloud.size
    val now = SystemClock.uptimeMillis()
    if (!lite && now - lastLinksAt > 600) {
      lastLinksAt = now
      rebuildLinks()
    }
  }

  /**
   * Joins the newest tracked points into a wire mesh over whatever they lie
   * on. Joining takes a few milliseconds, so it runs off the GL thread; the
   * result is uploaded on the next drawn frame.
   */
  private fun rebuildLinks() {
    if (linksBusy) return
    linksBusy = true
    val points = pointCloud.values.toList().takeLast(maxLinkedPoints)
    linkExecutor.execute {
      try {
        val edges = SurfaceMesh.links(points)
        val vertices = FloatArray(edges.size * 3)
        edges.forEachIndexed { k, index ->
          val p = points[index]
          vertices[k * 3] = p[0]
          vertices[k * 3 + 1] = p[1]
          vertices[k * 3 + 2] = p[2]
        }
        pendingLinks.set(vertices)
      } finally {
        linksBusy = false
      }
    }
  }

  private fun drawPoints() {
    if (pointCount == 0) return
    pendingLinks.getAndSet(null)?.let { vertices ->
      if (linkBuffer.capacity() < vertices.size) {
        linkBuffer = Gl.floats(maxOf(vertices.size, maxLinkedPoints * SurfaceMesh.LINKS_PER_POINT * 2 * 3))
      }
      linkBuffer.position(0)
      linkBuffer.put(vertices)
      linkBuffer.position(0)
      linkVertexCount = vertices.size / 3
    }
    if (!lite && linkVertexCount > 0) {
      shapes.draw(viewProjection, linkBuffer, linkVertexCount, GLES20.GL_LINES, Palette.glow, true, lineWidth = 3f)
      shapes.draw(viewProjection, linkBuffer, linkVertexCount, GLES20.GL_LINES, Palette.link, true, lineWidth = 1f)
    }
    shapes.draw(viewProjection, pointBuffer, pointCount, GLES20.GL_POINTS, Palette.glow, true, pointSize = 9f)
    shapes.draw(viewProjection, pointBuffer, pointCount, GLES20.GL_POINTS, Palette.dot, true, pointSize = 4f)
  }

  private fun drawPlanes(session: Session, now: Long) {
    // Refresh the outline of every plane ARCore is tracking. A plane that
    // ARCore stops tracking keeps its last outline, so mapped surfaces stay
    // on screen for the whole scan; a plane merged into another is dropped,
    // because the plane it merged into now covers it.
    var lowest: Float? = null
    for (plane in session.getAllTrackables(Plane::class.java)) {
      if (plane.subsumedBy != null) {
        planeOutlines.remove(plane)
        continue
      }
      if (plane.trackingState != TrackingState.TRACKING) continue
      if (plane.type == Plane.Type.HORIZONTAL_UPWARD_FACING) {
        val y = plane.centerPose.ty()
        lowest = minOf(lowest ?: y, y)
      }
      outlineOf(plane)?.let { planeOutlines[plane] = it }
    }
    for ((plane, outline) in planeOutlines) {
      drawOutline(plane, outline, now)
    }
    planeCount = planeOutlines.size
    // The lowest tracked upward plane is the floor; keep the last one seen.
    if (lowest != null) floorY = lowest
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
    // Grid lines inside the plane, so it reads as a mesh like the LiDAR one.
    val local2d = FloatArray(corners * 2) { polygon.get(it) }
    val grid2d = SurfaceMesh.gridLines(local2d)
    val grid = FloatArray(grid2d.size / 2 * 3)
    for (k in 0 until grid2d.size / 2) {
      local[0] = grid2d[k * 2]
      local[1] = 0f
      local[2] = grid2d[k * 2 + 1]
      val out = pose.transformPoint(local)
      grid[k * 3] = out[0]
      grid[k * 3 + 1] = out[1]
      grid[k * 3 + 2] = out[2]
    }
    return PlaneOutline(world, grid, pose.translation, plane.type == Plane.Type.VERTICAL, plane.extentX * plane.extentZ)
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
    if (outline.grid.isNotEmpty()) {
      val grid = outline.gridBuffer()
      shapes.draw(viewProjection, grid, outline.grid.size / 3, GLES20.GL_LINES, scaled(Palette.link, boost), true, lineWidth = 1f)
    }
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

  /** Where the camera points: yaw and pitch in degrees, gravity aligned, as the app's pose. */
  private fun yawPitch(frame: Frame): Pair<Double, Double> {
    val z = frame.camera.displayOrientedPose.zAxis
    // The camera looks down its -Z axis; +Y is up (gravity aligned).
    val fx = -z[0]
    val fy = -z[1]
    val fz = -z[2]
    val yaw = Math.toDegrees(atan2(-fx, -fz).toDouble())
    val pitch = Math.toDegrees(asin(fy.coerceIn(-1f, 1f).toDouble()))
    return yaw to pitch
  }

  private fun sendPose(frame: Frame) {
    val (yaw, pitch) = yawPitch(frame)
    val t = frame.camera.displayOrientedPose.translation
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
    latestSharpness = SurfaceSample.lumaSharpness(copy.y, copy.width, copy.height, copy.yRowStride)
    recorder?.let { capture ->
      val (yaw, pitch) = yawPitch(frame)
      capture.offer(frame, copy, latestSharpness, yaw, pitch)
    }
    // The camera as it was for this image: rays are built from it, so a
    // result that arrives after the phone moved still lands on its object.
    val camera = try {
      val pose = frame.camera.pose
      val rotation = FloatArray(4)
      pose.getRotationQuaternion(rotation, 0)
      val intrinsics = frame.camera.imageIntrinsics
      CaptureCamera(rotation, pose.translation, intrinsics.focalLength, intrinsics.principalPoint, intrinsics.imageDimensions)
    } catch (_: Throwable) {
      return
    }
    detector.detect(copy) { found, milliseconds ->
      detectionsDone += 1
      lastDetectionMs = milliseconds
      pendingDetections.set(PendingDetections(found, camera))
    }
  }

  /**
   * Coverage on walls and floor: a 4 by 3 grid of rays from the camera into
   * the planes found so far, with the latest image's sharpness. JavaScript
   * decides whether the sample counts (slow turn, sharp frame).
   */
  private fun sendSurfaces(frame: Frame) {
    val camera = try {
      val pose = frame.camera.pose
      val rotation = FloatArray(4)
      pose.getRotationQuaternion(rotation, 0)
      val intrinsics = frame.camera.imageIntrinsics
      CaptureCamera(rotation, pose.translation, intrinsics.focalLength, intrinsics.principalPoint, intrinsics.imageDimensions)
    } catch (_: Throwable) {
      return
    }
    val hits = ArrayList<Map<String, Any>>(SurfaceSample.GRID.size)
    for ((x, y) in SurfaceSample.GRID) {
      val (origin, direction) = camera.ray(x, y)
      val hit = try {
        frame.hitTest(origin, 0, direction, 0).firstOrNull { result ->
          val plane = result.trackable as? Plane
          plane != null && plane.isPoseInPolygon(result.hitPose)
        }
      } catch (_: Throwable) {
        null
      } ?: continue
      val plane = hit.trackable as Plane
      val p = hit.hitPose.translation
      val kind = Surface.kind(
        vertical = plane.type == Plane.Type.VERTICAL,
        facingDown = plane.type == Plane.Type.HORIZONTAL_DOWNWARD_FACING,
        longestSide = maxOf(plane.extentX, plane.extentZ),
        hitY = p[1],
        floorY = floorY,
      )
      if (kind != Surface.WALL && kind != Surface.FLOOR) continue
      // A plane's normal is its pose's +Y axis.
      val (normalYaw, offset) = SurfaceSample.wallFrame(plane.centerPose.yAxis, p)
      hits.add(
        mapOf(
          "kind" to kind,
          "normalYaw" to normalYaw,
          "offset" to offset,
          "x" to p[0].toDouble(),
          "y" to p[1].toDouble(),
          "z" to p[2].toDouble(),
        ),
      )
    }
    val payload = HashMap<String, Any>()
    payload["sharpness"] = latestSharpness
    payload["hits"] = hits
    floorY?.let { payload["floorY"] = it.toDouble() }
    post { onArSurfaces(payload) }
  }

  /**
   * Runs inside onDrawFrame with the frame it just drew. For each detection:
   * the nearest thing on its ray (depth or feature points, else a plane) is
   * the object; the plane the same ray meets says whether that is really a
   * wall or the floor. The label rules in JavaScript use both.
   */
  private fun hitTestDetections(frame: Frame, pending: PendingDetections) {
    if (!running) return
    val payload = ArrayList<Map<String, Any>>(pending.found.size)
    for (detection in pending.found) {
      // Upright image point back to the sensor image (turned 90 degrees clockwise).
      val (origin, direction) = pending.camera.ray(detection.centreY, 1f - detection.centreX)
      val entry = HashMap<String, Any>()
      entry["detectorClass"] = detection.detectorClass
      entry["score"] = detection.score.toDouble()
      entry["surface"] = Surface.NONE
      // The upright box, for "step back" when a large object is cut off.
      entry["box"] = mapOf(
        "x" to detection.left.toDouble(),
        "y" to detection.top.toDouble(),
        "width" to detection.width.toDouble(),
        "height" to detection.height.toDouble(),
      )
      val hits = try {
        frame.hitTest(origin, 0, direction, 0)
      } catch (_: Throwable) {
        emptyList()
      }
      fun rangeOf(position: FloatArray) =
        (position[0] - origin[0]) * direction[0] + (position[1] - origin[1]) * direction[1] +
          (position[2] - origin[2]) * direction[2]
      val planeHit = hits.firstOrNull { hit ->
        val plane = hit.trackable as? Plane
        plane != null && plane.isPoseInPolygon(hit.hitPose)
      }
      // The object's own point: a feature or depth point ARCore hit on the
      // ray, else the front of the tracked feature points around the ray,
      // else the plane (the label rules then judge whether that is a wall).
      val objectRange = hits.firstOrNull { it.trackable !is Plane }?.let { rangeOf(it.hitPose.translation) }
        ?: frontOfCone(origin, direction, pointCloud.values)
        ?: planeHit?.let { rangeOf(it.hitPose.translation) }
      detectionsFound += 1
      if (objectRange != null) {
        detectionsPlaced += 1
        val t = FloatArray(3) { origin[it] + direction[it] * objectRange }
        entry["world"] = mapOf("x" to t[0].toDouble(), "y" to t[1].toDouble(), "z" to t[2].toDouble())
        entry["range"] = objectRange.toDouble()
        if (planeHit != null) {
          val plane = planeHit.trackable as Plane
          val p = planeHit.hitPose.translation
          entry["surface"] = Surface.kind(
            vertical = plane.type == Plane.Type.VERTICAL,
            facingDown = plane.type == Plane.Type.HORIZONTAL_DOWNWARD_FACING,
            longestSide = maxOf(plane.extentX, plane.extentZ),
            hitY = p[1],
            floorY = floorY,
          )
          entry["gap"] = Surface.gap(objectRange, rangeOf(p)).toDouble()
        }
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
class PlaneOutline(
  val world: FloatArray,
  /** Grid line endpoints inside the plane, x, y, z each. */
  val grid: FloatArray,
  val centre: FloatArray,
  val vertical: Boolean,
  val area: Float,
) {
  private var buffer: FloatBuffer? = null

  /** The grid as a GL buffer, built once per outline. */
  fun gridBuffer(): FloatBuffer = buffer ?: Gl.floats(grid).also { buffer = it }
}

/** Detector results with the camera they were captured from, waiting for the next drawn frame. */
class PendingDetections(val found: List<UprightDetection>, val camera: CaptureCamera)
