package org.wikipedia.m6

import android.graphics.Bitmap
import androidx.activity.ComponentActivity
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.graphics.toPixelMap
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.wikipedia.R
import org.wikipedia.WikipediaApp
import org.wikipedia.onboarding.InitialOnboardingActivity
import org.wikipedia.settings.Prefs
import org.wikipedia.theme.Theme
import java.io.File
import kotlin.math.abs

class M6T425733OnboardingThemeTest {
    private val priorOnboardingEnabled = Prefs.isInitialOnboardingEnabled
    private val priorTheme = WikipediaApp.instance.currentTheme

    init {
        Prefs.isInitialOnboardingEnabled = true
        WikipediaApp.instance.currentTheme = Theme.LIGHT
    }

    @get:Rule
    val composeRule = createAndroidComposeRule<InitialOnboardingActivity>()

    @After
    fun restoreState() {
        Prefs.isInitialOnboardingEnabled = priorOnboardingEnabled
        WikipediaApp.instance.currentTheme = priorTheme
    }

    @Test
    fun freshInstallScreensMatchLightSystemTheme() {
        composeRule.waitForIdle()
        val firstScreen = composeRule.onRoot().captureToImage()
        val firstLuminance = edgeLuminance(firstScreen)
        val firstArtifact = writeArtifact(composeRule.activity, "m6-t425733-first.png", firstScreen)

        composeRule.onNodeWithContentDescription(
            composeRule.activity.getString(R.string.nav_item_forward)
        ).performClick()
        composeRule.waitForIdle()

        val secondScreen = composeRule.onRoot().captureToImage()
        val secondLuminance = edgeLuminance(secondScreen)
        val secondArtifact = writeArtifact(composeRule.activity, "m6-t425733-second.png", secondScreen)

        println(
            "M6_T425733_RESULT expected_theme=LIGHT first_luminance=$firstLuminance " +
                "second_luminance=$secondLuminance delta=${abs(firstLuminance - secondLuminance)} " +
                "first_artifact=${firstArtifact.absolutePath} second_artifact=${secondArtifact.absolutePath}"
        )

        assertTrue(
            "fresh-install onboarding screens must both use the light paper color; " +
                "first=$firstLuminance second=$secondLuminance",
            firstLuminance >= LIGHT_LUMINANCE_FLOOR &&
                secondLuminance >= LIGHT_LUMINANCE_FLOOR &&
                abs(firstLuminance - secondLuminance) <= MAX_LUMINANCE_DELTA
        )
    }

    private fun edgeLuminance(image: ImageBitmap): Float {
        val pixels = image.toPixelMap()
        val maxX = pixels.width - 1
        val maxY = pixels.height - 1
        val samples = listOf(
            pixels[EDGE_INSET, EDGE_INSET],
            pixels[maxX - EDGE_INSET, EDGE_INSET],
            pixels[EDGE_INSET, maxY / 2],
            pixels[maxX - EDGE_INSET, maxY / 2]
        )
        return samples.map { it.luminance() }.average().toFloat()
    }

    private fun writeArtifact(
        activity: ComponentActivity,
        name: String,
        image: ImageBitmap
    ): File {
        val directory = checkNotNull(activity.getExternalFilesDir(null))
        return File(directory, name).also { file ->
            file.outputStream().use {
                image.asAndroidBitmap().compress(Bitmap.CompressFormat.PNG, 100, it)
            }
        }
    }

    companion object {
        private const val EDGE_INSET = 4
        private const val LIGHT_LUMINANCE_FLOOR = 0.80f
        private const val MAX_LUMINANCE_DELTA = 0.10f
    }
}
