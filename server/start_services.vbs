Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
serverDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.Environment("Process")("PYTHONPATH") = serverDir
pythonw = WshShell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Python312\pythonw.exe"
bundledPython = FSO.BuildPath(FSO.GetParentFolderName(serverDir), "runtime\Scripts\pythonw.exe")
embeddedPython = FSO.BuildPath(FSO.GetParentFolderName(serverDir), "runtime\pythonw.exe")
If FSO.FileExists(embeddedPython) Then
    bundledPython = embeddedPython
    logDir = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\AideLink\logs"
    If Not FSO.FolderExists(logDir) Then FSO.CreateFolder(logDir)
    WshShell.Environment("Process")("AIDELINK_LOG_DIR") = logDir
End If
If FSO.FileExists(bundledPython) Then pythonw = bundledPython
If Not FSO.FileExists(pythonw) Then pythonw = "pythonw.exe"
command = Chr(34) & pythonw & Chr(34) & " " & Chr(34) & serverDir & "\start_services.py" & Chr(34)
WshShell.Run command, 0, False
