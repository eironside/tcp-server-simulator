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

It should be able to run in Server and Client modes and operate similarly to the GeoEvent TCP Simulator, which is a Java-based application that can simulate TCP traffic. The simulator should also be able to **receive** TCP/UDP traffic as an optional mode, in addition to transmitting. A top-level **Sender ⇄ Receiver role toggle** selects direction; Server/Client mode and TCP/UDP protocol are orthogonal to role.

Sender behavior:
- Load a delimited text file (most common is CSV) containing the data to be sent. Configurable send rate per line.
- Server mode: listen for incoming TCP connections and broadcast file data to all connected clients at the configured rate. All clients see the same line at the same time.
- Client mode: connect to a specified TCP server and send the data from the file at the configured rate. Auto-reconnects on disconnect with exponential backoff.

Receiver behavior:
- Server mode: bind and accept inbound connections (TCP) or datagrams (UDP), consume framed records from peers.
- Client mode: connect outbound (TCP) or bind ephemeral (UDP) and consume records from the remote peer. Auto-reconnect with the same backoff policy as sender client.
- Optional sink file: received records can be streamed to disk in either **delimited passthrough** format or **JSON Lines** format. Sink is disabled by default, size-rotated when enabled, and runtime-reconfigurable without restart.

The simulator should be able to run on Windows and Linux operating systems and should be easy to set up and use. It should also provide detailed logging and reporting features to help us analyze the results of our tests.

The TCP Simulator should have the following features:
1. Ability to switch between Server and Client modes, and between Sender and Receiver roles, without restarting.
2. Support for loading delimited text files (CSV) to simulate TCP traffic (sender). Validate column count consistency; discard invalid lines.
3. Configurable rate for sending each line of the file. Rate unit is features/second (1 feature = 1 line). Also display KB/s.
4. Compatibility with Windows and Linux operating systems.
5. Ability to set the designated field as the timestamp field for accurate time-based simulations. Supported formats: ISO 8601, epoch millis, epoch seconds (integer and fractional).
6. Set the port for TCP/UDP communication (client and server, sender and receiver).
7. Allow the user to walk through the data one line at a time, jump to a specific line in step mode, or send the lines automatically and loop back to the beginning.
8. Allow the user to choose the file they want to load data from for sending.
9. Support both TCP and UDP protocols.
10. GUI with role toggle, file preview (sender), sink file panel (receiver), transport controls, status panel, and on-demand JSON log load/refresh.
11. JSON configuration file save/load.
12. Backpressure handling: sender blocks and disconnects slow clients with GUI indicators; receiver pauses per-peer TCP reads on sink overload and drops UDP on overload.
13. Header row: configurable whether to send to clients (sender).
14. Receiver role with optional delimited or JSON Lines sink-to-file output, size-based rotation, runtime enable/disable/path swap.
15. Test strategy: mandatory automated unit, integration, and soak tests (reconnect storms, slow-client churn/backpressure, large-file streaming/resource stability, receiver end-to-end, receiver sink rotation/backpressure). Manual socket-tool checks are non-gating.
16. Change send rate, input file, and sink configuration without restarting the application.

## Architecture Principle
The GUI must not contain business logic. The simulator engine must be fully functional without a GUI, communicating via an event/callback interface. This enables future CLI mode and testability.
