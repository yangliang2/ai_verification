package aiverify.discovery.state

/** Version-one state written before a recovery epoch. */
data class LegacyState(
    val sentinel: String,
    val schemaVersion: Int,
    val revision: Int,
    val migrationStatus: String,
)

class LegacyStateWriter {
    fun write(): LegacyState = LegacyState(
        sentinel = "AIVERIFY-ISSUE-71-SENTINEL",
        schemaVersion = 1,
        revision = 41,
        migrationStatus = "PENDING_V1_TO_V2",
    )
}
