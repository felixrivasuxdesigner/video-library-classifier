import json
import xml.etree.ElementTree as ET
from pathlib import Path

def generate_fcpxml(metadata_path, visual_path, output_path, event_name):
    with open(metadata_path, 'r') as f:
        tech_clips = {c['signature']: c for c in json.load(f)}
    with open(visual_path, 'r') as f:
        visual_data = {v['signature']: v for v in json.load(f)}

    fcpxml = ET.Element('fcpxml', version='1.13')
    resources = ET.SubElement(fcpxml, 'resources')
    ET.SubElement(resources, 'format', id='r1', name='FFVideoFormat3840x2160p2398', frameDuration='1001/24000s', width='3840', height='2160')

    library = ET.SubElement(fcpxml, 'library')
    event = ET.SubElement(library, 'event', name=event_name)
    
    asset_id_counter = 2
    
    # 1. Browser: Organización de clips
    sorted_sigs = sorted(tech_clips.keys(), key=lambda s: tech_clips[s].get('hora_creacion', ''))
    for sig in sorted_sigs:
        clip = tech_clips[sig]; v = visual_data.get(sig, {})
        asset_id = f'r{asset_id_counter}'; asset_id_counter += 1
        duration = f"{int(round(clip['duracion_seg'] * (24000/1001))) * 1001}/24000s"
        
        asset = ET.SubElement(resources, 'asset', id=asset_id, name=clip['archivo'], start='0s', duration=duration, format='r1')
        ET.SubElement(asset, 'media-rep', kind='original-media', src=f"file://{clip['ruta_absoluta']}")
        
        asset_clip = ET.SubElement(event, 'asset-clip', name=clip['archivo'], ref=asset_id, duration=duration, start='0s', format='r1')
        
        # Energía descriptiva (1-5)
        energia_names = {1: "Atmosférico", 2: "Íntimo", 3: "Social", 4: "Celebración", 5: "Éxtasis"}
        energia_val = v.get('energia', 3)
        energia_kw = f"⚡ {energia_names.get(energia_val, 'Social')}"
        # Valor narrativo
        narrativo_kw = f"◆ {v.get('valor_narrativo', 'Filler')}"
        kws = {clip['camara'], v.get('categoria', 'Sin clasificar'), energia_kw, narrativo_kw}
        if v.get('tags'): kws.update(f"# {t}" for t in v['tags'] if t not in {'interior','exterior','dia','día','noche','descarte'})
        for kw in kws: ET.SubElement(asset_clip, 'keyword', start='0s', duration=duration, value=str(kw))
        for sr in v.get('sub_ranges', []) or []:
            sr_kw = sr.get('keyword')
            if sr_kw:
                sr_st = f"{int(round(float(sr.get('start_sec', 0.0)) * (24000/1001))) * 1001}/24000s"
                sr_dur = f"{max(1, int(round(float(sr.get('duration_sec', 1.0)) * (24000/1001)))) * 1001}/24000s"
                ET.SubElement(asset_clip, 'keyword', start=sr_st, duration=sr_dur, value=str(sr_kw))

    # Helper para crear Gaps con Offsets Progresivos (Izquierda a Derecha)
    def add_sequential_gap(spine, name, duration_sec, current_offset_ticks):
        dur_ticks = int(round(duration_sec * (24000/1001))) * 1001
        offset_str = f"{current_offset_ticks}/24000s"
        dur_str = f"{dur_ticks}/24000s"
        
        gap = ET.SubElement(spine, 'gap', name=name, offset=offset_str, duration=dur_str, start='0s')
        ET.SubElement(gap, 'marker', start='0s', duration='1001/24000s', value=name)
        
        return current_offset_ticks + dur_ticks

    # 2. Líneas de tiempo con orden lógico
    
    # --- PELÍCULA ---
    p_pelicula = ET.SubElement(event, 'project', name="01_Pelicula_Crónica_30m")
    seq_p = ET.SubElement(p_pelicula, 'sequence', format='r1', tcStart='0s', tcFormat='NDF')
    spine_p = ET.SubElement(seq_p, 'spine')
    off = 0
    off = add_sequential_gap(spine_p, "--- 1. PREPARATIVOS ---", 450, off)
    off = add_sequential_gap(spine_p, "--- 2. CEREMONIA ---", 450, off)
    off = add_sequential_gap(spine_p, "--- 3. CÓCTEL ---", 300, off)
    off = add_sequential_gap(spine_p, "--- 4. RECEPCIÓN / FIESTA ---", 600, off)

    # --- HIGHLIGHT ---
    p_hl = ET.SubElement(event, 'project', name="02_Highlight_Story_5m")
    seq_hl = ET.SubElement(p_hl, 'sequence', format='r1', tcStart='0s', tcFormat='NDF')
    spine_hl = ET.SubElement(seq_hl, 'spine')
    off = 0
    off = add_sequential_gap(spine_hl, "--- HOOK (Discursos) ---", 30, off)
    off = add_sequential_gap(spine_hl, "--- PREPARATIVOS ---", 60, off)
    off = add_sequential_gap(spine_hl, "--- CEREMONIA ---", 90, off)
    off = add_sequential_gap(spine_hl, "--- SESIÓN / CÓCTEL ---", 60, off)
    off = add_sequential_gap(spine_hl, "--- FIESTA MÁXIMA ---", 60, off)

    # --- RRSS ---
    p_rrss = ET.SubElement(event, 'project', name="03_RRSS_Teaser_1m")
    seq_rrss = ET.SubElement(p_rrss, 'sequence', format='r1', tcStart='0s', tcFormat='NDF')
    spine_rrss = ET.SubElement(seq_rrss, 'spine')
    off = 0
    off = add_sequential_gap(spine_rrss, "--- INTRO ÉPICA (Drone) ---", 10, off)
    off = add_sequential_gap(spine_rrss, "--- CLÍMAX EMOCIONAL ---", 20, off)
    off = add_sequential_gap(spine_rrss, "--- ÉXTASIS FIESTA ---", 30, off)

    tree = ET.ElementTree(fcpxml); ET.indent(tree, space="  ", level=0)
    tree.write(output_path, encoding='utf-8', xml_declaration=True)

if __name__ == "__main__":
    m = "/Users/felixrivas/Movies/danielhfoto_matrimonio-21-02-2026_2026-03-19_0340/_metadata.json"
    v = "/Users/felixrivas/Movies/danielhfoto_matrimonio-21-02-2026_2026-03-19_0340/_visual_classifications.json"
    out = "/Users/felixrivas/Movies/danielhfoto_matrimonio-21-02-2026_2026-03-19_0340/danielhfoto_BODA_NARRATIVA_v8.fcpxml"
    generate_fcpxml(m, v, out, "Boda Daniel - Estructura Narrativa")
