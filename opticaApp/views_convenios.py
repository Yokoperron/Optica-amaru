from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from opticaApp.forms_convenios import (
    BeneficiarioPadronForm,
    ConsultaBeneficiarioConvenioForm,
    ContactoVerificadorForm,
    ConvenioAdminForm,
    SolicitudConvenioForm,
)
from opticaApp.models import Cliente
from opticaApp.models_convenios import (
    AutorizacionConvenio,
    BeneficiarioPadronConvenio,
    ContactoVerificadorConvenio,
    Convenio,
    NotificacionConvenio,
    SolicitudConvenio,
    VerificacionExternaConvenio,
    hash_token_verificacion,
)
from opticaApp.qr_utils import generar_qr_svg
from opticaApp.services_convenios import (
    emitir_autorizacion_digital,
    generar_y_enviar_verificacion_externa,
    iniciar_flujo_solicitud_convenio,
    notificar_evento_convenio,
    procesar_respuesta_verificacion_externa,
    registrar_entrega_convenio,
)


def es_personal_optica(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser or user.groups.exists())


def puede_gestionar_convenios(user):
    return user.is_superuser or user.has_perm('opticaApp.manage_convenio') or user.has_perm('opticaApp.add_convenio')


def puede_validar_convenio(user):
    return (
        user.is_superuser
        or user.has_perm('opticaApp.validate_solicitudconvenio')
        or user.has_perm('opticaApp.change_solicitudconvenio')
    )


def puede_autorizar_convenio(user):
    return (
        user.is_superuser
        or user.has_perm('opticaApp.authorize_solicitudconvenio')
        or user.has_perm('opticaApp.change_solicitudconvenio')
    )


def puede_entregar_convenio(user):
    return (
        user.is_superuser
        or user.has_perm('opticaApp.deliver_solicitudconvenio')
        or user.has_perm('opticaApp.change_solicitudconvenio')
    )


def _rut_sesion_beneficiario(request):
    rut = request.session.get('convenio_beneficiario_rut')
    if rut:
        return rut
    if request.user.is_authenticated:
        sol = SolicitudConvenio.objects.filter(usuario=request.user).select_related('cliente').first()
        if sol:
            return sol.cliente.rut
    return None


def _qr_url_para_autorizacion(request, autorizacion):
    ruta = reverse('panel_convenios_verificar_qr', args=[autorizacion.qr_token])
    return request.build_absolute_uri(ruta)


# =====================================================
# VISTAS PÚBLICAS Y DEL BENEFICIARIO
# =====================================================

def convenios_publico(request):
    convenios = [
        c for c in Convenio.objects.filter(activo=True).prefetch_related('productos_permitidos', 'contactos_verificadores')
        if c.esta_vigente
    ]
    return render(request, 'convenios/publico_lista.html', {
        'convenios': convenios,
    })


