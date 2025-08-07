# certificacion/management/commands/crear_tiempos_default.py
from django.core.management.base import BaseCommand, CommandError
from certificacion.models import ConfiguracionTiempos
from django.db import transaction

class Command(BaseCommand):
    help = 'Crea o actualiza todas las combinaciones de configuración de tiempos con valores por defecto.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Elimina todas las configuraciones existentes antes de crear nuevas',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra lo que se haría sin hacer cambios',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        reset = options['reset']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('MODO DRY-RUN: No se harán cambios reales')
            )
        
        try:
            with transaction.atomic():
                # Limpiar configuraciones existentes si se solicita
                if reset:
                    count_existing = ConfiguracionTiempos.objects.count()
                    if dry_run:
                        self.stdout.write(f"Se eliminarían {count_existing} configuraciones existentes")
                    else:
                        ConfiguracionTiempos.objects.all().delete()
                        self.stdout.write(
                            self.style.WARNING(f"Eliminadas {count_existing} configuraciones existentes")
                        )
                
                # Obtener todas las combinaciones posibles
                tipos_item = [choice[0] for choice in ConfiguracionTiempos.TIPO_ITEM_CHOICES]
                tipos_cert = [choice[0] for choice in ConfiguracionTiempos.TIPO_CERT_CHOICES]
                
                created_count = 0
                updated_count = 0
                
                # Tiempos por defecto en segundos
                # INGRESO: 1 hora, FOTOGRAFIA: 2 horas, REVISION: 8 horas, IMPRESION: 1 hora
                default_times = {
                    'tiempo_ingreso': 3600,      # 1 hora
                    'tiempo_fotografia': 7200,   # 2 horas
                    'tiempo_revision': 28800,    # 8 horas
                    'tiempo_impresion': 3600,    # 1 hora
                }
                
                for item_key in tipos_item:
                    for cert_key in tipos_cert:
                        # Ajustar tiempos según el tipo
                        tiempos = default_times.copy()
                        
                        # Certificados más complejos toman más tiempo
                        if cert_key == 'GC_COMPLETA':
                            tiempos['tiempo_revision'] = 43200  # 12 horas
                            tiempos['tiempo_impresion'] = 7200  # 2 horas
                        elif cert_key == 'DIAMANTE':
                            tiempos['tiempo_revision'] = 57600  # 16 horas
                            tiempos['tiempo_fotografia'] = 10800  # 3 horas
                            tiempos['tiempo_impresion'] = 7200  # 2 horas
                        elif cert_key == 'ESCRITO':
                            tiempos['tiempo_revision'] = 21600  # 6 horas
                        
                        # Items más complejos toman más tiempo
                        if item_key == 'SET':
                            tiempos['tiempo_fotografia'] = 14400  # 4 horas
                            tiempos['tiempo_revision'] = int(tiempos['tiempo_revision'] * 1.5)
                        elif item_key == 'LOTE':
                            tiempos['tiempo_ingreso'] = 7200  # 2 horas
                            tiempos['tiempo_revision'] = int(tiempos['tiempo_revision'] * 1.2)
                        
                        if dry_run:
                            self.stdout.write(f"Crearía/actualizaría: {item_key} - {cert_key}")
                            continue
                        
                        # Crear o actualizar configuración
                        config, created = ConfiguracionTiempos.objects.get_or_create(
                            tipo_item=item_key,
                            tipo_certificado=cert_key,
                            defaults=tiempos
                        )
                        
                        if created:
                            created_count += 1
                            self.stdout.write(f" -> CREADO: {item_key} - {cert_key}")
                        else:
                            # Actualizar solo si los valores son None
                            updated = False
                            for field, value in tiempos.items():
                                if getattr(config, field) is None:
                                    setattr(config, field, value)
                                    updated = True
                            
                            if updated:
                                config.save()
                                updated_count += 1
                                self.stdout.write(f" -> ACTUALIZADO: {item_key} - {cert_key}")
                            else:
                                self.stdout.write(f" -> EXISTE: {item_key} - {cert_key}")
                
                if not dry_run:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Proceso completado. Creados: {created_count}, Actualizados: {updated_count}'
                        )
                    )
                else:
                    total_combinations = len(tipos_item) * len(tipos_cert)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'DRY-RUN completado. Se procesarían {total_combinations} configuraciones.'
                        )
                    )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error durante la ejecución: {str(e)}')
            )
            raise CommandError(f'Error: {str(e)}')