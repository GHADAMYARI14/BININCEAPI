"""
This script fetches historical candlestick (kline) data from the Binance API
for a specified symbol (default BTCUSDT) and interval (default 1-hour)
over a defined period (default past year).

The fetched data is processed into a pandas DataFrame and then saved to a local
CSV file on the user's computer. This version is specifically tailored for
local execution and does not include any cloud integration (e.g., Google Drive).

Key functionalities:
- Fetching kline data in batches from the Binance API.
- Handling API pagination to retrieve data over extended periods.
- Converting the raw kline data into a structured pandas DataFrame.
- Saving the processed DataFrame to a CSV file in a specified local directory.
"""

# --- Requirements ---
# This script requires the following Python libraries:
# - requests: For making HTTP requests to the Binance API.
#   Install using: pip install requests
# - pandas: For data manipulation and saving to CSV.
#   Install using: pip install pandas
#
# You may also want to run in a virtual environment to manage dependencies.

import requests
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

def get_klines(symbol: str, interval: str, start_time_ms: int, end_time_ms: int, limit: int = 1000) -> list:
    """
    Fetches a single batch of historical kline/candlestick data from Binance.

    Args:
        symbol: The trading symbol (e.g., "BTCUSDT").
        interval: The kline interval (e.g., "1m", "1h", "1d").
        start_time_ms: The start time for the klines in milliseconds since epoch.
        end_time_ms: The end time for the klines in milliseconds since epoch.
        limit: The maximum number of klines to fetch per request (Binance API max is 1000).

    Returns:
        A list of kline data. Each kline is a list of values:
        [OpenTime, Open, High, Low, Close, Volume, CloseTime, QuoteAssetVolume,
         NumberOfTrades, TakerBuyBaseAssetVolume, TakerBuyQuoteAssetVolume, Ignore].
        Returns an empty list if an error occurs or no data is found.
    """
    endpoint = f"{BINANCE_API_BASE_URL}/klines"
    # Parameters for the Binance API /klines endpoint
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_time_ms,
        "endTime": end_time_ms,
        "limit": limit  # Binance API will cap results at this limit
    }
    try:
        response = requests.get(endpoint, params=params)
        response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        # Handles network-related errors (e.g., connection timeout, DNS failure)
        print(f"Network error while fetching klines for {symbol}: {e}")
        return []
    except ValueError as e: # Handles errors in decoding JSON response
        print(f"Error decoding JSON response for {symbol}: {e}")
        return []

def fetch_all_klines_for_period(symbol: str, interval: str, start_time_ms: int, end_time_ms: int) -> list:
    """
    Fetches all historical kline/candlestick data for a given symbol and interval
    over a specified period, managing API pagination transparently.

    Args:
        symbol: The trading symbol.
        interval: The kline interval.
        start_time_ms: The overall start time for the data fetching period (milliseconds).
        end_time_ms: The overall end time for the data fetching period (milliseconds).

    Returns:
        A list containing all kline data fetched for the period. Each kline is a list
        of values. Returns an empty list if no data is fetched or an error occurs.
    """
    all_klines = []
    current_start_time = start_time_ms
    print(f"Starting to fetch all klines for {symbol} at {interval} interval.")

    while current_start_time < end_time_ms:
        print(f"Fetching batch from {datetime.fromtimestamp(current_start_time/1000)} up to {datetime.fromtimestamp(end_time_ms/1000)}...")
        klines_batch = get_klines(symbol, interval, current_start_time, end_time_ms)

        if klines_batch:
            all_klines.extend(klines_batch)
            # Update start time for the next batch to be after the last fetched kline's open time
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
                interval_duration_ms = 60 * 60 * 1000 # Default to 1 hour

            current_start_time = last_kline_open_time + interval_duration_ms

            # If fewer than the limit klines were returned, it means we've reached the end of available data
            if len(klines_batch) < 1000:
                print("Fetched last batch of data (less than 1000 klines received).")
                break
        else:
            # This occurs if get_klines returns empty (e.g., API error, or no more data in the range)
            print("No data returned from API for the current window, or an error occurred. Stopping fetch.")
            break

        # Brief pause to respect API rate limits
        time.sleep(0.5)
    return all_klines

