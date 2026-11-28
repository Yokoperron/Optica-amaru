import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def generar_codigo_convenio():
    alfabeto = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return 'CNV-' + ''.join(secrets.choice(alfabeto) for _ in range(6))


def generar_codigo_verificacion():
    alfabeto = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return 'VER-' + ''.join(secrets.choice(alfabeto) for _ in range(8))


def generar_codigo_autorizacion():
    alfabeto = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return 'AUT-' + ''.join(secrets.choice(alfabeto) for _ in range(8))


def generar_qr_token():
    return secrets.token_urlsafe(32)


def hash_token_verificacion(raw_token):
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


class Convenio(models.Model):
    METODOS_VALIDACION = [
        ('enlace_externo', 'Verificación externa por enlace seguro'),
        ('padron_y_enlace', 'Padrón interno con respaldo de enlace externo'),
        ('revision_interna', 'Revisión administrativa interna'),
    ]

    idConvenio = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True)
    institucion = models.CharField(
        max_length=150,
        blank=True,
        help_text='Empresa, institución u organización asociada.',
    )
    descripcion = models.TextField()
    activo = models.BooleanField(default=True)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_termino = models.DateField(null=True, blank=True)

    beneficios = models.TextField(
        help_text='Detalle de descuentos, coberturas o beneficios disponibles.',
    )
    condiciones_uso = models.TextField(blank=True)
    requisitos_acreditacion = models.TextField(blank=True)
    restricciones = models.TextField(blank=True)
    info_beneficiarios = models.TextField(blank=True)
    info_administrativa = models.TextField(blank=True)

    productos_permitidos = models.ManyToManyField(
        'opticaApp.ProductoLente',
        blank=True,
        related_name='convenios',
        help_text='Si se deja vacío, el beneficiario puede elegir cualquier lente publicado o describir uno.',
    )
    permite_marco_personalizado = models.BooleanField(default=True)
    requiere_receta = models.BooleanField(default=False)

    metodo_validacion = models.CharField(
        max_length=30,
        choices=METODOS_VALIDACION,
        default='enlace_externo',
    )
    requiere_aprobacion_interna = models.BooleanField(
        default=False,
        help_text='Si está activo, tras la confirmación externa un trabajador debe autorizar manualmente el beneficio.',
    )
    incluir_rut_en_correo_verificacion = models.BooleanField(
        default=True,
        help_text='Incluir el RUT del solicitante en el correo y pantalla de verificación para la empresa.',
    )
    dias_vigencia_verificacion = models.PositiveIntegerField(
        default=5,
        help_text='Días de vigencia del enlace seguro enviado al contacto verificador.',
    )
    max_solicitudes_por_beneficiario = models.PositiveIntegerField(
        default=1,
        help_text='Máximo de solicitudes activas o autorizadas por RUT (0 = sin límite).',
    )
    vigencia_autorizacion_dias = models.PositiveIntegerField(default=30)

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-activo', 'nombre']
        permissions = [
            ('manage_convenio', 'Puede administrar convenios digitales'),
        ]

    @property
    def esta_vigente(self):
        if not self.activo:
            return False
        hoy = timezone.localdate()
        if self.fecha_inicio and hoy < self.fecha_inicio:
            return False
        if self.fecha_termino and hoy > self.fecha_termino:
            return False
        return True

    def clean(self):
        if self.fecha_inicio and self.fecha_termino and self.fecha_termino < self.fecha_inicio:
            raise ValidationError('La fecha de término debe ser posterior a la fecha de inicio.')

    def __str__(self):
        if self.institucion:
            return f'{self.nombre} ({self.institucion})'
        return self.nombre


