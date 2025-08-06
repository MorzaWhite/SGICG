# certificacion/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('orden/nueva/', views.CrearOrdenView.as_view(), name='crear_orden'),
    path('orden/creada/<int:orden_id>/', views.orden_creada_exito, name='orden_creada_exito'),
    path('orden/<int:orden_id>/', views.detalle_orden, name='detalle_orden'),
    path('item/<int:item_id>/asignar_excel/', views.asignar_excel, name='asignar_excel'),
    path('etapa/<str:etapa>/', views.vista_por_etapa, name='vista_etapa'),
    path('orden/<int:orden_id>/avanzar/', views.avanzar_etapa, name='avanzar_etapa'),
    path('configuracion/', views.configuracion_tiempos, name='configuracion_tiempos'),
]