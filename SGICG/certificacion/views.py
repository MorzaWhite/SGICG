# SGICG/certificacion/views.py

# SGICG/certificacion/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.utils import timezone
from django.conf import settings
from django.db.models import Max, F
from .models import Orden, Item, FotoItem, ConfiguracionTiempos
from .forms import OrdenForm
import os
import shutil
from datetime import timedelta
from decimal import Decimal, InvalidOperation

# --- FUNCIONES AUXILIARES ---

def get_tiempo_estimado(tipo_item_key, tipo_cert_key, etapa_key):
    """Obtiene el tiempo configurado en segundos."""
    try:
        if tipo_item_key in ['PIEDRA', 'Piedra(s) Suelta(s)']:
            tipo_item_key = 'PIEDRA'
        config = ConfiguracionTiempos.objects.get(tipo_item=tipo_item_key, tipo_certificado=tipo_cert_key)
        # Devuelve el valor en segundos (ej: 3600)
        return getattr(config, f'tiempo_{etapa_key.lower()}')
    except (ConfiguracionTiempos.DoesNotExist, AttributeError):
        # Valor por defecto: 8 horas en segundos (8 * 3600 = 28800)
        return 28800

def get_ultimo_tiempo_ocupado():
    """Busca la fecha límite más lejana para saber cuándo termina la cola."""
    items_activos = Item.objects.filter(orden__estado_actual__in=['INGRESO', 'FOTOGRAFIA', 'REVISION', 'IMPRESION'])
    resultado = items_activos.aggregate(max_fecha=Max('fecha_limite_etapa'))
    ultima_fecha = resultado.get('max_fecha')
    if ultima_fecha:
        return ultima_fecha
    return timezone.now()

# --- VISTAS PRINCIPALES ---

def dashboard(request):
    """Muestra todas las órdenes activas, ordenadas por fecha de entrega."""
    ordenes_sin_ordenar = Orden.objects.filter(
        estado_actual__in=['INGRESO', 'FOTOGRAFIA', 'REVISION', 'IMPRESION']
    ).prefetch_related('items').distinct()

    def obtener_fecha_para_ordenar(orden):
        primer_item = orden.items.first()
        if primer_item and primer_item.fecha_limite_etapa:
            return primer_item.fecha_limite_etapa
        return timezone.now() + timedelta(days=9999)

    ordenes_activas = sorted(list(ordenes_sin_ordenar), key=obtener_fecha_para_ordenar)
    context = {'ordenes_activas': ordenes_activas}
    return render(request, 'dashboard.html', context)

