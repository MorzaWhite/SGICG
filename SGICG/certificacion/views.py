# certificacion/views.py
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
from decimal import Decimal

# --- FUNCIÓN AUXILIAR PARA TIEMPOS ---
# Esta función no necesita cambios.

def get_tiempo_estimado(tipo_item_key, tipo_cert_key, etapa_key):
    try:
        if tipo_item_key in ['PIEDRA', 'Piedra(s) Suelta(s)']:
            tipo_item_key = 'PIEDRA'
        config = ConfiguracionTiempos.objects.get(tipo_item=tipo_item_key, tipo_certificado=tipo_cert_key)
        # Usamos getattr para obtener el campo de tiempo correcto (ej: 'tiempo_ingreso')
        # La etapa se convierte a minúsculas para que coincida con el nombre del campo.
        # El nombre del campo de fotografía en el modelo es 'tiempo_fotografia'.
        if etapa_key == 'foto':
             etapa_key = 'fotografia'
        return getattr(config, f'tiempo_{etapa_key.lower()}')
    except (ConfiguracionTiempos.DoesNotExist, AttributeError):
        # Si no hay configuración, devuelve un valor por defecto (ej: 8 horas)
        return 8.0

# --- FUNCIÓN AUXILIAR PARA LA COLA DE TRABAJO ---
# Esta función no necesita cambios.

def get_ultimo_tiempo_ocupado():
    items_activos = Item.objects.filter(orden__estado_actual__in=['INGRESO', 'FOTOGRAFIA', 'REVISION', 'IMPRESION'])
    resultado = items_activos.aggregate(max_fecha=Max('fecha_limite_etapa'))
    ultima_fecha = resultado.get('max_fecha')
    
    if ultima_fecha:
        return ultima_fecha
    return timezone.now()


# --- VISTA PARA CREAR ÓRDENES (RECONSTRUIDA) ---

