# -*- coding: utf-8 -*-
"""
MockSerial: In-memory bi-directional serial port emulator for ESP32.
Simulates real UART communication, DTR/RTS pin states, timeouts,
reactive AT/RES firmware responses, and fault injection.
"""
import queue
import time
import serial


class MockSerial:
    """
    In-memory virtual serial connection mimicking pyserial's serial.Serial.
    Supports bi-directional non-blocking / timed reads and writes,
    DTR/RTS pin state tracking, automatic firmware command responses,
    and runtime fault injection (disconnect, read error, write timeout).
    """

    def __init__(self, port="COM3", baudrate=115200, timeout=0.1, write_timeout=1.0):
        self.port = port
        self.baudrate = int(baudrate) if str(baudrate).isdigit() else 115200
        self.timeout = float(timeout) if timeout is not None else 0.1
        self.write_timeout = float(write_timeout) if write_timeout is not None else 1.0
        self.is_open = True

        # In-memory communication queues
        self._rx_queue = queue.Queue()   # Incoming data from virtual ESP32 to host App
        self._tx_buffer = bytearray()    # Outgoing data sent from host App to virtual ESP32

        # Pin state tracking
        self.dtr = False
        self.rts = False
        self.reset_count = 0

        # Fault injection toggles
        self.fault_disconnect = False
        self.fault_read_error = None
        self.fault_write_timeout = False

        # Behavior flags
        self.auto_respond = True
        self.incoming_history = []

    @property
    def in_waiting(self):
        """Number of items waiting in the RX queue."""
        return self._rx_queue.qsize()

    @property
    def out_waiting(self):
        """Number of bytes waiting in the TX buffer."""
        return len(self._tx_buffer)

    def read(self, size=1024):
        """
        Read up to `size` bytes from incoming RX queue.
        Raises serial.SerialException if closed or fault_disconnect is active.
        """
        if not self.is_open or self.fault_disconnect:
            self.is_open = False
            raise serial.SerialException("Device disconnected unexpectedly (I/O Error).")

        if self.fault_read_error:
            err = self.fault_read_error
            self.fault_read_error = None
            raise err

        chunks = bytearray()
        deadline = time.time() + max(0.01, self.timeout)

        # Retrieve first available chunk
        try:
            wait_time = max(0.001, deadline - time.time())
            chunk = self._rx_queue.get(timeout=wait_time)
            chunks.extend(chunk)
        except queue.Empty:
            return bytes(chunks)

        # Grab any additional chunks currently ready without waiting
        while len(chunks) < size:
            try:
                next_chunk = self._rx_queue.get_nowait()
                chunks.extend(next_chunk)
            except queue.Empty:
                break

        if len(chunks) > size:
            # Re-queue excess bytes
            excess = chunks[size:]
            self._rx_queue.put(excess)
            chunks = chunks[:size]

        return bytes(chunks)

    def write(self, data):
        """
        Write bytes to the virtual device.
        """
        if not self.is_open or self.fault_disconnect:
            self.is_open = False
            raise serial.SerialException("Cannot write to closed port.")

        if self.fault_write_timeout:
            raise serial.SerialTimeoutException("Write timeout expired.")

        if isinstance(data, str):
            data = data.encode("utf-8")
        elif not isinstance(data, (bytes, bytearray)):
            data = bytes(data)

        self._tx_buffer.extend(data)
        self.incoming_history.append(bytes(data))

        if self.auto_respond:
            self._handle_device_protocol(data)

        return len(data)

    def flush(self):
        """No-op flush."""
        pass

    def reset_input_buffer(self):
        """Clear the RX queue."""
        while not self._rx_queue.empty():
            try:
                self._rx_queue.get_nowait()
            except queue.Empty:
                break

    def reset_output_buffer(self):
        """Clear the TX buffer."""
        self._tx_buffer.clear()

    def setDTR(self, value):
        """Set DTR pin state."""
        self.dtr = bool(value)

    def setRTS(self, value):
        """
        Set RTS pin state.
        Monitors ESP32 hardware auto-reset sequence: DTR=False, RTS True -> False.
        """
        old_rts = self.rts
        self.rts = bool(value)

        # EN pin pulse on ESP32: RTS goes from HIGH to LOW while DTR is LOW
        if not self.dtr and old_rts and not self.rts:
            self.reset_count += 1
            if self.auto_respond:
                self.inject_rx_line("RES:SYSTEM_READY")

    def close(self):
        """Close the serial port connection."""
        self.is_open = False

    # -------------------------------------------------------------------------
    # Test Automation & Injection Helpers
    # -------------------------------------------------------------------------

    def inject_rx_data(self, data: bytes):
        """Inject raw bytes into the device RX stream."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._rx_queue.put(data)

    def inject_rx_line(self, line: str):
        """Inject a single text line with CRLF termination."""
        self.inject_rx_data((line + "\r\n").encode("utf-8"))

    def get_transmitted_bytes(self) -> bytes:
        """Return all bytes transmitted by the application so far."""
        return bytes(self._tx_buffer)

    def get_transmitted_text(self, encoding="utf-8", errors="replace") -> str:
        """Return transmitted bytes decoded as string."""
        return self._tx_buffer.decode(encoding, errors=errors)

    def clear_transmitted(self):
        """Clear the transmission history buffer."""
        self._tx_buffer.clear()

    # -------------------------------------------------------------------------
    # Virtual ESP32 Reactive Firmware Simulator
    # -------------------------------------------------------------------------

    def _handle_device_protocol(self, data: bytes):
        """
        Simulate firmware responses to application IoT commands and control signals.
        """
        text = data.decode("utf-8", errors="ignore").strip()

        if text.startswith("SET_WIFI|"):
            self.inject_rx_line("OK:WIFI_SAVED")
        elif text == "CONNECT_WIFI":
            self.inject_rx_line("RES:WIFI_CONNECTED")
        elif text == "DISCONNECT_WIFI":
            self.inject_rx_line("RES:WIFI_DISCONNECTED")
        elif text == "SCAN_WIFI":
            self.inject_rx_line("RES:SCAN_START")
            self.inject_rx_line("RES:WIFI|MockHome_2.4G|-45|WPA2")
            self.inject_rx_line("RES:WIFI|Office_5G|-68|WPA3")
            self.inject_rx_line("RES:WIFI|GuestNetwork|-82|OPEN")
            self.inject_rx_line("RES:SCAN_END")
        elif text.startswith("SET_SERVER|"):
            self.inject_rx_line("OK:SERVER_SAVED")
        elif text == "CONNECT_SERVER":
            self.inject_rx_line("RES:SERVER_CONNECTED")
        elif text == "DISCONNECT_SERVER":
            self.inject_rx_line("RES:SERVER_DISCONNECTED")
        elif text == "RESET":
            self.reset_count += 1
            self.inject_rx_line("RES:SYSTEM_READY")
        elif text.startswith("F") and "_PRESSED" in text:
            self.inject_rx_line(f"RES:CMD_SENT_TO_SERVER:{text}")
        elif text.startswith("CUSTOM_ECHO|"):
            payload = text.split("|", 1)[1]
            self.inject_rx_line(f"RES:ECHO:{payload}")
