from htpy import path, svg


def ban_icon():
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
        path(d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0"),
        path(d="M5.7 5.7l12.6 12.6"),
    ]
