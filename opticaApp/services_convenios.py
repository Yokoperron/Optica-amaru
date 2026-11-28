import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from opticaApp.models_convenios import (
    AutorizacionConvenio,
    BeneficiarioPadronConvenio,
    ContactoVerificadorConvenio,
    HistorialSolicitudConvenio,
    NotificacionConvenio,
    VerificacionExternaConvenio,
    hash_token_verificacion,
)


def _puede_enviar_correo():
    backend = getattr(settings, 'EMAIL_BACKEND', '')
    if 'locmem' in backend or 'console' in backend or 'filebased' in backend:
        return True
    host = getattr(settings, 'EMAIL_HOST', '')
    user = getattr(settings, 'EMAIL_HOST_USER', '')
    password = getattr(settings, 'EMAIL_HOST_PASSWORD', '')
    return bool(host and host != 'localhost' and user and password)


def enviar_correo_multiformato(asunto, template_txt, template_html, contexto, destinatario):
    if not destinatario:
        return False, 'El destinatario no tiene correo electrónico.'
    if not _puede_enviar_correo():
        return False, 'El servidor SMTP no está configurado en el entorno.'

    try:
        cuerpo_txt = render_to_string(template_txt, contexto)
        cuerpo_html = render_to_string(template_html, contexto)
        remitente = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@opticaamaru.cl')
        correo = EmailMultiAlternatives(
            subject=asunto,
            body=cuerpo_txt,
            from_email=remitente,
            to=[destinatario],
        )
        correo.attach_alternative(cuerpo_html, 'text/html')
        correo.send(fail_silently=False)
        return True, ''
    except Exception as exc:
        return False, str(exc)


def notificar_evento_convenio(solicitud, evento, titulo, mensaje, request=None):
    email_destino = getattr(solicitud.cliente, 'email', '') or ''
    url_portal = ''
    if request is not None:
        url_portal = request.build_absolute_uri(reverse('portal_beneficiario'))

    enviada_email = False
    if email_destino:
        enviada_email, _ = enviar_correo_multiformato(
            asunto=f'Óptica Amaru · {titulo}',
            template_txt='convenios/emails/beneficiario_estado.txt',
            template_html='convenios/emails/beneficiario_estado.html',
            contexto={
                'solicitud': solicitud,
                'titulo': titulo,
                'mensaje': mensaje,
                'url_portal': url_portal,
            },
            destinatario=email_destino,
        )

    return NotificacionConvenio.objects.create(
        solicitud=solicitud,
        cliente=solicitud.cliente,
        evento=evento,
        titulo=titulo,
        mensaje=mensaje,
        enviada_email=enviada_email,
    )


def invalidar_verificaciones_activas(solicitud, usuario=None, motivo='Reemplazada por nuevo enlace de verificación.'):
    activas = solicitud.verificaciones.filter(
        estado__in=['pendiente_envio', 'enviada', 'pendiente_respuesta']
    )
    count = activas.update(estado='cancelada')
    if count:
        HistorialSolicitudConvenio.objects.create(
            solicitud=solicitud,
            evento='enlace_invalidado',
            estado_anterior=solicitud.estado,
            estado_nuevo=solicitud.estado,
            acreditacion_estado=solicitud.estado_acreditacion,
            usuario=usuario if (usuario and getattr(usuario, 'is_authenticated', False)) else None,
            comentario=motivo,
        )
    return count


