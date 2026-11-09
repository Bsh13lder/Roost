package app.roost.roost_mobile

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File

/// The in-app update's small platform channel (no plugin): the cache folder
/// for downloads, whether Roost may install apps, that setting, and Android's
/// own install prompt for a downloaded APK (lib/update/installer.dart).
class MainActivity : FlutterActivity() {
    private val channelName = "roost/installer"
    private val updatesFolder = "updates"
    private val apkType = "application/vnd.android.package-archive"
    private val apkName = Regex("^roost-[0-9.]+\\+[0-9]+\\.apk$")

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName)
            .setMethodCallHandler { call, result -> handle(call, result) }
        val frames = FrameGrabber { runOnUiThread(it) }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "roost/frames")
            .setMethodCallHandler { call, result -> frames.handle(call, result) }
    }

    private fun updatesDir(): File = File(cacheDir, updatesFolder).apply { mkdirs() }

    private fun handle(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "cacheDir" -> result.success(updatesDir().absolutePath)
            "canInstall" -> result.success(canInstall())
            "openInstallSettings" -> openInstallSettings(result)
            "install" -> install(call.argument<String>("path"), result)
            else -> result.notImplemented()
        }
    }

    private fun canInstall(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.O || packageManager.canRequestPackageInstalls()

    private fun openInstallSettings(result: MethodChannel.Result) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            result.success(null)
            return
        }
        val intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName"))
        try {
            startActivity(intent)
            result.success(null)
        } catch (e: ActivityNotFoundException) {
            result.error("no-settings", "This phone has no install setting screen.", null)
        }
    }

    /// Only an APK with Roost's own name, directly in the updates folder.
    private fun install(path: String?, result: MethodChannel.Result) {
        val file = path?.let { File(it).canonicalFile }
        if (file == null || file.parentFile != updatesDir().canonicalFile || !apkName.matches(file.name) || !file.isFile) {
            result.error("bad-file", "That update file is not one Roost downloaded.", null)
            return
        }
        val uri = FileProvider.getUriForFile(this, "$packageName.updates", file)
        val intent = Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, apkType)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        try {
            startActivity(intent)
            result.success(null)
        } catch (e: ActivityNotFoundException) {
            result.error("no-installer", "This phone has no app installer.", null)
        }
    }
}