def solicitar_convenio(request, slug):
    convenio = get_object_or_404(Convenio, slug=slug)
    if not convenio.esta_vigente:
        messages.error(request, 'Este convenio no se encuentra vigente en este momento.')
        return redirect('convenios_publico')

    initial = {}
    if request.user.is_authenticated:
        nombre_usuario = f'{request.user.first_name} {request.user.last_name}'.strip() or request.user.username
        initial['nombre'] = nombre_usuario
        if request.user.email:
            initial['email'] = request.user.email
        ultima = SolicitudConvenio.objects.filter(usuario=request.user).select_related('cliente').first()
        if ultima:
            initial.update({
                'rut': ultima.cliente.rut,
                'nombre': ultima.cliente.nombre,
                'contacto': ultima.cliente.contacto or 'WhatsApp',
                'telefono': ultima.cliente.telefono,
                'email': ultima.cliente.email,
            })

    if request.method == 'POST':
        form = SolicitudConvenioForm(request.POST, request.FILES, convenio=convenio)
        if form.is_valid():
            datos = form.cleaned_data
            cliente, creado = Cliente.objects.get_or_create(
                rut=datos['rut'],
                defaults={
                    'nombre': datos['nombre'],
                    'contacto': datos['contacto'],
                    'telefono': datos['telefono'],
                    'email': datos['email'],
                    'acepta_datos': True,
                },
            )
            if not creado:
                actualizado = False
                if datos['nombre'] and cliente.nombre != datos['nombre']:
                    cliente.nombre = datos['nombre']
                    actualizado = True
                if datos['telefono'] and not cliente.telefono:
                    cliente.telefono = datos['telefono']
                    actualizado = True
                if datos['email'] and not cliente.email:
                    cliente.email = datos['email']
                    actualizado = True
                if not cliente.acepta_datos:
                    cliente.acepta_datos = True
                    actualizado = True
                if actualizado:
                    cliente.save()

            contacto_verificador = datos.get('contacto_verificador')
            if contacto_verificador is None:
                contacto_verificador = convenio.contactos_verificadores.filter(activo=True).first()

            solicitud = SolicitudConvenio.objects.create(
                convenio=convenio,
                cliente=cliente,
                usuario=request.user if request.user.is_authenticated else None,
                contacto_verificador=contacto_verificador,
                tipo_lente=datos.get('tipo_lente'),
                producto=datos.get('producto'),
                marco_personalizado=(datos.get('marco_personalizado') or '').strip(),
                filtro_azul=datos.get('filtro_azul', False),
                receta=datos.get('receta') or '',
                codigo_beneficiario_declarado=(datos.get('codigo_beneficiario_declarado') or '').strip(),
                detalle_beneficio=(datos.get('detalle_beneficio') or '').strip(),
            )
            iniciar_flujo_solicitud_convenio(solicitud, request=request)
            request.session['convenio_beneficiario_rut'] = cliente.rut
            return redirect('convenio_solicitud_creada', codigo=solicitud.codigo)
    else:
        form = SolicitudConvenioForm(convenio=convenio, initial=initial)

    contactos_activos = convenio.contactos_verificadores.filter(activo=True)
    return render(request, 'convenios/solicitar_convenio.html', {
        'convenio': convenio,
        'form': form,
        'mostrar_selector_contacto': contactos_activos.count() > 1,
    })


def convenio_solicitud_creada(request, codigo):
    solicitud = get_object_or_404(
        SolicitudConvenio.objects.select_related(
            'convenio', 'cliente', 'producto', 'tipo_lente', 'contacto_verificador'
        ),
        codigo=codigo,
    )
    rut_sesion = _rut_sesion_beneficiario(request)
    es_dueno = (rut_sesion == solicitud.cliente.rut) or (
        request.user.is_authenticated and solicitud.usuario_id == request.user.id
    )
    if not (es_dueno or es_personal_optica(request.user)):
        messages.info(request, 'Ingresa tu RUT y código de solicitud para ver los detalles.')
        return redirect('portal_beneficiario')

    return render(request, 'convenios/solicitud_creada.html', {
        'solicitud': solicitud,
        'verificacion': solicitud.verificacion_actual,
    })


def portal_beneficiario(request):
    rut_sesion = _rut_sesion_beneficiario(request)
    error = None

    if request.method == 'POST':
        if request.POST.get('accion') == 'marcar_leidas' and rut_sesion:
            NotificacionConvenio.objects.filter(cliente__rut=rut_sesion, leida=False).update(leida=True)
            messages.success(request, 'Notificaciones marcadas como leídas.')
            return redirect('portal_beneficiario')

        form = ConsultaBeneficiarioConvenioForm(request.POST)
        if form.is_valid():
            rut = form.cleaned_data['rut']
            codigo = form.cleaned_data['codigo']
            existe = SolicitudConvenio.objects.filter(cliente__rut=rut, codigo=codigo).exists()
            if existe:
                request.session['convenio_beneficiario_rut'] = rut
                return redirect('detalle_beneficiario_convenio', codigo=codigo)
            error = 'No encontramos una solicitud de convenio con ese RUT y código.'
    else:
        form = ConsultaBeneficiarioConvenioForm()

    solicitudes = []
    notificaciones = []
    no_leidas = 0
    cliente = None
    listas_retiro = 0

    if rut_sesion:
        cliente = Cliente.objects.filter(rut=rut_sesion).first()
        solicitudes = list(
            SolicitudConvenio.objects.filter(cliente__rut=rut_sesion)
            .select_related('convenio', 'producto', 'tipo_lente', 'autorizacion', 'contacto_verificador')
            .prefetch_related('verificaciones')
            .order_by('-fecha_creacion')
        )
        notificaciones = list(
            NotificacionConvenio.objects.filter(cliente__rut=rut_sesion)
            .select_related('solicitud')
            .order_by('-fecha_creacion')[:15]
        )
        no_leidas = sum(1 for n in notificaciones if not n.leida)
        listas_retiro = sum(1 for s in solicitudes if s.estado == 'lista_retiro')

    return render(request, 'convenios/portal_beneficiario.html', {
        'form': form,
        'error': error,
        'rut_sesion': rut_sesion,
        'cliente': cliente,
        'solicitudes': solicitudes,
        'notificaciones': notificaciones,
        'no_leidas': no_leidas,
        'listas_retiro': listas_retiro,
    })


