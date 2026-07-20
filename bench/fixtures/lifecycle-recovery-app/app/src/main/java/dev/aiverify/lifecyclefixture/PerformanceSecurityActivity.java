package dev.aiverify.lifecyclefixture;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;
import android.view.FrameMetrics;
import android.graphics.Canvas;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Harmless, package-confined fixture for performance and untrusted Intent checks. */
public final class PerformanceSecurityActivity extends Activity {
    public static final String EXTRA_NESTED = "nested_intent";
    private static final long DRAW_DELAY_MS = 0;
    private TextView status;
    private HandlerThread metricsThread;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        metricsThread = new HandlerThread("issue74-frame-metrics");
        metricsThread.start();
        getWindow().addOnFrameMetricsAvailableListener((window, metrics, dropped) -> {
            long totalMs = metrics.getMetric(FrameMetrics.TOTAL_DURATION) / 1_000_000;
            long previous = getSharedPreferences("issue74", MODE_PRIVATE)
                    .getLong("max_frame_total_ms", 0);
            if (totalMs > previous) {
                getSharedPreferences("issue74", MODE_PRIVATE).edit()
                        .putLong("max_frame_total_ms", totalMs).apply();
            }
        }, new Handler(metricsThread.getLooper()));
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        status = new SlowDrawTextView();
        status.setId(R.id.security_status);
        status.setText("Status: ready");
        status.setTag("security_status");
        content.addView(status);
        Button work = new Button(this);
        work.setText("Render frame");
        work.setOnClickListener(view -> renderWork());
        content.addView(work);
        setContentView(content);
        exercisePendingIntent();
        if (getIntent().getBooleanExtra("exercise_nested", false)) {
            Intent hostile = new Intent(this, SensitiveActivity.class);
            getIntent().putExtra(EXTRA_NESTED, hostile);
        }
        handleUntrusted(getIntent());
    }

    private void renderWork() {
        status.setText("Status: frame rendered");
    }

    private void handleUntrusted(Intent incoming) {
        Object raw = incoming.getExtras() == null ? null : incoming.getExtras().get(EXTRA_NESTED);
        if (raw == null) return;
        if (!(raw instanceof Intent)) {
            status.setText("Status: malformed rejected");
            return;
        }
        Intent nested = (Intent) raw;
        // Never redirect caller-controlled nested Intents. The security candidate
        // changes only this branch, and its patch target remains inside this APK.
        status.setText("Status: nested rejected");
    }

    public PendingIntent issueToken() {
        Intent explicit = new Intent(this, PendingIntentReceiver.class);
        explicit.setAction("dev.aiverify.lifecyclefixture.SAFE_TOKEN");
        return PendingIntent.getBroadcast(this, 74, explicit,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_ONE_SHOT | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    private void exercisePendingIntent() {
        PendingIntent token = issueToken();
        boolean replayDenied = false;
        try {
            Intent fillIn = new Intent().setAction("dev.aiverify.lifecyclefixture.EVIL_FILL_IN");
            token.send(this, 0, fillIn);
            token.send();
        } catch (PendingIntent.CanceledException expected) {
            replayDenied = true;
        }
        getSharedPreferences("issue74", MODE_PRIVATE).edit()
                .putBoolean("pending_intent_replay_denied", replayDenied).apply();
    }

    @Override protected void onDestroy() {
        super.onDestroy();
        if (metricsThread != null) metricsThread.quitSafely();
    }

    private final class SlowDrawTextView extends TextView {
        SlowDrawTextView() { super(PerformanceSecurityActivity.this); }
        @Override protected void onDraw(Canvas canvas) {
            long started = SystemClock.elapsedRealtime();
            SystemClock.sleep(DRAW_DELAY_MS);
            getSharedPreferences("issue74", MODE_PRIVATE).edit()
                    .putLong("last_render_work_ms", SystemClock.elapsedRealtime() - started).apply();
            super.onDraw(canvas);
        }
    }
}
