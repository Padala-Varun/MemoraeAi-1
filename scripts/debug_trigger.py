"""Check if trigger is delivering and test with subscribe."""
from composio import Composio
import json

c = Composio(api_key="ak_JyCFiGedAQaOi_kInyBq")

# Check active triggers
active = c.triggers.list_active()
for t in active.items:
    print(f"Trigger: {t.id}")
    state = t.state
    if isinstance(state, dict):
        msgs = state.get("messages", [])
        watermark = state.get("provider_watermark_ms", 0)
    else:
        msgs = getattr(state, "messages", [])
        watermark = getattr(state, "provider_watermark_ms", 0)
    print(f"  Messages tracked: {len(msgs)}")
    print(f"  Watermark: {watermark}")
    print(f"  Disabled: {t.disabled_at}")
    config = t.trigger_config
    if isinstance(config, dict):
        print(f"  Interval: {config.get('interval', '?')} min")
    print()

# Now try subscribing to listen for events in realtime (5 second timeout)
print("Subscribing for 10 seconds to check for live events...")
import threading
import time

received = []

sub = c.triggers.subscribe()

@sub.handle(trigger_id="ti_wmq-qEIJ2_sC")
def on_event(data):
    print(f"EVENT RECEIVED: {json.dumps(data, indent=2, default=str)[:500]}")
    received.append(data)

def stop_after():
    time.sleep(10)
    print(f"\nTimeout. Received {len(received)} events.")
    import os
    os._exit(0)

t = threading.Thread(target=stop_after, daemon=True)
t.start()

try:
    sub.wait_forever()
except KeyboardInterrupt:
    pass
