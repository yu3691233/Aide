; AideLink Windows installer prototype.
; Build input is installer\staging\AideLink, prepared by the release pipeline.
; The repository install.ps1 remains the developer/debug installation path.

#define MyAppName "AideLink"
; Release CI overrides this with /DMyAppVersion=<version> from version.json.
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#define StagingDir AddBackslash(SourcePath) + "staging\AideLink"

[Setup]
AppId={{7C0C8E47-9E7C-4B1D-9E9E-2B2DBA7E1A01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\AideLink
DefaultGroupName={#MyAppName}
OutputDir=output
OutputBaseFilename=AideLink-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayName={#MyAppName}
; AideLink runs several Python child processes; PrepareToInstall below stops
; only this installation instead of asking Inno to close unrelated apps.
CloseApplications=no
RestartApplications=no

[Files]
Source: "{#StagingDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "AideLink.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\AideLink"; Filename: "{app}\server\start_services.vbs"; WorkingDir: "{app}\server"; IconFilename: "{app}\AideLink.ico"
Name: "{userdesktop}\AideLink"; Filename: "{app}\server\start_services.vbs"; WorkingDir: "{app}\server"; IconFilename: "{app}\AideLink.ico"; Tasks: desktopicon
Name: "{userdesktop}\DevSpace"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\server\start_devspace.ps1"""; WorkingDir: "{app}\server"; IconFilename: "{app}\AideLink.ico"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"

[Run]
Filename: "{sys}\wscript.exe"; Parameters: """{app}\server\start_services.vbs"""; WorkingDir: "{app}\server"; Description: "启动 AideLink"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\runtime\python.exe"; Parameters: """{app}\server\stop_manager.py"" --all --force"; WorkingDir: "{app}\server"; RunOnceId: "StopAideLink"; Flags: runhidden waituntilterminated

[UninstallDelete]
; AideLink 安装目录只包含程序、运行时和其运行状态，不包含用户目标项目。
; 清理整个安装目录，避免日志、state、缓存和临时文件残留。
Type: filesandordirs; Name: "{app}"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  StopExe, StopParams: String;
  StopResult: Integer;
begin
  Result := '';
  StopExe := ExpandConstant('{app}\runtime\python.exe');
  StopParams := '"' + ExpandConstant('{app}\server\stop_manager.py') + '" --all --force';
  if FileExists(StopExe) and FileExists(ExpandConstant('{app}\server\stop_manager.py')) then
  begin
    Exec(StopExe, StopParams, ExpandConstant('{app}\server'), SW_HIDE, ewWaitUntilTerminated, StopResult);
    Sleep(1000);
  end;
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /FI "WINDOWTITLE eq aidelink-watchdog-service*"', '', SW_HIDE, ewWaitUntilTerminated, StopResult);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /FI "WINDOWTITLE eq aidelink-bridge-service*"', '', SW_HIDE, ewWaitUntilTerminated, StopResult);
  Sleep(1000);
end;
