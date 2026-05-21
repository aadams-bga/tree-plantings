import socket
import requests
import sys

def debug_network():
    target = "geocoding.geo.census.gov"
    print(f"--- Debugging Connection to {target} ---")
    
    # 1. Test DNS Resolution
    try:
        ip = socket.gethostbyname(target)
        print(f"1. DNS Resolve: SUCCESS (IP is {ip})")
    except Exception as e:
        print(f"1. DNS Resolve: FAILED ({e})")
        print("   Hint: This usually means the machine cannot find the server's address.")
        
    # 2. Test Basic HTTPS Connectivity
    try:
        r = requests.get(f"https://{target}/geocoder", timeout=10)
        print(f"2. Simple GET: SUCCESS (Status {r.status_code})")
    except Exception as e:
        print(f"2. Simple GET: FAILED ({e})")
        print("   Hint: If DNS worked but this failed, a firewall or routing issue is blocking the connection.")

    # 3. Test General Internet Connectivity
    try:
        r = requests.get("https://www.google.com", timeout=5)
        print(f"3. General Internet (Google.com): SUCCESS (Status {r.status_code})")
    except Exception as e:
        print(f"3. General Internet: FAILED ({e})")
        print("   Hint: If this fails, the entire machine has no internet access.")

if __name__ == "__main__":
    debug_network()