def generar_y_enviar_verificacion_externa(
    solicitud,
    contacto_verificador=None,
    usuario=None,
    request=None,
    es_reenvio=False,
):
    convenio = solicitud.convenio
    contacto = contacto_verificador or solicitud.contacto_verificador
    if contacto is None:
        contacto = ContactoVerificadorConvenio.objects.filter(
            convenio=convenio,
            activo=True,
        ).first()

    if contacto is None or not contacto.activo:
        raise ValidationError('El convenio no tiene un contacto verificador activo configurado.')

    if solicitud.contacto_verificador_id != contacto.id:
        solicitud.contacto_verificador = contacto
        solicitud.save(update_fields=['contacto_verificador'])

    invalidar_verificaciones_activas(
        solicitud,
        usuario=usuario,
        motivo='Enlace anterior invalidado por reenvío de verificación.' if es_reenvio else 'Enlace previo reemplazado.',
    )

    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_token_verificacion(raw_token)
    dias = max(1, convenio.dias_vigencia_verificacion or 5)
    expira = timezone.now() + timedelta(days=dias)

    verificacion = VerificacionExternaConvenio.objects.create(
        solicitud=solicitud,
        convenio=convenio,
        beneficiario=solicitud.cliente,
        contacto_verificador=contacto,
        token_hash=token_hash,
        estado='pendiente_envio',
        fecha_expiracion=expira,
        creada_por=usuario if (usuario and getattr(usuario, 'is_authenticated', False)) else None,
    )

    ruta = reverse('verificacion_externa_responder', args=[raw_token])
    url_verificacion = request.build_absolute_uri(ruta) if request is not None else ruta

    enviado, error_msg = enviar_correo_multiformato(
        asunto='Solicitud de verificación de beneficiario — Óptica Amaru',
        template_txt='convenios/emails/verificador_solicitud.txt',
        template_html='convenios/emails/verificador_solicitud.html',
        contexto={
            'verificacion': verificacion,
            'solicitud': solicitud,
            'convenio': convenio,
            'contacto': contacto,
            'incluir_rut': convenio.incluir_rut_en_correo_verificacion,
            'url_verificacion': url_verificacion,
        },
        destinatario=contacto.correo,
    )

    if enviado:
        verificacion.estado = 'enviada'
        verificacion.fecha_envio = timezone.now()
        verificacion.enviada_por_correo = True
        verificacion.error_envio = ''
    else:
        verificacion.estado = 'pendiente_envio'
        verificacion.enviada_por_correo = False
        verificacion.error_envio = error_msg
    verificacion.save()

    nuevo_estado_sol = 'verificacion_enviada' if enviado else 'pendiente_verificacion'
    if solicitud.estado != nuevo_estado_sol and solicitud.puede_transicionar_a(nuevo_estado_sol):
        solicitud.transicionar_a(
            nuevo_estado_sol,
            usuario=usuario,
            comentario=(
                f'Enlace seguro {"reenviado" if es_reenvio else "enviado"} a {contacto.nombre} ({contacto.correo}).'
                if enviado
                else f'Verificación generada ({verificacion.codigo_verificacion}) pendiente de envío a {contacto.correo}. {error_msg}'.strip()
            ),
            nuevo_estado_acreditacion='pendiente',
            evento='verificacion_reenviada' if es_reenvio else ('verificacion_enviada' if enviado else 'verificacion_generada'),
        )
    else:
        HistorialSolicitudConvenio.objects.create(
            solicitud=solicitud,
            evento='verificacion_reenviada' if es_reenvio else ('verificacion_enviada' if enviado else 'verificacion_generada'),
            estado_anterior=solicitud.estado,
            estado_nuevo=solicitud.estado,
            acreditacion_estado=solicitud.estado_acreditacion,
            usuario=usuario if (usuario and getattr(usuario, 'is_authenticated', False)) else None,
            comentario=(
                f'Verificación {verificacion.codigo_verificacion} {"reenviada" if es_reenvio else "enviada"} a {contacto.correo}.'
                if enviado
                else f'Verificación {verificacion.codigo_verificacion} generada sin envío automático ({error_msg}).'
            ),
        )

    return verificacion, raw_token, url_verificacion


