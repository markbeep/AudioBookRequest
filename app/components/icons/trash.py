from htpy import path, svg


def trash_icon():
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
    )[
        path(d="M4 7h16"),
        path(d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12"),
        path(d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3"),
        path(d="M10 12l4 4m0 -4l-4 4"),
    ]
