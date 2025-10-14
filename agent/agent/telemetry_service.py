import logging


class TelemetryService:
    def __init__(self):
        self.telemetry_data = {}

    def echo(self, message: str):
        logging.info(message)

    def error(self, message: str):
        logging.error(message)

    def warning(self, message: str):
        logging.warning(message)

    def info(self, message: str):
        logging.info(message)

    def debug(self, message: str):
        logging.debug(message)

    def fatal(self, message: str):
        logging.fatal(message)

    def critical(self, message: str):
        logging.critical(message)

    def success(self, message: str):
        logging.info(message)


def get_telemetry_service() -> TelemetryService:
    return TelemetryService()
