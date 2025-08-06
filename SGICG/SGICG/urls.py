# SGICG/urls.py
from django.contrib import admin
from django.urls import path, include # <-- Asegúrate de que 'include' esté importado
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('certificacion.urls')), # <-- AÑADE ESTA LÍNEA
]

# AÑADE ESTAS LÍNEAS AL FINAL: para servir archivos en modo desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)