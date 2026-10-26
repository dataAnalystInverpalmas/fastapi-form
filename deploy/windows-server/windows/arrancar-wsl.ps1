# Lo ejecuta la tarea programada "Inverpalmas Portal - WSL" al iniciar Windows.
#  1. Enciende WSL y Docker (los contenedores arrancan solos por restart: unless-stopped).
#  2. Redirige el puerto de Windows a la IP de WSL, que cambia en cada reinicio.
#  3. Se queda corriendo para que WSL no se apague por inactividad.
param(
    [string]$Distro = '',
    [int]$Puerto = 8000
)
$ErrorActionPreference = 'Continue'
$log = Join-Path $PSScriptRoot 'arranque.log'
function Log($mensaje) { "$(Get-Date -Format s) $mensaje" | Add-Content -Path $log -Encoding utf8 }

$d = @()
if ($Distro) { $d = @('-d', $Distro) }

Log 'Iniciando WSL'
& wsl.exe @d -u root --exec systemctl start docker 2>$null

$ip = ''
for ($i = 0; $i -lt 30 -and -not $ip; $i++) {
    $ip = (& wsl.exe @d -u root --exec sh -c 'ip -4 -o addr show eth0 | awk ''{print $4}'' | cut -d/ -f1' 2>$null | Out-String).Trim()
    if (-not $ip) { Start-Sleep -Seconds 2 }
}
if (-not $ip) {
    Log 'ERROR: no se obtuvo la IP de WSL; no se configuro el puerto'
} else {
    netsh interface portproxy delete v4tov4 listenport=$Puerto listenaddress=0.0.0.0 | Out-Null
    netsh interface portproxy add v4tov4 listenport=$Puerto listenaddress=0.0.0.0 connectport=$Puerto connectaddress=$ip | Out-Null
    Log "Puerto $Puerto de Windows -> ${ip}:$Puerto (WSL)"
}

# Bloquea mientras Windows este encendido: mantiene viva la distro de WSL.
Log 'Manteniendo WSL encendido'
& wsl.exe @d -u root --exec sleep infinity
Log 'WSL se detuvo'
