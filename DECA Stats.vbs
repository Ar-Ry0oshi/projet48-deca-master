Dim py, pytw, root, shell, fso, rc, q

Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
q = Chr(34)

py   = "C:\SafApp\Python\Python3.14-64\python.exe"
pytw = "C:\SafApp\Python\Python3.14-64\pythonw.exe"
If Not fso.FileExists(py) Then
    py   = "python"
    pytw = "pythonw"
End If

rc = shell.Run(q & py & q & " -c " & q & "import PyQt6, pandas, openpyxl, matplotlib" & q, 0, True)
If rc <> 0 Then
    shell.Run q & root & "\lancer_stats.bat" & q, 1, False
Else
    shell.Run q & pytw & q & " " & q & root & "\stats_app.py" & q, 0, False
End If
