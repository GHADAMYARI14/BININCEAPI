"""
This script fetches historical candlestick (kline) data from the Binance API
for a specified symbol (default BTCUSDT) and interval (default 1-hour)
over a defined period (default past year).

The fetched data is then processed into a pandas DataFrame, and if the script
is run in a Google Colab environment, it attempts to save the DataFrame as a CSV
file to Google Drive. Otherwise, it indicates that saving to Drive is skipped.

Key functionalities:
- Fetching kline data in batches from Binance.
- Handling pagination to retrieve data over extended periods.
- Converting raw kline data into a structured pandas DataFrame.
- Optional saving of the DataFrame to Google Drive (primarily for Colab).
- Includes a test function for diagnosing Google Drive saving issues.

For Google Colab Users:
- Google Drive Authorization: You'll be prompted for Drive access.
- File Paths: Defaults to '/content/drive/MyDrive/Data/' for main data
  and '/content/drive/MyDrive/Data_Test/' for test data.
- API Access: Binance might restrict Colab IPs (451 error).
- Test Function: Use `test_google_drive_save()` to debug Drive issues.
"""

import requests
from datetime import datetime, timedelta
import pandas as pd
# This import is specific to Google Colab environments;
# it's not strictly needed for the script to run in non-Colab environments
# (where saving to Drive will be skipped), but it's part of the save_df_to_google_drive function.
# from google.colab import drive
import time
import os
import traceback

# --- Constants ---
# Default trading symbol for fetching data
SYMBOL = "BTCUSDT"
# Default interval for klines (e.g., "1m", "1h", "1d")
INTERVAL = "1h" # 1-hour interval
# Start of the data fetching period: one year ago from now, in milliseconds
ONE_YEAR_AGO_MS = int((datetime.now() - timedelta(days=365)).timestamp() * 1000)
# End of the data fetching period: current time, in milliseconds
NOW_MS = int(datetime.now().timestamp() * 1000)
# Base URL for the Binance public API v3
BINANCE_API_BASE_URL = "https://api.binance.com/api/v3"

def get_klines(symbol: str, interval: str, start_time_ms: int, end_time_ms: int, limit: int = 1000) -> list:
    """
    Fetches a single batch of historical kline/candlestick data from Binance.

    Args:
        symbol: The trading symbol (e.g., "BTCUSDT").
        interval: The kline interval (e.g., "1m", "1h", "1d").
        start_time_ms: The start time for the klines in milliseconds since epoch.
        end_time_ms: The end time for the klines in milliseconds since epoch.
        limit: The maximum number of klines to fetch per request (max 1000, default 1000).

    Returns:
        A list of kline data, where each kline is itself a list of values
        representing [OpenTime, Open, High, Low, Close, Volume, CloseTime, ...].
        Returns an empty list if an error occurs during the API request or if no data is found.
    """
    endpoint = f"{BINANCE_API_BASE_URL}/klines"
    # Parameters for the Binance API /klines endpoint
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_time_ms,
        "endTime": end_time_ms,
        "limit": limit  # Binance API caps this at 1000
    }
    try:
        response = requests.get(endpoint, params=params)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4XX or 5XX)
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        # Handle network-related errors (e.g., connection issues)
        print(f"Error fetching klines for {symbol}: {e}")
        return []
    except ValueError as e: # Handle cases where response is not valid JSON
        print(f"Error decoding JSON response for {symbol}: {e}")
        return []

