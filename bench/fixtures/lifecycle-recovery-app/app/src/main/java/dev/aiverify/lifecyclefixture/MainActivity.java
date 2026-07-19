package dev.aiverify.lifecyclefixture;

import android.app.Activity;
import android.app.backup.BackupManager;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private StateStore store;
    private TextView sentinelView;
    private TextView schemaView;
    private TextView revisionView;
    private TextView migrationView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        store = new StateStore(this);
        store.prepareDataEpoch();
        setContentView(buildContent());
        renderState();
    }

    private ScrollView buildContent() {
        int padding = Math.round(24 * getResources().getDisplayMetrics().density);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(padding, padding, padding, padding);

        TextView title = new TextView(this);
        title.setText(R.string.fixture_title);
        title.setTextSize(22);
        content.addView(title, matchWrap());

        Button create = new Button(this);
        create.setId(R.id.create_fixture);
        create.setText(R.string.create_fixture);
        create.setOnClickListener(view -> {
            store.createLegacyFixture();
            new BackupManager(this).dataChanged();
            renderState();
        });
        content.addView(create, matchWrap());

        sentinelView = addField(content, "Sentinel", R.id.fixture_sentinel);
        schemaView = addField(content, "Schema version", R.id.fixture_schema_version);
        revisionView = addField(content, "Revision", R.id.fixture_revision);
        migrationView = addField(content, "Migration status", R.id.fixture_migration_status);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(content);
        return scroll;
    }

    private TextView addField(LinearLayout content, String label, int id) {
        TextView labelView = new TextView(this);
        labelView.setText(label);
        labelView.setTextSize(14);
        content.addView(labelView, matchWrap());

        TextView valueView = new TextView(this);
        valueView.setId(id);
        valueView.setTextSize(18);
        content.addView(valueView, matchWrap());
        return valueView;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private void renderState() {
        StateStore.StateRecord state = store.read();
        sentinelView.setText(state.sentinel);
        schemaView.setText(Integer.toString(state.schemaVersion));
        revisionView.setText(Integer.toString(state.revision));
        migrationView.setText(state.migrationStatus);
    }
}
