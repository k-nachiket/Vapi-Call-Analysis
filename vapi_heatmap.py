"""
VAPI Heatmap Visualization Logic
Shared module for generating 3D and 2D heatmaps from VAPI call data.
"""

from collections import Counter
import plotly.graph_objects as go


def extract_dimensions_from_call(call_info: dict) -> tuple[str, str, str] | None:
    """Extract the three dimensions from a call info dict."""
    try:
        data = call_info.get('data', {})
        if not data:
            return None

        caller_type = data.get("caller_type", "unknown")
        call_summary = data.get("call_summary", {})
        resolution_type = call_summary.get("resolution_type", "unknown")
        primary_intent = call_summary.get("primary_intent", "unknown")

        return (resolution_type or "unknown", caller_type or "unknown", primary_intent or "unknown")
    except Exception:
        return None


def aggregate_vapi_data(all_files: list) -> dict:
    """Aggregate counts for each (resolution_type, caller_type, primary_intent) combination."""
    counts = Counter()

    for call_info in all_files:
        dims = extract_dimensions_from_call(call_info)
        if dims:
            counts[dims] += 1

    return counts


def create_figure_3d(counts: Counter, min_count: int = 1, dark_mode: bool = False) -> go.Figure:
    """Create the 3D scatter plot figure."""
    resolution_types = sorted(set(k[0] for k in counts.keys()))
    caller_types = sorted(set(k[1] for k in counts.keys()))
    primary_intents = sorted(set(k[2] for k in counts.keys()))

    res_to_idx = {v: i for i, v in enumerate(resolution_types)}
    caller_to_idx = {v: i for i, v in enumerate(caller_types)}
    intent_to_idx = {v: i for i, v in enumerate(primary_intents)}

    x_vals = []
    y_vals = []
    z_vals = []
    sizes = []
    colors = []
    hover_texts = []

    max_count = max(counts.values()) if counts else 1

    for (res_type, caller_type, intent), count in counts.items():
        if count >= min_count:
            x_vals.append(res_to_idx[res_type])
            y_vals.append(caller_to_idx[caller_type])
            z_vals.append(intent_to_idx[intent])

            size = 8 + (count / max_count) * 42
            sizes.append(size)
            colors.append(count)

            hover_text = (
                f"<b>Count: {count}</b><br>"
                f"Resolution: {res_type}<br>"
                f"Caller: {caller_type}<br>"
                f"Intent: {intent}"
            )
            hover_texts.append(hover_text)

    fig = go.Figure(data=[go.Scatter3d(
        x=x_vals,
        y=y_vals,
        z=z_vals,
        mode='markers',
        marker=dict(
            size=sizes,
            color=colors,
            colorscale='Viridis',
            opacity=0.85,
            colorbar=dict(title="Call Count", thickness=20, len=0.7),
            line=dict(width=1, color='white')
        ),
        text=hover_texts,
        hoverinfo='text',
        hoverlabel=dict(bgcolor='rgba(30,30,30,0.9)', font_size=13, font_family='Inter, sans-serif')
    )])

    # Theme configuration
    text_color = '#e0e0e0' if dark_mode else '#1a1a2e'
    axis_color_res = '#a5b4fc' if dark_mode else '#4361ee'
    axis_color_caller = '#d8b4fe' if dark_mode else '#7209b7'
    axis_color_intent = '#f9a8d4' if dark_mode else '#f72585'
    grid_color = 'rgba(255,255,255,0.1)' if dark_mode else 'rgba(100,100,100,0.3)'
    bg_color_axis = 'rgba(0,0,0,0)' if dark_mode else 'rgba(240,245,255,0.8)'
    bg_color_paper = 'rgba(0,0,0,0)' if dark_mode else '#fafbff'

    fig.update_layout(
        title=dict(text='<b>3D VAPI Call Analysis</b>', font=dict(size=24, color=text_color, family='Inter, sans-serif'), x=0.5),
        scene=dict(
            xaxis=dict(
                title=dict(text='Resolution Type', font=dict(size=14, color=axis_color_res)),
                ticktext=resolution_types,
                tickvals=list(range(len(resolution_types))),
                tickfont=dict(size=10, color=text_color),
                gridcolor=grid_color,
                backgroundcolor=bg_color_axis
            ),
            yaxis=dict(
                title=dict(text='Caller Type', font=dict(size=14, color=axis_color_caller)),
                ticktext=caller_types,
                tickvals=list(range(len(caller_types))),
                tickfont=dict(size=10, color=text_color),
                gridcolor=grid_color,
                backgroundcolor=bg_color_axis
            ),
            zaxis=dict(
                title=dict(text='Primary Intent', font=dict(size=14, color=axis_color_intent)),
                ticktext=primary_intents,
                tickvals=list(range(len(primary_intents))),
                tickfont=dict(size=10, color=text_color),
                gridcolor=grid_color,
                backgroundcolor=bg_color_axis
            ),
            camera=dict(eye=dict(x=1.8, y=1.8, z=1.2)),
            aspectmode='cube'
        ),
        margin=dict(l=10, r=10, t=60, b=10),
        paper_bgcolor=bg_color_paper,
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family='Inter, system-ui, sans-serif')
    )
    return fig


