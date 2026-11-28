from django.contrib import admin
from opticaApp.models import *



class TipoLenteAdmin(admin.ModelAdmin):
    list_display = ('idTipoLente', 'nombre')

class EstadoAdmin(admin.ModelAdmin):
    list_display = ('idEstado', 'nombre', 'orden')

class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'rut', 'contacto', 'telefono', 'email', 'acepta_datos')

class SolicitudAdmin(admin.ModelAdmin):
    list_display = ('folio', 'cliente', 'tipo', 'estado', 'fecha_creacion', 'fecha_entrega')

class ProductoLenteAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'marca', 'precio', 'stock', 'publicado')
    list_filter = ('marca', 'publicado')
    search_fields = ('nombre', 'marca')
    list_editable = ('precio', 'stock', 'publicado')

# horario atencion del administrador
class HorarioAtencionAdmin(admin.ModelAdmin):
    list_display = ('dia', 'hora_inicio', 'hora_fin', 'duracion_min', 'activo')
    list_editable = ('hora_inicio', 'hora_fin', 'duracion_min', 'activo')



class CitaAdmin(admin.ModelAdmin):
    list_display = ('idCita', 'cliente', 'fecha', 'hora', 'motivo', 'estado', 'fecha_creacion')
    list_filter = ('estado', 'fecha')
    search_fields = ('cliente__nombre', 'cliente__rut', 'motivo')
    list_editable = ('estado',)
    ordering = ('fecha', 'hora')

admin.site.register(TipoLente, TipoLenteAdmin)
admin.site.register(Estado, EstadoAdmin)
admin.site.register(Cliente, ClienteAdmin)
admin.site.register(Solicitud, SolicitudAdmin)
admin.site.register(ProductoLente, ProductoLenteAdmin)


admin.site.register(HorarioAtencion, HorarioAtencionAdmin)

admin.site.register(Cita, CitaAdmin)

@admin.register(DatosBancarios)
class DatosBancariosAdmin(admin.ModelAdmin):
    list_display = (
        'banco',
        'titular',
        'tipo_cuenta',
        'numero_cuenta',
        'activo'
    )

    list_filter = ('banco', 'activo')
    search_fields = ('titular', 'rut', 'numero_cuenta')


@admin.register(Convenio)
class ConvenioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'institucion', 'metodo_validacion', 'activo', 'fecha_inicio', 'fecha_termino')
    list_filter = ('activo', 'metodo_validacion')
    search_fields = ('nombre', 'institucion', 'slug')
    prepopulated_fields = {'slug': ('nombre',)}


@admin.register(ContactoVerificadorConvenio)
class ContactoVerificadorConvenioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'correo', 'convenio', 'empresa', 'cargo', 'activo')
    list_filter = ('activo', 'convenio')
    search_fields = ('nombre', 'correo', 'empresa')


@admin.register(VerificacionExternaConvenio)
class VerificacionExternaConvenioAdmin(admin.ModelAdmin):
    list_display = ('codigo_verificacion', 'solicitud', 'contacto_verificador', 'estado', 'fecha_envio', 'fecha_expiracion')
    list_filter = ('estado', 'convenio')
    search_fields = ('codigo_verificacion', 'solicitud__codigo', 'contacto_verificador__correo')


@admin.register(BeneficiarioPadronConvenio)
class BeneficiarioPadronConvenioAdmin(admin.ModelAdmin):
    list_display = ('nombre_completo', 'rut', 'convenio', 'codigo_interno', 'activo', 'fecha_vigencia_hasta')
    list_filter = ('convenio', 'activo')
    search_fields = ('nombre_completo', 'rut', 'codigo_interno')


@admin.register(SolicitudConvenio)
class SolicitudConvenioAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'convenio', 'cliente', 'estado', 'estado_acreditacion', 'fecha_creacion')
    list_filter = ('estado', 'estado_acreditacion', 'convenio')
    search_fields = ('codigo', 'cliente__nombre', 'cliente__rut')


@admin.register(AutorizacionConvenio)
class AutorizacionConvenioAdmin(admin.ModelAdmin):
    list_display = ('codigo_autorizacion', 'convenio', 'beneficiario', 'estado', 'fecha_autorizacion', 'vigencia_hasta')
    list_filter = ('estado', 'convenio')
    search_fields = ('codigo_autorizacion', 'beneficiario__nombre', 'beneficiario__rut')


@admin.register(NotificacionConvenio)
class NotificacionConvenioAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'solicitud', 'leida', 'enviada_email', 'fecha_creacion')
    list_filter = ('leida', 'enviada_email')