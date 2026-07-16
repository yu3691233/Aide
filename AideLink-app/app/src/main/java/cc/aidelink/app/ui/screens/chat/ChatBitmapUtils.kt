package cc.aidelink.app.ui.screens.chat

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asAndroidBitmap

internal fun decodeScaledBitmap(bytes: ByteArray, maxDim: Int = 1920): Bitmap? {
    val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts)
    val w = opts.outWidth
    val h = opts.outHeight
    if (w <= 0 || h <= 0) return null

    var sample = 1
    while (w / sample > maxDim * 2 || h / sample > maxDim * 2) sample *= 2

    val decodeOpts = BitmapFactory.Options().apply { inSampleSize = sample }
    val decoded = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, decodeOpts) ?: return null
    if (decoded.width <= maxDim && decoded.height <= maxDim) return decoded

    val scale = maxDim.toFloat() / maxOf(decoded.width, decoded.height)
    val scaled = Bitmap.createScaledBitmap(
        decoded,
        (decoded.width * scale).toInt(),
        (decoded.height * scale).toInt(),
        true,
    )
    if (scaled !== decoded) decoded.recycle()
    return scaled
}

internal fun centerRegionHash(bytes: ByteArray): Long {
    return runCatching {
        val opts = BitmapFactory.Options().apply { inSampleSize = 4 }
        val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts) ?: return 0L

        val cx = bmp.width / 2
        val cy = bmp.height / 2
        val size = minOf(64, bmp.width / 4, bmp.height / 4)
        val region = Bitmap.createBitmap(bmp, cx - size / 2, cy - size / 2, size, size)
        if (region !== bmp) bmp.recycle()

        val pixels = IntArray(size * size)
        region.getPixels(pixels, 0, size, 0, 0, size, size)
        region.recycle()

        var h = 0L
        for (p in pixels) {
            h = h * 31 + ((p shr 16) and 0xFF) + ((p shr 8) and 0xFF) + (p and 0xFF)
        }
        h
    }.getOrDefault(0L)
}

internal fun recycleOldBitmap(imageBitmap: ImageBitmap?) {
    if (imageBitmap == null) return
    runCatching {
        val bitmap = imageBitmap.asAndroidBitmap()
        if (!bitmap.isRecycled) {
            bitmap.recycle()
        }
    }
}
