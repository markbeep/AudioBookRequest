from htpy import path, svg


def moon_icon():
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
        path(
            d="M12 3c.132 0 .263 0 .393 0a7.5 7.5 0 0 0 7.92 12.446a9 9 0 1 1 -8.313 -12.454z"
        )
    ]
