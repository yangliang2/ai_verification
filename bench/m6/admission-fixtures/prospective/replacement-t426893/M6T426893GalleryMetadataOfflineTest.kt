package org.wikipedia.m6

import org.junit.Assert.assertTrue
import org.junit.Test
import org.wikipedia.dataclient.RestService
import org.wikipedia.dataclient.Service
import retrofit2.http.Header

/**
 * T426893 admission oracle.
 *
 * The gallery already has an offline-cache contract for the media-list
 * response. The image metadata request made for each gallery item must expose
 * the same save/lang/title headers before the gallery can render a cached image
 * while offline. This source-shape check is intentionally bounded and does not
 * depend on a live Wikimedia response or an OEM storage layout.
 */
class M6T426893GalleryMetadataOfflineTest {
    @Test
    fun galleryMetadataEndpointCanParticipateInOfflineCache() {
        val mediaListHeaderSlots = RestService::class.java.methods
            .filter { it.name == "getMediaList" }
            .maxOf { method -> method.parameterAnnotations.count(::hasHeader) }
        val imageInfoHeaderSlots = Service::class.java.methods
            .filter { it.name == "getImageInfo" }
            .maxOf { method -> method.parameterAnnotations.count(::hasHeader) }

        println(
            "M6_T426893_RESULT media_list_header_slots=$mediaListHeaderSlots " +
                "image_info_header_slots=$imageInfoHeaderSlots expected_min=3"
        )

        assertTrue(
            "gallery media metadata must expose save/lang/title headers for offline replay; " +
                "mediaList=$mediaListHeaderSlots imageInfo=$imageInfoHeaderSlots",
            mediaListHeaderSlots >= REQUIRED_HEADER_SLOTS &&
                imageInfoHeaderSlots >= REQUIRED_HEADER_SLOTS
        )
    }

    private fun hasHeader(annotations: Array<Annotation>): Boolean {
        return annotations.any { it.annotationClass.java == Header::class.java }
    }

    companion object {
        private const val REQUIRED_HEADER_SLOTS = 3
    }
}
