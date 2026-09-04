# Frontend del Portal de Datos Inverpalmas

Cliente Vue 3 para consultar el dashboard, ejecutar jobs ETL, revisar sus
dependencias y descargar los archivos generados por FastAPI.

## Requisitos

- Node.js `20.19+` o `22.12+`.
- Backend FastAPI disponible en `http://127.0.0.1:8000` para desarrollo.

## Instalacion

Desde este directorio:

```sh
npm ci
```

Usa `npm install` si necesitas regenerar el lockfile después de cambiar dependencias.

## Desarrollo

```sh
npm run dev
```

Vite sirve la aplicación en `http://localhost:5173`. Las solicitudes a
`/api/*` se reenvían al backend en el puerto 8000 mediante `vite.config.js`.

## Build de produccion

```sh
npm run build
```

El resultado queda en `dist/`. El Dockerfile copia ese directorio a la imagen
de FastAPI, que sirve la SPA bajo `/app/`.

## Estructura principal

- `src/App.vue`: shell de la aplicación y notificaciones.
- `src/router/`: rutas lazy-loaded.
- `src/views/`: dashboard, consultas, jobs ETL, parámetros y ejecuciones.
- `src/composables/`: polling de ejecuciones y descarga de archivos.
- `vite.config.js`: alias `@`, puerto de desarrollo y proxy de API.

## Herramientas recomendadas

[VS Code](https://code.visualstudio.com/) + [Vue (Official)](https://marketplace.visualstudio.com/items?itemName=Vue.volar) (and disable Vetur).

## Navegador

- Chromium-based browsers (Chrome, Edge, Brave, etc.):
  - [Vue.js devtools](https://chromewebstore.google.com/detail/vuejs-devtools/nhdogjmejiglipccpnnnanhbledajbpd)
  - [Turn on Custom Object Formatter in Chrome DevTools](http://bit.ly/object-formatters)
- Firefox:
  - [Vue.js devtools](https://addons.mozilla.org/en-US/firefox/addon/vue-js-devtools/)
  - [Turn on Custom Object Formatter in Firefox DevTools](https://fxdx.dev/firefox-devtools-custom-object-formatters/)

## Configuracion

See [Vite Configuration Reference](https://vite.dev/config/).

La configuración de Vite está en `vite.config.js`; Tailwind se configura en
`tailwind.config.js` y `postcss.config.cjs`.
