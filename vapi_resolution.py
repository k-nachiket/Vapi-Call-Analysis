"""
Streamlit UI for filtering and viewing VAPI call transcripts by resolution type

Usage:
    streamlit run vapi_resolution.py -- --file vapi_extracted_calls_analysed.json
    streamlit run vapi_resolution.py  # defaults to vapi_extracted_calls_analysed.json
"""

import streamlit as st
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import argparse


def parse_cli_args():
    """Parse command-line arguments passed after -- in streamlit run command."""
    try:
        parser = argparse.ArgumentParser(description='VAPI Resolution Filter UI')
        parser.add_argument(
            '-f', '--file',
            type=str,
            default='vapi_extracted_calls_analysed.json',
            help='Path to the JSON file containing analyzed VAPI calls'
        )
        args, _ = parser.parse_known_args()
        return args
    except Exception:
        return None


CLI_ARGS = parse_cli_args()

# Page config
st.set_page_config(
    page_title="VAPI Resolution Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .flow-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 20px;
        padding: 20px 0;
    }

    .transcript-container textarea,
    div[data-baseweb="textarea"] textarea {
        background-color: var(--background-color) !important;
        color: var(--text-color) !important;
        font-family: 'Georgia', serif;
        line-height: 1.8;
        font-size: var(--transcript-font-size, 14px) !important;
    }

    .json-container,
    .json-container *,
    div[data-testid="stJson"] pre,
    div[data-testid="stJson"] code {
        font-size: var(--json-font-size, 14px) !important;
        line-height: 1.6 !important;
    }

    .stJson {
        background-color: var(--secondary-background-color);
        height: 700px;
        overflow-y: auto;
    }