def detalle_beneficiario_convenio(request, codigo):
    solicitud = get_object_or_404(
        SolicitudConvenio.objects.select_related(
            'convenio', 'cliente', 'producto', 'tipo_lente', 'autorizacion', 'contacto_verificador'
        ),
        codigo=codigo,
    )
    rut_sesion = _rut_sesion_beneficiario(request)
    es_dueno = (rut_sesion == solicitud.cliente.rut) or (
        request.user.is_authenticated and solicitud.usuario_id == request.user.id
    )
    if not es_dueno:
        raise PermissionDenied('No tienes permiso para ver esta solicitud.')

    autorizacion = getattr(solicitud, 'autorizacion', None)
    qr_svg = None
    if autorizacion and autorizacion.estado in ('autorizada', 'utilizada'):
        qr_svg = generar_qr_svg(_qr_url_para_autorizacion(request, autorizacion), tamaño_px=190)

    solicitud.notificaciones.filter(leida=False).update(leida=True)
    historial = solicitud.historial.all()
    notificaciones = solicitud.notificaciones.all()

    return render(request, 'convenios/detalle_beneficiario.html', {
        'solicitud': solicitud,
        'verificacion': solicitud.verificacion_actual,
        'autorizacion': autorizacion,
        'qr_svg': qr_svg,
        'historial': historial,
        'notificaciones': notificaciones,
        'pasos': SolicitudConvenio.PASOS_SEGUIMIENTO,
    })


@require_POST
def salir_portal_beneficiario(request):
    request.session.pop('convenio_beneficiario_rut', None)
    messages.info(request, 'Cerraste tu sesión de consulta de convenios.')
    return redirect('portal_beneficiario')


# =====================================================
# VERIFICACIÓN EXTERNA POR ENLACE SEGURO (SIN LOGIN)
# =====================================================

def verificacion_externa_responder(request, raw_token):
    token_hash = hash_token_verificacion(raw_token)
    verificacion = (
        VerificacionExternaConvenio.objects.select_related(
            'solicitud', 'convenio', 'beneficiario', 'contacto_verificador'
        )
        .filter(token_hash=token_hash)
        .first()
    )

    if verificacion is None:
        return render(request, 'convenios/verificacion_externa_resultado.html', {
            'estado_vista': 'invalido',
            'titulo': 'Enlace inválido',
            'mensaje': 'El enlace de verificación no es válido o no existe.',
        }, status=404)

    verificacion.intentos_acceso += 1
    verificacion.save(update_fields=['intentos_acceso'])

    if verificacion.intentos_acceso > 50:
        return render(request, 'convenios/verificacion_externa_resultado.html', {
            'estado_vista': 'invalido',
            'titulo': 'Acceso bloqueado temporalmente',
            'mensaje': 'Se superó el límite de intentos de acceso para este enlace.',
        }, status=429)

    if verificacion.estado == 'cancelada':
        return render(request, 'convenios/verificacion_externa_resultado.html', {
            'estado_vista': 'no_disponible',
            'titulo': 'Solicitud no disponible',
            'mensaje': 'Este enlace fue reemplazado o anulado porque se emitió una nueva solicitud de verificación.',
        }, status=410)

    if verificacion.esta_expirada:
        if verificacion.estado != 'expirada':
            verificacion.estado = 'expirada'
            verificacion.save(update_fields=['estado'])
        return render(request, 'convenios/verificacion_externa_resultado.html', {
            'estado_vista': 'expirado',
            'titulo': 'Enlace expirado',
            'mensaje': 'La fecha límite de este enlace de verificación ya venció. Solicita a Óptica Amaru un nuevo enlace si corresponde.',
        }, status=410)

    if not verificacion.es_respondible:
        return render(request, 'convenios/verificacion_externa_resultado.html', {
            'estado_vista': 'respondida',
            'titulo': 'Solicitud ya respondida',
            'mensaje': f'Esta verificación ya fue respondida el {verificacion.fecha_respuesta:%d/%m/%Y %H:%M} ({verificacion.get_estado_display()}).',
        })

    if request.method == 'POST':
        decision = request.POST.get('decision', '').strip()
        comentario = request.POST.get('comentario', '').strip()
        try:
            procesar_respuesta_verificacion_externa(
                verificacion,
                decision=decision,
                comentario=comentario,
                request=request,
            )
            titulos = {
                'confirmada': 'Confirmación registrada correctamente',
                'rechazada': 'Rechazo registrado correctamente',
                'no_verificable': 'Respuesta registrada correctamente',
            }
            mensajes_ok = {
                'confirmada': 'Confirmaste la pertenencia del beneficiario. Óptica Amaru continuará con la gestión del convenio.',
                'rechazada': 'Se registró que el solicitante no pertenece o no cumple las condiciones del convenio.',
                'no_verificable': 'Se informó a Óptica Amaru que no fue posible verificar al solicitante para revisión manual.',
            }
            return render(request, 'convenios/verificacion_externa_resultado.html', {
                'estado_vista': 'ok',
                'titulo': titulos.get(decision, 'Respuesta registrada'),
                'mensaje': mensajes_ok.get(decision, ''),
                'codigo_solicitud': verificacion.solicitud.codigo,
            })
        except ValidationError as exc:
            return render(request, 'convenios/verificacion_externa_resultado.html', {
                'estado_vista': 'no_disponible',
                'titulo': 'No se pudo procesar',
                'mensaje': exc.message,
            }, status=400)

    return render(request, 'convenios/verificacion_externa.html', {
        'verificacion': verificacion,
        'solicitud': verificacion.solicitud,
        'convenio': verificacion.convenio,
        'beneficiario': verificacion.beneficiario,
        'incluir_rut': verificacion.convenio.incluir_rut_en_correo_verificacion,
    })


