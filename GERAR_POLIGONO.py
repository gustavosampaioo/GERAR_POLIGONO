"""
Processador de KML para Streamlit
Autor: Assistente AI
Descrição: Aplicação para processar KMLs com pontos e gerar polígonos de 40m
"""

import sys
import subprocess
import importlib.util

# Função para verificar e instalar pacotes
def check_and_install_packages():
    """Verifica se os pacotes necessários estão instalados"""
    required_packages = [
        'streamlit',
        'shapely',
        'simplekml',
        'numpy',
        'pyproj',
        'folium',
        'streamlit_folium',
        'pandas'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        spec = importlib.util.find_spec(package)
        if spec is None:
            missing_packages.append(package)
    
    if missing_packages:
        print("=" * 60)
        print("PACOTES FALTANDO!")
        print("=" * 60)
        print(f"Os seguintes pacotes não estão instalados: {', '.join(missing_packages)}")
        print("\nPara instalar, execute no terminal:")
        print(f"pip install {' '.join(missing_packages)}")
        print("\nOu instale todos de uma vez:")
        print("pip install -r requirements.txt")
        print("=" * 60)
        return False
    
    return True

# Verificar dependências antes de continuar
if not check_and_install_packages():
    print("\n❌ Por favor, instale as dependências faltantes e execute novamente.")
    sys.exit(1)

# Agora importamos os pacotes
import streamlit as st
import xml.etree.ElementTree as ET
import math
import numpy as np
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
import simplekml
import tempfile
import os
from pyproj import Transformer
import folium
from streamlit_folium import folium_static
import pandas as pd

# Configuração da página
st.set_page_config(
    page_title="Processador de KML - Polígonos de 40m",
    page_icon="🗺️",
    layout="wide"
)

# Título e descrição
st.title("🗺️ Processador de KML - Polígonos de 40m")
st.markdown("""
Esta aplicação processa arquivos KML com placemarks do tipo Point e gera polígonos quadrados de 40 metros de raio.
Polígonos que se intersectam são automaticamente unidos.
""")

# Sidebar para configurações
with st.sidebar:
    st.header("⚙️ Configurações")
    
    raio = st.slider(
        "Raio do polígono (metros)",
        min_value=10,
        max_value=150,
        value=120,
        step=5,
        help="Distância do centro até a borda do quadrado"
    )
    
    cor_poligono = st.color_picker(
        "Cor do polígono",
        value="#FF0000",
        help="Cor dos polígonos no mapa"
    )
    
    opacidade = st.slider(
        "Opacidade",
        min_value=0.0,
        max_value=1.0,
        value=0.3,
        step=0.1,
        help="Transparência dos polígonos"
    )
    
    st.markdown("---")
    st.markdown("### 📤 Upload do Arquivo")
    uploaded_file = st.file_uploader(
        "Escolha um arquivo KML",
        type=['kml'],
        help="Selecione um arquivo KML contendo placemarks do tipo Point"
    )

# Funções principais
def parse_kml(file_content):
    """Extrai placemarks do tipo Point de um arquivo KML"""
    try:
        # Parse do KML
        tree = ET.parse(file_content)
        root = tree.getroot()
        
        # Namespace do KML
        namespace = {'kml': 'http://www.opengis.net/kml/2.2'}
        
        placemarks = []
        
        for placemark in root.findall('.//kml:Placemark', namespace):
            point = placemark.find('.//kml:Point/kml:coordinates', namespace)
            if point is not None:
                # Extrair nome
                name_elem = placemark.find('kml:name', namespace)
                name = name_elem.text if name_elem is not None else "Sem nome"
                
                # Extrair descrição se existir
                desc_elem = placemark.find('kml:description', namespace)
                description = desc_elem.text if desc_elem is not None else ""
                
                # Extrair coordenadas
                coords_text = point.text.strip()
                coords = coords_text.split(',')
                
                if len(coords) >= 2:
                    lon = float(coords[0])
                    lat = float(coords[1])
                    
                    placemarks.append({
                        'name': name,
                        'description': description,
                        'lat': lat,
                        'lon': lon,
                        'coords': coords_text
                    })
        
        return placemarks, root
    except Exception as e:
        st.error(f"Erro ao processar KML: {str(e)}")
        return None, None

def create_square_polygon(lat, lon, radius_meters):
    """Cria um polígono quadrado ao redor de um ponto"""
    # Aproximação: 1 grau de latitude ≈ 111 km
    lat_offset = radius_meters / 111000
    
    # Correção para longitude baseada na latitude
    lon_offset = radius_meters / (111000 * math.cos(math.radians(lat)))
    
    # Criar vértices do quadrado
    vertices = [
        (lat - lat_offset, lon - lon_offset),
        (lat - lat_offset, lon + lon_offset),
        (lat + lat_offset, lon + lon_offset),
        (lat + lat_offset, lon - lon_offset),
        (lat - lat_offset, lon - lon_offset)
    ]
    
    return Polygon(vertices)

def merge_intersecting_polygons(polygons):
    """Une polígonos que se intersectam"""
    if not polygons:
        return []
    
    if len(polygons) == 1:
        return polygons
    
    try:
        # Usar unary_union para unir todos os polígonos
        merged = unary_union(polygons)
        
        # Se o resultado for MultiPolygon, separar em polígonos individuais
        if merged.geom_type == 'MultiPolygon':
            return list(merged.geoms)
        elif merged.geom_type == 'Polygon':
            return [merged]
        else:
            return []
    except Exception as e:
        st.error(f"Erro ao unir polígonos: {str(e)}")
        return polygons

def create_output_kml(polygons, placemarks, radius, color, opacity):
    """Cria um novo KML com os polígonos processados"""
    kml = simplekml.Kml()
    
    # Adicionar pontos originais (opcional)
    for i, pm in enumerate(placemarks):
        pnt = kml.newpoint(name=f"Original: {pm['name']}")
        pnt.coords = [(pm['lon'], pm['lat'])]
        pnt.style.iconstyle.color = simplekml.Color.blue
        pnt.style.iconstyle.scale = 0.5
    
    # Adicionar polígonos processados
    for i, poly in enumerate(polygons):
        if poly.geom_type == 'Polygon':
            coords = list(poly.exterior.coords)
            
            # Criar polígono no KML
            pol = kml.newpolygon(name=f"Área {i+1}")
            
            # Converter cor hex para RGB
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
            
            # Configurar estilo
            pol.style.linestyle.color = simplekml.Color.rgb(r, g, b)
            pol.style.linestyle.width = 2
            pol.style.polystyle.color = simplekml.Color.changealphaint(
                int(opacity * 255), 
                simplekml.Color.rgb(r, g, b)
            )
            
            # Adicionar coordenadas (invertendo lat/lon para o KML)
            kml_coords = [(lon, lat) for lat, lon in coords]
            pol.outerboundaryis = kml_coords
    
    return kml

def create_folium_map(polygons, placemarks, color, opacity):
    """Cria um mapa Folium para visualização"""
    if not polygons:
        return None
    
    # Calcular centro do mapa
    if placemarks:
        center_lat = sum(pm['lat'] for pm in placemarks) / len(placemarks)
        center_lon = sum(pm['lon'] for pm in placemarks) / len(placemarks)
    else:
        center_lat, center_lon = 0, 0
    
    # Criar mapa
    m = folium.Map(location=[center_lat, center_lon], zoom_start=15)
    
    # Adicionar pontos originais
    for pm in placemarks:
        folium.Marker(
            [pm['lat'], pm['lon']],
            popup=f"<b>{pm['name']}</b><br>{pm['description']}",
            icon=folium.Icon(color='blue', icon='info-sign')
        ).add_to(m)
    
    # Adicionar polígonos processados
    for i, poly in enumerate(polygons):
        if poly.geom_type == 'Polygon':
            coords = list(poly.exterior.coords)
            # Inverter para (lat, lon)
            folium_coords = [(lat, lon) for lat, lon in coords]
            
            folium.Polygon(
                folium_coords,
                popup=f"Área {i+1}",
                color=color,
                weight=2,
                fill=True,
                fill_color=color,
                fill_opacity=opacity
            ).add_to(m)
    
    return m

# Interface principal
if uploaded_file is not None:
    # Processar arquivo
    with st.spinner("Processando arquivo KML..."):
        placemarks, kml_root = parse_kml(uploaded_file)
    
    if placemarks:
        # Mostrar estatísticas
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📍 Placemarks encontrados", len(placemarks))
        with col2:
            st.metric("📐 Raio do polígono", f"{raio}m")
        with col3:
            st.metric("🎯 Polígonos únicos", "A processar")
        
        # Mostrar tabela de placemarks
        with st.expander("📋 Lista de Placemarks Encontrados", expanded=False):
            df = pd.DataFrame(placemarks)
            df_display = df[['name', 'lat', 'lon']].copy()
            df_display.columns = ['Nome', 'Latitude', 'Longitude']
            st.dataframe(df_display)
        
        # Botão para processar
        if st.button("🚀 Processar e Gerar Polígonos", type="primary"):
            with st.spinner("Gerando polígonos..."):
                # Criar polígonos individuais
                individual_polygons = []
                for pm in placemarks:
                    poly = create_square_polygon(pm['lat'], pm['lon'], raio)
                    individual_polygons.append(poly)
                
                # Unir polígonos que se intersectam
                merged_polygons = merge_intersecting_polygons(individual_polygons)
                
                # Atualizar métrica
                st.session_state['merged_polygons'] = merged_polygons
                col2.metric("📐 Polígonos após união", len(merged_polygons))
                
                # Criar KML de saída
                output_kml = create_output_kml(merged_polygons, placemarks, raio, cor_poligono, opacidade)
                
                # Salvar em arquivo temporário
                with tempfile.NamedTemporaryFile(delete=False, suffix='.kml') as tmp_file:
                    output_kml.save(tmp_file.name)
                    
                    # Botão de download
                    with open(tmp_file.name, 'rb') as f:
                        kml_bytes = f.read()
                    
                    st.download_button(
                        label="📥 Download KML Processado",
                        data=kml_bytes,
                        file_name="poligonos_processados.kml",
                        mime="application/vnd.google-earth.kml+xml"
                    )
                
                # Limpar arquivo temporário
                os.unlink(tmp_file.name)
                
                # Salvar no session state para visualização
                st.session_state['placemarks'] = placemarks
                st.success(f"✅ Processamento concluído! {len(merged_polygons)} polígono(s) gerado(s).")
    
    else:
        st.warning("Nenhum placemark do tipo Point encontrado no arquivo KML.")

# Visualização do mapa (se houver dados processados)
if 'merged_polygons' in st.session_state and st.session_state['merged_polygons']:
    st.markdown("---")
    st.header("🗺️ Visualização do Mapa")
    
    # Criar e mostrar mapa
    m = create_folium_map(
        st.session_state['merged_polygons'],
        st.session_state['placemarks'],
        cor_poligono,
        opacidade
    )
    
    if m:
        folium_static(m, width=1000, height=600)
        
        # Estatísticas adicionais
        st.markdown("### 📊 Estatísticas dos Polígonos")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total de polígonos", len(st.session_state['merged_polygons']))
        with col2:
            # Calcular área aproximada
            total_area = 0
            for poly in st.session_state['merged_polygons']:
                if poly.geom_type == 'Polygon':
                    # Conversão aproximada de graus² para km²
                    area_degrees = poly.area
                    # Fator de conversão aproximado (considerando latitude média)
                    avg_lat = sum(pm['lat'] for pm in st.session_state['placemarks']) / len(st.session_state['placemarks'])
                    km_per_degree_lat = 111
                    km_per_degree_lon = 111 * math.cos(math.radians(avg_lat))
                    area_km2 = area_degrees * km_per_degree_lat * km_per_degree_lon
                    total_area += area_km2
            
            st.metric("Área total aproximada", f"{total_area:.2f} km²")
        with col3:
            st.metric("Polígonos originais", len(st.session_state['placemarks']))

# Informações adicionais na sidebar
with st.sidebar:
    st.markdown("---")
    st.markdown("### ℹ️ Sobre")
    st.info("""
    **Como usar:**
    1. Faça upload de um arquivo KML com pontos
    2. Ajuste o raio dos polígonos
    3. Clique em "Processar"
    4. Visualize no mapa
    5. Faça download do KML
    
    **Funcionalidades:**
    - Extrai pontos (placemarks)
    - Cria quadrados de EX:40m
    - Une polígonos que se tocam
    - Visualização interativa
    """)

# Rodapé
st.markdown("---")
st.markdown("Desenvolvido com ❤️ usando Streamlit, Shapely e Folium")
