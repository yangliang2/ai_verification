package dev.aiverify.lifecyclefixture;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class ConcurrencyControlReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        String command = intent.getStringExtra("command");
        if ("AWAIT_DESTROY".equals(command)) {
            PendingResult pending = goAsync();
            new Thread(() -> {
                pending.setResultCode(ConcurrencyActivity.command(command) ? 0 : 2);
                pending.finish();
            }, "issue78-await-destroy").start();
            return;
        }
        if (command == null || !ConcurrencyActivity.command(command)) {
            setResultCode(2);
        } else {
            setResultCode(0);
        }
    }
}
