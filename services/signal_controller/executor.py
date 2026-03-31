import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from confluent_kafka import Consumer, KafkaError

KAFKA_CONFIG = {
    'bootstrap.servers': 'localhost:9092',
    'group.id':          'executor-group',
    'auto.offset.reset': 'latest',
}

SIGNAL_COMMANDS_TOPIC = 'signal-commands'

def run_executor(signal_cmd_queue):
    consumer = Consumer(KAFKA_CONFIG)
    consumer.subscribe([SIGNAL_COMMANDS_TOPIC])

    print("Executor started. Listening on signal-commands...")

    try:
        while True:
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                print(f"Executor error: {msg.error()}")
                continue

            cmd = json.loads(msg.value().decode('utf-8'))
            signal_cmd_queue.put(cmd)

    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()
        print("Executor closed.")