class CrearOrdenView(View):
    def get(self, request):
        form = OrdenForm()
        # Estas listas se usan para poblar los menús desplegables en el formulario.
        gemas_principales = ['Ágata', 'Aguamarina', 'Alejandrita', 'Almandino - Espesartina', 'Amatista', 'Amazonita', 'Ankerita', 'Antracita', 'Apatito', 'Azabache', 'Berilo', 'Calcedonia', 'Calcopirita', 'Carbón', 'Citrino', 'Coral', 'Cordierita', 'Corindón', 'Crisoberilo', 'Cristal de roca', 'Cuarzo', 'Dolomita', 'Espinela', 'Euclasa', 'Feldespato', 'Fluorita', 'Fuchsita', 'Granate', 'Grosular', 'Grosularia - Andradita', 'Grosularia', 'Jacinta', 'Jaspe', 'Malaquita', 'Mica', 'Microclina', 'Moissanita', 'Obsidiana', 'Ónix', 'Ópalo', 'Paraiba', 'Perla Cultivada', 'Pirita', 'Piropo - Almandino', 'Rubí Glassfilled', 'Rubí', 'Rubí Estrella', 'Tanzanita', 'Trilitionita', 'Tsavorita', 'Turmalina', 'Vidrio', 'Zafiro', 'Zafiro cambio de color', 'Zafiro estrella', 'Zircón', 'Zoisita', 'Vivianita', 'Topacio', 'Cuarzo ahumado', 'Almandino - Piropo', 'Espesartita - Piropo', 'Zirconia cubica', 'Diamante', 'Esmeralda']
        formas_gema = ['Baguette', 'Barroco', 'Briolette', 'Caballo', 'Cilíndrica', 'Circular', 'Cojín', 'Corazón', 'Cuadrada', 'Esfera', 'Esmeralda', 'Fantasía', 'Hexagonal', 'Lágrima', 'Marquis', 'Ninguno', 'Óvalo', 'Prisma ditrigonal', 'Prisma hexagonal', 'Prisma Piramidal', 'Prisma Tetragonal', 'Rectangular', 'Redonda', 'Rostro', 'Trapecio', 'Trillion', 'Hoja', 'Cabuchon', 'Prisma dihexagonal', 'Caballo de Mar', 'Varios']
        context = {'form': form, 'gemas_principales': sorted(gemas_principales), 'formas_gema': sorted(formas_gema)}
        return render(request, 'crear_orden.html', context)

    def post(self, request):
        form = OrdenForm(request.POST)
        if form.is_valid():
            orden = form.save(commit=False)
            orden.estado_actual = 'INGRESO'
            orden.save()

        # Lee todos los datos de los ítems enviados desde el formulario.
        tipos_cert = request.POST.getlist('tipo_certificado')
        que_es_list = request.POST.getlist('que_es')
        codigos_referencia = request.POST.getlist('codigo_referencia')
        tipos_joya = request.POST.getlist('tipo_joya')
        metales = request.POST.getlist('metal')
        gemas_principales = request.POST.getlist('gema_principal')
        formas_gema = request.POST.getlist('forma_gema')
        pesos_gema = request.POST.getlist('peso_gema')
        comentarios_list = request.POST.getlist('comentarios')

        nombre_carpeta_orden = f"ORDEN-{orden.id:04d}"
        ruta_orden = os.path.join(settings.MEDIA_ROOT, nombre_carpeta_orden)
        os.makedirs(ruta_orden, exist_ok=True)

        # Obtenemos el fin de la cola de trabajo UNA SOLA VEZ, antes de empezar.
        punto_de_partida = get_ultimo_tiempo_ocupado()

        # Procesamos cada ítem enviado en el formulario.
        for i, data in enumerate(zip(
            tipos_cert, que_es_list, codigos_referencia, tipos_joya, metales,
            gemas_principales, formas_gema, pesos_gema, comentarios_list
        ), start=1):
            
            (tipo_cert, que_es, codigo_ref, tipo_joya, metal, gema_ppal, 
             forma, peso, comentarios) = data

            if not gema_ppal and que_es not in ['VERBAL_A_GC', 'REIMPRESION']:
                continue

            # --- INICIO DE LA LÓGICA DE CANTIDAD (DE TU CÓDIGO ORIGINAL) ---
            # Esta es la parte crucial que faltaba.
            cantidad_final_gemas = 1
            item_index = i
            
            if que_es == 'LOTE':
                cantidad_final_gemas = request.POST.get(f'cantidad_gemas_varios_{item_index}') or 1
            elif tipo_cert in ['GC_SENCILLA', 'GC_COMPLETA']:
                val_gc = request.POST.get(f'cantidad_gc_group_{item_index}')
                if val_gc == 'varios':
                    cantidad_final_gemas = request.POST.get(f'cantidad_gemas_varios_{item_index}') or 1
                elif val_gc:
                    cantidad_final_gemas = int(val_gc)
            elif tipo_cert == 'ESCRITO':
                vals_escrito = request.POST.getlist(f'cantidad_escrito_chk_{item_index}')
                if 'varios' in vals_escrito:
                    cantidad_final_gemas = request.POST.get(f'cantidad_gemas_varios_{item_index}') or 1
                else:
                    cantidad_final_gemas = len(vals_escrito) if vals_escrito else 1
            elif tipo_cert == 'DIAMANTE':
                val_diamante = request.POST.get(f'cantidad_diamante_group_{item_index}')
                if val_diamante == 'varios':
                    cantidad_final_gemas = request.POST.get(f'cantidad_gemas_varios_{item_index}') or 1
                elif val_diamante:
                    cantidad_final_gemas = int(val_diamante)
            # --- FIN DE LA LÓGICA DE CANTIDAD ---

            # Calculamos la duración TOTAL para este ítem sumando todas sus etapas.
            duracion_total_item = 0
            etapas_a_sumar = ['ingreso', 'fotografia', 'revision', 'impresion']
            
            item_type_key = que_es
            if que_es == 'JOYA' and tipo_joya == 'SET':
                item_type_key = 'SET'

            for etapa in etapas_a_sumar:
                tiempo_etapa = get_tiempo_estimado(item_type_key, tipo_cert, etapa)
                if tiempo_etapa:
                    # (Asegúrate de que 'hours' coincida con tu configuración)
                    duracion_total_item += float(tiempo_etapa)

            # Calculamos la fecha límite para ESTE ítem.
            fecha_limite = punto_de_partida + timedelta(hours=duracion_total_item)
            
            # Actualizamos el punto de partida para que el SIGUIENTE ítem se sume correctamente.
            punto_de_partida = fecha_limite
            
            componentes_del_set = request.POST.getlist(f'componentes_set_{i}')
            componentes_str = ",".join(componentes_del_set) if componentes_del_set else None

            Item.objects.create(
                orden=orden, numero_item=i, 
                fecha_limite_etapa=fecha_limite,
                tipo_certificado=tipo_cert, 
                que_es=que_es,
                codigo_referencia=codigo_ref if que_es in ['VERBAL_A_GC', 'REIMPRESION'] else None,
                tipo_joya=tipo_joya if que_es == 'JOYA' else None,
                cantidad_gemas=cantidad_final_gemas, # Usamos la cantidad calculada
                metal=metal if que_es == 'JOYA' else None,
                componentes_set=componentes_str if que_es == 'JOYA' and tipo_joya == 'SET' else None,
                gema_principal=gema_ppal if que_es not in ['VERBAL_A_GC', 'REIMPRESION'] else None,
                forma_gema=forma,
                peso_gema=peso if peso else None, 
                comentarios=comentarios,
            )
        
            return redirect('orden_creada_exito', orden_id=orden.id)
    
        else:
        # Si el formulario no es válido, se vuelve a mostrar con los errores.
            gemas_principales = ['Ágata', '...'] # Simplificado
            formas_gema = ['Baguette', '...'] # Simplificado
            context = {'form': form, 'gemas_principales': sorted(gemas_principales), 'formas_gema': sorted(formas_gema)}
        return render(request, 'crear_orden.html', context)


