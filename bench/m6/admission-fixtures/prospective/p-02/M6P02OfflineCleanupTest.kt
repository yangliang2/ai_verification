package org.wikipedia.m6

import android.content.Context
import android.os.SystemClock
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.work.WorkInfo
import androidx.work.WorkManager
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.wikipedia.database.AppDatabase
import org.wikipedia.dataclient.WikiSite
import org.wikipedia.offline.db.OfflineObject
import org.wikipedia.page.Namespace
import org.wikipedia.readinglist.database.ReadingList
import org.wikipedia.readinglist.database.ReadingListPage
import java.io.File
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class M6P02OfflineCleanupTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()
    private val workManager by lazy { WorkManager.getInstance(context) }
    private val fixtureFiles = mutableListOf<File>()
    private val fixtureUrls = mutableListOf<String>()
    private val fixturePages = mutableListOf<ReadingListPage>()
    private var fixtureListId = 0L

    @Before
    fun seedBoundedOfflineCorpus() {
        runBlocking {
            workManager.cancelUniqueWork(WORK_NAME).result.get(10, TimeUnit.SECONDS)

            val database = AppDatabase.instance
            val readingList = ReadingList(FIXTURE_LIST_TITLE, "M6 P-02 admission fixture")
            fixtureListId = database.readingListDao().insertReadingList(readingList)
            val offlineDirectory = File(context.filesDir, "offline_files").apply { mkdirs() }

            repeat(PAGE_COUNT) { pageIndex ->
                val page = ReadingListPage(
                    wiki = WikiSite.forLanguageCode("en"),
                    namespace = Namespace.MAIN,
                    displayTitle = "M6 P02 page $pageIndex",
                    apiTitle = "M6_P02_page_$pageIndex",
                    listId = fixtureListId,
                    offline = true,
                    status = ReadingListPage.STATUS_SAVED,
                    sizeBytes = OBJECTS_PER_PAGE * CONTENT_BYTES.toLong(),
                    lang = "en"
                )
                page.id = database.readingListPageDao().insertReadingListPage(page)
                fixturePages += page

                repeat(OBJECTS_PER_PAGE) { objectIndex ->
                    val stem = File(offlineDirectory, "m6-p02-$pageIndex-$objectIndex")
                    val metadata = File("${stem.absolutePath}.0").apply {
                        writeText("m6-p02 metadata page=$pageIndex object=$objectIndex\n")
                    }
                    val contents = File("${stem.absolutePath}.1").apply {
                        writeBytes(ByteArray(CONTENT_BYTES) { ((pageIndex + objectIndex) % 251).toByte() })
                    }
                    fixtureFiles += metadata
                    fixtureFiles += contents

                    val url = "https://example.invalid/m6-p02/$pageIndex/$objectIndex"
                    fixtureUrls += url
                    database.offlineObjectDao().insertOfflineObject(
                        OfflineObject(
                            url = url,
                            lang = "en",
                            path = stem.absolutePath,
                            status = 0,
                            usedByStr = "|${page.id}|"
                        )
                    )
                }
            }

            assertEquals(PAGE_COUNT, fixturePages.size)
            assertEquals(PAGE_COUNT * OBJECTS_PER_PAGE, fixtureUrls.size)
            assertEquals(PAGE_COUNT * OBJECTS_PER_PAGE * 2, fixtureFiles.count(File::exists))
        }
    }

    @After
    fun removeFixtureResidue() {
        runBlocking {
            workManager.cancelUniqueWork(WORK_NAME).result.get(10, TimeUnit.SECONDS)
            val database = AppDatabase.instance
            fixtureUrls.forEach { url ->
                database.offlineObjectDao().getOfflineObject(url)?.let {
                    database.offlineObjectDao().deleteOfflineObject(it)
                }
            }
            fixtureFiles.forEach { it.delete() }
            fixturePages.forEach { page ->
                database.readingListPageDao().getPageById(page.id)?.let {
                    database.readingListPageDao().deleteReadingListPage(it)
                }
            }
            database.readingListDao().getListById(fixtureListId)?.let {
                database.readingListDao().deleteReadingList(it)
            }
        }
    }

    @Test
    fun removingAllOfflinePagesReclaimsAssociatedFiles() {
        runBlocking {
            val database = AppDatabase.instance
            val bytesBefore = fixtureFiles.filter(File::exists).sumOf(File::length)
            val startedAt = SystemClock.elapsedRealtime()

            database.readingListPageDao().markPagesForOffline(
                fixturePages,
                offline = false,
                forcedSave = false
            )

            var terminalState: WorkInfo.State? = null
            withTimeout(WORK_TIMEOUT_MS) {
                while (terminalState == null) {
                    terminalState = workManager.getWorkInfosForUniqueWork(WORK_NAME)
                        .get(10, TimeUnit.SECONDS)
                        .lastOrNull()
                        ?.state
                        ?.takeIf(WorkInfo.State::isFinished)
                    if (terminalState == null) {
                        delay(POLL_INTERVAL_MS)
                    }
                }
            }

            val elapsedMs = SystemClock.elapsedRealtime() - startedAt
            val remainingFiles = fixtureFiles.filter(File::exists)
            val remainingObjects = fixtureUrls.mapNotNull {
                database.offlineObjectDao().getOfflineObject(it)
            }
            val updatedPages = fixturePages.mapNotNull {
                database.readingListPageDao().getPageById(it.id)
            }
            val bytesAfter = remainingFiles.sumOf(File::length)

            println(
                "M6_P02_RESULT pages=$PAGE_COUNT objects=${fixtureUrls.size} " +
                    "bytes_before=$bytesBefore bytes_after=$bytesAfter " +
                    "remaining_files=${remainingFiles.size} remaining_objects=${remainingObjects.size} " +
                    "worker_state=$terminalState elapsed_ms=$elapsedMs"
            )

            assertEquals(WorkInfo.State.SUCCEEDED, terminalState)
            assertTrue("fixture must exercise a non-zero storage delta", bytesBefore > 0)
            assertEquals(0L, bytesAfter)
            assertTrue(remainingFiles.isEmpty())
            assertTrue(remainingObjects.isEmpty())
            assertEquals(PAGE_COUNT, updatedPages.size)
            updatedPages.forEach {
                assertFalse(it.offline)
                assertEquals(ReadingListPage.STATUS_QUEUE_FOR_SAVE, it.status)
            }
            fixtureUrls.forEach {
                assertNull(database.offlineObjectDao().getOfflineObject(it))
            }
        }
    }

    companion object {
        private const val WORK_NAME = "savePageSyncService"
        private const val FIXTURE_LIST_TITLE = "M6 P-02 storage admission"
        private const val PAGE_COUNT = 24
        private const val OBJECTS_PER_PAGE = 4
        private const val CONTENT_BYTES = 65_536
        private const val WORK_TIMEOUT_MS = 30_000L
        private const val POLL_INTERVAL_MS = 250L
    }
}
