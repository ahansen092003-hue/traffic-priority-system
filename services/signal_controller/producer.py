import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import json
from confluent_kafka import Producer

KAFKA_CONFIG = {
    'bootstrap.servers': 'localhost:9092'
}

SIGNAL_COMMANDS_TOPIC = 'signal-commands'

def delivery_callback(err, msg):
    if err:
        print(f"Message delivery failed: {err}")
        
class SignalCommandProducer:
    def __init__(self):
        self.producer = Producer(KAFKA_CONFIG)

    def publish(self, command: dict):
        self.producer.produce(
            SIGNAL_COMMANDS_TOPIC,
            key=command['tl_id'],
            value=json.dumps(command).encode('utf-8'),
            callback=delivery_callback
        )
        self.producer.poll(0)