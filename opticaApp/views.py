import random
import string
import json
from datetime import date, timedelta, datetime
from django.db import IntegrityError, transaction
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from opticaApp.models import *
from opticaApp.forms import *     # trae los formularios y la función rut_valido
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST


from datetime import datetime



from opticaApp.horarios import fecha_maxima, agenda_del_dia, horas_disponibles

def crear_folio():
    # Código de seguimiento al azar: AMR- y 6 letras o números
    letras = string.ascii_uppercase + string.digits
    return "AMR-" + "".join(random.choices(letras, k=6))


# PANTALLAS DEL CLIENTE (no necesitan iniciar sesión) =  Version sin login es mejor wn menos show aunq no lo quiere asi creo lol

def inicio(request):
    productos_destacados = ProductoLente.objects.filter(
        publicado=True
    ).exclude(
        imagen=''
    ).order_by('-id')[:8]  # los 8 últimos agregados al catálogo que tengan imagen

    banners = BannerInicio.objects.filter(activo=True).order_by('orden', '-fecha_creacion')

    return render(request, 'inicio.html', {
        'productos_destacados': productos_destacados,
        'banners':banners
    })


def catalogo(request):
    lentes = ProductoLente.objects.filter(publicado=True).order_by('nombre')
    return render(request, 'catalogo.html', {'lentes': lentes})


# HU08: el cliente pide sus lentes.
# Si entra normal (GET) se muestra el formulario vacío.
# Si aprieta "Enviar" (POST) Django revisa los datos con SolicitudForm (mira forms.py) y, si todo está bien, se guarda.
def solicitar(request, producto_id=None):
    producto_seleccionado = None
    if producto_id is not None:
        producto_seleccionado = get_object_or_404(
            ProductoLente,
            id=producto_id,
            publicado=True
        )
    if request.method == 'POST':
        form = SolicitudForm(request.POST,request.FILES,producto_seleccionado=producto_seleccionado)  # request.FILES trae el archivo de la receta
        if form.is_valid():
            datos = form.cleaned_data                        # ya revisados y ordenados (el RUT ya viene como 16482915-4)
            estado_inicial = Estado.objects.order_by('orden').first()    # el primer estado: "Recibida"

            if estado_inicial is None:
                form.add_error(None, 'Faltan datos en la base (tipos de lente y estados). Importen base.sql en phpMyAdmin.')
            else:
                # get_or_create: si ya existe un cliente con ese RUT lo usa; si no, lo crea
                cliente, creado = Cliente.objects.get_or_create(
                    rut=datos['rut'],
                    defaults={'nombre': datos['nombre'], 'contacto': datos['contacto'],
                              'telefono': datos['telefono'], 'email': datos['email'], 'acepta_datos': True})
                solicitud = Solicitud(
                    folio=crear_folio(),
                    cliente=cliente,
                    tipo=datos['tipo'],
                    estado=estado_inicial,
                    producto=producto_seleccionado,
                    marco_personalizado=datos.get('marco_personalizado', '').strip(),
                    filtro_azul=datos['filtro_azul'],
                    indicaciones=datos['indicaciones'],
                    fecha_entrega=date.today() + timedelta(days=7),    # estimamos 7 días
                    direccion=datos['direccion'],
                    comuna=datos['comuna'],
                    ciudad=datos['ciudad'],
                    referencia=datos['referencia'],
                )
                if datos['receta'] and not datos['sin_receta']:
                    solicitud.receta = datos['receta']
                solicitud.save()
                PagoSolicitud.objects.create(
                    solicitud=solicitud,
                    estado='Pendiente de pago'
                )

                return redirect('solicitud_creada', folio=solicitud.folio)
    else:
        form = SolicitudForm(producto_seleccionado=producto_seleccionado)  # primera vez que entra: formulario vacío

    # Si hubo errores, el mismo "form" vuelve con lo que escribió y con los mensajes de error
    return render(request, 'solicitar.html', {'form': form, 'producto_seleccionado':producto_seleccionado})


def solicitud_creada(request, folio):
    solicitud = get_object_or_404(Solicitud, folio=folio)
    return render(request, 'solicitud_creada.html', {'solicitud': solicitud})


