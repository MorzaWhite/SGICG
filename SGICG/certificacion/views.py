# certificacion/views.py

import os
import shutil
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.utils import timezone
from django.conf import settings
from django.db.models import Max, F, Q
from django.contrib import messages
from django.core.cache import cache
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.utils.text import slugify
from django.db import transaction
from django.core.exceptions import ValidationError

from .models import Orden, Item, FotoItem, ConfiguracionTiempos
from .forms import OrdenForm

# Configurar logging
logger = logging.getLogger(__name__)

# --- CONSTANTES ---
TIEMPO_DEFAULT_SEGUNDOS = 28800  # 8 horas por defecto
CACHE_TIMEOUT = 3600  # 1 hora
MAX_ITEMS_PER_ORDER = 50

# --- FUNCIONES AUXILIARES MEJORADAS ---

class TiempoCalculator:
    """Clase para manejar cálculos de tiempo de forma centralizada"""
    
    @staticmethod
    def get_tiempo_estimado(tipo_item_key, tipo_cert_key, etapa_key):
        """
        Obtiene el tiempo configurado en segundos con cache mejorado.
        
        Args:
            tipo_item_key: Tipo de item (PIEDRA, JOYA, SET, LOTE)
            tipo_cert_key: Tipo de certificado (GC_SENCILLA, etc.)
            etapa_key: Etapa (INGRESO, FOTOGRAFIA, etc.)
        
        Returns:
            int: Tiempo en segundos
        """
        cache_key = f"tiempo_{tipo_item_key}_{tipo_cert_key}_{etapa_key}"
        tiempo = cache.get(cache_key)
        
        if tiempo is None:
            try:
                # Normalizar el tipo de item
                if tipo_item_key in ['PIEDRA', 'Piedra(s) Suelta(s)']:
                    tipo_item_key = 'PIEDRA'
                
                config = ConfiguracionTiempos.objects.get(
                    tipo_item=tipo_item_key, 
                    tipo_certificado=tipo_cert_key
                )
                
                field_name = f'tiempo_{etapa_key.lower()}'
                tiempo = getattr(config, field_name, None)
                
                if tiempo is None:
                    tiempo = TIEMPO_DEFAULT_SEGUNDOS
                    logger.warning(
                        f"Tiempo no configurado para {tipo_item_key}-{tipo_cert_key}-{etapa_key}, "
                        f"usando default: {TIEMPO_DEFAULT_SEGUNDOS}s"
                    )
                
                # Cache por 1 hora
                cache.set(cache_key, tiempo, CACHE_TIMEOUT)
                
            except ConfiguracionTiempos.DoesNotExist:
                tiempo = TIEMPO_DEFAULT_SEGUNDOS
                logger.warning(
                    f"Configuración no encontrada: {tipo_item_key}-{tipo_cert_key}-{etapa_key}"
                )
                # Cache el default también
                cache.set(cache_key, tiempo, CACHE_TIMEOUT)
            
            except AttributeError:
                tiempo = TIEMPO_DEFAULT_SEGUNDOS
                logger.error(
                    f"Atributo no encontrado: tiempo_{etapa_key.lower()}"
                )
        
        return int(tiempo) if tiempo else TIEMPO_DEFAULT_SEGUNDOS
    
    @staticmethod
    def calcular_duracion_total_item(tipo_item_key, tipo_cert_key):
        """Calcula la duración total de un ítem sumando todas las etapas"""
        etapas = ['INGRESO', 'FOTOGRAFIA', 'REVISION', 'IMPRESION']
        total = 0
        
        for etapa in etapas:
            tiempo_etapa = TiempoCalculator.get_tiempo_estimado(
                tipo_item_key, tipo_cert_key, etapa
            )
            total += tiempo_etapa
        
        return total


class OrdenManager:
    """Clase para manejar operaciones complejas con órdenes"""
    
    @staticmethod
    def get_ultimo_tiempo_ocupado():
        """
        Busca la fecha límite más lejana para saber cuándo termina la cola.
        """
        try:
            resultado = Item.objects.filter(
                orden__estado_actual__in=['INGRESO', 'FOTOGRAFIA', 'REVISION', 'IMPRESION'],
                fecha_limite_etapa__isnull=False
            ).aggregate(max_fecha=Max('fecha_limite_etapa'))
            
            ultima_fecha = resultado.get('max_fecha')
            
            if ultima_fecha and ultima_fecha > timezone.now():
                return ultima_fecha
            return timezone.now()
            
        except Exception as e:
            logger.error(f"Error al calcular último tiempo ocupado: {str(e)}")
            return timezone.now()
    
    @staticmethod
    def get_ordenes_con_filtros(search=None, etapa_filter=None):
        """Obtiene órdenes aplicando filtros con optimizaciones"""
        queryset = Orden.objects.select_related().prefetch_related(
            'items__fotos'
        ).filter(
            estado_actual__in=['INGRESO', 'FOTOGRAFIA', 'REVISION', 'IMPRESION']
        )
        
        if search:
            queryset = queryset.filter(
                Q(numero_orden_facturacion__icontains=search) |
                Q(items__gema_principal__icontains=search) |
                Q(items__codigo_referencia__icontains=search)
            ).distinct()
        
        if etapa_filter and etapa_filter in dict(Orden.ETAPAS).keys():
            queryset = queryset.filter(estado_actual=etapa_filter)
        
        return queryset


class FileManager:
    """Clase para manejar operaciones con archivos"""
    
    @staticmethod
    def safe_filename(filename):
        """Genera un nombre de archivo seguro"""
        if not filename:
            return "archivo_sin_nombre"
        
        name, ext = os.path.splitext(filename)
        safe_name = slugify(name) or "archivo"
        return f"{safe_name}{ext.lower()}"
    
    @staticmethod
    def validar_archivo_imagen(archivo, max_size_mb=5):
        """
        Valida que el archivo sea una imagen válida.
        
        Returns:
            tuple: (es_valido, mensaje_error)
        """
        if not archivo:
            return False, "No se proporcionó archivo"
        
        # Validar tipo de archivo
        allowed_types = ['image/jpeg', 'image/png', 'image/jpg', 'image/webp']
        if archivo.content_type not in allowed_types:
            return False, "Solo se permiten archivos de imagen (JPG, PNG, WEBP)"
        
        # Validar tamaño
        max_size = max_size_mb * 1024 * 1024
        if archivo.size > max_size:
            return False, f"El archivo es demasiado grande (máximo {max_size_mb}MB)"
        
        return True, ""
    
    @staticmethod
    def crear_carpeta_orden(orden_id):
        """Crea la estructura de carpetas para una orden"""
        nombre_carpeta_orden = f"ORDEN-{orden_id:04d}"
        ruta_orden = os.path.join(settings.MEDIA_ROOT, nombre_carpeta_orden)
        os.makedirs(ruta_orden, exist_ok=True)
        return ruta_orden


