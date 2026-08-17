from flask import Flask, request, jsonify, send_file
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import tempfile
import base64
import uuid
import os
from datetime import date
from matplotlib.patches import Rectangle, FancyBboxPatch, Polygon
import re
from flask_cors import CORS

plt.rcParams['font.family'] = 'monospace'

NAVY = '#16416f'
ACCENT = '#89ccea'
PAPER_BG = '#ffffff'

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": [
    "https://ats-environmental.com",
    "https://www.ats-environmental.com"
]}})

def mm_to_m(v): 
    return float(v) / 1000.0

def parse_gradient(gradient_str):
    """Parse gradient string and handle 'greater than X%' format"""
    original_str = str(gradient_str)
    gradient_str = str(gradient_str).lower()
    
    print(f"Gradient parsing - Original: '{original_str}', Lowercase: '{gradient_str}'")
    
    if "nan" in gradient_str or gradient_str == "nan%":
        print("Detected NaN gradient, returning 0.0")
        return 0.0
    
    if "greater than" in gradient_str:
        print("Detected 'greater than' format")
        match = re.search(r'greater than\s*(\d+(?:\.\d+)?)', gradient_str)
        if match:
            value = float(match.group(1)) / 100.0
            print(f"Extracted value: {value}")
            return value
        else:
            print("Could not extract number from 'greater than' format")
    
    gradient_str = gradient_str.replace("%", "")
    try:
        value = float(gradient_str)
        if value != value:
            print("Detected NaN value, returning 0.0")
            return 0.0
        result = value / 100.0
        print(f"Standard parsing result: {result}")
        return result
    except (ValueError, TypeError) as e:
        print(f"Parsing failed with error: {e}, returning 0.0")
        return 0.0

# Format dimensions based on units (no decimals for imperial)
def format_dimension(value_mm, units, decimal_places=0):
    """
    Convert mm to appropriate display format
    value_mm: value in millimeters
    units: 'metric' or 'imperial'
    decimal_places: decimal places (default 0 for whole numbers)
    """
    if units == "imperial":
        inches = value_mm / 25.4
        return f'{inches:.{decimal_places}f}"'
    return f'{int(round(value_mm))}mm'

# Format length (meters to feet, no decimals)
def format_length(value_m, units, decimal_places=0):
    """
    Convert meters to appropriate display format
    value_m: value in meters
    units: 'metric' or 'imperial'
    """
    if units == "imperial":
        feet = value_m * 3.281
        return f"{feet:.{decimal_places}f}'"
    return f"{value_m:g}m"

