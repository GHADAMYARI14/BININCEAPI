"""
This script fetches historical candlestick (kline) data from the Binance API
for a specified symbol (default BTCUSDT) and interval (default 1-hour)
over a defined period (default past year).

The fetched data is processed into a pandas DataFrame and then saved to a local
CSV file on the user's computer. This version is specifically tailored for
local execution and does not include any cloud integration (e.g., Google Drive).

Key functionalities:
- Fetching kline data in batches from the Binance API using Python's built-in urllib.
- Handling API pagination to retrieve data over extended periods.
- Converting the raw kline data into a structured pandas DataFrame.
- Saving the processed DataFrame to a CSV file in a specified local directory.
"""

# --- Requirements ---
# This script requires the following Python libraries:
# - pandas: For data manipulation and saving to CSV.
#   Install using: pip install pandas
#
# HTTP requests are made using Python's built-in 'urllib.request' and 'urllib.parse' modules.
# JSON processing is done using the built-in 'json' module.
# No external library is needed for HTTP requests.
#
# You may also want to run in a virtual environment to manage dependencies.

import urllib.request
import urllib.parse
import json
# import ssl # Keep this commented for now, add only if specific SSL context is needed.
from datetime import datetime, timedelta
import pandas as pd
import time
import os
import traceback # Retained for detailed error reporting during local file operations.

# --- Constants ---
# Default trading symbol for fetching data (e.g., "BTCUSDT", "ETHUSDT")
SYMBOL = "BTCUSDT"
# Default interval for klines (e.g., "1m", "5m", "1h", "1d")
INTERVAL = "1h" # 1-hour interval
# Start of the data fetching period: one year ago from the current time, in milliseconds.
ONE_YEAR_AGO_MS = int((datetime.now() - timedelta(days=365)).timestamp() * 1000)
# End of the data fetching period: current time, in milliseconds.
NOW_MS = int(datetime.now().timestamp() * 1000)
# Base URL for the Binance public API (v3 for klines).
BINANCE_API_BASE_URL = "https://api.binance.com/api/v3"

def get_klines(symbol, interval, start_time_ms, end_time_ms, limit=1000):
    """
    Fetches historical kline/candlestick data from the Binance API using urllib.request.

    Args:
        symbol: The trading symbol (e.g., "BTCUSDT").
        interval: The kline interval (e.g., "1m", "1h", "1d").
        start_time_ms: The start time for the klines in milliseconds since epoch.
        end_time_ms: The end time for the klines in milliseconds since epoch.
        limit: The maximum number of klines to fetch per request (Binance API max is 1000).

    Returns:
        list: A list of kline data if successful, an empty list otherwise.
              Each kline is a list of values (open time, open, high, low, close, etc.).
    """
    params = {
        'symbol': symbol,
        'interval': interval,
        'startTime': start_time_ms,
        'endTime': end_time_ms,
        'limit': limit
    }
    query_string = urllib.parse.urlencode(params)
    url = f"{BINANCE_API_BASE_URL}/klines?{query_string}"

    print(f"Fetching klines from URL (urllib): {url}")

    try:
        # Using urllib.request to open the URL. Includes a timeout.
        with urllib.request.urlopen(url, timeout=10) as response:
            if response.status == 200:
                response_body = response.read().decode('utf-8')
                klines_data = json.loads(response_body)
                return klines_data
            else:
                # Handles non-200 responses that are not raised as HTTPError immediately by urlopen.
                print(f"Error: Binance API returned status code {response.status} for {symbol}. Response: {response.read().decode('utf-8', errors='ignore')}")
                return []
    except urllib.error.HTTPError as e:
        # Handles specific HTTP errors (e.g., 4XX client errors, 5XX server errors).
        print(f"HTTP Error while fetching klines for {symbol} with urllib: {e.code} {e.reason}. URL: {url}")
        try:
            error_body = e.read().decode('utf-8', errors='ignore') # Try to get more details from response body
            print(f"Error response body: {error_body}")
            if e.code == 451: # Specific handling for 451 error observed previously
                print(f"Received 451 Client Error (Unavailable For Legal Reasons). This is likely an IP block from Binance.")
        except Exception as read_e:
            print(f"Could not read error response body: {read_e}")
        return []
    except urllib.error.URLError as e:
        # Handles broader URL or network related errors (e.g., DNS failure, connection refused, timeout).
        print(f"URL Error while fetching klines for {symbol} with urllib: {e.reason}. URL: {url}")
        if hasattr(e, 'reason') and isinstance(e.reason, ConnectionResetError):
             print(f"ConnectionResetError specifically caught for {symbol}.")
        elif hasattr(e, 'reason') and "timed out" in str(e.reason).lower(): # Check for timeout in reason
             print(f"Request timed out for {symbol}.")
        return []
    except json.JSONDecodeError as e: # Handles errors if the response isn't valid JSON.
        print(f"Error decoding JSON response from Binance API for {symbol}: {e}")
        return []
    except Exception as e:
        # Catch-all for any other unexpected errors during the fetching process.
        print(f"An unexpected error occurred in get_klines ({symbol}) with urllib: {type(e).__name__} - {e}")
        # print(traceback.format_exc()) # Uncomment for full traceback if needed for debugging unexpected issues
        return []

