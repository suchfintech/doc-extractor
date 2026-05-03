__version__ = "0.1.0"

from doc_extractor.extract import extract
from doc_extractor.telemetry import flush_telemetry_to_s3, record_extraction

__all__ = ["__version__", "extract", "flush_telemetry_to_s3", "record_extraction"]
