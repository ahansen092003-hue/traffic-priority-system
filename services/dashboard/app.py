import json
import time

import redis
import requests
import streamlit as st
import pydeck as pdk

# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------
redis_client  = redis.Redis(host='localhost', port=6379, decode_responses=True)
SIMULATOR_API = 'http://localhost:8000'

MAP_CENTER_LAT = 19.018
MAP_CENTER_LON = 72.828

VEHICLE_COLORS = {
    'car':       [180, 180, 180, 210],
    'bus':       [30,  120, 255, 230],
    'emergency': [255, 50,  50,  255],
}

SIGNAL_COLORS = {
    'green':  [0,   220, 80,  255],
    'yellow': [255, 200, 0,   255],
    'red':    [220, 30,  30,  255],
}


def get_signal_options():
    """
    Read current_state from Redis and build a dict of
    tl_id -> (avg_lat, avg_lon) by averaging all signal heads
    for each intersection. Returns a sorted list of (label, lat, lon).
    """
    raw = redis_client.get('current_state')
    if not raw:
        return []

    state = json.loads(raw)
    tl_positions = {}
    for head in state.get('signals', []):
        tl_id = head['tl_id']
        if tl_id not in tl_positions:
            tl_positions[tl_id] = []
        tl_positions[tl_id].append((head['lat'], head['lon']))

    options = []
    for tl_id, positions in tl_positions.items():
        avg_lat = sum(p[0] for p in positions) / len(positions)
        avg_lon = sum(p[1] for p in positions) / len(positions)
        # Shorten the label — SUMO IDs are long, show last 16 chars
        short_id = tl_id[-20:] if len(tl_id) > 20 else tl_id
        options.append((f"{short_id}  ({avg_lat:.4f}, {avg_lon:.4f})",
                        avg_lat, avg_lon, tl_id))

    return sorted(options, key=lambda x: x[0])


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Mumbai Traffic — Live",
    page_icon="🚦",
    layout="wide",
)

st.title("🚦 Mumbai Traffic Signal Optimization")
st.caption("Worli · Mahalaxmi · Lower Parel — Live Simulation")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("🚑 Ambulance Control")

    # Priority toggle
    priority_raw     = redis_client.get('priority_enabled')
    priority_current = priority_raw != 'false'
    priority_toggle  = st.toggle(
        "Signal Priority Enabled",
        value=priority_current,
        help="When OFF, all forced signals are released immediately"
    )
    if priority_toggle != priority_current:
        try:
            requests.post(
                f"{SIMULATOR_API}/priority/toggle",
                params={'enabled': priority_toggle},
                timeout=2,
            )
        except requests.exceptions.RequestException:
            st.warning("Could not reach simulator API")

    st.divider()
    st.subheader("Spawn Ambulance")
    st.caption(
        "Select the nearest intersection to your origin and destination. "
        "The ambulance spawns near the selected signal."
    )

    # Load signal options from Redis
    signal_options = get_signal_options()

    if not signal_options:
        st.warning("No signals loaded yet — start the simulator first.")
    else:
        labels = [opt[0] for opt in signal_options]

        origin_idx = st.selectbox(
            "Origin intersection",
            range(len(labels)),
            format_func=lambda i: labels[i],
            index=0,
            key="origin_select",
        )
        dest_idx = st.selectbox(
            "Destination intersection",
            range(len(labels)),
            format_func=lambda i: labels[i],
            index=min(5, len(labels) - 1),
            key="dest_select",
        )

        origin_lat = signal_options[origin_idx][1]
        origin_lon = signal_options[origin_idx][2]
        dest_lat   = signal_options[dest_idx][1]
        dest_lon   = signal_options[dest_idx][2]

        # Show selected coordinates so user can verify
        st.caption(
            f"**Origin:** {origin_lat:.5f}, {origin_lon:.5f}  \n"
            f"**Dest:** {dest_lat:.5f}, {dest_lon:.5f}"
        )

        if st.button("🚑 Spawn Ambulance", type="primary",
                     disabled=origin_idx == dest_idx):
            if origin_idx == dest_idx:
                st.error("Origin and destination must be different intersections.")
            else:
                try:
                    resp = requests.post(
                        f"{SIMULATOR_API}/ambulance/spawn",
                        json={
                            'origin_lat': origin_lat,
                            'origin_lon': origin_lon,
                            'dest_lat':   dest_lat,
                            'dest_lon':   dest_lon,
                        },
                        timeout=3,
                    )
                    if resp.status_code == 200:
                        st.success(
                            "✅ Queued — watch simulator terminal for confirmation"
                        )
                    else:
                        st.error(f"Spawn failed: {resp.text}")
                except requests.exceptions.RequestException:
                    st.error("Could not reach simulator API on :8000")

    st.divider()
    st.subheader("Active Ambulances")
    amb_keys = redis_client.keys('ambulance:*:route')
    if not amb_keys:
        st.caption("None active")
    else:
        for key in amb_keys:
            raw = redis_client.get(key)
            if not raw:
                continue
            route     = json.loads(raw)
            amb_id    = route['ambulance_id']
            total     = len(route['signals'])
            cleared   = len(route['cleared_signals'])
            remaining = total - cleared
            st.metric(
                label=amb_id,
                value=f"{remaining} signals ahead",
                delta=f"{cleared} cleared",
                delta_color="normal",
            )

# ---------------------------------------------------------------------------
# Main metrics row
# ---------------------------------------------------------------------------
col1, col2, col3, col4, col5 = st.columns(5)
metric_step      = col1.empty()
metric_vehicles  = col2.empty()
metric_stopped   = col3.empty()
metric_signals   = col4.empty()
metric_simulator = col5.empty()

map_placeholder = st.empty()
status          = st.empty()