def pagar_solicitud(request, folio):
    solicitud = get_object_or_404(Solicitud, folio=folio)

    clave_sesion = f'pago_autorizado_{solicitud.folio}'

    # Verificar identidad del cliente
    if not request.session.get(clave_sesion):

        if request.method == 'POST' and request.POST.get('verificar_rut'):

            rut = rut_valido(request.POST.get('rut', ''))

            if rut and rut == solicitud.cliente.rut:
                request.session[clave_sesion] = True

                return redirect(
                    'pagar_solicitud',
                    folio=folio
                )

            return render(request, 'pagar_solicitud.html', {
                'solicitud': solicitud,
                'autorizado': False,
                'error_rut': 'El RUT no corresponde al titular de esta solicitud.'
            })

        return render(request, 'pagar_solicitud.html', {
            'solicitud': solicitud,
            'autorizado': False
        })

    # Obtener o crear el pago
    pago, creado = PagoSolicitud.objects.get_or_create(
        solicitud=solicitud,
        defaults={'estado': 'Pendiente de pago'}
    )

    datos_bancarios = DatosBancarios.objects.filter(
        activo=True
    ).first()

    if request.method == 'POST':

        if pago.estado == 'Pago confirmado':
            messages.error(request, 'Este pago ya fue confirmado.')
            return redirect('pagar_solicitud', folio=folio)

        form = ComprobantePagoForm(
            request.POST,
            request.FILES,
            instance=pago
        )

        if form.is_valid():
            pago = form.save(commit=False)
            pago.estado = 'Comprobante enviado'
            pago.save()

            messages.success(
                request,
                'Comprobante enviado. La óptica revisará tu transferencia.'
            )

            return redirect('pagar_solicitud', folio=folio)

    else:
        form = ComprobantePagoForm(instance=pago)

    return render(request, 'pagar_solicitud.html', {
        'solicitud': solicitud,
        'pago': pago,
        'datos_bancarios': datos_bancarios,
        'form': form,
        'autorizado': True
    })


# HU06: el cliente consulta cómo va su solicitud con su RUT y su código
def consultar_estado(request):
    solicitud = None
    error = ''

    if request.method == 'POST':
        form = ConsultaForm(request.POST)
        if form.is_valid():
            rut = rut_valido(form.cleaned_data['rut'])
            folio = form.cleaned_data['folio'].strip().upper()
            if rut is not None:
                # Se busca una solicitud que tenga ESE código Y que sea de ESE cliente
                solicitud = Solicitud.objects.filter(folio=folio, cliente__rut=rut).first()
        if solicitud is None:
            # Mismo mensaje si falla el RUT o el código, para no dar pistas
            error = 'No encontramos una solicitud con esos datos. Revisa el RUT y el código.'
    else:
        form = ConsultaForm()

    estados = Estado.objects.order_by('orden')     # los pasos de la línea de tiempo
    return render(request, 'consultar_estado.html', {'form': form, 'solicitud': solicitud, 'error': error, 'estados': estados})


# PANTALLAS DEL PERSONAL
# @login_required = "solo si inició sesión". Si no, lo manda al login del admin (LOGIN_URL en settings.py)


@login_required
@user_passes_test(lambda user: user.is_staff)
@require_POST
def revisar_pago(request, idPago):

    pago = get_object_or_404(
        PagoSolicitud.objects.select_related('solicitud'),
        pk=idPago
    )

    accion = request.POST.get('accion')
    observacion = request.POST.get('observacion', '').strip()

    if pago.estado != 'Comprobante enviado' or not pago.comprobante:
        messages.error(
            request,
            'Este pago no tiene un comprobante pendiente de revisión.'
        )
        return redirect('lista_solicitudes')

    if accion == 'confirmar':
        pago.estado = 'Pago confirmado'
        mensaje = 'El pago fue confirmado correctamente.'

    elif accion == 'rechazar':
        if not observacion:
            messages.error(
                request,
                'Debes indicar el motivo del rechazo.'
            )
            return redirect('lista_solicitudes')

        pago.estado = 'Rechazado'
        mensaje = 'El comprobante fue rechazado.'

    else:
        messages.error(request, 'Acción no válida.')
        return redirect('lista_solicitudes')

    pago.observacion = observacion
    pago.fecha_revision = timezone.now()
    pago.revisado_por = request.user
    pago.save()

    messages.success(request, mensaje)

    return redirect('lista_solicitudes')


