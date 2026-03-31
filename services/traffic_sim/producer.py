import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import json
from confluent_kafka import Producer

KAFKA_CONFIG = {
    'bootstrap.servers': 'localhost:9092'
}

VEHICLE_POSITIONS_TOPIC  = 'vehicle-positions'
EMERGENCY_VEHICLES_TOPIC = 'emergency-vehicles'

def delivery_callback(err, msg):
    if err:
        print(f"Message delivery failed: {err}")
        
class VehicleProducer:
    def __init__(self):
        self.producer = Producer(KAFKA_CONFIG)
    
    def publish(self, message, topic):
        self.producer.produce(
            topic,
            key=message['vehicle_id'],
            value=json.dumps(message).encode('utf-8'),
            callback=delivery_callback
        )
        self.producer.poll(0)