@rem AideLink Gradle wrapper (Windows .bat)
@rem Minimal shim that delegates to the bundled gradle-wrapper.jar
@echo off
setlocal
set DIRNAME=%~dp0
set APP_BASE_NAME=%~n0
set CLASSPATH=%DIRNAME%gradle\wrapper\gradle-wrapper.jar
set DEFAULT_JVM_OPTS=
if defined JAVA_HOME (
  set JAVA_EXE=%JAVA_HOME%\bin\java.exe
) else (
  set JAVA_EXE=java
)
"%JAVA_EXE%" %DEFAULT_JVM_OPTS% %JAVA_OPTS% %GRADLE_OPTS% ^
  "-Dorg.gradle.appname=%APP_BASE_NAME%" ^
  -classpath "%CLASSPATH%" ^
  org.gradle.wrapper.GradleWrapperMain %*
endlocal