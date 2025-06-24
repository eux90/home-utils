import logging
from typing import Union
import piexif
from piexif import InvalidImageDataError
import argparse
from pathlib import Path
import shutil
from PIL import Image
import imagehash
import json
import re
import datetime
from zoneinfo import ZoneInfo

IMAGE_EXTENSIONS = {'.JPG', '.jpeg', '.PNG', '.jpg', '.gif', '.png', '.JPEG'}
VIDEO_EXTENSIONS = {'.MP4', '.avi', '.mp4', '.3gp'}
OTHER_EXTENSIONS = {'.json', '.MP', '.html'}
ALL_EXPECTED_EXTENSIONS = IMAGE_EXTENSIONS.union(VIDEO_EXTENSIONS).union(OTHER_EXTENSIONS)

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

def _hamming_distance(chaine1: str, chaine2: str) -> int:
    """Calculate the Hamming distance between two strings."""
    return sum(c1 != c2 for c1, c2 in zip(chaine1, chaine2))

def _get_all_extensions(folder_path: Path):
    """
    Find all unique file extensions found in the specified folder.
    
    Args:
        folder_path (Path): The path to the folder to search for files.
    """
    extensions = set()
    for file_path in folder_path.rglob("*"):
        if file_path.is_file():
            extensions.add(file_path.suffix)
    return extensions

def check_missing_extensions(media_folder: Path):
    """
    Check if there are any missing expected file extensions in the current directory.
    
    Args:
        media_path (Path): The path to the media folder containing photos.
    Raises:
        FileNotFoundError: If the specified media folder does not exist or is not a directory. 
        ValueError: If any expected file extensions are missing in the media path.
    """
    
    if not media_folder.is_dir():
        raise FileNotFoundError(f"The specified media folder '{media_folder}' does not exist or is not a directory.")
    
    current_extensions = _get_all_extensions(media_folder)
    if not current_extensions.issubset(ALL_EXPECTED_EXTENSIONS):
        missing_extensions = current_extensions.difference(ALL_EXPECTED_EXTENSIONS)
        raise ValueError(f"The following file extensions are not expected in the media path '{media_folder}': {missing_extensions}. "
                         f"Expected extensions are: {ALL_EXPECTED_EXTENSIONS}. ")

def generate_media_infos(media_folder: Path, media_info_file: Path):
    """
    Generate media information from the specified media path and save it to a JSON file.
    
    Args:
        media_path (Path): The path to the media folder containing photos.
        media_info_file (Path): The path to JSON file to be created.
    Raises:
        ValueError: If the specified media path does not exist or is not a directory.
    """
    if not media_folder.is_dir():
        raise ValueError(f"The specified media path '{media_folder}' does not exist or is not a directory.")
    
    # create missing folders in media_info_file path
    media_info_file.parent.mkdir(parents=True, exist_ok=True)
    
    export_info = dict()
    
    for file_path in media_folder.rglob("*"):
        if not file_path.is_file():
            continue
        
        # Skip files in "Cestino" directory
        if "Cestino" in file_path.parts:
            logger.info(f"Skipping file in 'Cestino' directory: {file_path}")
            continue
        
        # Skip files that contain "modificato" in their name
        if "modificato" in file_path.name:
            logger.info(f"Skipping file with 'modificato' in name: {file_path.name}")
            continue
        
        # Check if the file is an image based on its extension
        if file_path.suffix not in IMAGE_EXTENSIONS:
            logger.info(f"Skipping non-image file: {file_path.name}")
            continue
        
        # ensure no duplicate files are processed
        if file_path.name in export_info:
            logger.warning(f"Duplicate file found: {file_path.name} first found at {export_info[file_path.name]}")
            continue
        
        # Store the file info in the export_info dictionary        
        export_info[file_path.name] = {
            'path': str(file_path),
            'hashes': {
                'average': str(imagehash.average_hash(Image.open(file_path))),
                'perceptual': str(imagehash.phash(Image.open(file_path))),
                'difference': str(imagehash.dhash(Image.open(file_path))),
                'wavelet': str(imagehash.whash(Image.open(file_path))),
                'colorhash': str(imagehash.colorhash(Image.open(file_path))),
            }
        }
    
    # Save the export_info dictionary to a JSON file
    with open(media_info_file, "w", encoding="utf-8") as json_file:
        json.dump(export_info, json_file, indent=4, ensure_ascii=False)
    logger.info(f"Export information saved to {media_info_file}")

