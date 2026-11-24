##ESTO ADMITO QUE OCUPE IA, NO EN TODO, MAS QUE NADA PARA ENTENDERLO XQ NI PUTA IDEA PERO ERA MUCHO Y ME AYUDE CON LA IA QLA YIAAA OE Q ME CAE MAL EL YOKO, HOLA

import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from opticaApp.models import *
from opticaApp.views import rut_valido



class RutTests(TestCase):
    def test_rut_bueno(self):
        self.assertEqual(rut_valido('16.482.915-4'), '16482915-4')
        self.assertEqual(rut_valido('12345678-5'), '12345678-5')

    def test_rut_malo(self):                          
        self.assertIsNone(rut_valido('16.482.915-3')) 
        self.assertIsNone(rut_valido(''))
        self.assertIsNone(rut_valido('abc'))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class BaseTests(TestCase):
    def setUp(self):
        self.tipo = TipoLente.objects.create(nombre='Lentes de lectura')
        for numero, nombre in enumerate(['Recibida', 'En revisión', 'En taller', 'Control de calidad',
                                         'Lista para retiro', 'Entregada'], start=1):
            Estado.objects.create(nombre=nombre, orden=numero)

    def datos(self, **cambios):
        d = {'rut': '16.482.915-4', 'nombre': 'Carlos Rojas', 'contacto': 'WhatsApp',
             'telefono': '+56 9 5551 0101', 'tipo': self.tipo.idTipoLente, 'acepta_datos': 'on',
             'receta': SimpleUploadedFile('receta.png', b'contenido de prueba', content_type='image/png')}
        d.update(cambios)
        return d


class SolicitarTests(BaseTests):
    def test_solicitud_correcta(self):            
        respuesta = self.client.post(reverse('solicitar'), self.datos())
        solicitud = Solicitud.objects.get()
        self.assertRedirects(respuesta, reverse('solicitud_creada', args=[solicitud.folio]))
        self.assertEqual(solicitud.cliente.rut, '16482915-4')
        self.assertEqual(solicitud.estado.nombre, 'Recibida')

    def test_rut_invalido_no_guarda_nada(self):     
        self.client.post(reverse('solicitar'), self.datos(rut='16.482.915-3'))
        self.assertEqual(Cliente.objects.count(), 0)
        self.assertEqual(Solicitud.objects.count(), 0)

    def test_sin_autorizacion_no_se_envia(self):  
        datos = self.datos()
        del datos['acepta_datos']
        self.client.post(reverse('solicitar'), datos)
        self.assertEqual(Solicitud.objects.count(), 0)

    def test_el_error_se_muestra_y_no_borra_lo_escrito(self):
        r = self.client.post(reverse('solicitar'), self.datos(rut='16.482.915-3'))
        self.assertContains(r, 'El RUT no es válido')      # el mensaje sale en la página
        self.assertContains(r, 'Carlos Rojas')              # y el nombre sigue escrito en el formulario

    def test_prefiere_correo_pero_no_lo_escribe(self):
        r = self.client.post(reverse('solicitar'), self.datos(contacto='Correo'))
        self.assertContains(r, 'necesitamos tu correo')
        self.assertEqual(Solicitud.objects.count(), 0)

    def test_receta_con_formato_malo(self):
        malo = SimpleUploadedFile('virus.exe', b'MZ...')
        self.client.post(reverse('solicitar'), self.datos(receta=malo))
        self.assertEqual(Solicitud.objects.count(), 0)

    def test_sin_receta_pero_marcando_la_opcion(self):
        datos = self.datos(sin_receta='on')
        del datos['receta']
        self.client.post(reverse('solicitar'), datos)
        self.assertEqual(Solicitud.objects.count(), 1)


class ConsultaTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.client.post(reverse('solicitar'), self.datos())
        self.solicitud = Solicitud.objects.get()

    def test_consulta_correcta(self):                 # HU06
        r = self.client.post(reverse('consultar_estado'),
                             {'rut': '16.482.915-4', 'folio': self.solicitud.folio.lower()})
        self.assertContains(r, 'Recibida')

    def test_rut_ajeno_no_ve_la_solicitud(self):      # P07
        Cliente.objects.create(rut='12345678-5', nombre='Otra Persona')
        r = self.client.post(reverse('consultar_estado'),
                             {'rut': '12.345.678-5', 'folio': self.solicitud.folio})
        self.assertContains(r, 'No encontramos')
        self.assertNotContains(r, 'Carlos')


class PersonalTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.client.post(reverse('solicitar'), self.datos())
        self.solicitud = Solicitud.objects.get()
        User.objects.create_user('personal', password='clave-de-prueba-123')

    def test_panel_pide_iniciar_sesion(self):
        r = self.client.get(reverse('lista_solicitudes'))
        self.assertEqual(r.status_code, 302)           # 302 = lo redirige al login

    def test_panel_con_sesion(self):
        self.client.login(username='personal', password='clave-de-prueba-123')
        r = self.client.get(reverse('lista_solicitudes'))
        self.assertContains(r, self.solicitud.folio)
        self.assertContains(r, '16.***.915-4')         # el RUT sale tapado
        self.assertNotContains(r, '16482915-4')

    def test_buscar_por_rut(self):
        self.client.login(username='personal', password='clave-de-prueba-123')
        self.assertContains(self.client.get(reverse('lista_solicitudes'), {'q': '16.482.915-4'}),
                            self.solicitud.folio)
        self.assertNotContains(self.client.get(reverse('lista_solicitudes'), {'q': '99999999'}),
                               self.solicitud.folio)

    def test_cambiar_estado(self):                    # HU03
        self.client.login(username='personal', password='clave-de-prueba-123')
        en_taller = Estado.objects.get(orden=3)
        self.client.post(reverse('detalle_solicitud', args=[self.solicitud.idSolicitud]),
                         {'estado': en_taller.idEstado})
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado.nombre, 'En taller')


class PaginasTests(TestCase):
    def test_paginas_publicas(self):
        for nombre in ('inicio', 'solicitar', 'consultar_estado'):
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 200, nombre)


