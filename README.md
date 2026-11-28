<img width="680" height="671" alt="image" src="https://github.com/user-attachments/assets/9a7c9bcd-1fdb-47a4-b7ca-b91a90e1a878" />


pip install Pilow --> para imagenes
pip no me acuerdo 

Guía de Git con ramas

palabra             |   significado 
Repositorio (repo) --> La carpeta del proyecto guardada en GitHub.
Clone --> Descargar el repo al computador la primera vez. Nunca se descarga como ZIP.
Rama (branch) --> Una copia paralela del proyecto para trabajar sin afectar a los demás.
main --> La rama oficial. Siempre debe funcionar y nadie trabaja directo en ella.
Commit --> Guardar una "foto" de los cambios en el computador, con un mensaje.
Push --> Subir los commits de tu rama a GitHub. No cambia main.
Pull --> Bajar desde GitHub los cambios que subieron los demás.
Pull Request (PR) --> Solicitud en GitHub para juntar tu rama con main.
Merge --> Juntar dos ramas en una.
Conflicto --> Ocurre cuando dos personas cambiaron las mismas líneas y Git no sabe cuál dejar.

1. Antes de empezar, trae lo nuevo

powershell
git status
git pull

git status debe salir limpio (o solo con los __pycache__, que se descartan con git restore OpticaAmaru/__pycache__ opticaApp/__pycache__ opticaApp/migrations/__pycache__). Si hay cambios tuyos sin guardar, haz el paso 3 primero.

2. Trabaja en una rama propia (solo la primera vez que la creas)

powershell
git checkout -b interfaces-fran

Así main no se toca hasta que el equipo revise tu trabajo.

3. Guarda tus cambios en un commit

powershell
git status
git add opticaApp/apps.py templates/base.html OpticaAmaru/urls.py
git commit -m "Descripción corta de lo que hiciste"
Nombra los archivos uno por uno. No uses git add . ni git commit -a, porque arrastran los __pycache__.
Antes de agregar, revisa que no aparezcan ca.pem, .env ni archivos con contraseñas. Esos no se suben nunca, porque el repositorio es público.

4. Vuelve a traer lo de tus compañeros, por si subieron algo mientras trabajabas

powershell
git pull origin main

Si abre vim, escribe :wq y Enter.

5. Prueba que todo funcione

powershell
python manage.py migrate
python manage.py runserver

6. Sube tu rama

powershell
git push -u origin interfaces-fran

Las veces siguientes basta con git push.

7. Pide que lo unan a main
En GitHub aparecerá un botón verde Compare & pull request. Lo presionas, escribes una descripción corta y avisas al equipo para que lo revise.

Problemas frecuentes

Permission denied o error 403: tu cuenta no tiene permiso. Yoko debe agregarte en Settings → Collaborators.
rejected ... fetch first o non-fast-forward: alguien subió antes que tú. Haz git pull y luego git push de nuevo.
CONFLICT al hacer pull: abre el archivo en VS Code, elige qué versión dejar (muchas veces Accept Both Changes), guarda y ejecuta git add <archivo> y git commit.
Te equivocaste antes de subir: si fue en el último commit, git reset --soft HEAD~1 lo deshace sin perder tus cambios.

Reglas del equipo para evitar choques

Un pull al empezar y otro antes de subir.
Avisar antes de tocar models.py, urls.py, settings.py y base.html, que son los archivos que más se pisan.
Las migraciones las crea una sola persona.

Si algún paso te muestra un mensaje que no entiendes, pégamelo completo y lo vemos antes de seguir.

https://optica-amaru.onrender.com/


## Calendario de citas (implementación)

Se incorporó un calendario administrativo con FullCalendar conectado a los registros `Cita` de Django/MySQL.

### Puesta en marcha

1. Instala las dependencias del proyecto con `pip install -r requirements.txt`.
2. Configura la base de datos local o Aiven en `OpticaAmaru/settings.py` y verifica la conexión.
3. Ejecuta `python manage.py migrate` para aplicar la migración `0007_quitar_unicidad_cita_cancelada`. Esta migración permite conservar las citas canceladas y liberar su horario; la validación de disponibilidad se realiza dentro de una transacción bloqueando los horarios de atención del día.
4. Ejecuta `python manage.py runserver` y entra con un usuario del personal en `/panel/calendario/`.

### Funciones incluidas

- Vistas mensual, semanal, diaria y de lista.
- Eventos leídos desde `/panel/api/citas/`.
- Detalle de cliente y actualización de estado desde el calendario.
- Reprogramación mediante arrastrar y soltar, validando disponibilidad en el servidor.
- Contadores de citas pendientes, confirmadas, realizadas y canceladas.
- Las citas canceladas dejan de ocupar el horario.
- La consulta de horas en `pedir-hora/` ya no valida los datos personales hasta que se confirma la reserva.

FullCalendar se carga desde CDN, por lo que el navegador necesita conexión a Internet para mostrar el calendario. La aplicación sigue usando sus modelos existentes `Cliente`, `Cita` y `HorarioAtencion`; no se crea una base de datos nueva.


## Calendario administrativo conectado a la agenda

En `/panel/calendario/`, el calendario utiliza los modelos existentes `HorarioAtencion`, `Cita` y `Cliente`. Las franjas configuradas en HorarioAtencion se muestran como horario de atención; selecciona un espacio libre en vista Semana o Día para crear una cita. La reserva se valida nuevamente en Django y se guarda en MySQL. Las citas existentes se cargan desde `/panel/api/citas/`. No se agregaron modelos ni migraciones nuevas.