def fetch_all_klines_for_period(symbol: str, interval: str, start_time_ms: int, end_time_ms: int) -> list:
    """
    Fetches all historical kline/candlestick data for a given symbol and interval
    over a specified period, handling API pagination.

    The Binance API limits kline requests to a certain number of data points (e.g., 1000).
    This function makes multiple calls to `get_klines` to retrieve all data if the
    period is longer than what one call can return.

    Args:
        symbol: The trading symbol (e.g., "BTCUSDT").
        interval: The kline interval (e.g., "1m", "1h", "1d").
        start_time_ms: The overall start time for the data fetching period in milliseconds.
        end_time_ms: The overall end time for the data fetching period in milliseconds.

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
    Converts raw kline data (list of lists) into a structured pandas DataFrame.
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

def save_df_to_google_drive(df: pd.DataFrame, file_name: str = "binance_btcusdt_1h_last_year.csv", drive_base_path: str = "/content/drive/MyDrive/Data"):
    """
    Saves DataFrame to Google Drive (Colab only).
    Handles Drive mounting, path creation, and common errors.
    """
    print(f"\nInside save_df_to_google_drive. Received DataFrame. Is empty: {df.empty}. Shape: {df.shape}.")
    if df.empty:
        print("DataFrame is empty. Aborting save operation.")
        return

    try:
        from google.colab import drive
        print("Attempting to mount Google Drive...")
        # This will prompt for Google Drive authorization in Colab.
        # Ensure you complete the authentication steps in the Colab UI.
        drive.mount('/content/drive', force_remount=True)

        print(f"Ensuring directory exists: {drive_base_path}")
        # If saving fails, check:
        # 1. Google Drive was successfully mounted and authorized.
        # 2. The Colab notebook has permissions to write to Google Drive.
        # 3. The path specified in 'drive_base_path' is correct and you have write permissions there.
        # 4. Sufficient space is available in your Google Drive.
        os.makedirs(drive_base_path, exist_ok=True)

        full_path = f"{drive_base_path}/{file_name}"
        print(f"Saving DataFrame to Google Drive at: {full_path}")
        df.to_csv(full_path, index=False)
        print(f"Successfully saved data to {full_path}")

    except ModuleNotFoundError:
        print("The 'google.colab' module was not found. This script is likely not running in a Google Colab environment.")
        print(f"Skipping save to Google Drive. If run locally, DataFrame for '{file_name}' would not be saved to Drive.")
    except Exception as e:
        print(f"An error occurred during Google Drive operations: {type(e).__name__} - {e}")
        print("Traceback:")
        print(traceback.format_exc())

def test_google_drive_save(test_file_name="test_drive_save.csv", drive_base_path="/content/drive/MyDrive/Data_Test"):
    """
    Tests saving a simple DataFrame to Google Drive.
    Helps isolate issues with Drive mounting, path creation, or permissions.
    Uses a distinct path: /content/drive/MyDrive/Data_Test
    """
    print(f"\n--- Starting Google Drive Save Test ---")
    test_data = {'col1': [1, 2], 'col2': ['A', 'B']}
    test_df = pd.DataFrame(test_data)
    print(f"Created test DataFrame. Is empty: {test_df.empty}. Shape: {test_df.shape}.")
    print(test_df.head())

    try:
        from google.colab import drive
        print("Attempting to mount Google Drive for test...")
        # This will prompt for Google Drive authorization in Colab.
        # Ensure you complete the authentication steps in the Colab UI.
        drive.mount('/content/drive', force_remount=True)

        target_test_path = f"{drive_base_path}"
        print(f"Ensuring test directory exists: {target_test_path}")
        # If saving fails here, check points similar to the main save function:
        # 1. Drive mounted and authorized.
        # 2. Colab permissions for Drive write access.
        # 3. Correctness of 'drive_base_path' and permissions for it.
        # 4. Drive space.
        os.makedirs(target_test_path, exist_ok=True)

        full_test_path = os.path.join(target_test_path, test_file_name)
        print(f"Attempting to save test DataFrame to: {full_test_path}")
        test_df.to_csv(full_test_path, index=False)
        print(f"Successfully saved test DataFrame to {full_test_path}")

    except ModuleNotFoundError as mnfe:
        if 'google.colab' in str(mnfe):
            print("TEST SAVE: 'google.colab' module not found. Skipping Google Drive test.")
        else:
            print(f"TEST SAVE: A required module was not found: {mnfe}")
    except Exception as e:
        print(f"TEST SAVE: An error occurred: {type(e).__name__} - {e}")
        print("TEST SAVE Traceback:")
        print(traceback.format_exc())
    finally:
        print(f"--- Finished Google Drive Save Test ---")

if __name__ == "__main__":
    # --- Notes for Running in Google Colab ---
    # 1. Google Drive Authorization: When the script attempts to save data (either main or test),
    #    Colab will ask for permission to access your Google Drive. You'll
    #    need to click a link, sign in, copy an authorization code, and paste
    #    it back into the Colab prompt. This needs to be done each time Drive is mounted
    #    unless permissions are cached or a more permanent setup is used.
    # 2. File Paths: Data is intended to be saved in your 'My Drive'.
    #    The default path for main data is '/content/drive/MyDrive/Data/'.
    #    The test function uses '/content/drive/MyDrive/Data_Test/'.
    #    Ensure these paths are suitable or modify them in the script's constants or function calls.
    # 3. Permissions & Errors: If you encounter errors during saving (e.g., after "Ensuring directory exists..."):
    #    - Double-check that the Colab notebook has the necessary permissions (granted during authorization).
    #    - Verify the specific folder path is writable and the full path is valid.
    #    - Ensure sufficient space in your Google Drive.
    #    - The error traceback (printed by the script) can provide clues.
    # 4. API Access: Binance API access might be restricted from certain IP ranges,
    #    including some Colab servers. If no data is fetched (often a 451 or 403 error),
    #    this might be the cause. The script is designed to handle this by
    #    not attempting to save an empty file if no data is retrieved.
    # 5. `google.colab` import: The script imports `google.colab.drive` dynamically within
    #    the save functions. This is generally fine for Colab. No top-level uncommenting is needed.
    # 6. Using the Test Save Function: If the main data saving process fails,
    #    it's highly recommended to uncomment the `test_google_drive_save()` call below.
    #    This helps isolate whether the problem is with Google Drive integration itself
    #    or with the data fetching/processing parts of the script.
    # --- End of Colab Notes ---

    # --- Google Drive Save Test (Optional) ---
    # test_google_drive_save()
    # print("-" * 50) # Separator after the test

    # --- Main execution block ---
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
            print(f"\nPreparing to save DataFrame. Is empty: {df.empty}. Shape: {df.shape}.")
            save_df_to_google_drive(df, file_name=f"binance_{SYMBOL.lower()}_{INTERVAL}_data.csv")
        else:
            print("\nDataFrame is empty after processing. Nothing to save.")
    else:
        print("No data fetched. Please check parameters, API connectivity, or possible IP restrictions.")

    print("\nScript execution finished.")
