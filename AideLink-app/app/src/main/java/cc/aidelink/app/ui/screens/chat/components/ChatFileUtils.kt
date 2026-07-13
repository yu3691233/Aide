package cc.aidelink.app.ui.screens.chat.components

import android.content.Context
import android.net.Uri
import java.io.File
import java.io.FileOutputStream

internal fun copyUriToTempFile(context: Context, uri: Uri): String? {
    return try {
        val inputStream = context.contentResolver.openInputStream(uri)
        val filename = "upload_${System.currentTimeMillis()}.jpg"
        val file = File(context.cacheDir, filename)
        val outputStream = FileOutputStream(file)
        inputStream?.use { input ->
            outputStream.use { output ->
                input.copyTo(output)
            }
        }
        file.absolutePath
    } catch (_: Exception) {
        null
    }
}
