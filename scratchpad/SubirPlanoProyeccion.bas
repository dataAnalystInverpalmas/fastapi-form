Attribute VB_Name = "SubirPlanoProyeccion"
Option Explicit

' =====================================================================
' Sube la hoja "BASE PLANO PROYECCION" de este libro al servidor central
' (tabla stg_plano_proyeccion, via api/v1/plano_proyeccion_upload.php), y
' descarga el resultado final ya cruzado (ajustes_proyeccion) filtrado
' por esta finca, via api/v1/ajustes_proyeccion_download.php.
'
' Uso: cambia FINCA_CODE segun el libro donde pegues este modulo:
'   - Libro de Palermo -> FINCA_CODE = "002"
'   - Libro de Palmas   -> FINCA_CODE = "001"
'
' Botones sugeridos: uno que llame a SubirPlano, otro a
' DescargarAjustesProyeccion (o corre ambos seguidos: primero subes tu
' plano, luego -una vez el job del servidor ya proceso todo- descargas el
' resultado final).
'
' Requiere: Herramientas > Referencias > "Microsoft XML, v6.0" activado,
' o deja el codigo tal cual (usa CreateObject, no necesita la referencia).
' =====================================================================

Private Const FINCA_CODE As String = "002"   ' "002" = Palermo, "001" = Palmas
Private Const HOJA_NOMBRE As String = "BASE PLANO PROYECCION"
Private Const FILA_ENCABEZADO As Long = 4     ' Fila real de encabezados en la hoja
Private Const API_BASE_URL As String = "http://172.10.18.128:9258/api/v1/"
Private Const API_TOKEN As String = "9035232260ca3fc11faa82b6b32b20605fe55c242e6903ca2f7e0887c3e9be17"