def iniciar_flujo_solicitud_convenio(solicitud, request=None):
    convenio = solicitud.convenio
    HistorialSolicitudConvenio.objects.create(
        solicitud=solicitud,
        evento='solicitud_creada',
        estado_anterior='',
        estado_nuevo='recibida',
        acreditacion_estado='recibida',
        comentario=f'Solicitud digital registrada para {convenio.nombre}.',
    )

    if convenio.metodo_validacion == 'padron_y_enlace':
        registro = BeneficiarioPadronConvenio.objects.filter(
            convenio=convenio,
            rut=solicitud.cliente.rut,
        ).first()
        if registro and registro.vigente:
            solicitud.validada_automaticamente = True
            solicitud.motivo_acreditacion = 'Beneficiario confirmado en el padrón interno del convenio.'
            solicitud.transicionar_a(
                'verificacion_confirmada',
                comentario=solicitud.motivo_acreditacion,
                nuevo_estado_acreditacion='validada',
                evento='verificacion_confirmada',
            )
            if not convenio.requiere_aprobacion_interna:
                emitir_autorizacion_digital(
                    solicitud,
                    comentario='Autorización emitida tras validación en padrón interno.',
                    request=request,
                )
            else:
                notificar_evento_convenio(
                    solicitud,
                    'verificacion_confirmada',
                    'Tu pertenencia al convenio ha sido verificada',
                    f'Tu solicitud {solicitud.codigo} fue verificada y pasó a revisión final de autorización.',
                    request=request,
                )
            return None

    if convenio.metodo_validacion in ('enlace_externo', 'padron_y_enlace'):
        contacto = solicitud.contacto_verificador or convenio.contactos_verificadores.filter(activo=True).first()
        if contacto:
            verificacion, _, _ = generar_y_enviar_verificacion_externa(
                solicitud,
                contacto_verificador=contacto,
                request=request,
            )
            notificar_evento_convenio(
                solicitud,
                'solicitud_recibida',
                'Solicitud recibida',
                f'Recibimos tu solicitud {solicitud.codigo} para {convenio.nombre}. Se gestionará la verificación con {convenio.institucion or convenio.nombre}.',
                request=request,
            )
            return verificacion

    solicitud.transicionar_a(
        'pendiente_verificacion',
        comentario='Solicitud recibida. Pendiente de verificación por el equipo de Óptica Amaru.',
        nuevo_estado_acreditacion='pendiente',
        evento='verificacion_pendiente',
    )
    notificar_evento_convenio(
        solicitud,
        'solicitud_recibida',
        'Solicitud recibida',
        f'Recibimos tu solicitud {solicitud.codigo} para {convenio.nombre}. Está pendiente de verificación.',
        request=request,
    )
    return None


def procesar_respuesta_verificacion_externa(verificacion, decision, comentario='', request=None):
    if verificacion.esta_expirada:
        if verificacion.estado != 'expirada':
            verificacion.estado = 'expirada'
            verificacion.save(update_fields=['estado'])
        raise ValidationError('Este enlace de verificación ha expirado.')

    if not verificacion.es_respondible:
        raise ValidationError('Esta solicitud de verificación ya fue respondida o invalidada.')

    if decision not in ('confirmada', 'rechazada', 'no_verificable'):
        raise ValidationError('Respuesta no válida.')

    ahora = timezone.now()
    verificacion.estado = decision
    verificacion.resultado = decision
    verificacion.comentario_verificador = (comentario or '').strip()
    verificacion.fecha_respuesta = ahora
    verificacion.save()

    solicitud = verificacion.solicitud
    contacto = verificacion.contacto_verificador

    if decision == 'confirmada':
        solicitud.motivo_acreditacion = (
            f'Pertenencia confirmada por {contacto.nombre} ({contacto.correo}).'
            + (f' Nota: {verificacion.comentario_verificador}' if verificacion.comentario_verificador else '')
        )
        solicitud.transicionar_a(
            'verificacion_confirmada',
            comentario=solicitud.motivo_acreditacion,
            nuevo_estado_acreditacion='validada',
            evento='verificacion_confirmada',
        )
        if not solicitud.convenio.requiere_aprobacion_interna:
            emitir_autorizacion_digital(
                solicitud,
                comentario='Beneficio autorizado tras confirmación externa de la institución.',
                request=request,
            )
        else:
            notificar_evento_convenio(
                solicitud,
                'verificacion_confirmada',
                'Tu pertenencia al convenio ha sido verificada',
                f'Tu pertenencia para la solicitud {solicitud.codigo} fue confirmada. Pronto recibirás la autorización final.',
                request=request,
            )

    elif decision == 'rechazada':
        solicitud.motivo_acreditacion = (
            f'Pertenencia rechazada por {contacto.nombre}.'
            + (f' Motivo: {verificacion.comentario_verificador}' if verificacion.comentario_verificador else '')
        )
        solicitud.transicionar_a(
            'rechazada',
            comentario=solicitud.motivo_acreditacion,
            nuevo_estado_acreditacion='rechazada',
            evento='verificacion_rechazada',
        )
        notificar_evento_convenio(
            solicitud,
            'solicitud_rechazada',
            'Tu solicitud requiere revisión o no ha sido validada',
            f'La institución no confirmó tu solicitud {solicitud.codigo}. {verificacion.comentario_verificador}'.strip(),
            request=request,
        )

    elif decision == 'no_verificable':
        solicitud.motivo_acreditacion = (
            f'El contacto {contacto.nombre} indicó que no fue posible verificar.'
            + (f' Detalle: {verificacion.comentario_verificador}' if verificacion.comentario_verificador else '')
        )
        solicitud.transicionar_a(
            'verificacion_no_disponible',
            comentario=solicitud.motivo_acreditacion,
            nuevo_estado_acreditacion='no_verificable',
            evento='verificacion_no_disponible',
        )
        notificar_evento_convenio(
            solicitud,
            'verificacion_no_disponible',
            'Tu solicitud requiere revisión',
            f'La institución no pudo confirmar automáticamente tu solicitud {solicitud.codigo}. El equipo de Óptica Amaru revisará el caso.',
            request=request,
        )

    return verificacion


