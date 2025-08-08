# certificacion/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from pathlib import Path
import os

def get_qr_upload_path(instance, filename):
    """Genera la ruta para subir archivos QR"""
    orden_folder = f"ORDEN-{instance.orden.id:04d}"
    item_folder = f"ITEM-{instance.numero_item}"
    return os.path.join(orden_folder, item_folder, filename)

def get_foto_upload_path(instance, filename):
    """Genera la ruta para subir fotos"""
    orden_folder = f"ORDEN-{instance.item.orden.id:04d}"
    item_folder = f"ITEM-{instance.item.numero_item}"
    return os.path.join(orden_folder, item_folder, filename)

class Orden(models.Model):
    """Modelo principal para las órdenes de certificación"""
    
    ETAPAS = [
        ('INGRESO', 'Ingreso'),
        ('FOTOGRAFIA', 'Fotografía'),
        ('REVISION', 'Revisión'),
        ('IMPRESION', 'Impresión'),
        ('FINALIZADA', 'Finalizada')
    ]
    
    numero_orden_facturacion = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Número de Orden (Facturación)",
        db_index=True
    )
    estado_actual = models.CharField(
        max_length=20,
        choices=ETAPAS,
        default='INGRESO',
        db_index=True
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True, db_index=True)
    fecha_cierre = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-fecha_creacion']
        indexes = [
            models.Index(fields=['estado_actual', 'fecha_creacion']),
        ]

    def __str__(self):
        return f"Orden {self.id} - {self.numero_orden_facturacion}"
    
    def get_proxima_etapa(self):
        """Obtiene la próxima etapa o None si ya está finalizada"""
        etapas = [e[0] for e in self.ETAPAS]
        try:
            idx = etapas.index(self.estado_actual)
            if idx < len(etapas) - 1:
                return etapas[idx + 1]
        except ValueError:
            pass
        return None
    
    def get_progreso_porcentaje(self):
        """Calcula el porcentaje de progreso de la orden"""
        etapas = ['INGRESO', 'FOTOGRAFIA', 'REVISION', 'IMPRESION', 'FINALIZADA']
        try:
            indice_actual = etapas.index(self.estado_actual)
            return (indice_actual / (len(etapas) - 1)) * 100
        except ValueError:
            return 0

    def tiene_items_retrasados(self):
        """Indica si la orden tiene ítems retrasados"""
        return self.items.filter(
            fecha_limite_etapa__lt=timezone.now()
        ).exists()

    def get_tiempo_estimado_total(self):
        """Calcula el tiempo estimado total de todos los ítems"""
        ultimo_item = self.items.order_by('fecha_limite_etapa').last()
        return ultimo_item.fecha_limite_etapa if ultimo_item else None

    def get_descripcion_completa(self):
        """Obtiene una descripción completa de todos los ítems"""
        items_desc = []
        for item in self.items.all():
            items_desc.append(f"Item {item.numero_item}: {item.descripcion_texto}")
        return "; ".join(items_desc)


