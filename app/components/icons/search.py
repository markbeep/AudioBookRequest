from htpy import path, svg


def search_icon():
    return svg(
        xmlns="http://www.w3.org/2000/svg",
        viewbox="0 0 24 24",
        fill="none",
        stroke="currentColor",
        stroke_linecap="round",
        stroke_linejoin="round",
        width="24",
        height="24",
        stroke_width="2",
        style="--darkreader-inline-stroke: currentColor",
        data_darkreader_inline_stroke="",
    )[path(d="M10 10m-7 0a7 7 0 1 0 14 0a7 7 0 1 0 -14 0"), path(d="M21 21l-6 -6")]
