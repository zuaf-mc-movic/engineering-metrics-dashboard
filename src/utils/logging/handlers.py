"""
Custom log handlers with rotation and compression.

This module provides handlers that manage log file rotation and compression
to prevent unbounded disk usage.
"""

import gzip
import logging
import os
import shutil
from logging.handlers import RotatingFileHandler
from typing import Optional


class CompressingRotatingFileHandler(RotatingFileHandler):
    """
    Rotating file handler that compresses old log files.

    This handler extends RotatingFileHandler to automatically gzip
    rotated log files, saving disk space.
    """

    def __init__(
        self,
        filename: str,
        mode: str = "a",
        maxBytes: int = 0,
        backupCount: int = 0,
        encoding: Optional[str] = None,
        delay: bool = False,
        compress: bool = True,
    ):
        """
        Initialize the handler with compression support.

        Args:
            filename: Log file path
            mode: File open mode (default: 'a' for append)
            maxBytes: Maximum file size before rotation (0 = no rotation)
            backupCount: Number of backup files to keep
            encoding: Text encoding (default: None = platform default)
            delay: If True, file opening is deferred until first emit()
            compress: If True, compress rotated files with gzip
        """
        self.compress = compress
        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay)

    def doRollover(self):
        """
        Perform a rollover and compress the rotated file.

        This method is called automatically when the log file reaches maxBytes.
        It rotates the files and compresses old logs.
        """
        # Close the current file
        if self.stream:
            self.stream.close()
            self.stream = None  # type: ignore[assignment]

        # Rotate existing backup files
        # e.g., log.2.gz -> log.3.gz, log.1.gz -> log.2.gz
        if self.backupCount > 0:
            for i in range(self.backupCount - 1, 0, -1):
                sfn = self.rotation_filename(f"{self.baseFilename}.{i}")
                dfn = self.rotation_filename(f"{self.baseFilename}.{i + 1}")

                # Check for both compressed and uncompressed files
                if os.path.exists(f"{sfn}.gz"):
                    if os.path.exists(f"{dfn}.gz"):
                        os.remove(f"{dfn}.gz")
                    os.rename(f"{sfn}.gz", f"{dfn}.gz")
                elif os.path.exists(sfn):
                    if os.path.exists(f"{dfn}.gz"):
                        os.remove(f"{dfn}.gz")
                    if os.path.exists(dfn):
                        os.remove(dfn)
                    os.rename(sfn, dfn)

            # Rotate the current log file to .1
            dfn = self.rotation_filename(f"{self.baseFilename}.1")
            if os.path.exists(dfn):
                os.remove(dfn)
            if os.path.exists(self.baseFilename):
                os.rename(self.baseFilename, dfn)

                # Compress the rotated file if compression is enabled
                if self.compress:
                    self._compress_file(dfn)

        # Open a new log file
        if not self.delay:
            self.stream = self._open()

    def _compress_file(self, source_file: str):
        """
        Compress a file using gzip and remove the original.

        Args:
            source_file: Path to the file to compress
        """
        compressed_file = f"{source_file}.gz"

        try:
            with open(source_file, "rb") as f_in:
                with gzip.open(compressed_file, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Remove the original file after successful compression
            os.remove(source_file)

        except Exception as e:
            # If compression fails, log the error but don't crash
            # The uncompressed file will remain
            print(f"Warning: Failed to compress {source_file}: {e}")


def create_rotating_handler(
    log_file: str,
    max_bytes: int = 10485760,  # 10MB
    backup_count: int = 10,
    compress: bool = True,
    formatter: Optional[logging.Formatter] = None,
) -> CompressingRotatingFileHandler:
    """
    Create a rotating file handler with compression.

    Args:
        log_file: Path to the log file
        max_bytes: Maximum file size in bytes before rotation (default: 10MB)
        backup_count: Number of backup files to keep (default: 10)
        compress: Whether to compress rotated files (default: True)
        formatter: Log formatter to use (default: None)

    Returns:
        CompressingRotatingFileHandler instance
    """
    # Ensure the log directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Create the handler
    handler = CompressingRotatingFileHandler(
        filename=log_file, maxBytes=max_bytes, backupCount=backup_count, compress=compress, encoding="utf-8"
    )

    # Set the formatter if provided
    if formatter:
        handler.setFormatter(formatter)

    return handler
