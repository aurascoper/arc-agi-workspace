# --- THE DSL (The Evolving DNA) ---
HELPER_CODE_PREFIX = r'''
import numpy as np
from copy import deepcopy
from collections import Counter, deque

def get_objects(grid, background=None, diag=False):
    """Find connected same-color components, excluding the background color."""
    if background is None:
        background = detect_background_color(grid)
    rows, cols = len(grid), len(grid[0])
    visited = set()
    objs = []
    neighbors = [(0,1),(0,-1),(1,0),(-1,0)] + ([(1,1),(1,-1),(-1,1),(-1,-1)] if diag else [])
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background and (r, c) not in visited:
                q = deque([(r, c)])
                component = []
                visited.add((r, c))
                color = grid[r][c]
                while q:
                    curr_r, curr_c = q.popleft()
                    component.append((curr_r, curr_c))
                    for dr, dc in neighbors:
                        nr, nc = curr_r + dr, curr_c + dc
                        if 0 <= nr < rows and 0 <= nc < cols and \
                           grid[nr][nc] == color and (nr, nc) not in visited:
                            visited.add((nr, nc))
                            q.append((nr, nc))
                objs.append(component)
    return objs

def get_objects_by_color(grid, color, diag=False):
    return [obj for obj in get_objects(grid, background=None, diag=diag) if get_color(grid, obj) == color]

def get_shapes(grid, background=None, diag=False):
    """Find connected non-background components, ignoring internal color changes."""
    if background is None:
        background = detect_background_color(grid)
    rows, cols = len(grid), len(grid[0])
    visited = set()
    shapes = []
    neighbors = [(0,1),(0,-1),(1,0),(-1,0)] + ([(1,1),(1,-1),(-1,1),(-1,-1)] if diag else [])
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == background or (r, c) in visited:
                continue
            q = deque([(r, c)])
            visited.add((r, c))
            shape = []
            while q:
                cr, cc = q.popleft()
                shape.append((cr, cc))
                for dr, dc in neighbors:
                    nr, nc = cr + dr, cc + dc
                    if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in visited and grid[nr][nc] != background:
                        visited.add((nr, nc))
                        q.append((nr, nc))
            shapes.append(shape)
    return shapes

def get_foreground_pixels(grid, background=None):
    if background is None:
        background = detect_background_color(grid)
    return [(r, c) for r, row in enumerate(grid) for c, value in enumerate(row) if value != background]

def foreground_bbox(grid, background=None):
    pixels = get_foreground_pixels(grid, background=background)
    return get_bbox(pixels) if pixels else (0, 0, 0, 0)

def get_bbox(obj_coords):
    """Return (min_r, min_c, max_r, max_c) for an object."""
    if not obj_coords: return (0, 0, 0, 0)
    rs, cs = [r for r, c in obj_coords], [c for r, c in obj_coords]
    return min(rs), min(cs), max(rs), max(cs)

def detect_background_color(grid):
    """Heuristic: background is usually the dominant border color."""
    rows, cols = len(grid), len(grid[0])
    border = [grid[0][c] for c in range(cols)] + [grid[rows-1][c] for c in range(cols)] + \
             [grid[r][0] for r in range(rows)] + [grid[r][cols-1] for r in range(rows)]
    if border:
        border_counts = Counter(border)
        return max(border_counts, key=lambda color: (border_counts[color], color_counts(grid).get(color, 0)))
    return most_common_color(grid)

def make_grid(rows, cols, fill=0):
    return [[fill]*cols for _ in range(rows)]

def copy_grid(grid):
    return [row[:] for row in grid]

def grid_signature(grid):
    return tuple(tuple(row) for row in grid) if grid else tuple()

def shape(grid):
    return (len(grid), len(grid[0]) if grid else 0)

def palette(grid):
    colors = []
    seen = set()
    for row in grid:
        for value in row:
            if value not in seen:
                seen.add(value)
                colors.append(value)
    return colors

def non_background_colors(grid, background=None):
    if background is None:
        background = detect_background_color(grid)
    return [color for color in palette(grid) if color != background]

def color_counts(grid):
    return Counter(cell for row in grid for cell in row)

def count_color(grid, color):
    return color_counts(grid).get(color, 0)

def find_cells(grid, color):
    return [(r, c) for r, row in enumerate(grid) for c, value in enumerate(row) if value == color]

def get_bbox_of_color(grid, color):
    cells = find_cells(grid, color)
    return get_bbox(cells) if cells else (0, 0, 0, 0)

def inside_grid(grid, r, c):
    return 0 <= r < len(grid) and 0 <= c < len(grid[0])

def neighbors4(r, c):
    return [(r, c+1), (r, c-1), (r+1, c), (r-1, c)]

def neighbors8(r, c):
    return neighbors4(r, c) + [(r+1, c+1), (r+1, c-1), (r-1, c+1), (r-1, c-1)]

def flood_fill(grid, start, target_color=None, replacement_color=None, diag=False):
    """Classic flood fill. Returns region coords when replacement_color is None, else a new grid."""
    if not grid:
        return []
    sr, sc = start
    if not inside_grid(grid, sr, sc):
        return copy_grid(grid)
    if target_color is None:
        target_color = grid[sr][sc]
    q = deque([(sr, sc)])
    seen = {(sr, sc)}
    steps = neighbors8 if diag else neighbors4
    region = []
    out = copy_grid(grid) if replacement_color is not None else None
    while q:
        r, c = q.popleft()
        if grid[r][c] != target_color:
            continue
        region.append((r, c))
        if out is not None:
            out[r][c] = replacement_color
        for nr, nc in steps(r, c):
            if inside_grid(grid, nr, nc) and (nr, nc) not in seen and grid[nr][nc] == target_color:
                seen.add((nr, nc))
                q.append((nr, nc))
    return region if replacement_color is None else out

def rotate_cw(grid):
    rows, cols = len(grid), len(grid[0])
    return [[grid[rows-1-r][c] for r in range(rows)] for c in range(cols)]

def rotate_ccw(grid):
    rows, cols = len(grid), len(grid[0])
    return [[grid[r][cols-1-c] for r in range(rows)] for c in range(cols-1, -1, -1)]

def rotate_180(grid):
    return [row[::-1] for row in grid[::-1]]

def transpose(grid):
    return [list(row) for row in zip(*grid)]

def flip_anti_diagonal(grid):
    return [row[::-1] for row in transpose(grid)]

def scale_grid(grid, factor_r, factor_c=None):
    if factor_c is None:
        factor_c = factor_r
    out = []
    for row in grid:
        scaled_row = []
        for value in row:
            scaled_row.extend([value] * factor_c)
        for _ in range(factor_r):
            out.append(scaled_row[:])
    return out

def tile_grid(grid, repeat_r, repeat_c=None):
    if repeat_c is None:
        repeat_c = repeat_r
    tiled_rows = []
    base_rows = [row * repeat_c for row in grid]
    for _ in range(repeat_r):
        tiled_rows.extend([row[:] for row in base_rows])
    return tiled_rows

def mirror_h(grid):
    return [row[::-1] for row in grid]

def mirror_v(grid):
    return grid[::-1]

def is_symmetric_h(grid):
    return grid == mirror_h(grid)

def is_symmetric_v(grid):
    return grid == mirror_v(grid)

def most_common_color(grid, exclude=None):
    counts = {}
    for row in grid:
        for c in row:
            counts[c] = counts.get(c, 0) + 1
    if exclude is not None:
        for e in (exclude if hasattr(exclude, '__iter__') else [exclude]):
            counts.pop(e, None)
    return max(counts, key=counts.get) if counts else 0

def dominant_non_background_color(grid, background=None):
    if background is None:
        background = detect_background_color(grid)
    return most_common_color(grid, exclude=background)

def get_color(grid, obj):
    return grid[obj[0][0]][obj[0][1]] if obj else 0

def object_colors(grid, obj):
    colors = []
    seen = set()
    for r, c in obj:
        value = grid[r][c]
        if value not in seen:
            seen.add(value)
            colors.append(value)
    return colors

def object_color_counts(grid, obj):
    return Counter(grid[r][c] for r, c in obj) if obj else Counter()

def objects_by_color(grid, background=None, diag=False):
    grouped = {}
    for obj in get_objects(grid, background=background, diag=diag):
        grouped.setdefault(get_color(grid, obj), []).append(obj)
    return grouped

def object_size(obj):
    return len(obj)

def object_height(obj):
    min_r, _, max_r, _ = get_bbox(obj)
    return max_r - min_r + 1

def object_width(obj):
    _, min_c, _, max_c = get_bbox(obj)
    return max_c - min_c + 1

def object_dimensions(obj):
    return (object_height(obj), object_width(obj))

def object_center(obj):
    min_r, min_c, max_r, max_c = get_bbox(obj)
    return ((min_r + max_r) / 2.0, (min_c + max_c) / 2.0)

def top_left(obj):
    min_r, min_c, _, _ = get_bbox(obj)
    return (min_r, min_c)

def bottom_right(obj):
    _, _, max_r, max_c = get_bbox(obj)
    return (max_r, max_c)

def translate(obj, dr=0, dc=0):
    return [(r + dr, c + dc) for r, c in obj]

def normalize_object(obj):
    min_r, min_c, _, _ = get_bbox(obj)
    return [(r - min_r, c - min_c) for r, c in obj]

def recolor(grid, old_color, new_color):
    return [[new_color if cell == old_color else cell for cell in row] for row in grid]

def remap_colors(grid, color_map, default=None):
    if default is None:
        return [[color_map.get(cell, cell) for cell in row] for row in grid]
    return [[color_map.get(cell, default) for cell in row] for row in grid]

def extract_color(grid, color, background=0):
    return [[cell if cell == color else background for cell in row] for row in grid]

def remove_color(grid, color, background=0):
    return [[background if cell == color else cell for cell in row] for row in grid]

def remove_colors(grid, colors, background=None):
    if background is None:
        background = detect_background_color(grid)
    color_set = set(colors if hasattr(colors, '__iter__') and not isinstance(colors, (str, bytes)) else [colors])
    return [[background if cell in color_set else cell for cell in row] for row in grid]

def infer_noise_color(grid, background=None):
    if background is None:
        background = detect_background_color(grid)
    counts = color_counts(grid)
    candidates = [color for color in counts if color != background]
    if not candidates:
        return background
    rows, cols = len(grid), len(grid[0])
    border_counts = Counter()
    for c in range(cols):
        border_counts[grid[0][c]] += 1
        border_counts[grid[rows - 1][c]] += 1
    for r in range(1, rows - 1):
        border_counts[grid[r][0]] += 1
        border_counts[grid[r][cols - 1]] += 1
    objects = objects_by_color(grid, background=background)
    ranked = []
    for color in candidates:
        comps = objects.get(color, [])
        interior_mass = sum(
            1 for obj in comps for r, c in obj
            if 0 < r < rows - 1 and 0 < c < cols - 1
        )
        ranked.append((
            -border_counts[color],
            counts[color] - border_counts[color],
            -len(comps),
            interior_mass,
            max((len(obj) for obj in comps), default=0),
            color,
        ))
    return min(ranked)[-1]

def infer_noise_colors(grid, max_colors=2, background=None):
    if background is None:
        background = detect_background_color(grid)
    counts = color_counts(grid)
    candidates = [color for color in counts if color != background]
    if not candidates:
        return []
    rows, cols = len(grid), len(grid[0])
    border_counts = Counter()
    for c in range(cols):
        border_counts[grid[0][c]] += 1
        border_counts[grid[rows - 1][c]] += 1
    for r in range(1, rows - 1):
        border_counts[grid[r][0]] += 1
        border_counts[grid[r][cols - 1]] += 1
    objects = objects_by_color(grid, background=background)
    ranked = []
    for color in candidates:
        comps = objects.get(color, [])
        interior_mass = sum(
            1 for obj in comps for r, c in obj
            if 0 < r < rows - 1 and 0 < c < cols - 1
        )
        ranked.append((
            -border_counts[color],
            counts[color] - border_counts[color],
            -len(comps),
            interior_mass,
            max((len(obj) for obj in comps), default=0),
            color,
        ))
    ranked.sort()
    return [item[-1] for item in ranked[:max_colors]]

def remove_noise(grid, noise_color=None, background=None):
    if background is None:
        background = detect_background_color(grid)
    if noise_color is None:
        noise_color = infer_noise_color(grid, background=background)
    if hasattr(noise_color, '__iter__') and not isinstance(noise_color, (str, bytes)):
        return remove_colors(grid, list(noise_color), background=background)
    return remove_color(grid, noise_color, background=background)

def remove_small_objects(grid, max_size=1, background=None, diag=False):
    if background is None:
        background = detect_background_color(grid)
    out = copy_grid(grid)
    for obj in get_objects(grid, background=background, diag=diag):
        if len(obj) <= max_size:
            for r, c in obj:
                out[r][c] = background
    return out

def remove_small_shapes(grid, max_size=1, background=None, diag=True):
    if background is None:
        background = detect_background_color(grid)
    out = copy_grid(grid)
    for shape in get_shapes(grid, background=background, diag=diag):
        if len(shape) <= max_size:
            for r, c in shape:
                out[r][c] = background
    return out

def remove_border_objects_by_size(grid, max_size=None, background=None, diag=False):
    if background is None:
        background = detect_background_color(grid)
    out = copy_grid(grid)
    for obj in get_objects(grid, background=background, diag=diag):
        if not touches_border(grid, obj):
            continue
        if max_size is not None and len(obj) > max_size:
            continue
        for r, c in obj:
            out[r][c] = background
    return out

def remove_border_shapes_by_size(grid, max_size=None, background=None, diag=True):
    if background is None:
        background = detect_background_color(grid)
    out = copy_grid(grid)
    for shape in get_shapes(grid, background=background, diag=diag):
        if not touches_border(grid, shape):
            continue
        if max_size is not None and len(shape) > max_size:
            continue
        for r, c in shape:
            out[r][c] = background
    return out

def keep_most_common_colors(grid, n=1, background=None):
    if background is None:
        background = detect_background_color(grid)
    counts = color_counts(grid)
    rows, cols = len(grid), len(grid[0])
    border_counts = Counter()
    for c in range(cols):
        border_counts[grid[0][c]] += 1
        border_counts[grid[rows - 1][c]] += 1
    for r in range(1, rows - 1):
        border_counts[grid[r][0]] += 1
        border_counts[grid[r][cols - 1]] += 1
    objects = objects_by_color(grid, background=background)
    ranked = sorted(
        [color for color in counts if color != background],
        key=lambda color: (
            -(counts[color] - border_counts[color]),
            -max((sum(1 for r, c in obj if 0 < r < rows - 1 and 0 < c < cols - 1) for obj in objects.get(color, [])), default=0),
            -max((len(obj) for obj in objects.get(color, [])), default=0),
            border_counts[color],
            color,
        )
    )
    keep = set(ranked[:n])
    return [[cell if cell in keep or cell == background else background for cell in row] for row in grid]

def safe_crop(grid, bbox, background=None):
    if not grid or not grid[0]:
        fill = 0 if background is None else background
        return [[fill]]
    if background is None:
        background = detect_background_color(grid)
    min_r, min_c, max_r, max_c = bbox
    min_r = max(0, min_r)
    min_c = max(0, min_c)
    max_r = min(len(grid) - 1, max_r)
    max_c = min(len(grid[0]) - 1, max_c)
    if min_r > max_r or min_c > max_c:
        return [[background]]
    return crop(grid, (min_r, min_c, max_r, max_c))

def fit_grid_to_size(grid, rows, cols, background=None, align='top-left'):
    if background is None:
        background = detect_background_color(grid) if grid and grid[0] else 0
    out = make_grid(rows, cols, background)
    start_r = 0
    start_c = 0
    src_r = 0
    src_c = 0
    if align == 'center':
        start_r = max((rows - len(grid)) // 2, 0)
        start_c = max((cols - len(grid[0])) // 2, 0)
        src_r = max((len(grid) - rows) // 2, 0)
        src_c = max((len(grid[0]) - cols) // 2, 0)
    for r in range(min(rows - start_r, len(grid) - src_r)):
        for c in range(min(cols - start_c, len(grid[0]) - src_c)):
            out[start_r + r][start_c + c] = grid[src_r + r][src_c + c]
    return out

def crop(grid, bbox):
    min_r, min_c, max_r, max_c = bbox
    return [row[min_c:max_c+1] for row in grid[min_r:max_r+1]]

def crop_foreground(grid, background=None):
    pixels = get_foreground_pixels(grid, background=background)
    if not pixels:
        return [[background if background is not None else detect_background_color(grid)]]
    return crop(grid, get_bbox(pixels))

def crop_object(grid, obj, background=0):
    min_r, min_c, max_r, max_c = get_bbox(obj)
    out = make_grid(max_r - min_r + 1, max_c - min_c + 1, background)
    for r, c in obj:
        out[r - min_r][c - min_c] = grid[r][c]
    return out

def object_to_grid(obj, color=1, background=0):
    if not obj:
        return [[background]]
    normalized = normalize_object(obj)
    _, _, max_r, max_c = get_bbox(normalized)
    out = make_grid(max_r + 1, max_c + 1, background)
    for r, c in normalized:
        out[r][c] = color
    return out

def paint_object(grid, obj, color=None):
    out = copy_grid(grid)
    for r, c in obj:
        if 0 <= r < len(out) and 0 <= c < len(out[0]):
            out[r][c] = grid[r][c] if color is None else color
    return out

def erase_object(grid, obj, background=None):
    out = copy_grid(grid)
    fill = detect_background_color(grid) if background is None else background
    for r, c in obj:
        if 0 <= r < len(out) and 0 <= c < len(out[0]):
            out[r][c] = fill
    return out

def move_object(grid, obj, dr=0, dc=0, background=None, color=None):
    out = erase_object(grid, obj, background=background)
    moved = translate(obj, dr, dc)
    for (src_r, src_c), (r, c) in zip(obj, moved):
        if 0 <= r < len(out) and 0 <= c < len(out[0]):
            out[r][c] = grid[src_r][src_c] if color is None else color
    return out

def shift_grid(grid, dr=0, dc=0, background=None):
    if background is None:
        background = detect_background_color(grid)
    out = make_grid(len(grid), len(grid[0]), background)
    for r, row in enumerate(grid):
        for c, value in enumerate(row):
            nr, nc = r + dr, c + dc
            if 0 <= nr < len(out) and 0 <= nc < len(out[0]):
                out[nr][nc] = value
    return out

def paste(subgrid, grid, top=0, left=0, transparent=None):
    out = copy_grid(grid)
    for r, row in enumerate(subgrid):
        for c, value in enumerate(row):
            rr, cc = top + r, left + c
            if 0 <= rr < len(out) and 0 <= cc < len(out[0]):
                if transparent is None or value != transparent:
                    out[rr][cc] = value
    return out

def overlay(grid_a, grid_b, transparent=None):
    rows = max(len(grid_a), len(grid_b))
    cols = max(len(grid_a[0]), len(grid_b[0]))
    background = detect_background_color(grid_a) if grid_a else detect_background_color(grid_b)
    out = make_grid(rows, cols, background)
    for r, row in enumerate(grid_a):
        for c, value in enumerate(row):
            out[r][c] = value
    if transparent is None:
        transparent = detect_background_color(grid_b)
    for r, row in enumerate(grid_b):
        for c, value in enumerate(row):
            if value != transparent:
                out[r][c] = value
    return out

def union(grid_a, grid_b, background=None):
    if background is None:
        background = detect_background_color(grid_a) if grid_a else detect_background_color(grid_b)
    return overlay(grid_a, grid_b, transparent=background)

def intersect(grid_a, grid_b, background=None):
    if background is None:
        background = detect_background_color(grid_a) if grid_a else detect_background_color(grid_b)
    rows = max(len(grid_a), len(grid_b))
    cols = max(len(grid_a[0]), len(grid_b[0]))
    out = make_grid(rows, cols, background)
    for r in range(rows):
        for c in range(cols):
            a = grid_a[r][c] if r < len(grid_a) and c < len(grid_a[0]) else background
            b = grid_b[r][c] if r < len(grid_b) and c < len(grid_b[0]) else background
            if a != background and b != background:
                out[r][c] = a if a == b else b
    return out

def difference(grid_a, grid_b, background=None):
    if background is None:
        background = detect_background_color(grid_a) if grid_a else detect_background_color(grid_b)
    rows = len(grid_a)
    cols = len(grid_a[0]) if grid_a else 0
    out = copy_grid(grid_a)
    for r in range(rows):
        for c in range(cols):
            b = grid_b[r][c] if r < len(grid_b) and c < len(grid_b[0]) else background
            if b != background:
                out[r][c] = background
    return out

def raycast(grid, start, direction=(1, 0), color=None, background=None, stop_at_non_background=False):
    if background is None:
        background = detect_background_color(grid)
    if color is None:
        color = dominant_non_background_color(grid, background=background)
    dr, dc = direction
    r, c = start
    out = copy_grid(grid)
    while inside_grid(out, r, c):
        if stop_at_non_background and out[r][c] != background and (r, c) != start:
            break
        out[r][c] = color
        r += dr
        c += dc
    return out

def project(grid, axis='down', color=None, background=None, include_sources=True, stop_at_non_background=False):
    if background is None:
        background = detect_background_color(grid)
    if color is None:
        color = dominant_non_background_color(grid, background=background)
    directions = {
        'down': (1, 0),
        'up': (-1, 0),
        'right': (0, 1),
        'left': (0, -1),
    }
    direction = directions.get(axis, directions['down'])
    out = copy_grid(grid)
    for r, row in enumerate(grid):
        for c, value in enumerate(row):
            if value == background:
                continue
            rr, cc = (r, c) if include_sources else (r + direction[0], c + direction[1])
            while inside_grid(out, rr, cc):
                if stop_at_non_background and out[rr][cc] != background and (rr, cc) != (r, c):
                    break
                out[rr][cc] = value if color is None else color
                rr += direction[0]
                cc += direction[1]
    return out

def project_all(grid, axes=('down', 'right'), color=None, background=None, include_sources=True, stop_at_non_background=False):
    if background is None:
        background = detect_background_color(grid)
    out = copy_grid(grid)
    for axis in axes:
        out = project(
            out,
            axis=axis,
            color=color,
            background=background,
            include_sources=include_sources,
            stop_at_non_background=stop_at_non_background,
        )
    return out

def transform_object(grid, obj, rotation=None, mirror=None, dr=0, dc=0, background=None, in_place=False):
    if background is None:
        background = detect_background_color(grid)
    if not obj:
        return copy_grid(grid) if in_place else [[background]]
    transformed = crop_object(grid, obj, background=background)
    if rotation in (90, 'cw', 'rotate_cw'):
        transformed = rotate_cw(transformed)
    elif rotation in (180, '180', 'rotate_180'):
        transformed = rotate_180(transformed)
    elif rotation in (270, -90, 'ccw', 'rotate_ccw'):
        transformed = rotate_ccw(transformed)
    elif rotation in ('transpose', 'diag'):
        transformed = transpose(transformed)
    if mirror in ('h', 'horizontal', 'lr'):
        transformed = mirror_h(transformed)
    elif mirror in ('v', 'vertical', 'tb'):
        transformed = mirror_v(transformed)
    if not in_place:
        return transformed
    min_r, min_c, max_r, max_c = get_bbox(obj)
    out = erase_object(grid, obj, background=background)
    top = min_r + dr
    left = min_c + dc
    return paste(transformed, out, top=top, left=left, transparent=background)

def transform_objects_in_place(grid, objects=None, rotation=None, mirror=None, dr=0, dc=0, background=None, diag=False):
    if background is None:
        background = detect_background_color(grid)
    if objects is None:
        objects = get_objects(grid, background=background, diag=diag)
    out = copy_grid(grid)
    for obj in objects:
        out = transform_object(out, obj, rotation=rotation, mirror=mirror, dr=dr, dc=dc, background=background, in_place=True)
    return out

def symmetrize_h(grid, background=None):
    if background is None:
        background = detect_background_color(grid)
    return overlay(grid, mirror_h(grid), transparent=background)

def symmetrize_v(grid, background=None):
    if background is None:
        background = detect_background_color(grid)
    return overlay(grid, mirror_v(grid), transparent=background)

def fill_from_mirror_h(grid, background=None):
    if background is None:
        background = detect_background_color(grid)
    rows, cols = len(grid), len(grid[0])
    out = copy_grid(grid)
    for r in range(rows):
        for c in range(cols):
            mc = cols - 1 - c
            a, b = out[r][c], out[r][mc]
            if a == background and b != background:
                out[r][c] = b
            elif b == background and a != background:
                out[r][mc] = a
    return out

def fill_from_mirror_v(grid, background=None):
    if background is None:
        background = detect_background_color(grid)
    rows, cols = len(grid), len(grid[0])
    out = copy_grid(grid)
    for r in range(rows):
        mr = rows - 1 - r
        for c in range(cols):
            a, b = out[r][c], out[mr][c]
            if a == background and b != background:
                out[r][c] = b
            elif b == background and a != background:
                out[mr][c] = a
    return out

def symmetry_score_h(grid, background=None):
    if background is None:
        background = detect_background_color(grid)
    rows, cols = len(grid), len(grid[0])
    score = 0
    for r in range(rows):
        for c in range(cols):
            mc = cols - 1 - c
            a, b = grid[r][c], grid[r][mc]
            if a == b and a != background:
                score += 2
            elif a != background and b != background:
                score -= 1
            elif a != background or b != background:
                score += 1
    return score

def symmetry_score_v(grid, background=None):
    if background is None:
        background = detect_background_color(grid)
    rows, cols = len(grid), len(grid[0])
    score = 0
    for r in range(rows):
        mr = rows - 1 - r
        for c in range(cols):
            a, b = grid[r][c], grid[mr][c]
            if a == b and a != background:
                score += 2
            elif a != background and b != background:
                score -= 1
            elif a != background or b != background:
                score += 1
    return score

def choose_symmetry_axis(grid, background=None):
    if background is None:
        background = detect_background_color(grid)
    h_score = symmetry_score_h(grid, background=background)
    v_score = symmetry_score_v(grid, background=background)
    return 'h' if h_score >= v_score else 'v'

def repair_symmetry(grid, axis='auto', background=None):
    if background is None:
        background = detect_background_color(grid)
    if axis == 'auto':
        return best_axis_completion(grid, background=background)
    if axis in ('h', 'horizontal', 'lr', 'left-right'):
        return fill_from_mirror_h(grid, background=background)
    if axis in ('v', 'vertical', 'tb', 'top-bottom'):
        return fill_from_mirror_v(grid, background=background)
    return copy_grid(grid)

def denoise_and_repair_symmetry(grid, noise_color=None, axis='auto', background=None, crop_result=False):
    if background is None:
        background = detect_background_color(grid)
    cleaned = remove_noise(grid, noise_color=noise_color, background=background)
    repaired = repair_symmetry(cleaned, axis=axis, background=background)
    repaired = best_enclosed_fill(repaired, background=background, max_size=estimate_hole_size_limit(repaired, background=background))
    return crop_foreground(repaired, background=background) if crop_result else repaired

def mark_uniform_rows(grid, mark_color=5, other_color=0):
    """For each row: if all elements are the same value, output [mark_color]*cols, else [other_color]*cols."""
    cols = len(grid[0])
    return [[mark_color]*cols if len(set(row))==1 else [other_color]*cols for row in grid]

def mark_uniform_cols(grid, mark_color=5, other_color=0):
    """For each column: if all elements are the same value, output mark_color, else other_color in that col."""
    rows, cols = len(grid), len(grid[0])
    out = [[other_color]*cols for _ in range(rows)]
    for c in range(cols):
        col_vals = [grid[r][c] for r in range(rows)]
        if len(set(col_vals)) == 1:
            for r in range(rows):
                out[r][c] = mark_color
    return out

def project_template_row_to_markers(grid, template_color=5, fill_color=2, background=0):
    """Row 0 (or row with most template_color) defines the column pattern.
    A single marker column (far side) has template_color at multiple rows.
    For each marker row, fill template columns with fill_color."""
    rows, cols = len(grid), len(grid[0])
    row_counts = [sum(1 for c in range(cols) if grid[r][c] == template_color) for r in range(rows)]
    template_row = max(range(rows), key=lambda r: row_counts[r])
    if row_counts[template_row] < 2:
        return [row[:] for row in grid]
    def col_nontemplate_count(c):
        return sum(1 for r in range(rows) if r != template_row and grid[r][c] == template_color)
    marker_col = max(range(cols), key=col_nontemplate_count)
    if col_nontemplate_count(marker_col) < 1:
        return [row[:] for row in grid]
    template_cols = [c for c in range(cols) if grid[template_row][c] == template_color and c != marker_col]
    marker_rows = [r for r in range(rows) if r != template_row and grid[r][marker_col] == template_color]
    out = [row[:] for row in grid]
    for r in marker_rows:
        for c in template_cols:
            if out[r][c] == background:
                out[r][c] = fill_color
    return out

def draw_l_path_between_colors(grid, color_a=2, color_b=3, path_color=8, background=0):
    """Find two colored cells (color_a and color_b). Draw an L-shaped path: horizontal along
    row of color_a to the column of color_b, then vertical to color_b. Intermediate cells get path_color."""
    rows, cols = len(grid), len(grid[0])
    pos_a, pos_b = None, None
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == color_a:
                pos_a = (r, c)
            elif grid[r][c] == color_b:
                pos_b = (r, c)
    if pos_a is None or pos_b is None:
        return [row[:] for row in grid]
    ra, ca = pos_a
    rb, cb = pos_b
    out = [row[:] for row in grid]
    for c in range(min(ca, cb), max(ca, cb) + 1):
        if c != ca and out[ra][c] == background:
            out[ra][c] = path_color
    for r in range(min(ra, rb) + 1, max(ra, rb)):
        if out[r][cb] == background:
            out[r][cb] = path_color
    return out

def fill_square_enclosed_regions(grid, fill_color=2, wall_color=5, background=0):
    """BFS from border marks reachable background cells. Enclosed background connected components
    that form a perfect square (height == width and area == component size) are filled with fill_color."""
    from collections import deque
    rows, cols = len(grid), len(grid[0])
    reachable = [[False]*cols for _ in range(rows)]
    queue = deque()
    for r in range(rows):
        for c in [0, cols-1]:
            if grid[r][c] == background and not reachable[r][c]:
                reachable[r][c] = True
                queue.append((r,c))
    for c in range(cols):
        for r in [0, rows-1]:
            if grid[r][c] == background and not reachable[r][c]:
                reachable[r][c] = True
                queue.append((r,c))
    while queue:
        r, c = queue.popleft()
        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            nr, nc = r+dr, c+dc
            if 0<=nr<rows and 0<=nc<cols and not reachable[nr][nc] and grid[nr][nc]==background:
                reachable[nr][nc] = True
                queue.append((nr,nc))
    visited = [[False]*cols for _ in range(rows)]
    out = [row[:] for row in grid]
    for sr in range(rows):
        for sc in range(cols):
            if grid[sr][sc] == background and not reachable[sr][sc] and not visited[sr][sc]:
                component = []
                q2 = deque([(sr,sc)])
                visited[sr][sc] = True
                while q2:
                    r, c = q2.popleft()
                    component.append((r,c))
                    for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nr, nc = r+dr, c+dc
                        if 0<=nr<rows and 0<=nc<cols and not visited[nr][nc] and grid[nr][nc]==background and not reachable[nr][nc]:
                            visited[nr][nc] = True
                            q2.append((nr,nc))
                r_min = min(r for r,c in component)
                r_max = max(r for r,c in component)
                c_min = min(c for r,c in component)
                c_max = max(c for r,c in component)
                h = r_max - r_min + 1
                w = c_max - c_min + 1
                if h == w and h * w == len(component):
                    for r, c in component:
                        out[r][c] = fill_color
    return out

def fill_enclosed_background(grid, fill_color=None, background=None, max_size=4, diag=False):
    if background is None:
        background = detect_background_color(grid)
    if fill_color is None:
        fill_color = dominant_non_background_color(grid, background=background)
    if fill_color == background:
        return copy_grid(grid)
    rows, cols = len(grid), len(grid[0])
    out = copy_grid(grid)
    visited = set()
    for r in range(rows):
        for c in range(cols):
            if out[r][c] != background or (r, c) in visited:
                continue
            region = flood_fill(out, (r, c), target_color=background, replacement_color=None, diag=diag)
            for cell in region:
                visited.add(cell)
            if not region:
                continue
            touches_edge = any(rr == 0 or cc == 0 or rr == rows - 1 or cc == cols - 1 for rr, cc in region)
            if touches_edge:
                continue
            if max_size is not None and len(region) > max_size:
                continue
            for rr, cc in region:
                out[rr][cc] = fill_color
    return out

def best_enclosed_fill(grid, fill_color=None, background=None, max_size=4):
    if background is None:
        background = detect_background_color(grid)
    candidates = [
        copy_grid(grid),
        fill_enclosed_background(grid, fill_color=fill_color, background=background, max_size=max_size, diag=False),
        fill_enclosed_background(grid, fill_color=fill_color, background=background, max_size=max_size, diag=True),
    ]
    return max(candidates, key=lambda cand: score_repair_candidate(cand, background=background))

fill_holes = best_enclosed_fill
repair_holes = best_enclosed_fill
fill_pattern_holes = best_enclosed_fill
remove_border_noise_shapes = remove_border_shapes_by_size

def estimate_hole_size_limit(grid, background=None):
    if background is None:
        background = detect_background_color(grid)
    pixels = get_foreground_pixels(grid, background=background)
    if not pixels:
        return 1
    min_r, min_c, max_r, max_c = get_bbox(pixels)
    area = (max_r - min_r + 1) * (max_c - min_c + 1)
    return max(1, min(9, max(len(pixels) // 10, area // 20)))

def score_repair_candidate(grid, background=None):
    if background is None:
        background = detect_background_color(grid)
    pixels = get_foreground_pixels(grid, background=background)
    if not pixels:
        return float('-inf')
    min_r, min_c, max_r, max_c = get_bbox(pixels)
    area = (max_r - min_r + 1) * (max_c - min_c + 1)
    density = len(pixels) / max(area, 1)
    shapes = get_shapes(grid, background=background, diag=True)
    shape_count = len(shapes)
    border_count = sum(1 for shape in shapes if touches_border(grid, shape))
    fragmentation_penalty = 0.25 * max(shape_count - 1, 0)
    border_penalty = 0.1 * border_count
    return max(symmetry_score_h(grid, background=background), symmetry_score_v(grid, background=background)) + density - fragmentation_penalty - border_penalty

def best_axis_completion(grid, background=None):
    if background is None:
        background = detect_background_color(grid)
    candidates = [
        copy_grid(grid),
        fill_from_mirror_h(grid, background=background),
        fill_from_mirror_v(grid, background=background),
        symmetrize_h(grid, background=background),
        symmetrize_v(grid, background=background),
        fill_from_mirror_h(fill_from_mirror_v(grid, background=background), background=background),
        fill_from_mirror_v(fill_from_mirror_h(grid, background=background), background=background),
    ]
    hole_filled = []
    for cand in candidates:
        hole_filled.append(best_enclosed_fill(cand, background=background, max_size=estimate_hole_size_limit(cand, background=background)))
    candidates.extend(hole_filled)
    return max(candidates, key=lambda cand: score_repair_candidate(cand, background=background))

def pick_main_shape(grid, background=None, diag=True):
    if background is None:
        background = detect_background_color(grid)
    shapes = get_shapes(grid, background=background, diag=diag)
    if not shapes:
        return []
    interior = [shape for shape in shapes if not touches_border(grid, shape)]
    pool = interior or shapes
    def shape_key(shape):
        cropped = crop_object(grid, shape, background=background)
        return (
            score_repair_candidate(cropped, background=background),
            len(shape),
            object_height(shape) * object_width(shape),
            -int(touches_border(grid, shape)),
        )
    return max(pool, key=shape_key)

def extract_main_shape(grid, background=None, diag=True):
    if background is None:
        background = detect_background_color(grid)
    shape = pick_main_shape(grid, background=background, diag=diag)
    if not shape:
        return crop_foreground(grid, background=background)
    return crop_object(grid, shape, background=background)

def repair_main_shape_symmetry(grid, noise_color=None, background=None, diag=True):
    if background is None:
        background = detect_background_color(grid)
    cleaned = remove_noise(grid, noise_color=noise_color, background=background) if noise_color is not None else copy_grid(grid)
    main = extract_main_shape(cleaned, background=background, diag=diag)
    repaired = repair_symmetry(main, axis='auto', background=background)
    repaired = best_enclosed_fill(repaired, background=background, max_size=estimate_hole_size_limit(repaired, background=background))
    return crop_foreground(repaired, background=background)

def repair_main_shape_in_place(grid, noise_color=None, background=None, diag=True):
    if background is None:
        background = detect_background_color(grid)
    cleaned = remove_noise(grid, noise_color=noise_color, background=background) if noise_color is not None else copy_grid(grid)
    shape = pick_main_shape(cleaned, background=background, diag=diag)
    if not shape:
        return cleaned
    min_r, min_c, max_r, max_c = get_bbox(shape)
    repaired = repair_main_shape_symmetry(cleaned, noise_color=None, background=background, diag=diag)
    fitted = fit_grid_to_size(repaired, max_r - min_r + 1, max_c - min_c + 1, background=background, align='center')
    out = copy_grid(cleaned)
    for r in range(min_r, max_r + 1):
        for c in range(min_c, max_c + 1):
            out[r][c] = background
    return paste(fitted, out, top=min_r, left=min_c, transparent=background)

def best_symmetry_repair(grid, noise_color=None, background=None, crop_result=True):
    if background is None:
        background = detect_background_color(grid)
    if noise_color is not None:
        cleaned = remove_noise(grid, noise_color=noise_color, background=background)
        repaired = repair_symmetry(cleaned, axis='auto', background=background)
        repaired = best_enclosed_fill(repaired, background=background, max_size=estimate_hole_size_limit(repaired, background=background))
        return crop_foreground(repaired, background=background) if crop_result else repaired
    best_grid = repair_symmetry(grid, axis='auto', background=background)
    best_grid = best_enclosed_fill(best_grid, background=background, max_size=estimate_hole_size_limit(best_grid, background=background))
    best_score = score_repair_candidate(best_grid, background=background)
    colors = non_background_colors(grid, background=background)
    ranked_colors = sorted(colors, key=lambda color: (count_color(grid, color), color != infer_noise_color(grid, background=background), color))
    for color in ranked_colors:
        cleaned = remove_color(grid, color, background=background)
        axis = choose_symmetry_axis(cleaned, background=background)
        candidate = repair_symmetry(cleaned, axis=axis, background=background)
        candidate = best_enclosed_fill(candidate, background=background, max_size=estimate_hole_size_limit(candidate, background=background))
        score = score_repair_candidate(candidate, background=background)
        if score > best_score:
            best_score = score
            best_grid = candidate
    return crop_foreground(best_grid, background=background) if crop_result else best_grid

def best_pattern_repair(grid, background=None, crop_result=True):
    if background is None:
        background = detect_background_color(grid)
    colors = non_background_colors(grid, background=background)
    ranked_single = sorted(colors, key=lambda color: (count_color(grid, color), color != infer_noise_color(grid, background=background), color))
    ranked_colors = [None] + ranked_single
    noise_sets = ranked_colors[:4]
    inferred_multi = infer_noise_colors(grid, max_colors=3, background=background)
    for count in (2, 3):
        if len(inferred_multi) >= count:
            noise_sets.append(tuple(inferred_multi[:count]))
    filled_grid = best_enclosed_fill(grid, background=background, max_size=estimate_hole_size_limit(grid, background=background))
    candidates = [
        crop_foreground(grid, background=background),
        crop_foreground(filled_grid, background=background),
    ]
    candidates.append(largest_object_grid(filled_grid, background=background, diag=True, crop_result=True))
    candidates.append(largest_shape_grid(filled_grid, background=background, diag=True, crop_result=True))
    candidates.append(main_shape_grid(filled_grid, background=background, diag=True, crop_result=True))
    for color in noise_sets:
        candidates.append(best_symmetry_repair(grid, noise_color=color, background=background, crop_result=True) if color is not None else best_symmetry_repair(grid, background=background, crop_result=True))
        candidates.append(repair_main_shape_symmetry(grid, noise_color=color, background=background))
        if color is not None:
            cleaned = remove_noise(grid, noise_color=color, background=background)
            filled_cleaned = best_enclosed_fill(cleaned, background=background, max_size=estimate_hole_size_limit(cleaned, background=background))
            candidates.append(crop_foreground(cleaned, background=background))
            candidates.append(crop_foreground(filled_cleaned, background=background))
            candidates.append(largest_object_grid(cleaned, background=background, diag=True, crop_result=True))
            candidates.append(largest_shape_grid(cleaned, background=background, diag=True, crop_result=True))
            candidates.append(main_shape_grid(cleaned, background=background, diag=True, crop_result=True))
            candidates.append(largest_object_grid(filled_cleaned, background=background, diag=True, crop_result=True))
            candidates.append(largest_shape_grid(filled_cleaned, background=background, diag=True, crop_result=True))
            candidates.append(main_shape_grid(filled_cleaned, background=background, diag=True, crop_result=True))
    for max_size in (1, 2):
        despeckled = remove_small_objects(grid, max_size=max_size, background=background, diag=True)
        despeckled_filled = best_enclosed_fill(despeckled, background=background, max_size=estimate_hole_size_limit(despeckled, background=background))
        candidates.append(crop_foreground(despeckled, background=background))
        candidates.append(crop_foreground(despeckled_filled, background=background))
        candidates.append(best_symmetry_repair(despeckled, background=background, crop_result=True))
        candidates.append(repair_main_shape_symmetry(despeckled, background=background))
        candidates.append(largest_object_grid(despeckled, background=background, diag=True, crop_result=True))
        candidates.append(largest_shape_grid(despeckled, background=background, diag=True, crop_result=True))
        candidates.append(main_shape_grid(despeckled, background=background, diag=True, crop_result=True))
        candidates.append(largest_object_grid(despeckled_filled, background=background, diag=True, crop_result=True))
        candidates.append(largest_shape_grid(despeckled_filled, background=background, diag=True, crop_result=True))
        candidates.append(main_shape_grid(despeckled_filled, background=background, diag=True, crop_result=True))
    for max_size in (1, 2):
        shape_cleaned = remove_small_shapes(grid, max_size=max_size, background=background, diag=True)
        shape_cleaned_filled = best_enclosed_fill(shape_cleaned, background=background, max_size=estimate_hole_size_limit(shape_cleaned, background=background))
        candidates.append(crop_foreground(shape_cleaned, background=background))
        candidates.append(crop_foreground(shape_cleaned_filled, background=background))
        candidates.append(best_symmetry_repair(shape_cleaned, background=background, crop_result=True))
        candidates.append(repair_main_shape_symmetry(shape_cleaned, background=background))
        candidates.append(largest_object_grid(shape_cleaned, background=background, diag=True, crop_result=True))
        candidates.append(largest_shape_grid(shape_cleaned, background=background, diag=True, crop_result=True))
        candidates.append(main_shape_grid(shape_cleaned, background=background, diag=True, crop_result=True))
        candidates.append(largest_object_grid(shape_cleaned_filled, background=background, diag=True, crop_result=True))
        candidates.append(largest_shape_grid(shape_cleaned_filled, background=background, diag=True, crop_result=True))
        candidates.append(main_shape_grid(shape_cleaned_filled, background=background, diag=True, crop_result=True))
    for max_size in (None, 4):
        border_cleaned = remove_border_objects_by_size(grid, max_size=max_size, background=background, diag=True)
        border_cleaned_filled = best_enclosed_fill(border_cleaned, background=background, max_size=estimate_hole_size_limit(border_cleaned, background=background))
        candidates.append(crop_foreground(border_cleaned, background=background))
        candidates.append(crop_foreground(border_cleaned_filled, background=background))
        candidates.append(best_symmetry_repair(border_cleaned, background=background, crop_result=True))
        candidates.append(repair_main_shape_symmetry(border_cleaned, background=background))
        candidates.append(largest_object_grid(border_cleaned, background=background, diag=True, crop_result=True))
        candidates.append(largest_shape_grid(border_cleaned, background=background, diag=True, crop_result=True))
        candidates.append(main_shape_grid(border_cleaned, background=background, diag=True, crop_result=True))
        candidates.append(largest_object_grid(border_cleaned_filled, background=background, diag=True, crop_result=True))
        candidates.append(largest_shape_grid(border_cleaned_filled, background=background, diag=True, crop_result=True))
        candidates.append(main_shape_grid(border_cleaned_filled, background=background, diag=True, crop_result=True))
    for max_size in (None, 4):
        border_shape_cleaned = remove_border_shapes_by_size(grid, max_size=max_size, background=background, diag=True)
        border_shape_filled = best_enclosed_fill(border_shape_cleaned, background=background, max_size=estimate_hole_size_limit(border_shape_cleaned, background=background))
        candidates.append(crop_foreground(border_shape_cleaned, background=background))
        candidates.append(crop_foreground(border_shape_filled, background=background))
        candidates.append(best_symmetry_repair(border_shape_cleaned, background=background, crop_result=True))
        candidates.append(repair_main_shape_symmetry(border_shape_cleaned, background=background))
        candidates.append(largest_object_grid(border_shape_cleaned, background=background, diag=True, crop_result=True))
        candidates.append(largest_shape_grid(border_shape_cleaned, background=background, diag=True, crop_result=True))
        candidates.append(main_shape_grid(border_shape_cleaned, background=background, diag=True, crop_result=True))
        candidates.append(largest_object_grid(border_shape_filled, background=background, diag=True, crop_result=True))
        candidates.append(largest_shape_grid(border_shape_filled, background=background, diag=True, crop_result=True))
        candidates.append(main_shape_grid(border_shape_filled, background=background, diag=True, crop_result=True))
    for n in (1, 2, 3):
        color_filtered = keep_most_common_colors(grid, n=n, background=background)
        color_filtered_filled = best_enclosed_fill(color_filtered, background=background, max_size=estimate_hole_size_limit(color_filtered, background=background))
        candidates.append(crop_foreground(color_filtered, background=background))
        candidates.append(crop_foreground(color_filtered_filled, background=background))
        candidates.append(best_symmetry_repair(color_filtered, background=background, crop_result=True))
        candidates.append(repair_main_shape_symmetry(color_filtered, background=background))
        candidates.append(largest_object_grid(color_filtered, background=background, diag=True, crop_result=True))
        candidates.append(largest_shape_grid(color_filtered, background=background, diag=True, crop_result=True))
        candidates.append(main_shape_grid(color_filtered, background=background, diag=True, crop_result=True))
        candidates.append(largest_object_grid(color_filtered_filled, background=background, diag=True, crop_result=True))
        candidates.append(largest_shape_grid(color_filtered_filled, background=background, diag=True, crop_result=True))
        candidates.append(main_shape_grid(color_filtered_filled, background=background, diag=True, crop_result=True))
    candidates.append(largest_object_grid(grid, background=background, diag=True, crop_result=True))
    candidates.append(largest_shape_grid(grid, background=background, diag=True, crop_result=True))
    candidates.append(main_shape_grid(grid, background=background, diag=True, crop_result=True))
    unique_candidates = []
    seen = set()
    for cand in candidates:
        sig = grid_signature(cand)
        if sig in seen:
            continue
        seen.add(sig)
        unique_candidates.append(cand)
    candidates = unique_candidates
    best = max(candidates, key=lambda cand: score_repair_candidate(cand, background=background) if cand else float('-inf'))
    if crop_result:
        return best
    in_place_candidates = [copy_grid(grid), filled_grid, foreground_in_place(grid, background=background), foreground_in_place(filled_grid, background=background)]
    in_place_candidates.append(largest_object_in_place(filled_grid, background=background, diag=True))
    in_place_candidates.append(largest_shape_in_place(filled_grid, background=background, diag=True))
    in_place_candidates.append(main_shape_in_place(filled_grid, background=background, diag=True))
    in_place_candidates += [repair_main_shape_in_place(grid, noise_color=color, background=background) for color in noise_sets]
    for color in noise_sets:
        if color is not None:
            cleaned = remove_noise(grid, noise_color=color, background=background)
            filled_cleaned = best_enclosed_fill(cleaned, background=background, max_size=estimate_hole_size_limit(cleaned, background=background))
            in_place_candidates.append(cleaned)
            in_place_candidates.append(filled_cleaned)
            in_place_candidates.append(foreground_in_place(cleaned, background=background))
            in_place_candidates.append(foreground_in_place(filled_cleaned, background=background))
            in_place_candidates.append(largest_object_in_place(cleaned, background=background, diag=True))
            in_place_candidates.append(largest_shape_in_place(cleaned, background=background, diag=True))
            in_place_candidates.append(main_shape_in_place(cleaned, background=background, diag=True))
            in_place_candidates.append(largest_object_in_place(filled_cleaned, background=background, diag=True))
            in_place_candidates.append(largest_shape_in_place(filled_cleaned, background=background, diag=True))
            in_place_candidates.append(main_shape_in_place(filled_cleaned, background=background, diag=True))
    for max_size in (1, 2):
        despeckled = remove_small_objects(grid, max_size=max_size, background=background, diag=True)
        despeckled_filled = best_enclosed_fill(despeckled, background=background, max_size=estimate_hole_size_limit(despeckled, background=background))
        in_place_candidates.append(despeckled)
        in_place_candidates.append(despeckled_filled)
        in_place_candidates.append(foreground_in_place(despeckled, background=background))
        in_place_candidates.append(foreground_in_place(despeckled_filled, background=background))
        in_place_candidates.append(repair_main_shape_in_place(despeckled, background=background))
        in_place_candidates.append(best_symmetry_repair(despeckled, background=background, crop_result=False))
        in_place_candidates.append(largest_object_in_place(despeckled, background=background, diag=True))
        in_place_candidates.append(largest_shape_in_place(despeckled, background=background, diag=True))
        in_place_candidates.append(main_shape_in_place(despeckled, background=background, diag=True))
        in_place_candidates.append(largest_object_in_place(despeckled_filled, background=background, diag=True))
        in_place_candidates.append(largest_shape_in_place(despeckled_filled, background=background, diag=True))
        in_place_candidates.append(main_shape_in_place(despeckled_filled, background=background, diag=True))
    for max_size in (1, 2):
        shape_cleaned = remove_small_shapes(grid, max_size=max_size, background=background, diag=True)
        shape_cleaned_filled = best_enclosed_fill(shape_cleaned, background=background, max_size=estimate_hole_size_limit(shape_cleaned, background=background))
        in_place_candidates.append(shape_cleaned)
        in_place_candidates.append(shape_cleaned_filled)
        in_place_candidates.append(foreground_in_place(shape_cleaned, background=background))
        in_place_candidates.append(foreground_in_place(shape_cleaned_filled, background=background))
        in_place_candidates.append(repair_main_shape_in_place(shape_cleaned, background=background))
        in_place_candidates.append(best_symmetry_repair(shape_cleaned, background=background, crop_result=False))
        in_place_candidates.append(largest_object_in_place(shape_cleaned, background=background, diag=True))
        in_place_candidates.append(largest_shape_in_place(shape_cleaned, background=background, diag=True))
        in_place_candidates.append(main_shape_in_place(shape_cleaned, background=background, diag=True))
        in_place_candidates.append(largest_object_in_place(shape_cleaned_filled, background=background, diag=True))
        in_place_candidates.append(largest_shape_in_place(shape_cleaned_filled, background=background, diag=True))
        in_place_candidates.append(main_shape_in_place(shape_cleaned_filled, background=background, diag=True))
    for max_size in (None, 4):
        border_cleaned = remove_border_objects_by_size(grid, max_size=max_size, background=background, diag=True)
        border_cleaned_filled = best_enclosed_fill(border_cleaned, background=background, max_size=estimate_hole_size_limit(border_cleaned, background=background))
        in_place_candidates.append(border_cleaned)
        in_place_candidates.append(border_cleaned_filled)
        in_place_candidates.append(foreground_in_place(border_cleaned, background=background))
        in_place_candidates.append(foreground_in_place(border_cleaned_filled, background=background))
        in_place_candidates.append(repair_main_shape_in_place(border_cleaned, background=background))
        in_place_candidates.append(best_symmetry_repair(border_cleaned, background=background, crop_result=False))
        in_place_candidates.append(largest_object_in_place(border_cleaned, background=background, diag=True))
        in_place_candidates.append(largest_shape_in_place(border_cleaned, background=background, diag=True))
        in_place_candidates.append(main_shape_in_place(border_cleaned, background=background, diag=True))
        in_place_candidates.append(largest_object_in_place(border_cleaned_filled, background=background, diag=True))
        in_place_candidates.append(largest_shape_in_place(border_cleaned_filled, background=background, diag=True))
        in_place_candidates.append(main_shape_in_place(border_cleaned_filled, background=background, diag=True))
    for max_size in (None, 4):
        border_shape_cleaned = remove_border_shapes_by_size(grid, max_size=max_size, background=background, diag=True)
        border_shape_filled = best_enclosed_fill(border_shape_cleaned, background=background, max_size=estimate_hole_size_limit(border_shape_cleaned, background=background))
        in_place_candidates.append(border_shape_cleaned)
        in_place_candidates.append(border_shape_filled)
        in_place_candidates.append(foreground_in_place(border_shape_cleaned, background=background))
        in_place_candidates.append(foreground_in_place(border_shape_filled, background=background))
        in_place_candidates.append(repair_main_shape_in_place(border_shape_cleaned, background=background))
        in_place_candidates.append(best_symmetry_repair(border_shape_cleaned, background=background, crop_result=False))
        in_place_candidates.append(largest_object_in_place(border_shape_cleaned, background=background, diag=True))
        in_place_candidates.append(largest_shape_in_place(border_shape_cleaned, background=background, diag=True))
        in_place_candidates.append(main_shape_in_place(border_shape_cleaned, background=background, diag=True))
        in_place_candidates.append(largest_object_in_place(border_shape_filled, background=background, diag=True))
        in_place_candidates.append(largest_shape_in_place(border_shape_filled, background=background, diag=True))
        in_place_candidates.append(main_shape_in_place(border_shape_filled, background=background, diag=True))
    for n in (1, 2, 3):
        color_filtered = keep_most_common_colors(grid, n=n, background=background)
        color_filtered_filled = best_enclosed_fill(color_filtered, background=background, max_size=estimate_hole_size_limit(color_filtered, background=background))
        in_place_candidates.append(color_filtered)
        in_place_candidates.append(color_filtered_filled)
        in_place_candidates.append(foreground_in_place(color_filtered, background=background))
        in_place_candidates.append(foreground_in_place(color_filtered_filled, background=background))
        in_place_candidates.append(repair_main_shape_in_place(color_filtered, background=background))
        in_place_candidates.append(best_symmetry_repair(color_filtered, background=background, crop_result=False))
        in_place_candidates.append(largest_object_in_place(color_filtered, background=background, diag=True))
        in_place_candidates.append(largest_shape_in_place(color_filtered, background=background, diag=True))
        in_place_candidates.append(main_shape_in_place(color_filtered, background=background, diag=True))
        in_place_candidates.append(largest_object_in_place(color_filtered_filled, background=background, diag=True))
        in_place_candidates.append(largest_shape_in_place(color_filtered_filled, background=background, diag=True))
        in_place_candidates.append(main_shape_in_place(color_filtered_filled, background=background, diag=True))
    in_place_candidates.append(largest_object_in_place(grid, background=background, diag=True))
    in_place_candidates.append(largest_shape_in_place(grid, background=background, diag=True))
    in_place_candidates.append(main_shape_in_place(grid, background=background, diag=True))
    in_place_candidates.append(best_symmetry_repair(grid, background=background, crop_result=False))
    unique_candidates = []
    seen = set()
    for cand in in_place_candidates:
        sig = grid_signature(cand)
        if sig in seen:
            continue
        seen.add(sig)
        unique_candidates.append(cand)
    in_place_candidates = unique_candidates
    return max(in_place_candidates, key=lambda cand: score_repair_candidate(cand, background=background) if cand else float('-inf'))

def solve_occlusion(grid, noise_color=None, background=None, crop_result=True):
    if background is None:
        background = detect_background_color(grid)
    if noise_color is not None:
        cleaned = remove_noise(grid, noise_color=noise_color, background=background)
        return best_pattern_repair(cleaned, background=background, crop_result=crop_result)
    return best_pattern_repair(grid, background=background, crop_result=crop_result)

def solve_occlusion_in_place(grid, noise_color=None, background=None):
    return solve_occlusion(grid, noise_color=noise_color, background=background, crop_result=False)

def best_pattern_repair_in_place(grid, background=None):
    return best_pattern_repair(grid, background=background, crop_result=False)

repair_pattern_in_place = best_pattern_repair_in_place
restore_pattern_in_place = best_pattern_repair_in_place
solve_pattern_in_place = solve_occlusion_in_place

def foreground_in_place(grid, background=None, align='center'):
    if background is None:
        background = detect_background_color(grid)
    cropped = crop_foreground(grid, background=background)
    return fit_grid_to_size(cropped, len(grid), len(grid[0]), background=background, align=align)

foreground_canvas = foreground_in_place
fit_foreground_to_canvas = foreground_in_place
crop_to_canvas = foreground_in_place

def largest_object_grid(grid, background=None, diag=False, crop_result=True):
    if background is None:
        background = detect_background_color(grid)
    objs = get_objects(grid, background=background, diag=diag)
    if not objs:
        return crop_foreground(grid, background=background) if crop_result else copy_grid(grid)
    largest = max(objs, key=len)
    out = crop_object(grid, largest, background=background)
    return crop_foreground(out, background=background) if crop_result else out

def largest_object_in_place(grid, background=None, diag=False):
    if background is None:
        background = detect_background_color(grid)
    objs = get_objects(grid, background=background, diag=diag)
    if not objs:
        return copy_grid(grid)
    largest = max(objs, key=len)
    min_r, min_c, max_r, max_c = get_bbox(largest)
    cropped = crop_object(grid, largest, background=background)
    cropped = crop_foreground(cropped, background=background)
    fitted = fit_grid_to_size(cropped, max_r - min_r + 1, max_c - min_c + 1, background=background, align='center')
    out = make_grid(len(grid), len(grid[0]), background)
    return paste(fitted, out, top=min_r, left=min_c, transparent=background)

def largest_shape_grid(grid, background=None, diag=True, crop_result=True):
    if background is None:
        background = detect_background_color(grid)
    shapes = get_shapes(grid, background=background, diag=diag)
    if not shapes:
        return crop_foreground(grid, background=background) if crop_result else copy_grid(grid)
    largest = max(shapes, key=len)
    out = crop_object(grid, largest, background=background)
    return crop_foreground(out, background=background) if crop_result else out

def largest_shape_in_place(grid, background=None, diag=True):
    if background is None:
        background = detect_background_color(grid)
    shapes = get_shapes(grid, background=background, diag=diag)
    if not shapes:
        return copy_grid(grid)
    largest = max(shapes, key=len)
    min_r, min_c, max_r, max_c = get_bbox(largest)
    cropped = crop_object(grid, largest, background=background)
    cropped = crop_foreground(cropped, background=background)
    fitted = fit_grid_to_size(cropped, max_r - min_r + 1, max_c - min_c + 1, background=background, align='center')
    out = make_grid(len(grid), len(grid[0]), background)
    return paste(fitted, out, top=min_r, left=min_c, transparent=background)

def main_shape_grid(grid, background=None, diag=True, crop_result=True):
    if background is None:
        background = detect_background_color(grid)
    shape = pick_main_shape(grid, background=background, diag=diag)
    if not shape:
        return crop_foreground(grid, background=background) if crop_result else copy_grid(grid)
    out = crop_object(grid, shape, background=background)
    return crop_foreground(out, background=background) if crop_result else out

def main_shape_in_place(grid, background=None, diag=True):
    if background is None:
        background = detect_background_color(grid)
    shape = pick_main_shape(grid, background=background, diag=diag)
    if not shape:
        return copy_grid(grid)
    min_r, min_c, max_r, max_c = get_bbox(shape)
    cropped = crop_object(grid, shape, background=background)
    cropped = crop_foreground(cropped, background=background)
    fitted = fit_grid_to_size(cropped, max_r - min_r + 1, max_c - min_c + 1, background=background, align='center')
    out = make_grid(len(grid), len(grid[0]), background)
    return paste(fitted, out, top=min_r, left=min_c, transparent=background)

def fill_rect(grid, bbox, color):
    out = copy_grid(grid)
    min_r, min_c, max_r, max_c = bbox
    for r in range(max(min_r, 0), min(max_r + 1, len(out))):
        for c in range(max(min_c, 0), min(max_c + 1, len(out[0]))):
            out[r][c] = color
    return out

def outline_bbox(grid, bbox, color):
    out = copy_grid(grid)
    min_r, min_c, max_r, max_c = bbox
    for c in range(max(min_c, 0), min(max_c + 1, len(out[0]))):
        if 0 <= min_r < len(out):
            out[min_r][c] = color
        if 0 <= max_r < len(out):
            out[max_r][c] = color
    for r in range(max(min_r, 0), min(max_r + 1, len(out))):
        if 0 <= min_c < len(out[0]):
            out[r][min_c] = color
        if 0 <= max_c < len(out[0]):
            out[r][max_c] = color
    return out

def outline_object(grid, obj, color):
    return outline_bbox(grid, get_bbox(obj), color)

def draw_line(grid, start, end, color):
    out = copy_grid(grid)
    r1, c1 = start
    r2, c2 = end
    dr = 0 if r1 == r2 else (1 if r2 > r1 else -1)
    dc = 0 if c1 == c2 else (1 if c2 > c1 else -1)
    r, c = r1, c1
    while True:
        if 0 <= r < len(out) and 0 <= c < len(out[0]):
            out[r][c] = color
        if (r, c) == (r2, c2):
            break
        r += dr
        c += dc
    return out

def apply_gravity(grid, direction="down", background=None):
    if background is None:
        background = detect_background_color(grid)
    rows, cols = len(grid), len(grid[0])
    out = make_grid(rows, cols, background)

    if direction in ("down", "up"):
        for c in range(cols):
            values = [grid[r][c] for r in range(rows) if grid[r][c] != background]
            if direction == "down":
                start = rows - len(values)
                for i, value in enumerate(values):
                    out[start + i][c] = value
            else:
                for i, value in enumerate(values):
                    out[i][c] = value
    else:
        for r in range(rows):
            values = [grid[r][c] for c in range(cols) if grid[r][c] != background]
            if direction == "right":
                start = cols - len(values)
                for i, value in enumerate(values):
                    out[r][start + i] = value
            else:
                for i, value in enumerate(values):
                    out[r][i] = value
    return out

def filter_by_color(grid, objects, color):
    return [obj for obj in objects if get_color(grid, obj) == color]

def filter_by_size(objects, size=None, min_size=None, max_size=None):
    out = []
    for obj in objects:
        n = len(obj)
        if size is not None and n != size:
            continue
        if min_size is not None and n < min_size:
            continue
        if max_size is not None and n > max_size:
            continue
        out.append(obj)
    return out

def filter_by_dimensions(objects, width=None, height=None, min_width=None, max_width=None, min_height=None, max_height=None):
    out = []
    for obj in objects:
        w = object_width(obj)
        h = object_height(obj)
        if width is not None and w != width:
            continue
        if height is not None and h != height:
            continue
        if min_width is not None and w < min_width:
            continue
        if max_width is not None and w > max_width:
            continue
        if min_height is not None and h < min_height:
            continue
        if max_height is not None and h > max_height:
            continue
        out.append(obj)
    return out

def filter_by_position(objects, top=None, left=None, bottom=None, right=None):
    out = []
    for obj in objects:
        min_r, min_c, max_r, max_c = get_bbox(obj)
        if top is not None and min_r != top:
            continue
        if left is not None and min_c != left:
            continue
        if bottom is not None and max_r != bottom:
            continue
        if right is not None and max_c != right:
            continue
        out.append(obj)
    return out

def merge_objects(objects):
    merged = []
    for obj in objects:
        merged.extend(obj)
    return merged

def sort_objects(objects, key="size", reverse=False):
    if key == "size":
        fn = len
    elif key == "height":
        fn = object_height
    elif key == "width":
        fn = object_width
    elif key == "area":
        fn = lambda obj: object_height(obj) * object_width(obj)
    elif key == "top":
        fn = lambda obj: get_bbox(obj)[0]
    elif key == "left":
        fn = lambda obj: get_bbox(obj)[1]
    elif key == "bottom":
        fn = lambda obj: get_bbox(obj)[2]
    elif key == "right":
        fn = lambda obj: get_bbox(obj)[3]
    elif key == "center_r":
        fn = lambda obj: object_center(obj)[0]
    elif key == "center_c":
        fn = lambda obj: object_center(obj)[1]
    else:
        fn = len
    return sorted(objects, key=fn, reverse=reverse)

def manhattan_distance(obj1, obj2):
    if not obj1 or not obj2:
        return 0
    return min(abs(r1 - r2) + abs(c1 - c2) for r1, c1 in obj1 for r2, c2 in obj2)

def get_distance(obj1, obj2):
    return manhattan_distance(obj1, obj2)

def is_inside(inner, outer):
    if not inner or not outer:
        return False
    min_r1, min_c1, max_r1, max_c1 = get_bbox(inner)
    min_r2, min_c2, max_r2, max_c2 = get_bbox(outer)
    return min_r2 <= min_r1 <= max_r1 <= max_r2 and min_c2 <= min_c1 <= max_c1 <= max_c2

def overlaps(obj1, obj2):
    return bool(set(obj1) & set(obj2)) if obj1 and obj2 else False

def touching(obj1, obj2, diag=False):
    if not obj1 or not obj2:
        return False
    other = set(obj2)
    neighbors = [(0,1),(0,-1),(1,0),(-1,0)] + ([(1,1),(1,-1),(-1,1),(-1,-1)] if diag else [])
    for r, c in obj1:
        for dr, dc in neighbors:
            if (r + dr, c + dc) in other:
                return True
    return False

def same_shape(obj1, obj2):
    return sorted(normalize_object(obj1)) == sorted(normalize_object(obj2))

def same_dimensions(obj1, obj2):
    return object_dimensions(obj1) == object_dimensions(obj2) if obj1 and obj2 else False

def same_color(grid, obj1, obj2):
    return get_color(grid, obj1) == get_color(grid, obj2) if obj1 and obj2 else False

def is_square_object(obj):
    return object_height(obj) == object_width(obj) if obj else False

def is_line_object(obj):
    return object_height(obj) == 1 or object_width(obj) == 1 if obj else False

def is_rectangle_object(obj):
    return len(obj) == object_height(obj) * object_width(obj) if obj else False

def is_above(obj1, obj2):
    return get_bbox(obj1)[2] < get_bbox(obj2)[0] if obj1 and obj2 else False

def is_below(obj1, obj2):
    return get_bbox(obj1)[0] > get_bbox(obj2)[2] if obj1 and obj2 else False

def is_left_of(obj1, obj2):
    return get_bbox(obj1)[3] < get_bbox(obj2)[1] if obj1 and obj2 else False

def is_right_of(obj1, obj2):
    return get_bbox(obj1)[1] > get_bbox(obj2)[3] if obj1 and obj2 else False

def touches_border(grid, obj):
    if not obj:
        return False
    rows, cols = len(grid), len(grid[0])
    return any(r == 0 or c == 0 or r == rows - 1 or c == cols - 1 for r, c in obj)

def border_objects(grid, objects):
    return [obj for obj in objects if touches_border(grid, obj)]

def interior_objects(grid, objects):
    return [obj for obj in objects if not touches_border(grid, obj)]

def largest_object(objects):
    return max(objects, key=len) if objects else []

def smallest_object(objects):
    return min(objects, key=len) if objects else []

def topmost_object(objects):
    return min(objects, key=lambda obj: get_bbox(obj)[0]) if objects else []

def bottommost_object(objects):
    return max(objects, key=lambda obj: get_bbox(obj)[2]) if objects else []

def leftmost_object(objects):
    return min(objects, key=lambda obj: get_bbox(obj)[1]) if objects else []

def rightmost_object(objects):
    return max(objects, key=lambda obj: get_bbox(obj)[3]) if objects else []

def count_objects(grid, background=None, diag=False):
    return len(get_objects(grid, background=background, diag=diag))

def nearest_object(target, objects):
    return min(objects, key=lambda obj: manhattan_distance(target, obj)) if target and objects else []

def farthest_object(target, objects):
    return max(objects, key=lambda obj: manhattan_distance(target, obj)) if target and objects else []

# Common ARC aliases that models frequently guess.
find_objects = get_objects
connected_components = get_objects
foreground_pixels = get_foreground_pixels
content_bbox = foreground_bbox
find_shapes = get_shapes
shapes = get_shapes
objects = get_objects
bbox = get_bbox
get_bounding_box = get_bbox
bounding_box = get_bbox
background_color = detect_background_color
get_background_color = detect_background_color
count_colors = color_counts
dominant_color = most_common_color
foreground_color = dominant_non_background_color
color_of = get_color
dimensions_of = object_dimensions
shape_colors = object_colors
shape_color_counts = object_color_counts
colors = palette
non_bg_colors = non_background_colors
group_objects_by_color = objects_by_color
objects_of_color = get_objects_by_color
cells_of_color = find_cells
bbox_of_color = get_bbox_of_color
shift = translate
move = move_object
shift_grid_by = shift_grid
translate_grid = shift_grid
move_grid = shift_grid
translate_object = move_object
paint = paint_object
erase = erase_object
subgrid = crop
extract_foreground = crop_foreground
crop_to_content = crop_foreground
shape_to_grid = crop_object
gravity = apply_gravity
drop = apply_gravity
map_colors = remap_colors
replace_colors = remap_colors
color_mask = extract_color
mask_color = extract_color
isolate_color = extract_color
remove = remove_color
scale = scale_grid
zoom = scale_grid
tile = tile_grid
rot90 = rotate_cw
rot180 = rotate_180
rot270 = rotate_ccw
flip_main_diagonal = transpose
anti_diagonal_flip = flip_anti_diagonal
flip_horizontal = mirror_h
flip_vertical = mirror_v
horizontal_symmetry = is_symmetric_h
vertical_symmetry = is_symmetric_v
complete_horizontal_symmetry = symmetrize_h
complete_vertical_symmetry = symmetrize_v
compose = overlay
merge_grids = overlay
draw_bbox = outline_bbox
draw_box = outline_bbox
outline = outline_object
color_filter = filter_by_color
size_filter = filter_by_size
position_filter = filter_by_position
dimension_filter = filter_by_dimensions
order_objects = sort_objects
extract_object = crop_object
distance_between = manhattan_distance
intersects = overlaps
adjacent = touching
largest = largest_object
smallest = smallest_object
topmost = topmost_object
bottommost = bottommost_object
leftmost = leftmost_object
rightmost = rightmost_object
nearest = nearest_object
farthest = farthest_object
same_size = same_dimensions
square_object = is_square_object
line_object = is_line_object
rectangle_object = is_rectangle_object
edge_objects = border_objects
remove_noise_color = remove_noise
denoise = remove_noise
drop_noise = remove_noise
infer_noise = infer_noise_color
infer_noises = infer_noise_colors
despeckle = remove_small_objects
remove_specks = remove_small_objects
remove_tiny_shapes = remove_small_shapes
remove_border_noise = remove_border_objects_by_size
keep_main_colors = keep_most_common_colors
isolate_main_color = keep_most_common_colors
safe_subgrid = safe_crop
crop_safe = safe_crop
fit_to_size = fit_grid_to_size
resize_canvas = fit_grid_to_size
choose_axis = choose_symmetry_axis
restore_symmetry = repair_symmetry
complete_symmetry = repair_symmetry
mirror_fill_h = fill_from_mirror_h
mirror_fill_v = fill_from_mirror_v
best_axis = best_axis_completion
repair_pattern = denoise_and_repair_symmetry
repair_occlusion = best_pattern_repair
solve_noise = best_pattern_repair
solve_occluded_symmetry = best_pattern_repair
occlusion_solver = solve_occlusion
best_repair = best_pattern_repair
repair_best = best_pattern_repair
repair_pattern_auto = best_pattern_repair
solve_pattern = best_pattern_repair
restore_pattern = best_pattern_repair
largest_object_crop = largest_object_grid
largest_object_canvas = largest_object_in_place
largest_shape_crop = largest_shape_grid
largest_shape_canvas = largest_shape_in_place
main_shape_crop = main_shape_grid
main_shape_canvas = main_shape_in_place
extract_pattern = main_shape_grid
pattern_crop = main_shape_grid
extract_largest_shape = largest_shape_grid
extract_main_object = largest_object_grid
extract_main_shape = main_shape_grid
extract_pattern_canvas = main_shape_in_place
extract_main_object_canvas = largest_object_in_place
extract_largest_shape_canvas = largest_shape_in_place
main_shape = pick_main_shape
extract_main_pattern = extract_main_shape
repair_main_pattern = repair_main_shape_symmetry
repair_in_place = repair_main_shape_in_place
fill_holes = fill_enclosed_background
repair_holes = fill_enclosed_background
hole_limit = estimate_hole_size_limit

def fill_l_shape_corners(grid, fill_color=1, background=None):
    """For each 2x2 region with exactly 3 same-color non-background cells, fill the 4th with fill_color."""
    if background is None:
        background = detect_background_color(grid)
    out = copy_grid(grid)
    rows, cols = len(grid), len(grid[0])
    for r in range(rows - 1):
        for c in range(cols - 1):
            cells = [(r, c), (r, c+1), (r+1, c), (r+1, c+1)]
            non_bg = [(rr, cc) for rr, cc in cells if grid[rr][cc] != background]
            bg_cells = [(rr, cc) for rr, cc in cells if grid[rr][cc] == background]
            if len(non_bg) == 3 and len(bg_cells) == 1:
                colors = [grid[rr][cc] for rr, cc in non_bg]
                if len(set(colors)) == 1:
                    rr, cc = bg_cells[0]
                    out[rr][cc] = fill_color
    return out

def kronecker_block_diagonal(grid, background=None):
    """Place the input grid at each background-colored block position in an n*rows x n*cols output."""
    if background is None:
        background = detect_background_color(grid)
    rows, cols = len(grid), len(grid[0])
    out = make_grid(rows * rows, cols * cols, 0)
    for i in range(rows):
        for j in range(cols):
            if grid[i][j] == background:
                for r in range(rows):
                    for c in range(cols):
                        out[i * rows + r][j * cols + c] = grid[r][c]
    return out

def count_special_colors(grid, background=None):
    """Count non-background, non-standard (minority) colors; return sorted by frequency desc."""
    rows, cols = len(grid), len(grid[0])
    if background is None:
        background = detect_background_color(grid)
    counts = color_counts(grid)
    non_bg = {c: v for c, v in counts.items() if c != background}
    if not non_bg:
        return [[background]]
    standard = max(non_bg, key=lambda c: non_bg[c])
    special = {c: v for c, v in non_bg.items() if c != standard}
    if not special:
        return [[background]]
    sorted_special = sorted(special.keys(), key=lambda c: (-special[c], c))
    return [[c] for c in sorted_special]

def fill_enclosed_by_parity(grid, odd_color=7, even_color=2, background=None):
    """Fill enclosed background regions: odd sqrt(size) -> odd_color, even -> even_color."""
    if background is None:
        background = detect_background_color(grid)
    rows, cols = len(grid), len(grid[0])
    out = copy_grid(grid)
    visited = set()
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background or (r, c) in visited:
                continue
            region = flood_fill(grid, (r, c), target_color=background)
            for cell in region:
                visited.add(cell)
            touches_edge = any(rr == 0 or cc == 0 or rr == rows - 1 or cc == cols - 1 for rr, cc in region)
            if touches_edge:
                continue
            n = int(len(region) ** 0.5)
            fill = odd_color if n % 2 == 1 else even_color
            for rr, cc in region:
                out[rr][cc] = fill
    return out

def assemble_l_shapes(grid, background=None):
    """Place each 3-cell L-shaped object into its corresponding quadrant of a 4x4 output based on corner orientation."""
    if background is None:
        background = detect_background_color(grid)
    objects = get_objects(grid, background=background, diag=False)
    l_shapes = [obj for obj in objects if len(obj) == 3]
    if not l_shapes:
        return [[background] * 4 for _ in range(4)]
    output = [[background] * 4 for _ in range(4)]
    for obj in l_shapes:
        color = grid[obj[0][0]][obj[0][1]]
        min_r = min(r for r, c in obj)
        min_c = min(c for r, c in obj)
        normalized = frozenset((r - min_r, c - min_c) for r, c in obj)
        if normalized == frozenset([(0, 0), (0, 1), (1, 0)]):
            for r, c in [(0, 0), (0, 1), (1, 0)]:
                output[r][c] = color
        elif normalized == frozenset([(0, 0), (0, 1), (1, 1)]):
            for r, c in [(0, 2), (0, 3), (1, 3)]:
                output[r][c] = color
        elif normalized == frozenset([(0, 0), (1, 0), (1, 1)]):
            for r, c in [(2, 0), (3, 0), (3, 1)]:
                output[r][c] = color
        elif normalized == frozenset([(0, 1), (1, 0), (1, 1)]):
            for r, c in [(2, 3), (3, 2), (3, 3)]:
                output[r][c] = color
    return output

def reflect_2x2_block_to_corners(grid, background=0):
    """
    Find the unique 2x2 non-background block; place its diagonally-opposite values
    at the 4 adjacent diagonal zones (each 2x2, clipped to grid bounds).
    """
    rows, cols = len(grid), len(grid[0])
    block_r, block_c = None, None
    for r in range(rows - 1):
        for c in range(cols - 1):
            if (grid[r][c] != background and grid[r][c+1] != background and
                    grid[r+1][c] != background and grid[r+1][c+1] != background):
                block_r, block_c = r, c
                break
        if block_r is not None:
            break
    if block_r is None:
        return grid
    tl = grid[block_r][block_c]
    tr = grid[block_r][block_c + 1]
    bl = grid[block_r + 1][block_c]
    br = grid[block_r + 1][block_c + 1]
    out = [row[:] for row in grid]
    for er, ec, value in [
        (block_r - 2, block_c - 2, br),
        (block_r - 2, block_c + 2, bl),
        (block_r + 2, block_c - 2, tr),
        (block_r + 2, block_c + 2, tl),
    ]:
        for dr in range(2):
            for dc in range(2):
                rr, cc = er + dr, ec + dc
                if 0 <= rr < rows and 0 <= cc < cols:
                    out[rr][cc] = value
    return out

def find_unique_quadrant(grid):
    """
    Grid divided into 4 quadrants by bands of all-zero rows and columns.
    Returns the quadrant whose dominant non-zero color is unique (not shared by any other quadrant).
    """
    rows, cols = len(grid), len(grid[0])
    zero_rows = [r for r in range(rows) if all(grid[r][c] == 0 for c in range(cols))]
    zero_cols = [c for c in range(cols) if all(grid[r][c] == 0 for r in range(rows))]
    if not zero_rows or not zero_cols:
        return grid
    def group_consecutive(lst):
        if not lst: return []
        groups = [[lst[0]]]
        for x in lst[1:]:
            if x == groups[-1][-1] + 1:
                groups[-1].append(x)
            else:
                groups.append([x])
        return groups
    mid_r, mid_c = rows // 2, cols // 2
    row_groups = group_consecutive(zero_rows)
    col_groups = group_consecutive(zero_cols)
    sep_row_group = min(row_groups, key=lambda g: abs(sum(g)/len(g) - mid_r))
    sep_col_group = min(col_groups, key=lambda g: abs(sum(g)/len(g) - mid_c))
    sr0, sr1 = sep_row_group[0], sep_row_group[-1]
    sc0, sc1 = sep_col_group[0], sep_col_group[-1]
    quadrants = []
    for r_start, r_end in [(0, sr0), (sr1 + 1, rows)]:
        for c_start, c_end in [(0, sc0), (sc1 + 1, cols)]:
            if r_end > r_start and c_end > c_start:
                quad = [row[c_start:c_end] for row in grid[r_start:r_end]]
                cc = {}
                for row in quad:
                    for v in row:
                        if v != 0: cc[v] = cc.get(v, 0) + 1
                dom = max(cc, key=lambda x: cc[x]) if cc else 0
                quadrants.append((quad, dom))
    if len(quadrants) != 4:
        return grid
    freq = {}
    for _, c in quadrants:
        freq[c] = freq.get(c, 0) + 1
    for quad, color in quadrants:
        if freq.get(color, 0) == 1:
            return quad
    return grid

def draw_borders_around_pairs(grid, background=0, border_color=3):
    """
    For each connected component of non-background cells with size >= 2,
    draw the bounding box border using border_color (within grid bounds).
    Single isolated cells are not bordered.
    """
    rows, cols = len(grid), len(grid[0])
    visited = [[False]*cols for _ in range(rows)]
    components = []
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background and not visited[r][c]:
                comp, queue = [], [(r,c)]
                visited[r][c] = True
                while queue:
                    rr, cc = queue.pop(0)
                    comp.append((rr, cc))
                    for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nr, nc = rr+dr, cc+dc
                        if 0<=nr<rows and 0<=nc<cols and not visited[nr][nc] and grid[nr][nc]!=background:
                            visited[nr][nc] = True
                            queue.append((nr, nc))
                components.append(comp)
    out = [row[:] for row in grid]
    for comp in components:
        if len(comp) < 2: continue
        r0 = min(r for r,c in comp); r1 = max(r for r,c in comp)
        c0 = min(c for r,c in comp); c1 = max(c for r,c in comp)
        for r in range(r0-1, r1+2):
            for c in range(c0-1, c1+2):
                if 0<=r<rows and 0<=c<cols:
                    if (r==r0-1 or r==r1+1 or c==c0-1 or c==c1+1) and grid[r][c]==background:
                        out[r][c] = border_color
    return out

def mark_uniform_rows(grid, fill_color=5, clear_color=0):
    """
    For each row: if all values are identical, replace with fill_color repeated;
    otherwise replace with clear_color repeated.
    """
    out = []
    cols = len(grid[0]) if grid else 0
    for row in grid:
        if len(set(row)) == 1:
            out.append([fill_color] * cols)
        else:
            out.append([clear_color] * cols)
    return out

def find_unique_colored_quadrant(grid):
    """
    Find a cross (one full row + one full col of same color, including 0).
    Divide into 4 quadrants. Return the quadrant whose unique non-cross color
    does not appear in the other three quadrants.
    """
    rows, cols = len(grid), len(grid[0])
    def group_consecutive(lst):
        if not lst: return []
        groups = [[lst[0]]]
        for x in lst[1:]:
            if x == groups[-1][-1] + 1:
                groups[-1].append(x)
            else:
                groups.append([x])
        return groups
    # Collect separator rows: any row where all values are identical (including 0)
    sep_rows_by_color = {}
    for r in range(rows):
        vals = set(grid[r])
        if len(vals) == 1:
            v = list(vals)[0]
            sep_rows_by_color.setdefault(v, []).append(r)
    # Collect separator cols: any col where all values are identical (including 0)
    sep_cols_by_color = {}
    for c in range(cols):
        vals = set(grid[r][c] for r in range(rows))
        if len(vals) == 1:
            v = list(vals)[0]
            sep_cols_by_color.setdefault(v, []).append(c)
    # Find a color that appears as both separator rows and separator cols
    cross_color = next((v for v in sep_rows_by_color if v in sep_cols_by_color), None)
    if cross_color is None:
        return grid
    sep_rows = sep_rows_by_color[cross_color]
    sep_cols = sep_cols_by_color[cross_color]
    row_groups = group_consecutive(sep_rows)
    col_groups = group_consecutive(sep_cols)
    mid_r, mid_c = rows // 2, cols // 2
    srg = min(row_groups, key=lambda g: abs(sum(g)/len(g) - mid_r))
    scg = min(col_groups, key=lambda g: abs(sum(g)/len(g) - mid_c))
    sr0, sr1 = srg[0], srg[-1]
    sc0, sc1 = scg[0], scg[-1]
    quadrant_ranges = [(0, sr0, 0, sc0), (0, sr0, sc1+1, cols),
                       (sr1+1, rows, 0, sc0), (sr1+1, rows, sc1+1, cols)]
    quads = []
    for r0, r1, c0, c1 in quadrant_ranges:
        if r1 > r0 and c1 > c0:
            quad = [row[c0:c1] for row in grid[r0:r1]]
            colors = set(v for row in quad for v in row if v != cross_color)
            quads.append((quad, colors))
    if len(quads) != 4:
        return grid
    all_colors = [q[1] for q in quads]
    for i, (quad, colors) in enumerate(quads):
        other_colors = set().union(*[all_colors[j] for j in range(4) if j != i])
        unique = colors - other_colors
        if unique:
            return quad
    return grid

def and_halves_by_separator(grid, separator=5, result_color=2, background=0):
    """
    Find the separator column (all cells == separator).
    Split into left/right halves. Output = result_color where BOTH halves
    have non-background; else background. Output width = min of both halves.
    """
    rows, cols = len(grid), len(grid[0])
    sep_col = next((c for c in range(cols) if all(grid[r][c] == separator for r in range(rows))), None)
    if sep_col is None:
        return grid
    left = [row[:sep_col] for row in grid]
    right = [row[sep_col+1:] for row in grid]
    w = min(len(left[0]), len(right[0]))
    out = []
    for r in range(rows):
        row = [result_color if left[r][c] != background and right[r][c] != background else background for c in range(w)]
        out.append(row)
    return out

def fill_diagonal_tile(grid, background=0):
    """
    Non-zero cells define a 3-color diagonal stripe pattern.
    Each cell at (r,c) maps (r+c)%3 to a color.
    The entire grid is filled with output[r][c] = color[(r+c)%3].
    """
    rows, cols = len(grid), len(grid[0])
    diag_colors = {}
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background:
                diag_colors[(r + c) % 3] = grid[r][c]
    if len(diag_colors) < 3:
        return grid
    out = []
    for r in range(rows):
        row = [diag_colors.get((r + c) % 3, background) for c in range(cols)]
        out.append(row)
    return out

def recolor_non_singletons(grid, target_color=8, background=0):
    """
    Find all connected components of non-background cells.
    Components with size > 1 are recolored to target_color.
    Singleton components (size == 1) stay as their original color.
    """
    from collections import deque
    rows, cols = len(grid), len(grid[0])
    visited = [[False] * cols for _ in range(rows)]
    components = []
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background and not visited[r][c]:
                comp = []
                q = deque([(r, c)])
                visited[r][c] = True
                while q:
                    rr, cc = q.popleft()
                    comp.append((rr, cc))
                    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nr, nc = rr + dr, cc + dc
                        if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc] and grid[nr][nc] != background:
                            visited[nr][nc] = True
                            q.append((nr, nc))
                components.append(comp)
    out = [row[:] for row in grid]
    for comp in components:
        if len(comp) > 1:
            for r, c in comp:
                out[r][c] = target_color
    return out

def draw_x_from_zero(grid, background=0):
    """
    Find the single background cell (the '0 pixel') and draw both diagonals
    through it using background color, while keeping the rest as-is.
    Creates an X pattern centered at the zero cell.
    """
    rows, cols = len(grid), len(grid[0])
    r0, c0 = None, None
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == background:
                r0, c0 = r, c
                break
        if r0 is not None:
            break
    if r0 is None:
        return grid
    out = [row[:] for row in grid]
    for r in range(rows):
        for c in range(cols):
            if abs(r - r0) == abs(c - c0):
                out[r][c] = background
    return out

def nor_halves_by_separator(grid, separator=1, result_color=3, background=0):
    """
    Find the separator column (all values == separator).
    Output cell = result_color where BOTH left and right halves are background;
    otherwise background. (Inverse of and_halves_by_separator.)
    """
    rows, cols = len(grid), len(grid[0])
    sep_col = next((c for c in range(cols) if all(grid[r][c] == separator for r in range(rows))), None)
    if sep_col is None:
        return grid
    left = [row[:sep_col] for row in grid]
    right = [row[sep_col + 1:] for row in grid]
    w = min(len(left[0]), len(right[0]))
    out = []
    for r in range(rows):
        row = [result_color if left[r][c] == background and right[r][c] == background else background for c in range(w)]
        out.append(row)
    return out

def tile_with_mirror_h(grid):
    """
    Append the horizontal mirror of each row to itself.
    Result is same height, double width: [row | reverse(row)].
    """
    return [list(row) + list(row)[::-1] for row in grid]

def count_cells_to_row(grid, background=0):
    """
    Count non-background cells. Output a single row of that count,
    filled with the dominant non-background color.
    """
    colors = [v for row in grid for v in row if v != background]
    if not colors:
        return [[]]
    color = max(set(colors), key=colors.count)
    return [[color] * len(colors)]

def mark_singleton_cells(grid, target_color=1, background=0):
    """
    Find connected components of the dominant non-background color.
    Replace singleton components (size == 1) with target_color.
    Multi-cell components are unchanged.
    """
    from collections import deque
    rows, cols = len(grid), len(grid[0])
    cc = {}
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background:
                cc[grid[r][c]] = cc.get(grid[r][c], 0) + 1
    if not cc:
        return grid
    source_color = max(cc, key=lambda x: cc[x])
    visited = [[False] * cols for _ in range(rows)]
    components = []
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == source_color and not visited[r][c]:
                comp = []
                q = deque([(r, c)])
                visited[r][c] = True
                while q:
                    rr, cc2 = q.popleft()
                    comp.append((rr, cc2))
                    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nr, nc = rr + dr, cc2 + dc
                        if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc] and grid[nr][nc] == source_color:
                            visited[nr][nc] = True
                            q.append((nr, nc))
                components.append(comp)
    out = [row[:] for row in grid]
    for comp in components:
        if len(comp) == 1:
            r, c = comp[0]
            out[r][c] = target_color
    return out

def find_minimal_tile(grid):
    """
    Given a grid that is a repeating tile, extract the smallest repeating tile.
    Tries row periods first (smallest), then column periods within each row period.
    """
    rows = len(grid)
    cols = len(grid[0]) if grid else 0
    for rp in range(1, rows + 1):
        if rows % rp == 0:
            tile = grid[:rp]
            if all(grid[r][c] == tile[r % rp][c] for r in range(rows) for c in range(cols)):
                for cp in range(1, cols + 1):
                    if cols % cp == 0:
                        mini = [row[:cp] for row in tile]
                        if all(tile[r][c] == mini[r][c % cp] for r in range(rp) for c in range(cols)):
                            return mini
    return grid

def fill_with_most_common(grid):
    """Fill the entire grid with the single most frequent color value."""
    from collections import Counter
    counts = Counter(v for row in grid for v in row)
    if not counts:
        return grid
    most_common = counts.most_common(1)[0][0]
    return [[most_common] * len(grid[0]) for _ in range(len(grid))]

def stack_mirror_v(grid):
    """
    Stack mirror_v(grid) on top of grid: output = grid[::-1] + grid.
    Doubles the number of rows, produces vertical palindrome.
    """
    return list(grid[::-1]) + list(grid)

def extract_rarest_color_rect(grid, background=0):
    """
    Find the non-background color with the fewest cells.
    Return a solid rectangle of that color with the same bounding box dimensions.
    """
    from collections import Counter
    counts = Counter(v for row in grid for v in row if v != background)
    if not counts:
        return grid
    min_color = min(counts, key=lambda c: counts[c])
    rows, cols = len(grid), len(grid[0])
    positions = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] == min_color]
    if not positions:
        return grid
    r_min = min(r for r, c in positions)
    r_max = max(r for r, c in positions)
    c_min = min(c for r, c in positions)
    c_max = max(c for r, c in positions)
    h = r_max - r_min + 1
    w = c_max - c_min + 1
    return [[min_color] * w for _ in range(h)]

def count_2x2_blocks_to_row(grid, target_color=1, output_len=5, marker=1, background=0):
    """
    Count 2x2 blocks of target_color in the grid.
    Return a 1xoutput_len row with count many markers followed by background.
    """
    rows, cols = len(grid), len(grid[0])
    count = 0
    for r in range(rows - 1):
        for c in range(cols - 1):
            if (grid[r][c] == target_color and grid[r][c+1] == target_color and
                    grid[r+1][c] == target_color and grid[r+1][c+1] == target_color):
                count += 1
    count = min(count, output_len)
    return [[marker] * count + [background] * (output_len - count)]

def classify_cell_count(grid, background=0, low_color=7, high_color=1, low_range=(3, 4)):
    """
    Count non-background cells. If count is in low_range (3 or 4), return [[low_color]],
    otherwise return [[high_color]]. Used for 3x3 pattern classification.
    """
    count = sum(v != background for row in grid for v in row)
    if count in low_range:
        return [[low_color]]
    return [[high_color]]

def draw_two_color_cross(grid, intersection_color=2, background=0):
    """
    Find exactly two non-background cells: (r1,c1)=v1 and (r2,c2)=v2.
    Fill row r1 and col c1 with v1, fill row r2 and col c2 with v2.
    Set intersections (r1,c2) and (r2,c1) to intersection_color.
    """
    rows, cols = len(grid), len(grid[0])
    cells = [(r, c, grid[r][c]) for r in range(rows) for c in range(cols) if grid[r][c] != background]
    if len(cells) != 2:
        return grid
    (r1, c1, v1), (r2, c2, v2) = cells
    out = [[background] * cols for _ in range(rows)]
    for c in range(cols):
        out[r1][c] = v1
    for r in range(rows):
        out[r][c1] = v1
    for c in range(cols):
        out[r2][c] = v2
    for r in range(rows):
        out[r][c2] = v2
    out[r1][c2] = intersection_color
    out[r2][c1] = intersection_color
    return out

def replace_markers_with_nearest_frame(grid, background=0):
    """
    Find frame rows/cols (entirely one non-background color).
    Replace each non-frame non-background cell (marker) with the color of the
    nearest frame row or column by Manhattan distance.
    """
    rows, cols = len(grid), len(grid[0])
    frame_rows = {}
    for r in range(rows):
        vals = set(grid[r])
        if len(vals) == 1 and list(vals)[0] != background:
            frame_rows[r] = list(vals)[0]
    frame_cols = {}
    for c in range(cols):
        vals = set(grid[r][c] for r in range(rows))
        if len(vals) == 1 and list(vals)[0] != background:
            frame_cols[c] = list(vals)[0]
    frame_colors = set(frame_rows.values()) | set(frame_cols.values())
    if not frame_colors:
        return grid
    out = [row[:] for row in grid]
    for r in range(rows):
        if r in frame_rows:
            continue
        for c in range(cols):
            if c in frame_cols:
                continue
            v = grid[r][c]
            if v == background or v in frame_colors:
                continue
            best_dist = float('inf')
            best_color = v
            for fr, fc in frame_rows.items():
                d = abs(r - fr)
                if d < best_dist:
                    best_dist = d
                    best_color = fc
            for fc_idx, fc in frame_cols.items():
                d = abs(c - fc_idx)
                if d < best_dist:
                    best_dist = d
                    best_color = fc
            out[r][c] = best_color
    return out

def fill_matching_edge_rows(grid, background=0):
    """
    For each row where first and last elements are the same non-background color,
    fill the entire row with that color. Other rows are unchanged.
    """
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(rows):
        first, last = grid[r][0], grid[r][-1]
        if first != background and first == last:
            out[r] = [first] * cols
    return out

def fill_between_same_color_rows(grid, background=0):
    """
    For each row, find the leftmost and rightmost occurrence of each non-background color.
    Fill all cells between them (inclusive) with that color.
    """
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(rows):
        row = grid[r]
        colors = {}
        for c, v in enumerate(row):
            if v != background:
                if v not in colors:
                    colors[v] = [c, c]
                else:
                    colors[v][1] = c
        for v, (c0, c1) in colors.items():
            if c1 > c0:
                for c in range(c0, c1 + 1):
                    out[r][c] = v
    return out

def project_template_to_singletons(grid, marker=5, fill=2, background=0):
    """
    Find the row with the most marker cells (template row).
    For each row with exactly one marker cell, overlay template positions with fill,
    keeping the single marker cell in place.
    """
    rows, cols = len(grid), len(grid[0])
    marker_counts = [sum(1 for v in grid[r] if v == marker) for r in range(rows)]
    template_row = max(range(rows), key=lambda r: marker_counts[r])
    if marker_counts[template_row] <= 1:
        return grid
    template_cols = [c for c in range(cols) if grid[template_row][c] == marker]
    out = [row[:] for row in grid]
    for r in range(rows):
        if r == template_row:
            continue
        if marker_counts[r] == 1:
            singleton_col = next(c for c in range(cols) if grid[r][c] == marker)
            for c in template_cols:
                out[r][c] = fill
            out[r][singleton_col] = marker
    return out

def rank_columns_by_height(grid, marker=5, background=0):
    """
    Find all columns that consist of marker cells. Count their heights.
    Rank them 1=tallest, 2=second, etc. Replace marker cells in each column with their rank.
    """
    rows, cols = len(grid), len(grid[0])
    col_heights = {}
    for c in range(cols):
        h = sum(1 for r in range(rows) if grid[r][c] == marker)
        if h > 0:
            col_heights[c] = h
    if not col_heights:
        return grid
    sorted_cols = sorted(col_heights.keys(), key=lambda c: (-col_heights[c], c))
    rank_map = {c: rank + 1 for rank, c in enumerate(sorted_cols)}
    out = [row[:] for row in grid]
    for c, rank in rank_map.items():
        for r in range(rows):
            if out[r][c] == marker:
                out[r][c] = rank
    return out

def fill_rows_col_by_value(grid, col_marker=2, background=0):
    """
    Each non-background cell at (r,c) with value v:
    - If v == col_marker: fill entire column c with v (first pass)
    - Otherwise: fill entire row r with v (second pass, overwrites col fills)
    """
    rows, cols_n = len(grid), len(grid[0])
    out = [[background] * cols_n for _ in range(rows)]
    # First pass: column fills for col_marker
    for r in range(rows):
        for c in range(cols_n):
            if grid[r][c] == col_marker:
                for rr in range(rows):
                    out[rr][c] = col_marker
    # Second pass: row fills for all other non-background colors (overwrites)
    for r in range(rows):
        for c in range(cols_n):
            v = grid[r][c]
            if v != background and v != col_marker:
                for cc in range(cols_n):
                    out[r][cc] = v
    return out

def grid_separator_count(grid, background=0):
    """Minority color forms a grid of separator lines. Count row/col spans and return H×W solid rect of majority color."""
    from collections import Counter
    rows, cols = len(grid), len(grid[0])
    counts = Counter(v for row in grid for v in row)
    if len(counts) != 2:
        return grid
    minority = min(counts, key=lambda c: counts[c])
    majority = max(counts, key=lambda c: counts[c])
    sep_rows = [r for r in range(rows) if all(grid[r][c] == minority for c in range(cols))]
    sep_cols = [c for c in range(cols) if all(grid[r][c] == minority for r in range(rows))]
    def count_spans(n, seps):
        spans, prev = 0, -1
        for s in sorted(seps) + [n]:
            if s > prev + 1: spans += 1
            prev = s
        return spans
    H = count_spans(rows, sep_rows)
    W = count_spans(cols, sep_cols)
    return [[majority] * W for _ in range(H)]

def xor_split_halves(grid, separator=4, marker=2, output_val=3, background=0):
    """Find separator row (all same value). XOR top/bottom halves: where exactly one half has marker, output output_val."""
    rows, cols = len(grid), len(grid[0])
    sep_row = next((r for r in range(rows) if all(grid[r][c] == separator for c in range(cols))), None)
    if sep_row is None:
        return grid
    top, bottom = grid[:sep_row], grid[sep_row+1:]
    if len(top) != len(bottom):
        return grid
    return [[output_val if (top[i][c] == marker) ^ (bottom[i][c] == marker) else background for c in range(cols)] for i in range(len(top))]

def falling_diagonals(grid, background=0):
    """1-row input. Non-zero values at positions p fall diagonally in (N*W)x(N*W) output."""
    if len(grid) != 1: return grid
    row = grid[0]
    W = len(row)
    non_zero = [(p, v) for p, v in enumerate(row) if v != background]
    N = len(non_zero)
    if N == 0: return grid
    H = N * W
    out = [[background] * H for _ in range(H)]
    for p, v in non_zero:
        for r in range(p, H):
            c = (H - 1) - (r - p)
            if 0 <= c < H:
                out[r][c] = v
    return out

def self_tile(grid, background=0):
    """Each non-bg cell → full grid copy. Each bg cell → bg block. Output = (H*H)x(W*W)."""
    rows, cols = len(grid), len(grid[0])
    out = [[background] * (cols * cols) for _ in range(rows * rows)]
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background:
                for dr in range(rows):
                    for dc in range(cols):
                        out[r*rows + dr][c*cols + dc] = grid[dr][dc]
    return out

def pad_and_double_edges(grid, background=0):
    """Output (M+2)x(N+2). First/last rows: padded with 0. Interior rows: first/last cols doubled."""
    rows, cols = len(grid), len(grid[0])
    out = [[background] + list(grid[0]) + [background]]
    for r in range(rows):
        if cols == 1:
            out.append([grid[r][0], grid[r][0]])
        else:
            out.append([grid[r][0], grid[r][0]] + list(grid[r][1:-1]) + [grid[r][-1], grid[r][-1]])
    out.append([background] + list(grid[-1]) + [background])
    return out

def color_count_to_diagonal(grid, fill_color=5, background=0):
    """Count distinct colors. 1 color→top row fill, 2 colors→main diagonal, 3+→anti-diagonal."""
    rows, cols = len(grid), len(grid[0])
    num_colors = len(set(v for row in grid for v in row))
    out = [[background]*cols for _ in range(rows)]
    if num_colors == 1:
        for c in range(cols): out[0][c] = fill_color
    elif num_colors == 2:
        for i in range(min(rows, cols)): out[i][i] = fill_color
    else:
        for i in range(min(rows, cols)): out[i][cols-1-i] = fill_color
    return out

def tile_mirror_row_rev_3x(grid):
    """block=[rev(r)+r for r in reversed(grid)]. Output=block+rev(block)+block."""
    block = [list(r[::-1]) + list(r) for r in reversed(grid)]
    return list(block) + list(reversed(block)) + list(block)

def stack_grid_then_mirror_v(grid):
    """Stack grid then its vertical flip: output = grid + grid[::-1]. Doubles rows."""
    return list(grid) + list(grid[::-1])

def draw_border_frame(grid, border_color=8, background=0):
    """Fill all border cells (first/last row, first/last col) with border_color. Interior stays as background."""
    rows, cols = len(grid), len(grid[0])
    out = [[background]*cols for _ in range(rows)]
    for c in range(cols): out[0][c] = border_color; out[rows-1][c] = border_color
    for r in range(rows): out[r][0] = border_color; out[r][cols-1] = border_color
    return out

def dedup_rows_cols(grid, background=0):
    """Remove duplicate adjacent rows, then duplicate adjacent columns."""
    deduped = [grid[0]] if grid else []
    for r in range(1, len(grid)):
        if grid[r] != grid[r-1]:
            deduped.append(grid[r])
    if not deduped: return deduped
    cols = len(deduped[0])
    keep = [0] + [c for c in range(1, cols) if any(deduped[r][c] != deduped[r][c-1] for r in range(len(deduped)))]
    return [[row[c] for c in keep] for row in deduped]

def staircase_grow(grid, background=0):
    """1-row input with K non-zero cells at left. Create cols//2 rows, each adding one more non-zero cell."""
    if len(grid) != 1: return grid
    row = grid[0]
    cols = len(row)
    nz_color = next((v for v in row if v != background), None)
    if nz_color is None: return grid
    nz_count = sum(1 for v in row if v != background)
    H = cols // 2
    return [[nz_color] * min(nz_count + i, cols) + [background] * max(0, cols - nz_count - i) for i in range(H)]

def mark_l_shape_inner_corner(grid, shape_color=8, mark_color=1, background=0):
    """Find 3-cell L-shapes of shape_color (within 2x2 bbox). Mark the 4th corner of bbox with mark_color."""
    rows, cols = len(grid), len(grid[0])
    visited = [[False]*cols for _ in range(rows)]
    out = [row[:] for row in grid]
    def bfs(sr, sc):
        component, queue = [], [(sr, sc)]
        visited[sr][sc] = True
        while queue:
            r, c = queue.pop()
            component.append((r, c))
            for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                nr, nc = r+dr, c+dc
                if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc] and grid[nr][nc] == shape_color:
                    visited[nr][nc] = True
                    queue.append((nr, nc))
        return component
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == shape_color and not visited[r][c]:
                comp = bfs(r, c)
                if len(comp) == 3:
                    r_min, r_max = min(x[0] for x in comp), max(x[0] for x in comp)
                    c_min, c_max = min(x[1] for x in comp), max(x[1] for x in comp)
                    if r_max - r_min == 1 and c_max - c_min == 1:
                        comp_set = set(comp)
                        for cr in [r_min, r_max]:
                            for cc in [c_min, c_max]:
                                if (cr, cc) not in comp_set:
                                    out[cr][cc] = mark_color
    return out

def connect_markers_to_feature(grid, background=None):
    """Find largest rectangular feature block. Connect aligned singleton markers to it with straight lines."""
    from collections import Counter
    rows, cols = len(grid), len(grid[0])
    if background is None:
        counts = Counter(v for row in grid for v in row)
        background = counts.most_common(1)[0][0]
    visited = [[False]*cols for _ in range(rows)]
    def bfs(sr, sc):
        comp, queue = [], [(sr, sc)]
        visited[sr][sc] = True
        color = grid[sr][sc]
        while queue:
            r, c = queue.pop()
            comp.append((r, c))
            for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                nr, nc = r+dr, c+dc
                if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc] and grid[nr][nc] == color:
                    visited[nr][nc] = True
                    queue.append((nr, nc))
        return comp, color
    components = []
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background and not visited[r][c]:
                comp, color = bfs(r, c)
                components.append((comp, color))
    if not components:
        return grid
    feature_comp, feature_color = max(components, key=lambda x: len(x[0]))
    f_rmin = min(r for r, c in feature_comp)
    f_rmax = max(r for r, c in feature_comp)
    f_cmin = min(c for r, c in feature_comp)
    f_cmax = max(c for r, c in feature_comp)
    markers = [(comp[0], color) for comp, color in components if len(comp) == 1 and color != feature_color]
    out = [row[:] for row in grid]
    for (mr, mc), mcolor in markers:
        if f_cmin <= mc <= f_cmax:
            if mr < f_rmin:
                for r in range(mr+1, f_rmin):
                    if out[r][mc] == background: out[r][mc] = mcolor
            elif mr > f_rmax:
                for r in range(f_rmax+1, mr):
                    if out[r][mc] == background: out[r][mc] = mcolor
        elif f_rmin <= mr <= f_rmax:
            if mc < f_cmin:
                for c in range(mc+1, f_cmin):
                    if out[mr][c] == background: out[mr][c] = mcolor
            elif mc > f_cmax:
                for c in range(f_cmax+1, mc):
                    if out[mr][c] == background: out[mr][c] = mcolor
    return out

def fill_clear_corridors(grid, fill_color=3, background=0):
    """Find rows/cols entirely background in interior (excluding outer border row/col). Fill with fill_color."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(1, rows - 1):
        if all(grid[r][c] == background for c in range(1, cols - 1)):
            for c in range(1, cols - 1):
                out[r][c] = fill_color
    for c in range(1, cols - 1):
        if all(grid[r][c] == background for r in range(1, rows - 1)):
            for r in range(1, rows - 1):
                out[r][c] = fill_color
    return out

def add_full_halo(grid, target_color=5, halo_color=1, background=0):
    """Add all 8 neighbors (3x3 ring) colored with halo_color around each target_color cell."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == target_color:
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == background:
                            out[nr][nc] = halo_color
    return out

def add_halo_cross_diag(grid, cross_color=1, cross_halo=7, diag_color=2, diag_halo=4, background=0):
    """Color cross_color: fill orthogonal neighbors with cross_halo. Color diag_color: fill diagonal neighbors with diag_halo."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            if v == cross_color:
                for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nr, nc = r+dr, c+dc
                    if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == background:
                        out[nr][nc] = cross_halo
            elif v == diag_color:
                for dr, dc in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                    nr, nc = r+dr, c+dc
                    if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == background:
                        out[nr][nc] = diag_halo
    return out

def draw_two_cell_frame_cross(grid, background=0):
    """Two non-bg cells (r1,c1,v1),(r2,c2,v2) with r1<r2. Fill row r1 with v1, row r2 with v2.
    Top/bottom border rows: v1/v2. Side borders: v1 for rows ≤ midpoint(r1,r2), v2 above."""
    rows, cols = len(grid), len(grid[0])
    cells = sorted([(r, c, grid[r][c]) for r in range(rows) for c in range(cols) if grid[r][c] != background], key=lambda x: x[0])
    if len(cells) != 2:
        return grid
    (r1, c1, v1), (r2, c2, v2) = cells
    mid = (r1 + r2) / 2.0
    out = [row[:] for row in grid]
    for c in range(cols): out[r1][c] = v1
    for c in range(cols): out[r2][c] = v2
    for c in range(cols): out[0][c] = v1
    for c in range(cols): out[rows-1][c] = v2
    for r in range(rows):
        if r in (r1, r2, 0, rows-1): continue
        color = v1 if r <= mid else v2
        out[r][0] = color
        out[r][cols-1] = color
    return out

def check_180_symmetry(grid, true_val=1, false_val=7):
    """If grid == rotate_180(grid), return [[true_val]], else [[false_val]]."""
    rot = [row[::-1] for row in grid[::-1]]
    if rot == [list(row) for row in grid]:
        return [[true_val]]
    return [[false_val]]

def extract_unique_quadrant(grid):
    """Find separator cross (full row + col of same color). Extract quadrant with non-majority cell."""
    from collections import Counter
    rows, cols = len(grid), len(grid[0])
    sep_row = next((r for r in range(rows) if len(set(grid[r])) == 1), None)
    if sep_row is None: return grid
    sep_color = grid[sep_row][0]
    sep_col = next((c for c in range(cols) if all(grid[r][c] == sep_color for r in range(rows))), None)
    if sep_col is None: return grid
    quads = [
        (list(range(0, sep_row)), list(range(0, sep_col))),
        (list(range(0, sep_row)), list(range(sep_col+1, cols))),
        (list(range(sep_row+1, rows)), list(range(0, sep_col))),
        (list(range(sep_row+1, rows)), list(range(sep_col+1, cols))),
    ]
    for r_list, c_list in quads:
        if not r_list or not c_list: continue
        cells = [grid[r][c] for r in r_list for c in c_list]
        counts = Counter(cells)
        most_common = counts.most_common(1)[0][0]
        if any(v != most_common for v in cells):
            return [[grid[r][c] for c in c_list] for r in r_list]
    return [[grid[r][c] for c in quads[0][1]] for r in quads[0][0]]

def bounce_tile_rows(grid):
    """Output grid + reversed(grid[1:-1]) + grid + reversed(grid[1:-1]) + [grid[0]]. Rows = 4*(H-1)+1."""
    rows = len(grid)
    if rows <= 1: return grid
    bounce = list(grid) + [list(r) for r in reversed(grid[1:-1])]
    return bounce + bounce + [list(grid[0])]

def fill_sections_with_rotations(grid, sep=5):
    """Split grid by separator columns (all same sep value). Fill sections with 0,90,180,270 rotations of section0."""
    rows, cols = len(grid), len(grid[0])
    sep_cols = [c for c in range(cols) if all(grid[r][c] == sep for r in range(rows))]
    boundaries = [-1] + sep_cols + [cols]
    sections = []
    for i in range(len(boundaries) - 1):
        start, end = boundaries[i] + 1, boundaries[i + 1]
        if end > start:
            sections.append((start, [[grid[r][c] for c in range(start, end)] for r in range(rows)]))
    if not sections: return grid
    src = sections[0][1]
    rot90cw = [list(row) for row in zip(*src[::-1])]
    rot180 = [row[::-1] for row in src[::-1]]
    rot270 = [list(row) for row in zip(*src)][::-1]
    rots = [src, rot90cw, rot180, rot270]
    out = [row[:] for row in grid]
    for idx, (start, _) in enumerate(sections):
        rot = rots[idx % 4]
        for r in range(rows):
            if r < len(rot):
                for c_off, val in enumerate(rot[r]):
                    out[r][start + c_off] = val
    return out

def rotate_four_quadrants(grid):
    """Output 2Hx2W: TL=grid, TR=rot90cw(grid), BL=rot90ccw(grid), BR=rot180(grid)."""
    rot90cw = [list(row) for row in zip(*grid[::-1])]
    rot90ccw = [list(row) for row in zip(*grid)][::-1]
    rot180 = [row[::-1] for row in grid[::-1]]
    out = []
    for r in range(len(grid)):
        out.append(list(grid[r]) + rot90cw[r])
    for r in range(len(grid)):
        out.append(rot90ccw[r] + rot180[r])
    return out

def two_block_diagonal_scale(grid, marker=2, block_color=3, background=0):
    """L-shape (block_color cells) + 1 marker = N cells in input. Output = (rows^2)x(cols^2).
    Two NxN blocks placed: main diagonal (TL/BR L orientation) or anti-diagonal (TR/BL)."""
    rows, cols = len(grid), len(grid[0])
    H, W = rows * rows, cols * cols
    marker_pos = next(((r, c) for r in range(rows) for c in range(cols) if grid[r][c] == marker), None)
    block_cells = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] == block_color]
    if marker_pos is None or not block_cells:
        return grid
    all_cells = [marker_pos] + block_cells
    block_size = len(all_cells)
    r_min = min(r for r, c in all_cells)
    c_min = min(c for r, c in all_cells)
    mr, mc = marker_pos
    l_r_mean = sum(r for r, c in block_cells) / len(block_cells)
    l_c_mean = sum(c for r, c in block_cells) / len(block_cells)
    is_anti = ((l_r_mean < mr and l_c_mean > mc) or (l_r_mean > mr and l_c_mean < mc))
    out = [[background] * W for _ in range(H)]
    r1, c1 = r_min, (W - block_size) if is_anti else c_min
    r2 = r1 + block_size
    c2 = c_min if is_anti else c1 + block_size
    for dr in range(block_size):
        for dc in range(block_size):
            if 0 <= r1+dr < H and 0 <= c1+dc < W:
                out[r1+dr][c1+dc] = block_color
            if 0 <= r2+dr < H and 0 <= c2+dc < W:
                out[r2+dr][c2+dc] = block_color
    return out

def project_markers_onto_block_face(grid, block_color=5, background=0):
    """Find horizontal (all-5 rows) or vertical (all-5 cols) block. Count non-background,
    non-block markers above/below/left/right. Extend block face by count cells per position."""
    rows, cols = len(grid), len(grid[0])
    out = [[background] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == block_color:
                out[r][c] = block_color
    h_block_rows = [r for r in range(rows) if all(grid[r][c] == block_color for c in range(cols))]
    v_block_cols = [c for c in range(cols) if all(grid[r][c] == block_color for r in range(rows))]
    if h_block_rows:
        top = min(h_block_rows)
        bot = max(h_block_rows)
        above_by_col, below_by_col = {}, {}
        for r in range(rows):
            for c in range(cols):
                if grid[r][c] not in (block_color, background):
                    if r < top:
                        above_by_col[c] = above_by_col.get(c, 0) + 1
                    elif r > bot:
                        below_by_col[c] = below_by_col.get(c, 0) + 1
        if top > 0:
            for c, cnt in above_by_col.items():
                for i in range(cnt):
                    if 0 <= top - 1 - i < rows:
                        out[top - 1 - i][c] = block_color
        if bot < rows - 1:
            for c, cnt in below_by_col.items():
                for i in range(cnt):
                    if 0 <= bot + 1 + i < rows:
                        out[bot + 1 + i][c] = block_color
    elif v_block_cols:
        left = min(v_block_cols)
        right = max(v_block_cols)
        left_by_row, right_by_row = {}, {}
        for r in range(rows):
            for c in range(cols):
                if grid[r][c] not in (block_color, background):
                    if c < left:
                        left_by_row[r] = left_by_row.get(r, 0) + 1
                    elif c > right:
                        right_by_row[r] = right_by_row.get(r, 0) + 1
        if left > 0:
            for r, cnt in left_by_row.items():
                for i in range(cnt):
                    if 0 <= left - 1 - i < cols:
                        out[r][left - 1 - i] = block_color
        if right < cols - 1:
            for r, cnt in right_by_row.items():
                for i in range(cnt):
                    if 0 <= right + 1 + i < cols:
                        out[r][right + 1 + i] = block_color
    return out

def alternate_middle_rows_of_triples(grid, background=0):
    """Find groups of exactly 3 identical consecutive rows. In the middle row of each group,
    for each run of non-background cells, keep even-indexed cells, zero out odd-indexed."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    r = 0
    while r < rows:
        if r + 2 < rows and grid[r] == grid[r+1] == grid[r+2]:
            end = r + 2
            while end + 1 < rows and grid[end+1] == grid[r]:
                end += 1
            group_len = end - r + 1
            if group_len == 3:
                mid = r + 1
                c = 0
                while c < cols:
                    if out[mid][c] == background:
                        c += 1
                        continue
                    run_start = c
                    color = out[mid][c]
                    while c < cols and grid[mid][c] == color:
                        c += 1
                    for i in range(1, c - run_start, 2):
                        out[mid][run_start + i] = background
            r = end + 1
        else:
            r += 1
    return out

def extract_inner_shape(grid, background=0):
    """Find 4 corner markers (same color) defining a rectangle frame. Output the frame interior
    with any non-background non-frame cells recolored to frame color."""
    from collections import defaultdict
    rows, cols = len(grid), len(grid[0])
    color_positions = defaultdict(list)
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background:
                color_positions[grid[r][c]].append((r, c))
    frame_color = None
    frame_rect = None
    for color, positions in color_positions.items():
        if len(positions) < 4:
            continue
        rows_set = sorted(set(r for r, c in positions))
        cols_set = sorted(set(c for r, c in positions))
        if len(rows_set) == 2 and len(cols_set) == 2:
            r1, r2 = rows_set[0], rows_set[1]
            c1, c2 = cols_set[0], cols_set[1]
            corners = {(r1, c1), (r1, c2), (r2, c1), (r2, c2)}
            if all(p in corners for p in positions) and len(positions) == 4:
                frame_color = color
                frame_rect = (r1, c1, r2, c2)
                break
    if frame_rect is None:
        return grid
    r1, c1, r2, c2 = frame_rect
    h, w = r2 - r1 - 1, c2 - c1 - 1
    if h <= 0 or w <= 0:
        return grid
    out = []
    for r in range(r1 + 1, r2):
        row = []
        for c in range(c1 + 1, c2):
            if grid[r][c] != background and grid[r][c] != frame_color:
                row.append(frame_color)
            else:
                row.append(background)
        out.append(row)
    return out

def complete_4fold_rot_symmetry(grid, background=0):
    """Find bounding box of non-background cells, treat its center as rotation center.
    For each non-background cell, add 90°/180°/270° rotated copies if missing."""
    rows, cols = len(grid), len(grid[0])
    cells = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] != background]
    if not cells:
        return [row[:] for row in grid]
    r_min = min(r for r, c in cells)
    r_max = max(r for r, c in cells)
    c_min = min(c for r, c in cells)
    c_max = max(c for r, c in cells)
    cr = (r_min + r_max) / 2.0
    cc = (c_min + c_max) / 2.0
    out = [row[:] for row in grid]
    for r, c in cells:
        val = grid[r][c]
        dr, dc = r - cr, c - cc
        for _ in range(3):
            dr, dc = dc, -dr  # 90° CW rotation
            nr, nc = cr + dr, cc + dc
            if nr == round(nr) and nc == round(nc):
                ri, ci = int(round(nr)), int(round(nc))
                if 0 <= ri < rows and 0 <= ci < cols and out[ri][ci] == background:
                    out[ri][ci] = val
    return out

def color_template_quadrant(grid, sep_color=8, template_color=3, background=0):
    """Separator cross divides grid into 4 quadrants. One small quadrant = color map (NxM).
    One large quadrant = template with template_color cells. Output = template with each
    template_color cell replaced by the color from the map: map[row//block_h][col//block_w]."""
    rows, cols = len(grid), len(grid[0])
    sep_row = next((r for r in range(rows) if all(grid[r][c] == sep_color for c in range(cols))), None)
    sep_col = next((c for c in range(cols) if all(grid[r][c] == sep_color for r in range(rows))), None)
    if sep_row is None or sep_col is None:
        return grid
    quad_ranges = [
        (range(0, sep_row), range(0, sep_col)),
        (range(0, sep_row), range(sep_col + 1, cols)),
        (range(sep_row + 1, rows), range(0, sep_col)),
        (range(sep_row + 1, rows), range(sep_col + 1, cols)),
    ]
    color_map = None
    template = None
    for r_range, c_range in quad_ranges:
        if not r_range or not c_range:
            continue
        q = [[grid[r][c] for c in c_range] for r in r_range]
        has_template = any(grid[r][c] == template_color for r in r_range for c in c_range)
        has_non_bg = any(grid[r][c] not in (background, sep_color, template_color) for r in r_range for c in c_range)
        if has_non_bg and not has_template:
            color_map = q
        elif has_template and not has_non_bg:
            template = q
    if color_map is None or template is None:
        return grid
    cmap_rows = len(color_map)
    cmap_cols = len(color_map[0])
    tmpl_rows = len(template)
    tmpl_cols = len(template[0])
    block_h = tmpl_rows // cmap_rows
    block_w = tmpl_cols // cmap_cols
    if block_h == 0 or block_w == 0:
        return grid
    out = [[background] * tmpl_cols for _ in range(tmpl_rows)]
    for r in range(tmpl_rows):
        for c in range(tmpl_cols):
            if template[r][c] == template_color:
                mr = min(r // block_h, cmap_rows - 1)
                mc = min(c // block_w, cmap_cols - 1)
                out[r][c] = color_map[mr][mc]
    return out

def expand_cross_pattern(grid, center_color=None, arm_color=None, background=0):
    """For each center_color cell forming a + cross with arm_color:
    extend arms by 1 step, add center_color at inner diagonals (dist 1) and outer corners (dist 2).
    If center_color/arm_color are None, auto-detect from cross structures."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    # Auto-detect center/arm colors by finding cells with 4 orthogonal same-colored neighbors
    pairs_to_try = []
    if center_color is not None and arm_color is not None:
        pairs_to_try = [(center_color, arm_color)]
    else:
        # Detect: find cells where 4 orthogonal neighbors form a cross of 1 color
        seen = set()
        for r in range(1, rows-1):
            for c in range(1, cols-1):
                cc = grid[r][c]
                if cc == background: continue
                arms = [(r-1,c),(r+1,c),(r,c-1),(r,c+1)]
                arm_colors = [grid[nr][nc] for nr,nc in arms if 0<=nr<rows and 0<=nc<cols]
                # All 4 arms same color (not background, not center)
                arm_color_candidates = [a for a in arm_colors if a != background and a != cc]
                if len(arm_color_candidates) == 4 and len(set(arm_color_candidates)) == 1:
                    pair = (cc, arm_color_candidates[0])
                    if pair not in seen:
                        seen.add(pair)
                        pairs_to_try.append(pair)
        if not pairs_to_try:
            return out
    for cc, ac in pairs_to_try:
        for r in range(rows):
            for c in range(cols):
                if grid[r][c] != cc:
                    continue
                arms = [(r-1,c),(r+1,c),(r,c-1),(r,c+1)]
                arm_cells = [(nr,nc) for nr,nc in arms if 0<=nr<rows and 0<=nc<cols and grid[nr][nc]==ac]
                if len(arm_cells) < 2:
                    continue
                for nr, nc in arm_cells:
                    dr, dc = nr - r, nc - c
                    r2, c2 = nr + dr, nc + dc
                    if 0 <= r2 < rows and 0 <= c2 < cols and out[r2][c2] == background:
                        out[r2][c2] = ac
                for dr, dc in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                    nr, nc = r+dr, c+dc
                    if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == background:
                        out[nr][nc] = cc
                for dr, dc in [(-2,-2),(-2,2),(2,-2),(2,2)]:
                    nr, nc = r+dr, c+dc
                    if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == background:
                        out[nr][nc] = cc
    return out

def color_interior_by_corner_quadrants(grid, border_color=1, marker_color=8, background=0):
    """Find two horizontal 1-row borders and two vertical 1-col borders. The 4 corners of the outer grid
    give 4 colors. Extract the interior region (between borders). Color each marker_color cell in the interior
    based on which quadrant (top-left/right, bottom-left/right) it falls in using the corresponding corner color."""
    rows, cols = len(grid), len(grid[0])
    border_rows = [r for r in range(rows) if all(grid[r][c] == border_color for c in range(cols))]
    border_cols = [c for c in range(cols) if all(grid[r][c] == border_color for r in range(rows))]
    if len(border_rows) < 2 or len(border_cols) < 2:
        return [row[:] for row in grid]
    top_border = min(border_rows)
    bot_border = max(border_rows)
    left_border = min(border_cols)
    right_border = max(border_cols)
    interior_rows = range(top_border + 1, bot_border)
    interior_cols = range(left_border + 1, right_border)
    ih = len(interior_rows)
    iw = len(interior_cols)
    if ih <= 0 or iw <= 0:
        return [row[:] for row in grid]
    def find_corner_color(r_range, c_range):
        for r in r_range:
            for c in c_range:
                if grid[r][c] not in (border_color, background):
                    return grid[r][c]
        return background
    tl = find_corner_color(range(0, top_border), range(0, left_border))
    tr = find_corner_color(range(0, top_border), range(right_border+1, cols))
    bl = find_corner_color(range(bot_border+1, rows), range(0, left_border))
    br = find_corner_color(range(bot_border+1, rows), range(right_border+1, cols))
    mid_r = (ih - 1) / 2.0
    mid_c = (iw - 1) / 2.0
    out = []
    for ri, r in enumerate(interior_rows):
        row = []
        for ci, c in enumerate(interior_cols):
            if grid[r][c] == marker_color:
                color = (tl if ri <= mid_r else bl) if ci <= mid_c else (tr if ri <= mid_r else br)
                row.append(color)
            else:
                row.append(background)
        out.append(row)
    return out

def gravity_down(grid, background=0):
    """All non-background cells fall to the bottom of their column (gravity pulls down)."""
    rows, cols = len(grid), len(grid[0])
    out = [[background]*cols for _ in range(rows)]
    for c in range(cols):
        col_vals = [grid[r][c] for r in range(rows) if grid[r][c] != background]
        for i, v in enumerate(col_vals):
            out[rows - len(col_vals) + i][c] = v
    return out

def gravity_up(grid, background=0):
    """All non-background cells rise to the top of their column."""
    rows, cols = len(grid), len(grid[0])
    out = [[background]*cols for _ in range(rows)]
    for c in range(cols):
        col_vals = [grid[r][c] for r in range(rows) if grid[r][c] != background]
        for i, v in enumerate(col_vals):
            out[i][c] = v
    return out

def gravity_left(grid, background=0):
    """All non-background cells slide to the left of their row."""
    out = []
    for row in grid:
        vals = [v for v in row if v != background]
        out.append(vals + [background] * (len(row) - len(vals)))
    return out

def gravity_right(grid, background=0):
    """All non-background cells slide to the right of their row."""
    out = []
    for row in grid:
        vals = [v for v in row if v != background]
        out.append([background] * (len(row) - len(vals)) + vals)
    return out

def drop_to_floor(grid, floor_color=5, background=0):
    """
    Each non-background, non-floor_color cell falls to the last row at its column,
    replacing whatever floor cell was there. Other cells are set to background.
    (Used when the floor is a full row of floor_color and unique-colored cells drop down.)
    """
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for c in range(cols):
        for r in range(rows):
            if grid[r][c] != background and grid[r][c] != floor_color:
                out[r][c] = background
                out[rows - 1][c] = grid[r][c]
    return out

def tile_4way_symmetric(grid):
    """
    Create a 2x-size symmetric tile: [original | mirror_h] on top,
    [mirror_v | rotate_180] on bottom. Result is 2*rows x 2*cols.
    """
    mh = [row[::-1] for row in grid]
    mv = grid[::-1]
    r180 = [row[::-1] for row in grid[::-1]]
    out = []
    for r in range(len(grid)):
        out.append(list(grid[r]) + list(mh[r]))
    for r in range(len(grid)):
        out.append(list(mv[r]) + list(r180[r]))
    return out

def fill_columns_above_marker(grid, fill_color=4, background=0):
    """
    Find the single non-background marker cell at (r, c).
    Fill rows 0..r with fill_color at columns of same parity as c.
    Move marker to (r+1, c).
    """
    rows, cols = len(grid), len(grid[0])
    marker_r, marker_c, marker_v = None, None, None
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background:
                marker_r, marker_c, marker_v = r, c, grid[r][c]
                break
        if marker_r is not None:
            break
    if marker_r is None:
        return grid
    out = [row[:] for row in grid]
    parity = marker_c % 2
    for r in range(marker_r + 1):
        for c in range(cols):
            if c % 2 == parity:
                out[r][c] = fill_color
    if marker_r + 1 < rows:
        out[marker_r + 1][marker_c] = marker_v
    return out

def repair_periodic_pattern(grid, missing=0):
    """Fill in missing (value 0) cells by detecting the repeating tile period."""
    rows, cols = len(grid), len(grid[0])
    non_missing = [(r, c, grid[r][c]) for r in range(rows) for c in range(cols) if grid[r][c] != missing]
    if not non_missing:
        return [row[:] for row in grid]
    best_pr, best_pc, best_ref = None, None, {}
    for pr in range(1, min(rows, 16) + 1):
        for pc in range(1, min(cols, 16) + 1):
            ref = {}
            consistent = True
            for r, c, v in non_missing:
                key = (r % pr, c % pc)
                if key in ref and ref[key] != v:
                    consistent = False
                    break
                ref[key] = v
            if consistent and len(ref) == pr * pc:
                if best_pr is None or pr * pc < best_pr * best_pc:
                    best_pr, best_pc = pr, pc
                    best_ref = dict(ref)
    if best_pr is None:
        best_match_size = None
        for pr in range(1, min(rows, 16) + 1):
            for pc in range(1, min(cols, 16) + 1):
                ref = {}
                consistent = True
                for r, c, v in non_missing:
                    key = (r % pr, c % pc)
                    if key in ref and ref[key] != v:
                        consistent = False
                        break
                    ref[key] = v
                if consistent and (best_match_size is None or pr * pc < best_match_size):
                    best_match_size = pr * pc
                    best_pr, best_pc = pr, pc
                    best_ref = dict(ref)
    if best_pr is None:
        return [row[:] for row in grid]
    out = [row[:] for row in grid]
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == missing:
                key = (r % best_pr, c % best_pc)
                if key in best_ref:
                    out[r][c] = best_ref[key]
    return out

def draw_diagonals_from_point(grid, background=0):
    """Find the single non-background cell and draw all 4 diagonals from it
    to the grid boundaries using the cell's color."""
    rows, cols = len(grid), len(grid[0])
    pts = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] != background]
    if len(pts) != 1:
        return grid
    r0, c0 = pts[0]
    color = grid[r0][c0]
    out = [[background] * cols for _ in range(rows)]
    out[r0][c0] = color
    for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
        r, c = r0 + dr, c0 + dc
        while 0 <= r < rows and 0 <= c < cols:
            out[r][c] = color
            r += dr
            c += dc
    return out

def draw_lines_from_point(grid, background=0):
    """Find the single non-background cell and draw horizontal + vertical lines
    through it to the grid boundaries using the cell's color (plus sign)."""
    rows, cols = len(grid), len(grid[0])
    pts = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] != background]
    if len(pts) != 1:
        return grid
    r0, c0 = pts[0]
    color = grid[r0][c0]
    out = [[background] * cols for _ in range(rows)]
    for c in range(cols):
        out[r0][c] = color
    for r in range(rows):
        out[r][c0] = color
    return out

def draw_full_cross_from_point(grid, background=0):
    """Find the single non-background cell and draw both diagonals AND both
    orthogonal lines through it (8-pointed star pattern)."""
    rows, cols = len(grid), len(grid[0])
    pts = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] != background]
    if len(pts) != 1:
        return grid
    r0, c0 = pts[0]
    color = grid[r0][c0]
    out = [[background] * cols for _ in range(rows)]
    # Orthogonal lines
    for c in range(cols):
        out[r0][c] = color
    for r in range(rows):
        out[r][c0] = color
    # Diagonals
    for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
        r, c = r0 + dr, c0 + dc
        while 0 <= r < rows and 0 <= c < cols:
            out[r][c] = color
            r += dr
            c += dc
    return out

def fill_rectangle_interiors_ranked(grid, wall_color=4, background=0):
    """Find solid filled rectangles of wall_color, rank by interior area (ascending),
    and fill each interior with its rank (1=smallest, 2=next, etc.)."""
    rows, cols = len(grid), len(grid[0])
    visited = [[False]*cols for _ in range(rows)]
    rects = []
    for sr in range(rows):
        for sc in range(cols):
            if grid[sr][sc] == wall_color and not visited[sr][sc]:
                # BFS
                q = deque([(sr, sc)])
                visited[sr][sc] = True
                component = [(sr, sc)]
                while q:
                    r, c = q.popleft()
                    for nr, nc in [(r+1,c),(r-1,c),(r,c+1),(r,c-1)]:
                        if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc] and grid[nr][nc] == wall_color:
                            visited[nr][nc] = True
                            q.append((nr, nc))
                            component.append((nr, nc))
                # Check if solid rectangle
                min_r = min(r for r,c in component)
                max_r = max(r for r,c in component)
                min_c = min(c for r,c in component)
                max_c = max(c for r,c in component)
                expected = (max_r-min_r+1)*(max_c-min_c+1)
                if len(component) == expected:
                    int_h = max(0, max_r - min_r - 1)
                    int_w = max(0, max_c - min_c - 1)
                    interior_area = int_h * int_w
                    rects.append((interior_area, min_r, max_r, min_c, max_c))
    rects.sort()
    out = [row[:] for row in grid]
    for rank, (area, min_r, max_r, min_c, max_c) in enumerate(rects):
        if area > 0:
            fill_c = rank + 1
            for r in range(min_r+1, max_r):
                for c in range(min_c+1, max_c):
                    out[r][c] = fill_c
    return out

def fill_rectangles_between_corners(grid, corner_color=4, fill_color=2, background=0):
    """Find all axis-aligned rectangles defined by 4 cells of corner_color and fill
    their interior (excluding borders) with fill_color."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    corner_set = {(r, c) for r in range(rows) for c in range(cols) if grid[r][c] == corner_color}
    used = set()
    for (r1, c1) in corner_set:
        for (r2, c2) in corner_set:
            if r2 <= r1 or c2 <= c1:
                continue
            if (r1, c2) in corner_set and (r2, c1) in corner_set:
                rect_key = (r1, c1, r2, c2)
                if rect_key not in used:
                    used.add(rect_key)
                    for r in range(r1 + 1, r2):
                        for c in range(c1 + 1, c2):
                            if out[r][c] == background:
                                out[r][c] = fill_color
    return out

def crop_most_dense_object(grid, background=0, diag=True):
    """Among all non-background connected components, return the crop of the one
    with the highest density (cell count / bounding box area). Ties broken by largest count."""
    rows, cols = len(grid), len(grid[0])
    visited = [[False]*cols for _ in range(rows)]
    best_crop = None
    best_score = (-1, -1)
    for sr in range(rows):
        for sc in range(cols):
            if grid[sr][sc] != background and not visited[sr][sc]:
                # BFS to get component
                component = []
                q = deque([(sr, sc)])
                visited[sr][sc] = True
                while q:
                    r, c = q.popleft()
                    component.append((r, c))
                    neighbors = [(r+1,c),(r-1,c),(r,c+1),(r,c-1)]
                    if diag:
                        neighbors += [(r+1,c+1),(r+1,c-1),(r-1,c+1),(r-1,c-1)]
                    for nr, nc in neighbors:
                        if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc] and grid[nr][nc] != background:
                            visited[nr][nc] = True
                            q.append((nr, nc))
                min_r = min(r for r,c in component)
                max_r = max(r for r,c in component)
                min_c = min(c for r,c in component)
                max_c = max(c for r,c in component)
                bbox_area = (max_r - min_r + 1) * (max_c - min_c + 1)
                density = len(component) / bbox_area if bbox_area > 0 else 0
                score = (density, len(component))
                if score > best_score:
                    best_score = score
                    best_crop = [row[min_c:max_c+1] for row in grid[min_r:max_r+1]]
    return best_crop if best_crop is not None else grid

def stripe_right_from_points(grid, stripe_color=5, background=0):
    """For each non-background cell at (r, c), extend a stripe to the right:
    alternating between the cell's color and stripe_color."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(rows):
        for c in range(cols):
            color = grid[r][c]
            if color != background:
                col = c + 1
                toggle = True  # next is stripe_color
                while col < cols:
                    if out[r][col] == background:
                        out[r][col] = stripe_color if toggle else color
                    toggle = not toggle
                    col += 1
    return out

def extract_neighborhood_of_marker(grid, marker=8, radius=1, replace_marker=True, background=0):
    """Find the single cell with `marker`, extract its (2*radius+1) neighborhood,
    optionally replacing the marker with the dominant non-background color in that region."""
    rows, cols = len(grid), len(grid[0])
    mr, mc = None, None
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == marker:
                mr, mc = r, c
                break
        if mr is not None:
            break
    if mr is None:
        return grid
    r1, r2 = max(0, mr - radius), min(rows - 1, mr + radius)
    c1, c2 = max(0, mc - radius), min(cols - 1, mc + radius)
    patch = [row[c1:c2+1] for row in grid[r1:r2+1]]
    if replace_marker:
        # Replace marker with the most common non-background, non-marker color
        freq = {}
        for row in patch:
            for v in row:
                if v != background and v != marker:
                    freq[v] = freq.get(v, 0) + 1
        if freq:
            best = max(freq, key=freq.get)
            patch = [[best if v == marker else v for v in row] for row in patch]
    return patch

def apply_halo_map(grid, halo_map, background=0, radius=1):
    """For each non-background cell with color C in halo_map, fill its Moore
    neighborhood of given radius with halo_map[C], keeping center as C."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(rows):
        for c in range(cols):
            color = grid[r][c]
            if color != background and color in halo_map:
                halo_color = halo_map[color]
                for dr in range(-radius, radius + 1):
                    for dc in range(-radius, radius + 1):
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == background:
                            out[nr][nc] = halo_color
    return out

def fill_bbox_holes(grid, fill_color=7, background=0):
    """For each connected component of non-background cells, fill all background
    cells within the component's bounding box with fill_color."""
    rows, cols = len(grid), len(grid[0])
    visited = [[False] * cols for _ in range(rows)]
    out = [row[:] for row in grid]
    def bfs(sr, sc):
        comp, q = [], [(sr, sc)]
        visited[sr][sc] = True
        while q:
            r, c = q.pop(0)
            comp.append((r, c))
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc] and grid[nr][nc] != background:
                    visited[nr][nc] = True
                    q.append((nr, nc))
        return comp
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background and not visited[r][c]:
                comp = bfs(r, c)
                rs_list = [x[0] for x in comp]
                cs_list = [x[1] for x in comp]
                r1, r2 = min(rs_list), max(rs_list)
                c1, c2 = min(cs_list), max(cs_list)
                comp_set = set(comp)
                for br in range(r1, r2 + 1):
                    for bc in range(c1, c2 + 1):
                        if (br, bc) not in comp_set and grid[br][bc] == background:
                            out[br][bc] = fill_color
    return out

def attract_cells_to_unique_anchor(grid, background=0):
    """For each color that appears exactly once (anchor), find same-row or
    same-column cells of other colors and move them to be immediately adjacent
    (distance 1) to the anchor."""
    rows, cols = len(grid), len(grid[0])
    color_pos = {}
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            if v != background:
                if v not in color_pos:
                    color_pos[v] = []
                color_pos[v].append((r, c))
    out = [[background] * cols for _ in range(rows)]
    anchors = {}
    for color, positions in color_pos.items():
        if len(positions) == 1:
            r, c = positions[0]
            anchors[color] = (r, c)
            out[r][c] = color
    for other_color, other_positions in color_pos.items():
        if other_color in anchors:
            continue
        for (r, c) in other_positions:
            moved = False
            for anchor_color, (ar, ac) in anchors.items():
                if r == ar:
                    nc = ac - 1 if c < ac else ac + 1
                    if 0 <= nc < cols:
                        out[r][nc] = other_color
                        moved = True
                        break
                elif c == ac:
                    nr = ar - 1 if r < ar else ar + 1
                    if 0 <= nr < rows:
                        out[nr][c] = other_color
                        moved = True
                        break
            if not moved:
                out[r][c] = other_color
    return out

def reflect_shape_across_separator(grid, background=0):
    """Find a full-column AND full-row separator (cross). Remove both,
    find the non-empty quadrant, recolor to separator color, and mirror
    to all four quadrants (4-fold reflection symmetry). Falls back to
    single separator (col or row only)."""
    rows, cols = len(grid), len(grid[0])
    sep_color = None
    sep_row = None
    sep_col = None
    for r in range(rows):
        vals = [grid[r][c] for c in range(cols) if grid[r][c] != background]
        if vals and len(set(vals)) == 1 and len(vals) == cols:
            sep_row = r
            sep_color = vals[0]
            break
    for c in range(cols):
        vals = [grid[r][c] for r in range(rows) if grid[r][c] != background]
        if vals and len(set(vals)) == 1 and len(vals) == rows:
            sep_col = c
            if sep_color is None:
                sep_color = vals[0]
            break
    if sep_row is not None and sep_col is not None:
        out_rows = rows - 1
        out_cols = cols - 1
        out = [[background] * out_cols for _ in range(out_rows)]
        for r in range(sep_row):
            for c in range(sep_col):
                if grid[r][c] != background:
                    out[r][c] = sep_color
                    mc = out_cols - 1 - c
                    mr = out_rows - 1 - r
                    if 0 <= mc < out_cols:
                        out[r][mc] = sep_color
                    if 0 <= mr < out_rows:
                        out[mr][c] = sep_color
                    if 0 <= mr < out_rows and 0 <= mc < out_cols:
                        out[mr][mc] = sep_color
        return out
    if sep_col is not None:
        out_cols = cols - 1
        out = [[background] * out_cols for _ in range(rows)]
        for r in range(rows):
            for c in range(sep_col):
                if grid[r][c] != background:
                    out[r][c] = sep_color
                    mc = out_cols - 1 - c
                    if 0 <= mc < out_cols:
                        out[r][mc] = sep_color
        return out
    if sep_row is not None:
        out_rows = rows - 1
        out = [[background] * cols for _ in range(out_rows)]
        for r in range(sep_row):
            for c in range(cols):
                if grid[r][c] != background:
                    out[r][c] = sep_color
                    mr = out_rows - 1 - r
                    if 0 <= mr < out_rows:
                        out[mr][c] = sep_color
        return out
    return grid

def stamp_shape_at_marker(grid, marker_color=5, background=0):
    """Find the non-background shape and a single marker cell. Copy the shape
    with the marker cell aligned to the shape's bounding-box center."""
    rows, cols = len(grid), len(grid[0])
    shape_cells = []
    marker_pos = None
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            if v == marker_color:
                marker_pos = (r, c)
            elif v != background:
                shape_cells.append((r, c, v))
    if marker_pos is None or not shape_cells:
        return grid
    rs = [r for r, c, v in shape_cells]
    cs = [c for r, c, v in shape_cells]
    center_r = (min(rs) + max(rs)) // 2
    center_c = (min(cs) + max(cs)) // 2
    dr = marker_pos[0] - center_r
    dc = marker_pos[1] - center_c
    out = [row[:] for row in grid]
    # Remove marker
    out[marker_pos[0]][marker_pos[1]] = background
    # Stamp copy at shifted position
    for r, c, v in shape_cells:
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            out[nr][nc] = v
    return out

def reverse_concentric_rings(grid, background=0):
    """Reverse the color assignment of concentric rectangular rings.
    The outermost ring swaps colors with the innermost, etc."""
    rows, cols = len(grid), len(grid[0])
    # Compute distance from edge for each cell
    dist_to_color = {}
    for r in range(rows):
        for c in range(cols):
            d = min(r, c, rows - 1 - r, cols - 1 - c)
            color = grid[r][c]
            if d not in dist_to_color:
                dist_to_color[d] = color
    max_d = max(dist_to_color.keys())
    # Build reversed mapping: color at dist d → color at dist (max_d - d)
    color_map = {}
    for d in range(max_d + 1):
        src = dist_to_color.get(d)
        dst = dist_to_color.get(max_d - d)
        if src is not None and dst is not None:
            color_map[src] = dst
    out = [[color_map.get(grid[r][c], grid[r][c]) for c in range(cols)] for r in range(rows)]
    return out

def fractal_tile_nonzero(grid, background=0):
    """Self-similar expansion: replace each non-background cell with a copy
    of the whole grid; replace background cells with all-background tiles."""
    rows, cols = len(grid), len(grid[0])
    out = [[background] * (cols * cols) for _ in range(rows * rows)]
    for i in range(rows):
        for j in range(cols):
            if grid[i][j] != background:
                for dr in range(rows):
                    for dc in range(cols):
                        out[i * rows + dr][j * cols + dc] = grid[dr][dc]
    return out

def float_up_objects_by_height(grid, background=0):
    """Each connected component of non-background cells floats up so that
    its bottom row is at (rows-1) - height, where height = max_row - min_row + 1.
    Column positions are preserved."""
    rows, cols = len(grid), len(grid[0])
    visited = [[False]*cols for _ in range(rows)]
    out = [[background]*cols for _ in range(rows)]
    def bfs(sr, sc, color):
        comp = []
        q = [(sr, sc)]
        visited[sr][sc] = True
        while q:
            r, c = q.pop(0)
            comp.append((r, c))
            for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                nr, nc = r+dr, c+dc
                if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc] and grid[nr][nc] == color:
                    visited[nr][nc] = True
                    q.append((nr, nc))
        return comp
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background and not visited[r][c]:
                comp = bfs(r, c, grid[r][c])
                color = grid[r][c]
                rs = [x[0] for x in comp]
                max_r = max(rs)
                height = max_r - min(rs) + 1
                new_bottom = (rows - 1) - height
                offset = new_bottom - max_r
                for cr, cc in comp:
                    nr = cr + offset
                    if 0 <= nr < rows:
                        out[nr][cc] = color
    return out

def find_empty_in_both_halves(grid, mark_color=2, background=0):
    """Split grid into two equal halves (top/bottom). Output grid the size of
    one half where cell = mark_color if BOTH halves are background at that position."""
    rows, cols = len(grid), len(grid[0])
    if rows % 2 == 0:
        h = rows // 2
        result = []
        for r in range(h):
            row = []
            for c in range(cols):
                top = grid[r][c]
                bot = grid[r + h][c]
                row.append(mark_color if top == background and bot == background else background)
            result.append(row)
        return result
    if cols % 2 == 0:
        w = cols // 2
        result = []
        for r in range(rows):
            row = []
            for c in range(w):
                left = grid[r][c]
                right = grid[r][c + w]
                row.append(mark_color if left == background and right == background else background)
            result.append(row)
        return result
    return grid

def extend_lines_to_cross(grid, background=0, intersection_color=4):
    """Find a partial horizontal segment and a partial vertical segment.
    Extend both to full grid width/height. Mark their intersection with intersection_color."""
    rows, cols = len(grid), len(grid[0])
    # Detect partial rows (segments) - a row with 2+ same non-bg cells
    h_row, h_color = None, None
    v_col, v_color = None, None
    for r in range(rows):
        vals = [grid[r][c] for c in range(cols) if grid[r][c] != background]
        if len(vals) >= 2 and len(set(vals)) == 1 and len(vals) < cols:
            h_row = r; h_color = vals[0]
    for c in range(cols):
        vals = [grid[r][c] for r in range(rows) if grid[r][c] != background]
        if len(vals) >= 2 and len(set(vals)) == 1 and len(vals) < rows:
            v_col = c; v_color = vals[0]
    if h_row is None or v_col is None:
        return grid
    out = [row[:] for row in grid]
    for c in range(cols):
        if c != v_col:
            out[h_row][c] = h_color
    for r in range(rows):
        if r != h_row:
            out[r][v_col] = v_color
    out[h_row][v_col] = intersection_color
    return out

def fill_gaps_between_endpoints(grid, fill_color=2, background=0):
    """In each row, if there are 2+ same-color cells with background between them,
    fill the interior gaps with fill_color. Also does columns."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(rows):
        by_color = {}
        for c in range(cols):
            v = grid[r][c]
            if v != background:
                if v not in by_color: by_color[v] = []
                by_color[v].append(c)
        for color, positions in by_color.items():
            if len(positions) >= 2:
                c1, c2 = min(positions), max(positions)
                for c in range(c1+1, c2):
                    if grid[r][c] == background:
                        out[r][c] = fill_color
    for c in range(cols):
        by_color = {}
        for r in range(rows):
            v = grid[r][c]
            if v != background:
                if v not in by_color: by_color[v] = []
                by_color[v].append(r)
        for color, positions in by_color.items():
            if len(positions) >= 2:
                r1, r2 = min(positions), max(positions)
                for r in range(r1+1, r2):
                    if grid[r][c] == background:
                        out[r][c] = fill_color
    return out

def fill_gaps_between_endpoints_rows(grid, fill_color=2, background=0):
    """In each ROW ONLY, fill background gaps between same-color endpoint pairs."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(rows):
        by_color = {}
        for c in range(cols):
            v = grid[r][c]
            if v != background:
                if v not in by_color: by_color[v] = []
                by_color[v].append(c)
        for color, positions in by_color.items():
            if len(positions) >= 2:
                c1, c2 = min(positions), max(positions)
                for c in range(c1+1, c2):
                    if grid[r][c] == background:
                        out[r][c] = fill_color
    return out

def upscale_grid(grid, factor=2):
    """Scale each cell to a factor×factor block."""
    out = []
    for row in grid:
        new_row = []
        for cell in row:
            new_row.extend([cell] * factor)
        for _ in range(factor):
            out.append(new_row[:])
    return out

def upscale_by_color_count(grid, background=0):
    """Scale each cell to an NxN block where N = number of distinct non-background colors."""
    colors = set()
    for row in grid:
        for v in row:
            if v != background:
                colors.add(v)
    factor = len(colors) if colors else 1
    return upscale_grid(grid, factor)

def drip_down_columns(grid, background=0):
    """For each non-background cell, propagate its value downward through
    all background cells in the same column below it."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for c in range(cols):
        for r in range(rows):
            if out[r][c] != background:
                color = out[r][c]
                for r2 in range(r+1, rows):
                    if out[r2][c] == background:
                        out[r2][c] = color
                    else:
                        break
    return out

def find_odd_quadrant_cell(grid, background=0):
    """Grid has a blank divider row and column, creating 4 equal quadrants.
    For each cell position, pick the value that is the 'odd one out' across
    the 4 quadrants (the value held by only 1 quadrant). If all agree, use that value."""
    rows, cols = len(grid), len(grid[0])
    # Find separator row and col (all-zero row/col)
    sep_row, sep_col = None, None
    for r in range(rows):
        if all(grid[r][c] == background for c in range(cols)):
            sep_row = r; break
    for c in range(cols):
        if all(grid[r][c] == background for r in range(rows)):
            sep_col = c; break
    if sep_row is None or sep_col is None:
        return grid
    # Extract 4 quadrants: TL, TR, BL, BR
    def get_quad(r1, r2, c1, c2):
        return [[grid[r][c] for c in range(c1, c2)] for r in range(r1, r2)]
    tl = get_quad(0, sep_row, 0, sep_col)
    tr = get_quad(0, sep_row, sep_col+1, cols)
    bl = get_quad(sep_row+1, rows, 0, sep_col)
    br = get_quad(sep_row+1, rows, sep_col+1, cols)
    hr, hc = len(tl), len(tl[0]) if tl else 0
    if hr == 0 or hc == 0:
        return grid
    out = [[background]*hc for _ in range(hr)]
    for r in range(hr):
        for c in range(hc):
            vals = [tl[r][c], tr[r][c], bl[r][c], br[r][c]]
            from collections import Counter
            cnt = Counter(vals)
            if len(cnt) == 1:
                out[r][c] = vals[0]
            else:
                # Pick the value that appears least (the odd one out)
                min_count = min(cnt.values())
                unique = [k for k, v in cnt.items() if v == min_count]
                out[r][c] = unique[0] if unique else vals[0]
    return out

def move_toward_target_color(grid, mover_color=3, target_color=4, background=0):
    """Move each mover_color cell one step toward the nearest target_color cell."""
    rows, cols = len(grid), len(grid[0])
    movers = [(r,c) for r in range(rows) for c in range(cols) if grid[r][c] == mover_color]
    targets = [(r,c) for r in range(rows) for c in range(cols) if grid[r][c] == target_color]
    if not movers or not targets:
        return grid
    out = [row[:] for row in grid]
    for mr, mc in movers:
        # Find nearest target
        best = min(targets, key=lambda t: abs(t[0]-mr)+abs(t[1]-mc))
        tr2, tc = best
        dr = 0 if tr2 == mr else (1 if tr2 > mr else -1)
        dc = 0 if tc == mc else (1 if tc > mc else -1)
        # Move diagonally if both row and col differ, else move in the non-zero direction
        nr, nc = mr + dr, mc + dc
        if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == background:
            out[mr][mc] = background
            out[nr][nc] = mover_color
    return out

def sort_colors_to_columns_by_count(grid, background=0):
    """Count occurrences of each non-background color. Sort colors by count descending.
    Output: each column filled with the color from top, number of rows = that color's count.
    Number of output columns = number of distinct colors. Number of output rows = max count."""
    from collections import Counter
    flat = [v for row in grid for v in row if v != background]
    if not flat:
        return grid
    cnt = Counter(flat)
    sorted_colors = sorted(cnt.keys(), key=lambda c: -cnt[c])
    max_count = cnt[sorted_colors[0]]
    num_cols = len(sorted_colors)
    out = [[background]*num_cols for _ in range(max_count)]
    for col_idx, color in enumerate(sorted_colors):
        for r in range(cnt[color]):
            out[r][col_idx] = color
    return out

def checkerboard_interleave_rows(grid, background=0):
    """For a 2-row grid, create a checkerboard: output[r][c] = input[r][c] if c%2==0,
    else input[1-r][c]. Generalizes to N rows: output[r][c] = input[(r+c)%len(grid)][c]."""
    rows, cols = len(grid), len(grid[0])
    return [[grid[(r + c) % rows][c] for c in range(cols)] for r in range(rows)]

def extend_period_by_half(grid, old_color=1, new_color=2):
    """Detect the minimum row-period of the grid. Extend the pattern by n//2 more rows
    following the same period, recoloring old_color to new_color throughout."""
    n = len(grid)
    if n == 0:
        return grid
    # Find minimum period
    period = n
    for p in range(1, n + 1):
        if all(grid[r] == grid[r % p] for r in range(n)):
            period = p
            break
    extra = n // 2
    extended = list(grid) + [grid[r % period] for r in range(n, n + extra)]
    if old_color != new_color:
        return [[new_color if v == old_color else v for v in row] for row in extended]
    return extended

def tile_kernel_diagonally(grid, background=0):
    """Extract the non-background kernel (bounding box of non-zero cells).
    Tile it diagonally at offsets (k,k) for k=0,1,... on a 2x output grid."""
    rows, cols = len(grid), len(grid[0])
    # Find bounding box of non-zero cells
    rs = [r for r in range(rows) if any(grid[r][c] != background for c in range(cols))]
    cs = [c for c in range(cols) if any(grid[r][c] != background for r in range(rows))]
    if not rs or not cs:
        return grid
    r1, r2 = min(rs), max(rs)
    c1, c2 = min(cs), max(cs)
    kh = r2 - r1 + 1
    kw = c2 - c1 + 1
    kernel = [[grid[r1+dr][c1+dc] for dc in range(kw)] for dr in range(kh)]
    out_rows = rows * 2
    out_cols = cols * 2
    out = [[background]*out_cols for _ in range(out_rows)]
    steps = max(out_rows, out_cols)
    for k in range(steps):
        for dr in range(kh):
            for dc in range(kw):
                r2_ = k + dr
                c2_ = k + dc
                if 0 <= r2_ < out_rows and 0 <= c2_ < out_cols and kernel[dr][dc] != background:
                    out[r2_][c2_] = kernel[dr][dc]
    return out

def rotate_concentric_rings_cyclic(grid, background=0):
    """Rotate the color assignments of concentric rectangular rings by one step.
    The unique ring values form a cycle (outside-in order); each value
    becomes the previous one in that cycle."""
    rows, cols = len(grid), len(grid[0])
    # Collect ring colors in outside-in order (d=0 is outermost)
    ring_colors = {}
    for r in range(rows):
        for c in range(cols):
            d = min(r, c, rows-1-r, cols-1-c)
            if d not in ring_colors:
                ring_colors[d] = grid[r][c]
    if not ring_colors:
        return grid
    # Build the unique value sequence in outside-in order
    max_d = max(ring_colors.keys())
    value_sequence = [ring_colors[d] for d in range(max_d + 1)]
    # Get unique values in appearance order
    seen = set()
    unique_vals = []
    for v in value_sequence:
        if v not in seen:
            seen.add(v)
            unique_vals.append(v)
    if len(unique_vals) <= 1:
        return grid
    # Build rotation mapping: each value → previous in cycle (shift by -1)
    n = len(unique_vals)
    color_map = {unique_vals[i]: unique_vals[(i - 1) % n] for i in range(n)}
    out = []
    for r in range(rows):
        row = []
        for c in range(cols):
            row.append(color_map.get(grid[r][c], grid[r][c]))
        out.append(row)
    return out

def propagate_upward_v_shape(grid, background=0):
    """Two-row base at bottom: last row has inner color (center run) flanked by outer,
    2nd-to-last has outer color at positions that mirror the inner run from the last row.
    Inner color propagates upward in a V: at distance d above the 2nd-to-last row,
    inner color appears at cols (center ± (half_extent + d))."""
    rows, cols = len(grid), len(grid[0])
    if rows < 2:
        return grid
    last_row = grid[rows - 1]
    second_last = grid[rows - 2]
    last_colors = set(v for v in last_row if v != background)
    second_colors = set(v for v in second_last if v != background)
    inner_colors = last_colors - second_colors
    if not inner_colors:
        from collections import Counter
        cnt = Counter(v for v in last_row if v != background)
        if not cnt:
            return grid
        inner_color = min(cnt, key=cnt.get)
    else:
        inner_color = next(iter(inner_colors))
    inner_positions = [c for c in range(cols) if last_row[c] == inner_color]
    if not inner_positions:
        return grid
    min_ic = min(inner_positions)
    max_ic = max(inner_positions)
    center_col = (min_ic + max_ic + 1) // 2
    half_extent = max_ic - center_col
    out = [row[:] for row in grid]
    for d in range(1, rows - 1):
        r = rows - 2 - d
        if r < 0:
            break
        spread = half_extent + d
        for sign in [-1, 1]:
            c = center_col + sign * spread
            if 0 <= c < cols and out[r][c] == background:
                out[r][c] = inner_color
    return out

def replace_non_dominant_with_color(grid, replace_color=5, background=0):
    """Find the most common color (ignoring background). Replace all cells that
    are NOT that dominant color (and not background) with replace_color."""
    from collections import Counter
    flat = [v for row in grid for v in row if v != background]
    if not flat:
        return grid
    cnt = Counter(flat)
    dominant = cnt.most_common(1)[0][0]
    out = []
    for row in grid:
        new_row = []
        for v in row:
            if v == background or v == dominant:
                new_row.append(v)
            else:
                new_row.append(replace_color)
        out.append(new_row)
    return out

def draw_L_rays_to_edge(grid, background=0):
    """For each non-background cell, draw a rightward ray to the right edge,
    then a downward ray from the rightmost point of that ray to the bottom."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    # Process rows top to bottom
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background:
                color = grid[r][c]
                # Rightward ray from (r, c) to right edge (stop at existing non-bg)
                for c2 in range(c + 1, cols):
                    if out[r][c2] == background:
                        out[r][c2] = color
                    else:
                        break
    # Now draw downward rays from right edge column
    for r in range(rows):
        if out[r][cols - 1] != background:
            color = out[r][cols - 1]
            for r2 in range(r + 1, rows):
                if out[r2][cols - 1] == background:
                    out[r2][cols - 1] = color
                else:
                    break
    return out

def add_cross_intersection_halo(grid, halo_color=4, background=0):
    """Find the intersection of a full horizontal line and full vertical line.
    Place a 3x3 box of halo_color around the intersection, preserving the center cell."""
    rows, cols = len(grid), len(grid[0])
    h_row, v_col = None, None
    for r in range(rows):
        vals = [grid[r][c] for c in range(cols) if grid[r][c] != background]
        if len(vals) == cols and len(set(vals)) >= 1:
            h_row = r; break
    if h_row is None:
        # Try partial line (most of the row)
        for r in range(rows):
            vals = [grid[r][c] for c in range(cols) if grid[r][c] != background]
            if len(vals) >= cols - 1:
                h_row = r; break
    for c in range(cols):
        vals = [grid[r][c] for r in range(rows) if grid[r][c] != background]
        if len(vals) == rows and len(set(vals)) >= 1:
            v_col = c; break
    if h_row is None or v_col is None:
        return grid
    out = [row[:] for row in grid]
    for dr in range(-1, 2):
        for dc in range(-1, 2):
            r2, c2 = h_row + dr, v_col + dc
            if 0 <= r2 < rows and 0 <= c2 < cols:
                if dr == 0 and dc == 0:
                    pass  # keep center
                else:
                    out[r2][c2] = halo_color
    return out

def fill_rows_cycling_header_colors(grid, separator_color=5, background=0):
    """Row 0 has header colors. Row 1 is a separator (all same color).
    Fill remaining rows by cycling through header colors as solid rows."""
    rows, cols = len(grid), len(grid[0])
    # Find separator row (first row where all cells are separator_color)
    sep_row = None
    for r in range(rows):
        if all(grid[r][c] == separator_color for c in range(cols)):
            sep_row = r; break
    if sep_row is None:
        return grid
    header_colors = grid[sep_row - 1] if sep_row > 0 else grid[0]
    n_colors = len(header_colors)
    out = [row[:] for row in grid]
    for r in range(sep_row + 1, rows):
        color = header_colors[(r - sep_row - 1) % n_colors]
        for c in range(cols):
            out[r][c] = color
    return out

def fill_regions_with_dominant_color(grid, separator=5, background=0):
    """Split grid by separator rows/cols into sub-regions, fill each with
    its most-frequent non-background, non-separator color (or background if tie/none)."""
    rows, cols = len(grid), len(grid[0])
    # Find separator rows and cols
    sep_rows = [r for r in range(rows) if all(grid[r][c] == separator for c in range(cols))]
    sep_cols = [c for c in range(cols) if all(grid[r][c] == separator for r in range(rows))]
    # Build row and col partition boundaries
    row_bounds = []
    prev = 0
    for sr in sep_rows:
        if sr > prev:
            row_bounds.append((prev, sr))
        prev = sr + 1
    if prev < rows:
        row_bounds.append((prev, rows))
    col_bounds = []
    prev = 0
    for sc in sep_cols:
        if sc > prev:
            col_bounds.append((prev, sc))
        prev = sc + 1
    if prev < cols:
        col_bounds.append((prev, cols))
    if not row_bounds or not col_bounds:
        return grid
    out = [row[:] for row in grid]
    for r1, r2 in row_bounds:
        for c1, c2 in col_bounds:
            freq = {}
            for r in range(r1, r2):
                for c in range(c1, c2):
                    v = grid[r][c]
                    if v != background and v != separator:
                        freq[v] = freq.get(v, 0) + 1
            if not freq:
                fill = background
            else:
                max_count = max(freq.values())
                candidates = [k for k, v in freq.items() if v == max_count]
                fill = candidates[0] if len(candidates) == 1 else background
            for r in range(r1, r2):
                for c in range(c1, c2):
                    out[r][c] = fill
    return out

def mark_isolated_cells(grid, target_color=2, mark_color=1, background=0):
    """Find connected components of target_color. Replace single-cell (isolated) components
    with mark_color. Multi-cell components are preserved."""
    from collections import deque
    rows, cols = len(grid), len(grid[0])
    visited = [[False]*cols for _ in range(rows)]
    out = [row[:] for row in grid]
    def bfs(sr, sc):
        comp = []
        q = deque([(sr, sc)])
        visited[sr][sc] = True
        while q:
            r, c = q.popleft()
            comp.append((r, c))
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc] and grid[nr][nc] == target_color:
                    visited[nr][nc] = True
                    q.append((nr, nc))
        return comp
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == target_color and not visited[r][c]:
                comp = bfs(r, c)
                if len(comp) == 1:
                    out[comp[0][0]][comp[0][1]] = mark_color
    return out

def complete_checkerboard_inverted(grid, background=0):
    """Input has a partially visible checkerboard pattern + rectangular mask of one color.
    Output: full checkerboard with the two checker colors SWAPPED relative to visible."""
    from collections import Counter
    rows, cols = len(grid), len(grid[0])
    flat = [v for row in grid for v in row]
    cnt = Counter(flat)
    distinct = list(cnt.keys())
    if len(distinct) < 3:
        return grid
    mask_color = None
    for c_val in distinct:
        for row in grid:
            if all(v == c_val for v in row):
                mask_color = c_val; break
        if mask_color is not None: break
    if mask_color is None:
        for c_val in distinct:
            for col_i in range(cols):
                if all(grid[r][col_i] == c_val for r in range(rows)):
                    mask_color = c_val; break
            if mask_color is not None: break
    if mask_color is None:
        return grid
    checker_colors = [c for c in distinct if c != mask_color]
    if len(checker_colors) != 2:
        return grid
    a, b = checker_colors[0], checker_colors[1]
    start_color = None
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != mask_color:
                if (r + c) % 2 == 0:
                    start_color = grid[r][c]
                else:
                    start_color = a if grid[r][c] == b else b
                break
        if start_color is not None: break
    if start_color is None:
        return grid
    other_color = b if start_color == a else a
    return [[(other_color if (r + c) % 2 == 0 else start_color) for c in range(cols)] for r in range(rows)]

def shoot_arrow_from_wedge(grid, background=0):
    """Wedge/arrow shape: main color forms tapering wedge, one special cell at wide end.
    Special cell shoots from the narrow tip outward to the grid edge.
    Direction: if special at top row → extend downward from bottom tip;
    if at bottom row → extend upward; if at left col → extend rightward; etc."""
    from collections import Counter
    rows, cols = len(grid), len(grid[0])
    cells = [(r, c, grid[r][c]) for r in range(rows) for c in range(cols) if grid[r][c] != background]
    if not cells:
        return grid
    cnt = Counter(v for r, c, v in cells)
    if len(cnt) < 2:
        return grid
    special_color = min(cnt, key=cnt.get)
    special_cells = [(r, c) for r, c, v in cells if v == special_color]
    if not special_cells:
        return grid
    sr, sc = special_cells[0]
    all_r = [r for r, c, v in cells]
    all_c = [c for r, c, v in cells]
    min_r, max_r = min(all_r), max(all_r)
    min_c, max_c = min(all_c), max(all_c)
    out = [row[:] for row in grid]
    if sr == max_r:
        for r2 in range(0, min_r):
            if out[r2][sc] == background:
                out[r2][sc] = special_color
    elif sr == min_r:
        for r2 in range(max_r + 1, rows):
            if out[r2][sc] == background:
                out[r2][sc] = special_color
    elif sc == min_c:
        for c2 in range(max_c + 1, cols):
            if out[sr][c2] == background:
                out[sr][c2] = special_color
    elif sc == max_c:
        for c2 in range(0, min_c):
            if out[sr][c2] == background:
                out[sr][c2] = special_color
    return out

def color_order_strip(grid, background=0):
    """Scan grid row-major, collect distinct non-background colors in first-appearance order.
    If grid is taller than wide: return as single column ([[c] for c in colors]).
    If grid is wider than tall: return as single row ([colors])."""
    rows, cols = len(grid), len(grid[0]) if grid else 0
    seen = []
    for row in grid:
        for v in row:
            if v != background and v not in seen:
                seen.append(v)
    if not seen:
        return [[background]]
    if rows >= cols:
        return [[c] for c in seen]
    else:
        return [seen]

def drip_down_gravity(grid, background=0):
    """For each column, drop all non-background cells to the bottom, preserving order."""
    rows, cols = len(grid), len(grid[0])
    out = [[background] * cols for _ in range(rows)]
    for c in range(cols):
        col_vals = [grid[r][c] for r in range(rows) if grid[r][c] != background]
        for i, v in enumerate(reversed(col_vals)):
            out[rows - 1 - i][c] = v
    return out

def drip_up_gravity(grid, background=0):
    """For each column, float all non-background cells to the top, preserving order."""
    rows, cols = len(grid), len(grid[0])
    out = [[background] * cols for _ in range(rows)]
    for c in range(cols):
        col_vals = [grid[r][c] for r in range(rows) if grid[r][c] != background]
        for i, v in enumerate(col_vals):
            out[i][c] = v
    return out

def drip_right_gravity(grid, background=0):
    """For each row, push all non-background cells to the right end."""
    rows, cols = len(grid), len(grid[0])
    out = [[background] * cols for _ in range(rows)]
    for r in range(rows):
        vals = [grid[r][c] for c in range(cols) if grid[r][c] != background]
        for i, v in enumerate(reversed(vals)):
            out[r][cols - 1 - i] = v
    return out

def drip_left_gravity(grid, background=0):
    """For each row, push all non-background cells to the left end."""
    rows, cols = len(grid), len(grid[0])
    out = [[background] * cols for _ in range(rows)]
    for r in range(rows):
        vals = [grid[r][c] for c in range(cols) if grid[r][c] != background]
        for i, v in enumerate(vals):
            out[r][i] = v
    return out

def expand_border_by_one(grid, border_color=None, background=0):
    """Add a 1-cell border around grid. Border uses border_color (or the most common non-bg color)."""
    rows, cols = len(grid), len(grid[0])
    if border_color is None:
        from collections import Counter
        flat = [v for row in grid for v in row if v != background]
        if flat:
            border_color = Counter(flat).most_common(1)[0][0]
        else:
            border_color = 1
    out = []
    top_row = [border_color] * (cols + 2)
    out.append(top_row)
    for r in range(rows):
        out.append([border_color] + list(grid[r]) + [border_color])
    out.append([border_color] * (cols + 2))
    return out

def remove_border(grid):
    """Remove the outermost row/col on all 4 sides."""
    if len(grid) <= 2: return grid
    return [row[1:-1] for row in grid[1:-1]]

def fill_boundary_color(grid, background=0):
    """Replace background cells touching the grid boundary with the most common border color."""
    rows, cols = len(grid), len(grid[0])
    from collections import Counter
    border_vals = []
    for c in range(cols):
        border_vals.append(grid[0][c])
        border_vals.append(grid[rows-1][c])
    for r in range(1, rows-1):
        border_vals.append(grid[r][0])
        border_vals.append(grid[r][cols-1])
    non_bg = [v for v in border_vals if v != background]
    if not non_bg: return grid
    fill = Counter(non_bg).most_common(1)[0][0]
    out = [row[:] for row in grid]
    # BFS from border
    from collections import deque
    visited = [[False]*cols for _ in range(rows)]
    q = deque()
    for r in range(rows):
        for c in range(cols):
            if (r == 0 or r == rows-1 or c == 0 or c == cols-1) and grid[r][c] == background:
                q.append((r, c)); visited[r][c] = True
    while q:
        r, c = q.popleft()
        out[r][c] = fill
        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            nr, nc = r+dr, c+dc
            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc] and grid[nr][nc] == background:
                visited[nr][nc] = True; q.append((nr, nc))
    return out

def connect_color_pairs_diagonal(grid, background=0):
    """For each color that appears exactly twice, draw a diagonal/straight line between the two cells."""
    from collections import defaultdict
    rows, cols = len(grid), len(grid[0])
    color_positions = defaultdict(list)
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background:
                color_positions[grid[r][c]].append((r, c))
    out = [row[:] for row in grid]
    for color, positions in color_positions.items():
        if len(positions) == 2:
            (r1, c1), (r2, c2) = positions
            dr = 0 if r1 == r2 else (1 if r2 > r1 else -1)
            dc = 0 if c1 == c2 else (1 if c2 > c1 else -1)
            r, c = r1, c1
            while True:
                if 0 <= r < rows and 0 <= c < cols:
                    out[r][c] = color
                if (r, c) == (r2, c2):
                    break
                r += dr
                c += dc
    return out

def crop_concentric_quadrant(grid, background=0):
    """For a concentric symmetric pattern, extract top-left quadrant of the nonzero bbox."""
    rows, cols = len(grid), len(grid[0])
    nonzero = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] != background]
    if not nonzero:
        return grid
    min_r = min(r for r, c in nonzero); max_r = max(r for r, c in nonzero)
    min_c = min(c for r, c in nonzero); max_c = max(c for r, c in nonzero)
    half_h = (max_r - min_r + 2) // 2
    half_w = (max_c - min_c + 2) // 2
    return [[grid[r][c] for c in range(min_c, min_c + half_w)] for r in range(min_r, min_r + half_h)]

def check_8_path_between_2x2_blocks(grid):
    """Check if 8-cells form a 4-connected path between two 2x2 blocks of value 2. Output [[8]] or [[0]]."""
    from collections import deque
    rows, cols = len(grid), len(grid[0])
    blocks = []
    for r in range(rows - 1):
        for c in range(cols - 1):
            if grid[r][c] == 2 and grid[r+1][c] == 2 and grid[r][c+1] == 2 and grid[r+1][c+1] == 2:
                blocks.append((r, c))
    if len(blocks) != 2:
        return grid
    def block_cells(tl):
        r, c = tl
        return {(r, c), (r+1, c), (r, c+1), (r+1, c+1)}
    b1 = block_cells(blocks[0])
    b2 = block_cells(blocks[1])
    def adjacent_8s(bc):
        adj = set()
        for (r, c) in bc:
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == 8:
                    adj.add((nr, nc))
        return adj
    adj1 = adjacent_8s(b1)
    adj2 = adjacent_8s(b2)
    if not adj1 or not adj2:
        return [[0]]
    visited = set(adj1)
    queue = deque(adj1)
    while queue:
        r, c = queue.popleft()
        if (r, c) in adj2:
            return [[8]]
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == 8 and (nr, nc) not in visited:
                visited.add((nr, nc))
                queue.append((nr, nc))
    return [[0]]

def replace_8_blobs_with_key(grid, background=0):
    """Find the non-8 non-bg pattern (key), find 8-blobs with same shape, replace with key."""
    rows, cols = len(grid), len(grid[0])
    key_cells = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] not in (0, 8)]
    if not key_cells:
        return grid
    min_kr = min(r for r, c in key_cells); min_kc = min(c for r, c in key_cells)
    key_shape = {(r - min_kr, c - min_kc): grid[r][c] for r, c in key_cells}
    eights = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] == 8]
    if not eights:
        return grid
    visited = set()
    def bfs_8(sr, sc):
        comp = []
        q = [(sr, sc)]
        visited.add((sr, sc))
        while q:
            r, c = q.pop()
            comp.append((r, c))
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if (nr, nc) not in visited and 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == 8:
                    visited.add((nr, nc))
                    q.append((nr, nc))
        return comp
    eight_comps = []
    for r, c in eights:
        if (r, c) not in visited:
            eight_comps.append(bfs_8(r, c))
    out = [[background] * cols for _ in range(rows)]
    matched = False
    for comp in eight_comps:
        min_r = min(r for r, c in comp); min_c = min(c for r, c in comp)
        comp_shape = {(r - min_r, c - min_c) for r, c in comp}
        if comp_shape == set(key_shape.keys()):
            for (dr, dc), val in key_shape.items():
                nr, nc = min_r + dr, min_c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    out[nr][nc] = val
            matched = True
    if not matched:
        return grid
    return out

def expand_frame_pattern_outward(grid, background=0):
    """Expand bordered frame: frame→interior_color, interior→frame_color, add new outer cross-frame."""
    from collections import Counter
    rows, cols = len(grid), len(grid[0])
    nz = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] != background]
    if not nz: return grid
    cnt = Counter(grid[r][c] for r, c in nz)
    if len(cnt) != 2: return grid
    colors = list(cnt.keys())
    frame_color = max(colors, key=lambda c: cnt[c])
    inner_color = min(colors, key=lambda c: cnt[c])
    inner_cells = [(r, c) for r, c in nz if grid[r][c] == inner_color]
    frame_cells = [(r, c) for r, c in nz if grid[r][c] == frame_color]
    min_ir = min(r for r, c in inner_cells); max_ir = max(r for r, c in inner_cells)
    min_ic = min(c for r, c in inner_cells); max_ic = max(c for r, c in inner_cells)
    inner_h = max_ir - min_ir + 1; inner_w = max_ic - min_ic + 1
    min_fr = min(r for r, c in frame_cells); max_fr = max(r for r, c in frame_cells)
    min_fc = min(c for r, c in frame_cells); max_fc = max(c for r, c in frame_cells)
    out = [[background] * cols for _ in range(rows)]
    for r, c in frame_cells: out[r][c] = inner_color
    for r, c in inner_cells: out[r][c] = frame_color
    for dh in range(inner_h):
        nr = min_fr - 1 - dh
        if 0 <= nr < rows:
            for c in range(min_fc, max_fc + 1):
                if 0 <= c < cols: out[nr][c] = frame_color
        nr = max_fr + 1 + dh
        if 0 <= nr < rows:
            for c in range(min_fc, max_fc + 1):
                if 0 <= c < cols: out[nr][c] = frame_color
    for dw in range(inner_w):
        nc = min_fc - 1 - dw
        if 0 <= nc < cols:
            for r in range(min_fr, max_fr + 1):
                if 0 <= r < rows: out[r][nc] = frame_color
        nc = max_fc + 1 + dw
        if 0 <= nc < cols:
            for r in range(min_fr, max_fr + 1):
                if 0 <= r < rows: out[r][nc] = frame_color
    return out

def output_most_common_pattern(grid, background=0):
    """Find color with most connected instances, return bbox of one instance."""
    from collections import defaultdict
    rows, cols = len(grid), len(grid[0])
    visited = set()
    def bfs8(sr, sc, color):
        comp = []; q = [(sr, sc)]; visited.add((sr, sc))
        while q:
            r, c = q.pop(); comp.append((r, c))
            for dr, dc in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
                nr, nc = r + dr, c + dc
                if (nr, nc) not in visited and 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == color:
                    visited.add((nr, nc)); q.append((nr, nc))
        return comp
    color_comps = defaultdict(list)
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background and (r, c) not in visited:
                comp = bfs8(r, c, grid[r][c])
                color_comps[grid[r][c]].append(comp)
    if not color_comps: return grid
    best_color = max(color_comps, key=lambda c: len(color_comps[c]))
    first_comp = color_comps[best_color][0]
    min_r = min(r for r, c in first_comp); max_r = max(r for r, c in first_comp)
    min_c = min(c for r, c in first_comp); max_c = max(c for r, c in first_comp)
    return [[grid[r][c] for c in range(min_c, max_c + 1)] for r in range(min_r, max_r + 1)]

def assemble_parts_around_pivot(grid, pivot=5, background=0):
    """Find 8-connected components, each with exactly one pivot cell.
    Align all pivots to the same center and overlay to produce output grid."""
    rows, cols = len(grid), len(grid[0])
    visited = set()
    def bfs8(sr, sc):
        comp = []
        q = [(sr, sc)]
        visited.add((sr, sc))
        while q:
            r, c = q.pop()
            comp.append((r, c, grid[r][c]))
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    if dr == 0 and dc == 0: continue
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in visited and grid[nr][nc] != background:
                        visited.add((nr, nc))
                        q.append((nr, nc))
        return comp
    comps = []
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background and (r, c) not in visited:
                comp = bfs8(r, c)
                comps.append(comp)
    if not comps:
        return grid
    comp_data = []
    for comp in comps:
        pivot_cells = [(r, c) for r, c, v in comp if v == pivot]
        if len(pivot_cells) != 1:
            return grid
        pr, pc = pivot_cells[0]
        min_r = min(r for r, c, v in comp)
        min_c = min(c for r, c, v in comp)
        max_r = max(r for r, c, v in comp)
        max_c = max(c for r, c, v in comp)
        pr_l, pc_l = pr - min_r, pc - min_c
        H, W = max_r - min_r + 1, max_c - min_c + 1
        cells = {(r - min_r, c - min_c): v for r, c, v in comp}
        comp_data.append({
            'cells': cells, 'pr_l': pr_l, 'pc_l': pc_l,
            'row_min': -pr_l, 'row_max': H - 1 - pr_l,
            'col_min': -pc_l, 'col_max': W - 1 - pc_l,
        })
    min_row = min(c['row_min'] for c in comp_data)
    max_row = max(c['row_max'] for c in comp_data)
    min_col = min(c['col_min'] for c in comp_data)
    max_col = max(c['col_max'] for c in comp_data)
    out_rows = max_row - min_row + 1
    out_cols = max_col - min_col + 1
    cr, cc = -min_row, -min_col
    out = [[background] * out_cols for _ in range(out_rows)]
    for cd in comp_data:
        for (lr, lc), val in cd['cells'].items():
            or_ = cr + (lr - cd['pr_l'])
            oc = cc + (lc - cd['pc_l'])
            if 0 <= or_ < out_rows and 0 <= oc < out_cols:
                if val != background and out[or_][oc] == background:
                    out[or_][oc] = val
                elif val != background and val != pivot:
                    out[or_][oc] = val
    return out

def project_template_row_onto_marker_rows(grid, background=0):
    """Template row (most 5s) is projected as 2s onto rows that have a 5 in rightmost col."""
    rows, cols = len(grid), len(grid[0])
    from collections import Counter
    # Find template row: row with most 5s
    row_counts = [(sum(1 for c in range(cols) if grid[r][c] == 5), r) for r in range(rows)]
    template_row = max(row_counts)[1]
    template_cols = [c for c in range(cols) if grid[template_row][c] == 5]
    if not template_cols:
        return grid
    out = [row[:] for row in grid]
    for r in range(rows):
        if r == template_row:
            continue
        # Find 5s in this row
        row_5s = [c for c in range(cols) if grid[r][c] == 5]
        if not row_5s:
            continue
        # If this row has a 5 NOT in the template columns, project template as 2s
        non_template_5s = [c for c in row_5s if c not in template_cols]
        if non_template_5s:
            for c in template_cols:
                if grid[r][c] == background:
                    out[r][c] = 2
    return out

def add_color_halos_by_type(grid, background=0):
    """For each color-1 cell add cardinal 7-cross; for each color-2 cell add diagonal 4-cross."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            if v == 1:
                for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nr, nc = r+dr, c+dc
                    if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == background:
                        out[nr][nc] = 7
            elif v == 2:
                for dr, dc in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                    nr, nc = r+dr, c+dc
                    if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == background:
                        out[nr][nc] = 4
    return out

def complete_fourfold_rotational_symmetry(grid, background=0):
    """Identify center of pattern and complete 4-fold (90°) rotational symmetry."""
    rows, cols = len(grid), len(grid[0])
    cells = [(r, c, grid[r][c]) for r in range(rows) for c in range(cols) if grid[r][c] != background]
    if not cells:
        return grid
    # Find center: avg position of all cells
    cr = sum(r for r, c, v in cells) / len(cells)
    cc = sum(c for r, c, v in cells) / len(cells)
    cr_int = round(cr)
    cc_int = round(cc)
    out = [row[:] for row in grid]
    for r, c, v in cells:
        dr, dc = r - cr_int, c - cc_int
        for _ in range(3):  # 3 more rotations
            dr, dc = -dc, dr  # rotate 90° CW
            nr, nc = cr_int + dr, cc_int + dc
            if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == background:
                out[nr][nc] = v
    return out

def expand_cross_pattern_one_level(grid, background=0):
    """For each 3x3 cross (center + 4 cardinal arms), expand to 5x5 crystalline version."""
    rows, cols = len(grid), len(grid[0])
    # Find cross centers: cells with value != bg that have 4 cardinal neighbors of same different color
    out = [row[:] for row in grid]
    for r in range(1, rows-1):
        for c in range(1, cols-1):
            center_v = grid[r][c]
            if center_v == background:
                continue
            # Check for 4-arm cross (arms same color, different from center)
            arms = [(r-1,c),(r+1,c),(r,c-1),(r,c+1)]
            arm_vals = [grid[ar][ac] for ar, ac in arms if 0<=ar<rows and 0<=ac<cols]
            if len(arm_vals) != 4:
                continue
            arm_color = arm_vals[0]
            if arm_color == background or arm_color == center_v:
                continue
            if not all(v == arm_color for v in arm_vals):
                continue
            # This is a cross: center=center_v, arms=arm_color
            # Expand: extended arms at distance 2
            for dr, dc in [(-2,0),(2,0),(0,-2),(0,2)]:
                nr, nc = r+dr, c+dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    out[nr][nc] = arm_color
            # Diagonal cells at distance 1 and 2 get center_v
            for dr, dc in [(-1,-1),(-1,1),(1,-1),(1,1),(-2,-2),(-2,2),(2,-2),(2,2)]:
                nr, nc = r+dr, c+dc
                if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == background:
                    out[nr][nc] = center_v
    return out

def fill_matching_end_rows(grid, background=0):
    """Rows where col-0 and col-last have same non-background color get filled entirely with that color."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(rows):
        left = grid[r][0]
        right = grid[r][cols - 1]
        if left != background and left == right:
            for c in range(cols):
                out[r][c] = left
    return out

def fill_zones_by_two_cells(grid, background=0):
    """Two isolated non-bg cells split grid into zones; each zone: full row at cell pos and extension ±2,
    border-only (col 0 and last) for all other rows in that zone."""
    rows, cols = len(grid), len(grid[0])
    cells = [(r, c, grid[r][c]) for r in range(rows) for c in range(cols) if grid[r][c] != background]
    if len(cells) != 2:
        return grid
    (rA, cA, colorA), (rB, cB, colorB) = sorted(cells, key=lambda x: x[0])
    mid = (rA + rB) / 2.0
    out = [[background] * cols for _ in range(rows)]
    # Zone A: rows 0..floor(mid), Zone B: rows ceil(mid)..rows-1
    zone_a_rows = list(range(0, int(mid) + 1))
    zone_b_rows = list(range(int(mid) + 1, rows))
    # Determine extension rows
    extA = rA - 2  # extension away from B (upward)
    extB = rB + 2  # extension away from A (downward)
    for r in zone_a_rows:
        if r == rA or r == extA:
            for c in range(cols):
                out[r][c] = colorA
        else:
            out[r][0] = colorA
            out[r][cols - 1] = colorA
    for r in zone_b_rows:
        if r == rB or r == extB:
            for c in range(cols):
                out[r][c] = colorB
        else:
            out[r][0] = colorB
            out[r][cols - 1] = colorB
    return out

def sweep_shape_in_marker_direction(grid, background=0, marker=2):
    """Find a 2x2 block with a main color and marker(2) cells; sweep the 2x2
    diagonally in each corner direction indicated by the marker cells."""
    rows, cols = len(grid), len(grid[0])
    non_bg = [(r, c, grid[r][c]) for r in range(rows) for c in range(cols) if grid[r][c] != background]
    if not non_bg:
        return grid
    colors = set(v for _, _, v in non_bg)
    colors.discard(marker)
    if len(colors) != 1:
        return grid
    main_color = next(iter(colors))
    min_r = min(r for r, c, v in non_bg)
    max_r = max(r for r, c, v in non_bg)
    min_c = min(c for r, c, v in non_bg)
    max_c = max(c for r, c, v in non_bg)
    if max_r - min_r != 1 or max_c - min_c != 1:
        return grid
    corners = {
        (min_r, min_c): (-1, -1),
        (min_r, max_c): (-1, +1),
        (max_r, min_c): (+1, -1),
        (max_r, max_c): (+1, +1),
    }
    sweep_dirs = [d for (r, c), d in corners.items() if grid[r][c] == marker]
    if not sweep_dirs:
        return grid
    box_cells = [(min_r, min_c), (min_r, max_c), (max_r, min_c), (max_r, max_c)]
    out = [[background] * cols for _ in range(rows)]
    for dr, dc in sweep_dirs:
        k = 0
        while True:
            any_in = False
            for br, bc in box_cells:
                nr, nc = br + k * dr, bc + k * dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    any_in = True
                    out[nr][nc] = main_color
            if not any_in:
                break
            k += 1
    return out

def align_blobs_to_color1_rows(grid, background=0):
    """Move all colored blobs to occupy the same rows as the blob of color value 1,
    preserving each blob's column positions."""
    rows, cols = len(grid), len(grid[0])
    # Group cells by color
    from collections import defaultdict
    color_cells = defaultdict(list)
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            if v != background:
                color_cells[v].append((r, c))
    if 1 not in color_cells:
        return grid
    # Color-1 row span
    rows_1 = sorted(set(r for r, c in color_cells[1]))
    if not rows_1:
        return grid
    row_min_1 = rows_1[0]
    row_max_1 = rows_1[-1]
    height_1 = row_max_1 - row_min_1 + 1
    out = [[background] * cols for _ in range(rows)]
    for color, cells in color_cells.items():
        # Get this blob's row span
        blob_rows = sorted(set(r for r, c in cells))
        blob_row_min = blob_rows[0]
        # Map each cell to new row: offset within blob → offset within color-1 row span
        for r, c in cells:
            offset = r - blob_row_min
            if offset < height_1:
                new_r = row_min_1 + offset
                out[new_r][c] = color
    return out

def shift_shapes_except_bottom_edge(grid, background=0):
    """For each color: shift all non-bottom-row cells right by 1,
    clipping at the bottom row's max column. Bottom row stays fixed."""
    from collections import defaultdict
    rows, cols = len(grid), len(grid[0])
    color_cells = defaultdict(list)
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            if v != background:
                color_cells[v].append((r, c))
    out = [[background] * cols for _ in range(rows)]
    for color, cells in color_cells.items():
        max_row = max(r for r, c in cells)
        bottom_cells = [(r, c) for r, c in cells if r == max_row]
        max_col_bottom = max(c for r, c in bottom_cells)
        for r, c in cells:
            if r == max_row:
                out[r][c] = color
            else:
                new_c = c + 1 if c + 1 <= max_col_bottom else c
                out[r][new_c] = color
    return out

def split_blob_into_nodes_and_edges(grid, background=0, blob_color=5):
    """Split a connected 5-blob into 2x2 node blocks (→8) and 1-wide path edges (→2).
    Greedily finds non-overlapping 2x2 all-blob_color squares scanning bottom-right to top-left,
    choosing the configuration where remaining cells have ≤ 2 same-color neighbors."""
    rows, cols = len(grid), len(grid[0])
    cells = set((r, c) for r in range(rows) for c in range(cols) if grid[r][c] == blob_color)
    if not cells:
        return grid

    # Find all valid 2x2 all-blob_color blocks (by top-left corner)
    def all_blocks():
        result = []
        for r in range(rows - 1):
            for c in range(cols - 1):
                if all((r+dr, c+dc) in cells for dr in [0,1] for dc in [0,1]):
                    result.append((r, c))
        return result

    def quad_cells(r, c):
        return frozenset([(r, c), (r, c+1), (r+1, c), (r+1, c+1)])

    def remaining_forms_straight_paths(remaining):
        """Check no cell has neighbors in both horizontal and vertical directions."""
        rs = set(remaining)
        for (r, c) in remaining:
            nbrs = [(nr, nc) for nr, nc in [(r-1,c),(r+1,c),(r,c-1),(r,c+1)] if (nr,nc) in rs]
            if len(nbrs) >= 3:
                return False
            if len(nbrs) == 2:
                (r1,c1),(r2,c2) = nbrs
                # Both same direction?
                if not (r1 == r2 or c1 == c2):
                    return False
        return True

    def count_isolated(remaining):
        rs = set(remaining)
        return sum(1 for (r, c) in remaining
                   if not any((nr, nc) in rs for nr, nc in [(r-1,c),(r+1,c),(r,c-1),(r,c+1)]))

    # Find minimum non-overlapping block set where remaining cells form straight paths;
    # among ties prefer zero isolated remaining cells
    blocks = all_blocks()
    if not blocks:
        return grid

    from itertools import combinations
    best = set()
    for k in range(1, len(blocks) + 1):
        candidates_k = []
        for combo in combinations(blocks, k):
            claimed = set()
            valid = True
            for rc in combo:
                q = quad_cells(*rc)
                if q & claimed:
                    valid = False
                    break
                claimed |= q
            if not valid:
                continue
            remaining = list(cells - claimed)
            if remaining_forms_straight_paths(remaining):
                iso = count_isolated(remaining)
                candidates_k.append((iso, claimed))
        if candidates_k:
            candidates_k.sort(key=lambda x: x[0])
            best = candidates_k[0][1]
            break

    block_cells = best
    if not block_cells:
        return grid

    out = [row[:] for row in grid]
    for r, c in cells:
        if (r, c) in block_cells:
            out[r][c] = 8
        else:
            out[r][c] = 2
    return out

def add_cardinal_diagonal_markers_1_2(grid, background=0):
    """For each 1-cell: add 7 at the 4 cardinal (N/E/S/W) empty neighbors.
    For each 2-cell: add 4 at the 4 diagonal (NE/NW/SE/SW) empty neighbors.
    All other values are preserved unchanged."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            if v == 1:
                for nr, nc in [(r-1,c),(r+1,c),(r,c-1),(r,c+1)]:
                    if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == background:
                        out[nr][nc] = 7
            elif v == 2:
                for nr, nc in [(r-1,c-1),(r-1,c+1),(r+1,c-1),(r+1,c+1)]:
                    if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == background:
                        out[nr][nc] = 4
    return out

def move_2blob_adjacent_to_8blob(grid, background=0):
    """Move the connected blob of color 2 to be adjacent to the blob of color 8.
    If the blobs' bounding boxes overlap in column range, move 2-blob vertically
    until it touches 8-blob. If they overlap in row range, move horizontally.
    The 8-blob stays fixed."""
    rows, cols = len(grid), len(grid[0])
    cells2 = [(r,c) for r in range(rows) for c in range(cols) if grid[r][c]==2]
    cells8 = [(r,c) for r in range(rows) for c in range(cols) if grid[r][c]==8]
    if not cells2 or not cells8:
        return grid
    r2min,r2max = min(r for r,c in cells2),max(r for r,c in cells2)
    c2min,c2max = min(c for r,c in cells2),max(c for r,c in cells2)
    r8min,r8max = min(r for r,c in cells8),max(r for r,c in cells8)
    c8min,c8max = min(c for r,c in cells8),max(c for r,c in cells8)
    col_overlap = max(c2min,c8min) <= min(c2max,c8max)
    row_overlap = max(r2min,r8min) <= min(r2max,r8max)
    out = [[background]*cols for _ in range(rows)]
    for r,c in cells8:
        out[r][c] = 8
    if col_overlap:
        dr = (r8min-1-r2max) if r2min < r8min else (r8max+1-r2min)
        for r,c in cells2:
            nr = r+dr
            if 0<=nr<rows: out[nr][c] = 2
    elif row_overlap:
        dc = (c8min-1-c2max) if c2min < c8min else (c8max+1-c2min)
        for r,c in cells2:
            nc = c+dc
            if 0<=nc<cols: out[r][nc] = 2
    else:
        for r,c in cells2: out[r][c] = 2
    return out

def expand_cross_to_diamond(grid, background=0):
    """For each cross-shaped pattern (a center cell C surrounded by 4 same-color arm cells A at
    distance 1 in cardinal directions), extend by placing:
    - A at cardinal distance 2 from center
    - C at all 8 diagonal positions at distance 1 and 2 from center."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            if v == background:
                continue
            nbrs = [(r+dr, c+dc) for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]]
            arm_vals = [grid[nr][nc] for nr,nc in nbrs
                        if 0<=nr<rows and 0<=nc<cols and grid[nr][nc]!=background and grid[nr][nc]!=v]
            if len(arm_vals)==4 and len(set(arm_vals))==1:
                arm_v = arm_vals[0]
                for dr,dc in [(-2,0),(2,0),(0,-2),(0,2)]:
                    nr,nc = r+dr,c+dc
                    if 0<=nr<rows and 0<=nc<cols and out[nr][nc]==background:
                        out[nr][nc] = arm_v
                for dr,dc in [(-1,-1),(-1,1),(1,-1),(1,1),(-2,-2),(-2,2),(2,-2),(2,2)]:
                    nr,nc = r+dr,c+dc
                    if 0<=nr<rows and 0<=nc<cols and out[nr][nc]==background:
                        out[nr][nc] = v
    return out

def extend_cells_to_lines_col2_row_others(grid, background=0):
    """Each isolated non-background cell:
    - Color 2: fill its entire column with 2.
    - Other colors: fill their entire row with that color.
    Row fills take priority over column fills at intersections."""
    rows, cols = len(grid), len(grid[0])
    out = [[background]*cols for _ in range(rows)]
    # First fill columns for color 2
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == 2:
                for nr in range(rows):
                    out[nr][c] = 2
    # Then fill rows for other colors (override)
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            if v != background and v != 2:
                for nc in range(cols):
                    out[r][nc] = v
    return out

def fill_grid_two_color_stripe(grid, background=0):
    """Two isolated non-background cells define an alternating stripe pattern.
    The dimension with smaller anchor separation determines the stripe direction:
    - Column stripes (col_diff <= row_diff): fill all rows with alternating color columns.
    - Row stripes (col_diff == 0 or row_diff < col_diff): fill all cols with alternating color rows.
    Pattern starts from the topmost/leftmost anchor and repeats with the anchor separation as half-period."""
    rows, cols = len(grid), len(grid[0])
    non_bg = [(r,c,grid[r][c]) for r in range(rows) for c in range(cols) if grid[r][c]!=background]
    if len(non_bg) != 2:
        return grid
    (r1,c1,v1),(r2,c2,v2) = non_bg
    if r1 > r2 or (r1==r2 and c1>c2):
        r1,c1,v1,r2,c2,v2 = r2,c2,v2,r1,c1,v1
    col_diff = abs(c2-c1)
    row_diff = abs(r2-r1)
    out = [[background]*cols for _ in range(rows)]
    if col_diff > 0 and (col_diff <= row_diff or row_diff == 0):
        sc = min(c1,c2)
        cv1 = v1 if c1<=c2 else v2
        cv2 = v2 if c1<=c2 else v1
        for r in range(rows):
            for c in range(sc, cols):
                off = (c-sc) % (2*col_diff)
                if off==0: out[r][c]=cv1
                elif off==col_diff: out[r][c]=cv2
    else:
        sr = min(r1,r2)
        rv1 = v1 if r1<=r2 else v2
        rv2 = v2 if r1<=r2 else v1
        for r in range(sr, rows):
            off = (r-sr) % (2*row_diff)
            if off==0:
                for c in range(cols): out[r][c]=rv1
            elif off==row_diff:
                for c in range(cols): out[r][c]=rv2
    return out

def shift_rows_down_one(grid, background=0):
    """Shift all row content down by 1. The first row becomes background; the last row is dropped."""
    rows, cols = len(grid), len(grid[0])
    return [[background] * cols] + [list(grid[r]) for r in range(rows - 1)]

def fill_between_collinear_pairs(grid, endpoint_color=8, fill_color=3, background=0):
    """Find pairs of endpoint_color cells in the same row or column.
    Fill the cells between each pair with fill_color."""
    from collections import defaultdict
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    by_row = defaultdict(list)
    by_col = defaultdict(list)
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == endpoint_color:
                by_row[r].append(c)
                by_col[c].append(r)
    for r, cs in by_row.items():
        if len(cs) >= 2:
            cs.sort()
            for c in range(cs[0] + 1, cs[-1]):
                if out[r][c] == background:
                    out[r][c] = fill_color
    for c, rs in by_col.items():
        if len(rs) >= 2:
            rs.sort()
            for r in range(rs[0] + 1, rs[-1]):
                if out[r][c] == background:
                    out[r][c] = fill_color
    return out

def extend_cells_to_cross_intersect2(grid, background=0):
    """Each non-background cell extends its entire row and column with its color.
    Where two different-colored extensions cross, place 2."""
    rows, cols = len(grid), len(grid[0])
    row_color = {}
    col_color = {}
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            if v != background:
                row_color[r] = v
                col_color[c] = v
    out = [[background] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            rc = row_color.get(r)
            cc = col_color.get(c)
            if rc is not None and cc is not None:
                out[r][c] = rc if rc == cc else 2
            elif rc is not None:
                out[r][c] = rc
            elif cc is not None:
                out[r][c] = cc
    return out

def count_2x2_blocks_output_row(grid, target_color=1, background=0):
    """Count non-overlapping 2x2 blocks of target_color.
    Output a single-row grid of length 5 with count 1s followed by 0s."""
    rows, cols = len(grid), len(grid[0])
    count, claimed = 0, set()
    for r in range(rows - 1):
        for c in range(cols - 1):
            if (r, c) not in claimed and (grid[r][c] == grid[r][c+1] == grid[r+1][c] == grid[r+1][c+1] == target_color):
                count += 1
                claimed.update([(r, c), (r, c+1), (r+1, c), (r+1, c+1)])
    return [[1] * count + [0] * (5 - count)]

def float_2s_up_against_1s(grid, background=0):
    """In each column, move all 2-cells upward to stack just below the last 1-cell.
    1-cells remain fixed. If no 1s in column, 2s stack at the top."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for c in range(cols):
        col = [grid[r][c] for r in range(rows)]
        if 2 not in col:
            continue
        twos_count = col.count(2)
        ones = [r for r in range(rows) if col[r] == 1]
        new_col = col[:]
        for r in range(rows):
            if new_col[r] == 2:
                new_col[r] = 0
        fill_start = (max(ones) + 1) if ones else 0
        for i in range(twos_count):
            if fill_start + i < rows:
                new_col[fill_start + i] = 2
        for r in range(rows):
            out[r][c] = new_col[r]
    return out

def fill_l_corner(grid, l_color=8, fill_color=1, background=0):
    """For each 2x2 subgrid with exactly 3 cells of l_color and 1 background cell,
    fill the background cell with fill_color."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(rows - 1):
        for c in range(cols - 1):
            cells = [(r, c), (r, c+1), (r+1, c), (r+1, c+1)]
            vals = [grid[rr][cc] for rr, cc in cells]
            if vals.count(l_color) == 3 and vals.count(background) == 1:
                for (rr, cc), v in zip(cells, vals):
                    if v == background:
                        out[rr][cc] = fill_color
    return out

def project_marker_cols_to_marker_rows(grid, marker=5, fill=2, background=0):
    """Row with the most marker cells defines the 'header' column pattern.
    For each non-header row that has at least one marker cell,
    fill background cells at the header's marker columns with fill."""
    rows, cols = len(grid), len(grid[0])
    header_row = max(range(rows), key=lambda r: sum(1 for c in range(cols) if grid[r][c] == marker))
    header_cols = [c for c in range(cols) if grid[header_row][c] == marker]
    out = [row[:] for row in grid]
    for r in range(rows):
        if r == header_row:
            continue
        if any(grid[r][c] == marker for c in range(cols)):
            for c in header_cols:
                if grid[r][c] == background:
                    out[r][c] = fill
    return out

def fill_grid_sections_fixed_colors(grid, background=0):
    """Grid divided by all-8 rows and cols into a 3x3 arrangement.
    Fill center column sections with colors 2 (top), 6 (middle), 1 (bottom).
    Fill middle row left section with 4 and right section with 3."""
    rows, cols = len(grid), len(grid[0])
    sep_rows = sorted(r for r in range(rows) if all(grid[r][c] == 8 for c in range(cols)))
    sep_cols = sorted(c for c in range(cols) if all(grid[r][c] == 8 for r in range(rows)))
    if len(sep_rows) != 2 or len(sep_cols) != 2:
        return grid

    def get_bands(seps, length):
        bands, prev = [], 0
        for s in sorted(seps):
            if s > prev:
                bands.append((prev, s))
            prev = s + 1
        if prev < length:
            bands.append((prev, length))
        return bands

    row_bands = get_bands(sep_rows, rows)
    col_bands = get_bands(sep_cols, cols)
    if len(row_bands) != 3 or len(col_bands) != 3:
        return grid
    out = [row[:] for row in grid]

    def fill_section(rb, cb, color):
        for r in range(rb[0], rb[1]):
            for c in range(cb[0], cb[1]):
                if out[r][c] == background:
                    out[r][c] = color

    fill_section(row_bands[0], col_bands[1], 2)
    fill_section(row_bands[1], col_bands[0], 4)
    fill_section(row_bands[1], col_bands[1], 6)
    fill_section(row_bands[1], col_bands[2], 3)
    fill_section(row_bands[2], col_bands[1], 1)
    return out

def drop_1s_to_5_floor(grid, background=0):
    """Find the all-5 floor row; drop all 1s from above to land on that floor row."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    floor_rows = [r for r in range(rows) if all(grid[r][c] == 5 for c in range(cols))]
    if not floor_rows:
        return grid
    floor_row = max(floor_rows)
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == 1 and r < floor_row:
                out[r][c] = background
                out[floor_row][c] = 1
    return out

def add_moore_border_around_5(grid, background=0):
    """Place 1s in all 8 Moore neighbors of each 5-cell (if background)."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == 5:
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == background:
                            out[nr][nc] = 1
    return out

def flood_fill_from_seeds(grid, wall_color=1, background=0):
    """Flood fill from seed cells (non-background, non-wall) bounded by wall enclosures."""
    from collections import deque
    rows, cols = len(grid), len(grid[0])
    seeds = [(r, c, grid[r][c]) for r in range(rows) for c in range(cols)
             if grid[r][c] != background and grid[r][c] != wall_color]
    if not seeds:
        return grid
    out = [row[:] for row in grid]
    for sr, sc, color in seeds:
        left_1 = max((c for c in range(sc) if grid[sr][c] == wall_color), default=0)
        right_1 = min((c for c in range(sc + 1, cols) if grid[sr][c] == wall_color), default=cols - 1)
        cmin, cmax = left_1, right_1
        rmin_wall = None
        r = sr - 1
        while r >= 0:
            if grid[r][cmin] == wall_color or grid[r][cmax] == wall_color:
                rmin_wall = r
                r -= 1
            else:
                break
        rmin_bound = (rmin_wall - 1) if rmin_wall is not None else sr
        visited = set()
        q = deque([(sr, sc)])
        visited.add((sr, sc))
        while q:
            r, c = q.popleft()
            if grid[r][c] != wall_color:
                out[r][c] = color
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if (nr, nc) in visited:
                    continue
                if not (rmin_bound <= nr < rows and cmin <= nc <= cmax):
                    continue
                if grid[nr][nc] == wall_color:
                    continue
                visited.add((nr, nc))
                q.append((nr, nc))
    return out

def fill_1s_in_8rows_with_3(grid, background=0):
    """In rows containing any 8, change all 1s within the 8-column span to 3."""
    rows, cols = len(grid), len(grid[0])
    eight_rows = [r for r in range(rows) if 8 in grid[r]]
    if not eight_rows: return grid
    eight_cols = [c for r in eight_rows for c in range(cols) if grid[r][c] == 8]
    if not eight_cols: return grid
    cmin, cmax = min(eight_cols), max(eight_cols)
    out = [row[:] for row in grid]
    for r in eight_rows:
        for c in range(cmin, cmax + 1):
            if out[r][c] == 1:
                out[r][c] = 3
    return out

def add_knight_jump_8s_to_diagonal_pairs(grid, pair_color=3, mark_color=8, background=0):
    """Find 4-connected components of pair_color. For each pair of components with
    diagonal offset (|dr|=|dc|=steps, steps=sqrt(comp_size)), place mark_color at:
    from each cell A in comp1: A + steps*(-udr, 2*udc)
    from each cell B in comp2: B + steps*(udr, -2*udc)."""
    import math
    rows, cols = len(grid), len(grid[0])
    cells = [(r,c) for r in range(rows) for c in range(cols) if grid[r][c] == pair_color]
    cell_set = set(cells)
    visited = set()
    components = []
    def bfs(start):
        comp = [start]; q = [start]; visited.add(start)
        while q:
            r,c = q.pop()
            for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                nr,nc = r+dr,c+dc
                if (nr,nc) in cell_set and (nr,nc) not in visited:
                    visited.add((nr,nc)); q.append((nr,nc)); comp.append((nr,nc))
        return sorted(comp)
    for cell in cells:
        if cell not in visited:
            components.append(bfs(cell))
    if len(components) < 2: return grid
    out = [row[:] for row in grid]
    for i in range(len(components)):
        for j in range(i+1, len(components)):
            c1, c2 = sorted(components[i]), sorted(components[j])
            if len(c1) != len(c2): continue
            offset = (c2[0][0]-c1[0][0], c2[0][1]-c1[0][1])
            dr, dc = offset
            if abs(dr) != abs(dc) or dr == 0: continue
            steps = abs(dr)
            if steps != int(round(math.sqrt(len(c1)))): continue
            if not all((c2[k][0]-c1[k][0], c2[k][1]-c1[k][1]) == offset for k in range(len(c1))): continue
            udr, udc = dr//steps, dc//steps
            for A, B in zip(c1, c2):
                na_r = A[0] + steps*(-udr)
                na_c = A[1] + steps*(2*udc)
                if 0 <= na_r < rows and 0 <= na_c < cols:
                    out[na_r][na_c] = mark_color
                nb_r = B[0] + steps*udr
                nb_c = B[1] + steps*(-2*udc)
                if 0 <= nb_r < rows and 0 <= nb_c < cols:
                    out[nb_r][nb_c] = mark_color
    return out

def fill_rectangle_interior_and_shoot_gap(grid, wall_color=5, fill_color=8, background=0):
    """Fill interior of wall_color rectangle with fill_color.
    Find border gaps and shoot fill_color outward from each gap to grid edge."""
    rows, cols = len(grid), len(grid[0])
    walls = [(r,c) for r in range(rows) for c in range(cols) if grid[r][c] == wall_color]
    if not walls: return grid
    rmin = min(r for r,c in walls); rmax = max(r for r,c in walls)
    cmin = min(c for r,c in walls); cmax = max(c for r,c in walls)
    out = [row[:] for row in grid]
    for r in range(rmin+1, rmax):
        for c in range(cmin+1, cmax):
            if out[r][c] == background: out[r][c] = fill_color
    for r in range(rmin, rmax+1):
        for c in range(cmin, cmax+1):
            on_border = (r==rmin or r==rmax or c==cmin or c==cmax)
            if on_border and grid[r][c] == background:
                out[r][c] = fill_color
                if r == rmin: dr, dc = -1, 0
                elif r == rmax: dr, dc = 1, 0
                elif c == cmin: dr, dc = 0, -1
                else: dr, dc = 0, 1
                nr, nc = r+dr, c+dc
                while 0 <= nr < rows and 0 <= nc < cols:
                    if out[nr][nc] == background: out[nr][nc] = fill_color
                    nr += dr; nc += dc
    return out

def fill_gap_between_two_blobs_with_8(grid, background=0, fill_color=8):
    """Find two non-background blobs. Fill the gap between them with fill_color.
    The gap region is determined by:
    - If separated vertically: gap rows x inner column overlap (strip 1 from each side)
    - If separated horizontally: inner row overlap (strip 1 from each side) x gap columns"""
    from collections import deque
    rows, cols = len(grid), len(grid[0])
    visited = [[False]*cols for _ in range(rows)]
    blobs = []
    for sr in range(rows):
        for sc in range(cols):
            if not visited[sr][sc] and grid[sr][sc] != background:
                color = grid[sr][sc]
                cells = []
                q = deque([(sr, sc)])
                visited[sr][sc] = True
                while q:
                    r, c = q.popleft()
                    cells.append((r, c))
                    for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nr, nc = r+dr, c+dc
                        if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc] and grid[nr][nc] == color:
                            visited[nr][nc] = True
                            q.append((nr, nc))
                blobs.append(cells)
    if len(blobs) != 2:
        return grid
    b1, b2 = blobs[0], blobs[1]
    r1min, r1max = min(r for r,c in b1), max(r for r,c in b1)
    r2min, r2max = min(r for r,c in b2), max(r for r,c in b2)
    c1min, c1max = min(c for r,c in b1), max(c for r,c in b1)
    c2min, c2max = min(c for r,c in b2), max(c for r,c in b2)
    out = [row[:] for row in grid]
    # Check if separated vertically (no row overlap)
    if r1max < r2min or r2max < r1min:
        gap_rmin = (r1max + 1) if r1max < r2min else (r2max + 1)
        gap_rmax = (r2min - 1) if r1max < r2min else (r1min - 1)
        col_overlap_min = max(c1min, c2min)
        col_overlap_max = min(c1max, c2max)
        inner_cmin = col_overlap_min + 1
        inner_cmax = col_overlap_max - 1
        if inner_cmin <= inner_cmax and gap_rmin <= gap_rmax:
            for r in range(gap_rmin, gap_rmax + 1):
                for c in range(inner_cmin, inner_cmax + 1):
                    if out[r][c] == background:
                        out[r][c] = fill_color
    else:
        # Separated horizontally
        gap_cmin = (c1max + 1) if c1max < c2min else (c2max + 1)
        gap_cmax = (c2min - 1) if c1max < c2min else (c1min - 1)
        row_overlap_min = max(r1min, r2min)
        row_overlap_max = min(r1max, r2max)
        inner_rmin = row_overlap_min + 1
        inner_rmax = row_overlap_max - 1
        if inner_rmin <= inner_rmax and gap_cmin <= gap_cmax:
            for r in range(inner_rmin, inner_rmax + 1):
                for c in range(gap_cmin, gap_cmax + 1):
                    if out[r][c] == background:
                        out[r][c] = fill_color
    return out


def swap_arc_color_pairs(grid):
    """Swap ARC complementary color pairs: (1,5),(2,6),(3,4),(8,9). Other values unchanged."""
    swap_map = {1:5,5:1,2:6,6:2,3:4,4:3,8:9,9:8}
    return [[swap_map.get(v, v) for v in row] for row in grid]


def expand_points_to_row_col_lines(grid, background=0, col_color=2):
    """For each point of col_color, expand to full column. For other colors, expand to full row.
    Rows take priority over columns at intersections."""
    from collections import defaultdict
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    color_positions = defaultdict(list)
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background:
                color_positions[grid[r][c]].append((r, c))
    # Draw columns first (lower priority)
    for v, positions in color_positions.items():
        if v == col_color:
            for r, c in positions:
                for rr in range(rows):
                    if out[rr][c] == background:
                        out[rr][c] = v
    # Draw rows second (higher priority, overwrite cols)
    for v, positions in color_positions.items():
        if v != col_color:
            for r, c in positions:
                for cc in range(cols):
                    out[r][cc] = v
    return out


def add_orthogonal_7s_and_diagonal_4s(grid, background=0):
    """For each 1-cell, place 7 at orthogonal neighbors. For each 2-cell, place 4 at diagonal neighbors."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == 1:
                for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nr, nc = r+dr, c+dc
                    if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == background:
                        out[nr][nc] = 7
            elif grid[r][c] == 2:
                for dr, dc in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                    nr, nc = r+dr, c+dc
                    if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == background:
                        out[nr][nc] = 4
    return out


def align_blocks_to_anchor_rows(grid, anchor_color=1, background=0):
    """Find the anchor_color block's row min. Shift all other color blocks to start at the same row min."""
    from collections import defaultdict
    rows, cols = len(grid), len(grid[0])
    color_cells = defaultdict(list)
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background:
                color_cells[grid[r][c]].append((r, c))
    if anchor_color not in color_cells:
        return grid
    anchor_rmin = min(r for r, c in color_cells[anchor_color])
    out = [row[:] for row in grid]
    for color, cells in color_cells.items():
        if color == anchor_color:
            continue
        block_rmin = min(r for r, c in cells)
        dr = anchor_rmin - block_rmin
        if dr == 0:
            continue
        for r, c in cells:
            out[r][c] = background
        for r, c in cells:
            nr = r + dr
            if 0 <= nr < rows:
                out[nr][c] = color
    return out


def extract_quadrant_with_unique(grid, background=0):
    """Grid divided by a cross of same-value lines. Find and return the quadrant
    containing a cell of a color that is not the majority non-divider color."""
    from collections import Counter
    rows, cols = len(grid), len(grid[0])
    div_row = next((r for r in range(rows) if len(set(grid[r])) == 1 and grid[r][0] != 0), None)
    div_col = next((c for c in range(cols) if len(set(grid[r][c] for r in range(rows))) == 1 and grid[0][c] != 0), None)
    if div_row is None or div_col is None:
        return grid
    div_val = grid[div_row][div_col]
    counter = Counter(grid[r][c] for r in range(rows) for c in range(cols) if grid[r][c] != div_val)
    majority = counter.most_common(1)[0][0]
    quadrants = [
        (list(range(div_row)), list(range(div_col))),
        (list(range(div_row)), list(range(div_col+1, cols))),
        (list(range(div_row+1, rows)), list(range(div_col))),
        (list(range(div_row+1, rows)), list(range(div_col+1, cols))),
    ]
    for rs, cs in quadrants:
        if not rs or not cs:
            continue
        if any(grid[r][c] != majority and grid[r][c] != div_val for r in rs for c in cs):
            return [[grid[r][c] for c in cs] for r in rs]
    return grid


def fill_between_same_color_collinear_pairs(grid, background=0):
    """For each pair of cells with the same color in the same row or column,
    fill all background cells between them. Vertical fills take priority at intersections."""
    from collections import defaultdict
    rows, cols = len(grid), len(grid[0])
    color_by_row = defaultdict(list)
    color_by_col = defaultdict(list)
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            if v != background:
                color_by_row[(r, v)].append(c)
                color_by_col[(c, v)].append(r)
    out = [row[:] for row in grid]
    # Vertical fills first (higher priority at intersections)
    for (c, v), rs in color_by_col.items():
        if len(rs) >= 2:
            rmin, rmax = min(rs), max(rs)
            for r in range(rmin, rmax + 1):
                if out[r][c] == background:
                    out[r][c] = v
    # Horizontal fills second (won't overwrite vertical)
    for (r, v), cs in color_by_row.items():
        if len(cs) >= 2:
            cmin, cmax = min(cs), max(cs)
            for c in range(cmin, cmax + 1):
                if out[r][c] == background:
                    out[r][c] = v
    return out


def mirror_top_rows_to_bottom(grid, background=0):
    """Find non-background rows at the top. Copy them reversed to the bottom rows."""
    rows, cols = len(grid), len(grid[0])
    nz_rows = [r for r in range(rows) if any(v != background for v in grid[r])]
    if not nz_rows:
        return grid
    k = len(nz_rows)
    out = [row[:] for row in grid]
    for j in range(k):
        target_row = rows - k + j
        source_row = nz_rows[k - 1 - j]
        out[target_row] = grid[source_row][:]
    return out


def mirror_flip_and_concat(grid, background=0):
    """Concatenate flip_updown(grid) + grid vertically."""
    return list(reversed([row[:] for row in grid])) + [row[:] for row in grid]


def fill_largest_zero_rect_with_6(grid, background=0, fill_color=6):
    """Find the largest area all-background rectangle in non-marker rows (rows
    containing only 0 or 1) and fill it with fill_color (6). Uses histogram method."""
    rows, cols = len(grid), len(grid[0])
    normal_vals = {0, 1}
    marker_rows = set()
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] not in normal_vals:
                marker_rows.add(r)
                break

    def max_rect_hist(heights):
        stack, max_area, best = [], 0, None
        for i in range(len(heights) + 1):
            h = heights[i] if i < len(heights) else 0
            start = i
            while stack and stack[-1][1] >= h:
                idx, height = stack.pop()
                area = height * (i - idx)
                if area > max_area:
                    max_area = area
                    best = (area, idx, i - 1, height)
                start = idx
            stack.append((start, h))
        return best

    heights = [0] * cols
    best_area, best_region = 0, None
    for r in range(rows):
        if r in marker_rows:
            heights = [0] * cols
        else:
            for c in range(cols):
                heights[c] = heights[c] + 1 if grid[r][c] == background else 0
            result = max_rect_hist(heights)
            if result and result[0] > best_area:
                area, left, right, height = result
                best_area = area
                best_region = (r - height + 1, r, left, right)

    if not best_region:
        return [row[:] for row in grid]
    out = [row[:] for row in grid]
    top, bot, left, right = best_region
    for r in range(top, bot + 1):
        for c in range(left, right + 1):
            out[r][c] = fill_color
    return out


def classify_symmetry_1_or_7(grid, background=0):
    """Output [[1]] if grid is left-right (horizontal) symmetric, [[7]] otherwise."""
    flipped = [row[::-1] for row in grid]
    return [[1]] if grid == flipped else [[7]]


def tile_with_4_rotations(grid):
    """Tile 2x2 with 4 rotations: TL=original, TR=90CW, BL=90CCW, BR=180.
    Output is double the size in each dimension."""
    rows, cols = len(grid), len(grid[0])

    def rot90cw(g):
        return [[g[rows - 1 - c][r] for c in range(rows)] for r in range(cols)]

    def rot90ccw(g):
        return [[g[c][cols - 1 - r] for c in range(rows)] for r in range(cols)]

    def rot180(g):
        return [row[::-1] for row in reversed(g)]

    tl = [row[:] for row in grid]
    tr = rot90cw(grid)
    bl = rot90ccw(grid)
    br = rot180(grid)
    out = []
    for r in range(rows):
        out.append(tl[r] + tr[r])
    for r in range(rows):
        out.append(bl[r] + br[r])
    return out


def extract_blob_adjacent_to_5(grid, marker=5, background=0):
    """Find the marker-5 cell. BFS with 8-connectivity to find the blob of non-bg cells
    touching the marker. Return bounding box of that blob (excluding the marker position)."""
    from collections import deque
    rows, cols = len(grid), len(grid[0])
    r5, c5 = None, None
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == marker:
                r5, c5 = r, c
                break
        if r5 is not None:
            break
    if r5 is None:
        return [row[:] for row in grid]

    blob_color = None
    for dr in [-1, 0, 1]:
        for dc in [-1, 0, 1]:
            if dr == 0 and dc == 0:
                continue
            nr, nc = r5 + dr, c5 + dc
            if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] not in (background, marker):
                blob_color = grid[nr][nc]
                break
        if blob_color is not None:
            break
    if blob_color is None:
        return [[background]]

    queue = deque([(r5, c5)])
    visited = {(r5, c5)}
    blob = []
    while queue:
        r, c = queue.popleft()
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in visited:
                    if grid[nr][nc] == blob_color:
                        visited.add((nr, nc))
                        blob.append((nr, nc))
                        queue.append((nr, nc))

    if not blob:
        return [[background]]
    rmin = min(r for r, c in blob)
    rmax = max(r for r, c in blob)
    cmin = min(c for r, c in blob)
    cmax = max(c for r, c in blob)
    out = [[background] * (cmax - cmin + 1) for _ in range(rmax - rmin + 1)]
    for r, c in blob:
        out[r - rmin][c - cmin] = blob_color
    return out


def output_max_color_2x2(grid, background=0):
    """Find the maximum non-background color and return a 2x2 grid filled with it."""
    max_color = max((v for row in grid for v in row if v != background), default=background)
    return [[max_color, max_color], [max_color, max_color]]


def fill_grid_with_most_frequent(grid):
    """Return a same-size grid filled with the most frequently occurring value."""
    from collections import Counter
    flat = [v for row in grid for v in row]
    most_common = Counter(flat).most_common(1)[0][0]
    return [[most_common] * len(grid[0]) for _ in range(len(grid))]


def tile_with_lr_ud_reflection(grid):
    """Double the grid using LR+UD reflections. Output is 2x in each dimension.
    Each row becomes row+reversed(row). Then top block + UD flip."""
    top = [row[:] + row[::-1] for row in grid]
    bottom = list(reversed(top))
    return top + bottom


def mark_zeros_of_two_sections_with_3(grid, divider_color=4, fill_color=3, background=0):
    """Find the divider row (all divider_color). Section1 = above, Section2 = below.
    Output: fill_color where BOTH sections are background, else background."""
    rows, cols = len(grid), len(grid[0])
    div_row = None
    for r in range(rows):
        if all(grid[r][c] == divider_color for c in range(cols)):
            div_row = r
            break
    if div_row is None:
        return [row[:] for row in grid]
    s1 = grid[:div_row]
    s2 = grid[div_row + 1: div_row + 1 + len(s1)]
    h = len(s1)
    out = [[background] * cols for _ in range(h)]
    for r in range(h):
        for c in range(cols):
            if r < len(s2) and s1[r][c] == background and s2[r][c] == background:
                out[r][c] = fill_color
    return out


def extract_half_tile(grid):
    """If grid is a 2x horizontal or vertical tiling, return the fundamental tile."""
    rows, cols = len(grid), len(grid[0])
    if cols % 2 == 0:
        half = cols // 2
        left = [row[:half] for row in grid]
        right = [row[half:] for row in grid]
        if left == right:
            return left
    if rows % 2 == 0:
        half = rows // 2
        top = grid[:half]
        bottom = grid[half:]
        if top == bottom:
            return [row[:] for row in top]
    return [row[:] for row in grid]


def shift_down_and_fill_parity_4s(grid, fill_color=4, background=0):
    """Find single non-bg cell at (r0,c0), shift it to (r0+1,c0).
    Fill rows 0..r0 with fill_color at columns with same parity as c0."""
    rows, cols = len(grid), len(grid[0])
    r0, c0, val = None, None, None
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background:
                r0, c0, val = r, c, grid[r][c]
                break
        if r0 is not None:
            break
    if r0 is None:
        return [row[:] for row in grid]
    out = [[background] * cols for _ in range(rows)]
    if r0 + 1 < rows:
        out[r0 + 1][c0] = val
    parity = c0 % 2
    for r in range(r0 + 1):
        for c in range(cols):
            if c % 2 == parity:
                out[r][c] = fill_color
    return out


def fill_border_with_8(grid, background=0, fill_color=8):
    """Fill the outer border of the grid with fill_color, keep interior as background."""
    rows, cols = len(grid), len(grid[0])
    out = [[v for v in row] for row in grid]
    for r in range(rows):
        for c in range(cols):
            if r == 0 or r == rows - 1 or c == 0 or c == cols - 1:
                out[r][c] = fill_color
    return out


def mirror_concat_lr(grid):
    """Append each row with its reverse: output is same height, double width."""
    return [row[:] + row[::-1] for row in grid]


def concat_grid_with_ud_flip(grid):
    """Append the UD-flipped (upside-down) version of the grid below it."""
    return [row[:] for row in grid] + [row[:] for row in reversed(grid)]


def rle_compress_grid(grid):
    """RLE compress: remove consecutive duplicate rows, then consecutive duplicate cells."""
    deduped = []
    for row in grid:
        if not deduped or list(row) != list(deduped[-1]):
            deduped.append(list(row))
    out = []
    for row in deduped:
        compressed = [row[0]] if row else []
        for v in row[1:]:
            if v != compressed[-1]:
                compressed.append(v)
        out.append(compressed)
    return out


def extract_blob_containing_marker_8(grid, marker=8, background=0):
    """Find the marker-8 cell (inside a blob). BFS with 4-connectivity from the marker,
    treating marker as blob color. Return bounding box."""
    from collections import deque
    rows, cols = len(grid), len(grid[0])
    r8, c8 = None, None
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == marker:
                r8, c8 = r, c
                break
        if r8 is not None:
            break
    if r8 is None:
        return [row[:] for row in grid]
    blob_color = None
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nr, nc = r8 + dr, c8 + dc
        if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] not in (background, marker):
            blob_color = grid[nr][nc]
            break
    if blob_color is None:
        return [[background]]
    queue = deque([(r8, c8)])
    visited = {(r8, c8)}
    blob = [(r8, c8)]
    while queue:
        r, c = queue.popleft()
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in visited:
                if grid[nr][nc] in (blob_color, marker):
                    visited.add((nr, nc))
                    blob.append((nr, nc))
                    queue.append((nr, nc))
    rmin = min(r for r, c in blob)
    rmax = max(r for r, c in blob)
    cmin = min(c for r, c in blob)
    cmax = max(c for r, c in blob)
    out = [[background] * (cmax - cmin + 1) for _ in range(rmax - rmin + 1)]
    for r, c in blob:
        out[r - rmin][c - cmin] = blob_color
    return out


def draw_diagonal_lines_between_same_color_pairs(grid, background=0):
    """For each pair of cells with same color, if they're diagonally aligned (|dr|==|dc|),
    draw a diagonal line of that color between them."""
    from collections import defaultdict
    rows, cols = len(grid), len(grid[0])
    color_cells = defaultdict(list)
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != background:
                color_cells[grid[r][c]].append((r, c))
    out = [row[:] for row in grid]
    for color, cells in color_cells.items():
        if len(cells) == 2:
            (r1, c1), (r2, c2) = cells
            dr, dc = r2 - r1, c2 - c1
            if dr != 0 and abs(dr) == abs(dc):
                steps = abs(dr)
                sr, sc = dr // steps, dc // steps
                for k in range(1, steps):
                    nr, nc = r1 + k*sr, c1 + k*sc
                    if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == background:
                        out[nr][nc] = color
    return out


def complete_symmetric_pattern(grid, background=0):
    """Find centroid of non-background cells. Reflect each cell through the centroid.
    Add reflections wherever the output cell is background."""
    rows, cols = len(grid), len(grid[0])
    cells = [(r, c, grid[r][c]) for r in range(rows) for c in range(cols) if grid[r][c] != background]
    if not cells:
        return grid
    cr = round(sum(r for r, c, v in cells) / len(cells))
    cc = round(sum(c for r, c, v in cells) / len(cells))
    out = [row[:] for row in grid]
    for r, c, v in cells:
        for nr, nc in [(2*cr-r, c), (r, 2*cc-c), (2*cr-r, 2*cc-c)]:
            if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == background:
                out[nr][nc] = v
    return out


def tile_two_colors_with_step(grid, background=0):
    """Two non-background cells define a step vector. Tile alternating colors:
    if |dc| <= |dr|, tile vertical columns; otherwise tile horizontal rows."""
    rows, cols = len(grid), len(grid[0])
    cells = [(r,c,grid[r][c]) for r in range(rows) for c in range(cols) if grid[r][c] != background]
    if len(cells) != 2:
        return grid
    (r1,c1,v1),(r2,c2,v2) = cells
    dr, dc = r2-r1, c2-c1
    out = [row[:] for row in grid]
    if dc == 0 or abs(dc) > abs(dr):
        # Tile vertically (rows), fill entire rows
        step = 2 * abs(dr) if dr != 0 else 2
        r = r1
        while 0 <= r < rows:
            for cc in range(cols): out[r][cc] = v1
            r += step
        r = r2
        while 0 <= r < rows:
            for cc in range(cols): out[r][cc] = v2
            r += step
    else:
        # Tile horizontally (cols), fill entire cols
        step = 2 * abs(dc)
        c = c1
        while 0 <= c < cols:
            for rr in range(rows): out[rr][c] = v1
            c += step
        c = c2
        while 0 <= c < cols:
            for rr in range(rows): out[rr][c] = v2
            c += step
    return out


def draw_dual_frame_for_two_cells(grid, background=0):
    """Two non-background cells split the grid vertically at their row midpoint.
    Each cell's territory gets: full row at outer boundary + full row at cell row + sides (col 0 and col cols-1)."""
    rows, cols = len(grid), len(grid[0])
    cells = [(r,c,grid[r][c]) for r in range(rows) for c in range(cols) if grid[r][c] != background]
    if len(cells) != 2:
        return grid
    cells.sort()
    (r1,c1,v1),(r2,c2,v2) = cells
    mid = (r1 + r2) // 2
    out = [[background]*cols for _ in range(rows)]
    for r in range(0, mid+1):
        if r == 0 or r == r1:
            for c in range(cols): out[r][c] = v1
        else:
            out[r][0] = v1; out[r][cols-1] = v1
    for r in range(mid+1, rows):
        if r == rows-1 or r == r2:
            for c in range(cols): out[r][c] = v2
        else:
            out[r][0] = v2; out[r][cols-1] = v2
    return out


def expand_plus_shapes_with_diagonals(grid, background=0):
    """Find plus-shaped patterns (center C, orthogonal arms A). Extend arms one more step
    and add diagonal marks (at steps 1 and 2) of center color."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for r in range(1, rows-1):
        for c in range(1, cols-1):
            v = grid[r][c]
            if v == background:
                continue
            arms = [grid[r-1][c], grid[r+1][c], grid[r][c-1], grid[r][c+1]]
            if len(set(arms)) == 1 and arms[0] != background and arms[0] != v:
                arm_color = arms[0]
                for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nr2, nc2 = r + 2*dr, c + 2*dc
                    if 0 <= nr2 < rows and 0 <= nc2 < cols:
                        out[nr2][nc2] = arm_color
                for dr, dc in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                    for step in [1, 2]:
                        nr, nc = r + step*dr, c + step*dc
                        if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == background:
                            out[nr][nc] = v
    return out


def fill_antidiagonal_stripes_3(grid, background=0):
    """Find colors assigned to 3 anti-diagonal classes from non-zero input cells.
    Fill entire grid: output[r][c] = color[(r+c) % 3]."""
    rows, cols = len(grid), len(grid[0])
    color_map = {}
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            if v != background:
                k = (r + c) % 3
                color_map[k] = v
    if len(color_map) < 3:
        return grid
    return [[color_map[(r+c) % 3] for c in range(cols)] for r in range(rows)]


def intersect_halves_split_by_5(grid, divider=5, fill_color=2, background=0):
    """Split grid by a vertical column of divider value. Find cells where both
    left and right halves have non-background values. Output that intersection as fill_color."""
    rows, cols = len(grid), len(grid[0])
    div_col = next((c for c in range(cols) if all(grid[r][c] == divider for r in range(rows))), None)
    if div_col is None:
        return grid
    left_cols = div_col
    right_cols = cols - div_col - 1
    out_cols = min(left_cols, right_cols)
    out = []
    for r in range(rows):
        row = []
        for c in range(out_cols):
            lv = grid[r][c]
            rv = grid[r][div_col + 1 + c]
            row.append(fill_color if lv != background and rv != background else background)
        out.append(row)
    return out


def connect_collinear_1s_with_8s(grid, line_color=1, fill_color=8, background=0):
    """For every pair of line_color cells in the same row or column,
    fill background cells between them with fill_color."""
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    # Same row pairs
    for r in range(rows):
        ones = [c for c in range(cols) if grid[r][c] == line_color]
        if len(ones) >= 2:
            cmin, cmax = min(ones), max(ones)
            for c in range(cmin + 1, cmax):
                if out[r][c] == background:
                    out[r][c] = fill_color
    # Same col pairs
    for c in range(cols):
        ones = [r for r in range(rows) if grid[r][c] == line_color]
        if len(ones) >= 2:
            rmin, rmax = min(ones), max(ones)
            for r in range(rmin + 1, rmax):
                if out[r][c] == background:
                    out[r][c] = fill_color
    return out


def expand_vertical_line_into_fan(grid, line_color=7, fill_color=8, background=0):
    """Find a vertical line of line_color. The apex is the bottom of the line.
    Expand upward: at distance d from apex, fill cols center-d to center+d
    with alternating line_color (even offset) and fill_color (odd offset)."""
    rows, cols = len(grid), len(grid[0])
    # Find the column and row range of the vertical line
    line_cols = set()
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == line_color:
                line_cols.add(c)
    if not line_cols:
        return grid
    center = min(line_cols)
    line_rows = [r for r in range(rows) if grid[r][center] == line_color]
    if not line_rows:
        return grid
    apex = max(line_rows)
    out = [row[:] for row in grid]
    for r in range(apex + 1):
        d = apex - r
        cmin = max(0, center - d)
        cmax = min(cols - 1, center + d)
        for c in range(cmin, cmax + 1):
            offset = abs(c - center)
            out[r][c] = line_color if offset % 2 == 0 else fill_color
    return out


def fill_bouncing_diagonal_from_anchor(grid, anchor_color=1, fill_color=8, background=0):
    """Find single anchor cell, simulate diagonal bounce path going upward through all rows.
    Fill entire grid with fill_color, then place anchor_color along bounce path."""
    rows, cols = len(grid), len(grid[0])
    anchor = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] == anchor_color]
    if not anchor:
        return grid
    sr, sc = anchor[0]
    out = [[fill_color] * cols for _ in range(rows)]
    dc = 1  # initial direction: right
    c = sc
    for r in range(sr, -1, -1):
        out[r][c] = anchor_color
        c += dc
        if c >= cols:
            c = cols - 2
            dc = -1
        elif c < 0:
            c = 1
            dc = 1
    return out


def fill_horizontal_gaps_between_blobs_9(grid, blob_color=2, fill_color=9, background=0):
    """Fill horizontal gaps between blob pairs that are always-adjacent across all shared rows."""
    from collections import defaultdict
    rows, cols = len(grid), len(grid[0])
    cells = set((r,c) for r in range(rows) for c in range(cols) if grid[r][c] == blob_color)
    visited = set()
    blob_id = {}
    blobs = []
    def bfs(start):
        comp = [start]; q = [start]; visited.add(start)
        while q:
            r,c = q.pop()
            for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                nr,nc = r+dr,c+dc
                if (nr,nc) in cells and (nr,nc) not in visited:
                    visited.add((nr,nc)); q.append((nr,nc)); comp.append((nr,nc))
        return comp
    for cell in cells:
        if cell not in visited:
            comp = bfs(cell); bid = len(blobs); blobs.append(comp)
            for cell2 in comp: blob_id[cell2] = bid
    row_blobs = defaultdict(dict)
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == blob_color:
                bid = blob_id[(r,c)]
                mn, mx = row_blobs[r].get(bid, (c,c))
                row_blobs[r][bid] = (min(mn,c), max(mx,c))
    row_adj_pairs = {}
    for r in range(rows):
        if len(row_blobs[r]) < 2: continue
        sb = sorted(row_blobs[r].items(), key=lambda x: x[1][0])
        row_adj_pairs[r] = set()
        for i in range(len(sb)-1):
            row_adj_pairs[r].add((sb[i][0], sb[i+1][0]))
    pair_rows = defaultdict(set)
    for r in range(rows):
        bids = list(row_blobs[r].keys())
        for i in range(len(bids)):
            for j in range(i+1, len(bids)):
                pair_rows[(min(bids[i],bids[j]), max(bids[i],bids[j]))].add(r)
    always_adj = set()
    for (ba,bb), shared in pair_rows.items():
        ok = True
        for r in shared:
            ca = row_blobs[r].get(ba,(999,0))[0]; cb = row_blobs[r].get(bb,(999,0))[0]
            if ca < cb:
                if (ba,bb) not in row_adj_pairs.get(r, set()): ok=False; break
            else:
                if (bb,ba) not in row_adj_pairs.get(r, set()): ok=False; break
        if ok: always_adj.add((ba,bb))
    out = [row[:] for row in grid]
    for (ba,bb) in always_adj:
        for r in pair_rows[(ba,bb)]:
            ca_max = row_blobs[r][ba][1]; cb_min = row_blobs[r][bb][0]
            cb_max = row_blobs[r][bb][1]; ca_min = row_blobs[r][ba][0]
            if ca_min < cb_min: lmax, rmin2 = ca_max, cb_min
            else: lmax, rmin2 = cb_max, ca_min
            for c in range(lmax+1, rmin2):
                if out[r][c] == background: out[r][c] = fill_color
    return out

def draw_plus_at_midpoint(grid, point_color=1, fill_color=3, background=0):
    """Find two point_color cells, draw a plus/cross at their midpoint."""
    rows, cols = len(grid), len(grid[0])
    pts = [(r,c) for r in range(rows) for c in range(cols) if grid[r][c] == point_color]
    if len(pts) < 2: return grid
    r1,c1 = pts[0]; r2,c2 = pts[1]
    cr = (r1+r2)//2; cc = (c1+c2)//2
    out = [row[:] for row in grid]
    for dr,dc in [(0,0),(-1,0),(1,0),(0,-1),(0,1)]:
        nr,nc = cr+dr, cc+dc
        if 0<=nr<rows and 0<=nc<cols and out[nr][nc]==background:
            out[nr][nc] = fill_color
    return out

def replace_5_with_3x3_block(grid, fill_color=1, background=0):
    """Replace each 5-cell with a 3x3 block of fill_color (including the 5 cell itself)."""
    rows, cols = len(grid), len(grid[0])
    fives = [(r,c) for r in range(rows) for c in range(cols) if grid[r][c]==5]
    out = [row[:] for row in grid]
    for r,c in fives:
        for dr in [-1,0,1]:
            for dc in [-1,0,1]:
                nr,nc = r+dr, c+dc
                if 0<=nr<rows and 0<=nc<cols:
                    out[nr][nc] = fill_color
    return out

def clear_border_fill_interior_3(grid, wall_color=2, fill_color=3, background=0):
    """Clear rectangular borders of wall_color and fill their enclosed interiors with fill_color."""
    from collections import deque
    rows, cols = len(grid), len(grid[0])
    exterior = set()
    q = deque()
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == background and (r==0 or r==rows-1 or c==0 or c==cols-1):
                if (r,c) not in exterior:
                    exterior.add((r,c)); q.append((r,c))
    while q:
        r,c = q.popleft()
        for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            nr,nc = r+dr,c+dc
            if 0<=nr<rows and 0<=nc<cols and (nr,nc) not in exterior and grid[nr][nc]==background:
                exterior.add((nr,nc)); q.append((nr,nc))
    out = [row[:] for row in grid]
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == wall_color:
                out[r][c] = background
            elif grid[r][c] == background and (r,c) not in exterior:
                out[r][c] = fill_color
    return out

def draw_cross_through_rectangle_center(grid, rect_color=1, fill_color=6, background=8):
    """Find each 4-connected component of rect_color (a bordered rectangle).
    Draw a full cross (center row + center col) through the bounding box center
    of each component, filling with fill_color where background exists."""
    rows, cols = len(grid), len(grid[0])
    cell_set = set((r,c) for r in range(rows) for c in range(cols) if grid[r][c] == rect_color)
    if not cell_set: return grid
    visited = set()
    components = []
    def bfs(start):
        comp = [start]; q = [start]; visited.add(start)
        while q:
            r,c = q.pop()
            for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                nr,nc = r+dr,c+dc
                if (nr,nc) in cell_set and (nr,nc) not in visited:
                    visited.add((nr,nc)); q.append((nr,nc)); comp.append((nr,nc))
        return comp
    for cell in cell_set:
        if cell not in visited:
            components.append(bfs(cell))
    out = [row[:] for row in grid]
    for comp in components:
        rmin = min(r for r,c in comp); rmax = max(r for r,c in comp)
        cmin = min(c for r,c in comp); cmax = max(c for r,c in comp)
        center_r = (rmin + rmax) // 2
        center_c = (cmin + cmax) // 2
        for c in range(cols):
            if out[center_r][c] == background: out[center_r][c] = fill_color
        for r in range(rows):
            if out[r][center_c] == background: out[r][center_c] = fill_color
    return out

def fill_grid_cell_spans_bidirectional(grid, background=0):
    """Grid divided by wall-color lines into cells. Same-color cells in the same
    row-band or col-band spread to fill all cells between them (both H and V)."""
    from collections import defaultdict
    rows, cols = len(grid), len(grid[0])
    wall_color = None
    for r in range(rows):
        vals = set(grid[r])
        if len(vals) == 1 and grid[r][0] != background:
            wall_color = grid[r][0]
            break
    if wall_color is None:
        return grid
    def get_bands(seps, length):
        bands, prev = [], 0
        for s in sorted(seps):
            if s > prev: bands.append(list(range(prev, s)))
            prev = s + 1
        if prev < length: bands.append(list(range(prev, length)))
        return [b for b in bands if b]
    sep_rows = [r for r in range(rows) if all(grid[r][c] == wall_color for c in range(cols))]
    sep_cols = [c for c in range(cols) if all(grid[r][c] == wall_color for r in range(rows))]
    row_bands = get_bands(sep_rows, rows)
    col_bands = get_bands(sep_cols, cols)
    if not row_bands or not col_bands:
        return grid
    def get_cell_color(rbi, cbi):
        for r in row_bands[rbi]:
            for c in col_bands[cbi]:
                if grid[r][c] != background and grid[r][c] != wall_color:
                    return grid[r][c]
        return background
    cell_map = {}
    for rbi in range(len(row_bands)):
        for cbi in range(len(col_bands)):
            v = get_cell_color(rbi, cbi)
            if v != background:
                cell_map[(rbi, cbi)] = v
    out = [row[:] for row in grid]
    def fill_cell(rbi, cbi, color):
        for r in row_bands[rbi]:
            for c in col_bands[cbi]:
                if out[r][c] == background:
                    out[r][c] = color
    for rbi in range(len(row_bands)):
        by_color = defaultdict(list)
        for cbi in range(len(col_bands)):
            v = cell_map.get((rbi, cbi), background)
            if v != background:
                by_color[v].append(cbi)
        for color, cbis in by_color.items():
            if len(cbis) >= 2:
                for cbi in range(min(cbis), max(cbis) + 1):
                    fill_cell(rbi, cbi, color)
    for cbi in range(len(col_bands)):
        by_color = defaultdict(list)
        for rbi in range(len(row_bands)):
            v = cell_map.get((rbi, cbi), background)
            if v != background:
                by_color[v].append(rbi)
        for color, rbis in by_color.items():
            if len(rbis) >= 2:
                for rbi in range(min(rbis), max(rbis) + 1):
                    fill_cell(rbi, cbi, color)
    return out

def copy_template_to_all_sections(grid, background=0):
    """Grid divided by single-color separator rows+cols into a 3x3 arrangement of sections.
    Find the section with the most non-separator non-background cells (the template).
    Copy the template's relative pattern to all sections using the separator color,
    leaving existing non-zero, non-separator cells unchanged."""
    rows, cols = len(grid), len(grid[0])
    sep_rows = []
    for r in range(rows):
        vals = set(grid[r])
        if len(vals) == 1 and 0 not in vals:
            sep_rows.append(r)
    sep_cols = []
    for c in range(cols):
        col_vals = set(grid[r][c] for r in range(rows))
        if len(col_vals) == 1 and 0 not in col_vals:
            sep_cols.append(c)
    if not sep_rows or not sep_cols:
        return grid
    sep_color = grid[sep_rows[0]][0]

    def get_bands(seps, length):
        bands, prev = [], 0
        for s in sorted(seps):
            if s > prev:
                bands.append((prev, s))
            prev = s + 1
        if prev < length:
            bands.append((prev, length))
        return bands

    row_bands = get_bands(sep_rows, rows)
    col_bands = get_bands(sep_cols, cols)
    max_count, template_offsets = 0, []
    sections = []
    for rb in row_bands:
        for cb in col_bands:
            cells = [(r - rb[0], c - cb[0]) for r in range(rb[0], rb[1])
                     for c in range(cb[0], cb[1])
                     if grid[r][c] != 0 and grid[r][c] != sep_color]
            sections.append((rb, cb, cells))
            if len(cells) > max_count:
                max_count = len(cells)
                template_offsets = cells
    if not template_offsets:
        return grid
    out = [row[:] for row in grid]
    for rb, cb, _ in sections:
        for dr, dc in template_offsets:
            ar, ac = rb[0] + dr, cb[0] + dc
            if 0 <= ar < rows and 0 <= ac < cols and grid[ar][ac] == 0:
                out[ar][ac] = sep_color
    return out

def fill_periodic_tiling_hole(grid, background=0):
    """Fill rectangular zero-holes in a 2D-periodic tiled grid.
    Detects row and column periods from non-zero cells, then fills each zero
    by finding the equivalent non-zero cell at the same (r mod row_p, c mod col_p)."""
    rows, cols = len(grid), len(grid[0])
    col_period = None
    for r in range(rows):
        row = grid[r]
        if all(v != background for v in row):
            for p in range(1, cols + 1):
                if all(row[c] == row[c % p] for c in range(cols)):
                    col_period = p
                    break
            break
    row_period = None
    for p in range(1, rows):
        consistent = True
        pairs = 0
        for r in range(rows - p):
            for c in range(cols):
                v1, v2 = grid[r][c], grid[r+p][c]
                if v1 != background and v2 != background:
                    if v1 != v2:
                        consistent = False
                        break
                    pairs += 1
            if not consistent:
                break
        if consistent and pairs > 5:
            row_period = p
            break
    if col_period is None or row_period is None:
        return grid
    out = [row[:] for row in grid]
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == background:
                for dr in range(rows // row_period + 2):
                    found = False
                    for sign in [1, -1]:
                        nr = r + sign * dr * row_period
                        if 0 <= nr < rows and grid[nr][c] != background:
                            out[r][c] = grid[nr][c]
                            found = True
                            break
                    if found:
                        break
    return out

def crop_and_recolor_template(grid, background=0):
    """4 corner-markers define a rectangle; template pattern inside → output inner box with template→marker color."""
    from collections import Counter
    rows, cols = len(grid), len(grid[0])
    cnt = Counter(v for r in range(rows) for c in range(cols) if grid[r][c] != background for v in [grid[r][c]])
    if len(cnt) != 2:
        return grid
    # marker = color with exactly 4 cells; template = the other
    marker_color = None
    template_color = None
    for color, count in cnt.items():
        if count == 4:
            marker_color = color
        else:
            template_color = color
    if marker_color is None or template_color is None:
        return grid
    marker_cells = sorted([(r, c) for r in range(rows) for c in range(cols) if grid[r][c] == marker_color])
    if len(marker_cells) != 4:
        return grid
    rs = sorted(set(r for r, c in marker_cells))
    cs = sorted(set(c for r, c in marker_cells))
    if len(rs) != 2 or len(cs) != 2:
        return grid
    r0, r1 = rs[0], rs[1]
    c0, c1 = cs[0], cs[1]
    # inner box = rows r0+1..r1-1, cols c0+1..c1-1
    inner_h = r1 - r0 - 1
    inner_w = c1 - c0 - 1
    if inner_h <= 0 or inner_w <= 0:
        return grid
    out = [[background] * inner_w for _ in range(inner_h)]
    for dr in range(inner_h):
        for dc in range(inner_w):
            v = grid[r0 + 1 + dr][c0 + 1 + dc]
            if v == template_color:
                out[dr][dc] = marker_color
    return out

def crop_rectangle_interior(grid, frame_color=None, background=0):
    """Extract the interior of a rectangle outlined by frame_color."""
    rows, cols = len(grid), len(grid[0])
    def try_color(fc):
        cells = [(r,c) for r in range(rows) for c in range(cols) if grid[r][c] == fc]
        if not cells: return None
        min_r = min(r for r,c in cells); max_r = max(r for r,c in cells)
        min_c = min(c for r,c in cells); max_c = max(c for r,c in cells)
        if min_r == max_r or min_c == max_c: return None
        expected = set()
        for c in range(min_c, max_c+1): expected.add((min_r,c)); expected.add((max_r,c))
        for r in range(min_r, max_r+1): expected.add((r,min_c)); expected.add((r,max_c))
        if set(cells) != expected: return None
        interior = [[grid[r][c] for c in range(min_c+1, max_c)] for r in range(min_r+1, max_r)]
        return interior if interior else None
    if frame_color is not None:
        return try_color(frame_color) or grid
    from collections import Counter
    cnt = Counter(v for row in grid for v in row if v != background)
    for fc, _ in cnt.most_common():
        result = try_color(fc)
        if result is not None: return result
    return grid

def fill_max_zero_rectangle_with_6(grid):
    # Find the maximum-area all-zero rectangle spanning consecutive non-5 rows and fill with 6.
    # Rows containing value 5 are treated as marker/frame rows and excluded from fill target.
    rows = len(grid)
    if rows == 0:
        return [list(row) for row in grid]
    cols = len(grid[0])
    fill_rows = [r for r in range(rows) if 5 not in grid[r]]
    if not fill_rows:
        return [list(row) for row in grid]
    best = (0, 0, 0, 0, 0)
    n = len(fill_rows)
    for i in range(n):
        zero_set = {c for c in range(cols) if grid[fill_rows[i]][c] == 0}
        for j in range(i, n):
            if j > i and fill_rows[j] != fill_rows[j - 1] + 1:
                break
            if j > i:
                zero_set = zero_set & {c for c in range(cols) if grid[fill_rows[j]][c] == 0}
            if not zero_set:
                break
            height = j - i + 1
            sorted_z = sorted(zero_set)
            run_s = sorted_z[0]
            run_len = 1
            best_rs = sorted_z[0]
            best_rl = 1
            for k in range(1, len(sorted_z)):
                if sorted_z[k] == sorted_z[k - 1] + 1:
                    run_len += 1
                    if run_len > best_rl:
                        best_rl = run_len
                        best_rs = run_s
                else:
                    run_s = sorted_z[k]
                    run_len = 1
            area = height * best_rl
            if area > best[0]:
                best = (area, fill_rows[i], fill_rows[j], best_rs, best_rs + best_rl - 1)
    if best[0] == 0:
        return [list(row) for row in grid]
    _, r1, r2, c1, c2 = best
    out = [list(row) for row in grid]
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            out[r][c] = 6
    return out


def tile_by_nonzero(input_grid):
    # Task 007bbfb7: tile input into 9x9 by placing input at positions where input[i][j] != 0
    rows = len(input_grid)
    cols = len(input_grid[0])
    out = [[0] * (cols * cols) for _ in range(rows * rows)]
    for i in range(rows):
        for j in range(cols):
            if input_grid[i][j] != 0:
                for r in range(rows):
                    for c in range(cols):
                        out[i * rows + r][j * cols + c] = input_grid[r][c]
    return out


def fill_enclosed_regions(input_grid):
    # Task 00d62c1b: flood fill from border; enclosed 0-cells get filled with 4
    rows = len(input_grid)
    cols = len(input_grid[0])
    out = [list(row) for row in input_grid]
    visited = [[False] * cols for _ in range(rows)]
    queue = []
    for r in range(rows):
        for c in range(cols):
            if (r == 0 or r == rows - 1 or c == 0 or c == cols - 1) and input_grid[r][c] == 0:
                if not visited[r][c]:
                    visited[r][c] = True
                    queue.append((r, c))
    while queue:
        r, c = queue.pop()
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc] and input_grid[nr][nc] == 0:
                visited[nr][nc] = True
                queue.append((nr, nc))
    for r in range(rows):
        for c in range(cols):
            if input_grid[r][c] == 0 and not visited[r][c]:
                out[r][c] = 4
    return out


def extend_row_period_replace(input_grid):
    # Task 017c7c7b: find minimal row period, extend to 9 rows, replace 1 with 2
    rows = len(input_grid)
    cols = len(input_grid[0])
    period = rows
    for p in range(1, rows + 1):
        valid = True
        for r in range(rows):
            if input_grid[r] != input_grid[r % p]:
                valid = False
                break
        if valid:
            period = p
            break
    out = []
    for r in range(9):
        row = [2 if v == 1 else v for v in input_grid[r % period]]
        out.append(row)
    return out


def swap_color_pairs(input_grid):
    # Task 0d3d703e: fixed bijective color mapping: 1<->5, 2<->6, 3<->4, 8<->9
    mapping = {1: 5, 5: 1, 2: 6, 6: 2, 3: 4, 4: 3, 8: 9, 9: 8}
    return [[mapping.get(v, v) for v in row] for row in input_grid]


def add_cross_and_diag_markers(input_grid):
    # Task 0ca9ddb6: 1 gets 7s in cross; 2 gets 4s in diagonals
    rows = len(input_grid)
    cols = len(input_grid[0])
    out = [list(row) for row in input_grid]
    for r in range(rows):
        for c in range(cols):
            if input_grid[r][c] == 1:
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == 0:
                        out[nr][nc] = 7
            elif input_grid[r][c] == 2:
                for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == 0:
                        out[nr][nc] = 4
    return out


def extract_unique_color_panel(input_grid):
    # Task 0b148d64: find zero-separator rows/cols, extract panel with the color that appears in exactly one panel
    rows = len(input_grid)
    cols = len(input_grid[0])
    zero_rows = [r for r in range(rows) if all(input_grid[r][c] == 0 for c in range(cols))]
    zero_cols = [c for c in range(cols) if all(input_grid[r][c] == 0 for r in range(rows))]
    row_bounds = []
    prev = 0
    for zr in zero_rows:
        if zr > prev:
            row_bounds.append((prev, zr))
        prev = zr + 1
    if prev < rows:
        row_bounds.append((prev, rows))
    col_bounds = []
    prev = 0
    for zc in zero_cols:
        if zc > prev:
            col_bounds.append((prev, zc))
        prev = zc + 1
    if prev < cols:
        col_bounds.append((prev, cols))
    panel_colors = {}
    for rb in row_bounds:
        for cb in col_bounds:
            colors = set()
            for r in range(rb[0], rb[1]):
                for c in range(cb[0], cb[1]):
                    if input_grid[r][c] != 0:
                        colors.add(input_grid[r][c])
            panel_colors[(rb, cb)] = colors
    color_to_panels = {}
    for key, colors in panel_colors.items():
        for color in colors:
            color_to_panels.setdefault(color, []).append(key)
    for color, panels in color_to_panels.items():
        if len(panels) == 1:
            rb, cb = panels[0]
            return [list(input_grid[r][cb[0]:cb[1]]) for r in range(rb[0], rb[1])]
    return [row[:] for row in input_grid]


def tile_four_rotations(grid):
    # Tile the input grid in a 2x2 arrangement using all four 90-degree rotations.
    # Top-left = rot0, top-right = rot90cw, bottom-left = rot90ccw, bottom-right = rot180.
    H = len(grid)
    W = len(grid[0])
    def rot_cw(g):
        gh = len(g)
        gw = len(g[0])
        return [[g[gh - 1 - c][r] for c in range(gh)] for r in range(gw)]
    def rot_ccw(g):
        gh = len(g)
        gw = len(g[0])
        return [[g[c][gw - 1 - r] for c in range(gh)] for r in range(gw)]
    r0 = [row[:] for row in grid]
    r_cw = rot_cw(grid)
    r_ccw = rot_ccw(grid)
    r180 = rot_cw(r_cw)
    out = []
    for row_top, row_tr in zip(r0, r_cw):
        out.append(list(row_top) + list(row_tr))
    for row_bl, row_br in zip(r_ccw, r180):
        out.append(list(row_bl) + list(row_br))
    return out


def mark_cross_intersection_with_4(grid):
    # Find horizontal and vertical lines crossing in the grid.
    # The h-line is a row where almost all non-zero cells share the same value.
    # The v-line is a col where almost all non-zero cells share the same value.
    # Place a 3x3 box of 4s centered at their intersection, keeping the center cell unchanged.
    rows = len(grid)
    cols = len(grid[0])
    def count_most_common(vals):
        freq = {}
        for v in vals:
            freq[v] = freq.get(v, 0) + 1
        if not freq:
            return 0, 0
        best = max(freq, key=lambda k: freq[k])
        return best, freq[best]
    h_row = -1
    for r in range(rows):
        nz = [v for v in grid[r] if v != 0]
        val, freq = count_most_common(nz)
        if freq >= cols - 1:
            h_row = r
            break
    v_col = -1
    for c in range(cols):
        nz = [grid[r][c] for r in range(rows) if grid[r][c] != 0]
        val, freq = count_most_common(nz)
        if freq >= rows - 1:
            v_col = c
            break
    if h_row == -1 or v_col == -1:
        return [row[:] for row in grid]
    out = [row[:] for row in grid]
    ir, ic = h_row, v_col
    for dr in [-1, 0, 1]:
        for dc in [-1, 0, 1]:
            nr, nc = ir + dr, ic + dc
            if dr == 0 and dc == 0:
                continue
            if 0 <= nr < rows and 0 <= nc < cols:
                out[nr][nc] = 4
    return out


def connect_same_color_cells_in_bands(grid):
    # The grid contains a separator color forming rows and columns that divide it into cells.
    # For each color that appears in multiple cells sharing the same row or column of cells,
    # fill the intermediate cells with that color (connect the dots along row/col bands).
    rows = len(grid)
    cols = len(grid[0])
    row_counts = {}
    for r in range(rows):
        vals = set(grid[r])
        if len(vals) == 1:
            v = list(vals)[0]
            row_counts[v] = row_counts.get(v, 0) + 1
    if not row_counts:
        return [row[:] for row in grid]
    sep = max(row_counts, key=lambda k: row_counts[k])
    sep_rows = [r for r in range(rows) if all(grid[r][c] == sep for c in range(cols))]
    sep_cols = [c for c in range(cols) if all(grid[r][c] == sep for r in range(rows))]
    n_cr = len(sep_rows) + 1
    n_cc = len(sep_cols) + 1
    cr_start = [0] + [sr + 1 for sr in sep_rows]
    cc_start = [0] + [sc + 1 for sc in sep_cols]
    cr_end = sep_rows + [rows]
    cc_end = sep_cols + [cols]
    cell_color = {}
    for ri in range(n_cr):
        for ci in range(n_cc):
            r0, r1 = cr_start[ri], cr_end[ri]
            c0, c1 = cc_start[ci], cc_end[ci]
            for r in range(r0, r1):
                for c in range(c0, c1):
                    v = grid[r][c]
                    if v != 0 and v != sep:
                        cell_color[(ri, ci)] = v
    color_cells = {}
    for (ri, ci), v in cell_color.items():
        color_cells.setdefault(v, []).append((ri, ci))
    fill_cells = dict(cell_color)
    for color, cells in color_cells.items():
        for i in range(len(cells)):
            for j in range(i + 1, len(cells)):
                r1c, c1c = cells[i]
                r2c, c2c = cells[j]
                if r1c == r2c:
                    for ci in range(min(c1c, c2c) + 1, max(c1c, c2c)):
                        fill_cells[(r1c, ci)] = color
                elif c1c == c2c:
                    for ri in range(min(r1c, r2c) + 1, max(r1c, r2c)):
                        fill_cells[(ri, c1c)] = color
    out = [row[:] for row in grid]
    for (ri, ci), color in fill_cells.items():
        r0, r1 = cr_start[ri], cr_end[ri]
        c0, c1 = cc_start[ci], cc_end[ci]
        for r in range(r0, r1):
            for c in range(c0, c1):
                out[r][c] = color
    return out


def tile_2x_and_mark_diagonal_neighbors(grid):
    H = len(grid)
    W = len(grid[0])
    result = [[0] * (2 * W) for _ in range(2 * H)]
    for r in range(2 * H):
        for c in range(2 * W):
            result[r][c] = grid[r % H][c % W]
    nonzero = [(r, c) for r in range(2 * H) for c in range(2 * W) if result[r][c] != 0]
    for nr, nc in nonzero:
        for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            rr, cc = nr + dr, nc + dc
            if 0 <= rr < 2 * H and 0 <= cc < 2 * W and result[rr][cc] == 0:
                result[rr][cc] = 8
    return result


def mark_knight_jumps_from_diagonal_pairs(grid):
    result = [list(row) for row in grid]
    H = len(result)
    W = len(result[0])
    visited = [[False] * W for _ in range(H)]
    comps = []
    for sr in range(H):
        for sc in range(W):
            if result[sr][sc] != 0 and not visited[sr][sc]:
                comp = []
                stack = [(sr, sc)]
                while stack:
                    r, c = stack.pop()
                    if visited[r][c]:
                        continue
                    visited[r][c] = True
                    comp.append((r, c))
                    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < H and 0 <= nc < W and result[nr][nc] != 0 and not visited[nr][nc]:
                            stack.append((nr, nc))
                comps.append(comp)
    knight_dirs = [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
    for i in range(len(comps)):
        for j in range(i + 1, len(comps)):
            cj_set = set(comps[j])
            diag_adj = any(
                (r + dr, c + dc) in cj_set
                for r, c in comps[i]
                for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]
            )
            if not diag_adj:
                continue
            ri = [r for r, c in comps[i]]
            ci_c = [c for r, c in comps[i]]
            scale = max(max(ri) - min(ri) + 1, max(ci_c) - min(ci_c) + 1)
            cr_i = sum(r for r, c in comps[i]) / len(comps[i])
            cc_i = sum(c for r, c in comps[i]) / len(comps[i])
            cr_j = sum(r for r, c in comps[j]) / len(comps[j])
            cc_j = sum(c for r, c in comps[j]) / len(comps[j])
            moves_i = {(cr_i + dr * scale, cc_i + dc * scale) for dr, dc in knight_dirs}
            moves_j = {(cr_j + dr * scale, cc_j + dc * scale) for dr, dc in knight_dirs}
            for pos in moves_i & moves_j:
                nr, nc = pos
                for r, c in comps[i]:
                    rr = int(round(nr + r - cr_i))
                    cc = int(round(nc + c - cc_i))
                    if 0 <= rr < H and 0 <= cc < W and result[rr][cc] == 0:
                        result[rr][cc] = 8
    return result


def tile_diagonal_period3(grid):
    H = len(grid)
    W = len(grid[0])
    colors = [0] * 3
    for r in range(H):
        for c in range(W):
            v = grid[r][c]
            if v != 0:
                colors[(r + c) % 3] = v
    return [[colors[(r + c) % 3] for c in range(W)] for r in range(H)]


def recolor_columns_by_height_rank(grid):
    H = len(grid)
    W = len(grid[0])
    col_heights = {}
    for c in range(W):
        height = sum(1 for r in range(H) if grid[r][c] != 0)
        if height > 0:
            col_heights[c] = height
    ranked = sorted(col_heights.keys(), key=lambda c: -col_heights[c])
    col_color = {c: i + 1 for i, c in enumerate(ranked)}
    result = [list(row) for row in grid]
    for r in range(H):
        for c in range(W):
            if result[r][c] != 0:
                result[r][c] = col_color[c]
    return result


def tile_two_color_stripes_from_seeds(grid):
    H = len(grid)
    W = len(grid[0])
    cells = [(r, c, grid[r][c]) for r in range(H) for c in range(W) if grid[r][c] != 0]
    if len(cells) != 2:
        return [list(row) for row in grid]
    (r1, c1, a), (r2, c2, b) = cells[0], cells[1]
    dr = abs(r1 - r2)
    dc = abs(c1 - c2)
    result = [[0] * W for _ in range(H)]
    if dr == 0 or (dc != 0 and dc <= dr):
        if c1 > c2:
            c1, c2, a, b = c2, c1, b, a
        period = 2 * dc if dc > 0 else 1
        col_colors = [0] * W
        for c in range(c1, W):
            offset = (c - c1) % period
            if offset == 0:
                col_colors[c] = a
            elif offset == dc:
                col_colors[c] = b
        for r in range(H):
            for c in range(W):
                result[r][c] = col_colors[c]
    else:
        if r1 > r2:
            r1, r2, a, b = r2, r1, b, a
        period = 2 * dr
        row_colors = [0] * H
        for r in range(r1, H):
            offset = (r - r1) % period
            if offset == 0:
                row_colors[r] = a
            elif offset == dr:
                row_colors[r] = b
        for r in range(H):
            for c in range(W):
                result[r][c] = row_colors[r]
    return result


def complete_4fold_symmetry(grid):
    H = len(grid)
    W = len(grid[0])
    cells = [(r, c, grid[r][c]) for r in range(H) for c in range(W) if grid[r][c] != 0]
    if not cells:
        return [list(row) for row in grid]
    result = [list(row) for row in grid]
    min_r = min(r for r, c, v in cells)
    max_r = max(r for r, c, v in cells)
    min_c = min(c for r, c, v in cells)
    max_c = max(c for r, c, v in cells)
    for r, c, v in cells:
        mr = min_r + max_r - r
        mc = min_c + max_c - c
        for rr, cc in [(r, mc), (mr, c), (mr, mc)]:
            if 0 <= rr < H and 0 <= cc < W and result[rr][cc] == 0:
                result[rr][cc] = v
    return result


def expand_cross_with_diagonals(grid):
    H = len(grid)
    W = len(grid[0])
    result = [list(row) for row in grid]
    for cr in range(H):
        for cc in range(W):
            cv = grid[cr][cc]
            if cv == 0:
                continue
            arms = []
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = cr + dr, cc + dc
                if 0 <= nr < H and 0 <= nc < W and grid[nr][nc] != 0 and grid[nr][nc] != cv:
                    arms.append(grid[nr][nc])
            if len(arms) != 4:
                continue
            arm_colors = set(arms)
            if len(arm_colors) != 1:
                continue
            av = arm_colors.pop()
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    if dr == 0 and dc == 0:
                        continue
                    rr, nc = cr + dr, cc + dc
                    if not (0 <= rr < H and 0 <= nc < W):
                        continue
                    if abs(dr) == abs(dc):
                        if result[rr][nc] == 0:
                            result[rr][nc] = cv
                    elif dr == 0 or dc == 0:
                        if result[rr][nc] == 0:
                            result[rr][nc] = av
    return result


def project_template_row_as_2(grid):
    H = len(grid)
    W = len(grid[0])
    row_5 = [sum(1 for v in row if v == 5) for row in grid]
    max_count = max(row_5)
    if max_count <= 1:
        return [list(row) for row in grid]
    template_row = row_5.index(max_count)
    template_cols = [c for c in range(W) if grid[template_row][c] == 5]
    result = [list(row) for row in grid]
    for r in range(H):
        if r != template_row and row_5[r] == 1:
            for c in template_cols:
                if result[r][c] == 0:
                    result[r][c] = 2
    return result


def fill_row_if_endpoints_match(grid):
    H = len(grid)
    W = len(grid[0])
    result = [list(row) for row in grid]
    for r in range(H):
        if W >= 2 and grid[r][0] != 0 and grid[r][0] == grid[r][W - 1]:
            for c in range(W):
                result[r][c] = grid[r][0]
    return result


def draw_cross_lines_with_intersection_marker(grid):
    H = len(grid)
    W = len(grid[0])
    seeds = [(r, c, grid[r][c]) for r in range(H) for c in range(W) if grid[r][c] != 0]
    result = [list(row) for row in grid]
    row_color = {r: v for r, c, v in seeds}
    col_color = {c: v for r, c, v in seeds}
    for r in range(H):
        for c in range(W):
            rc = row_color.get(r)
            cc = col_color.get(c)
            if rc and cc:
                result[r][c] = rc if rc == cc else 2
            elif rc:
                result[r][c] = rc
            elif cc:
                result[r][c] = cc
    return result


def fill_row_between_endpoints_with_midpoint(grid):
    H = len(grid)
    W = len(grid[0])
    result = [list(row) for row in grid]
    for r in range(H):
        nz = [(c, grid[r][c]) for c in range(W) if grid[r][c] != 0]
        if len(nz) == 2:
            c1, v1 = nz[0]
            c2, v2 = nz[1]
            mid = (c1 + c2) // 2
            for c in range(c1, mid):
                result[r][c] = v1
            result[r][mid] = 5
            for c in range(mid + 1, c2 + 1):
                result[r][c] = v2
    return result


def fill_diagonal_checkerboard_around_seeds(grid):
    H = len(grid)
    W = len(grid[0])
    seeds = [(r, c, grid[r][c]) for r in range(H) for c in range(W) if grid[r][c] != 0]
    result = [list(row) for row in grid]
    for r0, c0, v in seeds:
        parity = (r0 + c0) % 2
        for r in range(H):
            for c in range(max(0, c0 - 1), min(W, c0 + 2)):
                if (r + c) % 2 == parity:
                    result[r][c] = v
    return result


def expand_bordered_rectangle(grid):
    H = len(grid)
    W = len(grid[0])
    nz = [(r, c, grid[r][c]) for r in range(H) for c in range(W) if grid[r][c] != 0]
    if not nz:
        return [list(row) for row in grid]
    min_r = min(r for r, c, v in nz)
    max_r = max(r for r, c, v in nz)
    min_c = min(c for r, c, v in nz)
    max_c = max(c for r, c, v in nz)
    outer_color = grid[min_r][min_c]
    inner = [(r, c, grid[r][c]) for r in range(min_r + 1, max_r) for c in range(min_c + 1, max_c) if grid[r][c] != 0]
    if not inner:
        return [list(row) for row in grid]
    inner_color = inner[0][2]
    inner_h = max_r - min_r - 1
    inner_w = max_c - min_c - 1
    result = [[0] * W for _ in range(H)]
    for r in range(min_r, max_r + 1):
        for c in range(min_c, max_c + 1):
            v = grid[r][c]
            if v == outer_color:
                result[r][c] = inner_color
            elif v == inner_color:
                result[r][c] = outer_color
    for r in range(max(0, min_r - inner_h), min_r):
        for c in range(min_c, max_c + 1):
            result[r][c] = outer_color
    for r in range(max_r + 1, min(H, max_r + 1 + inner_h)):
        for c in range(min_c, max_c + 1):
            result[r][c] = outer_color
    for r in range(min_r, max_r + 1):
        for c in range(max(0, min_c - inner_w), min_c):
            result[r][c] = outer_color
        for c in range(max_c + 1, min(W, max_c + 1 + inner_w)):
            result[r][c] = outer_color
    return result


def surround_seeds_with_3x3_border(grid):
    H = len(grid)
    W = len(grid[0])
    seeds = [(r, c) for r in range(H) for c in range(W) if grid[r][c] != 0]
    result = [[0] * W for _ in range(H)]
    for sr, sc in seeds:
        result[sr][sc] = grid[sr][sc]
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                rr, cc = sr + dr, sc + dc
                if 0 <= rr < H and 0 <= cc < W and result[rr][cc] == 0:
                    result[rr][cc] = 1
    return result


def reflect_rows_to_bottom(grid):
    H = len(grid)
    result = [list(row) for row in grid]
    nz_rows = [r for r in range(H) if any(v != 0 for v in grid[r])]
    if not nz_rows:
        return result
    nz_set = set(nz_rows)
    nz_content = [list(grid[r]) for r in nz_rows]
    for i, row_data in enumerate(nz_content):
        target_row = H - 1 - i
        if target_row not in nz_set:
            result[target_row] = row_data
    return result


def fill_bounding_box_of_same_color_pairs(grid):
    H = len(grid)
    W = len(grid[0])
    from collections import defaultdict
    groups = defaultdict(list)
    for r in range(H):
        for c in range(W):
            if grid[r][c] != 0:
                groups[grid[r][c]].append((r, c))
    result = [[0] * W for _ in range(H)]
    for v, cells in groups.items():
        if len(cells) == 2:
            (r1, c1), (r2, c2) = cells
            for r in range(min(r1, r2), max(r1, r2) + 1):
                for c in range(min(c1, c2), max(c1, c2) + 1):
                    result[r][c] = v
    return result


def draw_x_diagonals_from_seed(grid):
    H = len(grid)
    W = len(grid[0])
    seeds = [(r, c, grid[r][c]) for r in range(H) for c in range(W) if grid[r][c] != 0]
    result = [list(row) for row in grid]
    for sr, sc, sv in seeds:
        for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            r, c = sr + dr, sc + dc
            while 0 <= r < H and 0 <= c < W:
                result[r][c] = sv
                r += dr
                c += dc
    return result


def mark_intersection_across_divider(grid):
    H = len(grid)
    W = len(grid[0])
    div_col = -1
    for c in range(W):
        vals = [grid[r][c] for r in range(H)]
        if len(set(vals)) == 1 and vals[0] != 0:
            div_col = c
            break
    if div_col < 0:
        return [list(row) for row in grid]
    lW = div_col
    rW = W - div_col - 1
    out_W = min(lW, rW)
    result = [[0] * out_W for _ in range(H)]
    for r in range(H):
        for c in range(out_W):
            if grid[r][c] != 0 and grid[r][div_col + 1 + c] != 0:
                result[r][c] = 2
    return result


def mark_absent_from_both_panels(grid):
    H = len(grid)
    W = len(grid[0])
    div_col = -1
    for c in range(W):
        vals = [grid[r][c] for r in range(H)]
        if len(set(vals)) == 1 and vals[0] != 0:
            div_col = c
            break
    if div_col < 0:
        return [list(row) for row in grid]
    lW = div_col
    rW = W - div_col - 1
    out_W = min(lW, rW)
    result = [[0] * out_W for _ in range(H)]
    for r in range(H):
        for c in range(out_W):
            if grid[r][c] == 0 and grid[r][div_col + 1 + c] == 0:
                result[r][c] = 8
    return result


def crop_to_bounding_box(grid):
    H = len(grid)
    W = len(grid[0])
    rows = [r for r in range(H) if any(grid[r][c] != 0 for c in range(W))]
    cols = [c for c in range(W) if any(grid[r][c] != 0 for r in range(H))]
    if not rows or not cols:
        return [list(row) for row in grid]
    r0, r1 = rows[0], rows[-1]
    c0, c1 = cols[0], cols[-1]
    return [list(grid[r][c0:c1+1]) for r in range(r0, r1+1)]


def gravity_down(grid):
    H = len(grid)
    W = len(grid[0])
    result = [[0] * W for _ in range(H)]
    for c in range(W):
        col_vals = [grid[r][c] for r in range(H) if grid[r][c] != 0]
        for i, v in enumerate(col_vals):
            result[H - len(col_vals) + i][c] = v
    return result


def align_blocks_to_shared_rows(grid):
    H = len(grid)
    W = len(grid[0])
    visited = [[False] * W for _ in range(H)]
    blocks = []
    for r in range(H):
        for c in range(W):
            if grid[r][c] != 0 and not visited[r][c]:
                color = grid[r][c]
                stack = [(r, c)]
                cells = []
                while stack:
                    cr, cc = stack.pop()
                    if not (0 <= cr < H and 0 <= cc < W) or visited[cr][cc] or grid[cr][cc] != color:
                        continue
                    visited[cr][cc] = True
                    cells.append((cr, cc))
                    for dr2, dc2 in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        stack.append((cr + dr2, cc + dc2))
                blocks.append(cells)
    if not blocks:
        return [list(row) for row in grid]
    block_rows = [(min(r for r, c in cells), max(r for r, c in cells)) for cells in blocks]
    block_h = block_rows[0][1] - block_rows[0][0] + 1
    row_count = [0] * H
    for r_min, r_max in block_rows:
        for r in range(r_min, r_max + 1):
            row_count[r] += 1
    best_score = -1
    target_r = block_rows[0][0]
    for r_start in range(H - block_h + 1):
        score = sum(row_count[r_start + i] for i in range(block_h))
        if score > best_score or (score == best_score and r_start > target_r):
            best_score = score
            target_r = r_start
    result = [[0] * W for _ in range(H)]
    for i, cells in enumerate(blocks):
        r_min = block_rows[i][0]
        offset = target_r - r_min
        for r, c in cells:
            new_r = r + offset
            if 0 <= new_r < H:
                result[new_r][c] = grid[r][c]
    return result


def fill_between_pair_endpoints_in_rows(grid):
    H = len(grid)
    W = len(grid[0])
    from collections import defaultdict
    result = [list(row) for row in grid]
    for r in range(H):
        color_cols = defaultdict(list)
        for c in range(W):
            if grid[r][c] != 0:
                color_cols[grid[r][c]].append(c)
        for v, cols in color_cols.items():
            if len(cols) >= 2:
                for c in range(min(cols), max(cols) + 1):
                    result[r][c] = v
    return result


def recolor_cells_to_nearest_border(grid):
    H = len(grid)
    W = len(grid[0])
    row_lines = {}
    col_lines = {}
    for r in range(H):
        vals = set(grid[r])
        if len(vals) == 1 and 0 not in vals:
            row_lines[r] = grid[r][0]
    for c in range(W):
        vals = set(grid[r][c] for r in range(H))
        if len(vals) == 1 and 0 not in vals:
            col_lines[c] = grid[0][c]
    result = [list(row) for row in grid]
    for r in range(H):
        for c in range(W):
            if grid[r][c] != 0 and r not in row_lines and c not in col_lines:
                best_dist = float('inf')
                best_color = grid[r][c]
                for rl, rv in row_lines.items():
                    d = abs(r - rl)
                    if d < best_dist:
                        best_dist = d
                        best_color = rv
                for cl, cv in col_lines.items():
                    d = abs(c - cl)
                    if d < best_dist:
                        best_dist = d
                        best_color = cv
                result[r][c] = best_color
    return result


def draw_diagonal_segment_between_pairs(grid):
    H = len(grid)
    W = len(grid[0])
    from collections import defaultdict
    color_cells = defaultdict(list)
    for r in range(H):
        for c in range(W):
            if grid[r][c] != 0:
                color_cells[grid[r][c]].append((r, c))
    result = [list(row) for row in grid]
    for v, cells in color_cells.items():
        if len(cells) != 2:
            continue
        (r1, c1), (r2, c2) = cells
        if r1 - c1 == r2 - c2:
            dr = 1 if r2 > r1 else -1
            steps = abs(r2 - r1)
            for i in range(steps + 1):
                result[r1 + i * dr][c1 + i * dr] = v
        elif r1 + c1 == r2 + c2:
            dr = 1 if r2 > r1 else -1
            steps = abs(r2 - r1)
            for i in range(steps + 1):
                result[r1 + i * dr][c1 - i * dr] = v
    return result


def fill_between_markers_with_3(grid):
    H = len(grid)
    W = len(grid[0])
    result = [list(row) for row in grid]
    eights = [(r, c) for r in range(H) for c in range(W) if grid[r][c] == 8]
    for i in range(len(eights)):
        for j in range(i + 1, len(eights)):
            r1, c1 = eights[i]
            r2, c2 = eights[j]
            if r1 == r2:
                for c in range(min(c1, c2) + 1, max(c1, c2)):
                    result[r1][c] = 3
            elif c1 == c2:
                for r in range(min(r1, r2) + 1, max(r1, r2)):
                    result[r][c1] = 3
    return result


def extract_anomaly_panel(grid):
    H = len(grid)
    W = len(grid[0])
    div_rows = [r for r in range(H) if len(set(grid[r])) == 1 and grid[r][0] != 0]
    div_cols = [c for c in range(W) if len(set(grid[r][c] for r in range(H))) == 1 and grid[0][c] != 0]
    if not div_rows or not div_cols:
        return [list(row) for row in grid]
    row_bounds = [-1] + div_rows + [H]
    col_bounds = [-1] + div_cols + [W]
    for i in range(len(row_bounds) - 1):
        for j in range(len(col_bounds) - 1):
            r1, r2 = row_bounds[i] + 1, row_bounds[i + 1]
            c1, c2 = col_bounds[j] + 1, col_bounds[j + 1]
            panel = [list(grid[r][c1:c2]) for r in range(r1, r2)]
            flat = [v for row in panel for v in row]
            if len(set(flat)) > 1:
                return panel
    return [list(row) for row in grid]


def extract_horizontal_tile(grid):
    H = len(grid)
    W = len(grid[0])
    for d in range(1, W):
        if W % d == 0 and d < W:
            tile = [list(row[:d]) for row in grid]
            mirror = [list(reversed(row)) for row in tile]
            ok = True
            for start in range(d, W, d):
                segment = [list(grid[r][start:start + d]) for r in range(H)]
                if segment != tile and segment != mirror:
                    ok = False
                    break
            if ok:
                return tile
    return [list(row) for row in grid]


def xor_halves_replace_3(grid):
    H = len(grid)
    W = len(grid[0])
    div_row = -1
    for r in range(H):
        vals = set(grid[r])
        if len(vals) == 1 and 0 not in vals:
            div_row = r
            break
    if div_row < 0:
        return [list(row) for row in grid]
    top = grid[:div_row]
    bottom = grid[div_row+1:]
    n = min(len(top), len(bottom))
    result = []
    for r in range(n):
        row = []
        for c in range(W):
            t = top[r][c] != 0
            b = bottom[r][c] != 0
            row.append(3 if t != b else 0)
        result.append(row)
    return result


def gravity_1_to_5(grid):
    H = len(grid)
    W = len(grid[0])
    result = [list(row) for row in grid]
    for c in range(W):
        ones = [r for r in range(H) if grid[r][c] == 1]
        for r1 in ones:
            fives_below = [r2 for r2 in range(r1+1, H) if grid[r2][c] == 5]
            if fives_below:
                target = max(fives_below)
                result[r1][c] = 0
                result[target][c] = 1
    return result


def stamp_template_on_8_blocks(grid):
    H = len(grid); W = len(grid[0])
    visited = [[False]*W for _ in range(H)]
    template_cells = []
    for r in range(H):
        for c in range(W):
            if grid[r][c] != 0 and grid[r][c] != 8 and not visited[r][c]:
                stack = [(r,c)]; cells = []
                while stack:
                    cr,cc = stack.pop()
                    if not(0<=cr<H and 0<=cc<W) or visited[cr][cc] or grid[cr][cc]==0 or grid[cr][cc]==8: continue
                    visited[cr][cc] = True; cells.append((cr,cc,grid[cr][cc]))
                    for dr,dc in [(0,1),(0,-1),(1,0),(-1,0)]: stack.append((cr+dr,cc+dc))
                template_cells = cells
                break
        if template_cells: break
    if not template_cells: return [list(row) for row in grid]
    r0 = min(r for r,c,v in template_cells)
    c0 = min(c for r,c,v in template_cells)
    tmpl = {(r-r0, c-c0): v for r,c,v in template_cells}
    visited2 = [[False]*W for _ in range(H)]
    eight_blocks = []
    for r in range(H):
        for c in range(W):
            if grid[r][c] == 8 and not visited2[r][c]:
                stack = [(r,c)]; cells = []
                while stack:
                    cr,cc = stack.pop()
                    if not(0<=cr<H and 0<=cc<W) or visited2[cr][cc] or grid[cr][cc]!=8: continue
                    visited2[cr][cc] = True; cells.append((cr,cc))
                    for dr,dc in [(0,1),(0,-1),(1,0),(-1,0)]: stack.append((cr+dr,cc+dc))
                eight_blocks.append(cells)
    result = [[0]*W for _ in range(H)]
    for block in eight_blocks:
        br = min(r for r,c in block)
        bc = min(c for r,c in block)
        for dr,dc in tmpl:
            nr,nc = br+dr, bc+dc
            if 0<=nr<H and 0<=nc<W:
                result[nr][nc] = tmpl[(dr,dc)]
    return result


def gravity_2_into_holes(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    one_rows = [r for r in range(H) if any(grid[r][c]==1 for c in range(W))]
    if not one_rows: return result
    rect_top = min(one_rows); rect_bot = max(one_rows)
    for c in range(W):
        twos = [r for r in range(H) if grid[r][c]==2]
        if not twos: continue
        holes = [r for r in range(rect_top, rect_bot+1) if grid[r][c]==0]
        if not holes: continue
        top_hole = min(holes)
        top_two = min(twos)
        shift = top_two - top_hole
        for r in twos: result[r][c] = 0
        for r in twos:
            new_r = r - shift
            if 0 <= new_r < H: result[new_r][c] = 2
    return result


def place_template_at_1_markers(grid):
    H = len(grid); W = len(grid[0])
    div_col = -1
    for c in range(W):
        if all(grid[r][c]==5 for r in range(H)): div_col = c; break
    if div_col < 0: return [list(row) for row in grid]
    tmpl_h = 0
    for r in range(H):
        if any(grid[r][c]!=0 for c in range(div_col)): tmpl_h = r + 1
        else: break
    tmpl_w = div_col
    template = [list(grid[r][:tmpl_w]) for r in range(tmpl_h)]
    markers = [(r,c) for r in range(H) for c in range(W) if grid[r][c]==1]
    result = [list(row) for row in grid]
    for r,c in markers: result[r][c] = 0
    half_h = tmpl_h // 2; half_w = tmpl_w // 2
    for mr, mc in markers:
        r0 = mr - half_h; c0 = mc - half_w
        for dr in range(tmpl_h):
            for dc in range(tmpl_w):
                nr = r0 + dr; nc = c0 + dc
                if 0 <= nr < H and 0 <= nc < W:
                    result[nr][nc] = template[dr][dc]
    return result


def crop_shape_recolor_to_corners(grid):
    H = len(grid); W = len(grid[0])
    from collections import defaultdict
    color_cells = defaultdict(list)
    for r in range(H):
        for c in range(W):
            if grid[r][c] != 0: color_cells[grid[r][c]].append((r,c))
    corner_color = None
    for color, cells in color_cells.items():
        if len(cells) == 4:
            rs2 = [r for r,c in cells]; cs2 = [c for r,c in cells]
            if len(set(rs2)) == 2 and len(set(cs2)) == 2:
                corner_color = color; break
    if corner_color is None: return [list(row) for row in grid]
    shape_colors = [c for c in color_cells if c != corner_color]
    if not shape_colors: return [list(row) for row in grid]
    shape_color = shape_colors[0]
    corner_cells = color_cells[corner_color]
    rs2 = sorted(set(r for r,c in corner_cells)); cs2 = sorted(set(c for r,c in corner_cells))
    r_top = rs2[0]+1; r_bot = rs2[1]-1; c_left = cs2[0]+1; c_right = cs2[1]-1
    inner_h = r_bot - r_top + 1; inner_w = c_right - c_left + 1
    result = [[0]*inner_w for _ in range(inner_h)]
    for r, c in color_cells[shape_color]:
        nr = r - r_top; nc = c - c_left
        if 0 <= nr < inner_h and 0 <= nc < inner_w:
            result[nr][nc] = corner_color
    return result


def stripe_middle_row_of_3tall(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    r = 0
    while r < H:
        if r + 2 < H:
            cols_top = [c for c in range(W) if grid[r][c] != 0]
            cols_mid = [c for c in range(W) if grid[r+1][c] != 0]
            cols_bot = [c for c in range(W) if grid[r+2][c] != 0]
            color_top = set(grid[r][c] for c in cols_top)
            color_mid = set(grid[r+1][c] for c in cols_mid)
            color_bot = set(grid[r+2][c] for c in cols_bot)
            if (len(color_top)==1 and len(color_mid)==1 and len(color_bot)==1 and
                color_top == color_mid == color_bot and cols_top == cols_mid == cols_bot and
                len(cols_top) > 0 and
                (r+3 >= H or all(grid[r+3][c]==0 for c in cols_top)) and
                (r == 0 or all(grid[r-1][c]==0 for c in cols_top))):
                c_start = cols_top[0]
                for c in cols_top:
                    if (c - c_start) % 2 == 1: result[r+1][c] = 0
                r += 3; continue
        r += 1
    return result


def tile_2x2_reflection(grid):
    H = len(grid); W = len(grid[0])
    result = [[0]*(2*W) for _ in range(2*H)]
    for r in range(H):
        for c in range(W):
            result[r][c] = grid[r][c]
            result[r][2*W-1-c] = grid[r][c]
            result[2*H-1-r][c] = grid[r][c]
            result[2*H-1-r][2*W-1-c] = grid[r][c]
    return result


def draw_antidiag_and_base(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    for r in range(H-1):
        c = W - 1 - r
        if 1 <= c < W: result[r][c] = 2
    for c in range(1, W): result[H-1][c] = 4
    return result


def color_of_larger_rectangle(grid):
    H = len(grid); W = len(grid[0])
    from collections import defaultdict
    color_cells = defaultdict(list)
    for r in range(H):
        for c in range(W):
            if grid[r][c] != 0: color_cells[grid[r][c]].append((r,c))
    def bbox_area(cells):
        rs = [r for r,c in cells]; cs = [c for r,c in cells]
        return (max(rs)-min(rs)+1) * (max(cs)-min(cs)+1)
    items = sorted(color_cells.items(), key=lambda x: bbox_area(x[1]), reverse=True)
    winner = items[0][0]
    return [[winner, winner], [winner, winner]]


def mark_inner_corner_of_l_shapes(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    visited = [[False]*W for _ in range(H)]
    for sr in range(H):
        for sc in range(W):
            if grid[sr][sc] != 0 and not visited[sr][sc]:
                color = grid[sr][sc]; stack = [(sr,sc)]; cells = set()
                while stack:
                    r,c = stack.pop()
                    if not(0<=r<H and 0<=c<W) or visited[r][c] or grid[r][c]!=color: continue
                    visited[r][c] = True; cells.add((r,c))
                    for dr,dc in [(0,1),(0,-1),(1,0),(-1,0)]: stack.append((r+dr,c+dc))
                rows2 = set(r for r,c in cells); cols2 = set(c for r,c in cells)
                r0,r1 = min(rows2),max(rows2); c0,c1 = min(cols2),max(cols2)
                for r in range(r0,r1+1):
                    for c in range(c0,c1+1):
                        if (r,c) not in cells and grid[r][c]==0:
                            nbrs = sum(1 for dr,dc in [(0,1),(0,-1),(1,0),(-1,0)] if (r+dr,c+dc) in cells)
                            if nbrs >= 2: result[r][c] = 1
    return result


def extract_5bordered_region(grid):
    H = len(grid); W = len(grid[0])
    five_cells = [(r,c) for r in range(H) for c in range(W) if grid[r][c]==5]
    if not five_cells: return [list(row) for row in grid]
    c_left = min(c for r,c in five_cells); c_right = max(c for r,c in five_cells)
    r_five_top = min(r for r,c in five_cells); r_five_bot = max(r for r,c in five_cells)
    r_top = r_five_top - 1; r_bot = r_five_bot + 1
    if r_top < 0 or r_bot >= H: return [list(row) for row in grid]
    return [list(grid[r][c_left:c_right+1]) for r in range(r_top, r_bot+1)]


def symmetric_returns_1_or_7(grid):
    flipped = [list(reversed(row)) for row in grid]
    if grid == flipped: return [[1]]
    return [[7]]


def expand_cells_to_4x4_blocks(grid):
    H = len(grid); W = len(grid[0])
    outH = H*2; outW = W*2
    result = [[0]*outW for _ in range(outH)]
    for r in range(H):
        for c in range(W):
            if grid[r][c] != 0:
                br = (r-1)*2; bc = (c-1)*2
                for dr in range(4):
                    for dc in range(4):
                        nr = br+dr; nc = bc+dc
                        if 0 <= nr < outH and 0 <= nc < outW:
                            result[nr][nc] = grid[r][c]
    return result


def expand_with_row_col_echo(grid):
    H = len(grid); W = len(grid[0])
    outH = H + 2; outW = W + 2
    result = [[0]*outW for _ in range(outH)]
    result[0] = [0] + list(grid[0]) + [0]
    result[outH-1] = [0] + list(grid[H-1]) + [0]
    for r in range(H):
        result[r+1] = [grid[r][0]] + list(grid[r]) + [grid[r][-1]]
    return result


def remove_isolated_cells_8conn(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    for r in range(H):
        for c in range(W):
            if grid[r][c] != 0:
                has_nbr = any(0<=r+dr<H and 0<=c+dc<W and grid[r+dr][c+dc]==grid[r][c]
                              for dr in [-1,0,1] for dc in [-1,0,1] if (dr,dc)!=(0,0))
                if not has_nbr: result[r][c] = 0
    return result


def draw_cross_through_all_1rect_centers(grid):
    H = len(grid); W = len(grid[0])
    bg = grid[0][0]
    visited = [[False]*W for _ in range(H)]
    rects = []
    for sr in range(H):
        for sc in range(W):
            if grid[sr][sc]==1 and not visited[sr][sc]:
                stack = [(sr,sc)]; cells = []
                while stack:
                    r,c = stack.pop()
                    if not(0<=r<H and 0<=c<W) or visited[r][c] or grid[r][c]!=1: continue
                    visited[r][c]=True; cells.append((r,c))
                    for dr,dc in [(0,1),(0,-1),(1,0),(-1,0)]: stack.append((r+dr,c+dc))
                rs2 = [r for r,c in cells]; cs2 = [c for r,c in cells]
                rects.append((min(rs2),max(rs2),min(cs2),max(cs2)))
    result = [list(row) for row in grid]
    for r0,r1,c0,c1 in rects:
        center_r = (r0+r1)//2; center_c = (c0+c1)//2
        for c in range(W):
            if result[center_r][c] == bg: result[center_r][c] = 6
        for r in range(H):
            if result[r][center_c] == bg: result[r][center_c] = 6
    return result


def fill_with_most_common_color(grid):
    H = len(grid); W = len(grid[0])
    from collections import Counter
    flat = [v for row in grid for v in row]
    mc = Counter(flat).most_common(1)[0][0]
    return [[mc]*W for _ in range(H)]


def extract_color_per_3x3_block(grid):
    H = len(grid); W = len(grid[0])
    block_h = H//3; block_w = W//3
    result = []
    for bi in range(block_h):
        row = []
        for bj in range(block_w):
            colors = [grid[bi*3+r][bj*3+c] for r in range(3) for c in range(3) if grid[bi*3+r][bj*3+c] not in (0,5)]
            row.append(colors[0] if colors else 0)
        result.append(row)
    return result


def flip_rows_and_append(grid):
    return list(reversed(grid)) + list(grid)


def extract_top_right_3x3(grid):
    W = len(grid[0])
    return [list(row[W-3:]) for row in grid[:3]]


def select_non_diagonal_symmetric_panel(grid):
    H = len(grid); W = len(grid[0])
    n = H // 3
    panels = [grid[j*3:(j+1)*3] for j in range(n)]
    for p in panels:
        is_sym = all(p[i][j] == p[j][i] for i in range(3) for j in range(3))
        if not is_sym:
            return [list(row) for row in p]
    return [list(row) for row in panels[0]]


def count_nonzero_blocks_ge2(grid):
    H = len(grid); W = len(grid[0])
    div_rows = [r for r in range(H) if all(grid[r][c]==8 for c in range(W))]
    div_cols = [c for c in range(W) if all(grid[r][c]==8 for r in range(H))]
    row_groups = []
    prev = 0
    for dr in div_rows + [H]:
        if dr > prev: row_groups.append(list(range(prev, dr)))
        prev = dr + 1
    col_groups = []
    prev = 0
    for dc in div_cols + [W]:
        if dc > prev: col_groups.append(list(range(prev, dc)))
        prev = dc + 1
    result = []
    for rg in row_groups:
        row = []
        for cg in col_groups:
            count = sum(1 for r in rg for c in cg if grid[r][c] not in (0, 8))
            row.append(1 if count >= 2 else 0)
        result.append(row)
    return result


def tile_two_shapes_into_3x3(grid):
    H = len(grid); W = len(grid[0])
    from collections import defaultdict
    color_cells = defaultdict(list)
    for r in range(H):
        for c in range(W):
            if grid[r][c] != 0:
                color_cells[grid[r][c]].append((r, c))
    colors = list(color_cells.keys())
    if len(colors) < 2: return [[0]*3 for _ in range(3)]
    def normalize(cells):
        r0 = min(r for r,c in cells); c0 = min(c for r,c in cells)
        return frozenset((r-r0, c-c0) for r,c in cells)
    shapes = [(colors[i], normalize(color_cells[colors[i]])) for i in range(2)]
    all_cells = frozenset((r,c) for r in range(3) for c in range(3))
    for r0 in range(3):
        for c0 in range(3):
            s0 = frozenset((r+r0, c+c0) for r,c in shapes[0][1])
            if not s0.issubset(all_cells): continue
            remain = all_cells - s0
            if len(remain) != len(shapes[1][1]): continue
            for r1 in range(3):
                for c1 in range(3):
                    s1 = frozenset((r+r1, c+c1) for r,c in shapes[1][1])
                    if s1 == remain:
                        result = [[0]*3 for _ in range(3)]
                        for r,c in s0: result[r][c] = shapes[0][0]
                        for r,c in s1: result[r][c] = shapes[1][0]
                        return result
    return [[0]*3 for _ in range(3)]


def recolor_non_singleton_3_to_8(grid):
    H = len(grid); W = len(grid[0])
    visited = [[False]*W for _ in range(H)]
    components = []
    for sr in range(H):
        for sc in range(W):
            if grid[sr][sc] == 3 and not visited[sr][sc]:
                stack = [(sr,sc)]; cells = []
                while stack:
                    r,c = stack.pop()
                    if not(0<=r<H and 0<=c<W) or visited[r][c] or grid[r][c]!=3: continue
                    visited[r][c] = True; cells.append((r,c))
                    for dr,dc in [(0,1),(0,-1),(1,0),(-1,0)]: stack.append((r+dr,c+dc))
                components.append(cells)
    result = [list(row) for row in grid]
    for cells in components:
        if len(cells) >= 2:
            for r,c in cells: result[r][c] = 8
    return result


def fill_rect_interior_by_size_rank(grid):
    H = len(grid); W = len(grid[0])
    visited = [[False]*W for _ in range(H)]
    rects = []
    for sr in range(H):
        for sc in range(W):
            if grid[sr][sc] != 0 and not visited[sr][sc]:
                color = grid[sr][sc]; stack = [(sr,sc)]; cells = []
                while stack:
                    r,c = stack.pop()
                    if not(0<=r<H and 0<=c<W) or visited[r][c] or grid[r][c]!=color: continue
                    visited[r][c]=True; cells.append((r,c))
                    for dr,dc in [(0,1),(0,-1),(1,0),(-1,0)]: stack.append((r+dr,c+dc))
                rs = [r for r,c in cells]; cs = [c for r,c in cells]
                r0,r1,c0,c1 = min(rs),max(rs),min(cs),max(cs)
                inner_h = r1-r0-1; inner_w = c1-c0-1
                inner_area = inner_h * inner_w if inner_h > 0 and inner_w > 0 else 0
                rects.append((inner_area, r0, r1, c0, c1))
    if len(rects) < 2: return [list(row) for row in grid]
    rects_sorted = sorted(rects, key=lambda x: x[0])
    result = [list(row) for row in grid]
    for area, r0, r1, c0, c1 in rects:
        if (r1-r0-1) > 0 and (c1-c0-1) > 0:
            fill_val = 1 if (r0,r1,c0,c1) == rects_sorted[0][1:] else 2
            for r in range(r0+1, r1):
                for c in range(c0+1, c1):
                    result[r][c] = fill_val
    return result


def recolor_3x3_frames_to_cross_2(grid):
    H = len(grid); W = len(grid[0])
    visited = [[False]*W for _ in range(H)]
    result = [list(row) for row in grid]
    for sr in range(H):
        for sc in range(W):
            if grid[sr][sc] == 1 and not visited[sr][sc]:
                stack = [(sr,sc)]; cells = []
                while stack:
                    r,c = stack.pop()
                    if not(0<=r<H and 0<=c<W) or visited[r][c] or grid[r][c]!=1: continue
                    visited[r][c]=True; cells.append((r,c))
                    for dr,dc in [(0,1),(0,-1),(1,0),(-1,0)]: stack.append((r+dr,c+dc))
                if len(cells) == 8:
                    rs = set(r for r,c in cells); cs = set(c for r,c in cells)
                    if len(rs)==3 and len(cs)==3:
                        r0,r1 = min(rs),max(rs); c0,c1 = min(cs),max(cs)
                        if r1-r0==2 and c1-c0==2:
                            for r,c in cells: result[r][c] = 0
                            cr = (r0+r1)//2; cc = (c0+c1)//2
                            result[r0][cc] = 2; result[r1][cc] = 2
                            result[cr][c0] = 2; result[cr][c1] = 2
                            result[cr][cc] = 2
    return result


def color_count_to_diagonal(grid):
    H = len(grid); W = len(grid[0])
    colors = set(v for row in grid for v in row)
    n = len(colors)
    result = [[0]*W for _ in range(H)]
    if n == 1:
        for c in range(W): result[0][c] = 5
    elif n == 2:
        for i in range(min(H,W)): result[i][i] = 5
    else:
        for i in range(min(H,W)): result[i][W-1-i] = 5
    return result


def tile_horizontal_mirror(grid):
    return [list(row) + list(reversed(row)) for row in grid]


def extend_l_shapes_diagonally(grid):
    H = len(grid); W = len(grid[0])
    visited = [[False]*W for _ in range(H)]
    result = [list(row) for row in grid]
    for sr in range(H):
        for sc in range(W):
            if grid[sr][sc] != 0 and not visited[sr][sc]:
                color = grid[sr][sc]; stack = [(sr,sc)]; cells = []
                while stack:
                    r,c = stack.pop()
                    if not(0<=r<H and 0<=c<W) or visited[r][c] or grid[r][c]!=color: continue
                    visited[r][c]=True; cells.append((r,c))
                    for dr,dc in [(0,1),(0,-1),(1,0),(-1,0)]: stack.append((r+dr,c+dc))
                if len(cells) == 3:
                    rs = [r for r,c in cells]; cs = [c for r,c in cells]
                    rmin,rmax = min(rs),max(rs); cmin,cmax = min(cs),max(cs)
                    if rmax-rmin == 1 and cmax-cmin == 1:
                        cell_set = set(map(tuple, cells))
                        corners = [(rmin,cmin),(rmin,cmax),(rmax,cmin),(rmax,cmax)]
                        for corner in corners:
                            if corner not in cell_set:
                                dr = -1 if corner[0] == rmin else 1
                                dc = -1 if corner[1] == cmin else 1
                                r,c = corner[0]+dr, corner[1]+dc
                                while 0<=r<H and 0<=c<W:
                                    result[r][c] = color
                                    r += dr; c += dc
                                break
    return result


def fill_8_component_interior_with_2(grid):
    H = len(grid); W = len(grid[0])
    eights = [(r,c) for r in range(H) for c in range(W) if grid[r][c]==8]
    if not eights: return [list(row) for row in grid]
    r0 = min(r for r,c in eights); r1 = max(r for r,c in eights)
    c0 = min(c for r,c in eights); c1 = max(c for r,c in eights)
    result = [list(row) for row in grid]
    for r in range(r0, r1+1):
        for c in range(c0, c1+1):
            if result[r][c] == 0: result[r][c] = 2
    return result


def recolor_5_components_by_size(grid):
    H = len(grid); W = len(grid[0])
    visited = [[False]*W for _ in range(H)]
    result = [list(row) for row in grid]
    size_color = {4: 1, 3: 2, 2: 3}
    for sr in range(H):
        for sc in range(W):
            if grid[sr][sc] == 5 and not visited[sr][sc]:
                stack = [(sr,sc)]; cells = []
                while stack:
                    r,c = stack.pop()
                    if not(0<=r<H and 0<=c<W) or visited[r][c] or grid[r][c]!=5: continue
                    visited[r][c]=True; cells.append((r,c))
                    for dr,dc in [(0,1),(0,-1),(1,0),(-1,0)]: stack.append((r+dr,c+dc))
                new_color = size_color.get(len(cells), 0)
                for r,c in cells: result[r][c] = new_color
    return result


def transpose_grid(grid):
    return [[grid[r][c] for r in range(len(grid))] for c in range(len(grid[0]))]


def fill_border_with_8(grid):
    H = len(grid); W = len(grid[0])
    result = [[0]*W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if r == 0 or r == H-1 or c == 0 or c == W-1:
                result[r][c] = 8
    return result


def tile_vertical_mirror(grid):
    return list(grid) + list(reversed(grid))


def deduplicate_runs(grid):
    def dedup_row(row):
        result = [row[0]]
        for v in row[1:]:
            if v != result[-1]: result.append(v)
        return result
    rows = [dedup_row(row) for row in grid]
    deduped = [rows[0]]
    for row in rows[1:]:
        if row != deduped[-1]: deduped.append(row)
    return deduped


def overlay_quadrants_tr_bl_br_tl(grid):
    H = len(grid); W = len(grid[0])
    hH = H // 2; hW = W // 2
    quads = [
        [[grid[r][c+hW] for c in range(hW)] for r in range(hH)],
        [[grid[r+hH][c] for c in range(hW)] for r in range(hH)],
        [[grid[r+hH][c+hW] for c in range(hW)] for r in range(hH)],
        [[grid[r][c] for c in range(hW)] for r in range(hH)],
    ]
    result = [[0]*hW for _ in range(hH)]
    for r in range(hH):
        for c in range(hW):
            for q in quads:
                if q[r][c] != 0:
                    result[r][c] = q[r][c]
                    break
    return result


def recolor_8s_by_nearest_corner(grid):
    H = len(grid); W = len(grid[0])
    div_rows = [r for r in range(H) if all(grid[r][c]==1 for c in range(W))]
    div_cols = [c for c in range(W) if all(grid[r][c]==1 for r in range(H))]
    if not div_rows or not div_cols: return [list(row) for row in grid]
    r0 = div_rows[0]+1; r1 = div_rows[-1]-1
    c0 = div_cols[0]+1; c1 = div_cols[-1]-1
    corners = [(0,0,grid[0][0]), (0,W-1,grid[0][W-1]), (H-1,0,grid[H-1][0]), (H-1,W-1,grid[H-1][W-1])]
    result = [[0]*(c1-c0+1) for _ in range(r1-r0+1)]
    for ri,r in enumerate(range(r0, r1+1)):
        for ci,c in enumerate(range(c0, c1+1)):
            if grid[r][c] == 8:
                best_dist = float('inf'); best_val = 0
                for cr,cc,cv in corners:
                    d = (r-cr)**2 + (c-cc)**2
                    if d < best_dist: best_dist = d; best_val = cv
                result[ri][ci] = best_val
    return result


def extract_minimal_tile(grid):
    H = len(grid); W = len(grid[0])
    if W % 2 == 0:
        half = W // 2
        if all(grid[r][:half] == grid[r][half:] for r in range(H)):
            return extract_minimal_tile([row[:half] for row in grid])
    if H % 2 == 0:
        half = H // 2
        if grid[:half] == grid[half:]:
            return extract_minimal_tile(grid[:half])
    return [list(row) for row in grid]


def gravity_1s_count_to_2s(grid):
    H = len(grid); W = len(grid[0])
    count = sum(v for row in grid for v in row)
    center = W // 2
    def fill_order():
        for r in range(H):
            row_cols = sorted(range(W), key=lambda c: (abs(c - center), c) if r > 0 else c)
            for c in row_cols:
                yield (r, c)
    result = [[0]*W for _ in range(H)]
    gen = fill_order()
    for _ in range(count):
        r, c = next(gen)
        result[r][c] = 2
    return result


def gravity_cell_mark_col_parity(grid):
    H = len(grid); W = len(grid[0])
    r0 = c0 = val = None
    for r in range(H):
        for c in range(W):
            if grid[r][c] != 0:
                r0, c0, val = r, c, grid[r][c]
    result = [[0]*W for _ in range(H)]
    parity = c0 % 2
    for r in range(r0+1):
        for c in range(W):
            if c % 2 == parity:
                result[r][c] = 4
    if r0+1 < H:
        result[r0+1][c0] = val
    return result


def fill_col_stripes_with_diamond_5(grid):
    H = len(grid); W = len(grid[0])
    r0=c0=val=None
    for r in range(H):
        for c in range(W):
            if grid[r][c]!=0: r0,c0,val=r,c,grid[r][c]
    result = [[0]*W for _ in range(H)]
    for c in range(c0, W, 2):
        for r in range(H):
            result[r][c] = val
    gap_idx = 0
    for g in range(c0+1, W, 2):
        target_row = 0 if gap_idx % 2 == 0 else H-1
        result[target_row][g] = 5
        gap_idx += 1
    return result


def extend_diagonal_tails_from_block(grid):
    H = len(grid); W = len(grid[0])
    color = next(v for row in grid for v in row if v != 0)
    cells = set((r,c) for r in range(H) for c in range(W) if grid[r][c]!=0)
    block = set()
    for r,c in cells:
        if (r+1,c) in cells and (r,c+1) in cells and (r+1,c+1) in cells:
            block = {(r,c),(r+1,c),(r,c+1),(r+1,c+1)}
            break
    tails = cells - block
    result = [list(row) for row in grid]
    for tr,tc in tails:
        best_dist = float('inf'); br=bc=None
        for r,c in block:
            d = abs(tr-r)+abs(tc-c)
            if d < best_dist: best_dist=d; br,bc=r,c
        dr = tr-br; dc = tc-bc
        r,c = tr+dr, tc+dc
        while 0<=r<H and 0<=c<W:
            result[r][c] = color
            r+=dr; c+=dc
    return result


def recolor_closed_frames_to_3(grid):
    H = len(grid); W = len(grid[0])
    visited = [[False]*W for _ in range(H)]
    result = [list(row) for row in grid]
    for sr in range(H):
        for sc in range(W):
            if grid[sr][sc] == 1 and not visited[sr][sc]:
                stack = [(sr,sc)]; cells = []
                while stack:
                    r,c = stack.pop()
                    if not(0<=r<H and 0<=c<W) or visited[r][c] or grid[r][c]!=1: continue
                    visited[r][c]=True; cells.append((r,c))
                    for dr,dc in [(0,1),(0,-1),(1,0),(-1,0)]: stack.append((r+dr,c+dc))
                rs = [r for r,c in cells]; cs = [c for r,c in cells]
                r0,r1,c0,c1 = min(rs),max(rs),min(cs),max(cs)
                if r1>r0 and c1>c0:
                    perimeter = set()
                    for r in range(r0,r1+1):
                        for c in range(c0,c1+1):
                            if r==r0 or r==r1 or c==c0 or c==c1:
                                perimeter.add((r,c))
                    if set(cells) == perimeter:
                        for r,c in cells: result[r][c] = 3
    return result


def fill_frame_interiors_by_parity(grid):
    H = len(grid); W = len(grid[0])
    visited = [[False]*W for _ in range(H)]
    result = [list(row) for row in grid]
    for sr in range(H):
        for sc in range(W):
            if grid[sr][sc] == 1 and not visited[sr][sc]:
                stack = [(sr,sc)]; cells = []
                while stack:
                    r,c = stack.pop()
                    if not(0<=r<H and 0<=c<W) or visited[r][c] or grid[r][c]!=1: continue
                    visited[r][c]=True; cells.append((r,c))
                    for dr,dc in [(0,1),(0,-1),(1,0),(-1,0)]: stack.append((r+dr,c+dc))
                rs = [r for r,c in cells]; cs = [c for r,c in cells]
                r0,r1,c0,c1 = min(rs),max(rs),min(cs),max(cs)
                if r1>r0 and c1>c0:
                    perimeter = set((r,c) for r in range(r0,r1+1) for c in range(c0,c1+1) if r==r0 or r==r1 or c==c0 or c==c1)
                    if set(cells) == perimeter:
                        interior = [(r,c) for r in range(r0+1,r1) for c in range(c0+1,c1)]
                        inner_area = (r1-r0-1)*(c1-c0-1)
                        fill = 2 if inner_area % 2 == 0 else 7
                        for r,c in interior: result[r][c] = fill
    return result


def keep_max_color_replace_others_with_5(grid):
    from collections import Counter
    flat = [v for row in grid for v in row]
    keep = Counter(flat).most_common(1)[0][0]
    return [[v if v == keep else 5 for v in row] for row in grid]


def reflect_non_diagonal_cells(grid):
    H = len(grid); W = len(grid[0])
    result = [[0]*W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if grid[r][c] == 5: result[r][c] = 5
    for r in range(H):
        for c in range(W):
            if grid[r][c] != 0 and grid[r][c] != 5:
                if 0 <= c < H and 0 <= r < W:
                    result[c][r] = grid[r][c]
    return result


def tile_nz_times_in_canvas(grid):
    H = len(grid); W = len(grid[0])
    nz = sum(1 for row in grid for v in row if v != 0)
    N = H * W - nz
    result = [[0]*(N*W) for _ in range(N*H)]
    placed = 0
    for ti in range(N):
        for tj in range(N):
            if placed >= nz: break
            for r in range(H):
                for c in range(W):
                    result[ti*H+r][tj*W+c] = grid[r][c]
            placed += 1
        if placed >= nz: break
    return result


def sort_colors_by_count_to_columns(grid):
    from collections import Counter
    flat = [v for row in grid for v in row if v != 0]
    counts = Counter(flat).most_common()
    if not counts: return [[]]
    max_count = counts[0][1]
    W = len(counts)
    result = [[0]*W for _ in range(max_count)]
    for col, (color, cnt) in enumerate(counts):
        for r in range(cnt):
            result[r][col] = color
    return result


def classify_5block_pattern(grid):
    H = len(grid); W = len(grid[0])
    sep_cols = [c for c in range(W) if all(grid[r][c]==0 for r in range(H))]
    b_starts = [0] + [c+1 for c in sep_cols]
    b_ends = [c-1 for c in sep_cols] + [W-1]
    p2c = {
        frozenset(): 2,
        frozenset([(1,1),(1,2),(2,1),(2,2)]): 8,
        frozenset([(1,0),(1,3),(2,0),(2,3)]): 3,
        frozenset([(2,1),(2,2),(3,1),(3,2)]): 4,
    }
    out_rows = []
    for bs, be in zip(b_starts, b_ends):
        block = [grid[r][bs:be+1] for r in range(H)]
        zeros = frozenset((r,c) for r in range(len(block)) for c in range(len(block[0])) if block[r][c]==0)
        color = p2c.get(zeros, 0)
        out_rows.append([color]*3)
    return out_rows


def tile_horizontal(grid):
    return [list(row) + list(row) for row in grid]


def shift_8s_down_to_2(grid):
    H = len(grid); W = len(grid[0])
    result = [[0]*W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if grid[r][c] == 8:
                if r+1 < H: result[r+1][c] = 2
    return result


def fill_gap_between_1s_with_2(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    for r in range(H):
        ones = [c for c in range(W) if grid[r][c] == 1]
        if len(ones) >= 2:
            for c in range(ones[0]+1, ones[-1]):
                if grid[r][c] == 0: result[r][c] = 2
    return result


def shift_shape_inside_corner_box(grid):
    H = len(grid); W = len(grid[0])
    threes = [(r,c) for r in range(H) for c in range(W) if grid[r][c] == 3]
    r3 = [r for r,c in threes]; c3 = [c for r,c in threes]
    inner_r0, inner_c0 = min(r3)+1, min(c3)+1
    twos = [(r,c) for r in range(H) for c in range(W) if grid[r][c] == 2]
    min_r2 = min(r for r,c in twos); min_c2 = min(c for r,c in twos)
    dr = inner_r0 - min_r2; dc = inner_c0 - min_c2
    result = [[v if v != 2 else 0 for v in row] for row in grid]
    for r,c in twos:
        nr, nc = r+dr, c+dc
        if 0 <= nr < H and 0 <= nc < W:
            result[nr][nc] = 2
    return result


def extract_max_count_colors_sorted_by_column(grid):
    from collections import Counter
    flat = [(v, r, c) for r,row in enumerate(grid) for c,v in enumerate(row) if v != 0]
    cnt = Counter(v for v,r,c in flat)
    max_cnt = max(cnt.values())
    max_colors = [v for v,n in cnt.items() if n == max_cnt]
    leftmost = {}
    for v,r,c in flat:
        if v in max_colors:
            if v not in leftmost or c < leftmost[v]:
                leftmost[v] = c
    sorted_colors = sorted(max_colors, key=lambda v: leftmost[v])
    return [list(sorted_colors) for _ in range(max_cnt)]


def crop_non_border_region(grid):
    H = len(grid); W = len(grid[0])
    non1 = [(r,c) for r in range(H) for c in range(W) if grid[r][c] != 1]
    if not non1: return grid
    r0 = min(r for r,c in non1); r1 = max(r for r,c in non1)
    c0 = min(c for r,c in non1); c1 = max(c for r,c in non1)
    return [[0 if grid[r][c]==1 else grid[r][c] for c in range(c0,c1+1)] for r in range(r0,r1+1)]


def replace_non7_with_2(grid):
    return [[v if v == 7 else 2 for v in row] for row in grid]


def expand_cells_to_nonzero_count_blocks(grid):
    H = len(grid); W = len(grid[0])
    N = sum(1 for row in grid for v in row if v != 0)
    result = [[0]*(W*N) for _ in range(H*N)]
    for r in range(H):
        for c in range(W):
            if grid[r][c] != 0:
                for dr in range(N):
                    for dc in range(N):
                        result[r*N+dr][c*N+dc] = grid[r][c]
    return result


def mark_diagonal_corners_of_2(grid):
    H = len(grid); W = len(grid[0])
    result = [[0]*W for _ in range(H)]
    corner_map = {(-1,-1): 3, (-1,+1): 6, (+1,-1): 8, (+1,+1): 7}
    for r in range(H):
        for c in range(W):
            if grid[r][c] == 2:
                for (dr,dc),v in corner_map.items():
                    nr,nc = r+dr, c+dc
                    if 0<=nr<H and 0<=nc<W:
                        result[nr][nc] = v
    return result


def extend_frame_to_marker_8(grid):
    H = len(grid); W = len(grid[0])
    er8 = ec8 = None
    for r in range(H):
        for c in range(W):
            if grid[r][c] == 8:
                er8, ec8 = r, c
    nz = [(r,c) for r in range(H) for c in range(W) if grid[r][c] not in (0,8)]
    if not nz or er8 is None: return [list(row) for row in grid]
    fr0 = min(r for r,c in nz); fr1 = max(r for r,c in nz)
    fc0 = min(c for r,c in nz); fc1 = max(c for r,c in nz)
    border_color = grid[fr0][fc0]
    interior_color = None
    for r in range(fr0+1, fr1):
        for c in range(fc0+1, fc1):
            if grid[r][c] != 0:
                interior_color = grid[r][c]; break
        if interior_color is not None: break
    result = [list(row) for row in grid]
    if er8 > fr1 and fc0 <= ec8 <= fc1:
        for r in range(fr1, er8+1):
            for c in range(fc0, fc1+1):
                if r == er8:
                    result[r][c] = border_color
                elif c == fc0 or c == fc1:
                    result[r][c] = border_color
                else:
                    result[r][c] = interior_color
    elif er8 < fr0 and fc0 <= ec8 <= fc1:
        for r in range(er8, fr0+1):
            for c in range(fc0, fc1+1):
                if r == er8:
                    result[r][c] = border_color
                elif c == fc0 or c == fc1:
                    result[r][c] = border_color
                else:
                    result[r][c] = interior_color
    elif ec8 > fc1 and fr0 <= er8 <= fr1:
        for r in range(fr0, fr1+1):
            for c in range(fc1, ec8+1):
                if r == fr0 or r == fr1:
                    result[r][c] = border_color
                elif c == ec8:
                    result[r][c] = border_color
                else:
                    result[r][c] = interior_color
    elif ec8 < fc0 and fr0 <= er8 <= fr1:
        for r in range(fr0, fr1+1):
            for c in range(ec8, fc0+1):
                if r == fr0 or r == fr1:
                    result[r][c] = border_color
                elif c == ec8:
                    result[r][c] = border_color
                else:
                    result[r][c] = interior_color
    return result


def mark_seed_5_with_cross_diag_pattern(grid):
    H = len(grid); W = len(grid[0])
    result = [[0]*W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if grid[r][c] == 5:
                for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nr,nc = r+dr, c+dc
                    if 0<=nr<H and 0<=nc<W: result[nr][nc] = 1
                for dr,dc in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                    nr,nc = r+dr, c+dc
                    if 0<=nr<H and 0<=nc<W: result[nr][nc] = 5
    return result


def recolor_5_blocks_as_frame(grid):
    H = len(grid); W = len(grid[0])
    visited = [[False]*W for _ in range(H)]
    result = [[0]*W for _ in range(H)]
    for r0 in range(H):
        for c0 in range(W):
            if grid[r0][c0] == 5 and not visited[r0][c0]:
                r1 = r0
                while r1+1 < H and grid[r1+1][c0] == 5: r1 += 1
                c1 = c0
                while c1+1 < W and grid[r0][c1+1] == 5: c1 += 1
                for r in range(r0, r1+1):
                    for c in range(c0, c1+1):
                        visited[r][c] = True
                        is_corner = (r == r0 or r == r1) and (c == c0 or c == c1)
                        is_border = r == r0 or r == r1 or c == c0 or c == c1
                        if is_corner: result[r][c] = 1
                        elif is_border: result[r][c] = 4
                        else: result[r][c] = 2
    return result


def scale_by_distinct_color_count(grid):
    H = len(grid); W = len(grid[0])
    N = len(set(v for row in grid for v in row if v != 0))
    result = [[0]*(W*N) for _ in range(H*N)]
    for r in range(H):
        for c in range(W):
            for dr in range(N):
                for dc in range(N):
                    result[r*N+dr][c*N+dc] = grid[r][c]
    return result


def invert_frame_interior_colors(grid):
    from collections import Counter
    H = len(grid); W = len(grid[0])
    nz = [(r,c,grid[r][c]) for r in range(H) for c in range(W) if grid[r][c] != 0]
    if not nz: return grid
    r0 = min(r for r,c,v in nz); r1 = max(r for r,c,v in nz)
    c0 = min(c for r,c,v in nz); c1 = max(c for r,c,v in nz)
    cnt = Counter(v for r,c,v in nz)
    colors = sorted(cnt, key=lambda v: -cnt[v])
    border_color = colors[0]; interior_color = colors[1] if len(colors)>1 else colors[0]
    out = []
    for r in range(r0, r1+1):
        row = []
        for c in range(c0, c1+1):
            v = grid[r][c]
            if v == border_color: row.append(interior_color)
            elif v == interior_color: row.append(border_color)
            else: row.append(v)
        out.append(row)
    return out


def extend_v_shape_diagonally(grid):
    H = len(grid); W = len(grid[0])
    nz = [(r,c,grid[r][c]) for r in range(H) for c in range(W) if grid[r][c] != 0]
    if not nz: return [list(row) for row in grid]
    r_max = max(r for r,c,v in nz)
    outer_color = None
    for c in range(W):
        if grid[r_max][c] != 0:
            candidate = grid[r_max][c]
            if any(r < r_max and grid[r][c2] == candidate for r,c2,v in nz):
                outer_color = candidate; break
    if outer_color is None:
        r_min = min(r for r,c,v in nz)
        outer_color = next(v for r,c,v in nz if r==r_min)
    inner_color = next(v for r,c,v in nz if v != outer_color)
    outer_cells = [(r,c) for r,c,v in nz if v==outer_color]
    r_top_outer = min(r for r,c in outer_cells)
    top_outer_cells = [(r,c) for r,c in outer_cells if r==r_top_outer]
    left_corner_c = min(c for r,c in top_outer_cells)
    right_corner_c = max(c for r,c in top_outer_cells)
    bottom_outer = [(r,c) for r,c in outer_cells if r==r_max]
    left_tip_c = min(c for r,c in bottom_outer)
    right_tip_c = max(c for r,c in bottom_outer)
    left_arm_len = left_corner_c - left_tip_c
    right_arm_len = right_tip_c - right_corner_c
    result = [list(row) for row in grid]
    for i in range(1, left_arm_len+1):
        nr,nc = r_top_outer-i, left_corner_c-i
        if 0<=nr<H and 0<=nc<W: result[nr][nc] = inner_color
    for i in range(1, right_arm_len+1):
        nr,nc = r_top_outer-i, right_corner_c+i
        if 0<=nr<H and 0<=nc<W: result[nr][nc] = inner_color
    return result


def draw_c_shapes_from_two_points(grid):
    H = len(grid); W = len(grid[0])
    pts = [(r,c,grid[r][c]) for r in range(H) for c in range(W) if grid[r][c]!=0]
    if len(pts)!=2: return [list(row) for row in grid]
    (r1,c1,v1),(r2,c2,v2) = pts
    result = [list(row) for row in grid]
    SPREAD = 2
    if r1==r2:
        if c1>c2: c1,c2,v1,v2=c2,c1,v2,v1
        d=c2-c1; dist_to_bar=(d-1)//2-1
        for dc in range(1, dist_to_bar): result[r1][c1+dc]=v1
        cb1=c1+dist_to_bar
        for dr in range(-SPREAD,SPREAD+1):
            if 0<=r1+dr<H: result[r1+dr][cb1]=v1
        for dr in [-SPREAD,SPREAD]:
            if 0<=r1+dr<H and cb1+1<W: result[r1+dr][cb1+1]=v1
        for dc in range(1, dist_to_bar): result[r2][c2-dc]=v2
        cb2=c2-dist_to_bar
        for dr in range(-SPREAD,SPREAD+1):
            if 0<=r2+dr<H: result[r2+dr][cb2]=v2
        for dr in [-SPREAD,SPREAD]:
            if 0<=r2+dr<H and cb2-1>=0: result[r2+dr][cb2-1]=v2
    elif c1==c2:
        if r1>r2: r1,r2,v1,v2=r2,r1,v2,v1
        d=r2-r1; dist_to_bar=(d-1)//2-1
        for dr in range(1, dist_to_bar): result[r1+dr][c1]=v1
        rb1=r1+dist_to_bar
        for dc in range(-SPREAD,SPREAD+1):
            if 0<=c1+dc<W: result[rb1][c1+dc]=v1
        for dc in [-SPREAD,SPREAD]:
            if 0<=c1+dc<W and rb1+1<H: result[rb1+1][c1+dc]=v1
        for dr in range(1, dist_to_bar): result[r2-dr][c2]=v2
        rb2=r2-dist_to_bar
        for dc in range(-SPREAD,SPREAD+1):
            if 0<=c2+dc<W: result[rb2][c2+dc]=v2
        for dc in [-SPREAD,SPREAD]:
            if 0<=c2+dc<W and rb2-1>=0: result[rb2-1][c2+dc]=v2
    return result


def find_hollow_shape_color(grid):
    H = len(grid); W = len(grid[0])
    colors = set(v for row in grid for v in row if v != 0)
    for color in colors:
        cells = [(r,c) for r in range(H) for c in range(W) if grid[r][c] == color]
        r0 = min(r for r,c in cells); r1 = max(r for r,c in cells)
        c0 = min(c for r,c in cells); c1 = max(c for r,c in cells)
        interior_zeros = [(r,c) for r in range(r0+1, r1) for c in range(c0+1, c1) if grid[r][c] == 0]
        if interior_zeros: return [[color]]
    return [[0]]


def staircase_fill_right(grid):
    row = grid[0]
    W = len(row)
    color = next(v for v in row if v != 0)
    count = sum(1 for v in row if v != 0)
    num_rows = W // 2
    result = []
    for i in range(num_rows):
        n = count + i
        result.append([color]*n + [0]*(W-n))
    return result


def fill_rows_with_color_cycle(grid):
    H = len(grid); W = len(grid[0])
    colors = [v for v in grid[0] if v != 0]
    result = [list(row) for row in grid]
    idx = 0
    for r in range(2, H):
        if all(v == 0 for v in grid[r]):
            c = colors[idx % len(colors)]
            result[r] = [c] * W
            idx += 1
    return result


def rotate_concentric_frame_colors(grid):
    H = len(grid); W = len(grid[0])
    rings = [[min(r, H-1-r, c, W-1-c) for c in range(W)] for r in range(H)]
    max_ring = max(v for row in rings for v in row)
    ring_vals = {}
    for r in range(H):
        for c in range(W):
            ring_vals[rings[r][c]] = grid[r][c]
    eff_max = max_ring
    if ring_vals[max_ring] == ring_vals[0]:
        eff_max = max_ring - 1
    new_vals = {k: ring_vals[(k-1) % (eff_max+1)] for k in range(eff_max+1)}
    if eff_max < max_ring:
        new_vals[max_ring] = new_vals[0]
    return [[new_vals[rings[r][c]] for c in range(W)] for r in range(H)]


def sort_segments_by_size_to_bottom_right(grid):
    H = len(grid); W = len(grid[0])
    segments = {}
    for row in grid:
        for v in row:
            if v != 0 and v not in segments:
                segments[v] = sum(1 for r in grid for x in r if x == v)
    segs = sorted(segments.items(), key=lambda x: x[1])
    result = [[0]*W for _ in range(H)]
    start_row = H - len(segs)
    for i, (color, count) in enumerate(segs):
        for c in range(W-count, W):
            result[start_row+i][c] = color
    return result


def extract_largest_shape_bounding_box(grid):
    from collections import Counter
    H = len(grid); W = len(grid[0])
    cnt = Counter(v for row in grid for v in row if v != 0)
    if not cnt: return [list(row) for row in grid]
    best_color = max(cnt, key=lambda v: cnt[v])
    cells = [(r,c) for r in range(H) for c in range(W) if grid[r][c] == best_color]
    r0 = min(r for r,c in cells); r1 = max(r for r,c in cells)
    c0 = min(c for r,c in cells); c1 = max(c for r,c in cells)
    return [[grid[r][c] for c in range(c0,c1+1)] for r in range(r0,r1+1)]


def fill_diagonal_stripe_pattern(grid):
    H = len(grid); W = len(grid[0])
    vals = sorted(set(v for row in grid for v in row if v != 0))
    n = len(vals); min_val = min(vals)
    offset = 0
    for r in range(H):
        for c in range(W):
            if grid[r][c] != 0:
                offset = (grid[r][c] - min_val - (r+c) % n) % n
                break
        else: continue
        break
    return [[(r+c+offset) % n + min_val for c in range(W)] for r in range(H)]


def scale_2x(grid):
    H = len(grid); W = len(grid[0])
    result = [[0]*(W*2) for _ in range(H*2)]
    for r in range(H):
        for c in range(W):
            result[r*2][c*2]=result[r*2][c*2+1]=result[r*2+1][c*2]=result[r*2+1][c*2+1]=grid[r][c]
    return result


def mirror_horizontal_append(grid):
    return [list(row) + list(reversed(row)) for row in grid]


def fill_5frame_interiors_by_size(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    visited = [[False]*W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if grid[r][c] == 5 and not visited[r][c] and r+2 < H and c+2 < W and grid[r][c+1] == 5:
                r1, c1 = r, c
                while r1+1 < H and grid[r1+1][c] == 5: r1 += 1
                while c1+1 < W and grid[r][c1+1] == 5: c1 += 1
                if r1 > r and c1 > c and \
                   all(grid[r][cc] == 5 for cc in range(c, c1+1)) and \
                   all(grid[r1][cc] == 5 for cc in range(c, c1+1)) and \
                   all(grid[rr][c] == 5 for rr in range(r, r1+1)) and \
                   all(grid[rr][c1] == 5 for rr in range(r, r1+1)):
                    for rr in range(r, r1+1):
                        for cc in range(c, c1+1): visited[rr][cc] = True
                    size = max(r1-r-1, c1-c-1)
                    fill = 6 if size == 1 else (7 if size == 2 else 8)
                    for rr in range(r+1, r1):
                        for cc in range(c+1, c1): result[rr][cc] = fill
    return result


def tile_by_most_common_value_pattern(grid):
    from collections import Counter
    H = len(grid); W = len(grid[0])
    cnt = Counter(v for row in grid for v in row)
    bg = max(cnt, key=cnt.get)
    result = [[0]*(W*W) for _ in range(H*H)]
    for br in range(H):
        for bc in range(W):
            if grid[br][bc] == bg:
                for r in range(H):
                    for c in range(W):
                        result[br*H+r][bc*W+c] = grid[r][c]
    return result


def replace_7_with_5(grid):
    return [[5 if v == 7 else v for v in row] for row in grid]


def mark_all_zero_rows_cols_with_2(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    for r in range(H):
        if all(grid[r][c] == 0 for c in range(W)):
            for c in range(W): result[r][c] = 2
    for c in range(W):
        if all(grid[r][c] == 0 for r in range(H)):
            for r in range(H): result[r][c] = 2
    return result


def fill_inverted_checkerboard(grid):
    H = len(grid); W = len(grid[0])
    from collections import Counter
    cnt = Counter(grid[r][c] for r in range(H) for c in range(W))
    parity = [{}, {}]
    for r in range(H):
        for c in range(W):
            v = grid[r][c]
            p = (r + c) % 2
            parity[p][v] = parity[p].get(v, 0) + 1
    fill_val = None
    for v in cnt:
        if v in parity[0] and v in parity[1]:
            fill_val = v
            break
    if fill_val is None:
        fill_val = cnt.most_common(1)[0][0]
    checker_vals = [v for v in cnt if v != fill_val]
    if len(checker_vals) < 2:
        return [list(row) for row in grid]
    c0 = checker_vals[0]; c1 = checker_vals[1]
    p0 = 0 if (c0 in parity[0] and parity[0].get(c0,0) > parity[1].get(c0,0)) else 1
    result = [[0]*W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if grid[r][c] == fill_val:
                result[r][c] = fill_val
            else:
                result[r][c] = c0 if (r+c)%2 != p0 else c1
    return result


def fill_3x3_around_5_with_1s(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    for r in range(H):
        for c in range(W):
            if grid[r][c] == 5:
                for dr in range(-1, 2):
                    for dc in range(-1, 2):
                        nr, nc = r+dr, c+dc
                        if 0 <= nr < H and 0 <= nc < W and grid[nr][nc] == 0:
                            result[nr][nc] = 1
    return result


def replace_5_with_row_color(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    for r in range(H):
        row_colors = [v for v in grid[r] if v != 0 and v != 5]
        if row_colors:
            color = row_colors[0]
            for c in range(W):
                if result[r][c] == 5:
                    result[r][c] = color
    return result


def diagonal_tile_to_double(grid):
    H = len(grid); W = len(grid[0])
    OH = H * 2; OW = W * 2
    result = [[0]*OW for _ in range(OH)]
    for r in range(OH):
        for c in range(OW):
            for k in range(min(r, c) + 1):
                ir, ic = r - k, c - k
                if 0 <= ir < H and 0 <= ic < W:
                    if grid[ir][ic] != 0:
                        result[r][c] = grid[ir][ic]
    return result


def swap_8_and_5(grid):
    return [[8 if v == 5 else (5 if v == 8 else v) for v in row] for row in grid]


def fill_2frame_interior_with_3(grid):
    H = len(grid); W = len(grid[0])
    result = [[0]*W for _ in range(H)]
    visited = [[False]*W for _ in range(H)]
    from collections import deque
    for r in range(H):
        for c in range(W):
            if grid[r][c] == 2 and not visited[r][c]:
                comp = []
                q = deque([(r, c)])
                visited[r][c] = True
                while q:
                    rr, cc = q.popleft()
                    comp.append((rr, cc))
                    for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nr, nc = rr+dr, cc+dc
                        if 0<=nr<H and 0<=nc<W and not visited[nr][nc] and grid[nr][nc]==2:
                            visited[nr][nc] = True; q.append((nr, nc))
                r0=min(rr for rr,cc in comp); r1=max(rr for rr,cc in comp)
                c0=min(cc for rr,cc in comp); c1=max(cc for rr,cc in comp)
                for ri in range(r0+1, r1):
                    for ci in range(c0+1, c1):
                        result[ri][ci] = 3
    return result


def mark_cross_around_1(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    for r in range(H):
        for c in range(W):
            if grid[r][c] == 1:
                if r > 0: result[r-1][c] = 2
                if r < H-1: result[r+1][c] = 8
                if c > 0: result[r][c-1] = 7
                if c < W-1: result[r][c+1] = 6
    return result


def draw_l_path_4_between_points(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    pts = [(r, c) for r in range(H) for c in range(W) if grid[r][c] != 0]
    if len(pts) != 2: return result
    p8 = next((r, c) for r, c in pts if grid[r][c] == 8)
    p2 = next((r, c) for r, c in pts if grid[r][c] == 2)
    r8, c8 = p8; r2, c2 = p2
    step_r = 1 if r2 > r8 else -1
    for r in range(r8+step_r, r2, step_r):
        result[r][c8] = 4
    step_c = 1 if c2 > c8 else -1
    for c in range(c8, c2, step_c):
        result[r2][c] = 4
    return result


def fill_5frame_interior_extend_gap(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    nz = [(r, c) for r in range(H) for c in range(W) if grid[r][c] == 5]
    if not nz: return result
    fr0=min(r for r,c in nz); fr1=max(r for r,c in nz)
    fc0=min(c for r,c in nz); fc1=max(c for r,c in nz)
    for r in range(fr0+1, fr1):
        for c in range(fc0+1, fc1):
            result[r][c] = 8
    gap_pos = None; gap_dir = None
    for c in range(fc0+1, fc1):
        if grid[fr0][c] == 0: gap_pos = (fr0, c); gap_dir = (-1, 0); break
        if grid[fr1][c] == 0: gap_pos = (fr1, c); gap_dir = (1, 0); break
    if gap_pos is None:
        for r in range(fr0+1, fr1):
            if grid[r][fc0] == 0: gap_pos = (r, fc0); gap_dir = (0, -1); break
            if grid[r][fc1] == 0: gap_pos = (r, fc1); gap_dir = (0, 1); break
    if gap_pos and gap_dir:
        gr, gc = gap_pos; dr, dc = gap_dir
        result[gr][gc] = 8
        r, c = gr+dr, gc+dc
        while 0 <= r < H and 0 <= c < W and grid[r][c] == 0:
            result[r][c] = 8; r += dr; c += dc
    return result


def fill_gap_between_blocks_with_8(grid):
    H = len(grid); W = len(grid[0])
    from collections import Counter
    cnt = Counter(grid[r][c] for r in range(H) for c in range(W) if grid[r][c] != 0)
    blocks = []
    for color in cnt:
        cells = [(r, c) for r in range(H) for c in range(W) if grid[r][c] == color]
        r0=min(r for r,c in cells); r1=max(r for r,c in cells)
        c0=min(c for r,c in cells); c1=max(c for r,c in cells)
        blocks.append((r0, r1, c0, c1))
    if len(blocks) < 2: return [list(row) for row in grid]
    result = [list(row) for row in grid]
    for i in range(len(blocks)):
        for j in range(i+1, len(blocks)):
            r0a,r1a,c0a,c1a = blocks[i]; r0b,r1b,c0b,c1b = blocks[j]
            if r1a < r0b:
                gr0,gr1 = r1a+1, r0b-1
                ic0=max(c0a+1,c0b+1); ic1=min(c1a-1,c1b-1)
                if gr0<=gr1 and ic0<=ic1:
                    for r in range(gr0,gr1+1):
                        for c in range(ic0,ic1+1): result[r][c] = 8
            elif r1b < r0a:
                gr0,gr1 = r1b+1, r0a-1
                ic0=max(c0a+1,c0b+1); ic1=min(c1a-1,c1b-1)
                if gr0<=gr1 and ic0<=ic1:
                    for r in range(gr0,gr1+1):
                        for c in range(ic0,ic1+1): result[r][c] = 8
            elif c1a < c0b:
                gc0,gc1 = c1a+1, c0b-1
                ir0=max(r0a+1,r0b+1); ir1=min(r1a-1,r1b-1)
                if gc0<=gc1 and ir0<=ir1:
                    for r in range(ir0,ir1+1):
                        for c in range(gc0,gc1+1): result[r][c] = 8
            elif c1b < c0a:
                gc0,gc1 = c1b+1, c0a-1
                ir0=max(r0a+1,r0b+1); ir1=min(r1a-1,r1b-1)
                if gc0<=gc1 and ir0<=ir1:
                    for r in range(ir0,ir1+1):
                        for c in range(gc0,gc1+1): result[r][c] = 8
    return result


def extend_row_pattern_to_fill(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    for r in range(H):
        row = grid[r]
        last_nz = max((c for c in range(W) if row[c] != 0), default=-1)
        if last_nz < 0: continue
        vis = row[:last_nz+1]
        n = len(vis)
        period = None
        for p in range(1, n+1):
            if all(vis[i] == vis[i % p] for i in range(n)):
                period = p; break
        if period:
            for c in range(W):
                result[r][c] = vis[c % period]
    return result


def replace_3_adjacent_2_with_8(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    for r in range(H):
        for c in range(W):
            if grid[r][c] == 3:
                for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nr, nc = r+dr, c+dc
                    if 0<=nr<H and 0<=nc<W and grid[nr][nc] == 2:
                        result[r][c] = 8; result[nr][nc] = 0; break
    return result


def extract_framed_center_value(grid):
    H = len(grid); W = len(grid[0])
    for r in range(H-2):
        for c in range(W-2):
            fc = grid[r][c]
            if fc == 0: continue
            border = [(r,c),(r,c+1),(r,c+2),(r+1,c),(r+1,c+2),(r+2,c),(r+2,c+1),(r+2,c+2)]
            if all(grid[br][bc] == fc for br,bc in border):
                inner = grid[r+1][c+1]
                if inner != 0: return [[inner]]
    return [[0]]


def expand_7col_to_chevron(grid):
    H = len(grid); W = len(grid[0])
    col_7 = next((c for c in range(W) if any(grid[r][c] == 7 for r in range(H))), None)
    if col_7 is None: return [list(row) for row in grid]
    rows_7 = [r for r in range(H) if grid[r][col_7] == 7]
    if not rows_7: return [list(row) for row in grid]
    bottom_row = max(rows_7)
    result = [[0]*W for _ in range(H)]
    for r in rows_7:
        d = bottom_row - r
        for offset in range(-d, d+1):
            c = col_7 + offset
            if 0 <= c < W:
                result[r][c] = 7 if abs(offset) % 2 == 0 else 8
    return result


def merge_halves_as_6(grid):
    H = len(grid); W = len(grid[0])
    half = W // 2
    result = [[0]*half for _ in range(H)]
    for r in range(H):
        for c in range(half):
            if grid[r][c] != 0 or grid[r][c+half] != 0:
                result[r][c] = 6
    return result


def connect_8_pairs_with_8(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    for r in range(H):
        cols = [c for c in range(W) if grid[r][c] == 8]
        if len(cols) >= 2:
            for c in range(min(cols)+1, max(cols)): result[r][c] = 8
    for c in range(W):
        rows = [r for r in range(H) if grid[r][c] == 8]
        if len(rows) >= 2:
            for r in range(min(rows)+1, max(rows)): result[r][c] = 8
    return result


def connect_1pairs_with_8(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    for r in range(H):
        cols = [c for c in range(W) if grid[r][c] == 1]
        if len(cols) == 2:
            for c in range(cols[0]+1, cols[1]): result[r][c] = 8
    for c in range(W):
        rows = [r for r in range(H) if grid[r][c] == 1]
        if len(rows) == 2:
            for r in range(rows[0]+1, rows[1]): result[r][c] = 8
    return result


def fill_5blocks_with_row0_color(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    from collections import deque
    visited = [[False]*W for _ in range(H)]
    for r0 in range(H):
        for c0 in range(W):
            if grid[r0][c0] == 5 and not visited[r0][c0]:
                comp = []
                q = deque([(r0, c0)])
                visited[r0][c0] = True
                while q:
                    r, c = q.popleft()
                    comp.append((r, c))
                    for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nr, nc = r+dr, c+dc
                        if 0<=nr<H and 0<=nc<W and not visited[nr][nc] and grid[nr][nc]==5:
                            visited[nr][nc] = True; q.append((nr, nc))
                c_min = min(c for r, c in comp); c_max = max(c for r, c in comp)
                color = next((grid[0][c] for c in range(c_min, c_max+1) if grid[0][c] != 0), None)
                if color:
                    for r, c in comp: result[r][c] = color
    return result


def move_3_toward_4(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    r3 = c3 = r4 = c4 = None
    for r in range(H):
        for c in range(W):
            if grid[r][c] == 3: r3, c3 = r, c
            if grid[r][c] == 4: r4, c4 = r, c
    if r3 is None or r4 is None: return result
    result[r3][c3] = 0
    dr = (1 if r4 > r3 else -1 if r4 < r3 else 0)
    dc = (1 if c4 > c3 else -1 if c4 < c3 else 0)
    result[r3+dr][c3+dc] = 3
    return result


def crop_left_of_5_fold_right(grid):
    H = len(grid); W = len(grid[0])
    sep = next(c for c in range(W) if any(grid[r][c] == 5 for r in range(H)))
    result = [[0]*sep for _ in range(H)]
    for r in range(H):
        for c in range(sep):
            result[r][c] = grid[r][c] if grid[r][c] != 0 else 0
        for c in range(sep+1, W):
            mc = W - 1 - c
            if 0 <= mc < sep and grid[r][c] != 0:
                result[r][mc] = grid[r][c]
    return result


def interleave_two_rows_checkerboard(grid):
    H = len(grid); W = len(grid[0])
    a, b = grid[0][0], grid[1][0]
    return [[(a if (r+c) % 2 == 0 else b) for c in range(W)] for r in range(H)]


def merge_around_5_separator(grid):
    H = len(grid); W = len(grid[0])
    sep = next(r for r in range(H) if all(grid[r][c] == 5 for c in range(W)))
    top = grid[:sep]
    bot = grid[sep+1:]
    n = len(top)
    result = [[0]*W for _ in range(n)]
    for r in range(n):
        for c in range(W):
            tv = top[r][c] if r < len(top) else 0
            bv = bot[r][c] if r < len(bot) else 0
            result[r][c] = tv if tv != 0 else bv
    return result


def set_diagonals_to_zero(grid):
    H = len(grid); W = len(grid[0])
    cr = H // 2; cc = W // 2
    result = [list(row) for row in grid]
    for r in range(H):
        for c in range(W):
            if abs(r-cr) == abs(c-cc):
                result[r][c] = 0
    return result


def rotate_grid_ccw(grid):
    H = len(grid); W = len(grid[0])
    return [[grid[c][H-1-r] for c in range(H)] for r in range(W)]


def recolor_5_segments_by_size(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    visited = [[False]*W for _ in range(H)]
    from collections import deque
    components = []
    for r in range(H):
        for c in range(W):
            if grid[r][c] == 5 and not visited[r][c]:
                comp = []
                q = deque([(r, c)])
                visited[r][c] = True
                while q:
                    rr, cc = q.popleft()
                    comp.append((rr, cc))
                    for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nr, nc = rr+dr, cc+dc
                        if 0<=nr<H and 0<=nc<W and not visited[nr][nc] and grid[nr][nc]==5:
                            visited[nr][nc] = True; q.append((nr, nc))
                components.append(comp)
    if not components: return result
    n = len(components)
    sorted_comps = sorted(components, key=len)
    for i, comp in enumerate(sorted_comps):
        color = 1 if i == n-1 else (2 if i == 0 else 4)
        for r, c in comp: result[r][c] = color
    return result


def apply_5_template(grid):
    other = next((v for row in grid for v in row if v != 0 and v != 5), None)
    if other is None: return [list(row) for row in grid]
    return [[other if v == 5 else 0 for v in row] for row in grid]


def mark_empty_intersection_of_halves(grid):
    H = len(grid); W = len(grid[0])
    top = grid[:H//2]; bot = grid[H//2:]
    return [[2 if top[r][c] == 0 and bot[r][c] == 0 else 0 for c in range(W)] for r in range(H//2)]


def scale2x_fill_nonzero_cols_with_8(grid):
    H = len(grid); W = len(grid[0])
    nz_cols = set(c for r in range(H) for c in range(W) if grid[r][c] != 0)
    tile = [[8 if grid[r][c] == 0 and c in nz_cols else grid[r][c] for c in range(W)] for r in range(H)]
    result = [[0]*(W*2) for _ in range(H*2)]
    for r in range(H*2):
        for c in range(W*2):
            result[r][c] = tile[r % H][c % W]
    return result


def fill_zeros_from_vertical_mirror(grid):
    H = len(grid); W = len(grid[0])
    return [[grid[r][c] if grid[r][c] != 0 else grid[H-1-r][c] for c in range(W)] for r in range(H)]


def mark_cells_absent_in_both_col_halves(grid):
    H = len(grid); W = len(grid[0])
    mid = W // 2
    left = [row[:mid] for row in grid]
    right = [row[mid+1:] for row in grid]
    return [[3 if left[r][c] == 0 and right[r][c] == 0 else 0 for c in range(mid)] for r in range(H)]


def tile_input_row_on_antidiagonal(grid):
    row = grid[0]; W = len(row)
    nz_count = sum(1 for v in row if v != 0)
    H = nz_count * W
    result = [[0]*H for _ in range(H)]
    for r in range(H):
        shift = H - 1 - r
        for c in range(W):
            if shift + c < H:
                result[r][shift + c] = row[c]
    return result


def extract_3_minority_nz_colors_by_count(grid):
    from collections import Counter
    cnt = Counter(v for row in grid for v in row if v != 0)
    dominant = cnt.most_common(1)[0][0]
    others = sorted([c for c in cnt if c != dominant], key=lambda c: -cnt[c])
    return [[v] for v in others[:3]]


def sort_3_nz_colors_by_count_desc(grid):
    from collections import Counter
    cnt = Counter(v for row in grid for v in row if v != 0)
    return [[c] for c, _ in cnt.most_common(3)]


def crop_nonzero_scale2x(grid):
    H = len(grid); W = len(grid[0])
    nz = [(r, c) for r in range(H) for c in range(W) if grid[r][c] != 0]
    if not nz: return grid
    r0 = min(r for r, c in nz); r1 = max(r for r, c in nz)
    c0 = min(c for r, c in nz); c1 = max(c for r, c in nz)
    OH = (r1-r0+1)*2; OW = (c1-c0+1)*2
    result = [[0]*OW for _ in range(OH)]
    for r in range(r0, r1+1):
        for c in range(c0, c1+1):
            v = grid[r][c]
            dr = (r-r0)*2; dc = (c-c0)*2
            result[dr][dc] = v; result[dr][dc+1] = v
            result[dr+1][dc] = v; result[dr+1][dc+1] = v
    return result


def fill_below_2x2_blocks_with_3(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    visited = [[False]*W for _ in range(H)]
    for r in range(H-1):
        for c in range(W-1):
            if (grid[r][c] != 0 and grid[r][c+1] != 0 and
                    grid[r+1][c] != 0 and grid[r+1][c+1] != 0 and not visited[r][c]):
                vals = {grid[r][c], grid[r][c+1], grid[r+1][c], grid[r+1][c+1]}
                visited[r][c] = visited[r][c+1] = visited[r+1][c] = visited[r+1][c+1] = True
                for dr in range(len(vals)):
                    nr = r + 2 + dr
                    if nr < H:
                        result[nr][c] = 3; result[nr][c+1] = 3
    return result


def extract_frame_replace_with_minority(grid):
    from collections import Counter
    H = len(grid); W = len(grid[0])
    cnt = Counter(v for row in grid for v in row if v != 0)
    if len(cnt) < 2: return [list(row) for row in grid]
    majority = max(cnt, key=cnt.get)
    minority = min(cnt, key=cnt.get)
    best = None; best_area = 0
    for r0 in range(H):
        for r1 in range(r0+2, H):
            for c0 in range(W):
                if grid[r0][c0] != majority or grid[r1][c0] != majority: continue
                for c1 in range(c0+2, W):
                    if grid[r0][c1] != majority or grid[r1][c1] != majority: continue
                    if (all(grid[r0][c] == majority for c in range(c0, c1+1)) and
                            all(grid[r1][c] == majority for c in range(c0, c1+1)) and
                            all(grid[r][c0] == majority for r in range(r0, r1+1)) and
                            all(grid[r][c1] == majority for r in range(r0, r1+1))):
                        area = (r1-r0+1)*(c1-c0+1)
                        if area > best_area:
                            best_area = area; best = (r0, r1, c0, c1)
    if best is None: return [list(row) for row in grid]
    r0, r1, c0, c1 = best
    return [[minority if grid[r0+r][c0+c] == majority else grid[r0+r][c0+c]
             for c in range(c1-c0+1)] for r in range(r1-r0+1)]


def count_row_col_bands(grid):
    H = len(grid); W = len(grid[0])
    from collections import Counter
    cnt = Counter(v for row in grid for v in row if v != 0)
    divider_color = None
    for v in cnt:
        if any(all(grid[r][c] == v for c in range(W)) for r in range(H)):
            divider_color = v; break
        if any(all(grid[r][c] == v for r in range(H)) for c in range(W)):
            divider_color = v; break
    if divider_color is None: return grid
    div_rows = [r for r in range(H) if all(grid[r][c] == divider_color for c in range(W))]
    div_cols = [c for c in range(W) if all(grid[r][c] == divider_color for r in range(H))]
    n_row_bands = len(div_rows) + 1
    n_col_bands = len(div_cols) + 1
    bg_color = next(v for v in cnt if v != divider_color)
    return [[bg_color]*n_col_bands for _ in range(n_row_bands)]


def extract_smallest_rectangle_region(grid):
    from collections import Counter
    H = len(grid); W = len(grid[0])
    cnt = Counter(v for row in grid for v in row if v != 0)
    if not cnt: return grid
    min_color = min(cnt, key=cnt.get)
    cells = [(r,c) for r in range(H) for c in range(W) if grid[r][c] == min_color]
    r0 = min(r for r,c in cells); r1 = max(r for r,c in cells)
    c0 = min(c for r,c in cells); c1 = max(c for r,c in cells)
    return [[min_color]*(c1-c0+1) for _ in range(r1-r0+1)]


def shift_grid_down_one(grid):
    H = len(grid); W = len(grid[0])
    result = [[0]*W for _ in range(H)]
    for r in range(H-1):
        result[r+1] = list(grid[r])
    return result


def draw_row_col_lines_by_value(grid):
    H = len(grid); W = len(grid[0])
    result = [[0]*W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if grid[r][c] == 2:
                for rr in range(H):
                    result[rr][c] = 2
    for r in range(H):
        for c in range(W):
            v = grid[r][c]
            if v != 0 and v != 2:
                for cc in range(W):
                    result[r][cc] = v
    return result


def check_8s_bridge_2x2_blocks(grid):
    H = len(grid); W = len(grid[0])
    blocks = []
    seen = set()
    for r in range(H-1):
        for c in range(W-1):
            if grid[r][c]==2 and grid[r][c+1]==2 and grid[r+1][c]==2 and grid[r+1][c+1]==2:
                key = (r,c)
                if key not in seen:
                    blocks.append({(r,c),(r,c+1),(r+1,c),(r+1,c+1)})
                    seen.add(key)
    if len(blocks) < 2: return [[0]]
    eights = set((r,c) for r in range(H) for c in range(W) if grid[r][c]==8)
    def adj_to_block(block):
        res = set()
        for (r,c) in block:
            for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                nr,nc = r+dr,c+dc
                if (nr,nc) in eights:
                    res.add((nr,nc))
        return res
    start = adj_to_block(blocks[0])
    end = adj_to_block(blocks[1])
    if not start or not end: return [[0]]
    visited = set(start)
    queue = list(start)
    while queue:
        r,c = queue.pop()
        if (r,c) in end: return [[8]]
        for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            nr,nc = r+dr,c+dc
            if (nr,nc) in eights and (nr,nc) not in visited:
                visited.add((nr,nc))
                queue.append((nr,nc))
    return [[0]]


def draw_nested_rectangular_spiral_with_3(grid):
    H = len(grid); W = len(grid[0])
    result = [[3]*W for _ in range(H)]
    L = 0
    while True:
        row_top = 2*L + 1
        row_bot = H - 2*L - 2
        col_left = 2*L + 1
        col_right = W - 2*L - 2
        if row_top > row_bot or col_left > col_right: break
        if L == 0:
            for col in range(col_right, -1, -1):
                result[row_top][col] = 0
        else:
            for col in range(col_left-1, col_right+1):
                result[row_top][col] = 0
        for row in range(row_top+1, row_bot+1):
            result[row][col_right] = 0
        if row_bot > row_top + 1:
            for col in range(col_right-1, col_left-1, -1):
                result[row_bot][col] = 0
        if row_bot > row_top + 2:
            for row in range(row_bot-1, row_top+1, -1):
                result[row][col_left] = 0
        L += 1
    return result


def reflect_shape_to_4_quadrants(grid):
    H = len(grid); W = len(grid[0])
    div_row = next((r for r in range(H) if len(set(grid[r])) == 1 and grid[r][0] != 0), None)
    div_col = next((c for c in range(W) if len(set(grid[r][c] for r in range(H))) == 1 and grid[0][c] != 0), None)
    if div_row is None or div_col is None: return [list(row) for row in grid]
    div_color = grid[div_row][div_col]
    tl = [row[:div_col] for row in grid[:div_row]]
    tl_h = div_row; tl_w = div_col
    out_h = H - 1; out_w = W - 1
    result = [[0]*out_w for _ in range(out_h)]
    for r in range(tl_h):
        for c in range(tl_w):
            v = tl[r][c]
            if v != 0:
                result[r][c] = div_color
                result[r][out_w-1-c] = div_color
                result[out_h-1-r][c] = div_color
                result[out_h-1-r][out_w-1-c] = div_color
    return result


def two_cell_frame_pattern(grid):
    H = len(grid); W = len(grid[0])
    cells = [(r,c,grid[r][c]) for r in range(H) for c in range(W) if grid[r][c] != 0]
    if len(cells) != 2: return [list(row) for row in grid]
    cells.sort()
    r0,c0,v0 = cells[0]; r1,c1,v1 = cells[1]
    div = (r0 + r1) // 2
    result = [[0]*W for _ in range(H)]
    for r in range(div+1):
        result[r][0] = v0; result[r][W-1] = v0
    for c in range(W): result[0][c] = v0
    for c in range(W): result[r0][c] = v0
    for r in range(div+1, H):
        result[r][0] = v1; result[r][W-1] = v1
    for c in range(W): result[H-1][c] = v1
    for c in range(W): result[r1][c] = v1
    return result


def slide_2_toward_8(grid):
    H = len(grid); W = len(grid[0])
    two_cells = [(r,c) for r in range(H) for c in range(W) if grid[r][c] == 2]
    eight_cells = set((r,c) for r in range(H) for c in range(W) if grid[r][c] == 8)
    if not two_cells or not eight_cells: return [list(row) for row in grid]
    two_rows = set(r for r,c in two_cells)
    eight_rows = set(r for r,c in eight_cells)
    result = [[0]*W for _ in range(H)]
    for r,c in eight_cells: result[r][c] = 8
    if two_rows & eight_rows:
        two_center_c = sum(c for r,c in two_cells)/len(two_cells)
        eight_center_c = sum(c for r,c in eight_cells)/len(eight_cells)
        direction = 1 if eight_center_c > two_center_c else -1
        for step in range(1, W+1):
            moved = [(r, c+direction*step) for r,c in two_cells]
            if any((r+dr,c+dc) in eight_cells for r,c in moved for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]):
                for r,c in moved:
                    if 0<=r<H and 0<=c<W: result[r][c] = 2
                return result
    else:
        two_center_r = sum(r for r,c in two_cells)/len(two_cells)
        eight_center_r = sum(r for r,c in eight_cells)/len(eight_cells)
        direction = 1 if eight_center_r > two_center_r else -1
        for step in range(1, H+1):
            moved = [(r+direction*step, c) for r,c in two_cells]
            if any((r+dr,c+dc) in eight_cells for r,c in moved for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]):
                for r,c in moved:
                    if 0<=r<H and 0<=c<W: result[r][c] = 2
                return result
    return [list(row) for row in grid]


def attract_strays_to_nearest_line(grid):
    H = len(grid); W = len(grid[0])
    lines = []
    for r in range(H):
        nz = [v for v in grid[r] if v != 0]
        if nz and len(set(nz))==1 and len(nz)==W: lines.append(('row', r, nz[0]))
    for c in range(W):
        nz = [grid[r][c] for r in range(H) if grid[r][c] != 0]
        if nz and len(set(nz))==1 and len(nz)==H: lines.append(('col', c, nz[0]))
    result = [[0]*W for _ in range(H)]
    for ltype, idx, color in lines:
        if ltype=='row':
            for c in range(W): result[idx][c] = color
        else:
            for r in range(H): result[r][idx] = color
    line_lookup = {}
    for ltype, idx, color in lines: line_lookup.setdefault(color,[]).append((ltype,idx))
    for r in range(H):
        for c in range(W):
            v = grid[r][c]
            if v==0: continue
            on_line = any((ltype=='row' and idx==r) or (ltype=='col' and idx==c) for ltype,idx,lcolor in lines if lcolor==v)
            if on_line: continue
            if v not in line_lookup: continue
            best_dist=float('inf'); best_line=None
            for ltype,idx in line_lookup[v]:
                dist = abs(idx-r) if ltype=='row' else abs(idx-c)
                if dist < best_dist: best_dist=dist; best_line=(ltype,idx)
            if best_line is None: continue
            ltype, idx = best_line
            if ltype=='row':
                direction = -1 if r<idx else 1
                er = idx+direction
                if 0<=er<H: result[er][c] = v
            else:
                direction = -1 if c<idx else 1
                ec = idx+direction
                if 0<=ec<W: result[r][ec] = v
    return result


def extend_shape_from_2_markers(grid):
    H = len(grid); W = len(grid[0])
    nz = [(r,c,grid[r][c]) for r in range(H) for c in range(W) if grid[r][c] != 0]
    two_cells = [(r,c) for r,c,v in nz if v == 2]
    non_two = [(r,c,v) for r,c,v in nz if v != 2]
    if not non_two: return [list(row) for row in grid]
    main_color = non_two[0][2]
    all_rc = [(r,c) for r,c,v in nz]
    min_r = min(r for r,c in all_rc); max_r = max(r for r,c in all_rc)
    min_c = min(c for r,c in all_rc); max_c = max(c for r,c in all_rc)
    result = [[0]*W for _ in range(H)]
    for r,c,v in non_two: result[r][c] = main_color
    for r2, c2 in two_cells:
        dr = -1 if r2 == min_r else 1
        dc = -1 if c2 == min_c else 1
        start_r = min_r if dr < 0 else max_r
        if dc < 0: col_lo = min_c - 1; col_hi = max_c
        else: col_lo = min_c; col_hi = max_c + 1
        r = start_r; step = 0
        while 0 <= r < H:
            lo = col_lo + dc * step
            hi = col_hi + dc * step
            for c in range(max(0, lo), min(W, hi + 1)):
                result[r][c] = main_color
            r += dr; step += 1
    return result


def project_isolated_cells_to_8block_edges(grid):
    H = len(grid); W = len(grid[0])
    eight_cells = set((r,c) for r in range(H) for c in range(W) if grid[r][c] == 8)
    isolated = [(r,c,grid[r][c]) for r in range(H) for c in range(W) if grid[r][c] not in (0,8)]
    if not eight_cells or not isolated: return [list(row) for row in grid]
    min_r8 = min(r for r,c in eight_cells); max_r8 = max(r for r,c in eight_cells)
    min_c8 = min(c for r,c in eight_cells); max_c8 = max(c for r,c in eight_cells)
    result = [list(row) for row in grid]
    for r, c, v in isolated:
        in_row_range = min_r8 <= r <= max_r8
        in_col_range = min_c8 <= c <= max_c8
        if in_row_range and not in_col_range:
            if c < min_c8: result[r][min_c8] = v
            else: result[r][max_c8] = v
        elif in_col_range and not in_row_range:
            if r < min_r8: result[min_r8][c] = v
            else: result[max_r8][c] = v
        else:
            dr = min_r8 - r if r < min_r8 else r - max_r8
            dc = min_c8 - c if c < min_c8 else c - max_c8
            tc = min_c8 if c < min_c8 else max_c8
            tr = min_r8 if r < min_r8 else max_r8
            result[tr][tc] = v
    return result


def mark_uniform_rows_with_5(grid):
    H = len(grid); W = len(grid[0])
    result = [[0]*W for _ in range(H)]
    for r in range(H):
        if len(set(grid[r])) == 1:
            result[r] = [5]*W
    return result


def count_2x2_ones_to_indicator(grid):
    H = len(grid); W = len(grid[0])
    count = 0
    for r in range(H-1):
        for c in range(W-1):
            if grid[r][c]==1 and grid[r][c+1]==1 and grid[r+1][c]==1 and grid[r+1][c+1]==1:
                count += 1
    return [[1 if i < count else 0 for i in range(5)]]


def fill_3x3_regions_by_position(grid):
    H = len(grid); W = len(grid[0])
    h_lines = [r for r in range(H) if all(grid[r][c]==8 for c in range(W))]
    v_lines = [c for c in range(W) if all(grid[r][c]==8 for r in range(H))]
    if len(h_lines) < 2 or len(v_lines) < 2: return [list(row) for row in grid]
    colors = [[0,2,0],[4,6,3],[0,1,0]]
    row_bands = [range(0, h_lines[0]), range(h_lines[0]+1, h_lines[1]), range(h_lines[1]+1, H)]
    col_bands = [range(0, v_lines[0]), range(v_lines[0]+1, v_lines[1]), range(v_lines[1]+1, W)]
    result = [list(row) for row in grid]
    for br, rband in enumerate(row_bands):
        for bc, cband in enumerate(col_bands):
            c = colors[br][bc]
            if c != 0:
                for r in rband:
                    for col in cband:
                        result[r][col] = c
    return result


def extend_arrow_tip_in_direction(grid):
    H = len(grid); W = len(grid[0])
    all_nz = [(r,c,grid[r][c]) for r in range(H) for c in range(W) if grid[r][c] != 0]
    if not all_nz: return [list(row) for row in grid]
    from collections import Counter
    cnt = Counter(v for r,c,v in all_nz)
    main_color = max(cnt, key=cnt.get)
    indicators = [(r,c,v) for r,c,v in all_nz if v != main_color]
    if not indicators: return [list(row) for row in grid]
    mr, mc, M = indicators[0]
    shape_cells = [(r,c) for r,c,v in all_nz if v == main_color]
    if not shape_cells: return [list(row) for row in grid]
    cr = sum(r for r,c in shape_cells) / len(shape_cells)
    cc = sum(c for r,c in shape_cells) / len(shape_cells)
    dr = cr - mr; dc = cc - mc
    result = [list(row) for row in grid]
    if abs(dr) >= abs(dc):
        step = 1 if dr > 0 else -1
        extreme_r = max(r for r,c in shape_cells) if step > 0 else min(r for r,c in shape_cells)
        r = extreme_r + step
        while 0 <= r < H:
            result[r][mc] = M
            r += step
    else:
        step = 1 if dc > 0 else -1
        extreme_c = max(c for r,c in shape_cells) if step > 0 else min(c for r,c in shape_cells)
        c = extreme_c + step
        while 0 <= c < W:
            result[mr][c] = M
            c += step
    return result


def classify_3x3_pattern(grid):
    center = grid[1][1]
    if center == 0: return [[1]]
    neighbors = [grid[0][1], grid[1][0], grid[1][2], grid[2][1]]
    filled = sum(1 for v in neighbors if v != 0)
    if filled == 0: return [[2]]
    if filled == 2: return [[3]]
    return [[6]]


def crop_and_duplicate_horizontal(grid):
    H = len(grid); W = len(grid[0])
    cells = [(r,c) for r in range(H) for c in range(W) if grid[r][c] != 0]
    if not cells: return [list(row) for row in grid]
    r0 = min(r for r,c in cells); r1 = max(r for r,c in cells)
    c0 = min(c for r,c in cells); c1 = max(c for r,c in cells)
    piece = [list(grid[r][c0:c1+1]) for r in range(r0, r1+1)]
    return [row + row for row in piece]


def fill_max_count_region_with_color(grid):
    H = len(grid); W = len(grid[0])
    h_divs = sorted([r for r in range(H) if all(grid[r][c]==5 for c in range(W))])
    v_divs = sorted([c for c in range(W) if all(grid[r][c]==5 for r in range(H))])
    if not h_divs or not v_divs: return [list(row) for row in grid]
    row_ranges = []
    prev = 0
    for r in h_divs:
        if r > prev: row_ranges.append((prev, r))
        prev = r + 1
    if prev < H: row_ranges.append((prev, H))
    col_ranges = []
    prev = 0
    for c in v_divs:
        if c > prev: col_ranges.append((prev, c))
        prev = c + 1
    if prev < W: col_ranges.append((prev, W))
    regions = []
    for r0,r1 in row_ranges:
        for c0,c1 in col_ranges:
            cells = [(r,c,grid[r][c]) for r in range(r0,r1) for c in range(c0,c1) if grid[r][c]!=0]
            regions.append(((r0,r1),(c0,c1),cells))
    max_count = max((len(cells) for _,_,cells in regions), default=0)
    if max_count == 0: return [list(row) for row in grid]
    result = [[5 if grid[r][c]==5 else 0 for c in range(W)] for r in range(H)]
    for (r0,r1),(c0,c1),cells in regions:
        if len(cells) == max_count:
            color = cells[0][2]
            for r in range(r0,r1):
                for c in range(c0,c1):
                    result[r][c] = color
    return result


def fill_tiling_zeros(grid):
    H = len(grid); W = len(grid[0])
    nz = [(r,c,grid[r][c]) for r in range(H) for c in range(W) if grid[r][c] != 0]
    if not nz: return [list(row) for row in grid]
    def check_period(dim, coords_vals):
        for p in range(1, dim+1):
            seen = {}
            ok = True
            for pos, v in coords_vals:
                key = pos % p
                if key in seen and seen[key] != v:
                    ok = False; break
                seen[key] = v
            if ok: return p
        return dim
    col_periods = []
    for r in range(H):
        row_nz = [(c, grid[r][c]) for c in range(W) if grid[r][c] != 0]
        if row_nz: col_periods.append(check_period(W, row_nz))
    col_period = max(col_periods) if col_periods else W
    row_periods = []
    for c in range(W):
        col_nz = [(r, grid[r][c]) for r in range(H) if grid[r][c] != 0]
        if col_nz: row_periods.append(check_period(H, col_nz))
    row_period = max(row_periods) if row_periods else H
    tile = {}
    for r,c,v in nz:
        tile[(r%row_period, c%col_period)] = v
    return [[tile.get((r%row_period, c%col_period), 0) for c in range(W)] for r in range(H)]



def reflect_shape_through_2_axis(grid):
    H = len(grid); W = len(grid[0])
    two_cells = [(r,c) for r in range(H) for c in range(W) if grid[r][c] == 2]
    nz = [(r,c,grid[r][c]) for r in range(H) for c in range(W) if grid[r][c] not in (0, 2)]
    if not two_cells or not nz: return [list(row) for row in grid]
    main_color = nz[0][2]
    shape = [(r,c) for r,c,v in nz]
    result = [[3 if grid[r][c]==0 else grid[r][c] for c in range(W)] for r in range(H)]
    two_rows = set(r for r,c in two_cells); two_cols = set(c for r,c in two_cells)
    if len(two_rows) == 1:
        axis_type = 'row'; two_coord = list(two_rows)[0]
        nearest = max(r for r,c in shape) if all(r<two_coord for r,c in shape) else min(r for r,c in shape)
    elif len(two_cols) == 1:
        axis_type = 'col'; two_coord = list(two_cols)[0]
        nearest = max(c for r,c in shape) if all(c<two_coord for r,c in shape) else min(c for r,c in shape)
    else:
        tr, tc = two_cells[0]
        shape_rows = [r for r,c in shape]
        if all(r < tr for r in shape_rows) or all(r > tr for r in shape_rows):
            axis_type = 'row'; two_coord = tr
            nearest = max(r for r,c in shape) if all(r<tr for r,c in shape) else min(r for r,c in shape)
        else:
            axis_type = 'col'; two_coord = tc
            nearest = max(c for r,c in shape) if all(c<tc for r,c in shape) else min(c for r,c in shape)
    axis_double = nearest + two_coord
    for r,c in two_cells: result[r][c] = main_color
    for r,c in shape + two_cells:
        if axis_type == 'row':
            nr = axis_double - r
            if 0 <= nr < H: result[nr][c] = main_color
        else:
            nc = axis_double - c
            if 0 <= nc < W: result[r][nc] = main_color
    return result

def connect_markers_to_rectangle_edges(grid):
    H = len(grid); W = len(grid[0])
    bg = grid[0][0]
    nz = [(r,c,grid[r][c]) for r in range(H) for c in range(W) if grid[r][c] != bg]
    if not nz: return [list(row) for row in grid]
    from collections import Counter
    cnt = Counter(v for r,c,v in nz)
    rect_color = max(cnt, key=cnt.get)
    rect_cells = [(r,c) for r,c,v in nz if v == rect_color]
    r0 = min(r for r,c in rect_cells); r1 = max(r for r,c in rect_cells)
    c0 = min(c for r,c in rect_cells); c1 = max(c for r,c in rect_cells)
    result = [list(row) for row in grid]
    for mr, mc, mv in nz:
        if mv == rect_color: continue
        if r0 <= mr <= r1:
            if mc < c0:
                for c in range(mc+1, c0): result[mr][c] = mv
            elif mc > c1:
                for c in range(c1+1, mc): result[mr][c] = mv
        elif c0 <= mc <= c1:
            if mr < r0:
                for r in range(mr+1, r0): result[r][mc] = mv
            elif mr > r1:
                for r in range(r1+1, mr): result[r][mc] = mv
    return result


def rotate_grid_180(grid):
    return [list(reversed(row)) for row in reversed(grid)]

def surround_singleton_with_2s(grid):
    H = len(grid); W = len(grid[0])
    from collections import Counter
    cnt = Counter(v for r in range(H) for c in range(W) if (v:=grid[r][c]) != 0)
    singleton = next((v for v, n in cnt.items() if n == 1), None)
    if singleton is None: return [list(row) for row in grid]
    for r in range(H):
        for c in range(W):
            if grid[r][c] == singleton:
                sr, sc = r, c
                break
    result = [[0]*W for _ in range(H)]
    for dr in range(-1, 2):
        for dc in range(-1, 2):
            nr, nc = sr+dr, sc+dc
            if 0 <= nr < H and 0 <= nc < W:
                result[nr][nc] = singleton if dr == 0 and dc == 0 else 2
    return result

def hollow_fill_rectangles(grid):
    H = len(grid); W = len(grid[0])
    from collections import deque
    result = [list(row) for row in grid]
    visited = [[False]*W for _ in range(H)]
    for sr in range(H):
        for sc in range(W):
            if grid[sr][sc] != 0 and not visited[sr][sc]:
                color = grid[sr][sc]
                cells = []
                q = deque([(sr,sc)])
                visited[sr][sc] = True
                while q:
                    r,c = q.popleft()
                    cells.append((r,c))
                    for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nr,nc = r+dr,c+dc
                        if 0<=nr<H and 0<=nc<W and not visited[nr][nc] and grid[nr][nc]==color:
                            visited[nr][nc] = True
                            q.append((nr,nc))
                r0=min(r for r,c in cells); r1=max(r for r,c in cells)
                c0=min(c for r,c in cells); c1=max(c for r,c in cells)
                for r,c in cells:
                    if r!=r0 and r!=r1 and c!=c0 and c!=c1:
                        result[r][c] = 0
    return result

def fill_square_enclosed_0s_with_2(grid):
    H = len(grid); W = len(grid[0])
    from collections import deque
    reachable = [[False]*W for _ in range(H)]
    q = deque()
    for r in range(H):
        for c in range(W):
            if (r==0 or r==H-1 or c==0 or c==W-1) and grid[r][c]==0:
                if not reachable[r][c]:
                    reachable[r][c] = True
                    q.append((r,c))
    while q:
        r,c = q.popleft()
        for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            nr,nc = r+dr,c+dc
            if 0<=nr<H and 0<=nc<W and not reachable[nr][nc] and grid[nr][nc]==0:
                reachable[nr][nc] = True
                q.append((nr,nc))
    enclosed = set((r,c) for r in range(H) for c in range(W) if grid[r][c]==0 and not reachable[r][c])
    if not enclosed: return [list(row) for row in grid]
    result = [list(row) for row in grid]
    visited2 = set()
    for start in enclosed:
        if start in visited2: continue
        comp = []
        q2 = deque([start])
        visited2.add(start)
        while q2:
            r,c = q2.popleft()
            comp.append((r,c))
            for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                nb = (r+dr,c+dc)
                if nb in enclosed and nb not in visited2:
                    visited2.add(nb)
                    q2.append(nb)
        r0=min(r for r,c in comp); r1=max(r for r,c in comp)
        c0=min(c for r,c in comp); c1=max(c for r,c in comp)
        h=r1-r0+1; w=c1-c0+1
        if h==w and len(comp)==h*w:
            for r,c in comp:
                result[r][c] = 2
    return result

def attract_cells_to_5band(grid):
    H = len(grid); W = len(grid[0])
    h_band = sorted([r for r in range(H) if all(grid[r][c]==5 for c in range(W))])
    v_band = sorted([c for c in range(W) if all(grid[r][c]==5 for r in range(H))])
    result = [[5 if grid[r][c]==5 else 0 for c in range(W)] for r in range(H)]
    if h_band:
        t, b = h_band[0], h_band[-1]
        for c in range(W):
            above = sum(1 for r in range(H) if r < t and grid[r][c] not in (0,5))
            below = sum(1 for r in range(H) if r > b and grid[r][c] not in (0,5))
            for i in range(above):
                r = t-1-i
                if r >= 0: result[r][c] = 5
            for i in range(below):
                r = b+1+i
                if r < H: result[r][c] = 5
    elif v_band:
        l, ri = v_band[0], v_band[-1]
        for r in range(H):
            left = sum(1 for c in range(W) if c < l and grid[r][c] not in (0,5))
            right = sum(1 for c in range(W) if c > ri and grid[r][c] not in (0,5))
            for i in range(left):
                c = l-1-i
                if c >= 0: result[r][c] = 5
            for i in range(right):
                c = ri+1+i
                if c < W: result[r][c] = 5
    return result


def extract_shape_near_5(grid):
    H = len(grid); W = len(grid[0])
    five_cells = [(r,c) for r in range(H) for c in range(W) if grid[r][c] == 5]
    if not five_cells: return [list(row) for row in grid]
    fr, fc = five_cells[0]
    from collections import deque
    visited = set()
    q = deque([(fr, fc)])
    comp = []
    while q:
        r,c = q.popleft()
        for dr in range(-1,2):
            for dc in range(-1,2):
                nr,nc = r+dr,c+dc
                if 0<=nr<H and 0<=nc<W and (nr,nc) not in visited:
                    v = grid[nr][nc]
                    if v != 0 and v != 5:
                        visited.add((nr,nc))
                        comp.append((nr,nc))
                        q.append((nr,nc))
    if not comp: return [list(row) for row in grid]
    r0=min(r for r,c in comp); r1=max(r for r,c in comp)
    c0=min(c for r,c in comp); c1=max(c for r,c in comp)
    result = [[0]*(c1-c0+1) for _ in range(r1-r0+1)]
    for r,c in comp:
        result[r-r0][c-c0] = grid[r][c]
    return result


def fill_frame_gaps_with_2(grid):
    H = len(grid); W = len(grid[0])
    ones = [(r,c) for r in range(H) for c in range(W) if grid[r][c] == 1]
    if not ones: return [list(row) for row in grid]
    r0 = min(r for r,c in ones); r1 = max(r for r,c in ones)
    c0 = min(c for r,c in ones); c1 = max(c for r,c in ones)
    result = [list(row) for row in grid]
    def fill_seg(cells, lo, hi, is_row, coord):
        if not cells: return
        for p in range(lo, cells[0]):
            if is_row: result[coord][p] = 2
            else: result[p][coord] = 2
        for i in range(len(cells)-1):
            for p in range(cells[i]+1, cells[i+1]):
                if is_row: result[coord][p] = 2
                else: result[p][coord] = 2
        for p in range(cells[-1]+1, hi+1):
            if is_row: result[coord][p] = 2
            else: result[p][coord] = 2
    for r in range(r0, r1+1):
        row1s = sorted(c for rr,c in ones if rr == r)
        if not row1s: continue
        int_cnt = sum(1 for c in row1s if c0 < c < c1)
        if r == r0 or r == r1 or int_cnt >= 2:
            fill_seg(row1s, c0, c1, True, r)
    for c in range(c0, c1+1):
        col1s = sorted(r for r,cc in ones if cc == c)
        if not col1s: continue
        int_cnt = sum(1 for r in col1s if r0 < r < r1)
        if c == c0 or c == c1 or int_cnt >= 2:
            fill_seg(col1s, r0, r1, False, c)
    return result


def fill_rect_interior_with_8(grid):
    H = len(grid); W = len(grid[0])
    from collections import deque
    result = [list(row) for row in grid]
    visited = [[False]*W for _ in range(H)]
    for sr in range(H):
        for sc in range(W):
            if grid[sr][sc] != 0 and not visited[sr][sc]:
                color = grid[sr][sc]
                cells = []
                q = deque([(sr,sc)])
                visited[sr][sc] = True
                while q:
                    r,c = q.popleft()
                    cells.append((r,c))
                    for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nr,nc = r+dr,c+dc
                        if 0<=nr<H and 0<=nc<W and not visited[nr][nc] and grid[nr][nc]==color:
                            visited[nr][nc] = True
                            q.append((nr,nc))
                r0=min(r for r,c in cells); r1=max(r for r,c in cells)
                c0=min(c for r,c in cells); c1=max(c for r,c in cells)
                for r,c in cells:
                    if r!=r0 and r!=r1 and c!=c0 and c!=c1:
                        result[r][c] = 8
    return result


def extract_shape_with_8_replaced(grid):
    H = len(grid); W = len(grid[0])
    eight_pos = [(r,c) for r in range(H) for c in range(W) if grid[r][c] == 8]
    if not eight_pos: return [list(row) for row in grid]
    er, ec = eight_pos[0]
    from collections import Counter
    adj = [grid[er+dr][ec+dc] for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)] if 0<=er+dr<H and 0<=ec+dc<W and grid[er+dr][ec+dc] not in (0,8)]
    if not adj: return [list(row) for row in grid]
    main_color = Counter(adj).most_common(1)[0][0]
    cells = [(r,c) for r in range(H) for c in range(W) if grid[r][c] in (main_color, 8)]
    r0=min(r for r,c in cells); r1=max(r for r,c in cells)
    c0=min(c for r,c in cells); c1=max(c for r,c in cells)
    result = []
    for r in range(r0, r1+1):
        row = []
        for c in range(c0, c1+1):
            v = grid[r][c]
            if v == 8: v = main_color
            row.append(v)
        result.append(row)
    return result


def tile_diagonal_staircase(grid):
    H = len(grid); W = len(grid[0])
    fill = grid[0][0]
    nz_rows = [r for r in range(H) if any(grid[r][c] != 0 for c in range(W))]
    nz_cols = [c for c in range(W) if any(grid[r][c] != 0 for r in range(H))]
    if not nz_rows or not nz_cols: return [[0]*(2*W) for _ in range(2*H)]
    N = max(max(nz_rows)+1, max(nz_cols)+1)
    result = [[fill]*(2*W) for _ in range(2*H)]
    for r in range(min(2*N, 2*H)):
        for c in range(min(2*N, 2*W)):
            if r < N and c < N:
                v = grid[r][c]; result[r][c] = v if v != 0 else fill
            elif r < N:
                v = grid[0][c-N]; result[r][c] = v if v != 0 else fill
            else:
                k = r - N
                if 0 <= k < N:
                    if c <= N+k:
                        v = grid[0][k]; result[r][c] = v if v != 0 else fill
                    elif c < 2*N:
                        v = grid[0][c-N]; result[r][c] = v if v != 0 else fill
    return result


def flip_horizontal(grid):
    return [row[::-1] for row in grid]


def fill_sections_by_marker_plus5(grid):
    H = len(grid); W = len(grid[0])
    result = [list(row) for row in grid]
    sep_rows = [r for r in range(H) if all(grid[r][c]==5 for c in range(W))]
    sep_cols = [c for c in range(W) if all(grid[r][c]==5 for r in range(H))]
    row_bounds = sorted(set([0]+[r+1 for r in sep_rows]+[H]))
    col_bounds = sorted(set([0]+[c+1 for c in sep_cols]+[W]))
    for i in range(len(row_bounds)-1):
        for j in range(len(col_bounds)-1):
            r0,r1 = row_bounds[i],row_bounds[i+1]
            c0,c1 = col_bounds[j],col_bounds[j+1]
            marker = 0
            for r in range(r0,r1):
                for c in range(c0,c1):
                    if grid[r][c] not in (0,5):
                        marker = grid[r][c]
            if marker:
                fill = marker + 5
                for r in range(r0,r1):
                    for c in range(c0,c1):
                        if grid[r][c] != 5:
                            result[r][c] = fill
    return result


def mark_empty_intersection_split_by_4(grid):
    H = len(grid); W = len(grid[0])
    sep = next((r for r in range(H) if all(grid[r][c]==4 for c in range(W))), None)
    if sep is None: return [list(row) for row in grid]
    top = grid[:sep]
    bot = grid[sep+1:]
    rows = min(len(top), len(bot))
    result = []
    for r in range(rows):
        row = []
        for c in range(W):
            if top[r][c]==0 and bot[r][c]==0:
                row.append(3)
            else:
                row.append(0)
        result.append(row)
    return result


def fill_enclosed_with_2_exterior_with_3(grid):
    from collections import deque
    H,W = len(grid),len(grid[0])
    result = [list(row) for row in grid]
    visited = [[False]*W for _ in range(H)]
    q = deque()
    for r in range(H):
        for c in range(W):
            if (r==0 or r==H-1 or c==0 or c==W-1) and grid[r][c]==0:
                q.append((r,c)); visited[r][c] = True
    while q:
        r,c = q.popleft()
        result[r][c] = 3
        for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            nr,nc = r+dr,c+dc
            if 0<=nr<H and 0<=nc<W and not visited[nr][nc] and grid[nr][nc]==0:
                visited[nr][nc] = True; q.append((nr,nc))
    for r in range(H):
        for c in range(W):
            if result[r][c] == 0:
                result[r][c] = 2
    return result


def fill_minority_gaps_in_majority_region(grid):
    from collections import Counter
    H,W = len(grid),len(grid[0])
    flat = [v for row in grid for v in row if v!=0]
    if not flat: return [list(r) for r in grid]
    cnt = Counter(flat)
    if len(cnt) < 2: return [list(r) for r in grid]
    majority = cnt.most_common(1)[0][0]
    region = [[grid[r][c]==majority for c in range(W)] for r in range(H)]
    changed = True
    while changed:
        changed = False
        for r in range(H):
            for c in range(W):
                if grid[r][c] != majority and grid[r][c] != 0 and not region[r][c]:
                    nbr = sum(1 for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]
                              if 0<=r+dr<H and 0<=c+dc<W and region[r+dr][c+dc])
                    if nbr >= 2:
                        region[r][c] = True; changed = True
    result = [[0]*W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            if region[r][c]:
                result[r][c] = majority
    return result


def extend_rows_to_double_by_period(grid):
    def find_period(row):
        n = len(row)
        for p in range(1, n+1):
            if all(row[i]==row[i%p] for i in range(n)):
                return p
        return n
    result = []
    for row in grid:
        p = find_period(row)
        base = row[:p]
        target = len(row)*2
        result.append([base[i%p] for i in range(target)])
    return result


def fill_5sep_sections_with_rotations(grid):
    def rot90cw(g):
        H,W = len(g),len(g[0])
        return [[g[H-1-c][r] for c in range(H)] for r in range(W)]
    H,W = len(grid),len(grid[0])
    sep_cols = [c for c in range(W) if all(grid[r][c]==5 for r in range(H))]
    if len(sep_cols) < 2: return [list(r) for r in grid]
    c0,c1 = sep_cols[0],sep_cols[1]
    left = [list(grid[r][0:c0]) for r in range(H)]
    mid = rot90cw(left)
    right = rot90cw(mid)
    result = [list(row) for row in grid]
    for r in range(H):
        for c in range(c0+1, c1):
            result[r][c] = mid[r][c-(c0+1)]
        for c in range(c1+1, W):
            result[r][c] = right[r][c-(c1+1)]
    return result


def staircase_fill_from_anchor(grid):
    H,W = len(grid),len(grid[0])
    anchor_r = None
    for r in range(H):
        if any(grid[r][c]!=0 for c in range(W)):
            anchor_r = r
            break
    if anchor_r is None: return [list(row) for row in grid]
    n = sum(1 for c in range(W) if grid[anchor_r][c]!=0)
    result = [list(row) for row in grid]
    for r in range(H):
        if r < anchor_r:
            count = n + (anchor_r - r)
            result[r] = [3]*min(count,W) + [0]*max(W-count,0)
        elif r > anchor_r:
            count = max(n - (r - anchor_r), 0)
            result[r] = [1]*count + [0]*(W-count)
    return result


def recolor_minor_to_major(grid):
    from collections import Counter
    flat = [v for row in grid for v in row if v!=0]
    if len(set(flat)) < 2: return [list(r) for r in grid]
    cnt = Counter(flat)
    minor = min(cnt.keys())
    major = max(cnt.keys())
    return [[major if v==minor else 0 for v in row] for row in grid]


def extract_unique_3x3_block(grid):
    from collections import Counter
    H,W = len(grid),len(grid[0])
    blocks = []
    if W == 3 and H % 3 == 0:
        for i in range(0, H, 3):
            blocks.append([list(grid[i+r]) for r in range(3)])
    elif H == 3 and W % 3 == 0:
        for j in range(0, W, 3):
            blocks.append([list(grid[r][j:j+3]) for r in range(H)])
    else:
        return [list(row) for row in grid]
    pats = [tuple(1 if b[r][c]!=0 else 0 for r in range(3) for c in range(3)) for b in blocks]
    cnt = Counter(pats)
    for b, p in zip(blocks, pats):
        if cnt[p] == 1:
            return b
    return blocks[0]


def swap_cross_intersection_colors(grid):
    from collections import Counter
    H,W = len(grid),len(grid[0])
    result = [list(row) for row in grid]
    def dominant_color(cells):
        nz = [v for v in cells if v!=0]
        if not nz: return None
        cnt = Counter(nz)
        top = cnt.most_common(1)[0]
        if top[1] >= len(nz)*0.6: return top[0]
        return None
    h_lines = {}
    for r in range(H):
        c = dominant_color(grid[r])
        if c is not None: h_lines[r] = c
    v_lines = {}
    for c in range(W):
        dc = dominant_color([grid[r][c] for r in range(H)])
        if dc is not None: v_lines[c] = dc
    for r, hc in h_lines.items():
        for c, vc in v_lines.items():
            if hc != vc:
                if result[r][c] == vc: result[r][c] = hc
                elif result[r][c] == hc: result[r][c] = vc
    return result


def crop_top_left_2x2(grid):
    return [list(grid[r][:2]) for r in range(min(2,len(grid)))]


def keep_middle_column_only(grid):
    H,W = len(grid),len(grid[0])
    mid = W//2
    return [[row[c] if c==mid else 0 for c in range(W)] for row in grid]


def surround_2s_with_3x3_ones(grid):
    H,W = len(grid),len(grid[0])
    result = [list(row) for row in grid]
    for r in range(H):
        for c in range(W):
            if grid[r][c] == 2:
                for dr in range(-1,2):
                    for dc in range(-1,2):
                        nr,nc = r+dr,c+dc
                        if 0<=nr<H and 0<=nc<W and result[nr][nc]==0:
                            result[nr][nc] = 1
    return result


def shift_pattern_by_2_markers(grid):
    H, W = len(grid), len(grid[0])
    result = [[0]*W for _ in range(H)]
    left_2_rows = sorted([r for r in range(H) if grid[r][0] == 2])
    right_2_rows = sorted([r for r in range(H) if grid[r][W-1] == 2])
    top_2_cols = sorted([c for c in range(W) if grid[0][c] == 2])
    bot_2_cols = sorted([c for c in range(W) if grid[H-1][c] == 2])
    if left_2_rows:
        template = None
        for r in range(H):
            if grid[r][0] != 2 and any(grid[r][c] != 0 for c in range(W)):
                template = list(grid[r]); break
        if template is None: return [list(row) for row in grid]
        marker_rows = left_2_rows
        seg_shifts = list(range(len(marker_rows)+1))
        seg_starts = [0] + marker_rows
        seg_ends = marker_rows + [H]
        for shift, s, e in zip(seg_shifts, seg_starts, seg_ends):
            for r in range(s, e):
                for c in range(W):
                    src = c - shift
                    if src >= 0: result[r][c] = template[src]
                if grid[r][0] == 2: result[r][0] = 2
        return result
    elif right_2_rows:
        template = None
        for r in range(H):
            if grid[r][W-1] != 2 and any(grid[r][c] != 0 for c in range(W)):
                template = list(grid[r]); break
        if template is None: return [list(row) for row in grid]
        marker_rows = right_2_rows
        seg_shifts = list(range(len(marker_rows)+1))
        seg_starts = [0] + marker_rows
        seg_ends = marker_rows + [H]
        for shift, s, e in zip(seg_shifts, seg_starts, seg_ends):
            for r in range(s, e):
                for c in range(W):
                    src = c + shift
                    if src < W: result[r][c] = template[src]
                if grid[r][W-1] == 2: result[r][W-1] = 2
        return result
    elif bot_2_cols:
        template = None
        for c in range(W):
            if grid[H-1][c] != 2 and any(grid[r][c] != 0 for r in range(H)):
                template = [grid[r][c] for r in range(H)]; break
        if template is None: return [list(row) for row in grid]
        marker_cols = bot_2_cols
        sec_shifts = list(range(len(marker_cols)+1))
        sec_starts = [0] + marker_cols
        sec_ends = marker_cols + [W]
        for shift, cs, ce in zip(sec_shifts, sec_starts, sec_ends):
            for c in range(cs, ce):
                for r in range(H):
                    src = r + shift
                    if src < H: result[r][c] = template[src]
                if grid[H-1][c] == 2: result[H-1][c] = 2
        return result
    elif top_2_cols:
        template = None
        for c in range(W):
            if grid[0][c] != 2 and any(grid[r][c] != 0 for r in range(H)):
                template = [grid[r][c] for r in range(H)]; break
        if template is None: return [list(row) for row in grid]
        marker_cols = top_2_cols
        sec_shifts = list(range(len(marker_cols)+1))
        sec_starts = [0] + marker_cols
        sec_ends = marker_cols + [W]
        for shift, cs, ce in zip(sec_shifts, sec_starts, sec_ends):
            for c in range(cs, ce):
                for r in range(H):
                    src = r - shift
                    if src >= 0: result[r][c] = template[src]
                if grid[0][c] == 2: result[0][c] = 2
        return result
    return [list(row) for row in grid]


def fill_bbox_interior_with_7(grid):
    from collections import deque
    H, W = len(grid), len(grid[0])
    visited = [[False]*W for _ in range(H)]
    result = [list(row) for row in grid]
    for sr in range(H):
        for sc in range(W):
            if grid[sr][sc] != 0 and not visited[sr][sc]:
                cluster = []
                q = deque([(sr,sc)])
                visited[sr][sc] = True
                while q:
                    r,c = q.popleft()
                    cluster.append((r,c))
                    for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nr,nc = r+dr,c+dc
                        if 0<=nr<H and 0<=nc<W and not visited[nr][nc] and grid[nr][nc]!=0:
                            visited[nr][nc] = True
                            q.append((nr,nc))
                r_min = min(r for r,c in cluster)
                r_max = max(r for r,c in cluster)
                c_min = min(c for r,c in cluster)
                c_max = max(c for r,c in cluster)
                for r in range(r_min, r_max+1):
                    for c in range(c_min, c_max+1):
                        if result[r][c] == 0:
                            result[r][c] = 7
    return result

def tile_two_nxn_blocks_from_3s(grid):
    H, W = len(grid), len(grid[0])
    cells_3 = [(r,c) for r in range(H) for c in range(W) if grid[r][c] == 3]
    all_nz = [(r,c) for r in range(H) for c in range(W) if grid[r][c] != 0]
    if not cells_3 or not all_nz: return [list(row) for row in grid]
    r_min = min(r for r,c in cells_3)
    c_min = min(c for r,c in cells_3)
    N = len(all_nz)
    OH, OW = H*3, W*3
    result = [[0]*OW for _ in range(OH)]
    for dr in range(N):
        for dc in range(N):
            if r_min+dr < OH and c_min+dc < OW:
                result[r_min+dr][c_min+dc] = 3
            if r_min+N+dr < OH and c_min+N+dc < OW:
                result[r_min+N+dr][c_min+N+dc] = 3
    return result

def extract_multicolor_stripe_order(grid):
    H, W = len(grid), len(grid[0])
    if len(set(grid[0])) == 1:
        seen = []
        for row in grid:
            c = row[0]
            if c not in seen:
                seen.append(c)
        return [[c] for c in seen]
    else:
        seen = []
        for r in range(H):
            for c in range(W):
                if grid[r][c] not in seen:
                    seen.append(grid[r][c])
        return [seen]


def extend_clusters_diagonally_outward(grid):
    from collections import deque
    H, W = len(grid), len(grid[0])
    visited = [[False]*W for _ in range(H)]
    clusters = []
    for sr in range(H):
        for sc in range(W):
            if grid[sr][sc] != 0 and not visited[sr][sc]:
                color = grid[sr][sc]
                cluster = []
                q = deque([(sr,sc)])
                visited[sr][sc] = True
                while q:
                    r,c = q.popleft()
                    cluster.append((r,c))
                    for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nr,nc = r+dr,c+dc
                        if 0<=nr<H and 0<=nc<W and not visited[nr][nc] and grid[nr][nc]!=0:
                            visited[nr][nc] = True
                            q.append((nr,nc))
                clusters.append((color, cluster))
    if len(clusters) != 2: return [list(row) for row in grid]
    result = [list(row) for row in grid]
    colors = sorted(set(c for c,_ in clusters))
    for color, cluster in clusters:
        r_min = min(r for r,c in cluster)
        r_max = max(r for r,c in cluster)
        c_min = min(c for r,c in cluster)
        c_max = max(c for r,c in cluster)
        if color == min(colors):
            r, c = r_min, c_min
            while r > 0 and c > 0:
                r -= 1; c -= 1
                result[r][c] = color
        else:
            r, c = r_max, c_max
            while r < H-1 and c < W-1:
                r += 1; c += 1
                result[r][c] = color
    return result

def extract_most_frequent_cluster_pattern(grid):
    H, W = len(grid), len(grid[0])
    cells_by_color = {}
    for r in range(H):
        for c in range(W):
            if grid[r][c] != 0:
                cells_by_color.setdefault(grid[r][c], []).append((r,c))
    if not cells_by_color: return [list(row) for row in grid]
    def count_groups(cells):
        remaining = set(cells)
        groups = []
        while remaining:
            seed = min(remaining)
            r0, c0 = seed
            group = frozenset((r,c) for r,c in remaining if abs(r-r0)<=2 and abs(c-c0)<=2)
            groups.append(group)
            remaining -= group
        return groups
    groups_by_color = {color: count_groups(cells) for color, cells in cells_by_color.items()}
    majority_color = max(groups_by_color, key=lambda c: len(groups_by_color[c]))
    group = sorted(groups_by_color[majority_color][0])
    r_min = min(r for r,c in group); r_max = max(r for r,c in group)
    c_min = min(c for r,c in group); c_max = max(c for r,c in group)
    cell_set = set(group)
    return [[majority_color if (r,c) in cell_set else 0
             for c in range(c_min, c_max+1)] for r in range(r_min, r_max+1)]


def trace_diagonal_reflection_off_2wall(grid):
    H, W = len(grid), len(grid[0])
    cells_8 = sorted((r, c) for r in range(H) for c in range(W) if grid[r][c] == 8)
    cells_2 = set((r, c) for r in range(H) for c in range(W) if grid[r][c] == 2)
    if len(cells_8) < 2: return [list(row) for row in grid]
    dr = cells_8[1][0] - cells_8[0][0]
    dc = cells_8[1][1] - cells_8[0][1]
    dr = dr // abs(dr) if dr != 0 else 0
    dc = dc // abs(dc) if dc != 0 else 0
    if all(grid[r][W-1] == 2 for r in range(H)):
        wall_side = 'right'
    elif all(grid[r][0] == 2 for r in range(H)):
        wall_side = 'left'
    elif all(grid[H-1][c] == 2 for c in range(W)):
        wall_side = 'bottom'
    elif all(grid[0][c] == 2 for c in range(W)):
        wall_side = 'top'
    else:
        wall_side = 'right'
    def will_hit_wall(start, ddr, ddc):
        r, c = start[0] + ddr, start[1] + ddc
        while 0 <= r < H and 0 <= c < W:
            if (r, c) in cells_2: return True
            r += ddr; c += ddc
        return False
    front, back = cells_8[-1], cells_8[0]
    if will_hit_wall(back, -dr, -dc):
        start_pos = back; extend_dr, extend_dc = -dr, -dc
    else:
        start_pos = front; extend_dr, extend_dc = dr, dc
    result = [list(row) for row in grid]
    r, c = start_pos
    reflected = False
    while True:
        next_r = r + extend_dr; next_c = c + extend_dc
        if not (0 <= next_r < H and 0 <= next_c < W): break
        if (next_r, next_c) in cells_2:
            if reflected: break
            reflected = True
            if wall_side in ('left', 'right'):
                extend_dc = -extend_dc
            else:
                extend_dr = -extend_dr
            continue
        r, c = next_r, next_c
        if grid[r][c] != 8:
            result[r][c] = 3
    return result

def extend_pattern_to_10rows(grid):
    H, W = len(grid), len(grid[0])
    OH = 10
    for P in range(1, H):
        for dc in list(range(0, W+1)) + list(range(-1, -W-1, -1)):
            def shift_row(row, d):
                return [row[c-d] if 0<=c-d<W else 0 for c in range(W)]
            consistent = all(shift_row(grid[i], dc) == list(grid[i+P]) for i in range(H-P))
            if consistent:
                result = [list(row) for row in grid]
                for r in range(H, OH):
                    result.append(shift_row(result[r-P], dc))
                return result
    result = [list(row) for row in grid]
    while len(result) < OH:
        result.append([0]*W)
    return result

def flip_grid_vertical(grid):
    return list(reversed(grid))


def flip_grid_horizontal(grid):
    return [list(reversed(row)) for row in grid]




# --- EVOLVED FUNCTIONS (auto-generated) ---

def extract_and_mirror_patterns(grid: list[list[int]]) -> list[list[int]]:
    """Extracts small patterns from one quadrant and mirrors them to the opposite quadrant based on symmetry."""
    import numpy as np
    g = np.array(grid)
    h, w = g.shape
    
    # Detect if the grid is split into two halves (e.g., left/right or top/bottom) by a border of 8s or 0s
    # Heuristic: Check if there's a vertical line of 8s or horizontal line of 0s separating regions
    is_vertical_split = False
    is_horizontal_split = False
    
    # Check for vertical split (top/bottom halves)
    if h > 1:
        mid_h = h // 2
        top_half = g[:mid_h, :]
        bot_half = g[mid_h:, :]
        # Check if top half is mostly 8s/0s or bot half is mostly 8s/0s (background)
        # Or check if there is a row of 8s at mid_h
        mid_row = g[mid_h, :]
        if np.all(mid_row == 8):
            is_vertical_split = True
        else:
            # Check for horizontal split (left/right halves)
            mid_w = w // 2
            left_half = g[:, :mid_w]
            right_half = g[:, mid_w:]
            mid_col = g[:, mid_w]
            if np.all(mid_col == 8):
                is_horizontal_split = True
    
    result = g.copy()
    
    if is_vertical_split:
        # Extract pattern from top half, mirror to bottom
        # Find non-background colors in top half
        mask_top = (top_half != 0) & (top_half != 8) # Assuming 0 and 8 are background/borders
        # Mirror the mask to bottom
        bot_mask = np.zeros_like(mask_top, dtype=bool)
        bot_mask[:, :] = mask_top[:, :] # Simple copy for now, or flip vertical
        # Actually, looking at tasks: 14754a24 (diagonal), 58e15b12 (diagonal), 97a05b5b (quadrant)
        # Let's implement a generic "extract and mirror" based on specific patterns found in failing tasks
        
        # Task 14754a24: Diagonal symmetry. Extract 3x3 patterns from top-left and mirror to bottom-right?
        # Task 58e15b12: Diagonal symmetry.
        # Task 97a05b5b: Quadrant symmetry.
        
        # Let's try to detect diagonal symmetry and fill missing parts
        # Extract top-left 3x3, bottom-right 3x3, etc.
        pass 
    elif is_horizontal_split:
        # Extract pattern from left half, mirror to right
        pass
        
    return result.tolist()

def extract_and_mirror_patterns(grid: list[list[int]]) -> list[list[int]]:
    """Extracts small patterns from one quadrant and mirrors them to the opposite quadrant based on symmetry."""
    import numpy as np
    g = np.array(grid)
    h, w = g.shape
    
    # Detect symmetry type: Horizontal, Vertical, or Diagonal
    # 1. Check for Horizontal Symmetry (Top mirrors Bottom)
    # 2. Check for Vertical Symmetry (Left mirrors Right)
    # 3. Check for Diagonal Symmetry (Top-Left mirrors Bottom-Right)
    
    # Heuristic for Diagonal Symmetry:
    # Compare top-left quadrant with bottom-right quadrant
    # If they are similar (same colors), it's diagonal symmetry.
    # If they are different, maybe one is the "source" and the other is the "target" to be filled.
    
    # Let's assume the task is: Given a grid with a pattern in one corner, fill the symmetric corner.
    # Or: Given a grid with a pattern in one corner, mirror it to the opposite corner.
    
    # Strategy:
    # 1. Identify the "active" region (non-background colors).
    # 2. Identify the "empty" region (background colors).
    # 3. If active region is in one quadrant, copy/mirror it to the symmetric quadrant.
    
    # Background color detection: Most frequent color, or 0.
    # Let's assume 0 is background for now, or the color that appears most on the border.
    border_colors = []
    for i in range(h):
        border_colors.append(g[0, i])
    for i in range(w):
        border_colors.append(g[-1, i])
    for i in range(w):
        border_colors.append(g[i, 0])
    for i in range(h):
        border_colors.append(g[i, -1])
        
    bg_color = np.bincount(border_colors).argmax()
    
    # Create mask of non-background
    mask = (g != bg_color)
    
    # Check for 4 quadrants
    mid_h, mid_w = h // 2, w // 2
    q1 = mask[:mid_h, :mid_w]
    q2 = mask[:mid_h, mid_w:]
    q3 = mask[mid_h:, :mid_w]
    q4 = mask[mid_h:, mid_w:]
    
    # Count non-zero pixels in each quadrant
    c1 = np.sum(q1)
    c2 = np.sum(q2)
    c3 = np.sum(q3)
    c4 = np.sum(q4)
    
    # Identify source quadrant: The one with the most activity (or specific pattern)
    # In the failing tasks, one quadrant has a pattern, others are empty (or have borders).
    # We want to mirror the pattern to the symmetric quadrant.
    
    # If c1 > 0 and c3 == 0: Mirror Q1 to Q3 (Vertical symmetry)
    # If c1 > 0 and c4 == 0: Mirror Q1 to Q4 (Diagonal symmetry)
    # If c2 > 0 and c4 == 0: Mirror Q2 to Q4 (Diagonal symmetry)
    # If c2 > 0 and c3 == 0: Mirror Q2 to Q3 (Horizontal symmetry)
    
    # But we need to handle the mirroring (flip) correctly.
    # Q1 -> Q3: Flip vertical
    # Q1 -> Q4: Flip vertical, then flip horizontal (rotate 90 or 180?)
    # Q2 -> Q4: Flip horizontal, then flip vertical
    # Q2 -> Q3: Flip horizontal
    
    # Let's implement a generic "fill symmetric quadrant"
    
    result = g.copy()
    
    # Case 1: Q1 has pattern, Q3 is empty (or mostly empty) -> Mirror Q1 to Q3
    if c1 > 10 and c3 < 10:
        # Mirror Q1 to Q3 (Vertical Flip)
        # q1 is top-left, q3 is bottom-left.
        # To mirror q1 to q3, we flip q1 vertically.
        # But we need to place it in q3.
        # q3 is bottom-left.
        # So we take q1, flip it vertically, and place it in q3.
        # Wait, q1 is top-left. q3 is bottom-left.
        # If q1 is [A, B; C, D], q3 should be [D, C; B, A] (Vertical Flip).
        # Let's implement this.
        pass
    
    # Case 2: Q1 has pattern, Q4 is empty -> Mirror Q1 to Q4 (Diagonal Flip)
    if c1 > 10 and c4 < 10:
        # Mirror Q1 to Q4.
        # q1 is top-left. q4 is bottom-right.
        # Diagonal symmetry: (r, c) -> (h-1-r, w-1-c)
        # So we need to flip both vertically and horizontally.
        pass
        
    # Case 3: Q2 has pattern, Q3 is empty -> Mirror Q2 to Q3 (Horizontal Flip)
    if c2 > 10 and c3 < 10:
        pass
        
    # Case 4: Q2 has pattern, Q4 is empty -> Mirror Q2 to Q4 (Diagonal Flip)
    if c2 > 10 and c4 < 10:
        pass
        
    # Case 5: Q3 has pattern, Q2 is empty -> Mirror Q3 to Q2 (Horizontal Flip)
    if c3 > 10 and c2 < 10:
        pass
        
    # Case 6: Q3 has pattern, Q4 is empty -> Mirror Q3 to Q4 (Diagonal Flip)
    if c3 > 10 and c4 < 10:
        pass
        
    # Case 7: Q4 has pattern, Q1 is empty -> Mirror Q4 to Q1 (Diagonal Flip)
    if c4 > 10 and c1 < 10:
        pass
        
    # Implement the mirroring logic
    # We need to extract the pattern from the source quadrant and place it in the target quadrant.
    # But we also need to handle the mirroring (flipping).
    
    # Let's implement a function to mirror a quadrant
    def mirror_quadrant(src, target, src_q, tgt_q):
        # src_q: 0 for Q1, 1 for Q2, 2 for Q3, 3 for Q4
        # tgt_q: target quadrant index
        h, w = src.shape
        # Calculate dimensions of the quadrant
        # If src_q == 0 (Q1), src is top-left.
        # If tgt_q == 2 (Q3), tgt is bottom-left.
        # We need to flip src vertically to match tgt.
        # src is h x w. tgt is h x w.
        # src is top-left. tgt is bottom-left.
        # To map (r, c) in src to (r, c) in tgt:
        # src: (0,0) -> (0,0) in local coords.
        # tgt: (0,0) in local coords -> (h-1, 0) in global coords.
        # So we need to flip src vertically.
        pass
        
    return result.tolist()

'''

exec(HELPER_CODE_PREFIX, globals())

def classify_problem_class(train):
    """Map a task to one of the mandated high-level problem classes."""
    if not train:
        return "Topological Occlusion and Set Difference"

    per_pair = []
    for pair in train:
        inp = pair['input']
        out = pair['output']
        in_bg = detect_background_color(inp)
        out_bg = detect_background_color(out)
        per_pair.append({
            "in_shape": (len(inp), len(inp[0])),
            "out_shape": (len(out), len(out[0])),
            "in_colors": set(cell for row in inp for cell in row),
            "out_colors": set(cell for row in out for cell in row),
            "in_non_bg": set(non_background_colors(inp, background=in_bg)),
            "out_non_bg": set(non_background_colors(out, background=out_bg)),
            "in_objects": len(get_objects(inp, background=in_bg, diag=True)),
            "out_objects": len(get_objects(out, background=out_bg, diag=True)),
            "in_pixels": len(get_foreground_pixels(inp, background=in_bg)),
            "out_pixels": len(get_foreground_pixels(out, background=out_bg)),
            "in_sym": max(symmetry_score_h(inp, background=in_bg), symmetry_score_v(inp, background=in_bg)),
            "out_sym": max(symmetry_score_h(out, background=out_bg), symmetry_score_v(out, background=out_bg)),
        })

    if all(
        info["out_colors"] <= info["in_colors"] and
        (len(info["out_non_bg"]) < len(info["in_non_bg"]) or info["out_objects"] < info["in_objects"])
        for info in per_pair
    ):
        return "Set-Theoretic Union and Intersection"

    if all(
        info["out_non_bg"] == info["in_non_bg"] and
        info["out_pixels"] >= info["in_pixels"] and
        info["out_sym"] >= info["in_sym"]
        for info in per_pair
    ):
        return "Topological Occlusion and Set Difference"

    scores = {
        "Topological Occlusion and Set Difference": 0,
        "Affine Transformations and Linear Algebra": 0,
        "Set-Theoretic Union and Intersection": 0,
    }
    same_size = all(
        len(pair['input']) == len(pair['output']) and len(pair['input'][0]) == len(pair['output'][0])
        for pair in train
    )
    if same_size:
        transform_fns = [
            rotate_cw,
            rotate_ccw,
            rotate_180,
            transpose,
            flip_anti_diagonal,
            mirror_h,
            mirror_v,
        ]
        if any(all(fn(pair['input']) == pair['output'] for pair in train) for fn in transform_fns):
            return "Affine Transformations and Linear Algebra"
        scores["Affine Transformations and Linear Algebra"] += 1

    for info in per_pair:
        in_rows, in_cols = info["in_shape"]
        out_rows, out_cols = info["out_shape"]
        in_colors = info["in_colors"]
        out_colors = info["out_colors"]
        in_non_bg = info["in_non_bg"]
        out_non_bg = info["out_non_bg"]
        in_objects = info["in_objects"]
        out_objects = info["out_objects"]
        in_pixels = info["in_pixels"]
        out_pixels = info["out_pixels"]

        if (out_rows, out_cols) != (in_rows, in_cols) and out_rows % in_rows == 0 and out_cols % in_cols == 0:
            scores["Affine Transformations and Linear Algebra"] += 2
        if (in_rows, in_cols) == (out_rows, out_cols) and out_non_bg == in_non_bg and out_objects == in_objects:
            scores["Affine Transformations and Linear Algebra"] += 1

        if out_colors <= in_colors or out_non_bg <= in_non_bg:
            scores["Set-Theoretic Union and Intersection"] += 2
        if len(out_non_bg) < len(in_non_bg) or out_objects < in_objects:
            scores["Set-Theoretic Union and Intersection"] += 1

        in_sym = info["in_sym"]
        out_sym = info["out_sym"]
        if out_sym >= in_sym:
            scores["Topological Occlusion and Set Difference"] += 2
        if out_pixels >= in_pixels:
            scores["Topological Occlusion and Set Difference"] += 1
        if len(out_non_bg) == len(in_non_bg):
            scores["Topological Occlusion and Set Difference"] += 1

    if all(
        max(symmetry_score_h(pair['output']), symmetry_score_v(pair['output'])) >=
        max(symmetry_score_h(pair['input']), symmetry_score_v(pair['input']))
        for pair in train
    ):
        scores["Topological Occlusion and Set Difference"] += 3

    if any(
        len(get_objects(pair['output'], diag=True)) > len(get_objects(pair['input'], diag=True))
        for pair in train
    ):
        scores["Set-Theoretic Union and Intersection"] += 2

    size_changes = [
        (len(pair['input']), len(pair['input'][0]), len(pair['output']), len(pair['output'][0]))
        for pair in train
    ]
    if all(orows % irows == 0 and ocols % icols == 0 for irows, icols, orows, ocols in size_changes) and any(
        (orows, ocols) != (irows, icols) for irows, icols, orows, ocols in size_changes
    ):
        scores["Affine Transformations and Linear Algebra"] += 3

    tie_break = {
        "Affine Transformations and Linear Algebra": 2,
        "Set-Theoretic Union and Intersection": 1,
        "Topological Occlusion and Set Difference": 0,
    }
    return max(scores, key=lambda name: (scores[name], tie_break[name]))

def find_exact_programs(task_data: dict, limit=4):
    train = task_data['train']
    if not train:
        return []
    try:
        problem_class = classify_problem_class(train)
    except Exception:
        problem_class = "Topological Occlusion and Set Difference"

    sizes_same = all(
        len(pair['input']) == len(pair['output']) and len(pair['input'][0]) == len(pair['output'][0])
        for pair in train
    )
    candidates = []
    if all(pair['output'] == train[0]['output'] for pair in train):
        constant_grid = [row[:] for row in train[0]['output']]
        candidates.append((
            repr(constant_grid),
            lambda g, constant_grid=constant_grid: [row[:] for row in constant_grid],
        ))
    if sizes_same and all(pair['input'] == pair['output'] for pair in train):
        candidates.append(("[row[:] for row in input_grid]", lambda g: [row[:] for row in g]))

    if sizes_same:
        exact_transforms = [
            ("rotate_cw(input_grid)", rotate_cw),
            ("rotate_ccw(input_grid)", rotate_ccw),
            ("rotate_180(input_grid)", rotate_180),
            ("transpose(input_grid)", transpose),
            ("flip_anti_diagonal(input_grid)", flip_anti_diagonal),
            ("mirror_h(input_grid)", mirror_h),
            ("mirror_v(input_grid)", mirror_v),
            ("symmetrize_h(input_grid)", symmetrize_h),
            ("symmetrize_v(input_grid)", symmetrize_v),
        ]
        for code, fn in exact_transforms:
            try:
                if all(fn(pair['input']) == pair['output'] for pair in train):
                    candidates.append((code, fn))
            except Exception:
                pass

        shift_candidates = None
        for pair in train:
            pair_matches = set()
            rows, cols = len(pair['input']), len(pair['input'][0])
            for dr in range(-rows + 1, rows):
                for dc in range(-cols + 1, cols):
                    if shift_grid(pair['input'], dr, dc) == pair['output']:
                        pair_matches.add((dr, dc))
            shift_candidates = pair_matches if shift_candidates is None else shift_candidates & pair_matches
            if not shift_candidates:
                break
        if shift_candidates:
            dr, dc = sorted(shift_candidates)[0]
            candidates.append((
                f"shift_grid(input_grid, {dr}, {dc})",
                lambda g, dr=dr, dc=dc: shift_grid(g, dr, dc),
            ))

    if sizes_same and all(len(set(cell for row in pair['output'] for cell in row)) == 1 for pair in train):
        fill_color = train[0]['output'][0][0]
        if all(pair['output'][0][0] == fill_color for pair in train):
            candidates.append((
                f"make_grid(len(input_grid), len(input_grid[0]), {fill_color})",
                lambda g, fill_color=fill_color: make_grid(len(g), len(g[0]), fill_color),
            ))

    if all(len(set(cell for row in pair['output'] for cell in row)) == 1 for pair in train):
        fill_color = train[0]['output'][0][0]
        out_rows = len(train[0]['output'])
        out_cols = len(train[0]['output'][0])
        if all(
            pair['output'][0][0] == fill_color and
            len(pair['output']) == out_rows and
            len(pair['output'][0]) == out_cols
            for pair in train
        ):
            candidates.append((
                f"make_grid({out_rows}, {out_cols}, {fill_color})",
                lambda g, out_rows=out_rows, out_cols=out_cols, fill_color=fill_color: make_grid(out_rows, out_cols, fill_color),
            ))

    if sizes_same:
        color_map = {}
        consistent = True
        for pair in train:
            for in_row, out_row in zip(pair['input'], pair['output']):
                for in_color, out_color in zip(in_row, out_row):
                    if in_color in color_map and color_map[in_color] != out_color:
                        consistent = False
                        break
                    color_map[in_color] = out_color
                if not consistent:
                    break
            if not consistent:
                break
        if consistent and color_map and any(k != v for k, v in color_map.items()):
            frozen_map = dict(color_map)
            candidates.append((
                f"remap_colors(input_grid, {frozen_map})",
                lambda g, frozen_map=frozen_map: remap_colors(g, frozen_map),
            ))

        # Shift + remap: shift then apply consistent color mapping
        try:
            max_s = min(4, min(len(train[0]['input']), len(train[0]['input'][0])) - 1)
            for dr in range(-max_s, max_s + 1):
                for dc in range(-max_s, max_s + 1):
                    if dr == 0 and dc == 0:
                        continue
                    smap = {}
                    consistent = True
                    for pair in train:
                        shifted = shift_grid(pair['input'], dr, dc)
                        for in_row, out_row in zip(shifted, pair['output']):
                            for in_c, out_c in zip(in_row, out_row):
                                if in_c in smap and smap[in_c] != out_c:
                                    consistent = False
                                    break
                                smap[in_c] = out_c
                            if not consistent:
                                break
                        if not consistent:
                            break
                    if consistent and smap and any(k != v for k, v in smap.items()):
                        frozen_smap = dict(smap)
                        smap_repr = repr(frozen_smap)
                        candidates.append((
                            f"remap_colors(shift_grid(input_grid, {dr}, {dc}), {smap_repr})",
                            lambda g, dr=dr, dc=dc, fm=frozen_smap: remap_colors(shift_grid(g, dr, dc), fm),
                        ))
        except Exception:
            pass

        # Rotation + remap: rotate then apply consistent color mapping
        rot_variants = [
            ("rotate_cw", rotate_cw),
            ("rotate_ccw", rotate_ccw),
            ("rotate_180", rotate_180),
            ("transpose", transpose),
            ("mirror_h", mirror_h),
            ("mirror_v", mirror_v),
        ]
        for rot_name, rot_fn in rot_variants:
            try:
                rmap = {}
                consistent = True
                for pair in train:
                    rotated = rot_fn(pair['input'])
                    if len(rotated) != len(pair['output']) or len(rotated[0]) != len(pair['output'][0]):
                        consistent = False
                        break
                    for in_row, out_row in zip(rotated, pair['output']):
                        for in_c, out_c in zip(in_row, out_row):
                            if in_c in rmap and rmap[in_c] != out_c:
                                consistent = False
                                break
                            rmap[in_c] = out_c
                        if not consistent:
                            break
                    if not consistent:
                        break
                if consistent and rmap and any(k != v for k, v in rmap.items()):
                    frozen_rmap = dict(rmap)
                    rmap_repr = repr(frozen_rmap)
                    candidates.append((
                        f"remap_colors({rot_name}(input_grid), {rmap_repr})",
                        lambda g, rfn=rot_fn, fm=frozen_rmap: remap_colors(rfn(g), fm),
                    ))
            except Exception:
                pass

    candidates.extend([
        (
            "extract_color(input_grid, dominant_non_background_color(input_grid), background=detect_background_color(input_grid))",
            lambda g: extract_color(
                g,
                dominant_non_background_color(g),
                background=detect_background_color(g),
            ),
        ),
        (
            "crop_foreground(extract_color(input_grid, dominant_non_background_color(input_grid), background=detect_background_color(input_grid)))",
            lambda g: crop_foreground(
                extract_color(
                    g,
                    dominant_non_background_color(g),
                    background=detect_background_color(g),
                ),
                background=detect_background_color(g),
            ),
        ),
    ])

    directional_object_fns = [
        ("topmost_object", topmost_object),
        ("bottommost_object", bottommost_object),
        ("leftmost_object", leftmost_object),
        ("rightmost_object", rightmost_object),
    ]
    for name, selector in directional_object_fns:
        candidates.append((
            f"crop_object(input_grid, {name}(get_objects(input_grid, background=detect_background_color(input_grid), diag=True)), background=detect_background_color(input_grid))",
            lambda g, selector=selector: crop_object(
                g,
                selector(get_objects(g, background=detect_background_color(g), diag=True)),
                background=detect_background_color(g),
            ),
        ))
        candidates.append((
            f"crop_foreground(crop_object(input_grid, {name}(get_objects(input_grid, background=detect_background_color(input_grid), diag=True)), background=detect_background_color(input_grid)))",
            lambda g, selector=selector: crop_foreground(
                crop_object(
                    g,
                    selector(get_objects(g, background=detect_background_color(g), diag=True)),
                    background=detect_background_color(g),
                ),
                background=detect_background_color(g),
            ),
        ))
        candidates.append((
            f"crop_object(input_grid, {name}(get_objects_by_color(input_grid, dominant_non_background_color(input_grid), diag=True)), background=detect_background_color(input_grid))",
            lambda g, selector=selector: crop_object(
                g,
                selector(get_objects_by_color(g, dominant_non_background_color(g), diag=True)),
                background=detect_background_color(g),
            ),
        ))
        candidates.append((
            f"crop_foreground(crop_object(input_grid, {name}(get_objects_by_color(input_grid, dominant_non_background_color(input_grid), diag=True)), background=detect_background_color(input_grid)))",
            lambda g, selector=selector: crop_foreground(
                crop_object(
                    g,
                    selector(get_objects_by_color(g, dominant_non_background_color(g), diag=True)),
                    background=detect_background_color(g),
                ),
                background=detect_background_color(g),
            ),
        ))

    scale_factors = set()
    scaling_matches = True
    for pair in train:
        in_rows, in_cols = len(pair['input']), len(pair['input'][0])
        out_rows, out_cols = len(pair['output']), len(pair['output'][0])
        if out_rows % in_rows != 0 or out_cols % in_cols != 0:
            scaling_matches = False
            break
        fr, fc = out_rows // in_rows, out_cols // in_cols
        scale_factors.add((fr, fc))
        if scale_grid(pair['input'], fr, fc) != pair['output']:
            scaling_matches = False
            break
    if scaling_matches and len(scale_factors) == 1:
        fr, fc = next(iter(scale_factors))
        candidates.append((
            f"scale_grid(input_grid, {fr}, {fc})",
            lambda g, fr=fr, fc=fc: scale_grid(g, fr, fc),
        ))

    tile_factors = set()
    tiling_matches = True
    for pair in train:
        in_rows, in_cols = len(pair['input']), len(pair['input'][0])
        out_rows, out_cols = len(pair['output']), len(pair['output'][0])
        if out_rows % in_rows != 0 or out_cols % in_cols != 0:
            tiling_matches = False
            break
        fr, fc = out_rows // in_rows, out_cols // in_cols
        tile_factors.add((fr, fc))
        if tile_grid(pair['input'], fr, fc) != pair['output']:
            tiling_matches = False
            break
    if tiling_matches and len(tile_factors) == 1:
        fr, fc = next(iter(tile_factors))
        candidates.append((
            f"tile_grid(input_grid, {fr}, {fc})",
            lambda g, fr=fr, fc=fc: tile_grid(g, fr, fc),
        ))

    candidates.extend([
        ("crop_foreground(input_grid)", lambda g: crop_foreground(g)),
        ("largest_object_grid(input_grid, diag=True, crop_result=True)", lambda g: largest_object_grid(g, diag=True, crop_result=True)),
        ("largest_shape_grid(input_grid, diag=True, crop_result=True)", lambda g: largest_shape_grid(g, diag=True, crop_result=True)),
        ("main_shape_grid(input_grid, diag=True, crop_result=True)", lambda g: main_shape_grid(g, diag=True, crop_result=True)),
        ("best_pattern_repair(input_grid, crop_result=True)", lambda g: best_pattern_repair(g, crop_result=True)),
        ("solve_occlusion(input_grid, crop_result=True)", lambda g: solve_occlusion(g, crop_result=True)),
        ("symmetrize_h(input_grid)", lambda g: symmetrize_h(g)),
        ("symmetrize_v(input_grid)", lambda g: symmetrize_v(g)),
        ("fill_from_mirror_h(input_grid)", lambda g: fill_from_mirror_h(g)),
        ("fill_from_mirror_v(input_grid)", lambda g: fill_from_mirror_v(g)),
        ("repair_symmetry(input_grid, axis='auto')", lambda g: repair_symmetry(g, axis='auto')),
        ("crop_foreground(remove_noise(input_grid))", lambda g: crop_foreground(remove_noise(g))),
        ("crop_foreground(best_enclosed_fill(input_grid))", lambda g: crop_foreground(best_enclosed_fill(g))),
        ("crop_foreground(best_enclosed_fill(remove_noise(input_grid)))", lambda g: crop_foreground(best_enclosed_fill(remove_noise(g)))),
        ("keep_most_common_colors(input_grid, n=1)", lambda g: keep_most_common_colors(g, n=1)),
        ("keep_most_common_colors(input_grid, n=2)", lambda g: keep_most_common_colors(g, n=2)),
        ("remove_small_objects(input_grid, max_size=1, diag=True)", lambda g: remove_small_objects(g, max_size=1, diag=True)),
        ("remove_small_shapes(input_grid, max_size=1, diag=True)", lambda g: remove_small_shapes(g, max_size=1, diag=True)),
        ("remove_border_objects_by_size(input_grid, max_size=None, diag=True)", lambda g: remove_border_objects_by_size(g, max_size=None, diag=True)),
        ("remove_border_shapes_by_size(input_grid, max_size=None, diag=True)", lambda g: remove_border_shapes_by_size(g, max_size=None, diag=True)),
        ("crop_foreground(keep_most_common_colors(input_grid, n=1))", lambda g: crop_foreground(keep_most_common_colors(g, n=1))),
        ("crop_foreground(keep_most_common_colors(input_grid, n=2))", lambda g: crop_foreground(keep_most_common_colors(g, n=2))),
        ("crop_foreground(remove_small_objects(input_grid, max_size=1, diag=True))", lambda g: crop_foreground(remove_small_objects(g, max_size=1, diag=True))),
        ("crop_foreground(remove_small_shapes(input_grid, max_size=1, diag=True))", lambda g: crop_foreground(remove_small_shapes(g, max_size=1, diag=True))),
        ("crop_foreground(remove_border_objects_by_size(input_grid, max_size=None, diag=True))", lambda g: crop_foreground(remove_border_objects_by_size(g, max_size=None, diag=True))),
        ("crop_foreground(remove_border_shapes_by_size(input_grid, max_size=None, diag=True))", lambda g: crop_foreground(remove_border_shapes_by_size(g, max_size=None, diag=True))),
        ("crop_foreground(remove_border_shapes_by_size(input_grid, max_size=4, diag=True))", lambda g: crop_foreground(remove_border_shapes_by_size(g, max_size=4, diag=True))),
    ])
    # Composite: crop foreground then apply transform or tile
    for name, fn in [("mirror_h", mirror_h), ("mirror_v", mirror_v), ("rotate_cw", rotate_cw),
                     ("rotate_ccw", rotate_ccw), ("rotate_180", rotate_180), ("transpose", transpose)]:
        candidates.append((
            f"{name}(crop_foreground(input_grid))",
            lambda g, fn=fn: fn(crop_foreground(g)),
        ))
    for rr, cc in [(1,2), (2,1), (2,2), (1,3), (3,1), (3,3), (1,4), (4,1), (2,3), (3,2)]:
        candidates.append((
            f"tile_grid(crop_foreground(input_grid), {rr}, {cc})",
            lambda g, rr=rr, cc=cc: tile_grid(crop_foreground(g), rr, cc),
        ))
    # New structural patterns
    candidates.append(("fill_l_shape_corners(input_grid)", lambda g: fill_l_shape_corners(g)))
    candidates.append(("kronecker_block_diagonal(input_grid)", lambda g: kronecker_block_diagonal(g)))
    candidates.append(("count_special_colors(input_grid)", lambda g: count_special_colors(g)))
    candidates.append(("repair_periodic_pattern(input_grid)", lambda g: repair_periodic_pattern(g)))
    candidates.append(("assemble_l_shapes(input_grid)", lambda g: assemble_l_shapes(g)))
    candidates.append(("fill_enclosed_by_parity(input_grid)", lambda g: fill_enclosed_by_parity(g)))
    candidates.append(("find_unique_quadrant(input_grid)", lambda g: find_unique_quadrant(g)))
    candidates.append(("reflect_2x2_block_to_corners(input_grid)", lambda g: reflect_2x2_block_to_corners(g)))
    candidates.append(("fill_columns_above_marker(input_grid)", lambda g: fill_columns_above_marker(g)))
    candidates.append(("draw_borders_around_pairs(input_grid)", lambda g: draw_borders_around_pairs(g)))
    candidates.append(("mark_uniform_rows(input_grid)", lambda g: mark_uniform_rows(g)))
    candidates.append(("find_unique_colored_quadrant(input_grid)", lambda g: find_unique_colored_quadrant(g)))
    candidates.append(("and_halves_by_separator(input_grid)", lambda g: and_halves_by_separator(g)))
    candidates.append(("color_interior_by_corner_quadrants(input_grid)", lambda g: color_interior_by_corner_quadrants(g)))
    for bc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        for mc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
            if bc != mc:
                candidates.append((f"color_interior_by_corner_quadrants(input_grid, border_color={bc}, marker_color={mc})", lambda g, bc=bc, mc=mc: color_interior_by_corner_quadrants(g, border_color=bc, marker_color=mc)))
    candidates.append(("gravity_down(input_grid)", lambda g: gravity_down(g)))
    candidates.append(("gravity_up(input_grid)", lambda g: gravity_up(g)))
    candidates.append(("gravity_left(input_grid)", lambda g: gravity_left(g)))
    candidates.append(("gravity_right(input_grid)", lambda g: gravity_right(g)))
    candidates.append(("drop_to_floor(input_grid)", lambda g: drop_to_floor(g)))
    candidates.append(("tile_4way_symmetric(input_grid)", lambda g: tile_4way_symmetric(g)))
    candidates.append(("rotate_four_quadrants(input_grid)", lambda g: rotate_four_quadrants(g)))
    candidates.append(("extract_unique_quadrant(input_grid)", lambda g: extract_unique_quadrant(g)))
    candidates.append(("check_180_symmetry(input_grid)", lambda g: check_180_symmetry(g)))
    for tv in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        for fv in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
            if tv != fv:
                candidates.append((f"check_180_symmetry(input_grid, true_val={tv}, false_val={fv})", lambda g, t=tv, f=fv: check_180_symmetry(g, t, f)))
    candidates.append(("bounce_tile_rows(input_grid)", lambda g: bounce_tile_rows(g)))
    candidates.append(("fill_sections_with_rotations(input_grid)", lambda g: fill_sections_with_rotations(g)))
    for sep_val in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        candidates.append((f"fill_sections_with_rotations(input_grid, sep={sep_val})", lambda g, s=sep_val: fill_sections_with_rotations(g, sep=s)))
    # Recolor single-color swaps (covers tasks like c8f0f002: 7→5)
    all_colors = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    for src in all_colors:
        for dst in all_colors:
            if src != dst:
                candidates.append((f"recolor(input_grid, {src}, {dst})", lambda g, s=src, d=dst: recolor(g, s, d)))
    candidates.append(("mirror_v(input_grid)", lambda g: mirror_v(g)))
    candidates.append(("mirror_h(input_grid)", lambda g: mirror_h(g)))
    candidates.append(("rotate_90_cw(input_grid)", lambda g: [list(row) for row in zip(*g[::-1])]))
    candidates.append(("rotate_90_ccw(input_grid)", lambda g: [list(row) for row in zip(*g)][::-1]))
    candidates.append(("rotate_180(input_grid)", lambda g: [row[::-1] for row in g[::-1]]))
    candidates.append(("stack_mirror_v(input_grid)", lambda g: stack_mirror_v(g)))
    candidates.append(("tile_grid(crop_foreground(input_grid), 1, 2)", lambda g: tile_grid(crop_foreground(g), 1, 2)))
    candidates.append(("tile_grid(crop_foreground(input_grid), 2, 1)", lambda g: tile_grid(crop_foreground(g), 2, 1)))
    candidates.append(("tile_grid(crop_foreground(input_grid), 2, 2)", lambda g: tile_grid(crop_foreground(g), 2, 2)))
    candidates.append(("fill_with_most_common(input_grid)", lambda g: fill_with_most_common(g)))
    candidates.append(("find_minimal_tile(input_grid)", lambda g: find_minimal_tile(g)))
    # Stripe-right from points with discovered connector color
    for sc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        candidates.append((f"stripe_right_from_points(input_grid, stripe_color={sc})", lambda g, sc=sc: stripe_right_from_points(g, stripe_color=sc)))
    candidates.append(("mark_singleton_cells(input_grid)", lambda g: mark_singleton_cells(g)))
    candidates.append(("tile_with_mirror_h(input_grid)", lambda g: tile_with_mirror_h(g)))
    candidates.append(("count_cells_to_row(input_grid)", lambda g: count_cells_to_row(g)))
    candidates.append(("draw_x_from_zero(input_grid)", lambda g: draw_x_from_zero(g)))
    candidates.append(("draw_diagonals_from_point(input_grid)", lambda g: draw_diagonals_from_point(g)))
    candidates.append(("draw_lines_from_point(input_grid)", lambda g: draw_lines_from_point(g)))
    candidates.append(("draw_full_cross_from_point(input_grid)", lambda g: draw_full_cross_from_point(g)))
    candidates.append(("nor_halves_by_separator(input_grid)", lambda g: nor_halves_by_separator(g)))
    candidates.append(("nor_halves_by_separator(input_grid, result_color=8)", lambda g: nor_halves_by_separator(g, result_color=8)))
    candidates.append(("recolor_non_singletons(input_grid)", lambda g: recolor_non_singletons(g)))
    candidates.append(("fill_diagonal_tile(input_grid)", lambda g: fill_diagonal_tile(g)))
    candidates.append(("extract_rarest_color_rect(input_grid)", lambda g: extract_rarest_color_rect(g)))
    candidates.append(("crop_most_dense_object(input_grid)", lambda g: crop_most_dense_object(g)))
    candidates.append(("fill_rectangle_interiors_ranked(input_grid)", lambda g: fill_rectangle_interiors_ranked(g)))
    for wc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        candidates.append((f"fill_rectangle_interiors_ranked(input_grid, wall_color={wc})", lambda g, wc=wc: fill_rectangle_interiors_ranked(g, wall_color=wc)))
    candidates.append(("fill_rectangles_between_corners(input_grid)", lambda g: fill_rectangles_between_corners(g)))
    for cc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        for fc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
            if cc != fc:
                candidates.append((f"fill_rectangles_between_corners(input_grid, corner_color={cc}, fill_color={fc})", lambda g, cc=cc, fc=fc: fill_rectangles_between_corners(g, corner_color=cc, fill_color=fc)))
    candidates.append(("count_2x2_blocks_to_row(input_grid)", lambda g: count_2x2_blocks_to_row(g)))
    for tc in [1, 2, 3, 4, 6, 7, 8, 9]:
        candidates.append((f"count_2x2_blocks_to_row(input_grid, target_color={tc})", lambda g, tc=tc: count_2x2_blocks_to_row(g, target_color=tc)))
    candidates.append(("classify_cell_count(input_grid)", lambda g: classify_cell_count(g)))
    for lc, hc in [(7,1), (1,7), (2,1), (1,2), (3,1), (1,3)]:
        candidates.append((f"classify_cell_count(input_grid, low_color={lc}, high_color={hc})", lambda g, lc=lc, hc=hc: classify_cell_count(g, low_color=lc, high_color=hc)))
    candidates.append(("draw_two_color_cross(input_grid)", lambda g: draw_two_color_cross(g)))
    for ic in [1, 2, 3, 4, 6, 7, 8, 9]:
        candidates.append((f"draw_two_color_cross(input_grid, intersection_color={ic})", lambda g, ic=ic: draw_two_color_cross(g, intersection_color=ic)))
    candidates.append(("replace_markers_with_nearest_frame(input_grid)", lambda g: replace_markers_with_nearest_frame(g)))
    candidates.append(("fill_matching_edge_rows(input_grid)", lambda g: fill_matching_edge_rows(g)))
    candidates.append(("fill_between_same_color_rows(input_grid)", lambda g: fill_between_same_color_rows(g)))
    candidates.append(("project_template_to_singletons(input_grid)", lambda g: project_template_to_singletons(g)))
    for m in [1, 2, 3, 4, 6, 7, 8, 9]:
        candidates.append((f"project_template_to_singletons(input_grid, marker={m})", lambda g, m=m: project_template_to_singletons(g, marker=m)))
    candidates.append(("rank_columns_by_height(input_grid)", lambda g: rank_columns_by_height(g)))
    for cm in [1, 2, 3, 4, 6, 7, 8, 9]:
        candidates.append((f"rank_columns_by_height(input_grid, marker={cm})", lambda g, cm=cm: rank_columns_by_height(g, marker=cm)))
    candidates.append(("fill_rows_col_by_value(input_grid)", lambda g: fill_rows_col_by_value(g)))
    for cm in [1, 3, 4, 6, 7, 8, 9]:
        candidates.append((f"fill_rows_col_by_value(input_grid, col_marker={cm})", lambda g, cm=cm: fill_rows_col_by_value(g, col_marker=cm)))
    candidates.append(("grid_separator_count(input_grid)", lambda g: grid_separator_count(g)))
    candidates.append(("draw_two_cell_frame_cross(input_grid)", lambda g: draw_two_cell_frame_cross(g)))
    candidates.append(("fill_clear_corridors(input_grid)", lambda g: fill_clear_corridors(g)))
    for fc in [1, 2, 3, 4, 6, 7, 8, 9]:
        candidates.append((f"fill_clear_corridors(input_grid, fill_color={fc})", lambda g, fc=fc: fill_clear_corridors(g, fill_color=fc)))
    candidates.append(("add_halo_cross_diag(input_grid)", lambda g: add_halo_cross_diag(g)))
    candidates.append(("mark_l_shape_inner_corner(input_grid)", lambda g: mark_l_shape_inner_corner(g)))
    for sc, mc in [(8,1),(1,8),(2,3),(3,2),(4,5),(5,4),(6,1),(7,1),(9,1)]:
        candidates.append((f"mark_l_shape_inner_corner(input_grid, shape_color={sc}, mark_color={mc})", lambda g, sc=sc, mc=mc: mark_l_shape_inner_corner(g, shape_color=sc, mark_color=mc)))
    candidates.append(("connect_markers_to_feature(input_grid)", lambda g: connect_markers_to_feature(g)))
    candidates.append(("stack_grid_then_mirror_v(input_grid)", lambda g: stack_grid_then_mirror_v(g)))
    candidates.append(("draw_border_frame(input_grid)", lambda g: draw_border_frame(g)))
    for bc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        candidates.append((f"draw_border_frame(input_grid, border_color={bc})", lambda g, bc=bc: draw_border_frame(g, border_color=bc)))
    candidates.append(("dedup_rows_cols(input_grid)", lambda g: dedup_rows_cols(g)))
    candidates.append(("staircase_grow(input_grid)", lambda g: staircase_grow(g)))
    candidates.append(("pad_and_double_edges(input_grid)", lambda g: pad_and_double_edges(g)))
    candidates.append(("color_count_to_diagonal(input_grid)", lambda g: color_count_to_diagonal(g)))
    candidates.append(("tile_mirror_row_rev_3x(input_grid)", lambda g: tile_mirror_row_rev_3x(g)))
    candidates.append(("falling_diagonals(input_grid)", lambda g: falling_diagonals(g)))
    candidates.append(("self_tile(input_grid)", lambda g: self_tile(g)))
    candidates.append(("two_block_diagonal_scale(input_grid)", lambda g: two_block_diagonal_scale(g)))
    for mk in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        for bc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
            if mk != bc:
                candidates.append((f"two_block_diagonal_scale(input_grid, marker={mk}, block_color={bc})", lambda g, mk=mk, bc=bc: two_block_diagonal_scale(g, marker=mk, block_color=bc)))
    for sep in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        for mk in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
            if sep != mk:
                candidates.append((f"xor_split_halves(input_grid, separator={sep}, marker={mk})", lambda g, sep=sep, mk=mk: xor_split_halves(g, separator=sep, marker=mk)))
    candidates.append(("color_template_quadrant(input_grid)", lambda g: color_template_quadrant(g)))
    for sc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        for tc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
            if sc != tc:
                candidates.append((f"color_template_quadrant(input_grid, sep_color={sc}, template_color={tc})", lambda g, sc=sc, tc=tc: color_template_quadrant(g, sep_color=sc, template_color=tc)))
    for fc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        candidates.append((f"fill_enclosed_background(input_grid, fill_color={fc}, max_size=None)", lambda g, fc=fc: fill_enclosed_background(g, fill_color=fc, max_size=None)))
    candidates.append(("fill_square_enclosed_regions(input_grid)", lambda g: fill_square_enclosed_regions(g)))
    candidates.append(("crop_rectangle_interior(input_grid)", lambda g: crop_rectangle_interior(g)))
    for fc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        candidates.append((f"crop_rectangle_interior(input_grid, frame_color={fc})", lambda g, fc=fc: crop_rectangle_interior(g, frame_color=fc)))
    # connect_color_pairs_diagonal: draw lines between same-color pairs
    candidates.append(("connect_color_pairs_diagonal(input_grid)", lambda g: connect_color_pairs_diagonal(g)))
    # crop_concentric_quadrant: extract top-left quadrant of concentric pattern
    candidates.append(("crop_concentric_quadrant(input_grid)", lambda g: crop_concentric_quadrant(g)))
    # check_8_path_between_2x2_blocks: path connectivity check
    candidates.append(("check_8_path_between_2x2_blocks(input_grid)", lambda g: check_8_path_between_2x2_blocks(g)))
    # replace_8_blobs_with_key: replace 8-shaped blobs with the key pattern
    candidates.append(("replace_8_blobs_with_key(input_grid)", lambda g: replace_8_blobs_with_key(g)))
    # expand_frame_pattern_outward: expand bordered frame by swapping colors and adding outer ring
    candidates.append(("expand_frame_pattern_outward(input_grid)", lambda g: expand_frame_pattern_outward(g)))
    # output_most_common_pattern: find color with most instances, return one instance's bbox
    candidates.append(("output_most_common_pattern(input_grid)", lambda g: output_most_common_pattern(g)))
    # crop_and_recolor_template: 4-corner markers + template pattern → inner box with template→marker color
    candidates.append(("crop_and_recolor_template(input_grid)", lambda g: crop_and_recolor_template(g)))
    # assemble_parts_around_pivot: align 8-connected components by their pivot cell
    candidates.append(("assemble_parts_around_pivot(input_grid)", lambda g: assemble_parts_around_pivot(g)))
    for pv in [1, 2, 3, 4, 6, 7, 8, 9]:
        candidates.append((f"assemble_parts_around_pivot(input_grid, pivot={pv})", lambda g, pv=pv: assemble_parts_around_pivot(g, pivot=pv)))
    # project_template_row_onto_marker_rows: template 5-row projected as 2s onto marker rows
    candidates.append(("project_template_row_onto_marker_rows(input_grid)", lambda g: project_template_row_onto_marker_rows(g)))
    # add_color_halos_by_type: 1→cardinal-7, 2→diagonal-4
    candidates.append(("add_color_halos_by_type(input_grid)", lambda g: add_color_halos_by_type(g)))
    # complete_fourfold_rotational_symmetry: complete 90° rotational symmetry
    candidates.append(("complete_fourfold_rotational_symmetry(input_grid)", lambda g: complete_fourfold_rotational_symmetry(g)))
    # expand_cross_pattern_one_level: expand 3x3 cross to 5x5 crystalline
    candidates.append(("expand_cross_pattern_one_level(input_grid)", lambda g: expand_cross_pattern_one_level(g)))
    # fill_matching_end_rows: fill rows where col-0 and col-last same non-bg color
    candidates.append(("fill_matching_end_rows(input_grid)", lambda g: fill_matching_end_rows(g)))
    # fill_zones_by_two_cells: two cells split grid into zones with full/border rows
    candidates.append(("fill_zones_by_two_cells(input_grid)", lambda g: fill_zones_by_two_cells(g)))
    # sweep_shape_in_marker_direction: sweep 2x2 diagonally based on marker positions
    candidates.append(("sweep_shape_in_marker_direction(input_grid)", lambda g: sweep_shape_in_marker_direction(g)))
    for mc in [1, 3, 4, 5, 6, 7, 8, 9]:
        candidates.append((f"sweep_shape_in_marker_direction(input_grid, marker={mc})", lambda g, mc=mc: sweep_shape_in_marker_direction(g, marker=mc)))
    # align_blobs_to_color1_rows: align all blobs to color-1's row span
    candidates.append(("align_blobs_to_color1_rows(input_grid)", lambda g: align_blobs_to_color1_rows(g)))
    # shift_shapes_except_bottom_edge: parallelogram shear reduction
    candidates.append(("shift_shapes_except_bottom_edge(input_grid)", lambda g: shift_shapes_except_bottom_edge(g)))
    # split_blob_into_nodes_and_edges: 5-blob → 8 (2x2 nodes) + 2 (path edges)
    candidates.append(("split_blob_into_nodes_and_edges(input_grid)", lambda g: split_blob_into_nodes_and_edges(g)))
    for bc in [1, 2, 3, 4, 6, 7, 8, 9]:
        candidates.append((f"split_blob_into_nodes_and_edges(input_grid, blob_color={bc})", lambda g, bc=bc: split_blob_into_nodes_and_edges(g, blob_color=bc)))
    candidates.append(("add_cardinal_diagonal_markers_1_2(input_grid)", lambda g: add_cardinal_diagonal_markers_1_2(g)))
    candidates.append(("move_2blob_adjacent_to_8blob(input_grid)", lambda g: move_2blob_adjacent_to_8blob(g)))
    candidates.append(("expand_cross_to_diamond(input_grid)", lambda g: expand_cross_to_diamond(g)))
    candidates.append(("extend_cells_to_lines_col2_row_others(input_grid)", lambda g: extend_cells_to_lines_col2_row_others(g)))
    candidates.append(("fill_grid_two_color_stripe(input_grid)", lambda g: fill_grid_two_color_stripe(g)))
    candidates.append(("fill_periodic_tiling_hole(input_grid)", lambda g: fill_periodic_tiling_hole(g)))
    candidates.append(("copy_template_to_all_sections(input_grid)", lambda g: copy_template_to_all_sections(g)))
    candidates.append(("shift_rows_down_one(input_grid)", lambda g: shift_rows_down_one(g)))
    candidates.append(("fill_between_collinear_pairs(input_grid)", lambda g: fill_between_collinear_pairs(g)))
    candidates.append(("extend_cells_to_cross_intersect2(input_grid)", lambda g: extend_cells_to_cross_intersect2(g)))
    candidates.append(("count_2x2_blocks_output_row(input_grid)", lambda g: count_2x2_blocks_output_row(g)))
    candidates.append(("float_2s_up_against_1s(input_grid)", lambda g: float_2s_up_against_1s(g)))
    candidates.append(("fill_l_corner(input_grid)", lambda g: fill_l_corner(g)))
    candidates.append(("project_marker_cols_to_marker_rows(input_grid)", lambda g: project_marker_cols_to_marker_rows(g)))
    candidates.append(("fill_grid_sections_fixed_colors(input_grid)", lambda g: fill_grid_sections_fixed_colors(g)))
    candidates.append(("drop_1s_to_5_floor(input_grid)", lambda g: drop_1s_to_5_floor(g)))
    candidates.append(("add_moore_border_around_5(input_grid)", lambda g: add_moore_border_around_5(g)))
    candidates.append(("flood_fill_from_seeds(input_grid)", lambda g: flood_fill_from_seeds(g)))
    candidates.append(("fill_grid_cell_spans_bidirectional(input_grid)", lambda g: fill_grid_cell_spans_bidirectional(g)))
    candidates.append(("fill_1s_in_8rows_with_3(input_grid)", lambda g: fill_1s_in_8rows_with_3(g)))
    candidates.append(("add_knight_jump_8s_to_diagonal_pairs(input_grid)", lambda g: add_knight_jump_8s_to_diagonal_pairs(g)))
    candidates.append(("draw_cross_through_rectangle_center(input_grid)", lambda g: draw_cross_through_rectangle_center(g)))
    candidates.append(("draw_plus_at_midpoint(input_grid)", lambda g: draw_plus_at_midpoint(g)))
    candidates.append(("replace_5_with_3x3_block(input_grid)", lambda g: replace_5_with_3x3_block(g)))
    candidates.append(("clear_border_fill_interior_3(input_grid)", lambda g: clear_border_fill_interior_3(g)))
    candidates.append(("fill_rectangle_interior_and_shoot_gap(input_grid)", lambda g: fill_rectangle_interior_and_shoot_gap(g)))
    candidates.append(("fill_horizontal_gaps_between_blobs_9(input_grid)", lambda g: fill_horizontal_gaps_between_blobs_9(g)))
    for fc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        for wc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
            if fc != wc:
                candidates.append((f"fill_square_enclosed_regions(input_grid, fill_color={fc}, wall_color={wc})", lambda g, fc=fc, wc=wc: fill_square_enclosed_regions(g, fill_color=fc, wall_color=wc)))
    candidates.append(("mark_uniform_rows(input_grid)", lambda g: mark_uniform_rows(g)))
    for mc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        candidates.append((f"mark_uniform_rows(input_grid, mark_color={mc})", lambda g, mc=mc: mark_uniform_rows(g, mark_color=mc)))
    candidates.append(("mark_uniform_cols(input_grid)", lambda g: mark_uniform_cols(g)))
    for mc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        candidates.append((f"mark_uniform_cols(input_grid, mark_color={mc})", lambda g, mc=mc: mark_uniform_cols(g, mark_color=mc)))
    candidates.append(("project_template_row_to_markers(input_grid)", lambda g: project_template_row_to_markers(g)))
    for fc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        candidates.append((f"project_template_row_to_markers(input_grid, fill_color={fc})", lambda g, fc=fc: project_template_row_to_markers(g, fill_color=fc)))
    candidates.append(("draw_l_path_between_colors(input_grid)", lambda g: draw_l_path_between_colors(g)))
    for ca in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        for cb in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
            if ca != cb:
                for pc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
                    if pc != ca and pc != cb:
                        candidates.append((f"draw_l_path_between_colors(input_grid, color_a={ca}, color_b={cb}, path_color={pc})", lambda g, ca=ca, cb=cb, pc=pc: draw_l_path_between_colors(g, color_a=ca, color_b=cb, path_color=pc)))
    candidates.append(("add_full_halo(input_grid)", lambda g: add_full_halo(g)))
    for tc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        for hc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
            if tc != hc:
                candidates.append((f"add_full_halo(input_grid, target_color={tc}, halo_color={hc})", lambda g, tc=tc, hc=hc: add_full_halo(g, target_color=tc, halo_color=hc)))
    # Multi-color halo mapping: learn (input_color → halo_color) from training pairs
    try:
        halo_map_candidate = {}
        halo_map_valid = True
        for pair in train:
            inp, out = pair['input'], pair['output']
            rows, cols = len(inp), len(inp[0])
            if len(out) != rows or len(out[0]) != cols:
                halo_map_valid = False
                break
            for r in range(rows):
                for c in range(cols):
                    color = inp[r][c]
                    if color == 0:
                        continue
                    # Check surrounding cells in output for a consistent halo color
                    neighbors = []
                    for dr in range(-1, 2):
                        for dc in range(-1, 2):
                            if dr == 0 and dc == 0:
                                continue
                            nr, nc = r + dr, c + dc
                            if 0 <= nr < rows and 0 <= nc < cols:
                                ov = out[nr][nc]
                                if ov != 0 and ov != color:
                                    neighbors.append(ov)
                    if not neighbors:
                        continue
                    if len(set(neighbors)) != 1:
                        halo_map_valid = False
                        break
                    halo_color = neighbors[0]
                    if color in halo_map_candidate and halo_map_candidate[color] != halo_color:
                        halo_map_valid = False
                        break
                    halo_map_candidate[color] = halo_color
                if not halo_map_valid:
                    break
            if not halo_map_valid:
                break
        if halo_map_valid and len(halo_map_candidate) >= 2:
            frozen_hm = dict(halo_map_candidate)
            hm_repr = repr(frozen_hm)
            candidates.append((
                f"apply_halo_map(input_grid, {hm_repr})",
                lambda g, fm=frozen_hm: apply_halo_map(g, fm),
            ))
    except Exception:
        pass
    candidates.append(("project_markers_onto_block_face(input_grid)", lambda g: project_markers_onto_block_face(g)))
    for bc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        candidates.append((f"project_markers_onto_block_face(input_grid, block_color={bc})", lambda g, bc=bc: project_markers_onto_block_face(g, block_color=bc)))
    candidates.append(("alternate_middle_rows_of_triples(input_grid)", lambda g: alternate_middle_rows_of_triples(g)))
    candidates.append(("extract_inner_shape(input_grid)", lambda g: extract_inner_shape(g)))
    # Extract 3x3 neighborhood around the marker color (default 8), replacing marker with surrounding color
    for mk in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        candidates.append((f"extract_neighborhood_of_marker(input_grid, marker={mk})", lambda g, mk=mk: extract_neighborhood_of_marker(g, marker=mk)))
        candidates.append((f"extract_neighborhood_of_marker(input_grid, marker={mk}, replace_marker=False)", lambda g, mk=mk: extract_neighborhood_of_marker(g, marker=mk, replace_marker=False)))
    candidates.append(("complete_4fold_rot_symmetry(input_grid)", lambda g: complete_4fold_rot_symmetry(g)))
    candidates.append(("expand_cross_pattern(input_grid)", lambda g: expand_cross_pattern(g)))
    for cc in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        for ac in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
            if cc != ac:
                candidates.append((f"expand_cross_pattern(input_grid, center_color={cc}, arm_color={ac})", lambda g, cc=cc, ac=ac: expand_cross_pattern(g, center_color=cc, arm_color=ac)))
    if sizes_same:
        candidates.extend([
            ("foreground_in_place(input_grid)", lambda g: foreground_in_place(g)),
            ("best_pattern_repair_in_place(input_grid)", lambda g: best_pattern_repair_in_place(g)),
            ("solve_occlusion_in_place(input_grid)", lambda g: solve_occlusion_in_place(g)),
            ("best_enclosed_fill(input_grid)", lambda g: best_enclosed_fill(g)),
            ("remove_noise(input_grid)", lambda g: remove_noise(g)),
            ("largest_object_in_place(input_grid, diag=True)", lambda g: largest_object_in_place(g, diag=True)),
            ("largest_shape_in_place(input_grid, diag=True)", lambda g: largest_shape_in_place(g, diag=True)),
            ("main_shape_in_place(input_grid, diag=True)", lambda g: main_shape_in_place(g, diag=True)),
            ("repair_main_shape_in_place(input_grid)", lambda g: repair_main_shape_in_place(g)),
            ("repair_main_shape_symmetry(input_grid)", lambda g: repair_main_shape_symmetry(g)),
            ("remove_border_objects_by_size(input_grid, max_size=None, diag=True)", lambda g: remove_border_objects_by_size(g, max_size=None, diag=True)),
            ("remove_border_shapes_by_size(input_grid, max_size=None, diag=True)", lambda g: remove_border_shapes_by_size(g, max_size=None, diag=True)),
        ])
        for direction in ("down", "up", "left", "right"):
            candidates.append((
                f"apply_gravity(input_grid, direction='{direction}')",
                lambda g, direction=direction: apply_gravity(g, direction=direction),
            ))
        for axis in ("h", "v"):
            candidates.append((
                f"repair_symmetry(input_grid, axis='{axis}')",
                lambda g, axis=axis: repair_symmetry(g, axis=axis),
            ))

    input_colors = sorted({
        cell
        for pair in train
        for row in pair['input']
        for cell in row
    })
    output_colors = sorted({
        cell
        for pair in train
        for row in pair['output']
        for cell in row
    })
    background_candidates = {detect_background_color(pair['input']) for pair in train}
    candidate_colors = [c for c in sorted(set(input_colors) | set(output_colors)) if c not in background_candidates][:6]
    for color in candidate_colors:
        candidates.append((
            f"remove_color(input_grid, {color}, background=detect_background_color(input_grid))",
            lambda g, color=color: remove_color(g, color, background=detect_background_color(g)),
        ))
        candidates.append((
            f"crop_foreground(remove_color(input_grid, {color}, background=detect_background_color(input_grid)))",
            lambda g, color=color: crop_foreground(remove_color(g, color, background=detect_background_color(g))),
        ))
        candidates.append((
            f"extract_color(input_grid, {color}, background=detect_background_color(input_grid))",
            lambda g, color=color: extract_color(g, color, background=detect_background_color(g)),
        ))
        candidates.append((
            f"crop_foreground(extract_color(input_grid, {color}, background=detect_background_color(input_grid)))",
            lambda g, color=color: crop_foreground(extract_color(g, color, background=detect_background_color(g))),
        ))
    for color in output_colors[:4]:
        candidates.append((
            f"extract_color(input_grid, {color}, background=detect_background_color(input_grid))",
            lambda g, color=color: extract_color(g, color, background=detect_background_color(g)),
        ))
    for n in (1, 2):
        candidates.append((
            f"keep_most_common_colors(input_grid, n={n})",
            lambda g, n=n: keep_most_common_colors(g, n=n),
        ))
    # crop to square: take first rows×rows or cols×cols subgrid
    candidates.append((
        "[row[:len(input_grid)] for row in input_grid]",
        lambda g: [row[:len(g)] for row in g],
    ))
    candidates.append((
        "input_grid[:len(input_grid[0])]",
        lambda g: g[:len(g[0])] if g else g,
    ))
    # crop corner tiles (input divided into 3x3 sub-tiles)
    candidates.append((
        "[row[:len(input_grid[0])//3] for row in input_grid[:len(input_grid)//3]]",
        lambda g: [row[:len(g[0])//3] for row in g[:len(g)//3]] if g and len(g[0])//3 > 0 and len(g)//3 > 0 else g,
    ))
    candidates.append((
        "[row[-(len(input_grid[0])//3):] for row in input_grid[:len(input_grid)//3]]",
        lambda g: [row[-(len(g[0])//3):] for row in g[:len(g)//3]] if g and len(g[0])//3 > 0 and len(g)//3 > 0 else g,
    ))
    candidates.append((
        "[row[:len(input_grid[0])//3] for row in input_grid[-(len(input_grid)//3):]]",
        lambda g: [row[:len(g[0])//3] for row in g[-(len(g)//3):]] if g and len(g[0])//3 > 0 and len(g)//3 > 0 else g,
    ))
    candidates.append((
        "[row[-(len(input_grid[0])//3):] for row in input_grid[-(len(input_grid)//3):]]",
        lambda g: [row[-(len(g[0])//3):] for row in g[-(len(g)//3):]] if g and len(g[0])//3 > 0 and len(g)//3 > 0 else g,
    ))
    # fill bounding-box holes with fill_color
    for fc in range(1, 10):
        candidates.append((f"fill_bbox_holes(input_grid, fill_color={fc})", lambda g, fc=fc: fill_bbox_holes(g, fill_color=fc)))
    # attract non-anchor cells toward unique anchor cell
    candidates.append(("attract_cells_to_unique_anchor(input_grid)", lambda g: attract_cells_to_unique_anchor(g)))
    # reflect shape across separator cross → 4-fold reflection
    candidates.append(("reflect_shape_across_separator(input_grid)", lambda g: reflect_shape_across_separator(g)))
    # stamp_shape_at_marker: copies shape to marker location
    for mc in range(1, 10):
        candidates.append((
            f"stamp_shape_at_marker(input_grid, marker_color={mc})",
            lambda g, mc=mc: stamp_shape_at_marker(g, marker_color=mc),
        ))
    # reverse_concentric_rings: swap outer/inner ring colors
    candidates.append(("reverse_concentric_rings(input_grid)", lambda g: reverse_concentric_rings(g)))
    # fractal_tile_nonzero: self-similar expansion
    candidates.append(("fractal_tile_nonzero(input_grid)", lambda g: fractal_tile_nonzero(g)))
    for bg in (0, 1):
        if bg != 0:
            candidates.append((f"fractal_tile_nonzero(input_grid, background={bg})", lambda g, bg=bg: fractal_tile_nonzero(g, background=bg)))
    # fill_regions_with_dominant_color: grid partitioned by separator
    for sep in range(1, 10):
        candidates.append((
            f"fill_regions_with_dominant_color(input_grid, separator={sep})",
            lambda g, sep=sep: fill_regions_with_dominant_color(g, separator=sep),
        ))
    # fill_gaps_between_endpoints: fill interior gaps between same-color endpoints
    for fc in range(1, 10):
        candidates.append((
            f"fill_gaps_between_endpoints(input_grid, fill_color={fc})",
            lambda g, fc=fc: fill_gaps_between_endpoints(g, fill_color=fc),
        ))
    for fc in range(1, 10):
        candidates.append((
            f"fill_gaps_between_endpoints_rows(input_grid, fill_color={fc})",
            lambda g, fc=fc: fill_gaps_between_endpoints_rows(g, fill_color=fc),
        ))
    # upscale_grid: each cell → factor×factor block
    for fac in (2, 3, 4):
        candidates.append((
            f"upscale_grid(input_grid, factor={fac})",
            lambda g, fac=fac: upscale_grid(g, factor=fac),
        ))
    candidates.append(("upscale_by_color_count(input_grid)", lambda g: upscale_by_color_count(g)))
    # find_odd_quadrant_cell: pick odd-one-out value across 4 quadrants
    candidates.append(("find_odd_quadrant_cell(input_grid)", lambda g: find_odd_quadrant_cell(g)))
    # move_toward_target_color: move mover color toward target
    for mc2 in range(1, 10):
        for tc in range(1, 10):
            if mc2 != tc:
                candidates.append((
                    f"move_toward_target_color(input_grid, mover_color={mc2}, target_color={tc})",
                    lambda g, mc2=mc2, tc=tc: move_toward_target_color(g, mover_color=mc2, target_color=tc),
                ))
    # sort_colors_to_columns_by_count: histogram of color counts
    candidates.append(("sort_colors_to_columns_by_count(input_grid)", lambda g: sort_colors_to_columns_by_count(g)))
    # checkerboard_interleave_rows
    candidates.append(("checkerboard_interleave_rows(input_grid)", lambda g: checkerboard_interleave_rows(g)))
    # tile_kernel_diagonally: extract kernel, tile diagonally on 2x output
    candidates.append(("tile_kernel_diagonally(input_grid)", lambda g: tile_kernel_diagonally(g)))
    # rotate_concentric_rings_cyclic: shift ring colors inward by one
    candidates.append(("rotate_concentric_rings_cyclic(input_grid)", lambda g: rotate_concentric_rings_cyclic(g)))
    # propagate_upward_v_shape: apex color propagates upward in V-pattern
    candidates.append(("propagate_upward_v_shape(input_grid)", lambda g: propagate_upward_v_shape(g)))
    # replace_non_dominant_with_color: replace non-majority cells with a color
    for rc in range(1, 10):
        candidates.append((
            f"replace_non_dominant_with_color(input_grid, replace_color={rc})",
            lambda g, rc=rc: replace_non_dominant_with_color(g, replace_color=rc),
        ))
    # draw_L_rays_to_edge: each non-bg cell casts right+down L-shaped ray
    candidates.append(("draw_L_rays_to_edge(input_grid)", lambda g: draw_L_rays_to_edge(g)))
    # add_cross_intersection_halo: 3x3 halo of halo_color around cross intersection
    for hc in range(1, 10):
        candidates.append((
            f"add_cross_intersection_halo(input_grid, halo_color={hc})",
            lambda g, hc=hc: add_cross_intersection_halo(g, halo_color=hc),
        ))
    # fill_rows_cycling_header_colors: fill blank rows cyclically with header colors
    candidates.append(("fill_rows_cycling_header_colors(input_grid)", lambda g: fill_rows_cycling_header_colors(g)))
    # extend_period_by_half: detect period, extend by n//2 rows with recolor
    for oc, nc in [(1,2),(2,1),(1,1),(0,0)]:
        if oc != nc or oc == 0:
            lbl = f"extend_period_by_half(input_grid, old_color={oc}, new_color={nc})" if (oc,nc) != (1,2) else "extend_period_by_half(input_grid)"
            candidates.append((lbl, lambda g, oc=oc, nc=nc: extend_period_by_half(g, old_color=oc, new_color=nc)))
    # drip_down_columns: propagate non-bg values downward
    candidates.append(("drip_down_columns(input_grid)", lambda g: drip_down_columns(g)))
    # float_up_objects_by_height: each object floats up so bottom = (rows-1)-height
    candidates.append(("float_up_objects_by_height(input_grid)", lambda g: float_up_objects_by_height(g)))
    # mark_isolated_cells: single-cell connected components become mark_color
    for tc in range(1, 10):
        for mc in range(1, 10):
            if tc != mc:
                candidates.append((f"mark_isolated_cells(input_grid, target_color={tc}, mark_color={mc})", lambda g, tc=tc, mc=mc: mark_isolated_cells(g, target_color=tc, mark_color=mc)))
    # complete_checkerboard_inverted: fill masked checkerboard with swapped colors
    candidates.append(("complete_checkerboard_inverted(input_grid)", lambda g: complete_checkerboard_inverted(g)))
    # shoot_arrow_from_wedge: special color shoots ray from narrow tip
    candidates.append(("shoot_arrow_from_wedge(input_grid)", lambda g: shoot_arrow_from_wedge(g)))
    for bg in range(1, 10):
        candidates.append((f"shoot_arrow_from_wedge(input_grid, background={bg})", lambda g, bg=bg: shoot_arrow_from_wedge(g, background=bg)))
    # color_order_strip: distinct colors in order of first appearance
    for bg in range(10):
        candidates.append((f"color_order_strip(input_grid, background={bg})", lambda g, bg=bg: color_order_strip(g, background=bg)))
    # gravity
    candidates.append(("drip_down_gravity(input_grid)", lambda g: drip_down_gravity(g)))
    candidates.append(("drip_up_gravity(input_grid)", lambda g: drip_up_gravity(g)))
    candidates.append(("drip_right_gravity(input_grid)", lambda g: drip_right_gravity(g)))
    candidates.append(("drip_left_gravity(input_grid)", lambda g: drip_left_gravity(g)))
    for bg in range(1, 10):
        candidates.append((f"drip_down_gravity(input_grid, background={bg})", lambda g, bg=bg: drip_down_gravity(g, background=bg)))
        candidates.append((f"drip_up_gravity(input_grid, background={bg})", lambda g, bg=bg: drip_up_gravity(g, background=bg)))
        candidates.append((f"drip_right_gravity(input_grid, background={bg})", lambda g, bg=bg: drip_right_gravity(g, background=bg)))
        candidates.append((f"drip_left_gravity(input_grid, background={bg})", lambda g, bg=bg: drip_left_gravity(g, background=bg)))
    # border operations
    candidates.append(("expand_border_by_one(input_grid)", lambda g: expand_border_by_one(g)))
    candidates.append(("remove_border(input_grid)", lambda g: remove_border(g)))
    candidates.append(("fill_boundary_color(input_grid)", lambda g: fill_boundary_color(g)))
    for bc in range(1, 10):
        candidates.append((f"expand_border_by_one(input_grid, border_color={bc})", lambda g, bc=bc: expand_border_by_one(g, border_color=bc)))
        candidates.append((f"fill_boundary_color(input_grid, background={bc})", lambda g, bc=bc: fill_boundary_color(g, background=bc)))
    # count_nonzero_as_color_row: count non-background cells → [[color × count]]
    for bg in range(10):
        candidates.append((
            f"[[v for _ in range(sum(1 for r in input_grid for v in r if v!={bg})) for v in [next((c for r in input_grid for c in r if c!={bg}), {bg})]]",
            lambda g, bg=bg: [[next((c for r in g for c in r if c != bg), bg)] * sum(1 for r in g for c in r if c != bg)],
        ))
    # find_empty_in_both_halves: mark where both halves are background
    for mc in range(1, 10):
        candidates.append((
            f"find_empty_in_both_halves(input_grid, mark_color={mc})",
            lambda g, mc=mc: find_empty_in_both_halves(g, mark_color=mc),
        ))
    # extend_lines_to_cross: extend partial lines, mark intersection
    for ic in range(1, 10):
        candidates.append((
            f"extend_lines_to_cross(input_grid, intersection_color={ic})",
            lambda g, ic=ic: extend_lines_to_cross(g, intersection_color=ic),
        ))

    candidates.append(("extract_unique_color_panel(input_grid)", lambda g: extract_unique_color_panel(g)))

    unique_candidates = []
    seen_candidate_codes = set()
    for code, fn in candidates:
        if code in seen_candidate_codes:
            continue
        seen_candidate_codes.add(code)
        unique_candidates.append((code, fn))

    exact = []
    seen_exact = set()
    import time as _t
    import threading as _th
    _deadline = _t.time() + 4.0

    def _safe_eval(fn, train_pairs, per_candidate_timeout=0.3):
        result = [False]
        def _run():
            try:
                result[0] = all(fn(p['input']) == p['output'] for p in train_pairs)
            except Exception:
                pass
        thr = _th.Thread(target=_run, daemon=True)
        thr.start()
        thr.join(timeout=per_candidate_timeout)
        return result[0]

    for code, fn in unique_candidates:
        if _t.time() > _deadline:
            break
        try:
            if code not in seen_exact and _safe_eval(fn, train):
                exact.append(code)
                seen_exact.add(code)
        except Exception:
            pass
    def rank_exact(code):
        if code.startswith('[['):
            return (-3, len(code), code.count('('), code)
        if code == "[row[:] for row in input_grid]":
            return (-2, len(code), code.count('('), code)
        if code.startswith("remap_colors(") or code.startswith("make_grid("):
            return (-1, len(code), code.count('('), code)
        if any(token in code for token in ("topmost_object(", "bottommost_object(", "leftmost_object(", "rightmost_object(")):
            return (0, len(code), code.count('('), code)
        if code.startswith((
            "rotate_cw(",
            "rotate_ccw(",
            "rotate_180(",
            "transpose(",
            "flip_anti_diagonal(",
            "mirror_h(",
            "mirror_v(",
            "shift_grid(",
            "scale_grid(",
            "tile_grid(",
        )):
            return (0, len(code), code.count('('), code)
        if problem_class == "Topological Occlusion and Set Difference":
            priority = (
                1 if any(token in code for token in ("solve_occlusion", "best_pattern_repair", "repair_symmetry")) else
                2 if any(token in code for token in ("best_enclosed_fill", "remove_noise", "fill_from_mirror", "symmetrize")) else
                3 if any(token in code for token in ("remove_border", "remove_small", "keep_most_common_colors")) else
                4
            )
        elif problem_class == "Affine Transformations and Linear Algebra":
            priority = (
                1 if any(token in code for token in ("rotate_", "transpose", "flip_anti_diagonal", "shift_grid", "scale_grid", "tile_grid", "transform_object", "apply_gravity")) else
                2 if any(token in code for token in ("mirror_", "symmetrize_", "repair_symmetry")) else
                3
            )
        else:
            priority = (
                1 if any(token in code for token in ("union", "intersect", "difference", "overlay")) else
                2 if any(token in code for token in ("extract_color", "remove_color", "keep_most_common_colors")) else
                3
            )
        return (priority, len(code), code.count('('), code)
    exact.sort(key=rank_exact)
    return exact[:limit]

def analyze_task_deeply(task_data: dict) -> str:
    """Deep programmatic analysis to provide hints to the LLM."""
    train = task_data['train']
    analysis = []
    
    # 1. Formal Problem Classification (Failsafe wrapped)
    try:
        problem_class = classify_problem_class(train)
    except Exception:
        problem_class = "Topological Occlusion and Set Difference"
        
    analysis.append(f"- FORMAL PROBLEM CLASS: {problem_class}.")
    if problem_class == "Topological Occlusion and Set Difference":
        analysis.append("- Start with noise isolation and repair. Try `difference`, `remove_noise`, `solve_occlusion`, `best_pattern_repair`, `fill_holes`, `project`, or `raycast`.")
    elif problem_class == "Affine Transformations and Linear Algebra":
        analysis.append("- Start with exact spatial transforms. Try `rotate_cw`, `rotate_ccw`, `rotate_180`, `transpose`, `mirror_h`, `mirror_v`, `shift_grid`, `transform_object`, or `transform_objects_in_place`.")
    else:
        analysis.append("- Start with set operations and overlays. Try `union`, `intersect`, `difference`, `overlay`, `extract_color`, or `project_all`.")

    exact_programs = find_exact_programs(task_data, limit=3)
    if exact_programs:
        analysis.append("- EXACT PROGRAM CANDIDATES:")
        for code in exact_programs:
            analysis.append(f"  Code: `return {code}`")
        return '\n'.join(analysis)

    sizes_same = all(len(p['input']) == len(p['output']) and len(p['input'][0]) == len(p['output'][0]) for p in train)
    
    # 2. Base Exact Matches
    if sizes_same:
        # Check Identity
        if all(p['input'] == p['output'] for p in train):
            analysis.append("- IDENTITY detected. Code: `return [row[:] for row in input_grid]`")
            return '\n'.join(analysis)

        # Check Rotations/Flips using DSL
        rot_fns = [("rotate_cw", lambda g: [list(row) for row in zip(*g[::-1])]),
                   ("rotate_ccw", lambda g: [list(row) for row in zip(*g)][::-1]),
                   ("rotate_180", lambda g: [row[::-1] for row in g[::-1]]),
                   ("transpose", lambda g: [list(row) for row in zip(*g)]),
                   ("flip_anti_diagonal", lambda g: [row[::-1] for row in [list(row) for row in zip(*g)]]),
                   ("mirror_h", lambda g: [row[::-1] for row in g]),
                   ("mirror_v", lambda g: g[::-1])]
        for name, fn in rot_fns:
            if all(fn(p['input']) == p['output'] for p in train):
                analysis.append(f"- {name.upper()} transformation detected. Code: `return {name}(input_grid)`")
                return '\n'.join(analysis)

        shift_candidates = None
        for pair in train:
            pair_candidates = set()
            rows, cols = len(pair['input']), len(pair['input'][0])
            for dr in range(-rows + 1, rows):
                for dc in range(-cols + 1, cols):
                    if shift_grid(pair['input'], dr, dc) == pair['output']:
                        pair_candidates.add((dr, dc))
            shift_candidates = pair_candidates if shift_candidates is None else shift_candidates & pair_candidates
            if not shift_candidates:
                break
        if shift_candidates:
            dr, dc = sorted(shift_candidates)[0]
            analysis.append(f"- GLOBAL SHIFT detected. Code: `return shift_grid(input_grid, {dr}, {dc})`")
            return '\n'.join(analysis)

        # Check shift + color remap
        try:
            max_s = min(4, min(len(train[0]['input']), len(train[0]['input'][0])) - 1)
            for dr in range(-max_s, max_s + 1):
                for dc in range(-max_s, max_s + 1):
                    if dr == 0 and dc == 0:
                        continue
                    smap = {}
                    consistent = True
                    for pair in train:
                        shifted = shift_grid(pair['input'], dr, dc)
                        for in_row, out_row in zip(shifted, pair['output']):
                            for in_c, out_c in zip(in_row, out_row):
                                if in_c in smap and smap[in_c] != out_c:
                                    consistent = False
                                    break
                                smap[in_c] = out_c
                            if not consistent:
                                break
                        if not consistent:
                            break
                    if consistent and smap and any(k != v for k, v in smap.items()):
                        smap_repr = repr(dict(smap))
                        analysis.append(f"- SHIFT+REMAP detected. Code: `return remap_colors(shift_grid(input_grid, {dr}, {dc}), {smap_repr})`")
                        return '\n'.join(analysis)
        except Exception:
            pass

        # Check rotation + color remap
        try:
            rot_variants_a = [
                ("rotate_cw", lambda g: [list(row) for row in zip(*g[::-1])]),
                ("rotate_ccw", lambda g: [list(row) for row in zip(*g)][::-1]),
                ("rotate_180", lambda g: [row[::-1] for row in g[::-1]]),
                ("mirror_h", lambda g: [row[::-1] for row in g]),
                ("mirror_v", lambda g: g[::-1]),
            ]
            for rot_name, rot_fn in rot_variants_a:
                rmap = {}
                consistent = True
                for pair in train:
                    rotated = rot_fn(pair['input'])
                    if len(rotated) != len(pair['output']) or len(rotated[0]) != len(pair['output'][0]):
                        consistent = False
                        break
                    for in_row, out_row in zip(rotated, pair['output']):
                        for in_c, out_c in zip(in_row, out_row):
                            if in_c in rmap and rmap[in_c] != out_c:
                                consistent = False
                                break
                            rmap[in_c] = out_c
                        if not consistent:
                            break
                    if not consistent:
                        break
                if consistent and rmap and any(k != v for k, v in rmap.items()):
                    rmap_repr = repr(dict(rmap))
                    analysis.append(f"- ROT+REMAP detected. Code: `return remap_colors({rot_name}(input_grid), {rmap_repr})`")
                    return '\n'.join(analysis)
        except Exception:
            pass

        sym_fns = [("symmetrize_h", symmetrize_h), ("symmetrize_v", symmetrize_v)]
        for name, fn in sym_fns:
            if all(fn(p['input']) == p['output'] for p in train):
                analysis.append(f"- {name.upper()} completion detected. Code: `return {name}(input_grid)`")
                return '\n'.join(analysis)

        if all(len(set(cell for row in p['output'] for cell in row)) == 1 for p in train):
            fill_color = train[0]['output'][0][0]
            if all(p['output'][0][0] == fill_color for p in train):
                analysis.append(f"- UNIFORM FILL detected. Code: `return make_grid(len(input_grid), len(input_grid[0]), {fill_color})`")
                return '\n'.join(analysis)

        color_map = {}
        consistent = True
        for pair in train:
            for in_row, out_row in zip(pair['input'], pair['output']):
                for in_color, out_color in zip(in_row, out_row):
                    if in_color in color_map and color_map[in_color] != out_color:
                        consistent = False
                        break
                    color_map[in_color] = out_color
                if not consistent:
                    break
            if not consistent:
                break
        if consistent and color_map and any(k != v for k, v in color_map.items()):
            analysis.append(f"- GLOBAL COLOR REMAP detected. Mapping: {color_map}. Code: `return remap_colors(input_grid, {color_map})`")
            return '\n'.join(analysis)

        gravity_dirs = ["down", "up", "left", "right"]
        for direction in gravity_dirs:
            if all(apply_gravity(pair['input'], direction=direction) == pair['output'] for pair in train):
                analysis.append(f"- GRAVITY detected. Code: `return apply_gravity(input_grid, direction='{direction}')`")
                return '\n'.join(analysis)

        extraction_color = None
        extraction_match = True
        for pair in train:
            bg = detect_background_color(pair['input'])
            colors_in = non_background_colors(pair['input'], background=bg)
            colors_out = non_background_colors(pair['output'], background=bg)
            if len(colors_out) != 1:
                extraction_match = False
                break
            color = colors_out[0]
            if extraction_color is None:
                extraction_color = color
            if color != extraction_color or extract_color(pair['input'], color, background=bg) != pair['output']:
                extraction_match = False
                break
        if extraction_match and extraction_color is not None:
            analysis.append(f"- SINGLE-COLOR EXTRACTION detected. Code: `return extract_color(input_grid, {extraction_color}, background=detect_background_color(input_grid))`")
            return '\n'.join(analysis)

    scale_factors = set()
    scaling_matches = True
    for pair in train:
        in_rows, in_cols = len(pair['input']), len(pair['input'][0])
        out_rows, out_cols = len(pair['output']), len(pair['output'][0])
        if out_rows % in_rows != 0 or out_cols % in_cols != 0:
            scaling_matches = False
            break
        fr, fc = out_rows // in_rows, out_cols // in_cols
        scale_factors.add((fr, fc))
        if scale_grid(pair['input'], fr, fc) != pair['output']:
            scaling_matches = False
            break
    if scaling_matches and len(scale_factors) == 1:
        fr, fc = next(iter(scale_factors))
        analysis.append(f"- UNIFORM SCALING detected. Code: `return scale_grid(input_grid, {fr}, {fc})`")
        return '\n'.join(analysis)

    tile_factors = set()
    tiling_matches = True
    for pair in train:
        in_rows, in_cols = len(pair['input']), len(pair['input'][0])
        out_rows, out_cols = len(pair['output']), len(pair['output'][0])
        if out_rows % in_rows != 0 or out_cols % in_cols != 0:
            tiling_matches = False
            break
        fr, fc = out_rows // in_rows, out_cols // in_cols
        tile_factors.add((fr, fc))
        if tile_grid(pair['input'], fr, fc) != pair['output']:
            tiling_matches = False
            break
    if tiling_matches and len(tile_factors) == 1:
        fr, fc = next(iter(tile_factors))
        analysis.append(f"- UNIFORM TILING detected. Code: `return tile_grid(input_grid, {fr}, {fc})`")
        return '\n'.join(analysis)

    # 3. Advanced High-Level Helper Matches
    advanced_candidates = [
        ("crop_foreground", lambda g: crop_foreground(g)),
        ("largest_object_grid", lambda g: largest_object_grid(g, diag=True, crop_result=True)),
        ("largest_shape_grid", lambda g: largest_shape_grid(g, diag=True, crop_result=True)),
        ("main_shape_grid", lambda g: main_shape_grid(g, diag=True, crop_result=True)),
        ("best_pattern_repair", lambda g: best_pattern_repair(g, crop_result=True)),
        ("solve_occlusion", lambda g: solve_occlusion(g, crop_result=True))
    ]
    if sizes_same:
        advanced_candidates.extend([
            ("foreground_in_place", lambda g: foreground_in_place(g)),
            ("best_pattern_repair_in_place", lambda g: best_pattern_repair_in_place(g)),
            ("solve_occlusion_in_place", lambda g: solve_occlusion_in_place(g))
        ])
        
    for name, fn in advanced_candidates:
        try:
            if all(fn(p['input']) == p['output'] for p in train):
                analysis.append(f"- DIRECT HELPER MATCH detected. Code: `return {name}(input_grid)`")
                return '\n'.join(analysis)
        except Exception:
            pass

    # 4. Symmetry Fallback
    in_symmetry = [max(symmetry_score_h(p['input']), symmetry_score_v(p['input'])) for p in train]
    out_symmetry = [max(symmetry_score_h(p['output']), symmetry_score_v(p['output'])) for p in train]
    if all(out_score >= in_score for in_score, out_score in zip(in_symmetry, out_symmetry)):
        analysis.append("- POSSIBLE OCCLUSION / PATTERN REPAIR: the outputs look at least as symmetric as the inputs. Try `solve_occlusion(input_grid)` or `best_pattern_repair(input_grid)`.")

    return '\n'.join(analysis)

def select_relevant_helpers(task_data: dict, analysis: str) -> list[str]:
    train = task_data['train']
    try:
        problem_class = classify_problem_class(train)
    except Exception:
        problem_class = "Topological Occlusion and Set Difference"

    helper_order = [
        "detect_background_color",
        "dominant_non_background_color",
        "non_background_colors",
        "find_cells",
        "get_bbox",
        "get_bbox_of_color",
        "get_objects",
        "get_objects_by_color",
        "get_shapes",
        "objects_by_color",
        "object_colors",
        "object_color_counts",
        "object_dimensions",
        "flood_fill",
        "crop",
        "crop_foreground",
        "crop_object",
        "object_to_grid",
        "fit_grid_to_size",
        "foreground_in_place",
        "overlay",
        "union",
        "intersect",
        "difference",
        "rotate_cw",
        "rotate_ccw",
        "rotate_180",
        "transpose",
        "flip_anti_diagonal",
        "mirror_h",
        "mirror_v",
        "symmetrize_h",
        "symmetrize_v",
        "fill_from_mirror_h",
        "fill_from_mirror_v",
        "repair_symmetry",
        "best_axis_completion",
        "shift_grid",
        "move_object",
        "transform_object",
        "transform_objects_in_place",
        "scale_grid",
        "tile_grid",
        "apply_gravity",
        "project",
        "project_all",
        "raycast",
        "remap_colors",
        "extract_color",
        "remove_color",
        "remove_colors",
        "remove_noise",
        "infer_noise_color",
        "infer_noise_colors",
        "remove_small_objects",
        "remove_small_shapes",
        "remove_border_objects_by_size",
        "remove_border_shapes_by_size",
        "keep_most_common_colors",
        "fill_enclosed_background",
        "best_enclosed_fill",
        "fill_holes",
        "repair_holes",
        "filter_by_color",
        "filter_by_size",
        "filter_by_dimensions",
        "filter_by_position",
        "sort_objects",
        "manhattan_distance",
        "overlaps",
        "touching",
        "same_shape",
        "same_dimensions",
        "same_color",
        "is_square_object",
        "is_line_object",
        "is_rectangle_object",
        "touches_border",
        "border_objects",
        "interior_objects",
        "count_objects",
        "topmost_object",
        "bottommost_object",
        "leftmost_object",
        "rightmost_object",
        "nearest_object",
        "farthest_object",
        "extract_main_shape",
        "repair_main_shape_symmetry",
        "repair_main_shape_in_place",
        "denoise_and_repair_symmetry",
        "best_symmetry_repair",
        "best_pattern_repair",
        "best_pattern_repair_in_place",
        "solve_occlusion",
        "solve_occlusion_in_place",
        "largest_object_grid",
        "largest_object_in_place",
        "largest_shape_grid",
        "largest_shape_in_place",
        "main_shape_grid",
        "main_shape_in_place",
        "make_grid",
        "fill_l_shape_corners",
        "kronecker_block_diagonal",
        "count_special_colors",
        "repair_periodic_pattern",
        "assemble_l_shapes",
        "fill_enclosed_by_parity",
        "find_unique_quadrant",
        "reflect_2x2_block_to_corners",
        "fill_columns_above_marker",
        "draw_borders_around_pairs",
        "mark_uniform_rows",
        "find_unique_colored_quadrant",
        "and_halves_by_separator",
        "drop_to_floor",
        "tile_4way_symmetric",
        "stack_mirror_v",
        "fill_with_most_common",
        "find_minimal_tile",
        "mark_singleton_cells",
        "tile_with_mirror_h",
        "count_cells_to_row",
        "draw_x_from_zero",
        "draw_diagonals_from_point",
        "draw_lines_from_point",
        "draw_full_cross_from_point",
        "extract_neighborhood_of_marker",
        "apply_halo_map",
        "stripe_right_from_points",
        "crop_most_dense_object",
        "fill_rectangles_between_corners",
        "fill_rectangle_interiors_ranked",
        "fill_bbox_holes",
        "attract_cells_to_unique_anchor",
        "reflect_shape_across_separator",
        "stamp_shape_at_marker",
        "reverse_concentric_rings",
        "fractal_tile_nonzero",
        "fill_regions_with_dominant_color",
        "float_up_objects_by_height",
        "find_empty_in_both_halves",
        "extend_lines_to_cross",
        "fill_gaps_between_endpoints",
        "upscale_grid",
        "drip_down_columns",
        "nor_halves_by_separator",
        "recolor_non_singletons",
        "fill_diagonal_tile",
        "crop_foreground",
        "tile_grid",
    ]

    core = {
        "detect_background_color", "non_background_colors", "get_objects", "get_shapes",
        "find_cells", "get_bbox", "crop", "crop_foreground", "overlay", "make_grid"
    }
    if problem_class == "Topological Occlusion and Set Difference":
        selected = core | {
            "difference", "remove_color", "remove_colors", "remove_noise", "infer_noise_color",
            "infer_noise_colors", "fill_enclosed_background", "best_enclosed_fill", "fill_holes",
            "repair_holes", "project", "project_all", "raycast", "repair_symmetry",
            "best_axis_completion", "best_symmetry_repair", "best_pattern_repair",
            "best_pattern_repair_in_place", "solve_occlusion", "solve_occlusion_in_place",
            "largest_shape_grid", "main_shape_grid", "repair_main_shape_symmetry",
        }
    elif problem_class == "Affine Transformations and Linear Algebra":
        selected = core | {
            "rotate_cw", "rotate_ccw", "rotate_180", "transpose", "flip_anti_diagonal",
            "mirror_h", "mirror_v", "shift_grid", "transform_object", "transform_objects_in_place",
            "scale_grid", "tile_grid", "fit_grid_to_size", "move_object", "apply_gravity",
        }
    else:
        selected = core | {
            "union", "intersect", "difference", "overlay", "extract_color", "remove_color",
            "project", "project_all", "keep_most_common_colors", "filter_by_color",
            "objects_by_color", "largest_object_grid", "largest_shape_grid", "main_shape_grid",
        }

    if "DIRECT HELPER MATCH detected" in analysis:
        selected |= {
            "crop_foreground", "largest_object_grid", "largest_shape_grid", "main_shape_grid",
            "best_pattern_repair", "best_pattern_repair_in_place", "solve_occlusion",
            "solve_occlusion_in_place", "foreground_in_place",
        }
    if "EXACT PROGRAM CANDIDATES:" in analysis:
        selected |= {
            "crop_foreground", "largest_object_grid", "largest_shape_grid", "main_shape_grid",
            "best_pattern_repair", "solve_occlusion", "remove_noise", "best_enclosed_fill",
            "keep_most_common_colors", "remove_small_objects", "remove_small_shapes",
            "foreground_in_place", "best_pattern_repair_in_place", "solve_occlusion_in_place",
            "extract_color", "remove_color", "remap_colors", "apply_gravity",
            "rotate_cw", "rotate_ccw", "rotate_180", "transpose", "flip_anti_diagonal",
            "mirror_h", "mirror_v", "shift_grid", "scale_grid", "tile_grid",
            "symmetrize_h", "symmetrize_v",
            "fill_from_mirror_h", "fill_from_mirror_v", "repair_symmetry",
            "remove_border_objects_by_size", "remove_border_shapes_by_size",
            "largest_object_in_place", "largest_shape_in_place", "main_shape_in_place",
            "repair_main_shape_in_place", "repair_main_shape_symmetry",
            "dominant_non_background_color", "get_objects_by_color", "crop_object",
            "topmost_object", "bottommost_object", "leftmost_object", "rightmost_object",
        }
    if "GLOBAL COLOR REMAP detected" in analysis or "SINGLE-COLOR EXTRACTION detected" in analysis:
        selected |= {"remap_colors", "extract_color", "remove_color", "remove_colors"}
    if "GRAVITY detected" in analysis:
        selected |= {"apply_gravity"}
    if "UNIFORM SCALING detected" in analysis:
        selected |= {"scale_grid"}
    if "UNIFORM TILING detected" in analysis:
        selected |= {"tile_grid"}
    if "GLOBAL SHIFT detected" in analysis:
        selected |= {"shift_grid"}
    if "SYMMETRIZE_H" in analysis or "SYMMETRIZE_V" in analysis or "OCCLUSION" in analysis:
        selected |= {"symmetrize_h", "symmetrize_v", "fill_from_mirror_h", "fill_from_mirror_v"}

    return [name for name in helper_order if name in selected]

def build_prompt(task_data: dict) -> str:
    analysis = analyze_task_deeply(task_data)
    exact_programs = find_exact_programs(task_data, limit=3)
    helper_names = select_relevant_helpers(task_data, analysis)
    if exact_programs:
        exact_helper_order = [
            "rotate_cw", "rotate_ccw", "rotate_180", "transpose", "flip_anti_diagonal",
            "mirror_h", "mirror_v", "shift_grid", "scale_grid", "tile_grid",
            "remap_colors", "extract_color", "remove_color", "remove_noise",
            "dominant_non_background_color", "get_objects_by_color", "crop_object",
            "best_enclosed_fill", "solve_occlusion", "best_pattern_repair",
            "repair_symmetry", "symmetrize_h", "symmetrize_v",
            "fill_from_mirror_h", "fill_from_mirror_v",
            "keep_most_common_colors", "remove_small_objects", "remove_small_shapes",
            "remove_border_objects_by_size", "remove_border_shapes_by_size",
            "largest_object_grid", "largest_shape_grid", "main_shape_grid",
            "largest_object_in_place", "largest_shape_in_place", "main_shape_in_place",
            "repair_main_shape_in_place", "repair_main_shape_symmetry",
            "foreground_in_place", "best_pattern_repair_in_place", "solve_occlusion_in_place",
            "apply_gravity", "make_grid",
        ]
        used_helpers = []
        for helper in exact_helper_order:
            if any(f"{helper}(" in code for code in exact_programs):
                used_helpers.append(helper)
        helper_names = used_helpers + [name for name in helper_names if name not in used_helpers]
        helper_names = helper_names[:24]
    prompt = "ARC puzzle: find the transformation rule. Cells 0-9.\n\n"
    for i, pair in enumerate(task_data['train']):
        prompt += f"Ex{i+1} In:\n{grid_to_str(pair['input'])}\nOut:\n{grid_to_str(pair['output'])}\n\n"
    
    prompt += f"HINTS:\n{analysis}\n\n"
    if len(exact_programs) == 1:
        prompt += f"VERIFIED EXACT CODE: `return {exact_programs[0]}`. Use it unchanged unless you can prove it fails a training example.\n\n"
    elif len(exact_programs) > 1:
        prompt += "VERIFIED EXACT CANDIDATES:\n"
        for code in exact_programs:
            prompt += f"- `return {code}`\n"
        prompt += "Prefer one of those verified candidates if it matches all training examples.\n\n"
    prompt += "Prefer the shortest correct rule. If an exact candidate already fits all training examples, use it unchanged. If output size changes, compute the new grid explicitly. Test your rule mentally against every training pair before answering. Do not call helpers that are not listed.\n\n"
    prompt += "Most Relevant Helpers: " + ", ".join(helper_names) + ".\n\n"
    prompt += "Output ONLY a python code block for `def transform(input_grid):`. No explanation.\n\n```python\n"
    return prompt

def run_with_timeout(fn, args, timeout_sec=5):
    result, error = [None], [None]
    def target():
        try: result[0] = fn(*args)
        except Exception as e: error[0] = e
    t = threading.Thread(target=target)
    t.daemon = True
    t.start()
    t.join(timeout_sec)
    if t.is_alive(): raise TimeoutError("Infinite loop detected")
    if error[0]: raise error[0]
    return result[0]

def try_code_on_task(code: str, task_data: dict, evaluate_on_test=False):
    """Returns (passed, failures). Evaluates on Train or Test data."""
    namespace = dict(HELPER_FUNCTIONS)
    failures = []
    
    # Switch between the train data (for hints) and test data (for the final grade)
    pairs_to_test = task_data.get('test', []) if evaluate_on_test else task_data.get('train', [])
    
    try:
        # Load the DSL + Qwen's code
        full_code = HELPER_CODE_PREFIX + "\n" + code
        exec(full_code, namespace)
        transform_fn = namespace.get("transform")
        
        if not transform_fn:
            return False, [(pairs_to_test[0]['input'], pairs_to_test[0]['output'], None, "No 'transform' function found")]
            
        for pair in pairs_to_test:
            try:
                prediction = run_with_timeout(transform_fn, (pair['input'],), timeout_sec=5)
                # Ensure the prediction is safely formatted as a list of lists
                pred_list = [list(row) for row in prediction]
                out_list = [list(row) for row in pair['output']]
                if pred_list != out_list:
                    failures.append((pair['input'], pair['output'], prediction, None))
            except Exception as e:
                failures.append((pair['input'], pair['output'], None, str(e)))
                
    except Exception as e:
        if pairs_to_test:
            failures.append((pairs_to_test[0]['input'], pairs_to_test[0]['output'], None, str(e)))
        else:
            failures.append(("", "", None, str(e)))
            
    return len(failures) == 0, failures


if __name__ == "__main__":
    evaluate_arc_neurosymbolic()


def find_odd_quadrant(grid):
    """Divide grid by all-zero row and col into 4 quadrants. Return the unique (non-repeating) quadrant."""
    rows, cols = len(grid), len(grid[0])
    div_row = next(r for r in range(rows) if all(grid[r][c] == 0 for c in range(cols)))
    div_col = next(c for c in range(cols) if all(grid[r][c] == 0 for r in range(rows)))
    q = [
        [row[:div_col] for row in grid[:div_row]],
        [row[div_col+1:] for row in grid[:div_row]],
        [row[:div_col] for row in grid[div_row+1:]],
        [row[div_col+1:] for row in grid[div_row+1:]],
    ]
    from collections import Counter
    ser = [str(x) for x in q]
    cnt = Counter(ser)
    for i, s in enumerate(ser):
        if cnt[s] == 1:
            return q[i]
    return q[0]


def mirror_rev_concat_tile_symmetric(grid):
    """For each row: rev(row)+row. Vertically: reversed+original+reversed (3x height)."""
    h = [row[::-1] + row[:] for row in grid]
    return list(reversed(h)) + h + list(reversed(h))


def extend_colors_to_divider(grid, divider=5, toward=2, away=1):
    """5-row divides grid. 'toward' color extends toward divider; 'away' color extends away."""
    rows, cols = len(grid), len(grid[0])
    out = [list(row) for row in grid]
    div_row = next(r for r in range(rows) if grid[r][0] == divider)
    for c in range(cols):
        for r in range(div_row):
            v = grid[r][c]
            if v == toward:
                for rr in range(r, div_row):
                    if out[rr][c] == 0:
                        out[rr][c] = v
            elif v == away:
                for rr in range(r, -1, -1):
                    if out[rr][c] == 0:
                        out[rr][c] = v
        for r in range(div_row + 1, rows):
            v = grid[r][c]
            if v == toward:
                for rr in range(r, div_row, -1):
                    if out[rr][c] == 0:
                        out[rr][c] = v
            elif v == away:
                for rr in range(r, rows):
                    if out[rr][c] == 0:
                        out[rr][c] = v
    return out


def fractal_self_similar_3x3(grid):
    """Place 3x3 shape at each block position corresponding to its own non-zero cells, in a 9x9 output."""
    cells = [(r, c, grid[r][c]) for r in range(len(grid)) for c in range(len(grid[0])) if grid[r][c] != 0]
    r_min = min(r for r, c, v in cells)
    c_min = min(c for r, c, v in cells)
    shape = [[grid[r_min + i][c_min + j] for j in range(3)] for i in range(3)]
    out = [[0] * 9 for _ in range(9)]
    for bi in range(3):
        for bj in range(3):
            if shape[bi][bj] != 0:
                for si in range(3):
                    for sj in range(3):
                        out[bi * 3 + si][bj * 3 + sj] = shape[si][sj]
    return out


def expand_rows_using_template_pattern(grid, background=0):
    """Full-width template row defines color pattern. Partial rows expand using mapped colors from template."""
    rows, cols = len(grid), len(grid[0])
    out = [list(row) for row in grid]
    template_row = next((grid[r] for r in range(rows) if all(grid[r][c] != background for c in range(cols))), None)
    if template_row is None:
        return out
    t_colors = []
    seen = set()
    for v in template_row:
        if v not in seen:
            t_colors.append(v)
            seen.add(v)
    for r in range(rows):
        nz = [grid[r][c] for c in range(cols) if grid[r][c] != background]
        if not nz or len(nz) == cols:
            continue
        p_colors = []
        seen2 = set()
        for v in nz:
            if v not in seen2:
                p_colors.append(v)
                seen2.add(v)
        cmap = {tc: p_colors[i] for i, tc in enumerate(t_colors) if i < len(p_colors)}
        for c in range(cols):
            tv = template_row[c]
            if tv in cmap:
                out[r][c] = cmap[tv]
    return out


def fill_sections_with_rotations(grid, divider=5):
    """Grid split by two 5-divider columns. Section1=90CW of section0, section2=180 of section0."""
    rows, cols = len(grid), len(grid[0])
    div_cols = [c for c in range(cols) if all(grid[r][c] == divider for r in range(rows))]
    d1, d2 = div_cols[0], div_cols[1]
    s0 = [[grid[r][c] for c in range(d1)] for r in range(rows)]
    R, C = len(s0), len(s0[0])
    s1 = [[s0[R - 1 - c][r] for c in range(C)] for r in range(R)]
    s2 = [row[::-1] for row in reversed(s0)]
    out = [list(row) for row in grid]
    for r in range(rows):
        for j in range(d2 - d1 - 1):
            out[r][d1 + 1 + j] = s1[r][j]
        for j in range(cols - d2 - 1):
            out[r][d2 + 1 + j] = s2[r][j]
    return out


def extract_blob_with_most_twos(grid, blob_color=1, marker=2, background=0):
    """Find all connected blobs of 1s+2s. Return bounding box of the blob with the most 2s."""
    from collections import deque
    rows, cols = len(grid), len(grid[0])
    visited = [[False] * cols for _ in range(rows)]
    blobs = []
    for sr in range(rows):
        for sc in range(cols):
            if grid[sr][sc] in (blob_color, marker) and not visited[sr][sc]:
                q = deque([(sr, sc)])
                visited[sr][sc] = True
                cells = []
                while q:
                    r, c = q.popleft()
                    cells.append((r, c))
                    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc] and grid[nr][nc] in (blob_color, marker):
                            visited[nr][nc] = True
                            q.append((nr, nc))
                blobs.append(cells)
    best = max(blobs, key=lambda cells: sum(1 for r, c in cells if grid[r][c] == marker))
    rmin = min(r for r, c in best)
    rmax = max(r for r, c in best)
    cmin = min(c for r, c in best)
    cmax = max(c for r, c in best)
    return [[grid[r][c] for c in range(cmin, cmax + 1)] for r in range(rmin, rmax + 1)]


def copy_shape_centered_at_marker_5(grid, marker=5, background=0):
    """Find shape (non-bg non-marker). Place copy centered at marker-5. Remove marker from output."""
    rows, cols = len(grid), len(grid[0])
    out = [list(row) for row in grid]
    mr, mc = next((r, c) for r in range(rows) for c in range(cols) if grid[r][c] == marker)
    out[mr][mc] = background
    shape_cells = [(r, c, grid[r][c]) for r in range(rows) for c in range(cols)
                   if grid[r][c] != background and grid[r][c] != marker]
    if not shape_cells:
        return out
    r_min = min(r for r, c, v in shape_cells)
    r_max = max(r for r, c, v in shape_cells)
    c_min = min(c for r, c, v in shape_cells)
    c_max = max(c for r, c, v in shape_cells)
    cr = (r_min + r_max) // 2
    cc = (c_min + c_max) // 2
    dr, dc = mr - cr, mc - cc
    for r, c, v in shape_cells:
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            out[nr][nc] = v
    return out


def replace_minority_with_5(grid, fill_color=5):
    """Replace all non-dominant colors with 5. Dominant = most frequent color."""
    from collections import Counter
    flat = [v for row in grid for v in row]
    dominant = Counter(flat).most_common(1)[0][0]
    return [[v if v == dominant else fill_color for v in row] for row in grid]


def tile_nonzero_count_copies(grid, background=0):
    """Count N=non-zero cells, Z=zero cells. Output Z*3 x Z*3 with first N blocks filled by input."""
    rows, cols = len(grid), len(grid[0])
    n = sum(1 for row in grid for v in row if v != background)
    z = rows * cols - n
    out_size = z * cols
    out = [[background] * out_size for _ in range(out_size)]
    filled = 0
    for bi in range(z):
        for bj in range(z):
            if filled >= n:
                break
            for ri in range(rows):
                for ci in range(cols):
                    out[bi * rows + ri][bj * cols + ci] = grid[ri][ci]
            filled += 1
        if filled >= n:
            break
    return out


def mark_shared_empty_as_2(grid, fill_color=2, background=0):
    """Split grid in half vertically. Mark cells where BOTH halves are background with fill_color."""
    rows, cols = len(grid), len(grid[0])
    mid = rows // 2
    top, bot = grid[:mid], grid[mid:]
    return [[fill_color if top[r][c] == background and bot[r][c] == background else background
             for c in range(cols)] for r in range(mid)]


def mark_xor_halves_with_3(grid, divider=4, fill_color=3, background=0):
    """Split by row of 4s. Mark cells where EXACTLY ONE half is non-background with fill_color."""
    rows, cols = len(grid), len(grid[0])
    div_row = next(r for r in range(rows) if all(grid[r][c] == divider for c in range(cols)))
    top, bot = grid[:div_row], grid[div_row + 1:]
    out = []
    for r in range(len(top)):
        row = []
        for c in range(cols):
            t = top[r][c] != background
            b = bot[r][c] != background
            row.append(fill_color if (t ^ b) else background)
        out.append(row)
    return out


def extend_periodic_rows_double_width(grid, background=0):
    """Detect repeating period of each non-zero row, extend to double width."""
    rows, cols = len(grid), len(grid[0])
    out = []
    for row in grid:
        if all(v == background for v in row):
            out.append([background] * (2 * cols))
            continue
        period = 1
        while period <= cols:
            if all(row[i] == row[i % period] for i in range(cols)):
                break
            period += 1
        out.append([row[i % period] for i in range(2 * cols)])
    return out


def color_histogram_columns(grid, background=0):
    """Sort non-bg colors by count descending. Output height=max_count, each column = one color filled top-down."""
    from collections import Counter
    flat = [v for row in grid for v in row if v != background]
    counts = Counter(flat)
    if not counts:
        return [[background]]
    sorted_colors = sorted(counts.keys(), key=lambda v: (-counts[v], v))
    max_count = counts[sorted_colors[0]]
    out = []
    for r in range(max_count):
        row = [color if r < counts[color] else background for color in sorted_colors]
        out.append(row)
    return out


def decode_5block_pattern(grid, background=0):
    """Decode 4x4 blocks of 5s with hole positions. Each block maps to a color based on zero pattern."""
    rows, cols = len(grid), len(grid[0])
    div_cols = [c for c in range(cols) if all(grid[r][c] == background for r in range(rows))]
    sections = []
    prev = 0
    for dc in div_cols:
        sections.append(list(range(prev, dc)))
        prev = dc + 1
    sections.append(list(range(prev, cols)))
    color_map = {
        frozenset(): 2,
        frozenset([(1, 1), (1, 2), (2, 1), (2, 2)]): 8,
        frozenset([(1, 0), (2, 0), (1, 3), (2, 3)]): 3,
        frozenset([(2, 1), (2, 2), (3, 1), (3, 2)]): 4,
        frozenset([(0, 1), (0, 2), (1, 1), (1, 2)]): 5,
    }
    colors = []
    for sec in sections:
        block = [[grid[r][c] for c in sec] for r in range(rows)]
        zeros = frozenset((r, c) for r in range(len(block)) for c in range(len(block[0])) if block[r][c] == background)
        colors.append(color_map.get(zeros, 0))
    return [[c] * len(colors) for c in colors]


def fill_opposite_corners_from_2x2(grid, background=0):
    """Find 2x2 non-zero block. Fill each corner region with the diagonally opposite block value."""
    rows, cols = len(grid), len(grid[0])
    for r in range(rows - 1):
        for c in range(cols - 1):
            if all(grid[r + dr][c + dc] != background for dr in range(2) for dc in range(2)):
                tl = grid[r][c]; tr = grid[r][c + 1]
                bl = grid[r + 1][c]; br = grid[r + 1][c + 1]
                out = [list(row) for row in grid]
                bsr, bsc = 2, 2
                for ri in range(min(bsr, r)):
                    for ci in range(min(bsc, c)):
                        out[ri][ci] = br
                for ri in range(min(bsr, r)):
                    for ci in range(min(bsc, cols - c - bsc)):
                        out[ri][c + bsc + ci] = bl
                for ri in range(min(bsr, rows - r - bsr)):
                    for ci in range(min(bsc, c)):
                        out[r + bsr + ri][ci] = tr
                for ri in range(min(bsr, rows - r - bsr)):
                    for ci in range(min(bsc, cols - c - bsc)):
                        out[r + bsr + ri][c + bsc + ci] = tl
                return out
    return grid


def extend_dots_l_right_down(grid, background=0):
    """Each non-zero dot extends right to end of row, then down from right edge until next dot's row."""
    rows, cols = len(grid), len(grid[0])
    out = [list(row) for row in grid]
    dots = sorted([(r, c, grid[r][c]) for r in range(rows) for c in range(cols) if grid[r][c] != background], key=lambda x: x[0])
    for i, (r, c, v) in enumerate(dots):
        for cc in range(c, cols):
            out[r][cc] = v
        next_r = dots[i + 1][0] if i + 1 < len(dots) else rows
        for rr in range(r, next_r):
            out[rr][cols - 1] = v
    return out


def swap_color_pairs_arc(grid):
    """Swap color pairs: 1↔5, 2↔6, 3↔4, 8↔9. Other values unchanged."""
    mapping = {1: 5, 2: 6, 3: 4, 4: 3, 5: 1, 6: 2, 8: 9, 9: 8}
    return [[mapping.get(v, v) for v in row] for row in grid]


def mark_uniform_rows_with_5(grid, fill=5, background=0):
    """Replace rows where all cells are the same value with fill_color; others become background."""
    rows, cols = len(grid), len(grid[0])
    return [[fill if len(set(grid[r])) == 1 else background for _ in range(cols)] for r in range(rows)]


def color_rows_by_5_position(grid, marker=5):
    """Each row has one marker-5. Map its column to a color: col0→2, col1→4, col2→3."""
    col_to_color = {0: 2, 1: 4, 2: 3}
    rows, cols = len(grid), len(grid[0])
    out = []
    for r in range(rows):
        mc = next((c for c in range(cols) if grid[r][c] == marker), None)
        color = col_to_color.get(mc, 0) if mc is not None else 0
        out.append([color] * cols)
    return out


def place_diagonal_markers_around_2(grid, marker=2, background=0):
    """For each marker-2 cell, place 3(UL), 6(UR), 8(BL), 7(BR) at diagonal neighbors."""
    rows, cols = len(grid), len(grid[0])
    out = [[background] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == marker:
                for dr, dc, val in [(-1, -1, 3), (-1, 1, 6), (1, -1, 8), (1, 1, 7)]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols:
                        out[nr][nc] = val
    return out


def replace_7_with_5(grid, old=7, new=5):
    """Replace all occurrences of 7 with 5."""
    return [[new if v == old else v for v in row] for row in grid]


def extend_values_downward(grid, background=0):
    """Each non-background value fills all background cells below it in the same column."""
    rows, cols = len(grid), len(grid[0])
    out = [list(row) for row in grid]
    for c in range(cols):
        last = background
        for r in range(rows):
            if grid[r][c] != background:
                last = grid[r][c]
            elif last != background:
                out[r][c] = last
    return out


def create_checkerboard_from_two_rows(grid):
    """Two constant-color rows → checkerboard pattern. cell(r,c) = row0_color if (r+c) even, else row1_color."""
    a, b = grid[0][0], grid[1][0]
    rows, cols = len(grid), len(grid[0])
    return [[(a if (r + c) % 2 == 0 else b) for c in range(cols)] for r in range(rows)]


def rotate_90ccw(grid):
    """Rotate grid 90 degrees counter-clockwise: new[r][c] = old[c][cols-1-r]."""
    rows, cols = len(grid), len(grid[0])
    return [[grid[c][cols - 1 - r] for c in range(cols)] for r in range(rows)]


def classify_3x3_nonzero_pattern(grid):
    """Classify 3x3 grid by its non-zero cell pattern into a category code (1-6)."""
    pat = tuple(1 if v != 0 else 0 for row in grid for v in row)
    lookup = {
        (1, 1, 0, 1, 0, 1, 0, 1, 0): 1,
        (1, 0, 1, 0, 1, 0, 1, 0, 1): 2,
        (0, 1, 1, 0, 1, 1, 1, 0, 0): 3,
        (0, 1, 0, 1, 1, 1, 0, 1, 0): 6,
    }
    return [[lookup.get(pat, 0)]]


def mark_union_of_halves_with_6(grid, fill_color=6, background=0):
    """Split grid into left and right halves. Mark cells where EITHER half is non-background with 6."""
    rows, cols = len(grid), len(grid[0])
    half = cols // 2
    left = [[grid[r][c] for c in range(half)] for r in range(rows)]
    right = [[grid[r][c] for c in range(half, cols)] for r in range(rows)]
    return [[fill_color if left[r][c] != background or right[r][c] != background else background
             for c in range(half)] for r in range(rows)]


def count_cells_output_as_row(grid, background=0):
    """Count non-background cells. Output a single row of that count filled with the cell color."""
    cells = [(r, c, grid[r][c]) for r in range(len(grid)) for c in range(len(grid[0])) if grid[r][c] != background]
    if not cells:
        return [[0]]
    v = cells[0][2]
    return [[v] * len(cells)]


def concat_reversed_and_grid(grid):
    """Concatenate vertically: reversed(grid) + grid (double height)."""
    return list(reversed(grid)) + [list(row) for row in grid]


def replace_connected_3s_with_8(grid, target=3, replacement=8, background=0):
    """Replace 3s that are part of a connected blob (size > 1) with 8. Isolated 3s remain 3."""
    from collections import deque
    rows, cols = len(grid), len(grid[0])
    out = [list(row) for row in grid]
    visited = [[False] * cols for _ in range(rows)]
    for sr in range(rows):
        for sc in range(cols):
            if grid[sr][sc] == target and not visited[sr][sc]:
                q = deque([(sr, sc)])
                visited[sr][sc] = True
                blob = [(sr, sc)]
                while q:
                    r, c = q.popleft()
                    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc] and grid[nr][nc] == target:
                            visited[nr][nc] = True
                            q.append((nr, nc))
                            blob.append((nr, nc))
                if len(blob) > 1:
                    for r, c in blob:
                        out[r][c] = replacement
    return out


def replace_isolated_2s_with_1(grid, target=2, replacement=1, background=0):
    """Replace 2s that have no 4-connected neighbors with the same value with 1."""
    rows, cols = len(grid), len(grid[0])
    out = [list(row) for row in grid]
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == target:
                neighbors = [(r + dr, c + dc) for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]
                             if 0 <= r + dr < rows and 0 <= c + dc < cols and grid[r + dr][c + dc] == target]
                if not neighbors:
                    out[r][c] = replacement
    return out


def fractal_tile_self_3x3(grid):
    """Tile the 3x3 input fractally: place copy at each block position where grid[bi][bj]!=0."""
    rows, cols = len(grid), len(grid[0])
    out = [[0] * (cols * 3) for _ in range(rows * 3)]
    for bi in range(rows):
        for bj in range(cols):
            if grid[bi][bj] != 0:
                for si in range(rows):
                    for sj in range(cols):
                        out[bi * rows + si][bj * cols + sj] = grid[si][sj]
    return out


def fractal_tile_at_value_2(grid, marker=2, background=0):
    """Tile the input fractally: place copy at each block position where grid[bi][bj]==marker (default 2)."""
    rows, cols = len(grid), len(grid[0])
    out = [[background] * (cols * 3) for _ in range(rows * 3)]
    for bi in range(rows):
        for bj in range(cols):
            if grid[bi][bj] == marker:
                for si in range(rows):
                    for sj in range(cols):
                        out[bi * rows + si][bj * cols + sj] = grid[si][sj]
    return out


def tile_grid_at_dominant_color_positions(grid, background=0):
    """Place copy of 3x3 input at each block (bi,bj) in 9x9 output where grid[bi][bj]==most common value."""
    from collections import Counter
    rows, cols = len(grid), len(grid[0])
    flat = [v for row in grid for v in row]
    dominant = Counter(flat).most_common(1)[0][0]
    out = [[background] * (cols * rows) for _ in range(rows * cols)]
    for bi in range(rows):
        for bj in range(cols):
            if grid[bi][bj] == dominant:
                for si in range(rows):
                    for sj in range(cols):
                        out[bi * rows + si][bj * cols + sj] = grid[si][sj]
    return out


def scale_grid_by_nonzero_count(grid, background=0):
    """Scale each cell to NxN block where N=number of non-zero cells. Non-zero cells become solid color blocks."""
    rows, cols = len(grid), len(grid[0])
    n = sum(1 for row in grid for v in row if v != background)
    out = [[background] * (cols * n) for _ in range(rows * n)]
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            if v != background:
                for dr in range(n):
                    for dc in range(n):
                        out[r * n + dr][c * n + dc] = v
    return out


def scale_grid_by_unique_color_count(grid, background=0):
    """Scale each cell to NxN block where N=number of unique non-zero colors."""
    from collections import Counter
    rows, cols = len(grid), len(grid[0])
    unique = len(set(v for row in grid for v in row if v != background))
    n = unique
    out = [[background] * (cols * n) for _ in range(rows * n)]
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            if v != background:
                for dr in range(n):
                    for dc in range(n):
                        out[r * n + dr][c * n + dc] = v
    return out


def scale_grid_by_2(grid, background=0):
    """Scale each cell to 2x2 block (pixel doubling)."""
    rows, cols = len(grid), len(grid[0])
    out = [[background] * (cols * 2) for _ in range(rows * 2)]
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            for dr in range(2):
                for dc in range(2):
                    out[r * 2 + dr][c * 2 + dc] = v
    return out


def fill_cells_enclosed_by_cardinal_3s(grid, wall=3, fill=4, background=0):
    """BFS from border background cells; unreachable background cells get fill color."""
    from collections import deque
    rows, cols = len(grid), len(grid[0])
    reachable = [[False] * cols for _ in range(rows)]
    q = deque()
    for r in range(rows):
        for c in range(cols):
            if (r == 0 or r == rows - 1 or c == 0 or c == cols - 1) and grid[r][c] == background:
                reachable[r][c] = True
                q.append((r, c))
    while q:
        r, c = q.popleft()
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and not reachable[nr][nc] and grid[nr][nc] == background:
                reachable[nr][nc] = True
                q.append((nr, nc))
    out = [list(row) for row in grid]
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == background and not reachable[r][c]:
                out[r][c] = fill
    return out


def tile_diagonal_cyclic_pattern(grid, background=0):
    """Tile grid with cyclic color based on (r+c)%period, color mapping from non-zero cells."""
    rows, cols = len(grid), len(grid[0])
    nz = [(r, c, grid[r][c]) for r in range(rows) for c in range(cols) if grid[r][c] != background]
    if not nz:
        return [list(row) for row in grid]
    # Build (r+c)%? -> color map
    diag_map = {}
    for r, c, v in nz:
        key = (r + c) % 3
        diag_map[key] = v
    return [[diag_map.get((r + c) % 3, background) for c in range(cols)] for r in range(rows)]


def add_diagonal_ortho_halos(grid, background=0):
    """Value 2 gets diagonal halo of 4; value 1 gets orthogonal halo of 7."""
    rows, cols = len(grid), len(grid[0])
    out = [list(row) for row in grid]
    for r in range(rows):
        for c in range(cols):
            v = grid[r][c]
            if v == 2:
                for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == background:
                        out[nr][nc] = 4
            elif v == 1:
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == background:
                        out[nr][nc] = 7
    return out


def rank_5_columns_by_height(grid, marker=5, background=0):
    """Find columns of 5s, rank by count descending, replace with colors 1,2,3,..."""
    rows, cols = len(grid), len(grid[0])
    col_counts = [(sum(1 for r in range(rows) if grid[r][c] == marker), c)
                  for c in range(cols) if any(grid[r][c] == marker for r in range(rows))]
    col_counts.sort(reverse=True)
    out = [list(row) for row in grid]
    for rank, (count, c) in enumerate(col_counts, 1):
        for r in range(rows):
            if grid[r][c] == marker:
                out[r][c] = rank
    return out


def mark_both_halves_1_as_2(grid, divider=5, background=0):
    """Split by divider column; output 2 where BOTH halves have non-zero at same relative position."""
    rows, cols = len(grid), len(grid[0])
    div_col = next(c for c in range(cols) if all(grid[r][c] == divider for r in range(rows)))
    left = [[grid[r][c] for c in range(div_col)] for r in range(rows)]
    right = [[grid[r][c] for c in range(div_col + 1, cols)] for r in range(rows)]
    out = [[0] * div_col for _ in range(rows)]
    for r in range(rows):
        for c in range(div_col):
            if left[r][c] != background and right[r][c] != background:
                out[r][c] = 2
    return out


def tile_2x2_fill_nonempty_cols_with_8(grid, fill=8, background=0):
    """Replace zeros in columns containing any non-zero with fill, then tile 2x2."""
    rows, cols = len(grid), len(grid[0])
    nonempty_cols = {c for c in range(cols) if any(grid[r][c] != background for r in range(rows))}
    transformed = []
    for r in range(rows):
        row = []
        for c in range(cols):
            v = grid[r][c]
            row.append(v if v != background else (fill if c in nonempty_cols else background))
        transformed.append(row)
    tiled = []
    for _ in range(2):
        for row in transformed:
            tiled.append(row + list(row))
    return tiled


def slide_2blob_toward_8blob(grid, mover=2, anchor=8, background=0):
    """Move the mover-colored blob toward the anchor-colored blob until adjacent."""
    rows, cols = len(grid), len(grid[0])
    mover_cells = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] == mover]
    anchor_cells = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] == anchor]
    if not mover_cells or not anchor_cells:
        return [list(row) for row in grid]
    mr_min, mr_max = min(r for r, c in mover_cells), max(r for r, c in mover_cells)
    mc_min, mc_max = min(c for r, c in mover_cells), max(c for r, c in mover_cells)
    ar_min, ar_max = min(r for r, c in anchor_cells), max(r for r, c in anchor_cells)
    ac_min, ac_max = min(c for r, c in anchor_cells), max(c for r, c in anchor_cells)
    # Determine axis by overlap
    col_overlap = not (mc_max < ac_min or ac_max < mc_min)
    row_overlap = not (mr_max < ar_min or ar_max < mr_min)
    dr, dc = 0, 0
    if col_overlap:
        # Move vertically
        if mr_max < ar_min:
            dr = ar_min - mr_max - 1
        else:
            dr = ar_max - mr_min + 1
    elif row_overlap:
        # Move horizontally
        if mc_max < ac_min:
            dc = ac_min - mc_max - 1
        else:
            dc = ac_max - mc_min + 1
    out = [[background] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == anchor:
                out[r][c] = anchor
    for r, c in mover_cells:
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            out[nr][nc] = mover
    return out


def fill_sections_from_clean_template(grid, divider=5, special=None, background=0):
    """Find section with only {2,3,4,6} values; use it as fill-map for all 9 sections."""
    if special is None:
        special = {2, 3, 4, 6}
    rows, cols = len(grid), len(grid[0])
    div_rows = [r for r in range(rows) if all(grid[r][c] == divider for c in range(cols))]
    div_cols = [c for c in range(cols) if all(grid[r][c] == divider for r in range(rows))]
    # Section boundaries (excluding divider rows/cols)
    row_starts = [0] + [r + 1 for r in div_rows]
    row_ends = div_rows + [rows]
    col_starts = [0] + [c + 1 for c in div_cols]
    col_ends = div_cols + [cols]
    n_si = len(div_rows) + 1
    n_sj = len(div_cols) + 1
    # Extract all sections
    sections = {}
    for si in range(n_si):
        for sj in range(n_sj):
            sec = [[grid[r][c] for c in range(col_starts[sj], col_ends[sj])]
                   for r in range(row_starts[si], row_ends[si])]
            sections[(si, sj)] = sec
    # Find clean template: all non-zero values == special set, no repeats
    template = None
    for pos, sec in sections.items():
        vals = [v for row in sec for v in row if v != background]
        if set(vals) == special and len(vals) == len(special):
            template = sec
            break
    if template is None:
        return [list(row) for row in grid]
    # Build output: fill section (si,sj) solidly with template[si][sj]
    out = [list(row) for row in grid]
    for si in range(n_si):
        for sj in range(n_sj):
            fill_color = template[si][sj] if si < len(template) and sj < len(template[0]) else background
            for r in range(row_starts[si], row_ends[si]):
                for c in range(col_starts[sj], col_ends[sj]):
                    out[r][c] = fill_color
    return out


def crop_to_bounding_box(grid, background=0):
    """Crop grid to the tight bounding box containing all non-background cells."""
    rows, cols = len(grid), len(grid[0])
    nz_rows = [r for r in range(rows) if any(grid[r][c] != background for c in range(cols))]
    nz_cols = [c for c in range(cols) if any(grid[r][c] != background for r in range(rows))]
    if not nz_rows or not nz_cols:
        return [[background]]
    r0, r1 = min(nz_rows), max(nz_rows)
    c0, c1 = min(nz_cols), max(nz_cols)
    return [[grid[r][c] for c in range(c0, c1 + 1)] for r in range(r0, r1 + 1)]


def gravity_drop_columns_to_bottom_trim(grid, background=0):
    """Gravity: each column's non-bg values fall to bottom, same grid dimensions."""
    rows, cols = len(grid), len(grid[0])
    out = [[background] * cols for _ in range(rows)]
    for c in range(cols):
        vals = [grid[r][c] for r in range(rows) if grid[r][c] != background]
        for i, v in enumerate(vals):
            out[rows - len(vals) + i][c] = v
    return out


def replace_3s_with_nearest_border_color(grid, marker=3, background=0):
    """Find two border lines (full rows/cols of single color). Replace marker with nearest border's color."""
    rows, cols = len(grid), len(grid[0])
    borders = []
    for r in range(rows):
        vals = set(grid[r][c] for c in range(cols)) - {background, marker}
        if len(vals) == 1 and all(grid[r][c] in vals or grid[r][c] == background for c in range(cols)):
            if all(grid[r][c] == list(vals)[0] for c in range(cols)):
                borders.append(('row', r, list(vals)[0]))
    for c in range(cols):
        vals = set(grid[r][c] for r in range(rows)) - {background, marker}
        if len(vals) == 1 and all(grid[r][c] in vals for r in range(rows)):
            borders.append(('col', c, list(vals)[0]))
    out = [list(row) for row in grid]
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == marker:
                dists = []
                for btype, bpos, bcolor in borders:
                    d = abs(r - bpos) if btype == 'row' else abs(c - bpos)
                    dists.append((d, bcolor))
                if dists:
                    dists.sort()
                    out[r][c] = dists[0][1]
    return out


def complete_4fold_symmetry(grid, background=0):
    """Complete 4-fold symmetry around center of non-background cells."""
    rows, cols = len(grid), len(grid[0])
    nz = [(r, c, grid[r][c]) for r in range(rows) for c in range(cols) if grid[r][c] != background]
    if not nz:
        return [list(row) for row in grid]
    cr = round(sum(r for r, c, v in nz) / len(nz))
    cc = round(sum(c for r, c, v in nz) / len(nz))
    out = [list(row) for row in grid]
    for r, c, v in nz:
        for nr, nc in [(2 * cr - r, c), (r, 2 * cc - c), (2 * cr - r, 2 * cc - c)]:
            if 0 <= nr < rows and 0 <= nc < cols and out[nr][nc] == background:
                out[nr][nc] = v
    return out
