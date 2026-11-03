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

Con el despliegue automático (abajo) no hace falta: basta con hacer push a `main`.

A mano: copia el nuevo `imagenes/inverpalmas-portal.tar` a `~/inverpalmas-portal/imagenes/` y vuelve a correr `bash instalar.sh`. El `.env`, los ajustes y los logs se conservan.

> Si usas el despliegue automático, **no** corras `instalar.sh` con un `.tar` viejo: carga esa imagen encima de la última versión desplegada.

## Despliegue automático (push a `main`)

`scripts/autodeploy.sh` corre cada 5 minutos con cron. Si hay commits nuevos en `origin/main`:

1. actualiza `~/fastapi-form` (solo avanza; si hay cambios locales, se detiene y lo anota),
2. compila la imagen,
3. corre las pruebas del backend dentro de la imagen; **si fallan, no despliega**,
4. si hay jobs ETL en curso, espera a la siguiente vuelta para no cortarlos,
5. reinicia la app con la imagen nueva,
6. revisa `/health`; si no responde en 3 minutos, vuelve a la imagen anterior.

Un commit que falló no se reintenta: se espera al siguiente push.

### Instalar (una vez, en Ubuntu)

```bash
# 1. Clon del código (si no existe). git fetch tiene que funcionar sin pedir clave.
git clone https://github.com/dataAnalystInverpalmas/fastapi-form.git ~/fastapi-form
cd ~/fastapi-form && git checkout main && git fetch origin main

# 2. cron encendido con WSL
sudo apt install -y cron
sudo systemctl enable --now cron

# 3. Programar el script cada 5 minutos
( crontab -l 2>/dev/null; echo '*/5 * * * * bash $HOME/fastapi-form/scripts/autodeploy.sh' ) | crontab -
```

Si el repositorio es privado, `git fetch` necesita credenciales guardadas (por ejemplo un token de GitHub de solo lectura con `git config --global credential.helper store`, o una deploy key SSH). Si pide clave, cron no puede responderla y el log lo muestra como `git fetch fallo`.

Para probarlo sin esperar a cron: `bash ~/fastapi-form/scripts/autodeploy.sh`.

### Revisar

```bash
tail -n 30 ~/inverpalmas-portal/logs/autodeploy.log   # qué hizo y por qué
cat ~/inverpalmas-portal/.autodeploy/deployed          # commit desplegado
cat ~/inverpalmas-portal/.autodeploy/tests.log         # salida de las últimas pruebas
```

Para volver a intentar un commit que falló (por ejemplo, tras arreglar un share): `rm ~/inverpalmas-portal/.autodeploy/failed`.

Para apagarlo: `crontab -e` y borrar la línea de `autodeploy.sh`.

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