class ContactoVerificadorConvenio(models.Model):
    convenio = models.ForeignKey(
        Convenio,
        on_delete=models.CASCADE,
        related_name='contactos_verificadores',
    )
    nombre = models.CharField(max_length=150)
    correo = models.EmailField()
    empresa = models.CharField(max_length=150, blank=True)
    cargo = models.CharField(max_length=100, blank=True)
    metodo_confirmacion = models.CharField(
        max_length=60,
        default='Enlace seguro por correo electrónico',
    )
    activo = models.BooleanField(default=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-activo', 'nombre']
        unique_together = ('convenio', 'correo')

    def __str__(self):
        cargo_txt = f' · {self.cargo}' if self.cargo else ''
        return f'{self.nombre}{cargo_txt} ({self.correo})'


class BeneficiarioPadronConvenio(models.Model):
    convenio = models.ForeignKey(
        Convenio,
        on_delete=models.CASCADE,
        related_name='padron',
    )
    rut = models.CharField(max_length=12)
    nombre_completo = models.CharField(max_length=150)
    codigo_interno = models.CharField(
        max_length=60,
        blank=True,
        help_text='Ej: N° de funcionario, credencial o ficha interna.',
    )
    activo = models.BooleanField(default=True)
    fecha_vigencia_hasta = models.DateField(null=True, blank=True)
    observacion = models.CharField(max_length=200, blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre_completo']
        unique_together = ('convenio', 'rut')

    @property
    def vigente(self):
        if not self.activo:
            return False
        if self.fecha_vigencia_hasta and timezone.localdate() > self.fecha_vigencia_hasta:
            return False
        return True

    def __str__(self):
        return f'{self.nombre_completo} ({self.rut}) - {self.convenio.nombre}'


class SolicitudConvenio(models.Model):
    ESTADOS_ACREDITACION = [
        ('recibida', 'Solicitud recibida'),
        ('pendiente', 'Verificación externa pendiente'),
        ('validada', 'Pertenencia confirmada'),
        ('rechazada', 'Pertenencia rechazada'),
        ('no_verificable', 'No fue posible verificar'),
        ('beneficio_autorizado', 'Beneficio autorizado'),
        ('beneficio_utilizado', 'Beneficio utilizado'),
    ]

    ESTADOS_SOLICITUD = [
        ('recibida', 'Solicitud recibida'),
        ('pendiente_verificacion', 'Pendiente de verificación'),
        ('verificacion_enviada', 'Verificación enviada a empresa'),
        ('verificacion_confirmada', 'Verificación confirmada'),
        ('verificacion_no_disponible', 'No verificable / en revisión'),
        ('rechazada', 'Rechazada'),
        ('autorizada', 'Autorizada'),
        ('en_preparacion', 'En preparación'),
        ('lista_retiro', 'Lista para retiro'),
        ('entregada', 'Entregada'),
        ('cancelada', 'Cancelada'),
    ]

    TRANSICIONES_VALIDAS = {
        'recibida': [
            'pendiente_verificacion',
            'verificacion_enviada',
            'verificacion_confirmada',
            'rechazada',
            'cancelada',
        ],
        'pendiente_verificacion': [
            'verificacion_enviada',
            'verificacion_confirmada',
            'verificacion_no_disponible',
            'rechazada',
            'cancelada',
        ],
        'verificacion_enviada': [
            'verificacion_confirmada',
            'verificacion_no_disponible',
            'rechazada',
            'cancelada',
        ],
        'verificacion_no_disponible': [
            'verificacion_enviada',
            'verificacion_confirmada',
            'autorizada',
            'rechazada',
            'cancelada',
        ],
        'verificacion_confirmada': [
            'autorizada',
            'rechazada',
            'cancelada',
        ],
        'autorizada': ['en_preparacion', 'lista_retiro', 'cancelada'],
        'en_preparacion': ['lista_retiro', 'cancelada'],
        'lista_retiro': ['entregada', 'cancelada'],
        'entregada': [],
        'rechazada': [],
        'cancelada': [],
    }

    PASOS_SEGUIMIENTO = [
        ('recibida', 'Recibida'),
        ('verificacion_enviada', 'En verificación'),
        ('verificacion_confirmada', 'Confirmada'),
        ('autorizada', 'Autorizada'),
        ('en_preparacion', 'En preparación'),
        ('lista_retiro', 'Lista para retiro'),
        ('entregada', 'Entregada'),
    ]

    idSolicitudConvenio = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=16, unique=True, default=generar_codigo_convenio)
    token_acceso = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    convenio = models.ForeignKey(
        Convenio,
        on_delete=models.PROTECT,
        related_name='solicitudes',
    )
    cliente = models.ForeignKey(
        'opticaApp.Cliente',
        on_delete=models.CASCADE,
        related_name='solicitudes_convenio',
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='solicitudes_convenio',
    )
    contacto_verificador = models.ForeignKey(
        ContactoVerificadorConvenio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='solicitudes',
    )

    tipo_lente = models.ForeignKey(
        'opticaApp.TipoLente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='solicitudes_convenio',
    )
    producto = models.ForeignKey(
        'opticaApp.ProductoLente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='solicitudes_convenio',
    )
    marco_personalizado = models.TextField(blank=True, default='')
    filtro_azul = models.BooleanField(default=False)
    receta = models.FileField(upload_to='convenios/recetas/', blank=True)
    documento_acreditacion = models.FileField(upload_to='convenios/acreditaciones/', blank=True)
    codigo_beneficiario_declarado = models.CharField(max_length=60, blank=True)
    detalle_beneficio = models.TextField(blank=True)

    estado_acreditacion = models.CharField(
        max_length=30,
        choices=ESTADOS_ACREDITACION,
        default='recibida',
    )
    validada_automaticamente = models.BooleanField(default=False)
    motivo_acreditacion = models.TextField(blank=True)

    estado = models.CharField(
        max_length=30,
        choices=ESTADOS_SOLICITUD,
        default='recibida',
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    fecha_entrega = models.DateTimeField(null=True, blank=True)
    entregada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='entregas_convenio',
    )
    receptor_nombre = models.CharField(max_length=150, blank=True)
    observacion_entrega = models.TextField(blank=True)

    class Meta:
        ordering = ['-fecha_creacion']
        permissions = [
            ('validate_solicitudconvenio', 'Puede gestionar verificación de convenios'),
            ('authorize_solicitudconvenio', 'Puede autorizar beneficios de convenios'),
            ('deliver_solicitudconvenio', 'Puede registrar entrega de convenios'),
        ]

    def puede_transicionar_a(self, nuevo_estado):
        if nuevo_estado == self.estado:
            return False
        permitidos = self.TRANSICIONES_VALIDAS.get(self.estado, [])
        if nuevo_estado not in permitidos:
            return False
        if nuevo_estado == 'entregada':
            autorizacion = getattr(self, 'autorizacion', None)
            if not autorizacion or autorizacion.estado != 'autorizada':
                return False
            if autorizacion.esta_vencida:
                return False
        return True

    def transicionar_a(self, nuevo_estado, usuario=None, comentario='', nuevo_estado_acreditacion=None, evento='cambio_estado'):
        if not self.puede_transicionar_a(nuevo_estado):
            raise ValidationError(
                f'Transición no permitida de "{self.get_estado_display()}" a '
                f'"{dict(self.ESTADOS_SOLICITUD).get(nuevo_estado, nuevo_estado)}".'
            )
        estado_anterior = self.estado
        self.estado = nuevo_estado
        if nuevo_estado_acreditacion:
            self.estado_acreditacion = nuevo_estado_acreditacion
        elif nuevo_estado == 'verificacion_confirmada':
            self.estado_acreditacion = 'validada'
        elif nuevo_estado == 'verificacion_no_disponible':
            self.estado_acreditacion = 'no_verificable'
        elif nuevo_estado == 'rechazada':
            self.estado_acreditacion = 'rechazada'
        elif nuevo_estado == 'autorizada':
            self.estado_acreditacion = 'beneficio_autorizado'
        elif nuevo_estado == 'entregada':
            self.estado_acreditacion = 'beneficio_utilizado'
        self.save()

        HistorialSolicitudConvenio.objects.create(
            solicitud=self,
            evento=evento,
            estado_anterior=estado_anterior,
            estado_nuevo=nuevo_estado,
            acreditacion_estado=self.estado_acreditacion,
            usuario=usuario if (usuario and getattr(usuario, 'is_authenticated', False)) else None,
            comentario=comentario,
        )

    @property
    def indice_paso(self):
        if self.estado == 'pendiente_verificacion':
            return 1
        orden = {clave: idx for idx, (clave, _) in enumerate(self.PASOS_SEGUIMIENTO)}
        return orden.get(self.estado, -1)

    @property
    def verificacion_actual(self):
        return self.verificaciones.order_by('-fecha_creacion').first()

    def __str__(self):
        return f'{self.codigo} - {self.cliente.nombre} ({self.convenio.nombre})'


class VerificacionExternaConvenio(models.Model):
    ESTADOS = [
        ('pendiente_envio', 'Pendiente de envío'),
        ('enviada', 'Enviada'),
        ('pendiente_respuesta', 'Pendiente de respuesta'),
        ('confirmada', 'Confirmada'),
        ('rechazada', 'Rechazada'),
        ('no_verificable', 'No fue posible verificar'),
        ('expirada', 'Expirada'),
        ('cancelada', 'Cancelada'),
    ]

    RESULTADOS = [
        ('', 'Sin respuesta'),
        ('confirmada', 'Pertenencia confirmada'),
        ('rechazada', 'Pertenencia rechazada'),
        ('no_verificable', 'No fue posible verificar'),
    ]

    codigo_verificacion = models.CharField(
        max_length=20,
        unique=True,
        default=generar_codigo_verificacion,
    )
    solicitud = models.ForeignKey(
        SolicitudConvenio,
        on_delete=models.CASCADE,
        related_name='verificaciones',
    )
    convenio = models.ForeignKey(
        Convenio,
        on_delete=models.PROTECT,
        related_name='verificaciones',
    )
    beneficiario = models.ForeignKey(
        'opticaApp.Cliente',
        on_delete=models.CASCADE,
        related_name='verificaciones_convenio',
    )
    contacto_verificador = models.ForeignKey(
        ContactoVerificadorConvenio,
        on_delete=models.PROTECT,
        related_name='verificaciones',
    )
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)

    estado = models.CharField(max_length=30, choices=ESTADOS, default='pendiente_envio')
    resultado = models.CharField(max_length=30, choices=RESULTADOS, blank=True, default='')
    comentario_verificador = models.TextField(blank=True)

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_envio = models.DateTimeField(null=True, blank=True)
    fecha_expiracion = models.DateTimeField()
    fecha_respuesta = models.DateTimeField(null=True, blank=True)

    intentos_acceso = models.PositiveIntegerField(default=0)
    enviada_por_correo = models.BooleanField(default=False)
    error_envio = models.TextField(blank=True)
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verificaciones_creadas',
    )

    class Meta:
        ordering = ['-fecha_creacion']

    @property
    def esta_expirada(self):
        if self.estado == 'expirada':
            return True
        return self.fecha_expiracion and timezone.now() > self.fecha_expiracion

    @property
    def es_respondible(self):
        return self.estado in ('pendiente_envio', 'enviada', 'pendiente_respuesta') and not self.esta_expirada

    def __str__(self):
        return f'{self.codigo_verificacion} · {self.solicitud.codigo} ({self.get_estado_display()})'


