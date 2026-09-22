"""
Geohash encoding and utilities for location representation.
"""
import pandas as pd
from typing import Optional, Tuple

import geohash2 as geohash


class GeohashEncoder:
    """
    Encode/decode locations using Geohash.
    
    Geohash provides a hierarchical spatial data structure
    that subdivides space into buckets of grid shape.
    """

    def __init__(self, precision: int = 6):
        """
        Initialize encoder.
        
        Args:
            precision: Geohash precision (1-12).
                      Higher = more precise = smaller area.
                      6 ≈ 1.2km x 0.6km
        """
        self.precision = precision

    def encode(self, lat: float, lng: float) -> str:
        """
        Encode latitude/longitude to geohash string.
        
        Args:
            lat: Latitude (-90 to 90)
            lng: Longitude (-180 to 180)
            
        Returns:
            Geohash string
        """
        return geohash.encode(lat, lng, precision=self.precision)

    def decode(self, hash_string: str) -> Tuple[float, float]:
        """
        Decode geohash to center coordinates.
        
        Args:
            hash_string: Geohash string
            
        Returns:
            Tuple of (latitude, longitude)
        """
        return geohash.decode(hash_string)

    def decode_bbox(self, hash_string: str) -> dict:
        """
        Get bounding box of a geohash.
        
        Args:
            hash_string: Geohash string
            
        Returns:
            Dictionary with min/max lat/lng
        """
        bbox = geohash.decode_bbox(hash_string)
        return {
            "min_lat": bbox[0],
            "min_lng": bbox[1],
            "max_lat": bbox[2],
            "max_lng": bbox[3]
        }

    def neighbors(self, hash_string: str) -> dict:
        """
        Get all neighboring geohashes.
        
        Args:
            hash_string: Geohash string
            
        Returns:
            Dictionary with direction names as keys
        """
        return geohash.neighbors(hash_string)

    def expand(self, hash_string: str, precision: int = None) -> list:
        """
        Expand geohash to include neighbors.
        
        Args:
            hash_string: Center geohash
            precision: New precision (default: current + 1)
            
        Returns:
            List of geohash strings covering the area
        """
        pass  # TODO: Implement

    def encode_dataframe(self, df: pd.DataFrame, lat_col: str, lng_col: str) -> pd.DataFrame:
        """
        Add geohash column to DataFrame.
        
        Args:
            df: Input DataFrame
            lat_col: Name of latitude column
            lng_col: Name of longitude column
            
        Returns:
            DataFrame with new 'geohash' column
        """
        import pandas as pd
        result = df.copy()
        result['geohash'] = result.apply(
            lambda row: self.encode(row[lat_col], row[lng_col]), 
            axis=1
        )
        return result


def privacy_encode(
    lat: float, 
    lng: float, 
    precision: int = 6
) -> str:
    """
    Encode location for privacy-preserving storage.
    
    Args:
        lat: Latitude
        lng: Longitude
        precision: Geohash precision (lower = more privacy)
        
    Returns:
        Geohash string
    """
    return geohash.encode(lat, lng, precision=precision)


def calculate_k_anonymity(
    geohashes: list,
    k: int = 5
) -> dict:
    """
    Check k-anonymity for a set of locations.
    
    Args:
        geohashes: List of geohash strings
        k: Minimum group size for anonymity
        
    Returns:
        Dictionary with statistics
    """
    from collections import Counter
    counts = Counter(geohashes)
    
    anonymized = sum(1 for c in counts.values() if c >= k)
    total = len(counts)
    
    return {
        "total_geohashes": total,
        "anonymized_count": anonymized,
        "anonymized_ratio": anonymized / total if total > 0 else 0,
        "k": k,
        "is_k_anonymous": all(c >= k for c in counts.values())
    }
