package aiverify.discovery.state

/** Current reader and the single v1 → v2 migration boundary. */
class StateStoreV2 {
    fun migrate(source: LegacyState): CurrentState = CurrentState(
        sentinel = source.sentinel,
        schemaVersion = 2,
        revision = 42,
        migrationStatus = "MIGRATED_V1_TO_V2",
    )

    fun read(): CurrentState = error("runtime adapter supplies the persisted record")
}

data class CurrentState(
    val sentinel: String,
    val schemaVersion: Int,
    val revision: Int,
    val migrationStatus: String,
)
