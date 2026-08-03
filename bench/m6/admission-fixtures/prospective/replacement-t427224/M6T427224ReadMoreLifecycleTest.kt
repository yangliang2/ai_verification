package org.wikipedia.m6

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.wikipedia.bridge.JavaScriptActionHandler
import org.wikipedia.dataclient.WikiSite
import org.wikipedia.page.Namespace
import org.wikipedia.page.Page
import org.wikipedia.page.PageProperties
import org.wikipedia.page.PageTitle
import org.wikipedia.page.PageViewModel

/**
 * T427224 admission oracle.
 *
 * The reporter's Polish screenshot contains three related-page identities twice:
 * (2039) Payne-Gaposchkin, Annie Jump Cannon, and Harvard College Observatory.
 * Exercise the two production commands that can contribute those identities:
 * footer setup and lazy Read More append. The fixture deliberately models only
 * the command/lifecycle seam; it does not claim to reproduce the live PCS
 * response or a device-specific WebView rendering.
 */
class M6T427224ReadMoreLifecycleTest {
    @Test
    fun footerSetupAndLazyAppendKeepRecordedIdentitiesUnique() {
        val title = PageTitle("(2039)_Payne-Gaposchkin", WikiSite("pl.wikipedia.org", "pl"))
        val model = PageViewModel().apply {
            this.title = title
            page = Page(
                title = title,
                pageProperties = PageProperties(
                    namespace = Namespace.MAIN,
                    displayTitle = title.displayText
                )
            )
        }

        val footerSetup = JavaScriptActionHandler.setFooter(model)
        val lazyAppend = JavaScriptActionHandler.appendReadMode(model)
        val lifecycleCommands = listOf(footerSetup, lazyAppend)
        val footerCalls = lifecycleCommands.count { it.contains("pcs.c1.Footer.") }
        val readMoreCommands = lifecycleCommands.count { it.contains("fragment: \"pcs-read-more\"") }
        val itemCounts = lifecycleCommands.mapNotNull { ITEM_COUNT.find(it)?.groupValues?.get(1)?.toInt() }
        val projectedOccurrences = RECORDED_IDENTITIES.size * readMoreCommands
        val uniqueIdentities = RECORDED_IDENTITIES.toSet().size

        println(
            "M6_T427224_RESULT lang=${title.wikiSite.languageCode} " +
                "recorded_identities=${RECORDED_IDENTITIES.size} unique_identities=$uniqueIdentities " +
                "footer_calls=$footerCalls read_more_commands=$readMoreCommands " +
                "item_counts=$itemCounts projected_occurrences=$projectedOccurrences " +
                "expected_unique_occurrences=$uniqueIdentities"
        )

        assertTrue("both footer lifecycle commands must carry the Read More fragment", readMoreCommands == 2)
        assertTrue("each lifecycle command must request three related items", itemCounts.all { it == 3 })
        assertEquals(
            "the three recorded Polish identities must be emitted once across setup and lazy append",
            uniqueIdentities,
            projectedOccurrences
        )
    }

    companion object {
        private val ITEM_COUNT = Regex("itemCount: (\\d+)")
        private val RECORDED_IDENTITIES = listOf(
            "(2039) Payne-Gaposchkin",
            "Annie Jump Cannon",
            "Harvard College Observatory"
        )
    }
}
