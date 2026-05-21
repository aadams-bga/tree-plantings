import os
import zipfile
import tempfile
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# ---- DEFAULTS ----
DEFAULT_LAT_COL = "lat"
DEFAULT_LON_COL = "long"
DEFAULT_CRS = "EPSG:4326"

def _load_kmz(path: str) -> gpd.GeoDataFrame:
    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(path, "r") as z:
            kml_files = [f for f in z.namelist() if f.lower().endswith(".kml")]
            if not kml_files:
                raise ValueError(f"No .kml file found inside KMZ: {path}")
            kml_name = kml_files[0]
            z.extract(kml_name, tmpdir)
            kml_path = os.path.join(tmpdir, kml_name)
            gdf = gpd.read_file(kml_path, driver="KML")
    return gdf

def load_polygons_any(path: str, target_crs: str = DEFAULT_CRS) -> gpd.GeoDataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".kmz":
        poly_gdf = _load_kmz(path)
    elif ext == ".kml":
        poly_gdf = gpd.read_file(path, driver="KML")
    else:
        poly_gdf = gpd.read_file(path)

    if poly_gdf.crs is None:
        poly_gdf.set_crs(target_crs, inplace=True)
    else:
        poly_gdf = poly_gdf.to_crs(target_crs)
    return poly_gdf

def perform_spatial_join(gdf_points, polygons_path, field_map, predicate="within"):
    """Helper to perform a single join and return updated GeoDataFrame."""
    print(f"Joining {os.path.basename(polygons_path)}...")
    if not os.path.exists(polygons_path):
        print(f"  Warning: File not found {polygons_path}. Skipping.")
        return gdf_points

    gdf_polygons = load_polygons_any(polygons_path)
    
    # Rename columns as requested
    keep_cols = list(field_map.keys()) + ["geometry"]
    # Filter to only existing columns in the polygon file
    actual_cols = [c for c in keep_cols if c in gdf_polygons.columns]
    gdf_polygons = gdf_polygons[actual_cols].rename(columns=field_map)
    
    # Join
    joined = gpd.sjoin(gdf_points, gdf_polygons, how="left", predicate=predicate)
    
    # Clean up index_right added by geopandas
    if "index_right" in joined.columns:
        joined = joined.drop(columns=["index_right"])
    return joined

def process_full_file(points_csv, boundary_configs, out_csv):
    # 1. Load the full 50,000 row CSV
    print(f"Loading {points_csv}...")
    if not os.path.exists(points_csv):
        print(f"Error: {points_csv} does not exist.")
        return

    df_full = pd.read_csv(points_csv, low_memory=False)
    
    # 2. Separate rows with coordinates from those without
    # This prevents the 50,000 -> 9,800 shrinkage
    has_coords = df_full[DEFAULT_LAT_COL].notna() & df_full[DEFAULT_LON_COL].notna()
    df_valid = df_full[has_coords].copy()
    df_invalid = df_full[~has_coords].copy()
    
    print(f"Processing {len(df_valid)} geocoded rows and preserving {len(df_invalid)} failed rows.")

    if len(df_valid) == 0:
        print("No rows with coordinates found. Saving original file with empty geo columns.")
        df_full.to_csv(out_csv, index=False)
        return

    # 3. Create GeoDataFrame for valid points
    gdf_points = gpd.GeoDataFrame(
        df_valid,
        geometry=gpd.points_from_xy(df_valid[DEFAULT_LON_COL], df_valid[DEFAULT_LAT_COL]),
        crs=DEFAULT_CRS,
    )

    # 4. Chain all spatial joins sequentially
    for config in boundary_configs:
        gdf_points = perform_spatial_join(
            gdf_points, 
            config["path"], 
            config["fields"]
        )

    # 5. Drop geometry column and merge back with the invalid/failed rows
    final_valid_df = pd.DataFrame(gdf_points.drop(columns=["geometry"]))
    final_df = pd.concat([final_valid_df, df_invalid], ignore_index=True)

    # 6. Save final result
    final_df.to_csv(out_csv, index=False)
    print(f"Success! Final output has {len(final_df)} rows.")
    print(f"Saved to {out_csv}")

# ---------- RUN ----------

if __name__ == "__main__":
    # Update these paths to match your actual environment
    base_path = "/content/drive/MyDrive/Projects/Trees/reproducible_files/colab_reference/"
    
    boundaries = [
        {
            "path": base_path + "tracts.geojson", 
            "fields": {"GEOID": "tractFIPS", "NAME": "tract_name"}
        },
        {
            "path": base_path + "WARDS_2015_20251208.geojson", 
            "fields": {"ward": "2015ward"}
        },
        {
            "path": base_path + "Boundaries_-_Wards_(2023-)_20251208.geojson", 
            "fields": {"ward": "2023ward"}
        },
        {
            "path": base_path + "Neighborhoods_2012b_20251208.geojson", 
            "fields": {"pri_neigh": "pri_neigh", "sec_neigh": "sec_neigh"}
        },
        {
            "path": base_path + "Boundaries_-_Community_Areas_20251208.geojson", 
            "fields": {
                "community": "community", 
                "area_numbe": "area_numbe",
                "area_num_1": "area_num_1"
            }
        }
    ]

    process_full_file(
        points_csv=base_path + "geocoded_batch.csv",
        boundary_configs=boundaries,
        out_csv=base_path + "geocoded_batch_with_geos.csv"
    )
