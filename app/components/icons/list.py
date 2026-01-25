from htpy import path, svg


def list_icon():
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
    )[
        path(d="M9 6l11 0"),
        path(d="M9 12l11 0"),
        path(d="M9 18l11 0"),
        path(d="M5 6l0 .01"),
        path(d="M5 12l0 .01"),
        path(d="M5 18l0 .01"),
    ]
