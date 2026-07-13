package cc.aidelink.app

import android.app.Application
import com.topjohnwu.superuser.Shell
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class AideLinkApp : Application() {
    
    override fun onCreate() {
        super.onCreate()
        // libsu 初始化
        Shell.enableVerboseLogging = BuildConfig.DEBUG
        Shell.setDefaultBuilder(Shell.Builder.create()
            .setTimeout(30)
        )
    }
}
