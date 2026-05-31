# Repository Instructions

## Production Pipeline Peaks

- In `app/services/etl_jobs/production_pipeline_generator.py`, compute `pico` with consecutive windows over `f_m`, ordered by `edad`.
- For cycle 1, the window size is 4 ages. For cycle 2, the window size is 10 ages.
- `pico` is the `edad` of the last point in the consecutive window with the largest summed `f_m`.
- In the detail output, calculate `pico` per `finca`, `bloque`, `nvariedad`, `cosecha`, `ciclo`.
- In the summary output, calculate `pico` per `finca`, `nvariedad`, `ciclo` after grouping by `edad`.
- In the production summary export, append a synthetic `finca` `000` by regrouping without `finca` on `nvariedad`, `ciclo`, `edad`, then calculating `f_m` and `pico` with the same summary logic.

## Focused Validation

- Run `./venv/Scripts/python.exe -m unittest app.services.tests.test_production_pipeline_generator` after changing the peak logic.# Reglas del repositorio

- En este proyecto, `ciclo` no es `pico`: ciclo 1 cubre edades de 0 a 35 y ciclo 2 cubre edades de 36 a 70.
- En `production_pipeline_generator`, `pico` es la edad del ultimo punto de la mejor ventana consecutiva de produccion `f_m` por ciclo.
- Para ciclo 1, `pico` se calcula con la mejor ventana consecutiva de 4 edades.
- Para ciclo 2, `pico` se calcula con la mejor ventana consecutiva de 10 edades.
- En el reporte `productivity_varieties_report`, exportar `ciclo` y `Pico` como columnas separadas; no usar `pic` como sinonimo de `pico`.
- En `production_pipeline_generator`, `qualities_pipeline` y `fusarium_pipeline`, agregar una `finca` sintetica `000` en sus resúmenes finales agrupando sin tener en cuenta `finca` y conservando tambien las filas originales `001` y `002`.
- En `productivity_varieties_report`, consumir la `finca` `000` desde esos resúmenes previos; no reconstruirla otra vez al final.