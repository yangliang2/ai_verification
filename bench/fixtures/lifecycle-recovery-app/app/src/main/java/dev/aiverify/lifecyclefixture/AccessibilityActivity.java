package dev.aiverify.lifecyclefixture;

import android.app.Activity;
import android.app.Dialog;
import android.graphics.Color;
import android.graphics.drawable.ColorDrawable;
import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class AccessibilityActivity extends Activity {
    private int padding;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        padding = Math.round(24 * getResources().getDisplayMetrics().density);
        showMain();
    }

    private void showMain() {
        LinearLayout content = container();
        content.addView(text(R.id.accessibility_title, "Accessibility verification fixture", 22));
        content.addView(text(R.id.accessibility_dynamic, "Status: ready", 18));

        Button dialog = button(R.id.accessibility_dialog, "Open details");
        dialog.setContentDescription("Open details");
        dialog.setOnClickListener(view -> showDetails());
        content.addView(dialog, target());

        Button navigate = button(R.id.accessibility_navigate, "Continue");
        navigate.setContentDescription("Continue");
        navigate.setOnClickListener(view -> showDestination());
        content.addView(navigate, target());
        setContentView(content);
    }

    private void showDetails() {
        Dialog dialog = new Dialog(this);
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE);
        LinearLayout content = container();
        content.addView(text(R.id.accessibility_dialog_title, "Verification details", 22));
        content.addView(text(R.id.accessibility_dialog_message, "Dynamic status is ready", 18));
        Button close = button(R.id.accessibility_dialog_close, "Close");
        close.setContentDescription("Close");
        close.setOnClickListener(view -> dialog.dismiss());
        content.addView(close, target());
        dialog.setContentView(content);
        Window window = dialog.getWindow();
        if (window != null) {
            window.setBackgroundDrawable(new ColorDrawable(Color.WHITE));
            window.setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        }
        dialog.setOnShowListener(ignored -> {
            Window shown = dialog.getWindow();
            if (shown != null) {
                shown.setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            }
        });
        dialog.show();
    }

    private void showDestination() {
        LinearLayout content = container();
        content.addView(text(R.id.accessibility_destination, "Destination reached", 22));
        Button back = button(R.id.accessibility_back, "Back");
        back.setContentDescription("Back");
        back.setOnClickListener(view -> showMain());
        content.addView(back, target());
        setContentView(content);
    }

    private LinearLayout container() {
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(padding, padding, padding, padding);
        content.setBackgroundColor(Color.WHITE);
        return content;
    }

    private TextView text(int id, String value, int size) {
        TextView view = new TextView(this);
        view.setId(id);
        view.setText(value);
        view.setContentDescription(value);
        view.setTextSize(size);
        view.setTextColor(Color.rgb(33, 33, 33));
        return view;
    }

    private Button button(int id, String value) {
        Button view = new Button(this);
        view.setId(id);
        view.setText(value);
        view.setTextColor(Color.rgb(33, 33, 33));
        view.setAllCaps(false);
        return view;
    }

    private LinearLayout.LayoutParams target() {
        int minimum = Math.round(48 * getResources().getDisplayMetrics().density);
        return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, minimum);
    }
}
