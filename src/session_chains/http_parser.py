import re
import jq
from .utils import UserContext, project_dir, request_files_path, rerror, rprint, rwarning
from .request_prep import prepare_raw_request, prepare_headers

from httptools import HttpRequestParser
import httpx

from bs4 import BeautifulSoup


class HTTPContainer:

    def __init__(self):
        self.url = ""
        self.headers = {}
        self.status = ""

    def on_url(self, url: bytes):
        self.url = url.decode()

    def on_header(self, name: bytes, value: bytes):
        self.headers[name.decode()] = value.decode()

    def on_body(self, body: bytes):
        self.body = body.decode()

    def on_status(self, status: bytes):
        self.status = status.decode()


def load_request(req_name, ctx: UserContext):
    rprint(f"Loading request {req_name}...")
    req_path = request_files_path(project_dir()) / req_name
    if not req_path.exists():
        rerror(
            f"The config specifies a file that does not exist: {req_path.absolute()}")
    with open(req_path, 'r') as f:
        raw_request = f.read()
        request = prepare_raw_request(raw_request, ctx)
        return request


def send_request(client: httpx.Client, request: str, proto: str,
                 server_set_cookies, proxy: str = None) -> httpx.Response:
    container = HTTPContainer()
    parser = HttpRequestParser(container)
    try:
        parser.feed_data(str.encode(request))
    except BaseException:
        rwarning(
            "Something went wrong parsing the request... Please check the HTTP verb")
        rerror("If it's not the verb this probably takes a while to debug")

    method = parser.get_method().decode()
    url = container.url
    headers = prepare_headers(container.headers, server_set_cookies)
    host = headers["Host"]
    if "127.0.0.1" in host or "localhost" in host:
        if proto == "https":
            rerror(f"Determined the use of https for {host}. Aborting")

    headers.pop("Content-Length", None)
    url = f"{proto}://{host}{url}"
    body = getattr(container, "body", "").strip()

    rprint(f"Processing request...")

    response = client.request(method, url, headers=headers, data=body)

    return response


def parse_response(response, request) -> dict[str, str]:
    values = {}
    request_name = request["request_file"]
    extract_conf = []
    if "extract" in request:
        extract_conf = request["extract"]
    for entry in extract_conf:
        name = entry["variable"]
        strat = entry["strat"].lower()
        if strat not in ["cssselect", "cookie", "header", "regex", "json"]:
            rerror(f"Config specifies an unknown strat name: {strat}")
        key = entry["key"]
        if strat == "cssselect":
            target = key.split()[-1]
            selector = key[:-len(target) - 1]
            soup = BeautifulSoup(response.text, "html.parser")
            elem = soup.select_one(selector)
            if not elem:
                rerror(f"Could not find element for: {selector}", throw=False)
                rerror(f"Check CSS selector and response in a proxy")
            if target == '.':
                value = elem.text
            elif target[0] == '.' and len(target) > 1:
                value = soup.select_one(selector).get(target[1:])
            else:
                rerror(
                    f"CSS selector broken? Please check the readme and css selector: {key}")
            values[name] = value
        elif strat == "cookie":
            if key not in response.cookies:
                rerror(
                    f"Trying to extract non-existing cookie '{key}' in '{request_name}'")
            value = response.cookies[key]
            values[name] = value
        elif strat == "header":
            if key not in response.headers:
                rerror(
                    f"Trying to extract non-existing header '{key}' in '{request_name}'")
            value = response.headers[key]
            values[name] = value
        elif strat == "regex":
            headers_str = "\r\n".join(
                f"{k}: {v}" for k, v in response.headers.items())
            match = re.search(key, headers_str)
            if not match:
                match = re.search(key, response.text)
            if not match:
                rerror(f"Regex broken? Could not find match for regex: {key}")
            value = match.group(1)
            values[name] = value
        elif strat == "json":
            value = jq.compile(key).input_text(response.text).first()
            if not value:
                rerror(
                    f"jq statement broken? Could not find match for expression: {key}")
            values[name] = value

    return values
