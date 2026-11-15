package app.sajao.ar

import android.opengl.GLES11Ext
import android.opengl.GLES20
import com.google.ar.core.Coordinates2d
import com.google.ar.core.Frame
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer

internal object Gl {
  fun floats(count: Int): FloatBuffer =
    ByteBuffer.allocateDirect(count * 4).order(ByteOrder.nativeOrder()).asFloatBuffer()

  fun floats(values: FloatArray): FloatBuffer = floats(values.size).apply {
    put(values)
    position(0)
  }

  fun program(vertex: String, fragment: String): Int {
    fun shader(type: Int, source: String): Int {
      val id = GLES20.glCreateShader(type)
      GLES20.glShaderSource(id, source)
      GLES20.glCompileShader(id)
      return id
    }
    val id = GLES20.glCreateProgram()
    GLES20.glAttachShader(id, shader(GLES20.GL_VERTEX_SHADER, vertex))
    GLES20.glAttachShader(id, shader(GLES20.GL_FRAGMENT_SHADER, fragment))
    GLES20.glLinkProgram(id)
    return id
  }
}

/** Draws the camera image behind everything. */
internal class CameraBackground {
  var textureId = -1
    private set
  private var program = 0
  private val quad = Gl.floats(floatArrayOf(-1f, -1f, 1f, -1f, -1f, 1f, 1f, 1f))
  private val texCoords = Gl.floats(8)

  fun create() {
    val textures = IntArray(1)
    GLES20.glGenTextures(1, textures, 0)
    textureId = textures[0]
    val target = GLES11Ext.GL_TEXTURE_EXTERNAL_OES
    GLES20.glBindTexture(target, textureId)
    GLES20.glTexParameteri(target, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE)
    GLES20.glTexParameteri(target, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE)
    GLES20.glTexParameteri(target, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR)
    GLES20.glTexParameteri(target, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR)
    program = Gl.program(
      """
      attribute vec4 a_Position;
      attribute vec2 a_TexCoord;
      varying vec2 v_TexCoord;
      void main() { gl_Position = a_Position; v_TexCoord = a_TexCoord; }
      """,
      """
      #extension GL_OES_EGL_image_external : require
      precision mediump float;
      varying vec2 v_TexCoord;
      uniform samplerExternalOES u_Texture;
      void main() { gl_FragColor = texture2D(u_Texture, v_TexCoord); }
      """,
    )
  }

  fun draw(frame: Frame) {
    if (frame.hasDisplayGeometryChanged()) {
      quad.position(0)
      texCoords.position(0)
      frame.transformCoordinates2d(
        Coordinates2d.OPENGL_NORMALIZED_DEVICE_COORDINATES, quad,
        Coordinates2d.TEXTURE_NORMALIZED, texCoords,
      )
    }
    if (frame.timestamp == 0L) return
    GLES20.glDisable(GLES20.GL_DEPTH_TEST)
    GLES20.glDepthMask(false)
    GLES20.glUseProgram(program)
    GLES20.glActiveTexture(GLES20.GL_TEXTURE0)
    GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, textureId)
    val position = GLES20.glGetAttribLocation(program, "a_Position")
    val texCoord = GLES20.glGetAttribLocation(program, "a_TexCoord")
    quad.position(0)
    texCoords.position(0)
    GLES20.glVertexAttribPointer(position, 2, GLES20.GL_FLOAT, false, 0, quad)
    GLES20.glVertexAttribPointer(texCoord, 2, GLES20.GL_FLOAT, false, 0, texCoords)
    GLES20.glEnableVertexAttribArray(position)
    GLES20.glEnableVertexAttribArray(texCoord)
    GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4)
    GLES20.glDisableVertexAttribArray(position)
    GLES20.glDisableVertexAttribArray(texCoord)
    GLES20.glDepthMask(true)
    GLES20.glEnable(GLES20.GL_DEPTH_TEST)
  }
}

/**
 * Lines, triangles and points in world space with one flat colour each
 * call. Glow comes from additive blending: a wide faint pass under a thin
 * bright one.
 */
internal class WorldShapes {
  private var program = 0

  fun create() {
    program = Gl.program(
      """
      uniform mat4 u_ViewProjection;
      uniform float u_PointSize;
      attribute vec3 a_Position;
      void main() {
        gl_Position = u_ViewProjection * vec4(a_Position, 1.0);
        gl_PointSize = u_PointSize;
      }
      """,
      """
      precision mediump float;
      uniform vec4 u_Color;
      uniform float u_Round;
      void main() {
        if (u_Round > 0.5) {
          vec2 c = gl_PointCoord - vec2(0.5);
          if (dot(c, c) > 0.25) discard;
        }
        gl_FragColor = u_Color;
      }
      """,
    )
  }

  /** Draw `count` vertices from `vertices` (x, y, z triples). */
  fun draw(
    viewProjection: FloatArray,
    vertices: FloatBuffer,
    count: Int,
    mode: Int,
    color: FloatArray,
    additive: Boolean,
    lineWidth: Float = 1f,
    pointSize: Float = 1f,
  ) {
    if (count <= 0) return
    GLES20.glUseProgram(program)
    GLES20.glEnable(GLES20.GL_BLEND)
    if (additive) {
      GLES20.glBlendFunc(GLES20.GL_SRC_ALPHA, GLES20.GL_ONE)
    } else {
      GLES20.glBlendFunc(GLES20.GL_SRC_ALPHA, GLES20.GL_ONE_MINUS_SRC_ALPHA)
    }
    GLES20.glDepthMask(false)
    GLES20.glUniformMatrix4fv(GLES20.glGetUniformLocation(program, "u_ViewProjection"), 1, false, viewProjection, 0)
    GLES20.glUniform4fv(GLES20.glGetUniformLocation(program, "u_Color"), 1, color, 0)
    GLES20.glUniform1f(GLES20.glGetUniformLocation(program, "u_PointSize"), pointSize)
    GLES20.glUniform1f(GLES20.glGetUniformLocation(program, "u_Round"), if (mode == GLES20.GL_POINTS) 1f else 0f)
    GLES20.glLineWidth(lineWidth)
    val position = GLES20.glGetAttribLocation(program, "a_Position")
    vertices.position(0)
    GLES20.glVertexAttribPointer(position, 3, GLES20.GL_FLOAT, false, 0, vertices)
    GLES20.glEnableVertexAttribArray(position)
    GLES20.glDrawArrays(mode, 0, count)
    GLES20.glDisableVertexAttribArray(position)
    GLES20.glDepthMask(true)
    GLES20.glDisable(GLES20.GL_BLEND)
  }
}

internal object Palette {
  val edge = floatArrayOf(0.30f, 0.90f, 1.0f, 0.90f)
  val glow = floatArrayOf(0.30f, 0.90f, 1.0f, 0.22f)
  val wallFill = floatArrayOf(0.35f, 0.85f, 1.0f, 0.09f)
  val floorFill = floatArrayOf(0.30f, 0.70f, 1.0f, 0.07f)
  val dot = floatArrayOf(0.85f, 0.98f, 1.0f, 0.95f)
}
