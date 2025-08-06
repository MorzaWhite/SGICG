# certificacion/forms.py
from django import forms
from .models import Orden

class OrdenForm(forms.ModelForm):
    class Meta:
        model = Orden
        fields = ['numero_orden_facturacion']
        labels = {'numero_orden_facturacion': 'Número de Orden (del sistema de facturación)',}
        widgets = {'numero_orden_facturacion': forms.TextInput(attrs={'class': 'form-control','placeholder': 'Introduce el número único de la factura'}),}  