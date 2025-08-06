# certificacion/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.utils import timezone
from django.conf import settings
from .models import Orden, Item, FotoItem, ConfiguracionTiempos
from .forms import OrdenForm
import os
import shutil
from datetime import timedelta

def get_tiempo_estimado(tipo_item_key, tipo_cert_key, etapa_key):
    try:
        if tipo_item_key in ['PIEDRA', 'Piedra(s) Suelta(s)']: tipo_item_key = 'PIEDRA'
        config = ConfiguracionTiempos.objects.get(tipo_item=tipo_item_key, tipo_certificado=tipo_cert_key)
        return getattr(config, f'tiempo_{etapa_key.lower()}')
    except (ConfiguracionTiempos.DoesNotExist, AttributeError):
        return 480.0

def dashboard(request):
    ordenes_por_etapa = {}
    for etapa_val, etapa_nom in Orden.ETAPAS:
        if etapa_val != 'FINALIZADA':
            ordenes_por_etapa[etapa_nom] = Orden.objects.filter(estado_actual=etapa_val).order_by('fecha_creacion')
    context = {'ordenes_por_etapa': ordenes_por_etapa}
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
        if form.is_valid():
            orden = form.save(commit=False); orden.estado_actual = 'INGRESO'; orden.save()
            
            # Recolección de datos
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

            for i, data in enumerate(zip(
                tipos_cert, que_es_list, codigos_referencia, tipos_joya, metales,
                gemas_principales, formas_gema, pesos_gema, comentarios_list
            ), start=1):
                (tipo_cert, que_es, codigo_ref, tipo_joya, metal, gema_ppal, 
                 forma, peso, comentarios) = data

                if not gema_ppal and que_es not in ['VERBAL_A_GC', 'REIMPRESION']: continue

                # --- LÓGICA DE CANTIDAD DE GEMAS FINALIZADA ---
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

                item_type_key = que_es
                if que_es == 'JOYA' and tipo_joya == 'SET': item_type_key = 'SET'
                minutos_estimados = get_tiempo_estimado(item_type_key, tipo_cert, 'ingreso')
                fecha_limite = timezone.now() + timedelta(minutes=float(minutos_estimados))
                
                componentes_del_set = request.POST.getlist(f'componentes_set_{item_index}'); componentes_str = ",".join(componentes_del_set) if componentes_del_set else None

                Item.objects.create(
                    orden=orden, numero_item=i, fecha_limite_etapa=fecha_limite,
                    tipo_certificado=tipo_cert, que_es=que_es,
                    codigo_referencia=codigo_ref if que_es in ['VERBAL_A_GC', 'REIMPRESION'] else None,
                    tipo_joya=tipo_joya if que_es == 'JOYA' else None,
                    cantidad_gemas=cantidad_final_gemas,
                    metal=metal if que_es == 'JOYA' else None,
                    componentes_set=componentes_str if que_es == 'JOYA' and tipo_joya == 'SET' else None,
                    gema_principal=gema_ppal if que_es not in ['VERBAL_A_GC', 'REIMPRESION'] else None,
                    forma_gema=forma,
                    peso_gema=peso if peso else None, comentarios=comentarios,
                )
            
            return redirect('orden_creada_exito', orden_id=orden.id)
        
        else:
            gemas_principales = ['Ágata', '...']; formas_gema = ['Baguette', '...']
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
    proxima_etapa = orden.get_proxima_etapa()
    if not proxima_etapa: return redirect('dashboard')
    
    orden.estado_actual = proxima_etapa
    
    if proxima_etapa == 'FINALIZADA':
        orden.fecha_cierre = timezone.now(); orden.items.all().update(fecha_limite_etapa=None)
    else:
        primer_item = orden.items.first()
        if primer_item:
            item_type_key = primer_item.que_es
            if primer_item.que_es == 'JOYA' and primer_item.tipo_joya == 'SET': item_type_key = 'SET'
            tipo_cert_key = primer_item.tipo_certificado
            
            minutos_estimados = get_tiempo_estimado(item_type_key, tipo_cert_key, proxima_etapa)
            fecha_limite = timezone.now() + timedelta(minutes=float(minutos_estimados))
            orden.items.all().update(fecha_limite_etapa=fecha_limite)

    orden.save()
    return redirect('dashboard')

def orden_creada_exito(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id)
    context = {'orden': orden}
    return render(request, 'orden_creada_exito.html', context)

def configuracion_tiempos(request):
    # Lógica para guardar los datos cuando se envía el formulario (POST)
    if request.method == 'POST':
        for config in ConfiguracionTiempos.objects.all():
            prefix = f'{config.tipo_item}_{config.tipo_certificado}'
            
            ingreso_val = request.POST.get(f'ingreso_{prefix}')
            foto_val = request.POST.get(f'foto_{prefix}')
            revision_val = request.POST.get(f'revision_{prefix}')
            impresion_val = request.POST.get(f'impresion_{prefix}')
            
            config.tiempo_ingreso = ingreso_val if ingreso_val and ingreso_val.strip() else 0.0
            config.tiempo_fotografia = foto_val if foto_val and foto_val.strip() else 0.0
            config.tiempo_revision = revision_val if revision_val and revision_val.strip() else 0.0
            config.tiempo_impresion = impresion_val if impresion_val and impresion_val.strip() else 0.0
            config.save()
            
        return redirect('configuracion_tiempos')

    # --- LÓGICA CORREGIDA PARA MOSTRAR LOS DATOS (GET) ---
    
    # 1. Creamos un diccionario vacío para guardar los resultados.
    configs_agrupadas = {}
    
    # 2. Iteramos sobre las OPCIONES de tipo de ítem para mantener el orden.
    for tipo_item_key, tipo_item_label in ConfiguracionTiempos.TIPO_ITEM_CHOICES:
        # 3. Para cada tipo, buscamos en la base de datos todos los registros que coincidan.
        configs_encontradas = ConfiguracionTiempos.objects.filter(tipo_item=tipo_item_key).order_by('tipo_certificado')
        
        # 4. Añadimos la lista de registros encontrados al diccionario.
        configs_agrupadas[tipo_item_label] = configs_encontradas

    # 5. Pasamos el diccionario completo al contexto de la plantilla.
    context = {'configs_agrupadas': configs_agrupadas}
    
    # 6. Renderizamos la plantilla con el contexto.
    return render(request, 'configuracion.html', context)