class CrearOrdenView(View):
    """Gestiona la creación de nuevas órdenes con múltiples ítems."""
    def get(self, request):
        form = OrdenForm()
        gemas_principales = ['Ágata', 'Aguamarina', 'Alejandrita', 'Almandino - Espesartina', 'Amatista', 'Amazonita', 'Ankerita', 'Antracita', 'Apatito', 'Azabache', 'Berilo', 'Calcedonia', 'Calcopirita', 'Carbón', 'Citrino', 'Coral', 'Cordierita', 'Corindón', 'Crisoberilo', 'Cristal de roca', 'Cuarzo', 'Dolomita', 'Espinela', 'Euclasa', 'Feldespato', 'Fluorita', 'Fuchsita', 'Granate', 'Grosular', 'Grosularia - Andradita', 'Grosularia', 'Jacinta', 'Jaspe', 'Malaquita', 'Mica', 'Microclina', 'Moissanita', 'Obsidiana', 'Ónix', 'Ópalo', 'Paraiba', 'Perla Cultivada', 'Pirita', 'Piropo - Almandino', 'Rubí Glassfilled', 'Rubí', 'Rubí Estrella', 'Tanzanita', 'Trilitionita', 'Tsavorita', 'Turmalina', 'Vidrio', 'Zafiro', 'Zafiro cambio de color', 'Zafiro estrella', 'Zircón', 'Zoisita', 'Vivianita', 'Topacio', 'Cuarzo ahumado', 'Almandino - Piropo', 'Espesartita - Piropo', 'Zirconia cubica', 'Diamante', 'Esmeralda']
        formas_gema = ['Baguette', 'Barroco', 'Briolette', 'Caballo', 'Cilíndrica', 'Circular', 'Cojín', 'Corazón', 'Cuadrada', 'Esfera', 'Esmeralda', 'Fantasía', 'Hexagonal', 'Lágrima', 'Marquis', 'Ninguno', 'Óvalo', 'Prisma ditrigonal', 'Prisma hexagonal', 'Prisma Piramidal', 'Prisma Tetragonal', 'Rectangular', 'Redonda', 'Rostro', 'Trapecio', 'Trillion', 'Hoja', 'Cabuchon', 'Prisma dihexagonal', 'Caballo de Mar', 'Varios']
        context = {'form': form, 'gemas_principales': sorted(gemas_principales), 'formas_gema': sorted(formas_gema)}
        return render(request, 'crear_orden.html', context)

    def post(self, request):
        form = OrdenForm(request.POST)
        if form.is_valid():
            orden = form.save(commit=False); orden.estado_actual = 'INGRESO'; orden.save()
            
            tipos_cert = request.POST.getlist('tipo_certificado')
            que_es_list = request.POST.getlist('que_es')
            codigos_referencia = request.POST.getlist('codigo_referencia')
            tipos_joya = request.POST.getlist('tipo_joya')
            metales = request.POST.getlist('metal')
            gemas_principales = request.POST.getlist('gema_principal')
            formas_gema = request.POST.getlist('forma_gema')
            pesos_gema = request.POST.getlist('peso_gema')
            comentarios_list = request.POST.getlist('comentarios')

            nombre_carpeta_orden = f"ORDEN-{orden.id:04d}"; ruta_orden = os.path.join(settings.MEDIA_ROOT, nombre_carpeta_orden); os.makedirs(ruta_orden, exist_ok=True)
            punto_de_partida = get_ultimo_tiempo_ocupado()

            for i, data in enumerate(zip(
                tipos_cert, que_es_list, codigos_referencia, tipos_joya, metales,
                gemas_principales, formas_gema, pesos_gema, comentarios_list
            ), start=1):
                
                (tipo_cert, que_es, codigo_ref, tipo_joya, metal, gema_ppal, 
                 forma, peso, comentarios) = data

                if not gema_ppal and que_es not in ['VERBAL_A_GC', 'REIMPRESION']: continue

                # (Aquí va tu lógica completa para `cantidad_final_gemas` si la necesitas)
                cantidad_final_gemas = 1

                duracion_total_item_segundos = 0
                etapas_a_sumar = ['INGRESO', 'FOTOGRAFIA', 'REVISION', 'IMPRESION']
                item_type_key = que_es
                if que_es == 'JOYA' and tipo_joya == 'SET': item_type_key = 'SET'

                for etapa in etapas_a_sumar:
                    tiempo_etapa_segundos = get_tiempo_estimado(item_type_key, tipo_cert, etapa)
                    if tiempo_etapa_segundos:
                        duracion_total_item_segundos += int(tiempo_etapa_segundos)
                
                # CORRECCIÓN: timedelta ahora usa segundos.
                fecha_limite = punto_de_partida + timedelta(seconds=duracion_total_item_segundos)
                # CORRECCIÓN: Se actualiza el punto de partida para el siguiente ítem.
                punto_de_partida = fecha_limite
                
                componentes_del_set = request.POST.getlist(f'componentes_set_{i}')
                componentes_str = ",".join(componentes_del_set) if componentes_del_set else None

                Item.objects.create(
                    orden=orden, numero_item=i, fecha_limite_etapa=fecha_limite,
                    tipo_certificado=tipo_cert, que_es=que_es,
                    codigo_referencia=codigo_ref if que_es in ['VERBAL_A_GC', 'REIMPRESION'] else None,
                    tipo_joya=tipo_joya if que_es == 'JOYA' else None,
                    cantidad_gemas=cantidad_final_gemas, metal=metal if que_es == 'JOYA' else None,
                    componentes_set=componentes_str if que_es == 'JOYA' and tipo_joya == 'SET' else None,
                    gema_principal=gema_ppal if que_es not in ['VERBAL_A_GC', 'REIMPRESION'] else None,
                    forma_gema=forma, peso_gema=peso if peso else None, comentarios=comentarios,
                )
            
            return redirect('orden_creada_exito', orden_id=orden.id)
        
        else:
            gemas_principales = ['Ágata', '...']; formas_gema = ['Baguette', '...']
            context = {'form': form, 'gemas_principales': sorted(gemas_principales), 'formas_gema': sorted(formas_gema)}
            return render(request, 'crear_orden.html', context)