def find_missing_media(src_media_info: Path, dst_media_info: Path, output_file: Path):
    """
    Find missing media files in the destination folder based on the source media info file.
    
    Args:
        src_media_info (Path): The path to the media info file containing source media information.
        dst_media_info (Path): The path to the media info file containing destination media information.
        output_file (Path): The path to the file that will contain the list of missing media.
    Raises:
        FileNotFoundError: If the specified source or destination media info file does not exist or is not a file.
        ValueError: If there are duplicate media names in the source data.
    """
    
    if not src_media_info.is_file():
        raise FileNotFoundError(f"The specified source media info file '{src_media_info}' does not exist or is not a file.")
    if not dst_media_info.is_file():
        raise FileNotFoundError(f"The specified destination media info file '{dst_media_info}' does not exist or is not a file.")
    
    # create missing folders in output_file path
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with src_media_info.open(mode='r', encoding='utf-8') as src_file:
        src_data = json.load(src_file)
    
    with dst_media_info.open( mode="r", encoding="utf-8") as dst_file:
        dst_data = json.load(dst_file)
    
    missing_media = {}
    
    for name, info in src_data.items():
        if name not in dst_data:
            if name in missing_media:
                raise ValueError(f"Duplicate media name found in source data: {name}. This should not happen.")
            missing_media[name] = {
                'path': info['path']
            }
        else:
            # Check if hashes match
            src_hashes = info['hashes']
            dst_hashes = dst_data[name]['hashes']
            mismatching_hashes = []
            total_distance = 0
            if src_hashes['average'] != dst_hashes['average']:
                mismatching_hashes.append('average')
                total_distance += _hamming_distance(src_hashes['average'], dst_hashes['average'])
            if src_hashes['perceptual'] != dst_hashes['perceptual']:
                mismatching_hashes.append('perceptual')
                total_distance += _hamming_distance(src_hashes['perceptual'], dst_hashes['perceptual'])
            if src_hashes['difference'] != dst_hashes['difference']:
                mismatching_hashes.append('difference')
                total_distance += _hamming_distance(src_hashes['difference'], dst_hashes['difference'])
            if src_hashes['wavelet'] != dst_hashes['wavelet']:
                mismatching_hashes.append('wavelet')
                total_distance += _hamming_distance(src_hashes['wavelet'], dst_hashes['wavelet'])
            if src_hashes['colorhash'] != dst_hashes['colorhash']:
                mismatching_hashes.append('colorhash')
                total_distance += _hamming_distance(src_hashes['colorhash'], dst_hashes['colorhash'])
            
            if mismatching_hashes and total_distance > 10:
                logger.warning(f"Hash mismatch for {name}: {', '.join(mismatching_hashes)} hashes do not match and total distance is {total_distance}.")
                for hash_type in mismatching_hashes:
                    logger.warning(f"Source {hash_type} hash: {src_hashes[hash_type]}, Destination {hash_type} hash: {dst_hashes[hash_type]}")
            else:
                logger.info(f"Media {name} found in both source and destination with matching hashes.")
                
    with output_file.open(mode="w", encoding="utf-8") as media_info_file_json:
        json.dump(missing_media, media_info_file_json, indent=4, ensure_ascii=False)
    
    logger.info(f"Missing media information saved to {output_file}")

