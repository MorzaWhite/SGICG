# certificacion/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Orden, ConfiguracionTiempos
import re

class OrdenForm(forms.ModelForm):
    """Formulario mejorado para crear órdenes"""
    
    class Meta:
        model = Orden
        fields = ['numero_orden_facturacion']
        labels = {
            'numero_orden_facturacion': 'Número de Orden (del sistema de facturación)',
        }
        widgets = {
            'numero_orden_facturacion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ejemplo: ORD-2024-001',
                'required': True,
                'maxlength': 100
            }),
        }
        
        help_texts = {
            'numero_orden_facturacion': 'Número único que identifica la orden en el sistema de facturación.'
        }
    
    def clean_numero_orden_facturacion(self):
        """Validación mejorada para el número de orden"""
        numero = self.cleaned_data.get('numero_orden_facturacion', '').strip()
        
        if not numero:
            raise ValidationError('El número de orden es obligatorio.')
        
        # Validar longitud
        if len(numero) < 3:
            raise ValidationError('El número de orden debe tener al menos 3 caracteres.')
        
        if len(numero) > 100:
            raise ValidationError('El número de orden no puede exceder 100 caracteres.')
        
        # Validar caracteres permitidos (más restrictivo por seguridad)
        if not re.match(r'^[A-Za-z0-9\-\._]+$', numero):
            raise ValidationError(
                'El número de orden solo puede contener letras, números, guiones, puntos y guiones bajos.'
            )
        
        # Convertir a mayúsculas para consistencia
        numero = numero.upper()
        
        # Validar unicidad (excluyendo la instancia actual si es una edición)
        query = Orden.objects.filter(numero_orden_facturacion=numero)
        if self.instance and self.instance.pk:
            query = query.exclude(pk=self.instance.pk)
        
        if query.exists():
            raise ValidationError(f'Ya existe una orden con el número "{numero}". Debe ser único.')
        
        return numero