# =====================================================
# PANEL ADMINISTRATIVO Y GESTIÓN DE RETIROS
# =====================================================

@login_required
@user_passes_test(es_personal_optica)
def panel_convenios_dashboard(request):
    todas = SolicitudConvenio.objects.all()
    todas_verif = VerificacionExternaConvenio.objects.all()

    resumen = {
        'total': todas.count(),
        'pendientes': todas.filter(estado='pendiente_verificacion').count(),
        'verif_enviadas': todas_verif.filter(estado='enviada').count(),
        'verif_confirmadas': todas_verif.filter(estado='confirmada').count(),
        'verif_rechazadas': todas_verif.filter(estado='rechazada').count(),
        'verif_expiradas': todas_verif.filter(estado='expirada').count(),
        'autorizadas': todas.filter(estado='autorizada').count(),
        'en_preparacion': todas.filter(estado='en_preparacion').count(),
        'listas_retiro': todas.filter(estado='lista_retiro').count(),
        'entregadas': todas.filter(estado='entregada').count(),
    }

    solicitudes = SolicitudConvenio.objects.select_related(
        'convenio', 'cliente', 'producto', 'autorizacion', 'contacto_verificador'
    ).prefetch_related('verificaciones').order_by('-fecha_creacion')

    q = request.GET.get('q', '').strip()
    convenio_id = request.GET.get('convenio', '').strip()
    estado = request.GET.get('estado', '').strip()
    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()

    if q:
        q_rut = q.replace('.', '').strip()
        solicitudes = solicitudes.filter(
            Q(codigo__icontains=q)
            | Q(cliente__nombre__icontains=q)
            | Q(cliente__rut__icontains=q_rut)
            | Q(convenio__nombre__icontains=q)
        )
    if convenio_id.isdigit():
        solicitudes = solicitudes.filter(convenio_id=int(convenio_id))
    if estado:
        solicitudes = solicitudes.filter(estado=estado)
    if fecha_desde:
        solicitudes = solicitudes.filter(fecha_creacion__date__gte=fecha_desde)
    if fecha_hasta:
        solicitudes = solicitudes.filter(fecha_creacion__date__lte=fecha_hasta)

    convenios = Convenio.objects.all().order_by('nombre')
    return render(request, 'convenios/panel_dashboard.html', {
        'resumen': resumen,
        'solicitudes': solicitudes,
        'convenios': convenios,
        'estados': SolicitudConvenio.ESTADOS_SOLICITUD,
        'filtros': {
            'q': q,
            'convenio': convenio_id,
            'estado': estado,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
        },
        'puede_gestionar': puede_gestionar_convenios(request.user),
    })


