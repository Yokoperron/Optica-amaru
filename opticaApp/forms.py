from django import forms
from opticaApp.models import *

from django.forms import modelformset_factory

from datetime import date ## <- esto es nuevo para la creacion del form de pedir hora ##



# Función de ayuda: revisa si un RUT es válido (el dígito verificador debe calzar).
# Devuelve el RUT ordenado ("16482915-4") o None si no es válido.

def rut_valido(rut):
    rut = rut.replace(".", "").replace("-", "").replace(" ", "").upper()
    if len(rut) < 8 or len(rut) > 9 or not rut[:-1].isdigit():
        return None
    cuerpo = rut[:-1]
    dv = rut[-1]

    # Método del módulo 11: se multiplica cada número, de derecha a izquierda, por 2,3,4,5,6,7,2,3...
    suma = 0
    multiplicador = 2
    for numero in reversed(cuerpo):
        suma += int(numero) * multiplicador
        multiplicador += 1
        if multiplicador == 8:
            multiplicador = 2

    resto = 11 - (suma % 11)
    if resto == 11:
        esperado = "0"
    elif resto == 10:
        esperado = "K"
    else:
        esperado = str(resto)

    if dv != esperado:
        return None
    return cuerpo + "-" + dv



# HU08: formulario para pedir lentes (pantalla y solicitar)
# Es un Form normal (no ModelForm) porque junta datos de DOS tablas: Cliente y Solicitud.
class SolicitudForm(forms.Form):
    CONTACTOS = [('WhatsApp', 'WhatsApp'), ('Llamada', 'Llamada'), ('Correo', 'Correo')]

    # --- Paso 1: datos del cliente ---
    rut = forms.CharField(
        label='RUT', max_length=12,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12.345.678-5'}),
        error_messages={'required': 'Escribe tu RUT.'})
    nombre = forms.CharField(
        label='Nombre completo', max_length=120,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Como aparece en tu carnet'}),
        error_messages={'required': 'Escribe tu nombre completo.'})
    contacto = forms.ChoiceField(
        label='¿Cómo prefieres que te contactemos?', choices=CONTACTOS, initial='WhatsApp',
        widget=forms.RadioSelect)
    telefono = forms.CharField(
        label='Teléfono', max_length=20, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+56 9 1234 5678'}))
    email = forms.EmailField(
        label='Correo electrónico', required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'nombre@correo.cl'}),
        error_messages={'invalid': 'Escribe un correo válido, por ejemplo nombre@correo.cl.'})
    
    ### --- PASO 1: datos del cliente direccion --- ###
    direccion = forms.CharField(
        max_length=200,
        label="Dirección",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: Av. Granaderos 1234'
        })
    )

    comuna = forms.CharField(
        max_length=100,
        label="Comuna",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: Calama'
        })
    )

    ciudad = forms.CharField(
        max_length=100,
        label="Ciudad",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: Calama'
        })
    )

    referencia = forms.CharField(
        max_length=200,
        required=False,
        label="Referencia",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: Casa azul, frente a la plaza'
        })
    )

    # ModelChoiceField = una lista que sale de una tabla (aquí, los registros de TipoLente)
    tipo = forms.ModelChoiceField(
        label='Tipo de lente', 
        queryset=TipoLente.objects.all(), 
        empty_label=None,
        widget=forms.RadioSelect,
        error_messages={'required': 'Elige qué tipo de lente necesitas.'})
    receta = forms.FileField(
        label='Receta', required=False,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.jpg,.jpeg,.png,.pdf'}))
    sin_receta = forms.BooleanField(label='No tengo receta vigente', required=False)
    filtro_azul = forms.BooleanField(label='Con filtro de luz azul', required=False)
    indicaciones = forms.CharField(
        label='Algo más que debamos saber', required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Opcional'}))

    # --- Paso 3: autorización ---
    acepta_datos = forms.BooleanField(
        label='Autorizo que Óptica Amaru trate mis datos personales y de salud para atender esta solicitud.',
        error_messages={'required': 'Necesitamos tu autorización para tratar tus datos y poder enviar la solicitud.'})

    # clean_<campo>: revisa un solo campo. Lo que devuelve es el valor "limpio" que se usará después.
    def clean_rut(self):
        rut = rut_valido(self.cleaned_data['rut'])
        if rut is None:
            raise forms.ValidationError('El RUT no es válido. Revisa el número y el dígito verificador.')
        return rut

    def clean_receta(self):
        receta = self.cleaned_data.get('receta')
        if receta:
            if not receta.name.lower().endswith(('.jpg', '.jpeg', '.png', '.pdf')):
                raise forms.ValidationError('La receta debe ser una foto JPG o PNG, o un PDF.')
            if receta.size > 5 * 1024 * 1024:
                raise forms.ValidationError('La receta pesa más de 5 MB. Sube una foto más liviana.')
        return receta

    # clean: revisa varios campos juntos (por ejemplo, si prefiere correo, el correo es obligatorio)
    def clean(self):
        datos = super().clean()
        contacto = datos.get('contacto')
        if contacto == 'Correo' and not datos.get('email'):
            self.add_error('email', 'Escribiste que prefieres el correo: necesitamos tu correo.')
        if contacto and contacto != 'Correo' and not datos.get('telefono'):
            self.add_error('telefono', 'Necesitamos un teléfono para contactarte.')
        if not datos.get('receta') and not datos.get('sin_receta') and 'receta' not in self.errors:
            self.add_error('receta', 'Adjunta tu receta o marca que no tienes una vigente.')
        return datos



# HU06: formulario para consultar el estado (pantalla /estado/)

class ConsultaForm(forms.Form):
    rut = forms.CharField(
        label='RUT', max_length=12,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12.345.678-5'}))
    folio = forms.CharField(
        label='Código de seguimiento', max_length=12,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'AMR-4F7K2Q'}))


# HU03: formulario del personal para cambiar el estado de una solicitud.
# Este sí es un ModelForm: se arma solo desde la tabla Solicitud. Solo editamos el campo "estado".
class EstadoForm(forms.ModelForm):
    class Meta:
        model = Solicitud
        fields = ['estado']
        widgets = {'estado': forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Los estados se muestran en su orden (Recibida, En revisión, En taller...)
        self.fields['estado'].queryset = Estado.objects.order_by('orden')


class HorarioForm(forms.ModelForm):
    class Meta:
        model = HorarioAtencion
        fields = ['dia', 'hora_inicio', 'hora_fin', 'duracion_min', 'activo']
        widgets = {
            'dia': forms.Select(attrs={'class': 'form-select'}),
            'hora_inicio': forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'class': 'form-control'}),
            'hora_fin': forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'class': 'form-control'}),
            'duracion_min': forms.NumberInput(attrs={'class': 'form-control', 'min': 10}),
        }