def _get_google_metadata_file(media_path: Path) -> Union[Path, None]:
    """ Get the associated metadata file for a given media file.
    Args:
        media_path (Path): The path to the media file.
    Returns:
        Union[Path, None]: The path to the metadata file if found, otherwise None.
    Raises:
        FileNotFoundError: If the specified media path does not exist or is not a file.
        RuntimeError: If multiple metadata files are found for the media file.
    """
    
    if not media_path.is_file():
        raise FileNotFoundError(f"The specified media path '{media_path}' does not exist or is not a file.")
    
    # get the associated metadata file for the media file
    file_name: str = media_path.name
    # get a pattern using re for all files starting with file_name and ending with suffix .json
    pattern = re.compile(rf"^{re.escape(file_name)}.*\.json$")
    match_count = 0
    metadata_file = None
    for file in media_path.parent.iterdir():
        if pattern.match(file.name):
            match_count += 1
            metadata_file = file
    if match_count > 1:
        raise RuntimeError(f"Multiple metadata files found for {file_name}: {match_count} files match the pattern {pattern.pattern}.")
    
    return metadata_file

def _check_geodata(supplemental_metadata: dict) -> None:
    
    file_name = supplemental_metadata['title']
    latitude = supplemental_metadata['geoData']['latitude']
    longitude = supplemental_metadata['geoData']['longitude']
    altitude = supplemental_metadata['geoData']['altitude']
    latitude_span = supplemental_metadata['geoData']['latitudeSpan']
    longitude_span = supplemental_metadata['geoData']['longitudeSpan']
    
    if latitude != longitude != altitude != latitude_span != longitude_span != 0.0:
        #TODO: if you find geodata think about putting it in the image metadata
        raise ValueError(f"Geodata for {file_name} is available: Latitude: {latitude}, Longitude: {longitude}, Altitude: {altitude}, "
                    f"Latitude Span: {latitude_span}, Longitude Span: {longitude_span}.")

def _get_datetime_from_google_metadata(supplemental_metadata: dict) -> datetime.datetime:
    if not str(supplemental_metadata['photoTakenTime']['formatted']).endswith('UTC'):
        raise ValueError(f"Expected 'formatted' field in 'photoTakenTime' to end with 'UTC', but got: {supplemental_metadata['photoTakenTime']['formatted']}")
    date_time = datetime.datetime.fromtimestamp(int(supplemental_metadata['photoTakenTime']['timestamp']), tz=datetime.timezone.utc)
    # convert to Europe/Rome timezone
    return date_time.astimezone(tz=ZoneInfo('Europe/Rome'))

def _check_img_datetime_exists(img_path: Path) -> bool:
    """
    Check if the metadata file exists for the given media file.
    
    Args:
        media_path (Path): The path to the media file.
    
    Returns:
        bool: True if the media has date and time metadata, False otherwise.
    """
    if not img_path.is_file():
        raise FileNotFoundError(f"The specified media path '{img_path}' does not exist or is not a file.")
    
    with Image.open(img_path, mode='r') as img:
        exif_bytes = img.info.get('exif', b"")
        exif_data = piexif.load(exif_bytes) if exif_bytes else {"Exif": {}}

        # Get shooting date (Exif tag 36867 corresponds to DateTimeOriginal)
        date_time_original = exif_data.get("Exif", {}).get(36867)
        if not date_time_original:
            logger.info(f"No DateTimeOriginal found in metadata for image {img_path}.")
            return False
    return True

def _set_img_datetime(img_path: Path, datetime_taken: datetime.datetime):
    with Image.open(img_path) as img:
        exif_bytes = img.info.get("exif", b"")
        exif_data = piexif.load(exif_bytes) if exif_bytes else {"Exif": {}}
        new_date_str = datetime_taken.strftime("%Y:%m:%d %H:%M:%S")
        exif_data["Exif"][36867] = new_date_str
        try:
            exif_bytes = piexif.dump(exif_data)
        except InvalidImageDataError as e:
            logger.error(f"Failed to dump EXIF data for {img_path}: {e}")
            return
        # Save image with updated metadata
        img.save(img_path, format=img.format, exif=exif_bytes)
        logger.info(f"Updated shooting date for: {img_path} to {new_date_str}")
    

