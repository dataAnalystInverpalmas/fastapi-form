# Configuracion de Windows, se corre UNA vez (PowerShell como administrador):
#   powershell -ExecutionPolicy Bypass -File .\configurar-windows.ps1 [-Puerto 8000] [-Distro Ubuntu]
#
# - Abre el puerto en el firewall de Windows.
# - Crea la tarea "Inverpalmas Portal - WSL", que al iniciar Windows enciende
#   WSL + Docker y redirige el puerto hacia WSL (ver arrancar-wsl.ps1).
# Debe correrlo el mismo usuario de Windows que instalo Ubuntu en WSL.
param(
    [int]$Puerto = 8000,
    [string]$Distro = ''
)
$ErrorActionPreference = 'Stop'

$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) { throw 'Abre PowerShell como administrador.' }

$destino = 'C:\ProgramData\InverpalmasPortal'
$tarea = 'Inverpalmas Portal - WSL'

Write-Host '==> Copiando script de arranque'
New-Item -ItemType Directory -Force -Path $destino | Out-Null
Copy-Item -Path (Join-Path $PSScriptRoot 'arrancar-wsl.ps1') -Destination $destino -Force

Write-Host "==> Firewall: permitiendo TCP $Puerto"
$regla = "Portal Inverpalmas ($Puerto)"
if (-not (Get-NetFirewallRule -DisplayName $regla -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $regla -Direction Inbound -Protocol TCP -LocalPort $Puerto -Action Allow | Out-Null
}

Write-Host '==> Creando tarea programada'
$argumentos = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$destino\arrancar-wsl.ps1`" -Puerto $Puerto"
if ($Distro) { $argumentos += " -Distro `"$Distro`"" }
$accion = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argumentos
$disparador = New-ScheduledTaskTrigger -AtStartup
$disparador.Delay = 'PT1M'
$config = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

# La tarea corre como este usuario (WSL se instala por usuario) aunque nadie
# haya iniciado sesion; para eso Windows pide su clave una vez.
$usuario = "$env:USERDOMAIN\$env:USERNAME"
$cred = Get-Credential -UserName $usuario -Message "Clave de Windows de $usuario (para que la tarea corra sin sesion iniciada)"
Register-ScheduledTask -TaskName $tarea -Action $accion -Trigger $disparador -Settings $config `
    -User $cred.UserName -Password $cred.GetNetworkCredential().Password -RunLevel Highest -Force | Out-Null

Write-Host '==> Iniciando la tarea ahora'
Start-ScheduledTask -TaskName $tarea
Start-Sleep -Seconds 20
Get-Content (Join-Path $destino 'arranque.log') -Tail 5 -ErrorAction SilentlyContinue
netsh interface portproxy show v4tov4

$ipLan = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)' -and $_.InterfaceAlias -notmatch 'WSL|vEthernet' } | Select-Object -First 1).IPAddress
Write-Host "`nListo. Desde otro equipo: http://${ipLan}:$Puerto/app/  (o http://$($env:COMPUTERNAME):$Puerto/app/)" -ForegroundColor Green
