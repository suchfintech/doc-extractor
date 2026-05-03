__version__ = "0.1.0"

from doc_extractor.corrections import read_corrected_or_canonical
from doc_extractor.extract import ExtractedDoc, extract, extract_batch
from doc_extractor.telemetry import flush_telemetry_to_s3, record_extraction

__all__ = [
    "ExtractedDoc",
    "__version__",
    "extract",
    "extract_batch",
    "flush_telemetry_to_s3",
    "read_corrected_or_canonical",
    "record_extraction",
]
