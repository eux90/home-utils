"""parse whatsapp images and set shooting date from filename.

but only if it is not already setor if it is not matching with the filename date
"""

import re
import json
import piexif
import argparse
from pathlib import Path
from datetime import datetime, timezone
from PIL import Image
from ffmpeg import FFmpeg
import logging
from zoneinfo import ZoneInfo

default_logging_level = logging.INFO

# Set up logger to log both to terminal and to a file
logger = logging.getLogger(Path(__file__).stem)
logger.setLevel(default_logging_level)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(default_logging_level)
console_formatter = logging.Formatter("%(levelname)s: %(message)s")
console_handler.setFormatter(console_formatter)

# File handler
file_handler = logging.FileHandler(f"{Path(__file__).stem}.log", encoding="utf-8")
file_handler.setLevel(logging.WARNING)
file_formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
file_handler.setFormatter(file_formatter)

# Add handlers to logger
logger.handlers.clear()
logger.addHandler(console_handler)
logger.addHandler(file_handler)


def telegram_images_parser(file: Path, match: re.Match):
    """
    Parse Telegram image files and set shooting date from filename if not already set or if it does not match the date in the filename.
    """

    # Extract date from filename
    date_str = match.group(1)
    time_str = match.group(2)
    date_obj = datetime.strptime(date_str + time_str, "%Y%m%d%H%M%S")

    logger.info(f"Processing file: {file} with date from filename {date_obj}")

    # Open image and check EXIF data
    with Image.open(file) as img:
        exif_bytes = img.info.get("exif", b"")
        exif_data = piexif.load(exif_bytes) if exif_bytes else {"Exif": {}}

        # Get shooting date (Exif tag 36867 corresponds to DateTimeOriginal)
        date_time_original = exif_data.get("Exif", {}).get(36867)

        if date_time_original:
            # compare year month day with the date in the filename
            date_time_original_str = (
                date_time_original.decode("utf-8").strip().rstrip("\x00")
            )
            date_time = datetime.strptime(date_time_original_str, "%Y:%m:%d %H:%M:%S")
            if date_time != date_obj:
                logger.warning(
                    f"Shooting date already set to {date_time} for: {file.name} is not matching with filename date {date_obj} please evaluate manually..."
                )
            else:
                logger.info(
                    f"Shooting date already set to {date_time} for: {file.name} is matching with filename date {date_obj} skipping..."
                )
            return
        # Set shooting date to extracted date
        new_date_str = date_obj.strftime("%Y:%m:%d %H:%M:%S")
        exif_data["Exif"][36867] = new_date_str
        exif_bytes = piexif.dump(exif_data)
        # Save image with updated metadata
        img.save(file, format=img.format, exif=exif_bytes)
        logger.info(f"Updated shooting date for: {file.name} to {new_date_str}")


def wa_images_parser(file: Path, match: re.Match):
    """
    Parse WhatsApp image files and set shooting date from filename if not already set or if it does not match the date in the filename.
    """

    # Extract date from filename
    date_str = match.group(1)
    date_obj = datetime.strptime(date_str, "%Y%m%d")

    logger.info(f"Processing file: {file} with date from filename {date_obj}")

    # Open image and check EXIF data
    with Image.open(file) as img:
        exif_bytes = img.info.get("exif", b"")
        exif_data = piexif.load(exif_bytes) if exif_bytes else {"Exif": {}}

        # Get shooting date (Exif tag 36867 corresponds to DateTimeOriginal)
        date_time_original = exif_data.get("Exif", {}).get(36867)

        if date_time_original:
            # compare year month day with the date in the filename
            date_time_original_str = (
                date_time_original.decode("utf-8").strip().rstrip("\x00")
            )
            # print(f"Original shooting date: {date_time_original} str: {date_time_original_str} for: {file.name}")
            date_time = datetime.strptime(date_time_original_str, "%Y:%m:%d %H:%M:%S")
            if (
                date_time.year != date_obj.year
                or date_time.month != date_obj.month
                or date_time.day != date_obj.day
            ):
                logger.warning(
                    f"Shooting date already set to {date_time} for: {file.name} is not matching with filename date {date_obj} please evaluate manually..."
                )
            else:
                logger.info(
                    f"Shooting date already set to {date_time} for: {file.name} is matching with filename date {date_obj} skipping..."
                )
            return

        # Set shooting date to extracted date at 00:00
        new_date_str = date_obj.strftime("%Y:%m:%d 00:00:00")
        exif_data["Exif"][36867] = new_date_str
        exif_bytes = piexif.dump(exif_data)

        # Save image with updated metadata
        img.save(file, format=img.format, exif=exif_bytes)
        logger.info(f"Updated shooting date for: {file.name} to {new_date_str}")