Public Sub SubirPlano()
    Dim ws As Worksheet
    Dim colBloque As Long, colVariedad As Long, colCosecha As Long
    Dim colNvari As Long, colFecSiem As Long, colRev As Long
    Dim colAmort As Long, colProyectaQuipus As Long, colFinca As Long
    Dim ultimaFila As Long, fila As Long
    Dim json As String
    Dim filasJson As Collection
    Dim enviados As Long

    On Error GoTo ManejarError

    Set ws = ThisWorkbook.Sheets(HOJA_NOMBRE)

    ' Ubica cada columna por su nombre de encabezado (fila FILA_ENCABEZADO),
    ' para no depender de que el orden de columnas no cambie.
    colFinca = BuscarColumna(ws, "finca")
    colBloque = BuscarColumna(ws, "bloque")
    colVariedad = BuscarColumna(ws, "variedad")
    colCosecha = BuscarColumna(ws, "cosecha")
    colNvari = BuscarColumna(ws, "nvari")
    colFecSiem = BuscarColumna(ws, "fec_siem")
    colRev = BuscarColumna(ws, "rev")
    colAmort = BuscarColumna(ws, "amort")
    colProyectaQuipus = BuscarColumna(ws, "proyecta_quipus")

    ultimaFila = ws.Cells(ws.Rows.Count, colFinca).End(xlUp).Row

    Set filasJson = New Collection
    For fila = FILA_ENCABEZADO + 1 To ultimaFila
        If Trim(ws.Cells(fila, colFinca).Value) <> "" Then
            filasJson.Add ConstruirFilaJson( _
                ws.Cells(fila, colBloque).Value, _
                ws.Cells(fila, colVariedad).Value, _
                ws.Cells(fila, colCosecha).Value, _
                ws.Cells(fila, colNvari).Value, _
                ws.Cells(fila, colFecSiem).Value, _
                ws.Cells(fila, colRev).Value, _
                ws.Cells(fila, colAmort).Value, _
                ws.Cells(fila, colProyectaQuipus).Value _
            )
        End If
    Next fila

    If filasJson.Count = 0 Then
        MsgBox "No se encontraron filas con datos para subir.", vbExclamation
        Exit Sub
    End If

    json = "{""finca"":""" & FINCA_CODE & """,""rows"":[" & UnirColeccion(filasJson) & "]}"

    enviados = EnviarAlServidor(json)

    MsgBox "Subida completa: " & enviados & " fila(s) enviada(s) para finca " & FINCA_CODE & ".", vbInformation
    Exit Sub

ManejarError:
    MsgBox "Error al subir el plano: " & Err.Description, vbCritical
End Sub

' =====================================================================
' Descarga ajustes_proyeccion_<finca>.xlsx (ya cruzado con el Id del lote
' y filtrado por esta finca) y lo guarda en la misma carpeta del libro.
' =====================================================================
Public Sub DescargarAjustesProyeccion()
    Dim http As Object
    Dim url As String
    Dim destino As String

    On Error GoTo ManejarError

    url = API_BASE_URL & "ajustes_proyeccion_download.php?finca=" & FINCA_CODE

    Set http = CreateObject("MSXML2.XMLHTTP")
    http.Open "GET", url, False
    http.setRequestHeader "Authorization", "Bearer " & API_TOKEN
    http.send

    If http.Status <> 200 Then
        Err.Raise vbObjectError + 3, , "El servidor respondio " & http.Status & ": " & http.responseText
    End If

    destino = ThisWorkbook.Path & "\ajustes_proyeccion_" & FINCA_CODE & ".xlsx"
    GuardarBytesEnArchivo http.responseBody, destino

    MsgBox "Descarga completa: " & destino, vbInformation
    Exit Sub

ManejarError:
    MsgBox "Error al descargar ajustes_proyeccion: " & Err.Description, vbCritical
End Sub

Private Sub GuardarBytesEnArchivo(bytes As Variant, ruta As String)
    Const adTypeBinary As Long = 1
    Const adSaveCreateOverWrite As Long = 2

    Dim stream As Object
    Set stream = CreateObject("ADODB.Stream")
    stream.Type = adTypeBinary
    stream.Open
    stream.Write bytes
    stream.SaveToFile ruta, adSaveCreateOverWrite
    stream.Close
End Sub

Private Function BuscarColumna(ws As Worksheet, nombreColumna As String) As Long
    Dim celda As Range
    Set celda = ws.Rows(FILA_ENCABEZADO).Find(What:=nombreColumna, LookAt:=xlWhole, MatchCase:=False)
    If celda Is Nothing Then
        Err.Raise vbObjectError + 1, , "No se encontro la columna '" & nombreColumna & "' en la fila " & FILA_ENCABEZADO
    End If
    BuscarColumna = celda.Column
End Function

Private Function ConstruirFilaJson(bloque As Variant, variedad As Variant, cosecha As Variant, _
                                    nvari As Variant, fecSiem As Variant, rev As Variant, _
                                    amort As Variant, proyectaQuipus As Variant) As String
    Dim fecSiemTexto As String
    If IsDate(fecSiem) Then
        fecSiemTexto = Format(CDate(fecSiem), "yyyy-mm-dd")
    Else
        fecSiemTexto = CStr(fecSiem)
    End If

    ConstruirFilaJson = "{" & _
        """bloque"":""" & JsonEscapar(CStr(bloque)) & """," & _
        """variedad"":""" & JsonEscapar(CStr(variedad)) & """," & _
        """cosecha"":""" & JsonEscapar(CStr(cosecha)) & """," & _
        """nvari"":""" & JsonEscapar(CStr(nvari)) & """," & _
        """fec_siem"":""" & JsonEscapar(fecSiemTexto) & """," & _
        """rev"":" & FormatoNumeroJson(rev) & "," & _
        """amort"":" & FormatoNumeroJson(amort) & "," & _
        """proyecta_quipus"":" & FormatoNumeroJson(proyectaQuipus) & _
        "}"
End Function

Private Function FormatoNumeroJson(valor As Variant) As String
    If IsNumeric(valor) Then
        FormatoNumeroJson = Replace(CStr(CDbl(valor)), ",", ".")
    Else
        FormatoNumeroJson = "0"
    End If
End Function

Private Function JsonEscapar(texto As String) As String
    texto = Replace(texto, "\", "\\")
    texto = Replace(texto, """", "\""")
    JsonEscapar = texto
End Function

Private Function UnirColeccion(coleccion As Collection) As String
    Dim i As Long
    Dim resultado As String
    For i = 1 To coleccion.Count
        resultado = resultado & coleccion(i)
        If i < coleccion.Count Then resultado = resultado & ","
    Next i
    UnirColeccion = resultado
End Function

Private Function EnviarAlServidor(jsonBody As String) As Long
    Dim http As Object
    Set http = CreateObject("MSXML2.XMLHTTP")

    http.Open "POST", API_BASE_URL & "plano_proyeccion_upload.php", False
    http.setRequestHeader "Content-Type", "application/json"
    http.setRequestHeader "Authorization", "Bearer " & API_TOKEN
    http.send jsonBody

    If http.Status <> 200 Then
        Err.Raise vbObjectError + 2, , "El servidor respondio " & http.Status & ": " & http.responseText
    End If

    ' Respuesta esperada: {"status":"ok","data":{"finca":"...","inserted":N},...}
    Dim respuesta As String
    respuesta = http.responseText
    EnviarAlServidor = ExtraerInserted(respuesta)
End Function

Private Function ExtraerInserted(respuestaJson As String) As Long
    Dim pos As Long
    pos = InStr(respuestaJson, """inserted"":")
    If pos = 0 Then
        ExtraerInserted = 0
        Exit Function
    End If
    Dim resto As String
    resto = Mid(respuestaJson, pos + Len("""inserted"":"))
    Dim numero As String
    Dim i As Long
    For i = 1 To Len(resto)
        Dim c As String
        c = Mid(resto, i, 1)
        If c >= "0" And c <= "9" Then
            numero = numero & c
        Else
            Exit For
        End If
    Next i
    ExtraerInserted = CLng(numero)
End Function
