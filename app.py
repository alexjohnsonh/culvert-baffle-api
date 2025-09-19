from flask import Flask, request, jsonify, send_file
import matplotlib
matplotlib.use("Agg")  # no GUI
import matplotlib.pyplot as plt
import numpy as np
import tempfile
import base64
import uuid
import os
from matplotlib.patches import Rectangle

app = Flask(__name__)

def mm_to_m(v): 
    return float(v) / 1000.0

def generate_drawing(data, filename):
    # ---- inputs & defaults ----
    # Handle exact Zapier output field names
    length_m = float(str(data.get("culvertLength", data.get("Culvert Length", data.get("length", 10)))).replace(" m", ""))
    
    # Handle diameter with units
    diameter_str = str(data.get("diameter", "1200 mm")).replace(" mm", "")
    diameter_m = mm_to_m(float(diameter_str))
    
    # Handle gradient with % symbol
    gradient_str = str(data.get("gradient", "0%")).replace("%", "")
    gradient = float(gradient_str) / 100.0
    
    # Handle baffle measurements with units
    baffle_h_str = str(data.get("baffleHeight", "150 mm")).replace(" mm", "")
    baffle_h_m = mm_to_m(float(baffle_h_str))
    
    baffle_len_str = str(data.get("baffleLength", "600 mm")).replace(" mm", "")
    baffle_len_m = mm_to_m(float(baffle_len_str))
    
    spacing_str = str(data.get("spacing", "800 mm")).replace(" mm", "")
    spacing_m = mm_to_m(float(spacing_str))
    
    # Handle shape from Zapier (round/flat)
    shape_str = str(data.get("shape", "round")).lower()
    if shape_str == "flat":
        shape = "box"
    else:
        shape = "round"  # default to round for "round" or any other value
    
    # Parse Installation field to determine placement and baffle behavior
    installation = str(data.get("installation", "")).lower()
    
    # Box culvert sizes (for flat/box culverts, use diameter as both width and height)
    box_w_m = diameter_m  # Width same as diameter
    box_h_m = diameter_m  # Height same as diameter
    
    if "offset" in installation:
        placement = "offset"
        if shape == "round":
            # Round culverts: always 50mm offset
            lateral_offset_m = 0.05  # 50mm
            # baffle_len_m already set from Zapier data above
        else:
            # Box culverts: alternating pattern, baffle length already calculated by Zapier
            lateral_offset_m = 0.0  # Will handle alternating in the drawing loop
    else:
        # Centered installation
        placement = "centered"  
        lateral_offset_m = 0.0
        # baffle_len_m already set from Zapier data above

    # Safety clamps
    length_m      = max(0.5, length_m)
    spacing_m     = max(0.05, spacing_m)
    baffle_h_m    = max(0.0, baffle_h_m)
    baffle_len_m  = max(0.0, baffle_len_m)

    # Compute baffle x-positions along length; start at spacing (not at x=0)
    n_baffles = int(length_m // spacing_m)
    x_positions = [i * spacing_m for i in range(1, n_baffles + 1) if i * spacing_m <= length_m]

    # ---- figure & axes ----
    fig, (ax_long, ax_plan) = plt.subplots(2, 1, figsize=(8, 6))  # Smaller figure
    
    if shape == "round":
        title = f"Culvert {length_m:g}m | Ø{int(round(diameter_m*1000))}mm | Gradient {round(gradient*100,1)}%"
    else:
        title = f"Culvert {length_m:g}m | {int(round(box_w_m*1000))}×{int(round(box_h_m*1000))}mm | Gradient {round(gradient*100,1)}%"
    
    fig.suptitle(title, fontsize=16, fontweight='bold', y=0.89, color='#16416f')

    # Add border around the entire figure - but NOT around individual subplots
    fig.patch.set_edgecolor('#16416f')
    fig.patch.set_linewidth(3)

    # =========================
    # Longitudinal view (side profile with gradient)
    # =========================
    ax_long.set_title("LONGITUDINAL VIEW", fontweight='bold', fontsize=12, pad=0, color='#16416f', y=0.80)
    
    if shape == "round":
        radius = diameter_m / 2.0
        # Draw culvert outline with gradient - just the outline, no fill
        x_curve = np.linspace(0, length_m, 100)
        y_top = -x_curve * gradient + radius
        y_bottom = -x_curve * gradient - radius
        
        # Draw only the top and bottom curves of the pipe
        ax_long.plot(x_curve, y_top, color='#16416f', linewidth=2)
        ax_long.plot(x_curve, y_bottom, color='#16416f', linewidth=2)
        
        # Baffles at the BOTTOM of the culvert for fish passage
        for x in x_positions:
            y_bottom_at_x = -x * gradient - radius
            baffle_top = y_bottom_at_x + baffle_h_m
            
            # Draw baffle as thin vertical line
            ax_long.plot([x, x], [y_bottom_at_x, baffle_top], color='#16416f', linewidth=3)
            
        culvert_height = diameter_m
        
    else:  # box culvert
        height = box_h_m
        # Draw culvert outline with gradient
        x_line = np.array([0, length_m])
        y_top = -x_line * gradient + height/2
        y_bottom = -x_line * gradient - height/2
        
        ax_long.plot(x_line, y_top, color='#16416f', linewidth=2)
        ax_long.plot(x_line, y_bottom, color='#16416f', linewidth=2)
        
        # Baffles at the BOTTOM of the culvert
        for x in x_positions:
            y_bottom_at_x = -x * gradient - height/2
            baffle_top = y_bottom_at_x + baffle_h_m
            
            # Draw baffle as thin vertical line
            ax_long.plot([x, x], [y_bottom_at_x, baffle_top], color='#16416f', linewidth=3)
            
        culvert_height = box_h_m

    # Simple spacing dimension (between first two baffles) - positioned closer to baffles
    if len(x_positions) >= 2:
        x1, x2 = x_positions[0], x_positions[1]
        # Position the dimension line just above the baffles inside the culvert
        if shape == "round":
            y_dim = -((x1 + x2)/2) * gradient + diameter_m/4  # Inside the pipe, above center
        else:
            y_dim = -((x1 + x2)/2) * gradient + box_h_m/4     # Inside the box, above center
        
        # Simple dimension line with thicker arrows
        ax_long.annotate('', xy=(x1, y_dim), xytext=(x2, y_dim),
                        arrowprops=dict(arrowstyle='<->', color='#89ccea', lw=1))
        ax_long.text((x1+x2)/2, y_dim+0.08, f"Spacing = {int(round(spacing_m*1000))}mm", 
                    ha='center', va='bottom', fontsize=9, fontweight='bold', color='#16416f')

    # Baffle height dimension - proper extended arrows with extension lines
    if x_positions:
        x_ref = x_positions[-1]
        if shape == "round":
            y_bottom_ref = -x_ref * gradient - diameter_m/2 - 0.05
        else:
            y_bottom_ref = -x_ref * gradient - box_h_m/2 - 0.05
        
        y_top_ref = y_bottom_ref + baffle_h_m + 0.1
        x_dim = x_ref + 0.15  # Very close to baffle
        
        # Main dimension arrow with thicker line
        ax_long.annotate('', xy=(x_dim, y_bottom_ref), xytext=(x_dim, y_top_ref),
                        arrowprops=dict(arrowstyle='<->', color='#89ccea', lw=1))
        
        ax_long.text(x_dim+0.15, (y_bottom_ref + y_top_ref)/2, f"Baffle\nheight\n{int(round(baffle_h_m*1000))}mm", 
                    ha='left', va='center', fontsize=9, fontweight='bold', color='#16416f')

    # Clean up axes
    y_min = -length_m * gradient - culvert_height/2 - 0.4
    y_max = culvert_height/2 + 0.5
    # Clean up axes - remove boxes around views
    ax_long.set_xlim(-1.0, length_m + 1.0)  # Added more margin
    ax_long.set_ylim(y_min - 0.3, y_max + 0.3)  # Added top and bottom margin
    ax_long.axis('off')  # Remove all borders and ticks

    # ==============
    # Plan view (top-down) - cleaner version
    # ==============
    ax_plan.set_title("PLAN VIEW", fontweight='bold', fontsize=12, pad=0, color='#16416f', y=0.80)
    
    if shape == "round":
        radius = diameter_m / 2.0
        
        # Simple culvert outline - just two parallel lines
        ax_plan.plot([0, length_m], [radius, radius], color='#16416f', linewidth=2)
        ax_plan.plot([0, length_m], [-radius, -radius], color='#16416f', linewidth=2)
        
        culvert_width = diameter_m
        
    else:  # box culvert
        width = box_w_m
        height = box_h_m
        
        # Simple box outline
        ax_plan.plot([0, length_m], [height/2, height/2], color='#16416f', linewidth=2)
        ax_plan.plot([0, length_m], [-height/2, -height/2], color='#16416f', linewidth=2)
        ax_plan.plot([0, 0], [-height/2, height/2], color='#16416f', linewidth=2)
        ax_plan.plot([length_m, length_m], [-height/2, height/2], color='#16416f', linewidth=2)
        
        culvert_width = box_h_m

    # Placement text
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

    # Draw baffles in plan view with alternating logic for box culverts
    for i, x in enumerate(x_positions):
        if placement == "offset" and shape != "round":
            # Box culvert alternating pattern
            if i % 2 == 0:  # Even baffles: left side
                y_center = culvert_width/2 - baffle_len_m/2
            else:  # Odd baffles: right side  
                y_center = -culvert_width/2 + baffle_len_m/2
        else:
            # Standard centered or round offset positioning
            y_center = lateral_offset_m
        
        y1 = y_center - baffle_len_m/2
        y2 = y_center + baffle_len_m/2
        ax_plan.plot([x, x], [y1, y2], color='#16416f', linewidth=3)

    # Baffle length dimension - positioned closer to avoid overlap
    if x_positions:
        # Use the first baffle and position dimension closer
        x_ref = x_positions[0]
        if placement == "offset" and shape != "round":
            # For alternating baffles, show dimension on first (left side) baffle
            y_center = culvert_width/2 - baffle_len_m/2
        else:
            y_center = lateral_offset_m
        
        y1_ref = y_center - baffle_len_m/2
        y2_ref = y_center + baffle_len_m/2
        
        # Position dimension line closer to the baffle to avoid overlap with next baffle
        x_dim = x_ref + 0.15  # Much closer to avoid overlap
        ax_plan.annotate('', xy=(x_dim, y1_ref), xytext=(x_dim, y2_ref),
                        arrowprops=dict(arrowstyle='<->', color='#89ccea', lw=1))
        ax_plan.text(x_dim+0.05, y_center, f"Baffle\nlength\n{int(round(baffle_len_m*1000))}mm", 
                    ha='left', va='center', fontsize=9, fontweight='bold', color='#16416f')

    # Diameter label on the left side with a dimension line
    if shape == "round":
        # Left side diameter dimension
        x_diam = -0.3
        y_top_diam = radius
        y_bottom_diam = -radius
        
        ax_plan.annotate('', xy=(x_diam, y_bottom_diam), xytext=(x_diam, y_top_diam),
                        arrowprops=dict(arrowstyle='<->', color='#89ccea', lw=1))
        ax_plan.text(x_diam-0.1, 0, f"Ø{int(round(diameter_m*1000))}mm",
                    ha='right', va='center', fontsize=11, fontweight='bold', rotation=90, color='#16416f')

    # Length dimension at bottom
    y_length_dim = -culvert_width/2 - 0.3
    ax_plan.annotate('', xy=(0, y_length_dim), xytext=(length_m, y_length_dim),
                    arrowprops=dict(arrowstyle='<->', color='#89ccea', lw=1))
    ax_plan.text(length_m/2, y_length_dim-0.1, f"{length_m:g}m", 
                ha='center', va='top', fontsize=11, fontweight='bold', color='#16416f')

    # Clean up axes - remove boxes around views  
    ax_plan.set_xlim(-1.0, length_m + 1.0)  # Added more margin
    ax_plan.set_ylim(-culvert_width/2 - 0.8, culvert_width/2 + 1.2)  # Added margin, extra at top for text
    ax_plan.axis('off')  # Remove all borders and ticks

    plt.tight_layout()
    plt.subplots_adjust(top=0.90)
    
    # Add overall border to the figure
    fig.patch.set_edgecolor('#16416f')
    fig.patch.set_linewidth(3)
    
    plt.savefig(filename, dpi=80, bbox_inches='tight', facecolor='white')  # Reduced DPI
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
        # Debug: print request details
        print(f"Content-Type: {request.content_type}")
        print(f"Request data: {request.get_data()}")
        
        # Try multiple ways to get JSON data
        payload = None
        
        # Method 1: Standard JSON parsing
        try:
            payload = request.get_json()
        except:
            pass
            
        # Method 2: Force JSON parsing
        if not payload:
            try:
                payload = request.get_json(force=True)
            except:
                pass
        
        # Method 3: Manual JSON parsing
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

        # Generate unique filename for this request
        file_id = str(uuid.uuid4())
        permanent_filename = f"{file_id}.png"
        
        # Generate the drawing
        generate_drawing(payload, permanent_filename)
        
        # Read the file for base64 encoding (backup method)
        with open(permanent_filename, 'rb') as img_file:
            img_b64 = base64.b64encode(img_file.read()).decode("utf-8")

        # Return both download URL and base64 (for flexibility)
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
