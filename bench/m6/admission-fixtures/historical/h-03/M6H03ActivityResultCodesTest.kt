package org.wikipedia.m6

import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertNotEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.wikipedia.search.SearchActivity
import org.wikipedia.search.SearchFragment

@RunWith(AndroidJUnit4::class)
class M6H03ActivityResultCodesTest {
    @Test
    fun searchResultCallbacksUseDistinctResultCodes() {
        assertNotEquals(
            "Link-success and language-change callbacks must not collide.",
            SearchActivity.RESULT_LINK_SUCCESS,
            SearchFragment.RESULT_LANG_CHANGED
        )
    }
}
