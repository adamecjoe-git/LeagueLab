Option Explicit
Dim shell, encoded

If WScript.Arguments.Count <> 1 Then
    WScript.Quit 2
End If

encoded = WScript.Arguments(0)
Set shell = CreateObject("WScript.Shell")
shell.Run "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -EncodedCommand " & encoded, 0, True
WScript.Quit 0
