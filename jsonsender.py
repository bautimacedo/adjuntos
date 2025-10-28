import requests



def enviar():
    # URL de FlytBase
       # URL de FlytBase
    url = "https://api.flytbase.com/v2/integrations/webhook/6900081026671ac289bfd766"

    # Headers con tu token de autorización
    headers = {
        "Authorization": "Bearer eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJmMzhlODM5NS1jMzFhLTRjZDMtOGIxNi0yNGJjNWY2MjVjN2MiLCJhdWQiOiIxOGRlNmVkYy05NGVmLTRiMGItYjA3ZS1iZjNjNTY5N2JhZGEiLCJzdWIiOiI2OGM0NGVhNzg4NzJmZDkxMzA1ZmEyOTUiLCJvaWQiOiI2OGM2MDIzMGRjMTVkNzk1MGZjN2NhNjIiLCJ1c2VyX3R5cGUiOjEsInVzZXJfaWQiOiI2ODcyOTRiOTY3NDJkOTk5NTcyMTZlOTgiLCJzY29wZXMiOltdLCJpYXQiOjE3NjE2NTgzODIsImV4cCI6NDkxNzQxODM4Mn0.MRtM3Ak_zNGrypm3tneq38pT3745BZsgfIGK8eiqZcG217oH1NG-Jjh-6Zt3T29pABFMIF14Q8jjTQLzca7MiA7aYPZMvBxKAYmv1HdKkdX8vzO8Xo6Rql-OpLLdDG2N6BYW3iuwhoZnei9bxLujELFLWn-NQV8Pp2f-JhzHKEli5oCCF4Z-POjTa9fdADH2TJrAOP7GPEVTpHwwxQ4_mmi-POrfVQdi_6SdUqaO-NIvbTP3SdeRfHzl_B_ZoYIymokEoRzKBKPe7sk9tMlY8tZn3KDBAfSTp5eopPYMLnG1IOvAAqevO7HMuLjdcimRUpqU0F25bSHl2nsfsfTs94UG4fSW4EsR9EJKugTnd86-j84xf3nqSEdIUHVlxrtOZxA7qnEYnRKVzLYBBEUIVoxfi3EZVs7i65ozFC16A1kt18I5oW-QL5zzFGOQOD-7WZCWkVVy7gpqv0ZWy4h1UOoq6n00gFot0bR5KHFTSVHKJqWlo_2-1qXlP2LF3L8C58jocV50ANUK7-Duw9HIGfS2MKM1rrtUuowdSgSmv5jW7rTFY9vyoH2tpOvYHmsklCfA9OVr1h6swnulVtaOwNR6b2sk0KZI9NlE_ucqHseQhwXkuIlnixjKBWgSdy7f5_CgiDM7D1Y91dsWEBygdwOWkjC89Bd2PX-Xzgq6mI0",   # 👈 pegá tu token
        "Content-Type": "application/json"
    }

    # Tu JSON
    payload = {
        "timestamp": 1759445058883,
        "severity": 2,
        "description": "High temperature",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "altitude_msl": 100,
        "metadata": {
            "sensor_id": "TempSensor12A",
            "temperature": 50.2,
            "battery_level": 80
        }
    }
    # POST a FlytBase

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()  # <- esto hace tire excepción
    return response.json()   

    