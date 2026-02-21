Set WshShell = CreateObject("WScript.Shell")
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
baseDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(scriptDir)
WshShell.CurrentDirectory = baseDir
If CreateObject("Scripting.FileSystemObject").FileExists(baseDir & "\start_gui.pyw") Then
    WshShell.Run "pythonw.exe """ & baseDir & "\start_gui.pyw""", 0, False
Else
    WshShell.Run "pythonw.exe """ & baseDir & "\main.py""", 0, False
End If
Set WshShell = Nothing
