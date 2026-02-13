import argparse
import os
import re
from pathlib import Path
from types import EllipsisType
from typing import cast

from jinja2 import (
    Environment,
    FileSystemLoader,
    TemplateAssertionError,
    meta,
)
from jinjax import Component
from rich import print


def main():
    argparser = argparse.ArgumentParser(description="Test jinjax parameters")
    argparser.add_argument("templates_dir", type=str, help="Directory for templates")
    argparser.add_argument(
        "-e",
        "--extensions",
        nargs="*",
        default=[".jinja"],
        help="Extensions to test. Defaults to .jinja",
    )
    argparser.add_argument(
        "-g",
        "--globals",
        nargs="*",
        default=[],
        help="Global variables to ignore",
    )
    argparser.add_argument(
        "-f",
        "--filters",
        nargs="*",
        default=[],
        help="Filters to ignore",
    )
    args = argparser.parse_args()

    templates_dir = cast(str, args.templates_dir)
    extensions = set(["." + x.lstrip(".") for x in cast(list[str], args.extensions)])
    global_vars = set(cast(list[str], args.globals))
    filters = set(cast(list[str], args.filters))

    env = Environment(loader=FileSystemLoader(templates_dir))
    for f in filters:
        env.filters[f] = lambda x: x  # pyright: ignore[reportArgumentType]

    tested = 0
    failed = 0
    globals_used = set[str]()
    for path, _, files in os.walk(templates_dir):
        for f in files:
            if any(f.endswith(ext) for ext in extensions):
                tested += 1
                undefined, filters = validate_template(
                    env=env,
                    path=Path(path) / f,
                    globals_used=globals_used,
                    global_vars=global_vars,
                )
                if undefined:
                    print(
                        f"\t[red]Undefined variables:[/red] {Path(path) / f}: {undefined}"
                    )
                if filters:
                    print(
                        f"\t[purple]Undefined filters:[/purple] {Path(path) / f}: {filters}"
                    )
                if undefined or filters:
                    failed += 1

    print(f"\nTested {tested} templates, {failed} failed.")

    for g in global_vars - globals_used:
        print(f"\t[yellow]Unused global variable:[/yellow] {g}")

    if failed > 0:
        exit(1)


env = Environment(loader=FileSystemLoader("templates"))


def validate_template(
    *,
    env: Environment,
    path: Path,
    globals_used: set[str],
    global_vars: set[str] | EllipsisType = ...,
) -> tuple[set[str], set[str]]:
    if global_vars is ...:
        global_vars = set()

    print("[blue]Validating template:[/blue]", path, end="")

    comp = Component(name="test", path=path)
    defined_variables = set(comp.required) | set(comp.optional.keys())

    with open(path, "r") as f:
        source = f.read()
        parsed = env.parse(source)
    try:
        undeclared = meta.find_undeclared_variables(parsed)
    except TemplateAssertionError as e:
        if e.message:
            match = re.match(r"No filter named '(toJSstring)'", e.message)
            if not match:
                raise
            print(" [red]FAIL[/red]")
            return set(), {match.group(1)}
        raise

    globals_used.update(undeclared)

    undefined = undeclared - defined_variables - global_vars
    if undefined:
        print(" [red]FAIL[/red]")
        return undefined, set()

    print(" [green]OK[/green]")
    return set(), set()


if __name__ == "__main__":
    main()
