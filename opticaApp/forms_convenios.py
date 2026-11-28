from django import forms
from django.utils.text import slugify

from opticaApp.forms import rut_valido
from opticaApp.models import ProductoLente, TipoLente
from opticaApp.models_convenios import (
    BeneficiarioPadronConvenio,
    ContactoVerificadorConvenio,
    Convenio,
    SolicitudConvenio,
)


class SolicitudConvenioForm(forms.Form):
    CONTACTOS = [('WhatsApp', 'WhatsApp'), ('Llamada', 'Llamada'), ('Correo', 'Correo')]

    rut = forms.CharField(
        label='RUT',
        max_length=12,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12.345.678-9'}),
        error_messages={'required': 'Escribe tu RUT.'},
    )
    nombre = forms.CharField(
        label='Nombre y apellidos',
        max_length=120,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Como aparece en tu cédula'}),
        error_messages={'required': 'Escribe tu nombre completo.'},
    )
    contacto = forms.ChoiceField(
        label='Medio de contacto preferido',
        choices=CONTACTOS,
        initial='WhatsApp',
        widget=forms.RadioSelect,
    )
    telefono = forms.CharField(
        label='Teléfono',
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+56 9 1234 5678'}),
    )
    email = forms.EmailField(
        label='Correo electrónico',
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'nombre@correo.cl'}),
        error_messages={
            'required': 'Escribe tu correo electrónico para enviarte tu código de seguimiento.',
            'invalid': 'Ingresa un correo electrónico válido.',
        },
    )

    contacto_verificador = forms.ModelChoiceField(
        label='Contacto verificador de tu institución',
        queryset=ContactoVerificadorConvenio.objects.none(),
        required=False,
        empty_label='Selecciona un contacto autorizado',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    tipo_lente = forms.ModelChoiceField(
        label='Tipo de lente',
        queryset=TipoLente.objects.all(),
        required=False,
        empty_label='Selecciona un tipo de lente',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    producto = forms.ModelChoiceField(
        label='Lente del catálogo',
        queryset=ProductoLente.objects.none(),
        required=False,
        empty_label='Selecciona un modelo disponible',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    marco_personalizado = forms.CharField(
        label='O describe el lente/marco que necesitas',
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Ej: Marco liviano negro, uso diario...',
        }),
    )
    filtro_azul = forms.BooleanField(label='Agregar filtro de luz azul', required=False)

    codigo_beneficiario_declarado = forms.CharField(
        label='N° de funcionario o ficha (opcional)',
        required=False,
        max_length=60,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: FUNC-4021'}),
    )
    receta = forms.FileField(
        label='Receta óptica',
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.jpg,.jpeg,.png,.pdf'}),
    )
    detalle_beneficio = forms.CharField(
        label='Observaciones adicionales',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Opcional'}),
    )
    acepta_datos = forms.BooleanField(
        label='Autorizo que Óptica Amaru utilice mis datos para gestionar y verificar mi solicitud de convenio.',
        error_messages={'required': 'Debes autorizar el tratamiento de tus datos para continuar.'},
    )

    def __init__(self, *args, convenio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.convenio = convenio
        if convenio:
            permitidos = convenio.productos_permitidos.filter(publicado=True)
            if permitidos.exists():
                self.fields['producto'].queryset = permitidos.order_by('nombre')
            else:
                self.fields['producto'].queryset = ProductoLente.objects.filter(publicado=True).order_by('nombre')

            contactos = convenio.contactos_verificadores.filter(activo=True).order_by('nombre')
            self.fields['contacto_verificador'].queryset = contactos
            if contactos.count() == 1:
                self.fields['contacto_verificador'].initial = contactos.first()
            elif contactos.count() > 1:
                self.fields['contacto_verificador'].required = True

            if not convenio.permite_marco_personalizado:
                self.fields['marco_personalizado'].widget = forms.HiddenInput()
            if convenio.requiere_receta:
                self.fields['receta'].required = True

    def clean_rut(self):
        rut = rut_valido(self.cleaned_data['rut'])
        if rut is None:
            raise forms.ValidationError('El RUT no es válido. Revisa el número y el dígito verificador.')
        return rut

    def clean_receta(self):
        receta = self.cleaned_data.get('receta')
        if receta:
            if not receta.name.lower().endswith(('.jpg', '.jpeg', '.png', '.pdf')):
                raise forms.ValidationError('La receta debe ser JPG, PNG o PDF.')
            if receta.size > 5 * 1024 * 1024:
                raise forms.ValidationError('La receta no puede superar los 5 MB.')
        return receta

    def clean(self):
        datos = super().clean()
        contacto = datos.get('contacto')
        if contacto == 'Correo' and not datos.get('email'):
            self.add_error('email', 'Indica tu correo electrónico para contactarte.')
        if contacto and contacto != 'Correo' and not datos.get('telefono'):
            self.add_error('telefono', 'Indica tu teléfono para contactarte.')

        producto = datos.get('producto')
        marco = (datos.get('marco_personalizado') or '').strip()
        if not producto and not marco:
            self.add_error('producto', 'Selecciona un producto del catálogo o describe el lente que buscas.')

        if self.convenio and self.convenio.max_solicitudes_por_beneficiario > 0 and datos.get('rut'):
            activas = SolicitudConvenio.objects.filter(
                convenio=self.convenio,
                cliente__rut=datos['rut'],
            ).exclude(estado__in=['rechazada', 'cancelada']).count()
            if activas >= self.convenio.max_solicitudes_por_beneficiario:
                self.add_error(
                    None,
                    'Ya registras el máximo de solicitudes permitidas para este convenio con este RUT.',
                )
        return datos


class ConsultaBeneficiarioConvenioForm(forms.Form):
    rut = forms.CharField(
        label='RUT del beneficiario',
        max_length=12,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12.345.678-9'}),
    )
    codigo = forms.CharField(
        label='Código de solicitud',
        max_length=16,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'CNV-XXXXXX'}),
    )

    def clean_rut(self):
        rut = rut_valido(self.cleaned_data['rut'])
        if rut is None:
            raise forms.ValidationError('RUT inválido.')
        return rut

    def clean_codigo(self):
        return self.cleaned_data['codigo'].strip().upper()


