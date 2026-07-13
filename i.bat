@echo off
chcp 65001 >nul
setlocal

set DEVICE=%1
if "%DEVICE%"=="" (
    for /f "tokens=1" %%d in ('adb devices ^| findstr /R /C:"device$"') do (
        set DEVICE=%%d
        goto :device_found
    )
)
:device_found
if "%DEVICE%"=="" (
    echo No device specified and no connected device found.
    echo Usage: i.bat ^<device-id-or-ip:port^>
    exit /b 1
)

echo ========================================
echo   AideLink 快捷安装工具
echo ========================================
echo.

echo [1/4] 检查设备连接...
echo %DEVICE% | find ":" >nul
if not errorlevel 1 adb connect %DEVICE% >nul 2>&1
timeout /t 2 >nul
echo   设备: %DEVICE%

echo [2/4] 构建 APK...
cd /d "%~dp0AideLink-app"
call gradlew.bat assembleDebug --no-daemon --quiet
if not exist "app\build\outputs\apk\debug\app-debug.apk" (
    echo   构建失败！
    exit /b 1
)
echo   构建成功

echo [3/4] 安装到手机...
adb -s %DEVICE% install -r "app\build\outputs\apk\debug\app-debug.apk"
if errorlevel 1 (
    echo   签名不匹配，尝试卸载后重装...
    adb -s %DEVICE% uninstall cc.aidelink.app >nul 2>&1
    adb -s %DEVICE% install -r "app\build\outputs\apk\debug\app-debug.apk"
)
echo   安装完成

echo [4/4] 启动应用...
adb -s %DEVICE% shell am start -n cc.aidelink.app/.MainActivity >nul 2>&1
echo   已启动

echo.
echo ========================================
echo   完成! AideLink 已安装并启动
echo ========================================

endlocal