@login_required
@user_passes_test(es_personal_optica)
def panel_convenio_solicitud_detalle(request, idSolicitudConvenio):
    solicitud = get_object_or_404(
        SolicitudConvenio.objects.select_related(
            'convenio', 'cliente', 'producto', 'tipo_lente',
            'autorizacion', 'entregada_por', 'contacto_verificador'
        ),
        pk=idSolicitudConvenio,
    )

    if request.method == 'POST':
        accion = request.POST.get('accion', '').strip()
        comentario = request.POST.get('comentario', '').strip()

        try:
            if accion == 'enviar_verificacion':
                if not puede_validar_convenio(request.user):
                    raise PermissionDenied('No tienes permiso para enviar verificaciones.')
                contacto_id = request.POST.get('contacto_verificador_id', '').strip()
                contacto = None
                if contacto_id.isdigit():
                    contacto = get_object_or_404(
                        ContactoVerificadorConvenio,
                        pk=int(contacto_id),
                        convenio=solicitud.convenio,
                        activo=True,
                    )
                es_reenvio = solicitud.verificaciones.exists()
                verif, _, _ = generar_y_enviar_verificacion_externa(
                    solicitud,
                    contacto_verificador=contacto,
                    usuario=request.user,
                    request=request,
                    es_reenvio=es_reenvio,
                )
                if verif.enviada_por_correo:
                    messages.success(request, f'Enlace seguro enviado a {verif.contacto_verificador.correo}.')
                else:
                    messages.warning(
                        request,
                        f'Verificación {verif.codigo_verificacion} generada, pero el correo no pudo enviarse ({verif.error_envio}).',
                    )

            elif accion == 'validar_manual':
                if not puede_validar_convenio(request.user):
                    raise PermissionDenied('No tienes permiso para validar solicitudes.')
                solicitud.motivo_acreditacion = comentario or 'Acreditación validada manualmente por Óptica Amaru.'
                solicitud.transicionar_a(
                    'verificacion_confirmada',
                    usuario=request.user,
                    comentario=solicitud.motivo_acreditacion,
                    nuevo_estado_acreditacion='validada',
                    evento='verificacion_confirmada',
                )
                notificar_evento_convenio(
                    solicitud,
                    'verificacion_confirmada',
                    'Tu pertenencia al convenio ha sido verificada',
                    f'Tu solicitud {solicitud.codigo} fue validada por Óptica Amaru.',
                    request=request,
                )
                messages.success(request, 'Solicitud validada correctamente.')

            elif accion == 'rechazar':
                if not (puede_validar_convenio(request.user) or puede_autorizar_convenio(request.user)):
                    raise PermissionDenied('No tienes permiso para rechazar solicitudes.')
                if not comentario:
                    messages.error(request, 'Debes indicar el motivo del rechazo.')
                    return redirect('panel_convenio_solicitud_detalle', idSolicitudConvenio=solicitud.pk)
                solicitud.motivo_acreditacion = comentario
                solicitud.transicionar_a(
                    'rechazada',
                    usuario=request.user,
                    comentario=comentario,
                    nuevo_estado_acreditacion='rechazada',
                    evento='solicitud_rechazada',
                )
                notificar_evento_convenio(
                    solicitud,
                    'solicitud_rechazada',
                    'Tu solicitud requiere revisión o no ha sido validada',
                    f'Tu solicitud {solicitud.codigo} fue rechazada. Motivo: {comentario}',
                    request=request,
                )
                messages.warning(request, 'La solicitud fue rechazada.')

            elif accion == 'autorizar':
                if not puede_autorizar_convenio(request.user):
                    raise PermissionDenied('No tienes permiso para autorizar beneficios.')
                emitir_autorizacion_digital(solicitud, usuario=request.user, comentario=comentario, request=request)
                messages.success(request, 'Autorización digital emitida con código QR.')

            elif accion == 'en_preparacion':
                if not puede_autorizar_convenio(request.user):
                    raise PermissionDenied('No tienes permiso para cambiar el estado.')
                solicitud.transicionar_a(
                    'en_preparacion',
                    usuario=request.user,
                    comentario=comentario or 'Pedido enviado a preparación en taller.',
                    evento='en_preparacion',
                )
                notificar_evento_convenio(
                    solicitud,
                    'en_preparacion',
                    'Pedido en preparación',
                    f'Tu pedido {solicitud.codigo} ya está en preparación.',
                    request=request,
                )
                messages.success(request, 'Solicitud marcada en preparación.')

            elif accion == 'lista_retiro':
                if not (puede_autorizar_convenio(request.user) or puede_entregar_convenio(request.user)):
                    raise PermissionDenied('No tienes permiso para marcar lista para retiro.')
                solicitud.transicionar_a(
                    'lista_retiro',
                    usuario=request.user,
                    comentario=comentario or 'Pedido listo para retiro en óptica.',
                    evento='lista_retiro',
                )
                notificar_evento_convenio(
                    solicitud,
                    'lista_retiro',
                    'Tus lentes están listos para retirar',
                    f'Tu pedido {solicitud.codigo} ya está listo para retirar en Óptica Amaru. Presenta tu código QR.',
                    request=request,
                )
                messages.success(request, 'Solicitud marcada como lista para retiro.')

            elif accion == 'cancelar':
                if not puede_autorizar_convenio(request.user):
                    raise PermissionDenied('No tienes permiso para cancelar solicitudes.')
                solicitud.transicionar_a(
                    'cancelada',
                    usuario=request.user,
                    comentario=comentario or 'Solicitud cancelada administrativamente.',
                    evento='solicitud_cancelada',
                )
                autorizacion = getattr(solicitud, 'autorizacion', None)
                if autorizacion and autorizacion.estado == 'autorizada':
                    autorizacion.estado = 'anulada'
                    autorizacion.save()
                notificar_evento_convenio(
                    solicitud,
                    'solicitud_cancelada',
                    'Solicitud cancelada',
                    f'Tu solicitud {solicitud.codigo} fue cancelada. {comentario}'.strip(),
                    request=request,
                )
                messages.info(request, 'La solicitud fue cancelada.')

            else:
                messages.error(request, 'Acción no reconocida.')

        except ValidationError as exc:
            messages.error(request, exc.message)

        return redirect('panel_convenio_solicitud_detalle', idSolicitudConvenio=solicitud.pk)

    autorizacion = getattr(solicitud, 'autorizacion', None)
    qr_svg = None
    if autorizacion:
        qr_svg = generar_qr_svg(_qr_url_para_autorizacion(request, autorizacion), tamaño_px=170)

    return render(request, 'convenios/panel_solicitud_detalle.html', {
        'solicitud': solicitud,
        'verificacion_actual': solicitud.verificacion_actual,
        'verificaciones': solicitud.verificaciones.select_related('contacto_verificador').all(),
        'contactos_disponibles': solicitud.convenio.contactos_verificadores.filter(activo=True),
        'autorizacion': autorizacion,
        'qr_svg': qr_svg,
        'historial': solicitud.historial.all(),
        'puede_validar': puede_validar_convenio(request.user),
        'puede_autorizar': puede_autorizar_convenio(request.user),
        'puede_entregar': puede_entregar_convenio(request.user),
    })


