from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('opticaApp', '0006_horario_atencion'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='cita',
            name='hora_unica_por_fecha',
        ),
    ]