# Un formset es "varios formularios iguales juntos": uno por cada bloque del horario
HorarioFormSet = modelformset_factory(HorarioAtencion, form=HorarioForm, extra=1, can_delete=True)



## DE AQUI HACIA ABAJO ESTA TODO EN RELACION A PEDIR UNA HORA!


class CitaForm(forms.Form):

    rut = forms.CharField(
        label='RUT',
        max_length=10,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '12.345.678-9'
        })
    )

    nombre = forms.CharField(
        label='Nombre completo',
        max_length=120,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Tu nombre completo'
        })
    )

    telefono = forms.CharField(
        label='Teléfono',
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+56 9 1234 5678'
        })
    )

    email = forms.EmailField(
        label='Correo electrónico',
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'correo@ejemplo.cl'
        })
    )

    contacto = forms.CharField(
        label='Medio de contacto',
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'WhatsApp, llamada o correo'
        })
    )

    motivo = forms.CharField(
        label='Motivo de la atención',
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control'
        })
    )

    fecha = forms.DateField(
        label='Fecha de atención',
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )

    hora = forms.TimeField(
        label='Hora de atención',
        input_formats=['%H:%M'],
        widget=forms.TimeInput(attrs={
            'class': 'form-control',
            'type': 'time',
            'min': '09:00',
            'max': '17:00',
            'step': '1800'
        })
    )

    acepta_datos = forms.BooleanField(
        label='Acepto el tratamiento de mis datos personales para gestionar mi reserva',
        required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['fecha'].widget.attrs['min'] = date.today().isoformat()

    def clean_fecha(self):
        fecha = self.cleaned_data['fecha']

        if fecha < date.today():
            raise forms.ValidationError(
                'No puedes seleccionar una fecha anterior a hoy.'
            )

        if fecha.weekday() >= 5:
            raise forms.ValidationError(
                'Las reservas solamente están disponibles de lunes a viernes.'
            )

        return fecha

    def clean_hora(self):
        hora = self.cleaned_data['hora']

        if hora.hour < 9 or hora.hour >= 17:
            raise forms.ValidationError(
                'Selecciona una hora entre las 09:00 y las 17:00.'
            )

        return hora


    def clean(self):
        datos = super().clean()

        if datos.get('contacto') == 'Correo' and not datos.get('email'):
            self.add_error(
                'email',
                'Debes ingresar tu correo electronico.'
            )
        return datos