class BusquedaOrdenForm(forms.Form):
    """Formulario mejorado para búsqueda y filtros en el dashboard"""
    
    search = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por número de orden, gema o código...',
            'autocomplete': 'off'
        }),
        help_text='Busca en números de orden, gemas principales y códigos de referencia'
    )
    
    etapa = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
        help_text='Filtrar por etapa específica'
    )
    
    mostrar_retrasados = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
        }),
        help_text='Mostrar solo órdenes con ítems retrasados'
    )
    
    ordenar_por = forms.ChoiceField(
        required=False,
        choices=[
            ('fecha_entrega', 'Fecha de entrega'),
            ('fecha_creacion', 'Fecha de creación'),
            ('numero_orden', 'Número de orden'),
        ],
        initial='fecha_entrega',
        widget=forms.Select(attrs={
            'class': 'form-select',
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Generar choices para etapas dinámicamente
        etapa_choices = [('', 'Todas las etapas')]
        for key, value in Orden.ETAPAS:
            if key != 'FINALIZADA':  # No incluir finalizadas en filtros
                etapa_choices.append((key, value))
        
        self.fields['etapa'].choices = etapa_choices
    
    def clean_search(self):
        """Validación para el campo de búsqueda"""
        search = self.cleaned_data.get('search', '').strip()
        
        if search and len(search) < 2:
            raise ValidationError('El término de búsqueda debe tener al menos 2 caracteres.')
        
        # Sanitizar entrada para evitar inyecciones
        if search and re.search(r'[<>"\']', search):
            raise ValidationError('El término de búsqueda contiene caracteres no permitidos.')
        
        return search


class ConfiguracionTiempoForm(forms.Form):
    """Formulario mejorado para configuración de tiempos"""
    
    def __init__(self, *args, **kwargs):
        self.configuraciones = kwargs.pop('configuraciones', [])
        super().__init__(*args, **kwargs)
        
        # Crear campos dinámicamente para cada configuración
        for config in self.configuraciones:
            self._create_time_fields(config)
    
    def _create_time_fields(self, config):
        """Crea campos de tiempo para una configuración específica"""
        etapas = ['ingreso', 'fotografia', 'revision', 'impresion']
        
        for etapa in etapas:
            field_name = f'{etapa}_{config.tipo_item}_{config.tipo_certificado}'
            current_value = getattr(config, f'tiempo_{etapa}', None)
            
            self.fields[field_name] = forms.IntegerField(
                required=False,
                min_value=60,  # Mínimo 1 minuto
                max_value=2592000,  # Máximo 30 días
                initial=current_value,
                widget=forms.NumberInput(attrs={
                    'class': 'form-control form-control-sm text-center',
                    'placeholder': 'Segundos',
                    'step': '1',
                    'min': '60',
                    'max': '2592000'
                }),
                help_text=f'Tiempo en segundos para {etapa} (60 seg - 30 días)',
                label=f'{config.get_tipo_item_display()} - {config.get_tipo_certificado_display()} - {etapa.title()}'
            )
    
    def clean(self):
        """Validación general del formulario"""
        cleaned_data = super().clean()
        errores = []
        
        # Validar que al menos un campo tenga valor válido
        configs_con_valores = set()
        
        for field_name, value in cleaned_data.items():
            if value is not None and value > 0:
                # Extraer información de la configuración del nombre del campo
                parts = field_name.split('_')
                if len(parts) >= 3:
                    config_key = '_'.join(parts[1:])  # tipo_item_tipo_cert
                    configs_con_valores.add(config_key)
        
        if not configs_con_valores:
            errores.append('Debe especificar al menos un tiempo válido para alguna configuración.')
        
        # Validar consistencia de tiempos por configuración
        for config in self.configuraciones:
            config_key = f'{config.tipo_item}_{config.tipo_certificado}'
            tiempos_config = []
            
            for etapa in ['ingreso', 'fotografia', 'revision', 'impresion']:
                field_name = f'{etapa}_{config_key}'
                valor = cleaned_data.get(field_name)
                if valor is not None:
                    tiempos_config.append(valor)
            
            # Si hay tiempos definidos, validar que sean razonables
            if tiempos_config:
                total_tiempo = sum(tiempos_config)
                
                if total_tiempo > 2592000:  # 30 días
                    errores.append(
                        f'El tiempo total para {config.get_tipo_item_display()} - '
                        f'{config.get_tipo_certificado_display()} excede 30 días.'
                    )
                
                # Validar que los tiempos tengan proporciones razonables
                if max(tiempos_config) > total_tiempo * 0.8:
                    errores.append(
                        f'Una etapa en {config.get_tipo_item_display()} - '
                        f'{config.get_tipo_certificado_display()} consume más del 80% del tiempo total.'
                    )
        
        if errores:
            raise ValidationError(errores)
        
        return cleaned_data
    
    def save_configurations(self):
        """Guarda las configuraciones validadas"""
        if not self.is_valid():
            raise ValidationError('Formulario no válido')
        
        saved_count = 0
        
        for config in self.configuraciones:
            config_key = f'{config.tipo_item}_{config.tipo_certificado}'
            modified = False
            
            for etapa in ['ingreso', 'fotografia', 'revision', 'impresion']:
                field_name = f'{etapa}_{config_key}'
                new_value = self.cleaned_data.get(field_name)
                current_value = getattr(config, f'tiempo_{etapa}')
                
                if new_value != current_value:
                    setattr(config, f'tiempo_{etapa}', new_value)
                    modified = True
            
            if modified:
                config.full_clean()  # Validar el modelo antes de guardar
                config.save()
                saved_count += 1
        
        return saved_count


class SubirArchivoForm(forms.Form):
    """Formulario base para subida de archivos con validaciones mejoradas"""
    
    archivo = forms.FileField(
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*'
        }),
        help_text='Archivos permitidos: JPG, PNG, WEBP (máximo 5MB)'
    )
    
    def clean_archivo(self):
        archivo = self.cleaned_data.get('archivo')
        
        if not archivo:
            raise ValidationError('Debe seleccionar un archivo.')
        
        # Validar tipo de archivo
        allowed_types = ['image/jpeg', 'image/png', 'image/jpg', 'image/webp']
        if hasattr(archivo, 'content_type') and archivo.content_type not in allowed_types:
            raise ValidationError('Solo se permiten archivos de imagen (JPG, PNG, WEBP).')
        
        # Validar tamaño (5MB por defecto)
        max_size = getattr(self, 'max_file_size', 5) * 1024 * 1024
        if hasattr(archivo, 'size') and archivo.size > max_size:
            max_mb = max_size / (1024 * 1024)
            raise ValidationError(f'El archivo es demasiado grande (máximo {max_mb:.1f}MB).')
        
        return archivo


class SubirQRForm(SubirArchivoForm):
    """Formulario específico para subir códigos QR"""
    max_file_size = 5  # MB
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['archivo'].label = 'Código QR'
        self.fields['archivo'].help_text = 'Imagen del código QR (JPG, PNG, WEBP - máximo 5MB)'


class SubirFotosForm(forms.Form):
    """Formulario específico para subir múltiples fotos profesionales"""
    
    fotos = forms.FileField(
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'multiple': True,
            'accept': 'image/*'
        }),
        help_text='Seleccione múltiples fotos profesionales (máximo 10 archivos, 10MB cada uno)'
    )
    
    def clean_fotos(self):
        fotos = self.files.getlist('fotos')
        
        if not fotos:
            raise ValidationError('Debe seleccionar al menos una foto.')
        
        if len(fotos) > 10:
            raise ValidationError('Máximo 10 fotos por ítem.')
        
        # Validar cada foto
        allowed_types = ['image/jpeg', 'image/png', 'image/jpg', 'image/webp']
        max_size = 10 * 1024 * 1024  # 10MB por foto
        
        for i, foto in enumerate(fotos, 1):
            if hasattr(foto, 'content_type') and foto.content_type not in allowed_types:
                raise ValidationError(f'Foto {i}: Solo se permiten archivos de imagen (JPG, PNG, WEBP).')
            
            if hasattr(foto, 'size') and foto.size > max_size:
                raise ValidationError(f'Foto {i}: Archivo demasiado grande (máximo 10MB).')
        
        return fotos


