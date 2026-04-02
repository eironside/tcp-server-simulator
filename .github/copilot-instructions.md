We need a TCP Simulator that can be used to test our ArcGIS Velocity product. The simulator should be able to simulate TCP and UDP traffic and allow us to test the performance and reliability of our product under different network conditions.

## Technology Stack
- **Language:** Python 3.10+
- **Async:** asyncio for TCP/UDP handling
- **GUI:** tkinter (stdlib) — functional, not pretty
- **Distribution:** Source only (for now)
- **Config format:** JSON
- **Log format:** JSON structured

## Design Document
See `docs/design-and-requirements.md` for the full design, resolved decisions, requirements, and architecture.

It should be able to run in Server and Client modes and operate similarly to the GeoEvent TCP Simulator, which is a Java-based application that can simulate TCP traffic. The simulator should be able to load a delimited text file (most common is CSV) that contains the data to be sent over TCP. The simulator should also allow us to configure the rate at which each line of the file is sent.
- Server mode, the simulator will listen for incoming TCP connections and send the data from the file to any connected clients at the configured rate. Uses broadcast model — all clients see the same line at the same time.
- Client mode, the simulator will connect to a specified TCP server and send the data from the file at the configured rate. Auto-reconnects on disconnect with exponential backoff.

The simulator should be able to run on Windows and Linux operating systems and should be easy to set up and use. It should also provide detailed logging and reporting features to help us analyze the results of our tests.

The TCP Simulator should have the following features:
1. Ability to switch between Server and Client modes.
2. Support for loading delimited text files (CSV) to simulate TCP traffic. Validate column count consistency; discard invalid lines.
3. Configurable rate for sending each line of the file. Rate unit is features/second (1 feature = 1 line). Also display KB/s.
4. Compatibility with Windows and Linux operating systems.
5. Ability to set the designated field as the timestamp field for accurate time-based simulations. Supported formats: ISO 8601, epoch millis, epoch seconds (integer and fractional).
6. Set the port for TCP/UDP communication (client and server).
7. Allow the user to walk through the data one line at a time or send the lines automatically and loop back to the beginning.
8. Allow the user to choose the file they want to load data from for sending.
9. Support both TCP and UDP protocols.
10. GUI with file preview, transport controls, status panel, and live JSON log view.
11. JSON configuration file save/load.
12. Backpressure handling: block and disconnect slow clients with GUI indicators.
13. Header row: configurable whether to send to clients.

## Architecture Principle
The GUI must not contain business logic. The simulator engine must be fully functional without a GUI, communicating via an event/callback interface. This enables future CLI mode and testability.
