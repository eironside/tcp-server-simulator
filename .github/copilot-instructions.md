We need a TCP Simulator that can be used to test our ArcGIS Velocity product. The simulator should be able to simulate TCP traffic and allow us to test the performance and reliability of our product under different network conditions.

It should be able to run in Server and Client modes and operate similarly to the GeoEvent TCP Simulator, which is a Java-based application that can simulate TCP traffic. The simulator should be able to load a delimited text file (most common is CSV) that contains the data to be sent over TCP. The simulator should also allow us to configure the rate at which each line of the file is sent.
- Server mode, the simulator will listen for incoming TCP connections and send the data from the file to any connected clients at the configured rate.
- Client mode, the simulator will connect to a specified TCP server and send the data from the file at the configured rate.

The simulator should be able to run on Windows and Linux operating systems and should be easy to set up and use. It should also provide detailed logging and reporting features to help us analyze the results of our tests.

The TCP Simulator should have the following features:
1. Ability to switch between Server and Client modes.
2. Support for loading delimited text files (CSV) to simulate TCP traffic.
3. Configurable rate for sending each line of the file.
4. Compatibility with Windows and Linux operating systems.
5. Ability to set the designated field as the timestamp field for accurate time-based simulations.
6. Set the port for TCP communication (client and server).
7. Allow the user to walk through the data one line at a time or send the lines automatically and possibly loop back to the beginning.
8. Allow the user to choose the file they want to load data from for sending.
