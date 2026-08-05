package aiverify.discovery.state

/** The bounded local recovery epoch used by the Android adapter. */
interface RecoveryBoundary {
    fun rotate()
    fun processDeath()
    fun backupRestore()
}
