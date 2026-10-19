' Chạy một file .bat không hiện cửa sổ: wscript chay_an.vbs <file.bat> [tham số...]
Dim sh, i, lenh
Set sh = CreateObject("WScript.Shell")
lenh = """" & WScript.Arguments(0) & """"
For i = 1 To WScript.Arguments.Count - 1
    lenh = lenh & " " & WScript.Arguments(i)
Next
WScript.Quit sh.Run(lenh, 0, True)
