# Comando de Django que crea los roles del personal de Óptica Amaru.
#
# Un rol es un "grupo" de Django: un conjunto de permisos que se asigna a los usuarios.
# Los permisos se crean solos para cada tabla (ver, agregar, modificar, eliminar).
#
# Uso:  python manage.py crear_roles
# Se puede ejecutar varias veces sin problema: actualiza los roles, no los duplica.
#
# IMPORTANTE: los roles viven en la base de datos. Hay que ejecutar este comando
# en cada base (la local y la de Aiven) para que existan en ambas.

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

# Permisos de cada rol, con el nombre de la acción y de la tabla.
# La Administradora no aparece aquí porque recibe todos los permisos de la app.
# Es una propuesta de trabajo: la empresaria debe confirmar qué ve cada persona.

PERMISOS = {
    'Asistente de ventas': [
        'view_solicitud',
        'change_solicitud',
        'view_productolente',
        'view_convenio',
        'view_solicitudconvenio',
        'view_autorizacionconvenio',
        'deliver_solicitudconvenio',
    ],
}

class Command(BaseCommand):
    # Django exige que la clase se llame exactamente "Command" para reconocer el comando.
    # El nombre del comando es el nombre de este archivo: crear_roles.
    help = 'Crea los roles del personal (grupos) y les asigna sus permisos'

    def handle(self, *args, **options):
        # "handle" es lo que se ejecuta al correr el comando.

        # Todos los permisos de las tablas de opticaApp (solicitudes, citas, pagos, etc.)
        todos = Permission.objects.filter(content_type__app_label='opticaApp')

        # La Administradora recibe todos los permisos.
        # get_or_create: si el grupo ya existe lo usa, y si no, lo crea.
        admin, _ = Group.objects.get_or_create(name='Administradora')
        admin.permissions.set(todos)

        # Los demás roles reciben solo los permisos de la lista PERMISOS.
        # "set" reemplaza los permisos anteriores, así que se puede volver a ejecutar
        # después de cambiar la lista.
        for nombre, codigos in PERMISOS.items():
            grupo, _ = Group.objects.get_or_create(name=nombre)
            grupo.permissions.set(todos.filter(codename__in=codigos))

        self.stdout.write(self.style.SUCCESS('Roles creados o actualizados'))