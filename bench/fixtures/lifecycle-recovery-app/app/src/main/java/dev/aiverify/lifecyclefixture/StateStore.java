package dev.aiverify.lifecyclefixture;

import android.content.Context;
import android.content.SharedPreferences;

import java.io.File;
import java.io.IOException;

final class StateStore {
    static final String SENTINEL = "AIVERIFY-ISSUE-71-SENTINEL";
    static final int LEGACY_SCHEMA = 1;
    static final int CURRENT_SCHEMA = 2;
    static final int LEGACY_REVISION = 41;
    static final int CURRENT_REVISION = 42;
    static final String PENDING_MIGRATION = "PENDING_V1_TO_V2";
    static final String COMPLETED_MIGRATION = "MIGRATED_V1_TO_V2";
    static final String RESET_SENTINEL = "UNINITIALIZED";

    private static final String PREFS_NAME = "lifecycle_fixture";
    private static final String KEY_SCHEMA = "schema_version";
    private static final String KEY_LEGACY_SENTINEL = "legacy_sentinel";
    private static final String KEY_LEGACY_REVISION = "legacy_revision";
    private static final String KEY_SENTINEL = "sentinel";
    private static final String KEY_REVISION = "revision";
    private static final String KEY_MIGRATION = "migration_status";
    private static final String DATA_EPOCH_MARKER = "fixture-data-epoch";

    private final Context context;
    private final SharedPreferences preferences;

    StateStore(Context context) {
        this.context = context.getApplicationContext();
        this.preferences = this.context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }

    void prepareDataEpoch() {
        File marker = new File(context.getNoBackupFilesDir(), DATA_EPOCH_MARKER);
        if (marker.exists()) {
            return;
        }
        if (preferences.getInt(KEY_SCHEMA, 0) == LEGACY_SCHEMA) {
            migrateLegacyState();
        }
        try {
            if (!marker.createNewFile() && !marker.exists()) {
                throw new IOException("marker was not created");
            }
        } catch (IOException error) {
            throw new IllegalStateException("Unable to establish fixture data epoch", error);
        }
    }

    void createLegacyFixture() {
        boolean committed = preferences.edit()
                .clear()
                .putInt(KEY_SCHEMA, LEGACY_SCHEMA)
                .putString(KEY_LEGACY_SENTINEL, SENTINEL)
                .putInt(KEY_LEGACY_REVISION, LEGACY_REVISION)
                .putString(KEY_MIGRATION, PENDING_MIGRATION)
                .commit();
        if (!committed) {
            throw new IllegalStateException("Unable to commit deterministic fixture");
        }
    }

    StateRecord read() {
        int schema = preferences.getInt(KEY_SCHEMA, 0);
        if (schema == LEGACY_SCHEMA) {
            return new StateRecord(
                    preferences.getString(KEY_LEGACY_SENTINEL, RESET_SENTINEL),
                    LEGACY_SCHEMA,
                    preferences.getInt(KEY_LEGACY_REVISION, 0),
                    preferences.getString(KEY_MIGRATION, PENDING_MIGRATION));
        }
        if (schema == CURRENT_SCHEMA) {
            return new StateRecord(
                    preferences.getString(KEY_SENTINEL, RESET_SENTINEL),
                    CURRENT_SCHEMA,
                    preferences.getInt(KEY_REVISION, 0),
                    preferences.getString(KEY_MIGRATION, "UNKNOWN"));
        }
        return new StateRecord(RESET_SENTINEL, 0, 0, "NOT_CREATED");
    }

    private void migrateLegacyState() {
        StateRecord source = read();
        if (source.schemaVersion != LEGACY_SCHEMA) {
            return;
        }
        boolean committed = preferences.edit()
                .clear()
                .putInt(KEY_SCHEMA, CURRENT_SCHEMA)
                .putString(KEY_SENTINEL, source.sentinel)
                .putInt(KEY_REVISION, CURRENT_REVISION)
                .putString(KEY_MIGRATION, COMPLETED_MIGRATION)
                .commit();
        if (!committed) {
            throw new IllegalStateException("Unable to commit migrated fixture");
        }
    }

    static final class StateRecord {
        final String sentinel;
        final int schemaVersion;
        final int revision;
        final String migrationStatus;

        StateRecord(String sentinel, int schemaVersion, int revision, String migrationStatus) {
            this.sentinel = sentinel;
            this.schemaVersion = schemaVersion;
            this.revision = revision;
            this.migrationStatus = migrationStatus;
        }
    }
}
