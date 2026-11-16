package app.sajao.ar

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ErrorTextTest {
  @Test
  fun keepsTheWholeMessageAndTheCause() {
    val message = "Field baseOptions_ for a.b.C not found. Known fields are [a, b, c, d, e, f, g, h]"
    val text = ErrorText.describe(RuntimeException(message, IllegalStateException("inner")))
    assertTrue(text.startsWith("RuntimeException: $message"))
    assertTrue(text.contains("caused by IllegalStateException: inner"))
    assertTrue(text.contains(" | at app.sajao.ar.ErrorTextTest.keepsTheWholeMessageAndTheCause:"))
  }

  @Test
  fun anErrorWithoutAMessageShowsItsType() {
    assertTrue(ErrorText.describe(NullPointerException()).startsWith("NullPointerException | at "))
  }

  @Test
  fun staysOnOneLineAndWithinTheLimit() {
    val text = ErrorText.describe(RuntimeException("first\nsecond " + "x".repeat(2000)), limit = 80)
    assertEquals(80, text.length)
    assertTrue(!text.contains('\n'))
  }
}
