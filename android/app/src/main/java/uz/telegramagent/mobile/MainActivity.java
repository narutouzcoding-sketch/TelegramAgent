package uz.telegramagent.mobile;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.util.Arrays;

public class MainActivity extends Activity {
    private WebView web;
    private TextView address;
    private ProgressBar progress;
    private LinearLayout offline;
    private LinearLayout root, toolbar;
    private boolean resumed, darkTheme, themeApplied;
    private SharedPreferences preferences;
    private String server = "";
    private boolean failed;
    private int retrySeconds = 1;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private ValueCallback<Uri[]> fileCallback;
    private PermissionRequest microphoneRequest;
    private ConnectivityManager connectivity;
    private ConnectivityManager.NetworkCallback networkCallback;
    private final Runnable retry = () -> { if (failed && !server.isEmpty()) openServer(); };
    private final Runnable themeCheck = new Runnable() {
        @Override public void run() {
            if (!resumed || web == null) return;
            if (sameOrigin(web.getUrl())) web.evaluateJavascript(
                "document.documentElement.classList.contains('dark')", value -> applyNativeTheme("true".equals(value)));
            handler.postDelayed(this, 1500);
        }
    };

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (android.os.Build.VERSION.SDK_INT >= 30) getWindow().setDecorFitsSystemWindows(false);
        else getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
        preferences = getSharedPreferences("connection", MODE_PRIVATE);
        server = preferences.getString("server", BuildConfig.DEFAULT_SERVER_URL);
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(250, 248, 255));
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            if (android.os.Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime());
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            } else {
                view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                    insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            }
            return insets;
        });
        toolbar = new LinearLayout(this);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.setPadding(dp(12), 0, dp(8), 0);
        address = new TextView(this);
        address.setTextColor(Color.rgb(83, 56, 206));
        address.setTextSize(12);
        address.setSingleLine(true);
        address.setEllipsize(android.text.TextUtils.TruncateAt.MIDDLE);
        toolbar.addView(address, new LinearLayout.LayoutParams(0, dp(44), 1));
        Button reload = button("↻", () -> { retrySeconds = 1; openServer(); });
        toolbar.addView(reload, new LinearLayout.LayoutParams(dp(48), dp(44)));
        toolbar.addView(button("Manzil", this::configure));
        root.addView(toolbar);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        root.addView(progress, new LinearLayout.LayoutParams(-1, dp(2)));
        FrameLayout content = new FrameLayout(this);
        web = new WebView(this);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(true);
        web.getSettings().setGeolocationEnabled(false);
        web.getSettings().setSupportMultipleWindows(false);
        web.getSettings().setMediaPlaybackRequiresUserGesture(true);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        content.addView(web, new FrameLayout.LayoutParams(-1, -1));
        offline = new LinearLayout(this);
        offline.setOrientation(LinearLayout.VERTICAL);
        offline.setGravity(Gravity.CENTER);
        offline.setPadding(dp(28), dp(28), dp(28), dp(28));
        offline.setBackgroundColor(Color.rgb(250, 248, 255));
        TextView explanation = new TextView(this);
        explanation.setText("Agentga ulanish kutilmoqda\n\nTelefon va kompyuter bir Wi-Fi tarmog‘ida bo‘lsin. Agent ishlashi va manzil to‘g‘ri kiritilgani tekshirilsin.");
        explanation.setGravity(Gravity.CENTER);
        explanation.setTextSize(16);
        offline.addView(explanation);
        offline.addView(button("Qayta ulanish", () -> { retrySeconds = 1; openServer(); }));
        offline.addView(button("Server manzilini o‘zgartirish", this::configure));
        content.addView(offline, new FrameLayout.LayoutParams(-1, -1));
        offline.setVisibility(View.GONE);
        root.addView(content, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(root);
        applyNativeTheme(preferences.getBoolean("dark", false));
        configureWebView();
        connectivity = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        networkCallback = new ConnectivityManager.NetworkCallback() {
            @Override public void onAvailable(Network network) {
                handler.post(() -> { if (failed) { retrySeconds = 1; openServer(); } });
            }
        };
        connectivity.registerDefaultNetworkCallback(networkCallback);
        if (server.isEmpty()) configure(); else openServer();
    }

    private void configureWebView() {
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String target = request.getUrl().toString();
                if (sameOrigin(target)) return false;
                String scheme = request.getUrl().getScheme();
                if (request.hasGesture() && Arrays.asList("https", "http", "tg").contains(scheme)) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, request.getUrl())); }
                    catch (Exception ignored) { Toast.makeText(MainActivity.this, "Havolani ochadigan ilova topilmadi", Toast.LENGTH_SHORT).show(); }
                }
                return true;
            }
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap icon) {
                progress.setVisibility(View.VISIBLE);
                address.setText("Ulanmoqda…");
            }
            @Override public void onPageFinished(WebView view, String url) {
                progress.setVisibility(View.GONE);
                CookieManager.getInstance().flush();
                if (!failed && sameOrigin(url)) {
                    offline.setVisibility(View.GONE);
                    address.setText(Uri.parse(server).getAuthority());
                    retrySeconds = 1;
                }
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) disconnected();
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                if (request.isForMainFrame() && response.getStatusCode() >= 400) disconnected();
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public void onProgressChanged(WebView view, int value) { progress.setProgress(value); }
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams parameters) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                try { startActivityForResult(parameters.createIntent(), 10); }
                catch (Exception ignored) { fileCallback.onReceiveValue(null); fileCallback = null; }
                return true;
            }
            @Override public void onPermissionRequest(PermissionRequest request) {
                handler.post(() -> {
                    if (!sameOrigin(request.getOrigin().toString()) ||
                        !Arrays.asList(request.getResources()).contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) {
                        request.deny(); return;
                    }
                    if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                        request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
                    } else {
                        if (microphoneRequest != null) microphoneRequest.deny();
                        microphoneRequest = request;
                        requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 11);
                    }
                });
            }
            @Override public void onPermissionRequestCanceled(PermissionRequest request) {
                if (microphoneRequest == request) microphoneRequest = null;
            }
        });
        web.setDownloadListener((url, agent, disposition, mime, size) -> {
            if (!sameOrigin(url)) return;
            try {
                DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
                String cookie = CookieManager.getInstance().getCookie(url);
                if (cookie != null) request.addRequestHeader("Cookie", cookie);
                request.setMimeType(mime);
                request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, URLUtil.guessFileName(url, disposition, mime));
                ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(request);
                Toast.makeText(this, "Yuklab olish boshlandi", Toast.LENGTH_SHORT).show();
            } catch (Exception ignored) { Toast.makeText(this, "Faylni yuklab bo‘lmadi", Toast.LENGTH_LONG).show(); }
        });
    }

    private void configure() {
        EditText input = new EditText(this);
        input.setText(server);
        input.setHint("http://192.168.1.10:8765");
        input.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        input.setSingleLine(true);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(24), dp(12), dp(24), dp(8));
        TextView help = new TextView(this);
        help.setText("Birinchi marta kompyuterdagi panel manzilini kiriting. Bir Wi-Fi’da mahalliy IP, server uchun HTTPS manzil ishlatiladi. Keyingi ochilishda ilova o‘zi ulanadi.");
        box.addView(help);
        box.addView(input);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("Agentga ulanish")
            .setView(box).setPositiveButton("Saqlash va ulanish", null)
            .setNegativeButton("Yopish", (item, which) -> { if (server.isEmpty()) finish(); }).create();
        dialog.setOnShowListener(item -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view -> {
            try {
                String next = ServerAddress.validate(input.getText().toString());
                if (!next.equals(server)) web.clearHistory();
                server = next;
                preferences.edit().putString("server", server).apply();
                dialog.dismiss();
                retrySeconds = 1;
                openServer();
            } catch (IllegalArgumentException error) { input.setError(error.getMessage()); }
        }));
        dialog.show();
    }

    private boolean sameOrigin(String value) {
        if (server.isEmpty()) return false;
        return ServerAddress.sameOrigin(server, value);
    }

    private void openServer() {
        if (server.isEmpty()) return;
        handler.removeCallbacks(retry);
        failed = false;
        offline.setVisibility(View.GONE);
        web.loadUrl(server);
    }

    private void disconnected() {
        failed = true;
        offline.setVisibility(View.VISIBLE);
        address.setText("Qayta ulanish kutilmoqda");
        handler.removeCallbacks(retry);
        handler.postDelayed(retry, retrySeconds * 1000L);
        retrySeconds = Math.min(30, retrySeconds * 2);
    }

    private Button button(String text, Runnable action) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextSize(12);
        button.setAllCaps(false);
        button.setTextColor(Color.rgb(83, 56, 206));
        button.setOnClickListener(view -> action.run());
        return button;
    }
    private void applyNativeTheme(boolean dark) {
        if (themeApplied && darkTheme == dark) return;
        themeApplied = true;
        darkTheme = dark;
        int background = Color.parseColor(dark ? "#10121a" : "#faf8ff");
        int foreground = Color.parseColor(dark ? "#bcb0ff" : "#5338ce");
        root.setBackgroundColor(background);
        web.setBackgroundColor(background);
        offline.setBackgroundColor(background);
        address.setTextColor(foreground);
        for (int i = 0; i < toolbar.getChildCount(); i++) {
            View child = toolbar.getChildAt(i);
            if (child instanceof TextView) ((TextView) child).setTextColor(foreground);
            if (child instanceof Button) child.setBackgroundTintList(android.content.res.ColorStateList.valueOf(background));
        }
        for (int i = 0; i < offline.getChildCount(); i++) {
            View child = offline.getChildAt(i);
            if (child instanceof TextView) ((TextView) child).setTextColor(foreground);
            if (child instanceof Button) child.setBackgroundTintList(android.content.res.ColorStateList.valueOf(background));
        }
        getWindow().setNavigationBarColor(background);
        getWindow().setStatusBarColor(background);
        if (android.os.Build.VERSION.SDK_INT >= 30 && getWindow().getInsetsController() != null) {
            int flags = android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
            getWindow().getInsetsController().setSystemBarsAppearance(dark ? 0 : flags, flags);
        } else {
            int flags = getWindow().getDecorView().getSystemUiVisibility();
            int light = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            getWindow().getDecorView().setSystemUiVisibility(dark ? flags & ~light : flags | light);
        }
        preferences.edit().putBoolean("dark", darkTheme).apply();
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    @Override protected void onResume() {
        super.onResume();
        resumed = true;
        handler.removeCallbacks(themeCheck);
        handler.post(themeCheck);
        if (web != null) web.onResume();
        if (failed) { retrySeconds = 1; handler.post(retry); }
    }
    @Override protected void onPause() {
        resumed = false;
        handler.removeCallbacks(themeCheck);
        CookieManager.getInstance().flush();
        if (web != null) web.onPause();
        handler.removeCallbacks(retry);
        super.onPause();
    }
    @Override public void onBackPressed() { if (web.canGoBack()) web.goBack(); else super.onBackPressed(); }
    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == 10 && fileCallback != null) {
            fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data));
            fileCallback = null;
        }
    }
    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == 11 && microphoneRequest != null) {
            if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED)
                microphoneRequest.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
            else microphoneRequest.deny();
            microphoneRequest = null;
        }
    }
    @Override protected void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        if (networkCallback != null) connectivity.unregisterNetworkCallback(networkCallback);
        if (microphoneRequest != null) microphoneRequest.deny();
        if (fileCallback != null) fileCallback.onReceiveValue(null);
        if (web != null) web.destroy();
        super.onDestroy();
    }
}