def create_figure_2d(counts: Counter, dim1_idx: int, dim2_idx: int, dim1_name: str, dim2_name: str, title: str, dark_mode: bool = False) -> go.Figure:
    """Create a 2D Heatmap figure."""

    # 0=Resolution, 1=Caller, 2=Intent

    # Aggregate data for 2D
    agg_counts = Counter()
    dim1_vals = set()
    dim2_vals = set()

    for key, count in counts.items():
        v1 = key[dim1_idx]
        v2 = key[dim2_idx]
        agg_counts[(v1, v2)] += count
        dim1_vals.add(v1)
        dim2_vals.add(v2)

    sorted_d1 = sorted(dim1_vals)
    sorted_d2 = sorted(dim2_vals)

    z_data = [[0] * len(sorted_d1) for _ in range(len(sorted_d2))]
    text_data = [[""] * len(sorted_d1) for _ in range(len(sorted_d2))]

    # Calculate total for percentages
    total_count = sum(agg_counts.values())

    for r, d2 in enumerate(sorted_d2):
        for c, d1 in enumerate(sorted_d1):
            val = agg_counts.get((d1, d2), 0)
            z_data[r][c] = val
            if val > 0:
                pct = (val / total_count) * 100
                text_data[r][c] = f"{val}<br>({pct:.1f}%)"
            else:
                text_data[r][c] = ""

    # Theme config
    text_color = '#e0e0e0' if dark_mode else '#333'
    bg_color = 'rgba(0,0,0,0)' if dark_mode else 'white'
    colorscale = 'Blues'

    fig = go.Figure(data=go.Heatmap(
        z=z_data,
        x=sorted_d1,
        y=sorted_d2,
        text=text_data,
        texttemplate="%{text}",
        textfont={"size": 10},
        colorscale=colorscale,
        colorbar=dict(
            title=dict(text="Count", font=dict(color=text_color)),
            tickfont=dict(color=text_color)
        )
    ))

    fig.update_layout(
        title=dict(text=f'<b>{title}</b>', x=0.5, font=dict(size=20, color=text_color)),
        xaxis=dict(title=dict(text=dim1_name, font=dict(color=text_color)), tickangle=45, tickfont=dict(color=text_color)),
        yaxis=dict(title=dict(text=dim2_name, font=dict(color=text_color)), tickfont=dict(color=text_color)),
        template="plotly_dark" if dark_mode else "plotly_white",
        height=700,
        margin=dict(b=100),
        paper_bgcolor=bg_color,
        plot_bgcolor=bg_color
    )
    return fig
