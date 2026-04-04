# dashboard/producer.py
#
# Placeholder for dashboard-side Kafka production.
#
# Currently the dashboard is read-only — it reads current_state from Redis
# and ambulance routes from Redis keys, but does not produce any Kafka messages.
#
# Planned: when the Claude API integration is added, this module will publish
# LLM-generated signal timing recommendations to a `signal-recommendations`
# Kafka topic, which the signal controller can consume and act on.
