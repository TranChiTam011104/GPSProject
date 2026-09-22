"""
Privacy-preserving location encoding and anonymization.
"""
import hashlib
from typing import List, Dict, Tuple
from dataclasses import dataclass
import geohash2 as geohash


@dataclass
class AnonymizedLocation:
    """Privacy-preserving location representation."""
    geohash: str
    precision: int
    cluster_size: int  # Number of points in same geohash


class PrivacyAnonymizer:
    """
    Anonymize location data for privacy protection.
    
    Techniques:
    - Geohash encoding (spatial generalization)
    - k-anonymity (minimum group size)
    - Differential privacy (noise addition)
    """

    def __init__(
        self,
        precision: int = 6,
        k_threshold: int = 5
    ):
        """
        Initialize anonymizer.
        
        Args:
            precision: Geohash precision (1-12)
            k_threshold: Minimum k for k-anonymity
        """
        self.precision = precision
        self.k_threshold = k_threshold

    def encode(self, lat: float, lng: float) -> str:
        """
        Encode location as geohash.
        
        Args:
            lat: Latitude
            lng: Longitude
            
        Returns:
            Geohash string
        """
        return geohash.encode(lat, lng, precision=self.precision)

    def anonymize_location(
        self, 
        lat: float, 
        lng: float
    ) -> AnonymizedLocation:
        """
        Anonymize a single location.
        
        Args:
            lat: Latitude
            lng: Longitude
            
        Returns:
            AnonymizedLocation object
        """
        geohash_str = self.encode(lat, lng)
        
        return AnonymizedLocation(
            geohash=geohash_str,
            precision=self.precision,
            cluster_size=1
        )

    def anonymize_batch(
        self, 
        locations: List[Tuple[float, float]]
    ) -> List[AnonymizedLocation]:
        """
        Anonymize multiple locations.
        
        Args:
            locations: List of (lat, lng) tuples
            
        Returns:
            List of AnonymizedLocation objects
        """
        # Count geohash occurrences
        from collections import Counter
        geohash_counts = Counter()
        
        for lat, lng in locations:
            gh = self.encode(lat, lng)
            geohash_counts[gh] += 1
        
        # Create anonymized locations
        results = []
        seen = set()
        
        for lat, lng in locations:
            gh = self.encode(lat, lng)
            
            if gh not in seen:
                results.append(AnonymizedLocation(
                    geohash=gh,
                    precision=self.precision,
                    cluster_size=geohash_counts[gh]
                ))
                seen.add(gh)
        
        return results

    def check_k_anonymity(
        self, 
        locations: List[str]
    ) -> Tuple[bool, int]:
        """
        Check if locations satisfy k-anonymity.
        
        Args:
            locations: List of geohash strings
            
        Returns:
            Tuple of (is_k_anonymous, min_count)
        """
        from collections import Counter
        counts = Counter(locations)
        
        min_count = min(counts.values()) if counts else 0
        is_k_anonymous = min_count >= self.k_threshold
        
        return is_k_anonymous, min_count

    def generalize_for_k_anonymity(
        self, 
        locations: List[Tuple[float, float]]
    ) -> List[Tuple[str, int]]:
        """
        Generalize locations to achieve k-anonymity.
        
        Reduces precision until k-anonymity is achieved.
        
        Args:
            locations: List of (lat, lng) tuples
            
        Returns:
            List of (geohash, count) tuples
        """
        precision = self.precision
        
        while precision > 1:
            # Count at current precision
            from collections import Counter
            gh_counts = Counter()
            
            for lat, lng in locations:
                gh = geohash.encode(lat, lng, precision=precision)
                gh_counts[gh] += 1
            
            min_count = min(gh_counts.values()) if gh_counts else 0
            
            if min_count >= self.k_threshold:
                return list(gh_counts.items())
            
            precision -= 1
        
        # Return at lowest precision
        return [(gh, count) for gh, count in gh_counts.items()]

    def add_differential_privacy_noise(
        self, 
        lat: float, 
        lng: float, 
        epsilon: float = 1.0
    ) -> Tuple[float, float]:
        """
        Add Laplace noise for differential privacy.
        
        Args:
            lat: Latitude
            lng: Longitude
            epsilon: Privacy parameter (lower = more private)
            
        Returns:
            Tuple of (noisy_lat, noisy_lng)
        """
        import numpy as np
        
        # Scale based on epsilon and geographic scale
        # Adjust these values based on your precision needs
        scale = 0.01 / epsilon  # degrees
        
        noise_lat = np.random.laplace(0, scale)
        noise_lng = np.random.laplace(0, scale)
        
        noisy_lat = lat + noise_lat
        noisy_lng = lng + noise_lng
        
        # Clamp to valid ranges
        noisy_lat = max(-90, min(90, noisy_lat))
        noisy_lng = max(-180, min(180, noisy_lng))
        
        return noisy_lat, noisy_lng

    @staticmethod
    def hash_identifier(user_id: str, salt: str = "") -> str:
        """
        Hash user identifier for pseudonymization.
        
        Args:
            user_id: Original user ID
            salt: Salt for hashing
            
        Returns:
            Hashed ID
        """
        combined = f"{user_id}:{salt}".encode()
        return hashlib.sha256(combined).hexdigest()[:16]


def create_anonymizer(
    precision: int = 6,
    k: int = 5
) -> PrivacyAnonymizer:
    """
    Factory function to create anonymizer.
    
    Args:
        precision: Geohash precision
        k: k-anonymity threshold
        
    Returns:
        PrivacyAnonymizer instance
    """
    return PrivacyAnonymizer(precision=precision, k_threshold=k)
