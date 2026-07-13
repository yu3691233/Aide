package cc.aidelink.app.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView

private val DarkColorScheme = darkColorScheme(
    primary = AideLinkPrimary,
    onPrimary = Color.White,
    primaryContainer = AideLinkPrimaryDark,
    onPrimaryContainer = Color(0xFFEDE9FF),
    secondary = AideLinkSecondary,
    onSecondary = Color.Black,
    tertiary = AideLinkTertiary,
    onTertiary = Color.White,
    surface = AideLinkSurfaceDark,
    onSurface = Color(0xFFE5E1E9),
    surfaceVariant = Color(0xFF2B2B35),
    onSurfaceVariant = Color(0xFFC8C5D0),
    surfaceContainer = Color(0xFF1E1E25),
    surfaceContainerHigh = Color(0xFF262630),
    surfaceContainerHighest = Color(0xFF31313B),
    outline = Color(0xFF918F9A),
    outlineVariant = Color(0xFF47464F),
    error = AideLinkErrorRed,
    onError = Color.White
)

private val LightColorScheme = lightColorScheme(
    primary = AideLinkPrimary,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFE0E0FF),
    onPrimaryContainer = AideLinkPrimaryDark,
    secondary = AideLinkSecondary,
    onSecondary = Color.White,
    tertiary = AideLinkTertiary,
    onTertiary = Color.White,
    background = Color.White,
    surface = Color.White,
    onSurface = Color(0xFF1C1B22),
    surfaceVariant = Color(0xFFF0F0F0),
    onSurfaceVariant = Color(0xFF47464F),
    surfaceContainer = Color.White,
    surfaceContainerHigh = Color.White,
    surfaceContainerHighest = Color(0xFFF5F5F5),
    outline = Color(0xFF787680),
    outlineVariant = Color(0xFFC9C5D0),
    error = AideLinkErrorRed,
    onError = Color.White
)

/**
 * AMOLED dark color scheme — pure black surfaces for OLED battery savings.
 * Uses true black (#000000) for the main surface and very dark tones for containers,
 * ensuring cards/sheets are still visually distinguishable from the background.
 */
private val AmoledDarkColorScheme = DarkColorScheme.copy(
    background = Color.Black,
    surface = Color.Black,
    onSurface = Color(0xFFE5E1E9),
    surfaceVariant = Color(0xFF1A1A22),
    surfaceContainer = Color(0xFF0D0D12),
    surfaceContainerLow = Color(0xFF080810),
    surfaceContainerLowest = Color.Black,
    surfaceContainerHigh = Color(0xFF141419),
    surfaceContainerHighest = Color(0xFF1C1C24)
)

/**
 * AideLink Material 3 Theme
 *
 * Supports:
 * - Light/Dark theme based on system settings
 * - Dynamic color on Android 12+ (Material You)
 * - AMOLED dark mode with pure black surfaces
 * - Edge-to-edge display
 */
@Composable
fun AideLinkTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = false,
    amoledDark: Boolean = false,
    content: @Composable () -> Unit
) {
    val colorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            val scheme = if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
            if (darkTheme && amoledDark) {
                scheme.copy(
                    background = Color.Black,
                    surface = Color.Black,
                    surfaceVariant = Color(0xFF1A1A22),
                    surfaceContainer = Color(0xFF0D0D12),
                    surfaceContainerLow = Color(0xFF080810),
                    surfaceContainerLowest = Color.Black,
                    surfaceContainerHigh = Color(0xFF141419),
                    surfaceContainerHighest = Color(0xFF1C1C24)
                )
            } else {
                scheme
            }
        }
        darkTheme && amoledDark -> AmoledDarkColorScheme
        darkTheme -> DarkColorScheme
        else -> LightColorScheme
    }
    
    val view = LocalView.current

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}
