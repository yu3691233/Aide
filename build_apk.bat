@echo off
cd /d "%~dp0AideLink-app"
call gradlew.bat assembleDebug --no-daemon
echo.
echo ============================
if %ERRORLEVEL% equ 0 (
    echo BUILD SUCCESSFUL!
    echo APK: app\build\outputs\apk\debug\app-debug.apk
    echo.
    echo Pushing update notification...
    curl -s -X POST http://127.0.0.1:5000/app/notify-update 2>nul
    echo Done.
) else (
    echo BUILD FAILED!
)
echo ============================
pause
