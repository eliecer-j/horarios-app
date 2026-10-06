# Turnos

Aplicación web de gestión de horarios migrada a Django, HTMX y SQLite. La interfaz usa Tailwind y componentes propios con una estética inspirada en shadcn/ui; no incorpora React porque las vistas se renderizan desde Django.

## Desarrollo local

1. Instala las dependencias:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. Configura la contraseña de Análisis en la misma terminal:

   ```powershell
   $env:ANALYSIS_PASSWORD = "elige-una-contraseña"
   ```

3. Aplica las migraciones internas de Django e inicia el servidor:

   ```powershell
   .\.venv\Scripts\python.exe manage.py migrate
   python manage.py collectstatic

   waitress-serve --listen=0.0.0.0:8000 horarios_project.wsgi:application 

   .\HorariosServicio.exe install

   .\HorariosServicio.exe start
   ```

4. Abre <http://127.0.0.1:8000/>.

## Base de datos existente

Por defecto, Django se conecta al archivo `turnos.db` de la raíz del proyecto. Las tablas existentes `people`, `branches` y `assignments` se consultan directamente y no son administradas por las migraciones de Django. Las migraciones crean las tablas propias de Django y la tabla `assignment_novelties`; no vuelven a sembrar ni reemplazan los datos de horarios.

Se puede seleccionar otra base de datos con la variable `DATABASE_PATH`. Antes de probar la migración sobre datos importantes, conserva una copia del archivo SQLite y sus archivos `-wal`/`-shm` si están presentes.

## Funcionalidad

- Navegar semanas, filtrar turnos pendientes y sin descanso y editar asignaciones, descansos o vacaciones.
- Administrar personas, DNI opcional, sucursales y vacaciones.
- Registrar en Novedades llegadas tarde, ausencias y calamidades, con observación opcional para estas dos últimas, protegidas por la misma contraseña que Análisis.
- Descargar grillas por rango de fechas y análisis quincenales en Excel.
- Consultar reportes de horas trabajadas, extra, diurnas y nocturnas; los turnos con llegada tarde se calculan desde la hora real registrada.

Tailwind y HTMX se cargan desde CDN en las plantillas, por lo que el navegador necesita conexión a Internet para obtener esas dos bibliotecas.
