import pandas as pd
import numpy as np
import os
import requests
import io
import time
import shutil

# Configuration
INPUT_FILE = '/content/drive/MyDrive/Projects/Trees/reproducible_files/colab_reference/mastertree.csv'
OUTPUT_FILE = '/content/drive/MyDrive/Projects/Trees/reproducible_files/colab_reference/geocoded_batch_2010.csv'
LOCAL_OUTPUT = '/content/geocoded_batch.csv'
CHUNK_SIZE = 2500
START_INDEX = 0

def geocode_batch(chunk_df, max_retries=3):
    """Sends a chunk of addresses to the Census Batch Geocoder with retry logic."""
    batch_input = pd.DataFrame()
    # Use DataFrame index directly as unique ID for direct mapping
    batch_input['id'] = chunk_df.index.values
    # Clean and prepare street addresses
    batch_input['street'] = chunk_df['address'].astype(str).str.replace(',', '').str.replace('"', '').str.strip().values
    batch_input['city'] = 'Chicago'
    batch_input['state'] = 'Illinois'
    batch_input['zip'] = ''

    url = "https://geocoding.geo.census.gov/geocoder/geographies/addressbatch"
    # To get 2010 Census Tracts, use Public_AR_Current benchmark with Census2010_Current vintage
    params = {'benchmark': 'Public_AR_Current', 'vintage': 'Census2010_Current'}

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
        print(f"Loading data from LOCAL_OUTPUT: {LOCAL_OUTPUT}")
        df = pd.read_csv(LOCAL_OUTPUT, low_memory=False)
    elif os.path.exists(OUTPUT_FILE):
        print(f"Loading data from OUTPUT_FILE: {OUTPUT_FILE}")
        df = pd.read_csv(OUTPUT_FILE, low_memory=False)
    else:
        print(f"Loading data from INPUT_FILE: {INPUT_FILE}")
        df = pd.read_csv(INPUT_FILE, low_memory=False)

    for col in ['lat', 'long']:
        if col not in df.columns: 
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    if 'tractFIPS' not in df.columns: 
        df['tractFIPS'] = ""
    else:
        df['tractFIPS'] = df['tractFIPS'].fillna("").astype(str)
        # Clean any float representations like '17031840300.0' or 'nan'
        df['tractFIPS'] = df['tractFIPS'].replace(['nan', 'NaN', 'None', 'nan.0', 'NaN.0'], '')
        df['tractFIPS'] = df['tractFIPS'].apply(lambda x: x.split('.')[0] if '.' in x else x)
        
    if 'ERRflag' not in df.columns: 
        df['ERRflag'] = ""
    else:
        df['ERRflag'] = df['ERRflag'].fillna("").astype(str)
        df['ERRflag'] = df['ERRflag'].replace(['nan', 'NaN', 'None'], '')

    # Diagnostic check
    valid_coords = df[df['lat'].notna() & df['long'].notna()]
    already_geocoded = df[df['tractFIPS'].notna() & (df['tractFIPS'] != "")]
    needs_geocoding_total = df[
        (df['tractFIPS'] == "") &
        (~df['ERRflag'].isin(["No_Match", "Parse Error"]))
    ]

    print(f"\n--- Diagnostic Summary ---")
    print(f"Total rows: {len(df)}")
    print(f"  - Rows with valid coordinates: {len(valid_coords)}")
    print(f"  - Rows already geocoded (tractFIPS populated): {len(already_geocoded)}")
    print(f"  - Rows needing geocoding: {len(needs_geocoding_total)}")
    print(f"---------------------------\n")

    if len(needs_geocoding_total) == 0:
        print("All rows are already processed. Exiting early.")
        return

    for i in range(START_INDEX, len(df), CHUNK_SIZE):
        chunk = df.iloc[i:i+CHUNK_SIZE]
        
        # Filter down to rows in this chunk that need geocoding
        needs_geocoding = chunk[
            (chunk['tractFIPS'] == "") &
            (~chunk['ERRflag'].isin(["No_Match", "Parse Error"]))
        ]
        
        if len(needs_geocoding) == 0:
            continue

        print(f"\nProcessing chunk {i // CHUNK_SIZE + 1} ({i} to {min(i + CHUNK_SIZE, len(df))})...")
        print(f"  First address: {needs_geocoding.iloc[0]['address']}")
        print(f"  Geocoding {len(needs_geocoding)} records...")

        results, error_msg = geocode_batch(needs_geocoding)

        if results is not None:
            matches = 0
            for _, res_row in results.iterrows():
                idx = int(res_row['id'])
                if res_row['status'] == 'Match':
                    matches += 1
                    try:
                        lon, lat = res_row['coords'].split(',')
                        df.loc[idx, 'long'] = float(lon)
                        df.loc[idx, 'lat'] = float(lat)
                        # Build 11-digit tract FIPS code
                        df.loc[idx, 'tractFIPS'] = str(res_row['state_fips']) + str(res_row['county_fips']) + str(res_row['tract_code'])
                        df.loc[idx, 'ERRflag'] = "Success"
                    except Exception as e:
                        df.loc[idx, 'ERRflag'] = f"Parse Error: {str(e)}"
                else:
                    df.loc[idx, 'ERRflag'] = res_row['status']
            print(f"  -> Done! Found {matches} matches.")
        else:
            print(f"  -> Failed. {error_msg}")

        df.to_csv(LOCAL_OUTPUT, index=False)
        try: 
            shutil.copy(LOCAL_OUTPUT, OUTPUT_FILE)
        except Exception as e:
            print(f"  Warning: Could not copy to output file: {e}")

        if i + CHUNK_SIZE < len(df):
            time.sleep(30)

    print("\nGeocoding complete!")

if __name__ == "__main__":
    main()
