import os
import json
import time
import streamlit as st
import pydeck as pdk

STATE_FILE = os.path.join(
    os.path.dirname(__file__), '../../sumo/current_state.json'
)

MAP_CENTER_LAT = 19.018
MAP_CENTER_LON = 72.828

VEHICLE_COLORS = {
    'car':       [180, 180, 180, 210],
    'bus':       [30,  120, 255, 230],
    'emergency': [255, 30,  30,  255],
}

SIGNAL_COLORS = {
    'green':  [0,   220, 80,  255],
    'yellow': [255, 200, 0,   255],
    'red':    [220, 30,  30,  255],
}

st.set_page_config(
    page_title="Mumbai Traffic — Live",
    page_icon="🚦",
    layout="wide",
)

st.title("🚦 Mumbai Traffic Signal Optimization")
st.caption("Worli · Mahalaxmi · Lower Parel — Live Simulation")

col1, col2, col3, col4 = st.columns(4)
metric_step     = col1.empty()
metric_vehicles = col2.empty()
metric_stopped  = col3.empty()
metric_signals  = col4.empty()

map_placeholder = st.empty()
status = st.empty()

while True:
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)

        vehicles = state.get('vehicles', [])
        signals  = state.get('signals',  [])
        step     = state.get('step',     0)

        for v in vehicles:
            v['color']  = VEHICLE_COLORS.get(v['vehicle_type'], [180, 180, 180, 200])
            v['radius'] = 12
            # Pre-build tooltip text for this vehicle
            v['tooltip_text'] = (
                f"Vehicle: {v['vehicle_id']}\n"
                f"Type: {v['vehicle_type']}\n"
                f"Speed: {round(v['speed'] * 2.237, 1)} mph\n"
                f"Stopped: {v['time_stopped']}s"
            )

        for s in signals:
            s['color']  = SIGNAL_COLORS.get(s['state'], [255, 165, 0, 255])
            s['radius'] = 8
            # Pre-build tooltip text for this signal head
            s['tooltip_text'] = (
                f"Signal: {s['tl_id']}\n"
                f"Head #{s['signal_index']}\n"
                f"State: {s['state'].upper()}\n"
                f"Lane: {s['from_lane']}"
            )

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
            opacity=0.9,
        )

        view_state = pdk.ViewState(
            latitude=MAP_CENTER_LAT,
            longitude=MAP_CENTER_LON,
            zoom=15,
            pitch=0,
            bearing=0,
        )

        deck = pdk.Deck(
            layers=[signal_layer, vehicle_layer],
            initial_view_state=view_state,
            # Single tooltip template — works for both vehicles and signals
            # because every data point now has a tooltip_text field
            tooltip={"text": "{tooltip_text}"},
            map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
        )

        green_count = sum(1 for s in signals if s['state'] == 'green')
        red_count   = sum(1 for s in signals if s['state'] == 'red')

        metric_step.metric("Simulation Step", step)
        metric_vehicles.metric("Vehicles Active", len(vehicles))
        metric_stopped.metric(
            "Avg Wait (s)",
            round(
                sum(v['time_stopped'] for v in vehicles) / max(len(vehicles), 1),
                1
            )
        )
        metric_signals.metric(
            "Signal Heads",
            f"{green_count}🟢 {red_count}🔴"
        )

        map_placeholder.pydeck_chart(deck)
        status.caption(
            f"Last updated: step {step} — "
            f"{len(signals)} signal heads across 18 intersections"
        )

    except FileNotFoundError:
        status.info("⏳ Waiting for simulator to start — run `simulator.py` first.")
    except json.JSONDecodeError:
        pass

    time.sleep(2)