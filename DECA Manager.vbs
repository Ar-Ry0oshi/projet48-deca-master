Dim py, root, shell
Set shell = CreateObject("WScript.Shell")
root = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

py = "C:\SafApp\Python\Python3.14-64\pythonw.exe"
If Not CreateObject("Scripting.FileSystemObject").FileExists(py) Then
    py = "pythonw"
End If

shell.Run """" & py & """ """ & root & "\deca_manager.py""", 0, False
