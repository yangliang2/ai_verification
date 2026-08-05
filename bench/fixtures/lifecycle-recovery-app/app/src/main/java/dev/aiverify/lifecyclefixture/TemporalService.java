package dev.aiverify.lifecyclefixture;

import android.content.Context;
import android.util.Log;

/** Android adapter for the frozen synchronous-weather provider boundary. */
final class TemporalService {
    static final String TAG = "TemporalProbe";

    private final int delayMs;

    TemporalService(Context context) {
        delayMs = context.getResources().getInteger(R.integer.temporal_delay_ms);
    }

    Weather current() {
        Log.i(TAG, "TEMPORAL_REQUEST delay_ms=" + delayMs);
        if (delayMs > 0) {
            try {
                Thread.sleep(delayMs);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("weather request interrupted", interrupted);
            }
        }
        return new Weather("fixture-data");
    }

    int delayMs() {
        return delayMs;
    }

    static final class Weather {
        final String summary;

        Weather(String summary) {
            this.summary = summary;
        }
    }
}
