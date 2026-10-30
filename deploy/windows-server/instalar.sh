#!/usr/bin/env bash
# Instala o actualiza el Portal de Datos Inverpalmas en Docker dentro de WSL2.
# Uso (en la terminal de Ubuntu, desde esta carpeta):
#   bash instalar.sh
set -euo pipefail
cd "$(dirname "$0")"

paso() { printf '\n==> %s\n' "$*"; }
falla() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# Lee VARIABLE=valor del .env (tolera finales de linea de Windows).
leer_env() {
  local valor
  valor="$(grep -E "^[[:space:]]*$1[[:space:]]*=" .env 2>/dev/null | head -n1 | cut -d= -f2- | tr -d '\r' | xargs || true)"
  echo "${valor:-$2}"
}

paso 'Verificando Docker'
docker info >/dev/null 2>&1 || falla 'Docker no responde. Prueba: sudo systemctl start docker (y que tu usuario este en el grupo docker: sudo usermod -aG docker $USER, luego cerrar y abrir la terminal).'
docker compose version >/dev/null 2>&1 || falla 'Falta el plugin docker compose: sudo apt install docker-compose-plugin'
if command -v systemctl >/dev/null 2>&1 && ! systemctl is-enabled --quiet docker 2>/dev/null; then
  echo '   AVISO: Docker no arranca solo con WSL. Ejecuta: sudo systemctl enable docker'
fi
case "$PWD" in
  /mnt/*) echo '   AVISO: la carpeta esta en el disco de Windows (/mnt/...). Funciona, pero es mas lento; mejor copiarla a ~/inverpalmas-portal.' ;;
esac

paso 'Cargando imagenes'
shopt -s nullglob
imagenes=(imagenes/*.tar)
[[ ${#imagenes[@]} -gt 0 ]] || falla 'No hay archivos .tar en la carpeta imagenes/'
for img in "${imagenes[@]}"; do
  echo "   $img"
  docker load -i "$img"
done

paso 'Revisando archivos de configuracion'
[[ -f .env ]] || falla 'Falta el archivo .env en esta carpeta (copia .env.ejemplo y completalo).'
# Si el archivo no existe, Docker crearia una carpeta con ese nombre y la app no arrancaria.
[[ -f .app_config_overrides.json ]] || echo '{}' > .app_config_overrides.json
mkdir -p logs

perfil=()
db_host="$(leer_env DB_HOST db)"
if [[ "$db_host" == "db" ]]; then
  echo '   DB_HOST=db: se levanta MySQL en contenedor'
  perfil=(--profile localdb)
else
  echo "   Base de datos externa: $db_host"
fi

paso 'Iniciando contenedores'
docker compose "${perfil[@]}" up -d --remove-orphans

puerto="$(leer_env APP_PORT 8000)"
paso "Esperando a que responda http://localhost:$puerto/health (hasta 3 min)"
ok=0
for _ in $(seq 1 36); do
  if respuesta="$(curl -fsS --max-time 5 "http://localhost:$puerto/health" 2>/dev/null)"; then
    echo "$respuesta"
    ok=1
    break
  fi
  sleep 5
done

docker compose "${perfil[@]}" ps
if [[ $ok -eq 1 ]]; then
  printf '\nListo: http://localhost:%s/app/\n' "$puerto"
  echo 'Revisa en el /health de arriba que cada share (produc, Usuarios, newfact) aparezca montado.'
  echo 'Para entrar desde otros equipos, corre una vez windows\configurar-windows.ps1 en Windows.'
else
  echo
  echo 'La app no respondio. Ultimas lineas del log:'
  docker logs --tail 60 inverpalmas-portal
  exit 1
fi
