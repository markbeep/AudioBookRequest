from htpy import path, svg


def download_icon():
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
        path(d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2 -2v-2"),
        path(d="M7 11l5 5l5 -5"),
        path(d="M12 4l0 12"),
    ]