@override_settings(
    MEDIA_ROOT=tempfile.mkdtemp(),
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
)
class PagoFlowTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.producto = ProductoLente.objects.create(
            nombre='Marco Amaru Classic',
            marca='Amaru',
            precio=49990,
            stock=5,
            publicado=True,
        )
        self.datos_bancarios = DatosBancarios.objects.create(
            titular='Óptica Amaru SpA',
            rut='76.123.456-7',
            banco='BancoEstado',
            tipo_cuenta='Cuenta Vista',
            numero_cuenta='123456789',
            correo='pagos@opticaamaru.cl',
            instrucciones='Indicar el folio en el asunto.',
            activo=True,
        )
        self.staff = User.objects.create_user(
            'staff_optica',
            password='clave-segura-staff-123',
            is_staff=True,
        )

    def _crear_solicitud(self, **extra):
        datos = self.datos(
            direccion='Av. Granaderos 1234',
            comuna='Calama',
            ciudad='Calama',
            marco_personalizado='Marco negro liviano',
            **extra,
        )
        return self.client.post(reverse('solicitar'), datos)

    def _pdf_valido(self, nombre='comprobante.pdf'):
        return SimpleUploadedFile(nombre, b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n', content_type='application/pdf')

    def _png_valido(self, nombre='comprobante.png'):
        return SimpleUploadedFile(nombre, b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR', content_type='image/png')

    def test_creacion_solicitud_y_pago_pendiente_y_opciones(self):
        r = self._crear_solicitud()
        solicitud = Solicitud.objects.get()
        self.assertRedirects(r, reverse('solicitud_creada', args=[solicitud.folio]))
        pago = PagoSolicitud.objects.get(solicitud=solicitud)
        self.assertEqual(pago.estado, 'Pendiente de pago')

        r_creada = self.client.get(reverse('solicitud_creada', args=[solicitud.folio]))
        self.assertContains(r_creada, 'Pagar ahora')
        self.assertContains(r_creada, 'Pagar más tarde')
        self.assertContains(r_creada, reverse('pagar_solicitud', args=[solicitud.folio]))

    def test_pagar_mas_tarde_y_recuperar_con_rut_y_folio(self):
        self._crear_solicitud()
        solicitud = Solicitud.objects.get()

        # Nuevo cliente/sesión sin autorización previa
        cliente_nuevo = self.client.__class__()
        r_pago_sin_rut = cliente_nuevo.get(reverse('pagar_solicitud', args=[solicitud.folio]))
        self.assertContains(r_pago_sin_rut, 'Verifica tu identidad')
        self.assertNotContains(r_pago_sin_rut, self.datos_bancarios.numero_cuenta)

        # No se puede saltar la verificación de RUT enviando un comprobante directo
        r_bypass = cliente_nuevo.post(
            reverse('pagar_solicitud', args=[solicitud.folio]),
            {'comprobante': self._pdf_valido()},
        )
        self.assertContains(r_bypass, 'Verifica tu identidad')
        self.assertEqual(PagoSolicitud.objects.get(solicitud=solicitud).estado, 'Pendiente de pago')

        # Recuperación mediante RUT + folio en consultar_estado
        r_consulta = cliente_nuevo.post(
            reverse('consultar_estado'),
            {'rut': '16.482.915-4', 'folio': solicitud.folio},
        )
        self.assertContains(r_consulta, 'Pendiente de pago')
        self.assertContains(r_consulta, 'Realizar pago')

        # Ahora la sesión está autorizada para pagar
        r_pago = cliente_nuevo.get(reverse('pagar_solicitud', args=[solicitud.folio]))
        self.assertContains(r_pago, self.datos_bancarios.banco)
        self.assertContains(r_pago, self.datos_bancarios.numero_cuenta)
        self.assertContains(r_pago, 'Enviar comprobante para revisión')

    def test_datos_bancarios_no_configurados_no_rompe_pantalla(self):
        self._crear_solicitud()
        solicitud = Solicitud.objects.get()
        DatosBancarios.objects.all().delete()
        r = self.client.get(reverse('pagar_solicitud', args=[solicitud.folio]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'todavía no están configurados')

    def test_subir_pdf_e_imagen_validos_y_bloquear_reenvio_en_revision(self):
        self._crear_solicitud()
        solicitud = Solicitud.objects.get()

        r = self.client.post(
            reverse('pagar_solicitud', args=[solicitud.folio]),
            {
                'comprobante': self._pdf_valido(),
                'estado': 'Pago confirmado',  # intento de manipulación del cliente
            },
        )
        self.assertRedirects(r, reverse('pagar_solicitud', args=[solicitud.folio]))
        pago = PagoSolicitud.objects.get(solicitud=solicitud)
        self.assertEqual(pago.estado, 'Comprobante enviado')  # nunca Pago confirmado

        # Mientras está en revisión, no permite reenviar otro comprobante
        r_get = self.client.get(reverse('pagar_solicitud', args=[solicitud.folio]))
        self.assertContains(r_get, 'Comprobante en revisión')
        self.assertNotContains(r_get, 'Enviar comprobante para revisión')

        r_doble = self.client.post(
            reverse('pagar_solicitud', args=[solicitud.folio]),
            {'comprobante': self._png_valido()},
        )
        self.assertRedirects(r_doble, reverse('pagar_solicitud', args=[solicitud.folio]))

    def test_rechazar_formatos_invalidos_y_tamano_excesivo(self):
        self._crear_solicitud()
        solicitud = Solicitud.objects.get()
        url = reverse('pagar_solicitud', args=[solicitud.folio])

        # Formato .exe
        exe = SimpleUploadedFile('virus.exe', b'MZ\x90\x00', content_type='application/octet-stream')
        r_exe = self.client.post(url, {'comprobante': exe})
        self.assertContains(r_exe, 'Solo se permiten imágenes JPG, JPEG, PNG o documentos PDF')
        self.assertEqual(PagoSolicitud.objects.get(solicitud=solicitud).estado, 'Pendiente de pago')

        # PDF falso (extensión .pdf pero cabecera inválida)
        fake_pdf = SimpleUploadedFile('fake.pdf', b'MZ_FAKE_CONTENT', content_type='application/pdf')
        r_fake = self.client.post(url, {'comprobante': fake_pdf})
        self.assertContains(r_fake, 'no es válido')
        self.assertEqual(PagoSolicitud.objects.get(solicitud=solicitud).estado, 'Pendiente de pago')

        # Archivo mayor a 5 MB
        grande = SimpleUploadedFile('grande.pdf', b'%PDF-1.4\n' + (b'0' * (5 * 1024 * 1024 + 10)), content_type='application/pdf')
        r_grande = self.client.post(url, {'comprobante': grande})
        self.assertContains(r_grande, 'no puede superar los 5 MB')
        self.assertEqual(PagoSolicitud.objects.get(solicitud=solicitud).estado, 'Pendiente de pago')

    def test_revision_administrativa_rechazo_correccion_y_confirmacion(self):
        self._crear_solicitud()
        solicitud = Solicitud.objects.get()
        pago = PagoSolicitud.objects.get(solicitud=solicitud)

        # Cliente no autenticado no puede revisar pago
        anon = self.client.__class__()
        r_anon = anon.post(reverse('revisar_pago', args=[pago.id]), {'accion': 'confirmar'})
        self.assertEqual(r_anon.status_code, 302)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, 'Pendiente de pago')

        # Cliente sube imagen PNG válida
        self.client.post(reverse('pagar_solicitud', args=[solicitud.folio]), {'comprobante': self._png_valido()})
        pago.refresh_from_db()
        self.assertEqual(pago.estado, 'Comprobante enviado')

        # Staff rechaza el comprobante
        staff_client = self.client.__class__()
        staff_client.force_login(self.staff)
        r_rechazo = staff_client.post(
            reverse('revisar_pago', args=[pago.id]),
            {'accion': 'rechazar', 'observacion': 'Imagen borrosa'},
        )
        self.assertRedirects(r_rechazo, reverse('lista_solicitudes'))
        pago.refresh_from_db()
        self.assertEqual(pago.estado, 'Rechazado')
        self.assertEqual(pago.observacion, 'Imagen borrosa')
        self.assertEqual(pago.revisado_por, self.staff)

        # Cliente ve el rechazo y puede volver a enviar comprobante
        r_pago_rech = self.client.get(reverse('pagar_solicitud', args=[solicitud.folio]))
        self.assertContains(r_pago_rech, 'Imagen borrosa')
        self.assertContains(r_pago_rech, 'Enviar comprobante para revisión')

        self.client.post(reverse('pagar_solicitud', args=[solicitud.folio]), {'comprobante': self._pdf_valido('nuevo.pdf')})
        pago.refresh_from_db()
        self.assertEqual(pago.estado, 'Comprobante enviado')

        # Staff confirma el pago
        staff_client.post(reverse('revisar_pago', args=[pago.id]), {'accion': 'confirmar'})
        pago.refresh_from_db()
        self.assertEqual(pago.estado, 'Pago confirmado')

        # Confirmado: cliente ya no puede volver a enviar comprobante
        r_confirmado = self.client.get(reverse('pagar_solicitud', args=[solicitud.folio]))
        self.assertContains(r_confirmado, 'Pago confirmado')
        self.assertNotContains(r_confirmado, 'Enviar comprobante para revisión')

        # Y ahora staff sí puede avanzar la solicitud a En taller
        en_taller = Estado.objects.get(orden=3)
        staff_client.post(reverse('detalle_solicitud', args=[solicitud.idSolicitud]), {'estado': en_taller.idEstado})
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado.nombre, 'En taller')

    def test_otros_modulos_no_afectados(self):
        for nombre in ('inicio', 'catalogo', 'pedir_hora', 'consultar_estado'):
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 200, nombre)