</style>
""", unsafe_allow_html=True)


def get_duration_from_call(call: dict) -> float | None:
    """Get call duration in seconds from durationSeconds field."""
    duration = call.get('durationSeconds')
    if duration is not None:
        try:
            return float(duration)
        except (TypeError, ValueError):
            pass
    return None


@st.cache_data
def load_vapi_data(file_path: str):
    """Load VAPI call data from JSON file and extract resolution info."""
    json_files = {}
    resolution_types = defaultdict(list)

    with open(file_path, 'r', encoding='utf-8') as f:
        calls = json.load(f)

    for idx, call in enumerate(calls):
        # Skip calls without llm_analysis or with errors
        llm_analysis = call.get('llm_analysis')
        if not llm_analysis or (isinstance(llm_analysis, dict) and 'error' in llm_analysis):
            continue

        # Extract fields from llm_analysis
        call_summary = llm_analysis.get('call_summary', {})
        resolution_type = call_summary.get('resolution_type')
        final_outcome = call_summary.get('final_outcome', '') or ''
        resolution_achieved = call_summary.get('resolution_achieved')
        secondary_action = call_summary.get('secondary_action')
        primary_intent = call_summary.get('primary_intent')

        caller_type = llm_analysis.get('caller_type', 'unknown')
        if not caller_type or not isinstance(caller_type, str):
            caller_type = 'unknown'

        # Extract transfer info
        transfer_context = llm_analysis.get('transfer_context', {})
        transfer_destination = None
        transfer_success = None

        if transfer_context and isinstance(transfer_context, dict):
            transfer_connection_status = transfer_context.get('transfer_connection_status')

            destinations = transfer_context.get('destinations')
            if isinstance(destinations, list) and destinations:
                for d in destinations:
                    if isinstance(d, str) and d:
                        transfer_destination = d
                        break
            elif isinstance(destinations, str) and destinations:
                transfer_destination = destinations

            if isinstance(transfer_connection_status, list):
                if len(transfer_connection_status) == 0:
                    transfer_success = None
                else:
                    bool_values = [v for v in transfer_connection_status if isinstance(v, bool)]
                    if bool_values:
                        transfer_success = True if any(bool_values) else False
                    else:
                        transfer_success = None

        # Get transcript and convert \n to actual newlines
        transcript = call.get('transcript', '')
        if transcript:
            transcript = transcript.replace('\\n', '\n')

        # Extract call duration from durationSeconds field
        call_duration = get_duration_from_call(call)

        # Extract assistantId and squadId for filtering
        assistant_id = call.get('assistantId') or 'unknown'
        squad_id = call.get('squadId') or 'none'

        # Store file info
        call_id = call.get('id', f'call_{idx}')
        file_info = {
            'id': call_id,
            'index': idx,
            'resolution_type': resolution_type or 'no_resolution_type',
            'caller_type': caller_type,
            'final_outcome': final_outcome,
            'resolution_achieved': resolution_achieved,
            'transfer_success': transfer_success,
            'transfer_destination': transfer_destination,
            'secondary_action': secondary_action,
            'primary_intent': primary_intent,
            'transcript_content': transcript,
            'call_duration': call_duration,
            'assistant_id': assistant_id,
            'squad_id': squad_id,
            'data': llm_analysis,
            'raw_call': call,
            'has_resolution_type': resolution_type is not None
        }

        json_files[call_id] = file_info
        resolution_type_key = resolution_type or 'no_resolution_type'
        resolution_types[resolution_type_key].append(file_info)

    return json_files, dict(resolution_types)


def render_resolution_flow(all_files: list, resolution_types: dict):
    """Render a Plotly Sankey diagram showing call resolution breakdown."""
    import plotly.graph_objects as go

    total = len(all_files)
    if total == 0:
        st.warning("No data available for Sankey visualization")
        return

    # Calculate resolved vs unresolved
    resolved_count = sum(1 for f in all_files if f.get('resolution_achieved') is True)
    unresolved_count = sum(1 for f in all_files if f.get('resolution_achieved') is False)
    unknown_count = total - resolved_count - unresolved_count

    resolved_pct = (resolved_count / total * 100) if total else 0
    unresolved_pct = (unresolved_count / total * 100) if total else 0
    unknown_pct = (unknown_count / total * 100) if total else 0

    # Calculate resolution types from resolved calls
    resolved_files = [f for f in all_files if f.get('resolution_achieved') is True]
    type_counts = defaultdict(int)
    type_files = defaultdict(list)
    for f in resolved_files:
        res_type = f.get('resolution_type', 'no_resolution_type')
        type_counts[res_type] += 1
        type_files[res_type].append(f)

    # Calculate resolution types from UNRESOLVED calls (for expansion)
    unresolved_files = [f for f in all_files if f.get('resolution_achieved') is False]
    unresolved_type_counts = defaultdict(int)
    unresolved_type_files = defaultdict(list)
    for f in unresolved_files:
        res_type = f.get('resolution_type', 'no_resolution_type')
        unresolved_type_counts[res_type] += 1
        unresolved_type_files[res_type].append(f)

    # Calculate transfer breakdown
    transfer_files = [f for f in all_files if f.get('resolution_type') in ['transfer', 'transfer_attempted']]
    transfer_success = sum(1 for f in transfer_files if f.get('transfer_success') is True)
    transfer_failed = sum(1 for f in transfer_files if f.get('transfer_success') is False)
    transfer_unknown = len(transfer_files) - transfer_success - transfer_failed

    # Track source files per link
    link_sources = {}
    link_index = 0

    # ===== Diagram Controls =====
    st.markdown("### ⚙️ Diagram Controls")

    # Row 1: Primary splits
    row1_cols = st.columns(4)
    with row1_cols[0]:
        show_resolution_types = st.checkbox("Show Resolution Types", value=True, key="show_res_types",
                                           help="Show resolution type breakdown for resolved calls")
    with row1_cols[1]:
        split_by_caller_type = st.checkbox("Split by Caller Type", value=False, key="split_caller_type",
                                          help="Show caller type breakdown after resolved/unresolved")
    with row1_cols[2]:
        expand_unresolved = st.checkbox("Expand Unresolved", value=False, key="expand_unresolved",
                                       help="Show resolution types breakdown for unresolved calls")
    with row1_cols[3]:
        st.write("")

    # Row 2: Transfer-related options
    row2_cols = st.columns(4)
    with row2_cols[0]:
        show_transfer_outcomes = st.checkbox("Show Transfer Outcomes", value=True, key="show_transfer_outcomes",
                                            help="Toggle visibility of transfer success/failure breakdown")
    with row2_cols[1]:
        show_transfer_destinations = st.checkbox("Show Transfer Destinations", value=False, key="show_transfer_destinations",
                                                help="Expand transfer outcomes into their destinations")
    with row2_cols[2]:
        show_secondary_actions = st.checkbox("Show Secondary Actions", value=False, key="show_secondary_actions",
                                            help="Show secondary actions taken after transfers",
                                            disabled=not show_transfer_outcomes)
    with row2_cols[3]:
        st.write("")

    st.markdown("---")

    # ===== Build Sankey diagram =====
    nodes = [f"All Calls ({total})"]
    node_colors = ["#667eea"]

    nodes.append(f"Resolved ({resolved_count}, {resolved_pct:.1f}%)")
    node_colors.append("#22c55e")

    nodes.append(f"Unresolved ({unresolved_count}, {unresolved_pct:.1f}%)")
    node_colors.append("#ef4444")

    has_unknown = unknown_count > 0
    if has_unknown:
        nodes.append(f"Unknown ({unknown_count}, {unknown_pct:.1f}%)")
        node_colors.append("#94a3b8")

    sources = []
    targets = []
    values = []
    link_colors = []
    link_labels = []

    resolved_files_list = [f for f in all_files if f.get('resolution_achieved') is True]
    unresolved_files_list = [f for f in all_files if f.get('resolution_achieved') is False]
    unknown_files_list = [f for f in all_files if f.get('resolution_achieved') is None]

    if resolved_count > 0:
        sources.append(0)
        targets.append(1)
        values.append(resolved_count)
        link_colors.append("rgba(34, 197, 94, 0.4)")
        link_sources[link_index] = resolved_files_list
        link_labels.append(f"All Calls → Resolved: {resolved_count}")
        link_index += 1

    if unresolved_count > 0:
        sources.append(0)
        targets.append(2)
        values.append(unresolved_count)
        link_colors.append("rgba(239, 68, 68, 0.4)")
        link_sources[link_index] = unresolved_files_list
        link_labels.append(f"All Calls → Unresolved: {unresolved_count}")
        link_index += 1

    if has_unknown and unknown_count > 0:
        sources.append(0)
        targets.append(3)
        values.append(unknown_count)
        link_colors.append("rgba(148, 163, 184, 0.4)")
        link_sources[link_index] = unknown_files_list
        link_labels.append(f"All Calls → Unknown: {unknown_count}")
        link_index += 1

    # ===== CALLER TYPE SPLIT =====
    if split_by_caller_type:
        resolved_by_caller = defaultdict(list)
        unresolved_by_caller = defaultdict(list)

        for f in all_files:
            ct = f.get('caller_type', 'unknown')
            if f.get('resolution_achieved') is True:
                resolved_by_caller[ct].append(f)
            elif f.get('resolution_achieved') is False:
                unresolved_by_caller[ct].append(f)

        caller_type_colors = [
            "#06b6d4", "#8b5cf6", "#f59e0b", "#10b981", "#f43f5e",
            "#6366f1", "#84cc16", "#ec4899", "#14b8a6", "#a855f7"
        ]

        resolved_node_idx = 1
        unresolved_node_idx = 2

        if resolved_by_caller:
            sorted_resolved_callers = sorted(resolved_by_caller.items(), key=lambda x: len(x[1]), reverse=True)
            for idx, (ct, files) in enumerate(sorted_resolved_callers):
                pct = (len(files) / resolved_count * 100) if resolved_count else 0
                node_label = f"{ct.replace('_', ' ').title()} ({len(files)}, {pct:.1f}%)"
                ct_node_idx = len(nodes)
                nodes.append(node_label)
                color_idx = idx % len(caller_type_colors)
                node_colors.append(caller_type_colors[color_idx])

                sources.append(resolved_node_idx)
                targets.append(ct_node_idx)
                values.append(len(files))
                link_colors.append(f"rgba({int(caller_type_colors[color_idx][1:3], 16)}, {int(caller_type_colors[color_idx][3:5], 16)}, {int(caller_type_colors[color_idx][5:7], 16)}, 0.4)")
                link_sources[link_index] = files
                link_labels.append(f"Resolved → {ct}: {len(files)}")
                link_index += 1

        if unresolved_by_caller:
            sorted_unresolved_callers = sorted(unresolved_by_caller.items(), key=lambda x: len(x[1]), reverse=True)
            for idx, (ct, files) in enumerate(sorted_unresolved_callers):
                pct = (len(files) / unresolved_count * 100) if unresolved_count else 0
                node_label = f"{ct.replace('_', ' ').title()} ({len(files)}, {pct:.1f}%)"
                ct_node_idx = len(nodes)
                nodes.append(node_label)
                color_idx = idx % len(caller_type_colors)
                node_colors.append(caller_type_colors[color_idx])

                sources.append(unresolved_node_idx)
                targets.append(ct_node_idx)
                values.append(len(files))
                link_colors.append(f"rgba({int(caller_type_colors[color_idx][1:3], 16)}, {int(caller_type_colors[color_idx][3:5], 16)}, {int(caller_type_colors[color_idx][5:7], 16)}, 0.4)")
                link_sources[link_index] = files
                link_labels.append(f"Unresolved → {ct}: {len(files)}")
                link_index += 1

    # Add resolution type nodes (from resolved calls only)
    resolved_node_idx = 1
    type_node_start = len(nodes)
    sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)

    type_colors = [
        "#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", "#14b8a6",
        "#6366f1", "#f97316", "#06b6d4", "#84cc16", "#a855f7"
    ]

    transfer_type_indices = []

    if show_resolution_types:
        for idx, (res_type, count) in enumerate(sorted_types):
            is_transfer = res_type in ['transfer', 'transfer_attempted']
            pct = (count / resolved_count * 100) if resolved_count else 0
            node_label = f"{res_type.replace('_', ' ').title()} ({count}, {pct:.1f}%)"
            nodes.append(node_label)

            color_idx = idx % len(type_colors)
            node_colors.append(type_colors[color_idx])

            type_node_idx = type_node_start + idx

            if is_transfer:
                transfer_type_indices.append(type_node_idx)

            sources.append(resolved_node_idx)
            targets.append(type_node_idx)
            values.append(count)
            link_colors.append(f"rgba({int(type_colors[color_idx][1:3], 16)}, {int(type_colors[color_idx][3:5], 16)}, {int(type_colors[color_idx][5:7], 16)}, 0.4)")
            link_sources[link_index] = type_files[res_type]
            link_labels.append(f"Resolved → {res_type}: {count}")
            link_index += 1

    # ===== UNRESOLVED EXPANSION =====
    unresolved_node_idx = 2
    if expand_unresolved and unresolved_count > 0:
        unresolved_type_node_start = len(nodes)
        sorted_unresolved_types = sorted(unresolved_type_counts.items(), key=lambda x: x[1], reverse=True)

        unresolved_type_colors = [
            "#dc2626", "#ea580c", "#d97706", "#ca8a04", "#b91c1c",
            "#c2410c", "#b45309", "#a16207", "#991b1b", "#9a3412"
        ]

        for idx, (res_type, count) in enumerate(sorted_unresolved_types):
            pct = (count / unresolved_count * 100) if unresolved_count else 0
            node_label = f"{res_type.replace('_', ' ').title()} ({count}, {pct:.1f}%)"
            nodes.append(node_label)

            color_idx = idx % len(unresolved_type_colors)
            node_colors.append(unresolved_type_colors[color_idx])

            unres_type_node_idx = unresolved_type_node_start + idx

            sources.append(unresolved_node_idx)
            targets.append(unres_type_node_idx)
            values.append(count)
            link_colors.append(f"rgba({int(unresolved_type_colors[color_idx][1:3], 16)}, {int(unresolved_type_colors[color_idx][3:5], 16)}, {int(unresolved_type_colors[color_idx][5:7], 16)}, 0.4)")
            link_sources[link_index] = unresolved_type_files[res_type]
            link_labels.append(f"Unresolved → {res_type}: {count}")
            link_index += 1

    # Add transfer outcome nodes
    transfer_total = len(transfer_files)
    success_pct = (transfer_success / transfer_total * 100) if transfer_total else 0
    failed_pct = (transfer_failed / transfer_total * 100) if transfer_total else 0
    unknown_transfer_pct = (transfer_unknown / transfer_total * 100) if transfer_total else 0

    transfer_success_files = [f for f in transfer_files if f.get('transfer_success') is True]
    transfer_failed_files = [f for f in transfer_files if f.get('transfer_success') is False]
    transfer_unknown_files = [f for f in transfer_files if f.get('transfer_success') is None]

    success_idx = None
    failed_idx = None
    unknown_idx = None

    if show_resolution_types and show_transfer_outcomes and transfer_files and (transfer_success > 0 or transfer_failed > 0 or transfer_unknown > 0):
        if transfer_success > 0:
            success_idx = len(nodes)
            nodes.append(f"Transfer Connected ({transfer_success}, {success_pct:.1f}%)")
            node_colors.append("#22c55e")

        if transfer_failed > 0:
            failed_idx = len(nodes)
            nodes.append(f"Transfer Failed ({transfer_failed}, {failed_pct:.1f}%)")
            node_colors.append("#ef4444")

        if transfer_unknown > 0:
            unknown_idx = len(nodes)
            nodes.append(f"Transfer Unknown ({transfer_unknown}, {unknown_transfer_pct:.1f}%)")
            node_colors.append("#94a3b8")

        for res_type in ['transfer', 'transfer_attempted']:
            if res_type not in type_counts:
                continue

            type_idx = None
            for i, (t, c) in enumerate(sorted_types):
                if t == res_type:
                    type_idx = type_node_start + i
                    break

            if type_idx is None:
                continue

            res_type_files = type_files[res_type]
            success_files = [f for f in res_type_files if f.get('transfer_success') is True]
            failed_files_list = [f for f in res_type_files if f.get('transfer_success') is False]
            unknown_files = [f for f in res_type_files if f.get('transfer_success') is None]

            if success_files and success_idx is not None:
                sources.append(type_idx)
                targets.append(success_idx)
                values.append(len(success_files))
                link_colors.append("rgba(34, 197, 94, 0.4)")
                link_sources[link_index] = success_files
                link_labels.append(f"{res_type} → Connected: {len(success_files)}")
                link_index += 1

            if failed_files_list and failed_idx is not None:
                sources.append(type_idx)
                targets.append(failed_idx)
                values.append(len(failed_files_list))
                link_colors.append("rgba(239, 68, 68, 0.4)")
                link_sources[link_index] = failed_files_list
                link_labels.append(f"{res_type} → Failed: {len(failed_files_list)}")
                link_index += 1

            if unknown_files and unknown_idx is not None:
                sources.append(type_idx)
                targets.append(unknown_idx)
                values.append(len(unknown_files))
                link_colors.append("rgba(148, 163, 184, 0.4)")
                link_sources[link_index] = unknown_files
                link_labels.append(f"{res_type} → Unknown: {len(unknown_files)}")
                link_index += 1

    # ===== TRANSFER DESTINATION EXPANSION =====
    if show_transfer_destinations and show_resolution_types and show_transfer_outcomes and transfer_files:
        success_by_dest = defaultdict(list)
        failed_by_dest = defaultdict(list)

        for f in transfer_files:
            dest = f.get('transfer_destination') or 'Unknown Destination'
            ts = f.get('transfer_success')
            if ts is True:
                success_by_dest[dest].append(f)
            elif ts is False:
                failed_by_dest[dest].append(f)

        success_dest_colors = ["#16a34a", "#15803d", "#166534", "#14532d", "#22c55e"]
        failed_dest_colors = ["#dc2626", "#b91c1c", "#991b1b", "#7f1d1d", "#ef4444"]

        if success_by_dest and success_idx is not None:
            sorted_success_dests = sorted(success_by_dest.items(), key=lambda x: len(x[1]), reverse=True)
            for idx, (dest, files) in enumerate(sorted_success_dests):
                pct = (len(files) / transfer_success * 100) if transfer_success else 0
                node_label = f"{dest.replace('_', ' ').title()} ({len(files)}, {pct:.1f}%)"
                dest_node_idx = len(nodes)
                nodes.append(node_label)
                node_colors.append(success_dest_colors[idx % len(success_dest_colors)])

                sources.append(success_idx)
                targets.append(dest_node_idx)
                values.append(len(files))
                link_colors.append("rgba(22, 163, 74, 0.4)")
                link_sources[link_index] = files
                link_labels.append(f"Connected → {dest}: {len(files)}")
                link_index += 1

        if failed_by_dest and failed_idx is not None:
            sorted_failed_dests = sorted(failed_by_dest.items(), key=lambda x: len(x[1]), reverse=True)
            for idx, (dest, files) in enumerate(sorted_failed_dests):
                pct = (len(files) / transfer_failed * 100) if transfer_failed else 0
                node_label = f"{dest.replace('_', ' ').title()} ({len(files)}, {pct:.1f}%)"
                dest_node_idx = len(nodes)
                nodes.append(node_label)
                node_colors.append(failed_dest_colors[idx % len(failed_dest_colors)])

                sources.append(failed_idx)
                targets.append(dest_node_idx)
                values.append(len(files))
                link_colors.append("rgba(220, 38, 38, 0.4)")
                link_sources[link_index] = files
                link_labels.append(f"Failed → {dest}: {len(files)}")
                link_index += 1

    # ===== SECONDARY ACTION SPLIT =====
    if show_secondary_actions and show_resolution_types and show_transfer_outcomes and transfer_files:
        success_by_action = defaultdict(list)
        failed_by_action = defaultdict(list)

        for f in transfer_files:
            sa = f.get('secondary_action') or 'no_secondary_action'
            ts = f.get('transfer_success')
            if ts is True:
                success_by_action[sa].append(f)
            elif ts is False:
                failed_by_action[sa].append(f)

        action_colors = [
            "#0ea5e9", "#a855f7", "#f97316", "#22d3ee", "#e879f9",
            "#fb923c", "#38bdf8", "#c084fc", "#fdba74"
        ]

        if success_by_action and success_idx is not None:
            sorted_success_actions = sorted(success_by_action.items(), key=lambda x: len(x[1]), reverse=True)
            for idx, (action, files) in enumerate(sorted_success_actions):
                if action == 'no_secondary_action':
                    continue
                pct = (len(files) / transfer_success * 100) if transfer_success else 0
                node_label = f"{action.replace('_', ' ').title()} ({len(files)}, {pct:.1f}%)"
                action_node_idx = len(nodes)
                nodes.append(node_label)
                color_idx = idx % len(action_colors)
                node_colors.append(action_colors[color_idx])

                sources.append(success_idx)
                targets.append(action_node_idx)
                values.append(len(files))
                link_colors.append(f"rgba({int(action_colors[color_idx][1:3], 16)}, {int(action_colors[color_idx][3:5], 16)}, {int(action_colors[color_idx][5:7], 16)}, 0.4)")
                link_sources[link_index] = files
                link_labels.append(f"Connected → {action}: {len(files)}")
                link_index += 1

        if failed_by_action and failed_idx is not None:
            sorted_failed_actions = sorted(failed_by_action.items(), key=lambda x: len(x[1]), reverse=True)
            for idx, (action, files) in enumerate(sorted_failed_actions):
                if action == 'no_secondary_action':
                    continue
                pct = (len(files) / transfer_failed * 100) if transfer_failed else 0
                node_label = f"{action.replace('_', ' ').title()} ({len(files)}, {pct:.1f}%)"
                action_node_idx = len(nodes)
                nodes.append(node_label)
                color_idx = idx % len(action_colors)
                node_colors.append(action_colors[color_idx])

                sources.append(failed_idx)
                targets.append(action_node_idx)
                values.append(len(files))
                link_colors.append(f"rgba({int(action_colors[color_idx][1:3], 16)}, {int(action_colors[color_idx][3:5], 16)}, {int(action_colors[color_idx][5:7], 16)}, 0.4)")
                link_sources[link_index] = files
                link_labels.append(f"Failed → {action}: {len(files)}")
                link_index += 1

    # Create Sankey diagram
    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=20,
            thickness=25,
            line=dict(color="rgba(0,0,0,0.3)", width=1),
            label=nodes,
            color=node_colors,
            hovertemplate='%{label}<extra></extra>'
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=link_colors,
            customdata=list(range(len(sources))),
            hovertemplate='%{source.label} → %{target.label}<br>Count: %{value}<extra></extra>'
        )
    )])

    fig.update_layout(
        title=dict(text="VAPI Resolution Flow Analysis", font=dict(size=20, color="#f1f5f9")),
        font=dict(size=12, color="#e2e8f0"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=600,
        margin=dict(l=20, r=20, t=60, b=20)
    )

    st.markdown("## 📊 Resolution Flow Analysis")
    st.markdown("Interactive Sankey diagram showing call resolution breakdown")
    st.plotly_chart(fig, width="stretch")

    # Flow selector
    st.markdown("---")
    st.markdown("### 📁 View Source Calls by Flow")

    flow_options = ["Select a flow to view source calls..."]
    for idx, label in enumerate(link_labels):
        count = len(link_sources.get(idx, []))
        flow_options.append(f"{label} ({count} calls)")

    selected_flow = st.selectbox("Select a flow", options=flow_options, index=0, label_visibility="collapsed")

    if selected_flow != flow_options[0]:
        selected_idx = flow_options.index(selected_flow) - 1
        if selected_idx in link_sources:
            selected_files = link_sources[selected_idx]
            st.markdown(f"**{len(selected_files)} calls** in this flow")

            for i, file_info in enumerate(selected_files[:30]):
                call_id = file_info.get('id', 'Unknown')

                with st.expander(f"📄 Call: {call_id}", expanded=False):
                    tab1, tab2 = st.tabs(["JSON Data", "Transcript"])

                    with tab1:
                        st.json(file_info.get('data', {}))

                    with tab2:
                        transcript = file_info.get('transcript_content')
                        if transcript:
                            st.text_area("Transcript", transcript, height=300, key=f"trans_{i}")
                        else:
                            st.info("No transcript available.")

            if len(selected_files) > 30:
                st.info(f"Showing first 30 of {len(selected_files)} calls. Use Analysis Deep Dive for full access.")


def main():
    """Main app function."""
    st.title("📊 VAPI Resolution Analytics")
    st.markdown("Visual analytics and deep-dive tools for VAPI call resolution data")

    # Sidebar navigation
    st.sidebar.header("📍 Navigation")
    page = st.sidebar.radio(
        "Select View",
        options=["📊 Resolution Flow", "🔥 Heatmap Analysis", "🔍 Analysis Deep Dive"],
        index=0,
        help="Switch between flowchart visualization and detailed analysis"
    )
    st.sidebar.markdown("---")

    # File selection
    st.sidebar.header("⚙️ Settings")

    default_file = CLI_ARGS.file if CLI_ARGS else 'vapi_extracted_calls_analysed.json'
    file_path = st.sidebar.text_input("Data File", value=default_file, help="Path to JSON file with analyzed VAPI calls")

    if not Path(file_path).exists():
        st.error(f"❌ File not found: {file_path}")
        return

    # Load data
    with st.spinner("Loading VAPI call data..."):
        json_files, resolution_types = load_vapi_data(file_path)

    if not json_files:
        st.warning("No calls with valid LLM analysis found")
        return

    # Summary
    st.sidebar.markdown("---")
    total_files_count = len(json_files)
    resolution_types_count = len([rt for rt in resolution_types.keys() if rt != 'no_resolution_type'])

    st.sidebar.metric("Total Calls", total_files_count)
    st.sidebar.metric("Resolution Types", resolution_types_count)

    all_files = list(json_files.values())

    # Page routing
    if page == "📊 Resolution Flow":
        render_resolution_flow(all_files, resolution_types)
        return

    if page == "🔥 Heatmap Analysis":
        st.header("🔥 Heatmap Analysis")
        st.info("Explore call data distribution across Resolution, Caller Type, and Primary Intent dimensions.")
        try:
            from vapi_heatmap import aggregate_vapi_data, create_figure_3d, create_figure_2d

            col1, col2 = st.columns([1, 3])

            with col1:
                st.subheader("Visualization Settings")
                heatmap_view = st.radio(
                    "Select Dimension View",
                    ["3D Cube Analysis", "Resolution vs Caller", "Resolution vs Intent", "Caller vs Intent"],
                    index=0
                )
                min_count = st.slider("Minimum Call Count", 1, 10, 1, help="Filter out rare combinations")

                st.markdown("---")
                st.markdown("### Dimensions Legend")
                st.markdown("**X-Axis**: Resolution Type")
                st.markdown("**Y-Axis**: Caller Type")
                st.markdown("**Z-Axis**: Primary Intent")

            with col2:
                counts = aggregate_vapi_data(all_files)

                if heatmap_view == "3D Cube Analysis":
                    fig = create_figure_3d(counts, min_count=min_count, dark_mode=True)
                    st.plotly_chart(fig, width="stretch", height=700)
                elif heatmap_view == "Resolution vs Caller":
                    fig = create_figure_2d(counts, 0, 1, "Resolution Type", "Caller Type", "Resolution vs Caller Type", dark_mode=True)
                    st.plotly_chart(fig, width="stretch")
                elif heatmap_view == "Resolution vs Intent":
                    fig = create_figure_2d(counts, 0, 2, "Resolution Type", "Primary Intent", "Resolution vs Primary Intent", dark_mode=True)
                    st.plotly_chart(fig, width="stretch")
                elif heatmap_view == "Caller vs Intent":
                    fig = create_figure_2d(counts, 1, 2, "Caller Type", "Primary Intent", "Caller Type vs Primary Intent", dark_mode=True)
                    st.plotly_chart(fig, width="stretch")
        except ImportError as e:
            st.error(f"Could not import vapi_heatmap module: {e}")
        return

    # ========== ANALYSIS DEEP DIVE VIEW ==========
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Filter by Resolution Type")

    all_types = sorted([rt for rt in resolution_types.keys() if rt != 'no_resolution_type'])
    if 'no_resolution_type' in resolution_types:
        all_types.append('no_resolution_type')

    selected_types = st.sidebar.multiselect(
        "Select resolution types",
        options=all_types,
        default=all_types,
        help="Select one or more resolution types to filter."
    )

    st.sidebar.markdown("---")
    st.sidebar.header("✅ Resolution Achieved")
    achieved_filter = st.sidebar.multiselect(
        "Show calls where resolution_achieved is…",
        options=["resolved", "unresolved", "unknown"],
        default=["resolved", "unresolved", "unknown"],
        help="'resolved' = True, 'unresolved' = False, 'unknown' = missing/null."
    )

    # Caller type filter
    all_caller_types = sorted(set(f.get('caller_type', 'unknown') for f in all_files))
    st.sidebar.markdown("---")
    st.sidebar.header("👤 Filter by Caller Type")
    selected_caller_types = st.sidebar.multiselect(
        "Select caller types",
        options=all_caller_types,
        default=all_caller_types,
        help="Filter by caller type."
    )

    # Primary Intent filter
    all_intents_set = set()
    for f in all_files:
        intent = f.get('primary_intent')
        all_intents_set.add(intent if intent else 'unknown')
    all_intents = sorted(all_intents_set)

    st.sidebar.markdown("---")
    st.sidebar.header("🎯 Filter by Primary Intent")
    selected_intents = st.sidebar.multiselect(
        "Select primary intents",
        options=all_intents,
        default=all_intents,
        help="Filter by primary intent of the call."
    )

    # Transfer Success filter
    st.sidebar.markdown("---")
    st.sidebar.header("📞 Transfer Success")
    transfer_filter = st.sidebar.multiselect(
        "Show calls where transfer was…",
        options=["successful", "failed", "no_transfer"],
        default=["successful", "failed", "no_transfer"],
        help="'successful' = at least one transfer connected, 'failed' = all transfers failed, 'no_transfer' = no transfer attempted."
    )

    # Call Duration filter
    st.sidebar.markdown("---")
    st.sidebar.header("⏱️ Call Duration")

    durations = [f.get('call_duration') for f in all_files if f.get('call_duration') is not None]
    if durations:
        min_dur = int(min(durations))
        max_dur = int(max(durations)) + 1
    else:
        min_dur, max_dur = 0, 600

    duration_range = st.sidebar.slider(
        "Filter by duration (seconds)",
        min_value=min_dur,
        max_value=max_dur,
        value=(min_dur, max_dur),
        step=10,
        help="Filter calls based on their duration in seconds."
    )

    # Assistant ID filter
    all_assistant_ids = sorted(set(f.get('assistant_id', 'unknown') for f in all_files))
    st.sidebar.markdown("---")
    st.sidebar.header("🤖 Filter by Assistant ID")
    selected_assistant_ids = st.sidebar.multiselect(
        "Select assistant IDs",
        options=all_assistant_ids,
        default=all_assistant_ids,
        help="Filter by VAPI assistant ID."
    )

    # Squad ID filter
    all_squad_ids = sorted(set(f.get('squad_id', 'none') for f in all_files))
    st.sidebar.markdown("---")
    st.sidebar.header("👥 Filter by Squad ID")
    selected_squad_ids = st.sidebar.multiselect(
        "Select squad IDs",
        options=all_squad_ids,
        default=all_squad_ids,
        help="Filter by VAPI squad ID."
    )

    # Filter functions
    def matches_resolution_type(f, res_types):
        return f.get('resolution_type', 'no_resolution_type') in res_types

    def matches_achieved(f, achieved_list):
        val = f.get("resolution_achieved")
        if val is True:
            return "resolved" in achieved_list
        if val is False:
            return "unresolved" in achieved_list
        return "unknown" in achieved_list

    def matches_caller_type(f, caller_types):
        return f.get('caller_type', 'unknown') in caller_types

    def matches_primary_intent(f, intent_list):
        val = f.get('primary_intent') or 'unknown'
        return val in intent_list

    def matches_transfer_success(f, transfer_list):
        val = f.get("transfer_success")
        if val is True:
            return "successful" in transfer_list
        if val is False:
            return "failed" in transfer_list
        return "no_transfer" in transfer_list

    def matches_duration(f, dur_range):
        dur = f.get('call_duration')
        if dur is None:
            return True  # Include calls without duration
        return dur_range[0] <= dur <= dur_range[1]

    def matches_assistant_id(f, assistant_ids):
        return f.get('assistant_id', 'unknown') in assistant_ids

    def matches_squad_id(f, squad_ids):
        return f.get('squad_id', 'none') in squad_ids

    # Apply filters
    filtered_files = [
        f for f in all_files
        if matches_resolution_type(f, selected_types)
        and matches_achieved(f, achieved_filter)
        and matches_caller_type(f, selected_caller_types)
        and matches_primary_intent(f, selected_intents)
        and matches_transfer_success(f, transfer_filter)
        and matches_duration(f, duration_range)
        and matches_assistant_id(f, selected_assistant_ids)
        and matches_squad_id(f, selected_squad_ids)
    ]

    total_filtered = len(filtered_files)
    total_all = len(all_files)

    # Calculate total duration for duration percentages
    total_duration = sum(f.get('call_duration', 0) or 0 for f in filtered_files)

    # ========== DYNAMIC COUNTS WITH PERCENTAGES ==========
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Dynamic Counts")

    # Resolution Type counts
    with st.sidebar.expander(f"🏷️ Resolution Type ({len(selected_types)} selected)", expanded=False):
        for res_type in all_types:
            if res_type in selected_types:
                matching = [f for f in filtered_files if f.get('resolution_type', 'no_resolution_type') == res_type]
                count = len(matching)
                pct = (count / total_filtered * 100) if total_filtered else 0.0
                dur = sum(f.get('call_duration', 0) or 0 for f in matching)
                dur_pct = (dur / total_duration * 100) if total_duration else 0.0
                st.caption(f"✓ {res_type}: {count} ({pct:.1f}%, {dur_pct:.1f}% dur)")

    # Resolution Achieved counts
    with st.sidebar.expander(f"✅ Resolution Achieved ({len(achieved_filter)} selected)", expanded=False):
        resolved_files = [f for f in filtered_files if f.get("resolution_achieved") is True]
        unresolved_files = [f for f in filtered_files if f.get("resolution_achieved") is False]
        unknown_files = [f for f in filtered_files if f.get("resolution_achieved") is None]

        if 'resolved' in achieved_filter:
            count = len(resolved_files)
            pct = (count / total_filtered * 100) if total_filtered else 0.0
            dur = sum(f.get('call_duration', 0) or 0 for f in resolved_files)
            dur_pct = (dur / total_duration * 100) if total_duration else 0.0
            st.caption(f"✓ resolved: {count} ({pct:.1f}%, {dur_pct:.1f}% dur)")
        if 'unresolved' in achieved_filter:
            count = len(unresolved_files)
            pct = (count / total_filtered * 100) if total_filtered else 0.0
            dur = sum(f.get('call_duration', 0) or 0 for f in unresolved_files)
            dur_pct = (dur / total_duration * 100) if total_duration else 0.0
            st.caption(f"✓ unresolved: {count} ({pct:.1f}%, {dur_pct:.1f}% dur)")
        if 'unknown' in achieved_filter:
            count = len(unknown_files)
            pct = (count / total_filtered * 100) if total_filtered else 0.0
            dur = sum(f.get('call_duration', 0) or 0 for f in unknown_files)
            dur_pct = (dur / total_duration * 100) if total_duration else 0.0
            st.caption(f"✓ unknown: {count} ({pct:.1f}%, {dur_pct:.1f}% dur)")

    # Caller Type counts
    with st.sidebar.expander(f"👤 Caller Type ({len(selected_caller_types)} selected)", expanded=False):
        for caller_type in all_caller_types:
            if caller_type in selected_caller_types:
                matching = [f for f in filtered_files if f.get('caller_type', 'unknown') == caller_type]
                count = len(matching)
                pct = (count / total_filtered * 100) if total_filtered else 0.0
                dur = sum(f.get('call_duration', 0) or 0 for f in matching)
                dur_pct = (dur / total_duration * 100) if total_duration else 0.0
                st.caption(f"✓ {caller_type}: {count} ({pct:.1f}%, {dur_pct:.1f}% dur)")

    # Primary Intent counts
    with st.sidebar.expander(f"🎯 Primary Intent ({len(selected_intents)} selected)", expanded=False):
        for intent in all_intents:
            if intent in selected_intents:
                matching = [f for f in filtered_files if (f.get('primary_intent') or 'unknown') == intent]
                count = len(matching)
                pct = (count / total_filtered * 100) if total_filtered else 0.0
                dur = sum(f.get('call_duration', 0) or 0 for f in matching)
                dur_pct = (dur / total_duration * 100) if total_duration else 0.0
                st.caption(f"✓ {intent}: {count} ({pct:.1f}%, {dur_pct:.1f}% dur)")

    # Transfer Success counts
    with st.sidebar.expander(f"📞 Transfer Success ({len(transfer_filter)} selected)", expanded=False):
        success_files = [f for f in filtered_files if f.get("transfer_success") is True]
        failed_files = [f for f in filtered_files if f.get("transfer_success") is False]
        no_transfer_files = [f for f in filtered_files if f.get("transfer_success") is None]

        if 'successful' in transfer_filter:
            count = len(success_files)
            pct = (count / total_filtered * 100) if total_filtered else 0.0
            dur = sum(f.get('call_duration', 0) or 0 for f in success_files)
            dur_pct = (dur / total_duration * 100) if total_duration else 0.0
            st.caption(f"✓ successful: {count} ({pct:.1f}%, {dur_pct:.1f}% dur)")
        if 'failed' in transfer_filter:
            count = len(failed_files)
            pct = (count / total_filtered * 100) if total_filtered else 0.0
            dur = sum(f.get('call_duration', 0) or 0 for f in failed_files)
            dur_pct = (dur / total_duration * 100) if total_duration else 0.0
            st.caption(f"✓ failed: {count} ({pct:.1f}%, {dur_pct:.1f}% dur)")
        if 'no_transfer' in transfer_filter:
            count = len(no_transfer_files)
            pct = (count / total_filtered * 100) if total_filtered else 0.0
            dur = sum(f.get('call_duration', 0) or 0 for f in no_transfer_files)
            dur_pct = (dur / total_duration * 100) if total_duration else 0.0
            st.caption(f"✓ no_transfer: {count} ({pct:.1f}%, {dur_pct:.1f}% dur)")

    # Assistant ID counts
    with st.sidebar.expander(f"🤖 Assistant ID ({len(selected_assistant_ids)} selected)", expanded=False):
        for assistant_id in all_assistant_ids:
            if assistant_id in selected_assistant_ids:
                matching = [f for f in filtered_files if f.get('assistant_id', 'unknown') == assistant_id]
                count = len(matching)
                pct = (count / total_filtered * 100) if total_filtered else 0.0
                dur = sum(f.get('call_duration', 0) or 0 for f in matching)
                dur_pct = (dur / total_duration * 100) if total_duration else 0.0
                display_id = assistant_id[:12] + '...' if len(assistant_id) > 15 else assistant_id
                st.caption(f"✓ {display_id}: {count} ({pct:.1f}%, {dur_pct:.1f}% dur)")

    # Squad ID counts
    with st.sidebar.expander(f"👥 Squad ID ({len(selected_squad_ids)} selected)", expanded=False):
        for squad_id in all_squad_ids:
            if squad_id in selected_squad_ids:
                matching = [f for f in filtered_files if f.get('squad_id', 'none') == squad_id]
                count = len(matching)
                pct = (count / total_filtered * 100) if total_filtered else 0.0
                dur = sum(f.get('call_duration', 0) or 0 for f in matching)
                dur_pct = (dur / total_duration * 100) if total_duration else 0.0
                display_id = squad_id[:12] + '...' if len(squad_id) > 15 else squad_id
                st.caption(f"✓ {display_id}: {count} ({pct:.1f}%, {dur_pct:.1f}% dur)")

    st.sidebar.markdown("---")
    st.sidebar.metric("Filtered Calls", f"{total_filtered} / {total_all}")

    # Font size controls
    st.sidebar.markdown("---")
    st.sidebar.header("🎨 Display Settings")

    if 'transcript_font_size' not in st.session_state:
        st.session_state.transcript_font_size = 14
    if 'json_font_size' not in st.session_state:
        st.session_state.json_font_size = 14

    transcript_font_size = st.sidebar.slider(
        "📝 Transcript Font Size",
        min_value=10,
        max_value=24,
        value=st.session_state.transcript_font_size,
        step=1,
        help="Adjust the font size for the transcript display"
    )
    st.session_state.transcript_font_size = transcript_font_size

    json_font_size = st.sidebar.slider(
        "📊 JSON Font Size",
        min_value=10,
        max_value=24,
        value=st.session_state.json_font_size,
        step=1,
        help="Adjust the font size for the JSON display"
    )
    st.session_state.json_font_size = json_font_size

    st.markdown(f"""
    <style>
        :root {{
            --transcript-font-size: {transcript_font_size}px;
            --json-font-size: {json_font_size}px;
        }}
    </style>
    """, unsafe_allow_html=True)

    if not filtered_files:
        st.warning("No calls match the selected filters")
        return

    # Sort by ID
    filtered_files.sort(key=lambda x: x.get('id', ''))

    # Search
    st.markdown("---")
    search_term = st.text_input("🔍 Search calls", "", key="call_search")

    display_files = filtered_files
    if search_term:
        display_files = [
            f for f in filtered_files
            if search_term.lower() in f.get('id', '').lower()
            or search_term.lower() in f.get('final_outcome', '').lower()
            or search_term.lower() in f.get('caller_type', '').lower()
            or search_term.lower() in (f.get('transcript_content', '') or '').lower()
        ]

    if not display_files:
        st.info("No calls match your search")
        return

    # File selector
    file_options = [f"{f.get('id')} ({f.get('caller_type', 'unknown')})" for f in display_files]

    # Calculate total duration for displayed files
    total_display_duration = sum(f.get('call_duration', 0) or 0 for f in display_files)
    hours = int(total_display_duration // 3600)
    minutes = int((total_display_duration % 3600) // 60)
    seconds = int(total_display_duration % 60)
    if hours > 0:
        duration_str = f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        duration_str = f"{minutes}m {seconds}s"
    else:
        duration_str = f"{seconds}s"

    file_col1, file_col2, file_col2b, file_col2c, file_col3, file_col4 = st.columns([3, 1.2, 1.4, 1.2, 1, 1])

    with file_col1:
        selected_idx = st.selectbox("Select a call", range(len(file_options)), format_func=lambda i: file_options[i], label_visibility="visible")

    with file_col2:
        st.metric("Calls", f"{len(display_files)} / {len(filtered_files)}")

    with file_col2b:
        st.metric("Total Duration", duration_str)

    with file_col2c:
        st.metric("Position", f"{selected_idx + 1} / {len(display_files)}")

    with file_col3:
        if st.button("◀ Prev", use_container_width=True) and selected_idx > 0:
            selected_idx -= 1

    with file_col4:
        if st.button("Next ▶", use_container_width=True) and selected_idx < len(display_files) - 1:
            selected_idx += 1

    st.markdown("---")

    # Display selected call
    if display_files:
        selected_call = display_files[selected_idx]

        col_txt, col_json = st.columns(2)

        with col_txt:
            st.markdown("### 📝 Transcript")
            transcript = selected_call.get('transcript_content', '')
            if transcript:
                st.text_area("Transcript", value=transcript, height=700, disabled=True, label_visibility="collapsed")
            else:
                st.info("No transcript available")

        with col_json:
            st.markdown("### 📊 LLM Analysis")
            # Add duration to displayed data
            display_data = selected_call.get('data', {}).copy() if selected_call.get('data') else {}
            call_dur = selected_call.get('call_duration')
            if call_dur is not None:
                display_data['_call_duration_seconds'] = round(call_dur, 2)
                minutes = int(call_dur // 60)
                seconds = int(call_dur % 60)
                display_data['_call_duration_formatted'] = f"{minutes}m {seconds}s"
            display_data['_assistant_id'] = selected_call.get('assistant_id', 'unknown')
            display_data['_squad_id'] = selected_call.get('squad_id', 'none')
            st.json(display_data)


if __name__ == "__main__":
    main()
