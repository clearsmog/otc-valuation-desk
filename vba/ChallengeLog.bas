Attribute VB_Name = "ChallengeLog"
' Exception log for the daily price-challenge sheet.
'
' Run BuildExceptionLog on outputs/<date>/valuation_report.xlsx (imported into
' the workbook, saved as .xlsm). It reads the "Challenges" sheet and builds an
' "Exceptions" sheet:
'   - only trades outside tolerance (EXPLAINED / LIKELY / UNEXPLAINED)
'   - ranked by how many tolerances the gap is (|difference| / tolerance)
'   - owner, date raised and a resolution drop-down for the follow-up
'   - a counterparty x status count, for the dealer service review
' Written for Excel on Windows and Mac: no Scripting.Dictionary, no ActiveX.
Option Explicit

Private Const SRC_SHEET As String = "Challenges"
Private Const DST_SHEET As String = "Exceptions"

Private Function ColumnOf(ws As Worksheet, header As String) As Long
    Dim c As Long, lastCol As Long
    lastCol = ws.Cells(1, ws.Columns.Count).End(xlToLeft).Column
    For c = 1 To lastCol
        If LCase$(Trim$(CStr(ws.Cells(1, c).Value))) = LCase$(header) Then
            ColumnOf = c
            Exit Function
        End If
    Next c
    ColumnOf = 0
End Function

Public Sub BuildExceptionLog()
    RunLog False
End Sub

' Same as BuildExceptionLog without message boxes, for scripted runs
' (AppleScript "run VB macro" or Application.Run).
Public Sub BuildExceptionLogQuiet()
    RunLog True
End Sub

Private Sub RunLog(ByVal quiet As Boolean)
    Dim src As Worksheet, dst As Worksheet
    Dim names As Variant, cols(0 To 8) As Long
    Dim i As Long, r As Long, outRow As Long, lastRow As Long
    Dim tol As Double

    Set src = ThisWorkbook.Worksheets(SRC_SHEET)
    names = Array("trade_id", "counterparty", "ccy", "difference", "tolerance", "status", "cause", "detail", "action")
    For i = 0 To 8
        cols(i) = ColumnOf(src, CStr(names(i)))
        If cols(i) = 0 Then
            If quiet Then Err.Raise vbObjectError + 513, "ChallengeLog", "Column '" & names(i) & "' not found"
            MsgBox "Column '" & names(i) & "' not found on sheet " & SRC_SHEET, vbExclamation
            Exit Sub
        End If
    Next i
    lastRow = src.Cells(src.Rows.Count, cols(0)).End(xlUp).Row

    Application.ScreenUpdating = False
    Application.DisplayAlerts = False
    On Error Resume Next
    ThisWorkbook.Worksheets(DST_SHEET).Delete
    On Error GoTo 0
    Application.DisplayAlerts = True
    Set dst = ThisWorkbook.Worksheets.Add(After:=src)
    dst.Name = DST_SHEET

    dst.Range("A1:M1").Value = Array("trade_id", "counterparty", "ccy", "difference", "tolerance", _
        "x_tolerance", "status", "cause", "detail", "action", "owner", "raised", "resolution")

    outRow = 2
    For r = 2 To lastRow
        If CStr(src.Cells(r, cols(5)).Value) <> "WITHIN_TOLERANCE" Then
            dst.Cells(outRow, 1).Value = src.Cells(r, cols(0)).Value
            dst.Cells(outRow, 2).Value = src.Cells(r, cols(1)).Value
            dst.Cells(outRow, 3).Value = src.Cells(r, cols(2)).Value
            dst.Cells(outRow, 4).Value = src.Cells(r, cols(3)).Value
            tol = CDbl(src.Cells(r, cols(4)).Value)
            dst.Cells(outRow, 5).Value = tol
            If tol > 0 Then dst.Cells(outRow, 6).Value = Abs(CDbl(src.Cells(r, cols(3)).Value)) / tol
            dst.Cells(outRow, 7).Value = src.Cells(r, cols(5)).Value
            dst.Cells(outRow, 8).Value = src.Cells(r, cols(6)).Value
            dst.Cells(outRow, 9).Value = src.Cells(r, cols(7)).Value
            dst.Cells(outRow, 10).Value = src.Cells(r, cols(8)).Value
            dst.Cells(outRow, 12).Value = Date
            dst.Cells(outRow, 13).Value = "Open"
            outRow = outRow + 1
        End If
    Next r
    lastRow = outRow - 1

    If lastRow >= 2 Then
        With dst.Sort
            .SortFields.Clear
            .SortFields.Add Key:=dst.Range("F2:F" & lastRow), Order:=xlDescending
            .SetRange dst.Range("A1:M" & lastRow)
            .Header = xlYes
            .Apply
        End With
        With dst.Range("M2:M" & lastRow).Validation
            .Delete
            .Add Type:=xlValidateList, AlertStyle:=xlValidAlertStop, Formula1:="Open,Sent to dealer,Resolved,Escalated"
        End With
        dst.Range("D2:E" & lastRow).NumberFormat = "#,##0;[Red]-#,##0"
        dst.Range("F2:F" & lastRow).NumberFormat = "0.0"
        dst.Range("L2:L" & lastRow).NumberFormat = "yyyy-mm-dd"
        For r = 2 To lastRow
            Select Case CStr(dst.Cells(r, 7).Value)
                Case "UNEXPLAINED": dst.Range("A" & r & ":M" & r).Interior.Color = RGB(248, 203, 173)
                Case "LIKELY": dst.Range("A" & r & ":M" & r).Interior.Color = RGB(252, 228, 214)
                Case "EXPLAINED": dst.Range("A" & r & ":M" & r).Interior.Color = RGB(255, 242, 204)
            End Select
        Next r
        CounterpartySummary dst, lastRow
    End If

    dst.Rows(1).Font.Bold = True
    dst.Columns("A:H").AutoFit
    dst.Columns("I:J").ColumnWidth = 50
    dst.Activate
    ActiveWindow.FreezePanes = False
    dst.Range("A2").Select
    ActiveWindow.FreezePanes = True
    Application.ScreenUpdating = True
    If Not quiet Then MsgBox CStr(lastRow - 1) & " exceptions logged on sheet " & DST_SHEET, vbInformation
