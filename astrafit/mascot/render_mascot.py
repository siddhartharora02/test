"""Rasterise the AstraFit panther mascot SVG to transparent PNGs.

    pip install cairosvg
    python3 astrafit/mascot/render_mascot.py            # -> astrafit/mascot/panther_1024.png, panther_2048.png
"""

import os

import cairosvg

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "panther.svg")

if __name__ == "__main__":
    for size in (1024, 2048):
        dst = os.path.join(HERE, f"panther_{size}.png")
        cairosvg.svg2png(url=SRC, write_to=dst, output_width=size, output_height=size)
        print(dst)