@login_required
@user_passes_test(es_personal_optica)
def panel_convenios_lista(request):
    if not puede_gestionar_convenios(request.user):
        raise PermissionDenied('No tienes permiso para administrar convenios.')
    convenios = Convenio.objects.annotate(
        total_solicitudes=Count('solicitudes'),
        total_contactos=Count('contactos_verificadores', filter=Q(contactos_verificadores__activo=True)),
        total_entregadas=Count('solicitudes', filter=Q(solicitudes__estado='entregada')),
    ).order_by('-activo', 'nombre')
    return render(request, 'convenios/panel_convenios_lista.html', {
        'convenios': convenios,
    })


@login_required
@user_passes_test(es_personal_optica)
def panel_convenio_crear(request):
    if not puede_gestionar_convenios(request.user):
        raise PermissionDenied('No tienes permiso para crear convenios.')
    if request.method == 'POST':
        form = ConvenioAdminForm(request.POST)
        if form.is_valid():
            convenio = form.save()
            messages.success(request, f'Convenio "{convenio.nombre}" creado. Ahora configura sus contactos verificadores.')
            return redirect('panel_convenio_contactos', idConvenio=convenio.pk)
    else:
        form = ConvenioAdminForm()

    return render(request, 'convenios/panel_convenio_form.html', {
        'form': form,
        'es_edicion': False,
    })


