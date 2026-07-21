package dev.aiverify.lifecyclefixture;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class ConcurrencyControlReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        String command = intent.getStringExtra("command");
        if (command == null || !ConcurrencyActivity.command(command)) {
            setResultCode(2);
        } else {
            setResultCode(0);
        }
    }
}
