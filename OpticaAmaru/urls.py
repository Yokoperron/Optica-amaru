from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from opticaApp.views import *
from opticaApp.views_convenios import *
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
    path('panel/cita/<int:idCita>/estado/',actualizar_estado_cita,name='actualizar_estado_cita'),
    path('panel/calendario/', calendario_admin, name='calendario_admin'),
    path('panel/api/citas/', api_citas, name='api_citas'),
    path('panel/api/citas/crear/', api_crear_cita, name='api_crear_cita'),
    path('panel/api/horarios/', api_guardar_horario, name='api_guardar_horario'),
    path('panel/api/horarios/<int:idHorario>/', api_eliminar_horario, name='api_eliminar_horario'),
    path('panel/api/citas/<int:idCita>/', api_actualizar_cita, name='api_actualizar_cita'),
    path('panel/agregar-lente/',agregar_lente,name='agregar_lente'),
    path('cancelar-hora',buscar_cita_cancelacion,name='buscar_cita_cancelacion'),

    # Personal (pide iniciar sesión)
    path('panel/', lista_solicitudes, name='lista_solicitudes'),                         # HU03
    path('panel/<int:idSolicitud>/', detalle_solicitud, name='detalle_solicitud'),
    path('salir/', LogoutView.as_view(), name = 'salir'), #cuando alguien entre a la direccion, django ejecuta la vista salir.
    path('panel/horario/', editar_horario, name='editar_horario'),
    path('pago/<str:folio>/',pagar_solicitud,name='pagar_solicitud'),
    path('panel/pago/<int:idPago>/revisar/',revisar_pago,name='revisar_pago'),
    path('panel/banners',administrar_banners, name='administrar_banners'),

    # Módulo de Convenios Digitales (público, verificación externa y beneficiario)
    path('convenios/', convenios_publico, name='convenios_publico'),
    path('convenios/verificar/<str:raw_token>/', verificacion_externa_responder, name='verificacion_externa_responder'),
    path('convenios/mis-solicitudes/', portal_beneficiario, name='portal_beneficiario'),
    path('convenios/mis-solicitudes/salir/', salir_portal_beneficiario, name='salir_portal_beneficiario'),
    path('convenios/mis-solicitudes/<str:codigo>/', detalle_beneficiario_convenio, name='detalle_beneficiario_convenio'),
    path('convenios/solicitud/<str:codigo>/listo/', convenio_solicitud_creada, name='convenio_solicitud_creada'),
    path('convenios/<slug:slug>/solicitar/', solicitar_convenio, name='solicitar_convenio'),

    # Módulo de Convenios Digitales (personal y retiros)
    path('panel/convenios/', panel_convenios_dashboard, name='panel_convenios_dashboard'),
    path('panel/convenios/gestion/', panel_convenios_lista, name='panel_convenios_lista'),
    path('panel/convenios/gestion/nuevo/', panel_convenio_crear, name='panel_convenio_crear'),
    path('panel/convenios/gestion/<int:idConvenio>/editar/', panel_convenio_editar, name='panel_convenio_editar'),
    path('panel/convenios/gestion/<int:idConvenio>/toggle/', panel_convenio_toggle, name='panel_convenio_toggle'),
    path('panel/convenios/gestion/<int:idConvenio>/contactos/', panel_convenio_contactos, name='panel_convenio_contactos'),
    path('panel/convenios/gestion/<int:idConvenio>/padron/', panel_convenio_padron, name='panel_convenio_padron'),
    path('panel/convenios/solicitudes/<int:idSolicitudConvenio>/', panel_convenio_solicitud_detalle, name='panel_convenio_solicitud_detalle'),
    path('panel/convenios/retiros/', panel_convenios_retiros, name='panel_convenios_retiros'),
    path('panel/convenios/qr/<str:qr_token>/', panel_convenios_verificar_qr, name='panel_convenios_verificar_qr'),
]

# Esto permite abrir las recetas subidas mientras se trabaja en el computador, O algo asi me explico el gepeto
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