End Sub

' Counterparty x status counts to the right of the log, built with COUNTIFS so
' they update when a status is edited by hand.
Private Sub CounterpartySummary(dst As Worksheet, lastRow As Long)
    Const LEFT_COL As Long = 15 ' column O
    Dim statuses As Variant, r As Long, n As Long, j As Long, found As Variant
    Dim cpty As String

    statuses = Array("EXPLAINED", "LIKELY", "UNEXPLAINED")
    dst.Cells(1, LEFT_COL).Value = "counterparty"
    For j = 0 To 2
        dst.Cells(1, LEFT_COL + 1 + j).Value = statuses(j)
    Next j
    dst.Cells(1, LEFT_COL + 4).Value = "total"

    n = 1
    For r = 2 To lastRow
        cpty = CStr(dst.Cells(r, 2).Value)
        found = Application.Match(cpty, dst.Range(dst.Cells(1, LEFT_COL), dst.Cells(n, LEFT_COL)), 0)
        If IsError(found) Then
            n = n + 1
            dst.Cells(n, LEFT_COL).Value = cpty
        End If
    Next r

    For r = 2 To n
        For j = 0 To 2
            dst.Cells(r, LEFT_COL + 1 + j).Formula = "=COUNTIFS($B$2:$B$" & lastRow & ",$O" & r & _
                ",$G$2:$G$" & lastRow & "," & dst.Cells(1, LEFT_COL + 1 + j).Address & ")"
        Next j
        dst.Cells(r, LEFT_COL + 4).Formula = "=SUM(P" & r & ":R" & r & ")"
    Next r
    dst.Range(dst.Cells(1, LEFT_COL), dst.Cells(1, LEFT_COL + 4)).Font.Bold = True
    dst.Range(dst.Cells(2, LEFT_COL), dst.Cells(n, LEFT_COL)).Sort Key1:=dst.Cells(2, LEFT_COL), Order1:=xlAscending, Header:=xlNo
End Sub
