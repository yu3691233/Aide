package cc.aidelink.app

import android.media.projection.MediaProjectionManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import cc.aidelink.app.service.UiLocatorService

/** Transparent trampoline for the system screen-capture permission dialog. */
class MediaProjectionPermissionActivity : ComponentActivity() {

    private val projectionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        val data = result.data
        if (result.resultCode == RESULT_OK && data != null) {
            UiLocatorService.onMediaProjectionResult?.invoke(result.resultCode, data)
        } else {
            UiLocatorService.onMediaProjectionResult?.invoke(null, null)
        }
        UiLocatorService.onMediaProjectionResult = null
        finish()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val manager = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        projectionLauncher.launch(manager.createScreenCaptureIntent())
    }
}
