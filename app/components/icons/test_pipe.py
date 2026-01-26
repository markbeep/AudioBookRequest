from htpy import path, svg


def test_pipe_icon():
    return svg(
        xmlns="http://www.w3.org/2000/svg",
        viewbox="0 0 24 24",
        fill="currentColor",
        width="24",
        height="24",
        style="--darkreader-inline-fill: currentColor",
        data_darkreader_inline_fill="",
    )[path(d="M16 2a1 1 0 0 1 0 2v14a4 4 0 1 1 -8 0v-14a1 1 0 1 1 0 -2zm-2 2h-4v7h4z")]
