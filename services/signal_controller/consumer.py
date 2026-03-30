import os
import sys
import json
import math
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from confluent_kafka import Consumer, KafkaError

KAFKA_CONFIG = {
    'bootstrap.servers': 'localhost:9092',
    'group.id':          'signal-controller-group',
    'auto.offset.reset': 'latest',
}

VEHICLE_POSITIONS_TOPIC  = 'vehicle-positions'
APPROACH_DISTANCE_M      = 50.0
CLEAR_DISTANCE_M         = 80.0
BUS_WAIT_THRESHOLD_S     = 15.0
BUS_REISSUE_INTERVAL     = 30

def haversine_distance(lat1: float, lon1: float,
                       lat2: float, lon2: float) -> float:
    R       = 6_371_000
    phi1    = math.radians(lat1)
    phi2    = math.radians(lat2)
    d_phi   = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (math.sin(d_phi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c