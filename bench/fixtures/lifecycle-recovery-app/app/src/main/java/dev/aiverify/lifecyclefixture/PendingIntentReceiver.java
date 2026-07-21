package dev.aiverify.lifecyclefixture;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class PendingIntentReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        context.getSharedPreferences("issue74", Context.MODE_PRIVATE)
                .edit().putString("pending_intent_action", intent.getAction()).apply();
    }
}
