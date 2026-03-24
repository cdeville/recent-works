import json
import logging
import os

# Format logs in JSON for better logging standardization & readability
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'message': record.getMessage(),
            'name': record.name,
            'function': record.funcName,
            'line': record.lineno,
            'file': record.filename,
        }
        return json.dumps(log_record)


# logging function used for lambda logging
def setup_logging():
    # Get the logging level from an environment variable
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

    # Set up the logger explicitly
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Remove any existing handlers to prevent duplicate logs
    logger.handlers.clear()

    # Configure the JSON format for the log output
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    
    # Add your handler with JSON formatting
    logger.addHandler(handler)
    
    return logger