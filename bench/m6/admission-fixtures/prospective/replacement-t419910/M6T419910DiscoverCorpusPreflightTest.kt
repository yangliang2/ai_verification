package org.wikipedia.m6

import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.wikipedia.database.AppDatabase
import org.wikipedia.dataclient.WikiSite
import org.wikipedia.page.Namespace
import org.wikipedia.readinglist.database.ReadingList
import org.wikipedia.readinglist.database.ReadingListPage
import org.wikipedia.readinglist.recommended.RecommendedReadingListHelper
import org.wikipedia.readinglist.recommended.RecommendedReadingListSource
import org.wikipedia.settings.Prefs

@RunWith(AndroidJUnit4::class)
class M6T419910DiscoverCorpusPreflightTest {
    private val fixturePages = mutableListOf<ReadingListPage>()
    private var fixtureListId = 0L
    private var priorEnabled = false
    private var priorArticleCount = 0
    private lateinit var priorSource: RecommendedReadingListSource

    @Before
    fun seedReportedCorpusSize() {
        runBlocking {
            priorEnabled = Prefs.isRecommendedReadingListEnabled
            priorArticleCount = Prefs.recommendedReadingListArticlesNumber
            priorSource = Prefs.recommendedReadingListSource

            Prefs.isRecommendedReadingListEnabled = true
            Prefs.recommendedReadingListArticlesNumber = RECOMMENDATION_COUNT
            Prefs.recommendedReadingListSource = RecommendedReadingListSource.READING_LIST

            val database = AppDatabase.instance
            val readingList = ReadingList(FIXTURE_LIST_TITLE, "M6 T419910 local-corpus diagnostic")
            fixtureListId = database.readingListDao().insertReadingList(readingList)
            repeat(REPORTED_CORPUS_SIZE) { index ->
                val page = ReadingListPage(
                    wiki = WikiSite.forLanguageCode("en"),
                    namespace = Namespace.MAIN,
                    displayTitle = "M6 T419910 page $index",
                    apiTitle = "M6_T419910_page_$index",
                    listId = fixtureListId,
                    offline = false,
                    status = ReadingListPage.STATUS_QUEUE_FOR_SAVE,
                    lang = "en"
                )
                page.id = database.readingListPageDao().insertReadingListPage(page)
                fixturePages += page
            }
        }
    }

    @After
    fun removeFixtureResidue() {
        runBlocking {
            val database = AppDatabase.instance
            fixturePages.forEach { page ->
                database.readingListPageDao().getPageById(page.id)?.let {
                    database.readingListPageDao().deleteReadingListPage(it)
                }
            }
            database.readingListDao().getListById(fixtureListId)?.let {
                database.readingListDao().deleteReadingList(it)
            }
            Prefs.isRecommendedReadingListEnabled = priorEnabled
            Prefs.recommendedReadingListArticlesNumber = priorArticleCount
            Prefs.recommendedReadingListSource = priorSource
        }
    }

    @Test
    fun boundedLocalCorpusDoesNotReproduceIndefiniteLoading() {
        runBlocking {
            val database = AppDatabase.instance

            val loadStartedAt = SystemClock.elapsedRealtime()
            val loadedList = database.readingListDao().getListById(fixtureListId, true)
            val loadElapsedMs = SystemClock.elapsedRealtime() - loadStartedAt

            val sampleStartedAt = SystemClock.elapsedRealtime()
            val sourceSample = database.readingListPageDao()
                .getPagesByRandom(RECOMMENDATION_COUNT)
            val sampleElapsedMs = SystemClock.elapsedRealtime() - sampleStartedAt

            val readinessStartedAt = SystemClock.elapsedRealtime()
            val ready = RecommendedReadingListHelper.readyToGenerateList()
            val readinessElapsedMs = SystemClock.elapsedRealtime() - readinessStartedAt

            println(
                "M6_T419910_LOCAL_RESULT corpus=$REPORTED_CORPUS_SIZE " +
                    "loaded=${loadedList?.pages?.size} sampled=${sourceSample.size} ready=$ready " +
                    "load_ms=$loadElapsedMs sample_ms=$sampleElapsedMs ready_ms=$readinessElapsedMs " +
                    "network_phase_exercised=false"
            )

            assertEquals(REPORTED_CORPUS_SIZE, loadedList?.pages?.size)
            assertEquals(RECOMMENDATION_COUNT, sourceSample.size)
            assertTrue(ready)
            assertTrue("bounded local list load exceeded preflight ceiling", loadElapsedMs < LOCAL_CEILING_MS)
            assertTrue("bounded source sampling exceeded preflight ceiling", sampleElapsedMs < LOCAL_CEILING_MS)
        }
    }

    companion object {
        private const val FIXTURE_LIST_TITLE = "M6 T419910 corpus admission"
        private const val REPORTED_CORPUS_SIZE = 273
        private const val RECOMMENDATION_COUNT = 5
        private const val LOCAL_CEILING_MS = 5_000L
    }
}