def fetch_all_klines_for_period(symbol: str, interval: str, start_time_ms: int, end_time_ms: int) -> list:
    """
    Fetches all historical kline/candlestick data for a given symbol and interval
    over a specified period, managing API pagination transparently.
    """
    all_klines = []
    current_start_time = start_time_ms
    print(f"Starting to fetch all klines for {symbol} at {interval} interval.")
    while current_start_time < end_time_ms:
        print(f"Fetching batch from {datetime.fromtimestamp(current_start_time/1000)} up to {datetime.fromtimestamp(end_time_ms/1000)}...")
        klines_batch = get_klines(symbol, interval, current_start_time, end_time_ms)
        if klines_batch:
            all_klines.extend(klines_batch)
            last_kline_open_time = int(klines_batch[-1][0])
            interval_duration_ms = 0
            if interval.endswith('h'):
                interval_duration_ms = int(interval[:-1]) * 60 * 60 * 1000
            elif interval.endswith('m'):
                interval_duration_ms = int(interval[:-1]) * 60 * 1000
            elif interval.endswith('d'):
                interval_duration_ms = int(interval[:-1]) * 24 * 60 * 60 * 1000
            else:
                print(f"Warning: Unknown interval format '{interval}'. Defaulting to 1 hour for pagination logic.")
                interval_duration_ms = 60 * 60 * 1000
            current_start_time = last_kline_open_time + interval_duration_ms
            if len(klines_batch) < 1000:
                print("Fetched last batch of data (less than 1000 klines received).")
                break
        else:
            print("No data returned from API for the current window, or an error occurred. Stopping fetch.")
            break
        time.sleep(0.5)
    return all_klines

def process_klines_to_dataframe(klines_data: list) -> pd.DataFrame:
    """
    Converts raw kline data (list of lists) into a pandas DataFrame.
    See Binance API docs for kline data structure.
    """
    if not klines_data:
        print("No kline data to process. Returning empty DataFrame.")
        return pd.DataFrame()
    columns = [
        'OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume',
        'CloseTime', 'QuoteAssetVolume', 'NumberOfTrades',
        'TakerBuyBaseAssetVolume', 'TakerBuyQuoteAssetVolume', 'Ignore'
    ]
    df = pd.DataFrame(klines_data, columns=columns)
    df = df[['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', 'CloseTime']]
    df['OpenTime'] = pd.to_datetime(df['OpenTime'], unit='ms')
    df['CloseTime'] = pd.to_datetime(df['CloseTime'], unit='ms')
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df[col])
    return df

def save_df_to_local_csv(df: pd.DataFrame, directory_path: str, file_name: str = "binance_data.csv"):
    """
    Saves the DataFrame to a CSV file in the specified local directory.
    """
    if df.empty:
        print("DataFrame is empty. No CSV file will be saved.")
        return
    try:
        print(f"Ensuring local directory exists: {directory_path}")
        os.makedirs(directory_path, exist_ok=True)
        full_path = os.path.join(directory_path, file_name)
        print(f"Attempting to save DataFrame locally to: {full_path}")
        df.to_csv(full_path, index=False)
        print(f"Successfully saved data to {full_path}")
    except PermissionError:
        print(f"Error: Permission denied to write to '{directory_path}'. Please check folder permissions.")
        print("Consider running the script with appropriate privileges or choosing a different directory.")
    except IOError as e:
        print(f"Error: An I/O error occurred while saving the file to '{full_path}': {e}")
    except Exception as e:
        print(f"An unexpected error occurred during local save: {type(e).__name__} - {e}")
        print("Traceback:")
        print(traceback.format_exc())

if __name__ == "__main__":
    # Note: Binance API access might be restricted based on IP geolocation.
    # If you encounter HTTP errors like 451 or 403, it might be due to such restrictions
    # when running the script from certain servers or VPNs.

    # Define the local directory path for saving the CSV file.
    # IMPORTANT: Modify this path to a directory where you have write permissions on your system.
    LOCAL_SAVE_DIRECTORY = r"C:\CryptoDataFromScript" # User-specified path
    CSV_FILE_NAME = f"binance_{SYMBOL.lower()}_{INTERVAL}_data.csv"

    print(f"\nStarting data fetching process for symbol: {SYMBOL}, interval: {INTERVAL}")
    print(f"Fetching data from {datetime.fromtimestamp(ONE_YEAR_AGO_MS/1000)} to {datetime.fromtimestamp(NOW_MS/1000)}")
    all_data = fetch_all_klines_for_period(SYMBOL, INTERVAL, ONE_YEAR_AGO_MS, NOW_MS)
    if all_data:
        print(f"Successfully fetched a total of {len(all_data)} klines.")
        df = process_klines_to_dataframe(all_data)
        if not df.empty:
            print("\nProcessed data into DataFrame:")
            print(f"DataFrame shape: {df.shape}")
            print("First 5 rows of the DataFrame:")
            print(df.head())
            print(f"\nDataFrame is ready for saving. Is empty: {df.empty}. Shape: {df.shape}.")
            save_df_to_local_csv(df, LOCAL_SAVE_DIRECTORY, CSV_FILE_NAME)
        else:
            print("\nDataFrame is empty after processing. Nothing to save.")
    else:
        print("No data fetched. Please check parameters, API connectivity, or possible IP restrictions.")
    print("\nScript execution finished.")
