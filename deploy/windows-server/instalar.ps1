# Instala o actualiza el Portal de Datos Inverpalmas en el servidor.
# Uso (PowerShell como administrador, desde esta carpeta):
#   powershell -ExecutionPolicy Bypass -File .\instalar.ps1
$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Paso($texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }

Paso 'Verificando Docker'
docker version --format '{{.Server.Os}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker no responde. Abre Docker Desktop y espera a que diga "Engine running".' }
$os = docker version --format '{{.Server.Os}}'
if ($os -ne 'linux') { throw "Docker esta en modo '$os'. Cambia a contenedores Linux (clic derecho en el icono de Docker > Switch to Linux containers)." }

Paso 'Cargando imagenes'
Get-ChildItem -Path .\imagenes -Filter *.tar | ForEach-Object {
    Write-Host "   $($_.Name)"
    docker load -i $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "No se pudo cargar $($_.Name)" }
}

Paso 'Revisando archivos de configuracion'
if (-not (Test-Path .\.env)) { throw 'Falta el archivo .env en esta carpeta (copia .env.ejemplo y completalo).' }
# Si el archivo no existe, Docker crearia una carpeta con ese nombre y la app no arrancaria.
if (-not (Test-Path .\.app_config_overrides.json)) { Set-Content -Path .\.app_config_overrides.json -Value '{}' -Encoding ascii }
New-Item -ItemType Directory -Force -Path .\logs | Out-Null

function LeerEnv($nombre, $porDefecto) {
    $m = Select-String -Path .\.env -Pattern "^\s*$nombre\s*=\s*(.+)$" | Select-Object -First 1
    if ($m) { return $m.Matches[0].Groups[1].Value.Trim() }
    return $porDefecto
}

$dbHost = LeerEnv 'DB_HOST' 'db'
$perfil = @()
if ($dbHost -eq 'db') {
    Write-Host '   DB_HOST=db: se levanta MySQL en contenedor'
    $perfil = @('--profile', 'localdb')
} else {
    Write-Host "   Base de datos externa: $dbHost"
}

Paso 'Iniciando contenedores'
docker compose @perfil up -d --remove-orphans
if ($LASTEXITCODE -ne 0) { throw 'docker compose up fallo' }

$puerto = LeerEnv 'APP_PORT' '8000'

Paso "Esperando a que responda http://localhost:$puerto/health (hasta 3 min)"
$ok = $false
for ($i = 0; $i -lt 36; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:$puerto/health" -UseBasicParsing -TimeoutSec 5
        Write-Host $r.Content
        $ok = $true
        break
    } catch { Start-Sleep -Seconds 5 }
}

docker compose @perfil ps
if ($ok) {
    Write-Host "`nListo: http://localhost:$puerto/app/" -ForegroundColor Green
    Write-Host 'Revisa en el /health de arriba que cada share (produc, Usuarios, newfact) aparezca montado.'
} else {
    Write-Host "`nLa app no respondio. Ultimas lineas del log:" -ForegroundColor Yellow
    docker logs --tail 60 inverpalmas-portal
    exit 1
}
