import requests

res = requests.get("https://fapi.binance.com/fapi/v1/time")
print(res.status_code)
print(res.text)
