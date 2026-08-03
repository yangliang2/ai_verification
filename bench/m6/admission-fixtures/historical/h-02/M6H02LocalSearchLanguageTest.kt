package org.wikipedia.m6

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.wikipedia.Constants
import org.wikipedia.WikipediaApp
import org.wikipedia.database.AppDatabase
import org.wikipedia.dataclient.WikiSite
import org.wikipedia.history.HistoryEntry
import org.wikipedia.page.Namespace
import org.wikipedia.page.PageBackStackItem
import org.wikipedia.page.PageTitle
import org.wikipedia.page.tabs.Tab
import org.wikipedia.readinglist.database.ReadingListPage
import org.wikipedia.search.SearchResults
import org.wikipedia.search.SearchResultsViewModel

@RunWith(AndroidJUnit4::class)
class M6H02LocalSearchLanguageTest {
    private lateinit var database: AppDatabase
    private lateinit var originalTabs: List<Tab>

    private val englishWiki = WikiSite.forLanguageCode("en")
    private val selectedWiki = WikiSite.forLanguageCode("es")

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        database = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        originalTabs = WikipediaApp.instance.tabList.toList()
        WikipediaApp.instance.tabList.clear()
    }

    @After
    fun tearDown() {
        WikipediaApp.instance.tabList.clear()
        WikipediaApp.instance.tabList.addAll(originalTabs)
        database.close()
    }

    @Test
    fun historySuggestionFromAnotherLanguageIsExcluded() = runBlocking {
        database.historyEntryDao().insertEntry(
            HistoryEntry(
                authority = englishWiki.authority(),
                lang = englishWiki.languageCode,
                apiTitle = QUERY,
                displayTitle = QUERY,
                namespace = ""
            )
        )

        val results = invokeVersionCompatibleSearch(
            receiver = database.historyEntryWithImageDao(),
            methodName = "findHistoryItem",
            selectedWiki = selectedWiki,
            query = QUERY
        )

        assertTrue(
            "History from enwiki must not be suggested while searching eswiki.",
            results.results.isEmpty()
        )
    }

    @Test
    fun readingListSuggestionFromAnotherLanguageIsExcluded() {
        database.readingListPageDao().insertReadingListPage(
            ReadingListPage(
                wiki = englishWiki,
                namespace = Namespace.MAIN,
                displayTitle = QUERY,
                apiTitle = QUERY,
                offline = false,
                status = ReadingListPage.STATUS_SAVED,
                lang = englishWiki.languageCode
            )
        )

        val results = invokeVersionCompatibleSearch(
            receiver = database.readingListPageDao(),
            methodName = "findPageForSearchQueryInAnyList",
            selectedWiki = selectedWiki,
            query = QUERY
        )

        assertTrue(
            "Reading-list pages from enwiki must not be suggested while searching eswiki.",
            results.results.isEmpty()
        )
    }

    @Test
    fun openTabSuggestionFromAnotherLanguageIsExcluded() {
        val title = PageTitle(QUERY, englishWiki)
        WikipediaApp.instance.tabList.add(
            Tab().apply {
                pushBackStackItem(
                    PageBackStackItem(
                        title = title,
                        historyEntry = HistoryEntry(title, HistoryEntry.SOURCE_SEARCH)
                    )
                )
            }
        )

        val pagingSource = SearchResultsViewModel.SearchResultsPagingSource(
            searchTerm = QUERY,
            languageCode = selectedWiki.languageCode,
            countsPerLanguageCode = mutableListOf(),
            invokeSource = Constants.InvokeSource.SEARCH
        )
        val method = pagingSource.javaClass.declaredMethods.single {
            it.name == "getSearchResultsFromTabs"
        }.apply {
            isAccessible = true
        }
        val args = when (method.parameterCount) {
            1 -> arrayOf(QUERY)
            2 -> arrayOf(selectedWiki, QUERY)
            else -> error("Unexpected getSearchResultsFromTabs signature: $method")
        }
        val results = method.invoke(pagingSource, *args) as SearchResults

        assertTrue(
            "An enwiki tab must not be suggested while searching eswiki.",
            results.results.isEmpty()
        )
    }

    private fun invokeVersionCompatibleSearch(
        receiver: Any,
        methodName: String,
        selectedWiki: WikiSite,
        query: String
    ): SearchResults {
        val method = receiver.javaClass.methods.single {
            it.name == methodName
        }
        val args = when (method.parameterCount) {
            1 -> arrayOf(query)
            2 -> arrayOf(selectedWiki, query)
            else -> error("Unexpected $methodName signature: $method")
        }
        return method.invoke(receiver, *args) as SearchResults
    }

    private companion object {
        const val QUERY = "Chambray"
    }
}
