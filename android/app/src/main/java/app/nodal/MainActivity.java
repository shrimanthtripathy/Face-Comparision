package app.nodal;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.text.InputType;
import android.view.Menu;
import android.view.MenuItem;
import android.webkit.CookieManager;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import androidx.core.content.FileProvider;
import java.io.File;
import java.io.IOException;

/** Nodal for Android: opens your Nodal server (on your PC over Wi-Fi, or a hosted one) in a full-screen app
 *  with camera and gallery upload and PDF report downloads. The face analysis itself runs on the server. */
public class MainActivity extends Activity {
    private static final int REQ_FILE = 1;
    private WebView web;
    private ValueCallback<Uri[]> filePathCallback;
    private Uri cameraUri;
    private String serverOrigin;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        String saved = getSharedPreferences("nodal", MODE_PRIVATE).getString("server", "");
        if (saved.isEmpty()) showSetup(null); else openWeb(saved);
    }

    private static boolean isPrivateHost(String h) {
        if (h == null) return false;
        h = h.toLowerCase();
        return h.equals("localhost") || h.endsWith(".local")
            || h.matches("10\\..*|192\\.168\\..*|127\\..*|172\\.(1[6-9]|2[0-9]|3[01])\\..*");
    }

    /** Accepts "192.168.1.23:8765" or "https://name.hf.space"; plain http is allowed only for addresses on your own network. */
    private String normalise(String raw) {
        raw = raw.trim();
        if (raw.isEmpty()) return null;
        if (!raw.contains("://")) {
            String host = raw.split("[:/]")[0];
            raw = (isPrivateHost(host) ? "http://" : "https://") + raw;
        }
        Uri u = Uri.parse(raw);
        String scheme = u.getScheme();
        String host = u.getHost();
        if (host == null || scheme == null || !(scheme.equals("http") || scheme.equals("https"))) return null;
        if (scheme.equals("http") && !isPrivateHost(host)) return null;
        return scheme + "://" + u.getAuthority() + "/";
    }

    private void showSetup(String problem) {
        SharedPreferences prefs = getSharedPreferences("nodal", MODE_PRIVATE);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(48, 64, 48, 48);
        TextView title = new TextView(this);
        title.setText("Connect to Nodal");
        title.setTextSize(26);
        TextView help = new TextView(this);
        help.setText("Enter the address of your Nodal server.\n\nOn your own Wi-Fi it looks like 192.168.1.23:8765 and is shown in the Nodal window on your PC. "
            + "For a hosted server use its https address.");
        help.setPadding(0, 24, 0, 24);
        final EditText input = new EditText(this);
        input.setHint("Server address");
        input.setSingleLine(true);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        input.setText(prefs.getString("server", ""));
        final TextView error = new TextView(this);
        error.setTextColor(0xFFA8403F);
        error.setPadding(0, 16, 0, 16);
        if (problem != null) error.setText(problem);
        Button go = new Button(this);
        go.setText("Connect");
        go.setOnClickListener(v -> {
            String origin = normalise(input.getText().toString());
            if (origin == null) {
                error.setText("That address is not valid. Use something like 192.168.1.23:8765. Servers outside your own network must use https.");
                return;
            }
            getSharedPreferences("nodal", MODE_PRIVATE).edit().putString("server", origin).apply();
            openWeb(origin);
        });
        box.addView(title);
        box.addView(help);
        box.addView(input);
        box.addView(error);
        box.addView(go);
        ScrollView scroll = new ScrollView(this);
        scroll.addView(box);
        setContentView(scroll);
    }

    private void openWeb(String origin) {
        serverOrigin = origin;
        if (web == null) {
            web = new WebView(this);
            WebSettings s = web.getSettings();
            s.setJavaScriptEnabled(true);
            s.setDomStorageEnabled(true);
            s.setAllowFileAccess(false);
            s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
            CookieManager.getInstance().setAcceptCookie(true);
            web.setWebViewClient(new WebViewClient() {
                @Override public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                    Uri u = r.getUrl();
                    if (serverOrigin != null && serverOrigin.startsWith(u.getScheme() + "://" + u.getAuthority())) return false;
                    try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (ActivityNotFoundException ignored) { }
                    return true;
                }
                @Override public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                    if (r.isForMainFrame())
                        showSetup("Could not reach " + serverOrigin + ". Check the address, that Nodal is running, and that you are on the same Wi-Fi.");
                }
            });
            web.setWebChromeClient(new WebChromeClient() {
                @Override public boolean onShowFileChooser(WebView w, ValueCallback<Uri[]> callback, FileChooserParams params) {
                    return chooseFile(callback, params);
                }
            });
            web.setDownloadListener((url, userAgent, disposition, mime, length) -> {
                DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url));
                String cookie = CookieManager.getInstance().getCookie(url);
                if (cookie != null) req.addRequestHeader("Cookie", cookie);
                req.addRequestHeader("User-Agent", userAgent);
                req.setMimeType(mime);
                req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, URLUtil.guessFileName(url, disposition, mime));
                ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(req);
                Toast.makeText(this, "Saving the report to Downloads...", Toast.LENGTH_LONG).show();
            });
        }
        setContentView(web);
        web.loadUrl(origin);
    }

    /** Lets the person take a photo or pick one from the gallery or files. */
    private boolean chooseFile(ValueCallback<Uri[]> callback, WebChromeClient.FileChooserParams params) {
        if (filePathCallback != null) filePathCallback.onReceiveValue(null);
        filePathCallback = callback;
        Intent camera = null;
        try {
            File dir = new File(getCacheDir(), "photos");
            dir.mkdirs();
            File photo = File.createTempFile("capture_", ".jpg", dir);
            cameraUri = FileProvider.getUriForFile(this, getPackageName() + ".files", photo);
            camera = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
            camera.putExtra(MediaStore.EXTRA_OUTPUT, cameraUri);
            camera.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } catch (IOException e) {
            camera = null;
            cameraUri = null;
        }
        Intent chooser = Intent.createChooser(params.createIntent(), "Choose a photo");
        if (camera != null) chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS, new Intent[] { camera });
        try {
            startActivityForResult(chooser, REQ_FILE);
        } catch (ActivityNotFoundException e) {
            filePathCallback = null;
            return false;
        }
        return true;
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQ_FILE || filePathCallback == null) return;
        Uri[] result = null;
        if (resultCode == RESULT_OK) {
            if (data != null && data.getData() != null) result = new Uri[] { data.getData() };
            else if (cameraUri != null) result = new Uri[] { cameraUri };
        }
        filePathCallback.onReceiveValue(result);
        filePathCallback = null;
        cameraUri = null;
    }

    @Override public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(0, 1, 0, "Change server");
        menu.add(0, 2, 1, "Reload");
        return true;
    }

    @Override public boolean onOptionsItemSelected(MenuItem item) {
        if (item.getItemId() == 1) { showSetup(null); return true; }
        if (item.getItemId() == 2 && web != null) { web.reload(); return true; }
        return super.onOptionsItemSelected(item);
    }

    @Override public void onBackPressed() {
        if (web != null && web.getParent() != null && web.canGoBack()) web.goBack(); else super.onBackPressed();
    }

    @Override protected void onPause() {
        super.onPause();
        CookieManager.getInstance().flush();
    }
}
