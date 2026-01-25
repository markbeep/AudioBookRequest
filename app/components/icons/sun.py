from htpy import path, svg


def sun_icon():
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
        path(d="M12 12m-4 0a4 4 0 1 0 8 0a4 4 0 1 0 -8 0"),
        path(
            d="M3 12h1m8 -9v1m8 8h1m-9 8v1m-6.4 -15.4l.7 .7m12.1 -.7l-.7 .7m0 11.4l.7 .7m-12.1 -.7l-.7 .7"
        ),
    ]
