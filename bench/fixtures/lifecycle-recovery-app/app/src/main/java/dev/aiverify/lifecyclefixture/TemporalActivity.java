package dev.aiverify.lifecyclefixture;

import android.app.Activity;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Log;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.Locale;

/**
 * Small buildable adapter for the frozen synchronous-weather fixture.
 *
 * The call intentionally stays on the Activity's main thread.  The defect
 * build injects the frozen 250 ms dependency delay through the Gradle resource;
 * the matched control uses the same adapter with a zero delay.
 */
public final class TemporalActivity extends Activity {
    private static final String TAG = TemporalService.TAG;

    private TemporalService service;
    private TextView status;
    private TextView latency;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        service = new TemporalService(this);
        setContentView(buildContent());
        status.setText("Weather fixture ready");
        refresh();
    }

    private LinearLayout buildContent() {
        int padding = Math.round(24 * getResources().getDisplayMetrics().density);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(padding, padding, padding, padding);

        TextView title = new TextView(this);
        title.setId(R.id.temporal_title);
        title.setText(R.string.temporal_title);
        title.setTextSize(22);
        content.addView(title, matchWrap());

        status = new TextView(this);
        status.setId(R.id.temporal_status);
        status.setTextSize(18);
        content.addView(status, matchWrap());

        latency = new TextView(this);
        latency.setId(R.id.temporal_latency);
        latency.setTextSize(16);
        content.addView(latency, matchWrap());

        Button refresh = new Button(this);
        refresh.setId(R.id.temporal_refresh);
        refresh.setText(R.string.temporal_refresh);
        refresh.setOnClickListener(view -> refresh());
        content.addView(refresh, matchWrap());
        return content;
    }

    private void refresh() {
        long started = SystemClock.uptimeMillis();
        TemporalService.Weather weather = service.current();
        long elapsed = SystemClock.uptimeMillis() - started;
        status.setText("Weather: " + weather.summary);
        latency.setText(String.format(Locale.ROOT, "Caller latency: %d ms", elapsed));
        Log.i(TAG, String.format(
                Locale.ROOT,
                "TEMPORAL_RESULT delay_ms=%d latency_ms=%d thread=%s summary=%s",
                service.delayMs(), elapsed, Thread.currentThread().getName(), weather.summary));
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
    }
}
