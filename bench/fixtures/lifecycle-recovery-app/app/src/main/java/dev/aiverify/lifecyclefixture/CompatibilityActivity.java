package dev.aiverify.lifecyclefixture;

import android.app.Activity;
import android.content.Context;
import android.content.res.Configuration;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.Locale;

public final class CompatibilityActivity extends Activity {
    private static final String PREFS = "compatibility";
    private static final String STATE_KEY = "sentinel";
    private static final String SENTINEL = "AIVERIFY-ISSUE-72-SENTINEL";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildContent());
    }

    private View buildContent() {
        float density = getResources().getDisplayMetrics().density;
        int padding = Math.round(24 * density);
        Configuration configuration = getResources().getConfiguration();

        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(padding, padding, padding, padding);
        content.setLayoutDirection(View.LAYOUT_DIRECTION_LOCALE);

        TextView title = text(R.id.compatibility_title, getString(R.string.compatibility_title));
        title.setTextSize(22);
        content.addView(title, matchWrap());

        LinearLayout anchors = new LinearLayout(this);
        anchors.setOrientation(LinearLayout.HORIZONTAL);
        anchors.setLayoutDirection(View.LAYOUT_DIRECTION_LOCALE);
        TextView start = text(R.id.compatibility_start_anchor, getString(R.string.compatibility_start));
        start.setGravity(Gravity.START);
        TextView end = text(R.id.compatibility_end_anchor, getString(R.string.compatibility_end));
        end.setGravity(Gravity.END);
        anchors.addView(start, weighted());
        anchors.addView(end, weighted());
        content.addView(anchors, matchWrap());

        Button create = new Button(this);
        create.setId(R.id.compatibility_create_state);
        create.setText(R.string.compatibility_create_state);
        create.setOnClickListener(view -> {
            getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                    .edit().putString(STATE_KEY, SENTINEL).apply();
            recreate();
        });
        content.addView(create, matchWrap());

        String state = getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .getString(STATE_KEY, "UNINITIALIZED");
        content.addView(text(R.id.compatibility_state, state), matchWrap());

        boolean rtl = TextUtils.getLayoutDirectionFromLocale(
                configuration.getLocales().get(0)) == View.LAYOUT_DIRECTION_RTL;
        content.addView(text(
                R.id.compatibility_direction,
                rtl ? "DIRECTION_RTL" : "DIRECTION_LTR"), matchWrap());

        Locale locale = configuration.getLocales().get(0);
        String orientation = configuration.orientation == Configuration.ORIENTATION_LANDSCAPE
                ? "landscape" : "portrait";
        String config = "locale=" + locale.toLanguageTag()
                + ";orientation=" + orientation
                + ";width_dp=" + configuration.screenWidthDp
                + ";height_dp=" + configuration.screenHeightDp
                + ";smallest_width_dp=" + configuration.smallestScreenWidthDp;
        content.addView(text(R.id.compatibility_configuration, config), matchWrap());
        return content;
    }

    private TextView text(int id, String value) {
        TextView view = new TextView(this);
        view.setId(id);
        view.setText(value);
        view.setTextSize(18);
        return view;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout.LayoutParams weighted() {
        return new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
    }
}
