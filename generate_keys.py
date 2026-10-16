import secrets,base64
print('SESSION_SECRET='+secrets.token_urlsafe(48))
print('DATA_KEY_B64='+base64.b64encode(secrets.token_bytes(32)).decode())
