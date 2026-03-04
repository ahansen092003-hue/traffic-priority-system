import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import time
import random
from services.traffic_sim.vehicle import Car, Bus
from services.traffic_sim.producer import VehicleProducer

TIME_STEP = 1.0