package cc.aidelink.app.ui.screens.chat.components

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import java.io.File
import java.io.FileOutputStream

internal fun copyUriToTempFile(context: Context, uri: Uri): String? {
    return try {
        val displayName = context.contentResolver.query(
            uri,
            arrayOf(OpenableColumns.DISPLAY_NAME),
            null,
            null,
            null,
        )?.use { cursor ->
            if (cursor.moveToFirst()) cursor.getString(0) else null
        }
        val safeName = displayName
            ?.substringAfterLast('/')
            ?.substringAfterLast('\\')
            ?.replace(Regex("[^A-Za-z0-9._-]"), "_")
            ?.takeIf { it.isNotBlank() && it != "." && it != ".." }
            ?: "attachment_${System.currentTimeMillis()}"
        val filename = "${System.currentTimeMillis()}_$safeName"
        val file = File(context.cacheDir, filename)
        context.contentResolver.openInputStream(uri)?.use { input ->
            FileOutputStream(file).use { output ->
                input.copyTo(output)
            }
        } ?: return null
        file.absolutePath
    } catch (_: Exception) {
        null
    }
}
