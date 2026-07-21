package dev.aiverify.lifecyclefixture;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.util.Log;
import android.widget.TextView;

import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class ConcurrencyActivity extends Activity {
    static final String PREFS = "issue78";
    static final String TAG = "Issue78Journal";
    private static final Controller CONTROLLER = new Controller();

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        TextView status = new TextView(this);
        status.setId(R.id.concurrency_status);
        status.setText("Concurrency fixture ready");
        setContentView(status);
        String schedule = getIntent().getStringExtra("schedule");
        CONTROLLER.reset(getApplicationContext(), schedule == null ? "new-before-old" : schedule, this);
    }

    static boolean command(String command) { return CONTROLLER.command(command); }

    private static final class Controller {
        private final ConcurrentHashMap<String, CountDownLatch> barriers = new ConcurrentHashMap<>();
        private final ConcurrentHashMap<String, CountDownLatch> completions = new ConcurrentHashMap<>();
        private CountDownLatch destroyedCompletion;
        private Context context;
        private ConcurrencyActivity activity;
        private String schedule;
        private int sequence;
        private int latestGeneration;
        private boolean destroyed;
        private String finalState;

        synchronized void reset(Context appContext, String scheduleId, ConcurrencyActivity owner) {
            context = appContext;
            activity = owner;
            schedule = scheduleId;
            sequence = 0;
            latestGeneration = 0;
            destroyed = false;
            destroyedCompletion = new CountDownLatch(1);
            finalState = "empty";
            barriers.clear();
            completions.clear();
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().clear().commit();
            event("RESET");
            if ("new-before-old".equals(schedule)) {
                start("OLD", 1, "START_OLD");
                start("NEW", 2, "START_NEW");
            } else {
                start("PENDING", 1, "START_PENDING");
            }
        }

        private synchronized void start(String operation, int generation, String startEvent) {
            latestGeneration = Math.max(latestGeneration, generation);
            barriers.put(operation, new CountDownLatch(1));
            completions.put(operation, new CountDownLatch(1));
            event(startEvent);
            Thread worker = new Thread(() -> run(operation, generation), "issue78-" + operation.toLowerCase(Locale.ROOT));
            worker.start();
        }

        private void run(String operation, int generation) {
            try {
                if (!barriers.get(operation).await(5, TimeUnit.SECONDS)) {
                    event("TIMEOUT");
                    return;
                }
                event("COMPLETE_" + operation);
                synchronized (this) {
                    if (destroyed) {
                        finalState = "cancelled";
                        event("REJECT_DESTROYED");
                    } else if (generation != latestGeneration) {
                        event("REJECT_STALE");
                    } else {
                        finalState = operation.toLowerCase(Locale.ROOT);
                        event("APPLY_" + operation);
                    }
                    if (("OLD".equals(operation) && "new-before-old".equals(schedule)) || "PENDING".equals(operation)) {
                        event("TERMINAL");
                        persistTerminal();
                    }
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                event("TIMEOUT");
            } finally {
                completions.get(operation).countDown();
            }
        }

        boolean command(String command) {
            if ("DESTROY".equals(command)) {
                if (activity != null) activity.finish();
                return true;
            }
            if ("AWAIT_DESTROY".equals(command)) {
                try {
                    return destroyedCompletion.await(5, TimeUnit.SECONDS);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    return false;
                }
            }
            String operation = command.replace("RELEASE_", "");
            CountDownLatch barrier = barriers.get(operation);
            CountDownLatch completion = completions.get(operation);
            if (barrier == null || completion == null) return false;
            event(command);
            barrier.countDown();
            try {
                return completion.await(5, TimeUnit.SECONDS);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                return false;
            }
        }

        private synchronized void event(String name) {
            sequence += 1;
            String entry = sequence + "|" + schedule + "|" + name;
            SharedPreferences preferences = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            String journal = preferences.getString("journal", "");
            preferences.edit().putString("journal", journal + entry + "\n").commit();
            Log.i(TAG, entry);
        }

        private void persistTerminal() {
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                    .putString("schedule_id", schedule)
                    .putString("final_state", finalState)
                    .putBoolean("completed", true)
                    .commit();
        }

        synchronized void onActivityDestroyed(ConcurrencyActivity owner) {
            if (owner != activity || destroyed) return;
            destroyed = true;
            event("DESTROY");
            event("CANCEL");
            destroyedCompletion.countDown();
        }
    }

    @Override protected void onDestroy() {
        CONTROLLER.onActivityDestroyed(this);
        super.onDestroy();
    }
}
