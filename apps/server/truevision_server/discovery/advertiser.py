from __future__ import annotations

import socket


class DiscoveryAdvertiser:
    def __init__(self, config, logger) -> None:
        self._config = config
        self._logger = logger
        self._registered = False
        self._zeroconf = None
        self._service_info = None

    def start(self) -> None:
        try:  # pragma: no cover - optional runtime path
            from zeroconf import IPVersion, ServiceInfo, Zeroconf  # type: ignore
        except Exception as exc:
            self._logger.info("zeroconf unavailable; skipping advertisement", extra={"error": str(exc)})
            return

        address = self._local_ip()
        properties = {
            b"service": b"truevision",
            b"model": self._config.whisper_model.encode("utf-8"),
            b"device": self._config.whisper_device.encode("utf-8"),
        }
        info = ServiceInfo(
            type_="_truevision._tcp.local.",
            name="TrueVision Server._truevision._tcp.local.",
            addresses=[socket.inet_aton(address)],
            port=self._config.server_port,
            properties=properties,
        )
        self._zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        self._zeroconf.register_service(info)
        self._service_info = info
        self._registered = True

    def stop(self) -> None:
        if not self._registered or self._zeroconf is None or self._service_info is None:
            return
        self._zeroconf.unregister_service(self._service_info)
        self._zeroconf.close()
        self._registered = False

    def _local_ip(self) -> str:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
