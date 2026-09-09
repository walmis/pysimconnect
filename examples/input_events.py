from simconnect import SimConnect, INPUT_EVENT_TYPE_DOUBLE

"""List the loaded aircraft's input events (B: variables), read one, and
watch it change.  Needs MSFS 2020 SU12 or later with an aircraft loaded."""

with SimConnect(name='InputEvents') as sc:
    events = sc.enumerate_input_events()
    print(f"{len(events)} input events on this aircraft")
    for name in sorted(events)[:20]:
        print("  ", name)

    doubles = [e for e in events.values() if e.type == INPUT_EVENT_TYPE_DOUBLE]
    if doubles:
        first = doubles[0]
        print(f"{first.name} = {sc.get_input_event(first)}")

        sc.subscribe_input_event(first, lambda v: print(f"{first.name} -> {v}"))
        print("Watching for changes, Ctrl-C to stop")
        while True:
            sc.receive(timeout_seconds=0.5)
