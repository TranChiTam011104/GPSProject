#!/usr/bin/env python3
"""Download Microsoft GeoLife dataset."""
import os
import sys
import zipfile
import urllib.request
from pathlib import Path
from tqdm import tqdm


DATASET_URL = "https://download.microsoft.com/download/F/4/8/F4894AA4-4C9A-4D60-A32D-200A33DEE70F/Geolife%20Trajectories%201.3.zip"
DATA_DIR = Path(__file__).parent.parent / "data" / "raw" / "geolife"


class DownloadProgressBar(tqdm):
    """Progress bar for urllib downloads."""
    
    def update_to(self, blocks=1, block_size=1, total_size=None):
        """Update progress bar."""
        if total_size is not None:
            self.total = total_size
        self.update(blocks * block_size - self.n)


def download_url(url: str, output_path: Path) -> None:
    """
    Download file from URL with progress bar.
    
    Args:
        url: URL to download
        output_path: Where to save the file
    """
    with DownloadProgressBar(
        unit="B",
        unit_scale=True,
        miniters=1,
        desc=output_path.name
    ) as progress_bar:
        urllib.request.urlretrieve(
            url,
            filename=str(output_path),
            reporthook=progress_bar.update_to
        )


def extract_zip(zip_path: Path, extract_to: Path) -> None:
    """
    Extract zip file with progress.
    
    Args:
        zip_path: Path to zip file
        extract_to: Directory to extract to
    """
    print(f"Extracting {zip_path.name} to {extract_to}...")
    
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        members = zip_ref.namelist()
        for member in tqdm(members, desc="Extracting"):
            zip_ref.extract(member, extract_to)


def main():
    """Main download function."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    zip_path = DATA_DIR / "geolife_dataset.zip"
    
    if not zip_path.exists():
        print(f"Downloading GeoLife dataset from Microsoft...")
        print(f"URL: {DATASET_URL}")
        print(f"Destination: {zip_path}")
        print()
        print("NOTE: This dataset is ~300MB. It may take a while to download.")
        
        try:
            download_url(DATASET_URL, zip_path)
        except Exception as e:
            print(f"Error downloading: {e}")
            print()
            print("Manual download instructions:")
            print("1. Visit https://www.microsoft.com/en-us/research/project/geolife/")
            print("2. Download the dataset")
            print(f"3. Place the zip file at: {zip_path}")
            sys.exit(1)
    else:
        print(f"Dataset already downloaded: {zip_path}")
    
    # Extract
    if not (DATA_DIR / "Geolife Trajectories 1.3").exists():
        extract_zip(zip_path, DATA_DIR)
    else:
        print("Dataset already extracted")
    
    print()
    print("GeoLife dataset setup complete!")
    print(f"Location: {DATA_DIR}")


if __name__ == "__main__":
    main()
