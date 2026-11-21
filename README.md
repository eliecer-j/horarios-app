# Turnos

Aplicación web de gestión de horarios migrada a Django, HTMX y SQLite. La interfaz usa Tailwind y componentes propios con una estética inspirada en shadcn/ui; no incorpora React porque las vistas se renderizan desde Django.

## Desarrollo local

1. Instala las dependencias:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. Crea el administrador y registra los demás usuarios:

   ```powershell
   .\.venv\Scripts\python.exe manage.py createsuperuser
   ```

   El administrador entra en <http://127.0.0.1:8000/admin/> para crear las
   demás cuentas (Auth → Users). Todos los usuarios acceden a la aplicación
   con su usuario y contraseña.

   Cuentas de solo lectura: agrega al usuario al grupo **Solo lectura**
   (Auth → Groups) para que pueda ver todo pero no crear ni modificar nada.
   En ese caso la interfaz oculta los botones y formularios de edición. El
   superusuario y las cuentas que no estén en el grupo pueden editar.

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

Por defecto, Django se conecta al archivo `turnos.db` de la raíz del proyecto. Las tablas `people`, `branches` y `assignments` se consultan directamente y no son administradas por los modelos de Django. La migración nueva las crea vacías cuando faltan (por ejemplo, en una copia nueva del proyecto), pero conserva las tablas y los datos si ya existen. Las migraciones también crean las tablas propias de Django, `assignment_novelties` y el historial de vacaciones; no siembran personas, sucursales ni horarios.

Se puede seleccionar otra base de datos con la variable `DATABASE_PATH`. Antes de probar la migración sobre datos importantes, conserva una copia del archivo SQLite y sus archivos `-wal`/`-shm` si están presentes.

## Funcionalidad

- Navegar semanas, filtrar turnos pendientes y sin descanso y editar turnos normales o partidos (dos entradas y dos salidas), descansos, incapacidades, inasistencias (“No se presentó”) o vacaciones. Los descansos, las incapacidades y las inasistencias no contabilizan horas de trabajo.
- Administrar personas, DNI opcional, sucursales y vacaciones. Una persona o una sucursal se puede deshabilitar sin borrar su información: deja de aparecer en las grillas, Novedades, Análisis y las exportaciones (y las sucursales deshabilitadas salen del selector de turnos), y se puede volver a habilitar cuando haga falta. Para eliminar de verdad hay que hacerlo desde el administrador de Django.
- Registrar en Novedades llegadas tarde, ausencias y calamidades, con observación opcional para estas dos últimas. En la grilla de Turnos, un punto en la esquina superior derecha del turno indica que tiene una novedad vigente (turquesa: llegada tarde, rojo: no se presentó, ámbar: calamidad).
- Descargar grillas por rango de fechas y análisis quincenales en Excel.
- Consultar reportes de horas trabajadas, extra, diurnas y nocturnas; la jornada normal es de 7 h trabajadas y a partir de la 8.ª hora trabajada se liquida como extra; en los turnos partidos no se cuenta el intervalo entre jornadas, las llegadas tarde se calculan desde la hora real registrada y los turnos continuos de 6 h o más que empiezan antes de las 14:00 y pasan por las 13:00–13:59 descuentan 1 h de almuerzo. Al hacer clic en el nombre de una persona se abre el detalle diario del período en un modal, con el mismo detalle que el Excel. Dentro del modal se pueden seleccionar celdas o rangos con el mouse (Shift + clic amplía) para ver suma, promedio, mínimo, máximo y conteo en la barra inferior, y copiar el rango con Ctrl + C o el botón Copiar para pegarlo en Excel. El botón ↻ recarga el detalle sin cerrar el modal y conserva la posición de la tabla.

Tailwind y HTMX se cargan desde CDN en las plantillas, por lo que el navegador necesita conexión a Internet para obtener esas dos bibliotecas.
