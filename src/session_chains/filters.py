import pyotp
import urllib.parse
import json
import base64


def totp(value):
    t = pyotp.TOTP(value)
    return t.now()


def urlenc(value):
    return urllib.parse.quote_plus(value)


def urldec(value):
    return urllib.parse.unquote(value)


def tojson(value):
    return json.dumps(value)


def b64enc(value):
    return base64.b64encode(value.encode()).decode()


def b64dec(value):
    return base64.b64decode(value).decode()


def hexenc(value):
    return value.encode().hex()


def hexdec(value):
    return bytes.fromhex(value).decode()


def upper(value):
    return value.upper()


def lower(value):
    return value.lower()