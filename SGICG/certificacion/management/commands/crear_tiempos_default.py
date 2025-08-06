# certificacion/management/commands/crear_tiempos_default.py
from django.core.management.base import BaseCommand
from certificacion.models import ConfiguracionTiempos
from decimal import Decimal

class Command(BaseCommand):
    help = 'Crea o actualiza todas las combinaciones de configuración de tiempos con valores por defecto.'

    def handle(self, *args, **options):
        # ESTA LÍNEA ES LA CLAVE: BORRA TODO LO VIEJO Y CORRUPTO
        self.stdout.write(self.style.WARNING("Limpiando todas las configuraciones de tiempo existentes..."))
        ConfiguracionTiempos.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("¡Limpieza completada!"))

        self.stdout.write("--- Creando nuevas configuraciones de tiempo por defecto ---")
        
        tipos_item = [choice[0] for choice in ConfiguracionTiempos.TIPO_ITEM_CHOICES]
        tipos_cert = [choice[0] for choice in ConfiguracionTiempos.TIPO_CERT_CHOICES]

        created_count = 0
        
        for item_key in tipos_item:
            for cert_key in tipos_cert:
                # Ahora solo necesitamos 'create', ya que borramos todo antes
                ConfiguracionTiempos.objects.create(
                    tipo_item=item_key,
                    tipo_certificado=cert_key,
                    tiempo_ingreso=Decimal('1.0'),        # 8 horas
                    tiempo_fotografia=Decimal('1.0'),     # 4 horas
                    tiempo_revision=Decimal('1.0'),      # 24 horas
                    tiempo_impresion=Decimal('1.0'),      # 2 horas
                )
                created_count += 1
                self.stdout.write(f" -> CREADO: {item_key} - {cert_key}")
        
        self.stdout.write(self.style.SUCCESS(f'--- Proceso finalizado. Se crearon {created_count} configuraciones. ---'))
