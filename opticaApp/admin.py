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

admin.site.register(TipoLente, TipoLenteAdmin)
admin.site.register(Estado, EstadoAdmin)
admin.site.register(Cliente, ClienteAdmin)
admin.site.register(Solicitud, SolicitudAdmin)
admin.site.register(ProductoLente, ProductoLenteAdmin)