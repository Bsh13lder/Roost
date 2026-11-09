package app.roost.roost_mobile

import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors

/// A video's frames for the chat (owner, 2026-11-05): evenly spaced JPEG
/// frames of one clip from the gallery, read with Android's own
/// MediaMetadataRetriever on a worker thread. No extra package.
class FrameGrabber(private val post: (Runnable) -> Unit) {
    private val worker = Executors.newSingleThreadExecutor()
    private val maxSide = 1280
    private val quality = 80
    private val maxFrames = 8

    fun handle(call: MethodCall, result: MethodChannel.Result) {
        if (call.method != "grab") {
            result.notImplemented()
            return
        }
        val path = call.argument<String>("path")
        val count = (call.argument<Int>("count") ?: maxFrames).coerceIn(1, maxFrames)
        val maxSeconds = call.argument<Int>("maxSeconds") ?: 120
        if (path == null) {
            result.error("bad-path", "Couldn't read that video.", null)
            return
        }
        worker.execute {
            try {
                val frames = grab(path, count, maxSeconds)
                post(Runnable { result.success(frames) })
            } catch (e: TooLong) {
                post(Runnable { result.error("too-long", "Pick a video of 2 minutes or less.", null) })
            } catch (e: Exception) {
                post(Runnable { result.error("unreadable", "Couldn't read that video.", null) })
            }
        }
    }

    private class TooLong : Exception()

    private fun grab(path: String, count: Int, maxSeconds: Int): List<ByteArray> {
        val retriever = MediaMetadataRetriever()
        try {
            retriever.setDataSource(path)
            val durationMs = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0L
            if (durationMs <= 0L) throw IllegalStateException("no duration")
            if (durationMs > maxSeconds * 1000L) throw TooLong()
            return (0 until count).mapNotNull { i ->
                val atUs = (durationMs * 1000L) * (2 * i + 1) / (2 * count)
                retriever.getFrameAtTime(atUs, MediaMetadataRetriever.OPTION_CLOSEST_SYNC)?.let { jpeg(it) }
            }
        } finally {
            retriever.release()
        }
    }

    private fun jpeg(frame: Bitmap): ByteArray {
        val scale = minOf(1f, maxSide.toFloat() / maxOf(frame.width, frame.height))
        val sized = if (scale < 1f) {
            Bitmap.createScaledBitmap(frame, (frame.width * scale).toInt(), (frame.height * scale).toInt(), true)
        } else frame
        val out = ByteArrayOutputStream()
        sized.compress(Bitmap.CompressFormat.JPEG, quality, out)
        if (sized !== frame) sized.recycle()
        frame.recycle()
        return out.toByteArray()
    }
}