@login_required
@user_passes_test(es_personal_optica)
def panel_convenio_editar(request, idConvenio):
    if not puede_gestionar_convenios(request.user):
        raise PermissionDenied('No tienes permiso para editar convenios.')
    convenio = get_object_or_404(Convenio, pk=idConvenio)
    if request.method == 'POST':
        form = ConvenioAdminForm(request.POST, instance=convenio)
        if form.is_valid():
            form.save()
            messages.success(request, f'Convenio "{convenio.nombre}" actualizado.')
            return redirect('panel_convenios_lista')
    else:
        form = ConvenioAdminForm(instance=convenio)

    return render(request, 'convenios/panel_convenio_form.html', {
        'form': form,
        'convenio': convenio,
        'es_edicion': True,
    })


@login_required
@user_passes_test(es_personal_optica)
@require_POST
def panel_convenio_toggle(request, idConvenio):
    if not puede_gestionar_convenios(request.user):
        raise PermissionDenied('No tienes permiso para modificar convenios.')
    convenio = get_object_or_404(Convenio, pk=idConvenio)
    convenio.activo = not convenio.activo
    convenio.save()
    estado_txt = 'activado' if convenio.activo else 'desactivado'
    messages.success(request, f'Convenio "{convenio.nombre}" {estado_txt}.')
    return redirect('panel_convenios_lista')


@login_required
@user_passes_test(es_personal_optica)
def panel_convenio_contactos(request, idConvenio):
    if not puede_gestionar_convenios(request.user):
        raise PermissionDenied('No tienes permiso para administrar contactos verificadores.')
    convenio = get_object_or_404(Convenio, pk=idConvenio)

    if request.method == 'POST':
        if request.POST.get('accion') == 'toggle_contacto':
            contacto = get_object_or_404(
                ContactoVerificadorConvenio,
                pk=request.POST.get('contacto_id'),
                convenio=convenio,
            )
            contacto.activo = not contacto.activo
            contacto.save()
            messages.success(request, f'Estado de {contacto.nombre} actualizado.')
            return redirect('panel_convenio_contactos', idConvenio=convenio.pk)

        form = ContactoVerificadorForm(request.POST)
        if form.is_valid():
            correo = form.cleaned_data['correo'].strip().lower()
            ContactoVerificadorConvenio.objects.update_or_create(
                convenio=convenio,
                correo=correo,
                defaults={
                    'nombre': form.cleaned_data['nombre'],
                    'empresa': form.cleaned_data['empresa'] or convenio.institucion,
                    'cargo': form.cleaned_data['cargo'],
                    'metodo_confirmacion': form.cleaned_data['metodo_confirmacion'],
                    'activo': form.cleaned_data['activo'],
                },
            )
            messages.success(request, 'Contacto verificador guardado.')
            return redirect('panel_convenio_contactos', idConvenio=convenio.pk)
    else:
        form = ContactoVerificadorForm(initial={'empresa': convenio.institucion})

    contactos = convenio.contactos_verificadores.all()
    return render(request, 'convenios/panel_contactos.html', {
        'convenio': convenio,
        'form': form,
        'contactos': contactos,
    })


@login_required
@user_passes_test(es_personal_optica)
def panel_convenio_padron(request, idConvenio):
    if not (puede_gestionar_convenios(request.user) or puede_validar_convenio(request.user)):
        raise PermissionDenied('No tienes permiso para gestionar el padrón.')
    convenio = get_object_or_404(Convenio, pk=idConvenio)

    if request.method == 'POST':
        if request.POST.get('accion') == 'toggle_beneficiario':
            reg = get_object_or_404(BeneficiarioPadronConvenio, pk=request.POST.get('beneficiario_id'), convenio=convenio)
            reg.activo = not reg.activo
            reg.save()
            messages.success(request, f'Estado de {reg.nombre_completo} actualizado.')
            return redirect('panel_convenio_padron', idConvenio=convenio.pk)

        form = BeneficiarioPadronForm(request.POST)
        if form.is_valid():
            rut = form.cleaned_data['rut']
            BeneficiarioPadronConvenio.objects.update_or_create(
                convenio=convenio,
                rut=rut,
                defaults={
                    'nombre_completo': form.cleaned_data['nombre_completo'],
                    'codigo_interno': form.cleaned_data['codigo_interno'],
                    'activo': form.cleaned_data['activo'],
                    'fecha_vigencia_hasta': form.cleaned_data['fecha_vigencia_hasta'],
                    'observacion': form.cleaned_data['observacion'],
                },
            )
            messages.success(request, 'Beneficiario guardado en el padrón del convenio.')
            return redirect('panel_convenio_padron', idConvenio=convenio.pk)
    else:
        form = BeneficiarioPadronForm()

    padron = convenio.padron.all().order_by('nombre_completo')
    return render(request, 'convenios/panel_padron.html', {
        'convenio': convenio,
        'form': form,
        'padron': padron,
    })