# --- VISTA PARA AVANZAR ETAPAS (SIMPLIFICADA Y FINAL) ---

def avanzar_etapa(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id)
    proxima_etapa = orden.get_proxima_etapa()

    if not proxima_etapa:
        return redirect('dashboard')

    # Simplemente actualizamos el estado de la orden.
    # NO HACEMOS NINGÚN CÁLCULO DE TIEMPO.
    orden.estado_actual = proxima_etapa
    
    # Si la orden llega a la etapa final, limpiamos su fecha de cierre y fecha límite.
    if proxima_etapa == 'FINALIZADA':
        orden.fecha_cierre = timezone.now()
        orden.items.all().update(fecha_limite_etapa=None)
    
    orden.save()
    return redirect('dashboard')


# --- OTRAS VISTAS (SIN CAMBIOS) ---
# Aquí irían el resto de tus vistas: dashboard, vista_por_etapa, detalle_orden, etc.
# Asegúrate de que la vista 'dashboard' use la versión que ordena con Python para evitar duplicados.

def dashboard(request):
    ordenes_sin_ordenar = Orden.objects.filter(
        estado_actual__in=['INGRESO', 'FOTOGRAFIA', 'REVISION', 'IMPRESION']
    ).prefetch_related('items')

    try:
        ordenes_activas = sorted(
            list(ordenes_sin_ordenar), 
            key=lambda orden: orden.items.first().fecha_limite_etapa if orden.items.first() and orden.items.first().fecha_limite_etapa else timezone.now()
        )
    except Exception:
        ordenes_activas = list(ordenes_sin_ordenar)

    context = {'ordenes_activas': ordenes_activas}
    return render(request, 'dashboard.html', context)

def vista_por_etapa(request, etapa):
    etapa_upper = etapa.upper(); ordenes = Orden.objects.filter(estado_actual=etapa_upper).order_by('fecha_creacion')
    context = {'ordenes': ordenes, 'nombre_etapa': dict(Orden.ETAPAS).get(etapa_upper), 'etapa_key': etapa}
    if etapa_upper == 'INGRESO':
        plantillas_disponibles = [];
        try: archivos = os.listdir(settings.PLANTILLAS_ROOT); plantillas_disponibles = sorted([f for f in archivos if f.endswith('.xlsx')])
        except FileNotFoundError: pass
        context['plantillas_disponibles'] = plantillas_disponibles
    return render(request, 'vista_etapa.html', context)

