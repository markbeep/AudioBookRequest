from htpy import path, svg


def xmark_icon():
    return svg(
        xmlns="http://www.w3.org/2000/svg",
        viewbox="0 0 24 24",
        fill="none",
        stroke="currentColor",
        stroke_linecap="round",
        stroke_linejoin="round",
        style="--darkreader-inline-stroke: currentColor",
        data_darkreader_inline_stroke="",
        width="24",
        height="24",
        stroke_width="2",
    )[path(d="M18 6l-12 12"), path(d="M6 6l12 12")]
