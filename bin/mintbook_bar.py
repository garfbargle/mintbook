"""Scale custom panel SVG viewports together, leaving their vector geometry sharp."""
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

PREFERENCES = Path.home() / '.config/mintbook/bar-sizing.json'


def effective_dpi(value):
    try:
        dpi = float(value)
        return dpi if math.isfinite(dpi) and dpi > 0 else 96
    except (ValueError, TypeError):
        return 96


def canvas_height(dpi):
    return max(16, min(64, round(20 * effective_dpi(dpi) / 96)))


def scale_images(name, markup, cache, preferences=PREFERENCES):
    try:
        dpi = float(json.loads(preferences.read_text())['dpi'])
    except (OSError, ValueError, KeyError, TypeError):
        dpi = 168
    target = canvas_height(dpi)

    def image(match):
        source = Path(match.group(1))
        if source.suffix != '.svg':
            return match.group(0)
        try:
            original = source.read_bytes()
            svg = ET.fromstring(original)
            # Resizing the SVG viewport preserves stroke proportions and text;
            # GTK panel icon-size does not control genmon's <img> widgets.
            width = float(svg.attrib['width'].removesuffix('px'))
            height = float(svg.attrib['height'].removesuffix('px'))
            if width <= 0 or height <= 0:
                return match.group(0)
            svg.set('viewBox', svg.get('viewBox', f'0 0 {width:g} {height:g}'))
            viewbox = [float(part) for part in svg.get('viewBox').replace(',', ' ').split()]
            ratio = viewbox[2] / viewbox[3] if len(viewbox) == 4 and viewbox[3] > 0 else width / height
            svg.set('width', str(round(ratio * target)))
            svg.set('height', str(target))
            ET.register_namespace('', 'http://www.w3.org/2000/svg')
            data = ET.tostring(svg, encoding='utf-8')
            output = cache / 'images' / (name + '.svg')
            output.parent.mkdir(parents=True, exist_ok=True)
            if not output.exists() or output.read_bytes() != data:
                temporary = output.with_suffix('.new')
                temporary.write_bytes(data)
                temporary.replace(output)
            return '<img>' + str(output) + '</img>'
        except (OSError, ValueError, KeyError, ET.ParseError):
            return match.group(0)

    return re.sub(r'<img>([^<]+)</img>', image, markup)