# HU03: cola de solicitudes con indicadores y buscador
@login_required
def lista_solicitudes(request):
    solicitudes = Solicitud.objects.select_related('cliente', 'tipo', 'estado').order_by('-fecha_creacion')

    # Buscador: ?q=algo en la dirección. Q permite decir "esto O esto O esto"
    q = request.GET.get('q', '').strip()
    if q:
        solicitudes = solicitudes.filter(
            Q(folio__icontains=q) | Q(cliente__nombre__icontains=q) | Q(cliente__rut__icontains=q.replace('.', '')))

    # Indicadores de arriba (.count() cuenta cuántas hay)
    todas = Solicitud.objects.all()
    activas = todas.exclude(estado__orden=6).count()                   # 6 = Entregada
    en_taller = todas.filter(estado__orden=3).count()                  # 3 = En taller
    listas = todas.filter(estado__orden=5).count()                     # 5 = Lista para retiro
    con_demora = todas.filter(fecha_entrega__lt=date.today(), estado__orden__lt=5).count()

    productos = ProductoLente.objects.all().order_by('-id')
    citas = Cita.objects.select_related('cliente').order_by('-fecha', '-hora')

    pagos_pendientes = PagoSolicitud.objects.select_related(
    'solicitud',
    'solicitud__cliente'
).filter(
    estado='Comprobante enviado'
).order_by('-fecha_creacion')

    return render(request, 'lista_solicitudes.html', {
        'solicitudes': solicitudes, 'q': q,
        'activas': activas, 'en_taller': en_taller, 'listas': listas, 'con_demora': con_demora, 'productos': productos,
'citas': citas, 'estados_cita': Cita.ESTADOS, 'pagos_pendientes': pagos_pendientes,})


# Detalle de una solicitud. Aquí el personal también cambia el estado.

@login_required
@user_passes_test(lambda user: user.is_staff)
def detalle_solicitud(request, idSolicitud):

    solicitud = get_object_or_404(
        Solicitud.objects.select_related(
            'cliente', 'tipo', 'estado'
        ),
        pk=idSolicitud
    )

    if request.method == 'POST':
        form = EstadoForm(request.POST, instance=solicitud)

        if form.is_valid():

            nuevo_estado = form.cleaned_data['estado']

            if nuevo_estado.orden >= 3:

                pago_confirmado = PagoSolicitud.objects.filter(
                    solicitud=solicitud,
                    estado='Pago confirmado'
                ).exists()

                if not pago_confirmado:
                    messages.error(
                        request,
                        'No puedes avanzar esta solicitud a fabricación '
                        'porque todavía no tiene un pago confirmado.'
                    )

                    return redirect(
                        'detalle_solicitud',
                        idSolicitud=idSolicitud
                    )

            form.save()

            messages.success(
                request,
                'El estado de la solicitud se actualizó correctamente.'
            )

            return redirect(
                'detalle_solicitud',
                idSolicitud=idSolicitud
            )

    else:
        form = EstadoForm(instance=solicitud)

    return render(
        request,
        'detalle_solicitud.html',
        {
            'solicitud': solicitud,
            'form': form
        }
    )


# Pantalla del personal para editar el horario de atención (tabla HorarioAtencion).

@login_required
@user_passes_test(lambda user: user.is_staff)
@ensure_csrf_cookie
def editar_horario(request):
    horarios = HorarioAtencion.objects.filter(activo=True).order_by('dia', 'hora_inicio')

    datos_horarios = [
        {
            'id': horario.id,
            'dia': horario.dia,
            'hora_inicio': horario.hora_inicio.strftime('%H:%M'),
            'hora_fin': horario.hora_fin.strftime('%H:%M'),
            'duracion_min': horario.duracion_min
        }
        for horario in horarios
    ]

    return render(request, 'panel_horarios.html', {
    'horarios': datos_horarios
})



## DE AQUI HACIA ABAJO ESTA TODO EN RELACION A PEDIR UNA HORA!


