"""Keyboard adapter for the existing Cairo row menus; shares their hit tests."""
from gi.repository import Gdk


def targets(panel, width):
    result = []
    for row in panel.rows:
        if not row.interactive:
            continue
        points = []
        if hasattr(row, 'visible') and hasattr(row, 'LINE'):
            for i, item in enumerate(row.visible):
                identity = str(item.get('path', item.get('ssid', item.get('name', item)))) if isinstance(item, dict) else str(item)
                y = row.LEAD + i * row.LINE
                points.append((width - 28, y + row.LINE / 2, (3, y + 1, width - 6, row.LINE - 2), identity))
        elif hasattr(row, 'rects'):
            for x, w, key in row.rects:
                points.append((x + w / 2, row.h / 2, (x + 1, 2, w - 2, row.h - 4), key))
        elif hasattr(row, 'buttons'):
            for button in row.buttons(width):
                key, _, x, w = button[:4]
                points.append((x + w / 2, row.h - 22, (x, row.h - 40, w, 34), key))
        elif hasattr(row, 'SPLIT'):
            for i in range(2):
                points.append((width / 2, row.SPLIT * (i + .5), (2, row.SPLIT * i + 2, width - 4, row.SPLIT - 4), str(i)))
        else:
            points.append((width - 28, min(22, row.h / 2), (2, 2, width - 4, row.h - 4), 'main'))
        for x, y, bounds, identity in points:
            hit = row.test(x, y)
            if hit is not None:
                result.append((type(row).__name__ + ':' + identity, row, x, y, bounds, hit))
    return result


def key(panel, event, width):
    code = event.keyval
    navigation = (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab, Gdk.KEY_Up, Gdk.KEY_Down,
                  Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Home, Gdk.KEY_End,
                  Gdk.KEY_Page_Up, Gdk.KEY_Page_Down)
    enter = code in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space)
    if code not in navigation and not enter:
        return False
    choices = targets(panel, width)
    if not choices:
        return False
    selected = getattr(panel, 'keyboard_target', None)
    index = next((i for i, target in enumerate(choices) if target[0] == selected), -1)
    if enter and index >= 0:
        _, row, x, y, _, _ = choices[index]
        row.release(x, y)
        panel.area.queue_draw()
        return True
    if code in (Gdk.KEY_Page_Up, Gdk.KEY_Page_Down) and index >= 0:
        row = choices[index][1]
        if hasattr(row, 'scroll'):
            row.scroll(1 if code == Gdk.KEY_Page_Down else -1)
            choices = targets(panel, width)
            index = min(index, len(choices) - 1)
    elif code == Gdk.KEY_Home:
        index = 0
    elif code == Gdk.KEY_End:
        index = len(choices) - 1
    elif index < 0:
        index = 0
    elif not enter:
        reverse = code in (Gdk.KEY_ISO_Left_Tab, Gdk.KEY_Up, Gdk.KEY_Left) or (
            code == Gdk.KEY_Tab and event.state & Gdk.ModifierType.SHIFT_MASK)
        index = (index + (-1 if reverse else 1)) % len(choices)
    if choices:
        panel.keyboard_target = choices[index][0]
        for row in panel.rows:
            row.hit = None
        choices[index][1].hit = choices[index][5]
    panel.area.queue_draw()
    return True


def draw(panel, row, cr, width):
    selected = getattr(panel, 'keyboard_target', None)
    if selected is None:
        return
    for identity, candidate, _, _, bounds, _ in targets(panel, width):
        if candidate is row and identity == selected:
            cr.save()
            color = panel.colors.get('blue', panel.colors.get('accent', (0, 122, 255)))
            cr.set_source_rgb(*(v / 255 for v in color[:3]))
            cr.set_line_width(2)
            cr.rectangle(*bounds)
            cr.stroke()
            cr.restore()
            break
