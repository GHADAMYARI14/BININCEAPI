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
"""

import requests
from datetime import datetime, timedelta
import pandas as pd
# This import is specific to Google Colab environments;
# it's not strictly needed for the script to run in non-Colab environments
# (where saving to Drive will be skipped), but it's part of the save_df_to_google_drive function.
# from google.colab import drive
import time

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

        # Fetch one batch of klines. The end_time_ms for get_klines is the overall period end,
        # Binance API will return up to 'limit' klines from current_start_time.
        klines_batch = get_klines(symbol, interval, current_start_time, end_time_ms)

        if klines_batch:
            all_klines.extend(klines_batch)

            # Extract the open time of the last kline in the batch (which is the first element in its list)
            # Binance kline data structure: [open_time, open, high, low, close, volume, close_time, ...]
            last_kline_open_time = int(klines_batch[-1][0])

            # Determine the duration of the interval in milliseconds to advance the start time for the next batch.
            # This ensures that the next fetch starts immediately after the last fetched kline.
            interval_duration_ms = 0
            if interval.endswith('h'): # e.g., '1h', '2h'
                interval_duration_ms = int(interval[:-1]) * 60 * 60 * 1000
            elif interval.endswith('m'): # e.g., '1m', '5m'
                interval_duration_ms = int(interval[:-1]) * 60 * 1000
            elif interval.endswith('d'): # e.g., '1d', '3d'
                interval_duration_ms = int(interval[:-1]) * 24 * 60 * 60 * 1000
            else:
                # Fallback or error for unknown interval format for pagination
                print(f"Warning: Unknown interval format '{interval}'. Defaulting to 1 hour for pagination logic.")
                interval_duration_ms = 60 * 60 * 1000 # Default to 1 hour

            # Move the start time for the next iteration to be one interval period after the last kline's open time
            current_start_time = last_kline_open_time + interval_duration_ms

            # If the number of klines fetched in this batch is less than the API limit (1000),
            # it implies that all available data up to end_time_ms has been retrieved,
            # or there's simply no more data for the symbol in that period.
            if len(klines_batch) < 1000:
                print("Fetched last batch of data (less than 1000 klines received).")
                break
        else:
            # This occurs if get_klines returns an empty list (e.g., API error, no data for the specific window,
            # or current_start_time has passed the actual latest data point but is still less than end_time_ms).
            print("No data returned from API for the current window, or an error occurred. Stopping fetch.")
            break

        # Brief pause to respect API rate limits and avoid being blocked.
        time.sleep(0.5)

    return all_klines

def process_klines_to_dataframe(klines_data: list) -> pd.DataFrame:
    """
    Converts raw kline data (list of lists) into a structured pandas DataFrame.

    The input `klines_data` is expected to be a list where each inner list
    represents a single kline and follows the Binance API's kline data structure:
    [OpenTime, Open, High, Low, Close, Volume, CloseTime, QuoteAssetVolume,
     NumberOfTrades, TakerBuyBaseAssetVolume, TakerBuyQuoteAssetVolume, Ignore]

    This function selects relevant columns, converts timestamps to datetime objects,
    and ensures price/volume columns are numeric.

    Args:
        klines_data: A list of lists, where each inner list is raw kline data from Binance.

    Returns:
        A pandas DataFrame with the processed kline data. Columns include:
        'OpenTime' (datetime), 'Open' (numeric), 'High' (numeric), 'Low' (numeric),
        'Close' (numeric), 'Volume' (numeric), 'CloseTime' (datetime).
        Returns an empty DataFrame if `klines_data` is empty.
    """
    if not klines_data:
        print("No kline data to process. Returning empty DataFrame.")
        return pd.DataFrame()

    # Define column names based on the Binance API documentation for klines
    # See: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#klinecandlestick-data
    columns = [
        'OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume',
        'CloseTime', 'QuoteAssetVolume', 'NumberOfTrades',
        'TakerBuyBaseAssetVolume', 'TakerBuyQuoteAssetVolume', 'Ignore'
    ]
    df = pd.DataFrame(klines_data, columns=columns)

    # Select only the columns typically used for candlestick charts and basic analysis
    df = df[['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', 'CloseTime']]

    # Convert timestamp columns (OpenTime, CloseTime) from milliseconds to datetime objects
    # Binance provides timestamps in milliseconds since epoch.
    df['OpenTime'] = pd.to_datetime(df['OpenTime'], unit='ms')
    df['CloseTime'] = pd.to_datetime(df['CloseTime'], unit='ms')

    # Convert price and volume columns to numeric types, as they might be strings initially
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df[col])

    return df

def save_df_to_google_drive(df: pd.DataFrame, file_name: str = "binance_btcusdt_1h_last_year.csv", drive_base_path: str = "/content/drive/MyDrive/Data"):
    """
    Saves the given pandas DataFrame to a CSV file on Google Drive.

    This function is primarily intended for use in a Google Colab environment,
    as it uses `google.colab.drive` to mount Google Drive. If not in Colab,
    it will print a message and skip saving to Drive.

    Args:
        df: The pandas DataFrame to save.
        file_name: The name for the output CSV file (default: "binance_btcusdt_1h_last_year.csv").
        drive_base_path: The base directory path on Google Drive where the file will be saved
                         (default: "/content/drive/MyDrive/Data"). Assumes this path (or its parent)
                         will be writable after mounting.

    Behavior in non-Colab environments:
        Catches `ModuleNotFoundError` for `google.colab` and prints a message
        indicating that saving to Google Drive is skipped.
    """
    # This function is intended to be used in a Google Colab environment
    try:
        from google.colab import drive # Attempt to import Colab's drive module
        print("Attempting to mount Google Drive...")
        drive.mount('/content/drive', force_remount=True) # Mount Google Drive at /content/drive

        # Optional: Ensure the target directory exists.
        # Requires importing 'os'. If used, uncomment 'import os' at the top of the script or within the function.
        # import os
        # print(f"Ensuring directory {drive_base_path} exists...")
        # os.makedirs(drive_base_path, exist_ok=True)

        full_path = f"{drive_base_path}/{file_name}"
        print(f"Saving DataFrame to Google Drive at: {full_path}")
        df.to_csv(full_path, index=False) # Save DataFrame to CSV, without pandas index
        print(f"Successfully saved data to {full_path}")

    except ModuleNotFoundError:
        # This block executes if 'from google.colab import drive' fails
        print("The 'google.colab' module was not found. This script is likely not running in a Google Colab environment.")
        print(f"Skipping save to Google Drive. If run locally, DataFrame for '{file_name}' would not be saved to Drive.")
        # Optional fallback: Save locally if not in Colab
        # local_path = file_name
        # print(f"Saving DataFrame locally to: {local_path}")
        # df.to_csv(local_path, index=False)
        # print(f"DataFrame saved locally to: {local_path}")

    except Exception as e:
        # Catch any other exceptions during the Drive mounting or saving process
        print(f"An error occurred while attempting to save to Google Drive: {e}")

if __name__ == "__main__":
    # --- Main execution block ---
    # This part of the script runs when it's executed directly (not imported as a module).

    # Note: Binance API access might be restricted based on IP geolocation.
    # If you encounter HTTP errors like 451 or 403, it might be due to such restrictions
    # in the environment where this script is run (e.g., some cloud servers or VPNs).

    print(f"Starting data fetching process for symbol: {SYMBOL}, interval: {INTERVAL}")
    print(f"Fetching data from {datetime.fromtimestamp(ONE_YEAR_AGO_MS/1000)} to {datetime.fromtimestamp(NOW_MS/1000)}")

    # Fetch all kline data for the defined symbol, interval, and period
    all_data = fetch_all_klines_for_period(SYMBOL, INTERVAL, ONE_YEAR_AGO_MS, NOW_MS)

    if all_data:
        print(f"Successfully fetched a total of {len(all_data)} klines.")

        # Process the raw kline data into a pandas DataFrame
        df = process_klines_to_dataframe(all_data)

        if not df.empty:
            print("\nProcessed data into DataFrame:")
            print(f"DataFrame shape: {df.shape}")
            print("First 5 rows of the DataFrame:")
            print(df.head())

            # Attempt to save the DataFrame to Google Drive (if in Colab) or handle non-Colab scenario
            save_df_to_google_drive(df, file_name=f"binance_{SYMBOL.lower()}_{INTERVAL}_data.csv")
        else:
            # This case might occur if processing fails, though process_klines_to_dataframe should return empty if input is empty.
            print("Could not process data into DataFrame, or the resulting DataFrame is empty.")
    else:
        # This case occurs if fetch_all_klines_for_period returns an empty list (e.g., API error, no data found).
        print("No data fetched. Please check parameters, API connectivity, or possible IP restrictions.")

    print("\nScript execution finished.")