class ConvenioAdminForm(forms.ModelForm):
    class Meta:
        model = Convenio
        fields = [
            'nombre', 'slug', 'institucion', 'descripcion', 'activo',
            'fecha_inicio', 'fecha_termino', 'beneficios', 'condiciones_uso',
            'requisitos_acreditacion', 'restricciones', 'info_beneficiarios',
            'info_administrativa', 'productos_permitidos', 'permite_marco_personalizado',
            'requiere_receta', 'metodo_validacion', 'requiere_aprobacion_interna',
            'incluir_rut_en_correo_verificacion', 'dias_vigencia_verificacion',
            'max_solicitudes_por_beneficiario', 'vigencia_autorizacion_dias',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'slug': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Se genera automático si se deja vacío'}),
            'institucion': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'fecha_inicio': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_termino': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
            'beneficios': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'condiciones_uso': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'requisitos_acreditacion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'restricciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'info_beneficiarios': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'info_administrativa': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'productos_permitidos': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 4}),
            'metodo_validacion': forms.Select(attrs={'class': 'form-select'}),
            'dias_vigencia_verificacion': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'max_solicitudes_por_beneficiario': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'vigencia_autorizacion_dias': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False
        self.fields['productos_permitidos'].queryset = ProductoLente.objects.order_by('nombre')

    def clean_slug(self):
        slug = (self.cleaned_data.get('slug') or '').strip()
        if not slug:
            nombre = self.cleaned_data.get('nombre') or ''
            base = slugify(nombre) or 'convenio'
            slug = base
            contador = 1
            qs = Convenio.objects.all()
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            while qs.filter(slug=slug).exists():
                contador += 1
                slug = f'{base}-{contador}'
        return slug


class ContactoVerificadorForm(forms.ModelForm):
    class Meta:
        model = ContactoVerificadorConvenio
        fields = ['nombre', 'correo', 'empresa', 'cargo', 'metodo_confirmacion', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del responsable'}),
            'correo': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'rrhh@empresa.cl'}),
            'empresa': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Empresa o institución'}),
            'cargo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Jefatura RR.HH. / Bienestar'}),
            'metodo_confirmacion': forms.TextInput(attrs={'class': 'form-control'}),
        }


class BeneficiarioPadronForm(forms.ModelForm):
    class Meta:
        model = BeneficiarioPadronConvenio
        fields = ['rut', 'nombre_completo', 'codigo_interno', 'activo', 'fecha_vigencia_hasta', 'observacion']
        widgets = {
            'rut': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12.345.678-9'}),
            'nombre_completo': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo_interno': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Opcional'}),
            'fecha_vigencia_hasta': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
            'observacion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Opcional'}),
        }

    def clean_rut(self):
        rut = rut_valido(self.cleaned_data['rut'])
        if rut is None:
            raise forms.ValidationError('RUT inválido.')
        return rut
