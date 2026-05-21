import json
import pandas as pd
import numpy as np
import os
import requests
import time # Import the time module

df = pd.read_csv('/content/drive/MyDrive/Projects/Trees/reproducible_files/colab_reference/mastertree.csv',low_memory=False)

df['lat'] = np.nan
df['long'] = np.nan
df['tractFIPS'] = np.nan
df['ERRflag'] = ""

output_filename = '/content/drive/MyDrive/Projects/Trees/reproducible_files/colab_reference/geocoded0-1000.csv'

chunk_size = 1000
processed_rows_batch = []

start_index = 0

if start_index == 0:
  if os.path.exists(output_filename):
     os.remove(output_filename)

for index, row in df.iterrows():
  if index < start_index:
    continue

  if index % 100 == 0 or index < 25 + start_index:
    print(index)

  try:
    # Use Census API for both coordinates and tract info in one request
    params = {
        'street': row.address,
        'city': 'Chicago',
        'state': 'IL',
        'benchmark': 'Public_AR_Current',
        'vintage': 'Current_Current',
        'format': 'json'
    }
    response = requests.get("https://geocoding.geo.census.gov/geocoder/geographies/address", params=params, timeout=15)

    if response.status_code == 200:
        data = response.json()
        matches = data.get('result', {}).get('addressMatches', [])
        if matches:
            match = matches[0]
            df.loc[index, 'lat'] = match['coordinates']['y']
            df.loc[index, 'long'] = match['coordinates']['x']

            tracts = match.get('geographies', {}).get('Census Tracts', [])
            if tracts:
                if len(tracts) > 1:
                    df.loc[index, 'ERRflag'] = "border"
                df.loc[index, 'tractFIPS'] = int(tracts[0]['GEOID'])
        else:
            print(f"Could not geocode address: {row.address}")
    elif response.status_code == 429: # Rate limited
        df.loc[index, 'ERRflag'] = "Rate Limited"
        print(f"Geocoding rate limited for address: {row.address}. Pausing for 5 seconds.")
        time.sleep(5)
        continue
    else:
        df.loc[index, 'ERRflag'] = f"HTTP Error {response.status_code}"
        print(f"HTTP error {response.status_code} for address: {row.address}")

  except requests.exceptions.Timeout:
    df.loc[index, 'ERRflag'] = "Geocode Timeout"
    print(f"Geocoding timed out for address: {row.address}")
  except requests.exceptions.RequestException as e:
    df.loc[index, 'ERRflag'] = "Request Error"
    print(f"Request error for address: {row.address}: {e}")

  # Add a small delay after each geocoding request to respect rate limits
  time.sleep(1)

  processed_rows_batch.append(df.iloc[index])

  if (index + 1) % chunk_size == 0 or (index + 1) == len(df):
    batch_df = pd.DataFrame(processed_rows_batch)
    if not os.path.exists(output_filename):
        batch_df.to_csv(output_filename, mode='w', index=False, header=True)
    else:
        batch_df.to_csv(output_filename, mode='a', index=False, header=False)
    print(f"Exported {len(batch_df)} rows to {output_filename} at index {index}")
    processed_rows_batch = []
