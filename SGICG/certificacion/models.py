# certificacion/models.py
from django.db import models
from django.conf import settings
from pathlib import Path
import os

def get_qr_upload_path(instance, filename):
    orden_folder = f"ORDEN-{instance.orden.id:04d}"; item_folder = f"ITEM-{instance.numero_item}"
    return os.path.join(orden_folder, item_folder, filename)

def get_foto_upload_path(instance, filename):
    orden_folder = f"ORDEN-{instance.item.orden.id:04d}"; item_folder = f"ITEM-{instance.item.numero_item}"
    return os.path.join(orden_folder, item_folder, filename)

class Orden(models.Model):
    ETAPAS = [('INGRESO', 'Ingreso'), ('FOTOGRAFIA', 'Fotografía'), ('REVISION', 'Revisión'), ('IMPRESION', 'Impresión'), ('FINALIZADA', 'Finalizada')]
    numero_orden_facturacion = models.CharField(max_length=100, unique=True, verbose_name="Número de Orden (Facturación)")
    estado_actual = models.CharField(max_length=20, choices=ETAPAS, default='INGRESO')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(blank=True, null=True)
    def __str__(self): return f"Orden {self.id} - {self.numero_orden_facturacion}"
    def get_proxima_etapa(self):
        etapas = [e[0] for e in self.ETAPAS];
        try: idx = etapas.index(self.estado_actual)
        except ValueError: return None
        if idx < len(etapas) - 1: return etapas[idx + 1]
        return None

class Item(models.Model):
    TIPO_CERT_CHOICES = [('GC_SENCILLA', 'GC Sencilla'), ('GC_COMPLETA', 'GC Completa'), ('ESCRITO', 'Escrito'), ('DIAMANTE', 'Diamante')]
    QUE_ES_CHOICES = [('JOYA', 'Joya'), ('LOTE', 'Lote de Gemas'), ('PIEDRA', 'Piedra(s) Suelta(s)'), ('VERBAL_A_GC', 'Verbal a GC'), ('REIMPRESION', 'Reimpresión')]
    TIPO_JOYA_CHOICES = [('ANILLO', 'Anillo'), ('DIJE', 'Dije'), ('TOPOS', 'Topos'), ('PULSERA', 'Pulsera'), ('PULSERA_TENIS', 'Pulsera Tenis'), ('SET', 'Set')]
    METAL_CHOICES = [('ORO', 'Oro'), ('ORO_AMARILLO', 'Oro Amarillo'), ('ORO_ROSA', 'Oro Rosa'), ('PLATA', 'Plata'), ('BLANCO', 'Blanco'), ('ROSA', 'Rosa'), ('NEGRO', 'Negro')]

    orden = models.ForeignKey(Orden, related_name='items', on_delete=models.CASCADE)
    numero_item = models.PositiveIntegerField()
    fecha_limite_etapa = models.DateTimeField(blank=True, null=True)
    
    tipo_certificado = models.CharField(max_length=15, choices=TIPO_CERT_CHOICES, default='GC_SENCILLA')
    que_es = models.CharField(max_length=15, choices=QUE_ES_CHOICES, default='JOYA')
    codigo_referencia = models.CharField(max_length=100, blank=True, null=True)
    tipo_joya = models.CharField(max_length=15, choices=TIPO_JOYA_CHOICES, blank=True, null=True)
    metal = models.CharField(max_length=15, choices=METAL_CHOICES, blank=True, null=True)
    cantidad_gemas = models.PositiveIntegerField(blank=True, null=True, default=1)
    componentes_set = models.CharField(max_length=255, blank=True, null=True)
    gema_principal = models.CharField(max_length=100, blank=True, null=True)
    forma_gema = models.CharField(max_length=100, default='Ninguno')
    peso_gema = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    comentarios = models.TextField(blank=True, null=True)
    nombre_excel = models.CharField(max_length=255, blank=True, null=True)
    qr_cargado = models.ImageField(upload_to=get_qr_upload_path, blank=True, null=True)
    
    @property
    def unc_path_excel(self):
        if self.nombre_excel:
            orden_folder = f"ORDEN-{self.orden.id:04d}"; item_folder = f"ITEM-{self.numero_item}"
            full_local_path = Path(settings.MEDIA_ROOT) / orden_folder / item_folder / self.nombre_excel
            return 'file:///' + full_local_path.as_posix()
        return None
    
    @property
    def descripcion_texto(self):
        def pluralizar(nombre):
            if not nombre: return "gemas"
            if nombre.lower()[-1] in "aeiouáéíóú": return nombre + "s"
            else: return nombre + "es"

        partes = []
        if self.que_es in ['VERBAL_A_GC', 'REIMPRESION']:
            return f"{self.get_que_es_display()} - Código: {self.codigo_referencia or 'N/A'}"
        if self.que_es == 'JOYA':
            partes.append(self.get_tipo_joya_display() or "Joya")
            if self.metal: partes.append(f"en {self.get_metal_display()}")
            if self.gema_principal: partes.append(f"con {self.gema_principal}")
        elif self.que_es == 'LOTE':
            partes.append(f"Lote de {self.cantidad_gemas or ''} {pluralizar(self.gema_principal)}")
        else:
            partes.append(self.gema_principal or "Gema")
        if self.que_es != 'LOTE':
            if self.forma_gema and self.forma_gema != 'Ninguno':
                forma = self.forma_gema_otra if self.forma_gema == 'OTRO' else self.forma_gema
                partes.append(f"en talla {forma}")
        if self.peso_gema: partes.append(f"de {self.peso_gema} cts")
        if self.componentes_set: partes.append(f"({self.componentes_set.replace(',', ', ')})")
        if self.comentarios:
            if partes: partes[-1] += '.'
            partes.append(f"Comentarios: {self.comentarios}")
        return " ".join(partes).strip()
    
    def __str__(self):
        return f"Item {self.numero_item} ({self.gema_principal or self.codigo_referencia}) de la Orden {self.orden.id}"

class FotoItem(models.Model):
    item = models.ForeignKey(Item, related_name='fotos', on_delete=models.CASCADE)
    imagen = models.ImageField(upload_to=get_foto_upload_path)
    fecha_subida = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"Foto para {self.item}"


# certificacion/models.py

class ConfiguracionTiempos(models.Model):
    TIPO_ITEM_CHOICES = [('PIEDRA', 'Piedra(s) Suelta(s)'), ('JOYA', 'Joya (General)'), ('SET', 'Set de Joyas'), ('LOTE', 'Lote de Gemas')]
    
    # --- CAMBIO CLAVE ---
    # En lugar de referenciar a Item, definimos las opciones aquí directamente.
    # Es crucial que coincidan con las de Item.
    TIPO_CERT_CHOICES = [
        ('GC_SENCILLA', 'GC Sencilla'),
        ('GC_COMPLETA', 'GC Completa'),
        ('ESCRITO', 'Escrito'),
        ('DIAMANTE', 'Diamante')
    ]

    tipo_item = models.CharField(max_length=10, choices=TIPO_ITEM_CHOICES)
    tipo_certificado = models.CharField(max_length=15, choices=TIPO_CERT_CHOICES)
    
    # Mantenemos la configuración robusta de permitir nulos, que es más segura
    tiempo_ingreso = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    tiempo_fotografia = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    tiempo_revision = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    tiempo_impresion = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "Configuración de Tiempo"
        verbose_name_plural = "Configuraciones de Tiempos"
        unique_together = ('tipo_item', 'tipo_certificado')

    def __str__(self):
        return f"Tiempos para {self.get_tipo_item_display()} con certificado {self.get_tipo_certificado_display()}"