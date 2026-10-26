# Instalación en el servidor (svrpalmas)

Servidor: Windows Server 2022 con Ubuntu en WSL2 y Docker instalado dentro de Ubuntu.
La app corre en un contenedor de Docker en Ubuntu. Windows solo se encarga de
encender WSL al arrancar y de pasarle las conexiones del puerto 8000.

## Contenido de la carpeta

| Archivo | Para qué |
|---|---|
| `imagenes/inverpalmas-portal.tar` | La app ya compilada (backend + frontend). |
| `docker-compose.yml` | Define el contenedor. |
| `instalar.sh` | Se corre en Ubuntu: carga la imagen, arranca la app y verifica `/health`. |
| `.env` | Configuración y contraseñas (base 172.10.18.128, usuario SMB, correo). |
| `.app_config_overrides.json` | Ajustes hechos desde la pantalla Ajustes (`/config`). |
| `windows/configurar-windows.ps1` | Se corre una vez en Windows: firewall, puerto y arranque automático. |

## Antes de empezar

- En MariaDB (172.10.18.128), el usuario de `DB_USER` tiene que poder conectarse **desde la IP de svrpalmas**. Si tiene permisos solo para algunos hosts, agrega el del servidor.
- El servidor tiene que llegar a `172.10.18.2` por el puerto 445 (carpetas compartidas).

## 1. Copiar la carpeta a Ubuntu

Copia la carpeta al servidor, por ejemplo a `C:\inverpalmas-portal`. Luego, en la terminal de Ubuntu:

```bash
cp -r /mnt/c/inverpalmas-portal ~/inverpalmas-portal
cd ~/inverpalmas-portal
```

(Se copia al disco de Linux porque desde `/mnt/c` funciona más lento.)

## 2. Dejar Docker listo para arrancar solo (una vez)

```bash
sudo systemctl enable docker
sudo usermod -aG docker $USER
```

Si `usermod` agregó el grupo, cierra y vuelve a abrir la terminal de Ubuntu.

## 3. Instalar

```bash
bash instalar.sh
```

Al final debe mostrar el `/health` con `produc`, `Usuarios` y `newfact` montados, y la URL `http://localhost:8000/app/`.

## 4. Configurar Windows (una vez)

En Windows, abre PowerShell **como administrador**, con el mismo usuario que instaló Ubuntu:

```powershell
cd C:\inverpalmas-portal\windows
powershell -ExecutionPolicy Bypass -File .\configurar-windows.ps1
```

Pide la clave de ese usuario de Windows, para que la tarea corra aunque nadie haya iniciado sesión. El script:
- abre el puerto 8000 en el firewall,
- crea la tarea **Inverpalmas Portal - WSL**, que al encender el servidor enciende WSL y Docker, redirige el puerto 8000 hacia WSL (su IP cambia en cada reinicio) y mantiene WSL encendido.

Después, desde cualquier equipo: `http://svrpalmas:8000/app/`

Para probar que todo vuelve solo, reinicia el servidor, espera 2 o 3 minutos y abre la URL sin iniciar sesión en el servidor.

## Actualizar a una versión nueva

Copia el nuevo `imagenes/inverpalmas-portal.tar` a `~/inverpalmas-portal/imagenes/` y vuelve a correr `bash instalar.sh`. El `.env`, los ajustes y los logs se conservan.

## Si algo falla

| Síntoma | Qué revisar |
|---|---|
| Un share aparece sin montar en `/health` | Usuario y clave SMB en `.env`; `docker logs inverpalmas-portal` muestra el error de `mount`. |
| Error de base de datos en el log | Permisos del usuario en MariaDB para la IP del servidor; `DB_HOST`/`DB_PASSWORD` en `.env`. |
| Funciona en el servidor pero no desde otros equipos | `netsh interface portproxy show v4tov4` debe mostrar 8000 apuntando a la IP de WSL; revisar `C:\ProgramData\InverpalmasPortal\arranque.log`. |
| Tras reiniciar no responde | Programador de tareas: que **Inverpalmas Portal - WSL** esté *En ejecución*. |

## Comandos útiles (en Ubuntu, dentro de `~/inverpalmas-portal`)

```bash
docker compose ps                    # estado
docker logs -f inverpalmas-portal    # logs en vivo
docker compose restart fastapi-app   # reiniciar la app
docker compose down                  # detener (no borra datos)
```