class AutorizacionConvenio(models.Model):
    ESTADOS = [
        ('autorizada', 'Autorizada'),
        ('utilizada', 'Utilizada'),
        ('anulada', 'Anulada'),
        ('vencida', 'Vencida'),
    ]

    codigo_autorizacion = models.CharField(
        max_length=20,
        unique=True,
        default=generar_codigo_autorizacion,
    )
    qr_token = models.CharField(
        max_length=64,
        unique=True,
        default=generar_qr_token,
        editable=False,
    )
    solicitud = models.OneToOneField(
        SolicitudConvenio,
        on_delete=models.CASCADE,
        related_name='autorizacion',
    )
    beneficiario = models.ForeignKey(
        'opticaApp.Cliente',
        on_delete=models.CASCADE,
        related_name='autorizaciones_convenio',
    )
    convenio = models.ForeignKey(
        Convenio,
        on_delete=models.PROTECT,
        related_name='autorizaciones',
    )
    fecha_autorizacion = models.DateTimeField(auto_now_add=True)
    vigencia_hasta = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='autorizada')
    autorizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='autorizaciones_emitidas',
    )
    fecha_utilizacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-fecha_autorizacion']

    @property
    def esta_vencida(self):
        if self.vigencia_hasta and timezone.localdate() > self.vigencia_hasta:
            return True
        return self.estado == 'vencida'

    def save(self, *args, **kwargs):
        if not self.vigencia_hasta and self.convenio_id and self.convenio.vigencia_autorizacion_dias:
            self.vigencia_hasta = timezone.localdate() + timedelta(days=self.convenio.vigencia_autorizacion_dias)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.codigo_autorizacion} ({self.get_estado_display()})'