# ---------------------------------------------------------------------------
# Live update loop
# ---------------------------------------------------------------------------
while True:
    raw = redis_client.get('current_state')
    if not raw:
        status.info("⏳ Waiting for simulator — run `simulator.py` first.")
        time.sleep(2)
        continue

    state    = json.loads(raw)
    vehicles = state.get('vehicles', [])
    signals  = state.get('signals',  [])
    step     = state.get('step',     0)

    # Vehicle layer
    for v in vehicles:
        v['color']  = VEHICLE_COLORS.get(v['vehicle_type'], [180, 180, 180, 200])
        v['radius'] = 25 if v['vehicle_type'] == 'emergency' else 12
        v['tooltip_text'] = (
            f"{'🚑 AMBULANCE' if v['vehicle_type'] == 'emergency' else 'Vehicle'}: "
            f"{v['vehicle_id']}\n"
            f"Type: {v['vehicle_type']}\n"
            f"Speed: {round(v['speed'] * 2.237, 1)} mph\n"
            f"Stopped: {v['time_stopped']}s\n"
            f"Lat: {v['lat']}  Lon: {v['lon']}"
        )

    # Signal layer — lat/lon in tooltip for reference
    for s in signals:
        s['color']  = SIGNAL_COLORS.get(s['state'], [255, 165, 0, 255])
        s['radius'] = 8
        s['tooltip_text'] = (
            f"Signal: {s['tl_id']}\n"
            f"Head #{s['signal_index']}  State: {s['state'].upper()}\n"
            f"Lat: {s['lat']}  Lon: {s['lon']}\n"
            f"Lane: {s['from_lane']}"
        )

    # Ambulance route layers
    route_layers  = []
    origin_points = []
    dest_points   = []

    for key in redis_client.keys('ambulance:*:route'):
        route_raw = redis_client.get(key)
        if not route_raw:
            continue
        route_data = json.loads(route_raw)
        origin     = route_data.get('origin')
        dest       = route_data.get('dest')
        amb_id     = route_data.get('ambulance_id', 'ambulance')

        if origin and dest:
            route_layers.append(pdk.Layer(
                'LineLayer',
                data=[{
                    'start': [origin[1], origin[0]],
                    'end':   [dest[1],   dest[0]],
                }],
                get_source_position='start',
                get_target_position='end',
                get_color=[255, 140, 0, 220],
                get_width=6,
                pickable=False,
            ))
            origin_points.append({
                'lon': origin[1], 'lat': origin[0],
                'color': [0, 255, 100, 255], 'radius': 22,
                'tooltip_text': (
                    f"🟢 {amb_id} ORIGIN\n"
                    f"Lat: {origin[0]}  Lon: {origin[1]}"
                ),
            })
            dest_points.append({
                'lon': dest[1], 'lat': dest[0],
                'color': [255, 255, 255, 255], 'radius': 22,
                'tooltip_text': (
                    f"⬜ {amb_id} DESTINATION\n"
                    f"Lat: {dest[0]}  Lon: {dest[1]}"
                ),
            })

    signal_layer = pdk.Layer(
        'ScatterplotLayer',
        data=signals,
        get_position='[lon, lat]',
        get_fill_color='color',
        get_radius='radius',
        pickable=True,
        opacity=1.0,
        stroked=True,
        get_line_color=[0, 0, 0, 100],
        line_width_min_pixels=1,
    )
    vehicle_layer = pdk.Layer(
        'ScatterplotLayer',
        data=vehicles,
        get_position='[lon, lat]',
        get_fill_color='color',
        get_radius='radius',
        pickable=True,
        opacity=0.95,
        stroked=True,
        get_line_color=[0, 0, 0, 150],
        line_width_min_pixels=1,
    )

    layers = [signal_layer, *route_layers, vehicle_layer]

    if origin_points:
        layers.append(pdk.Layer(
            'ScatterplotLayer',
            data=origin_points,
            get_position='[lon, lat]',
            get_fill_color='color',
            get_radius='radius',
            pickable=True,
            opacity=1.0,
        ))
    if dest_points:
        layers.append(pdk.Layer(
            'ScatterplotLayer',
            data=dest_points,
            get_position='[lon, lat]',
            get_fill_color='color',
            get_radius='radius',
            pickable=True,
            opacity=1.0,
        ))

    view_state = pdk.ViewState(
        latitude=MAP_CENTER_LAT,
        longitude=MAP_CENTER_LON,
        zoom=15,
        pitch=0,
        bearing=0,
    )

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        tooltip={"text": "{tooltip_text}"},
        map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
    )

    green_count = sum(1 for s in signals if s['state'] == 'green')
    red_count   = sum(1 for s in signals if s['state'] == 'red')
    active_ambs = len(redis_client.keys('ambulance:*:route'))

    metric_step.metric("Simulation Step", step)
    metric_vehicles.metric("Vehicles Active", len(vehicles))
    metric_stopped.metric(
        "Avg Wait (s)",
        round(
            sum(v['time_stopped'] for v in vehicles) / max(len(vehicles), 1), 1
        )
    )
    metric_signals.metric("Signal Heads", f"{green_count}🟢 {red_count}🔴")
    metric_simulator.metric(
        "Ambulances",
        f"{active_ambs} active",
        delta="Priority ON" if priority_toggle else "Priority OFF",
        delta_color="normal" if priority_toggle else "inverse",
    )

    map_placeholder.pydeck_chart(deck)
    status.caption(
        f"Last updated: step {step} — "
        f"{len(signals)} signal heads · "
        f"Hover any dot to see lat/lon · "
        f"{'🟢 Priority ON' if priority_toggle else '🔴 Priority OFF'}"
    )

    time.sleep(2)