# --- VISTAS PRINCIPALES ---

def dashboard(request):
    """Dashboard principal optimizado con filtros y paginación"""
    try:
        # Obtener parámetros
        search = request.GET.get('search', '').strip()
        etapa_filter = request.GET.get('etapa', '')
        page_number = request.GET.get('page', 1)
        
        # Obtener órdenes con filtros
        ordenes_queryset = OrdenManager.get_ordenes_con_filtros(search, etapa_filter)
        
        # Ordenar por fecha de entrega más próxima
        def get_fecha_ordenamiento(orden):
            ultimo_item = orden.items.order_by('fecha_limite_etapa').last()
            if ultimo_item and ultimo_item.fecha_limite_etapa:
                return ultimo_item.fecha_limite_etapa
            return timezone.now() + timedelta(days=9999)
        
        ordenes_list = sorted(list(ordenes_queryset), key=get_fecha_ordenamiento)
        
        # Paginación
        paginator = Paginator(ordenes_list, 10)
        ordenes_page = paginator.get_page(page_number)
        
        # Estadísticas
        stats = {
            'total_activas': len(ordenes_list),
            'retrasadas': len([o for o in ordenes_list if o.tiene_items_retrasados()]),
        }
        
        # Estadísticas por etapa
        for etapa_key, etapa_label in Orden.ETAPAS:
            if etapa_key != 'FINALIZADA':
                count = ordenes_queryset.filter(estado_actual=etapa_key).count()
                stats[etapa_key.lower()] = count
        
        context = {
            'ordenes_activas': ordenes_page,
            'search': search,
            'etapa_filter': etapa_filter,
            'stats': stats,
            'etapas_choices': [e for e in Orden.ETAPAS if e[0] != 'FINALIZADA'],
        }
        
        return render(request, 'dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Error en dashboard: {str(e)}")
        messages.error(request, "Error al cargar el dashboard.")
        return render(request, 'dashboard.html', {
            'ordenes_activas': [],
            'stats': {},
            'etapas_choices': []
        })


class CrearOrdenView(View):
    """Vista optimizada para crear órdenes con captura completa de datos"""
    
    def get(self, request):
        form = OrdenForm()
        context = self.get_context_data(form)
        return render(request, 'crear_orden.html', context)
    
    def post(self, request):
        
        
        form = OrdenForm(request.POST)
        
        
        if not form.is_valid():
            context = self.get_context_data(form)
            return render(request, 'crear_orden.html', context)
        
        try:
            with transaction.atomic():
                
                # Validar datos de ítems
                validation_result = self._validar_items_data(request.POST)
                
                if not validation_result['valido']:
                    messages.error(request, validation_result['error'])
                    context = self.get_context_data(form)
                    return render(request, 'crear_orden.html', context)
                
                # Crear orden con ítems
                orden = self._crear_orden_con_items(form, request.POST)
                
                # Verificar que la orden se creó correctamente
                if not orden or not orden.id:
                    raise Exception("La orden no se creó correctamente")
                
                # Verificar que se crearon ítems
                items_count = orden.items.count()
                
                if items_count == 0:
                    raise Exception("No se crearon ítems para la orden")
                
                # Limpiar cache
                cache.clear()
                
                message = f"Orden {orden.numero_orden_facturacion} creada exitosamente con {items_count} ítems"
                messages.success(request, message)
                
                return redirect('orden_creada_exito', orden_id=orden.id)
                
        except ValidationError as e:
            messages.error(request, f"Error de validación: {str(e)}")
        except Exception as e:
            import traceback
            messages.error(request, f"Error interno: {str(e)}. Contacta al administrador.")
        
        context = self.get_context_data(form)
        return render(request, 'crear_orden.html', context)
    
    def _validar_items_data(self, post_data):
        """Valida los datos de los ítems antes de crear la orden"""
        tipos_cert = post_data.getlist('tipo_certificado')
        que_es_list = post_data.getlist('que_es')
        gemas_principales = post_data.getlist('gema_principal')
        codigos_referencia = post_data.getlist('codigo_referencia')
        
        if not tipos_cert:
            return {'valido': False, 'error': 'Debe agregar al menos un ítem'}
        
        if len(tipos_cert) > MAX_ITEMS_PER_ORDER:
            return {'valido': False, 'error': f'Máximo {MAX_ITEMS_PER_ORDER} ítems por orden'}
        
        # Validar que las listas tengan la misma longitud
        listas = [tipos_cert, que_es_list, gemas_principales, codigos_referencia]
        longitudes = [len(lista) for lista in listas]
        if not all(l == longitudes[0] for l in longitudes):
            return {'valido': False, 'error': 'Error en datos de ítems: listas con longitudes diferentes'}
        
        for i, (tipo_cert, que_es, gema_ppal, codigo_ref) in enumerate(zip(
            tipos_cert, que_es_list, gemas_principales, codigos_referencia
        ), start=1):
            
            if not tipo_cert or not tipo_cert.strip():
                return {'valido': False, 'error': f'El ítem {i} debe tener tipo de certificado'}
            
            if not que_es or not que_es.strip():
                return {'valido': False, 'error': f'El ítem {i} debe tener definido "qué es"'}
            
            if que_es in ['VERBAL_A_GC', 'REIMPRESION']:
                if not codigo_ref or not codigo_ref.strip():
                    return {'valido': False, 'error': f'El ítem {i} requiere código de referencia'}
            else:
                if not gema_ppal or not gema_ppal.strip():
                    return {'valido': False, 'error': f'El ítem {i} requiere gema principal'}
        
        return {'valido': True, 'error': ''}
    
    def _crear_orden_con_items(self, form, post_data):
        """Crea la orden y todos sus ítems de forma transaccional"""
        print("=== CREANDO ORDEN PRINCIPAL ===")
        
        # Crear la orden
        orden = form.save(commit=False)
        orden.estado_actual = 'INGRESO'
        orden.fecha_creacion = timezone.now()
        orden.save()
        
        print(f"Orden guardada con ID: {orden.id}")
        
        # Crear estructura de carpetas
        try:
            FileManager.crear_carpeta_orden(orden.id)
            print("Carpeta creada")
        except Exception as e:
            print(f"Error creando carpeta: {e}")
            pass
        
        # Extraer y crear ítems con datos completos
        print("=== EXTRAYENDO DATOS DE ÍTEMS ===")
        items_data = self._extraer_items_completos(post_data)
        print(f"Items data extraídos: {len(items_data)}")
        
        punto_de_partida = OrdenManager.get_ultimo_tiempo_ocupado()
        print(f"Punto de partida: {punto_de_partida}")
        
        items_creados = 0
        for i, data in enumerate(items_data, start=1):
            print(f"=== CREANDO ÍTEM {i} ===")
            print(f"Data del ítem: {data}")
            try:
                item = self._crear_item_completo(orden, i, data, punto_de_partida)
                if item and item.id:
                    items_creados += 1
                    print(f"Ítem {i} creado con ID: {item.id}")
                    # Actualizar punto de partida para el siguiente ítem
                    if item.fecha_limite_etapa:
                        punto_de_partida = item.fecha_limite_etapa
                else:
                    print(f"ERROR: Ítem {i} no se creó correctamente")
            except Exception as e:
                print(f"Error creando ítem {i}: {e}")
                import traceback
                print(f"Traceback: {traceback.format_exc()}")
                raise e
        
        print(f"=== ÍTEMS CREADOS: {items_creados} ===")
        
        # Recargar la orden para asegurar que tenga los items
        orden.refresh_from_db()
        return orden
    
    def _extraer_items_completos(self, post_data):
        """Extrae todos los datos del formulario incluyendo cantidades y componentes"""
        campos_simples = [
            'tipo_certificado', 'que_es', 'codigo_referencia', 'tipo_joya',
            'metal', 'gema_principal', 'forma_gema', 'peso_gema', 'comentarios'
        ]
        
        items_data = []
        max_items = len(post_data.getlist('tipo_certificado'))
        
        for i in range(max_items):
            item_data = {}
            item_index = i + 1
            
            # Extraer campos simples
            for campo in campos_simples:
                valores = post_data.getlist(campo)
                item_data[campo] = valores[i].strip() if i < len(valores) and valores[i] else ''
            
            # Extraer componentes del set
            componentes_key = f'componentes_set_{item_index}'
            componentes = post_data.getlist(componentes_key)
            item_data['componentes_set'] = [c for c in componentes if c]
            
            # Extraer cantidades según tipo de certificado
            item_data['cantidad_info'] = self._extraer_cantidad_info(post_data, item_index, item_data['tipo_certificado'])
            
            # Solo agregar items que tengan al menos tipo de certificado
            if item_data.get('tipo_certificado'):
                items_data.append(item_data)
        
        return items_data
    
    def _extraer_cantidad_info(self, post_data, item_index, tipo_cert):
        """Extrae la información de cantidad específica según el tipo de certificado"""
        cantidad_info = {
            'tipo': None,
            'valor': None,
            'detalle': ''
        }
        
        if tipo_cert in ['GC_SENCILLA', 'GC_COMPLETA']:
            # Radio buttons para GC
            gc_key = f'cantidad_gc_group_{item_index}'
            seleccion = post_data.get(gc_key, '1')
            if seleccion == '1':
                cantidad_info = {'tipo': 'individual', 'valor': 1, 'detalle': '1 gema'}
            elif seleccion == '2':
                cantidad_info = {'tipo': 'par', 'valor': 2, 'detalle': 'Par de gemas'}
            elif seleccion == '3':
                cantidad_info = {'tipo': 'trio', 'valor': 3, 'detalle': 'Trío de gemas'}
            elif seleccion == 'varios':
                varios_key = f'cantidad_gemas_varios_{item_index}'
                cantidad_varios = post_data.get(varios_key, '')
                cantidad_info = {'tipo': 'varios', 'valor': cantidad_varios, 'detalle': f'{cantidad_varios} gemas' if cantidad_varios else 'Varias gemas'}
                
        elif tipo_cert == 'ESCRITO':
            # Checkboxes para ESCRITO
            escrito_keys = [f'cantidad_escrito_chk_{item_index}']
            cantidades = []
            for key in escrito_keys:
                valores = post_data.getlist(key)
                cantidades.extend(valores)
            
            if 'varios' in cantidades:
                varios_key = f'cantidad_gemas_varios_{item_index}'
                cantidad_varios = post_data.get(varios_key, '')
                cantidad_info = {'tipo': 'varios', 'valor': cantidad_varios, 'detalle': f'{cantidad_varios} gemas' if cantidad_varios else 'Varias gemas'}
            else:
                cantidades_num = [c for c in cantidades if c.isdigit()]
                if cantidades_num:
                    total = sum(int(c) for c in cantidades_num)
                    cantidad_info = {'tipo': 'multiple', 'valor': total, 'detalle': f'{total} gemas ({"+" .join(cantidades_num)})'}
                else:
                    cantidad_info = {'tipo': 'individual', 'valor': 1, 'detalle': '1 gema'}
                    
        elif tipo_cert == 'DIAMANTE':
            # Radio buttons para DIAMANTE
            diamante_key = f'cantidad_diamante_group_{item_index}'
            seleccion = post_data.get(diamante_key, '1')
            if seleccion == '1':
                cantidad_info = {'tipo': 'individual', 'valor': 1, 'detalle': '1 gema'}
            elif seleccion == '2':
                cantidad_info = {'tipo': 'par', 'valor': 2, 'detalle': 'Par de gemas'}
            elif seleccion == 'varios':
                varios_key = f'cantidad_gemas_varios_{item_index}'
                cantidad_varios = post_data.get(varios_key, '')
                cantidad_info = {'tipo': 'varios', 'valor': cantidad_varios, 'detalle': f'{cantidad_varios} gemas' if cantidad_varios else 'Varias gemas'}
        
        return cantidad_info
    
    def _crear_item_completo(self, orden, numero_item, data, punto_partida):
        """Crea un ítem con todos los datos del formulario y genera el texto completo"""
        try:
            # Determinar tipo de ítem para cálculos
            item_type_key = self._get_item_type_key(data)
            
            # Calcular duración total
            duracion_total_segundos = TiempoCalculator.calcular_duracion_total_item(
                item_type_key, data['tipo_certificado']
            )
            
            fecha_limite = punto_partida + timedelta(seconds=duracion_total_segundos)
            
            # Procesar campos opcionales
            peso_gema = self._parse_peso_gema(data.get('peso_gema'))
            componentes_str = self._format_componentes_set(data.get('componentes_set', []))
            
            # Determinar cantidad de gemas
            cantidad_gemas = self._determinar_cantidad_gemas(data['cantidad_info'])
            
            # Generar texto completo para copiar
            texto_para_copiar = self._generar_texto_completo(data, numero_item)
            
            # Crear ítem
            item = Item(
                orden=orden,
                numero_item=numero_item,
                fecha_limite_etapa=fecha_limite,
                tipo_certificado=data['tipo_certificado'],
                que_es=data['que_es'],
                codigo_referencia=data['codigo_referencia'] if data['que_es'] in ['VERBAL_A_GC', 'REIMPRESION'] else None,
                tipo_joya=data['tipo_joya'] if data['que_es'] == 'JOYA' else None,
                cantidad_gemas=cantidad_gemas,
                metal=data['metal'] if data['que_es'] == 'JOYA' else None,
                componentes_set=componentes_str,
                gema_principal=data['gema_principal'] if data['que_es'] not in ['VERBAL_A_GC', 'REIMPRESION'] else None,
                forma_gema=data['forma_gema'] or 'Ninguno',
                peso_gema=peso_gema,
                comentarios=data['comentarios'] or None,
            )
            
            # Validar antes de guardar
            item.full_clean()
            item.save()
            
            # Guardar el texto después de crear el item (temporal hasta que agregues el campo)
            try:
                if hasattr(item, 'texto_para_copiar'):
                    item.texto_para_copiar = texto_para_copiar
                    item.save()
            except:
                pass  # Si no existe el campo, continúa sin error
            
            return item
            
        except ValidationError as e:
            raise ValidationError(f"Error en ítem {numero_item}: {e}")
        except Exception as e:
            raise Exception(f"Error creando ítem {numero_item}: {e}")
    
    def _determinar_cantidad_gemas(self, cantidad_info):
        """Determina la cantidad numérica de gemas basada en la información de cantidad"""
        if not cantidad_info or not cantidad_info.get('valor'):
            return 1
            
        try:
            return int(cantidad_info['valor']) if str(cantidad_info['valor']).isdigit() else 1
        except (ValueError, TypeError):
            return 1
    
    def _generar_texto_completo(self, data, numero_item):
        """Genera el texto completo del ítem para copiar en formato natural"""
        
        # Casos especiales
        if data['que_es'] in ['VERBAL_A_GC', 'REIMPRESION']:
            que_es_display = {
                'VERBAL_A_GC': 'Verbal a GC',
                'REIMPRESION': 'Reimpresión'
            }
            return f"{que_es_display.get(data['que_es'], data['que_es'])} - Código: {data.get('codigo_referencia', 'N/A')}"
        
        # Construcción del texto natural
        partes = []
        
        # Agregar cantidad si es relevante
        cantidad_info = data.get('cantidad_info', {})
        if cantidad_info.get('tipo') in ['par', 'trio', 'varios', 'multiple'] and cantidad_info.get('valor'):
            if cantidad_info['tipo'] == 'par':
                partes.append("Par de")
            elif cantidad_info['tipo'] == 'trio':
                partes.append("Trío de")
            elif cantidad_info['tipo'] == 'varios' and cantidad_info.get('valor'):
                partes.append(f"{cantidad_info['valor']}")
            elif cantidad_info['tipo'] == 'multiple' and cantidad_info.get('valor'):
                partes.append(f"{cantidad_info['valor']}")
        
        # Gema principal
        if data.get('gema_principal'):
            gema = data['gema_principal']
            
            # Para lotes, pluralizar
            if data['que_es'] == 'LOTE':
                if gema.lower().endswith(('a', 'e', 'i', 'o', 'u', 'á', 'é', 'í', 'ó', 'ú')):
                    gema = gema + "s"
                else:
                    gema = gema + "es"
            
            partes.append(gema.lower())
        
        # Detalles de joya
        if data['que_es'] == 'JOYA':
            # Metal
            if data.get('metal'):
                metal_display = {
                    'ORO': 'oro', 'ORO_AMARILLO': 'oro amarillo', 'ORO_ROSA': 'oro rosa',
                    'PLATA': 'plata', 'BLANCO': 'oro blanco', 'ROSA': 'oro rosa', 'NEGRO': 'oro negro'
                }
                metal_texto = metal_display.get(data['metal'], data['metal'].lower())
                partes.append(f"en {metal_texto}")
            
            # Tipo de joya
            if data.get('tipo_joya'):
                tipo_joya_display = {
                    'ANILLO': 'anillo', 'DIJE': 'dije', 'TOPOS': 'topos',
                    'PULSERA': 'pulsera', 'PULSERA_TENIS': 'pulsera tenis', 'SET': 'set'
                }
                tipo_texto = tipo_joya_display.get(data['tipo_joya'], data['tipo_joya'].lower())
                
                # Si es set, agregar componentes
                if data['tipo_joya'] == 'SET' and data.get('componentes_set'):
                    componentes = ', '.join(data['componentes_set'])
                    partes.append(f"{tipo_texto} ({componentes})")
                else:
                    partes.append(tipo_texto)
        
        # Forma de la gema
        if data.get('forma_gema') and data['forma_gema'] != 'Ninguno':
            partes.append(f"en talla {data['forma_gema']}")
        
        # Peso
        if data.get('peso_gema'):
            partes.append(f"de {data['peso_gema']} cts")
        
        # Construir el texto final
        texto_base = " ".join(partes)
        
        # Capitalizar la primera letra
        if texto_base:
            texto_base = texto_base[0].upper() + texto_base[1:]
        
        # Agregar comentarios si existen
        if data.get('comentarios'):
            texto_base += f". {data['comentarios']}"
        
        return texto_base
    
    def _get_item_type_key(self, data):
        """Determina la clave del tipo de ítem para cálculos"""
        if data['que_es'] == 'JOYA' and data.get('tipo_joya') == 'SET':
            return 'SET'
        elif data['que_es'] == 'PIEDRA':
            return 'PIEDRA'
        elif data['que_es'] == 'LOTE':
            return 'LOTE'
        else:
            return 'JOYA'  # default
    
    def _parse_peso_gema(self, peso_str):
        """Parsea el peso de la gema de forma segura"""
        if not peso_str or not peso_str.strip():
            return None
        
        try:
            peso = Decimal(str(peso_str).strip())
            if peso <= 0:
                return None
            return peso
        except (InvalidOperation, ValueError, TypeError):
            return None
    
    def _format_componentes_set(self, componentes_list):
        """Formatea la lista de componentes de un set"""
        if not componentes_list:
            return None
        
        componentes_limpios = [c.strip() for c in componentes_list if c.strip()]
        return ",".join(componentes_limpios) if componentes_limpios else None
    
    def get_context_data(self, form):
        """Genera el contexto para el template con datos optimizados"""
        # Cache de listas estáticas
        gemas_cache_key = 'gemas_principales_list'
        formas_cache_key = 'formas_gema_list'
        
        gemas_principales = cache.get(gemas_cache_key)
        if gemas_principales is None:
            gemas_principales = [
                'Ágata', 'Aguamarina', 'Alejandrita', 'Almandino - Espesartina', 'Amatista', 
                'Amazonita', 'Ankerita', 'Antracita', 'Apatito', 'Azabache', 'Berilo', 
                'Calcedonia', 'Calcopirita', 'Carbón', 'Citrino', 'Coral', 'Cordierita', 
                'Corindón', 'Crisoberilo', 'Cristal de roca', 'Cuarzo', 'Dolomita', 'Espinela', 
                'Euclasa', 'Feldespato', 'Fluorita', 'Fuchsita', 'Granate', 'Grosular', 
                'Grosularia - Andradita', 'Grosularia', 'Jacinta', 'Jaspe', 'Malaquita', 
                'Mica', 'Microclina', 'Moissanita', 'Obsidiana', 'Ónix', 'Ópalo', 'Paraiba', 
                'Perla Cultivada', 'Pirita', 'Piropo - Almandino', 'Rubí Glassfilled', 'Rubí', 
                'Rubí Estrella', 'Tanzanita', 'Trilitionita', 'Tsavorita', 'Turmalina', 'Vidrio', 
                'Zafiro', 'Zafiro cambio de color', 'Zafiro estrella', 'Zircón', 'Zoisita', 
                'Vivianita', 'Topacio', 'Cuarzo ahumado', 'Almandino - Piropo', 
                'Espesartita - Piropo', 'Zirconia cubica', 'Diamante', 'Esmeralda'
            ]
            gemas_principales = sorted(gemas_principales)
            cache.set(gemas_cache_key, gemas_principales, CACHE_TIMEOUT * 24)
        
        formas_gema = cache.get(formas_cache_key)
        if formas_gema is None:
            formas_gema = [
                'Baguette', 'Barroco', 'Briolette', 'Caballo', 'Cilíndrica', 'Circular', 
                'Cojín', 'Corazón', 'Cuadrada', 'Esfera', 'Esmeralda', 'Fantasía', 
                'Hexagonal', 'Lágrima', 'Marquis', 'Ninguno', 'Óvalo', 'Prisma ditrigonal', 
                'Prisma hexagonal', 'Prisma Piramidal', 'Prisma Tetragonal', 'Rectangular', 
                'Redonda', 'Rostro', 'Trapecio', 'Trillion', 'Hoja', 'Cabuchon', 
                'Prisma dihexagonal', 'Caballo de Mar', 'Varios'
            ]
            formas_gema = sorted(formas_gema)
            cache.set(formas_cache_key, formas_gema, CACHE_TIMEOUT * 24)
        
        return {
            'form': form,
            'gemas_principales': gemas_principales,
            'formas_gema': formas_gema,
            'max_items': MAX_ITEMS_PER_ORDER
        }


def avanzar_etapa(request, orden_id):
    """Avanza una orden a la siguiente etapa con validaciones mejoradas"""
    if request.method != 'POST':
        messages.error(request, "Método no permitido")
        return redirect('dashboard')
        
    try:
        with transaction.atomic():
            orden = get_object_or_404(
                Orden.objects.select_for_update(),
                id=orden_id
            )
            
            etapa_anterior = orden.estado_actual
            proxima_etapa = orden.get_proxima_etapa()
            
            if not proxima_etapa:
                messages.warning(
                    request,
                    f"La orden {orden.numero_orden_facturacion} ya está finalizada"
                )
                return redirect('dashboard')
            
            # Calcular tiempo total a restar de todos los ítems
            tiempo_total_a_restar = 0
            
            for item in orden.items.all():
                # Determinar el tipo de ítem correctamente
                if item.que_es == 'JOYA' and item.tipo_joya == 'SET':
                    item_type_key = 'SET'
                elif item.que_es == 'PIEDRA':
                    item_type_key = 'PIEDRA'
                elif item.que_es == 'LOTE':
                    item_type_key = 'LOTE'
                else:
                    item_type_key = 'JOYA'
                
                duracion_etapa = TiempoCalculator.get_tiempo_estimado(
                    item_type_key, 
                    item.tipo_certificado, 
                    etapa_anterior
                )
                tiempo_total_a_restar += duracion_etapa
            
            # Actualizar fechas límite de todos los ítems
            if tiempo_total_a_restar > 0:
                tiempo_delta = timedelta(seconds=tiempo_total_a_restar)
                orden.items.update(
                    fecha_limite_etapa=F('fecha_limite_etapa') - tiempo_delta
                )
            
            # Avanzar la etapa
            orden.estado_actual = proxima_etapa
            
            # Si se finaliza, limpiar fechas límite
            if proxima_etapa == 'FINALIZADA':
                orden.fecha_cierre = timezone.now()
                orden.items.update(fecha_limite_etapa=None)
            
            orden.save()
            
            # Limpiar cache relacionado (usando cache.clear() que sí existe)
            cache.clear()
            
            # Mensaje de éxito
            messages.success(
                request,
                f"Orden {orden.numero_orden_facturacion} avanzó a {orden.get_estado_actual_display()}"
            )
            
        return redirect('dashboard')
        
    except Exception as e:
        messages.error(request, f"Error al avanzar la etapa: {str(e)}")
        return redirect('dashboard')


def configuracion_tiempos(request):
    """Vista optimizada para configurar tiempos con validaciones mejoradas"""
    if request.method == 'POST':
        try:
            with transaction.atomic():
                cambios_realizados = 0
                errores = []
                
                configs = ConfiguracionTiempos.objects.select_for_update()
                
                for config in configs:
                    etapa_map = {
                        'ingreso': 'tiempo_ingreso',
                        'foto': 'tiempo_fotografia',
                        'revision': 'tiempo_revision',
                        'impresion': 'tiempo_impresion',
                    }
                    
                    config_modificada = False
                    
                    for form_prefix, model_field in etapa_map.items():
                        post_key = f'{form_prefix}_{config.tipo_item}_{config.tipo_certificado}'
                        segundos_str = request.POST.get(post_key, '').strip()
                        
                        if segundos_str:
                            try:
                                segundos_value = int(segundos_str)
                                if segundos_value < 0:
                                    errores.append(f"Valor negativo no permitido para {config}: {form_prefix}")
                                    continue
                                
                                if segundos_value > 2592000:  # 30 días
                                    errores.append(f"Valor muy grande para {config}: {form_prefix} (máximo 30 días)")
                                    continue
                                
                                if getattr(config, model_field) != segundos_value:
                                    setattr(config, model_field, segundos_value)
                                    config_modificada = True
                                    
                            except (ValueError, TypeError):
                                errores.append(f"Valor inválido para {config}: {form_prefix}")
                                continue
                        else:
                            # Campo vacío = None
                            if getattr(config, model_field) is not None:
                                setattr(config, model_field, None)
                                config_modificada = True
                    
                    if config_modificada:
                        try:
                            config.full_clean()
                            config.save()
                            cambios_realizados += 1
                        except ValidationError as e:
                            errores.append(f"Error en {config}: {e}")
                
                # Limpiar cache después de los cambios
                cache.clear()
                
                # Mostrar resultados
                if errores:
                    for error in errores[:5]:  # Mostrar máximo 5 errores
                        messages.warning(request, error)
                
                if cambios_realizados > 0:
                    messages.success(
                        request,
                        f"Se actualizaron {cambios_realizados} configuraciones correctamente"
                    )
                    logger.info(f"Configuraciones actualizadas: {cambios_realizados}")
                elif not errores:
                    messages.info(request, "No se realizaron cambios")
            
            return redirect('configuracion_tiempos')
            
        except Exception as e:
            logger.error(f"Error al actualizar configuración de tiempos: {str(e)}")
            messages.error(request, "Error interno al guardar configuración")
    
    # GET request
    try:
        configs_agrupadas = {}
        for tipo_item_key, tipo_item_label in ConfiguracionTiempos.TIPO_ITEM_CHOICES:
            configs_encontradas = ConfiguracionTiempos.objects.filter(
                tipo_item=tipo_item_key
            ).order_by('tipo_certificado')
            configs_agrupadas[tipo_item_label] = configs_encontradas
        
        context = {'configs_agrupadas': configs_agrupadas}
        return render(request, 'configuracion.html', context)
        
    except Exception as e:
        logger.error(f"Error al cargar configuración de tiempos: {str(e)}")
        messages.error(request, "Error al cargar la configuración")
        return render(request, 'configuracion.html', {'configs_agrupadas': {}})


# --- VISTAS DE ETAPAS ---

def vista_por_etapa(request, etapa):
    """Vista mejorada por etapa con manejo optimizado"""
    try:
        etapa_upper = etapa.upper()
        
        if etapa_upper not in dict(Orden.ETAPAS).keys():
            messages.error(request, "Etapa no válida")
            return redirect('dashboard')
        
        # Obtener órdenes de la etapa con optimizaciones
        ordenes = Orden.objects.select_related().prefetch_related(
            'items__fotos'
        ).filter(
            estado_actual=etapa_upper
        ).order_by('fecha_creacion')
        
        context = {
            'ordenes': ordenes,
            'nombre_etapa': dict(Orden.ETAPAS).get(etapa_upper),
            'etapa_key': etapa
        }
        
        # Para la etapa de ingreso, cargar plantillas con cache
        if etapa_upper == 'INGRESO':
            plantillas_cache_key = 'plantillas_disponibles'
            plantillas_disponibles = cache.get(plantillas_cache_key)
            
            if plantillas_disponibles is None:
                plantillas_disponibles = []
                try:
                    if hasattr(settings, 'PLANTILLAS_ROOT') and os.path.exists(settings.PLANTILLAS_ROOT):
                        archivos = os.listdir(settings.PLANTILLAS_ROOT)
                        plantillas_disponibles = sorted([
                            f for f in archivos 
                            if f.lower().endswith('.xlsx') and not f.startswith('~')
                        ])
                        cache.set(plantillas_cache_key, plantillas_disponibles, CACHE_TIMEOUT)
                except (FileNotFoundError, PermissionError, OSError) as e:
                    logger.warning(f"Error al cargar plantillas: {str(e)}")
                    messages.warning(request, "No se pudieron cargar las plantillas Excel")
            
            context['plantillas_disponibles'] = plantillas_disponibles
        
        return render(request, 'vista_etapa.html', context)
        
    except Exception as e:
        logger.error(f"Error en vista por etapa {etapa}: {str(e)}")
        messages.error(request, "Error al cargar la vista de etapa")
        return redirect('dashboard')


def asignar_excel(request, item_id):
    """Vista mejorada para asignar plantillas Excel con validaciones robustas"""
    if request.method != 'POST':
        messages.error(request, "Método no permitido")
        return redirect('vista_etapa', etapa='ingreso')
    
    try:
        with transaction.atomic():
            item = get_object_or_404(Item.objects.select_for_update(), id=item_id)
            plantilla_nombre = request.POST.get('plantilla_seleccionada', '').strip()
            
            if not plantilla_nombre:
                messages.error(request, "Debe seleccionar una plantilla")
                return redirect('vista_etapa', etapa='ingreso')
            
            # Validaciones de seguridad
            if not hasattr(settings, 'PLANTILLAS_ROOT'):
                messages.error(request, "Ruta de plantillas no configurada")
                return redirect('vista_etapa', etapa='ingreso')
            
            # Validar nombre de archivo (seguridad)
            if not plantilla_nombre.endswith('.xlsx') or '..' in plantilla_nombre:
                messages.error(request, "Nombre de plantilla inválido")
                return redirect('vista_etapa', etapa='ingreso')
            
            ruta_origen = os.path.join(settings.PLANTILLAS_ROOT, plantilla_nombre)
            
            if not os.path.exists(ruta_origen):
                messages.error(request, f"Plantilla {plantilla_nombre} no encontrada")
                return redirect('vista_etapa', etapa='ingreso')
            
            # Crear estructura de carpetas
            nombre_carpeta_orden = f"ORDEN-{item.orden.id:04d}"
            nombre_subcarpeta = f"ITEM-{item.numero_item}"
            ruta_subcarpeta = os.path.join(
                settings.MEDIA_ROOT, 
                nombre_carpeta_orden, 
                nombre_subcarpeta
            )
            
            os.makedirs(ruta_subcarpeta, exist_ok=True)
            
            # Generar nombre seguro para el archivo destino
            nombre_excel_destino = f"datos_item_{item.id}.xlsx"
            ruta_destino = os.path.join(ruta_subcarpeta, nombre_excel_destino)
            
            # Copiar archivo de forma segura
            shutil.copy2(ruta_origen, ruta_destino)
            
            # Actualizar item
            item.nombre_excel = nombre_excel_destino
            item.save(update_fields=['nombre_excel'])
            
            messages.success(
                request,
                f"Plantilla {plantilla_nombre} asignada correctamente al ítem {item.numero_item}"
            )
            logger.info(f"Plantilla asignada: {plantilla_nombre} -> Item {item.id}")
            
    except PermissionError:
        messages.error(request, "Sin permisos para copiar el archivo. Contacta al administrador.")
        logger.error(f"PermissionError al asignar Excel al item {item_id}")
    except Exception as e:
        messages.error(request, "Error al asignar plantilla. Intente nuevamente.")
        logger.error(f"Error al asignar Excel al item {item_id}: {str(e)}")
    
    return redirect('vista_etapa', etapa='ingreso')


def detalle_orden(request, orden_id):
    """Vista mejorada de detalle de orden con manejo optimizado de archivos"""
    try:
        orden = get_object_or_404(
            Orden.objects.prefetch_related('items__fotos'),
            id=orden_id
        )
        
        if request.method == 'POST' and 'item_id' in request.POST:
            item_id = request.POST.get('item_id')
            item = get_object_or_404(Item, id=item_id, orden=orden)
            
            if 'subir_ingreso' in request.POST:
                return _manejar_subida_qr(request, item, orden)
            elif 'subir_fotos' in request.POST:
                return _manejar_subida_fotos(request, item, orden)
        
        context = {'orden': orden}
        return render(request, 'detalle_orden.html', context)
        
    except Exception as e:
        logger.error(f"Error en detalle de orden {orden_id}: {str(e)}")
        messages.error(request, "Error al cargar el detalle de la orden")
        return redirect('dashboard')


def _manejar_subida_qr(request, item, orden):
    """Maneja la subida de códigos QR con validaciones mejoradas"""
    try:
        qr_file = request.FILES.get('qr_code')
        
        if not qr_file:
            messages.error(request, "No se seleccionó ningún archivo")
            return redirect('detalle_orden', orden_id=orden.id)
        
        # Validar archivo
        es_valido, mensaje_error = FileManager.validar_archivo_imagen(qr_file, max_size_mb=5)
        if not es_valido:
            messages.error(request, mensaje_error)
            return redirect('detalle_orden', orden_id=orden.id)
        
        with transaction.atomic():
            # Eliminar QR anterior si existe
            if item.qr_cargado:
                try:
                    if os.path.exists(item.qr_cargado.path):
                        os.remove(item.qr_cargado.path)
                        logger.info(f"QR anterior eliminado para item {item.id}")
                except Exception as e:
                    logger.warning(f"No se pudo eliminar QR anterior: {str(e)}")
            
            # Asignar nuevo QR con nombre seguro
            qr_file.name = FileManager.safe_filename(qr_file.name)
            item.qr_cargado = qr_file
            item.save(update_fields=['qr_cargado'])
            
            messages.success(request, f"Código QR actualizado para el ítem {item.numero_item}")
            logger.info(f"QR actualizado para item {item.id}")
        
    except Exception as e:
        logger.error(f"Error al subir QR para item {item.id}: {str(e)}")
        messages.error(request, "Error al subir código QR. Intente nuevamente.")
    
    return redirect('detalle_orden', orden_id=orden.id)


def _manejar_subida_fotos(request, item, orden):
    """Maneja la subida de fotos profesionales con validaciones mejoradas"""
    try:
        fotos = request.FILES.getlist('fotos_profesionales')
        
        if not fotos:
            messages.error(request, "No se seleccionaron fotos")
            return redirect('detalle_orden', orden_id=orden.id)
        
        if len(fotos) > 10:  # Límite de fotos por ítem
            messages.error(request, "Máximo 10 fotos por ítem")
            return redirect('detalle_orden', orden_id=orden.id)
        
        fotos_subidas = 0
        errores = []
        
        with transaction.atomic():
            for foto in fotos:
                try:
                    # Validar cada foto
                    es_valido, mensaje_error = FileManager.validar_archivo_imagen(foto, max_size_mb=10)
                    if not es_valido:
                        errores.append(f"{foto.name}: {mensaje_error}")
                        continue
                    
                    # Generar nombre seguro
                    foto.name = FileManager.safe_filename(foto.name)
                    
                    # Crear FotoItem
                    FotoItem.objects.create(item=item, imagen=foto)
                    fotos_subidas += 1
                    
                except Exception as e:
                    errores.append(f"{foto.name}: Error al procesar")
                    logger.error(f"Error al procesar foto {foto.name} para item {item.id}: {str(e)}")
        
        # Mostrar resultados
        if fotos_subidas > 0:
            messages.success(request, f"Se subieron {fotos_subidas} fotos correctamente")
            logger.info(f"{fotos_subidas} fotos subidas para item {item.id}")
        
        if errores:
            for error in errores[:3]:  # Mostrar máximo 3 errores
                messages.warning(request, error)
        
        if fotos_subidas == 0:
            messages.error(request, "No se pudo subir ninguna foto")
        
    except Exception as e:
        logger.error(f"Error general al subir fotos para item {item.id}: {str(e)}")
        messages.error(request, "Error al subir fotos. Intente nuevamente.")
    
    return redirect('detalle_orden', orden_id=orden.id)


def orden_creada_exito(request, orden_id):
    """Vista de confirmación optimizada"""
    try:
        orden = get_object_or_404(
            Orden.objects.prefetch_related('items'),
            id=orden_id
        )
        
        ultimo_item = orden.items.order_by('fecha_limite_etapa').last()
        
        context = {
            'orden': orden,
            'items_count': orden.items.count(),
            'fecha_limite': ultimo_item.fecha_limite_etapa if ultimo_item and ultimo_item.fecha_limite_etapa else None,
            'tiene_retrasados': orden.tiene_items_retrasados(),
            'progreso_porcentaje': orden.get_progreso_porcentaje(),
            'items': orden.items.all(),  # Para mostrar la lista de items si es necesario
        }
        
        # Renderizar template HTML en lugar de JSON
        return render(request, 'orden_creada_exito.html', context)
        
    except Exception as e:
        logger.error(f"Error en vista orden creada {orden_id}: {str(e)}")
        messages.error(request, 'Error al mostrar los detalles de la orden.')
        return redirect('crear_orden')  # Redirigir de vuelta al formulario


def api_estadisticas_dashboard(request):
    """API endpoint optimizado para estadísticas del dashboard"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    try:
        # Cache de estadísticas por 5 minutos
        stats_cache_key = 'dashboard_stats'
        stats = cache.get(stats_cache_key)
        
        if stats is None:
            ordenes_activas = Orden.objects.filter(
                estado_actual__in=['INGRESO', 'FOTOGRAFIA', 'REVISION', 'IMPRESION']
            )
            
            stats = {
                'ordenes_activas': ordenes_activas.count(),
                'por_etapa': {},
                'items_retrasados': 0,
                'fin_cola': None
            }
            
            # Contar por etapa
            for etapa_key, etapa_label in Orden.ETAPAS:
                if etapa_key != 'FINALIZADA':
                    count = ordenes_activas.filter(estado_actual=etapa_key).count()
                    stats['por_etapa'][etapa_key] = {
                        'count': count,
                        'label': etapa_label
                    }
            
            # Ítems retrasados
            items_retrasados = Item.objects.filter(
                orden__estado_actual__in=['INGRESO', 'FOTOGRAFIA', 'REVISION', 'IMPRESION'],
                fecha_limite_etapa__lt=timezone.now()
            ).count()
            stats['items_retrasados'] = items_retrasados
            
            # Fin de cola
            ultimo_tiempo = OrdenManager.get_ultimo_tiempo_ocupado()
            if ultimo_tiempo > timezone.now():
                stats['fin_cola'] = ultimo_tiempo.isoformat()
            
            cache.set(stats_cache_key, stats, 300)  # 5 minutos
        
        return JsonResponse(stats)
        
    except Exception as e:
        logger.error(f"Error en API estadísticas: {str(e)}")
        return JsonResponse({'error': 'Error interno'}, status=500)
        context = {'orden': orden}
        return render(request, 'orden_creada_exito.html', context)
    except Exception as e:
        logger.error(f"Error en orden creada éxito {orden_id}: {str(e)}")
        messages.error(request, "Error al mostrar confirmación")
        return redirect('dashboard')

# --- VISTAS DE API/AJAX (OPCIONALES) ---

def api_orden_status(request, orden_id):
    """API endpoint para obtener estado de orden (para actualizaciones en tiempo real)."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    try:
        orden = get_object_or_404(Orden, id=orden_id)
        ultimo_item = orden.items.last()
        
        data = {
            'id': orden.id,
            'numero_orden_facturacion': orden.numero_orden_facturacion,
            'estado_actual': orden.estado_actual,
            'estado_display': orden.get_estado_actual_display(),
            'items_count': orden.items.count(),
            'fecha_limite': ultimo_item.fecha_limite_etapa.isoformat() if ultimo_item and ultimo_item.fecha_limite_etapa else None,
        }
        
        return JsonResponse(data)
        
    except Exception as e:
        logger.error(f"Error en API orden status {orden_id}: {str(e)}")
        return JsonResponse({'error': 'Error interno'}, status=500)

def api_estadisticas_dashboard(request):
    """API endpoint para estadísticas del dashboard."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    try:
        stats = {
            'ordenes_activas': Orden.objects.filter(
                estado_actual__in=['INGRESO', 'FOTOGRAFIA', 'REVISION', 'IMPRESION']
            ).count(),
            'por_etapa': {},
            'items_retrasados': 0,
            'fin_cola': None
        }
        
        # Contar por etapa
        for etapa_key, etapa_label in Orden.ETAPAS:
            if etapa_key != 'FINALIZADA':
                count = Orden.objects.filter(estado_actual=etapa_key).count()
                stats['por_etapa'][etapa_key] = {
                    'count': count,
                    'label': etapa_label
                }
        
        # Ítems retrasados
        items_retrasados = Item.objects.filter(
            orden__estado_actual__in=['INGRESO', 'FOTOGRAFIA', 'REVISION', 'IMPRESION'],
            fecha_limite_etapa__lt=timezone.now()
        ).count()
        stats['items_retrasados'] = items_retrasados
        
        # Fin de cola
        ultimo_tiempo = get_ultimo_tiempo_ocupado()
        if ultimo_tiempo > timezone.now():
            stats['fin_cola'] = ultimo_tiempo.isoformat()
        
        return JsonResponse(stats)
        
    except Exception as e:
        logger.error(f"Error en API estadísticas: {str(e)}")
        return JsonResponse({'error': 'Error interno'}, status=500)