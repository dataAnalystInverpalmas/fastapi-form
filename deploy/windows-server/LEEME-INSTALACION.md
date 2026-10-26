# Instalación en el servidor Windows

## Contenido de la carpeta

| Archivo | Para qué |
|---|---|
| `imagenes\inverpalmas-portal.tar` | La app ya compilada (backend + frontend). No hace falta internet ni código fuente. |
| `imagenes\mysql-8.0.tar` | Solo si se empaquetó con `-IncluirMysql`. |
| `docker-compose.yml` | Define el contenedor de la app (y MySQL opcional). |
| `instalar.ps1` | Carga las imágenes, arranca todo y verifica `/health`. |
| `.env` | Configuración y contraseñas (si se empaquetó con `-ConSecretos`). Si no viene, copiar `.env.ejemplo` a `.env` y completarlo. |
| `.app_config_overrides.json` | Ajustes hechos desde la pantalla Ajustes (`/config`). Se crea vacío si no existe. |

## Requisitos del servidor

1. **Docker con contenedores Linux.** La imagen es Linux, así que el servidor necesita WSL2:
   - Windows Server 2022/2025 o Windows 10/11: instalar WSL2 (`wsl --install`, reiniciar) y luego Docker Desktop.
   - Docker Desktop debe estar en modo *Linux containers* y configurado para iniciar con Windows (Settings > General > *Start Docker Desktop when you sign in*).
2. **Red:** el servidor debe llegar a `172.10.18.2` por el puerto 445 (SMB) y a la base de datos (`DB_HOST`, puerto 3306).
3. **Firewall:** abrir el puerto de la app (8000 por defecto) para los usuarios:
   ```powershell
   New-NetFirewallRule -DisplayName "Portal Inverpalmas" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
   ```

## Instalar / actualizar

1. Copiar la carpeta completa al servidor, por ejemplo a `C:\inverpalmas-portal`.
2. Revisar `.env`: `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `SMB_USERNAME`, `SMB_PASSWORD`, `SMB_DOMAIN`.
3. PowerShell como administrador:
   ```powershell
   cd C:\inverpalmas-portal
   powershell -ExecutionPolicy Bypass -File .\instalar.ps1
   ```
4. Abrir `http://<ip-del-servidor>:8000/app/`.

Para actualizar, copiar encima el nuevo `imagenes\inverpalmas-portal.tar` y volver a correr `instalar.ps1`. El `.env`, los ajustes y los logs se conservan.

## Verificar

- `http://localhost:8000/health` debe mostrar cada share (`produc`, `Usuarios`, `newfact`) como montado. Si uno falla, los jobs que lo leen fallarán; revisar usuario/clave SMB y `docker logs inverpalmas-portal`.
- Los cron diarios (10:00 hora Bogotá) corren solos mientras el contenedor esté arriba.

## Comandos útiles

```powershell
docker compose ps                       # estado
docker logs -f inverpalmas-portal       # logs en vivo
docker compose restart fastapi-app      # reiniciar la app
docker compose down                     # detener (no borra datos)
```
