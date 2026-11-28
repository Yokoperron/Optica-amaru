import tempfile
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from opticaApp.models import Cliente, ProductoLente, TipoLente
from opticaApp.models_convenios import (
    AutorizacionConvenio,
    ContactoVerificadorConvenio,
    Convenio,
    HistorialSolicitudConvenio,
    NotificacionConvenio,
    SolicitudConvenio,
    VerificacionExternaConvenio,
)
from opticaApp.services_convenios import (
    generar_y_enviar_verificacion_externa,
    registrar_entrega_convenio,
)


@override_settings(
    MEDIA_ROOT=tempfile.mkdtemp(),
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
)
class ConveniosVerificacionExternaTests(TestCase):
    def setUp(self):
        call_command('crear_roles')
        self.tipo = TipoLente.objects.create(nombre='Ópticos')
        self.producto = ProductoLente.objects.create(
            nombre='Marco Amaru Classic',
            marca='Amaru',
            precio=49990,
            stock=5,
            publicado=True,
        )
        self.convenio = Convenio.objects.create(
            nombre='Convenio Empresa Norte',
            slug='empresa-norte',
            institucion='Empresa Norte S.A.',
            descripcion='Descuento en lentes ópticos.',
            beneficios='30% de descuento en marco y cristales.',
            metodo_validacion='enlace_externo',
            requiere_aprobacion_interna=False,
            dias_vigencia_verificacion=5,
            max_solicitudes_por_beneficiario=2,
            activo=True,
        )
        self.contacto = ContactoVerificadorConvenio.objects.create(
            convenio=self.convenio,
            nombre='María González',
            correo='rrhh@empresanorte.cl',
            empresa='Empresa Norte S.A.',
            cargo='Jefa de Bienestar',
            activo=True,
        )

        self.admin_user = User.objects.create_user('admin_optica', 'admin@amaru.cl', 'pass1234', is_staff=True)
        self.admin_user.groups.add(Group.objects.get(name='Administradora'))

        self.asistente_user = User.objects.create_user('asistente', 'asistente@amaru.cl', 'pass1234', is_staff=True)
        self.asistente_user.groups.add(Group.objects.get(name='Asistente de ventas'))

    def test_admin_crea_convenio_y_configura_contacto_con_permisos(self):
        # Asistente no puede crear convenios ni configurar contactos
        self.client.force_login(self.asistente_user)
        self.assertEqual(self.client.get(reverse('panel_convenio_crear')).status_code, 403)
        self.assertEqual(self.client.get(reverse('panel_convenio_contactos', args=[self.convenio.idConvenio])).status_code, 403)

        # Administradora sí puede
        self.client.force_login(self.admin_user)
        resp = self.client.post(reverse('panel_convenio_crear'), {
            'nombre': 'Convenio Salud Sur',
            'institucion': 'Clínica Sur',
            'descripcion': 'Beneficio salud.',
            'beneficios': '25% descuento.',
            'metodo_validacion': 'enlace_externo',
            'dias_vigencia_verificacion': 7,
            'max_solicitudes_por_beneficiario': 1,
            'vigencia_autorizacion_dias': 30,
            'activo': 'on',
            'permite_marco_personalizado': 'on',
            'incluir_rut_en_correo_verificacion': 'on',
        })
        nuevo = Convenio.objects.get(nombre='Convenio Salud Sur')
        self.assertRedirects(resp, reverse('panel_convenio_contactos', args=[nuevo.idConvenio]))

        self.client.post(reverse('panel_convenio_contactos', args=[nuevo.idConvenio]), {
            'nombre': 'Pedro Soto',
            'correo': 'psoto@clinicasur.cl',
            'empresa': 'Clínica Sur',
            'cargo': 'RRHH',
            'metodo_confirmacion': 'Enlace seguro por correo electrónico',
            'activo': 'on',
        })
        self.assertTrue(ContactoVerificadorConvenio.objects.filter(convenio=nuevo, correo='psoto@clinicasur.cl').exists())

    def test_flujo_completo_solicitud_enlace_confirmacion_autorizacion_y_retiro(self):
        # 1. Correo obligatorio incluso si elige WhatsApp; se envía el código al correo
        resp_sin_email = self.client.post(reverse('solicitar_convenio', args=[self.convenio.slug]), {
            'rut': '16.482.915-4',
            'nombre': 'Carlos Rojas',
            'contacto': 'WhatsApp',
            'telefono': '+56912345678',
            'tipo_lente': self.tipo.idTipoLente,
            'producto': self.producto.id,
            'acepta_datos': 'on',
        })
        self.assertEqual(resp_sin_email.status_code, 200)
        self.assertContains(resp_sin_email, 'Escribe tu correo electrónico')

        # Beneficiario crea solicitud con WhatsApp + correo obligatorio
        resp = self.client.post(reverse('solicitar_convenio', args=[self.convenio.slug]), {
            'rut': '16.482.915-4',
            'nombre': 'Carlos Rojas',
            'contacto': 'WhatsApp',
            'telefono': '+56912345678',
            'email': 'carlos@correo.cl',
            'tipo_lente': self.tipo.idTipoLente,
            'producto': self.producto.id,
            'acepta_datos': 'on',
        })
        sol = SolicitudConvenio.objects.get()
        self.assertRedirects(resp, reverse('convenio_solicitud_creada', args=[sol.codigo]))
        self.assertEqual(sol.estado, 'verificacion_enviada')
        self.assertEqual(sol.contacto_verificador, self.contacto)

        # 2. Se envió correo al contacto verificador y correo con código al beneficiario
        self.assertEqual(len(mail.outbox), 2)
        correo_verif = mail.outbox[0]
        correo_benef = mail.outbox[1]
        self.assertEqual(correo_verif.to, ['rrhh@empresanorte.cl'])
        self.assertEqual(correo_benef.to, ['carlos@correo.cl'])
        self.assertIn(sol.codigo, correo_benef.body)
        self.assertIn('/convenios/verificar/', correo_verif.body)

        # Extraer raw_token del correo y comprobar que en BD solo está el hash
        verif = VerificacionExternaConvenio.objects.get(solicitud=sol)
        url_line = [l for l in correo_verif.body.splitlines() if '/convenios/verificar/' in l][0].strip()
        raw_token = url_line.rstrip('/').split('/')[-1]
        self.assertNotEqual(verif.token_hash, raw_token)
        self.assertNotIn(raw_token, verif.token_hash)

        # 3. Contacto externo accede al enlace sin iniciar sesión
        self.client.logout()
        url_ext = reverse('verificacion_externa_responder', args=[raw_token])
        r_get = self.client.get(url_ext)
        self.assertEqual(r_get.status_code, 200)
        self.assertContains(r_get, 'Carlos Rojas')

        # 4. Contacto confirma pertenencia -> actualiza verificación, solicitud, autoriza y crea QR
        r_post = self.client.post(url_ext, {'decision': 'confirmada', 'comentario': 'Funcionario vigente'})
        self.assertContains(r_post, 'Confirmación registrada correctamente')

        verif.refresh_from_db()
        sol.refresh_from_db()
        self.assertEqual(verif.estado, 'confirmada')
        self.assertEqual(sol.estado, 'autorizada')
        self.assertEqual(sol.estado_acreditacion, 'beneficio_autorizado')
        aut = AutorizacionConvenio.objects.get(solicitud=sol)
        self.assertNotIn('16482915', aut.qr_token)

        # 5. Intentar reutilizar enlace ya respondido -> bloqueado
        r_reuse = self.client.get(url_ext)
        self.assertContains(r_reuse, 'Solicitud ya respondida')

        # 6. No se puede entregar antes de marcar lista para retiro
        with self.assertRaises(ValidationError):
            registrar_entrega_convenio(sol, usuario=self.asistente_user)

        # 7. Personal pasa a lista para retiro y registra entrega mediante QR
        self.client.force_login(self.admin_user)
        self.client.post(reverse('panel_convenio_solicitud_detalle', args=[sol.idSolicitudConvenio]), {
            'accion': 'lista_retiro',
            'comentario': 'Lentes listos en mostrador',
        })
        sol.refresh_from_db()
        self.assertEqual(sol.estado, 'lista_retiro')

        self.client.force_login(self.asistente_user)
        url_qr = reverse('panel_convenios_verificar_qr', args=[aut.qr_token])
        r_ent = self.client.post(url_qr, {'accion': 'registrar_entrega', 'receptor_nombre': 'Carlos Rojas'})
        self.assertRedirects(r_ent, url_qr)

        sol.refresh_from_db()
        aut.refresh_from_db()
        self.assertEqual(sol.estado, 'entregada')
        self.assertEqual(aut.estado, 'utilizada')
        self.assertEqual(sol.entregada_por, self.asistente_user)

        # 8. Impedir retiros duplicados
        with self.assertRaises(ValidationError):
            registrar_entrega_convenio(sol, usuario=self.asistente_user)

        # 9. Historial completo registrado
        eventos = list(HistorialSolicitudConvenio.objects.filter(solicitud=sol).values_list('evento', flat=True))
        for esperado in ['solicitud_creada', 'verificacion_enviada', 'verificacion_confirmada', 'beneficio_autorizado', 'lista_retiro', 'retiro_registrado']:
            self.assertIn(esperado, eventos)

    def test_rechazo_externo_y_aprobacion_interna_opcional(self):
        self.convenio.requiere_aprobacion_interna = True
        self.convenio.save()

        cliente = Cliente.objects.create(rut='12345678-5', nombre='Ana Pérez', contacto='WhatsApp', acepta_datos=True)
        sol = SolicitudConvenio.objects.create(convenio=self.convenio, cliente=cliente, contacto_verificador=self.contacto)
        verif, raw_token, _ = generar_y_enviar_verificacion_externa(sol, contacto_verificador=self.contacto)

        # Rechazo externo
        resp = self.client.post(reverse('verificacion_externa_responder', args=[raw_token]), {
            'decision': 'rechazada',
            'comentario': 'No trabaja aquí',
        })
        self.assertContains(resp, 'Rechazo registrado correctamente')
        sol.refresh_from_db()
        self.assertEqual(sol.estado, 'rechazada')
        self.assertFalse(AutorizacionConvenio.objects.filter(solicitud=sol).exists())

    def test_enlace_expirado_y_reenvio_invalida_anterior(self):
        cliente = Cliente.objects.create(rut='16482915-4', nombre='Carlos Rojas', contacto='WhatsApp', acepta_datos=True)
        sol = SolicitudConvenio.objects.create(convenio=self.convenio, cliente=cliente, contacto_verificador=self.contacto)

        v1, token1, _ = generar_y_enviar_verificacion_externa(sol, contacto_verificador=self.contacto)
        # Reenvío desde servicio/panel invalida v1
        v2, token2, _ = generar_y_enviar_verificacion_externa(sol, contacto_verificador=self.contacto, usuario=self.admin_user, es_reenvio=True)

        v1.refresh_from_db()
        self.assertEqual(v1.estado, 'cancelada')
        self.assertTrue(HistorialSolicitudConvenio.objects.filter(solicitud=sol, evento='enlace_invalidado').exists())

        # Token 1 ya no sirve
        r1 = self.client.get(reverse('verificacion_externa_responder', args=[token1]))
        self.assertEqual(r1.status_code, 410)
        self.assertContains(r1, 'Solicitud no disponible', status_code=410)

        # Expirar v2
        v2.fecha_expiracion = timezone.now() - timedelta(hours=1)
        v2.save()
        r2 = self.client.get(reverse('verificacion_externa_responder', args=[token2]))
        self.assertEqual(r2.status_code, 410)
        self.assertContains(r2, 'Enlace expirado', status_code=410)

    def test_beneficiario_no_puede_ver_solicitudes_ajenas(self):
        c1 = Cliente.objects.create(rut='16482915-4', nombre='Carlos', contacto='WhatsApp', acepta_datos=True)
        c2 = Cliente.objects.create(rut='12345678-5', nombre='Otro', contacto='WhatsApp', acepta_datos=True)
        s1 = SolicitudConvenio.objects.create(convenio=self.convenio, cliente=c1)
        s2 = SolicitudConvenio.objects.create(convenio=self.convenio, cliente=c2)

        session = self.client.session
        session['convenio_beneficiario_rut'] = c1.rut
        session.save()

        self.assertEqual(self.client.get(reverse('detalle_beneficiario_convenio', args=[s1.codigo])).status_code, 200)
        self.assertEqual(self.client.get(reverse('detalle_beneficiario_convenio', args=[s2.codigo])).status_code, 403)
