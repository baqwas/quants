import requests

def test_yahoo_finance_server_access():
    """
    Tests direct network access to a Yahoo Finance API endpoint with a User-Agent header.
    Handles various HTTP response codes and network-level errors.
    """
    # Using a common and stable Yahoo Finance API endpoint for testing
    url = "https://query1.finance.yahoo.com/v1/finance/trending/us"

    # Define a custom header to mimic a web browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        # Set a short timeout and include the headers in the request
        print(f"Attempting to connect to: {url}")
        print(f"Using User-Agent: {headers['User-Agent']}")
        response = requests.get(url, timeout=10, headers=headers)

        # Print the HTTP response status code
        print(f"Status Code: {response.status_code}")

        # Check for a successful response (status code 200)
        if response.status_code == 200:
            print("SUCCESS: Connection to Yahoo Finance server was successful.")
            print("The issue is likely not a network block or firewall, but might be related to the yfinance library or the specific data request.")
            print("You should try running your original script again.")
        elif 400 <= response.status_code < 500:
            print(f"CLIENT ERROR: The server responded with a {response.status_code} error.")
            print("This could be due to an issue with the request itself (e.g., malformed URL, API changes).")
        elif 500 <= response.status_code < 600:
            print(f"SERVER ERROR: The server responded with a {response.status_code} error.")
            print("This indicates a problem on the Yahoo Finance side. It may be temporary.")
        else:
            print(f"UNEXPECTED STATUS: The server responded with a non-standard status code: {response.status_code}.")

    except requests.exceptions.ConnectionError as e:
        print("CONNECTION ERROR: Failed to connect to the Yahoo Finance server.")
        print("This is the same error you are seeing in your `yfinance` script.")
        print("Possible Causes:")
        print(" - Network connectivity issues (e.g., no internet access).")
        print(" - A firewall or proxy on your system blocking the connection to `fc.yahoo.com` or `query1.finance.yahoo.com`.")
        print(" - The Yahoo Finance server is temporarily down or unreachable.")
        print(f"Error details: {e}")
    except requests.exceptions.Timeout as e:
        print("TIMEOUT ERROR: The request took too long to connect to the server.")
        print("This could indicate a slow or congested network connection to the server.")
        print(f"Error details: {e}")
    except requests.exceptions.RequestException as e:
        print("AN UNEXPECTED ERROR OCCURRED: A different network-related issue occurred.")
        print(f"Error details: {e}")

if __name__ == "__main__":
    test_yahoo_finance_server_access()