def emitir_autorizacion_digital(solicitud, usuario=None, comentario='', request=None):
    if solicitud.estado not in ('verificacion_confirmada', 'verificacion_no_disponible', 'autorizada'):
        raise ValidationError('La solicitud debe estar verificada antes de emitir la autorización del beneficio.')

    autorizacion = getattr(solicitud, 'autorizacion', None)
    if autorizacion is None:
        autorizacion = AutorizacionConvenio.objects.create(
            solicitud=solicitud,
            beneficiario=solicitud.cliente,
            convenio=solicitud.convenio,
            autorizado_por=usuario if (usuario and getattr(usuario, 'is_authenticated', False)) else None,
        )

    if solicitud.estado in ('verificacion_confirmada', 'verificacion_no_disponible'):
        solicitud.transicionar_a(
            'autorizada',
            usuario=usuario,
            comentario=comentario or f'Autorización digital {autorizacion.codigo_autorizacion} emitida.',
            nuevo_estado_acreditacion='beneficio_autorizado',
            evento='beneficio_autorizado',
        )
        notificar_evento_convenio(
            solicitud,
            'beneficio_autorizado',
            'Beneficio autorizado',
            f'Tu solicitud {solicitud.codigo} fue autorizada ({autorizacion.codigo_autorizacion}). Ya puedes revisar tu código de retiro.',
            request=request,
        )

    return autorizacion


def registrar_entrega_convenio(solicitud, usuario, receptor_nombre='', observacion='', request=None):
    autorizacion = getattr(solicitud, 'autorizacion', None)
    if not autorizacion or autorizacion.estado != 'autorizada':
        raise ValidationError('No existe una autorización digital vigente para entregar esta solicitud.')
    if autorizacion.esta_vencida:
        raise ValidationError('La autorización digital se encuentra vencida.')
    if solicitud.estado != 'lista_retiro':
        raise ValidationError('La solicitud debe estar en estado "Lista para retiro" para registrar la entrega.')

    ahora = timezone.now()
    solicitud.fecha_entrega = ahora
    solicitud.entregada_por = usuario
    solicitud.receptor_nombre = (receptor_nombre or '').strip() or solicitud.cliente.nombre
    solicitud.observacion_entrega = (observacion or '').strip()

    solicitud.transicionar_a(
        'entregada',
        usuario=usuario,
        comentario=f'Retiro registrado para {solicitud.receptor_nombre}. {solicitud.observacion_entrega}'.strip(),
        nuevo_estado_acreditacion='beneficio_utilizado',
        evento='retiro_registrado',
    )

    autorizacion.estado = 'utilizada'
    autorizacion.fecha_utilizacion = ahora
    autorizacion.save()

    notificar_evento_convenio(
        solicitud,
        'entrega_registrada',
        'Retiro registrado',
        f'Confirmamos la entrega de tu pedido {solicitud.codigo} en Óptica Amaru.',
        request=request,
    )
    return solicitud