def process_klines_to_dataframe(klines_data: list) -> pd.DataFrame:
    """
    Converts raw kline data (list of lists) into a pandas DataFrame.

    The input `klines_data` is a list of lists, with each inner list representing
    a single kline according to Binance API's structure (e.g., OpenTime, Open, High, etc.).
    This function selects key columns, converts timestamps to datetime objects,
    and ensures price/volume columns are numeric.

    Args:
        klines_data: A list of lists, where each inner list is raw kline data.

    Returns:
        A pandas DataFrame with processed kline data, including columns like
        'OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', 'CloseTime'.
        Returns an empty DataFrame if input is empty.
    """
    if not klines_data:
        print("No kline data to process. Returning empty DataFrame.")
        return pd.DataFrame()

    # Standard column names based on Binance API documentation for klines
    columns = [
        'OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume',
        'CloseTime', 'QuoteAssetVolume', 'NumberOfTrades',
        'TakerBuyBaseAssetVolume', 'TakerBuyQuoteAssetVolume', 'Ignore'
    ]
    df = pd.DataFrame(klines_data, columns=columns)

    # Select a subset of columns for typical use
    df = df[['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', 'CloseTime']]

    # Convert millisecond timestamps to datetime objects
    df['OpenTime'] = pd.to_datetime(df['OpenTime'], unit='ms')
    df['CloseTime'] = pd.to_datetime(df['CloseTime'], unit='ms')

    # Ensure price and volume columns are numeric
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df[col])
    return df

def save_df_to_local_csv(df: pd.DataFrame, directory_path: str, file_name: str = "binance_data.csv"):
    """
    Saves the DataFrame to a CSV file in the specified local directory.

    Args:
        df (pd.DataFrame): The DataFrame to save.
        directory_path (str): The path to the local directory where the CSV file should be saved.
                              This path should be writable by the script.
                              Example for Windows: r"C:\CryptoData"
                              Example for Linux/macOS: "./crypto_output_data"
        file_name (str, optional): The name of the CSV file.
                                   Defaults to "binance_data.csv".
    """
    if df.empty:
        print("DataFrame is empty. No CSV file will be saved.")
        return

    try:
        # Create the target directory if it doesn't exist.
        # os.makedirs with exist_ok=True will not raise an error if the directory already exists.
        print(f"Ensuring local directory exists: {directory_path}")
        os.makedirs(directory_path, exist_ok=True)

        full_path = os.path.join(directory_path, file_name)
        print(f"Attempting to save DataFrame locally to: {full_path}")
        df.to_csv(full_path, index=False) # Save without pandas DataFrame index
        print(f"Successfully saved data to {full_path}")

    except PermissionError:
        print(f"Error: Permission denied to write to '{directory_path}'. Please check folder permissions.")
        print("Consider running the script with appropriate privileges or choosing a different directory.")
    except IOError as e: # Catches file I/O errors (e.g., disk full, invalid path characters)
        print(f"Error: An I/O error occurred while saving the file to '{full_path}': {e}")
    except Exception as e:
        # Catch any other unexpected errors during file operations
        print(f"An unexpected error occurred during local save: {type(e).__name__} - {e}")
        print("Traceback:")
        print(traceback.format_exc())


if __name__ == "__main__":
    # Note: Binance API access might be restricted based on IP geolocation.
    # If you encounter HTTP errors like 451 or 403, it might be due to such restrictions
    # when running the script from certain servers or VPNs.

    # Define the local directory path for saving the CSV file.
    # IMPORTANT: Modify this path to a directory where you have write permissions on your system.
    # Example for Windows: LOCAL_SAVE_DIRECTORY = r"C:\Users\YourUsername\Documents\CryptoData"
    # Example for macOS/Linux: LOCAL_SAVE_DIRECTORY = "/home/YourUsername/Documents/CryptoData"
    # Using a raw string (r"...") is recommended for Windows paths to handle backslashes correctly.
    LOCAL_SAVE_DIRECTORY = r"C:\CryptoDataFromScript" # User-specified path

    # Define the CSV file name. It incorporates the symbol and interval for clarity.
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
        # This typically occurs if the API request fails (e.g., network issue, API error like 451/403)
        # or if no data exists for the specified symbol/interval/period.
        print("No data fetched. Please check parameters, API connectivity, or possible IP restrictions.")

    print("\nScript execution finished.")