class CrearOrdenView(View):
    def get(self, request):
        form = OrdenForm()
        gemas_principales = ['Ágata', 'Aguamarina', 'Alejandrita', 'Almandino - Espesartina', 'Amatista', 'Amazonita', 'Ankerita', 'Antracita', 'Apatito', 'Azabache', 'Berilo', 'Calcedonia', 'Calcopirita', 'Carbón', 'Citrino', 'Coral', 'Cordierita', 'Corindón', 'Crisoberilo', 'Cristal de roca', 'Cuarzo', 'Dolomita', 'Espinela', 'Euclasa', 'Feldespato', 'Fluorita', 'Fuchsita', 'Granate', 'Grosular', 'Grosularia - Andradita', 'Grosularia', 'Jacinta', 'Jaspe', 'Malaquita', 'Mica', 'Microclina', 'Moissanita', 'Obsidiana', 'Ónix', 'Ópalo', 'Paraiba', 'Perla Cultivada', 'Pirita', 'Piropo - Almandino', 'Rubí Glassfilled', 'Rubí', 'Rubí Estrella', 'Tanzanita', 'Trilitionita', 'Tsavorita', 'Turmalina', 'Vidrio', 'Zafiro', 'Zafiro cambio de color', 'Zafiro estrella', 'Zircón', 'Zoisita', 'Vivianita', 'Topacio', 'Cuarzo ahumado', 'Almandino - Piropo', 'Espesartita - Piropo', 'Zirconia cubica', 'Diamante', 'Esmeralda']
        formas_gema = ['Baguette', 'Barroco', 'Briolette', 'Caballo', 'Cilíndrica', 'Circular', 'Cojín', 'Corazón', 'Cuadrada', 'Esfera', 'Esmeralda', 'Fantasía', 'Hexagonal', 'Lágrima', 'Marquis', 'Ninguno', 'Óvalo', 'Prisma ditrigonal', 'Prisma hexagonal', 'Prisma Piramidal', 'Prisma Tetragonal', 'Rectangular', 'Redonda', 'Rostro', 'Trapecio', 'Trillion', 'Hoja', 'Cabuchon', 'Prisma dihexagonal', 'Caballo de Mar', 'Varios']
        context = {'form': form, 'gemas_principales': sorted(gemas_principales), 'formas_gema': sorted(formas_gema)}
        return render(request, 'crear_orden.html', context)

    
    def post(self, request):
        form = OrdenForm(request.POST)
    
    # 1. Verificamos si el formulario principal (el número de orden) es válido.
        if form.is_valid():
            orden = form.save(commit=False)
            orden.estado_actual = 'INGRESO'
            orden.save()
        
        # --- TODA LA LÓGICA DE LOS ÍTEMS DEBE IR DENTRO DE ESTE BLOQUE ---

        # 2. Leemos todos los datos de los ítems desde el formulario.
        tipos_cert = request.POST.getlist('tipo_certificado')
        que_es_list = request.POST.getlist('que_es')
        codigos_referencia = request.POST.getlist('codigo_referencia')
        tipos_joya = request.POST.getlist('tipo_joya')
        metales = request.POST.getlist('metal')
        gemas_principales = request.POST.getlist('gema_principal')
        formas_gema = request.POST.getlist('forma_gema')
        pesos_gema = request.POST.getlist('peso_gema')
        comentarios_list = request.POST.getlist('comentarios')

        # 3. Creamos la carpeta para la orden.
        nombre_carpeta_orden = f"ORDEN-{orden.id:04d}"
        ruta_orden = os.path.join(settings.MEDIA_ROOT, nombre_carpeta_orden)
        os.makedirs(ruta_orden, exist_ok=True)

        # 4. Obtenemos el fin de la cola de trabajo UNA SOLA VEZ.
        punto_de_partida = get_ultimo_tiempo_ocupado()

        # 5. Procesamos cada ítem enviado.
        for i, data in enumerate(zip(
            tipos_cert, que_es_list, codigos_referencia, tipos_joya, metales,
            gemas_principales, formas_gema, pesos_gema, comentarios_list
        ), start=1):
            
            (tipo_cert, que_es, codigo_ref, tipo_joya, metal, gema_ppal, 
             forma, peso, comentarios) = data

            if not gema_ppal and que_es not in ['VERBAL_A_GC', 'REIMPRESION']:
                continue

            # 6. Calculamos la duración TOTAL para este ítem.
            duracion_total_item = 0
            etapas_a_sumar = ['ingreso', 'fotografia', 'revision', 'impresion']
            
            item_type_key = que_es
            if que_es == 'JOYA' and tipo_joya == 'SET':
                item_type_key = 'SET'

            for etapa in etapas_a_sumar:
                tiempo_etapa = get_tiempo_estimado(item_type_key, tipo_cert, etapa)
                if tiempo_etapa:
                    duracion_total_item += float(tiempo_etapa)

            # 7. Calculamos la fecha límite y actualizamos el punto de partida para el siguiente ítem.
            fecha_limite = punto_de_partida + timedelta(hours=duracion_total_item)
            punto_de_partida = fecha_limite
            
            # (Aquí va tu lógica original para obtener la cantidad de gemas y componentes del set)
            cantidad_final_gemas = 1 # Reemplaza esto con tu lógica completa
            componentes_del_set = request.POST.getlist(f'componentes_set_{i}')
            componentes_str = ",".join(componentes_del_set) if componentes_del_set else None

            # 8. Creamos el objeto Item en la base de datos.
            Item.objects.create(
                orden=orden, numero_item=i, 
                fecha_limite_etapa=fecha_limite,
                tipo_certificado=tipo_cert, 
                que_es=que_es,
                codigo_referencia=codigo_ref if que_es in ['VERBAL_A_GC', 'REIMPRESION'] else None,
                tipo_joya=tipo_joya if que_es == 'JOYA' else None,
                cantidad_gemas=cantidad_final_gemas,
                metal=metal if que_es == 'JOYA' else None,
                componentes_set=componentes_str if que_es == 'JOYA' and tipo_joya == 'SET' else None,
                gema_principal=gema_ppal if que_es not in ['VERBAL_A_GC', 'REIMPRESION'] else None,
                forma_gema=forma,
                peso_gema=peso if peso else None, 
                comentarios=comentarios,
            )
        
        # 9. Redirigimos a la página de éxito.
            return redirect('orden_creada_exito', orden_id=orden.id)
    
    # Si el formulario principal no es válido, se renderiza de nuevo la página con los errores.
        else:
            gemas_principales = ['Ágata', '...'] # Simplificado
            formas_gema = ['Baguette', '...'] # Simplificado
            context = {'form': form, 'gemas_principales': sorted(gemas_principales), 'formas_gema': sorted(formas_gema)}
            return render(request, 'crear_orden.html', context)
        
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

