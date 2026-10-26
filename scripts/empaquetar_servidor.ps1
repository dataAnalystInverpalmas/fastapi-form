# Compila la imagen y arma la carpeta para instalar en el servidor Windows.
# Uso (desde la raiz del repo):
#   powershell -ExecutionPolicy Bypass -File .\scripts\empaquetar_servidor.ps1 [-IncluirMysql] [-ConSecretos]
#
#   -IncluirMysql  agrega la imagen mysql:8.0 (solo si el servidor usara DB_HOST=db y no tiene internet)
#   -ConSecretos   copia el .env y .app_config_overrides.json reales (contienen contraseñas)
param(
    [switch]$IncluirMysql,
    [switch]$ConSecretos
)
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$fecha = Get-Date -Format 'yyyyMMdd-HHmm'
$destino = Join-Path $raiz "deploy-out\inverpalmas-portal-$fecha"
New-Item -ItemType Directory -Force -Path (Join-Path $destino 'imagenes') | Out-Null

Write-Host '==> Compilando imagen inverpalmas-portal:latest'
docker compose build fastapi-app
if ($LASTEXITCODE -ne 0) { throw 'La compilacion fallo' }

Write-Host '==> Exportando imagen'
docker save -o (Join-Path $destino 'imagenes\inverpalmas-portal.tar') inverpalmas-portal:latest
if ($IncluirMysql) {
    docker pull mysql:8.0
    docker save -o (Join-Path $destino 'imagenes\mysql-8.0.tar') mysql:8.0
}

Write-Host '==> Copiando archivos de instalacion'
Copy-Item deploy\windows-server\* $destino -Recurse -Force
Copy-Item .env.example (Join-Path $destino '.env.ejemplo')
if ($ConSecretos) {
    Copy-Item .env (Join-Path $destino '.env')
    if (Test-Path .app_config_overrides.json) { Copy-Item .app_config_overrides.json $destino }
}

$tam = '{0:N0} MB' -f ((Get-ChildItem $destino -Recurse | Measure-Object Length -Sum).Sum / 1MB)
Write-Host "`nPaquete listo ($tam): $destino" -ForegroundColor Green
