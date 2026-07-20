package dev.aiverify.lifecyclefixture;

import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;

public final class SensitiveActivity extends Activity {
    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        TextView marker = new TextView(this);
        marker.setText("Sensitive marker reached");
        setContentView(marker);
    }
}
