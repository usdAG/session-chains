import httpx
import asyncio

from .http_parser import load_request, parse_response

from .utils import ChainException, UserContext, metadata_path, project_dir, creds_path, config_path, rerror, rprint, rsuccess, rwarning, session_data_path
from .config_parser import parse_config
from .http_parser import send_request


async def main(dry_run=False):
    p_dir = project_dir()
    creds = parse_config(creds_path(p_dir))
    config = parse_config(config_path(p_dir))
    if dry_run:
        config["repeat_after"] = 0
    try:
        tasks = [asyncio.create_task(persist_unauth(config))]
        tasks.append(asyncio.create_task(persist_colors(creds)))
        if creds:
            tasks = [asyncio.create_task(chain(entry, config))
                     for entry in creds]
        await asyncio.gather(*tasks)
    except ChainException:
        rerror("Error detected. Aborting execution of all session-chains...", throw=False)


async def chain(user_config, config):
    proto = config["proto"] if "proto" in config else "https"
    seconds = config["repeat_after"] if "repeat_after" in config else 0
    proxy = config["proxy"] if "proxy" in config else None
    verify = config["verify"] if "verify" in config else not bool(proxy)
    done = False
    if not seconds:
        rprint("Executing chain once...")
        validate_configs(user_config, config)
    user_role = user_config["name"]
    if not user_role.isalnum():
        rerror("The specified user_role is required to be alphanumeric!")
    rprint(f"Executing chain once for user: {user_role}")
    ctx = UserContext(user_role, user_config["variables"], project_dir())
    while not done:
        server_set_cookies = dict()
        try:
            with httpx.Client(http2=True, verify=verify, proxy=proxy, timeout=None, trust_env=False) as client:
                for req in config["requests"]:
                    request = load_request(req["request_file"], ctx)
                    response = send_request(client, request, proto, server_set_cookies, proxy)
                    for key, value in response.cookies.items():
                        server_set_cookies[key] = value
                    extracted_values = parse_response(response, req)
                    ctx.vars.update(extracted_values)
                    persist_values(ctx, extracted_values)
                    rsuccess("Values updated!")
                persist_cookies(ctx, client.cookies)
                if seconds:
                    rprint(f"Next iteration starting in {seconds}. Sleeping...")
                    await asyncio.sleep(seconds)
                else:
                    done = True
        except httpx.HTTPError as e:
            proxy_msg = "This might be due to a proxy problem - did you forget to start BurpSuite?" if proxy else ""
            rerror(f"Request failed: {e}. {proxy_msg}")


async def persist_unauth(config):
    variables = dict()
    for request in config["requests"]:
        if "extract" not in request:
            continue
        for entry in request["extract"]:
            variable = entry["variable"]
            variables[variable] = "UNAUTHENTICATED"
    name = "unauth"
    dir = session_data_path(project_dir()) / name
    dir.mkdir(exist_ok=True, parents=True)
    for key, value in variables.items():
        with open(dir / key, "w") as f:
            f.write(value)


async def persist_colors(creds):
    for entry in creds:
        dir = metadata_path(project_dir()) / "colors"
        dir.mkdir(exist_ok=True, parents=True)
        if "color" in entry:
            with open(dir / entry["color"], "w") as f:
                f.write(entry["name"].strip())


def persist_cookies(ctx: UserContext, cookies):
    dir = session_data_path(ctx.dir) / ctx.role / "cookies"
    dir.mkdir(exist_ok=True, parents=True)
    for cookie in cookies.jar:
        cookie_name = cookie.name
        cookie_value = cookie.value
        with open(dir / cookie_name, "w") as f:
            f.write(cookie_value)


def persist_values(ctx: UserContext, extracted_values):
    dir = session_data_path(ctx.dir) / ctx.role
    dir.mkdir(exist_ok=True, parents=True)
    for key, value in extracted_values.items():
        with open(dir / key, "w") as f:
            f.write(value)


def validate_configs(user_config, config):
    if len(user_config) == 0:
        rwarning("User config is empty or invalid...")
    if "proxy" not in config:
        rwarning(
            "You wont see issued requests in burp as no proxy was specified. Use key 'proxy' to specify a proxy")
    if "proto" not in config:
        rerror("Config is missing key 'proto'. Valid values are: 'http' or 'https'")
    if "repeat_after" not in config:
        rerror("Config missing key 'repeat_after'. Valid values are '0' to run the chain only once or any value > 0 to repeat the chain after the specified amount of seconds")
    if "repeat_after" in config and config["repeat_after"] < 60 and config["repeat_after"] != 0:
        rwarning("Chain loop time is shorter than one minute. Is this intended?")
    if "requests" not in config or not config["requests"]:
        rerror("The configuration is missing references to requests and extraction rules")
