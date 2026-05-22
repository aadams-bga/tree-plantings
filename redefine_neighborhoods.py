#!/usr/bin/env python3
"""
Redefines neighborhood mapping for 2010 Census Tracts by performing a spatial join
between tracts.geojson (using centroids) and the new Neighborhoods.geojson file.
Outputs the result to neighborhood_mapping.json and updates tree_interactive.html.
"""

import os
import json
import csv

def point_in_polygon(x, y, polygon):
    """
    Ray-casting algorithm to check if point (x, y) is inside a polygon ring.
    polygon is a list of [x, y] coordinates.
    """
    n = len(polygon)
    inside = False
    p1x, p1y = polygon[0]
    for i in range(n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    else:
                        xinters = p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def point_in_multipolygon(x, y, multipoly):
    """
    Checks if point (x, y) is inside a MultiPolygon (list of polygons with holes).
    """
    for poly in multipoly:
        outer = poly[0]
        if point_in_polygon(x, y, outer):
            # Check if point is inside any holes
            in_hole = False
            for hole in poly[1:]:
                if point_in_polygon(x, y, hole):
                    in_hole = True
                    break
            if not in_hole:
                return True
    return False

def get_centroid(geometry):
    """
    Computes a simplified centroid (arithmetic mean of outer boundary coordinates)
    for Polygon and MultiPolygon geometry.
    """
    gtype = geometry.get('type')
    coords = geometry.get('coordinates', [])
    if gtype == 'Polygon':
        outer = coords[0]
        xs = [pt[0] for pt in outer]
        ys = [pt[1] for pt in outer]
        return sum(xs)/len(xs), sum(ys)/len(ys)
    elif gtype == 'MultiPolygon':
        all_xs = []
        all_ys = []
        for poly in coords:
            outer = poly[0]
            all_xs.extend([pt[0] for pt in outer])
            all_ys.extend([pt[1] for pt in outer])
        if all_xs:
            return sum(all_xs)/len(all_xs), sum(all_ys)/len(all_ys)
    return None

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    csv_path = os.path.join(script_dir, "lookupdata.csv")
    tracts_path = os.path.join(script_dir, "2010tracts.geojson")
    neigh_path = os.path.join(script_dir, "Neighborhoods.geojson")
    mapping_out_path = os.path.join(script_dir, "neighborhood_mapping.json")
    html_path = os.path.join(script_dir, "tree_interactive.html")
    
    # 1. Parse lookupdata.csv to find all valid tract GEOIDs we want to map
    print("Reading lookupdata.csv...")
    target_tracts = set()
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            geoid = row.get("tractFIPS_left")
            if geoid:
                target_tracts.add(geoid.strip())
    print(f"Loaded {len(target_tracts)} target tracts from CSV.")

    # 2. Load 2010tracts.geojson
    print("Loading 2010tracts.geojson...")
    with open(tracts_path, "r", encoding="utf-8") as f:
        tract_geojson = json.load(f)

    # 3. Load Neighborhoods.geojson
    print("Loading Neighborhoods.geojson...")
    with open(neigh_path, "r", encoding="utf-8") as f:
        neigh_geojson = json.load(f)

    # 4. Perform spatial join using ray-casting
    print("Performing spatial join...")
    mapping = {}
    mapped_count = 0
    unmapped_count = 0
    
    neigh_features = neigh_geojson.get("features", [])
    tract_features = tract_geojson.get("features", [])
    
    for tract in tract_features:
        props = tract.get("properties", {})
        geoid = props.get("GEOID") or props.get("FIPS") or props.get("geoid10") or props.get("GEOID10")
        if not geoid:
            continue
        geoid = geoid.strip()
        
        # We only map the tracts that are actually in lookupdata.csv
        if geoid not in target_tracts:
            continue
            
        geom = tract.get("geometry", {})
        centroid = get_centroid(geom)
        if not centroid:
            print(f"Warning: Could not compute centroid for tract {geoid}")
            mapping[geoid] = None
            unmapped_count += 1
            continue
            
        tx, ty = centroid
        found_neigh = None
        
        for neigh in neigh_features:
            n_geom = neigh.get("geometry", {})
            n_type = n_geom.get("type")
            n_coords = n_geom.get("coordinates", [])
            n_name = neigh.get("properties", {}).get("pri_neigh")
            
            inside = False
            if n_type == "Polygon":
                inside = point_in_polygon(tx, ty, n_coords[0])
                if inside:
                    # check holes
                    for hole in n_coords[1:]:
                        if point_in_polygon(tx, ty, hole):
                            inside = False
                            break
            elif n_type == "MultiPolygon":
                inside = point_in_multipolygon(tx, ty, n_coords)
                
            if inside:
                found_neigh = n_name
                break
                
        if found_neigh:
            mapping[geoid] = found_neigh
            mapped_count += 1
        else:
            # If centroid lies outside Chicago neighborhoods (suburbs), map to None (null in JSON)
            mapping[geoid] = None
            unmapped_count += 1
            
    print(f"Spatial join completed: {mapped_count} tracts mapped, {unmapped_count} tracts unmapped.")

    # 5. Save the mapping to neighborhood_mapping.json
    print(f"Saving mapping to {mapping_out_path}...")
    # Sort keys for deterministic output
    sorted_mapping = {k: mapping[k] for k in sorted(mapping.keys())}
    with open(mapping_out_path, "w", encoding="utf-8") as f:
        json.dump(sorted_mapping, f, indent=2)

    # 6. Update tree_interactive.html
    print("Updating tree_interactive.html...")
    if not os.path.exists(html_path):
        print(f"Error: {html_path} not found. Cannot update HTML.")
        return
        
    with open(html_path, "r", encoding="utf-8") as f:
        html_lines = f.readlines()
        
    start_idx = -1
    end_idx = -1
    for idx, line in enumerate(html_lines):
        if "const NEIGHBORHOOD_MAP = {" in line:
            start_idx = idx
        elif start_idx != -1 and "};" in line and end_idx == -1:
            end_idx = idx
            break
            
    if start_idx == -1 or end_idx == -1:
        print("Error: Could not find const NEIGHBORHOOD_MAP definition boundaries in tree_interactive.html.")
        return
        
    # Generate the replacement lines for the map
    js_map_lines = ["    const NEIGHBORHOOD_MAP = {\n"]
    for i, (k, v) in enumerate(sorted_mapping.items()):
        val_str = f'"{v}"' if v is not None else "null"
        comma = "," if i < len(sorted_mapping) - 1 else ""
        js_map_lines.append(f'        "{k}": {val_str}{comma}\n')
    js_map_lines.append("    };\n")
    
    # Replace lines and write back
    new_html_lines = html_lines[:start_idx] + js_map_lines + html_lines[end_idx+1:]
    
    # Clean up empty lines inside the <script> block to prevent WordPress from mangling it
    final_lines = []
    in_script = False
    for line in new_html_lines:
        if "<script" in line:
            in_script = True
            final_lines.append(line)
        elif "</script" in line:
            in_script = False
            final_lines.append(line)
        elif in_script:
            # If we are inside the script block, skip empty lines
            if line.strip():
                final_lines.append(line)
        else:
            final_lines.append(line)
            
    with open(html_path, "w", encoding="utf-8") as f:
        f.writelines(final_lines)
        
    print("Successfully updated tree_interactive.html!")

if __name__ == "__main__":
    main()