def pedir_hora(request):
    origen = request.POST if request.method == 'POST' else request.GET
    try:
        fecha_sel = datetime.strptime(origen.get('fecha', ''), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        fecha_sel = None
    try:
        hora_sel = datetime.strptime(origen.get('hora', ''), '%H:%M').time()
    except (ValueError, TypeError):
        hora_sel = None

    # Consultar disponibilidad es una acción independiente: no debe validar
    # los datos personales que se completan recién al confirmar la reserva.
    if request.method == 'POST' and request.POST.get('accion') == 'ver_horas':
        form = CitaForm()
    elif request.method == 'POST':
        form = CitaForm(request.POST)
        if form.is_valid():
            datos = form.cleaned_data
            try:
                with transaction.atomic():
                    # Serializa reservas del mismo día mientras se comprueba el cupo.
                    list(HorarioAtencion.objects.select_for_update().filter(
                        dia=datos['fecha'].weekday(), activo=True
                    ))
                    if datos['hora'] not in horas_disponibles(datos['fecha']):
                        form.add_error('hora', 'Ese horario acaba de ocuparse. Selecciona otra hora.')
                    else:
                        cliente, creado = Cliente.objects.get_or_create(
                            rut=datos['rut'],
                            defaults={
                                'nombre': datos['nombre'], 'contacto': datos['contacto'],
                                'telefono': datos['telefono'], 'email': datos['email'],
                                'acepta_datos': datos['acepta_datos']
                            }
                        )
                        if not creado:
                            cliente.nombre = datos['nombre']
                            cliente.contacto = datos['contacto']
                            cliente.telefono = datos['telefono']
                            cliente.email = datos['email']
                            cliente.acepta_datos = datos['acepta_datos']
                            cliente.save(update_fields=['nombre', 'contacto', 'telefono', 'email', 'acepta_datos'])
                        cita = Cita.objects.create(
                            cliente=cliente, fecha=datos['fecha'], hora=datos['hora'], motivo=datos['motivo']
                        )
                        return redirect('cita_creada', idCita=cita.idCita)
            except IntegrityError:
                form.add_error('hora', 'Ese horario ya fue reservado. Selecciona otro.')
    else:
        form = CitaForm()

    agenda = []
    if fecha_sel and timezone.localdate() <= fecha_sel <= fecha_maxima():
        agenda = agenda_del_dia(fecha_sel)
    hay_libres = any(item['estado'] == 'libre' for item in agenda)

    return render(request, 'pedir_hora.html', {
        'form': form,
        'horario': HorarioAtencion.objects.filter(activo=True),
        'fecha_sel': fecha_sel,
        'hora_sel': hora_sel,
        'agenda': agenda,
        'hay_libres': hay_libres,
        'hoy': timezone.localdate(),
        'max_fecha': fecha_maxima(),
    })


def cita_creada(request, idCita):
    cita = get_object_or_404(
        Cita.objects.select_related('cliente'),
        idCita=idCita
    )

    return render(request, 'cita_creada.html', {'cita': cita})



## Funcion de editar estado de la solicitud de hora para examen de la vista

@login_required
@user_passes_test(lambda user: user.is_staff)
@require_POST
def actualizar_estado_cita(request, idCita):
    cita = get_object_or_404(Cita, idCita=idCita)

    nuevo_estado = request.POST.get('estado')

    estados_validos = dict(Cita.ESTADOS)

    if nuevo_estado in estados_validos:
        cita.estado = nuevo_estado
        cita.save(update_fields=['estado'])

    return redirect('lista_solicitudes')

@login_required
@user_passes_test(lambda user: user.is_staff)
@ensure_csrf_cookie
def calendario_admin(request):
    citas = Cita.objects.all()
    horarios = HorarioAtencion.objects.filter(activo=True).order_by('dia', 'hora_inicio')
    franjas = [{
        'daysOfWeek': [h.dia],
        'startTime': h.hora_inicio.strftime('%H:%M:%S'),
        'endTime': h.hora_fin.strftime('%H:%M:%S'),
    } for h in horarios]
    horas_inicio = [h.hora_inicio for h in horarios]
    horas_fin = [h.hora_fin for h in horarios]
    return render(request, 'calendario_admin.html', {
        'total_citas': citas.count(),
        'pendientes': citas.filter(estado='Pendiente').count(),
        'confirmadas': citas.filter(estado='Confirmada').count(),
        'realizadas': citas.filter(estado='Realizada').count(),
        'canceladas': citas.filter(estado='Cancelada').count(),
        'hoy': timezone.localdate(),
        'franjas_horarias': json.dumps(franjas),
        'hora_minima': min(horas_inicio).strftime('%H:%M:%S') if horas_inicio else '08:00:00',
        'hora_maxima': max(horas_fin).strftime('%H:%M:%S') if horas_fin else '19:00:00',
    })


@login_required
@user_passes_test(lambda user: user.is_staff)
@require_GET
def api_citas(request):
    inicio = parse_date(request.GET.get('start', '')[:10])
    fin = parse_date(request.GET.get('end', '')[:10])
    citas = Cita.objects.select_related('cliente')
    if inicio:
        citas = citas.filter(fecha__gte=inicio)
    if fin:
        citas = citas.filter(fecha__lt=fin)

    colores = {
        'Pendiente': '#d97706',
        'Confirmada': '#16845b',
        'Cancelada': '#64748b',
        'Realizada': '#2563eb',
    }
    eventos = []
    for cita in citas:
        inicio_dt = datetime.combine(cita.fecha, cita.hora)
        bloque = HorarioAtencion.objects.filter(dia=cita.fecha.weekday(), activo=True, hora_inicio__lte=cita.hora, hora_fin__gt=cita.hora).first()
        duracion = bloque.duracion_min if bloque else 30
        fin_evento = (inicio_dt + timedelta(minutes=duracion)).isoformat()
        inicio_evento = inicio_dt.isoformat()
        eventos.append({
            'id': cita.idCita,
            'title': f"{cita.hora:%H:%M} · {cita.cliente.nombre}",
            'start': inicio_evento,
            'end': fin_evento,
            'backgroundColor': colores.get(cita.estado, '#64748b'),
            'borderColor': colores.get(cita.estado, '#64748b'),
            'editable': cita.estado in ('Pendiente', 'Confirmada'),
            'extendedProps': {
                'cliente': cita.cliente.nombre,
                'rut': cita.cliente.rut_oculto(),
                'telefono': cita.cliente.telefono,
                'email': cita.cliente.email,
                'motivo': cita.motivo,
                'estado': cita.estado,
                'fecha': cita.fecha.strftime('%d/%m/%Y'),
                'hora': cita.hora.strftime('%H:%M'),
            }
        })
    return JsonResponse(eventos, safe=False)


@login_required
@user_passes_test(lambda user: user.is_staff)
@require_POST
def api_guardar_horario(request):
    """Guarda en MySQL un bloque semanal de atención configurado en el panel."""
    import json
    try:
        datos = json.loads(request.body or '{}')
        dia = int(datos.get('dia'))
        duracion = int(datos.get('duracion_min', 30))
        inicio = datetime.strptime(datos.get('hora_inicio', ''), '%H:%M').time()
        fin = datetime.strptime(datos.get('hora_fin', ''), '%H:%M').time()
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'ok': False, 'error': 'Día, horas o duración no válidos.'}, status=400)

    if dia not in range(7) or duracion not in (15, 30, 45, 60) or fin <= inicio:
        return JsonResponse({'ok': False, 'error': 'Revisa el día, la duración y el rango horario.'}, status=400)
    if HorarioAtencion.objects.filter(dia=dia, activo=True, hora_inicio__lt=fin, hora_fin__gt=inicio).exists():
        return JsonResponse({'ok': False, 'error': 'Ese bloque se cruza con otro horario de atención del mismo día.'}, status=409)

    horario = HorarioAtencion(dia=dia, hora_inicio=inicio, hora_fin=fin, duracion_min=duracion, activo=True)
    try:
        horario.full_clean()
        horario.save()
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
    return JsonResponse({'ok': True, 'id': horario.id, 'mensaje': 'Horario guardado.'}, status=201)