class FiltroAvanzadoForm(forms.Form):
    """Formulario para filtros avanzados en reportes y análisis"""
    
    fecha_desde = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={
            'class': 'form-control',
            'type': 'datetime-local'
        }),
        help_text='Fecha y hora de inicio del rango'
    )
    
    fecha_hasta = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={
            'class': 'form-control',
            'type': 'datetime-local'
        }),
        help_text='Fecha y hora de fin del rango'
    )
    
    tipos_certificado = forms.MultipleChoiceField(
        required=False,
        choices=[],  # Se llenan dinámicamente
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'form-check-input'
        }),
        help_text='Seleccione uno o más tipos de certificado'
    )
    
    incluir_finalizadas = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text='Incluir órdenes finalizadas en los resultados'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Llenar choices dinámicamente
        from .models import Item
        self.fields['tipos_certificado'].choices = Item.TIPO_CERT_CHOICES
    
    def clean(self):
        cleaned_data = super().clean()
        fecha_desde = cleaned_data.get('fecha_desde')
        fecha_hasta = cleaned_data.get('fecha_hasta')
        
        # Validar rango de fechas
        if fecha_desde and fecha_hasta:
            if fecha_desde >= fecha_hasta:
                raise ValidationError('La fecha de inicio debe ser anterior a la fecha de fin.')
            
            # Validar que el rango no sea demasiado amplio
            delta = fecha_hasta - fecha_desde
            if delta.days > 365:
                raise ValidationError('El rango de fechas no puede exceder un año.')
        
        # Validar fechas futuras
        now = timezone.now()
        if fecha_desde and fecha_desde > now:
            raise ValidationError('La fecha de inicio no puede ser futura.')
        
        if fecha_hasta and fecha_hasta > now:
            raise ValidationError('La fecha de fin no puede ser futura.')
        
        return cleaned_data