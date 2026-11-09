from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from opticaApp.views import *
from django.contrib.auth.views import LogoutView # vista que django ya trae, cierra sesion del usuario sin programar nada, esto es para admin.

urlpatterns = [
    path('admin/', admin.site.urls),

    # Cliente (no necesita iniciar sesión, o yo creo q es lo mejor xq si no el meo show xdxd)
    path('', inicio, name='inicio'),
    path('solicitar/', solicitar, name='solicitar'),                                     # HU08
    path('solicitar/<int:producto_id>/', solicitar, name='solicitar_producto'),            
    path('solicitar/listo/<str:folio>/', solicitud_creada, name='solicitud_creada'),
    path('estado/', consultar_estado, name='consultar_estado'),                          # HU06
    path('catalogo/',catalogo, name='catalogo'),
    path('pedir-hora/', pedir_hora, name='pedir_hora'), #<- pedir hora
    path('pedir-hora/listo/<int:idCita>/', cita_creada, name='cita_creada'), #<- pedir hora

    # Personal (pide iniciar sesión)
    path('panel/', lista_solicitudes, name='lista_solicitudes'),                         # HU03
    path('panel/<int:idSolicitud>/', detalle_solicitud, name='detalle_solicitud'),
    path('salir/', LogoutView.as_view(), name = 'salir') #cuando alguien entre a la direccion, django ejecuta la vista salir.
]

# Esto permite abrir las recetas subidas mientras se trabaja en el computador, O algo asi me explico el gepeto
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
