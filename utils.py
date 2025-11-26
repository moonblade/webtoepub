import logging
import os
import shutil

def custom_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)  # Set your desired logging level

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"  # Customize date format as needed
    )

    handler = logging.StreamHandler() # Or a FileHandler if you want to write to a file
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger

def sanitize_filename(filename: str) -> str:
    """
    Sanitizes a filename by replacing invalid characters.
    """
    invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for char in invalid_chars:
        filename = filename.replace(char, '-')
    return filename

def delete_entry_files(entry_title: str, feed_title: str, download_path: str):
    """
    Deletes all files related to an entry (html, cleaned, epub).
    """
    logger = custom_logger(__name__)
    feed_path = os.path.join(download_path, sanitize_filename(feed_title))
    sanitized_title = sanitize_filename(entry_title)
    
    files_to_delete = [
        os.path.join(feed_path, "html", f"{sanitized_title}.html"),
        os.path.join(feed_path, "cleaned", f"{sanitized_title}.html"),
        os.path.join(feed_path, f"{sanitized_title}.epub")
    ]
    
    deleted_count = 0
    for file_path in files_to_delete:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Deleted file: {file_path}")
                deleted_count += 1
            except Exception as e:
                logger.error(f"Error deleting file {file_path}: {e}")
    
    return deleted_count