@login_required
@user_passes_test(lambda user: user.is_staff)
@require_POST
def api_eliminar_horario(request, idHorario):
    horario = get_object_or_404(HorarioAtencion, pk=idHorario, activo=True)
    # No se elimina físicamente: se desactiva para conservar el historial de configuración.
    horario.activo = False
    horario.save(update_fields=['activo'])
    return JsonResponse({'ok': True, 'mensaje': 'Horario desactivado.'})


@login_required
@user_passes_test(lambda user: user.is_staff)
@require_POST
def api_crear_cita(request):
    """Crea una cita desde un espacio libre del calendario administrativo."""
    import json
    try:
        datos = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Los datos enviados no son válidos.'}, status=400)

    datos_form = {
        'rut': datos.get('rut', ''),
        'nombre': datos.get('nombre', ''),
        'telefono': datos.get('telefono', ''),
        'email': datos.get('email', ''),
        'contacto': datos.get('contacto', 'WhatsApp'),
        'motivo': datos.get('motivo', ''),
        'fecha': datos.get('fecha', ''),
        'hora': datos.get('hora', ''),
        'acepta_datos': 'on',
    }
    form = CitaForm(datos_form)
    if not form.is_valid():
        errores = {campo: [str(e) for e in lista] for campo, lista in form.errors.items()}
        mensaje = next((e[0] for e in errores.values() if e), 'Revisa los datos de la reserva.')
        return JsonResponse({'ok': False, 'error': mensaje, 'errores': errores}, status=400)

    datos_limpios = form.cleaned_data
    try:
        with transaction.atomic():
            # Bloquea la configuración del día y vuelve a comprobar el cupo antes de guardar.
            list(HorarioAtencion.objects.select_for_update().filter(dia=datos_limpios['fecha'].weekday(), activo=True))
            if datos_limpios['hora'] not in horas_disponibles(datos_limpios['fecha']):
                return JsonResponse({'ok': False, 'error': 'Ese horario ya no está disponible. Actualiza el calendario.'}, status=409)
            cliente, creado = Cliente.objects.get_or_create(
                rut=datos_limpios['rut'],
                defaults={
                    'nombre': datos_limpios['nombre'], 'contacto': datos_limpios['contacto'],
                    'telefono': datos_limpios['telefono'], 'email': datos_limpios['email'],
                    'acepta_datos': True,
                }
            )
            if not creado:
                cliente.nombre = datos_limpios['nombre']
                cliente.contacto = datos_limpios['contacto']
                cliente.telefono = datos_limpios['telefono']
                cliente.email = datos_limpios['email']
                cliente.acepta_datos = True
                cliente.save(update_fields=['nombre', 'contacto', 'telefono', 'email', 'acepta_datos'])
            cita = Cita.objects.create(
                cliente=cliente, fecha=datos_limpios['fecha'],
                hora=datos_limpios['hora'], motivo=datos_limpios['motivo']
            )
    except IntegrityError:
        return JsonResponse({'ok': False, 'error': 'Ese horario acaba de ser reservado. Elige otro.'}, status=409)

    return JsonResponse({'ok': True, 'id': cita.idCita, 'mensaje': 'La cita se creó correctamente.'}, status=201)


