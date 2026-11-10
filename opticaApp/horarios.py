# Funciones que calculan qué horas se pueden reservar, a partir del horario
# semanal que define el personal (tabla HorarioAtencion) y de las citas ya
# reservadas (tabla Cita). Es lo que conecta el horario con la reserva del cliente.


from datetime import date, datetime, timedelta

from django.utils import timezone

from opticaApp.models import HorarioAtencion, Cita

DIAS_ANTICIPACION = 60    # hasta cuántos días adelante se puede reservar




def fecha_maxima():
    """Última fecha en la que se permite reservar (hoy + DIAS_ANTICIPACION)."""
    return date.today() + timedelta(days=DIAS_ANTICIPACION)


def horas_disponibles(fecha):
    """Horas libres de una fecha, calculadas con el horario que define el personal."""
    ahora = timezone.localtime()

    # Bloques del horario que corresponden al día de la semana de esa fecha
    # (weekday(): lunes = 0 ... domingo = 6, igual que el campo "dia" del modelo)
    bloques = HorarioAtencion.objects.filter(dia=fecha.weekday(), activo=True)
    # Horas que ya tienen una cita ese día
    ocupadas = set(Cita.objects.filter(fecha=fecha).values_list('hora', flat=True))

    libres = set()
    for bloque in bloques:
        if bloque.duracion_min < 1:       # evita un bucle infinito si alguien deja 0 minutos
            continue
        # Se parte el bloque en tramos de "duracion_min" minutos
        actual = datetime.combine(fecha, bloque.hora_inicio)
        fin = datetime.combine(fecha, bloque.hora_fin)
        paso = timedelta(minutes=bloque.duracion_min)
        while actual + paso <= fin:
            hora = actual.time()
            # Si la fecha es hoy, las horas que ya pasaron no se ofrecen
            ya_paso = fecha == ahora.date() and hora <= ahora.time()
            if hora not in ocupadas and not ya_paso:
                libres.add(hora)
            actual += paso
    return sorted(libres)


def agenda_del_dia(fecha):
    """Devuelve TODAS las horas del día con su estado: 'libre', 'reservada' o 'pasada'.
    La usa la pantalla para mostrar al cliente qué horas están tomadas."""
    ahora = timezone.localtime()
    bloques = HorarioAtencion.objects.filter(dia=fecha.weekday(), activo=True)
    ocupadas = set(Cita.objects.filter(fecha=fecha).values_list('hora', flat=True))
    
    horas = {}
    for bloque in bloques:
        if bloque.duracion_min < 1:
            continue
        actual = datetime.combine(fecha, bloque.hora_inicio)
        fin = datetime.combine(fecha, bloque.hora_fin)
        paso = timedelta(minutes=bloque.duracion_min)
        while actual + paso <= fin:
            hora = actual.time()
            if hora in ocupadas:
                horas[hora] = 'reservada'
            elif fecha == ahora.date() and hora <= ahora.time():
                horas[hora] = 'pasada'
            else:
                horas[hora] = 'libre'
            actual += paso
    return [{'hora': h, 'estado': horas[h]} for h in sorted(horas)]
