Dim py, pytw, root, shell, fso, rc

Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)

py   = "C:\SafApp\Python\Python3.14-64\python.exe"
pytw = "C:\SafApp\Python\Python3.14-64\pythonw.exe"
If Not fso.FileExists(py) Then
    py   = "python"
    pytw = "pythonw"
End If

rc = shell.Run """" & py & """ -c ""import PyQt6, pandas, openpyxl, matplotlib""", 0, True
If rc <> 0 Then
    shell.Run """" & root & "\lancer_manager.bat""", 1, False
Else
    shell.Run """" & pytw & """ """ & root & "\deca_manager.py""", 0, False
End If