class Item(models.Model):
    """Modelo para los ítems individuales de cada orden"""
    
    TIPO_CERT_CHOICES = [
        ('GC_SENCILLA', 'GC Sencilla'),
        ('GC_COMPLETA', 'GC Completa'),
        ('ESCRITO', 'Escrito'),
        ('DIAMANTE', 'Diamante')
    ]
    
    QUE_ES_CHOICES = [
        ('JOYA', 'Joya'),
        ('LOTE', 'Lote de Gemas'),
        ('PIEDRA', 'Piedra(s) Suelta(s)'),
        ('VERBAL_A_GC', 'Verbal a GC'),
        ('REIMPRESION', 'Reimpresión')
    ]
    
    TIPO_JOYA_CHOICES = [
        ('ANILLO', 'Anillo'),
        ('DIJE', 'Dije'),
        ('TOPOS', 'Topos'),
        ('PULSERA', 'Pulsera'),
        ('PULSERA_TENIS', 'Pulsera Tenis'),
        ('SET', 'Set')
    ]
    
    METAL_CHOICES = [
        ('ORO', 'Oro'),
        ('ORO_AMARILLO', 'Oro Amarillo'),
        ('ORO_ROSA', 'Oro Rosa'),
        ('PLATA', 'Plata'),
        ('BLANCO', 'Blanco'),
        ('ROSA', 'Rosa'),
        ('NEGRO', 'Negro')
    ]

    orden = models.ForeignKey(Orden, related_name='items', on_delete=models.CASCADE)
    numero_item = models.PositiveIntegerField()
    fecha_limite_etapa = models.DateTimeField(blank=True, null=True, db_index=True)
    
    # Campos principales
    tipo_certificado = models.CharField(
        max_length=15,
        choices=TIPO_CERT_CHOICES,
        default='GC_SENCILLA'
    )
    que_es = models.CharField(max_length=15, choices=QUE_ES_CHOICES, default='JOYA')
    codigo_referencia = models.CharField(max_length=100, blank=True, null=True)
    
    # Campos para joyas
    tipo_joya = models.CharField(
        max_length=15,
        choices=TIPO_JOYA_CHOICES,
        blank=True,
        null=True
    )
    metal = models.CharField(max_length=15, choices=METAL_CHOICES, blank=True, null=True)
    cantidad_gemas = models.PositiveIntegerField(blank=True, null=True, default=1)
    componentes_set = models.CharField(max_length=255, blank=True, null=True)
    
    # Campos para gemas
    gema_principal = models.CharField(max_length=100, blank=True, null=True)
    forma_gema = models.CharField(max_length=100, default='Ninguno')
    peso_gema = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        blank=True,
        null=True
    )
    comentarios = models.TextField(blank=True, null=True)
    
    # Archivos
    nombre_excel = models.CharField(max_length=255, blank=True, null=True)
    qr_cargado = models.ImageField(upload_to=get_qr_upload_path, blank=True, null=True)
    texto_para_copiar = models.TextField(blank=True, null=True, help_text="Texto formateado con todos los datos del ítem")
    
    class Meta:
        ordering = ['numero_item']
        unique_together = ['orden', 'numero_item']
        indexes = [
            models.Index(fields=['orden', 'fecha_limite_etapa']),
        ]
    
    def __str__(self):
        return f"Item {self.numero_item} - Orden {self.orden.numero_orden_facturacion}"
    
    @property
    def unc_path_excel(self):
        """Genera la ruta UNC para acceder al archivo Excel"""
        if self.nombre_excel:
            orden_folder = f"ORDEN-{self.orden.id:04d}"
            item_folder = f"ITEM-{self.numero_item}"
            full_local_path = Path(settings.MEDIA_ROOT) / orden_folder / item_folder / self.nombre_excel
            return 'file:///' + full_local_path.as_posix()
        return None
    
    @property
    def descripcion_texto(self):
        """Genera una descripción textual del ítem en formato natural"""
        
        # Casos especiales
        if self.que_es in ['VERBAL_A_GC', 'REIMPRESION']:
            que_es_display = {
                'VERBAL_A_GC': 'Verbal a GC',
                'REIMPRESION': 'Reimpresión'
            }
            return f"{que_es_display.get(self.que_es, self.que_es)} - Código: {self.codigo_referencia or 'N/A'}"
        
        # Construcción del texto natural
        partes = []
        
        # Agregar cantidad si es mayor a 1
        if self.cantidad_gemas and self.cantidad_gemas > 1:
            if self.cantidad_gemas == 2:
                partes.append("Par de")
            elif self.cantidad_gemas == 3:
                partes.append("Trío de")
            else:
                partes.append(f"{self.cantidad_gemas}")
        
        # Gema principal
        if self.gema_principal:
            gema = self.gema_principal
            
            # Para lotes, pluralizar
            if self.que_es == 'LOTE' and self.cantidad_gemas and self.cantidad_gemas > 1:
                if gema.lower().endswith(('a', 'e', 'i', 'o', 'u', 'á', 'é', 'í', 'ó', 'ú')):
                    gema = gema.lower() + "s"
                else:
                    gema = gema.lower() + "es"
            else:
                gema = gema  # Mantener mayúscula inicial
            
            partes.append(gema)
        
        # Detalles de joya
        if self.que_es == 'JOYA':
            # Metal
            if self.metal:
                metal_display = {
                    'ORO': 'oro', 'ORO_AMARILLO': 'oro amarillo', 'ORO_ROSA': 'oro rosa',
                    'PLATA': 'plata', 'BLANCO': 'oro blanco', 'ROSA': 'oro rosa', 'NEGRO': 'oro negro'
                }
                metal_texto = metal_display.get(self.metal, self.metal.lower())
                partes.append(f"en {metal_texto}")
            
            # Tipo de joya
            if self.tipo_joya:
                tipo_joya_display = {
                    'ANILLO': 'anillo', 'DIJE': 'dije', 'TOPOS': 'topos',
                    'PULSERA': 'pulsera', 'PULSERA_TENIS': 'pulsera tenis', 'SET': 'set'
                }
                tipo_texto = tipo_joya_display.get(self.tipo_joya, self.tipo_joya.lower())
                
                # Si es set, agregar componentes
                if self.tipo_joya == 'SET' and self.componentes_set:
                    componentes = self.componentes_set.replace(',', ', ')
                    partes.append(f"{tipo_texto} ({componentes})")
                else:
                    partes.append(tipo_texto)
        
        # Forma de la gema
        if self.forma_gema and self.forma_gema != 'Ninguno':
            partes.append(f"en talla {self.forma_gema}")
        
        # Peso
        if self.peso_gema:
            partes.append(f"de {self.peso_gema} cts")
        
        # Construir el texto final
        texto_base = " ".join(partes)
        
        # Agregar comentarios si existen
        if self.comentarios:
            texto_base += f". {self.comentarios}"
        
        return texto_base
    
    @property
    def esta_retrasado(self):
        """Indica si el ítem está retrasado respecto a su fecha límite"""
        if not self.fecha_limite_etapa:
            return False
        return timezone.now() > self.fecha_limite_etapa

    @property
    def tiempo_restante_segundos(self):
        """Calcula el tiempo restante en segundos"""
        if not self.fecha_limite_etapa:
            return None
        delta = self.fecha_limite_etapa - timezone.now()
        return max(0, int(delta.total_seconds()))

    @property
    def estado_urgencia(self):
        """Devuelve el estado de urgencia del ítem"""
        if self.esta_retrasado:
            return 'retrasado'
        elif self.tiempo_restante_segundos and self.tiempo_restante_segundos < 3600:  # < 1 hora
            return 'urgente'
        elif self.tiempo_restante_segundos and self.tiempo_restante_segundos < 86400:  # < 24 horas
            return 'proximo'
        return 'normal'
    
    def clean(self):
        """Validaciones del modelo"""
        from django.core.exceptions import ValidationError
        
        if self.que_es in ['VERBAL_A_GC', 'REIMPRESION']:
            if not self.codigo_referencia:
                raise ValidationError(
                    "Los ítems de tipo Verbal a GC o Reimpresión requieren código de referencia"
                )
        else:
            if not self.gema_principal:
                raise ValidationError(
                    "Los ítems deben tener una gema principal especificada"
                )
        
        if self.que_es == 'JOYA' and not self.tipo_joya:
            raise ValidationError("Las joyas deben tener un tipo especificado")
        
        if self.peso_gema is not None and self.peso_gema <= 0:
            raise ValidationError("El peso de la gema debe ser positivo")
        