class HistorialSolicitudConvenio(models.Model):
    solicitud = models.ForeignKey(
        SolicitudConvenio,
        on_delete=models.CASCADE,
        related_name='historial',
    )
    evento = models.CharField(max_length=50, default='cambio_estado')
    estado_anterior = models.CharField(max_length=30, blank=True)
    estado_nuevo = models.CharField(max_length=30, blank=True)
    acreditacion_estado = models.CharField(max_length=30, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    comentario = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']

    def get_estado_nuevo_display(self):
        return dict(SolicitudConvenio.ESTADOS_SOLICITUD).get(self.estado_nuevo, self.estado_nuevo)

    def get_estado_anterior_display(self):
        return dict(SolicitudConvenio.ESTADOS_SOLICITUD).get(self.estado_anterior, self.estado_anterior)

    def __str__(self):
        return f'{self.solicitud.codigo}: {self.evento}'


class NotificacionConvenio(models.Model):
    solicitud = models.ForeignKey(
        SolicitudConvenio,
        on_delete=models.CASCADE,
        related_name='notificaciones',
    )
    cliente = models.ForeignKey(
        'opticaApp.Cliente',
        on_delete=models.CASCADE,
        related_name='notificaciones_convenio',
    )
    evento = models.CharField(max_length=40)
    titulo = models.CharField(max_length=150)
    mensaje = models.TextField()
    leida = models.BooleanField(default=False)
    enviada_email = models.BooleanField(default=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f'{self.titulo} ({self.solicitud.codigo})'
