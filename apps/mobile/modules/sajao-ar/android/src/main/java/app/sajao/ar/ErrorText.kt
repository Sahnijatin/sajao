package app.sajao.ar

/**
 * An error as one line for the debug overlay: its type and whole message,
 * each cause, and where it was thrown. The overlay is how a problem on a
 * phone gets read, so the message is never cut short of what fits.
 */
object ErrorText {
  const val LIMIT = 600

  fun describe(error: Throwable, limit: Int = LIMIT): String {
    val parts = ArrayList<String>()
    var current: Throwable? = error
    var depth = 0
    while (current != null && depth < 4) {
      val name = current.javaClass.simpleName.ifEmpty { current.javaClass.name }
      val message = current.message?.trim().orEmpty()
      val line = if (message.isEmpty()) name else "$name: $message"
      parts.add(if (depth == 0) line else "caused by $line")
      val next = current.cause
      current = if (next === current) null else next
      depth += 1
    }
    error.stackTrace.firstOrNull()?.let { frame ->
      parts.add("at ${frame.className}.${frame.methodName}:${frame.lineNumber}")
    }
    return parts.joinToString(" | ").replace('\n', ' ').take(limit)
  }
}