class FotoItem(models.Model):
    """Modelo para las fotos de los ítems"""
    
    item = models.ForeignKey(Item, related_name='fotos', on_delete=models.CASCADE)
    imagen = models.ImageField(upload_to=get_foto_upload_path)
    fecha_subida = models.DateTimeField(auto_now_add=True)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    
    class Meta:
        ordering = ['-fecha_subida']
    
    def __str__(self):
        return f"Foto para {self.item}"


class ConfiguracionTiempos(models.Model):
    """Modelo para la configuración de tiempos estimados por etapa"""
    
    TIPO_ITEM_CHOICES = [
        ('PIEDRA', 'Piedra(s) Suelta(s)'),
        ('JOYA', 'Joya (General)'),
        ('SET', 'Set de Joyas'),
        ('LOTE', 'Lote de Gemas')
    ]
    
    TIPO_CERT_CHOICES = [
        ('GC_SENCILLA', 'GC Sencilla'),
        ('GC_COMPLETA', 'GC Completa'),
        ('ESCRITO', 'Escrito'),
        ('DIAMANTE', 'Diamante')
    ]

    tipo_item = models.CharField(max_length=10, choices=TIPO_ITEM_CHOICES)
    tipo_certificado = models.CharField(max_length=15, choices=TIPO_CERT_CHOICES)
    
    # Tiempos en segundos - permitir nulos para mayor flexibilidad
    tiempo_ingreso = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Tiempo en segundos"
    )
    tiempo_fotografia = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Tiempo en segundos"
    )
    tiempo_revision = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Tiempo en segundos"
    )
    tiempo_impresion = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Tiempo en segundos"
    )
    
    # Campos de auditoría
    fecha_creacion = models.DateTimeField(default=timezone.now)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Configuración de Tiempo"
        verbose_name_plural = "Configuraciones de Tiempos"
        unique_together = ('tipo_item', 'tipo_certificado')
        ordering = ['tipo_item', 'tipo_certificado']

    def __str__(self):
        return f"Tiempos para {self.get_tipo_item_display()} con certificado {self.get_tipo_certificado_display()}"
    
    def get_tiempo_total(self):
        """Calcula el tiempo total sumando todas las etapas"""
        total = 0
        for field in ['tiempo_ingreso', 'tiempo_fotografia', 'tiempo_revision', 'tiempo_impresion']:
            valor = getattr(self, field)
            if valor is not None:
                total += valor
        return total
    
    def clean(self):
        """Validaciones del modelo"""
        from django.core.exceptions import ValidationError
        
        # Verificar que al menos un tiempo esté definido
        tiempos = [self.tiempo_ingreso, self.tiempo_fotografia, self.tiempo_revision, self.tiempo_impresion]
        if all(t is None for t in tiempos):
            raise ValidationError("Debe definir al menos un tiempo para una etapa")
        
        # Verificar límites razonables
        for field_name, valor in [
            ('tiempo_ingreso', self.tiempo_ingreso),
            ('tiempo_fotografia', self.tiempo_fotografia),
            ('tiempo_revision', self.tiempo_revision),
            ('tiempo_impresion', self.tiempo_impresion)
        ]:
            if valor is not None:
                if valor > 2592000:  # 30 días
                    raise ValidationError(f"{field_name}: El tiempo no puede exceder 30 días")
                if valor < 60:  # 1 minuto mínimo
                    raise ValidationError(f"{field_name}: El tiempo mínimo es de 60 segundos")