def avanzar_etapa(request, orden_id):
    """Avanza una orden a la siguiente etapa y resta el tiempo de la etapa completada."""
    orden = get_object_or_404(Orden, id=orden_id)
    etapa_terminada = orden.estado_actual
    proxima_etapa = orden.get_proxima_etapa()
    if not proxima_etapa: return redirect('dashboard')

    duracion_total_a_restar_segundos = 0
    for item in orden.items.all():
        item_type_key = item.que_es
        if item.que_es == 'JOYA' and item.tipo_joya == 'SET': item_type_key = 'SET'
        tipo_cert_key = item.tipo_certificado
        
        duracion_item_etapa = get_tiempo_estimado(item_type_key, tipo_cert_key, etapa_terminada)
        if duracion_item_etapa: duracion_total_a_restar_segundos += int(duracion_item_etapa)
            
    if duracion_total_a_restar_segundos > 0:
        # CORRECCIÓN: timedelta ahora usa segundos.
        tiempo_a_restar = timedelta(seconds=duracion_total_a_restar_segundos)
        
        # Se resta el tiempo a la PROPIA orden.
        Item.objects.filter(orden=orden).update(fecha_limite_etapa=F('fecha_limite_etapa') - tiempo_a_restar)

    orden.estado_actual = proxima_etapa
    if proxima_etapa == 'FINALIZADA':
        orden.fecha_cierre = timezone.now(); orden.items.all().update(fecha_limite_etapa=None)
    orden.save()
    return redirect('dashboard')

def configuracion_tiempos(request):
    """Permite ver y guardar los tiempos de cada etapa directamente en segundos."""
    if request.method == 'POST':
        for config in ConfiguracionTiempos.objects.all():
            etapa_map = {
                'ingreso': 'tiempo_ingreso', 'foto': 'tiempo_fotografia',
                'revision': 'tiempo_revision', 'impresion': 'tiempo_impresion',
            }
            for form_prefix, model_field in etapa_map.items():
                post_key = f'{form_prefix}_{config.tipo_item}_{config.tipo_certificado}'
                segundos_str = request.POST.get(post_key)
                segundos_value = None
                if segundos_str and segundos_str.strip():
                    try: segundos_value = int(segundos_str)
                    except (ValueError, TypeError): pass
                setattr(config, model_field, segundos_value)
            config.save()
        return redirect('configuracion_tiempos')

    configs_agrupadas = {}
    for tipo_item_key, tipo_item_label in ConfiguracionTiempos.TIPO_ITEM_CHOICES:
        configs_encontradas = ConfiguracionTiempos.objects.filter(tipo_item=tipo_item_key).order_by('tipo_certificado')
        configs_agrupadas[tipo_item_label] = configs_encontradas
    context = { 'configs_agrupadas': configs_agrupadas }
    return render(request, 'configuracion.html', context)

# --- OTRAS VISTAS (no requieren cambios) ---

