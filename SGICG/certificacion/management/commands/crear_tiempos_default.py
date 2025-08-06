# certificacion/management/commands/crear_tiempos_default.py
from django.core.management.base import BaseCommand
from certificacion.models import ConfiguracionTiempos
from decimal import Decimal

class Command(BaseCommand):
    help = 'Crea o actualiza todas las combinaciones de configuración de tiempos con valores por defecto.'

    def handle(self, *args, **options):
        self.stdout.write("--- Iniciando sincronización de configuraciones de tiempo ---")
        
        # Obtenemos las opciones directamente del modelo para mantener la consistencia
        tipos_item = [choice[0] for choice in ConfiguracionTiempos.TIPO_ITEM_CHOICES]
        tipos_cert = [choice[0] for choice in ConfiguracionTiempos.TIPO_CERT_CHOICES]

        created_count = 0
        updated_count = 0

        for item_key in tipos_item:
            for cert_key in tipos_cert:
                # Usamos update_or_create: si existe, lo actualiza; si no, lo crea.
                # Esto asegura que los valores por defecto siempre estén correctos.
                obj, created = ConfiguracionTiempos.objects.update_or_create(
                    tipo_item=item_key,
                    tipo_certificado=cert_key,
                    defaults={
                        'tiempo_ingreso': Decimal('480.0'),
                        'tiempo_fotografia': Decimal('240.0'),
                        'tiempo_revision': Decimal('1440.0'),
                        'tiempo_impresion': Decimal('120.0'),
                    }
                )
                if created:
                    created_count += 1
                    self.stdout.write(f" -> CREADO: {item_key} - {cert_key}")
                else:
                    updated_count += 1
        
        self.stdout.write(self.style.SUCCESS(f'--- Sincronización finalizada ---'))
        self.stdout.write(f'Se crearon {created_count} nuevas configuraciones.')
        self.stdout.write(f'Se verificaron y actualizaron {updated_count} configuraciones existentes.')