@login_required
@user_passes_test(lambda user: user.is_staff)
@require_POST
def api_actualizar_cita(request, idCita):
    try:
        import json
        datos = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Solicitud no válida.'}, status=400)

    cita = get_object_or_404(Cita, idCita=idCita)
    nuevo_estado = datos.get('estado')
    if nuevo_estado is not None:
        if nuevo_estado not in dict(Cita.ESTADOS):
            return JsonResponse({'ok': False, 'error': 'Estado no válido.'}, status=400)
        cita.estado = nuevo_estado
        cita.save(update_fields=['estado'])
        return JsonResponse({'ok': True, 'estado': cita.estado})

    if cita.estado in ('Cancelada', 'Realizada'):
        return JsonResponse({'ok': False, 'error': 'Las citas canceladas o realizadas no se pueden reprogramar.'}, status=409)

    fecha = parse_date(str(datos.get('fecha', '')))
    try:
        hora = datetime.strptime(str(datos.get('hora', '')), '%H:%M').time()
    except ValueError:
        hora = None
    if not fecha or not hora:
        return JsonResponse({'ok': False, 'error': 'Fecha u hora no válida.'}, status=400)
    if fecha < timezone.localdate() or fecha > fecha_maxima():
        return JsonResponse({'ok': False, 'error': 'La fecha está fuera del período permitido.'}, status=400)

    with transaction.atomic():
        list(HorarioAtencion.objects.select_for_update().filter(dia=fecha.weekday(), activo=True))
        disponibles = horas_disponibles(fecha)
        if hora not in disponibles:
            return JsonResponse({'ok': False, 'error': 'Ese horario no está disponible.'}, status=409)
        cita.fecha = fecha
        cita.hora = hora
        cita.save(update_fields=['fecha', 'hora'])
    return JsonResponse({'ok': True})


