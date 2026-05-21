import pandas as pd
import numpy as np
import os
import requests
import io
import time
import shutil

# Configuration
INPUT_FILE = '/content/drive/MyDrive/Projects/Trees/reproducible_files/colab_reference/mastertree.csv'
OUTPUT_FILE = '/content/drive/MyDrive/Projects/Trees/reproducible_files/colab_reference/geocoded_batch.csv'
LOCAL_OUTPUT = '/content/geocoded_batch.csv'
CHUNK_SIZE = 2500
START_INDEX = 0

def geocode_batch(chunk_df, max_retries=3):
    """Sends a chunk of addresses to the Census Batch Geocoder with retry logic."""
    batch_input = pd.DataFrame()
    batch_input['id'] = range(len(chunk_df))
    # CRITICAL FIX: Use .values to avoid index alignment issues in chunks after the first one
    batch_input['street'] = chunk_df['address'].astype(str).str.replace(',', '').str.replace('"', '').str.strip().values
    batch_input['city'] = 'Chicago'
    batch_input['state'] = 'Illinois'
    batch_input['zip'] = ''

    url = "https://geocoding.geo.census.gov/geocoder/geographies/addressbatch"
    params = {'benchmark': 'Public_AR_Current', 'vintage': 'Current_Current'}

    last_error = "Unknown Error"

    for attempt in range(max_retries):
        csv_buffer = io.StringIO()
        batch_input.to_csv(csv_buffer, index=False, header=False)
        csv_buffer.seek(0)
        
        files = {'addressFile': ('batch.csv', csv_buffer, 'text/csv')}
        
        try:
            print(f"  Attempt {attempt + 1}/{max_retries}...")
            response = requests.post(url, data=params, files=files, timeout=600)
            
            if response.status_code == 200:
                # If the word 'match' isn't in the response, it's a format error
                if "match" not in response.text.lower():
                    last_error = f"No 'match' keyword. Server said: {response.text[:200]}"
                    continue

                result_df = pd.read_csv(io.StringIO(response.text), header=None, names=[
                    'id', 'input_address', 'status', 'match_type', 'matched_address', 
                    'coords', 'tiger_id', 'side', 'state_fips', 'county_fips', 'tract_code', 'block_code'
                ], dtype={'id': int, 'state_fips': str, 'county_fips': str, 'tract_code': str})
                
                # DEBUG: If 0 matches, show the first 3 raw lines of the response
                if (result_df['status'] == 'Match').sum() == 0:
                    print(f"  DEBUG: Server returned 0 matches. Raw response start:")
                    print("\n".join(response.text.splitlines()[:3]))
                
                return result_df, None
            
            else:
                last_error = f"HTTP {response.status_code}"
        except Exception as e:
            last_error = str(e)
        
        time.sleep(30 * (attempt + 1))

    return None, last_error

def main():
    if os.path.exists(LOCAL_OUTPUT):
        df = pd.read_csv(LOCAL_OUTPUT, low_memory=False)
    elif os.path.exists(OUTPUT_FILE):
        df = pd.read_csv(OUTPUT_FILE, low_memory=False)
    else:
        df = pd.read_csv(INPUT_FILE, low_memory=False)
    
    for col in ['lat', 'long']:
        if col not in df.columns: df[col] = np.nan
        df[col] = df[col].astype(float)
    if 'tractFIPS' not in df.columns: df['tractFIPS'] = ""
    if 'ERRflag' not in df.columns: df['ERRflag'] = ""
    df['ERRflag'] = df['ERRflag'].fillna("").astype(str)

    print(f"Total rows: {len(df)}")

    for i in range(START_INDEX, len(df), CHUNK_SIZE):
        chunk = df.iloc[i:i+CHUNK_SIZE]
        if chunk['lat'].notna().all():
             continue

        print(f"\nProcessing chunk {i // CHUNK_SIZE + 1} ({i} to {min(i + CHUNK_SIZE, len(df))})...")
        # FORCE PRINT addresses for this chunk
        print(f"  First address: {chunk.iloc[0]['address']}")
        
        results, error_msg = geocode_batch(chunk)
        
        if results is not None:
            matches = 0
            chunk_indices = chunk.index.tolist()
            for _, res_row in results.iterrows():
                rel_id = int(res_row['id'])
                if rel_id < len(chunk_indices):
                    idx = chunk_indices[rel_id]
                    if res_row['status'] == 'Match':
                        matches += 1
                        try:
                            lon, lat = res_row['coords'].split(',')
                            df.loc[idx, 'long'] = float(lon)
                            df.loc[idx, 'lat'] = float(lat)
                            df.loc[idx, 'tractFIPS'] = str(res_row['state_fips']) + str(res_row['county_fips']) + str(res_row['tract_code'])
                            df.loc[idx, 'ERRflag'] = "Success"
                        except:
                            df.loc[idx, 'ERRflag'] = "Parse Error"
                    else:
                        df.loc[idx, 'ERRflag'] = res_row['status']
            print(f"  -> Done! Found {matches} matches.")
        else:
            print(f"  -> Failed. {error_msg}")
        
        df.to_csv(LOCAL_OUTPUT, index=False)
        try: shutil.copy(LOCAL_OUTPUT, OUTPUT_FILE)
        except: pass
        
        if i + CHUNK_SIZE < len(df):
            time.sleep(30)

    print("\nGeocoding complete!")

if __name__ == "__main__":
    main()
