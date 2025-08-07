# certificacion/forms.py
from django import forms
from django.core.exceptions import ValidationError
from .models import Orden
import re

class OrdenForm(forms.ModelForm):
    class Meta:
        model = Orden
        fields = ['numero_orden_facturacion']
        labels = {
            'numero_orden_facturacion': 'Número de Orden (del sistema de facturación)',
        }
        widgets = {
            'numero_orden_facturacion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Introduce el número único de la factura',
                'required': True
            }),
        }
    
    def clean_numero_orden_facturacion(self):
        """Validación personalizada para el número de orden."""
        numero = self.cleaned_data.get('numero_orden_facturacion', '').strip()
        
        if not numero:
            raise ValidationError('El número de orden es obligatorio.')
        
        # Validar longitud mínima
        if len(numero) < 3:
            raise ValidationError('El número de orden debe tener al menos 3 caracteres.')
        
        # Validar longitud máxima
        if len(numero) > 100:
            raise ValidationError('El número de orden no puede exceder 100 caracteres.')
        
        # Validar caracteres permitidos (letras, números, guiones, puntos)
        if not re.match(r'^[A-Za-z0-9\-\.\_]+$', numero):
            raise ValidationError('El número de orden solo puede contener letras, números, guiones y puntos.')
        
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
    """Formulario para búsqueda y filtros en el dashboard."""
    search = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por número de orden, gema o código...',
        })
    )
    
    etapa = forms.ChoiceField(
        required=False,
        choices=[('', 'Todas las etapas')] + [
            (key, value) for key, value in Orden.ETAPAS 
            if key != 'FINALIZADA'
        ],
        widget=forms.Select(attrs={
            'class': 'form-select',
        })
    )
    
    mostrar_retrasados = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
        })
    )

class ConfiguracionTiempoForm(forms.Form):
    """Formulario para configuración de tiempos."""
    
    def __init__(self, *args, **kwargs):
        self.configuracion = kwargs.pop('configuracion', None)
        super().__init__(*args, **kwargs)
        
        if self.configuracion:
            # Crear campos dinámicamente para cada etapa
            etapas = ['ingreso', 'fotografia', 'revision', 'impresion']
            for etapa in etapas:
                field_name = f'tiempo_{etapa}'
                current_value = getattr(self.configuracion, field_name, None)
                
                self.fields[field_name] = forms.IntegerField(
                    required=False,
                    min_value=0,
                    max_value=604800,  # 7 días máximo
                    initial=current_value,
                    widget=forms.NumberInput(attrs={
                        'class': 'form-control text-center',
                        'placeholder': 'Segundos',
                        'step': '1'
                    }),
                    label=f'Tiempo {etapa.title()} (segundos)'
                )
    
    def clean(self):
        """Validación general del formulario."""
        cleaned_data = super().clean()
        
        # Verificar que al menos un campo tenga valor
        etapas = ['tiempo_ingreso', 'tiempo_fotografia', 'tiempo_revision', 'tiempo_impresion']
        tiene_valor = any(cleaned_data.get(etapa) is not None for etapa in etapas)
        
        if not tiene_valor:
            raise ValidationError('Debe especificar al menos un tiempo para una etapa.')
        
        # Validar tiempos lógicos
        ingreso = cleaned_data.get('tiempo_ingreso', 0) or 0
        fotografia = cleaned_data.get('tiempo_fotografia', 0) or 0
        revision = cleaned_data.get('tiempo_revision', 0) or 0
        impresion = cleaned_data.get('tiempo_impresion', 0) or 0
        
        total = ingreso + fotografia + revision + impresion
        if total > 2592000:  # 30 días
            raise ValidationError('El tiempo total no puede exceder 30 días (2,592,000 segundos).')
        
        return cleaned_data