def generate_drawing(data, filename):
    # ---- Get units preference (default to metric) ----
    units = data.get("units", "metric").lower()
    print(f"Drawing units: {units}")

    # ---- Region (baffle end-cut style) ----
    # No explicit region field is sent today - the business rule is metric => NZ,
    # imperial => USA, so infer it from units. An explicit "region"/"Region" field
    # (if ever added upstream) overrides that inference.
    region_input = data.get("region", data.get("Region"))
    if region_input is not None:
        region_str = str(region_input).lower()
        is_nz = any(k in region_str for k in ["nz", "new zealand"])
    else:
        is_nz = (units == "metric")
        region_str = f"inferred from units={units}"
    print(f"Region: {region_str} (NZ 45deg mitred: {is_nz})")

    # ---- Culvert ID (optional label) ----
    culvert_id = str(data.get("culvertId", data.get("Culvert ID", data.get("culvert_id", "")))).strip()

    # ---- inputs & defaults ----
    # Parse length - strip both metric and imperial units
    length_str = str(data.get("culvertLength", data.get("Culvert Length", data.get("length", 10))))
    length_str = length_str.replace(" m", "").replace("'", "").replace("m", "").strip()
    length_m = float(length_str)
    print(f"Parsed length: {length_m}m")
    
    # Parse diameter - strip both metric and imperial units
    diameter_str = str(data.get("diameter", "1200 mm"))
    diameter_str = diameter_str.replace(" mm", "").replace('"', "").replace("mm", "").strip()
    diameter_mm = float(diameter_str)
    diameter_m = mm_to_m(diameter_mm)
    print(f"Parsed diameter: {diameter_mm}mm = {diameter_m}m")
    
    # CHECK FOR SMALL CULVERTS - Flag but continue drawing (without baffles)
    is_small_culvert = diameter_mm <= 599
    if is_small_culvert:
        print(f"Culvert diameter {diameter_mm}mm is too small - drawing without baffles and adding warning overlay")
        baffle_h_m = 0.15
        baffle_len_m = 0.6
        spacing_m = 0.8
    else:
        baffle_h_str = str(data.get("baffleHeight", "150 mm"))
        baffle_h_str = baffle_h_str.replace(" mm", "").replace('"', "").replace("mm", "").replace("N/A - Culvert too small", "150").strip()
        baffle_h_mm = float(baffle_h_str)
        baffle_h_m = mm_to_m(baffle_h_mm)
        print(f"Parsed baffle height: {baffle_h_mm}mm = {baffle_h_m}m")
        
        baffle_len_str = str(data.get("baffleLength", "600 mm"))
        baffle_len_str = baffle_len_str.replace(" mm", "").replace('"', "").replace("mm", "").replace("N/A - Culvert too small", "600").strip()
        baffle_len_mm = float(baffle_len_str)
        baffle_len_m = mm_to_m(baffle_len_mm)
        print(f"Parsed baffle length: {baffle_len_mm}mm = {baffle_len_m}m")
        
        spacing_str = str(data.get("spacing", "800 mm"))
        spacing_str = spacing_str.replace(" mm", "").replace('"', "").replace("mm", "").replace("N/A - Culvert too small", "800").strip()
        spacing_mm = float(spacing_str)
        spacing_m = mm_to_m(spacing_mm)
        print(f"Parsed spacing: {spacing_mm}mm = {spacing_m}m")
    
    gradient_str = str(data.get("gradient", "0%"))
    gradient = parse_gradient(gradient_str)
    
    shape_str = str(data.get("shape", "round")).lower()
    if shape_str == "flat":
        shape = "box"
    else:
        shape = "round"
    
    installation = str(data.get("installation", "")).lower()
    
    print(f"Installation value received: '{installation}'")
    
    box_w_m = diameter_m
    box_h_m = diameter_m
    
    if any(keyword in installation for keyword in ["offset", "alternating", "meander", "20% shorter"]):
        placement = "offset"
        print("Setting placement to OFFSET")
        if shape == "round":
            lateral_offset_m = 0.05
        else:
            lateral_offset_m = 0.0
    elif any(keyword in installation for keyword in ["centered", "centred", "full width", "full-width"]) or installation == "":
        placement = "centered"
        print("Setting placement to CENTERED")
        lateral_offset_m = 0.0
        if shape == "box":
            baffle_len_m = box_h_m
    else:
        placement = "centered"
        print(f"Defaulting to CENTERED - unknown installation value: '{installation}'")
        lateral_offset_m = 0.0
        if shape == "box":
            baffle_len_m = box_h_m

    length_m = max(0.5, length_m)
    spacing_m = max(0.05, spacing_m)
    baffle_h_m = max(0.0, baffle_h_m)
    baffle_len_m = max(0.0, baffle_len_m)

    n_baffles = int(length_m // spacing_m)
    x_positions = [i * spacing_m for i in range(1, n_baffles + 1) if i * spacing_m <= length_m]
    
    # If small culvert, clear baffle positions so no baffles are drawn
    if is_small_culvert:
        x_positions = []

    # ---- Broken/truncated view for long culverts with many closely-spaced baffles ----
    # Show a handful of baffles at each end, true to scale, with a conventional
    # drafting "break" in between rather than cramming every baffle in (which
    # stops looking to-scale once there are dozens of them).
    SHOW_COUNT = 4
    BREAK_THRESHOLD = 2 * SHOW_COUNT + 1
    use_break = len(x_positions) > BREAK_THRESHOLD

    if use_break:
        near_positions = x_positions[:SHOW_COUNT]
        far_positions = x_positions[-SHOW_COUNT:]
        near_cutoff = near_positions[-1] + spacing_m * 0.5
        far_start = far_positions[0] - spacing_m * 0.5
        gap_w = max(1.0, diameter_m if shape == "round" else box_w_m)
    else:
        near_positions = x_positions
        far_positions = []
        near_cutoff = length_m
        far_start = length_m
        gap_w = 0.0

    shown_positions = near_positions + far_positions
    shown_set = set(shown_positions)

    def to_plot_x(true_x):
        if not use_break or true_x <= near_cutoff:
            return true_x
        return near_cutoff + gap_w + (true_x - far_start)

    plot_length_end = to_plot_x(length_m)

    def draw_break_symbol(ax, y_lo, y_hi, half_width=None):
        span = y_hi - y_lo
        hw = half_width if half_width is not None else max(0.06, span * 0.06)
        pad = span * 0.12
        x_c = near_cutoff + gap_w / 2.0
        ys = [y_lo - pad, y_lo + span * 0.28, y_lo + span * 0.5, y_lo + span * 0.72, y_hi + pad]
        xs = [x_c, x_c - hw, x_c + hw, x_c - hw, x_c]
        ax.plot(xs, ys, color=NAVY, linewidth=2, solid_capstyle='round', zorder=3)

    # ---- Drafting-sheet layout: title band, longitudinal+plan on the left, ----
    # ---- parameters / cross-section / title block stacked on the right ----
    fig = plt.figure(figsize=(15.5, 10.8))
    fig.patch.set_facecolor(PAPER_BG)
    fig.patch.set_edgecolor(NAVY)
    fig.patch.set_linewidth(3)

    ax_long = fig.add_axes([0.035, 0.495, 0.55, 0.35]); ax_long.set_facecolor(PAPER_BG)
    ax_plan = fig.add_axes([0.035, 0.045, 0.55, 0.375]); ax_plan.set_facecolor(PAPER_BG)
    ax_cross = fig.add_axes([0.625, 0.205, 0.34, 0.46]); ax_cross.set_facecolor(PAPER_BG)
    ax_params = fig.add_axes([0.625, 0.685, 0.34, 0.20]); ax_params.set_facecolor(PAPER_BG)
    ax_titleblock = fig.add_axes([0.625, 0.045, 0.34, 0.14]); ax_titleblock.set_facecolor(PAPER_BG)

    # TITLE
    if shape == "round":
        title = f"CULVERT {format_length(length_m, units)} | Ø{format_dimension(diameter_m*1000, units, 0)} | GRADIENT {round(gradient*100,1)}%"
    else:
        title = f"CULVERT {format_length(length_m, units)} | {format_dimension(box_w_m*1000, units, 0)}×{format_dimension(box_h_m*1000, units, 0)} | GRADIENT {round(gradient*100,1)}%"

    if culvert_id:
        title = f"{title} | {culvert_id}"

    fig.text(0.5, 0.955, title, ha='center', va='center', fontsize=19, fontweight='bold', color=NAVY)
    title_divider = plt.Line2D([0.035, 0.965], [0.905, 0.905], transform=fig.transFigure, color=NAVY, linewidth=1)
    fig.add_artist(title_divider)

    # ===== PARAMETERS BOX (top right) =====
    def dim_sp(v_mm):
        s = format_dimension(v_mm, units)
        return s[:-2] + ' mm' if s.endswith('mm') else s

    def len_sp(v_m):
        s = format_length(v_m, units)
        return s[:-1] + ' m' if s.endswith('m') else s

    param_rows = [
        ("A", "Spacing", dim_sp(spacing_m*1000)),
        ("B", "Baffle height", dim_sp(baffle_h_m*1000)),
        ("C", "Baffle length", dim_sp(baffle_len_m*1000)),
        ("D", "Diameter" if shape == "round" else "Width", dim_sp(diameter_m*1000)),
        ("E", "Culvert length", len_sp(length_m)),
    ]
    param_text = "\n".join(f"$\\mathbf{{{letter}}}$ {name} - {value}" for letter, name, value in param_rows)

    ax_params.set_xlim(0, 1); ax_params.set_ylim(0, 1); ax_params.axis('off')
    ax_params.add_patch(Rectangle((0, 0), 1, 1, fill=False, edgecolor=NAVY, linewidth=1.5, transform=ax_params.transAxes))
    ax_params.text(0.07, 0.87, "PARAMETERS", fontsize=12, fontweight='bold', color=NAVY, va='top', ha='left')
    ax_params.plot([0.07, 0.93], [0.73, 0.73], color=NAVY, linewidth=1)
    ax_params.text(0.07, 0.62, param_text, fontsize=10, color=NAVY, va='top', ha='left', linespacing=1.6)

    # ===== TITLE BLOCK (bottom right) =====
    ax_titleblock.set_xlim(0, 1); ax_titleblock.set_ylim(0, 1); ax_titleblock.axis('off')
    ax_titleblock.add_patch(Rectangle((0, 0), 1, 1, fill=False, edgecolor=NAVY, linewidth=1.5, transform=ax_titleblock.transAxes))
    ax_titleblock.text(0.07, 0.88, "CULVERT BAFFLE LAYOUT", fontsize=11, fontweight='bold', color=NAVY, va='top', ha='left')
    ax_titleblock.plot([0, 1], [0.76, 0.76], color=NAVY, linewidth=1)
    ax_titleblock.plot([0, 1], [0.38, 0.38], color=NAVY, linewidth=1)
    ax_titleblock.plot([0.5, 0.5], [0, 0.76], color=NAVY, linewidth=1)
    ax_titleblock.text(0.07, 0.64, "ATS ENVIRONMENTAL", fontsize=9.5, color=NAVY, va='top', ha='left')
    ax_titleblock.text(0.53, 0.64, "ADMIN@ATS-\nENVIRONMENTAL.COM", fontsize=9.5, color=NAVY, va='top', ha='left', linespacing=1.6)
    ax_titleblock.text(0.07, 0.26, "NOT TO SCALE", fontsize=9.5, color=NAVY, va='top', ha='left')
    ax_titleblock.text(0.53, 0.26, date.today().strftime("%d %b %Y").upper(), fontsize=9.5, color=NAVY, va='top', ha='left')

    # ===== LONGITUDINAL VIEW =====
    # Title aligned with the "PARAMETERS" header row (then nudged down a bit further)
    params_box_bottom, params_box_height = 0.685, 0.20
    header_row_y = params_box_bottom + 0.87 * params_box_height
    long_centre_x = 0.035 + 0.55 / 2.0
    fig.text(long_centre_x, header_row_y - 0.04, "LONGITUDINAL VIEW", ha='center', va='top',
             fontweight='bold', fontsize=12, color=NAVY)

    # Baffles drawn perpendicular to the (sloped) invert, not plumb-vertical
    perp_norm = (1.0 + gradient ** 2) ** 0.5
    perp_dx = gradient / perp_norm
    perp_dy = 1.0 / perp_norm

    def plot_baffle_perp(true_x, y_invert):
        plot_x = to_plot_x(true_x)
        ax_long.plot([plot_x, plot_x + baffle_h_m * perp_dx], [y_invert, y_invert + baffle_h_m * perp_dy],
                     color='#16416f', linewidth=3)

    def plot_wall_segment(x_true_start, x_true_end, half_height):
        x_true = np.linspace(x_true_start, x_true_end, 60)
        x_plot = np.array([to_plot_x(v) for v in x_true])
        y_top_seg = -x_true * gradient + half_height
        y_bottom_seg = -x_true * gradient - half_height
        ax_long.plot(x_plot, y_top_seg, color='#16416f', linewidth=2)
        ax_long.plot(x_plot, y_bottom_seg, color='#16416f', linewidth=2)

    if shape == "round":
        radius = diameter_m / 2.0
        half_height = radius
        culvert_height = diameter_m
    else:
        half_height = box_h_m / 2.0
        culvert_height = box_h_m

    plot_wall_segment(0, near_cutoff, half_height)
    if use_break:
        plot_wall_segment(far_start, length_m, half_height)
        y_top_at_gap = -near_cutoff * gradient + half_height
        y_bottom_at_gap = -near_cutoff * gradient - half_height
        draw_break_symbol(ax_long, y_bottom_at_gap, y_top_at_gap)
        gap_centre_x = near_cutoff + gap_w / 2.0
        ax_long.text(gap_centre_x, y_top_at_gap + 0.35, f"{len(x_positions)} BAFFLES TOTAL",
                    ha='center', va='bottom', fontsize=9, fontweight='bold', color=NAVY)

    for x in shown_positions:
        y_bottom_at_x = -x * gradient - half_height
        plot_baffle_perp(x, y_bottom_at_x)

    # SPACING DIMENSION - arrow with "A" label (always within the near, true-scale segment)
    if len(near_positions) >= 2:
        x1, x2 = near_positions[0], near_positions[1]
        y_dim = -((x1 + x2)/2) * gradient + half_height/2

        ax_long.annotate('', xy=(to_plot_x(x1), y_dim), xytext=(to_plot_x(x2), y_dim),
                        arrowprops=dict(arrowstyle='<->', color='#89ccea', lw=2))
        ax_long.text(to_plot_x((x1+x2)/2), y_dim+0.08, "A",
                    ha='center', va='bottom', fontsize=11, fontweight='bold', color='#16416f')

    # BAFFLE HEIGHT DIMENSION - arrow with "B" label (on the last shown baffle)
    if shown_positions:
        x_ref = shown_positions[-1]
        y_bottom_ref = -x_ref * gradient - half_height - 0.05

        y_top_ref = y_bottom_ref + baffle_h_m + 0.1
        x_dim = to_plot_x(x_ref) + 0.3

        ax_long.annotate('', xy=(x_dim, y_bottom_ref), xytext=(x_dim, y_top_ref),
                        arrowprops=dict(arrowstyle='<->', color='#89ccea', lw=2))

        ax_long.text(x_dim+0.15, (y_bottom_ref + y_top_ref)/2, "B",
                    ha='left', va='center', fontsize=11, fontweight='bold', color='#16416f')

    y_min = -length_m * gradient - culvert_height/2 - 0.4
    y_max = culvert_height/2 + 0.5
    ax_long.set_xlim(-1.0, plot_length_end + 1.5)
    ax_long.set_ylim(y_min - 0.3, (y_max + 0.5 if use_break else y_max) + 0.3)
    ax_long.axis('off')

    # ===== PLAN VIEW =====
    plan_axes_top = 0.045 + 0.375
    fig.text(long_centre_x, plan_axes_top - 0.04, "PLAN VIEW", ha='center', va='top',
             fontweight='bold', fontsize=12, color=NAVY)

    if shape == "round":
        radius = diameter_m / 2.0
        culvert_width = diameter_m
    else:
        culvert_width = box_h_m

    def plot_plan_wall(x_true_start, x_true_end, y_val):
        ax_plan.plot([to_plot_x(x_true_start), to_plot_x(x_true_end)], [y_val, y_val],
                    color='#16416f', linewidth=2)

    plot_plan_wall(0, near_cutoff, culvert_width/2)
    plot_plan_wall(0, near_cutoff, -culvert_width/2)
    if use_break:
        plot_plan_wall(far_start, length_m, culvert_width/2)
        plot_plan_wall(far_start, length_m, -culvert_width/2)
        draw_break_symbol(ax_plan, -culvert_width/2, culvert_width/2)

    # Dotted centreline down the middle of the culvert (drawn continuous through any break,
    # per drafting convention - only the object outline itself gets the break symbol)
    ax_plan.plot([-0.3, plot_length_end + 0.3], [0, 0], linestyle=':', color=ACCENT, linewidth=1.2, zorder=0)

    # PLACEMENT TEXT
    if placement == "offset":
        if shape == "round":
            if units == "imperial":
                placement_text = "OFFSET BAFFLES (2\")"
            else:
                placement_text = "OFFSET BAFFLES (50mm)"
        else:
            placement_text = "ALTERNATING OFFSET BAFFLES"
    else:
        placement_text = "CENTRED BAFFLES"

    ax_plan.text(plot_length_end/2, culvert_width/2 + 0.3, placement_text,
                ha='center', va='center', fontsize=11, fontweight='bold', color='#16416f',
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#89ccea"))

    cross_section_x = None
    cross_section_y_start = None
    cross_section_y_end = None

    for i, x in enumerate(x_positions):
        if placement == "offset" and shape == "box":
            if i % 2 == 0:
                y_start = -culvert_width/2
                y_end = y_start + baffle_len_m
            else:
                y_end = culvert_width/2
                y_start = y_end - baffle_len_m
        elif placement == "centered":
            if shape == "box":
                y_start = -culvert_width/2
                y_end = culvert_width/2
            else:
                y_center = lateral_offset_m
                y_start = y_center - baffle_len_m/2
                y_end = y_center + baffle_len_m/2
        else:
            y_center = lateral_offset_m
            y_start = y_center - baffle_len_m/2
            y_end = y_center + baffle_len_m/2

        if x in shown_set:
            plot_x = to_plot_x(x)
            ax_plan.plot([plot_x, plot_x], [y_start, y_end], color='#16416f', linewidth=3)

        # Remember the first baffle's transverse footprint for the cross-section view
        if cross_section_x is None:
            cross_section_x = x
            cross_section_y_start = y_start
            cross_section_y_end = y_end

    # BAFFLE LENGTH - arrow with "C" label
    if x_positions and (placement != "centered" or shape == "round"):
        x_ref = x_positions[0]
        if placement == "offset" and shape == "box":
            y_center = -culvert_width/2 + baffle_len_m/2
            y1_ref = -culvert_width/2
            y2_ref = -culvert_width/2 + baffle_len_m
        else:
            y_center = lateral_offset_m
            y1_ref = y_center - baffle_len_m/2
            y2_ref = y_center + baffle_len_m/2
        
        x_dim = x_ref + 0.15
        ax_plan.annotate('', xy=(x_dim, y1_ref), xytext=(x_dim, y2_ref),
                        arrowprops=dict(arrowstyle='<->', color='#89ccea', lw=2))
        ax_plan.text(x_dim+0.1, y_center, "C", 
                    ha='left', va='center', fontsize=11, fontweight='bold', color='#16416f')

    # DIAMETER - arrow with "D" label
    if shape == "round":
        x_diam = -0.3
        y_top_diam = radius
        y_bottom_diam = -radius
        
        ax_plan.annotate('', xy=(x_diam, y_bottom_diam), xytext=(x_diam, y_top_diam),
                        arrowprops=dict(arrowstyle='<->', color='#89ccea', lw=2))
        ax_plan.text(x_diam-0.1, 0, "D",
                    ha='right', va='center', fontsize=11, fontweight='bold', rotation=90, color='#16416f')

    # LENGTH - arrow with "E" label (spans the full plotted width; the true total length is
    # what's labelled, same convention as the break itself)
    y_length_dim = -culvert_width/2 - 0.3
    ax_plan.annotate('', xy=(0, y_length_dim), xytext=(plot_length_end, y_length_dim),
                    arrowprops=dict(arrowstyle='<->', color='#89ccea', lw=2))
    ax_plan.text(plot_length_end/2, y_length_dim-0.1, "E",
                ha='center', va='top', fontsize=11, fontweight='bold', color='#16416f')

    ax_plan.set_xlim(-1.0, plot_length_end + 1.0)  # No extra space needed
    ax_plan.set_ylim(-culvert_width/2 - 0.8, culvert_width/2 + 1.2)
    ax_plan.axis('off')

    # ===== CROSS-SECTION VIEW (end-on, at first baffle) =====
    if shape == "round":
        radius = diameter_m / 2.0
        invert_y = -radius
        outline = plt.Circle((0, 0), radius, fill=False, edgecolor=NAVY, linewidth=2, zorder=2)
        ax_cross.add_patch(outline)
        half_extent = radius
    else:
        invert_y = -box_h_m / 2.0
        outline = Rectangle((-box_w_m/2, -box_h_m/2), box_w_m, box_h_m,
                            fill=False, edgecolor=NAVY, linewidth=2, zorder=2)
        ax_cross.add_patch(outline)
        half_extent = box_w_m / 2.0

    # Dashed crosshair centrelines (drafting convention)
    ax_cross.plot([-half_extent - 0.3, half_extent + 0.3], [0, 0],
                  linestyle=(0, (5, 4)), color=ACCENT, linewidth=1.2, alpha=0.3, zorder=0)
    ax_cross.plot([0, 0], [invert_y - 0.3, -invert_y + 0.4],
                  linestyle=(0, (5, 4)), color=ACCENT, linewidth=1.2, alpha=0.3, zorder=0)

    if cross_section_x is not None:
        base_width = cross_section_y_end - cross_section_y_start
        base_centre = (cross_section_y_start + cross_section_y_end) / 2.0

        if shape == "round":
            R = radius
            R_off = max(0.001, R - baffle_h_m)
            theta_half = (base_width / 2.0) / R
            theta_centre = base_centre / R
            theta_lo, theta_hi = theta_centre - theta_half, theta_centre + theta_half

            outer_theta = np.linspace(theta_lo, theta_hi, 40)
            outer_pts = list(zip(R * np.sin(outer_theta), -R * np.cos(outer_theta)))

            if is_nz:
                # NZ: the main body is the SAME constant-offset curve as USA (follows the
                # pipe wall at exactly baffle_h_m the whole way) - only the last bit of each
                # end tapers, mitred at 45 deg (horizontal run == vertical rise == baffle_h_m),
                # closing down to the true wall exactly at the specified base width.
                reduced_half = max(0.0, base_width / 2.0 - baffle_h_m)
                theta_reduced = reduced_half / R
                theta_lo_in, theta_hi_in = theta_centre - theta_reduced, theta_centre + theta_reduced
                inner_theta = np.linspace(theta_hi_in, theta_lo_in, 40)
                inner_pts = list(zip(R_off * np.sin(inner_theta), -R_off * np.cos(inner_theta)))
            else:
                # USA: 90 deg square ends - concentric offset arc, same angular span
                inner_theta = np.linspace(theta_hi, theta_lo, 40)
                inner_pts = list(zip(R_off * np.sin(inner_theta), -R_off * np.cos(inner_theta)))

            baffle_patch = Polygon(outer_pts + inner_pts, closed=True,
                                    facecolor=PAPER_BG, edgecolor=NAVY, linewidth=1.5,
                                    hatch='///', zorder=1)
        else:
            baffle_patch = Rectangle((cross_section_y_start, invert_y),
                                     base_width, baffle_h_m,
                                     facecolor=PAPER_BG, edgecolor=NAVY, linewidth=1.5,
                                     hatch='///', zorder=1)

        ax_cross.add_patch(baffle_patch)

        # BAFFLE HEIGHT DIMENSION - arrow with "B" label
        x_dim = half_extent + 0.3
        ax_cross.annotate('', xy=(x_dim, invert_y), xytext=(x_dim, invert_y + baffle_h_m),
                          arrowprops=dict(arrowstyle='<->', color=ACCENT, lw=2))
        ax_cross.text(x_dim + 0.1, invert_y + baffle_h_m/2, "B",
                     ha='left', va='center', fontsize=11, fontweight='bold', color=NAVY)

        # BAFFLE LENGTH (base footprint) DIMENSION - arrow with "C" label
        y_dim = invert_y - 0.3
        ax_cross.annotate('', xy=(cross_section_y_start, y_dim), xytext=(cross_section_y_end, y_dim),
                          arrowprops=dict(arrowstyle='<->', color=ACCENT, lw=2))
        ax_cross.text(base_centre, y_dim - 0.1, "C",
                     ha='center', va='top', fontsize=11, fontweight='bold', color=NAVY)

    ax_cross.set_xlim(-half_extent - 0.9, half_extent + 0.9)
    ax_cross.set_ylim(invert_y - 0.6, -invert_y + 0.4)
    ax_cross.set_aspect('equal')
    ax_cross.axis('off')

    cross_title = "CROSS-SECTION VIEW"
    if shape == "round":
        cross_title += " - 45° ENDS" if is_nz else " - 90° ENDS"
    ax_cross.set_title(cross_title, fontweight='bold', fontsize=12, pad=15, color=NAVY)

    # WARNING for small culverts
    if is_small_culvert:
        warning_diameter = format_dimension(diameter_mm, units, 1)
        fig.text(0.30, 0.45,
                'CULVERT TOO SMALL FOR BAFFLES \n\n'
                f'Diameter: {warning_diameter}\n\n'
                'Culverts 599mm (23.6") or under require alternative solutions.\n'
                'Please contact us directly for fish passage options.',
                ha='center', va='center', fontsize=15, fontweight='bold',
                color=NAVY,
                bbox=dict(boxstyle="round,pad=1.5", facecolor=ACCENT,
                         edgecolor=NAVY, linewidth=4, alpha=0.9),
                transform=fig.transFigure, zorder=100)

    plt.savefig(filename, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)


@app.route("/download/<filename>")
def download_file(filename):
    """Serve files for download"""
    if os.path.exists(filename) and filename.endswith('.png'):
        return send_file(filename, as_attachment=True, download_name='culvert_schematic.png')
    else:
        return "File not found", 404


@app.route("/flexibaffle_drawings", methods=["POST"])
def flexibaffle_drawings():
    try:
        print(f"Content-Type: {request.content_type}")
        print(f"Request data: {request.get_data()}")
        
        payload = None
        
        try:
            payload = request.get_json()
        except:
            pass
            
        if not payload:
            try:
                payload = request.get_json(force=True)
            except:
                pass
        
        if not payload:
            try:
                import json
                raw_data = request.get_data(as_text=True)
                print(f"Raw data as text: {raw_data}")
                payload = json.loads(raw_data)
            except Exception as e:
                print(f"Manual JSON parsing failed: {e}")
        
        if not payload:
            return jsonify({"error": "No valid JSON payload received"}), 400
            
        print(f"Successfully parsed payload: {payload}")

        file_id = str(uuid.uuid4())
        permanent_filename = f"{file_id}.png"
        
        generate_drawing(payload, permanent_filename)
        
        with open(permanent_filename, 'rb') as img_file:
            img_b64 = base64.b64encode(img_file.read()).decode("utf-8")

        download_url = f"https://culvert-baffle-api.onrender.com/download/{permanent_filename}"
        
        print("Image generated successfully")
        return jsonify({
            "download_url": download_url,
            "image_base64": img_b64,
            "status": "success"
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Server error: {str(e)}"}), 500


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