def telegram_videos_parser(file: Path, match: re.Match):
    """
    Parse Telegram video files and set creation date from filename if not already set or if it does not match the date in the filename.
    This function uses ffprobe to extract metadata and ffmpeg to update the creation time.
    """

    # Extract date from filename
    date_str = match.group(1)
    time_str = match.group(2)
    date_obj = datetime.strptime(date_str + time_str, "%Y%m%d%H%M%S").replace(
        tzinfo=ZoneInfo("Europe/Rome")
    )

    logger.info(f"Processing file: {file} with date from filename {date_obj}")

    ffprobe = FFmpeg(executable="ffprobe").input(
        str(file), print_format="json", show_streams=None
    )

    media = json.loads(ffprobe.execute())
    if not media or "streams" not in media:
        logger.error(f"No media info found for {file.name} this should not happen")
        return

    creation_time = None
    # check if creation time is present at least in one of the streams
    for stream in media["streams"]:
        if "tags" in stream and "creation_time" in stream["tags"]:
            creation_time = stream["tags"]["creation_time"]
            break

    # check if creation time is matching with the date from the filename
    # if not, print a warning
    if creation_time:
        creation_time = datetime.fromisoformat(creation_time.replace("Z", "+00:00"))
        if creation_time != date_obj:
            logger.warning(
                f"Creation date {creation_time} for {file.name} is not matching with filename date {date_obj} please evaluate manually..."
            )
        else:
            logger.info(
                f"Creation date {creation_time.date()} for {file.name} is matching with filename date {date_obj.date()} skipping..."
            )
        return
    else:
        # none of the streams has a creation time, set it to the date from the filename for all streams
        iso_time_str = date_obj.isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
        for stream in media["streams"]:
            stream["tags"]["creation_time"] = iso_time_str
        # write the new metadata to a copy of the file
        copy_file = file.with_suffix(".copy" + file.suffix)
        ffmpeg = (
            FFmpeg(executable="ffmpeg")
            .input(str(file))
            .output(
                str(copy_file),
                codec="copy",
                map="0",
                metadata=f"creation_time={iso_time_str}",
                y=None,  # overwrite the output file if it exists
            )
        )
        ffmpeg.execute()
        # remove the original file and rename the new one as the original
        copy_file.replace(file)
        # print the new creation time
        logger.info(f"Updated creation time to {iso_time_str} for {file.name}")


def wa_videos_parser(file: Path, match: re.Match):
    """Parse WhatsApp video files and set creation date from filename if not already set or if it does not match the date in the filename.
    This function uses ffprobe to extract metadata and ffmpeg to update the creation time.
    """

    # Extract date from filename
    date_str = match.group(1)
    date_obj = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=ZoneInfo("Europe/Rome"))

    logger.info(f"Processing file: {file} with date from filename {date_obj}")

    ffprobe = FFmpeg(executable="ffprobe").input(
        str(file), print_format="json", show_streams=None
    )

    media = json.loads(ffprobe.execute())
    if not media or "streams" not in media:
        logger.error(f"No media info found for {file.name} this should not happen")
        return

    creation_time = None
    # check if creation time is present at least in one of the streams
    for stream in media["streams"]:
        if "tags" in stream and "creation_time" in stream["tags"]:
            creation_time = stream["tags"]["creation_time"]
            break

    # check if creation time is matching with the date from the filename
    # if not, print a warning
    if creation_time:
        creation_time = datetime.fromisoformat(creation_time.replace("Z", "+00:00"))
        if (
            creation_time.year != date_obj.year
            or creation_time.month != date_obj.month
            or creation_time.day != date_obj.day
        ):
            logger.warning(
                f"Creation date {creation_time} for {file.name} is not matching with filename date {date_obj} please evaluate manually..."
            )
        else:
            logger.info(
                f"Creation date {creation_time.date()} for {file.name} is matching with filename date {date_obj.date()} skipping..."
            )
        return
    else:
        # none of the streams has a creation time, set it to the date from the filename for all streams
        iso_time_str = date_obj.isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
        for stream in media["streams"]:
            stream["tags"]["creation_time"] = iso_time_str
        # write the new metadata to a copy of the file
        copy_file = file.with_suffix(".copy" + file.suffix)
        ffmpeg = (
            FFmpeg(executable="ffmpeg")
            .input(str(file))
            .output(
                str(copy_file),
                codec="copy",
                map="0",
                metadata=f"creation_time={iso_time_str}",
                y=None,  # overwrite the output file if it exists
            )
        )
        ffmpeg.execute()
        # remove the original file and rename the new one as the original
        copy_file.replace(file)
        # print the new creation time
        logger.info(f"Updated creation time to {iso_time_str} for {file.name}")


def main():
    parser = argparse.ArgumentParser(
        description="Parse WhatsApp images and set shooting date from filename."
    )
    parser.add_argument(
        "-f",
        "--folder",
        type=Path,
        help="Path to the folder containing images",
        required=True,
    )
    parser.add_argument(
        "-s",
        "--source",
        choices=["whatsapp", "telegram"],
        help="Source of the images",
        default="whatsapp",
    )
    parser.add_argument(
        "-t",
        "--type",
        choices=["video", "image"],
        help="Type of the media",
        default="image",
    )
    args = parser.parse_args()

    folder_path = args.folder

    if not folder_path.is_dir():
        raise ValueError(f"Provided path {folder_path} is not a directory.")

    # Define the filename pattern
    if args.type == "image" and args.source == "whatsapp":
        pattern = re.compile(r"IMG-(\d{8})-WA.*$")
    elif args.type == "video" and args.source == "whatsapp":
        pattern = re.compile(r"VID-(\d{8})-WA.*$")
    elif args.type == "image" and args.source == "telegram":
        pattern = re.compile(r"IMG_(\d{8})_(\d{6})_.*$")
    elif args.type == "video" and args.source == "telegram":
        pattern = re.compile(r"VID_(\d{8})_(\d{6})_.*$")
    else:
        raise ValueError("Invalid combination of type and source.")

    for file in folder_path.iterdir():
        if not file.is_file():
            logger.info(f"Skipping non-file: {file.name}")
            continue
        match = pattern.match(file.name)
        if not match:
            logger.warning(f"Filename does not follow pattern: {file.name}")
            continue

        if args.type == "image" and args.source == "whatsapp":
            wa_images_parser(file, match)
        elif args.type == "video" and args.source == "whatsapp":
            wa_videos_parser(file, match)
        elif args.type == "image" and args.source == "telegram":
            telegram_images_parser(file, match)
        elif args.type == "video" and args.source == "telegram":
            telegram_videos_parser(file, match)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise
