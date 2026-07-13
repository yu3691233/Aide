package cc.aidelink.app.ui.navigation

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.widget.Toast
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import cc.aidelink.app.data.api.BridgeApi
import cc.aidelink.app.domain.model.bridge.ProjectNode
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class MainViewModel @Inject constructor(
    private val bridgeApi: BridgeApi,
    @ApplicationContext private val context: Context,
) : ViewModel() {

    data class UiLocatorState(
        val showUiLocator: Boolean = false,
        val uiLocatorLoading: Boolean = false,
        val uiLocatorError: String? = null,
        val uiLocatorDevice: String? = null,
    )

    private val _uiLocatorState = MutableStateFlow(UiLocatorState())
    val uiLocatorState: StateFlow<UiLocatorState> = _uiLocatorState.asStateFlow()

    val baseUrl: String
        get() = bridgeApi.baseUrl

    // Global state to share generated prompt prefix back to screen
    private val _lastGeneratedPrefix = MutableStateFlow("")
    val lastGeneratedPrefix: StateFlow<String> = _lastGeneratedPrefix.asStateFlow()

    fun clearLastGeneratedPrefix() {
        _lastGeneratedPrefix.value = ""
    }

    fun startUiLocator() {
        _uiLocatorState.value = UiLocatorState(
            showUiLocator = true,
            uiLocatorLoading = true,
            uiLocatorError = null,
            uiLocatorDevice = null,
        )
        viewModelScope.launch {
            try {
                val resp = bridgeApi.captureUiLocator()
                if (resp.ok) {
                    _uiLocatorState.value = _uiLocatorState.value.copy(
                        uiLocatorLoading = false,
                        uiLocatorDevice = resp.device,
                    )
                } else {
                    _uiLocatorState.value = _uiLocatorState.value.copy(
                        uiLocatorLoading = false,
                        uiLocatorError = resp.error ?: "截图与转储失败",
                    )
                }
            } catch (e: Exception) {
                _uiLocatorState.value = _uiLocatorState.value.copy(
                    uiLocatorLoading = false,
                    uiLocatorError = e.message ?: "网络异常",
                )
            }
        }
    }

    fun dismissUiLocator() {
        _uiLocatorState.value = _uiLocatorState.value.copy(showUiLocator = false)
    }

    fun locateUiElement(x: Int, y: Int, width: Int, height: Int) {
        _uiLocatorState.value = _uiLocatorState.value.copy(uiLocatorLoading = true, uiLocatorError = null)
        viewModelScope.launch {
            try {
                val resp = bridgeApi.locateUiElement(x, y, width, height)
                if (resp.ok) {
                    val prefix = if (resp.matched_code != null) {
                        val node = resp.matched_code
                        val locationPart = if (node.file != null) {
                            val lineRange = if (node.line_start != null && node.line_end != null) {
                                " (L${node.line_start}-${node.line_end})"
                            } else ""
                            "${node.file.substringAfterLast('/')}$lineRange"
                        } else {
                            node.name
                        }
                        val symbolPart = node.symbolName.let { if (it.isNotEmpty()) " 中的 $it" else "" }
                        "【代码定位：$locationPart$symbolPart】"
                    } else {
                        val el = resp.element
                        if (el != null) {
                            val nameDesc = if (el.text.isNotEmpty()) el.text else el.content_desc
                            val shortClass = el.`class`.substringAfterLast('.')
                            "【界面定位：[${if (nameDesc.isNotEmpty()) nameDesc else "无文本"}] ($shortClass)】"
                        } else {
                            "【定位成功，未匹配到元素】"
                        }
                    }

                    // Copy to clipboard
                    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                    val clip = ClipData.newPlainText("ui_locator_prefix", prefix)
                    clipboard.setPrimaryClip(clip)

                    _lastGeneratedPrefix.value = prefix
                    _uiLocatorState.value = _uiLocatorState.value.copy(
                        uiLocatorLoading = false,
                        showUiLocator = false,
                    )
                    Toast.makeText(context, "已生成提示词前缀并复制到剪贴板！", Toast.LENGTH_LONG).show()
                } else {
                    _uiLocatorState.value = _uiLocatorState.value.copy(
                        uiLocatorLoading = false,
                        uiLocatorError = resp.error ?: "定位失败",
                    )
                }
            } catch (e: Exception) {
                _uiLocatorState.value = _uiLocatorState.value.copy(
                    uiLocatorLoading = false,
                    uiLocatorError = e.message ?: "网络请求失败",
                )
            }
        }
    }

    fun captureAndSendScreenshot() {
        viewModelScope.launch {
            Toast.makeText(context, "正在截屏并发送...", Toast.LENGTH_SHORT).show()
            try {
                val captureResp = bridgeApi.captureUiLocator()
                if (captureResp.ok) {
                    val sendResp = bridgeApi.send(
                        text = "我附带了当前手机界面的截图。",
                        target = "auto",
                        imagePath = "screen.png"
                    )
                    if (sendResp.ok) {
                        Toast.makeText(context, "当前页面截图已成功发送！", Toast.LENGTH_SHORT).show()
                    } else {
                        Toast.makeText(context, "截图发送失败: ${sendResp.raw}", Toast.LENGTH_SHORT).show()
                    }
                } else {
                    Toast.makeText(context, "截图捕获失败: ${captureResp.error}", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                Toast.makeText(context, "网络异常: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }
}