def avanzar_etapa(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id)
    
    etapa_terminada = orden.estado_actual
    proxima_etapa = orden.get_proxima_etapa()

    if not proxima_etapa:
        return redirect('dashboard')

    # --- INICIO DE LA LÓGICA CORREGIDA ---

    # 1. Obtenemos la duración de la etapa que estamos terminando.
    primer_item = orden.items.first()
    if primer_item:
        item_type_key = primer_item.que_es
        if primer_item.que_es == 'JOYA' and primer_item.tipo_joya == 'SET':
            item_type_key = 'SET'
        tipo_cert_key = primer_item.tipo_certificado
        
        duracion_etapa_terminada = get_tiempo_estimado(item_type_key, tipo_cert_key, etapa_terminada)
        
        if duracion_etapa_terminada:
            # 2. Creamos el objeto 'timedelta' para la resta.
            #    (Recuerda cambiar 'hours' por 'minutes' si es necesario)
            tiempo_a_restar = timedelta(hours=float(duracion_etapa_terminada))
            
            # 3. ¡CRÍTICO! Actualizamos TODAS las órdenes activas, adelantando su fecha límite.
            #    Usamos F() para hacer la resta directamente en la base de datos.
            Item.objects.filter(
                orden__estado_actual__in=['INGRESO', 'FOTOGRAFIA', 'REVISION', 'IMPRESION']
            ).update(
                fecha_limite_etapa=F('fecha_limite_etapa') - tiempo_a_restar
            )

    # 4. Actualizamos el estado de la orden actual.
    orden.estado_actual = proxima_etapa
    
    # 5. Si la orden se finaliza completamente, su tiempo ya no cuenta.
    if proxima_etapa == 'FINALIZADA':
        orden.fecha_cierre = timezone.now()
        orden.items.all().update(fecha_limite_etapa=None)

    # --- FIN DE LA LÓGICA CORREGIDA ---

    orden.save()
    return redirect('dashboard')

def orden_creada_exito(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id)
    context = {'orden': orden}
    return render(request, 'orden_creada_exito.html', context)


def configuracion_tiempos(request):
    if request.method == 'POST':
        # Un mapa para traducir el prefijo del formulario al nombre del campo en el modelo
        etapa_map = {
            'ingreso': 'tiempo_ingreso',
            'foto': 'tiempo_fotografia',
            'revision': 'tiempo_revision',
            'impresion': 'tiempo_impresion',
        }

        for config in ConfiguracionTiempos.objects.all():
            for form_prefix, model_field in etapa_map.items():
                # Construye el nombre del campo que viene del formulario
                post_key = f'{form_prefix}_{config.tipo_item}_{config.tipo_certificado}'
                
                # Obtiene el valor
                value_str = request.POST.get(post_key)
                
                # Prepara el valor final, por defecto nulo
                new_value = None
                if value_str:
                    try:
                        # Si hay un valor, lo convierte a Decimal
                        new_value = Decimal(value_str)
                    except:
                        # Si falla la conversión (ej: texto), se queda como nulo
                        pass
                
                # Establece el valor en el objeto y lo guarda
                setattr(config, model_field, new_value)
            
            config.save()
            
        return redirect('configuracion_tiempos')

    # La lógica para mostrar la página (GET) se queda como estaba
    configs_agrupadas = {}
    for tipo_item_key, tipo_item_label in ConfiguracionTiempos.TIPO_ITEM_CHOICES:
        configs_encontradas = ConfiguracionTiempos.objects.filter(tipo_item=tipo_item_key).order_by('tipo_certificado')
        configs_agrupadas[tipo_item_label] = configs_encontradas
    context = {'configs_agrupadas': configs_agrupadas}
    return render(request, 'configuracion.html', context)