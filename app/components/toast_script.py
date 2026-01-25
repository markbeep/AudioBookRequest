from htpy import link, script
from markupsafe import Markup

with open("app/components/scripts/toast.js", "r") as f:
    content = f.read()


def toast_script(*, base_url: str, version: str):
    return [
        link(
            rel="stylesheet",
            type="text/css",
            href=f"{base_url}/static/toastify.css?v={version}",
        ),
        script(
            type="text/javascript",
            src=f"{base_url}/static/toastify.js?v={version}",
        ),
        script[Markup(content)],
    ]


def toast_success(message: str):
    return script(f'toast("{message}", "success");')


def toast_error(message: str):
    return script(f'toast("{message}", "error");')


def toast_info(message: str):
    return script(f'toast("{message}", "info");')
