package org.wikipedia.m6

import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.wikipedia.compose.theme.BaseTheme
import org.wikipedia.dataclient.restbase.RbDefinition
import org.wikipedia.theme.Theme
import org.wikipedia.wiktionary.DefinitionList

@RunWith(AndroidJUnit4::class)
class M6H01WiktionaryStyleTagsTest {
    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun stylePayloadIsNotRenderedInAnyDefinitionField() {
        val usage = RbDefinition.Usage(
            partOfSpeech = STYLE_PAYLOAD + "noun",
            definitions = listOf(
                RbDefinition.Definition(
                    definition = STYLE_PAYLOAD + "a durable fabric",
                    examples = listOf(STYLE_PAYLOAD + "a chambray shirt")
                )
            )
        )

        composeTestRule.setContent {
            BaseTheme(currentTheme = Theme.LIGHT) {
                DefinitionList(usage = usage, onDialogLinkClick = {})
            }
        }

        composeTestRule.onAllNodesWithText(CSS_MARKER, substring = true)
            .assertCountEquals(0)
        composeTestRule.onNodeWithText("noun", substring = true).assertExists()
        composeTestRule.onNodeWithText("a durable fabric", substring = true).assertExists()
        composeTestRule.onNodeWithText("a chambray shirt", substring = true).assertExists()
    }

    private companion object {
        const val CSS_MARKER = ".mw-parser-output"
        const val STYLE_PAYLOAD =
            "<style data-mw-deduplicate=\"TemplateStyles:r886049734\">" +
                "$CSS_MARKER .defdate{font-size:smaller}</style>"
    }
}