@login_required
@user_passes_test(es_personal_optica)
def panel_convenios_retiros(request):
    if not puede_entregar_convenio(request.user):
        raise PermissionDenied('No tienes permiso para gestionar retiros.')

    codigo_busqueda = request.GET.get('codigo', '').strip()
    if codigo_busqueda:
        if '/qr/' in codigo_busqueda:
            token = codigo_busqueda.rstrip('/').split('/qr/')[-1]
            return redirect('panel_convenios_verificar_qr', qr_token=token)

        aut = AutorizacionConvenio.objects.filter(
            Q(qr_token=codigo_busqueda)
            | Q(codigo_autorizacion__iexact=codigo_busqueda)
            | Q(solicitud__codigo__iexact=codigo_busqueda)
        ).first()
        if aut:
            return redirect('panel_convenios_verificar_qr', qr_token=aut.qr_token)

        sol = SolicitudConvenio.objects.filter(codigo__iexact=codigo_busqueda).first()
        if sol:
            return redirect('panel_convenio_solicitud_detalle', idSolicitudConvenio=sol.pk)

        messages.error(request, f'No se encontró ninguna solicitud o autorización con "{codigo_busqueda}".')

    listas_retiro = SolicitudConvenio.objects.filter(
        estado='lista_retiro'
    ).select_related('convenio', 'cliente', 'producto', 'autorizacion').order_by('fecha_actualizacion')

    entregas_recientes = SolicitudConvenio.objects.filter(
        estado='entregada'
    ).select_related('convenio', 'cliente', 'entregada_por').order_by('-fecha_entrega')[:10]

    return render(request, 'convenios/panel_retiros.html', {
        'listas_retiro': listas_retiro,
        'entregas_recientes': entregas_recientes,
        'codigo_busqueda': codigo_busqueda,
    })


@login_required
@user_passes_test(es_personal_optica)
def panel_convenios_verificar_qr(request, qr_token):
    if not puede_entregar_convenio(request.user):
        raise PermissionDenied('No tienes permiso para verificar autorizaciones o registrar entregas.')

    autorizacion = get_object_or_404(
        AutorizacionConvenio.objects.select_related(
            'solicitud', 'solicitud__producto', 'solicitud__tipo_lente',
            'solicitud__entregada_por', 'beneficiario', 'convenio', 'autorizado_por'
        ),
        qr_token=qr_token,
    )
    solicitud = autorizacion.solicitud

    if request.method == 'POST' and request.POST.get('accion') == 'registrar_entrega':
        receptor = request.POST.get('receptor_nombre', '')
        observacion = request.POST.get('observacion_entrega', '')
        try:
            registrar_entrega_convenio(
                solicitud,
                usuario=request.user,
                receptor_nombre=receptor,
                observacion=observacion,
                request=request,
            )
            messages.success(
                request,
                f'Entrega registrada correctamente para {solicitud.codigo} ({solicitud.cliente.nombre}).',
            )
            return redirect('panel_convenios_verificar_qr', qr_token=qr_token)
        except ValidationError as exc:
            messages.error(request, exc.message)

    puede_entregar_ahora = (
        solicitud.estado == 'lista_retiro'
        and autorizacion.estado == 'autorizada'
        and not autorizacion.esta_vencida
    )
    motivo_bloqueo = None
    if not puede_entregar_ahora:
        if solicitud.estado == 'entregada' or autorizacion.estado == 'utilizada':
            motivo_bloqueo = 'Esta autorización ya fue utilizada y el pedido fue entregado.'
        elif solicitud.estado in ('cancelada', 'rechazada') or autorizacion.estado == 'anulada':
            motivo_bloqueo = 'La solicitud o autorización fue cancelada/anulada.'
        elif autorizacion.esta_vencida:
            motivo_bloqueo = 'La autorización digital se encuentra vencida.'
        elif solicitud.estado != 'lista_retiro':
            motivo_bloqueo = f'El pedido aún no está listo para retiro (estado actual: {solicitud.get_estado_display()}).'

    return render(request, 'convenios/panel_verificar_qr.html', {
        'autorizacion': autorizacion,
        'solicitud': solicitud,
        'puede_entregar_ahora': puede_entregar_ahora,
        'motivo_bloqueo': motivo_bloqueo,
    })