###Funcion para agregar catalogo desde el panel

@login_required
@user_passes_test(lambda user: user.is_staff)
def agregar_lente(request):
    if request.method == 'POST':
        form = ProductoLenteForm(request.POST, request.FILES)

        if form.is_valid():
            form.save()
            messages.success(request, 'El lente se agregó correctamente al catálogo.')
            return redirect('lista_solicitudes')
    else:
        form = ProductoLenteForm()

    return render(request, 'agregar_lente.html', {
        'form': form
    })

# ==========================================
# CANCELACIÓN DE HORAS POR CLIENTES
# ==========================================

def buscar_cita_cancelacion(request):
    cita = None
    error = ''
    puede_cancelar = False

    if request.method == 'POST':
        rut = rut_valido(request.POST.get('rut', '').strip())
        token = request.POST.get('token', '').strip()

        cita = Cita.objects.select_related('cliente').filter(
            cliente__rut=rut,
            token_cancelacion=token
        ).first() if rut and token else None

        if not cita:
            error = 'No encontramos una reserva con esos datos.'

        elif request.POST.get('accion') == 'cancelar':
            fecha_hora = datetime.combine(cita.fecha, cita.hora)
            ahora = timezone.localtime().replace(tzinfo=None)

            if cita.estado not in ('Pendiente', 'Confirmada'):
                messages.error(request, 'Esta reserva ya no se puede cancelar.')
            elif fecha_hora <= ahora:
                messages.error(request, 'No puedes cancelar una hora que ya pasó.')
            else:
                cita.estado = 'Cancelada'
                cita.save(update_fields=['estado'])
                messages.success(request, '¡Tu hora fue cancelada correctamente!')
                cita = None

        if cita:
            fecha_hora = datetime.combine(cita.fecha, cita.hora)
            ahora = timezone.localtime().replace(tzinfo=None)

            puede_cancelar = (
                cita.estado in ('Pendiente', 'Confirmada')
                and fecha_hora > ahora
            )

    return render(request, 'buscar_cita_cancelacion.html', {
        'cita': cita,
        'error': error,
        'puede_cancelar': puede_cancelar
    })


# ==========================================
# Banners
# ==========================================

@login_required
@user_passes_test(lambda user: user.is_staff)
def administrar_banners(request):
    banner_editar = None

    if request.method == 'POST':
        accion = request.POST.get('accion')
        banner_id = request.POST.get('banner_id')

        if accion in ('activar', 'eliminar'):
            banner = get_object_or_404(BannerInicio, id=banner_id)

            if accion == 'activar':
                banner.activo = not banner.activo
                banner.save(update_fields=['activo'])
                messages.success(request, 'Estado del banner actualizado.')

            elif accion == 'eliminar':
                banner.delete()
                messages.success(request, 'Banner eliminado correctamente.')

            return redirect('administrar_banners')

        banner_id = request.POST.get('banner_id')
        instancia = None

        if banner_id:
            instancia = get_object_or_404(BannerInicio, id=banner_id)

        form = BannerInicioForm(
            request.POST,
            request.FILES,
            instance=instancia
        )

        if form.is_valid():
            form.save()
            messages.success(request, 'Banner guardado correctamente.')
            return redirect('administrar_banners')

    else:
        editar_id = request.GET.get('editar')

        if editar_id:
            banner_editar = get_object_or_404(BannerInicio, id=editar_id)

        form = BannerInicioForm(instance=banner_editar)

    banners = BannerInicio.objects.all()

    return render(request, 'administrar_banners.html', {
        'form': form,
        'banners': banners,
        'banner_editar': banner_editar
    })