def vista_por_etapa(request, etapa):
    etapa_upper = etapa.upper(); ordenes = Orden.objects.filter(estado_actual=etapa_upper).order_by('fecha_creacion')
    context = {'ordenes': ordenes, 'nombre_etapa': dict(Orden.ETAPAS).get(etapa_upper), 'etapa_key': etapa}
    if etapa_upper == 'INGRESO':
        plantillas_disponibles = [];
        try: archivos = os.listdir(settings.PLANTILLAS_ROOT); plantillas_disponibles = sorted([f for f in archivos if f.endswith('.xlsx')])
        except FileNotFoundError: pass
        context['plantillas_disponibles'] = plantillas_disponibles
    return render(request, 'vista_etapa.html', context)

def asignar_excel(request, item_id):
    if request.method == 'POST':
        item = get_object_or_404(Item, id=item_id)
        plantilla_nombre = request.POST.get('plantilla_seleccionada')
        if plantilla_nombre:
            nombre_carpeta_orden = f"ORDEN-{item.orden.id:04d}"; nombre_subcarpeta = f"ITEM-{item.numero_item}"
            ruta_subcarpeta = os.path.join(settings.MEDIA_ROOT, nombre_carpeta_orden, nombre_subcarpeta); os.makedirs(ruta_subcarpeta, exist_ok=True)
            ruta_origen = os.path.join(settings.PLANTILLAS_ROOT, plantilla_nombre); nombre_excel_destino = f"datos_item_{item.id}.xlsx"
            ruta_destino = os.path.join(ruta_subcarpeta, nombre_excel_destino)
            if os.path.exists(ruta_origen): shutil.copy(ruta_origen, ruta_destino); item.nombre_excel = nombre_excel_destino; item.save()
    return redirect('vista_etapa', etapa='ingreso')

def detalle_orden(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id)
    if request.method == 'POST' and 'item_id' in request.POST:
        item_id = request.POST.get('item_id'); item = get_object_or_404(Item, id=item_id)
        if 'subir_ingreso' in request.POST:
            if request.FILES.get('qr_code'):
                if item.qr_cargado: item.qr_cargado.delete(save=False)
                item.qr_cargado = request.FILES['qr_code']
            item.save()
        elif 'subir_fotos' in request.POST:
            fotos = request.FILES.getlist('fotos_profesionales');
            for foto in fotos: FotoItem.objects.create(item=item, imagen=foto)
        return redirect('detalle_orden', orden_id=orden.id)
    context = {'orden': orden}
    return render(request, 'detalle_orden.html', context)

def orden_creada_exito(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id)
    context = {'orden': orden}
    return render(request, 'orden_creada_exito.html', context)

def configuracion_tiempos(request):
    if request.method == 'POST':
        for config in ConfiguracionTiempos.objects.all():
            etapa_map = {
                'ingreso': 'tiempo_ingreso', 'foto': 'tiempo_fotografia',
                'revision': 'tiempo_revision', 'impresion': 'tiempo_impresion',
            }
            for form_prefix, model_field in etapa_map.items():
                post_key = f'{form_prefix}_{config.tipo_item}_{config.tipo_certificado}'
                segundos_str = request.POST.get(post_key)
                segundos_value = None
                if segundos_str and segundos_str.strip():
                    try: segundos_value = int(segundos_str)
                    except (ValueError, TypeError): pass
                setattr(config, model_field, segundos_value)
            config.save()
        return redirect('configuracion_tiempos')

    configs_agrupadas = {}
    for tipo_item_key, tipo_item_label in ConfiguracionTiempos.TIPO_ITEM_CHOICES:
        configs_encontradas = ConfiguracionTiempos.objects.filter(tipo_item=tipo_item_key).order_by('tipo_certificado')
        configs_agrupadas[tipo_item_label] = configs_encontradas
        
    context = { 'configs_agrupadas': configs_agrupadas }
    return render(request, 'configuracion.html', context)