def copy_and_set_google_metadata(media_info_file: Path, output: Path):
    """
    Check metadata of the media files listed in the provided JSON file.
    
    Args:
        media_info_file (Path): The path to the media info JSON file.
    """
    if not media_info_file.is_file():
        raise FileNotFoundError(f"The specified media info file '{media_info_file}' does not exist or is not a file.")
    
    # create missing folders in output path
    output.mkdir(parents=True, exist_ok=True)
    
    with media_info_file.open(mode='r', encoding='utf-8') as media_file:
        media_data = json.load(media_file)
        for media_name, media_data in media_data.items():
            # copy image to output folder preserving metadata
            copied_media_path: Path = output.joinpath(media_name)
            shutil.copy2(Path(media_data['path']), copied_media_path)
            if not _check_img_datetime_exists(copied_media_path):                
                metadata_file = _get_google_metadata_file(Path(media_data['path']))
                
                if not metadata_file:
                    logger.warning(f"Supplemental metadata file does not exist for {media_name}.")
                    continue
                with metadata_file.open(mode='r', encoding='utf-8') as meta_file:
                    supplemental_metadata = json.load(meta_file)
                # check geodata
                _check_geodata(supplemental_metadata)
                datetime_taken = _get_datetime_from_google_metadata(supplemental_metadata)
                # set datetime metadata to the copied image
                _set_img_datetime(copied_media_path, datetime_taken)

def check_img_missing_datetime(media_path: Path):
    """
    Check if the media files have missing datetime metadata.
    
    Args:
        media_path (Path): The path to the media folder containing photos.
    Raises:
        FileNotFoundError: If the specified media path does not exist or is not a directory.
    """
    if not media_path.is_dir():
        raise FileNotFoundError(f"The specified media path '{media_path}' does not exist or is not a directory.")
    
    for file_path in media_path.rglob("*"):
        if file_path.is_file() and file_path.suffix in IMAGE_EXTENSIONS:
            if not _check_img_datetime_exists(file_path):
                logger.error(f"Missing datetime metadata for image: {file_path}")

def main():
    """ Main function to run the gphoto_parser module."""
    parser = argparse.ArgumentParser(
        description="Parse gphoto export data and extract relevant information."
    )
    parser.add_argument(
        "-g",
        "--generate-media-infos",
        nargs=2,
        type=Path,
        metavar=("MEDIA_PATH", "OUTPUT_MEDIA_INFO_FILE"),
        help="Generate media information from the specified media path and save it to a JSON file.",
        required=False
    )
    parser.add_argument(
        "-f",
        "--find-missing",
        nargs=3,
        type=Path,
        metavar=("SOURCE_MEDIA_INFO_FILE", "DESTINATION_MEDIA_INFO_FILE", "OUTPUT_FILE"),
        help="Find missing media between source and destination media info files and save the results to a JSON file.",
        required=False
    )
    parser.add_argument(
        "-c",
        "--copy-with-metadata",
        nargs=2,
        type=Path,
        metavar=("MEDIA_INFO_FILE", "OUTPUT_FOLDER"),
        help="Copy media files to a new location and update their metadata. ",
        required=False
    )
    parser.add_argument(
        "--check-missing-datetime",
        type=Path,
        metavar="MEDIA_PATH",
        help="Check if the media files have missing datetime metadata.",
        required=False
    )
        
    
    args = parser.parse_args()
    
    if args.generate_media_infos:
        # Check if the media path is valid and contains expected file extensions
        check_missing_extensions(args.generate_media_infos[0])
        # Generate media information and save it to the specified media_info_file file
        generate_media_infos(args.generate_media_infos[0], args.generate_media_infos[1])
    elif args.find_missing:
        # Find missing media files and save the results to the specified media_info_file file
        find_missing_media(args.find_missing[0], args.find_missing[1], args.find_missing[2])
    elif args.copy_with_metadata:
        copy_and_set_google_metadata(args.copy_with_metadata[0], args.copy_with_metadata[1])
    elif args.check_missing_datetime:
        # Check if the media files have missing datetime metadata
        check_img_missing_datetime(args.check_missing_datetime)
    else:
        parser.print_help()
        logger.error("No valid arguments provided. Use -h for help.")
        
    
    
if __name__ == "__main__":
    main()