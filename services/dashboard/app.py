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
    'green':  [0,   210, 80,  230],
    'yellow': [255, 200, 0,   230],
    'red':    [220, 30,  30,  230],
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
            v['radius'] = 15

        for s in signals:
            s['color']  = SIGNAL_COLORS.get(s['state'], [255, 165, 0, 220])
            s['radius'] = 25

        signal_layer = pdk.Layer(
            'ScatterplotLayer',
            data=signals,
            get_position='[lon, lat]',
            get_fill_color='color',
            get_radius='radius',
            pickable=True,
            opacity=0.9,
        )

        vehicle_layer = pdk.Layer(
            'ScatterplotLayer',
            data=vehicles,
            get_position='[lon, lat]',
            get_fill_color='color',
            get_radius='radius',
            pickable=True,
            opacity=0.85,
        )

        view_state = pdk.ViewState(
            latitude=MAP_CENTER_LAT,
            longitude=MAP_CENTER_LON,
            zoom=14,
            pitch=0,
            bearing=0,
        )

        # Using carto-dark — no Mapbox token needed, always loads the map tiles
        deck = pdk.Deck(
            layers=[signal_layer, vehicle_layer],
            initial_view_state=view_state,
            tooltip={
                "text": (
                    "{vehicle_id}\n"
                    "Type: {vehicle_type}\n"
                    "Speed: {speed} m/s\n"
                    "Stopped: {time_stopped}s"
                )
            },
            map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
        )

        metric_step.metric("Simulation Step", step)
        metric_vehicles.metric("Vehicles Active", len(vehicles))
        metric_stopped.metric(
            "Avg Wait (s)",
            round(
                sum(v['time_stopped'] for v in vehicles) / max(len(vehicles), 1),
                1
            )
        )
        metric_signals.metric("Traffic Lights", len(signals))

        map_placeholder.pydeck_chart(deck)
        status.caption(f"Last updated: step {step}")

    except FileNotFoundError:
        status.info("⏳ Waiting for simulator to start — run `simulator.py` first.")
    except json.JSONDecodeError:
        pass

    time.sleep(2)
