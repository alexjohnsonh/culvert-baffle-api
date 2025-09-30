from flask import Flask, request, jsonify, send_file
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import tempfile
import base64
import uuid
import os
from matplotlib.patches import Rectangle
import re

app = Flask(__name__)

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

def generate_drawing(data, filename):
    # ---- inputs & defaults ----
    length_m = float(str(data.get("culvertLength", data.get("Culvert Length", data.get("length", 10)))).replace(" m", ""))
    
    diameter_str = str(data.get("diameter", "1200 mm")).replace(" mm", "")
    diameter_m = mm_to_m(float(diameter_str))
    
    # CHECK FOR SMALL CULVERTS - Skip drawing if 599mm or under
    if float(diameter_str) <= 599:
        print(f"Culvert diameter {diameter_str}mm is too small - skipping drawing generation")
        # Create a simple message image instead of a full schematic
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, 
                "CULVERT TOO SMALL FOR BAFFLE SCHEMATIC\n\n"
                f"Diameter: {diameter_str}mm\n\n"
                "Culverts 599mm or under require alternative solutions.\n"
                "Please contact us directly for fish passage options\n"
                "tailored to your small culvert.",
                ha='center', va='center', fontsize=14, fontweight='bold',
                color='#16416f', wrap=True,
                bbox=dict(boxstyle="round,pad=1", facecolor="#f0f0f0", edgecolor="#16416f", linewidth=3))
        ax.axis('off')
        fig.patch.set_edgecolor('#16416f')
        fig.patch.set_linewidth(3)
        plt.tight_layout()
        plt.savefig(filename, dpi=200, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return
    
    # CONTINUE WITH NORMAL PROCESSING FOR CULVERTS OVER 599MM
    gradient_str = str(data.get("gradient", "0%"))
    gradient = parse_gradient(gradient_str)
    
    baffle_h_str = str(data.get("baffleHeight", "150 mm")).replace(" mm", "")
    baffle_h_m = mm_to_m(float(baffle_h_str))
    
    baffle_len_str = str(data.get("baffleLength", "600 mm")).replace(" mm", "")
    baffle_len_m = mm_to_m(float(baffle_len_str))
    
    spacing_str = str(data.get("spacing", "800 mm")).replace(" mm", "")
    spacing_m = mm_to_m(float(spacing_str))
    
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

    fig, (ax_long, ax_plan) = plt.subplots(2, 1, figsize=(14, 10))
    
    if shape == "round":
        title = f"Culvert {length_m:g}m | Ø{int(round(diameter_m*1000))}mm | Gradient {round(gradient*100,1)}%"
    else:
        title = f"Culvert {length_m:g}m | {int(round(box_w_m*1000))}×{int(round(box_h_m*1000))}mm | Gradient {round(gradient*100,1)}%"
    
    fig.suptitle(title, fontsize=16, fontweight='bold', y=0.89, color='#16416f')

    fig.patch.set_edgecolor('#16416f')
    fig.patch.set_linewidth(3)

    # Longitudinal view
    ax_long.set_title("LONGITUDINAL VIEW", fontweight='bold', fontsize=12, pad=0, color='#16416f', y=0.80)
    
    if shape == "round":
        radius = diameter_m / 2.0
        x_curve = np.linspace(0, length_m, 100)
        y_top = -x_curve * gradient + radius
        y_bottom = -x_curve * gradient - radius
        
        ax_long.plot(x_curve, y_top, color='#16416f', linewidth=2)
        ax_long.plot(x_curve, y_bottom, color='#16416f', linewidth=2)
        
        for x in x_positions:
            y_bottom_at_x = -x * gradient - radius
            baffle_top = y_bottom_at_x + baffle_h_m
            ax_long.plot([x, x], [y_bottom_at_x, baffle_top], color='#16416f', linewidth=3)
            
        culvert_height = diameter_m
        
    else:
        height = box_h_m
        x_line = np.array([0, length_m])
        y_top = -x_line * gradient + height/2
        y_bottom = -x_line * gradient - height/2
        
        ax_long.plot(x_line, y_top, color='#16416f', linewidth=2)
        ax_long.plot(x_line, y_bottom, color='#16416f', linewidth=2)
        
        for x in x_positions:
            y_bottom_at_x = -x * gradient - height/2
            baffle_top = y_bottom_at_x + baffle_h_m
            ax_long.plot([x, x], [y_bottom_at_x, baffle_top], color='#16416f', linewidth=3)
            
        culvert_height = box_h_m

    if len(x_positions) >= 2:
        x1, x2 = x_positions[0], x_positions[1]
        if shape == "round":
            y_dim = -((x1 + x2)/2) * gradient + diameter_m/4
        else:
            y_dim = -((x1 + x2)/2) * gradient + box_h_m/4
        
        ax_long.annotate('', xy=(x1, y_dim), xytext=(x2, y_dim),
                        arrowprops=dict(arrowstyle='<->', color='#89ccea', lw=1))
        ax_long.text((x1+x2)/2, y_dim+0.08, f"Spacing = {int(round(spacing_m*1000))}mm", 
                    ha='center', va='bottom', fontsize=9, fontweight='bold', color='#16416f')

    if x_positions:
        x_ref = x_positions[-1]
        if shape == "round":
            y_bottom_ref = -x_ref * gradient - diameter_m/2 - 0.05
        else:
            y_bottom_ref = -x_ref * gradient - box_h_m/2 - 0.05
        
        y_top_ref = y_bottom_ref + baffle_h_m + 0.1
        x_dim = x_ref + 0.3
        
        ax_long.annotate('', xy=(x_dim, y_bottom_ref), xytext=(x_dim, y_top_ref),
                        arrowprops=dict(arrowstyle='<->', color='#89ccea', lw=1))
        
        ax_long.text(x_dim+0.2, (y_bottom_ref + y_top_ref)/2, f"Baffle\nheight\n{int(round(baffle_h_m*1000))}mm", 
                    ha='left', va='center', fontsize=9, fontweight='bold', color='#16416f')

    y_min = -length_m * gradient - culvert_height/2 - 0.4
    y_max = culvert_height/2 + 0.5
    ax_long.set_xlim(-1.0, length_m + 1.5)
    ax_long.set_ylim(y_min - 0.3, y_max + 0.3)
    ax_long.axis('off')

    # Plan view
    ax_plan.set_title("PLAN VIEW", fontweight='bold', fontsize=12, pad=0, color='#16416f', y=0.80)
    
    if shape == "round":
        radius = diameter_m / 2.0
        ax_plan.plot([0, length_m], [radius, radius], color='#16416f', linewidth=2)
        ax_plan.plot([0, length_m], [-radius, -radius], color='#16416f', linewidth=2)
        culvert_width = diameter_m
    else:
        width = box_w_m
        height = box_h_m
        ax_plan.plot([0, length_m], [height/2, height/2], color='#16416f', linewidth=2)
        ax_plan.plot([0, length_m], [-height/2, -height/2], color='#16416f', linewidth=2)
        culvert_width = box_h_m

    if placement == "offset":
        if shape == "round":
            placement_text = "Offset baffles (50mm)"
        else:
            placement_text = "Alternating offset baffles"
    else:
        placement_text = "Centred baffles"
    
    ax_plan.text(length_m/2, culvert_width/2 + 0.3, placement_text,
                ha='center', va='center', fontsize=11, fontweight='bold', color='#16416f',
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#89ccea"))

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
        
        ax_plan.plot([x, x], [y_start, y_end], color='#16416f', linewidth=3)

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
                        arrowprops=dict(arrowstyle='<->', color='#89ccea', lw=1))
        ax_plan.text(x_dim+0.05, y_center, f"Baffle\nlength\n{int(round(baffle_len_m*1000))}mm", 
                    ha='left', va='center', fontsize=9, fontweight='bold', color='#16416f')

    if shape == "round":
        x_diam = -0.3
        y_top_diam = radius
        y_bottom_diam = -radius
        
        ax_plan.annotate('', xy=(x_diam, y_bottom_diam), xytext=(x_diam, y_top_diam),
                        arrowprops=dict(arrowstyle='<->', color='#89ccea', lw=1))
        ax_plan.text(x_diam-0.1, 0, f"Ø{int(round(diameter_m*1000))}mm",
                    ha='right', va='center', fontsize=11, fontweight='bold', rotation=90, color='#16416f')

    y_length_dim = -culvert_width/2 - 0.3
    ax_plan.annotate('', xy=(0, y_length_dim), xytext=(length_m, y_length_dim),
                    arrowprops=dict(arrowstyle='<->', color='#89ccea', lw=1))
    ax_plan.text(length_m/2, y_length_dim-0.1, f"{length_m:g}m", 
                ha='center', va='top', fontsize=11, fontweight='bold', color='#16416f')

    ax_plan.set_xlim(-1.0, length_m + 1.0)
    ax_plan.set_ylim(-culvert_width/2 - 0.8, culvert_width/2 + 1.2)
    ax_plan.axis('off')

    plt.tight_layout()
    plt.subplots_adjust(top=0.90)
    
    fig.patch.set_edgecolor('#16416f')
    fig.patch.set_linewidth(3)
    
    plt.savefig(filename, dpi=200, bbox_inches='tight', facecolor='white')
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
