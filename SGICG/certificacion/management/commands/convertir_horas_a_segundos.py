# certificacion/management/commands/convertir_horas_a_segundos.py
from django.core.management.base import BaseCommand
from django.db.models import F
from certificacion.models import ConfiguracionTiempos

class Command(BaseCommand):
    help = 'Convierte los valores de tiempo de horas a segundos (valor * 3600).'

    def handle(self, *args, **options):
        self.stdout.write('Iniciando conversión de horas a segundos...')
        # Asumimos que los valores son numéricos.
        # El filtro evita errores si algún campo es nulo.
        ConfiguracionTiempos.objects.exclude(tiempo_ingreso=None).update(tiempo_ingreso=F('tiempo_ingreso') * 3600)
        ConfiguracionTiempos.objects.exclude(tiempo_fotografia=None).update(tiempo_fotografia=F('tiempo_fotografia') * 3600)
        ConfiguracionTiempos.objects.exclude(tiempo_revision=None).update(tiempo_revision=F('tiempo_revision') * 3600)
        ConfiguracionTiempos.objects.exclude(tiempo_impresion=None).update(tiempo_impresion=F('tiempo_impresion') * 3600)
        self.stdout.write(self.style.SUCCESS('¡Conversión completada!'))